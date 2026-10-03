"""Per-UAV policy. No fleet registry, physical adjacency, or remote state access."""
from dataclasses import dataclass
import math
import json
import numpy as np
from src.core.uav import UAVState, UAVRole
from .transport import Packet
from .routing import choose_route, valid_route


@dataclass(frozen=True)
class Task:
    id: int
    x: float
    y: float
    priority: int
    deadline: float = 1e9


class Agent:
    def __init__(self, uav, home, tasks, planner, send, config, record):
        self.uav, self.home, self.planner = uav, np.array(home), planner
        self.send, self.config, self.record = send, config, record
        self.tasks = {t.id:t for t in tasks}
        self.neighbors = {}
        self.claims = {}
        self.completed = set()
        self.acquired = set()
        self.pending = {}
        self.custody = {}
        self.custody_peers = {}
        self.route = ()
        self.route_at = -1e9
        self.last_beacon = -1e9
        self.last_bid = -1e9
        self.timeout = float(config.get('heartbeat_timeout_s', 3))
        self.lease_s = float(config.get('task_lease_s', 8))
        self.return_margin = 0.
        self.request = None
        self.replacing = None
        self.ready_at = None
        self.ready_probe_id = None
        self.ready_route = ()
        self.downstream_proofs = {}
        self.last_service_probe = -1e9
        self.fleet_size=int(config.get('fleet_size',8))
        self.reposition_slot=-1
        self.position_lease_until=-1e9
        self.retiring = False
        self.lost_contacts = set()
        self.mode = 'bootstrap'
        self.sequence = 0
        self.boot_epoch=int(config.get('boot_epoch',0))
        self.delivery_proof_at = -1e9
        self.recovery_attempts = 0
        self.offline_since = None
        self.probes = {}
        self.serves = None
        self.scout_recovery_target = None
        self.relay_recovery_since = None
        self.relay_recovery_route_since = None

    def broadcast(self, kind, payload, now, priority=5):
        self.send(Packet(self.uav.id,-2,kind,payload,now,max(128,len(json.dumps(payload).encode())),priority,now+2))

    def receive(self, p, now):
        data = p.payload
        if p.kind=='beacon':
            # Discard reordered beacons instead of rolling a neighbor's route back.
            old = self.neighbors.get(p.source)
            epoch=data.get('boot_epoch',0)
            if type(epoch) is not int or epoch<0:return
            if old is not None and (epoch<old.get('boot_epoch',0) or
                    (epoch==old.get('boot_epoch',0) and p.created<old.get('beacon_created',-math.inf))):return
            self.neighbors[p.source] = {**data, 'seen': now, 'beacon_created': p.created}
            self.lost_contacts.discard(p.source)
            if p.source >= 0 and 'pos' in data:
                self.uav.receive_telemetry(p.source,np.array(data['pos']),np.array(data.get('vel',[0,0])),now)
            self.route, self.route_at = choose_route(self.neighbors, self.uav.id, now, self.timeout)
            for raw in data.get('tasks',[]):
                t=Task(**raw);self.tasks[t.id]=t
            self.completed.update(data.get('completed',[]))
            for task_id, claim in data.get('claims',[]):
                if claim['until'] <= now: continue
                old=self.claims.get(task_id)
                if old is None or old['until']<=now or (claim['owner']==old['owner'] and claim['until']>old['until']) or (claim['bid'],-claim['owner'])>(old['bid'],-old['owner']):
                    self.claims[task_id]=claim.copy()
        elif p.kind == 'custody':
            self.receive_custody(p, now)
        elif p.kind == 'custody_ack':
            entry = self.custody_peers.get(data.get('id'))
            if entry and entry['peer'] == p.source and data['id'] in self.pending:
                entry['confirmed'] = True
                self.record({'event': 'custody_confirmed', 'time': now, 'uav': self.uav.id,
                             'peer': p.source, 'id': data['id']})
        elif p.kind=='ack':
            oid=data['id']
            if p.source != -1 or (oid not in self.pending and oid not in self.probes and oid not in self.custody):
                return
            self.pending.pop(oid,None)
            self.custody.pop(oid,None);self.custody_peers.pop(oid,None)
            self.delivery_proof_at=now
            self.record({'event':'ack','time':now,'uav':self.uav.id,'id':oid,'route':list(reversed(p.hops))})
            probe=self.probes.pop(oid,None)
            if probe is not None and probe.get('kind')=='downstream' and 0<=now-probe['sent']<self.timeout:
                proof={'old':probe['old'],'token':probe['token'],'candidate':probe['candidate'],
                       'proof_at':now,'route':list(probe['route']),'probe_id':oid}
                self.record({'event':'downstream_service_confirmed','time':now,'uav':self.uav.id,**proof})
                self.broadcast('downstream_ready',proof,now,9)
            elif self.replacing is not None and probe is not None and 0 <= now-probe['sent'] < self.timeout and self.replacing not in probe['route']:
                self.ready_at=now;self.ready_probe_id=oid;self.ready_route=probe['route']
        elif p.kind=='ready' and self.request and data.get('old')==self.uav.id:
            if (valid_route(data.get('route'),p.source,self.uav.id,data.get('proof_at',-1e9),now,self.timeout)
                    and data.get('token',self.request['created'])==self.request['created']):
                self.request.update(candidate=p.source,candidate_route=data['route'],
                                    candidate_proof_at=data['proof_at'],candidate_probe_id=data.get('probe_id'))
                self.finish_handoff(now)
        elif p.kind=='downstream_ready' and self.request:
            if (data.get('old')==self.uav.id and data.get('token')==self.request['created']
                    and data.get('candidate')==self.request.get('candidate')
                    and p.source in self.request.get('downstream',[])
                    and valid_route(data.get('route'),p.source,self.uav.id,data.get('proof_at',-1e9),now,self.timeout)
                    and len(data['route'])>2 and data['route'][1]==self.request['candidate']):
                self.downstream_proofs[p.source]=data.copy()
                self.finish_handoff(now)

    def finish_handoff(self,now):
        req=self.request
        if not req or 'candidate' not in req or now-req['created']<self.config.get('overlap_s',2):return
        if not 0<=now-req['candidate_proof_at']<self.timeout:return
        req['downstream']=sorted(set(req.get('downstream',[])) | {i for i,n in self.neighbors.items() if i>=0 and now-n['seen']<=self.timeout and len(n.get('route',[]))>1 and n['route'][1]==self.uav.id})
        required=set(req.get('downstream',[]))-{req['candidate']}
        if not all(uid in self.downstream_proofs and 0<=now-self.downstream_proofs[uid]['proof_at']<self.timeout
                   and self.downstream_proofs[uid]['candidate']==req['candidate'] for uid in required):return
        self.record({'event':'handoff_complete','time':now,'old':self.uav.id,'new':req['candidate'],
                     'downstream':sorted(required),'replacement_probe_id':req.get('candidate_probe_id'),
                     'downstream_proofs':{str(uid):self.downstream_proofs[uid] for uid in required}})
        self.retiring=True;self.request=None;self.downstream_proofs.clear()
        self.return_home(now)

    def check_downstream_service(self,now):
        if now-self.last_service_probe<1:return
        for old,n in sorted(self.neighbors.items()):
            req=n.get('request')
            if not req or self.uav.id not in req.get('downstream',[]) or now-n['seen']>self.timeout:continue
            candidate=req.get('candidate');route=req.get('candidate_route')
            if candidate is None or candidate==self.uav.id:continue
            if not valid_route(route,candidate,self.uav.id,req.get('candidate_proof_at',-1e9),now,self.timeout):continue
            if old in route:continue
            path=(self.uav.id,)+tuple(route)
            oid=f'service:{self.uav.id}:{old}:{req["created"]}:{now:.1f}'
            self.probes={key:value for key,value in self.probes.items() if now-value['sent']<self.timeout}
            if self.send(Packet(self.uav.id,-1,'probe',{'id':oid},now,128,9,now+self.timeout,path,(self.uav.id,))):
                self.probes[oid]={'kind':'downstream','sent':now,'route':path,'old':old,
                                  'candidate':candidate,'token':req['created']}
                self.last_service_probe=now
                self.record({'event':'downstream_service_probe','time':now,'uav':self.uav.id,'id':oid,'route':list(path)})
            break

    def receive_custody(self, p, now):
        d = p.payload
        required = ('id', 'task', 'origin', 'level', 'priority', 'acquired_at', 'deadline', 'size')
        if (not self.config.get('custody_enabled', True) or self.config.get('mode') == 'no_buffer'
                or any(k not in d for k in required) or d['origin'] != p.source
                or d['level'] != 'full' or not d['acquired_at'] <= now < d['deadline']
                or not isinstance(d['size'], int) or d['size'] <= 0 or p.size != d['size']):
            return
        oid = d['id']
        if oid not in self.custody:
            used = sum(x['size'] for x in self.custody.values())
            limit=self.config.get('custody_buffer_bytes',65536)
            victims=sorted((x for x in self.custody.values() if x['priority']<d['priority']),
                           key=lambda x:(x['priority'],x['acquired_at'],x['id']))
            if d['size']>limit or used+d['size']-sum(x['size'] for x in victims)>limit:
                self.record({'event': 'custody_rejected', 'time': now, 'uav': self.uav.id, 'id': oid})
                return
            for victim in victims:
                if used+d['size']<=limit:break
                self.custody.pop(victim['id']);used-=victim['size']
                self.record({'event':'custody_evicted','time':now,'uav':self.uav.id,'id':victim['id'],
                             'reason':'higher_priority_observation'})
            self.custody[oid] = {k: d[k] for k in required}
            self.custody[oid]['last_sent'] = -1e9
            self.record({'event': 'custody_stored', 'time': now, 'uav': self.uav.id,
                         'source': p.source, 'id': oid, 'size': d['size']})
        elif any(self.custody[oid][key]!=d[key] for key in required):
            self.record({'event':'custody_conflict','time':now,'uav':self.uav.id,'id':oid});return
        # Acknowledgement is enqueued only after the local storage insertion.
        self.send(Packet(self.uav.id, p.source, 'custody_ack', {'id': oid}, now,
                         128, 8, min(d['deadline'], now + self.timeout),
                         (self.uav.id, p.source), (self.uav.id,)))

    def maintain_custody(self, now):
        if self.config.get('custody_enabled', True) and self.config.get('mode') != 'no_buffer':
            peers = sorted(i for i,n in self.neighbors.items() if i >= 0 and i != self.uav.id
                           and 0 <= now-n['seen'] <= self.timeout
                           and n.get('state') != 'failed')
            for oid,d in self.pending.items():
                if d['level'] != 'full' or now >= d['deadline']:
                    continue
                if oid not in self.custody_peers and peers:
                    # One backup destination for this observation's lifetime. Copies
                    # never replicate, bounding replication even during partitions.
                    self.custody_peers[oid] = {'peer': peers[0], 'confirmed': False, 'sent': -1e9}
                entry = self.custody_peers.get(oid)
                if entry and not entry['confirmed'] and now-entry['sent'] >= self.config.get('retry_s', 2):
                    peer = entry['peer']
                    if self.send(Packet(self.uav.id, peer, 'custody', d, now, d['size'], d['priority'],
                                        d['deadline'], (self.uav.id, peer), (self.uav.id,))):
                        entry['sent'] = now
        for oid,d in list(self.custody.items()):
            if now >= d['deadline']:
                self.custody.pop(oid)
                self.record({'event': 'custody_expired', 'time': now, 'uav': self.uav.id, 'id': oid})
            elif self.route and now-d['last_sent'] >= self.config.get('retry_s', 2):
                if self.send(Packet(self.uav.id, -1, 'observation', d, now, d['size'], d['priority'],
                                    d['deadline'], self.route, (self.uav.id,))):
                    d['last_sent'] = now
        self.custody_peers = {oid:e for oid,e in self.custody_peers.items() if oid in self.pending}

    def reposition_relay(self,now,live):
        """Improve task admission using only the preflight map and received peers.

        One preflight ID gets each 60 s planning slot. Endpoint constraints retain
        observed upstream/downstream links with margin; raw tests, not this local
        estimate, determine whether connectivity and safety actually held.
        """
        u=self.uav
        if (self.config.get('mode') in ('fixed','direct') or now<120 or not self.route
                or self.request or self.replacing is not None or self.retiring
                or u.state!=UAVState.RELAY or u.relay_station_pos is None
                or np.linalg.norm(u.pos-u.relay_station_pos)>2 or now<self.position_lease_until):return
        slot=int((now-120)//60)
        if slot%max(1,self.fleet_size)!=u.id or slot==self.reposition_slot:return
        self.reposition_slot=slot
        upstream=self.route[1]
        if upstream!=-1 and upstream not in live:return
        anchor=self.home if upstream==-1 else np.array(live[upstream]['pos'])
        dependents=[np.array(n['pos']) for i,n in live.items()
                    if len(n.get('route',[]))>1 and n['route'][1]==u.id]
        constraints=[anchor]+dependents
        radio=self.config.get('range_m',700);admission=self.config.get('admission_range_m',.8*radio)
        # A target with a live lease already has service in progress. Moving
        # its relay can remove redundancy without admitting any waiting work.
        tasks=[t for t in self.tasks.values() if t.id not in self.completed
               and self.claims.get(t.id,{}).get('until',-1)<=now]
        def score(point):
            return sum(t.priority for t in tasks if np.linalg.norm(point-np.array([t.x,t.y]))<=admission)
        current=score(u.pos);choices=[]
        for task in tasks:
            delta=np.array([task.x,task.y])-u.pos;distance=float(np.linalg.norm(delta))
            if distance<=admission:continue
            for fraction in (.25,.5,.75,1.):
                target=u.pos+delta/max(distance,1e-9)*min(distance,.4*radio)*fraction
                gain=score(target)-current
                if gain<=0 or any(np.linalg.norm(target-point)>.95*radio for point in constraints):continue
                path=self.path(target)
                # A straight, obstacle-clear station move and direct preflight
                # segments to each observed dependent avoid detour-based LOS claims.
                if len(path)!=2 or any(len(self.planner.plan(target,point))!=2 for point in constraints):continue
                travel=self.distance(path)/u.cruise_speed
                if self.safe_hold()<travel+60:continue
                choices.append((-gain,travel,task.id,target,path))
        if not choices:return
        _,travel,task_id,target,path=min(choices,key=lambda row:row[:3])
        old=u.pos.copy();u.assign_relay(target,now)
        u.waypoints=[np.array(p) for p in path[1:]];u.waypoint_index=0
        self.position_lease_until=now+60
        self.record({'event':'relay_reposition','time':now,'uav':u.id,'for_task':task_id,
                     'from':old.tolist(),'station':target.tolist(),'lease_until':self.position_lease_until,
                     'observed_link_constraints':[point.tolist() for point in constraints]})

    def path(self, target):
        return self.planner.plan(self.uav.pos,np.array(target))

    def distance(self, path):
        if not path:return math.inf
        return sum(float(np.linalg.norm(np.asarray(b)-a)) for a,b in zip(path,path[1:]))

    def return_home(self,now):
        self.scout_recovery_target=None
        path=self.path(self.home)
        if not path:
            if self.mode!='infeasible':self.record({'event':'return_infeasible','time':now,'uav':self.uav.id})
            self.mode='infeasible';self.uav.state=UAVState.IDLE;self.uav.target_pos=None
            return
        self.uav.send_to_recharge(self.home,now)
        self.uav.waypoints=[np.array(p) for p in path[1:]];self.uav.waypoint_index=0

    def safe_hold(self):
        u=self.uav
        distance=self.distance(self.path(self.home))
        energy=u.battery.energy_for_distance(distance,u.cruise_speed)
        if not math.isfinite(energy):
            self.return_margin=-u.battery.capacity_wh
            return -1.0
        reserve=u.battery.capacity_wh*float(self.config.get('reserve_fraction',.15))
        self.return_margin=u.battery.current_wh-energy-reserve
        return self.return_margin*3600/max(1,u.battery.hover_power_w*u.battery.drain_multiplier)

    def tick(self,now):
        u=self.uav
        if u.state==UAVState.FAILED:return
        # Loss of contact is suspicion, not privileged knowledge of hardware failure.
        for uid,n in self.neighbors.items():
            if now-n['seen']>self.timeout and uid not in self.lost_contacts:
                self.lost_contacts.add(uid)
                self.record({'event':'contact_lost','time':now,'observer':u.id,'peer':uid})
        if now-self.route_at>self.timeout:
            self.route,self.route_at=choose_route(self.neighbors,u.id,now,self.timeout)
        if self.route:
            self.offline_since=None
            if self.scout_recovery_target is not None and self.mode=='recover':
                u.state=UAVState.IDLE;u.target_pos=None;u.waypoints=[]
                self.scout_recovery_target=None
            elif self.mode=='recover' and u.state==UAVState.RTL and self.relay_recovery_since is None:
                u.state=UAVState.IDLE;u.target_pos=None
        elif self.offline_since is None:self.offline_since=now
        self.claims={t:c for t,c in self.claims.items() if c['until']>now and t not in self.completed}
        if u.state not in (UAVState.RECHARGE,UAVState.FAILED):
            hold=self.safe_hold()
            if hold<=float(self.config.get('return_margin_s',10)):
                if u.state!=UAVState.RTL:
                    if self.request:
                        self.record({'event':'handoff_timeout','time':now,'uav':u.id,'reason':'return reserve reached before service proofs','downstream':self.request.get('downstream',[])})
                        self.request=None;self.downstream_proofs.clear()
                    self.record({'event':'reserve_return','time':now,'uav':u.id,'margin_wh':self.return_margin})
                    self.return_home(now)
                self.mode='return'
        else:hold=math.inf
        if self.retiring and u.state==UAVState.IDLE:
            self.retiring=False;u.role=UAVRole.UNASSIGNED
        if now-self.last_beacon>=.5:
            self.last_beacon=now
            payload={'boot_epoch':self.boot_epoch,'pos':u.estimator.estimated_pos.tolist(),'vel':u.estimator.estimated_vel.tolist(),'altitude':u.altitude,'battery':u.battery.level,'role':u.role.value,
                     'state':u.state.value,'route':list(self.route),'route_at':self.route_at,
                     'claims':list(self.claims.items()),'completed':sorted(self.completed),
                     'tasks':[vars(t) for t in self.tasks.values()], 'request':self.request,
                     'replacing':self.replacing,'serves':self.serves,'retiring':self.retiring,
                     'heard_relays':[i for i,n in self.neighbors.items() if now-n['seen']<=self.timeout and n.get('role')=='relay']}
            self.broadcast('beacon',payload,now)
        self.check_downstream_service(now)
        self.finish_handoff(now)
        # Locally acquired data persists until an actual ACK, expiry, or storage eviction.
        for task_id in u.tasks_completed:
            if task_id in self.acquired:continue
            self.acquired.add(task_id);self.completed.add(task_id)
            t=self.tasks[task_id]
            for kind,size in [('alert',256),('preview',1024),('full',int(self.config.get('observation_bytes',4096)))]:
                self.sequence+=1;oid=f'{u.id}:{task_id}:{kind}:{self.sequence}'
                if self.boot_epoch:oid+=f':epoch{self.boot_epoch}'
                d={'id':oid,'task':task_id,'origin':u.id,'level':kind,'priority':t.priority,
                   'acquired_at':now,'deadline':min(t.deadline,now+self.config.get('observation_ttl_s',120)), 'size':size}
                self.record({'event':'acquired','time':now,**d})
                if sum(x['size'] for x in self.pending.values())+size>self.config.get('observation_buffer_bytes',262144):
                    self.record({'event':'observation_evicted','time':now,**d});continue
                self.pending[oid]={**d,'last_sent':-1e9}
        for oid,d in list(self.pending.items()):
            if now>d['deadline']:
                self.pending.pop(oid);self.record({'event':'observation_expired','time':now,**d});continue
            if self.route and now-d['last_sent']>=self.config.get('retry_s',2):
                priority=d['priority']+(2 if d['level']=='alert' else 0)
                if self.send(Packet(u.id,-1,'observation',d,now,d['size'],priority,d['deadline'],self.route,(u.id,))):
                    d['last_sent']=now
            elif not self.route and self.config.get('mode')=='no_buffer':
                self.pending.pop(oid);self.record({'event':'observation_dropped','time':now,**d})
        self.maintain_custody(now)
        # Relays used to return from tick before the scout recovery branch, so a
        # broken upstream chain left them isolated indefinitely. Retreat along a
        # preflight-map path, then hold a new station after sustained route contact.
        # A hardware radio fault is not read by this policy: recovery uses timeout.
        if self.relay_recovery_since is not None:
            if self.mode=='return' or u.state==UAVState.RECHARGE:
                self.relay_recovery_since=None;self.relay_recovery_route_since=None
                self.replacing=None;self.serves=None;self.request=None
            elif self.route:
                if self.relay_recovery_route_since is None:self.relay_recovery_route_since=now
                if now-self.relay_recovery_route_since>=self.config.get('relay_recovery_stable_s',2):
                    u.assign_relay(u.pos.copy(),now);u.waypoints=[];u.waypoint_index=0
                    self.record({'event':'relay_recovery_complete','time':now,'uav':u.id,
                                 'duration_s':now-self.relay_recovery_since,'route':list(self.route),
                                 'station':u.pos.tolist()})
                    self.relay_recovery_since=None;self.relay_recovery_route_since=None
                    self.replacing=None;self.serves=None;self.request=None;self.probes.clear()
                    self.mode='relay'
            else:self.relay_recovery_route_since=None
        if (u.role==UAVRole.RELAY and not self.route and self.offline_since is not None
                and now-self.offline_since>self.timeout*2
                and u.state not in (UAVState.RTL,UAVState.RECHARGE) and not self.retiring
                and self.relay_recovery_since is None and self.config.get('mode')!='fixed'):
            # Deterministic preflight holding offsets keep radio-isolated relays
            # out of the charger's vertical approach column. These are not extra
            # charging stations and do not add charging capacity.
            recovery_target=None;path=[]
            spacing=3*max(5.,u.min_separation)
            for direction in ([1.,0.],[0.,1.],[-1.,0.],[0.,-1.]):
                target=self.home+np.array(direction)*spacing*(u.id+1)
                path=self.path(target)
                if path:
                    recovery_target=target;break
            if path:
                # Communication recovery is horizontal relay repositioning, not
                # a request to descend onto an occupied charging pad.
                u.assign_relay(recovery_target,now)
                u.waypoints=[np.array(p) for p in path[1:]];u.waypoint_index=0
                self.relay_recovery_since=now;self.relay_recovery_route_since=None
                self.mode='relay_recover'
                self.record({'event':'relay_recovery_started','time':now,'uav':u.id,
                             'station':u.pos.tolist()})
        if self.relay_recovery_since is not None:return
        if u.state in (UAVState.RTL,UAVState.RECHARGE) or self.retiring:return
        live={i:n for i,n in self.neighbors.items() if i>=0 and now-n['seen']<=self.timeout}
        # A relay advertises its safe departure deadline; candidates decide using received information.
        if u.role==UAVRole.RELAY and self.config.get('mode') not in ('fixed','reactive'):
            travel=max([float(np.linalg.norm(np.asarray(n['pos'])-u.pos))/max(u.cruise_speed,1)
                        for n in live.values()]+[0])
            if hold<travel+self.config.get('handoff_margin_s',30)+self.config.get('overlap_s',2):
                if self.request is None:
                    downstream=sorted(i for i,n in live.items() if len(n.get('route',[]))>1 and n['route'][1]==u.id)
                    self.request={'old':u.id,'pos':u.pos.tolist(),'created':now,'depart_by':now+hold,'downstream':downstream}
                    self.downstream_proofs.clear()
                    self.record({'event':'handoff_requested','time':now,**self.request})
        if self.replacing is not None:
            old=self.neighbors.get(self.replacing,{})
            # A contact timeout is only suspicion. Release a speculative replacement
            # if the original relay is heard again and did not ask to retire.
            if (now-old.get('seen',-1e9)<=self.timeout and old.get('state')=='relay'
                    and not old.get('request') and not getattr(self,'planned_replacement',False)):
                self.record({'event':'replacement_cancelled','time':now,'uav':u.id,'old':self.replacing})
                self.replacing=None;self.serves=None;self.ready_at=None;self.probes.clear()
                u.role=UAVRole.UNASSIGNED;u.state=UAVState.IDLE;u.target_pos=None;u.waypoints=[]
            if now-old.get('seen',-1e9)<=self.timeout and old.get('state') in ('return_to_launch','recharge'):
                self.record({'event':'replacement_active','time':now,'uav':u.id,'old':self.replacing})
                self.replacing=None;self.ready_at=None;self.probes.clear()
        if self.replacing is not None:
            self.mode='replacement'
            if self.route and self.replacing not in self.route and np.linalg.norm(u.pos-u.relay_station_pos)<5:
                if self.ready_at is not None and now-self.ready_at<self.timeout:
                    self.broadcast('ready',{'old':self.replacing,'proof_at':self.ready_at,'route':list(self.ready_route),
                                            'probe_id':self.ready_probe_id,'token':old.get('request',{}).get('created') if old.get('request') else None},now)
                elif now-self.last_bid>=1:
                    self.last_bid=now
                    oid=f'probe:{u.id}:{now:.1f}'
                    self.probes={k:v for k,v in self.probes.items() if now-v['sent']<self.timeout}
                    if self.send(Packet(u.id,-1,'probe',{'id':oid},now,128,9,now+3,self.route,(u.id,))):
                        self.probes[oid]={'sent':now,'route':self.route}
            return
        covered={n.get('serves') for n in live.values() if n.get('role')=='relay'}
        heard={i for n in live.values() for i in n.get('heard_relays',[])}
        requests=[n['request'] for n in live.values() if n.get('request') and n['request']['old'] not in covered]
        if self.config.get('mode')!='fixed':
            requests += [{'old':i,'pos':n['pos'],'created':now,'depart_by':now+30,'suspected':True}
                         for i,n in self.neighbors.items() if i in self.lost_contacts and n.get('role')=='relay'
                         and i not in covered and i not in heard and np.linalg.norm(n.get('vel',[0,0]))<1
                         and now-n['seen']>2*self.timeout
                         and np.linalg.norm(u.pos-np.array(n['pos']))<.8*self.config.get('range_m',700)]
        if u.state!=UAVState.IDLE:
            requests=[r for r in requests if not r.get('suspected')]
        if u.role!=UAVRole.RELAY and requests and hold>30:
            req=min(requests,key=lambda r:r['depart_by'])
            old=req['old'];pos=np.array(req['pos'])
            candidates=[(float(np.linalg.norm(u.pos-pos)),u.id)]
            candidates += [(float(np.linalg.norm(np.array(n['pos'])-pos)),i) for i,n in live.items()
                           if n.get('role')!='relay' and n.get('battery',0)>.25 and n.get('state') not in ('return_to_launch','recharge')]
            if min(candidates)[1]==u.id and not any(n.get('replacing')==old for n in live.values()):
                target=pos+np.array([0.,15.])
                path=self.path(target)
                if path and self.distance(path)/u.cruise_speed+20<hold:
                    u.assign_relay(target,now);u.waypoints=[np.array(p) for p in path[1:]];u.waypoint_index=0
                    self.replacing=old;self.recovery_attempts+=1
                    self.serves=old;self.planned_replacement=bool(self.neighbors.get(old,{}).get('request'))
                    self.record({'event':'replacement_dispatched','time':now,'uav':u.id,'old':old})
                    return
        if u.role==UAVRole.RELAY:
            self.reposition_relay(now,live)
            return
        # Backpressure and route timeout are local observations; return toward known connectivity.
        if not self.route:
            self.mode='recover'
            if now-self.offline_since>self.timeout*2 and self.scout_recovery_target is None:
                # Loss of contact is not a request to land or recharge. Keep the
                # scout in its flight layer, outside the charging approach column.
                spacing=3*max(5.,u.min_separation)
                for direction in ([1.,0.],[0.,1.],[-1.,0.],[0.,-1.]):
                    target=self.home+np.array(direction)*spacing*(u.id+1)
                    path=self.path(target)
                    if not path:continue
                    u.assign_relay(target,now);u.role=UAVRole.SCOUT
                    u.assigned_task_id=None;u.target_pos=None;u.true_target_pos=None
                    u.survey_timer=0.;u.detection_confidence=0.
                    u.waypoints=[np.array(p) for p in path[1:]];u.waypoint_index=0
                    self.scout_recovery_target=target
                    self.record({'event':'scout_recovery_started','time':now,'uav':u.id,'station':target.tolist()})
                    break
            return
        self.mode='survey'
        if sum(d['size'] for d in self.pending.values())>self.config.get('observation_buffer_bytes',262144)*.75:
            self.mode='drain';return
        if now-self.last_bid<1:return
        self.last_bid=now
        if u.assigned_task_id is not None:
            current=self.claims.get(u.assigned_task_id)
            if u.assigned_task_id in self.completed or (current and current['owner']!=u.id):
                u.assigned_task_id=None;u.target_pos=None;u.waypoints=[];u.state=UAVState.IDLE
            else:
                # Lease renewal occurs only through subsequent beacons.
                if current:current['until']=now+self.lease_s
                return
        choices=[]
        for t in self.tasks.values():
            if t.id in self.completed:continue
            claim=self.claims.get(t.id)
            if claim and claim['owner']!=u.id:continue
            target=np.array([t.x,t.y]);path=self.path(target)
            distance=self.distance(path)
            if not math.isfinite(distance):continue
            back=self.planner.plan(target,self.home)
            total=distance+self.distance(back)
            energy=u.battery.energy_for_distance(total,u.cruise_speed)+u.battery.hover_power_w*u.survey_time_s/3600
            if energy+u.battery.capacity_wh*self.config.get('reserve_fraction',.15)>u.battery.current_wh:continue
            # Conservative admission: target must be near a recently heard routed anchor.
            anchors=[self.home]+[np.array(n['pos']) for n in live.values() if n.get('route')]
            # The radio model has full geometric quality inside 80% of range.
            # Keep explicit scenario overrides; otherwise use that same margin.
            admission=self.config.get('admission_range_m',.8*self.config.get('range_m',700))
            if min(np.linalg.norm(target-a) for a in anchors)>admission:continue
            delivery=self.config.get('observation_bytes',4096)*max(1,len(self.route)-1)/self.config.get('bytes_per_second',32768)
            if now+distance/u.cruise_speed+u.survey_time_s+delivery>t.deadline:continue
            choices.append((t.priority/(1+distance),-t.id,t,path))
        if choices:
            bid,_,t,path=max(choices,key=lambda x:(x[0],x[1]))
            self.claims[t.id]={'owner':u.id,'bid':bid,'until':now+self.lease_s}
            u.assign_scout_task(t.id,np.array([t.x,t.y]),now,waypoint_path=path,true_target=np.array([t.x,t.y]))
            self.record({'event':'task_claim','time':now,'uav':u.id,'task':t.id,'lease_until':now+self.lease_s})
