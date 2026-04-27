#!/usr/bin/env bash
# Bootstrap the per-skill .venv for transcript-fetcher.
#
# Repo policy (CLAUDE.md §1): NEVER pip install globally. Each skill
# owns its own .venv in scripts/.venv. Re-running this script is
# idempotent — it reuses an existing venv if present.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "[install.sh] Created .venv"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

echo "[install.sh] OK — installed into $HERE/.venv"
echo "[install.sh] yt-dlp version: $(python -m yt_dlp --version 2>/dev/null || echo 'unavailable')"
