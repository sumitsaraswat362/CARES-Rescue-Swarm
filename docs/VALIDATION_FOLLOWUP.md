# Validation follow-up — 2026-09-17

## Completed

- Fixed the WebSocket server to run one simulation clock, irrespective of viewer
  count. Opening/reconnecting a tab preserves the mission; explicit reset retains
  the selected scenario and clears narration cursors.
- Exercised two actual ASGI WebSocket sessions with shared failure, reset and pause
  commands, reconnect, and static dashboard HTTP delivery.
- Corrected the end-screen connectivity field, replaced the unsupported Fiedler
  display with measured per-hop delivery, and distinguished acquisition from GCS
  delivery in labels. Moved delivery evidence into the existing log panel to avoid
  its separate fixed overlay covering controls.
- Added measured flight-status gates: every vehicle must be observed armed in
  offboard mode; mission progress waits for engagement; landing success requires
  fresh post-landing disarm telemetry from every vehicle. Stale/missing status,
  offboard loss, timeout and interrupted execution cannot count as success.
- Rejected nonfinite position updates and included vertical speed in survey dwell.
- Local suite: 27 tests passed. Python compilation and JavaScript syntax passed.

## Still blocked, not passed

**Visual browser QA:** the available remote browser rejected the local dashboard
URL with `net::ERR_BLOCKED_BY_CLIENT`. No desktop/mobile screenshot inspection was
completed. ASGI integration and syntax checks are not visual QA. The dashboard
still needs inspection in a browser that can reach its server, including WebGL
rendering, responsive layout, overlays and reconnect behavior.

**Live flight:** this workspace has none of `ros2`, `gz`, `gazebo`, `px4`, or
`docker`, and neither `rclpy` nor `px4_msgs` is importable. No PX4/Gazebo flight was
run. A configured SITL host with the matching ROS message workspace and an explicit
vehicle-origin mapping is required to execute `docs/SITL.md`. Retain raw measured
telemetry, simulator versions and video for the takeoff/survey/relay-loss/recovery/
landing gates. The software radio and logical failure remain models, not measured
RF behavior or real motor-failure evidence.

Keep the PR draft and flight-validation claims pending until these gates execute.
