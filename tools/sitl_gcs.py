"""Software-only GCS heartbeat for the isolated local SITL gate.

Keeps PX4's GCS-presence checks enabled. Never arms or changes parameters.
Reference: https://mavlink.io/en/mavgen_python/ and /en/services/heartbeat.html
"""
import argparse
import json
import time
from importlib.metadata import version
from pymavlink import mavutil


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=14550)
    args = p.parse_args()
    link=mavutil.mavlink_connection(f'udpin:127.0.0.1:{args.port}',source_system=255,source_component=190)
    print(json.dumps({'event':'gcs_start','pymavlink':version('pymavlink'),'port':args.port}),flush=True)
    if link.wait_heartbeat(timeout=60) is None:raise SystemExit('No PX4 MAVLink heartbeat received')
    print(json.dumps({'event':'px4_heartbeat','system':link.target_system}),flush=True)
    last=-1
    while True:
        msg=link.recv_match(blocking=True,timeout=.2)
        if msg is not None and msg.get_type()=='STATUSTEXT':
            print(json.dumps({'event':'status_text','severity':msg.severity,'text':msg.text}),flush=True)
        now=time.monotonic()
        if now-last>=1:
            link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,mavutil.mavlink.MAV_STATE_ACTIVE)
            last=now

if __name__=='__main__':main()
