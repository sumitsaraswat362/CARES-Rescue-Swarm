# Installation and reproducibility

Python 3.10+; run all commands from the repository root.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python src/main.py --headless --scenario scenarios/relay_required.yaml --out logs/current
```

For the web dashboard:

```bash
python -m uvicorn src.server:app --host 127.0.0.1 --port 8000
```

For paired benchmarks:

```bash
python run_batch.py --scenario scenarios/relay_recovery.yaml --seeds 5 --out logs/benchmarks
```

No ROS installation is needed for the lightweight simulator or pure adapter tests.
PX4 integration instructions are in `docs/SITL.md`. A missing ROS dependency is an
integration prerequisite, not a passing flight test. Scripts fail with nonzero status
on runtime/test errors. Do not use archived degradation outputs to evaluate v2.
