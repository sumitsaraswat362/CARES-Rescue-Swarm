import itertools
import numpy as np
from src.resilience.routing import valid_route, choose_route
from src.resilience.agent import Agent, Task
from src.resilience.transport import Packet
from src.core.uav import UAV, UAVState
from tests.resilience.test_agents import agent, Planner
from tests.resilience.test_transport import net


def test_route_tie_is_independent_of_arrival_order():
    entries = [(2, {'route': [2,-1], 'route_at': 5, 'seen': 5}),
               (1, {'route': [1,-1], 'route_at': 4, 'seen': 5})]
    for order in itertools.permutations(entries):
        assert choose_route(dict(order), 0, 5, 3) == ((0,1,-1),4)
    assert choose_route(dict(entries), 0, 8, 3) == ((0,2,-1),5)
    assert choose_route(dict(entries), 0, 9, 3)[0] == ()


def test_malformed_loop_future_and_wrong_source_routes_rejected():
    for route,stamp in [([2,2,-1],5),([2,0,-1],5),([3,-1],5),([2,3],5),
                        ([2,-1],6),([2,-1],float('nan')),([2,-1],1),([True,-1],5)]:
        assert not valid_route(route,2,0,stamp,5,3)
    assert valid_route([-1],-1,0,5,5,3)
    assert valid_route([2,3,-1],2,0,5,5,3)


def test_reordered_beacon_cannot_replace_newer_route():
    a,_,_=agent()
    a.receive(Packet(2,-2,'beacon',{'route':[2,-1],'route_at':5},5),5)
    a.receive(Packet(2,-2,'beacon',{'route':[],'route_at':4},4),5.1)
    assert a.route==(0,2,-1) and a.route_at==5
    a.receive(Packet(2,-2,'beacon',{'route':[],'route_at':5.2},5.2),5.2)
    assert not a.route


def observation(oid='0:1:full:1'):
    return dict(id=oid,task=1,origin=0,level='full',priority=5,acquired_at=0,
                deadline=10,size=256,last_sent=-1e9)


def test_custody_storage_bound_expiry_and_ack_after_storage():
    a,events,sent=agent();a.config['custody_buffer_bytes']=256
    d={**observation(),'origin':2}
    p=Packet(2,0,'custody',d,0,256)
    a.receive(p,.1);a.receive(p,.2)
    assert len(a.custody)==1 and len(sent)==2
    assert sum(e['event']=='custody_stored' for e in events)==1
    a.receive(Packet(2,0,'custody',{**d,'id':'other'},0,256),.3)
    assert len(a.custody)==1 and len(sent)==2
    a.maintain_custody(10)
    assert not a.custody
    a.receive(p,10)
    assert not a.custody and len(sent)==2


def test_real_transport_backup_delivers_after_origin_dies():
    t,_=net(range_m=150,packet_loss=0)
    # Origin and backup communicate while GCS is blocked. Only the backup
    # remains alive when GCS connectivity returns.
    t.vehicles[0].pos=np.array([200.,0.]);t.vehicles[1].pos=np.array([100.,0.])
    events=[];agents={}
    for uid in (0,1):
        u=UAV(uid,t.vehicles[uid].pos,{})
        agents[uid]=Agent(u,[0,0],[Task(1,200,0,5)],Planner(),t.send,{},events.append)
        t.register(uid,agents[uid].receive)
    original=observation();agents[0].pending[original['id']]=original.copy()
    agents[0].neighbors[1]={'seen':0,'state':'relay'}
    t.blocked={-1}
    for tick in range(15):
        now=tick/10;t.step(.1,now)
        agents[0].maintain_custody(now);agents[1].maintain_custody(now)
    assert agents[0].custody_peers[original['id']]['confirmed']
    assert original['id'] in agents[0].pending  # Storage ACK is not delivery ACK.
    assert original['id'] in agents[1].custody
    t.vehicles[0].state.value='failed';agents[0].uav.state=UAVState.FAILED
    t.blocked.clear();agents[1].route=(1,-1)
    arrivals=[]
    def receive(p,now):
        arrivals.append(p)
        t.send(Packet(-1,p.source,'ack',{'id':p.payload['id']},now,128,9,now+2,
                      tuple(reversed(p.hops)),(-1,)))
    t.register(-1,receive)
    for tick in range(15,50):
        now=tick/10;t.step(.1,now);agents[1].maintain_custody(now)
    assert {p.payload['id'] for p in arrivals}=={original['id']}
    assert all(p.payload['origin']==0 and p.hops==(1,-1) for p in arrivals)
    assert not agents[1].custody
    assert any(e['event']=='custody_stored' for e in events)
    assert any(e['event']=='packet_arrived' and e['kind']=='custody' for e in t.events)


def test_copies_do_not_replicate_and_wrong_peer_ack_is_ignored():
    a,_,sent=agent();d=observation();a.pending[d['id']]=d
    a.neighbors={1:{'seen':0},2:{'seen':0}}
    a.maintain_custody(0)
    a.receive(Packet(2,0,'custody_ack',{'id':d['id']},0),.1)
    assert not a.custody_peers[d['id']]['confirmed']
    a.pending.clear();a.custody[d['id']]=d.copy();sent.clear()
    a.maintain_custody(.2)
    assert not sent  # No route to GCS and no replication of backups.


def test_old_boot_epoch_cannot_reenter_after_new_boot():
    a,_,_=agent()
    a.receive(Packet(2,-2,'beacon',{'route':[2,-1],'route_at':5,'boot_epoch':1},5),5)
    a.receive(Packet(2,-2,'beacon',{'route':[],'route_at':6,'boot_epoch':0},6),6)
    assert a.route==(0,2,-1) and a.neighbors[2]['boot_epoch']==1


def test_higher_priority_can_evict_lower_custody_without_duplicate_credit():
    a,events,sent=agent();a.config['custody_buffer_bytes']=256
    low={**observation('low'),'origin':2,'priority':1}
    high={**observation('high'),'origin':2,'priority':5}
    a.receive(Packet(2,0,'custody',low,0,256),.1)
    a.receive(Packet(2,0,'custody',high,0,256),.2)
    assert set(a.custody)=={'high'}
    assert any(e['event']=='custody_evicted' and e['id']=='low' for e in events)
    a.receive(Packet(2,0,'custody',{**high,'task':9},0,256),.3)
    assert a.custody['high']['task']==1 and len(sent)==2
