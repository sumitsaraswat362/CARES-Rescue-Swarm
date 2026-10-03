#!/usr/bin/env bash
set -euo pipefail
python -m pytest tests -q
python src/main.py --headless --scenario scenarios/relay_required.yaml --out logs/cold-test
