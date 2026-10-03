"""
CARES — Ground Control Station Module
Central command that aggregates telemetry and tracks mission-level metrics.
"""

import numpy as np
from typing import List, Dict, Optional
from src.core.uav import UAV, UAVState


class GCS:
    """
    Ground Control Station — aggregates UAV telemetry, tracks communication
    topology, and computes mission-level metrics.
    """

    def __init__(self, position: np.ndarray, label: str = "GCS"):
        self.pos = np.array(position, dtype=np.float64)
        self.label = label
        self.comm_range = 700.0  # Matches swarm_config max_range and LinkModel ~774m dead-zone

        # Metrics tracking
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.connectivity_log: List[Dict] = []
        self.total_ticks = 0
        self.connected_ticks = 0  # Ticks where GCS has path to at least one scout

    def can_communicate_with(self, uav: UAV) -> bool:
        """Check if GCS can directly communicate with a UAV."""
        if uav.state == UAVState.FAILED:
            return False
        return float(np.linalg.norm(self.pos - uav.pos)) <= self.comm_range

    def compute_connectivity_graph(self, uavs: List[UAV]) -> Dict[int, List[int]]:
        """
        Build adjacency list for the communication graph.
        Nodes: GCS (id=-1) + all active UAVs.
        """
        active_uavs = [u for u in uavs if u.state != UAVState.FAILED]
        adj: Dict[int, List[int]] = {-1: []}  # -1 = GCS

        for u in active_uavs:
            adj[u.id] = []

        # GCS <-> UAV links
        for u in active_uavs:
            if self.can_communicate_with(u):
                adj[-1].append(u.id)
                adj[u.id].append(-1)

        # UAV <-> UAV links
        for i, u1 in enumerate(active_uavs):
            for u2 in active_uavs[i + 1:]:
                if u1.can_communicate_with(u2):
                    adj[u1.id].append(u2.id)
                    adj[u2.id].append(u1.id)

        return adj

    def bfs_connected_to_gcs(self, adj: Dict[int, List[int]]) -> set:
        """BFS from GCS to find all nodes reachable from GCS."""
        visited = set()
        queue = [-1]  # Start from GCS
        visited.add(-1)

        while queue:
            node = queue.pop(0)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return visited

    def compute_metrics(self, uavs: List[UAV]) -> Dict:
        """
        Compute real-time communication and mission metrics.
        """
        self.total_ticks += 1
        adj = self.compute_connectivity_graph(uavs)
        reachable = self.bfs_connected_to_gcs(adj)

        active_uavs = [u for u in uavs if u.state != UAVState.FAILED]
        active_ids = {u.id for u in active_uavs}

        # How many active UAVs are reachable from GCS
        connected_ids = reachable.intersection(active_ids)
        connectivity_ratio = len(connected_ids) / max(1, len(active_ids))

        if connectivity_ratio > 0:
            self.connected_ticks += 1

        # Algebraic connectivity (Fiedler value) for the swarm subgraph
        fiedler = self._compute_fiedler_value(uavs, adj)

        metrics = {
            'connectivity_ratio': connectivity_ratio,
            'connected_uavs': len(connected_ids),
            'total_active_uavs': len(active_ids),
            'disconnected_uavs': len(active_ids) - len(connected_ids),
            'connectivity_availability': (self.connected_ticks / max(1, self.total_ticks)),
            'fiedler_value': fiedler,
            'adjacency': adj,
            'reachable_from_gcs': connected_ids,
        }
        return metrics

    def _compute_fiedler_value(self, uavs: List[UAV],
                                adj: Dict[int, List[int]]) -> float:
        """
        Compute the algebraic connectivity (second smallest eigenvalue
        of the Laplacian) of the communication graph.
        Higher = more resilient network.
        """
        # Build node list (GCS + active UAVs)
        active = [u for u in uavs if u.state != UAVState.FAILED]
        nodes = [-1] + [u.id for u in active]
        n = len(nodes)
        if n < 2:
            return 0.0

        node_to_idx = {nid: i for i, nid in enumerate(nodes)}

        # Build Laplacian matrix
        L = np.zeros((n, n))
        for nid, neighbors in adj.items():
            if nid not in node_to_idx:
                continue
            i = node_to_idx[nid]
            for nbr in neighbors:
                if nbr not in node_to_idx:
                    continue
                j = node_to_idx[nbr]
                L[i, j] = -1.0
                L[i, i] += 1.0

        # Eigenvalues
        eigenvalues = np.sort(np.real(np.linalg.eigvalsh(L)))

        # Fiedler value = second smallest eigenvalue
        if len(eigenvalues) >= 2:
            return max(0.0, float(eigenvalues[1]))
        return 0.0

    def packet_delivery_ratio(self) -> float:
        """PDR = received / (received + dropped)."""
        total = self.packets_received + self.packets_dropped
        if total == 0:
            return 1.0
        return self.packets_received / total

    def __repr__(self):
        return f"<GCS '{self.label}' pos=({self.pos[0]:.0f},{self.pos[1]:.0f})>"

