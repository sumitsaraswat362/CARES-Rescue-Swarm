# Qualification v1 rejection and repair status

Evidence date: 2026-09-21. Candidate: `3138a8a50b4ed91a7e17d114fe0294bd7541fc4e`.
Runtime SHA-256: `4a03210ff281d59ca1dfd78377e58749224fb2de424bbc669ede98f79fb39d13`.

## Verdict

**Rejected. Do not describe this candidate as safety-qualified or ready to submit.**
The immutable 600-attempt workflow is complete. Its result is not a passing 600-run
qualification: 598 processes completed, 538 attempts passed the recorded audit,
60 candidate runs violated separation, and 2 candidate processes timed out at
1,800 wall-clock seconds. All 300 reference attempts passed. The candidate had
238 passed attempts, 60 unsafe completed runs and 2 timeouts.

Authoritative receipts:
- `validation/qualification_v1_runs.json`: 600 literal per-attempt records extracted
  from retained CI artifacts, including errors and independently recomputed metrics.
- `validation/qualification_v1_acceptance.json`: the unmodified rejected acceptance
  result (65 errors; this includes missing-pair and statistical errors, not 65 crashes).
- `validation/qualification_v1_summary.json`: descriptive grouping; unsafe completed
  runs remain in the means, timed-out processes have no fabricated mission metrics.
- Original run: https://github.com/sumitsaraswat362/UAV-X-Resilient-Swarm/actions/runs/35534036901
- Artifact inspection: https://github.com/sumitsaraswat362/UAV-X-Resilient-Swarm/actions/runs/35553116359

## Reproduced separation failure

The independent local reproduction of tier3, seed 200 agrees with the retained
candidate result: 2,059 violating frames, 0 m minimum separation, all six scheduled
disturbances injected. At t=487.8 s UAV 5 was at [150,1000,0.5] and UAV 7 at
[150,1000,5.0], both in recharge state. UAV 5's radio had failed and its battery was
190 Wh; UAV 7 was returning after the battery-drain disturbance. These positions
come from raw telemetry, not the summary counter.

`Agent.tick()` routed an isolated scout through `return_home()`, which enters RTL
and subsequently recharge, even with substantial energy remaining. Radio failure
then caused repeated takeoff/return behavior. The charger-slot accounting limited
which aircraft gained charge, but did not exclude another aircraft from the same
landing column. The earlier relay-only holding repair did not cover scouts.

The repair separates **contact recovery** from **energy return**. An isolated scout
flies to an obstacle-cleared, per-ID holding point outside the charger column and
keeps its flight layer. Restored contact releases the hold. Energy-reserve return
continues to take precedence. No extra charger, landing pad, battery or aircraft is
added. This removes the reproduced unnecessary-landing mechanism; it is not a
certification of arbitrary simultaneous low-energy returns to a single charger.
A general multi-aircraft landing/ground-service controller remains a limitation.

## Path-search timeout investigation

Timed-out jobs: `confirmation-earthquake_hard-308-candidate` and
`qualification-tier2-227-candidate`. No completed metrics are assigned to them.
The grid planner could round an obstacle-clear exact endpoint onto an obstructed
grid node, then exhaust the grid looking for an unreachable goal. The repaired
planner selects a clear nearby connector and retains negative results only for an
exhausted search of the static grid. Its exact-endpoint regression exercises this
mechanism. Full reruns, rather than this code change alone, determine whether the
original timeout is resolved. Do not present this mechanism as a profiled cause of
every slow run without the corresponding trace.

## Performance interpretation

On 30 qualification seeds, the rejected candidate's hard-family delivered mean
was 63.3333%, versus 42.5% reference; the paired mean difference was +20.8333 pp
(95% bootstrap interval +17.9167 to +24.1667 pp). These are **unsafe-candidate
results**, not an accepted performance claim. The burst basic family's operational
connectivity difference was -5.83 pp (interval -7.9817 to -3.94), also failing the
implemented 2 pp non-inferiority gate. Do not remove the failed family or relax the
gate after seeing results.

All seeds 200-229, 300-309 and 400-409 have now been examined. They may be used for
regression testing, but are no longer held-out confirmation for a repaired policy.
A new immutable protocol and unused confirmation seeds are required before claiming
that the repaired source is statistically qualified.

## Flight evidence

PX4 run 35532841043 built the pinned stack and exchanged 19,538 position messages,
479 status messages and 180 ACKs. It never armed. There were 85 arm acknowledgements
with result 1 (temporarily rejected), and PX4 reported no GCS connection. The
measured pose remained near the ground; the final bridge result was false.
The repair adds an actual MAVLink GCS heartbeat to the isolated SITL runner, instead
of disabling the GCS health requirement. An interface connection is not a flight.
The next flight attempt must independently establish arm, takeoff, motion and landing.
