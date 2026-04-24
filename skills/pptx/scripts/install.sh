#!/usr/bin/env bash
# Bootstrap local dependencies for the pptx skill.
#
# Creates:
#   scripts/.venv/          — Python venv with requirements.txt
#   scripts/node_modules/   — npm packages from package.json (local, not global)
#
# System tools expected on PATH (not installed here — this script only
# CHECKS and prints install hints per the project plan §3.3):
#   - node 18+
#   - python3 3.10+
#   - soffice   (LibreOffice; required by pptx_to_pdf.py, pptx_thumbnails.py,
#                and md2pptx.js --via-marp)
#   - pdftoppm  (Poppler; required by pptx_thumbnails.py)
#
# Idempotent; safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

missing_host=0

say()     { printf '[install.sh] %s\n'   "$*"; }
warn()    { printf '[install.sh] WARN: %s\n' "$*" >&2; }
die()     { printf '[install.sh] ERROR: %s\n' "$*" >&2; exit 1; }

say "Checking host tools..."

# --- node ---
if ! command -v node >/dev/null 2>&1; then
    die "node not found. Install Node 18+ from https://nodejs.org/."
fi
NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    die "Node 18+ required; found v$NODE_MAJOR."
fi
say "node:    $(node --version)"

# --- python3 ---
if ! command -v python3 >/dev/null 2>&1; then
    die "python3 not found. Install Python 3.10+."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
case "$PY_VER" in
    3.1[0-9]|3.[2-9][0-9]) ;;
    *) die "Python 3.10+ required; found $PY_VER." ;;
esac
say "python3: $PY_VER"

# --- soffice (LibreOffice) ---
find_soffice() {
    for p in \
        "$(command -v soffice 2>/dev/null || true)" \
        /Applications/LibreOffice.app/Contents/MacOS/soffice \
        /opt/homebrew/bin/soffice \
        /usr/local/bin/soffice \
        /usr/bin/soffice ; do
        if [ -n "$p" ] && [ -x "$p" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

if SOFFICE=$(find_soffice); then
    say "soffice: $SOFFICE"
else
    warn "soffice (LibreOffice) NOT FOUND on PATH or in standard locations."
    warn "Required by:  pptx_to_pdf.py, pptx_thumbnails.py, md2pptx.js --via-marp"
    warn "Install:"
    warn "  macOS:   brew install --cask libreoffice"
    warn "  Debian:  sudo apt install libreoffice --no-install-recommends"
    warn "  Fedora:  sudo dnf install libreoffice"
    warn "Re-run this script after installing to verify."
    missing_host=1
fi

# --- pdftoppm (Poppler) ---
if command -v pdftoppm >/dev/null 2>&1; then
    say "pdftoppm: $(pdftoppm -v 2>&1 | head -1)"
else
    warn "pdftoppm (Poppler) NOT FOUND on PATH."
    warn "Required by:  pptx_thumbnails.py"
    warn "Install:"
    warn "  macOS:   brew install poppler"
    warn "  Debian:  sudo apt install poppler-utils"
    missing_host=1
fi

# --- Python venv ---
if [ ! -x ".venv/bin/python" ]; then
    say "Creating Python venv at scripts/.venv/..."
    python3 -m venv .venv
else
    say "Python venv already exists at scripts/.venv/"
fi
./.venv/bin/python -m pip install --quiet --upgrade pip
say "Installing Python requirements into scripts/.venv/ ..."
./.venv/bin/pip install --quiet -r requirements.txt

# --- npm install ---
if [ ! -f "package.json" ]; then
    die "package.json missing in $SCRIPT_DIR."
fi
say "Installing npm dependencies into scripts/node_modules/ ..."
npm install --no-fund --no-audit --silent

if [ ! -x "./node_modules/.bin/mmdc" ]; then
    die "scripts/node_modules/.bin/mmdc was not installed."
fi
say "mmdc:    $(./node_modules/.bin/mmdc --version 2>&1 | head -1)"

echo ""
if [ "$missing_host" -eq 0 ]; then
    say "All dependencies installed and verified."
else
    warn "Local deps OK, but some system tools are missing (see warnings above)."
    warn "Commands that need them will fail with a clear error until you install them."
fi
echo ""
say "Usage:"
say "  node scripts/md2pptx.js INPUT.md OUTPUT.pptx"
say "  node scripts/md2pptx.js INPUT.md OUTPUT.pptx --via-marp   # needs soffice"
say "  ./.venv/bin/python scripts/pptx_to_pdf.py DECK.pptx"
say "  ./.venv/bin/python scripts/pptx_thumbnails.py DECK.pptx GRID.jpg"
