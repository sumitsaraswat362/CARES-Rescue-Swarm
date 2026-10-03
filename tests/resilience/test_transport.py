from types import SimpleNamespace
import numpy as np
from src.resilience.transport import Transport,Packet
from src.resilience.evaluation import Evaluator
from src.resilience.agent import Task


def net(mode='cares',**cfg):
    us=[SimpleNamespace(id=i,pos=np.array([100.+i*100,0]),state=SimpleNamespace(value='idle')) for i in range(2)]
    w=SimpleNamespace(gcs_pos=np.array([0.,0]),obstacles=[])
    t=Transport(w,us,{'range_m':150,'packet_loss':0,'hop_delay_s':.1,**cfg},mode=mode)
    received=[]
    for i in [-1,0,1]:t.register(i,lambda p,now:received.append((p,now)))
    return t,received


def run(t,start,end):
    for tick in range(start,end):t.step(.1,tick/10)


def test_multihop_requires_forwarding_and_delay():
    t,r=net();t.send(Packet(1,-1,'observation',{'id':'a'},0,128,1,10,(1,0,-1),(1,)))
    t.step(.1,0);assert not r
    run(t,1,10);assert len(r)==1 and r[0][0].hops==(1,0,-1)
    direct,received=net('direct');direct.send(Packet(1,-1,'observation',{'id':'a'},0,128,1,10,(1,0,-1),(1,)))
    run(direct,0,20);assert not received


def test_outage_buffer_expiration_and_queue_bound():
    t,r=net(queue_bytes=256);t.outage_until=2
    assert t.send(Packet(1,-1,'observation',{'id':'a'},0,128,1,10,(1,0,-1),(1,)))
    assert t.send(Packet(1,-1,'observation',{'id':'expired'},0,128,1,1,(1,0,-1),(1,)))
    assert not t.send(Packet(1,-1,'observation',{},0,128))
    run(t,0,20);assert not r
    run(t,20,40);assert [p.payload['id'] for p,_ in r]==['a']
    assert t.stats['expired_packets']==1


def test_control_cannot_cross_blocked_link():
    t,r=net();t.blocked={0,1}
    t.send(Packet(1,-2,'beacon',{},0,128,9,1));run(t,0,20)
    assert not r


def test_fifo_and_priority_schedule_differ():
    for mode,expected in [('cares','urgent'),('fifo','ordinary')]:
        t,r=net(mode,bytes_per_second=1280)
        t.send(Packet(0,-1,'observation',{'id':'ordinary'},0,128,1,10,(0,-1),(0,)))
        t.send(Packet(0,-1,'observation',{'id':'urgent'},0,128,9,10,(0,-1),(0,)))
        run(t,0,10);assert r[0][0].payload['id']==expected


def test_acquisition_is_not_delivery_and_duplicate_is_not_double_credit():
    e=Evaluator();task=Task(1,0,0,5)
    event={'event':'acquired','id':'x','task':1,'level':'full','acquired_at':0,'deadline':10,'time':0}
    e.record(event);assert e.report([task],1)['delivered_completion_pct']==0
    event={**event,'event':'received','time':2};e.record(event);e.record(event)
    assert e.report([task],3)['delivered_completion_pct']==100
    assert len(e.delivered)==1
