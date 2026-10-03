"""Measured-state runtime backend: no simulated motion or manufactured survey progress."""
import numpy as np
from src.core.uav import UAVState

class MeasuredBackend:
    def __init__(self,feedback,command,tolerance=2):
        self.feedback=feedback;self.command=command;self.tolerance=tolerance
        self.dwell={}
    def advance(self,u,dt,now):
        position,velocity,battery=self.feedback(u.id)
        if not np.isfinite([*position,*velocity]).all() or (battery is not None and not 0 <= battery <= 1):
            raise ValueError('Measured state must be finite with battery fraction in [0,1]')
        u.pos=np.array(position[:2]);u.altitude=float(position[2]);u.vel=np.array(velocity[:2])
        if battery is not None:u.battery.current_wh=float(battery)*u.battery.capacity_wh
        if u.state==UAVState.FAILED:return
        target=None
        if u.waypoints and u.waypoint_index<len(u.waypoints):
            target=u.waypoints[u.waypoint_index]
            if np.linalg.norm(target-u.pos)<self.tolerance:u.waypoint_index+=1
        elif u.state==UAVState.RELAY:target=u.relay_station_pos
        elif u.state in (UAVState.SCOUT,UAVState.RTL):target=u.target_pos
        if target is None:target=u.pos
        if hasattr(u,'motion_filter'):
            target=u.motion_filter(np.asarray(target),dt)
        altitude=u.flight_altitude
        self.command(u.id,[float(target[0]),float(target[1]),altitude])
        if u.state==UAVState.SCOUT and u.assigned_task_id is not None:
            near=np.linalg.norm(u.pos-u.true_target_pos)<self.tolerance and np.linalg.norm(velocity)<1 and abs(u.altitude-altitude)<self.tolerance
            key=(u.id,u.assigned_task_id)
            self.dwell[key]=self.dwell.get(key,0)+dt if near else 0
            if self.dwell[key]>=u.survey_time_s:
                u.tasks_completed.append(u.assigned_task_id);u.assigned_task_id=None
                u.state=UAVState.IDLE;u.target_pos=None;u.waypoints=[]
