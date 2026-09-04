#!/usr/bin/env bash
# Run every check CI runs. Expects requirements-dev.txt installed in the active interpreter.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

echo "== ruff format"; "$PYTHON" -m ruff format --check .
echo "== ruff check";  "$PYTHON" -m ruff check .
echo "== mypy";        "$PYTHON" -m mypy
echo "== compile";     "$PYTHON" -m compileall -q src scripts tests
echo "== shell";       bash -n run.sh
echo "== sources";     "$PYTHON" src/builder.py validate
echo "== build";       "$PYTHON" src/builder.py build --output "$SCRATCH/v1"
echo "== rebuild";     "$PYTHON" src/builder.py build --output "$SCRATCH/v1" --check
echo "== tests";       "$PYTHON" -m unittest discover -s tests -t . "$@"
echo "All checks passed."
