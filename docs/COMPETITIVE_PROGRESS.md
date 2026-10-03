# Competitive release implementation ledger

This draft is work in progress against `CARES_COMPETITIVE_RELEASE_PRD.md`.

## Connectivity diagnosis

The raw hard-scenario traces (seeds 100/101, production PR #4) show UAV 3 isolated
for 771.7/769.3 seconds respectively. Radio-capable-survivor all-connected time
was also only 13.30%/13.59%. Thus the permanent failed-radio denominator explains
an upper limit but does not explain away the operational connectivity failure.

`tools/diagnose_connectivity.py` computes both denominators and per-vehicle
disconnection intervals directly from raw graph/state. It does not infer local
belief/heartbeat state that is absent from these logs. Three tests cover directed
multi-hop paths, denominator/exclusion changes, recovery intervals and empty sets.
Exact baseline results are in `validation/connectivity_diagnosis_hard100.json` and
`validation/connectivity_diagnosis_hard101.json`.

`Agent.tick` returned for relay roles before the recovery action used by scouts.
A relay whose upstream aircraft failed therefore continued to its assigned station
and remained isolated. The candidate adds timeout-driven retreat and requires
sustained route reception before holding a new relay station. No global graph or
hardware failure flag is read by that policy.

## Rejected first candidate

The first recovery implementation used the return-to-charger action. It delivered
56.25% in each hard seed, but independent raw audits detected separation violations:
19 frames for seed 100, 1594 for seed 101, minimum separation zero. The two vehicles
converged on a shared charger. This is rejected evidence, not an improvement claim.
Its run summaries are preserved in `validation/rejected_relay_candidate.json`.

A second candidate retained relay altitude but still occupied the charger approach
column. It also failed safety (40/60 violation frames for hard 100/101). Its
summaries remain in `validation/rejected_relay_refined.json`.

The current development candidate uses distinct, preflight-valid holding offsets.
Four complete reruns (hard 100/101, basic 100, rotation 100) passed independent raw
safety and evidence checks. Hard delivery is 9/16 = 56.25% in each seed, compared
with 7/16 = 43.75% before. Operational connectivity is 97.28%/95.87%; the original
all-active metric remains 18.99%/16.56%, including the permanently radio-failed UAV.
Minimum hard-run separations are 10.2578 m / 10.6001 m. Basic and rotation delivered
100%; rotation recorded one handoff. These four development runs are not held-out
qualification. Exact audits and paired results are in
`validation/relay_recovery_runs.json` and `validation/relay_recovery_comparison.json`.

## Reproducibility and claims

`tools/compare_runs.py` independently re-audits both sides, rejects unequal scenario,
radio and failure conditions, retains failed runs and reports paired bootstrap
intervals. `tools/qualification.py` constructs the 600-run protocol across 50 distinct
seeds, freezes clean checkout hashes and retains attempt failures. The protocol
construction has unit coverage; the 600 runs have not been executed.

`tools/check_claims.py` validates explicitly registered paths, Python symbols,
evidence hashes and exact JSON values. Both `verify.sh` and ordinary CI run it.
It does not validate arbitrary prose or turn existence checks into flight proof.

## PX4 environment attempt

The local environment still lacks Docker, Podman, ROS 2, px4_msgs, Gazebo, PX4,
CMake and Ninja. A separate GitHub Actions job attempts an actual headless flight
using ROS Humble/Ubuntu 22.04, PX4 v1.16.0 commit
`6ea3539157ca358c70a515878b77077af7d4611d`, px4_msgs release/1.16 commit
`392e831c1f659429ca83902e66820d7094591410`, and XRCE Agent 2.4.3 commit
`73622810d984349b80bbac0ef55fc0b694d62222`.

PX4 1.16 VehicleStatus has message version 1. The previous unversioned subscription
would not receive that topic. Both adapters now derive topic suffixes from installed
message definitions; the pure mapping test is not evidence of a DDS connection.

The launcher retains simulator/DDS/bridge logs and fails if processes, readiness,
ACK/pose/status evidence or the adapter's measured landing result fail. It sets an
explicit RC-loss exception for software offboard operation (COM_RCL_EXCEPT=4).
This is an isolated SITL job, never a physical-vehicle launcher. The one-vehicle
waypoint job is only a first feasibility gate; it does not establish swarm survey,
radio recovery, repeated starts or full W2 acceptance.

Sources for setup: [PX4 ROS 2 guide](https://docs.px4.io/v1.16/en/ros2/user_guide),
[Ubuntu setup](https://docs.px4.io/v1.16/en/dev_setup/dev_env_linux_ubuntu),
[headless Gazebo](https://docs.px4.io/v1.16/en/sim_gazebo_gz/).

The first actual Actions run, 35502616278, failed during PX4 version-header
construction: the shallow NuttX checkout had no matching release tags, causing
`px_update_git_header.py` to raise `IndexError`. Flight was skipped. The workflow
now requests complete PX4 history and explicitly fetches NuttX tags. A passing
build and real flight remain unverified.

## Browser verification

The cloud browser rejected the local dashboard URL with `ERR_BLOCKED_BY_CLIENT`.
WebSocket integration tests remain distinct from visual browser verification;
no completed visual rehearsal or demo video is claimed.

## Local test receipt

```text
65 passed, 2 warnings in 7.26s
```

This covers the full Python test suite including new diagnostic/recovery/topic tests.
Warnings are the existing Starlette/httpx and AnyIO deprecations. W1 qualification,
live PX4, W3–W5 and the final proposal are not complete.

## Routing and observation backup development checkpoint

`src/resilience/routing.py` rejects repeated-node paths, routes naming the wrong
sender, routes containing the receiver, missing GCS endpoints, stale/future epochs
and nonfinite timestamps. Equal-hop routes use lexicographic path ordering rather
than arrival order. Older reordered beacons cannot overwrite a newer neighbor
advertisement. This is a validated path-vector policy, not a link-state protocol
or a proof of convergence under all asynchronous faults.

Full observations can be stored at one peer. Storage ACKs follow insertion into a
bounded 64 KiB buffer; they do not delete the original or count as GCS delivery.
Backups preserve observation IDs, original acquisition and expiry, cannot replicate
further, retry through their own received route, and clear after GCS ACK or expiry.
Control, backup and original traffic use the same finite radio budget. A transport
integration test stores a backup across a partition, kills the origin, restores the
GCS link and checks the actual arriving ID/origin and returned ACK. This validates
the mechanism, not a fleet-wide delivery guarantee. A lost selected backup is not
replaced by unlimited replication; that is an explicit limitation.

`validation/custody_development_runs.json` contains four complete development
runs: hard 100/101 delivered 56.25% each with zero recorded safety violations;
basic 100 and rotation 100 delivered 100%, and rotation completed one handoff.
Hard p95 full-observation receipt latency was 4.52 s / 3.00 s. Both hard runs used
source hash `555b2fda5d8aab50250bb025d65bf089804187a5e388488c5d836fc050ea7cdc`;
the later basic/rotation runs used `d5415f404f036ac8f9d8abebea1abbe51f259430bb62b57c723112d391de50b3`
because dashboard code was being edited while queued development jobs ran. These
are explicitly not an immutable qualification batch. Qualification uses detached,
clean checkouts and checks every tracked file before and after execution.

## Dashboard command/replay implementation

Shared command receipts include ID, status/reason, generation and simulation time.
Duplicate IDs with identical content reuse the receipt without reapplying a pause
or reset. Conflicting IDs, stale generations and missing/dead kill targets reject.
The idempotency window is the most recent 256 commands, not permanent storage.
The existing two-viewer WebSocket test is retained. Separate tests exercise
pause/reset duplicates and stale commands. The frontend displays command status.

`web/replay.html` is an offline, dependency-free top-down replay of `replay.jsonl`,
with manifest targets, seek/play/speed controls and an optional event log. It labels
advertised routes separately from delivery evidence. JavaScript syntax was checked;
visual browser rehearsal and video remain blocked/unverified. No measured 3D flight
or new physics is implied by this page.

The protocol runner now hashes every retained attempt artifact and rejects resume
if an artifact changed. Comparison requires both reference and candidate evidence
consistency, and fails unmatched candidate runs. A sample count alone is no longer
labelled sufficient qualification. W2 live flight, W3 held-out release acceptance,
W4 browser/video, W5 terrain/dynamics integration and final W6 proposal remain open.

## Analytic environment checkpoint

The optional `analytic-v2` profile is now connected to path feasibility, radio LOS,
AGL/footprint acquisition, coverage, normal acceleration-limited movement and
climb/payload energy. Defaults remain the original declared model. See
`docs/ENVIRONMENT_MODEL.md` for assumptions, rejected export attempt, exact seeded
results and remaining limitations. Full 120 s fixture runs for seeds 100/101 both
passed the independent raw audit and delivered 2/2 tasks. Their mapped-area raster
estimates differ (14,300 / 8,700 m²); these are neither ground-truth continuous areas
nor cross-team performance scores. A new regression test also checks that leaving a
target resets continuous survey dwell instead of preserving partial credit.

Latest local full-suite receipt:

```text
81 passed, 2 warnings in 7.16s
```

A 24-run development protocol is executing on detached source checkouts: 6 scenario
families × 2 existing development seeds × reference/candidate. The checkouts freeze
the routing/custody checkpoint before analytic-v2 was added. It is a runner pilot,
not final qualification of the latest source. Reserved qualification seeds remain
unused. The full planned 600-run batch and final acceptance are still pending.

Additional diagnosis of hard seed 100: all seven undelivered tasks have feasible
preflight paths. The ending trace has idle scouts and a surviving relay chain, while
the conservative anchor-radius admission excludes several remote targets. Two hidden
tasks remain outside visited discovery footprints. This is an allocation/exploration
coverage limitation, not evidence that all remaining observations were acquired and
lost in transport. Dynamic frontier relay placement and downstream-service handoff
proof are still open W1 requirements; current routing/custody does not close them.

## Frozen release-candidate preparation

The 24-run pilot finished: all 24 recorded attempts passed their raw consistency
and sampled-safety audits. This remains the earlier routing/custody checkpoint,
not the latest candidate. Its protocol, summary and independently paired comparison
are retained under `validation/frozen_development_*`. The release acceptance tool
correctly rejects this development protocol as insufficient for the reserved 600-run
plan; see `validation/development_acceptance_rejection.json`.

Downstream handoff now requires an actual probe/ACK through the replacement to GCS
for every recorded immediate downstream client before voluntary retirement. A test
dropping that return ACK prevents retirement. This is a protocol test and one full
rotation-scenario demonstration, not a proof of zero packet loss in flight.

Relays may reposition in serialized fleet slots to cover waiting targets, preserving
observed upstream/downstream range, obstacle clearance and return reserve. The
controller uses received peer state and its preflight map, not evaluator connectivity.
Epoch ordering rejects older peer incarnations; epochs are caller-provided and are
not durable restart storage. Custody prioritizes high-priority records within its
bounded buffer and rejects conflicting duplicate payloads.

`validation/service_placement_development.json` records four complete runs from one
runtime source hash, `4a03210ff281d59ca1dfd78377e58749224fb2de424bbc669ede98f79fb39d13`.
Hard seeds 100/101 delivered 13/16 (81.25%) and 12/16 (75%); both had zero recorded
separation, geofence, depletion, terrain and obstacle violations. Radio-capable
survivor connectivity was 94.0444% / 92.5444%, while the original all-active metric
was 19.3333% / 16.4667%. The latter includes the intentionally failed radio. These
denominators are explicitly different; neither is silently substituted for the other.
Basic and rotation seed 100 delivered 100%; rotation had one downstream-proven handoff.
The analytic fixture was also rerun on this source (`validation/analytic_release_development.json`).
All these seeds were used during development and are not held-out qualification.

Latest executed full-suite result:

```text
88 passed, 2 warnings in 7.30s
```

The new qualification workflow freezes both checkouts, enumerates 600 run instances
across 50 reserved seeds and six scenario families, preserves every failed attempt,
and re-audits raw artifacts in a separate acceptance job. Twelve shards bound disk
and wall-clock requirements. Creating this workflow is not a passing result.
PX4 flight, browser/video rehearsal and final release acceptance remain unverified.

## Qualification rejection and next candidate (2026-09-21)

The first frozen 600-attempt protocol has finished and was rejected: 538 passed
attempts, 60 unsafe candidate missions, two candidate timeouts. Read
`docs/QUALIFICATION_FAILURE_ANALYSIS.md`; improved delivery did not override safety.
All original raw artifacts and the failed acceptance remain unchanged.

A full tier3 seed-200 reproduction found two UAVs descending onto the same charger.
Radio-isolated scouts now recover to separate airborne holding points instead of
requesting recharge without an energy need. The repaired tier3-200 and hard-200
runs had zero recorded safety violations; the formerly timed-out hard-308 mission
completed with a consistent, safe audit. Those three runs used source `6eccdc1e4dc983b8b77d3535d15924709fa87520ddab3654d48bd5efb256003f`
and remain observed-seed regressions. General simultaneous low-energy landing at a
single pad is not certified by that repair.

The next refinement excludes live leased tasks from relay repositioning. On observed
burst basic seeds 400/401, complete regressions delivered 100%, with operational
connectivity 95.0167% / 92.65% and safe audits. This is not a new statistical result.
A fresh epoch-1 protocol is registered in PRD section 13 with unused seed ranges
1200-1229, 1300-1309 and 1400-1409. Thresholds and scenario difficulty are unchanged.

Latest full test output before qualification-tool epoch extension:

```text
91 passed, 2 warnings in 8.20s
```

After the extension, both qualification test files passed (5 tests in 0.04s).
The rendered dashboard remained inaccessible to the review browser. A recorded
simulation video was generated from an audited development trajectory, with a
video/raw/source checksum receipt; it is not a browser rehearsal or PX4 recording.

PX4 exchanged real DDS messages but did not arm due to its GCS-presence health
check. A real local MAVLink heartbeat was added to the isolated simulator gate,
keeping that check enabled. Its flight result must be inspected independently.
