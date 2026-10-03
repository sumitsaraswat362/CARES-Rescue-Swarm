#!/usr/bin/env python3
"""CARES shared runtime entry point; errors propagate with a nonzero exit."""
import argparse
import os
from pathlib import Path
import sys
import time
import math
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.resilience.runtime import Runtime


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scenario',default='scenarios/earthquake_basic.yaml')
    p.add_argument('--config',default='config/swarm_config.yaml')
    p.add_argument('--seed',type=int,default=int(os.environ.get('CARES_SEED',42)))
    p.add_argument('--mode',choices=['cares','direct','fixed','reactive','fifo','no_buffer'],default='cares')
    p.add_argument('--headless',action='store_true')
    p.add_argument('--speed',type=float,default=5.)
    p.add_argument('--duration',type=float)
    p.add_argument('--out',default=os.environ.get('CARES_LOG_DIR','logs/current'))
    args=p.parse_args();runtime=Runtime(args.scenario,args.config,args.seed,args.mode)
    m=runtime.mission
    if args.duration is not None:
        if not math.isfinite(args.duration) or args.duration <= 0:
            p.error('--duration must be positive and finite')
        m.world.duration_s=args.duration
    if not math.isfinite(args.speed) or args.speed <= 0:
        p.error('--speed must be positive and finite')
    renderer=None
    if not args.headless:
        from src.visualization.renderer import Renderer
        renderer=Renderer(m.world,m.uavs,m.gcs)
    try:
        while m.running:
            metrics=runtime.step()
            if renderer:
                renderer.render(metrics,m.mission_log)
                events=renderer.handle_events()
                if events.get('quit'):break
                if events.get('pause'):m.paused=not m.paused
                args.speed=max(.5,min(50,args.speed+events.get('speed_change',0)))
                if events.get('inject_failure') or events.get('inject_poi'):
                    from src.server import handle_command
                    state=SimpleNamespace(mission=m,runtime=runtime)
                    for action in ('inject_failure','inject_poi'):
                        if events.get(action):handle_command(state,{'action':action})
                time.sleep(m.dt/max(.1,args.speed))
    finally:
        runtime.save(args.out)
        if renderer:renderer.cleanup()
    print(runtime.report())

if __name__=='__main__':main()
