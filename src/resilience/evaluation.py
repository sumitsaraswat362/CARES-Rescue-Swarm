"""Ground-truth evaluator: never feeds policy decisions."""
import math
import numpy as np


class Evaluator:
    def __init__(self, minimum=5, max_altitude=120):
        self.minimum,self.max_altitude=minimum,max_altitude
        self.previous={};self.min_separation=math.inf
        self.separation_frames=0;self.geofence_frames=0;self.battery_frames=0
        self.time=0.;self.connected={};self.active={};self.all_time=0.;self.any_time=0.
        self.events=[];self.delivered={};self.acquired={}

    def record(self,event):
        self.events.append(event)
        if event['event']=='acquired':self.acquired.setdefault(event['id'],event)
        if event['event']=='received':self.delivered.setdefault(event['id'],event)

    def sample(self,uavs,world,transport,dt):
        pos={u.id:np.array([*u.pos,u.altitude]) for u in uavs if u.state.value!='failed'}
        ids=sorted(pos);violation=False
        for i,a in enumerate(ids):
            for b in ids[i+1:]:
                start=self.previous.get(a,pos[a])-self.previous.get(b,pos[b])
                end=pos[a]-pos[b];v=end-start
                t=float(np.clip(-np.dot(start,v)/max(float(np.dot(v,v)),1e-12),0,1))
                d=float(np.linalg.norm(start+t*v));self.min_separation=min(self.min_separation,d)
                violation |= d<self.minimum
        self.separation_frames+=int(violation)
        self.geofence_frames+=sum(not(0<=p[0]<=world.width and 0<=p[1]<=world.height and 0<=p[2]<=self.max_altitude) for p in pos.values())
        self.battery_frames+=sum(u.battery.current_wh<=0 for u in uavs if u.state.value!='failed')
        connected=[]
        for uid in ids:
            self.active[uid]=self.active.get(uid,0)+dt
            ok=transport.reachable(uid);connected.append(ok)
            self.connected[uid]=self.connected.get(uid,0)+dt*ok
        self.time+=dt;self.all_time+=dt*bool(connected)*all(connected);self.any_time+=dt*any(connected)
        self.previous=pos

    def report(self,tasks,now):
        acquired={e['task'] for e in self.acquired.values() if e['level']=='full'}
        delivered={e['task'] for e in self.delivered.values() if e['level']=='full'}
        ontime={e['task'] for e in self.delivered.values() if e['level']=='full' and e['time']<=e['deadline']}
        latencies=[e['time']-e['acquired_at'] for e in self.delivered.values() if e['level']=='full']
        weights={t.id:t.priority for t in tasks};den=max(1,sum(weights.values()))
        return {'duration_s':round(now,3),'total_pois':len(tasks),'surveyed_pois':len(acquired),
                'acquired_completion_pct':100*len(acquired)/max(1,len(tasks)),
                'mission_completion_pct':100*len(delivered)/max(1,len(tasks)),
                'delivered_completion_pct':100*len(delivered)/max(1,len(tasks)),
                'priority_weighted_pct':100*sum(weights.get(t,0) for t in delivered)/den,
                'on_time_priority_pct':100*sum(weights.get(t,0) for t in ontime)/den,
                'observation_delivery_pct':100*len(self.delivered)/max(1,len(self.acquired)),
                'latency_p50_s':float(np.percentile(latencies,50)) if latencies else None,
                'latency_p95_s':float(np.percentile(latencies,95)) if latencies else None,
                'minimum_separation_m':self.min_separation if math.isfinite(self.min_separation) else None,
                'separation_violation_frames':self.separation_frames,'geofence_violation_samples':self.geofence_frames,
                'depleted_battery_samples':self.battery_frames,
                'communication_downtime_s':max(0.,self.time-self.all_time),
                'all_uav_connectivity_pct':100*self.all_time/max(self.time,1e-9),
                'any_uav_connectivity_pct':100*self.any_time/max(self.time,1e-9),
                'per_uav_connectivity_pct':{str(k):100*v/max(self.active[k],1e-9) for k,v in self.connected.items()},
                'contacts_measured':False,
                'expired_observations':sum(e['event']=='observation_expired' for e in self.events),
                'evicted_observations':sum(e['event']=='observation_evicted' for e in self.events)}
