#!/usr/bin/env python3
"""Paired deterministic policy comparisons using the same shared runtime."""
import argparse
import json
from pathlib import Path
import statistics
from src.resilience.runtime import Runtime


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scenario',default='scenarios/relay_required.yaml')
    p.add_argument('--config',default='config/swarm_config.yaml')
    p.add_argument('--seeds',type=int,default=5)
    p.add_argument('--start-seed',type=int,default=100)
    p.add_argument('--modes',nargs='+',default=['cares','direct','fixed','reactive','fifo','no_buffer'])
    p.add_argument('--duration',type=float)
    p.add_argument('--out',default='logs/benchmarks')
    args=p.parse_args();rows=[]
    for seed in range(args.start_seed,args.start_seed+args.seeds):
        for mode in args.modes:
            r=Runtime(args.scenario,args.config,seed,mode)
            if args.duration:r.mission.world.duration_s=args.duration
            while r.mission.running:r.step()
            r.save(Path(args.out)/f'{mode}-{seed}');rows.append(r.report())
            print(mode,seed,rows[-1]['delivered_completion_pct'],flush=True)
    summary={}
    for mode in args.modes:
        values=[x for x in rows if x['mode']==mode]
        summary[mode]={}
        for metric in ['delivered_completion_pct','priority_weighted_pct','all_uav_connectivity_pct','separation_violation_frames','latency_p95_s']:
            nums=[x[metric] for x in values if x[metric] is not None]
            summary[mode][metric]={'n':len(nums),'mean':statistics.mean(nums) if nums else None,
                                  'min':min(nums) if nums else None,'max':max(nums) if nums else None,
                                  'std':statistics.stdev(nums) if len(nums)>1 else None}
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps({'runs':rows,'summary':summary},indent=2,allow_nan=False))

if __name__=='__main__':main()
