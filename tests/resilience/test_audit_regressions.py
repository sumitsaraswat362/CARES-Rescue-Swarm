import numpy as np
from src.core.uav import UAV
from src.resilience.agent import Agent
from src.resilience.transport import Packet
from tests.resilience.test_transport import net, run
from tests.resilience.test_agents import agent


def test_arrival_snap_obeys_safety_filter():
    u = UAV(0, [0, 0], {})
    u.motion_filter = lambda proposed, dt: u.pos.copy()
    assert not u.move_towards(np.array([1., 0.]), 10, .1)
    assert np.array_equal(u.pos, [0, 0])


def test_packet_expired_in_flight_never_reaches_application():
    t, received = net(hop_delay_s=2)
    t.send(Packet(0, -1, 'observation', {'id': 'expired'}, 0, 128, 1, .5, (0, -1), (0,)))
    run(t, 0, 40)
    assert not received


def test_same_owner_lease_renewal_propagates():
    a, _, _ = agent()
    a.claims[1] = {'owner': 2, 'bid': 9, 'until': 3}
    a.receive(Packet(2, -2, 'beacon', {'claims': [(1, {'owner': 2, 'bid': 9, 'until': 9})]}, 1), 1)
    assert a.claims[1]['until'] == 9


def test_unknown_ack_cannot_authorize_relay_departure():
    a, _, _ = agent()
    a.replacing = 2
    a.receive(Packet(-1, 0, 'ack', {'id': 'not-a-probe'}, 1), 1)
    assert a.ready_at is None


def test_reassignment_resets_survey_confidence():
    u = UAV(0, [0, 0], {})
    u.detection_confidence = .94
    u.assign_scout_task(2, np.array([10., 0.]), 0)
    assert u.detection_confidence == 0


def test_survey_respects_configured_dwell():
    u = UAV(0, [0, 0], {'sensors': {'survey_time_s': 30}})
    u.assign_scout_task(2, np.array([0., 0.]), 0)
    u.altitude = 30
    for i in range(150):
        u.update(.1, i * .1)
    assert not u.tasks_completed


def test_empty_radio_does_not_claim_perfect_delivery():
    t, _ = net()
    assert t.summary()['hop_pdr_pct'] is None


def test_zero_bandwidth_rejected():
    import pytest
    with pytest.raises(ValueError):
        net(bytes_per_second=0)


def test_relay_altitudes_do_not_collapse_at_ceiling():
    uavs = [UAV(i, [0, 0], {}) for i in range(8)]
    for u in uavs:
        u.assign_relay(np.array([0., 0.]), 0)
        for i in range(400):
            u.update(.1, i*.1)
    altitudes = sorted(u.altitude for u in uavs)
    assert all(b-a >= 5 for a, b in zip(altitudes, altitudes[1:]))


def test_noncanonical_scenario_is_not_silently_empty(tmp_path):
    import pytest
    from src.core.world import World
    path = tmp_path / 'bad.yaml'
    path.write_text('pois: [{id: 1, x: 10, y: 10, priority: 1}]\n')
    with pytest.raises(ValueError, match='Unsupported scenario keys'):
        World(path)


def test_viewers_receive_same_narration_and_measured_altitude():
    from src.server import SimState, serialize_state
    sim = SimState()
    sim.init('scenarios/relay_required.yaml')
    first, second = serialize_state(sim), serialize_state(sim)
    assert first['explain'] and first['explain'] == second['explain']
    assert first['uavs'][0]['altitude'] == sim.mission.uavs[0].altitude


def test_planner_rejects_blocked_endpoint_without_exploring_map():
    from types import SimpleNamespace
    from src.core.world import Obstacle
    from src.resilience.planner import Planner
    planner=Planner(SimpleNamespace(width=1000,height=1000,obstacles=[Obstacle(0,0,50)]))
    assert planner.plan([0,0],[500,500]) == []
    assert not planner.cache


def test_osm_fixture_launch_is_clear_and_requested_fleet_is_loaded():
    from src.resilience.runtime import Runtime
    runtime=Runtime('scenarios/osm_bombay.yaml')
    assert len(runtime.mission.uavs) == 2
    assert len(runtime.tasks) == 1
    assert runtime.mission.world.duration_s == 1800
    assert runtime.planner.clear(runtime.mission.world.launch_pos,runtime.mission.world.launch_pos)


def test_initial_and_hidden_task_deadlines_are_preserved(tmp_path):
    import yaml
    from src.resilience.runtime import Runtime
    config=yaml.safe_load(open('scenarios/relay_required.yaml'))
    config['points_of_interest'][0]['deadline_s']=45
    config['hidden_pois']=[{'id':99,'x':200,'y':200,'priority':1,'deadline_s':60}]
    path=tmp_path/'deadline.yaml'
    path.write_text(yaml.safe_dump(config))
    runtime=Runtime(str(path))
    assert runtime.tasks[config['points_of_interest'][0]['id']].deadline == 45
    assert runtime.mission.world.hidden_pois[0].deadline_s == 60


def test_recharged_retired_relay_can_rejoin():
    from src.core.uav import UAVState
    a,_,_=agent()
    a.retiring=True
    a.uav.state=UAVState.IDLE
    a.tick(1)
    assert not a.retiring
