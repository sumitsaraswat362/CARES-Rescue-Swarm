"""
CARES — Optimal Relay Placement Module
Computes relay UAV positions to maintain multi-hop connectivity between
the GCS and actively surveying scouts.

Methodology:
1. Places initial relay candidates along lines from GCS to scouts.
2. Applies a spring-force (gradient-based) relaxation algorithm to maximize
   minimum link quality across the formed mesh topology, pulling disconnected
   nodes together and pushing densely clustered nodes apart.
"""

import numpy as np
from typing import List


def compute_optimal_relay_positions(gcs_pos: np.ndarray,
                                    scout_positions: List[np.ndarray],
                                    num_relays: int,
                                    comm_range: float) -> List[np.ndarray]:
    """
    Computes optimal positions for relay UAVs to maintain connectivity.
    Iteratively adjusts to maximize minimum link quality across the network.
    """
    if num_relays <= 0 or not scout_positions:
        return []

    # 1. Calculate distances from GCS to scouts
    distances = [float(np.linalg.norm(scout_pos - gcs_pos)) for scout_pos in scout_positions]
    
    # 2. Sort scouts by distance (descending) to prioritize far scouts
    sorted_indices = np.argsort(distances)[::-1]
    
    relay_positions = []
    relays_left = num_relays
    
    safe_comm_range = comm_range * 0.8  # Target distance between hops
    
    # 3. Distribute initial relay positions among the furthest scouts
    for idx in sorted_indices:
        if relays_left <= 0:
            break
            
        scout_pos = scout_positions[idx]
        dist = distances[idx]
        
        # If scout is within safe comm range of GCS, skip
        if dist <= safe_comm_range:
            continue
            
        # Estimate how many relays needed for this straight line
        relays_needed = int(np.ceil(dist / safe_comm_range)) - 1
        relays_to_assign = min(relays_needed, relays_left)
        
        if relays_to_assign > 0:
            # Place relays evenly along the line
            direction = (scout_pos - gcs_pos) / dist
            step = dist / (relays_to_assign + 1)
            
            for i in range(1, relays_to_assign + 1):
                pos = gcs_pos + direction * (step * i)
                relay_positions.append(pos)
                
            relays_left -= relays_to_assign
            
    # If there are still relays left, distribute them near the GCS randomly
    while relays_left > 0:
        angle = np.random.uniform(0, 2 * np.pi)
        r = np.random.uniform(0, safe_comm_range * 0.5)
        relay_positions.append(gcs_pos + np.array([r * np.cos(angle), r * np.sin(angle)]))
        relays_left -= 1
        
    # 4. Spring-force Gradient Relaxation
    # Adjust each relay to maximize minimum link quality across all neighbors
    iterations = 50
    lr = 2.0  # learning rate / step size
    
    for _ in range(iterations):
        # We don't move GCS or Scouts, only Relays
        for i in range(len(relay_positions)):
            pos = relay_positions[i]
            grad = np.zeros(2)
            
            # Repulsive/Attractive forces from all other nodes
            other_nodes = [gcs_pos] + scout_positions + [p for j, p in enumerate(relay_positions) if j != i]
            
            for other_pos in other_nodes:
                diff = other_pos - pos
                dist_to_other = float(np.linalg.norm(diff))
                
                if dist_to_other > 0:
                    if dist_to_other > comm_range:
                        # Spring tension: Pull towards disconnected nodes (attractive)
                        grad += (diff / dist_to_other) * lr
                    elif dist_to_other < comm_range * 0.4:
                        # Collision avoidance: Push away if too clustered (repulsive)
                        grad -= (diff / dist_to_other) * lr
                        
            relay_positions[i] += grad
            
    return relay_positions

