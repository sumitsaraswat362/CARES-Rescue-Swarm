"""
CARES — ORCA + CBF Collision and Connectivity Avoidance Module
Implements Optimal Reciprocal Collision Avoidance (van den Berg et al., 2011)
augmented with Control Barrier Functions (CBF) for Connectivity Maintenance
(inspired by Sujit et al. ICUAS 2024).

Computes safe velocities for each UAV that avoid inter-agent collisions,
geofence violations, AND enforce the Fiedler eigenvalue (λ2) to stay
above a minimum connectivity threshold.
"""

import numpy as np
from scipy.optimize import minimize
from typing import List, Dict, Tuple, Optional


class ORCAManager:
    def __init__(self, min_separation: float = 5.0, max_speed: float = 15.0,
                 time_horizon: float = 10.0, sensing_range: float = 80.0):
        self.min_separation = min_separation       # Collision COUNTING threshold (real danger zone)
        self.planning_separation = 12.0            # ORCA PLANNING threshold (avoidance buffer)
        self.max_speed = max_speed
        self.time_horizon = time_horizon
        self.sensing_range = sensing_range
        self.collision_count = 0  # Track actual near-misses at min_separation
        
        # CBF Connectivity parameters
        self.min_fiedler = 0.05  # λ2_min
        self.cbf_alpha = 1.0     # Relaxation coefficient

    def compute_safe_velocities(self, uavs: List,
                                 bounds: Optional[Tuple[float, float, float, float]] = None,
                                 gcs = None) -> Dict[int, np.ndarray]:
        """
        Computes ORCA-based safe velocities and CBF connectivity guarantees,
        then APPLIES them back to each UAV's velocity vector.
        """
        safe_velocities = {}
        
        # 1. Compute current global connectivity if GCS provided (for CBF)
        current_fiedler = 1.0
        if gcs is not None:
            try:
                adj = gcs.compute_connectivity_graph(uavs)
                current_fiedler = gcs._compute_fiedler_value(uavs, adj)
            except Exception:
                pass

        for i, uav in enumerate(uavs):
            if not uav.is_active():
                safe_velocities[i] = np.zeros(2)
                continue

            # Preferred velocity is current velocity
            v_pref = uav.vel.copy()
            if np.linalg.norm(v_pref) > self.max_speed:
                v_pref = (v_pref / np.linalg.norm(v_pref)) * self.max_speed

            constraints = []

            # Use estimated positions for CBF
            # If the UAV hasn't received telemetry from neighbors, their estimated positions
            # might drift. ORCA uses these estimates.
            all_estimates = uav.neighbor_tracker.get_all_estimates() if hasattr(uav, 'neighbor_tracker') else {}
            
            # ── CBF Connectivity Constraint ──
            if gcs is not None:
                # EKF Pillar 2: Use estimated positions for CBF gradient
                # UAV 'i' plans using its own local estimates of the swarm
                original_positions = {u.id: u.pos.copy() for u in uavs}
                
                for neighbor in uavs:
                    if neighbor.id in all_estimates:
                        est_pos, _ = all_estimates[neighbor.id]
                        neighbor.pos = est_pos
                
                est_current_adj = gcs.compute_connectivity_graph(uavs)
                est_current_fiedler = gcs._compute_fiedler_value(uavs, est_current_adj)
                
                if est_current_fiedler < self.min_fiedler * 2.0:
                    # h(x) = λ2(x) - λ2_min
                    hx = est_current_fiedler - self.min_fiedler
                    
                    # Compute ∇λ2 via finite differences
                    eps = 0.5
                    
                    # Nudge X
                    original_pos = uav.pos.copy()
                    uav.pos[0] += eps
                    adj_x = gcs.compute_connectivity_graph(uavs)
                    fiedler_x = gcs._compute_fiedler_value(uavs, adj_x)
                    grad_x = (fiedler_x - est_current_fiedler) / eps
                    uav.pos = original_pos.copy()
                    
                    # Nudge Y
                    uav.pos[1] += eps
                    adj_y = gcs.compute_connectivity_graph(uavs)
                    fiedler_y = gcs._compute_fiedler_value(uavs, adj_y)
                    grad_y = (fiedler_y - est_current_fiedler) / eps
                    uav.pos = original_pos.copy()
                    
                    grad = np.array([grad_x, grad_y])
                    
                    if np.linalg.norm(grad) > 1e-4:
                        def make_cbf_constraint(g, h, alpha):
                            return lambda v: np.dot(g, v) + alpha * h
                        constraints.append({
                            'type': 'ineq', 
                            'fun': make_cbf_constraint(grad, hx, self.cbf_alpha)
                        })
                        
                # Restore original true positions so we don't pollute the sim state
                for u in uavs:
                    u.pos = original_positions[u.id]

            # ── ORCA Collision Constraints ──
            for j, neighbor in enumerate(uavs):
                if i == j or not neighbor.is_active():
                    continue

                # EKF Pillar 2: Use estimated position & uncertainty if available
                if j in all_estimates:
                    est_pos, uncertainty = all_estimates[j]
                    p_rel = est_pos - uav.pos
                    # Inflate avoidance radius based on neighbor's position uncertainty
                    effective_separation = self.planning_separation + (uncertainty * 1.5)
                else:
                    # Fallback if tracker not active yet
                    p_rel = neighbor.pos - uav.pos
                    effective_separation = self.planning_separation

                dist = np.linalg.norm(p_rel)
                
                alt_diff = abs(uav.altitude - getattr(neighbor, 'altitude', 0.0))
                if alt_diff > 10.0:
                    # 3D Separation: UAVs are in different altitude layers, ignore lateral collision
                    continue

                if dist > self.sensing_range:
                    continue

                # Track near-misses
                if not hasattr(self, 'active_collisions'):
                    self.active_collisions = set()
                pair = tuple(sorted((i, j)))
                
                # Count REAL physical near-misses using min_separation,
                # NOT the EKF-inflated effective_separation (which is for planning only)
                if dist < self.min_separation:
                    if pair not in self.active_collisions:
                        self.collision_count += 1
                        self.active_collisions.add(pair)
                elif dist > self.min_separation + 1.0:
                    if pair in self.active_collisions:
                        self.active_collisions.remove(pair)

                if dist < 1e-6:
                    p_rel = np.random.randn(2) * 0.1
                    dist = np.linalg.norm(p_rel)

                v_rel = uav.vel - neighbor.vel
                n = p_rel / dist
                v_rel_dot_n = np.dot(v_rel, n)

                # ORCA half-plane
                u = n * max(0, (effective_separation - dist) / self.time_horizon + v_rel_dot_n)

                def make_orca_constraint(n_vec, u_vec, v_current):
                    return lambda v: -np.dot(v, n_vec) + np.dot(v_current + u_vec / 2.0, n_vec)

                constraints.append({'type': 'ineq', 'fun': make_orca_constraint(n, u, uav.vel)})

            # Objective: minimize ||v - v_pref||^2
            def objective(v):
                return np.sum((v - v_pref) ** 2)

            v_bounds = [(-self.max_speed, self.max_speed),
                        (-self.max_speed, self.max_speed)]

            if constraints:
                try:
                    res = minimize(objective, v_pref, method='SLSQP',
                                   bounds=v_bounds, constraints=constraints,
                                   options={'maxiter': 20, 'ftol': 1e-6})
                    v_safe = res.x if res.success else v_pref * 0.3  # Emergency: slow down, don't ignore
                except Exception:
                    v_safe = v_pref * 0.3  # Emergency braking on solver crash
            else:
                v_safe = v_pref

            # Geofence enforcement
            if bounds:
                x_min, y_min, x_max, y_max = bounds
                dt = 0.1
                next_pos = uav.pos + v_safe * dt
                if next_pos[0] < x_min or next_pos[0] > x_max:
                    v_safe[0] *= -0.5
                if next_pos[1] < y_min or next_pos[1] > y_max:
                    v_safe[1] *= -0.5

            safe_velocities[i] = v_safe

            # APPLY the safe velocity back to the UAV
            uav.vel = v_safe.copy()

        return safe_velocities

    def check_collisions(self, uavs: List) -> List[Tuple[int, int]]:
        collisions = []
        n = len(uavs)
        for i in range(n):
            if not uavs[i].is_active():
                continue
            for j in range(i + 1, n):
                if not uavs[j].is_active():
                    continue
                alt_diff = abs(uavs[i].altitude - getattr(uavs[j], 'altitude', 0.0))
                if alt_diff > 10.0:
                    continue
                dist = np.linalg.norm(uavs[i].pos - uavs[j].pos)
                if dist < self.min_separation:
                    collisions.append((i, j))
        return collisions

    def get_min_separation_observed(self, uavs: List) -> float:
        min_dist = float('inf')
        n = len(uavs)
        for i in range(n):
            if not uavs[i].is_active():
                continue
            for j in range(i + 1, n):
                if not uavs[j].is_active():
                    continue
                alt_diff = abs(uavs[i].altitude - getattr(uavs[j], 'altitude', 0.0))
                if alt_diff > 10.0:
                    continue
                d = np.linalg.norm(uavs[i].pos - uavs[j].pos)
                if d < min_dist:
                    min_dist = d
        return min_dist

