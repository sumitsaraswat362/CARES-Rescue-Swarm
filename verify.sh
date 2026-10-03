#!/usr/bin/env bash
set -euo pipefail
PYTHON="${PYTHON:-$(command -v python3 || command -v python)}"
"$PYTHON" tools/check_claims.py
"$PYTHON" -m pytest tests -q
"$PYTHON" src/main.py --headless --scenario scenarios/relay_required.yaml --seed 100 --out logs/verify
"$PYTHON" tools/audit_evidence.py logs/verify
