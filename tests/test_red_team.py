import numpy as np
from types import SimpleNamespace
from src.resilience.evaluation import Evaluator
from src.core.uav import UAV,UAVState


def test_failed_vehicle_does_not_move():
    u=UAV(1,[10,10],{});u.inject_failure('motor_failure',0)
    u.update(1,1)
    assert u.state==UAVState.FAILED
    assert np.array_equal(u.pos,[10,10])


def test_swept_monitor_detects_between_sample_crossing():
    e=Evaluator(minimum=5)
    e.previous={0:np.array([0,10,30]),1:np.array([10,10,30])}
    us=[UAV(0,[10,10],{}),UAV(1,[0,10],{})]
    for u in us:u.altitude=30
    e.sample(us,SimpleNamespace(width=100,height=100),SimpleNamespace(reachable=lambda _:True),1)
    assert e.separation_frames==1
    assert e.min_separation==0
