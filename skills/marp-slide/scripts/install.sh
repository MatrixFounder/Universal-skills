#!/usr/bin/env bash
# Install all external dependencies needed by render.py — locally under scripts/.
# Creates:
#   scripts/.venv/          (Python venv, stdlib only — no pip deps beyond pip itself)
#   scripts/node_modules/   (marp-cli + mermaid-cli + Puppeteer Chromium)
# Idempotent; safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[install.sh] Checking host tools..."

# --- Node.js ---
if ! command -v node >/dev/null 2>&1; then
    echo "[install.sh] ERROR: Node.js not found. Install Node 18+ from https://nodejs.org/ first." >&2
    exit 1
fi
NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "[install.sh] ERROR: Node.js 18+ required; found v$NODE_MAJOR." >&2
    exit 1
fi
echo "[install.sh] Node.js: $(node --version)"

# --- Python (host) ---
if ! command -v python3 >/dev/null 2>&1; then
    echo "[install.sh] ERROR: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
case "$PY_VER" in
    3.1[0-9]|3.[2-9][0-9]) ;;
    *) echo "[install.sh] ERROR: Python 3.10+ required; found $PY_VER." >&2; exit 1;;
esac
echo "[install.sh] Python: $PY_VER"

# --- Python venv ---
if [ ! -x ".venv/bin/python" ]; then
    echo "[install.sh] Creating Python venv at scripts/.venv/..."
    python3 -m venv .venv
else
    echo "[install.sh] Python venv already exists at scripts/.venv/"
fi
# No pip packages needed (stdlib only), but upgrade pip for hygiene.
./.venv/bin/python -m pip install --quiet --upgrade pip

# --- package.json (local npm project) ---
if [ ! -f "package.json" ]; then
    echo "[install.sh] Writing scripts/package.json..."
    cat > package.json <<'EOF'
{
  "name": "marp-slide-renderer",
  "version": "1.0.0",
  "private": true,
  "description": "Local dependencies for the marp-slide skill renderer. Installed under scripts/node_modules/; never published.",
  "dependencies": {
    "@marp-team/marp-cli": "^4.3.1",
    "@mermaid-js/mermaid-cli": "^11.4.0"
  }
}
EOF
fi

# --- Local npm install ---
echo "[install.sh] Installing local npm dependencies in scripts/node_modules/ (this may download Chromium via Puppeteer on first run)..."
npm install --no-fund --no-audit

# --- Sanity-check local binaries ---
if [ ! -x "./node_modules/.bin/marp" ]; then
    echo "[install.sh] ERROR: scripts/node_modules/.bin/marp was not installed." >&2
    exit 1
fi
if [ ! -x "./node_modules/.bin/mmdc" ]; then
    echo "[install.sh] ERROR: scripts/node_modules/.bin/mmdc was not installed." >&2
    exit 1
fi
echo "[install.sh] Local marp: $(./node_modules/.bin/marp --version 2>&1 | head -1)"
echo "[install.sh] Local mmdc: $(./node_modules/.bin/mmdc --version 2>&1 | head -1)"

# --- Smoke test ---
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
cat > "$TMPDIR/smoke.md" <<'EOF'
---
marp: true
---
# Smoke

```mermaid
mindmap
  root((T))
    A
      a1
    B
      b1
```
EOF

echo "[install.sh] Running smoke test via .venv Python..."
./.venv/bin/python "$SCRIPT_DIR/render.py" "$TMPDIR/smoke.md" --format pdf --output "$TMPDIR/smoke.pdf"

if [ -s "$TMPDIR/smoke.pdf" ]; then
    SMOKE_SIZE=$(stat -f%z "$TMPDIR/smoke.pdf" 2>/dev/null || stat -c%s "$TMPDIR/smoke.pdf")
    echo "[install.sh] OK — smoke test produced $SMOKE_SIZE bytes"
else
    echo "[install.sh] ERROR: smoke test produced empty or missing PDF." >&2
    exit 1
fi

echo ""
echo "[install.sh] All dependencies installed and verified."
echo "[install.sh] Render a deck with:"
echo "             scripts/render INPUT.md [--format pptx|pdf|html|png|jpeg]"
echo "             (or: scripts/.venv/bin/python scripts/render.py INPUT.md ...)"
