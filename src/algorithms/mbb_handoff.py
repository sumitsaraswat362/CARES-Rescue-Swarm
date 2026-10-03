"""
CARES — Make-Before-Break (MBB) Predictive Relay Handoff

Implements predictive relay replacement to maintain algebraic connectivity
(Fiedler value λ₂) during battery-driven relay rotations.

The key insight: instead of waiting for a relay to hit critical battery and
then reactively scrambling for a replacement, MBB monitors relay battery
drain rates and proactively dispatches a replacement UAV to the relay
position *before* the current relay departs.

Timeline of a handoff:
  t_predict:  Relay's time_remaining_s() < handoff_horizon_s
              → MBB selects best idle UAV, dispatches to relay position
  t_overlap:  Replacement arrives at relay position
              → Both old and new relay are in position (dual connectivity)
  t_depart:   Old relay departs for recharge
              → New relay takes over seamlessly

Safety: if the Fiedler value would drop below fiedler_safety_margin during
the handoff, the old relay stays until replacement is confirmed in-position.

References:
  - 3GPP TS 38.300 §9.2.3: Make-Before-Break handover in 5G NR
  - Sujit et al. (RA-L 2025): Persistent coverage with charging constraints
"""

import numpy as np
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple
from src.core.uav import UAV, UAVState, UAVRole

logger = logging.getLogger("CARES.MBB")


class HandoffState(Enum):
    """State of a single relay handoff operation."""
    IDLE = "idle"                    # No handoff in progress
    DISPATCHING = "dispatching"     # Replacement en route to relay position
    OVERLAPPING = "overlapping"     # Both old and new relay at position
    COMPLETING = "completing"       # Old relay departing, new relay confirmed


class HandoffRecord:
    """Tracks a single relay handoff operation."""
    __slots__ = [
        'old_relay_id', 'new_relay_id', 'relay_pos',
        'state', 'dispatch_time', 'overlap_start_time',
        'complete_time', 'fiedler_at_dispatch',
    ]

    def __init__(self, old_relay_id: int, relay_pos: np.ndarray,
                 dispatch_time: float, fiedler_at_dispatch: float):
        self.old_relay_id = old_relay_id
        self.new_relay_id: Optional[int] = None
        self.relay_pos = relay_pos.copy()
        self.state = HandoffState.DISPATCHING
        self.dispatch_time = dispatch_time
        self.overlap_start_time: Optional[float] = None
        self.complete_time: Optional[float] = None
        self.fiedler_at_dispatch = fiedler_at_dispatch


