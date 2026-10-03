# PX4 integration gate

Status: **three-iteration cold-start flight with 5 s survey dwell passed in CI**
(commit `f5d63f0`). Three-vehicle relay-loss fault-injection mission CI job added
and pending first execution.

## Gate architecture

The PX4 integration consists of two independent CI jobs:

| Job | Scope | Gate |
|-----|-------|------|
| `single-vehicle` | 3× cold start, waypoint flight, 5 s survey dwell | All 3 flights pass with measured position, armed/offboard status, and post-route landing |
| `swarm-fault-injection` | 3 PX4 vehicles, relay-required scenario, comms failure injected on vehicle 1 | Swarm policy detects contact loss, dispatches replacement relay, completes mission |

Both jobs run inside `ros:humble-ros-base-jammy` with PX4 Autopilot
(`6ea3539`), `px4_msgs` (`392e831`), and Micro-XRCE-DDS (`7362281`).

## Measured flight result (single vehicle)

GitHub Actions run 35553416694 executed a single-vehicle offboard waypoint
flight inside the PX4 SITL + ROS 2 environment. The gate result:

```json
{"passed":true,"bridge_exit_code":0,"position_messages":2279,"status_messages":54,"command_ack_messages":9,"scope":"one-vehicle offboard waypoint flight; no survey/radio recovery claim"}
```

Artifact 10618968144 retains the full recording. An independently published
auditor (run 35572863892) checked ordered measured positions within 2 m, fresh
armed/offboard status, post-route disarm and a contemporaneous near-ground pose.
It passed with an empty error list; its result is in
`validation/px4_independent_audit.json`. Final horizontal offset was about
2.64 m — precision landing is not demonstrated. Earlier failed attempts remain
part of the engineering record.

The updated gate now runs **three sequential cold starts** — the entire PX4 +
Gazebo + XRCE stack is launched, the flight is executed with a **5-second
survey dwell** at the target waypoint, and the stack is torn down. This repeats
3 times, and the gate only passes if all 3 iterations succeed.

## Survey dwell implementation

The `FlightSession` class in `src/px4_bridge/sitl_agent.py` now tracks
continuous dwell time at each waypoint:

1. When the measured position is within tolerance of the target, a dwell timer
   starts.
2. The waypoint only advances after the drone has been stationary within
   tolerance for `dwell_s` seconds (default: 5 s in the gate).
3. If the drone drifts out of tolerance, the timer resets.
4. This is real PX4 hover, not simulated — the position is read from
   `VehicleLocalPosition` and the drone must physically maintain station.

## Three-vehicle swarm adapter

`python -m src.px4_bridge.swarm_sitl --scenario scenarios/relay_required.yaml --vehicles vehicles.json`

`vehicles.json` is an array with one entry for every configured UAV:

```json
[
  {"id":0,"namespace":"/px4_1","system_id":2,"origin_enu":[0,0,0]},
  {"id":1,"namespace":"/px4_2","system_id":3,"origin_enu":[200,0,0]},
  {"id":2,"namespace":"/px4_3","system_id":4,"origin_enu":[400,0,0]}
]
```

Every ID, namespace, system ID and spawn origin must match the launched
simulator. Local NED feedback is converted to global ENU using the supplied
origin, and commands reverse that transform.

The measured backend uses the same Agent and transport as the lightweight
runtime. It derives survey progress from measured position, altitude, speed
and dwell, without calling simulated UAV motion. The radio remains a software
model using measured poses. Battery feedback is used when available.

## Three-vehicle fault-injection gate

`tools/run_px4_swarm_gate.py` launches:
- 3 PX4 SITL instances on separate UDP ports
- 3 Micro-XRCE-DDS agents (ports 8888–8890)
- 3 MAVLink GCS heartbeats (ports 14550–14570)

It then runs the full CARES swarm policy (`swarm_sitl.py`) against
`scenarios/relay_required.yaml`. The scenario includes a fault injection
that disables comms on vehicle 1 mid-flight. The gate verifies:

- All 3 vehicles reach armed + offboard
- The policy detects contact loss and dispatches a replacement
- The mission completes with measured relay recovery
- All vehicles land safely

This is not hardware or RF field validation. This is real PX4 physics with
real ROS 2 message passing and real Gazebo kinematics.

## Development container note

The development container does not contain ROS 2, PX4 or Gazebo; CI runs in a
Docker environment that installs them. Do not describe local development as
flight validated. The bridge's own `passed` flag alone is not independent
verification — the separate auditor above is the verification step.

The bridge follows PX4's official ROS 2 offboard interface:
https://docs.px4.io/main/en/ros2/offboard_control
