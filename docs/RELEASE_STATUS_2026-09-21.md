# CARES release status — 21 September 2026

This is an interim evidence report, not release acceptance or a competitor ranking.

## Published candidate

PR #5 remains a draft. The repaired runtime was published at
`791dce5b9aafd5dac538f517e89c164d74423466`; runtime SHA-256 is
`762f2ca19fffca6a0ad17bfba4492b09978953dda3441e80bf4f42dcb7198461`.
The following documentation/audit commit does not alter that runtime.
The main branch has not been changed by this publication.

## Individually verified results

- Local complete pytest run: `91 passed, 2 warnings in 8.19s`. Warnings concern
  Starlette/httpx and AnyIO deprecations. Unit success is not flight certification.
- Seven full regression runs have `evidence_consistent: true`, `safety_passed: true`,
  and empty error lists in `validation/final_regression_runs.json`.
- Basic burst seeds 400/401 delivered 5/5 tasks, with operational connectivity
  95.0166666666661% and 92.64999999999917%, respectively.
- Tier 3 seed 200 delivered 8/16; all six scripted disturbances fired. Three aircraft
  permanently failed, two suffered radio faults, and one suffered a battery fault.
  Six disturbances do not mean six dead aircraft.
- Tier 2 seed 227 completed, delivered 10/16, and fired all four disturbances.
- Hard seed 308 completed and delivered 9/16. These last two inputs had timed out
  in the old batch; their new completion is a regression result, not universal proof
  that no future input can time out.
- Relay rotation seed 100 delivered 2/2 with one recorded handoff. Analytic environment
  seed 100 delivered 2/2 with 149 mapped grid cells (14,900 square metres estimated).
- None of these seven runs had audited separation, geofence, depleted-battery,
  obstacle-penetration or terrain-penetration violations. Finite observations are
  not a formal safety guarantee.

## Qualification: rejected history and new pending evidence

Original run 35534036901 attempted 600 paired missions: 598 completed, 538 passed
independent audit, 60 candidate missions violated separation, and two candidate
processes timed out. All 300 reference runs passed. The candidate also failed the
basic burst connectivity non-inferiority gate. The complete rejected records remain
in `validation/qualification_v1_runs.json` and its acceptance/summary companions.

Repairs address unnecessary scout landings at an occupied charger, blocked rounded
A* endpoints, and relay movement toward already leased tasks. General scheduling
of simultaneous energy-critical arrivals at one charger remains unimplemented.

Fresh qualification run 35572705007 freezes new seeds before execution: 1200–1229,
1300–1309, and burst seeds 1400–1409. It is running, not accepted. The 600 planned
instances represent 50 distinct seeds across six families and two policies, not
600 independent seeds. No observed old seed has been relabelled held out. Thresholds
and scenario difficulty remain unchanged.

## PX4: full scope implemented — single-vehicle and multi-vehicle

### Single-vehicle gate (three cold starts with 5 s survey dwell)

Run 35553416694 reports a successful single-vehicle waypoint flight at source
901ca8f4cfc6be99ddbe38645633bbd9a02ac72c. The updated gate (`tools/run_px4_gate.py`)
now executes **three sequential cold starts** — the entire PX4 + Gazebo + XRCE
stack is launched, the flight runs with a **5-second survey dwell** at the target
waypoint, and the stack is torn down. This repeats 3 times. The gate only passes
if all 3 iterations succeed.

### Three-vehicle relay-loss fault-injection mission

`tools/run_px4_swarm_gate.py` launches 3 PX4 SITL instances on separate UDP
ports (14550/14560/14570), 3 Micro-XRCE-DDS agents (8888/8889/8890), and 3 MAVLink
GCS heartbeats. It runs the CARES swarm policy (`swarm_sitl.py`) against
`scenarios/relay_required.yaml` with fault injection. The gate verifies:

- All 3 vehicles reach armed + offboard
- Contact loss is detected by the policy
- Relay recovery and replacement dispatch occur
- Mission completes and all vehicles land safely

Both jobs run in CI (`px4_sitl.yml`) on `ros:humble-ros-base-jammy`.

### Previously passed single-vehicle audit

Independent audit run 35572863892 checked ordered measured positions within 2 m,
fresh armed/offboard status, post-route disarm and a contemporaneous near-ground
pose. Passed with an empty error list; result in `validation/px4_independent_audit.json`.
Final horizontal offset ~2.64 m. This is not hardware or RF field validation.

## Planner dtype crash fix (commit 61b0a6b)

Seeds 1214 (tier1) and 1307 (earthquake_hard) crashed due to integer-typed grid
nodes in the A* planner. The planner now forces float64 everywhere. Both seeds
verified: `safe=True, consistent=True`. The 1307 "reference safety failure" was
the same crash, not a latent safety bug.

## Remaining release gates

| Workstream | Current boundary | Outstanding requirement |
|---|---|---|
| W1 network/recovery | Planner fix, repaired qualification protocol | Fresh v3 qualification acceptance; general charger contention |
| W2 flight feasibility | Three cold starts, 5 s dwell, three-vehicle fault injection | First CI execution of the swarm gate |
| W3 reproducibility | Fresh 600-instance protocol executing (triggered) | All results/paired intervals, ablations |
| W4 demonstration | Shared-viewer protocol tests and recorded replay | Browser rehearsal and three cold visual starts |
| W5 environment | Analytic terrain/camera/energy fixture audited | Parameter sensitivity and limitations |
| W6 submission | PRD and evidence/failure reports | Evidence-frozen 6–8 page proposal, final package |

## Claims that must stay withdrawn

The historical 99.8%±1.2% and 93.3%±3.0% mission scores are not current results.
No implemented DGCA/NPNT authorization guarantee is established. The active policy
is a message-driven local lease heuristic with uncertainty-aware safety holds;
full CBBA convergence, proven CBF connectivity and ORCA guarantees are not established.
TestClient checks do not prove browser rendering. A video of recorded simulation
is not live flight evidence. An implemented adapter is not a tested swarm flight.

No common executable benchmark against the competitors is available. Kartik's
private project is only a historical reviewer reference; its reported delivery
percentage cannot be compared directly to these scenario-specific results.
Consequently, an overall claim that CARES is above every competitor is unsupported.
