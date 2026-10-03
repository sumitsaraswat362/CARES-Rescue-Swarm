import hashlib
import json
from tools.check_claims import check


def fixture(tmp_path):
    source = tmp_path / 'module.py'
    source.write_text('def observed():\n    return 1\n')
    evidence = tmp_path / 'result.json'
    evidence.write_text(json.dumps({'completion': 50}))
    claim = {'id': 'completion', 'status': 'verified',
             'implementation': [{'path': 'module.py', 'symbol': 'observed'}],
             'evidence': [{'path': 'result.json', 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(),
                           'keys': ['completion'], 'equals': 50}]}
    registry = tmp_path / 'claims.json'
    registry.write_text(json.dumps({'claims': [claim]}))
    return registry, evidence, claim


def test_tampered_result_cannot_pass_claim_check(tmp_path):
    registry, evidence, _ = fixture(tmp_path)
    assert check(registry, tmp_path)['passed']
    evidence.write_text(json.dumps({'completion': 100}))
    assert not check(registry, tmp_path)['passed']


def test_missing_symbol_and_false_number_are_rejected(tmp_path):
    registry, _, claim = fixture(tmp_path)
    claim['implementation'][0]['symbol'] = 'invented'
    claim['evidence'][0]['equals'] = 99.8
    registry.write_text(json.dumps({'claims': [claim]}))
    assert len(check(registry, tmp_path)['errors']) == 2


def test_verified_claim_requires_evidence(tmp_path):
    registry, _, claim = fixture(tmp_path)
    claim['evidence'] = []
    registry.write_text(json.dumps({'claims': [claim]}))
    assert not check(registry, tmp_path)['passed']
