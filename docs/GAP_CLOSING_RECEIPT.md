# Gap-closing verification receipt — 2026-09-20

## Scope and outcome

28 full-duration simulations on one frozen source hash, independently recomputed from raw telemetry. All 28 evidence checks passed; all 28 recorded zero separation-violation frames, geofence violations, and depleted-battery samples. These checks do not certify physical safety or mission success. There are only a few seeds per scenario, not hundreds.

Source SHA256: `154961a940841f2e3acff8fd5515259bb9186e09079fa05ef214914cc1f7848c`.

Basic delivery rose from 40% to 100% for seed 100 and remained 100% for held-out seeds 101 and 102. Hard seed 100 delivery rose from 25% to 43.75%, but all-UAV connectivity fell from 21.71% to 13.30%. Basic connectivity also fell from 98.48% to 97.65%. These are trade-offs, not blanket superiority. Hard connectivity remains an open weakness. The delivery metric requires full observation receipt at the GCS; intermittent buffering can deliver data despite low continuous connectivity.

The code prevents duplicate speculative relay replacements and frees scouts when the original relay reappears. Neighbor hearsay suppresses suspicion but never suppresses explicit retirement requests. Initial relay spacing and task admission derive from radio range. Five targeted regression tests cover these mechanisms and fault accounting.

## P0: WebSocket lifecycle

The test was already restored in merged PR #3. The prior fix handled asynchronous cancellation cleanup and shared mission lifetime rather than silencing assertions. Fresh isolated execution passed: `1 passed, 2 warnings in 1.39s`. Full gate execution on the final source printed:

```text
51 passed, 2 warnings in 6.81s
```

Warnings concern dependency deprecations (Starlette/httpx and AnyIO), not skipped assertions. The full current test file is reproduced verbatim:

```python
from fastapi.testclient import TestClient
from src import server


def receive_until(ws, predicate):
    for _ in range(30):
        state = ws.receive_json()
        if predicate(state):
            return state
    raise AssertionError('Expected WebSocket state was not received')


def test_two_viewers_preserve_mission_and_share_commands(monkeypatch):
    sim = server.SimState()
    sim.init('scenarios/relay_required.yaml')
    sim.mission.paused = True
    monkeypatch.setattr(server, 'sim', sim)
    with TestClient(server.app) as client:
        assert client.get('/').status_code == 200
        with client.websocket_connect('/ws') as one:
            initial = one.receive_json()
            with client.websocket_connect('/ws') as two:
                second = two.receive_json()
                assert second['generation'] == initial['generation']
                assert second['sim_time'] == initial['sim_time']
                one.send_json({'action': 'kill_uav', 'uav_id': 0})
                state = receive_until(two, lambda s: s['uavs'][0]['state'] == 'failed')
                assert state['paused']
                one.send_json({'action': 'reset'})
                state = receive_until(two, lambda s: s['generation'] > initial['generation'])
                assert state['world']['name'] == initial['world']['name']
                assert state['uavs'][0]['state'] != 'failed'
                one.send_json({'action': 'pause'})
                paused = receive_until(two, lambda s: s['paused'])
                assert two.receive_json()['sim_time'] == paused['sim_time']
        with client.websocket_connect('/ws') as reconnect:
            assert reconnect.receive_json()['generation'] == state['generation']
    assert sim.clients == 0
```

## P0: fault counts — corrected premise

`src/core/world.py::check_failures` triggers due events. In `src/core/uav.py::inject_failure`, `battery_critical` changes the drain multiplier to 20 without setting `FAILED`. Thus the legacy counter was one below the number of scripted disturbances even when every event fired. In the current `src/resilience/runtime.py` injector, a communication failure sets `radio_failed` rather than killing the aircraft. Counting every disturbance as a dead UAV would misrepresent the simulation.

Reports now distinguish scheduled events, injected events, permanent failed aircraft, radio-fault aircraft, and battery-fault aircraft. The independent auditor checks these against raw events and final state. Fresh `degradation_results.json` contains six 900-second runs, seeds 100/101, actual burst probability 0.15. Tier 1 fired 2/2 events, Tier 2 4/4, Tier 3 6/6 in both seeds. Permanent failed-UAV counts are 1, 2, 3 respectively; the remaining events are radio faults and battery drain. Randomized event times differ between seeds; equal completion in some runs does not establish nonzero completion variance.

The old degradation scripts used obsolete batch options and one contained hardcoded Tier 1 results. Both now invoke `tools/degradation.py`; no prefilled outcome is used.

## P0/P3: proposal accuracy

Both unsupported generic completion claims (99.8% and 93.3%) were withdrawn. The current proposal points to named scenario results and explains why inspectable heuristics are used before RL. It explicitly disclaims active proven CBF, complete CBBA, or ORCA guarantees. Legacy modules and documents are not proof of active runtime behavior.

## P1/P2: flight-stack boundary and reproducibility

Environment inspection returned:

```json
{"executables":{"docker":null,"px4":null,"ros2":null,"colcon":null,"gz":null},"python_modules":{"rclpy":false,"px4_msgs":false}}
```

No live PX4 connection, DDS message exchange, takeoff, fault-response flight, or landing was executed. `docs/SITL.md` describes the boundary. A completed flight scenario and hundreds-of-seeds statistical validation remain outstanding. Do not claim either based on mocks or imports.

`verify.sh` passed locally using installed test dependencies. `verify_cold.sh` creates a fresh clone and venv, unsets Python path overrides, disables pip caching, and runs the gate. A dedicated GitHub Actions job executes this independently. Consult the PR checks for its actual result; this document does not presume a future CI pass.

## Current results

