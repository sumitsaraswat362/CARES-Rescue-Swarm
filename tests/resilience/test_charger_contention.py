import pytest
import numpy as np
from src.resilience.runtime import Runtime
from src.core.uav import UAVState
from src.core.world import RechargeStation

def test_priority_charger_contention():
    r = Runtime('scenarios/earthquake_basic.yaml', 'config/swarm_config.yaml', 42, 'cares')
    m = r.mission
    m.world.recharge_stations = [
        RechargeStation(x=0., y=0., label='pad1'),
        RechargeStation(x=100., y=100., label='pad2')
    ]
    for i in range(3):
        m.uavs[i].pos = np.array([0., 0.])
        m.uavs[i].state = UAVState.RECHARGE
    
    m.uavs[0].battery.current_wh = m.uavs[0].battery.capacity_wh * 0.50
    m.uavs[1].battery.current_wh = m.uavs[1].battery.capacity_wh * 0.10
    m.uavs[2].battery.current_wh = m.uavs[2].battery.capacity_wh * 0.20
    
    r.step()
    
    assert getattr(m.uavs[1], '_charging_allowed', False) == True
    assert getattr(m.uavs[2], '_charging_allowed', False) == False
    assert np.allclose(m.uavs[2].target_pos, np.array([100., 100.]))
    assert getattr(m.uavs[0], '_charging_allowed', False) == False
    assert np.allclose(m.uavs[0].target_pos, np.array([100., 100.]))

    events = [e for e in r.evaluator.events if e.get('event') == 'charger_redirect']
    assert len(events) == 2
    assert events[0]['uav'] == m.uavs[2].id
    assert events[1]['uav'] == m.uavs[0].id

