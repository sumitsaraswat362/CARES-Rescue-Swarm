# CARES competitive release PRD

Date: 2026-09-20

Status: implementation specification; new requirements below are not completed features.

Baseline: upstream `main` at `151ac89e09cc0c6cd6e4ab8349b95e5bb6a5cf67` (merged PR #4).

## 1. Product objective

Demonstrate a disaster-response swarm that delivers useful observations to the GCS,
maintains communication among operable vehicles, reallocates tasks and relays after
disturbances, and respects measured safety and energy constraints. Every headline
claim must resolve to a versioned implementation and independently checked evidence.

The competitive objective is a stronger demonstrated submission than the visible
projects and the historical Kartik reference. It is a target, not an established
ranking. Unavailable competitor code and incompatible metrics cannot support a
claim of measured superiority. Zero future bugs cannot be guaranteed.

### Challenge alignment

Source: the user's attached UAV-X challenge PDF, not a newly verified organizer
announcement. Its rubric is mission completion 25%, communication resilience 25%,
autonomous relay/role management 20%, recovery/reconfiguration 15%, safety 10%,
innovation 5%. Its Stage 1 deliverables include a 6–8 page proposal, architecture,
working simulation, source code, installation instructions, and demonstration video.
The supplied brief lists 27 September 2026 as the Stage 1 deadline; confirm any
organizer amendments before submission. Do not invent a standardized organizer log
schema that has not yet been supplied.

Spend effort first on mission, communication, relay management and recovery: these
account for 85% of the supplied rubric. Additional visual or algorithmic features
must support those requirements or the demonstration.

## 2. Known baseline and corrections

- The prior gate passed 51 tests and an independent relay evidence audit in a fresh
  GitHub checkout. The locally audited batch comprises 28 full-duration runs, not
  28 independent seeds per scenario. See `docs/GAP_CLOSING_RECEIPT.md`.
- Basic seed 100 delivered 100% versus the preceding 40%; basic seeds 101/102 also
  delivered 100%. Hard seed 100 delivered 43.75% versus 25%, while the reported
  all-UAV connectivity changed from 21.71% to 13.30%.
- Local and remote source hashes differ due to five empty package-marker files;
  the existing receipt records this. Future qualification must use a complete,
  exact checkout and a single versioned source manifest.
- A permanently radio-failed aircraft remains in the current all-UAV connectivity
  denominator, while `Transport.positions()` removes it from the graph. Thus all
  fleet connectivity is impossible while that aircraft remains active with a dead
  radio. Low all-UAV connectivity alone is not a sufficient root-cause diagnosis.
- Keep the existing metric intact. Add separate, explicitly named operational
  metrics and report excluded identities/reasons and time-varying denominators.
- Fault-event counts and permanently failed aircraft are distinct. Battery drain
  and radio failure must not be relabelled as motor failure to make counts match.
- The supported allocator is a local lease auction and the supported safety action
  is an uncertainty-aware hold. Full CBBA convergence, certified CBF connectivity,
  ORCA guarantees and a trained policy are not established properties.
- Live ROS 2/PX4/Gazebo flight and browser visual QA are not established by the
  existing unit tests. They need separate execution evidence.

## 3. Competitive design inputs

| Reference | Useful idea to adapt independently | Evidence boundary |
|---|---|---|
| Kartik | Real flight-controller feasibility, deterministic routing, leased roles, observation custody during partitions, set-based receipt checking | Historical reviewer description only; private code and 99.98% delivery cannot be rechecked or used as a directly comparable target |
| Sciencebanda | Terrain/obstacle effects, camera footprint and dwell, inspectable safety constraints, canonical replay, presentation polish | Public source inspected at `0d0cea6cc22b3a8a944781b370b7c4401750fd3b`; optional CCPL training/adapter exist, but a trained policy advantage was not demonstrated in this review |
| Nihit | Simple installation and understandable task/failure demonstration | Public source inspected at `cd5981596a3a21b00a74cf7bc66c02c4d7d36c84`; allocation is nearest available UAV and networking is range based |

Use original implementation and cite conceptual influences. Reuse third-party code
only after checking its license and keeping required attribution. A public repository
is not automatic permission to copy. Do not copy private implementation details.

## 4. Requirement states and execution order

Each requirement has one of: PLANNED, IMPLEMENTED, UNIT-TESTED, INTEGRATION-TESTED,
BENCHMARKED, BLOCKED, or ACCEPTED. Acceptance requires the stated gate, not merely a
file or function with the right name. Record a reason and evidence for each transition.

Execute W1 before policy feature expansion. W2 environment preparation can begin
while W1 runs, but flight evidence remains its own gate. W3 wraps W1/W2 evidence;
W4/W5 follow a stable core; W6 produces the final submission after frozen validation.
The public competitor recheck already scheduled is advisory and cannot change the
qualification suite after results are visible without a versioned protocol amendment.

## 5. W1 — connectivity, mission delivery, relay recovery (P0)

### Deliverables

1. Trace diagnosis: for every disconnection record vehicle ID, interval, reachable
   component, radio state, last received heartbeat, role, relay request, route age,
   battery, backlog and independently reconstructed GCS reachability.
2. Preserve all-UAV connectivity; additionally report all-radio-capable-survivor
   connectivity, per-vehicle availability, pre/post-fault availability, and longest
   blackout. Empty populations are undefined, not 100%. Log membership transitions.
3. Distinguish physical reachability, locally believed route freshness, and actual
   acknowledged end-to-end service. The evaluator can use truth; agent decisions
   cannot read evaluator state or the simulator's global graph.
4. Correct relay placement or role churn only after attributing lost service to a
   specific mechanism. Incorporate obstacle-aware preflight planning, hysteresis,
   bounded recovery attempts, role leases and battery-aware handoff as justified.
5. Deterministic route selection with explicit tie-break, expiry, loop rejection,
   reboot/epoch handling and partition reconciliation. Add protocol metadata only
   where needed; charge all bytes to the same finite network budget.
6. Bounded observation custody: unique observation IDs; explicit custodian ACK;
   deduplication; storage limits, TTL and priority eviction; bounded replication for
   critical observations. An ACK means the documented storage level, not delivery
   to GCS. If persistence across restart is claimed, test a real restart.
7. Protect relay service during planned rotation: verify replacement GCS service
   and affected downstream reachability before releasing the old relay. Log failed
   or timed-out handoffs, not only successes. Assess the cost in survey capacity.

### Gates

- Ground truth recomputation agrees with summaries for all new metrics. An aircraft
  with a dead radio remains visible in the all-UAV metric and fault inventory.
- Adversarial fixtures include duplicate messages, reordered old epochs, one-way
  loss, split/merge partitions, a failed custodian, queue saturation, and a retiring
  relay with downstream clients. Successful custody is never inferred from send().
- Every scripted fault due before mission end fires exactly once with the intended
  physical or logical effect. Record rejected fault IDs/configuration as errors.
- Same-scenario paired comparison shows improved operational connectivity/recovery
  without masking poorer GCS delivery, priority completion, latency or safety.
- Pre-register a non-inferiority margin of 2 percentage points for mean delivered
  completion and mean radio-capable-survivor connectivity, separately in each hard
  and tier scenario family. A claim of improvement requires the paired 95% interval
  for its difference to exclude zero. If sample size is insufficient, report that.
- Preserve zero independently observed separation, geofence and depleted-battery
  violations in the qualification batch; this is finite test evidence, not a proof.

## 6. W2 — real PX4 feasibility and fault handling (P1)

### Deliverables

1. Establish an available Linux execution environment with pinned PX4, Gazebo,
   ROS 2, matching px4_msgs and XRCE-DDS versions. Record OS, resources, build IDs
   and installation commands. Verify compatibility from official documentation
   when implementing. First probe whether the current environment can support it.
2. Automated simulator launch, readiness/health checks, namespace/system-ID/spawn
   frame validation, log collection, timeout, clean shutdown and nonzero failure exit.
3. One-vehicle measured mission: valid telemetry, arm/mode ACKs, actual offboard
   state, takeoff, waypoint arrival, survey dwell, return, landing and disarm.
4. Three-vehicle feasibility mission before larger swarms: relay-required route,
   delivered observation, relay loss, replacement/recovery, and measured return.
   Reuse the production policy through the existing measured-state backend.
5. Fault matrix: stale pose, missing status, rejected arm/offboard, wrong namespace,
   link outage, controller process interruption and failed mission timeout. A
   simulated radio outage and an actual flight-controller fault are separate tests.

### Gates

- Retain ULog/flight logs, DDS-derived measured pose/status and command ACK logs,
  simulator versions, vehicle mapping, scenario and actual recording.
- Recompute movement, waypoint/dwell, safety and completion from measured data.
  Setpoint publication or mock callbacks cannot pass the flight gate.
- Pass three clean starts of the one-vehicle mission, then three clean starts of
  the three-vehicle mission, with all attempts and failures retained.
- State radio-model and battery-feedback boundaries explicitly. PX4 flight physics
  with a simulated radio is not hardware RF validation.
- If dependencies, network access or compute prevent execution, mark W2 BLOCKED
  with exact command/error. Continue independent work; do not substitute synthetic
  output. The final proposal must then describe SITL as pending.

## 7. W3 — reproducibility and qualification (P1)

### Deliverables

1. One documented command for installation verification and one for a versioned
   benchmark protocol, including resumable jobs and failed-run accounting.
2. Freeze candidate and reference commits. Use full Git trees and manifests of
   runtime source, scenarios, configuration, dependency versions and environment.
3. Each run retains seed, resolved fault times, actual duration, actual RF settings,
   commands/exit codes, acquisition coordinates and dwell, packet IDs/arrivals,
   custody transfers, raw telemetry, summary and independent audit.
4. Summary tables: completion at GCS, priority/on-time completion, hop PDR and
   end-to-end observation delivery separately, p50/p95 delay, all-fleet and
   operational connectivity, blackout/recovery duration, custody losses, relay
   overhead, energy, safety, compute time and peak memory.
5. Baselines: preceding production commit, nearest-feasible task assignment, fixed
   relays and reactive relays. Targeted ablations cover custody, relay prediction,
   priority scheduling and the new environment model. Equal resources and the same
   exogenous disturbance field are required; disclose different policy traffic.

### Frozen seed protocol (planned, not executed)

- Development/tuning seeds: 100–109. Never call these held-out qualification.
- Qualification: seeds 200–229 in six families: basic, hard, tier1, tier2, tier3,
  relay rotation, at explicitly recorded scenario-default RF settings. Candidate
  and preceding production policy: 180 runs each, 360 total.
- Independent held-out confirmation: seeds 300–309 in the same six families and
  two policies: 120 additional runs. After examining these, they cease to be held out
  for a subsequent revision; register a new seed range before another qualification.
- Explicit burst stress: seeds 400–409 in the same families with burst probability
  0.15 for both policies: 120 additional runs. Never pool silently with default RF.
- Total planned primary/reference run instances: 600. This is 50 distinct seeds
  across the three stages, repeated across scenarios/policies, not 600 independent
  seeds. Targeted ablations and integration fixtures are additional and labelled.
- Measure pilot runtime/storage before launch. If the resources or deadline prevent
  completion, publish actual counts and protocol deviations; do not claim 600 runs.
- Preserve all unsuccessful attempts. Process crash, simulator failure, evidence
  inconsistency, infrastructure outage and unsafe mission are different outcomes.

### Gates

- All completed-run summaries independently match raw evidence; failed audits fail
  the benchmark gate. No change of scenario difficulty under the same batch name.
- Report paired differences and fixed-method 95% bootstrap intervals; completion,
  connectivity and latency are not interchangeable. Show zero variance when real.
- Same commit/config/seed reproduces the declared deterministic outputs; timing
  nondeterminism in live SITL is disclosed, not forced into an identical-hash claim.
- Two clean installs in disposable environments run the gate without local caches,
  implicit Python paths or untracked files. One is CI; one is the demonstration setup.
- Store raw evidence as release/CI artifacts with checksums and verified download
  links. Repository summaries alone are insufficient long-term evidence storage.

## 8. W4 — live demonstration and replay (P2)

### Deliverables

- Mission truth comes from the running backend. Every UI metric has a definition,
  unit and matching exported field. Distinguish estimated agent routes from truth.
- Show acquired versus delivered tasks, observation age/backlog, active and failed
  radios, relay responsibilities, failures, recovery and battery reserves.
- Fault commands return accepted/rejected status with command ID, generation and
  simulation time; duplicate commands cannot silently double-apply a fault.
- A reproducible scripted demonstration: start, priority task arrival, relay loss,
  network recovery, data receipt, battery handoff, pause/reset and viewer reconnect.
- Replay the same backend logs with timeline/seek and event inspection. A 3D viewer
  must consume recorded positions and avoid implying unmodelled physics. Start with
  the existing working dashboard before expanding visualization.
- Package a short real demonstration video, backed by the exact build/logs, and
  an offline replay fallback on the judging machine.

### Gates

- Browser-level execution: two simultaneous viewers, shared commands, generation
  consistency, reconnect, mission completion and cleanup. Existing TestClient tests
  remain, but cannot stand in for rendering and user-interaction checks.
- Run three rehearsals from cold launch, including one offline replay. Retain video,
  console/network errors, startup commands and performance observations.
- No chart may extrapolate completed mission results from an unfinished run or
  display a nominal link as proof that a packet arrived.

## 9. W5 — useful realism and coverage (P2)

### Deliverables

- Versioned terrain/obstacle interfaces for path planning, clearance and radio LOS.
  Begin with small deterministic analytic terrain fixtures; asset appearance is not
  ground truth. Add open geodata only with provenance and compatible licensing.
- Acceleration, climb and wind effects with explicit units and bounded commands;
  energy terms for flight/climb/payload. Treat parameters as assumptions until
  calibrated. Compare selected trajectories with measured PX4 where available.
- Camera acquisition requires ground-target footprint, AGL bounds, speed and dwell.
  Count mapped area separately from completed PoIs and GCS-delivered observations.
- Separate command constraints from safety observations; record between-tick swept
  separation/obstacle checks. Do not teleport vehicles to make a safety metric pass.
- Add terrain-shadow, obstacle-detour, limited-battery and camera-footprint cases
  where the environment changes the decision or observation validity.

### Gates

- Analytic fixtures verify slope/clearance, obstructed LOS, footprint containment,
  area union (no double-count), energy units and timestep convergence.
- All scoring is recomputed from measured/simulated raw positions and declared
  sensing constraints. A target near the second path waypoint is not automatically
  a completed survey. Transit over a target is not enough without dwell.
- Version changed physics/scenarios; rerun reference policies under the same model.
  Do not compare an easy old environment with a hard new one as algorithm evidence.
- Full qualification reruns after the final runtime/model change. The evidence
  freeze occurs after W5, not before adding realism to the validated candidate.

## 10. W6 — claims, final CARES proposal and submission (P0 throughout; final last)

### Deliverables

- A machine-readable claims registry: claim ID, precise wording, source symbol or
  artifact, commit/config/seed, evidence hash, scope, status and known limitation.
- A documentation checker for referenced paths/symbols, stale source manifests,
  broken evidence references and metric values drawn from approved batch outputs.
  Automated checks cannot validate arbitrary prose or substitute for human review.
- Update README, installation, architecture, metric definitions, limitations and
  feature status together. Correct stale documents such as the upgrade map's
  statement that the newly regenerated degradation JSON is historical.
- Final `CARES_Technical_Proposal.md` plus rendered 6–8 page PDF and editable source.
  Keep the current candid proposal until final results exist. The final proposal is
  written after evidence freeze; planned features must not appear as achievements.
- Submission archive, reproducibility manifest, source/release commit, raw-evidence
  download, recorded demonstration, and one-page reviewer quick-start.

### Proposed eight-page structure

1. Mission, objective and measured contribution.
2. Architecture, agent information boundaries and software interfaces.
3. Task allocation, routing and observation custody.
4. Relay retirement, partition recovery and energy management.
5. Safety, environment/sensor assumptions and PX4 status.
6. Reproducible evaluation protocol and primary results.
7. Baselines, ablations, uncertainty and failures/limitations.
8. Demonstration/install path, challenge mapping and references.

Compress to six or seven pages if needed without deleting evidence limits. Validate
the rendered page count and layout. References count in the 6–8 pages unless the
organizer explicitly permits otherwise. Do not include invented regulatory locks,
authorization integration, mathematical guarantees or teammate credentials.

### Gates

- Every numerical result in the proposal resolves to exact JSON in a frozen batch.
- Every named implemented module/function exists at the cited commit; every planned
  component is explicitly marked planned. Validate symbols and paths with `rg` plus
  structured checks where appropriate; string presence alone does not prove behavior.
- Tests, CI and benchmark counts are actual observed counts. Flight feasibility,
  simulated safety and hardware/field validation have separate labels.
- Record literal `git log -1`, `git status`, remote head and CI result. Verify published
  blobs/artifact hashes after uploading. Do not claim pushed files from local existence.
- A reviewer can cold-start, reproduce a small mission, inspect its raw evidence,
  replay it, and trace proposal numbers without relying on this conversation.

## 11. Acceptance and release decisions

| Gate | Pass evidence | If it fails |
|---|---|---|
| Metric integrity | Independent event/pose/packet reconstruction | Block performance claims and repair evidence pipeline |
| Core mission/regression | Same-seed reference comparison and targeted fault fixtures | Diagnose and rerun affected work; retain failed results |
| Statistical qualification | Frozen manifest and completed required batch with uncertainty | Report actual subset; no statistical superiority claim |
| PX4 | Measured flight logs and completed return/landing | Explicitly mark flight tier blocked/pending |
| Demo | Real browser rehearsals and recording | Fix interaction or label unverified; preserve offline evidence |
| Proposal | 6–8 page render, exact source/result references | Correct unsupported text before submission |

All six workstreams are requested scope. An unavailable flight environment is a
documented blocker, not permission to call W2 complete. An achievable Stage 1
package may disclose that limitation, but is not completion of this full PRD.

There is no overall 'better than everyone' gate without a common executable
benchmark and access to all compared systems. The defensible release claim is:
what CARES accomplished, under which disturbances, using which model, on which
seeds, with which failures and uncertainty. A competitor comparison must distinguish
inspected code, reproduced results and historical/unverified descriptions.

## 12. Work ledger at PRD publication

| Workstream | Status | Next action |
|---|---|---|
| W1 | PLANNED; denominator mechanism inspected | Produce per-vehicle disconnection diagnosis before policy edits |
| W2 | BLOCKED for execution in prior environment; setup investigation planned | Probe execution prerequisites and establish a real runner |
| W3 | PLANNED; existing 28-run receipt remains valid within its scope | Freeze complete baseline and implement benchmark manifest |
| W4 | PLANNED; existing two-viewer protocol test passes | Browser rehearsal and evidence export |
| W5 | PLANNED | Add minimal analytic terrain/sensing fixtures with useful effects |
| W6 | PRD prepared; final proposal PLANNED | Build claims registry and generate proposal only after qualification |

This document is the plan requested before implementation. It reports no new
completed benchmark, simulation feature, PX4 flight, video or final proposal.

## 13. Protocol amendment after v1 rejection (2026-09-21)

The first 600-attempt protocol completed with 60 unsafe candidate runs and two
candidate timeouts; release acceptance failed. All original seeds are now observed.
The original artifacts, thresholds and failed acceptance are retained unchanged.

For a repaired candidate, seed epoch 1 is reserved before execution: qualification
1200-1229, confirmation 1300-1309, and 15% burst stress 1400-1409, in the same six
families and candidate/reference pairing (600 attempts, 50 distinct seeds). Use
`freeze --seed-epoch 1`. Development seeds and observed v1 seeds remain regression
inputs. No old seed is relabelled held out. Scenario content, failure distributions,
radio settings, 2 pp non-inferiority margin and safety gates are unchanged.

V2 uses 24 immutable shards, two workers each and at most 12 concurrent shards,
reducing wall time without shortening mission duration or omitting failed runs.
The preceding production reference stays at 151ac89. The repaired candidate is
frozen by the protocol job's exact Git checkout and runtime hash. The qualification
plan is not an assertion that any of its future results will pass.
