# Versioned analytic environment

The default remains `legacy-v1`. The explicit `environment_model.version:
analytic-v2` profile is implemented in `src/resilience/environment.py` and connected
to the runtime, planner, radio and UAV. Run the declared fixture with:

```bash
python src/main.py --headless --scenario scenarios/analytic_environment_v2.yaml --seed 100 --out logs/environment
python tools/audit_evidence.py logs/environment
```

## Model and limits

- Terrain is a datum plane plus x-aligned triangular ridges. All heights and
  positions are metres. Piecewise-linear segment checks include every ridge
  breakpoint, so a thin ridge is not skipped by a coarse ray sampler. This is
  synthetic analytic terrain, not a digital elevation survey.
- The A* map excludes terrain above the shared maximum-altitude clearance ceiling.
  Radio LOS uses actual vehicle altitude and a 2 m GCS antenna. Circular obstacles
  remain conservative infinite-height no-fly/radio proxies, not detailed buildings.
- UAV altitude is datum height. Normal cruise targets a fixed height above local
  terrain, capped by the configured datum-altitude ceiling. Vertical rate remains
  at most 5 m/s. The horizontal command ramps at the smaller of declared acceleration
  and the equivalent 30-degree tilt limit, with braking before waypoints. A hard
  safety hold can stop motion abruptly; this is a kinematic simulator and does not
  establish physically feasible emergency braking or calibrated attitude dynamics.
- The nadir camera has a circular footprint of `AGL * tan(FOV / 2)`. Acquisition
  additionally requires configured AGL/speed limits, target visibility, the original
  survey-radius limit and continuous dwell. Moving away resets dwell. Synthetic
  confidence remains an additional simulator requirement, not a detection ROC.
- Mapped area is the union of grid cells whose centres fall in a valid stationary
  footprint and are visible. Boundary cells are clipped to the world. This is a
  resolution-dependent area estimate, not the exact continuous union of footprints.
  It is separate from acquired PoIs and full observations delivered to the GCS.
- Base hover/cruise energy remains the configured power model. Extra watts are
  `(mass + payload) * g * max(climb_rate, 0) / efficiency + 20 * payload + c * airspeed^3`.
  No descent energy regeneration is credited. The 20 W/kg payload term, drag
  coefficient and efficiency are declared assumptions, not measured calibration.
  Return budgeting conservatively adds worst-direction wind and continuous maximum
  climb cost; this is not a guarantee for real batteries or prolonged detours.

`tools/environment_audit.py` reconstructs footprint/AGL/visibility and covered cells
from the manifest and raw trajectories without importing simulation classes.
`tools/audit_evidence.py` also checks swept obstacle/terrain penetration when the
new manifest supplies that geometry. Old logs without geometry cannot establish
those new checks.

## Observed evidence

The first complete fixture attempt failed JSON export because a NumPy scalar entered
the battery-derived count. It is recorded in `validation/environment_attempts.json`
and contributes no accepted metrics. Conversion to native scalar values and a
runtime-export regression test address the failure.

`validation/analytic_environment_final.json` records full 120 s runs for seeds
100 and 101 at source hash
`d461dd85b1ed9d49520b115ab7f3e7d60817844ce1722818aa80215ddbb31d12`.
Each delivered both tasks, with zero audited separation, geofence, depleted-battery,
terrain-penetration or obstacle-penetration samples. Cell-centre mapped estimates
were 14,300 and 8,700 square metres respectively. This two-seed deterministic fixture
is not broad environmental qualification or a comparison with measured PX4 motion.

The analytic tests cover a thin terrain shadow, infeasible over-ceiling terrain,
footprint/AGL/speed/occlusion rejection, clipped area union without double counting,
energy units, ideal acceleration timestep convergence, JSON export, and dwell reset.
PX4 calibration, general 3D obstacle meshes, terrain-aware altitude optimization,
long battery missions and large-sample profile qualification remain open.
