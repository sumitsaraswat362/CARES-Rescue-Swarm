import numpy as np
from src.core.uav import UAV,UAVState,UAVRole
from src.resilience.agent import Agent,Task
from src.resilience.transport import Packet
from src.px4_bridge.sitl_agent import FlightSession,enu_to_ned,ned_to_enu

class Planner:
    def plan(self,a,b):return [np.array(a),np.array(b)]

def agent():
    u=UAV(0,[0,0],{});events=[];sent=[]
    a=Agent(u,[0,0],[Task(1,30,0,5)],Planner(),lambda p:sent.append(p) or True,{},events.append)
    return a,events,sent

def test_failure_requires_received_contact_timeout():
    a,e,s=agent()
    a.receive(Packet(2,-2,'beacon',{'pos':[30,0],'role':'scout'},0),0)
    a.tick(1);assert not any(x['event']=='contact_lost' for x in e)
    a.tick(4);assert any(x['event']=='contact_lost' for x in e)
    a.tick(5);assert sum(x['event']=='contact_lost' for x in e)==1


def test_claim_only_changes_after_message_and_expires():
    a,e,s=agent()
    assert not a.claims
    a.receive(Packet(2,-2,'beacon',{'claims':[(1,{'owner':2,'bid':9,'until':3})]},0),0)
    assert a.claims[1]['owner']==2
    a.tick(4);assert 1 not in a.claims


def test_old_route_timestamp_not_refreshed_by_forwarding():
    a,_,_=agent()
    a.receive(Packet(2,-2,'beacon',{'route':[2,-1],'route_at':0},0),2)
    assert a.route_at==0
    a.tick(4);assert not a.route


def test_mbb_requires_fresh_proof_before_departure():
    a,e,s=agent();a.uav.assign_relay(np.array([30.,0]),0)
    a.request={'created':0,'old':0}
    a.receive(Packet(2,-2,'ready',{'old':0,'proof_at':-10},0),5)
    assert a.uav.state==UAVState.RELAY
    a.receive(Packet(2,-2,'ready',{'old':0,'proof_at':5,'route':[2,-1]},5),5)
    assert a.uav.state==UAVState.RTL


def test_frames_stale_feedback_and_waypoint_progress():
    assert enu_to_ned([1,2,3])==[2,1,-3]
    assert ned_to_enu([2,1,-3])==[1,2,3]
    s=FlightSession([[0,0,5],[10,0,5]])
    assert s.target(0) is None
    s.observe([0,0,-5],0);assert s.target(0)==[0,10,-5]
    assert s.target(2) is None
    s.observe([0,10,-5],2);s.target(2);assert s.complete


def test_measured_backend_cannot_complete_survey_on_ground():
    from src.px4_bridge.measured import MeasuredBackend
    a,_,_=agent();u=a.uav
    u.assign_scout_task(1,np.array([0.,0.]),0)
    commands=[]
    feedback=lambda _:(np.array([0.,0.,0.]),np.zeros(3),.8)
    b=MeasuredBackend(feedback,lambda i,p:commands.append(p))
    for tick in range(200):b.advance(u,.1,tick*.1)
    assert not u.tasks_completed
    b.feedback=lambda _:(np.array([0.,0.,30.]),np.zeros(3),.8)
    for tick in range(200):b.advance(u,.1,20+tick*.1)
    assert 1 in u.tasks_completed
    assert commands
