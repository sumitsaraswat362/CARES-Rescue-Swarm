import numpy as np
import yaml
from src.core.uav import UAVState, UAVRole
from src.resilience.runtime import Runtime
from tests.resilience.test_agents import agent


def test_all_disturbances_fire_without_being_counted_as_dead_aircraft(tmp_path):
    data=yaml.safe_load(open('scenarios/relay_required.yaml'))
    data['failures']=[{'time_s':.1*(i+1),'uav_index':0,'type':kind}
                      for i,kind in enumerate(('motor_failure','comms_failure','battery_critical'))]
    data['simulation']['duration_s']=1
    path=tmp_path/'faults.yaml';path.write_text(yaml.safe_dump(data))
    r=Runtime(str(path))
    while r.mission.running:r.step()
    report=r.report()
    assert report['scheduled_failure_events']==report['injected_failure_events']==3
    assert report['failed_uavs']==1
    assert report['radio_failed_uavs']==report['battery_fault_uavs']==1
    assert all(f.triggered for f in r.mission.world.failures)


def test_live_replacement_prevents_repeated_dispatch_for_stale_original():
    a,events,_=agent()
    a.route=(0,-1);a.route_at=10
    a.neighbors={2:{'seen':0,'pos':[30,0],'vel':[0,0],'role':'relay'},
                 3:{'seen':10,'pos':[30,15],'vel':[0,0],'role':'relay','serves':2}}
    a.tick(10)
    assert a.replacing is None
    assert not any(e['event']=='replacement_dispatched' for e in events)


def test_temporary_contact_loss_does_not_permanently_consume_scout():
    a,events,_=agent()
    a.uav.assign_relay(np.array([30.,0.]),0)
    a.replacing=2;a.serves=2
    a.neighbors[2]={'seen':10,'state':'relay','role':'relay','pos':[30,0],'vel':[0,0]}
    a.route=(0,-1);a.route_at=10
    a.tick(10)
    assert a.replacing is None and a.serves is None
    assert a.uav.role != UAVRole.RELAY
    assert any(e['event']=='replacement_cancelled' for e in events)


def test_initial_hard_relay_geometry_respects_radio_range():
    runtime=Runtime('scenarios/earthquake_hard.yaml')
    stations=[u.relay_station_pos for u in runtime.mission.uavs if u.role==UAVRole.RELAY]
    points=[runtime.mission.gcs.pos]+stations
    assert len(stations)<=len(runtime.mission.uavs)//2
    assert all(np.linalg.norm(b-a)<runtime.transport.range for a,b in zip(points,points[1:]))


def test_hearing_old_relay_does_not_block_its_explicit_retirement_request():
    a,events,_=agent();a.route=(0,-1);a.route_at=10
    a.neighbors={2:{'seen':10,'pos':[30,0],'vel':[0,0],'role':'relay','state':'relay',
                    'request':{'old':2,'pos':[30,0],'created':5,'depart_by':99}},
                 3:{'seen':10,'pos':[40,0],'role':'relay','heard_relays':[2]}}
    a.tick(10)
    assert a.replacing==2
    assert any(e['event']=='replacement_dispatched' for e in events)


def test_isolated_relay_retreats_and_holds_after_stable_route_contact():
    a,events,_=agent()
    a.uav.pos=np.array([800.,0.])
    a.uav.assign_relay(np.array([1000.,0.]),0)
    a.offline_since=0
    a.tick(7)
    assert a.uav.state==UAVState.RELAY
    recovery_target=a.uav.relay_station_pos.copy()
    assert np.linalg.norm(recovery_target-a.home)>=3*a.uav.min_separation
    assert a.mode=='relay_recover'
    a.route=(0,-1);a.route_at=8;a.tick(8)
    assert np.array_equal(a.uav.relay_station_pos,recovery_target)  # One beacon is not stable reconnection.
    a.uav.pos=np.array([500.,0.]);a.route_at=10;a.tick(10)
    assert a.uav.state==UAVState.RELAY
    assert np.array_equal(a.uav.relay_station_pos,[500.,0.])
    assert not a.uav.waypoints
    assert any(e['event']=='relay_recovery_complete' for e in events)


