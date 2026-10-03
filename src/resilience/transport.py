"""Bounded, delayed, per-hop transport. Only this simulator reads true RF geometry."""
from dataclasses import dataclass, field
from collections import defaultdict
import copy
import hashlib
import heapq
import math
import numpy as np


@dataclass
class Packet:
    source: int
    destination: int
    kind: str
    payload: dict
    created: float
    size: int = 256
    priority: int = 1
    expires: float = 30.0
    path: tuple = ()
    hops: tuple = ()
    sequence: int = 0


class Transport:
    def __init__(self, world, vehicles, config, seed=42, mode='cares'):
        self.world, self.vehicles = world, vehicles
        self.config, self.seed, self.mode = config, seed, mode
        self.rate = float(config.get('bytes_per_second', 32768))
        self.limit = int(config.get('queue_bytes', 262144))
        self.delay = float(config.get('hop_delay_s', .05))
        self.loss = float(config.get('packet_loss', .05))
        self.range = float(config.get('range_m', 700))
        if not all(math.isfinite(x) for x in (self.rate, self.delay, self.loss, self.range)) or self.rate <= 0 or self.range <= 0 or self.limit <= 0 or self.delay < 0 or not 0 <= self.loss <= 1:
            raise ValueError('Radio requires positive bandwidth/range/queue, nonnegative delay and loss in [0,1]')
        self.queues = defaultdict(list)
        self.credit = defaultdict(float)
        self.inflight = []
        self.receivers = {}
        self.events = []
        self.sequence = 0
        self.now = 0.0
        self.stats = defaultdict(int)
        self.edges = {}
        self.blocked = set()
        self.outage_until = 0.0

    def uniform(self, *parts):
        key = ':'.join(map(str, (self.seed,) + parts)).encode()
        return int.from_bytes(hashlib.sha256(key).digest()[:8], 'big') / 2**64

    def register(self, uid, callback):
        self.receivers[uid] = callback

    def positions(self):
        return {-1: np.asarray(self.world.gcs_pos), **{u.id: u.pos for u in self.vehicles
                if u.state.value != 'failed' and not getattr(u, 'radio_failed', False)}}

    def refresh(self, now):
        self.now = now
        positions = self.positions()
        self.edges = {}
        for a, pa in positions.items():
            for b, pb in positions.items():
                if a == b: continue
                d = float(np.linalg.norm(pa-pb))
                blocked = False
                v = pb-pa
                for obs in self.world.obstacles:
                    t = float(np.clip(np.dot(obs.center-pa, v)/max(float(np.dot(v,v)), 1e-9),0,1))
                    if np.linalg.norm(pa+t*v-obs.center) < obs.radius: blocked = True
                q = max(0., min(1., (self.range-d)/max(.2*self.range, 1.)))
                if hasattr(self.world,'terrain'):
                    heights={-1:self.world.terrain.height(*self.world.gcs_pos)+2,
                             **{u.id:u.altitude for u in self.vehicles}}
                    if not self.world.terrain.clear([*pa,heights[a]],[*pb,heights[b]]):blocked=True
                if blocked: q *= float(self.config.get('nlos_factor', 0.0))
                if a in self.blocked or b in self.blocked or now < self.outage_until: q = 0.
                # A fixed time-indexed RF field preserves exogenous disturbances across policies.
                epoch = int(now / max(.1, float(self.config.get('burst_duration_s', 2))))
                if self.uniform('burst',min(a,b),max(a,b),epoch) < float(self.config.get('burst_probability',0)):
                    q = 0.
                if self.mode == 'direct' and a != -1 and b != -1: q = 0.
                self.edges[a,b] = q

    def send(self, packet, holder=None):
        p = copy.deepcopy(packet)
        self.sequence += 1
        p.sequence = self.sequence
        holder = p.source if holder is None else holder
        if p.size <= 0 or p.size > self.limit: return False
        used = sum(x.size for x in self.queues[holder])
        if used+p.size > self.limit:
            self.stats['queue_rejected'] += 1
            return False
        self.queues[holder].append(p)
        self.stats['enqueued'] += 1
        return True

    def reachable(self, origin):
        seen, todo = {origin}, [origin]
        while todo:
            a=todo.pop()
            for (x,b),q in self.edges.items():
                if x==a and q>0 and b not in seen: seen.add(b);todo.append(b)
        return -1 in seen

    def step(self, dt, now):
        self.refresh(now)
        # Revalidate at arrival: a receiver that died during flight cannot accept traffic.
        while self.inflight and self.inflight[0][0] <= now + 1e-9:
            _, _, receiver, packet = heapq.heappop(self.inflight)
            if packet.expires <= now:
                self.stats['expired_inflight_packets'] += 1; continue
            if receiver not in self.positions():
                self.stats['lost_receiver'] += 1; continue
            packet.hops = packet.hops + (receiver,)
            self.events.append({'event':'packet_arrived','time':now,'receiver':receiver,'source':packet.source,
                                'kind':packet.kind,'observation_id':packet.payload.get('id'),'hops':list(packet.hops)})
            if packet.destination == -2 or receiver == packet.destination:
                self.stats['received'] += 1
                self.receivers[receiver](packet, now)
            else:
                self.send(packet, receiver)
        for holder in sorted(list(self.queues)):
            queue = self.queues[holder]
            if holder not in self.positions():
                self.stats['lost_vehicle_packets'] += len(queue); queue.clear(); continue
            self.credit[holder] = min(self.limit, self.credit[holder]+self.rate*dt)
            expired = [p for p in queue if p.expires <= now]
            self.stats['expired_packets'] += len(expired)
            queue[:] = [p for p in queue if p.expires > now]
            # Aging prevents lower-priority packets starving. Control shares the finite radio budget.
            ordered = sorted(queue, key=lambda p: (p.created,p.sequence) if self.mode=='fifo' else
                             (-(p.priority+min(10,(now-p.created)/5)), p.created,p.sequence))
            for p in ordered:
                if p.size > self.credit[holder]: continue
                if p.destination == -2:
                    targets=[b for (a,b),q in self.edges.items() if a==holder and q>0]
                else:
                    route = p.path
                    if holder not in route: queue.remove(p);continue
                    idx=route.index(holder)
                    targets=list(route[idx+1:idx+2])
                if not targets or not any(self.edges.get((holder,b),0)>0 for b in targets):
                    if self.mode=='no_buffer': queue.remove(p);self.stats['no_route_drops']+=1
                    continue
                queue.remove(p)
                self.credit[holder]-=p.size
                for b in targets:
                    self.stats['hop_attempts'] += 1
                    q=self.edges.get((holder,b),0)*(1-self.loss)
                    # Independent link/time field rather than a shared RNG advanced by policy code.
                    if self.uniform('packet',holder,b,round(now,6),p.kind,p.source,p.payload.get('id','')) >= q:
                        self.stats['hop_drops'] += 1; continue
                    self.sequence+=1
                    heapq.heappush(self.inflight,(now+self.delay+p.size/self.rate,self.sequence,b,copy.deepcopy(p)))
                    self.events.append({'time':now,'event':'hop','source':holder,'target':b,'kind':p.kind,
                                        'observation_id':p.payload.get('id')})

    def summary(self):
        return {**dict(self.stats), 'queue_bytes':sum(p.size for q in self.queues.values() for p in q),
                'inflight_packets':len(self.inflight), 'hop_pdr_pct':100*(1-self.stats['hop_drops']/self.stats['hop_attempts']) if self.stats['hop_attempts'] else None}
