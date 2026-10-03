"""Compare paired, independently audited full runs without pooling scenarios."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_evidence import audit
from tools.diagnose_connectivity import diagnose


def paired_interval(values, samples=2000):
    """Fixed percentile paired bootstrap, descriptive only for tiny samples."""
    if not values:
        return None
    rng = random.Random(731)
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return {'mean_difference': statistics.mean(values),
            'paired_seed_count': len(values), 'bootstrap_95_low': draws[int(.025 * samples)],
            'bootstrap_95_high': draws[min(samples - 1, int(.975 * samples))],
            'sample_size_at_least_30': len(values) >= 30,
            'method': 'paired percentile bootstrap, 2000 resamples, RNG seed 731'}


def load_runs(root):
    rows = {}
    for file in sorted(Path(root).glob('*/run_manifest.json')):
        manifest = json.loads(file.read_text())
        manifest.setdefault('environment_model', {'version':'legacy-v1'})
        report = json.loads((file.parent / 'final_report.json').read_text())
        checked = audit(file.parent)
        diagnosed = diagnose(file.parent)
        # Scenario content hash and resolved radio settings identify equal tests.
        radio_hash = hashlib.sha256(json.dumps(manifest['resolved_radio_config'], sort_keys=True).encode()).hexdigest()
        key = (manifest['scenario_sha256'], manifest['seed'], manifest['mode'], radio_hash)
        if key in rows:
            raise ValueError(f'Duplicate scenario/seed/mode in {root}: {key}')
        rows[key] = {'directory': str(file.parent), 'manifest': manifest, 'report': report,
                     'audit': checked, 'diagnosis': diagnosed}
    return rows


def compare(reference, candidate):
    left, right = load_runs(reference), load_runs(candidate)
    matched = sorted(left.keys() & right.keys())
    if not matched:
        raise ValueError('No matching scenario/seed/mode pairs')
    groups, pairs = {}, []
    for key in matched:
        a, b = left[key], right[key]
        # Configuration hash must match. Scenario-side radio overrides are covered
        # by the scenario hash; runtime overrides must match the resolved manifest.
        if a['manifest']['config_sha256'] != b['manifest']['config_sha256']:
            raise ValueError('Configuration file hashes differ')
        for field in ('resolved_radio_config', 'duration_s', 'world', 'survey_requirements', 'failures', 'environment_model'):
            if a['manifest'].get(field) != b['manifest'].get(field):
                raise ValueError(f'Resolved {field} differs')
        metrics = {}
        for name in ('delivered_completion_pct', 'priority_weighted_pct', 'all_uav_connectivity_pct',
                     'latency_p95_s', 'separation_violation_frames'):
            av, bv = a['audit']['recomputed'][name], b['audit']['recomputed'][name]
            metrics[name] = {'reference': av, 'candidate': bv,
                             'difference': bv - av if av is not None and bv is not None else None}
        name = 'all_radio_capable_survivors_connected_pct'
        av, bv = a['diagnosis'][name], b['diagnosis'][name]
        metrics[name] = {'reference': av, 'candidate': bv,
                         'difference': bv - av if av is not None and bv is not None else None}
        pair = {'scenario_sha256': key[0], 'seed': key[1], 'mode': key[2], 'radio_config_sha256': key[3], 'metrics': metrics,
                'reference_raw_sha256': a['audit']['raw_trace_sha256'],
                'candidate_raw_sha256': b['audit']['raw_trace_sha256'],
                'reference_evidence_consistent': a['audit']['evidence_consistent'],
                'candidate_evidence_consistent': b['audit']['evidence_consistent'],
                'reference_safety_passed': a['audit']['safety_passed'],
                'candidate_safety_passed': b['audit']['safety_passed']}
        pairs.append(pair)
        group = groups.setdefault(':'.join((key[0], key[2], key[3])), {})
        for name, row in metrics.items():
            if row['difference'] is not None:
                group.setdefault(name, []).append(row['difference'])
    return {'schema': 'cares-paired-comparison/v1', 'pairs': pairs,
            'unmatched_reference': [list(k) for k in sorted(left.keys() - right.keys())],
            'unmatched_candidate': [list(k) for k in sorted(right.keys() - left.keys())],
            'groups': {scenario: {name: paired_interval(values) for name, values in rows.items()}
                       for scenario, rows in groups.items()},
            'all_candidate_gates_passed': not (right.keys() - left.keys()) and all(
                p['reference_evidence_consistent'] and p['candidate_evidence_consistent']
                and p['candidate_safety_passed'] for p in pairs),
            'limits': 'This tool does not accept a release: seed reservation, immutable protocol, model parity and per-family noninferiority require separate qualification gates. Small seed sets are development evidence. No cross-competitor or physical-flight superiority is established.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = compare(args.reference, args.candidate)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'pairs': len(result['pairs']), 'all_candidate_gates_passed': result['all_candidate_gates_passed']}))
    if not result['all_candidate_gates_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
