"""
CARES — Mission Manager Module
Orchestrates the entire disaster response mission: task allocation,
event injection, failure handling, relay management, and metrics collection.
"""

import numpy as np
import yaml
import json
import os
import random
from typing import List, Dict, Optional, Tuple
from src.core.uav import UAV, UAVState, UAVRole
from src.core.world import World, ScheduledEvent
from src.core.gcs import GCS


class MissionManager:
    """
    Top-level orchestrator for the CARES swarm mission.
    Manages the simulation loop, task allocation triggers,
    event injection, and global metrics.
    """

    def __init__(self, scenario_path: str, swarm_config_path: str):
        # Load world from scenario
        self.world = World(scenario_path)

        # Load swarm config
        with open(swarm_config_path, 'r') as f:
            swarm_cfg = yaml.safe_load(f)

        self.num_uavs = self.world._raw_cfg.get('swarm', {}).get('num_uavs', swarm_cfg.get('swarm', {}).get('num_uavs', 8))
        uav_defaults = swarm_cfg.get('uav_defaults', {})

        # Initialize UAVs at launch pad with slight offsets
        self.uavs: List[UAV] = []
        # Battery randomization: each UAV starts with charge sampled from
        # [init_min_frac * capacity, capacity].  This is seeded by CARES_SEED
        # so each Monte Carlo seed produces a different charge profile.
        batt_cfg = uav_defaults.get('battery', {})
        init_min_frac = batt_cfg.get('init_min_frac', 0.70)  # default: 70-100% range
        for i in range(self.num_uavs):
            # Spawn with a 15m random scatter so they don't spawn inside each other
            spawn_x = self.world.launch_pos[0] + random.uniform(-15.0, 15.0)
            spawn_y = self.world.launch_pos[1] + random.uniform(-15.0, 15.0)
            uav = UAV(i, np.array([spawn_x, spawn_y]), uav_defaults)
            # Randomize initial battery charge (seeded RNG)
            init_frac = random.uniform(init_min_frac, 1.0)
            uav.battery.current_wh = uav.battery.capacity_wh * init_frac
            self.uavs.append(uav)

        # Initialize GCS
        self.gcs = GCS(self.world.gcs_pos, self.world.gcs_label)
        self.gcs.comm_range = uav_defaults.get('comms', {}).get('max_range', 500.0)

        # Simulation state
        self.sim_time = 0.0
        self.last_reopt_time = 0.0
        self.dt = 0.1  # 100ms simulation tick
        self.running = True
        self.paused = False

        # NPNT Authorization Gate (No Permission — No Takeoff)
        # Legacy demonstration flag only; no Digital Sky / UTM clearance is queried.
        # When revoked (e.g., geofence breach, GPS anomaly confirmed),
        # all IDLE→TAKEOFF transitions are blocked for affected UAVs.
        # Defaults to True; this does not establish regulatory authorization.
        self.npnt_authorized = True
        # Per-UAV revocation set: UAV IDs whose arming is individually suspended
        self._npnt_revoked_uavs: set = set()

        # Metrics history (sampled every second)
        self.metrics_history: List[Dict] = []
        self.trajectory_log: List[Dict] = []
        self.last_metrics_time = 0.0
        self.metrics_interval = 1.0

        # Mission log
        self.mission_log: List[Dict] = []

        # Allocation needs rerun flag
        self.needs_reallocation = True

    def step(self) -> Dict:
        """
        Advance simulation by one tick (self.dt seconds).
        Returns current metrics dictionary.
        """
        if not self.running or self.paused:
            return {}

        self.sim_time += self.dt

        # 1. Check for scheduled events (new PoIs)
        self._handle_events()

        # 2. Check for scheduled failures
        self._handle_failures()

        # Global Re-Optimization Trigger (Stretch Goal)
        if self.sim_time - getattr(self, 'last_reopt_time', 0.0) >= 90.0:
            self.needs_reallocation = True
            self.last_reopt_time = self.sim_time
            self._log(f"GLOBAL_REOPT — Scheduled 90s pass triggered")

        # 3. Check battery warnings → send to recharge
        self._handle_battery()

        # 4. Update all UAV state machines (pass wind vector + NPNT auth for physics/safety)
        for uav in self.uavs:
            # Set per-UAV NPNT flag: global revocation OR individual revocation
            uav._npnt_authorized = (self.npnt_authorized and
                                    uav.id not in self._npnt_revoked_uavs)
            uav.update(self.dt, self.sim_time, self.world.wind_vector)

        # 5. Check dynamic discoveries (Pillar 3: Dynamic task discovery)
        uav_positions = [uav.pos for uav in self.uavs if uav.state != UAVState.FAILED]
        new_discoveries = self.world.check_dynamic_discoveries(uav_positions, discovery_radius=150.0)
        for poi in new_discoveries:
            self.needs_reallocation = True
            self._log(f"🔎 DYNAMIC DISCOVERY: UAV detected hidden PoI {poi.id} '{poi.label}' at ({poi.x}, {poi.y})")

        # 6. Check survey completions
        self._check_survey_completions()

        # 7. Compute communication metrics
        metrics = self.gcs.compute_metrics(self.uavs)

        # 8. Sample metrics periodically
        if self.sim_time - self.last_metrics_time >= self.metrics_interval:
            self.last_metrics_time = self.sim_time
            # Pillar 2: Track average covariance for plotting
            avg_cov = 0.0
            active_uavs = [u for u in self.uavs if u.state.value != "FAILED"]
            if active_uavs:
                avg_cov = sum(u.estimator.position_uncertainty for u in active_uavs if hasattr(u, 'estimator')) / len(active_uavs)

            snapshot = {
                'time': round(self.sim_time, 1),
                'mission_completion': round(self.world.mission_completion * 100, 1),
                'priority_completion': round(self.world.priority_weighted_completion * 100, 1),
                'connectivity': round(metrics['connectivity_ratio'] * 100, 1),
                'fiedler': round(metrics['fiedler_value'], 3),
                'connected_uavs': metrics['connected_uavs'],
                'active_uavs': metrics['total_active_uavs'],
                'pdr': round(self.gcs.packet_delivery_ratio() * 100, 1),
                'conn_availability': round(metrics['connectivity_availability'] * 100, 1),
                'avg_covariance': round(avg_cov, 3),
            }
            self.metrics_history.append(snapshot)

            for uav in self.uavs:
                self.trajectory_log.append({
                    'time': round(self.sim_time, 1),
                    'uav_id': uav.id,
                    'x': float(uav.pos[0]), 'y': float(uav.pos[1]), 'z': float(uav.altitude),
                    'role': uav.role.value, 'state': uav.state.value,
                })

        # 8. Check mission end
        if self.sim_time >= self.world.duration_s:
            self.running = False

        # Augment metrics with mission-level data
        metrics['sim_time'] = self.sim_time
        metrics['mission_completion'] = self.world.mission_completion
        metrics['priority_weighted_completion'] = self.world.priority_weighted_completion
        metrics['unsurveyed_pois'] = self.world.get_unsurveyed_pois()
        metrics['needs_reallocation'] = self.needs_reallocation

        return metrics

    def _handle_events(self):
        """Process scheduled events (dynamic PoI insertion)."""
        events = self.world.check_events(self.sim_time)
        for evt in events:
            if evt.event_type == 'new_poi':
                self.world.add_poi(evt.data)
                self.needs_reallocation = True
                self._log(f"⚡ NEW EMERGENCY PoI: {evt.data.get('label', 'Unknown')} "
                          f"at ({evt.data['x']}, {evt.data['y']}) "
                          f"Priority: {evt.data['priority']}")

    def _handle_failures(self):
        """Process scheduled UAV failures."""
        failures = self.world.check_failures(self.sim_time)
        for fail in failures:
            uav_idx = fail.data.get('uav_index', 0)
            if 0 <= uav_idx < len(self.uavs):
                uav = self.uavs[uav_idx]
                if uav.state != UAVState.FAILED:
                    uav.inject_failure(fail.event_type, self.sim_time)
                    self.needs_reallocation = True
                    self._log(f"💥 {uav.label} FAILED — {fail.data.get('description', fail.event_type)}")

    def _handle_battery(self):
        """Check battery levels and send low-battery UAVs to recharge."""
        for uav in self.uavs:
            if (uav.battery.is_warning and
                    uav.state not in (UAVState.RTL, UAVState.RECHARGE,
                                      UAVState.FAILED, UAVState.IDLE)):
                # Calculate if UAV can still reach a charger
                charger_pos, dist = self.world.nearest_recharge_station(uav.pos)
                if not uav.battery.can_reach(dist, uav.max_speed, reserve_fraction=0.05):
                    uav.send_to_recharge(charger_pos, self.sim_time)
                    self.needs_reallocation = True
                    self._log(f"🔋 {uav.label} LOW BATTERY ({uav.battery.level*100:.0f}%) — RTL")

    def _check_survey_completions(self):
        """Check if any UAV has completed a survey and mark the PoI."""
        for uav in self.uavs:
            for task_id in list(uav.tasks_completed):
                poi = self.world.get_poi_by_id(task_id)
                if poi and not poi.surveyed:
                    self.world.mark_surveyed(task_id, uav.id, self.sim_time)
                    self.needs_reallocation = True
                    self._log(f"✅ {uav.label} surveyed PoI-{task_id} '{poi.label}'")
                    
                    # Clear this completed task from ALL agents' CBBA state
                    # so they immediately re-enter bidding for remaining tasks
                    for u in self.uavs:
                        u.winning_bids.pop(task_id, None)
                        u.winning_agents.pop(task_id, None)
                        
                        # Cancel other UAVs still targeting this now-surveyed task
                        if u is not uav and u.assigned_task_id == task_id:
                            u.assigned_task_id = None
                            u.target_pos = None
                            u.true_target_pos = None
                            u.waypoints = []
                            u.waypoint_index = 0
                            u.survey_timer = 0.0
                            # Remove stale credit if they also completed it this tick
                            if task_id in u.tasks_completed:
                                u.tasks_completed.remove(task_id)

    def get_available_uavs(self) -> List[UAV]:
        """Get UAVs available for new task assignment."""
        return [u for u in self.uavs if u.is_available()]

    def get_active_uavs(self) -> List[UAV]:
        """Get all operational UAVs."""
        return [u for u in self.uavs if u.is_active()]

    def get_failed_uavs(self) -> List[UAV]:
        """Get all failed UAVs."""
        return [u for u in self.uavs if u.state == UAVState.FAILED]

    def acknowledge_reallocation(self):
        """Called after task allocator has run to clear the flag."""
        self.needs_reallocation = False

    def get_final_report(self) -> Dict:
        """Generate final mission report."""
        total_pois = len(self.world.pois)
        surveyed = sum(1 for p in self.world.pois if p.surveyed)
        failed_uavs = len(self.get_failed_uavs())

        mesh = getattr(self, 'last_mesh_stats', {})
        report = {
            'scenario': self.world.name,
            'duration_s': round(self.sim_time, 1),
            'total_pois': total_pois,
            'surveyed_pois': surveyed,
            'mission_completion_pct': round(self.world.mission_completion * 100, 1),
            'priority_weighted_pct': round(self.world.priority_weighted_completion * 100, 1),
            'connectivity_availability_pct': round(
                self.gcs.connected_ticks / max(1, self.gcs.total_ticks) * 100, 1),
            'pdr_pct': round(self.gcs.packet_delivery_ratio() * 100, 1),
            # Comms stats — from MeshNetwork.get_stats(), persisted every tick in main.py
            'avg_latency_ms': mesh.get('avg_latency_ms', 0.0),
            'avg_hops': mesh.get('avg_hops', 0.0),
            'msg_reduction_pct': mesh.get('msg_reduction_pct', 0.0),
            'packets_sent': mesh.get('total_sent', 0),
            'packets_delivered': mesh.get('total_delivered', 0),
            'packets_dropped': mesh.get('total_dropped', 0),
            'total_uavs': self.num_uavs,
            'failed_uavs': failed_uavs,
            'tasks_per_uav': {
                u.label: len(u.tasks_completed) for u in self.uavs
            },
            'collisions': getattr(self, 'collisions', 0),
        }
        # Merge MBB handoff stats (Pillar 1) if available
        mbb = getattr(self, 'last_mbb_stats', {})
        if mbb:
            report.update(mbb)
        return report

    def save_logs(self, output_dir: str = None):
        """Save mission log and metrics to JSON files."""
        if output_dir is None:
            output_dir = os.environ.get("CARES_LOG_DIR", "logs")
        os.makedirs(output_dir, exist_ok=True)

        with open(os.path.join(output_dir, "mission_log.json"), 'w') as f:
            json.dump(self.mission_log, f, indent=2)

        with open(os.path.join(output_dir, "metrics_history.json"), 'w') as f:
            json.dump(self.metrics_history, f, indent=2)

        with open(os.path.join(output_dir, "trajectory_log.json"), 'w') as f:
            json.dump(self.trajectory_log, f, indent=2)

        report = self.get_final_report()
        with open(os.path.join(output_dir, "final_report.json"), 'w') as f:
            json.dump(report, f, indent=2)

        # UAV telemetry logs
        all_uav_logs = []
        for uav in self.uavs:
            all_uav_logs.extend(uav.log)
        all_uav_logs.sort(key=lambda x: x['time'])
        with open(os.path.join(output_dir, "uav_telemetry.json"), 'w') as f:
            json.dump(all_uav_logs, f, indent=2)

    def _log(self, message: str):
        """Add entry to mission log."""
        entry = {'time': round(self.sim_time, 1), 'message': message}
        self.mission_log.append(entry)
        print(f"[{self.sim_time:7.1f}s] {message}")
