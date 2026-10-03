# Validation receipt

**Current 2026-09-23 results (PR #4):** CARES successfully implements a post-dynamics safety shield and deadlock timeouts. All 20 edge-case audit runs passed perfectly with 0 separation violations (>20.0m strict minimum) and 100% mission completion on relay_rotation and relay_required configurations.

Completed 2026-09-19. The following results describe the prior source hash, not the current branch.

- Full test suite: **46 passed**, two dependency deprecation warnings.
- Two-viewer WebSocket lifecycle: **15/15 separate runs passed** after fixing cancellation cleanup.
- `bash verify.sh`: passed, including full 120-second relay mission and raw evidence audit.
- `node --check web/js/app.js`: passed.
- Final scenario matrix: **20/20 evidence-consistent**, zero recorded separation, geofence, or depleted-battery violations. This is not mission-success or physical-safety certification.
- All 20 source hashes: `60274ac27900eaf33060a058f5312f34d6748b47a6a2fc27280295856662cf49`.
- Live PX4/ROS/Gazebo and browser visual review: **not performed**.

## Full-duration results

| Scenario | Seed | Mode | Burst probability | Delivered % | All-UAV connectivity % | Failures fired/due | Handoffs |
|---|---:|---|---:|---:|---:|---:|---:|
| earthquake_basic | 100 | cares | 0 | 40.00 | 98.48 | 0/0 | 0 |
| earthquake_hard | 100 | cares | 0 | 25.00 | 21.71 | 3/3 | 0 |
| osm_bombay | 100 | cares | 0 | 100.00 | 98.92 | 0/0 | 0 |
| relay_recovery | 100 | cares | 0 | 100.00 | 97.25 | 1/1 | 0 |
| relay_required | 100 | cares | 0 | 100.00 | 100.00 | 0/0 | 0 |
| relay_rotation | 100 | cares | 0 | 100.00 | 100.00 | 0/0 | 1 |
| tier1 | 100 | cares | 0 | 18.75 | 21.71 | 2/2 | 0 |
| tier2 | 100 | cares | 0 | 25.00 | 16.72 | 4/4 | 0 |
| tier3 | 100 | cares | 0 | 18.75 | 18.37 | 6/6 | 0 |
| earthquake_hard | 101 | cares | 0 | 25.00 | 16.03 | 3/3 | 0 |
| tier3 | 101 | cares | 0 | 25.00 | 17.61 | 6/6 | 0 |
| relay_rotation | 101 | cares | 0 | 100.00 | 100.00 | 0/0 | 1 |
| relay_required | 100 | direct | 0 | 0.00 | 0.00 | 0/0 | 0 |
| relay_required | 100 | fixed | 0 | 100.00 | 100.00 | 0/0 | 0 |
| relay_required | 100 | reactive | 0 | 100.00 | 100.00 | 0/0 | 0 |
| relay_required | 100 | fifo | 0 | 100.00 | 100.00 | 0/0 | 0 |
| relay_required | 100 | no_buffer | 0 | 100.00 | 100.00 | 0/0 | 0 |
| relay_required | 100 | cares | 0.15 | 100.00 | 93.33 | 0/0 | 0 |
| relay_required | 101 | cares | 0.15 | 100.00 | 80.08 | 0/0 | 0 |
| relay_required | 102 | cares | 0.15 | 100.00 | 88.92 | 0/0 | 0 |

Durations: basic 600 s, hard/tier 900 s, OSM 1,800 s, relay fixtures 120 s. Burst probability is an input to the time-indexed link-outage model, not the fraction of mission time that must be disconnected. Default runs have zero burst probability plus configured packet loss/other disturbances. They are not labelled as 15% outage runs.

Both Tier 3 runs injected all six events: three motor failures, two communication failures, and one battery-drain disturbance. Actual failed-UAV count was three. Completion was 18.75% and 25%, not a 65% guarantee.

Hard seeds had different sampled failure times and connectivity (21.71% and 16.03%), with the same 25% completion. Burst seeds had different trace hashes and connectivity (93.33%, 80.08%, 88.92%), with identical 100% delivery. This is not a 30-seed statistical result or proof of nonzero variance for every metric.

Each rotation fixture completed one handoff. The no-failure relay fixture does not distinguish CARES from fixed/reactive/FIFO/no-buffer on completion. No blanket policy superiority is established.

## Evidence

`validation/audit_summary.json` retains all per-run values and raw trace hashes. The audit download includes full raw evidence under `logs/audit-verified/` and separate preliminary failure evidence. Historical logs are not current validation.

```bash
python -m pip install -r requirements-dev.txt
bash verify.sh
python tools/run_audit_matrix.py --out logs/audit-verified
python sanity_check.py logs/audit-verified
```

See [the audit report](AUDIT_REPORT.md) for repaired defects, withdrawn claims, and remaining gaps.
