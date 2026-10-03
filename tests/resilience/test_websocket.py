from fastapi.testclient import TestClient
from src import server


def receive_until(ws, predicate):
    for _ in range(30):
        state = ws.receive_json()
        if predicate(state):
            return state
    raise AssertionError('Expected WebSocket state was not received')


def test_two_viewers_preserve_mission_and_share_commands(monkeypatch):
    sim = server.SimState()
    sim.init('scenarios/relay_required.yaml')
    sim.mission.paused = True
    monkeypatch.setattr(server, 'sim', sim)
    with TestClient(server.app) as client:
        assert client.get('/').status_code == 200
        with client.websocket_connect('/ws') as one:
            initial = one.receive_json()
            with client.websocket_connect('/ws') as two:
                second = two.receive_json()
                assert second['generation'] == initial['generation']
                assert second['sim_time'] == initial['sim_time']
                one.send_json({'action': 'kill_uav', 'uav_id': 0})
                state = receive_until(two, lambda s: s['uavs'][0]['state'] == 'failed')
                assert state['paused']
                one.send_json({'action': 'reset'})
                state = receive_until(two, lambda s: s['generation'] > initial['generation'])
                assert state['world']['name'] == initial['world']['name']
                assert state['uavs'][0]['state'] != 'failed'
                one.send_json({'action': 'pause'})
                paused = receive_until(two, lambda s: s['paused'])
                assert two.receive_json()['sim_time'] == paused['sim_time']
        with client.websocket_connect('/ws') as reconnect:
            assert reconnect.receive_json()['generation'] == state['generation']
    assert sim.clients == 0
