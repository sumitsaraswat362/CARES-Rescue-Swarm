"""Freeze and execute a resumable qualification plan against two clean checkouts.

freeze records immutable commits/source files and enumerates every planned job.
run fails on changed inputs and retains failures. No prefilled benchmark outcomes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

FAMILIES = ('earthquake_basic', 'earthquake_hard', 'tier1', 'tier2', 'tier3', 'relay_rotation')
STAGES = {'development': (range(100, 102), None), 'qualification': (range(200, 230), None),
          'confirmation': (range(300, 310), None), 'burst': (range(400, 410), .15)}


def fingerprint(root):
    root = Path(root).resolve()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError(f'Checkout must be clean, including untracked files: {root}')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    digests = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files if p}
    # Detect runtime Python files that are ignored and would escape git status.
    unexpected = [str(p.relative_to(root)) for p in (root / 'src').rglob('*.py')
                  if str(p.relative_to(root)) not in digests]
    if unexpected:
        raise ValueError(f'Untracked runtime Python files: {unexpected}')
    runtime=hashlib.sha256()
    for path in sorted((root/'src').rglob('*.py')):
        runtime.update(str(path.relative_to(root)).encode());runtime.update(path.read_bytes())
    return {'root': str(root), 'commit': commit, 'files_sha256': digests, 'runtime_source_sha256':runtime.hexdigest()}


def jobs_for(stages, seed_epoch=0):
    if seed_epoch not in (0,1):raise ValueError('Unregistered seed epoch')
    jobs = []
    for stage in stages:
        seeds, burst = STAGES[stage]
        for family in FAMILIES:
            for original_seed in seeds:
                seed=original_seed+(1000*seed_epoch if stage!='development' else 0)
                for side in ('reference', 'candidate'):
                    jobs.append({'id': f'{stage}-{family}-{seed}-{side}', 'stage': stage,
                                 'scenario': f'scenarios/{family}.yaml', 'seed': seed,
                                 'mode': 'cares', 'burst': burst, 'side': side})
    return jobs


def freeze(reference, candidate, out, stages, seed_epoch=0):
    result = {'schema': 'cares-qualification/v1', 'created_unix': time.time(),
              'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'checkouts': {side: fingerprint(root) for side, root in [('reference', reference), ('candidate', candidate)]},
              'seed_epoch':seed_epoch, 'jobs': jobs_for(stages,seed_epoch), 'python': sys.version, 'platform': platform.platform(),
              'dependencies': subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines()}
    # Same scenarios/config files are a prerequisite to a paired policy comparison.
    a, b = (result['checkouts'][side]['files_sha256'] for side in ('reference', 'candidate'))
    for name in ['config/swarm_config.yaml'] + [f'scenarios/{f}.yaml' for f in FAMILIES]:
        if a.get(name) != b.get(name) or name not in a:
            raise ValueError(f'Paired input file mismatch: {name}')
    destination = Path(out)
    if destination.exists():
        raise ValueError('Refusing to replace an existing frozen protocol')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n')
    return result


def artifact_hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name not in ('attempt.json','attempt.tmp')}


def execute_job(job, checkouts, root, timeout):
    directory = root / job['id']
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / 'attempt.json'
    # Every prior failure remains visible. Repairing a candidate requires a new
    # commit and new protocol; resumption skips recorded success or failure alike.
    if receipt.exists():
        prior = json.loads(receipt.read_text())
        if prior['job'] != job or prior.get('artifacts_sha256') != artifact_hashes(directory):
            raise ValueError(f'Recorded attempt artifacts changed: {directory}')
        return prior
    started = time.monotonic()
    command = [sys.executable, '-c',
               'import json,sys; from tools.run_audit_matrix import execute; '
               'print(json.dumps(execute(tuple(json.loads(sys.argv[1])))))',
               json.dumps([job['scenario'], job['seed'], job['mode'], job['burst'], str(directory)])]
    result = {'job': job, 'command': command, 'passed': False}
    try:
        with (directory / 'stdout.log').open('w') as stdout, (directory / 'stderr.log').open('w') as stderr:
            process = subprocess.run(command, cwd=checkouts[job['side']]['root'], env=os.environ.copy(),
                                     stdout=stdout, stderr=stderr, timeout=timeout)
        result['exit_code'] = process.returncode
        audits = list(directory.glob('*/independent_audit.json'))
        if process.returncode == 0 and len(audits) == 1:
            evidence = json.loads(audits[0].read_text())
            result['audit'] = evidence
            result['passed'] = evidence['evidence_consistent'] and evidence['safety_passed']
        else:
            result['error'] = 'Worker failed or did not produce exactly one independent audit'
    except subprocess.TimeoutExpired:
        result['error'] = f'Wall-clock timeout after {timeout} seconds'
    except Exception as exc:
        result['error'] = str(exc)
    result['wall_seconds'] = time.monotonic() - started
    result['artifacts_sha256'] = artifact_hashes(directory)
    temporary = receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    temporary.replace(receipt)
    return result


def run(plan, out, workers=2, timeout=1800, shard_index=0, shard_count=1):
    if workers < 1 or timeout <= 0 or shard_count<1 or not 0<=shard_index<shard_count:
        raise ValueError('Positive worker count and timeout required')
    protocol_path = Path(plan)
    protocol = json.loads(protocol_path.read_text())
    if protocol['driver_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('Qualification driver changed after protocol freeze')
    for side, expected in protocol['checkouts'].items():
        if fingerprint(expected['root']) != expected:
            raise ValueError(f'{side} checkout changed after freeze')
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    marker = root / 'protocol.sha256'
    if marker.exists() and marker.read_text().strip() != identity:
        raise ValueError('Output directory belongs to another frozen protocol')
    marker.write_text(identity + '\n')
    selected=[job for index,job in enumerate(protocol['jobs']) if index%shard_count==shard_index]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(lambda job: execute_job(job, protocol['checkouts'], root, timeout), selected):
            rows.append(row)
            print(json.dumps({'job': row['job']['id'], 'passed': row['passed'], 'wall_seconds': row['wall_seconds']}), flush=True)
            summary = {'protocol_sha256': identity, 'planned_runs': len(protocol['jobs']),
                       'shard_index':shard_index,'shard_count':shard_count,'planned_shard_runs':len(selected),
                       'recorded_runs': len(rows), 'passed_runs': sum(r['passed'] for r in rows), 'runs': rows}
            (root / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    # Recheck after running; a concurrently changed checkout invalidates the batch.
    for expected in protocol['checkouts'].values():
        if fingerprint(expected['root']) != expected:
            raise ValueError('Checkout changed during execution; batch is invalid')
    return all(row['passed'] for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    creation = commands.add_parser('freeze')
    creation.add_argument('--reference', required=True)
    creation.add_argument('--candidate', required=True)
    creation.add_argument('--out', required=True)
    creation.add_argument('--seed-epoch',type=int,choices=(0,1),default=0)
    creation.add_argument('--stages', nargs='+', choices=STAGES, default=['qualification', 'confirmation', 'burst'])
    execution = commands.add_parser('run')
    execution.add_argument('plan')
    execution.add_argument('--out', required=True)
    execution.add_argument('--workers', type=int, default=2)
    execution.add_argument('--timeout', type=float, default=1800)
    execution.add_argument('--shard-index',type=int,default=0)
    execution.add_argument('--shard-count',type=int,default=1)
    args = parser.parse_args()
    if args.action == 'freeze':
        plan = freeze(args.reference, args.candidate, args.out, args.stages,args.seed_epoch)
        print(json.dumps({'planned_runs': len(plan['jobs']), 'status': 'planned, not executed'}))
    elif not run(args.plan, args.out, args.workers, args.timeout,args.shard_index,args.shard_count):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
