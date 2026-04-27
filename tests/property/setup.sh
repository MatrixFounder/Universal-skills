#!/usr/bin/env bash
# Bootstrap a Python venv for the property-based fuzz tests (q-5).
#
# The fuzzer drives the per-skill CLIs as black boxes — each skill's
# own .venv must already exist (run skills/<skill>/scripts/install.sh
# first).
#
# Usage: bash tests/property/setup.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi

./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "tests/property: setup complete (venv at $(pwd)/.venv)"
