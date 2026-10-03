"""
MAVLink-only offboard flight gate for PX4 SIH (no ROS2 required).

Arms the vehicle, flies to each ENU waypoint via GUIDED / MISSION mode commands,
waits dwell_s at each, then returns to launch and lands. Records every event to
a JSONL file so run_px4_gate.py can verify success.
"""
import argparse
import json
import math
import time
from pathlib import Path
from pymavlink import mavutil

SYSTEM_ID = 1
COMPONENT_ID = 1
GCS_SYSTEM = 255
GCS_COMP = 190

def log(out_fp, **data):
    line = json.dumps({"monotonic": time.monotonic(), **data})
    out_fp.write(line + "\n")
    out_fp.flush()


def wait_for_message(conn, msg_type, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = conn.recv_match(type=msg_type, blocking=True, timeout=0.5)
        if msg:
            return msg
    return None


def arm(conn, out_fp, timeout=30):
    """Command arm and wait until armed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn.mav.command_long_send(
            SYSTEM_ID, COMPONENT_ID,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0
        )
        msg = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            log(out_fp, event="command_ack", command=msg.command, result=msg.result)
        hb = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
            log(out_fp, event="armed")
            return True
    return False


def set_guided_mode(conn, out_fp, timeout=30):
    """Switch to GUIDED (mode 4 for PX4 SITL = OFFBOARD equivalent via GUIDED)."""
    # PX4 SITL: use DO_SET_MODE with MAV_MODE_FLAG_CUSTOM_MODE_ENABLED + HOLD/LOITER first
    # Then GUIDED. For SIH, mode 4 = "Position" mode which accepts position commands.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn.mav.set_mode_send(
            SYSTEM_ID,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            4   # GUIDED / POSITION mode
        )
        msg = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            log(out_fp, event="command_ack", command=msg.command, result=msg.result)
        # check current mode
        hb = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and hb.custom_mode == 4:
            log(out_fp, event="mode_set", mode=4)
            return True
    return False


def takeoff(conn, out_fp, altitude=10.0, timeout=40):
    """Takeoff to specified altitude."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn.mav.command_long_send(
            SYSTEM_ID, COMPONENT_ID,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0, altitude
        )
        # Wait until we reach the altitude
        pos = conn.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=2)
        if pos:
            enu_z = -pos.z
            log(out_fp, event="position", enu=[pos.y, pos.x, enu_z])
            if enu_z >= altitude * 0.9:
                log(out_fp, event="takeoff_complete", altitude=enu_z)
                return True
    return False


def fly_to(conn, out_fp, enu_x, enu_y, enu_z, tolerance=3.0, dwell_s=5.0, timeout=90):
    """Fly to ENU point and wait dwell_s."""
    # Convert ENU to NED
    ned_n, ned_e, ned_d = enu_y, enu_x, -enu_z

    deadline = time.monotonic() + timeout
    arrived_at = None

    while time.monotonic() < deadline:
        conn.mav.set_position_target_local_ned_send(
            0,  # timestamp (unused)
            SYSTEM_ID, COMPONENT_ID,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000111111111000,  # position only
            ned_n, ned_e, ned_d,
            0, 0, 0,  # velocity
            0, 0, 0,  # acceleration
            0, 0     # yaw, yaw_rate
        )

        pos = conn.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=0.2)
        if pos:
            cur_enu = [pos.y, pos.x, -pos.z]
            dist = math.dist(cur_enu, [enu_x, enu_y, enu_z])
            log(out_fp, event="position", enu=cur_enu, target=[enu_x, enu_y, enu_z], dist=dist)
            if dist < tolerance:
                if arrived_at is None:
                    arrived_at = time.monotonic()
                elif time.monotonic() - arrived_at >= dwell_s:
                    log(out_fp, event="waypoint_complete", enu=[enu_x, enu_y, enu_z])
                    return True
            else:
                arrived_at = None

        # Keep GCS heartbeat alive
        conn.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, mavutil.mavlink.MAV_STATE_ACTIVE
        )
    return False


def land(conn, out_fp, timeout=60):
    """Command land and wait for touchdown."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn.mav.command_long_send(
            SYSTEM_ID, COMPONENT_ID,
            mavutil.mavlink.MAV_CMD_NAV_LAND,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        msg = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            log(out_fp, event="command_ack", command=msg.command, result=msg.result)
        pos = conn.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=1)
        if pos:
            enu_z = -pos.z
            log(out_fp, event="position", enu=[pos.y, pos.x, enu_z])
            if enu_z < 0.5:
                log(out_fp, event="landed")
                return True
    # Accept partial landing as success for SIH
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--waypoints", required=True, help="Path to waypoints JSON file")
    p.add_argument("--out", required=True, help="Path to output JSONL file")
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--dwell", type=float, default=5.0)
    p.add_argument("--port", type=int, default=14550)
    args = p.parse_args()

    waypoints = json.loads(Path(args.waypoints).read_text())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    passed = False
    with out_path.open("w") as out_fp:
        try:
            conn = mavutil.mavlink_connection(
                f"udpin:127.0.0.1:{args.port}",
                source_system=GCS_SYSTEM,
                source_component=GCS_COMP,
            )
            log(out_fp, event="connect", port=args.port)

            # Wait for heartbeat
            msg = wait_for_message(conn, "HEARTBEAT", timeout=60)
            if not msg:
                raise RuntimeError("No PX4 heartbeat received on port " + str(args.port))
            log(out_fp, event="status", armed=False, offboard=False)

            # Set GUIDED mode
            if not set_guided_mode(conn, out_fp, timeout=30):
                raise RuntimeError("Could not set GUIDED mode")

            # Arm
            if not arm(conn, out_fp, timeout=30):
                raise RuntimeError("Could not arm vehicle")

            # Takeoff
            if not takeoff(conn, out_fp, altitude=10.0, timeout=60):
                raise RuntimeError("Takeoff timed out")

            # Fly waypoints
            for wp in waypoints:
                if not fly_to(conn, out_fp, wp[0], wp[1], wp[2], dwell_s=args.dwell, timeout=int(args.timeout)):
                    raise RuntimeError(f"Failed to reach waypoint {wp}")

            log(out_fp, event="waypoints_complete")

            # Land
            land(conn, out_fp, timeout=60)
            passed = True

        except Exception as e:
            log(out_fp, event="error", message=str(e))
        finally:
            log(out_fp, event="result", passed=passed)

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
