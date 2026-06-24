#!/usr/bin/env bash
# html2md skill installer (bead 022-01 baseline; expanded in 022-07).
#
#   bash install.sh                 # venv + python deps + node deps
#   bash install.sh --with-chrome   # + Playwright Chromium (soft-optional engine)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "[html2md] creating .venv ..."
python3 -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip

# requirements.txt may be comment-only in early beads — only run if it has a real line.
if grep -qvE '^\s*(#.*)?$' requirements.txt 2>/dev/null; then
  echo "[html2md] installing python deps ..."
  ./.venv/bin/python -m pip install -r requirements.txt
fi

if [ "${1:-}" = "--with-chrome" ]; then
  echo "[html2md] installing Chrome engine (Playwright) ..."
  ./.venv/bin/python -m pip install -r requirements-chrome.txt
  ./.venv/bin/python -m playwright install chromium
fi

if [ -f package.json ]; then
  echo "[html2md] installing node deps ..."
  npm install --silent
fi

echo "[html2md] done."
