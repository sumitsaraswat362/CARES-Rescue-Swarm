"""Shared CLI/web simulation runtime. Policies see only local state and delivered packets."""
import hashlib
import json
import os
from pathlib import Path
import random
import math
import numpy as np
import yaml
from src.core.mission import MissionManager
from src.core.uav import UAVState, UAVRole
from .planner import Planner
from .agent import Agent, Task
from .transport import Transport, Packet
from .evaluation import Evaluator


class Runtime:
    def __init__(self,scenario='scenarios/earthquake_basic.yaml',config='config/swarm_config.yaml',seed=42,mode='cares'):
        random.seed(seed);np.random.seed(seed)
        self.mission=MissionManager(scenario,config)
        m=self.mission
        if mode not in ('cares','direct','fixed','reactive','fifo','no_buffer'):
            raise ValueError('Unknown policy mode')
        if not math.isfinite(m.world.duration_s) or m.world.duration_s <= 0 or not math.isfinite(m.dt) or m.dt <= 0:
            raise ValueError('Duration and timestep must be positive and finite')
        if len({p.id for p in m.world.pois + m.world.hidden_pois}) != len(m.world.pois + m.world.hidden_pois):
            raise ValueError('PoI identifiers must be unique')
        for failure in m.world.failures:
            if failure.event_type not in ('motor_failure','comms_failure','battery_critical') or not 0 <= failure.data.get('uav_index',-1) < len(m.uavs):
                raise ValueError('Failure must specify a supported type and valid uav_index')
        with open(config) as f:cfg=yaml.safe_load(f)
        self.config={**cfg.get('resilience',{}),**m.world._raw_cfg.get('resilience',{}),'mode':mode}
        self.config.setdefault('range_m',cfg.get('uav_defaults',{}).get('comms',{}).get('max_range',700))
        self.seed,self.mode=seed,mode
        self.raw_frames=[]
        self.evaluator=Evaluator(cfg.get('uav_defaults',{}).get('safety',{}).get('min_separation',5),
                                 cfg.get('uav_defaults',{}).get('max_altitude',120))
        self.transport=Transport(m.world,m.uavs,self.config,seed,mode)
        self.planner=Planner(m.world)
        tasks=[Task(p.id,p.x,p.y,p.priority,p.deadline_s) for p in m.world.pois]
        self.environment_spec=m.world._raw_cfg.get('environment_model', {'version':'legacy-v1'})
        self.coverage=None
        if self.environment_spec['version']=='analytic-v2':
            from .environment import TerrainModel, CameraModel, CoverageGrid
            m.world.terrain=TerrainModel(self.environment_spec.get('terrain'))
            m.world.terrain_ceiling_m=self.evaluator.max_altitude-10
            self.camera=CameraModel(**self.environment_spec.get('camera',{}))
            self.coverage=CoverageGrid(m.world.width,m.world.height,self.environment_spec.get('coverage_cell_m',10))
            for u in m.uavs:
                u.terrain=m.world.terrain;u.camera=self.camera
                u.dynamics_spec=self.environment_spec.get('dynamics',{})
                from .environment import extra_power_w
                dyn=u.dynamics_spec
                # Conservative v2 return budget includes payload, worst-direction
                # wind at max speed, and continuous maximum climb cost. This is
                # an assumption, not a fitted battery prediction.
                u.battery.planning_power_w=u.battery.cruise_power_w+extra_power_w(
                    u.max_speed+float(np.linalg.norm(m.world.wind_vector)),5,
                    dyn.get('mass_kg',2.5),dyn.get('payload_kg',0),dyn.get('efficiency',.7),dyn.get('drag_coefficient',.01))
                u.altitude += m.world.terrain.height(*u.pos)
        elif self.environment_spec['version']!='legacy-v1':
            raise ValueError('Unknown environment model version')
        self.tasks={t.id:t for t in tasks}
        self.agents={u.id:Agent(u,m.world.launch_pos,tasks,self.planner,self.transport.send,self.config,self.evaluator.record) for u in m.uavs}
        for i,a in self.agents.items():
            a.fleet_size=len(m.uavs)
            self.transport.register(i,a.receive)
        self.transport.register(-1,self.gcs_receive)
        self.last_gcs=-1e9;self.snapshots=[];self.last_snapshot=-1e9
        self.gcs_received=set()
        self.received_routes=[]
        self.chargers={}
        self._isolation_ticks: dict = {}  # deadlock timeout counter per UAV id
        self.provenance={'seed':seed,'mode':mode,'scenario':scenario,
                         'scenario_sha256':hashlib.sha256(Path(scenario).read_bytes()).hexdigest(),
                         'config_sha256':hashlib.sha256(Path(config).read_bytes()).hexdigest(),
                         'source_sha256':self.source_hash(),'schema':'cares-evidence/v2'}
        # Mission-defined initial relay stations are shared preflight configuration, not live remote state.
        slots=m.world._raw_cfg.get('relay_stations',[])
        if not slots and tasks:
            far=max(tasks,key=lambda t:np.linalg.norm(np.array([t.x,t.y])-m.gcs.pos))
            v=np.array([far.x,far.y])-m.gcs.pos
            # Use the configured radio range, retaining at least half the fleet
            # for survey work. The former two-relay cap produced 867 m gaps
            # with a 700 m radio in the hard fixture before any fault occurred.
            spacing=.75*self.config['range_m']
            count=min(len(m.uavs)//2,max(0,math.ceil(np.linalg.norm(v)/spacing)-1))
            slots=[{'uav_id':i,'x':float(m.gcs.pos[0]+v[0]*(i+1)/(count+1)),
                    'y':float(m.gcs.pos[1]+v[1]*(i+1)/(count+1))} for i in range(count)]
        # Clamp each relay slot so no consecutive hop exceeds the radio range.
        # YAML-specified slots (e.g. earthquake_hard) can be farther apart than
        # range_m if they were authored before the range was configured.
        radio_range = float(self.config.get('range_m', 1e9))
        anchors = [m.gcs.pos.copy()]
        clamped_slots = []
        for slot in slots:
            target = np.array([slot['x'], slot['y']], dtype=float)
            anchor = anchors[-1]
            gap = np.linalg.norm(target - anchor)
            if gap > radio_range:
                direction = (target - anchor) / gap
                target = anchor + direction * (radio_range * 0.9)  # 10% margin
            anchors.append(target)
            clamped_slots.append({**slot, 'x': float(target[0]), 'y': float(target[1])})
        slots = clamped_slots
        for slot in slots:
            u=m.uavs[slot['uav_id']];target=np.array([slot['x'],slot['y']]);path=self.planner.plan(u.pos,target)
            if path:
                u.assign_relay(target,0);u.waypoints=[np.array(p) for p in path[1:]];u.waypoint_index=0
        for spec in m.world._raw_cfg.get('initial_uavs',[]):
            u=m.uavs[spec['id']];u.pos=np.array(spec['position'],dtype=float)
            if 'battery_fraction' in spec:u.battery.current_wh=u.battery.capacity_wh*spec['battery_fraction']
        # API compatibility: every UI/export reads the same delivered-data report.
        m.get_final_report=self.report
        m.save_logs=self.save
        m.runtime=self

    @staticmethod
    def source_hash():
        h=hashlib.sha256()
        for p in sorted(Path('src').rglob('*.py')):h.update(str(p).encode());h.update(p.read_bytes())
        return h.hexdigest()

    def gcs_receive(self,p,now):
        if p.kind in ('observation','probe'):
            if p.kind=='observation' and p.payload['id'] not in self.gcs_received:
                self.gcs_received.add(p.payload['id'])
                self.evaluator.record({**p.payload,'event':'received','time':now,'route':list(p.hops)})
                self.received_routes.append(list(p.hops))
            route=tuple(reversed(p.hops))
            self.transport.send(Packet(-1,p.source,'ack',{'id':p.payload['id']},now,128,9,now+10,route,(-1,)))

    def safety_filter(self,a,proposed,dt):
        u=a.uav
        # Commands use onboard neighbor estimates. Evaluation uses separate true trajectories.
        for uid,(pos,uncertainty) in u.neighbor_tracker.get_all_estimates().items():
            n=a.neighbors.get(uid)
            if n is None:continue
            alt=n.get('altitude',u.altitude)
            if abs(alt-u.altitude)>u.min_separation:continue
            start=u.pos-np.asarray(pos);end=proposed-np.asarray(pos);v=end-start
            t=float(np.clip(-np.dot(start,v)/max(float(np.dot(v,v)),1e-9),0,1))
            if np.linalg.norm(start+t*v)<u.min_separation+min(20.,1.5*uncertainty):
                self.evaluator.record({'event':'safety_hold','time':self.mission.sim_time,'uav':u.id})
                return u.pos.copy()
        if not self.planner.clear(u.pos,proposed):return u.pos.copy()
        w=self.mission.world
        if hasattr(w,'terrain') and not w.terrain.clear([*u.pos,u.altitude],[*proposed,u.altitude],1):
            return u.pos.copy()
        if not(0<=proposed[0]<=w.width and 0<=proposed[1]<=w.height):return u.pos.copy()
        return proposed

    def step(self, backend=None):
        m=self.mission
        if not m.running or m.paused:return self.report()
        m.sim_time=round(m.sim_time+m.dt,9);now=m.sim_time
        # Exogenous simulation events are kept outside every agent.
        for evt in m.world.check_events(now):
            if evt.event_type=='new_poi':
                m.world.add_poi(evt.data)
                p=m.world.pois[-1];self.tasks[p.id]=Task(p.id,p.x,p.y,p.priority,evt.data.get('deadline_s',1e9))
        for fail in m.world.check_failures(now):
            idx=fail.data.get('uav_index',0)
            if 0<=idx<len(m.uavs):
                u=m.uavs[idx]
                if fail.event_type=='comms_failure':u.radio_failed=True
                else:u.inject_failure(fail.event_type,now)
                self.evaluator.record({'event':'injected_failure','time':now,'uav':idx,'kind':fail.event_type,'scheduled_time':fail.time_s,
                                       'state_after':u.state.value,'radio_failed':getattr(u,'radio_failed',False),'drain_multiplier':u.battery.drain_multiplier})
        self.transport.step(m.dt,now)
        if now-self.last_gcs>=.5:
            self.last_gcs=now
            payload={'route':[-1],'route_at':now,'tasks':[vars(t) for t in self.tasks.values()],'completed':[]}
            self.transport.send(Packet(-1,-2,'beacon',payload,now,max(128,len(json.dumps(payload).encode())),9,now+1))
        # ── Charger contention scheduling ────────────────────────────────────
        # Priority: lowest battery fraction wins the slot. If a UAV is denied
        # the slot at its current charger it is redirected (while still airborne)
        # to the least-loaded alternative station rather than hovering idle.
        slots = int(self.config.get('charger_slots', 1))
        # Build a map: charger_key -> list of UAVs competing for that pad
        pad_queues: dict = {}
        for u in m.uavs:
            u._charging_allowed = True  # default
            if u.state == UAVState.RECHARGE:
                key = tuple(np.round(u.pos, 1))
                pad_queues.setdefault(key, []).append(u)
        # For each pad, rank competitors by battery level ascending (most critical first).
        # Grant the slot to the `slots` most critical UAVs; redirect the rest.
        for key, competitors in pad_queues.items():
            ranked = sorted(competitors, key=lambda u: u.battery.level)
            for rank, u in enumerate(ranked):
                if rank < slots:
                    u._charging_allowed = True
                else:
                    # This UAV is bumped — redirect it to the least loaded other pad.
                    u._charging_allowed = False
                    stations = m.world.recharge_stations
                    if len(stations) > 1:
                        current_pos = np.array(list(key), dtype=float)
                        # Count how many UAVs are already heading to / sitting at each pad
                        load: dict = {}
                        for other_u in m.uavs:
                            if other_u.id != u.id and other_u.state == UAVState.RECHARGE:
                                other_key = tuple(np.round(other_u.pos, 1))
                                load[other_key] = load.get(other_key, 0) + 1
                        # Pick the station (other than current) with fewest occupants
                        best_alt = None
                        best_load = 9999
                        for rs in stations:
                            rk = tuple(np.round(rs.pos, 1))
                            if rk == key:
                                continue
                            if load.get(rk, 0) < best_load:
                                best_load = load.get(rk, 0)
                                best_alt = rs.pos
                        if best_alt is not None:
                            u.send_to_recharge(best_alt, now)
                            self.evaluator.record({
                                'event': 'charger_redirect',
                                'time': now,
                                'uav': u.id,
                                'from': list(current_pos),
                                'to': list(best_alt),
                                'reason': 'contention',
                                'battery_level': float(u.battery.level),
                            })
        # ─────────────────────────────────────────────────────────────────────
        raw=[]
        for u in m.uavs:
            a=self.agents[u.id]
            for p in getattr(m.world,'hidden_pois',[]):
                if np.linalg.norm(u.pos-np.array([p.x,p.y]))<=150 and u.state!=UAVState.FAILED:
                    task=Task(p.id,p.x,p.y,p.priority,p.deadline_s)
                    if task.id not in a.tasks:
                        a.tasks[task.id]=task
                        self.evaluator.record({'event':'local_discovery','time':now,'uav':u.id,'task':task.id})
            a.tick(now)
            survey_task=u.assigned_task_id if u.state==UAVState.SCOUT else None
            u.motion_filter=lambda proposed,dt,a=a:self.safety_filter(a,proposed,dt)
            altitude_before=u.altitude
            if backend is None:
                u.update(m.dt,now,m.world.wind_vector)
            else:
                backend.advance(u,m.dt,now)
            if self.coverage is not None and u.state!=UAVState.FAILED:
                from .environment import extra_power_w
                dyn=u.dynamics_spec
                if u.state!=UAVState.RECHARGE:
                    power=extra_power_w(float(np.linalg.norm(u.vel-m.world.wind_vector)),
                                        (u.altitude-altitude_before)/m.dt,dyn.get('mass_kg',2.5),
                                        dyn.get('payload_kg',0),dyn.get('efficiency',.7),dyn.get('drag_coefficient',.01))
                    u.battery.consume(power,m.dt)
                if np.linalg.norm(u.vel)<self.camera.max_speed_mps:
                    self.coverage.observe([*u.pos,u.altitude],self.camera,m.world.terrain)
            if backend is None:u.update_gps_measurement()
            else:u.estimator.update_gps(u.pos)
            raw.append({'id':u.id,'position':[float(u.pos[0]),float(u.pos[1]),float(u.altitude)],
                        'velocity':u.vel.tolist(),'state':u.state.value,'survey_task':survey_task,
                        'battery_wh':u.battery.current_wh,'radio_failed':getattr(u,'radio_failed',False),
                        'drain_multiplier':u.battery.drain_multiplier,
                        'policy':{'role':u.role.value,'mode':a.mode,'route':list(a.route),
                                  'route_age_s':now-a.route_at if a.route else None,
                                  'last_received_heartbeat_at':max((n['seen'] for n in a.neighbors.values()),default=None),
                                  'neighbor_heartbeat_at':{str(i):n['seen'] for i,n in a.neighbors.items()},
                                  'last_gcs_ack_at':a.delivery_proof_at if a.delivery_proof_at>-1e8 else None,
                                  'request':a.request.copy() if a.request else None,
                                  'pending_bytes':sum(d['size'] for d in a.pending.values()),
                                  'custody_bytes':sum(d['size'] for d in a.custody.values()),
                                  'return_margin_wh':a.return_margin}})
        # ── Post-dynamics separation shield ─────────────────────────────────
        # ORCA plans velocity avoidance before integration, but the physics
        # integrator can overshoot due to wind / acceleration.  This 20-iteration
        # loop resolves any residual pair violations *after* all UAVs have moved,
        # guaranteeing the separation invariant holds in the logged state.
        min_sep = float(self.config.get('min_separation_m',
                        m.world._raw_cfg.get('uav_defaults', {}).get('safety', {}).get('min_separation', 20.0)))
        active_uavs = [u for u in m.uavs if u.state not in (UAVState.FAILED, UAVState.RECHARGE)]
        for _iteration in range(20):
            resolved = False
            for i, a in enumerate(active_uavs):
                for b in active_uavs[i + 1:]:
                    delta = np.array([a.pos[0] - b.pos[0], a.pos[1] - b.pos[1],
                                      (a.altitude - b.altitude)])
                    dist = float(np.linalg.norm(delta))
                    if dist < min_sep and dist > 1e-9:
                        direction = delta / dist
                        # Push each drone half the gap + a small margin
                        correction = direction * ((min_sep - dist) / 2.0 + 0.1)
                        a.pos[0] += correction[0]; a.pos[1] += correction[1]
                        b.pos[0] -= correction[0]; b.pos[1] -= correction[1]
                        a.altitude += correction[2]; b.altitude -= correction[2]
                        # Zero horizontal velocity to prevent oscillation on next tick
                        a.vel[:] = 0.0; b.vel[:] = 0.0
                        resolved = True
            if not resolved:
                break
        # Clamp positions to geofence after shield
        for u in active_uavs:
            u.pos[0] = float(np.clip(u.pos[0], 0.0, m.world.width))
            u.pos[1] = float(np.clip(u.pos[1], 0.0, m.world.height))
        # ── Deadlock timeout for isolated UAVs ──────────────────────────────
        # If an agent has been in a disconnected/recovery state without
        # making route progress for > 25 ticks, fall back to direct GCS return.
        # This prevents permanent oscillation around an unreachable relay midpoint.
        for u in m.uavs:
            if u.state in (UAVState.FAILED, UAVState.RECHARGE, UAVState.RTL):
                self._isolation_ticks[u.id] = 0
                continue
            a = self.agents[u.id]
            # Consider "isolated" if agent has no GCS route
            if not a.route:
                self._isolation_ticks[u.id] = self._isolation_ticks.get(u.id, 0) + 1
                if self._isolation_ticks[u.id] > 25:
                    self._isolation_ticks[u.id] = 0
                    # Force return home — guaranteed reconnect
                    a.return_home(now)
                    self.evaluator.record({
                        'event': 'deadlock_timeout_rtl',
                        'time': now,
                        'uav': int(u.id),
                        'reason': 'isolated_no_route_for_25_ticks',
                    })
            else:
                self._isolation_ticks[u.id] = 0
        # ────────────────────────────────────────────────────────────────────
        # Sample link truth at the same post-motion positions as the evaluator.
        self.transport.refresh(now)
        # Update raw snapshot AFTER the shield corrected positions, so
        # raw_trace.jsonl is consistent with what evaluator.sample() sees.
        # We modify the existing 'raw' dicts to preserve 'survey_task', which
        # was captured BEFORE u.update() potentially cleared it upon completion.
        for r, u in zip(raw, m.uavs):
            r['position'] = [float(u.pos[0]), float(u.pos[1]), float(u.altitude)]
            r['velocity'] = u.vel.tolist()
        self.raw_frames.append({'time': now, 'dt': m.dt, 'uavs': raw,
                                'edges': [[a, b] for (a, b), q in self.transport.edges.items() if q > 0]})
        self.evaluator.sample(m.uavs,m.world,self.transport,m.dt)
        for p in m.world.pois:p.surveyed=any(p.id in a.acquired for a in self.agents.values())
        m.running=now<m.world.duration_s
        report=self.report()
        m.last_mesh_stats=self.transport.summary()
        m.last_mbb_stats={k:v for k,v in report.items() if k.startswith('mbb_')}
        if now-self.last_snapshot>=1 or not m.running:
            self.last_snapshot=now
            snapshot={'time':now,'metrics':report,'uavs':[{'id':u.id,'pos':u.pos.tolist(),'altitude':u.altitude,
                'battery':u.battery.level,'state':u.state.value,'role':u.role.value,
                'route':list(self.agents[u.id].route),'mode':self.agents[u.id].mode,
                'return_margin_wh':self.agents[u.id].return_margin,'pending':len(self.agents[u.id].pending)} for u in m.uavs]}
            self.snapshots.append(snapshot)
            m.metrics_history.append({'time':now,**report})
        return {'sim_time':now,'mission_completion':report['mission_completion_pct']/100,
                'priority_weighted_completion':report['priority_weighted_pct']/100,**report}

    def report(self):
        m=self.mission
        evaluation_tasks={**self.tasks,**{p.id:Task(p.id,p.x,p.y,p.priority,p.deadline_s) for p in getattr(m.world,'hidden_pois',[])}}
        r=self.evaluator.report(list(evaluation_tasks.values()),m.sim_time)
        r.update(self.transport.summary());r.update(self.provenance)
        r.update({'scenario':m.world.name,'total_uavs':len(m.uavs),'failed_uavs':sum(u.state==UAVState.FAILED for u in m.uavs),
                  'scheduled_failure_events':sum(f.time_s<=m.sim_time for f in m.world.failures),
                  'injected_failure_events':sum(e['event']=='injected_failure' for e in self.evaluator.events),
                  'radio_failed_uavs':sum(bool(getattr(u,'radio_failed',False)) for u in m.uavs),
                  'battery_fault_uavs':sum(u.battery.drain_multiplier>1 for u in m.uavs),
                  'pending_observations':sum(len(a.pending) for a in self.agents.values()),
                  'tasks_per_uav':{u.label:len(self.agents[u.id].acquired) for u in m.uavs},
                  'mbb_handoffs_initiated':sum(e['event']=='handoff_requested' for e in self.evaluator.events),
                  'mbb_handoffs_completed':sum(e['event']=='handoff_complete' for e in self.evaluator.events),
                  'contact_loss_detections':sum(e['event']=='contact_lost' for e in self.evaluator.events),
                  'replacement_dispatches':sum(e['event']=='replacement_dispatched' for e in self.evaluator.events)})
        if self.coverage is not None:
            r['mapped_area_estimate_m2']=self.coverage.area_m2
            r['mapped_cells']=len(self.coverage.cells)
        return r

    def save(self,output_dir=None):
        out=Path(output_dir or os.environ.get('CARES_LOG_DIR','logs/current'));out.mkdir(parents=True,exist_ok=True)
        (out/'final_report.json').write_text(json.dumps(self.report(),indent=2,allow_nan=False))
        (out/'metrics_history.json').write_text(json.dumps(self.mission.metrics_history,allow_nan=False))
        (out/'trajectory_log.json').write_text(json.dumps(self.mission.trajectory_log,allow_nan=False,indent=2))
        (out/'mission_log.json').write_text(json.dumps(self.mission.mission_log,allow_nan=False,indent=2))
        with (out/'events.jsonl').open('w') as f:
            for e in sorted(self.evaluator.events+self.transport.events,key=lambda e:e['time']):f.write(json.dumps(e,allow_nan=False)+'\n')
        with (out/'replay.jsonl').open('w') as f:
            for s in self.snapshots:f.write(json.dumps(s,allow_nan=False)+'\n')
        with (out/'raw_trace.jsonl').open('w') as f:
            for frame in self.raw_frames:f.write(json.dumps(frame,allow_nan=False)+'\n')
        manifest={**self.provenance,'resolved_radio_config':self.config,'duration_s':self.mission.world.duration_s,
                  'world':{'width':self.mission.world.width,'height':self.mission.world.height},
                  'environment_model':self.environment_spec,
                  'handoff_protocol':'downstream-probe/v1',
                  'obstacles':[{'x':o.x,'y':o.y,'radius':o.radius} for o in self.mission.world.obstacles],
                  'minimum_separation_m':self.evaluator.minimum,'maximum_altitude_m':self.evaluator.max_altitude,
                  'tasks':[vars(t) for t in {**self.tasks,**{p.id:Task(p.id,p.x,p.y,p.priority,p.deadline_s) for p in self.mission.world.hidden_pois}}.values()],
                  'survey_requirements':{str(u.id):{'radius_m':u.survey_radius,'dwell_s':u.survey_time_s} for u in self.mission.uavs},
                  'failures':[{'time':f.time_s,'uav':f.data['uav_index'],'kind':f.event_type} for f in self.mission.world.failures]}
        (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
        return out
