"""Describe disconnections from recorded graph/state; never import the policy.

Operational connectivity excludes only explicitly failed aircraft/radios. It is
additional context, not a replacement for the original all-active-UAV metric.
"""
import argparse
import hashlib
import json
from pathlib import Path


def diagnose(directory):
    directory = Path(directory)
    trace = directory / 'raw_trace.jsonl'
    manifest=json.loads((directory/'run_manifest.json').read_text())
    first_fault=min((f['time'] for f in manifest.get('failures',[])),default=float('inf'))
    periods={name:{'population_s':0.,'connected_s':0.} for name in ('before_first_fault','after_first_fault')}
    elapsed = all_connected = operational_time = operational_connected = 0.0
    forced_radio_time = 0.0
    members = None
    transitions, intervals, open_intervals = [], [], {}
    totals = {}
    last = 0.0
    with trace.open() as stream:
        for line in stream:
            frame = json.loads(line)
            now, dt = frame['time'], frame['dt']
            if dt <= 0 or abs(now - last - dt) > 1e-6:
                raise ValueError('Raw trace must have contiguous positive time steps')
            start = last
            last = now
            elapsed += dt
            all_uavs = {u['id']: u for u in frame['uavs']}
            active = {i: u for i, u in all_uavs.items() if u['state'] != 'failed'}
            operational = {i: u for i, u in active.items() if not u['radio_failed']}
            adjacency = {}
            for a, b in frame['edges']:
                adjacency.setdefault(a, []).append(b)
            reachability = {};reachable_nodes={}
            for uid in active:
                seen, todo = {uid}, [uid]
                while todo:
                    for neighbor in adjacency.get(todo.pop(), []):
                        if neighbor not in seen:
                            seen.add(neighbor)
                            todo.append(neighbor)
                reachability[uid] = -1 in seen
                reachable_nodes[uid]=sorted(seen)
            all_connected += dt * bool(active) * all(reachability.values())
            forced_radio_time += dt * any(u['radio_failed'] for u in active.values())
            if operational:
                operational_time += dt
                operational_connected += dt * all(reachability[i] for i in operational)
                period=periods['before_first_fault' if now<first_fault else 'after_first_fault']
                period['population_s']+=dt;period['connected_s']+=dt*all(reachability[i] for i in operational)
            membership = (tuple(sorted(active)), tuple(sorted(operational)))
            if membership != members:
                transitions.append({'interval_start_s': start, 'sample_time_s': now,
                                    'active_ids': sorted(active),
                                    'operational_ids': sorted(operational),
                                    'excluded': [{'id': i, 'reason': 'aircraft_failed' if u['state'] == 'failed' else 'radio_failed'}
                                                 for i, u in all_uavs.items() if i not in operational]})
                members = membership
            for uid in list(open_intervals):
                reason = ('radio_failed' if active[uid]['radio_failed'] else 'no_graph_route') if uid in active and not reachability[uid] else None
                if reason != open_intervals[uid]['reason']:
                    intervals.append({**open_intervals.pop(uid), 'end_s': start})
            for uid, u in active.items():
                total = totals.setdefault(str(uid), {'active_s': 0.0, 'reachable_s': 0.0,
                                                      'radio_failed_s': 0.0, 'no_graph_route_s': 0.0})
                total['active_s'] += dt
                total['reachable_s'] += dt * reachability[uid]
                if not reachability[uid]:
                    reason = 'radio_failed' if u['radio_failed'] else 'no_graph_route'
                    total[reason + '_s'] += dt
                    open_intervals.setdefault(uid, {'id': uid, 'start_s': start, 'reason': reason,
                                                    'initial_state': u['state'], 'initial_position': u['position'],
                                                    'initial_battery_wh':u.get('battery_wh'),
                                                    'initial_reachable_nodes':reachable_nodes[uid],
                                                    'initial_policy':u.get('policy')})
                    open_intervals[uid]['last_policy']=u.get('policy')
                    open_intervals[uid]['last_battery_wh']=u.get('battery_wh')
    if not elapsed:
        raise ValueError('No raw frames')
    intervals.extend({**value, 'end_s': last} for value in open_intervals.values())
    for entry in intervals:
        entry['duration_s'] = entry['end_s'] - entry['start_s']
    for uid,total in totals.items():
        total['availability_pct']=100*total['reachable_s']/total['active_s'] if total['active_s'] else None
        total['longest_blackout_s']=max((row['duration_s'] for row in intervals if str(row['id'])==uid),default=0.)
    for period in periods.values():
        period['all_operational_connected_pct']=100*period['connected_s']/period['population_s'] if period['population_s'] else None
    return {'schema': 'cares-connectivity-diagnosis/v1', 'seed': manifest['seed'],
            'source_sha256': manifest['source_sha256'],
            'raw_trace_sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
            'duration_s': elapsed, 'all_active_connected_pct': 100 * all_connected / elapsed,
            'operational_population_time_s': operational_time,
            'all_radio_capable_survivors_connected_pct': 100 * operational_connected / operational_time if operational_time else None,
            'permanent_radio_exclusion_present_s': forced_radio_time,
            'fault_periods':periods,'per_vehicle': totals, 'population_transitions': transitions,
            'disconnections': sorted(intervals, key=lambda x: (x['start_s'], x['id'])),
            'limits': 'Graph reachability only, not packet delivery. No heartbeat age, route belief, or recovery cause is inferred from missing telemetry.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = diagnose(args.directory)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in ['seed', 'duration_s', 'all_active_connected_pct',
                                                 'all_radio_capable_survivors_connected_pct',
                                                 'permanent_radio_exclusion_present_s']}))


if __name__ == '__main__':
    main()
