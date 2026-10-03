"""
CARES — World Environment Module
Defines the 2D disaster environment with obstacles, PoIs, GCS, and recharge stations.
"""

import numpy as np
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Obstacle:
    """Circular no-fly zone."""
    x: float
    y: float
    radius: float
    label: str = ""

    @property
    def center(self) -> np.ndarray:
        return np.array([self.x, self.y])

    def contains(self, pos: np.ndarray) -> bool:
        return float(np.linalg.norm(pos - self.center)) < self.radius


@dataclass
class PointOfInterest:
    """A location that needs to be surveyed."""
    id: int
    x: float
    y: float
    priority: int  # 1 (low) to 5 (critical)
    label: str = ""
    surveyed: bool = False
    surveyed_by: Optional[int] = None  # UAV id
    surveyed_at: Optional[float] = None  # sim time
    deadline_s: float = 1e9

    @property
    def pos(self) -> np.ndarray:
        return np.array([self.x, self.y])


@dataclass
class RechargeStation:
    """A location where UAVs can recharge."""
    x: float
    y: float
    label: str = ""

    @property
    def pos(self) -> np.ndarray:
        return np.array([self.x, self.y])


@dataclass
class ScheduledEvent:
    """An event to be triggered at a specific simulation time."""
    time_s: float
    event_type: str  # "new_poi", "failure", etc.
    data: dict = field(default_factory=dict)
    triggered: bool = False


