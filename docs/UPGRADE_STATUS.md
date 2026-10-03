# Twelve-change implementation map

The supported execution path is `src/resilience/runtime.py`, shared by CLI and web.
The old global CA-CBBA, GCS metric, and MBB modules remain for source-history comparison;
they are not used by this runtime. The new allocator is a local lease auction, not a
claim to implement the full CBBA convergence proof. The safety controller is a local
uncertainty-aware motion hold, not a certified ORCA/CBF guarantee.

| # | Change | Implementation | Validation / remaining limit |
|---|---|---|---|
| 1 | Correct mission metrics | evaluator separates acquisition, full GCS receipt, priority/on-time completion, latency | Duplicate receipt and acquisition-without-delivery tests |
| 2 | Unified communication | one bounded delayed per-hop transport for beacons, claims, observations, probes and ACKs | Blocked control and relay-required tests; abstract radio, no MAC interference model |
| 3 | Local coordination | per-agent received neighbor tables, contact timeout, task leases, reconciliation | Partition/lease tests; temporary duplicate work is allowed |
| 4 | Store and forward | bounded origin storage, intermediate queues, retries, ACKs, deadlines | Outage, expiration, queue-bound tests; source loss may lose unreplicated observations |
| 5 | Predictive handoff | return reserve plus travel/overlap budget; replacement GCS probe excluding old relay | Actual battery-rotation run; downstream service continuity is not a formal guarantee |
| 6 | Delivery-aware admission | return energy, local routed anchors, payload service estimate, deadlines, backlog threshold | Implemented conservative heuristic, not global optimization |
| 7 | Priority transmission | alerts/previews/full observations, priority plus aging, FIFO ablation | Scheduling test; full receipt alone earns delivered completion |
| 8 | Safety/energy | command hold, altitude ceiling, independent swept separation monitor, charger capacity | Safety tests and sampled runs; simplified kinematics/power, no contact physics |
| 9 | Reproducibility | shared runner, fail-fast checks, development requirements, hashes, seeded RF field | Automated suite and deterministic replay test |
| 10 | PX4 integration | ROS 2 offboard adapter, frame conversion, measured-state backend, swarm runner | Pure adapter tests only. ROS/PX4/Gazebo flight execution is NOT verified in this environment |
| 11 | Benchmarks | same scenario/seeds across direct, fixed, reactive, FIFO, no-buffer and CARES modes | Generated reports preserve per-run metrics; no blanket superiority claim |
| 12 | Evidence dashboard | delivered/acquired, backlog, latency, separation, handoffs and contact losses | Shared server serializer tested; full browser rendering still requires a local run |

## Information boundaries

Initial tasks, the static obstacle map, home location and initial relay stations are
preflight inputs. Hidden tasks are revealed to an individual agent by the simulator's
local sensor; new GCS tasks propagate in delivered beacons. Agents cannot access the
fleet registry or physical adjacency. The transport and evaluator may access truth.
The ground-truth link overlay must not be confused with an agent's estimated route.

## Radio and physics assumptions

The runtime uses a configured range with a linear edge-quality transition, obstacle
attenuation, finite node byte service, propagation/serialization delay, and a seeded
time-indexed burst field. This intentionally replaces the inconsistent legacy RF
models with one inspectable abstraction; it is not calibrated to a particular radio.
Broadcast payloads share one transmit service cost, with per-recipient reception loss.
Packets use discovered source routes; no oracle supplies a route. Route root timestamps
expire through partitions. Ground truth evaluation uses the same instantaneous edges.

Battery values are simulation parameters, not measured hardware endurance. A 200 Wh
battery at 150 W has 80 minutes nominal hover endurance. The rotation fixture starts a
relay with reduced charge to exercise replacement naturally; it is not field validation.

## Results policy

Existing `logs/mc_*` predate the new definitions and are historical. The root
`degradation_results.json` was regenerated in PR #4 with explicit fault accounting;
its source hash still identifies that specific prior batch. These sets must not be
mixed or cited as performance guarantees. New reports carry
`cares-evidence/v2` plus scenario, configuration, and source hashes. Queueing and eventual
delivery do not imply continuous connectivity. A simulation pass is not a flight pass.
