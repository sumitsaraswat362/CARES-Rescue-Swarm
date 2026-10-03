import json
from tools.accept_qualification import accept
from tools.qualification import jobs_for


def test_development_plan_cannot_be_called_qualification(tmp_path):
    plan=tmp_path/'plan.json';plan.write_text(json.dumps({'jobs':jobs_for(['development'])}))
    result=accept(plan,tmp_path)
    assert not result['accepted']
    assert '600-run' in result['errors'][0]


def test_missing_runs_fail_even_with_full_plan(tmp_path):
    plan=tmp_path/'plan.json';plan.write_text(json.dumps({'jobs':jobs_for(['qualification','confirmation','burst'])}))
    result=accept(plan,tmp_path)
    assert not result['accepted'] and result['observed_pairs']==0
    assert sum(x.startswith('Missing attempt:') for x in result['errors'])==600
