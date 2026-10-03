# CARES reviewer quick-start

## Read the status first

The competitive branch is an experimental review candidate, not an accepted release.
Start with `docs/QUALIFICATION_FAILURE_ANALYSIS.md`. The first full 600-attempt batch
was rejected; development repair runs do not overwrite that result. Use the source
hash in each receipt when reproducing a number.

## Run a small complete mission

Python 3.12 is used by CI. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
bash verify.sh
```

This runs the structured claims check, actual tests, a full relay-required mission,
and an independent raw-evidence audit. It fails on discrepancies. For a disposable
cold installation with no pip cache, run `bash verify_cold.sh`.

Inspect `logs/verify/run_manifest.json`, `final_report.json`, `events.jsonl` and
`raw_trace.jsonl`. Survey completion requires geometry and continuous dwell at the
real target. Delivered completion requires a matching full observation at the GCS.
Zero separation violations is not a measured physical collision count.

## Dashboard and offline replay

```bash
python -m uvicorn src.server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in two tabs. Check shared pause/reset/failure receipts and
reconnect. The backend integration tests exercise this protocol, but the remote
review browser could not access the local server (`ERR_BLOCKED_BY_CLIENT`). Three
visual cold rehearsals remain unverified.

Open `web/replay.html` locally and choose the exported `replay.jsonl`, then the
manifest and optional events file using the labelled file inputs. This offline
viewer has no external JavaScript dependency. The live 3D dashboard does use a CDN.

A separate recorded simulation video can be reproduced with FFmpeg installed:

```bash
python tools/render_evidence_video.py PATH_TO_AUDITED_RUN --out replay.mp4
```

It shows actual recorded positions and packet-supported task receipts, with a
checksum receipt. It is a simulation replay, not a browser test or flight video.

## Evaluate a frozen candidate

Use two clean checkouts and an output directory outside both:

```bash
python tools/qualification.py freeze --reference PATH_TO_REFERENCE --candidate PATH_TO_CANDIDATE --out protocol.json
python tools/qualification.py run protocol.json --out evidence --workers 2
python tools/accept_qualification.py protocol.json evidence --out acceptance.json
```

The original seed ranges are now observed regression seeds. Before a new claim of
held-out qualification, register a new protocol with unused confirmation seeds.
Do not rerun the rejected v1 plan and label it fresh confirmation. The CI workflow
retains raw shards; review the attempted/completed/unsafe/timeout counts separately.

## Flight boundary

See `docs/SITL.md` and `.github/workflows/px4_sitl.yml`. Run only in an isolated
software simulator. A successful build and DDS exchange do not pass the flight
gate. Actual measured arm, movement, return and disarm must appear in the logs.
The one-vehicle waypoint gate does not establish the requested three-UAV mission,
physical RF behavior, BVLOS approval, or field safety.