def test_fixed_relay_ablation_does_not_gain_repositioning():
    a,events,_=agent();a.config['mode']='fixed'
    a.uav.assign_relay(np.array([1000.,0.]),0);a.offline_since=0
    a.tick(7)
    assert a.uav.state==UAVState.RELAY
    assert not any(e['event']=='relay_recovery_started' for e in events)


def test_relay_reposition_covers_waiting_task_without_adding_a_relay():
    from src.resilience.agent import Task
    a,events,_=agent();a.uav.id=1;a.fleet_size=8
    a.uav.pos=np.array([1140.,960.]);a.uav.assign_relay(a.uav.pos,0)
    a.home=np.array([150.,1000.]);a.route=(1,0,-1);a.route_at=180
    a.tasks={3:Task(3,1200,200,5)}
    live={0:{'seen':180,'pos':[620.,980.],'route':[0,-1]},
          3:{'seen':180,'pos':[1755.,936.],'route':[3,1,0,-1]}}
    a.reposition_relay(180,live)
    assert np.linalg.norm(a.uav.relay_station_pos-[1200,200])<=560
    assert all(np.linalg.norm(a.uav.relay_station_pos-n['pos'])<=665 for n in live.values())
    assert a.uav.role==UAVRole.RELAY
    assert any(e['event']=='relay_reposition' for e in events)
    station=a.uav.relay_station_pos.copy()
    a.reposition_relay(181,live)
    assert np.array_equal(a.uav.relay_station_pos,station)


def test_radio_isolated_scout_recovers_without_entering_charger_column():
    from src.resilience.runtime import Runtime
    from src.core.uav import UAVRole, UAVState
    import numpy as np
    runtime=Runtime('scenarios/earthquake_basic.yaml',seed=200)
    a=runtime.agents[5];u=a.uav
    u.role=UAVRole.SCOUT;u.state=UAVState.IDLE
    u.pos=np.array([400.,400.]);a.offline_since=0
    a.tick(20)
    assert a.mode=='recover' and u.state!=UAVState.RTL
    assert a.scout_recovery_target is not None
    assert np.linalg.norm(a.scout_recovery_target-a.home)>=3*u.min_separation
    for tick in range(500):u.update(.1,20+tick*.1,np.zeros(2))
    assert u.state!=UAVState.RECHARGE and u.altitude>=u.flight_altitude-1
    a.route=(u.id,-1);a.route_at=70;a.tick(70)
    assert a.scout_recovery_target is None


def test_planner_connects_clear_exact_endpoint_when_rounded_cell_is_blocked():
    from types import SimpleNamespace
    from src.resilience.planner import Planner
    import numpy as np
    obstacle=SimpleNamespace(center=np.array([50.,50.]),radius=4.)
    p=Planner(SimpleNamespace(width=150,height=150,obstacles=[obstacle]),resolution=25)
    start=np.array([0.,50.]);goal=np.array([60.1,50.])
    path=p.plan(start,goal)
    assert path and all(p.clear(a,b) for a,b in zip(path,path[1:]))
    assert np.array_equal(path[-1],goal)


def test_relay_does_not_reposition_for_work_already_under_a_live_lease():
    from src.resilience.agent import Task
    a,events,_=agent();a.uav.id=1;a.fleet_size=8
    a.uav.pos=np.array([1140.,960.]);a.uav.assign_relay(a.uav.pos,0)
    a.home=np.array([150.,1000.]);a.route=(1,0,-1);a.route_at=180
    a.tasks={3:Task(3,1200,200,5)}
    a.claims={3:{'owner':6,'until':187}}
    live={0:{'seen':180,'pos':[620.,980.],'route':[0,-1]},
          3:{'seen':180,'pos':[1755.,936.],'route':[3,1,0,-1]}}
    a.reposition_relay(180,live)
    assert np.array_equal(a.uav.relay_station_pos,[1140.,960.])
    assert not any(e['event']=='relay_reposition' for e in events)
