"""
CARES — Neighbor State Tracker

Each UAV maintains a NeighborTracker that holds EKF estimates for
every known neighbor.  When a heartbeat/telemetry packet arrives from
neighbor j, UAV i runs a KF update with the reported position as the
measurement.  When no packet arrives (comms loss, distance, fading),
UAV i runs predict-only, and the covariance grows — this is the
"uncertainty inflation" signal that ORCA uses to widen avoidance margins.

This is the bridge between EKF (per-neighbor estimation) and ORCA
(collision avoidance).  ORCA reads estimated positions + uncertainty
from this tracker instead of ground-truth uav.pos.

Design decisions:
  - Measurement is the neighbor's BROADCAST position (which is itself
    the neighbor's own EKF estimate — so we have cascaded estimation).
    In practice, with GPS σ=2.0m, this adds ~√2 × 2.0m ≈ 2.8m effective
    uncertainty, which is realistic.
  - Stale entries (no update for >30s) are pruned to prevent phantom neighbors.
  - position_uncertainty is clamped to 50m max to prevent ORCA from
    allocating absurdly large avoidance radii.
"""

import numpy as np
from typing import Dict, Optional, Tuple
from src.core.ekf import EKFState


class NeighborEstimate:
    """Estimated state of one neighbor."""
    __slots__ = ['ekf_state', 'last_update_time', 'update_count']

    def __init__(self, pos: np.ndarray, vel: np.ndarray, sim_time: float,
                 init_pos_var: float = 10.0):
        self.ekf_state = EKFState(pos, vel, pos_var=init_pos_var, vel_var=2.0)
        self.last_update_time = sim_time
        self.update_count = 0


class NeighborTracker:
    """
    Per-UAV neighbor state tracker.
    Maintains EKF estimates for each known neighbor.
    """

    # KF parameters for neighbor tracking
    GPS_SIGMA = 3.0          # Neighbor broadcast uncertainty (higher than self GPS)
    PROCESS_NOISE_POS = 0.2  # Position process noise
    PROCESS_NOISE_VEL = 2.0  # Velocity process noise
    STALE_TIMEOUT = 30.0     # Prune neighbors not heard from in 30s
    MAX_UNCERTAINTY = 50.0   # Clamp position uncertainty

    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        self.neighbors: Dict[int, NeighborEstimate] = {}

        # Stats
        self.total_updates = 0
        self.total_predictions = 0

    def predict_all(self, dt: float, sim_time: float):
        """
        Run predict step on all neighbor estimates.
        Called every tick.  Neighbors with no recent update will see
        their covariance grow monotonically (this is the key signal).
        """
        stale_ids = []
        for nid, est in self.neighbors.items():
            # KF predict
            self._predict(est.ekf_state, dt)
            self.total_predictions += 1

            # Prune stale entries
            if sim_time - est.last_update_time > self.STALE_TIMEOUT:
                stale_ids.append(nid)

        for nid in stale_ids:
            del self.neighbors[nid]

    def update_neighbor(self, neighbor_id: int, reported_pos: np.ndarray,
                        reported_vel: np.ndarray, sim_time: float):
        """
        Update neighbor estimate with a received telemetry packet.
        If neighbor is new, create a fresh entry.
        """
        if neighbor_id not in self.neighbors:
            self.neighbors[neighbor_id] = NeighborEstimate(
                reported_pos, reported_vel, sim_time
            )
        else:
            est = self.neighbors[neighbor_id]
            # KF measurement update
            self._update(est.ekf_state, reported_pos)
            est.last_update_time = sim_time
            est.update_count += 1

        self.total_updates += 1

    def get_estimated_pos(self, neighbor_id: int) -> Optional[np.ndarray]:
        """Get estimated position of a neighbor, or None if unknown."""
        est = self.neighbors.get(neighbor_id)
        if est is None:
            return None
        return est.ekf_state.pos

    def get_position_uncertainty(self, neighbor_id: int) -> float:
        """
        Get position uncertainty (meters) for a neighbor.
        Returns MAX_UNCERTAINTY if neighbor is unknown.
        """
        est = self.neighbors.get(neighbor_id)
        if est is None:
            return self.MAX_UNCERTAINTY
        unc = est.ekf_state.pos_uncertainty
        return min(unc, self.MAX_UNCERTAINTY)

    def get_all_estimates(self) -> Dict[int, Tuple[np.ndarray, float]]:
        """
        Returns: {neighbor_id: (estimated_pos, uncertainty)}
        """
        result = {}
        for nid, est in self.neighbors.items():
            unc = min(est.ekf_state.pos_uncertainty, self.MAX_UNCERTAINTY)
            result[nid] = (est.ekf_state.pos, unc)
        return result

    def get_stats(self) -> Dict:
        """Stats for the final report."""
        uncertainties = [
            min(est.ekf_state.pos_uncertainty, self.MAX_UNCERTAINTY)
            for est in self.neighbors.values()
        ]
        return {
            'tracked_neighbors': len(self.neighbors),
            'total_updates': self.total_updates,
            'total_predictions': self.total_predictions,
            'avg_uncertainty_m': round(
                sum(uncertainties) / len(uncertainties), 2
            ) if uncertainties else 0.0,
            'max_uncertainty_m': round(
                max(uncertainties), 2
            ) if uncertainties else 0.0,
        }

    @staticmethod
    def _predict(state: EKFState, dt: float):
        """Predict step for a neighbor's EKF state."""
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1,  0],
            [0, 0, 0,  1],
        ], dtype=np.float64)

        dt2 = dt * dt
        q_pos = NeighborTracker.PROCESS_NOISE_POS
        q_vel = NeighborTracker.PROCESS_NOISE_VEL
        Q = np.array([
            [dt2 * q_pos, 0, 0, 0],
            [0, dt2 * q_pos, 0, 0],
            [0, 0, dt2 * q_vel, 0],
            [0, 0, 0, dt2 * q_vel],
        ], dtype=np.float64)

        state.x = F @ state.x
        state.P = F @ state.P @ F.T + Q

    @staticmethod
    def _update(state: EKFState, measured_pos: np.ndarray):
        """Update step with a position measurement."""
        H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)

        R = np.diag([
            NeighborTracker.GPS_SIGMA ** 2,
            NeighborTracker.GPS_SIGMA ** 2,
        ]).astype(np.float64)

        z = np.array([measured_pos[0], measured_pos[1]], dtype=np.float64)
        y = z - H @ state.x
        S = H @ state.P @ H.T + R
        K = state.P @ H.T @ np.linalg.inv(S)

        state.x = state.x + K @ y
        state.P = (np.eye(4) - K @ H) @ state.P

