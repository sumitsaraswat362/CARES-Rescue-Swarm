from src.px4_bridge.health import FlightHealth
from src.px4_bridge.sitl_agent import FlightSession


def test_disarmed_without_flight_cannot_pass():
    h = FlightHealth([0])
    h.observe(0, False, False, 0)
    h.begin_landing(0)
    assert not h.landed(0)


def test_landing_requires_new_fresh_status_from_every_vehicle():
    h = FlightHealth([0, 1])
    for uid in [0, 1]:
        h.observe(uid, True, True, 0)
    assert h.ready(0)
    h.observe(0, False, False, .1)
    h.begin_landing(.2)
    h.observe(1, False, False, .3)
    assert not h.landed(.3)
    h.observe(0, False, False, .4)
    assert h.landed(.4)
    assert not h.landed(2)


def test_offboard_loss_and_missing_vehicle_are_not_ready():
    h = FlightHealth([0, 1])
    h.observe(0, True, True, 0)
    assert not h.ready(0)
    h.observe(1, True, False, 0)
    assert not h.ready(0)
    h.observe(1, True, True, 0)
    assert h.ready(0)
    assert not h.ready(2)


def test_nonfinite_position_does_not_refresh_feedback():
    s = FlightSession([[0, 0, 5]])
    s.observe([0, 0, -5], 0)
    s.observe([float('nan'), 0, -5], 2)
    assert s.target(2) is None
