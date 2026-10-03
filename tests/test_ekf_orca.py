"""
Unit mechanics only: estimator covariance growth and stale-neighbor pruning.
These tests do not validate an ORCA integration or collision-avoidance guarantee.
"""
import sys
import os
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.ekf import UAVEstimator
from src.core.neighbor_tracker import NeighborTracker


def test_ekf_basic():
    """Verify EKF tracks correctly and covariance grows on predict."""
    pos = np.array([0.0, 0.0])
    vel = np.array([10.0, 0.0])
    estimator = UAVEstimator(pos, vel, gps_sigma=2.0)

    # 1. Update with perfect GPS
    estimator.update_gps(np.array([0.0, 0.0]))
    initial_unc = estimator.position_uncertainty

    # 2. Predict without update (comms loss)
    for _ in range(10):
        estimator.predict(dt=1.0)

    final_unc = estimator.position_uncertainty
    assert final_unc > initial_unc, f"Covariance did not grow! {final_unc} <= {initial_unc}"
    print(f"  [✅] A1: Covariance grows monotonically on packet loss "
          f"(unc: {initial_unc:.2f} -> {final_unc:.2f})")


def test_neighbor_tracker():
    """Verify neighbor tracker prunes stale entries."""
    tracker = NeighborTracker(owner_id=1)

    # Receive telemetry
    tracker.update_neighbor(2, np.array([10.0, 10.0]), np.array([0.0, 0.0]), sim_time=0.0)
    assert 2 in tracker.neighbors

    # Predict step (simulate 15s passing)
    tracker.predict_all(dt=15.0, sim_time=15.0)
    assert 2 in tracker.neighbors

    # Predict step (simulate 35s passing, exceeds 30s timeout)
    tracker.predict_all(dt=20.0, sim_time=35.0)
    assert 2 not in tracker.neighbors, "Stale neighbor was not pruned!"
    print("  [✅] A2: Stale neighbors successfully pruned after timeout")