| Scenario | Seed | Mode | Burst | Delivery % | Connectivity % | Events fired/due |
|---|---:|---|---:|---:|---:|---:|
| earthquake_basic | 100 | cares | 0 | 100.00 | 97.65 | 0/0 |
| earthquake_hard | 100 | cares | 0 | 43.75 | 13.30 | 3/3 |
| osm_bombay | 100 | cares | 0 | 100.00 | 100.00 | 0/0 |
| relay_recovery | 100 | cares | 0 | 100.00 | 94.75 | 1/1 |
| relay_required | 100 | cares | 0 | 100.00 | 100.00 | 0/0 |
| relay_rotation | 100 | cares | 0 | 100.00 | 100.00 | 0/0 |
| tier1 | 100 | cares | 0 | 37.50 | 13.51 | 2/2 |
| tier2 | 100 | cares | 0 | 37.50 | 13.87 | 4/4 |
| tier3 | 100 | cares | 0 | 37.50 | 12.50 | 6/6 |
| earthquake_hard | 101 | cares | 0 | 43.75 | 13.59 | 3/3 |
| tier3 | 101 | cares | 0 | 37.50 | 13.54 | 6/6 |
| relay_rotation | 101 | cares | 0 | 100.00 | 100.00 | 0/0 |
| relay_required | 100 | direct | 0 | 0.00 | 0.00 | 0/0 |
| relay_required | 100 | fixed | 0 | 100.00 | 100.00 | 0/0 |
| relay_required | 100 | reactive | 0 | 100.00 | 100.00 | 0/0 |
| relay_required | 100 | fifo | 0 | 100.00 | 100.00 | 0/0 |
| relay_required | 100 | no_buffer | 0 | 100.00 | 100.00 | 0/0 |
| relay_required | 100 | cares | 0.15 | 100.00 | 76.67 | 0/0 |
| relay_required | 101 | cares | 0.15 | 100.00 | 70.00 | 0/0 |
| relay_required | 102 | cares | 0.15 | 100.00 | 80.00 | 0/0 |
| earthquake_basic | 101 | cares | 0 | 100.00 | 97.82 | 0/0 |
| earthquake_basic | 102 | cares | 0 | 100.00 | 97.77 | 0/0 |
| tier1 | 100 | cares | 0.15 | 37.50 | 11.98 | 2/2 |
| tier1 | 101 | cares | 0.15 | 43.75 | 12.92 | 2/2 |
| tier2 | 100 | cares | 0.15 | 37.50 | 11.93 | 4/4 |
| tier2 | 101 | cares | 0.15 | 43.75 | 12.54 | 4/4 |
| tier3 | 100 | cares | 0.15 | 43.75 | 12.48 | 6/6 |
| tier3 | 101 | cares | 0.15 | 43.75 | 12.60 | 6/6 |

The 20-run matrix uses scenario defaults (zero burst probability) except three explicit 0.15 burst runs. The six degradation runs separately use 0.15. Two held-out basic runs use scenario defaults. Easy and burst runs are labelled separately; this is not a single official Monte Carlo aggregate.

Full exact JSON, including trace hashes, is in `validation/gap_summary.json` and `degradation_results.json`. Raw per-run directories are recorded in each row; regenerate with the commands below. Previous baseline values remain in `validation/audit_summary.json` and the historical section of `docs/VALIDATION.md`.

```bash
bash verify_cold.sh
python tools/run_audit_matrix.py --out logs/audit-gap-final
python tools/degradation.py --seeds 2 --workers 2 --out logs/audit-gap-degradation-final --result degradation_results.json
```

## Remaining priorities

## Publication and cold-checkout receipts

Published as draft PR #4, runtime commit `30b993c284d229ce3643d74d5dfafe05331763b2`. GitHub Actions run `35489617920` passed both `python` and `cold-checkout`. Cold-checkout job `106022185183` printed:

```text
51 passed, 2 warnings in 8.68s
```

Its raw relay trace hash is `45cbb535ad9d80db4ee37bd6d36ff8ef57805bfc01f9124060e3141ccb00ab0a`, exactly matching the local gate trace. The cold checkout source hash is `2363560016985ee91be20a55eb0378cb2eaf86c0e44929d7ae508dc4a591a1cb`. It differs from the 28-run local snapshot because GitHub retains five empty `__init__.py` files: `src/`, `src/algorithms/`, `src/comms/`, `src/core/`, and `src/visualization/`. Every one has empty-blob SHA `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`. All 105 local tracked file blobs match their published counterparts. Old remote log artifacts also remain; they are not current evidence. Do not represent the local and remote source hashes as identical.

Literal local publication preparation output (local snapshot history differs from GitHub history):

```text
commit 890062ca35e0c3f625371fe98783de06451aec8f
Author: Codex <codex@localhost>
Date:   Sun Sep 20 07:36:27 2026 +0300

    Improve relay recovery and audit fault semantics with 28 full runs
On branch codex/closing-gap
nothing to commit, working tree clean
```

Literal code-location checks:

```text
tools/degradation.py:12:def main(argv=None):
src/core/world.py:267:    def check_failures(self, sim_time: float) -> List[ScheduledEvent]:
src/core/uav.py:465:    def inject_failure(self, failure_type: str, sim_time: float):
src/core/uav.py:467:        if failure_type == "battery_critical":
src/resilience/runtime.py:124:                if fail.event_type=='comms_failure':u.radio_failed=True
```

## Remaining priorities (not completed)

Improve sustained hard-scenario connectivity without erasing real fault effects or sacrificing delivery; then repeat paired-seed audits. Run the bridge on an equipped flight stack. Expand seeds only with adequate compute and publish the actual distributions. A public competitor recheck was scheduled in four days; the private competitor will not be probed.
