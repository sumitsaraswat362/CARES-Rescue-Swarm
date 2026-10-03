"""PX4 ROS 2 position adapter. Importable without ROS; ROS required only to run.
See docs/SITL.md for frames, prerequisites, and the unexecuted integration gate.
"""
import argparse
import json
import math
import time
from pathlib import Path
from .health import FlightHealth
from .topics import topic_name


def enu_to_ned(position):
    east,north,up=map(float,position)
    if not all(math.isfinite(x) for x in (east,north,up)):raise ValueError('Non-finite setpoint')
    return [north,east,-up]


def ned_to_enu(position):
    north,east,down=map(float,position)
    return [east,north,-down]


class FlightSession:
    """Measured-state waypoint progression; reusable with a policy's waypoint stream."""
    def __init__(self,waypoints,tolerance=2.,stale_s=1.,dwell_s=0.):
        if not waypoints:raise ValueError('At least one ENU waypoint is required')
        for point in waypoints:enu_to_ned(point)
        self.waypoints=waypoints;self.index=0;self.position=None;self.received_at=-math.inf
        self.tolerance=tolerance;self.stale_s=stale_s;self.complete=False
        self.dwell_s=dwell_s;self.dwell_start=-math.inf
    def observe(self,ned,now):
        if not all(math.isfinite(float(x)) for x in ned):
            return
        self.position=ned_to_enu(ned);self.received_at=now
    def target(self,now):
        if now-self.received_at>self.stale_s:return None
        target=self.waypoints[self.index]
        if math.dist(self.position,target)<=self.tolerance:
            if self.dwell_start==-math.inf:self.dwell_start=now
            if now-self.dwell_start>=self.dwell_s:
                if self.index+1<len(self.waypoints):
                    self.index+=1;self.dwell_start=-math.inf
                else:self.complete=True
        else:
            self.dwell_start=-math.inf
        return enu_to_ned(self.waypoints[self.index])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--namespace',default='')
    p.add_argument('--system-id',type=int,default=1)
    p.add_argument('--waypoints',required=True,help='JSON array of local ENU waypoints in meters')
    p.add_argument('--out',default='logs/sitl/flight.jsonl')
    p.add_argument('--timeout',type=float,default=180.)
    p.add_argument('--dwell',type=float,default=0.)
    args=p.parse_args()
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
    from px4_msgs.msg import OffboardControlMode,TrajectorySetpoint,VehicleCommand,VehicleLocalPosition,VehicleStatus,VehicleCommandAck
    session=FlightSession(json.loads(Path(args.waypoints).read_text()),dwell_s=args.dwell)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    class Bridge(Node):
        def __init__(self):
            super().__init__('cares_offboard')
            self.prefix=args.namespace.rstrip('/')
            qos=QoSProfile(depth=10,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.control=self.create_publisher(OffboardControlMode,topic_name(self.prefix,'in','offboard_control_mode',OffboardControlMode),10)
            self.setpoint=self.create_publisher(TrajectorySetpoint,topic_name(self.prefix,'in','trajectory_setpoint',TrajectorySetpoint),10)
            self.command=self.create_publisher(VehicleCommand,topic_name(self.prefix,'in','vehicle_command',VehicleCommand),10)
            self.create_subscription(VehicleLocalPosition,topic_name(self.prefix,'out','vehicle_local_position',VehicleLocalPosition),self.position,qos)
            self.create_subscription(VehicleStatus,topic_name(self.prefix,'out','vehicle_status',VehicleStatus),self.status,qos)
            self.create_subscription(VehicleCommandAck,topic_name(self.prefix,'out','vehicle_command_ack',VehicleCommandAck),self.ack,qos)
            self.armed=False;self.offboard=False;self.count=0;self.last_command=-math.inf
            self.health=FlightHealth([args.system_id])
            self.started=time.monotonic();self.finished=False;self.failed=False;self.landing=False
            self.log=out.open('w');self.create_timer(.1,self.tick)
        def stamp(self):return self.get_clock().now().nanoseconds//1000
        def record(self,**data):self.log.write(json.dumps({'monotonic':time.monotonic(),**data})+'\n');self.log.flush()
        def position(self,msg):
            if msg.xy_valid and msg.z_valid:
                session.observe([msg.x,msg.y,msg.z],time.monotonic())
                self.record(event='position',enu=session.position)
        def status(self,msg):
            self.armed=msg.arming_state==VehicleStatus.ARMING_STATE_ARMED
            self.offboard=msg.nav_state==VehicleStatus.NAVIGATION_STATE_OFFBOARD
            self.health.observe(args.system_id,self.armed,self.offboard,time.monotonic())
            self.record(event='status',armed=self.armed,offboard=self.offboard)
            if self.landing and self.health.landed(time.monotonic()):self.finished=True
        def ack(self,msg):self.record(event='command_ack',command=msg.command,result=msg.result)
        def send_command(self,command,p1=0.,p2=0.):
            msg=VehicleCommand();msg.timestamp=self.stamp();msg.command=command
            msg.param1=float(p1);msg.param2=float(p2);msg.target_system=args.system_id;msg.target_component=1
            msg.source_system=255;msg.source_component=1;msg.from_external=True;self.command.publish(msg)
        def tick(self):
            now=time.monotonic()
            # Stream the first target during warmup, but only progress after measured engagement.
            target=(session.target(now) if self.health.ready(now) else
                    enu_to_ned(session.waypoints[session.index]) if now-session.received_at<=session.stale_s else None)
            if self.health.engaged and not self.landing and not self.health.ready(now):self.failed=True
            if now-self.started>args.timeout+20:
                self.failed=True;self.finished=True;return
            if now-self.started>args.timeout:self.failed=True
            if self.failed or self.landing:
                self.health.begin_landing(now)
                if now-self.last_command>2:
                    self.send_command(VehicleCommand.VEHICLE_CMD_NAV_LAND);self.last_command=now;self.landing=True
                if self.health.landed(now):self.finished=True
                return
            if target is None:
                if self.armed:self.failed=True;self.record(event='stale_state')
                return
            control=OffboardControlMode();control.timestamp=self.stamp();control.position=True;self.control.publish(control)
            sp=TrajectorySetpoint();sp.timestamp=self.stamp();sp.position=target;sp.yaw=0.;self.setpoint.publish(sp)
            self.count+=1
            if self.count>=20 and now-self.last_command>2 and (not self.armed or not self.offboard):
                self.send_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE,1,6)
                self.send_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,1)
                self.last_command=now
            if session.complete and self.armed:
                self.record(event='waypoints_complete');self.landing=True
    rclpy.init();node=Bridge()
    try:
        while rclpy.ok() and not node.finished:rclpy.spin_once(node,timeout_sec=.1)
    finally:
        passed=session.complete and not node.failed and node.health.landed(time.monotonic())
        node.record(event='result',passed=passed)
        node.log.close();node.destroy_node();rclpy.shutdown()
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
