"""Execute every bundled scenario, plus paired seeds/modes, with raw audits."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.resilience.runtime import Runtime
from tools.audit_evidence import audit


def execute(job):
    scenario, seed, mode, burst, root = job
    name=f'{Path(scenario).stem}-{seed}-{mode}-burst{burst}'
    out=Path(root)/name
    runtime=Runtime(scenario,seed=seed,mode=mode)
    if burst is not None:
        runtime.config['burst_probability']=burst
    while runtime.mission.running:
        runtime.step()
    runtime.save(out)
    result=audit(out)
    result.update(scenario=scenario,output=str(out),configured_burst_probability=runtime.config.get('burst_probability',0),
                  handoffs=runtime.report()['mbb_handoffs_completed'],duration_s=runtime.mission.sim_time)
    (out/'independent_audit.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='logs/audit-matrix');args=parser.parse_args()
    jobs=[(str(p),100,'cares',None,args.out) for p in sorted(Path('scenarios').glob('*.yaml'))]
    jobs += [('scenarios/'+name+'.yaml',101,'cares',None,args.out) for name in ['earthquake_hard','tier3','relay_rotation']]
    jobs += [('scenarios/relay_required.yaml',100,mode,None,args.out) for mode in ['direct','fixed','reactive','fifo','no_buffer']]
    jobs += [('scenarios/relay_required.yaml',seed,'cares',.15,args.out) for seed in [100,101,102]]
    results=[]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(execute,jobs):
            results.append(result)
            print(json.dumps({k:result[k] for k in ['scenario','seed','mode','evidence_consistent','safety_passed','recomputed','observed_failure_events']}),flush=True)
            Path(args.out).mkdir(parents=True,exist_ok=True)
            (Path(args.out)/'summary.json').write_text(json.dumps(results,indent=2))
    if any(not r['evidence_consistent'] or not r['safety_passed'] for r in results):
        raise SystemExit(1)


if __name__=='__main__':main()
