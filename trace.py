import numpy as np

class DummyTask:
    def __init__(self, id, x, y):
        self.id = id; self.x = x; self.y = y; self.surveyed = False

class DummyUAV:
    def __init__(self, id, x, y):
        self.id = id; self.pos = np.array([x, y]); self.assigned_task_id = None
        self.winning_bids = {}; self.winning_agents = {}
        
    def __repr__(self): return f"UAV({self.id})"

tasks = [DummyTask(10, 100, 0), DummyTask(11, 200, 0)]
scouts = [DummyUAV(1, 0, 0), DummyUAV(2, 0, 0)]

def utility(uav, task):
    return 1000.0 - np.linalg.norm(uav.pos - np.array([task.x, task.y]))

# Iteration 0
bids = {}
for a in scouts:
    best_task, best_util = None, -float('inf')
    for t in tasks:
        u = utility(a, t)
        cur_bid = a.winning_bids.get(t.id, -float('inf'))
        cur_winner = a.winning_agents.get(t.id, -1)
        if (u > cur_bid) or (u == cur_bid and a.id < cur_winner):
            if u > best_util: best_util, best_task = u, t
    if best_task:
        bids[a.id] = (best_task.id, best_util)
        a.winning_bids[best_task.id] = best_util
        a.winning_agents[best_task.id] = a.id

print("Iter 0 bids:", bids)

# Consensus (all connected)
for a in scouts:
    for b in scouts:
        for tid, bid in b.winning_bids.items():
            win = b.winning_agents[tid]
            my_bid = a.winning_bids.get(tid, -float('inf'))
            my_win = a.winning_agents.get(tid, -1)
            if (bid > my_bid) or (bid == my_bid and win < my_win):
                a.winning_bids[tid] = bid; a.winning_agents[tid] = win

print("Iter 0 post-consensus:", scouts[1].winning_agents)

# Iteration 1
bids = {}
for a in scouts:
    # IF NO CLAIMED TASKS (my_won_tasks logic)
    my_won = [tid for tid, wid in a.winning_agents.items() if wid == a.id]
    if my_won:
        bids[a.id] = (my_won[0], a.winning_bids[my_won[0]])
        continue
        
    best_task, best_util = None, -float('inf')
    for t in tasks:
        u = utility(a, t)
        cur_bid = a.winning_bids.get(t.id, -float('inf'))
        cur_winner = a.winning_agents.get(t.id, -1)
        if (u > cur_bid) or (u == cur_bid and a.id < cur_winner):
            if u > best_util: best_util, best_task = u, t
    if best_task:
        bids[a.id] = (best_task.id, best_util)
        a.winning_bids[best_task.id] = best_util
        a.winning_agents[best_task.id] = a.id

print("Iter 1 bids:", bids)

