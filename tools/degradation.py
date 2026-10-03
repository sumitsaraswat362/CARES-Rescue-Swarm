"""Fresh degradation runs; event injections and permanent failures are distinct."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.run_audit_matrix import execute


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--seeds',type=int,default=2)
    parser.add_argument('--start-seed',type=int,default=100)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--burst-probability',type=float,default=.15)
    parser.add_argument('--out',default='logs/audit-degradation')
    parser.add_argument('--result',default='degradation_results.json')
    args=parser.parse_args(argv)
    if args.seeds<1 or args.workers<1 or not 0<=args.burst_probability<=1:
        parser.error('Positive seeds/workers and burst probability in [0,1] required')
    jobs=[(f'scenarios/{tier}.yaml',seed,'cares',args.burst_probability,args.out)
          for tier in ('tier1','tier2','tier3') for seed in range(args.start_seed,args.start_seed+args.seeds)]
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(execute,jobs):
            report=json.loads((Path(result['output'])/'final_report.json').read_text())
            manifest=json.loads((Path(result['output'])/'run_manifest.json').read_text())
            rows.append({**result,'failed_uavs':report['failed_uavs'],
                         'radio_failed_uavs':report['radio_failed_uavs'],'battery_fault_uavs':report['battery_fault_uavs'],
                         'resolved_failures':manifest['failures']})
            print(json.dumps(rows[-1]),flush=True)
    summary={}
    for tier in ('tier1','tier2','tier3'):
        subset=[r for r in rows if Path(r['scenario']).stem==tier]
        summary[tier]={}
        for metric in ('failed_uavs','observed_failure_events','scheduled_failures_due'):
            values=[r[metric] for r in subset]
            summary[tier][metric]={'mean':statistics.mean(values),'std':statistics.stdev(values) if len(values)>1 else None}
    out={'schema':'cares-degradation/v2','burst_probability':args.burst_probability,
         'definition':'failed_uavs counts permanent FAILED state; injected events include recoverable comms/battery disturbances',
         'runs':rows,'summary':summary}
    Path(args.result).write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    if any(not r['evidence_consistent'] or not r['safety_passed'] for r in rows):raise SystemExit(1)


if __name__=='__main__':main()
