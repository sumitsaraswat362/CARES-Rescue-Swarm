"""Launch isolated PX4/Gazebo SITL and retain measured flight evidence.

This runs a software simulator only. Requires a built PX4 tree, sourced ROS and
px4_msgs, Gazebo, and MicroXRCEAgent. A nonzero process result is never a flight pass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--px4', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    px4 = Path(args.px4).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (px4 / 'build/px4_sitl_default/bin/px4').is_file():
        raise SystemExit('PX4 SITL executable is missing; no flight attempted')
    waypoints = out / 'waypoints.json'
    waypoints.write_text(json.dumps([[0, 0, 5], [10, 0, 5], [0, 0, 5]]))
    result = {'passed': False, 'scope': 'three-iteration cold start, offboard waypoint flight with 5s survey dwell',
              'waypoints_sha256': hashlib.sha256(waypoints.read_bytes()).hexdigest(),
              'flights': []}
    
    try:
        # Container bind mounts can have a different UID from the checkout action.
        # Trust only these explicit task checkouts for read-only provenance queries.
        for key, checkout in [('px4_commit',px4),('code_commit',Path.cwd().resolve())]:
            result[key]=subprocess.check_output(['git','-c',f'safe.directory={checkout}',
                                                '-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
        
        all_passed = True
        for attempt in range(1, 4):
            processes, logs = [], []
            flight_result = {'attempt': attempt, 'passed': False}
            try:
                for name, command, directory, environment in [
                    ('gcs', [sys.executable, '-u', 'tools/sitl_gcs.py'], str(Path.cwd()), os.environ.copy()),
                    ('xrce', ['MicroXRCEAgent', 'udp4', '-p', '8888'], None, os.environ.copy()),
                    ('px4', [str(px4 / 'build/px4_sitl_default/bin/px4'), '-i', '0', '-d', str(px4 / 'build/px4_sitl_default/etc')], str(px4 / 'build/px4_sitl_default'), {**os.environ, 'HEADLESS': '1', 'PX4_SIMULATOR': 'sihsim', 'PX4_SYS_AUTOSTART': '10016', 'PX4_UXRCE_DDS_PORT': '8888'})]:
                    log = (out / f'{name}_{attempt}.log').open('w')
                    logs.append(log)
                    processes.append(subprocess.Popen(command, cwd=directory, env=environment,
                                                        stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                                        start_new_session=True, text=True))
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError(f'Simulator or DDS agent exited before readiness on attempt {attempt}')
                    if 'Startup script returned successfully' in (out / f'px4_{attempt}.log').read_text():
                        break
                    time.sleep(.5)
                else:
                    raise RuntimeError(f'PX4 startup readiness timed out on attempt {attempt}')
                
                # Software-only offboard test: disable hardware preflight checks
                # that SIH mode does not emulate (no real baro, mag, ESC).
                px4_stdin = processes[-1].stdin
                for param_cmd in [
                    'param set COM_RCL_EXCEPT 4',   # no RC required in software test
                    'param set SYS_HAS_MAG 0',       # no magnetometer in SIH
                    'param set EKF2_BARO_CTRL 0',    # disable baro EKF
                    'param set EKF2_MAG_TYPE 5',     # no-mag EKF fusion
                    'param set COM_ARM_CHK_ESCS 0',  # no ESC preflight
                    'param set COM_ARM_MAG_STR 0',   # no mag strength check
                    'param set CBRK_IO_SAFETY 22027',# bypass IO safety arming check
                    'param set COM_PREARM_MODE 0',   # disable prearm mode requirement
                ]:
                    try:
                        px4_stdin.write(param_cmd + '\n')
                        px4_stdin.flush()
                    except Exception:
                        pass
                time.sleep(1.0)  # let params settle
                with (out / f'bridge_{attempt}.log').open('w') as log:
                    flight = subprocess.run([sys.executable, 'tools/mavlink_flight.py',
                                             '--waypoints', str(waypoints), '--out', str(out / f'flight_{attempt}.jsonl'),
                                             '--timeout', '180', '--dwell', '5'], stdout=log, stderr=subprocess.STDOUT, timeout=220)
                flight_result['bridge_exit_code'] = flight.returncode
                records = [json.loads(line) for line in (out / f'flight_{attempt}.jsonl').read_text().splitlines()]
                flight_result['position_messages'] = sum(r['event'] == 'position' for r in records)
                flight_result['status_messages'] = sum(r['event'] == 'status' for r in records)
                flight_result['command_ack_messages'] = sum(r['event'] == 'command_ack' for r in records)
                flight_result['passed'] = (flight.returncode == 0 and bool(records) and records[-1].get('passed') is True
                                           and flight_result['position_messages'] > 0 and flight_result['status_messages'] > 0
                                           and flight_result['command_ack_messages'] > 0)
            except Exception as e:
                flight_result['error'] = str(e)
            finally:
                for p in reversed(processes):
                    if p.poll() is None:
                        os.killpg(p.pid, signal.SIGTERM)
                        try:
                            p.wait(timeout=8)
                        except subprocess.TimeoutExpired:
                            os.killpg(p.pid, signal.SIGKILL)
                            p.wait(timeout=8)
                for log in logs:
                    log.close()
            
            result['flights'].append(flight_result)
            if not flight_result['passed']:
                all_passed = False
                break
        
        result['passed'] = all_passed
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait(timeout=8)
        for log in logs:
            log.close()
        (out / 'gate_result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
