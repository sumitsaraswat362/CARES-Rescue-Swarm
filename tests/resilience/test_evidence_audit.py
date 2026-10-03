import json
import shutil

import pytest

from src.resilience.runtime import Runtime
from tools.audit_evidence import audit


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    out = tmp_path_factory.mktemp('evidence')
    runtime = Runtime('scenarios/relay_required.yaml', seed=100)
    while runtime.mission.running:
        runtime.step()
    runtime.save(out)
    result = audit(out)
    assert result['evidence_consistent'] and result['safety_passed']
    assert result['received_full_task_ids']
    return out


def test_audit_rejects_fabricated_completion(evidence, tmp_path):
    shutil.copytree(evidence, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'final_report.json'
    report = json.loads(path.read_text())
    report['delivered_completion_pct'] = 99.5
    path.write_text(json.dumps(report))
    assert not audit(tmp_path)['evidence_consistent']


def test_audit_rejects_remote_position_survey(evidence, tmp_path):
    shutil.copytree(evidence, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'raw_trace.jsonl'
    frames = [json.loads(line) for line in path.read_text().splitlines()]
    for frame in frames:
        for uav in frame['uavs']:
            uav['position'][:2] = [0, 0]
    path.write_text(''.join(json.dumps(frame)+'\n' for frame in frames))
    errors = audit(tmp_path)['errors']
    assert any('Acquisition lacks position' in error for error in errors)


def test_audit_rejects_missing_failure(evidence, tmp_path):
    shutil.copytree(evidence, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'run_manifest.json'
    manifest = json.loads(path.read_text())
    manifest['failures'].append({'time': 10, 'uav': 0, 'kind': 'motor_failure'})
    path.write_text(json.dumps(manifest))
    assert any('Failure count mismatch' in error for error in audit(tmp_path)['errors'])


def test_audit_rejects_receipt_without_packet(evidence, tmp_path):
    shutil.copytree(evidence, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'events.jsonl'
    events = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text(''.join(json.dumps(e)+'\n' for e in events if e['event'] != 'packet_arrived'))
    assert any('Receipt lacks GCS packet' in error for error in audit(tmp_path)['errors'])