class World:
    """
    2D disaster response environment.
    Loads from a YAML scenario file.
    """

    def __init__(self, scenario_path: str):
        with open(scenario_path, 'r') as f:
            cfg = yaml.safe_load(f)
        self._raw_cfg = cfg  # Keep raw config for other modules (e.g., MBB handoff)
        unsupported = {'pois','uavs','max_time','scenario_name','dt'} & cfg.keys()
        if unsupported:
            raise ValueError(f'Unsupported scenario keys {sorted(unsupported)}; use the canonical scenario/world/points_of_interest/simulation schema')

        scenario = cfg.get('scenario', {})
        self.name = scenario.get('name', 'Unknown Scenario')
        self.description = scenario.get('description', '')

        # World dimensions
        world_cfg = cfg.get('world', {})
        self.width = world_cfg.get('width', 2000)
        self.height = world_cfg.get('height', 1500)
        
        # Wind vector (dx, dy) affecting UAV dynamics and battery
        self.wind_vector = np.array(world_cfg.get('wind_vector', [0.0, 0.0]), dtype=np.float64)

        # Obstacles
        self.obstacles: List[Obstacle] = []
        for obs in world_cfg.get('obstacles', []):
            self.obstacles.append(Obstacle(
                x=obs['x'], y=obs['y'],
                radius=obs['radius'],
                label=obs.get('label', '')
            ))
            
        # Real-World Geography (OSM Integration)
        if 'osm_file' in world_cfg:
            import os
            osm_path = world_cfg['osm_file']
            # Fallback for relative paths in scenarios
            if not os.path.exists(osm_path):
                osm_path = os.path.join(os.path.dirname(__file__), '..', '..', osm_path)
            
            if os.path.exists(osm_path):
                from .real_world_loader import load_osm_buildings
                origin_lat = world_cfg.get('osm_origin_lat', 19.126)
                origin_lon = world_cfg.get('osm_origin_lon', 72.906)
                osm_obs = load_osm_buildings(osm_path, origin_lat, origin_lon)
                for ob in osm_obs:
                    self.obstacles.append(Obstacle(
                        x=ob['x'], y=ob['y'],
                        radius=ob['radius'],
                        label='OSM_Bldg'
                    ))

        # GCS
        gcs_cfg = cfg.get('gcs', {})
        gcs_pos = gcs_cfg.get('position', {'x': 100, 'y': 750})
        self.gcs_pos = np.array([gcs_pos['x'], gcs_pos['y']], dtype=np.float64)
        self.gcs_label = gcs_cfg.get('label', 'GCS')

        # Launch pad
        lp_cfg = cfg.get('launch_pad', {})
        lp_pos = lp_cfg.get('position', {'x': 150, 'y': 750})
        self.launch_pos = np.array([lp_pos['x'], lp_pos['y']], dtype=np.float64)

        # Recharge stations
        self.recharge_stations: List[RechargeStation] = []
        for rs in cfg.get('recharge_stations', []):
            self.recharge_stations.append(RechargeStation(
                x=rs['x'], y=rs['y'], label=rs.get('label', '')
            ))

        # Points of Interest
        self.pois: List[PointOfInterest] = []
        for poi in cfg.get('points_of_interest', []):
            self.pois.append(PointOfInterest(
                id=poi['id'], x=poi['x'], y=poi['y'],
                priority=poi['priority'], label=poi.get('label', ''), deadline_s=poi.get('deadline_s',1e9)
            ))
            
        # Hidden Points of Interest (for dynamic discovery)
        self.hidden_pois: List[PointOfInterest] = []
        for poi in cfg.get('hidden_pois', []):
            self.hidden_pois.append(PointOfInterest(
                id=poi['id'], x=poi['x'], y=poi['y'],
                priority=poi['priority'], label=poi.get('label', ''), deadline_s=poi.get('deadline_s',1e9)
            ))

        # Events
        self.events: List[ScheduledEvent] = []
        for evt in cfg.get('events', []):
            self.events.append(ScheduledEvent(
                time_s=evt['time_s'],
                event_type=evt['type'],
                data=evt.get('poi', evt),
            ))

        # Failures — support both fixed time_s and randomized time_window
        self.failures: List[ScheduledEvent] = []
        for fail in cfg.get('failures', []):
            if 'time_window' in fail:
                # Sample actual trigger time from seeded RNG at world init.
                # Different seeds → different failure times → real MC variance.
                import random
                t_min, t_max = fail['time_window']
                trigger_time = random.uniform(t_min, t_max)
            else:
                trigger_time = fail['time_s']
            self.failures.append(ScheduledEvent(
                time_s=trigger_time,
                event_type=fail.get('type', 'motor_failure'),
                data=fail,
            ))

        # Simulation config
        sim_cfg = cfg.get('simulation', {})
        self.duration_s = sim_cfg.get('duration_s', 600)
        self.time_scale = sim_cfg.get('time_scale', 5.0)
        self.seed = sim_cfg.get('seed', 42)

    def get_unsurveyed_pois(self) -> List[PointOfInterest]:
        """Return all PoIs that haven't been surveyed yet."""
        return [p for p in self.pois if not p.surveyed]

    def get_poi_by_id(self, poi_id: int) -> Optional[PointOfInterest]:
        """Find a PoI by its ID."""
        for p in self.pois:
            if p.id == poi_id:
                return p
        return None

    def mark_surveyed(self, poi_id: int, uav_id: int, sim_time: float):
        """Mark a PoI as surveyed."""
        poi = self.get_poi_by_id(poi_id)
        if poi:
            poi.surveyed = True
            poi.surveyed_by = uav_id
            poi.surveyed_at = sim_time

    def add_poi(self, poi_data: dict):
        """Dynamically add a new PoI (from events)."""
        if any(p.id == poi_data['id'] for p in self.pois + self.hidden_pois):
            raise ValueError('Duplicate PoI identifier')
        self.pois.append(PointOfInterest(
            id=poi_data['id'], x=poi_data['x'], y=poi_data['y'],
            priority=poi_data['priority'], label=poi_data.get('label', ''), deadline_s=poi_data.get('deadline_s',1e9)
        ))

    def nearest_recharge_station(self, pos: np.ndarray) -> Tuple[np.ndarray, float]:
        """Find the nearest recharge station to a position."""
        best_dist = float('inf')
        best_pos = self.launch_pos  # fallback to launch pad
        for rs in self.recharge_stations:
            d = float(np.linalg.norm(pos - rs.pos))
            if d < best_dist:
                best_dist = d
                best_pos = rs.pos
        return best_pos, best_dist

    def is_in_obstacle(self, pos: np.ndarray) -> bool:
        """Check if a position is inside any no-fly zone."""
        return any(obs.contains(pos) for obs in self.obstacles)

    def is_line_of_sight_blocked(self, p1: np.ndarray, p2: np.ndarray) -> bool:
        """Check if the line segment from p1 to p2 intersects any obstacle."""
        d = p2 - p1
        d_len_sq = float(np.dot(d, d))
        if d_len_sq < 1e-6:
            return self.is_in_obstacle(p1)
            
        for obs in self.obstacles:
            f = p1 - obs.center
            a = d_len_sq
            b = 2.0 * float(np.dot(f, d))
            c = float(np.dot(f, f)) - obs.radius**2
            
            discriminant = b**2 - 4*a*c
            if discriminant >= 0:
                discriminant = np.sqrt(discriminant)
                t1 = (-b - discriminant) / (2*a)
                t2 = (-b + discriminant) / (2*a)
                if (0 <= t1 <= 1) or (0 <= t2 <= 1):
                    return True
        return False

    def is_in_bounds(self, pos: np.ndarray, margin: float = 0.0) -> bool:
        """Check if a position is within world boundaries."""
        return (margin <= pos[0] <= self.width - margin and
                margin <= pos[1] <= self.height - margin)

    def check_events(self, sim_time: float) -> List[ScheduledEvent]:
        """Check and return any events that should trigger at the current time."""
        triggered = []
        for evt in self.events:
            if not evt.triggered and sim_time >= evt.time_s:
                evt.triggered = True
                triggered.append(evt)
        return triggered

    def check_failures(self, sim_time: float) -> List[ScheduledEvent]:
        """Check and return any failures that should trigger at the current time."""
        triggered = []
        for fail in self.failures:
            if not fail.triggered and sim_time >= fail.time_s:
                fail.triggered = True
                triggered.append(fail)
        return triggered

    def check_dynamic_discoveries(self, uav_positions: List[np.ndarray], discovery_radius: float = 150.0) -> List[PointOfInterest]:
        """Check if any UAV has flown close enough to a hidden PoI to discover it."""
        discovered = []
        remaining_hidden = []
        
        for poi in self.hidden_pois:
            found = False
            for pos in uav_positions:
                if np.linalg.norm(pos - poi.pos) <= discovery_radius:
                    found = True
                    break
            
            if found:
                discovered.append(poi)
                self.pois.append(poi)  # Add to active PoIs
            else:
                remaining_hidden.append(poi)
                
        self.hidden_pois = remaining_hidden
        return discovered

    @property
    def mission_completion(self) -> float:
        """Fraction of PoIs surveyed [0, 1]."""
        if not self.pois:
            return 1.0
        return sum(1 for p in self.pois if p.surveyed) / len(self.pois)

    @property
    def priority_weighted_completion(self) -> float:
        """Priority-weighted mission completion [0, 1]."""
        total = sum(p.priority for p in self.pois)
        if total == 0:
            return 1.0
        done = sum(p.priority for p in self.pois if p.surveyed)
        return done / total

    def __repr__(self):
        return (f"<World '{self.name}' {self.width}x{self.height}m "
                f"pois={len(self.pois)} obstacles={len(self.obstacles)}>")
