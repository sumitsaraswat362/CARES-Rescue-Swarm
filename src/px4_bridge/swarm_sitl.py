"""Run the shared CARES policy against externally launched PX4 SITL vehicles.
Requires an explicit vehicle mapping (namespace, system ID, and local ENU origin).
No Gazebo or PX4 instance is installed or launched by this command.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .sitl_agent import enu_to_ned,ned_to_enu
from .measured import MeasuredBackend
from .health import FlightHealth
from .topics import topic_name
from src.resilience.runtime import Runtime


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scenario',required=True);p.add_argument('--config',default='config/swarm_config.yaml')
    p.add_argument('--vehicles',required=True);p.add_argument('--out',default='logs/sitl/swarm')
    p.add_argument('--timeout',type=float,default=300)
    args=p.parse_args()
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
    from px4_msgs.msg import OffboardControlMode,TrajectorySetpoint,VehicleCommand,VehicleLocalPosition,VehicleStatus,BatteryStatus
    mapping=json.loads(Path(args.vehicles).read_text())
    runtime=Runtime(args.scenario,args.config)
    if sorted(x['id'] for x in mapping)!=sorted(runtime.agents):raise ValueError('Map every configured UAV exactly once')
    if len({x['namespace'] for x in mapping})!=len(mapping):raise ValueError('Namespaces must be unique')
    class NodeBridge(Node):
        def __init__(self):
            super().__init__('cares_swarm_sitl')
            self.rows={x['id']:x for x in mapping};self.feedbacks={};self.targets={};self.batteries={}
            self.armed={};self.publishers_by_id={};self.started=time.monotonic();self.count=0;self.failed=False
            self.last_tick=None;self.landing=False;self.finished=False
            self.health=FlightHealth(self.rows)
            qos=QoSProfile(depth=10,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.TRANSIENT_LOCAL)
            for uid,row in self.rows.items():
                prefix=row['namespace'].rstrip('/')
                self.publishers_by_id[uid]=[self.create_publisher(cls,topic_name(prefix,'in',topic,cls),10) for cls,topic in
                    [(OffboardControlMode,'offboard_control_mode'),(TrajectorySetpoint,'trajectory_setpoint'),(VehicleCommand,'vehicle_command')]]
                self.create_subscription(VehicleLocalPosition,topic_name(prefix,'out','vehicle_local_position',VehicleLocalPosition),lambda msg,i=uid:self.observe(i,msg),qos)
                self.create_subscription(VehicleStatus,topic_name(prefix,'out','vehicle_status',VehicleStatus),lambda msg,i=uid:self.status(i,msg),qos)
                self.create_subscription(BatteryStatus,topic_name(prefix,'out','battery_status',BatteryStatus),lambda msg,i=uid:self.battery(i,msg),qos)
            self.backend=MeasuredBackend(self.feedback,lambda i,p:self.targets.update({i:p}))
            self.create_timer(.1,self.tick)
        def observe(self,i,msg):
            if msg.xy_valid and msg.z_valid and np.isfinite([msg.x,msg.y,msg.z,msg.vx,msg.vy,msg.vz]).all():
                pos=np.array(ned_to_enu([msg.x,msg.y,msg.z]))+np.array(self.rows[i]['origin_enu'])
                vel=ned_to_enu([msg.vx,msg.vy,msg.vz])
                self.feedbacks[i]=(pos,vel,time.monotonic())
        def status(self,i,msg):
            self.armed[i]=msg.arming_state==VehicleStatus.ARMING_STATE_ARMED
            self.health.observe(i,self.armed[i],msg.nav_state==VehicleStatus.NAVIGATION_STATE_OFFBOARD,time.monotonic())
        def battery(self,i,msg):
            if 0<=msg.remaining<=1:self.batteries[i]=msg.remaining
        def feedback(self,i):
            pos,vel,_=self.feedbacks[i];return pos,vel,self.batteries.get(i)
        def command(self,i,cmd,p1=0,p2=0):
            msg=VehicleCommand();msg.timestamp=self.get_clock().now().nanoseconds//1000;msg.command=cmd
            msg.param1=float(p1);msg.param2=float(p2);msg.target_system=self.rows[i]['system_id'];msg.target_component=1
            msg.source_system=255;msg.source_component=1;msg.from_external=True
            self.publishers_by_id[i][2].publish(msg)
        def tick(self):
            now=time.monotonic()
            fresh=len(self.feedbacks)==len(self.rows) and all(now-v[2]<1 for v in self.feedbacks.values())
            if now-self.started>args.timeout+20:
                self.failed=True;self.finished=True;return
            if now-self.started>args.timeout:self.failed=True;self.landing=True
            if self.last_tick is not None and not self.landing and not self.health.ready(now):
                self.failed=True;self.landing=True
            if not fresh:
                if any(self.armed.values()):self.failed=True;self.landing=True
                elif not self.landing:return
            if self.landing:
                self.health.begin_landing(now)
                for i in self.rows:self.command(i,VehicleCommand.VEHICLE_CMD_NAV_LAND)
                if self.health.landed(now):self.finished=True
                return
            # State is copied from the physics adapter before policies execute.
            for i,u in enumerate(runtime.mission.uavs):
                pos,vel,battery=self.feedback(i);u.pos=np.array(pos[:2]);u.altitude=float(pos[2]);u.vel=np.array(vel[:2])
                if battery is not None:u.battery.current_wh=battery*u.battery.capacity_wh
            for i,u in enumerate(runtime.mission.uavs):
                self.targets.setdefault(i,[float(u.pos[0]),float(u.pos[1]),min(u.max_altitude,30+u.id*10)])
            if self.health.ready(now):
                if self.last_tick is not None:runtime.mission.dt=min(.25,now-self.last_tick)
                self.last_tick=now
                runtime.step(self.backend)
            self.count+=1
            for i,pubs in self.publishers_by_id.items():
                control=OffboardControlMode();control.timestamp=self.get_clock().now().nanoseconds//1000;control.position=True
                pubs[0].publish(control)
                sp=TrajectorySetpoint();sp.timestamp=control.timestamp
                sp.position=enu_to_ned(np.array(self.targets[i])-np.array(self.rows[i]['origin_enu']));sp.yaw=0.;pubs[1].publish(sp)
                if self.count>=20 and self.count%20==0 and not self.health.ready(now):
                    self.command(i,VehicleCommand.VEHICLE_CMD_DO_SET_MODE,1,6)
                    self.command(i,VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,1)
            if not runtime.mission.running:self.landing=True
    rclpy.init();node=NodeBridge()
    try:
        while rclpy.ok() and not node.finished:rclpy.spin_once(node,timeout_sec=.1)
    finally:
        runtime.provenance['backend']='px4-measured'
        runtime.provenance['battery_feedback_ids']=sorted(node.batteries)
        runtime.provenance['vehicle_mapping']=mapping
        passed=node.finished and not node.failed and not runtime.mission.running and node.health.landed(time.monotonic())
        runtime.provenance['flight_gate_passed']=passed
        runtime.provenance['measured_engaged_ids']=sorted(node.health.engaged)
        runtime.save(args.out);node.destroy_node();rclpy.shutdown()
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
