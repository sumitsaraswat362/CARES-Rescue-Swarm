"""Independent check of recorded measured poses; no bridge result is trusted."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def audit(path, waypoints):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    index = 0
    hits = []
    status = None
    last_pose = None
    disarm = None
    errors = []
    previous = -math.inf
    for row in rows:
        now = row['monotonic']
        if now < previous:
            errors.append('nonmonotonic log')
        previous = now
        if row['event'] == 'status':
            status = row
            if index == len(waypoints) and not row['armed']:
                disarm = row
        if row['event'] == 'position':
            last_pose = row
            if not all(math.isfinite(v) for v in row['enu']):
                errors.append('nonfinite pose')
                continue
            engaged = status and status['armed'] and status['offboard'] and 0 <= now-status['monotonic'] <= 1
            if index < len(waypoints) and engaged and math.dist(row['enu'], waypoints[index]) <= 2:
                hits.append({'waypoint': waypoints[index], 'measured': row['enu'], 'time': now, 'error_m': math.dist(row['enu'], waypoints[index])})
                index += 1
    if index != len(waypoints):
        errors.append('ordered measured waypoints missing')
    if disarm is None:
        errors.append('post-route measured disarm missing')
    if last_pose is None or abs(last_pose['enu'][2]) > 1:
        errors.append('final pose not near home altitude')
    if last_pose and disarm and abs(last_pose['monotonic']-disarm['monotonic']) > 1:
        errors.append('landing pose/status not contemporaneous')
    return {'passed': not errors, 'errors': errors, 'scope': 'one recorded waypoint flight only; no dwell, swarm, radio recovery or field validation', 'raw_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'ordered_hits': hits, 'final_pose': last_pose, 'post_route_disarm': disarm, 'records': len(rows)}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('recording', type=Path)
    p.add_argument('waypoints', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = audit(args.recording, json.loads(args.waypoints.read_text()))
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print('INDEPENDENT_PX4_JSON '+json.dumps(result), flush=True)
    raise SystemExit(0 if result['passed'] else 1)
