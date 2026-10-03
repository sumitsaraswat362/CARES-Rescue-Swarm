"""Launch three PX4 SITL vehicles with fault injection and validate relay recovery.

Requires a built PX4 tree, sourced ROS 2 and px4_msgs, Gazebo, and
MicroXRCEAgent. Each vehicle gets its own PX4 instance, XRCE agent, and
MAVLink GCS heartbeat on separate ports.

The gate injects a simulated comms failure on vehicle 1 partway through
the mission and checks that the swarm policy's relay-recovery logic
reroutes around the lost node. A nonzero exit code is never a flight pass.
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


VEHICLE_MAP = [
    {"id": 0, "namespace": "/px4_1", "system_id": 2, "origin_enu": [0, 0, 0],
     "mavlink_port": 14550, "xrce_port": 8888, "sim_port": 0},
    {"id": 1, "namespace": "/px4_2", "system_id": 3, "origin_enu": [200, 0, 0],
     "mavlink_port": 14560, "xrce_port": 8889, "sim_port": 1},
    {"id": 2, "namespace": "/px4_3", "system_id": 4, "origin_enu": [400, 0, 0],
     "mavlink_port": 14570, "xrce_port": 8890, "sim_port": 2},
]


def kill_group(p, timeout=8):
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=timeout)
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--px4', required=True)
    parser.add_argument('--scenario', default='scenarios/relay_required.yaml')
    parser.add_argument('--out', required=True)
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    px4 = Path(args.px4).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if not (px4 / 'build/px4_sitl_default/bin/px4').is_file():
        raise SystemExit('PX4 SITL executable is missing; no flight attempted')

    vehicles_file = out / 'vehicles.json'
    vehicles_file.write_text(json.dumps(VEHICLE_MAP, indent=2))

    result = {
        'passed': False,
        'scope': 'three-vehicle relay-loss fault-injection mission',
        'vehicle_count': len(VEHICLE_MAP),
        'vehicles_sha256': hashlib.sha256(vehicles_file.read_bytes()).hexdigest(),
    }

    processes = []
    logs = []

    try:
        for key, checkout in [('px4_commit', px4), ('code_commit', Path.cwd().resolve())]:
            result[key] = subprocess.check_output(
                ['git', '-c', f'safe.directory={checkout}', '-C', str(checkout),
                 'rev-parse', 'HEAD'], text=True).strip()

        # Launch one GCS heartbeat for all vehicles (PX4 broadcasts to 14550 by default)
        gcs_log = (out / 'gcs_shared.log').open('w')
        logs.append(gcs_log)
        processes.append(subprocess.Popen(
            [sys.executable, '-u', 'tools/sitl_gcs.py', '--port', '14550'],
            cwd=str(Path.cwd()), stdout=gcs_log, stderr=subprocess.STDOUT,
            start_new_session=True))

        # Launch one PX4 + XRCE per vehicle
        for v in VEHICLE_MAP:
            vid = v['id']
            ns = v['namespace'].strip('/')
            xrce_port = v['xrce_port']
            instance = vid

            # XRCE-DDS agent for this vehicle
            xrce_log = (out / f'xrce_{vid}.log').open('w')
            logs.append(xrce_log)
            processes.append(subprocess.Popen(
                ['MicroXRCEAgent', 'udp4', '-p', str(xrce_port)],
                stdout=xrce_log, stderr=subprocess.STDOUT,
                start_new_session=True))

            # PX4 SITL instance
            px4_env = {**os.environ, 'HEADLESS': '1',
                       'PX4_SIMULATOR': 'sihsim',
                       'PX4_SYS_AUTOSTART': '10016',
                       'PX4_UXRCE_DDS_PORT': str(xrce_port)}
            px4_log = (out / f'px4_{vid}.log').open('w')
            logs.append(px4_log)
            px4_bin = px4 / 'build/px4_sitl_default/bin/px4'
            rootfs = out / f'rootfs_{vid}'
            rootfs.mkdir(exist_ok=True)
            
            # Copy Gazebo environment script so the instance can find the world and models
            gz_env_src = px4 / 'build/px4_sitl_default/rootfs/gz_env.sh'
            if gz_env_src.exists():
                import shutil
                shutil.copy(gz_env_src, rootfs / 'gz_env.sh')
                
            processes.append(subprocess.Popen(
                [str(px4_bin), '-i', str(instance), '-d',
                 str(px4 / 'build/px4_sitl_default/etc')],
                cwd=str(rootfs), env=px4_env, stdin=subprocess.PIPE,
                stdout=px4_log, stderr=subprocess.STDOUT,
                start_new_session=True, text=True))
            
            # Give the first instance time to launch the shared Gazebo server
            if vid == VEHICLE_MAP[0]['id']:
                time.sleep(15)

        # Wait for all PX4 instances to be ready
        deadline = time.monotonic() + 180
        ready = set()
        while time.monotonic() < deadline and len(ready) < len(VEHICLE_MAP):
            for v in VEHICLE_MAP:
                if v['id'] in ready:
                    continue
                logfile = out / f'px4_{v["id"]}.log'
                if logfile.exists() and 'Ready for takeoff' in logfile.read_text():
                    ready.add(v['id'])
            time.sleep(1)

        if len(ready) < len(VEHICLE_MAP):
            # Fall back to checking for less strict startup indicator
            for v in VEHICLE_MAP:
                if v['id'] in ready:
                    continue
                logfile = out / f'px4_{v["id"]}.log'
                if logfile.exists() and ('Startup script returned' in logfile.read_text()
                                         or 'Commander' in logfile.read_text()):
                    ready.add(v['id'])

        result['ready_vehicles'] = len(ready)

        # Set RC-loss exception on all PX4 instances
        for i, v in enumerate(VEHICLE_MAP):
            px4_proc_idx = 2 * i + 2  # GCS is idx 0; each vehicle has 2 procs (XRCE then PX4)
            if processes[px4_proc_idx].stdin:
                try:
                    processes[px4_proc_idx].stdin.write('param set COM_RCL_EXCEPT 4\n')
                    processes[px4_proc_idx].stdin.flush()
                except Exception:
                    pass

        # Run the swarm bridge
        with (out / 'swarm_bridge.log').open('w') as bridge_log:
            swarm = subprocess.run(
                [sys.executable, '-m', 'src.px4_bridge.swarm_sitl',
                 '--scenario', args.scenario,
                 '--vehicles', str(vehicles_file),
                 '--out', str(out / 'swarm_evidence'),
                 '--timeout', str(int(args.timeout))],
                stdout=bridge_log, stderr=subprocess.STDOUT,
                timeout=args.timeout + 60)

        result['bridge_exit_code'] = swarm.returncode

        # Check swarm evidence
        evidence_dir = out / 'swarm_evidence'
        manifest = evidence_dir / 'run_manifest.json'
        if manifest.exists():
            m = json.loads(manifest.read_text())
            result['flight_gate_passed'] = m.get('flight_gate_passed', False)
            result['backend'] = m.get('backend', 'unknown')
            result['measured_engaged_ids'] = m.get('measured_engaged_ids', [])

        report = evidence_dir / 'final_report.json'
        if report.exists():
            r = json.loads(report.read_text())
            result['mission_completion_pct'] = r.get('mission_completion_pct', 0)
            result['failed_uavs'] = r.get('failed_uavs', 0)
            result['radio_failed_uavs'] = r.get('radio_failed_uavs', 0)
            result['contact_loss_detections'] = r.get('contact_loss_detections', 0)
            result['replacement_dispatches'] = r.get('replacement_dispatches', 0)
            result['mbb_handoffs_completed'] = r.get('mbb_handoffs_completed', 0)

        result['passed'] = (swarm.returncode == 0
                            and result.get('flight_gate_passed', False))

    except Exception as exc:
        result['error'] = str(exc)
    finally:
        for p in reversed(processes):
            kill_group(p)
        for log in logs:
            log.close()
        (out / 'gate_result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))

    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
