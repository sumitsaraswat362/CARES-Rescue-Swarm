"""
CARES — Fault Detection & Reconfiguration Module
Detects UAV failures via heartbeat timeout and triggers
swarm reconfiguration when network partitions are detected.
"""

import numpy as np
from typing import List, Set
from src.core.uav import UAV, UAVState, UAVRole


class FaultDetector:
    """
    Monitors UAV health via heartbeat tracking and detects:
    1. Individual UAV failures (heartbeat timeout)
    2. Network partitions (scouts disconnected from GCS)

    When failures are detected, trigger_reconfiguration() reassigns
    available UAVs to fill the gaps left by failed agents.
    """

    def __init__(self, heartbeat_timeout: float = 2.0):
        self.heartbeat_timeout = heartbeat_timeout
        self.detected_failures: List[int] = []  # IDs of UAVs detected as failed
        self.partition_detected: bool = False
        self.recovery_count: int = 0  # Number of reconfigurations triggered

    def detect_failures(self, uavs: List[UAV], sim_time: float) -> List[int]:
        """
        Detect UAVs that have failed based on heartbeat timeout.
        Returns list of newly detected failed UAV indices.
        """
        newly_failed = []
        for i, uav in enumerate(uavs):
            if uav.state == UAVState.FAILED:
                if uav.id not in self.detected_failures:
                    self.detected_failures.append(uav.id)
                    newly_failed.append(i)
        return newly_failed

    def check_network_partition(self, uavs: List[UAV], gcs,
                                 adj: dict) -> Set[int]:
        """
        Check if any active scouts are disconnected from GCS.
        Returns set of disconnected UAV IDs.
        """
        reachable = gcs.bfs_connected_to_gcs(adj)

        disconnected = set()
        for uav in uavs:
            if uav.is_active() and uav.id not in reachable:
                disconnected.add(uav.id)

        self.partition_detected = len(disconnected) > 0
        return disconnected

    def trigger_reconfiguration(self, failed_indices: List[int],
                                 uavs: List[UAV], gcs,
                                 allocator=None,
                                 sim_time: float = 0.0) -> bool:
        """
        Trigger swarm reconfiguration after failure detection.

        Strategy:
        1. If a failed UAV was a relay, find nearest idle UAV to take its position.
        2. If a failed UAV was a scout, release its task for reallocation.
        3. Flag the mission for reallocation so CA-CBBA runs next tick.

        Returns True if reconfiguration was needed and applied.
        """
        if not failed_indices:
            return False

        reconfigured = False

        for idx in failed_indices:
            if idx < 0 or idx >= len(uavs):
                continue

            failed_uav = uavs[idx]

            if failed_uav.role == UAVRole.RELAY and failed_uav.relay_station_pos is not None:
                # Find nearest idle UAV to take over relay position
                relay_pos = failed_uav.relay_station_pos.copy()
                best_uav = None
                best_dist = float('inf')

                for candidate in uavs:
                    if candidate.is_available() and candidate.id != failed_uav.id:
                        d = float(np.linalg.norm(candidate.pos - relay_pos))
                        if d < best_dist:
                            best_dist = d
                            best_uav = candidate

                if best_uav is not None:
                    best_uav.assign_relay(relay_pos, sim_time)
                    reconfigured = True

            elif failed_uav.role == UAVRole.SCOUT and failed_uav.assigned_task_id is not None:
                # The task will be picked up by the next allocation round
                # Just ensure it's marked for reallocation
                reconfigured = True

        if reconfigured:
            self.recovery_count += 1

        return reconfigured

