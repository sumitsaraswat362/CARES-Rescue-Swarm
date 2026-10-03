from types import SimpleNamespace
import numpy as np
from src.core.uav import UAV
from src.resilience.agent import Agent
from src.resilience.transport import Packet,Transport
from tests.resilience.test_agents import Planner


def run_handoff(block_child_ack=False):
    vehicles=[SimpleNamespace(id=i,pos=np.array([x,0.]),state=SimpleNamespace(value='relay')) for i,x in enumerate((100,200,110))]
    world=SimpleNamespace(gcs_pos=np.zeros(2),obstacles=[])
    t=Transport(world,vehicles,{'range_m':150,'packet_loss':0,'hop_delay_s':.05})
    if block_child_ack:
        original=t.uniform
        t.uniform=lambda *p: 1 if p[0]=='packet' and p[2]==1 and p[4]=='ack' else original(*p)
    events=[];agents={}
    for i,v in enumerate(vehicles):
        u=UAV(i,v.pos,{});u.assign_relay(v.pos,0)
        agents[i]=Agent(u,[0,0],[],Planner(),t.send,{'mode':'fixed'},events.append)
        t.register(i,agents[i].receive)
    old,child,new=agents[0],agents[1],agents[2]
    old.request={'old':0,'pos':[100,0],'created':0,'depart_by':99,'downstream':[1]}
    new.replacing=0;new.serves=0;new.planned_replacement=True
    def gcs(p,now):
        if p.kind=='probe':
            t.send(Packet(-1,p.source,'ack',{'id':p.payload['id']},now,128,9,now+3,tuple(reversed(p.hops)),(-1,)))
    t.register(-1,gcs)
    for tick in range(100):
        now=tick/10;t.step(.1,now)
        if tick%5==0:t.send(Packet(-1,-2,'beacon',{'route':[-1],'route_at':now},now,128,9,now+1))
        for a in agents.values():a.tick(now)
    return old,events,t.events


def test_planned_rotation_requires_actual_downstream_round_trip():
    old,events,traffic=run_handoff()
    completed=[e for e in events if e['event']=='handoff_complete']
    assert len(completed)==1 and completed[0]['downstream']==[1]
    proof=completed[0]['downstream_proofs']['1']
    assert proof['route']==[1,2,-1]
    assert any(e['event']=='packet_arrived' and e['kind']=='ack' and e['receiver']==1
               and e['observation_id']==proof['probe_id'] for e in traffic)
    assert old.retiring


def test_one_way_ack_loss_blocks_retirement_despite_replacement_gcs_service():
    old,events,_=run_handoff(block_child_ack=True)
    assert any(e['event']=='ack' and e['uav']==2 for e in events)
    assert not any(e['event']=='handoff_complete' for e in events)
    assert not old.retiring and old.request is not None
