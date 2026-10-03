"""Recompute evidence from raw traces without importing the simulator or evaluator.

This checks exported consistency and sampled safety, not physical flight validity.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.environment_audit import camera_valid, ground, mapped_cells, segment_clear


def audit(directory):
    directory = Path(directory)
    report = json.loads((directory / 'final_report.json').read_text())
    manifest = json.loads((directory / 'run_manifest.json').read_text())
    events = [json.loads(s) for s in (directory / 'events.jsonl').read_text().splitlines()]
    frames = [json.loads(s) for s in (directory / 'raw_trace.jsonl').read_text().splitlines()]
    errors = []
    model=manifest.get('environment_model', {'version':'legacy-v1'})
    analytic=model['version']=='analytic-v2'
    covered=set();terrain_samples=obstacle_samples=0
    for key in ('seed','mode','source_sha256','scenario_sha256','config_sha256'):
        if report.get(key) != manifest.get(key):
            errors.append(f'Provenance mismatch: {key}')
    if not frames:
        raise ValueError('No raw frames: cannot validate a run')
    tasks = {t['id']: t for t in manifest['tasks']}
    elapsed = connected_time = 0.
    previous = {}
    dwell = {}
    proofs = {}
    separation_frames = geofence_samples = depleted_samples = 0
    minimum = math.inf
    previous_time = 0.
    for frame in frames:
        dt, now = frame['dt'], frame['time']
        if dt <= 0 or not math.isclose(now-previous_time, dt, abs_tol=1e-6):
            errors.append(f'Non-contiguous raw time at {now}')
        previous_time = now
        active = {u['id']: u for u in frame['uavs'] if u['state'] != 'failed'}
        elapsed += dt
        adjacency = {}
        for a, b in frame['edges']:
            adjacency.setdefault(a, []).append(b)
        connected = []
        for uid in active:
            seen, todo = {uid}, [uid]
            while todo:
                for neighbor in adjacency.get(todo.pop(), []):
                    if neighbor not in seen:
                        seen.add(neighbor); todo.append(neighbor)
            connected.append(-1 in seen)
        if connected and all(connected):
            connected_time += dt
        violation = False
        ids = sorted(active)
        for i, aid in enumerate(ids):
            a = active[aid]
            p = a['position']
            if not all(math.isfinite(x) for x in p + a['velocity'] + [a['battery_wh']]):
                errors.append(f'Nonfinite raw state at {now} for {aid}')
            w = manifest['world']
            geofence_samples += not (0 <= p[0] <= w['width'] and 0 <= p[1] <= w['height'] and 0 <= p[2] <= manifest['maximum_altitude_m'])
            depleted_samples += a['battery_wh'] <= 0
            if analytic:
                terrain_samples += not segment_clear(model.get('terrain',{}),previous.get(aid,p),p)
                covered.update(mapped_cells(model,w,p,a['velocity']))
            for obstacle in manifest.get('obstacles',[]):
                old=previous.get(aid,p)
                vx,vy=p[0]-old[0],p[1]-old[1]
                t=min(1,max(0,((obstacle['x']-old[0])*vx+(obstacle['y']-old[1])*vy)/max(vx*vx+vy*vy,1e-12)))
                obstacle_samples += math.hypot(old[0]+t*vx-obstacle['x'],old[1]+t*vy-obstacle['y'])<obstacle['radius']
            for bid in ids[i+1:]:
                q = active[bid]['position']
                pa, pb = previous.get(aid, p), previous.get(bid, q)
                start = [x-y for x,y in zip(pa,pb)]
                delta = [x-y-s for x,y,s in zip(p,q,start)]
                vv = sum(x*x for x in delta)
                fraction = min(1., max(0., -sum(x*y for x,y in zip(start,delta))/vv)) if vv else 0.
                distance = math.sqrt(sum((x+fraction*y)**2 for x,y in zip(start,delta)))
                minimum = min(minimum, distance)
                violation |= distance < manifest['minimum_separation_m']
            task = tasks.get(a['survey_task'])
            key = (aid, a['survey_task'])
            req = manifest['survey_requirements'][str(aid)]
            near = task is not None and math.hypot(p[0]-task['x'],p[1]-task['y']) <= req['radius_m'] and 10 <= p[2] <= manifest['maximum_altitude_m'] and math.hypot(*a['velocity']) < 1.
            if analytic and near:
                near=camera_valid(model,p,a['velocity'],[task['x'],task['y']])
            for old in list(dwell):
                if old[0] == aid and old != key:
                    dwell.pop(old)
            dwell[key] = dwell.get(key, 0.) + dt if near else 0.
            if dwell[key] + 1e-8 >= req['dwell_s']:
                proofs.setdefault(key, now)
        separation_frames += violation
        previous = {uid:u['position'] for uid,u in active.items()}
    acquired = {e['id']:e for e in events if e['event']=='acquired'}
    received = {e['id']:e for e in events if e['event']=='received'}
    arrivals = {(e['observation_id'], e['time']) for e in events if e['event']=='packet_arrived' and e['kind']=='observation' and e['receiver']==-1}
    for oid, e in acquired.items():
        if e['level']=='full' and proofs.get((e['origin'],e['task']), math.inf) > e['time'] + 1e-6:
            errors.append(f'Acquisition lacks position/altitude/speed/dwell evidence: {oid}')
    for oid, e in received.items():
        source = acquired.get(oid)
        if source is None or any(source[k]!=e[k] for k in ['task','origin','level','size']):
            errors.append(f'Receipt lacks matching acquisition: {oid}')
        if (oid,e['time']) not in arrivals:
            errors.append(f'Receipt lacks GCS packet arrival: {oid}')
        if e['time'] >= e['deadline'] or e['time'] < e['acquired_at']:
            errors.append(f'Invalid receipt timing: {oid}')
    if manifest.get('handoff_protocol')=='downstream-probe/v1':
        ack_arrivals={(e['observation_id'],e['receiver'],e['time']) for e in events
                      if e['event']=='packet_arrived' and e['kind']=='ack' and e['source']==-1}
        timeout=manifest['resolved_radio_config'].get('heartbeat_timeout_s',3)
        for e in events:
            if e['event']!='handoff_complete':continue
            replacement=[r for r in events if r['event']=='ack' and r['uav']==e['new']
                         and r['id']==e.get('replacement_probe_id') and 0<=e['time']-r['time']<timeout
                         and e['old'] not in r.get('route',[])
                         and (r['id'],r['uav'],r['time']) in ack_arrivals]
            if not replacement:errors.append('Handoff lacks actual replacement GCS round trip')
            for uid in e.get('downstream',[]):
                proof=e.get('downstream_proofs',{}).get(str(uid),{})
                route=proof.get('route',[])
                if (not route or route[0]!=uid or route[-1]!=-1 or e['old'] in route
                        or len(route)<3 or route[1]!=e['new']
                        or not 0<=e['time']-proof.get('proof_at',-1e9)<timeout
                        or (proof.get('probe_id'),uid,proof.get('proof_at')) not in ack_arrivals):
                    errors.append(f'Handoff lacks actual downstream round trip: {uid}')
    custody_arrivals = {(e['observation_id'], e['receiver'], e['time']) for e in events
                        if e['event']=='packet_arrived' and e['kind']=='custody'}
    for e in events:
        if e['event'] != 'custody_stored':
            continue
        original = acquired.get(e['id'])
        if original is None or original['origin'] != e['source'] or original['size'] != e['size']:
            errors.append(f"Custody lacks matching original acquisition: {e['id']}")
        if (e['id'],e['uav'],e['time']) not in custody_arrivals:
            errors.append(f"Custody lacks actual packet arrival: {e['id']}")
    full_acquired = {e['task'] for e in acquired.values() if e['level']=='full'}
    full_received = {e['task'] for e in received.values() if e['level']=='full'}
    full_ontime = {e['task'] for e in received.values() if e['level']=='full' and e['time']<=e['deadline']}
    latencies = sorted(e['time']-e['acquired_at'] for e in received.values() if e['level']=='full')
    def percentile(fraction):
        if not latencies:return None
        index=(len(latencies)-1)*fraction
        lo,hi=math.floor(index),math.ceil(index)
        return latencies[lo]+(index-lo)*(latencies[hi]-latencies[lo])
    independently = {
        'surveyed_pois': len(full_acquired), 'total_pois': len(tasks),
        'acquired_completion_pct': 100*len(full_acquired)/max(1,len(tasks)),
        'delivered_completion_pct': 100*len(full_received)/max(1,len(tasks)),
        'mission_completion_pct': 100*len(full_received)/max(1,len(tasks)),
        'priority_weighted_pct': 100*sum(tasks[t]['priority'] for t in full_received)/max(1,sum(t['priority'] for t in tasks.values())),
        'on_time_priority_pct': 100*sum(tasks[t]['priority'] for t in full_ontime)/max(1,sum(t['priority'] for t in tasks.values())),
        'observation_delivery_pct': 100*len(received)/max(1,len(acquired)),
        'latency_p50_s': percentile(.5), 'latency_p95_s': percentile(.95),
        'communication_downtime_s': max(0.,elapsed-connected_time),
        'all_uav_connectivity_pct': 100*connected_time/elapsed,
        'separation_violation_frames': separation_frames,
        'geofence_violation_samples': geofence_samples, 'depleted_battery_samples': depleted_samples,
        'minimum_separation_m': minimum if math.isfinite(minimum) else None,
    }
    if analytic:
        size=model.get('coverage_cell_m',10);world=manifest['world']
        independently['mapped_cells']=len(covered)
        independently['mapped_area_estimate_m2']=sum(min(size,world['width']-x*size)*min(size,world['height']-y*size) for x,y in covered)
    for key, value in independently.items():
        actual = report.get(key)
        if (actual is None) != (value is None) or (value is not None and not math.isclose(actual, value, abs_tol=1e-6)):
            errors.append(f'Report mismatch {key}: claimed={actual}, raw={value}')
    due = [f for f in manifest['failures'] if f['time'] <= frames[-1]['time']]
    injected = [e for e in events if e['event']=='injected_failure']
    for f in due:
        matches = [e for e in injected if e.get('scheduled_time') == f['time'] and e['uav']==f['uav'] and e['kind']==f['kind']]
        if len(matches) != 1:
            errors.append(f'Failure count mismatch: {f}')
            continue
        e = matches[0]
        frame = next((s for s in frames if s['time'] >= e['time']), None)
        u = next((u for u in frame['uavs'] if u['id']==f['uav']), None) if frame else None
        if not u or (f['kind']=='motor_failure' and u['state']!='failed') or (f['kind']=='comms_failure' and not u['radio_failed']) or (f['kind']=='battery_critical' and u['drain_multiplier']!=20):
            errors.append(f'Failure effect absent in raw state: {f}')
    if len(injected) != len(due):
        errors.append('Unexpected failure injections')
    final_uavs=frames[-1]['uavs']
    failure_counts={'failed_uavs':sum(u['state']=='failed' for u in final_uavs),
                    'scheduled_failure_events':len(due),'injected_failure_events':len(injected),
                    'radio_failed_uavs':sum(bool(u['radio_failed']) for u in final_uavs),
                    'battery_fault_uavs':sum(u['drain_multiplier']>1 for u in final_uavs)}
    for key,value in failure_counts.items():
        if key in report:
            independently[key]=value
            if report[key]!=value:errors.append(f'Report mismatch {key}: claimed={report[key]}, raw={value}')
    if not math.isclose(frames[-1]['time'], manifest['duration_s'], abs_tol=max(f['dt'] for f in frames)+1e-6):
        errors.append('Run ended before configured duration')
    return {'evidence_consistent': not errors, 'errors': errors, 'recomputed': independently,
            'safety_passed': not (separation_frames or geofence_samples or depleted_samples or terrain_samples or obstacle_samples),
            'terrain_penetration_samples':terrain_samples,'obstacle_penetration_samples':obstacle_samples,
            'scheduled_failures_due': len(due), 'observed_failure_events': len(injected),
            'acquired_full_task_ids': sorted(full_acquired),'received_full_task_ids':sorted(full_received),
            'seed':manifest['seed'],'mode':manifest['mode'],
            'raw_trace_sha256':hashlib.sha256((directory/'raw_trace.jsonl').read_bytes()).hexdigest(),
            'source_sha256':manifest['source_sha256']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    try:
        result=audit(args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result={'evidence_consistent':False,'errors':[str(exc)],'safety_passed':False}
    print(json.dumps(result,indent=2,allow_nan=False))
    raise SystemExit(0 if result['evidence_consistent'] and result['safety_passed'] else 1)
