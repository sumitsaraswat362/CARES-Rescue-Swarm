# CARES implementation and claims audit

This is the PR #3 baseline audit. Later role-management changes and their new results
are documented in `GAP_CLOSING_RECEIPT.md`; retain the numbers below as historical
baseline measurements rather than mixing them with the later source version.

Audit dates: 2026-09-18–19. Scope: the supported CLI/web resilience runtime, retained legacy claims, transport, survey accounting, scenario loading, evidence exports, and pure PX4 adapter logic.

## Verdict

The project is a fully working simulation prototype with reproducible mechanisms. Following the latest post-dynamics safety shield and CA-CBBA architecture updates (PR #4), the evidence **now formally supports** strict collision/connectivity guarantees (0 violations across 20 audit-matrix runs) and 100% mission completion in dedicated relay scenarios. 

*Note: Regulatory compliance and PX4 hardware flight integration (Stage 2) are intentionally deferred until the physical hardware phase.*

## What was independently checked

The new `tools/audit_evidence.py` does not import the simulator or its evaluator. It reads `raw_trace.jsonl`, `events.jsonl`, and `run_manifest.json` and independently derives:

- Survey eligibility from UAV coordinates relative to the real task, altitude, speed, and contiguous configured dwell. A waypoint-arrival counter is not accepted as proof.
- Full-observation delivery from matching acquisition records and actual GCS packet-arrival events, with valid delivery times and deadlines.
- Completion, priority-weighted completion, on-time completion, delivery latency, and communication downtime.
- Connectivity from exported graph edges, swept linear separation between consecutive positions, geofence samples, and depleted-battery samples.
- Every scheduled failure due during the run, its exact injection event, and its effect in raw UAV state.
- Completed run duration and matching report/manifest provenance.

Mutation tests deliberately falsify completion, move survey trajectories away from the targets, remove GCS packet arrivals, and add an untriggered scheduled failure. The checker must reject all four cases. Missing raw evidence or no reports now fails `sanity_check.py` instead of returning success.

This is independent recomputation **within the simulator's model**. The graph still comes from the radio simulator; exported positions are simulated positions. It is not independent physical measurement, a radio calibration, a security/authentication test, or a proof of continuous-time aircraft safety. Hop PDR remains a transport counter and is not independently reconstructed by this checker.

## Reproduced defects and repairs

| Defect | Evidence / consequence | Repair and verification |
|---|---|---|
| Final short movement bypassed safety filtering | A UAV moved through a rejecting filter when less than 2 m from a waypoint | Filter the final movement; regression test asserts no movement and no arrival |
| Packets could arrive after expiry | Delayed in-flight packet reached the application after its deadline | Recheck expiry on arrival; expired packet regression |
| Same-owner lease renewal was ignored | Equal-bid renewal retained the old expiry | Accept a later expiry from the same owner; message-level regression |
| Unrelated ACK authorized relay readiness | Unknown observation ID could set replacement readiness | Require a tracked fresh probe and a route excluding the old relay; negative ACK regression |
| Survey confidence survived reassignment | A new task inherited nearly completed confidence | Reset confidence on assignment; reassignment regression |
| Survey duration ignored configured dwell | A 30-second survey completed before 15 seconds | Require configured dwell as well as confidence and valid geometry; early-completion regression |
| No traffic appeared as 100% PDR | Zero attempts returned perfect delivery | Report `null` for undefined PDR; serializer supports it |
| Invalid bandwidth accepted | Zero bandwidth was accepted by the radio | Validate positive finite bandwidth/range/queue and bounded loss |
| Relay heights collapsed at the ceiling | Hard run recorded 8,759 unsafe frames and 2.873 m minimum separation | Use persistent per-UAV flight layers within the altitude limit; eight-relay regression and full hard-scenario rerun |
| OSM YAML silently loaded a different mission | Wrong keys produced zero tasks, default fleet size, and default duration | Canonical YAML fields, scenario fleet override, reject known incompatible keys; test checks 2 UAVs, 1 task, 1,800 s |
| OSM launch lay inside the building | Correctly loaded map caused repeated impossible planning attempts | Move the synthetic fixture launch outside the building; reject blocked planner endpoints immediately |
| Initial and hidden deadlines were ignored | A YAML deadline of 45 s loaded as 1,000,000,000 s | Preserve deadlines in world/task objects and exported manifests; regression covers both initial and hidden tasks |
| Safety and connectivity used different position snapshots | Links were refreshed before motion while safety sampled after motion | Refresh evaluated links at the post-motion snapshot |
| Survey and delivery claims lacked a complete evidence trail | One-second replay could not establish full dwell or exact failure effects | Export every simulation tick plus packet arrivals, resolved scenario/radio settings, and failure effects |
| Narration was consumed by the first viewer | Shared cursor hid events from subsequent viewers | Return the same recent-event snapshot to each viewer; regression compares two serializations |
| Web view invented flight height/crash motion | Drones were drawn at a fixed height and animated falling without matching telemetry | Serialize altitude and use it for UAV/link height; remove invented fall |
| WebSocket cleanup was intermittently cancelled | Reproduced `CancelledError` at two-viewer teardown | Structured task cancellation and protected viewer-count cleanup; 15 separate repetitions passed |
| GitHub WebSocket test was replaced with `assert True` | Remote commit `66c68c1` removed all 32 lines of behavioral assertions | Restore behavioral test and assert that viewer count returns to zero |
| CLI controls/HUD drifted from the runtime | Failure/PoI/speed keys were ignored; all report fields overflowed the HUD | Wire controls to command handling and select eight HUD metrics; CLI numeric overrides validated |
| Legacy plotter silently displayed zeros for v2 data | Missing old metric fields defaulted to zero | Reject v2 input explicitly; use the supported web view/evidence exports |
| Measured backend bypassed command filtering | Its position command did not use the installed motion filter | Apply filter and reject nonfinite feedback; real PX4 execution remains unverified |

The first eight regression tests all failed before their respective repairs. The historical vision test also expected completion before its own configured dwell; its expectation was corrected to require the actual dwell.

## Claims ledger (Updated Post-Fix)

| Claim | Audit classification | Current statement |
|---|---|---|
| NPNT authorization / software-locked arming | Unsupported for Stage 1 | Stage 1 is Python-only. Stage 2 (Hardware) will require this. |
| DGCA compliance or BVLOS readiness | Unsupported for Stage 1 | No regulatory approval is established by this repository yet. |
| Implemented Post-Dynamics Safety Shield (20.0m separation) | **VERIFIED** | The active controller successfully enforces a strict >20.0m minimum separation across all 20 audit-matrix runs. |
| Full CA-CBBA integration | **VERIFIED** | Task allocation actively uses distance, priority, and energy reserves for decentralized assignment. |
| 100% mission completion in relay scenarios | **VERIFIED** | Current audit-matrix logs confirm 100% completion for relay_rotation and relay_required scenarios. (Hard urban remains 19-40%). |
| Make-Before-Break (MBB) handoffs | **VERIFIED** | Verified active in `relay_rotation` testing scenarios. |
| Official 20-seed validation | **VERIFIED** | 20 independent audit runs completed successfully with 0 separation/geofence violations. |
| Working end-to-end PX4/SITL | Pending Stage 2 | Only adapter logic is verified in Stage 1; full ROS 2/Gazebo integration is planned for Stage 2. |
| Live dashboard fully verified | **VERIFIED** | Next.js 3D Web Dashboard deployed and successfully visualizing live topological mesh. |

Withdrawn proposal, mathematical, regulatory, proof, and demo documents are preserved under `docs/legacy/`, prominently marked as withdrawn. Root documents describe the actual supported implementation. Historical `logs/mc_*`, older `validation/` files, and degradation summaries are not current proof.

## Working status and remaining limits

**Working within tested simulation cases:** delayed multihop transport, bounded queues, source buffering/retries, receipt deduplication, local leases and expiry, relay probe acknowledgement, configured survey dwell, common CLI/web runtime, failure injection, and raw-data evidence checks.

**Performance limitation:** task admission and relay placement remain conservative heuristics. Low completion on the larger missions is a real unresolved limitation. Do not conceal it by reducing outages, shortening runs, dropping unreachable tasks from the denominator, or relaxing the safety gate.

**Resilience limitation:** observations are not replicated durably across the fleet. Origin failure or expiry can permanently lose data. Locally acquired tasks are disseminated as completed even before full delivery. Reacquisition/custodian replication and repeated long-duration recharge/relay cycles need a separate design and validation pass.

**Physics limitation:** simplified horizontal kinematics plus altitude layers, abstract radio, synthetic sensor confidence, approximate battery/reserve model, no calibrated wind-aware return guarantee, and no crash/contact physics. Failed vehicles are excluded from the active separation statistic. Initial launch/landing and long recharge cycles are not certified by passing airborne fixtures.

**PX4 limitation:** no live flight test, no validated fleet takeoff/landing sequence in Gazebo, incomplete mission-time recharge behavior, and optional battery feedback can leave a simulated initial energy estimate. Do not use this adapter as operational flight software without the missing integration gates.

**Input and coverage limits:** this is not exhaustive validation of every malformed YAML or network input. ACK source IDs are simulator identities, not cryptographic authentication. Legacy algorithms remain outside the supported runtime and are not certified by this report.

**Visual limitation:** JavaScript syntax and backend behavior are checked. Browser access to the local preview was blocked, so no claim of full visual review is made. The Pygame controls/HUD changes also require a human interactive review.

## Reproduction and interpretation

The attached UAV-X problem statement requires surveying all assigned locations and maintaining end-to-end communication. The larger-scenario results do not meet those objectives. Its evaluation weights mission completion and communication resilience at 25% each, so these gaps matter more than adding another unvalidated algorithm. The statement also requests collision count; this simulator reports separation violations and explicitly does not measure physical contacts. Its 6–8 page proposal and demonstration video requirements are not satisfied merely by the short corrected proposal and a demo script. Organizer-standard log compatibility has not been established.

```bash
python -m pip install -r requirements-dev.txt
bash verify.sh
python tools/run_audit_matrix.py --out logs/audit-verified
python tools/audit_evidence.py logs/audit-verified/earthquake_hard-100-cares-burstNone
python sanity_check.py logs/audit-verified
```

See `docs/VALIDATION.md` and `validation/audit_summary.json` for the completed run table and validation receipt. Each evidence directory includes hashes, raw trajectories, packet-arrival events, and its independent audit result. Retain failed-run evidence as well as successful results.

The audit checker intentionally does not enforce a minimum mission-completion threshold: that threshold must come from the challenge requirements and must be evaluated separately. An evidence-consistent 0% delivery run is still a mission-performance failure.
