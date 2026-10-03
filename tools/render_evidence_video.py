"""Render recorded simulation positions/events. This is not a live browser recording."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_evidence import audit


def render(directory, output, speed=15, fps=10):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Circle
    root=Path(directory);out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    checked=audit(root)
    if not checked['evidence_consistent']:
        raise ValueError('Refusing to render evidence-inconsistent run')
    manifest=json.loads((root/'run_manifest.json').read_text())
    events=[json.loads(s) for s in (root/'events.jsonl').read_text().splitlines()]
    frames=[];next_time=0
    for line in (root/'raw_trace.jsonl').open():
        frame=json.loads(line)
        if frame['time']>=next_time:
            frames.append(frame);next_time+=speed/fps
    if frames[-1]['time']!=frame['time']:frames.append(frame)
    gcs_events=[e for e in events if e['event']=='received' and e.get('level')=='full']
    acquired=[e for e in events if e['event']=='acquired' and e.get('level')=='full']
    arrivals={(e.get('observation_id'),e['time']) for e in events if e['event']=='packet_arrived' and e.get('receiver')==-1}
    gcs_events=[e for e in gcs_events if (e['id'],e['time']) in arrivals]
    # GCS coordinates are static scenario input, not invented from a trajectory.
    import yaml
    scenario_path=Path(manifest['scenario'])
    if hashlib.sha256(scenario_path.read_bytes()).hexdigest()!=manifest['scenario_sha256']:
        raise ValueError('Scenario file differs from recorded manifest')
    scenario=yaml.safe_load(scenario_path.read_text())
    gcs=scenario['gcs']['position'];gcs_xy=(gcs['x'],gcs['y'])
    fig=plt.figure(figsize=(12.8,7.2),facecolor='#101b2c')
    ax=fig.add_axes([.06,.15,.64,.70],facecolor='#14253b');side=fig.add_axes([.74,.16,.25,.68]);side.axis('off')
    ax.set(xlim=(0,manifest['world']['width']),ylim=(0,manifest['world']['height']),xlabel='East / m',ylabel='North / m')
    ax.tick_params(colors='white');ax.xaxis.label.set_color('white');ax.yaxis.label.set_color('white');ax.set_aspect('equal')
    for o in manifest.get('obstacles',[]):ax.add_patch(Circle((o['x'],o['y']),o['radius'],color='#66717c',alpha=.7))
    links=LineCollection([],colors='#4a7996',linewidths=.6,alpha=.6);ax.add_collection(links)
    tasks=manifest['tasks'];pts=ax.scatter([t['x'] for t in tasks],[t['y'] for t in tasks],s=65,marker='s')
    for t in tasks:ax.text(t['x']+25,t['y']+15,str(t['id']),color='#d8e2ec',fontsize=8)
    ax.scatter(*gcs_xy,marker='*',s=160,c='#ffffff');ax.text(gcs_xy[0],gcs_xy[1]-65,'GCS',color='white',fontsize=9)
    fleet=ax.scatter([],[],s=48,zorder=5);labels=[ax.text(0,0,str(u['id']),color='white',fontsize=8) for u in frames[0]['uavs']]
    title=fig.text(.06,.92,'CARES | Recorded simulation evidence',fontsize=20,color='white',weight='bold')
    fig.text(.06,.875,f"{Path(manifest['scenario']).stem} | seed {manifest['seed']} | {speed}x playback | source {manifest['source_sha256'][:12]}",fontsize=10,color='#9cb5ca')
    fig.text(.06,.05,'Simulated positions. Lines show model reachability, not packet receipt. Top-down view hides altitude layers.',fontsize=9,color='#9cb5ca')
    stats=side.text(0,.98,'',va='top',color='white',fontsize=12,linespacing=1.5)
    note=side.text(0,.38,'',va='top',color='#efbd72',fontsize=10,linespacing=1.5,wrap=True)
    writer=FFMpegWriter(fps=fps,metadata={'title':'CARES recorded simulation evidence'},codec='libx264',extra_args=['-pix_fmt','yuv420p','-crf','23'])
    with writer.saving(fig,str(out),100):
        for f in frames:
            now=f['time'];by_id={u['id']:u for u in f['uavs']};positions={i:u['position'][:2] for i,u in by_id.items()};positions[-1]=gcs_xy
            links.set_segments([[positions[a],positions[b]] for a,b in f['edges'] if a<b and a in positions and b in positions])
            fleet.set_offsets([u['position'][:2] for u in f['uavs']])
            fleet.set_color(['#ea665c' if u['state']=='failed' else '#ffaf49' if u['radio_failed'] else '#7fc8ff' for u in f['uavs']])
            for label,u in zip(labels,f['uavs']):label.set_position((u['position'][0]+18,u['position'][1]+18))
            got={e['task'] for e in gcs_events if e['time']<=now};seen={e['task'] for e in acquired if e['time']<=now}
            pts.set_color(['#59d9a2' if t['id'] in got else '#efd274' if t['id'] in seen else '#61778d' for t in tasks])
            faults=[e for e in events if e['event']=='injected_failure' and e['time']<=now]
            stats.set_text(f"MISSION TIME\n{now:6.1f} / {manifest['duration_s']} s\n\nFull observations at GCS\n{len(got)} / {len(tasks)} targets\n\nLocally acquired\n{len(seen)} / {len(tasks)} targets\n\nInjected disturbances\n{len(faults)}")
            note.set_text('TARGETS\nGreen: full GCS receipt\nYellow: acquired only\nGrey: not acquired\n\nAIRCRAFT\nBlue: active\nOrange: radio failed\nRed: motor failed\n\n'+'\n'.join(f"{e['time']:.1f}s: UAV {e['uav']}\n{e['kind']}" for e in faults[-2:]))
            writer.grab_frame()
    plt.close(fig)
    receipt={'scope':'Recorded simulation replay, not browser QA or measured flight','frames':len(frames),'fps':fps,'playback_speed':speed,'source_sha256':manifest['source_sha256'],'raw_trace_sha256':checked['raw_trace_sha256'],'video_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'final_delivered_targets':len(got),'total_targets':len(tasks)}
    out.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--out',required=True);p.add_argument('--speed',type=float,default=15);a=p.parse_args();print(json.dumps(render(a.directory,a.out,a.speed)))