class MBBHandoffManager:
    """
    Make-Before-Break relay handoff manager.

    Monitors relay battery levels, predicts when relays will need to
    depart for recharge, and proactively dispatches replacements to
    maintain seamless connectivity.
    """

    def __init__(self, handoff_horizon_s: float = 90.0,
                 min_overlap_s: float = 10.0,
                 fiedler_safety_margin: float = 0.05,
                 arrival_threshold: float = 15.0,
                 max_stall_s: float = 60.0):
        """
        Args:
            handoff_horizon_s: Seconds before battery depletion to begin handoff
            min_overlap_s: Minimum overlap period with both relays in position
            fiedler_safety_margin: Abort handoff if Fiedler dips below this
            arrival_threshold: Distance (m) to consider replacement "arrived"
            max_stall_s: Max seconds to wait in OVERLAPPING after min_overlap_s
                         before forcing a decision (prevents infinite deadlock)
        """
        self.handoff_horizon_s = handoff_horizon_s
        self.min_overlap_s = min_overlap_s
        self.fiedler_safety_margin = fiedler_safety_margin
        self.arrival_threshold = arrival_threshold
        self.max_stall_s = max_stall_s

        # Active handoff operations: {old_relay_id: HandoffRecord}
        self.active_handoffs: Dict[int, HandoffRecord] = {}

        # Completed handoffs history for metrics
        self.completed_handoffs: List[HandoffRecord] = []

        # Stats
        self.total_handoffs_initiated = 0
        self.total_handoffs_completed = 0
        self.total_handoffs_aborted = 0
        self.fiedler_min_during_handoff = float('inf')
        self.overlap_durations: List[float] = []
        self._no_candidate_logged: set = set()  # Relay IDs where we already logged "no replacement"

    def step(self, uavs: List[UAV], gcs, world, sim_time: float, dt: float, path_planner=None):
        """
        Called every simulation tick. Three responsibilities:
        1. Scan relays for impending battery depletion → initiate handoffs
        2. Monitor in-flight replacements → transition to overlap
        3. Manage overlap period → complete handoffs
        """
        # Phase 1: Scan for relays that need predictive handoff
        self._scan_relay_batteries(uavs, gcs, world, sim_time, path_planner)

        # Phase 2: Update active handoffs
        self._update_handoffs(uavs, gcs, world, sim_time, dt)

    def _scan_relay_batteries(self, uavs: List[UAV], gcs, world,
                               sim_time: float, path_planner=None):
        """
        Check all active relays. If time_remaining_s() < handoff_horizon_s
        and no handoff is already in progress, initiate a predictive handoff.
        """
        for uav in uavs:
            # Only consider active relays with a relay position
            if (uav.state != UAVState.RELAY or uav.role != UAVRole.RELAY
                    or uav.relay_station_pos is None):
                continue

            # Skip if handoff already in progress for this relay
            if uav.id in self.active_handoffs:
                continue

            # Check time remaining at hover power
            time_remaining = uav.battery.time_remaining_s(
                uav.battery.hover_power_w
            )

            if time_remaining < self.handoff_horizon_s:
                # Initiate handoff (logs internally if no candidate found)
                self._initiate_handoff(uav, uavs, gcs, world, sim_time, path_planner)

    def _initiate_handoff(self, relay: UAV, uavs: List[UAV], gcs, world,
                           sim_time: float, path_planner=None):
        """
        Select the best replacement UAV and dispatch it to the relay position.

        Selection criteria (in order):
        1. Must be available (IDLE state, not critical battery)
        2. Must have enough battery to reach relay position and hover
        3. Prefer closest UAV (minimizes transit time)
        4. Prefer UAV with highest remaining battery
        """
        relay_pos = relay.relay_station_pos.copy()
        candidates = []

        for uav in uavs:
            if not uav.is_available():
                continue
            if uav.id == relay.id:
                continue
            # Skip UAVs already involved in another handoff
            if any(h.new_relay_id == uav.id
                   for h in self.active_handoffs.values()):
                continue

            # Calculate A* path distance if planner available, else straight line
            dist = float(np.linalg.norm(uav.pos - relay_pos))
            if path_planner:
                path = path_planner.plan(uav.pos, relay_pos)
                if path and len(path) > 1:
                    dist = sum(float(np.linalg.norm(path[i] - path[i-1])) 
                              for i in range(1, len(path)))
                elif not path:
                    # Impassable
                    continue

            transit_time = dist / max(uav.cruise_speed, 1.0)
            transit_energy = uav.battery.energy_for_distance(dist, uav.cruise_speed)

            # Must have enough energy for transit + at least 120s hover + return to charger
            charger_pos, charger_dist = world.nearest_recharge_station(relay_pos)
            return_energy = uav.battery.energy_for_distance(charger_dist, uav.cruise_speed)
            hover_reserve = uav.battery.hover_power_w * (120.0 / 3600.0)

            total_needed = transit_energy + hover_reserve + return_energy
            if uav.battery.current_wh < total_needed * 1.2:  # 20% safety margin
                continue

            # Score: distance penalty + battery bonus
            score = -dist + 0.5 * uav.battery.current_wh
            candidates.append((uav, score, transit_time))

        if not candidates:
            if relay.id not in self._no_candidate_logged:
                logger.warning(
                    f"[MBB] No replacement available for {relay.label} at "
                    f"t={sim_time:.1f}s — relay will deplete without handoff"
                )
                self._no_candidate_logged.add(relay.id)
            return

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        replacement, _, est_transit = candidates[0]

        # Compute current Fiedler for the handoff record
        adj = gcs.compute_connectivity_graph(uavs)
        fiedler = gcs._compute_fiedler_value(uavs, adj)

        # Create handoff record
        record = HandoffRecord(
            old_relay_id=relay.id,
            relay_pos=relay_pos,
            dispatch_time=sim_time,
            fiedler_at_dispatch=fiedler,
        )
        record.new_relay_id = replacement.id

        # Dispatch replacement as relay to the same position
        replacement.assign_relay(relay_pos, sim_time)
        self.active_handoffs[relay.id] = record
        self.total_handoffs_initiated += 1

        logger.info(
            f"[MBB] Initiated handoff: {relay.label} → {replacement.label} "
            f"at ({relay_pos[0]:.0f},{relay_pos[1]:.0f}), "
            f"est. transit {est_transit:.0f}s, "
            f"relay battery {relay.battery.level*100:.0f}%"
        )

    def _update_handoffs(self, uavs: List[UAV], gcs, world,
                          sim_time: float, dt: float):
        """Update all active handoff operations."""
        completed_ids = []

        for old_id, record in self.active_handoffs.items():
            old_relay = self._find_uav(uavs, old_id)
            new_relay = self._find_uav(uavs, record.new_relay_id)

            if old_relay is None or new_relay is None:
                # UAV was lost (failed) — abort handoff
                self.total_handoffs_aborted += 1
                completed_ids.append(old_id)
                logger.warning(
                    f"[MBB] Handoff aborted (UAV lost): "
                    f"old={old_id}, new={record.new_relay_id}"
                )
                continue

            # Check if old relay has failed
            if old_relay.state == UAVState.FAILED:
                # Handoff continues — new relay takes over unilaterally
                record.state = HandoffState.COMPLETING
                record.complete_time = sim_time
                self.total_handoffs_completed += 1
                self.completed_handoffs.append(record)
                completed_ids.append(old_id)
                logger.info(
                    f"[MBB] Handoff completed (old relay failed): "
                    f"{old_relay.label} → {new_relay.label}"
                )
                continue

            if record.state == HandoffState.DISPATCHING:
                # Check if replacement has arrived at relay position
                dist_to_target = float(
                    np.linalg.norm(new_relay.pos - record.relay_pos)
                )
                if dist_to_target < self.arrival_threshold:
                    record.state = HandoffState.OVERLAPPING
                    record.overlap_start_time = sim_time
                    logger.info(
                        f"[MBB] Overlap started: {old_relay.label} + "
                        f"{new_relay.label} at t={sim_time:.1f}s"
                    )

            elif record.state == HandoffState.OVERLAPPING:
                # Compute Fiedler for safety check
                adj = gcs.compute_connectivity_graph(uavs)
                fiedler = gcs._compute_fiedler_value(uavs, adj)
                self.fiedler_min_during_handoff = min(
                    self.fiedler_min_during_handoff, fiedler
                )

                overlap_duration = sim_time - record.overlap_start_time
                stall_duration = overlap_duration - self.min_overlap_s

                # Debug instrumentation — log every tick during overlap
                logger.debug(
                    f"[MBB] OVERLAPPING: t={sim_time:.1f}s, "
                    f"fiedler={fiedler:.4f}, overlap={overlap_duration:.1f}s, "
                    f"old={old_relay.label}, new={new_relay.label}"
                )

                if overlap_duration >= self.min_overlap_s:
                    if fiedler >= self.fiedler_safety_margin:
                        # Safe to complete — send old relay to recharge
                        charger_pos, _ = world.nearest_recharge_station(
                            old_relay.pos
                        )
                        old_relay.send_to_recharge(charger_pos, sim_time)
                        record.state = HandoffState.COMPLETING
                        record.complete_time = sim_time
                        self.total_handoffs_completed += 1
                        self.overlap_durations.append(overlap_duration)
                        self.completed_handoffs.append(record)
                        completed_ids.append(old_id)

                        logger.info(
                            f"[MBB] Handoff complete: {old_relay.label} → "
                            f"{new_relay.label}, overlap={overlap_duration:.1f}s, "
                            f"Fiedler={fiedler:.3f}"
                        )

                    elif stall_duration >= self.max_stall_s:
                        # STALL TIMEOUT: Fiedler has been below safety margin
                        # for max_stall_s after min_overlap_s elapsed.
                        # Force-complete: new relay is in position, keeping both
                        # relays indefinitely wastes a UAV and blocks mission.
                        charger_pos, _ = world.nearest_recharge_station(
                            old_relay.pos
                        )
                        old_relay.send_to_recharge(charger_pos, sim_time)
                        record.state = HandoffState.COMPLETING
                        record.complete_time = sim_time
                        self.total_handoffs_completed += 1
                        self.overlap_durations.append(overlap_duration)
                        self.completed_handoffs.append(record)
                        completed_ids.append(old_id)

                        logger.warning(
                            f"[MBB] STALL TIMEOUT: Force-completing handoff "
                            f"{old_relay.label} → {new_relay.label} after "
                            f"{stall_duration:.1f}s stall (Fiedler={fiedler:.3f} "
                            f"< safety={self.fiedler_safety_margin}). "
                            f"New relay in position — proceeding under "
                            f"degraded connectivity."
                        )

                    else:
                        # Still waiting for Fiedler to recover — log delay
                        logger.warning(
                            f"[MBB] Fiedler too low ({fiedler:.3f} < "
                            f"{self.fiedler_safety_margin}) — delaying "
                            f"departure of {old_relay.label} "
                            f"(stall {stall_duration:.1f}s / "
                            f"{self.max_stall_s:.0f}s max)"
                        )

        # Clean up completed handoffs
        for old_id in completed_ids:
            del self.active_handoffs[old_id]

    @staticmethod
    def _find_uav(uavs: List[UAV], uav_id: Optional[int]) -> Optional[UAV]:
        """Find a UAV by ID."""
        if uav_id is None:
            return None
        for uav in uavs:
            if uav.id == uav_id:
                return uav
        return None

    def get_stats(self) -> Dict:
        """Return MBB handoff statistics for the final report."""
        avg_overlap = (
            sum(self.overlap_durations) / len(self.overlap_durations)
            if self.overlap_durations else 0.0
        )
        return {
            'mbb_handoffs_initiated': self.total_handoffs_initiated,
            'mbb_handoffs_completed': self.total_handoffs_completed,
            'mbb_handoffs_aborted': self.total_handoffs_aborted,
            'mbb_handoffs_active': len(self.active_handoffs),
            'mbb_avg_overlap_s': round(avg_overlap, 1),
            'mbb_fiedler_min_during_handoff': round(
                self.fiedler_min_during_handoff, 4
            ) if self.fiedler_min_during_handoff < float('inf') else None,
        }

