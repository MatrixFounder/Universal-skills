#!/usr/bin/env bash
# Bootstrap local dependencies for the pdf skill.
#
# Creates:
#   scripts/.venv/ — Python venv with requirements.txt
#
# System tools expected on PATH (checked, not installed):
#   - python3 3.10+
#   - pango + cairo + gdk-pixbuf (weasyprint runtime; required by md2pdf.py)
#
# Idempotent; safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

missing_host=0

say()  { printf '[install.sh] %s\n'        "$*"; }
warn() { printf '[install.sh] WARN: %s\n'  "$*" >&2; }
die()  { printf '[install.sh] ERROR: %s\n' "$*" >&2; exit 1; }

say "Checking host tools..."

if ! command -v python3 >/dev/null 2>&1; then
    die "python3 not found. Install Python 3.10+."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
case "$PY_VER" in
    3.1[0-9]|3.[2-9][0-9]) ;;
    *) die "Python 3.10+ required; found $PY_VER." ;;
esac
say "python3: $PY_VER"

# --- Python venv ---
if [ ! -x ".venv/bin/python" ]; then
    say "Creating Python venv at scripts/.venv/..."
    python3 -m venv .venv
else
    say "Python venv already exists."
fi
./.venv/bin/python -m pip install --quiet --upgrade pip
say "Installing Python requirements into scripts/.venv/ ..."
./.venv/bin/pip install --quiet -r requirements.txt

# --- weasyprint native libs probe (pango, cairo, gdk-pixbuf) ---
# Run weasyprint's ffi binding — if pango is missing it fails on import.
if ! ./.venv/bin/python -c 'import weasyprint' 2>/dev/null; then
    warn "weasyprint cannot import — native libraries missing."
    warn "Required by:  md2pdf.py"
    warn "Install native deps:"
    warn "  macOS:   brew install pango gdk-pixbuf libffi"
    warn "  Debian:  sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf2.0-0 libfontconfig1"
    warn "  Fedora:  sudo dnf install pango gdk-pixbuf2 cairo libffi"
    warn "After installing, re-run this script to verify."
    missing_host=1
else
    say "weasyprint: OK (pango + cairo visible)"
fi

echo ""
if [ "$missing_host" -eq 0 ]; then
    say "All dependencies installed and verified."
else
    warn "Local deps OK, but weasyprint cannot run until pango/cairo/gdk-pixbuf are installed."
fi
echo ""
say "Usage:"
say "  ./.venv/bin/python scripts/md2pdf.py INPUT.md OUTPUT.pdf     # needs pango+cairo"
say "  ./.venv/bin/python scripts/pdf_merge.py OUT.pdf A.pdf B.pdf"
say "  ./.venv/bin/python scripts/pdf_split.py INPUT.pdf --each-page OUTDIR/"
