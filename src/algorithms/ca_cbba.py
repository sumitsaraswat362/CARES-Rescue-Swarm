"""
CARES — Communication-Aware Consensus-Based Bundle Algorithm (CA-CBBA)

Extends CBBA (Choi et al., 2009) with a connectivity-aware utility term
that uses the actual algebraic connectivity (Fiedler value λ₂) of the
communication graph Laplacian.

Key differences from standard CBBA:
  1. Utility function includes Δλ₂ — the change in Fiedler value if
     agent i moves to task j. Computed by constructing the hypothetical
     adjacency matrix and solving the eigenvalue problem.
  2. Iterative consensus: agents build bundles, broadcast bids, and
     resolve conflicts over multiple rounds until convergence (not a
     single centralized greedy pass).
  3. Relay/scout partitioning adapts to current Fiedler value.

References:
  - Choi, Han, Johnson (2009): CBBA for multi-agent task allocation
  - Sujit et al. (2024): Event-driven CBBA variant for constrained comms
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from src.algorithms.relay_placement import compute_optimal_relay_positions
from src.core.uav import UAV, UAVState, UAVRole


class CACBBA:
    def __init__(self, uavs: List[UAV], world, gcs,
                 alpha: float = 0.35, beta: float = 0.40, gamma: float = 0.25):
        self.uavs = uavs
        self.world = world
        self.gcs = gcs
        self.alpha = alpha   # Priority / distance weight
        self.beta = beta     # Connectivity gain weight
        self.gamma = gamma   # Battery feasibility weight
        self.max_consensus_iters = 5  # Number of bid-exchange-resolve rounds
        self.allocation_count = 0

    # ── Fiedler-Based Connectivity Gain ──────────────────────────────────

    def _build_hypothetical_adjacency(self, uavs: List[UAV],
                                       override: Optional[Dict[int, np.ndarray]] = None
                                       ) -> Dict[int, List[int]]:
        """
        Build the communication adjacency graph, optionally overriding
        positions for specific UAVs (to simulate hypothetical moves).
        """
        def get_pos(u):
            if override and u.id in override:
                return override[u.id]
            return u.pos

        active = [u for u in uavs if u.state != UAVState.FAILED]
        adj: Dict[int, List[int]] = {-1: []}
        for u in active:
            adj[u.id] = []

        # GCS <-> UAV links
        gcs_pos = self.gcs.pos
        for u in active:
            d = float(np.linalg.norm(gcs_pos - get_pos(u)))
            if d <= self.gcs.comm_range:
                adj[-1].append(u.id)
                adj[u.id].append(-1)

        # UAV <-> UAV links
        for i, u1 in enumerate(active):
            for u2 in active[i + 1:]:
                d = float(np.linalg.norm(get_pos(u1) - get_pos(u2)))
                if d <= u1.comm_range:
                    adj[u1.id].append(u2.id)
                    adj[u2.id].append(u1.id)

        return adj

    def _compute_fiedler(self, adj: Dict[int, List[int]]) -> float:
        """
        Compute the Fiedler value (λ₂ of the graph Laplacian).
        Uses the same eigenvalue method as gcs._compute_fiedler_value
        but operates on any adjacency dict.
        """
        nodes = sorted(adj.keys())
        n = len(nodes)
        if n < 2:
            return 0.0

        node_to_idx = {nid: i for i, nid in enumerate(nodes)}
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

        eigenvalues = np.sort(np.real(np.linalg.eigvalsh(L)))
        if len(eigenvalues) >= 2:
            return max(0.0, float(eigenvalues[1]))
        return 0.0

    def compute_connectivity_gain(self, agent: UAV, task_pos: np.ndarray) -> float:
        """
        Compute Δλ₂: the change in algebraic connectivity if agent
        moves from its current position to task_pos.

        This is the actual graph-theoretic computation, not a heuristic.
        We build two adjacency matrices — current and hypothetical —
        and return fiedler(hypothetical) - fiedler(current).
        """
        # Current Fiedler value
        adj_current = self._build_hypothetical_adjacency(self.uavs)
        fiedler_current = self._compute_fiedler(adj_current)

        # Hypothetical: agent moves to task_pos
        adj_hyp = self._build_hypothetical_adjacency(
            self.uavs, override={agent.id: task_pos}
        )
        fiedler_hyp = self._compute_fiedler(adj_hyp)

        return fiedler_hyp - fiedler_current

    # ── Battery Feasibility ──────────────────────────────────────────────

    def battery_feasibility(self, energy_required_wh: float,
                             energy_available_wh: float) -> float:
        """
        Sigmoid function smoothly penalizing infeasible assignments.
        Returns [0, 1] where 1 = plenty of energy, 0 = infeasible.
        """
        if energy_available_wh <= 0:
            return 0.0
        ratio = energy_required_wh / energy_available_wh
        # Clamp exponent to prevent overflow
        exp_arg = 5.0 * (ratio - 0.7)
        exp_arg = min(exp_arg, 50.0)  # Prevent overflow
        return 1.0 / (1.0 + np.exp(exp_arg))

    # ── Utility Function ─────────────────────────────────────────────────

    def utility(self, agent: UAV, task) -> float:
        """
        U(i, j) = α · Priority(j)/Distance(i,j)
                 + β · Δλ₂(i→j)
                 + γ · BatteryFeasibility(i,j)
                 - δ · LoadPenalty(i)
        """
        task_pos = np.array([task.x, task.y])
        dist = np.linalg.norm(agent.pos - task_pos)
        if dist < 1.0:
            dist = 1.0

        # Term 1: Priority / distance
        pri_term = task.priority / dist

        # Term 2: Actual Fiedler-based connectivity delta
        conn_gain = self.compute_connectivity_gain(agent, task_pos)

        # Term 3: Battery feasibility using real energy model
        energy_req = agent.battery.energy_for_distance(dist, agent.cruise_speed)
        energy_avail = agent.battery.current_wh
        batt_term = self.battery_feasibility(energy_req, energy_avail)

        # Term 4: Load penalty — combines intra-round and lifetime task balance
        # Intra-round: tasks won in THIS CBBA allocation (from winning_agents)
        tasks_won_now = sum(1 for wid in agent.winning_agents.values() if wid == agent.id)
        # Lifetime: tasks already completed in prior rounds
        tasks_done = len(agent.tasks_completed) if hasattr(agent, 'tasks_completed') else 0
        # Active: currently flying to a task
        tasks_active = 1 if agent.assigned_task_id is not None else 0
        total_load = tasks_won_now + tasks_done + tasks_active
        load_penalty = 0.35 ** total_load  # 1.0→0.35→0.12→0.04...

        base_score = self.alpha * pri_term + self.beta * conn_gain + self.gamma * batt_term
        return base_score * load_penalty

    # ── CBBA Consensus Rounds ────────────────────────────────────────────

    def _bundle_build(self, agents: List['UAV'], tasks: list) -> Dict[int, Tuple[int, float]]:
        """
        Phase 1: Each agent greedily selects its highest-utility task that it can win.
        It uses its local knowledge of `winning_bids` to determine if it can outbid
        the current winner. No centralized 'claimed_tasks' cheat is used.
        """
        bids = {}

        for agent in agents:
            # Pass 1: Keep active task if we already have one
            if agent.assigned_task_id is not None:
                poi = self.world.get_poi_by_id(agent.assigned_task_id)
                if poi and not poi.surveyed:
                    # We are actively flying this task, maintain our claim
                    bid_val = agent.winning_bids.get(agent.assigned_task_id, 
                                                      self.utility(agent, poi))
                    bids[agent.id] = (agent.assigned_task_id, bid_val)
                    agent.winning_bids[agent.assigned_task_id] = bid_val
                    agent.winning_agents[agent.assigned_task_id] = agent.id
                    continue
                    
            # Pass 2: If idle, check if we ALREADY won a task in this CBBA round
            my_won_tasks = [tid for tid, wid in agent.winning_agents.items() if wid == agent.id]
            if my_won_tasks:
                best_task_id = my_won_tasks[0]
                bids[agent.id] = (best_task_id, agent.winning_bids[best_task_id])
                continue

            # Pass 3: Bid on a new task
            best_task = None
            best_util = -float('inf')

            for task in tasks:
                u = self.utility(agent, task)
                current_winning_bid = agent.winning_bids.get(task.id, -float('inf'))
                current_winner = agent.winning_agents.get(task.id, -1)
                
                # CBBA outbid rule: strictly greater utility, or tie-break on lower agent ID
                can_outbid = (u > current_winning_bid) or (u == current_winning_bid and agent.id < current_winner)
                
                if can_outbid and u > best_util:
                    best_util = u
                    best_task = task

            if best_task is not None:
                bids[agent.id] = (best_task.id, best_util)
                agent.winning_bids[best_task.id] = best_util
                agent.winning_agents[best_task.id] = agent.id

        return bids

    def _consensus_resolve(self, agents: List['UAV'], 
                            bids: Dict[int, Tuple[int, float]]) -> Dict[int, Tuple[int, float]]:
        """
        Phase 2: Gossip CBBA consensus using the REAL mesh adjacency graph.
        Information propagates strictly 1 hop per iteration.
        """
        # Use the real mesh adjacency graph (respects NLOS blocking)
        try:
            real_adj = self.gcs.compute_connectivity_graph(self.uavs)
        except Exception:
            real_adj = {a.id: [] for a in agents}
            for i, a in enumerate(agents):
                for b in agents[i+1:]:
                    if float(np.linalg.norm(a.pos - b.pos)) <= a.comm_range:
                        real_adj[a.id].append(b.id)
                        real_adj[b.id].append(a.id)

        # 1-Hop Gossip Exchange (simulating 1 packet exchange per physical neighbor)
        messages = {
            a.id: {
                'bids': a.winning_bids.copy(),
                'agents': a.winning_agents.copy()
            }
            for a in agents
        }

        # Process messages from 1-hop neighbors
        for a in agents:
            neighbor_ids = real_adj.get(a.id, [])
            for nbr_id in neighbor_ids:
                if nbr_id not in messages:
                    continue  # Skip GCS or non-scouts
                
                msg = messages[nbr_id]
                for task_id, neighbor_bid in msg['bids'].items():
                    neighbor_winner = msg['agents'][task_id]
                    
                    my_bid = a.winning_bids.get(task_id, -float('inf'))
                    my_winner = a.winning_agents.get(task_id, -1)
                    
                    # CBBA conflict resolution rule
                    if (neighbor_bid > my_bid) or (neighbor_bid == my_bid and neighbor_winner < my_winner):
                        a.winning_bids[task_id] = neighbor_bid
                        a.winning_agents[task_id] = neighbor_winner

        # Build resolved assignments from each agent's strictly LOCAL knowledge.
        # This preserves the intended limitation: if diameter > max_iters, inconsistencies remain.
        resolved = {}
        for a in agents:
            for task_id, winner_id in a.winning_agents.items():
                if winner_id == a.id:
                    resolved[a.id] = (task_id, a.winning_bids[task_id])
                    break # Only 1 task per agent

        return resolved

    def _compute_relay_budget(self, available: list, unsurveyed: list,
                               current_fiedler: float) -> int:
        """
        Distance-driven relay budget: compute how many relay hops are needed
        to physically bridge the furthest active scout to GCS, then blend
        with Fiedler-based connectivity demand.

        Scout-attrition aware: if active scouts are critically low AND a
        survey backlog remains, aggressively reclaims relays as scouts.
        This is the structural fix for the solo-survivor task hoarding problem —
        load_penalty can only rebalance between multiple competing agents;
        this ensures there ARE multiple agents competing in the first place.
        """
        if not available or not unsurveyed:
            return 0

        gcs_pos = self.world.gcs_pos
        effective_hop = self.gcs.comm_range * 0.85  # conservative: 85% of max range

        # Distance to the furthest unsurveyed PoI
        max_dist = 0.0
        for task in unsurveyed:
            d = float(np.linalg.norm(np.array([task.x, task.y]) - gcs_pos))
            if d > max_dist:
                max_dist = d

        # Hops needed to bridge that distance (minus 1 because scouts are endpoint)
        hops_needed = max(0, int(np.ceil(max_dist / effective_hop)) - 1)

        # Fiedler-based demand
        n = len(available)
        if current_fiedler < 0.3:
            fiedler_based = max(1, n // 3)
        elif current_fiedler < 0.8:
            fiedler_based = max(0, n // 4)
        else:
            fiedler_based = max(0, n // 5)

        # Take whichever asks for more, but keep at least half as scouts
        relay_count = max(hops_needed, fiedler_based)
        max_relays = len(available) // 2  # At least half must be scouts
        relay_count = min(relay_count, max_relays)

        # ── Scout Attrition Override ──────────────────────────────────────
        # Count how many active scouts exist across ALL UAVs (not just available).
        # A UAV is an "active scout" if it has an assigned task and is not FAILED/RTL.
        from src.core.uav import UAVState
        all_active_scouts = [u for u in self.uavs
                             if u.state == UAVState.SCOUT and
                             u.assigned_task_id is not None]
        n_active_scouts = len(all_active_scouts)
        n_unassigned = len(unsurveyed)

        # If we have fewer than 2 active scouts AND tasks remain:
        # Emergency reclaim — keep only the bare minimum relay hop count,
        # ignoring Fiedler-based padding. This trades marginal connectivity
        # gain for critical survey throughput.
        if n_active_scouts < 2 and n_unassigned > 0:
            # Keep only hops strictly needed for connectivity; release extras
            relay_count = min(relay_count, max(hops_needed, 1))

        return relay_count

    # ── Main Allocation ───────────────────────────────────────────────────


    def allocate(self, sim_time: float) -> Dict[int, Tuple[int, np.ndarray]]:
        """
        Main CA-CBBA allocation. Runs iterative bundle-build + consensus
        rounds, then assigns relays to maintain connectivity.

        Returns:
            {uav_id: (task_id, target_position)} for scout assignments
        """
        unsurveyed = self.world.get_unsurveyed_pois()
        available = [u for u in self.uavs if u.is_available()]

        if not unsurveyed or not available:
            return {}

        self.allocation_count += 1

        # Determine relay/scout split based on current Fiedler value
        try:
            adj = self.gcs.compute_connectivity_graph(self.uavs)
            current_fiedler = self.gcs._compute_fiedler_value(self.uavs, adj)
        except Exception:
            current_fiedler = 1.0

        num_available = len(available)

        # Distance-driven relay budget: how many hops do we NEED?
        num_relays = self._compute_relay_budget(available, unsurveyed, current_fiedler)
        num_scouts = max(1, num_available - num_relays)

        # Prioritize active scouts — NEVER demote a scouting UAV to relay.
        # This prevents relay-budget fluctuations from canceling in-progress surveys.
        active_scouts = [u for u in available if u.assigned_task_id is not None
                         and not getattr(self.world.get_poi_by_id(u.assigned_task_id) or object(), 'surveyed', True)]
        idle_uavs = [u for u in available if u not in active_scouts]

        # STRUCTURAL LOAD BALANCING: Sort idle UAVs by tasks completed (ascending)
        # before selecting who gets to be a scout. This prevents lower-ID UAVs
        # from being permanently selected as scouts while higher-ID UAVs are
        # permanently relegated to relays.
        idle_uavs.sort(key=lambda u: len(u.tasks_completed))
        
        # print(f"DEBUG {sim_time}: active_scouts={[u.id for u in active_scouts]}, idle_uavs={[u.id for u in idle_uavs]}")

        num_additional = max(0, num_scouts - len(active_scouts))
        scouts = active_scouts + idle_uavs[:num_additional]
        relays = idle_uavs[num_additional:]

        # ── Iterative CBBA: Bundle Build + Consensus ──
        final_assignments: Dict[int, Tuple[int, float]] = {}

        # Reset CBBA state for all agents to clear stale bids from previous rounds
        for u in available:
            u.winning_bids.clear()
            u.winning_agents.clear()
            
            # Re-seed active tasks: If a scout is actively flying/surveying a task,
            # it starts this round already bidding on it. Since it is close to the task,
            # its utility is high, preventing other scouts from stealing it.
            if u.assigned_task_id is not None:
                poi = self.world.get_poi_by_id(u.assigned_task_id)
                if poi and not poi.surveyed:
                    util = self.utility(u, poi)
                    u.winning_bids[u.assigned_task_id] = util
                    u.winning_agents[u.assigned_task_id] = u.id

        for iteration in range(self.max_consensus_iters):
            # Phase 1: Bundle build
            bids = self._bundle_build(scouts, unsurveyed)

            # Phase 2: Consensus resolution (simulate message exchange)
            resolved = self._consensus_resolve(scouts, bids)

            # Check convergence: assignments didn't change
            if resolved == final_assignments:
                break

            final_assignments = resolved

        # ── GCS-side deconfliction ──
        # If gossip left two scouts claiming the same task (network partition),
        # keep only the highest bidder. Losers get the next-best unclaimed task.
        task_to_best: Dict[int, Tuple[int, float]] = {}  # task_id -> (agent_id, bid)
        for agent_id, (task_id, bid) in final_assignments.items():
            if task_id not in task_to_best or bid > task_to_best[task_id][1] or \
               (bid == task_to_best[task_id][1] and agent_id < task_to_best[task_id][0]):
                task_to_best[task_id] = (agent_id, bid)

        # Build set of winners and claimed tasks
        winners = {agent_id for agent_id, _ in task_to_best.values()}
        claimed_task_ids = set(task_to_best.keys())

        deconflicted: Dict[int, Tuple[int, float]] = {}
        for task_id, (agent_id, bid) in task_to_best.items():
            deconflicted[agent_id] = (task_id, bid)

        # Reassign losers to next-best unclaimed tasks
        for agent_id in list(final_assignments.keys()):
            if agent_id not in winners:
                agent = next((a for a in scouts if a.id == agent_id), None)
                if agent is None:
                    continue
                best_task, best_util = None, -float('inf')
                for task in unsurveyed:
                    if task.id in claimed_task_ids:
                        continue
                    u = self.utility(agent, task)
                    if u > best_util:
                        best_util = u
                        best_task = task
                if best_task is not None:
                    deconflicted[agent_id] = (best_task.id, best_util)
                    claimed_task_ids.add(best_task.id)

        final_assignments = deconflicted

        # Convert to output format: {uav_id: (task_id, target_pos)}
        scout_assignments: Dict[int, Tuple[int, np.ndarray]] = {}
        for agent_id, (task_id, _) in final_assignments.items():
            task = self.world.get_poi_by_id(task_id)
            if task:
                scout_assignments[agent_id] = (task_id, np.array([task.x, task.y]))

        # ── Relay Placement ──
        if relays and scout_assignments:
            scout_positions = [pos for _, pos in scout_assignments.values()]
            relay_positions = compute_optimal_relay_positions(
                self.world.gcs_pos, scout_positions, len(relays),
                self.gcs.comm_range * 0.9  # 90% of range = 630m per hop
            )

            for i, relay_uav in enumerate(relays):
                if i < len(relay_positions):
                    relay_uav.assign_relay(relay_positions[i], sim_time)

        return scout_assignments

