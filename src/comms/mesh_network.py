"""
CARES — Multi-Hop Mesh Network Module
Implements real BFS-based packet routing over the communication graph.
Each hop uses LinkModel.packet_success_probability(distance) to determine
whether the packet survives that hop, with NLOS penalty for obstacles.
Implements Event-Triggered Communication (Sujit et al.) to reduce bandwidth.
"""

import random
from collections import deque
from typing import List, Dict, Optional, Tuple
from src.comms.protocol import Message, MessageType
from src.comms.link_model import LinkModel
import numpy as np


class MeshNetwork:
    """
    Multi-hop mesh network that routes packets from UAVs to GCS (and vice versa)
    through the swarm's communication graph using BFS shortest-path routing.
    Each hop applies a realistic packet success probability from the Friis
    free-space path-loss model via LinkModel, penalized by NLOS blockages.
    """

    def __init__(self, link_model: LinkModel, uavs, gcs, world):
        self.link_model = link_model
        self.uavs = uavs
        self.gcs = gcs
        self.world = world  # For LOS checking
        self.queue: deque = deque()
        self.msg_counter = 0

        # Per-tick statistics
        self.stats = {
            'total_sent': 0,
            'total_delivered': 0,
            'total_dropped': 0,
            'total_latency': 0.0,
            'total_hops': 0,
            'naive_messages': 0,
            'event_messages': 0,
        }

        # Per-hop latency model (seconds)
        self.per_hop_latency = 0.005  # 5ms per hop (realistic for 2.4GHz mesh)
        self.processing_latency = 0.002  # 2ms processing per node
        
        # Event-triggered communication state
        self.last_tx_state = {}

    def _get_link_success_prob(self, p1: np.ndarray, p2: np.ndarray) -> float:
        """
        Compute hop success probability in dB-space.
        NLOS penalty is +25 dB additive to path loss, not a probability multiplier.
        This ensures a blocked 300m link is actually dead (~-97 dBm < sensitivity),
        while a clear 600m link still has a fighting chance (~40% quality).
        """
        dist = float(np.linalg.norm(p1 - p2))
        nlos = self.world.is_line_of_sight_blocked(p1, p2)
        pl_db = self.link_model.path_loss_db(dist, nlos=nlos)
        prx = self.link_model.tx_power_dbm - pl_db
        return self.link_model.link_quality_from_prx(prx)

    def _build_adjacency(self) -> Dict[int, List[int]]:
        """
        Build adjacency list using the link model + NLOS.
        Node IDs: -1 = GCS, 0..N-1 = UAV IDs.
        """
        from src.core.uav import UAVState
        active_uavs = [u for u in self.uavs if u.state != UAVState.FAILED]
        adj: Dict[int, List[int]] = {-1: []}

        for u in active_uavs:
            adj[u.id] = []

        # GCS <-> UAV links
        for u in active_uavs:
            if self._get_link_success_prob(self.gcs.pos, u.pos) > 0.05:
                adj[-1].append(u.id)
                adj[u.id].append(-1)

        # UAV <-> UAV links
        for i, u1 in enumerate(active_uavs):
            for u2 in active_uavs[i + 1:]:
                if self._get_link_success_prob(u1.pos, u2.pos) > 0.05:
                    adj[u1.id].append(u2.id)
                    adj[u2.id].append(u1.id)

        return adj

    def _get_node_pos(self, node_id: int) -> Optional[np.ndarray]:
        """Get position of a network node by ID."""
        if node_id == -1:
            return self.gcs.pos
        for u in self.uavs:
            if u.id == node_id:
                return u.pos
        return None

    def _bfs_path(self, adj: Dict[int, List[int]],
                  src: int, dst: int) -> Optional[List[int]]:
        """
        BFS shortest path from src to dst in the adjacency graph.
        Returns list of node IDs forming the path, or None if unreachable.
        """
        if src == dst:
            return [src]
        if src not in adj:
            return None

        visited = {src}
        queue = deque([(src, [src])])

        while queue:
            node, path = queue.popleft()
            for neighbor in adj.get(node, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_path = path + [neighbor]
                if neighbor == dst:
                    return new_path
                queue.append((neighbor, new_path))

        return None  # No path exists

    def send(self, message: Message) -> bool:
        """Queue a message for routing."""
        self.msg_counter += 1
        message.msg_id = self.msg_counter
        self.queue.append(message)
        self.stats['total_sent'] += 1
        self.stats['event_messages'] += 1
        return True

    def route_packet(self, msg: Message, adj: Dict[int, List[int]]) -> bool:
        """
        Route a single packet from sender to receiver using BFS multi-hop.
        At each hop, apply packet_success_probability + NLOS.
        Returns True if delivered, False if dropped.
        """
        src = msg.sender_id
        dst = msg.receiver_id

        # Broadcast messages go to GCS
        if dst == -1 or dst == -2:
            dst = -1

        # Find shortest path
        path = self._bfs_path(adj, src, dst)

        if path is None or len(path) < 2:
            # No route exists — packet dropped
            self.stats['total_dropped'] += 1
            self.gcs.packets_dropped += 1
            return False

        # Simulate hop-by-hop delivery
        total_latency = 0.0
        hops = 0

        for i in range(len(path) - 1):
            from_id = path[i]
            to_id = path[i + 1]

            from_pos = self._get_node_pos(from_id)
            to_pos = self._get_node_pos(to_id)

            if from_pos is None or to_pos is None:
                self.stats['total_dropped'] += 1
                self.gcs.packets_dropped += 1
                return False

            p_success = self._get_link_success_prob(from_pos, to_pos)

            if random.random() > p_success:
                # Packet lost at this hop
                self.stats['total_dropped'] += 1
                self.gcs.packets_dropped += 1
                return False

            # Accumulate latency
            total_latency += self.per_hop_latency + self.processing_latency
            hops += 1

            # TTL check
            if hops > msg.ttl:
                self.stats['total_dropped'] += 1
                self.gcs.packets_dropped += 1
                return False

        # Packet delivered successfully
        self.stats['total_delivered'] += 1
        self.stats['total_latency'] += total_latency
        self.stats['total_hops'] += hops
        self.gcs.packets_received += 1
        return True

    def step(self, dt: float):
        """
        Process the message queue for this tick.
        Also applies burst outage drops (CARES_BURST_PROB env var) to simulate
        stochastic link outages that differ between Monte Carlo seeds.
        """
        if not self.queue:
            return

        # Burst outage probability — drives Monte Carlo variance.
        # Set via CARES_BURST_PROB env var in run_batch.py.
        import os
        burst_prob = float(os.environ.get("CARES_BURST_PROB", "0.0"))

        adj = self._build_adjacency()

        while self.queue:
            msg = self.queue.popleft()

            # Burst outage: randomly kill the packet before routing
            if burst_prob > 0.0 and random.random() < burst_prob:
                self.stats['total_dropped'] += 1
                self.gcs.packets_dropped += 1
                continue

            self.route_packet(msg, adj)

    def broadcast_local_estimates(self, sim_time: float):
        """
        Pillar 2: EKF local broadcast.
        Each UAV updates its own GPS and broadcasts its estimated state to 1-hop neighbors.
        """
        import os
        burst_prob = float(os.environ.get("CARES_BURST_PROB", "0.0"))
        
        from src.core.uav import UAVState
        
        # 1. Every active UAV gets a new noisy GPS reading
        for uav in self.uavs:
            if uav.state != UAVState.FAILED:
                uav.update_gps_measurement()
                
        # 2. Broadcast estimated state to 1-hop neighbors
        for uav in self.uavs:
            if uav.state == UAVState.FAILED:
                continue
                
            est_pos = uav.estimator.estimated_pos
            est_vel = uav.estimator.estimated_vel
            
            for neighbor in self.uavs:
                if uav.id == neighbor.id or neighbor.state == UAVState.FAILED:
                    continue
                    
                # Check 1-hop communication range
                dist = float(np.linalg.norm(uav.pos - neighbor.pos))
                if dist <= uav.comm_range:
                    # Apply stochastic packet loss
                    if burst_prob == 0.0 or random.random() >= burst_prob:
                        neighbor.receive_telemetry(uav.id, est_pos, est_vel, sim_time)

    def generate_heartbeats(self, sim_time: float):
        """
        Event-Triggered Communication (ED-CBBA style).
        Instead of broadcasting every tick, only broadcast if:
        1. State changed
        2. Position changed by > 5 meters
        3. Max silence (2.0s) exceeded
        """
        from src.core.uav import UAVState
        
        # Track naive baseline for proposal comparisons
        active_count = sum(1 for u in self.uavs if u.state != UAVState.FAILED)
        self.stats['naive_messages'] += active_count
        
        for uav in self.uavs:
            if uav.state == UAVState.FAILED:
                continue
                
            trigger = False
            if uav.id not in self.last_tx_state:
                trigger = True
            else:
                last = self.last_tx_state[uav.id]
                if last['state'] != uav.state:
                    trigger = True
                elif float(np.linalg.norm(last['pos'] - uav.pos)) > 5.0:
                    trigger = True
                elif sim_time - last['time'] >= 2.0:
                    trigger = True
                    
            if trigger:
                self.last_tx_state[uav.id] = {
                    'time': sim_time,
                    'pos': uav.pos.copy(),
                    'state': uav.state
                }
                msg = Message(
                    msg_type=MessageType.HEARTBEAT,
                    sender_id=uav.id,
                    receiver_id=-1,  # GCS
                    payload={'battery': uav.battery.level, 'state': uav.state.value},
                    timestamp=sim_time,
                    ttl=5,
                )
                self.send(msg)

    def generate_telemetry(self, sim_time: float):
        """
        Event-Triggered Telemetry.
        """
        from src.core.uav import UAVState
        
        # Base count telemetry if they were sending it
        scout_count = sum(1 for u in self.uavs if u.state == UAVState.SCOUT and u.target_pos is not None)
        self.stats['naive_messages'] += scout_count
        
        for uav in self.uavs:
            if uav.state == UAVState.SCOUT and uav.target_pos is not None:
                # Same ED logic
                trigger = False
                key = f"tel_{uav.id}"
                if key not in self.last_tx_state:
                    trigger = True
                else:
                    last = self.last_tx_state[key]
                    if float(np.linalg.norm(last['pos'] - uav.pos)) > 2.0:  # tighter threshold for telemetry
                        trigger = True
                    elif sim_time - last['time'] >= 1.0:
                        trigger = True
                        
                if trigger:
                    self.last_tx_state[key] = {
                        'time': sim_time,
                        'pos': uav.pos.copy()
                    }
                    msg = Message(
                        msg_type=MessageType.TELEMETRY,
                        sender_id=uav.id,
                        receiver_id=-1,
                        payload={
                            'pos': uav.pos.tolist(),
                            'target': uav.target_pos.tolist(),
                            'battery': uav.battery.level,
                        },
                        timestamp=sim_time,
                        ttl=5,
                    )
                    self.send(msg)

    def get_stats(self) -> dict:
        """PDR, avg latency, avg hops, and ED-CBBA savings."""
        sent = self.stats['total_sent']
        delivered = self.stats['total_delivered']
        dropped = self.stats['total_dropped']
        
        # PDR calculation (real metrics)
        pdr = (delivered / max(1, delivered + dropped)) * 100
        avg_latency = (self.stats['total_latency'] / max(1, delivered)) * 1000  # ms
        avg_hops = self.stats['total_hops'] / max(1, delivered)
        
        # ED-CBBA savings %
        naive = max(1, self.stats['naive_messages'])
        event = self.stats['event_messages']
        msg_reduction_pct = ((naive - event) / naive) * 100.0

        return {
            'pdr': round(pdr, 1),
            'avg_latency_ms': round(avg_latency, 2),
            'avg_hops': round(avg_hops, 2),
            'total_sent': sent,
            'total_delivered': delivered,
            'total_dropped': dropped,
            'msg_reduction_pct': round(msg_reduction_pct, 1),
        }

