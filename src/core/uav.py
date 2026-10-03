"""
CARES — UAV Agent Module
Defines the UAV state machine, kinematics, battery model, and role management.
"""

import enum
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


class UAVState(enum.Enum):
    IDLE = "idle"
    TAKEOFF = "takeoff"
    SCOUT = "scout"            # Flying to / surveying a PoI
    RELAY = "relay"            # Holding position as communication relay
    RTL = "return_to_launch"   # Returning to base / recharge station
    RECHARGE = "recharge"
    FAILED = "failed"


class UAVRole(enum.Enum):
    SCOUT = "scout"
    RELAY = "relay"
    UNASSIGNED = "unassigned"


class BatteryModel:
    """Tracks battery state and computes remaining flight time."""
    def __init__(self, capacity_wh: float, current_wh: float,
                 hover_power_w: float, cruise_power_w: float,
                 charge_rate_wh_per_s: float,
                 critical_threshold: float, warning_threshold: float):
        self.capacity_wh = capacity_wh
        self.current_wh = current_wh
        self.hover_power_w = hover_power_w
        self.cruise_power_w = cruise_power_w
        self.charge_rate_wh_per_s = charge_rate_wh_per_s
        self.critical_threshold = critical_threshold
        self.warning_threshold = warning_threshold
        self.drain_multiplier = 1.0  # Used to simulate rapid battery drain failures

    @property
    def level(self) -> float:
        """Battery percentage [0.0, 1.0]."""
        return self.current_wh / self.capacity_wh

    @property
    def is_critical(self) -> bool:
        return self.level <= self.critical_threshold

    @property
    def is_warning(self) -> bool:
        return self.level <= self.warning_threshold

    def consume(self, power_w: float, dt: float):
        """Consume energy based on power draw and time."""
        energy_wh = (power_w * self.drain_multiplier * dt) / 3600.0
        self.current_wh = max(0.0, self.current_wh - energy_wh)

    def charge(self, dt: float):
        """Recharge battery."""
        self.current_wh = min(self.capacity_wh * 0.95, 
                              self.current_wh + self.charge_rate_wh_per_s * dt)

    def time_remaining_s(self, power_w: float) -> float:
        """Estimate seconds of flight remaining at given power draw."""
        if power_w <= 0:
            return float('inf')
        actual_power = power_w * self.drain_multiplier
        return (self.current_wh / actual_power) * 3600.0

    def energy_for_distance(self, distance: float, speed: float) -> float:
        """Energy (Wh) required to fly a given distance at a given speed."""
        if speed <= 0:
            return float('inf')
        time_h = (distance / speed) / 3600.0
        return getattr(self,'planning_power_w',self.cruise_power_w) * self.drain_multiplier * time_h

    def can_reach(self, distance: float, speed: float, reserve_fraction: float = 0.15) -> bool:
        """Check if UAV can fly distance and still have reserve battery."""
        required = self.energy_for_distance(distance, speed)
        available = self.current_wh - (self.capacity_wh * reserve_fraction)
        return available >= required


