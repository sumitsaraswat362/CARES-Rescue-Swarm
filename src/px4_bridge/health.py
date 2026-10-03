"""Measured flight evidence, independent of ROS so failure cases can be tested."""
import math


class FlightHealth:
    def __init__(self, ids, stale_s=1.0):
        self.ids = set(ids)
        self.stale_s = stale_s
        self.states = {}
        self.engaged = set()
        self.landing_at = None

    def observe(self, uid, armed, offboard, now):
        if uid not in self.ids or not math.isfinite(now):
            raise ValueError('Invalid vehicle status')
        self.states[uid] = (bool(armed), bool(offboard), now)
        if armed and offboard:
            self.engaged.add(uid)

    def fresh(self, now):
        return self.states.keys() == self.ids and all(
            0 <= now - row[2] <= self.stale_s for row in self.states.values())

    def ready(self, now):
        return self.fresh(now) and all(row[0] and row[1] for row in self.states.values())

    def begin_landing(self, now):
        if self.landing_at is None:
            self.landing_at = now

    def landed(self, now):
        return (self.landing_at is not None and self.engaged == self.ids
                and self.fresh(now) and all(not row[0] and row[2] >= self.landing_at
                                           for row in self.states.values()))
