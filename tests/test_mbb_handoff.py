"""Behavioral handoff tests for the runtime used by CLI and web."""
import numpy as np
from tests.resilience.test_agents import agent
from src.core.uav import UAVState
from src.resilience.transport import Packet


def test_predictive_request_before_safe_departure():
    a,events,_=agent();u=a.uav
    u.assign_relay(np.array([0.,0.]),0)
    u.battery.current_wh=u.battery.capacity_wh*.15+1.0
    a.tick(1)
    assert a.request is not None
    assert a.request['depart_by']>1
    assert any(e['event']=='handoff_requested' for e in events)


def test_unverified_replacement_does_not_release_old_relay():
    a,events,_=agent();a.uav.assign_relay(np.array([0.,0.]),0)
    a.request={'old':0,'created':0}
    a.receive(Packet(1,-2,'ready',{'old':0,'proof_at':-50},0),5)
    assert a.uav.state==UAVState.RELAY
    a.receive(Packet(1,-2,'ready',{'old':0,'proof_at':5,'route':[1,-1]},5),5)
    assert a.uav.state==UAVState.RTL
    assert sum(e['event']=='handoff_complete' for e in events)==1