class UAV:
    """
    Autonomous UAV agent with full state machine, kinematics, battery,
    communication state, and task assignment tracking.
    """

    def __init__(self, uav_id: int, start_pos: Tuple[float, float], config: dict):
        self.id = uav_id
        self.label = f"UAV-{uav_id + 1}"

        # Kinematics
        self.pos = np.array(start_pos, dtype=np.float64)
        self.vel = np.zeros(2, dtype=np.float64)
        self.heading = 0.0  # radians
        # Initialize with a staggered altitude so they don't climb in perfect lockstep from 0
        unique_offset = (self.id % 8) * 12.0
        self.altitude = 5.0 + unique_offset  # meters (3D separation)
        self.max_speed = config.get('max_speed', 15.0)
        self.max_altitude = config.get('max_altitude',120.0)
        self.flight_altitude = 30.0 + self.id * 10.0
        if self.flight_altitude > self.max_altitude:
            raise ValueError('Fleet exceeds available distinct altitude slots')
        self.cruise_speed = config.get('cruise_speed', 10.0)

        # State machine
        self.state = UAVState.IDLE
        self.role = UAVRole.UNASSIGNED

        # Battery
        batt_cfg = config.get('battery', {})
        self.battery = BatteryModel(
            capacity_wh=batt_cfg.get('capacity_wh', 200.0),
            current_wh=batt_cfg.get('capacity_wh', 200.0),
            hover_power_w=batt_cfg.get('hover_power_w', 150.0),
            cruise_power_w=batt_cfg.get('cruise_power_w', 120.0),
            charge_rate_wh_per_s=batt_cfg.get('charge_rate_wh', 100.0) / 60.0,
            critical_threshold=batt_cfg.get('critical_threshold', 0.15),
            warning_threshold=batt_cfg.get('warning_threshold', 0.30),
        )

        # Communication
        comms_cfg = config.get('comms', {})
        self.comm_range = comms_cfg.get('max_range', 500.0)
        self.reliable_range = comms_cfg.get('reliable_range', 350.0)
        self.heartbeat_interval = comms_cfg.get('heartbeat_interval_ms', 500) / 1000.0
        self.heartbeat_timeout = comms_cfg.get('heartbeat_timeout_ms', 2000) / 1000.0
        self.last_heartbeat_sent = 0.0
        
        # Additive Reactive Sensing Mode (Phase 3)
        import os
        self.reactive_sensing = os.environ.get("CARES_REACTIVE_SENSING", "0") == "1"
        self.sensor_radius = 100.0
        self.known_obstacles = []
        self.last_heartbeats_received: dict[int, float] = {}  # uav_id -> timestamp

        # Safety
        safety_cfg = config.get('safety', {})
        self.min_separation = safety_cfg.get('min_separation', 5.0)

        # Sensors
        sensor_cfg = config.get('sensors', {})
        self.survey_radius = sensor_cfg.get('survey_radius', 30.0)
        self.survey_time_s = sensor_cfg.get('survey_time_s', 10.0)

        # Task assignment
        self.assigned_task_id: Optional[int] = None
        self.target_pos: Optional[np.ndarray] = None
        self.true_target_pos: Optional[np.ndarray] = None  # Real PoI location for proximity check
        self.waypoints: List[np.ndarray] = []               # Full A* path
        self.waypoint_index: int = 0                         # Current waypoint being pursued
        self.relay_station_pos: Optional[np.ndarray] = None
        self.survey_timer: float = 0.0
        self.tasks_completed: List[int] = []
        
        # Pillar 2: State Estimation & Neighbor Tracking
        from src.core.ekf import UAVEstimator
        from src.core.neighbor_tracker import NeighborTracker
        
        self.estimator = UAVEstimator(self.pos, self.vel, gps_sigma=2.0)
        self.neighbor_tracker = NeighborTracker(self.id)

        # CBBA state
        self.bundle: List[int] = []       # Ordered list of task IDs this UAV has won
        self.path: List[int] = []         # Ordered execution path
        self.winning_bids: dict[int, float] = {}   # task_id -> bid value
        self.winning_agents: dict[int, int] = {}    # task_id -> agent_id who won

        # Telemetry log
        self.log: List[dict] = []

    def distance_to(self, target: np.ndarray) -> float:
        """Euclidean distance to a target position."""
        return float(np.linalg.norm(self.pos - target))

    def can_communicate_with(self, other: 'UAV') -> bool:
        """Check if this UAV can communicate with another."""
        if self.state == UAVState.FAILED or other.state == UAVState.FAILED:
            return False
        return self.distance_to(other.pos) <= self.comm_range

    def link_quality(self, other: 'UAV') -> float:
        """Link quality [0, 1] based on distance. 1=perfect, 0=no link."""
        if self.state == UAVState.FAILED or other.state == UAVState.FAILED:
            return 0.0
        d = self.distance_to(other.pos)
        if d > self.comm_range:
            return 0.0
        if d <= self.reliable_range * 0.5:
            return 1.0
        # Linear falloff from reliable_range to max_range
        return max(0.0, 1.0 - (d - self.reliable_range * 0.5) /
                   (self.comm_range - self.reliable_range * 0.5))

    def move_towards(self, target: np.ndarray, speed: float, dt: float) -> bool:
        """
        Move towards target at given speed. Returns True if arrived.
        Wind effect: headwind reduces effective groundspeed and increases battery draw.
        """
        if hasattr(self,'dynamics_spec'):
            return self.move_bounded(target,speed,dt)
        diff = target - self.pos
        dist = np.linalg.norm(diff)

        if dist < 2.0:  # Arrival threshold
            proposed = target.copy()
            if hasattr(self, 'motion_filter'):
                proposed = self.motion_filter(proposed, dt)
            self.pos = proposed
            self.vel = np.zeros(2)
            return bool(np.linalg.norm(self.pos-target)<1e-6)

        # Direction and velocity
        direction = diff / dist
        
        # Wind effect: project wind onto flight direction
        # Positive = tailwind (speeds up), Negative = headwind (slows down)
        wind = getattr(self, 'current_wind', np.zeros(2))
        wind_component = float(np.dot(wind, direction))  # m/s along flight path
        
        # Effective groundspeed: airspeed ± wind component (min 1.0 m/s to not stall)
        effective_speed = max(1.0, speed + wind_component)
        actual_speed = min(effective_speed, dist / dt) if dt > 0 else effective_speed
        
        self.vel = direction * actual_speed
        proposed = self.pos + self.vel * dt
        if hasattr(self, 'motion_filter'):
            proposed = self.motion_filter(proposed, dt)
            self.vel = (proposed-self.pos)/max(dt,1e-9)
        self.pos = proposed
        self.heading = math.atan2(direction[1], direction[0])

        # Battery drain scales with effective airspeed (fighting headwind costs more power)
        # airspeed = groundspeed - wind_component (always >= cruise_speed when upwind)
        airspeed_factor = max(0.5, (speed - wind_component) / max(speed, 1.0))
        self.battery.consume(self.battery.cruise_power_w * airspeed_factor, dt)
        return False

    def move_bounded(self,target,speed,dt):
        from src.resilience.environment import bounded_velocity
        if dt<=0:return False
        diff=target-self.pos;distance=float(np.linalg.norm(diff))
        accel=min(float(self.dynamics_spec.get('max_acceleration_mps2',3)),9.80665*math.tan(math.radians(30)))
        if distance<.2 and np.linalg.norm(self.vel)<=accel*dt:
            self.vel=np.zeros(2)
            return True
        direction=diff/max(distance,1e-9)
        along_wind=float(np.dot(getattr(self,'current_wind',np.zeros(2)),direction))
        desired=direction*min(max(0,speed+along_wind),math.sqrt(2*accel*max(0,distance-.1)))
        self.vel=bounded_velocity(self.vel,desired,dt,accel)
        proposed=self.pos+self.vel*dt
        if hasattr(self,'motion_filter'):
            proposed=self.motion_filter(proposed,dt)
            self.vel=(proposed-self.pos)/dt
        self.pos=proposed
        self.heading=math.atan2(self.vel[1],self.vel[0])
        self.battery.consume(self.battery.cruise_power_w,dt)
        return False

    def hover(self, dt: float):
        """Hover in place (relay mode or survey mode)."""
        self.vel = np.zeros(2)
        self.battery.consume(self.battery.hover_power_w, dt)

    def sense_and_replan(self, world, path_planner, sim_time: float):
        """
        Phase 3: Reactive Obstacle Sensing (Isolated Additive Feature).
        Simulates an onboard LiDAR/Vision sensor that dynamically discovers
        obstacles within 100m. If a newly discovered obstacle intersects
        the current flight path, it triggers an immediate local replan.
        """
        if not self.reactive_sensing or self.state not in (UAVState.SCOUT, UAVState.RELAY):
            return

        new_discovery = False
        for obs in world.obstacles:
            # Check if obstacle is within sensor radius
            dist = np.linalg.norm(self.pos - np.array([obs.x, obs.y]))
            if dist <= self.sensor_radius + obs.radius:
                # Check if we already know about it
                known = any(k['label'] == obs.label for k in self.known_obstacles)
                if not known:
                    self.known_obstacles.append({'x': obs.x, 'y': obs.y, 'radius': obs.radius, 'label': obs.label})
                    new_discovery = True
                    self._log_event(sim_time, f"SENSOR — Discovered {obs.label} at {dist:.1f}m")

        if new_discovery and self.state == UAVState.SCOUT and self.assigned_task_id is not None:
            path = path_planner.plan_with_obstacles(self.pos, self.true_target_pos, self.known_obstacles, self.battery, self.cruise_speed)
            if path and len(path) > 1:
                self.waypoints = [np.array(wp, dtype=np.float64) for wp in path[1:]]
                self.waypoint_index = 0
                self._log_event(sim_time, f"REPLAN — Rerouted due to new obstacle discovery")

    def update(self, dt: float, sim_time: float, wind_vector: np.ndarray = None):
        """
        Main state machine update. Called every simulation tick.
        """
        if wind_vector is None:
            wind_vector = np.zeros(2)
            
        if self.state == UAVState.FAILED:
            self.vel = np.zeros(2)
            return
            
        # Step estimators
        self.estimator.predict(dt)
        self.neighbor_tracker.predict_all(dt, sim_time)
        
        # Save wind_vector for move_towards logic
        self.current_wind = wind_vector

        # Check critical battery → force RTL
        if (self.battery.is_critical and
                self.state not in (UAVState.RTL, UAVState.RECHARGE, UAVState.IDLE, UAVState.FAILED)):
            self.state = UAVState.RTL
            self.assigned_task_id = None
            self._log_event(sim_time, "BATTERY_CRITICAL — Forced RTL")

        # Persistent preflight slots keep role changes and the altitude ceiling
        # from collapsing multiple relays onto one altitude. This is a simplified
        # deconfliction assumption, not a general collision-avoidance guarantee.
        ground=self.terrain.height(*self.pos) if hasattr(self,'terrain') else 0.
        target_alt = ground if self.state == UAVState.RECHARGE else min(self.max_altitude,ground+self.flight_altitude)
        alt_diff = target_alt - self.altitude
        if abs(alt_diff) > 0.1:
            # Climb/descend at max 5 m/s
            v_speed = min(5.0, abs(alt_diff) / dt) if dt > 0 else 5.0
            self.altitude += math.copysign(v_speed * dt, alt_diff)
        else:
            self.altitude = target_alt

        if self.state == UAVState.IDLE:
            self.hover(dt)

        elif self.state == UAVState.TAKEOFF:
            # Legacy local boolean gate, not a Digital Sky/UTM integration.
            # The resilience Runtime does not use this as authorization evidence.
            npnt_ok = getattr(self, '_npnt_authorized', True)
            if not npnt_ok:
                # Stay IDLE — arming is software-locked pending re-authorization
                self.state = UAVState.IDLE
                self._log_event(sim_time, "NPNT_BLOCK: arming denied — authorization revoked")
            elif self.assigned_task_id is not None:
                self.state = UAVState.SCOUT if self.role == UAVRole.SCOUT else UAVState.RELAY
            else:
                self.state = UAVState.IDLE

        elif self.state == UAVState.SCOUT:
            if self.target_pos is not None:
                # Determine current navigation target: use waypoint path if available
                if self.waypoints and self.waypoint_index < len(self.waypoints):
                    nav_target = self.waypoints[self.waypoint_index]
                else:
                    nav_target = self.target_pos

                arrived_at_waypoint = self.move_towards(nav_target, self.cruise_speed, dt)

                if not arrived_at_waypoint:
                    self.survey_timer=0.0
                    self.detection_confidence=0.0
                if arrived_at_waypoint:
                    # Check if there are more waypoints to follow
                    if self.waypoints and self.waypoint_index < len(self.waypoints) - 1:
                        self.waypoint_index += 1  # Advance to next waypoint
                    else:
                        # At final waypoint — verify proximity to actual PoI
                        check_pos = self.true_target_pos if self.true_target_pos is not None else self.target_pos
                        dist_to_poi = float(np.linalg.norm(self.pos - check_pos))

                        if (dist_to_poi <= self.survey_radius and 10 <= self.altitude <= self.max_altitude
                                and (not hasattr(self,'camera') or self.camera.accepts(
                                    [*self.pos,self.altitude],check_pos,float(np.linalg.norm(self.vel)),self.terrain))):
                            # Synthetic Vision CameraCone model: rate of confidence gain depends on altitude and lateral offset
                            # Altitude penalty: higher altitude = slower accumulation (base 40m)
                            alt_factor = max(0.1, 40.0 / max(self.altitude, 10.0))
                            # Distance penalty: edge of cone (30m) = slower accumulation
                            dist_factor = max(0.1, 1.0 - (dist_to_poi / self.survey_radius))
                            
                            # Base rate: 0.1 per second (takes ~10s in perfect conditions to hit 0.95)
                            confidence_rate = alt_factor * dist_factor * 0.15
                            self.detection_confidence = getattr(self, 'detection_confidence', 0.0) + (confidence_rate * dt)
                            self.survey_timer += dt
                            
                            self.hover(dt)
                            if self.detection_confidence >= 0.95 and self.survey_timer + 1e-9 >= self.survey_time_s:
                                # Survey complete — credit only with confidence verified
                                if self.assigned_task_id is not None:
                                    self.tasks_completed.append(self.assigned_task_id)
                                    self._log_event(sim_time,
                                                    f"SURVEY_COMPLETE — PoI {self.assigned_task_id}"
                                                    f" (dist={dist_to_poi:.1f}m, conf={self.detection_confidence:.2f})")
                                self.detection_confidence = 0.0
                                self.assigned_task_id = None
                                self.target_pos = None
                                self.true_target_pos = None
                                self.waypoints = []
                                self.waypoint_index = 0
                                self.state = UAVState.IDLE
                        else:
                            if hasattr(self,'dynamics_spec'):self.hover(dt)
                            self.survey_timer = 0.0
                            self.detection_confidence = 0.0
                            # Path ended but not at PoI — fly directly to true target
                            self.waypoints = []
                            self.waypoint_index = 0
                            self.target_pos = check_pos.copy()
            else:
                self.state = UAVState.IDLE

        elif self.state == UAVState.RELAY:
            if self.relay_station_pos is not None:
                target = self.waypoints[self.waypoint_index] if self.waypoints and self.waypoint_index < len(self.waypoints) else self.relay_station_pos
                arrived = self.move_towards(target, self.cruise_speed, dt)
                if arrived and self.waypoints and self.waypoint_index < len(self.waypoints):
                    self.waypoint_index += 1
                    arrived = self.waypoint_index >= len(self.waypoints)
                if arrived:
                    self.hover(dt)
            else:
                self.hover(dt)

        elif self.state == UAVState.RTL:
            if self.target_pos is not None:
                target = self.waypoints[self.waypoint_index] if self.waypoints and self.waypoint_index < len(self.waypoints) else self.target_pos
                arrived = self.move_towards(target, self.max_speed, dt)
                if arrived and self.waypoints and self.waypoint_index < len(self.waypoints):
                    self.waypoint_index += 1
                    arrived = self.waypoint_index >= len(self.waypoints)
                if arrived:
                    self.state = UAVState.RECHARGE
                    self._log_event(sim_time, "ARRIVED_AT_CHARGER — Recharging")
            else:
                self.state = UAVState.IDLE

        elif self.state == UAVState.RECHARGE:
            self.vel = np.zeros(2)
            if getattr(self, '_charging_allowed', True):
                self.battery.charge(dt)
            if self.battery.level >= 0.95:
                self.state = UAVState.IDLE
                self._log_event(sim_time, "RECHARGE_COMPLETE — Ready for tasking")

    def assign_scout_task(self, task_id: int, target: np.ndarray, sim_time: float,
                          waypoint_path: Optional[List[np.ndarray]] = None,
                          true_target: Optional[np.ndarray] = None):
        """Assign a scouting task to this UAV.
        
        Args:
            task_id: PoI task ID
            target: Navigation target (final PoI position)
            sim_time: Current simulation time
            waypoint_path: Optional full A* path (list of waypoint positions)
            true_target: Optional true PoI position for proximity verification
        """
        self.assigned_task_id = task_id
        self.target_pos = np.array(target, dtype=np.float64)
        self.true_target_pos = np.array(true_target, dtype=np.float64) if true_target is not None else self.target_pos.copy()
        self.survey_timer = 0.0
        self.detection_confidence = 0.0
        self.role = UAVRole.SCOUT
        self.state = UAVState.SCOUT
        
        # Store full waypoint path for multi-hop navigation
        if waypoint_path and len(waypoint_path) > 1:
            self.waypoints = [np.array(wp, dtype=np.float64) for wp in waypoint_path[1:]]  # Skip current pos
            self.waypoint_index = 0
        else:
            self.waypoints = []
            self.waypoint_index = 0
        
        self._log_event(sim_time, f"ASSIGNED_SCOUT — PoI {task_id} via {len(self.waypoints)} waypoints")

    def assign_relay(self, position: np.ndarray, sim_time: float):
        """Assign this UAV as a communication relay at a given position."""
        self.role = UAVRole.RELAY
        self.relay_station_pos = np.array(position, dtype=np.float64)
        self.state = UAVState.RELAY
        self.assigned_task_id = None
        self._log_event(sim_time, f"ASSIGNED_RELAY — pos ({position[0]:.0f}, {position[1]:.0f})")

    def send_to_recharge(self, charger_pos: np.ndarray, sim_time: float):
        """Send UAV to a recharge station."""
        self.state = UAVState.RTL
        self.target_pos = np.array(charger_pos, dtype=np.float64)
        self.assigned_task_id = None
        self._log_event(sim_time, "SENT_TO_RECHARGE")

    def inject_failure(self, failure_type: str, sim_time: float):
        """Inject a hardware failure."""
        if failure_type == "battery_critical":
            self.battery.drain_multiplier = 20.0
            self._log_event(sim_time, "FAILURE — Rapid battery drain (20x) initiated")
        else:
            self.state = UAVState.FAILED
            self.vel = np.zeros(2)
            self.assigned_task_id = None
            self._log_event(sim_time, f"FAILURE — {failure_type}")

    def is_available(self) -> bool:
        """Check if UAV is available for task assignment (not failed, RTL, or recharging)."""
        return (self.state in (UAVState.IDLE, UAVState.TAKEOFF, UAVState.SCOUT, UAVState.RELAY) and
                not self.battery.is_critical)

    def update_gps_measurement(self, rng=None):
        """Simulate a GPS reading and update the EKF."""
        noisy_pos = self.estimator.get_noisy_gps(self.pos, rng)
        self.estimator.update_gps(noisy_pos)
        
    def receive_telemetry(self, neighbor_id: int, reported_pos: np.ndarray, reported_vel: np.ndarray, sim_time: float):
        """Process a received telemetry packet from a neighbor."""
        self.neighbor_tracker.update_neighbor(neighbor_id, reported_pos, reported_vel, sim_time)

    def is_active(self) -> bool:
        """Check if UAV is operational (not failed, not recharging)."""
        return self.state not in (UAVState.FAILED, UAVState.RECHARGE)

    def _log_event(self, sim_time: float, event: str):
        self.log.append({
            'time': sim_time,
            'uav': self.label,
            'event': event,
            'pos': (round(self.pos[0], 1), round(self.pos[1], 1)),
            'battery': round(self.battery.level * 100, 1),
            'state': self.state.value,
        })

    def __repr__(self):
        return (f"<{self.label} state={self.state.value} role={self.role.value} "
                f"batt={self.battery.level*100:.0f}% "
                f"pos=({self.pos[0]:.0f},{self.pos[1]:.0f})>")
