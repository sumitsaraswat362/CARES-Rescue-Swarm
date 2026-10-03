#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
scratch="$(mktemp -d "${CARES_COLD_ROOT:-${TMPDIR:-/tmp}}/cares-cold.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
git clone --quiet --no-local "$root" "$scratch/repo"
cd "$scratch/repo"
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
python3 -m venv "$scratch/venv"
export PATH="$scratch/venv/bin:$PATH"
python -m pip install --no-cache-dir -r requirements-dev.txt
git log -1
git status --short
bash verify.sh
