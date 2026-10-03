import json
from src.resilience.runtime import Runtime

def test_reproducible_runtime_and_finite_report(tmp_path):
    reports=[]
    for _ in range(2):
        r=Runtime('scenarios/relay_required.yaml',seed=7)
        for i in range(100):r.step()
        reports.append(r.report())
    assert reports[0]==reports[1]
    r.save(tmp_path)
    assert json.loads((tmp_path/'final_report.json').read_text())['schema']=='cares-evidence/v2'
    assert reports[0]['geofence_violation_samples']==0


def test_web_uses_same_runtime_and_outage_clock():
    from src.server import SimState,serialize_state,handle_command
    sim=SimState();sim.init('scenarios/relay_required.yaml')
    sim.last_metrics=sim.runtime.step()
    state=serialize_state(sim)
    assert state['metrics']['delivered_completion_pct']==sim.runtime.report()['delivered_completion_pct']
    handle_command(sim,{'action':'trigger_outage'})
    assert sim.runtime.transport.outage_until==sim.mission.sim_time+5
