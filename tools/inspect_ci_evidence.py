"""Read prior CI artifacts; never replace, rerun or relabel a mission result."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile


def download(run,name,root,repo):
    subprocess.run(['gh','run','download',str(run),'--repo',repo,'--name',name,'--dir',str(root)],check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',required=True);p.add_argument('--out',required=True);args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    download(35534036901,'qualification-acceptance',out/'acceptance',args.repository)
    print('ACCEPTANCE_JSON '+(out/'acceptance/acceptance.json').read_text(),flush=True)
    summaries=[]
    for shard in range(12):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);download(35534036901,f'qualification-shard-{shard}',root,args.repository)
            summary=json.loads((root/'summary.json').read_text());summaries.append(summary)
            (out/f'shard-{shard}-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            for row in summary['runs']:
                audit=row.get('audit',{});m=audit.get('recomputed',{})
                record={'job':row['job']['id'],'passed':row['passed'],'error':row.get('error'),'exit_code':row.get('exit_code'),'wall_seconds':row['wall_seconds'],'errors':audit.get('errors'), 'safety':audit.get('safety_passed'),'metrics':m,'obstacle_penetration_samples':audit.get('obstacle_penetration_samples'),'terrain_penetration_samples':audit.get('terrain_penetration_samples')}
                print('RUN_JSON '+json.dumps(record),flush=True)
                if not row['passed']:
                    folder=root/row['job']['id']
                    stderr=folder/'stderr.log'
                    if stderr.exists() and stderr.stat().st_size:print('STDERR '+row['job']['id']+' '+stderr.read_text()[-4000:],flush=True)
                    manifests=list(folder.glob('*/run_manifest.json'))
                    if manifests:
                        run=manifests[0].parent
                        if audit.get('obstacle_penetration_samples',0)>0:
                            manifest=json.loads(manifests[0].read_text());first=None
                            for line in (run/'raw_trace.jsonl').open():
                                f=json.loads(line)
                                for u in f['uavs']:
                                    for o in manifest['obstacles']:
                                        if u['state']!='failed' and (u['position'][0]-o['x'])**2+(u['position'][1]-o['y'])**2 < o['radius']**2:
                                            first={'time':f['time'],'uav':u,'obstacle':o};break
                                    if first:break
                                if first:break
                            print('OBSTACLE_FIRST '+row['job']['id']+' '+json.dumps(first),flush=True)
    (out/'counts.json').write_text(json.dumps({'planned':600,'recorded':sum(s['recorded_runs'] for s in summaries),'passed':sum(s['passed_runs'] for s in summaries)},indent=2)+'\n')
    print('COUNTS_JSON '+(out/'counts.json').read_text(),flush=True)
    download(35532841043,'px4-measured-evidence',out/'px4',args.repository)
    for f in sorted((out/'px4').rglob('*')):
        if f.name in ('gate_result.json','bridge.log','px4.log'):
            print('PX4_FILE '+f.name+'\n'+f.read_text(errors='replace')[-14000:],flush=True)
        elif f.name=='flight.jsonl':
            rows=[json.loads(s) for s in f.read_text().splitlines()]
            print('PX4_EVENTS '+json.dumps(dict(Counter(r['event'] for r in rows))),flush=True)
            print('PX4_ACKS '+json.dumps(dict(Counter(str((r['command'],r['result'])) for r in rows if r['event']=='command_ack'))),flush=True)
            statuses=[r for r in rows if r['event']=='status'];print('PX4_STATUS '+json.dumps([r for i,r in enumerate(statuses) if i==0 or any(r[k]!=statuses[i-1][k] for k in ('armed','offboard'))]),flush=True)
            positions=[r for r in rows if r['event']=='position'];print('PX4_FIRST_LAST_POSE '+json.dumps([positions[0],positions[-1]] if positions else []),flush=True)
            print('PX4_OTHER '+json.dumps([r for r in rows if r['event'] not in ('position','status','command_ack')]),flush=True)
if __name__=='__main__':main()
