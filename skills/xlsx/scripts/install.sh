#!/usr/bin/env bash
# Bootstrap local dependencies for the xlsx skill.
#
# Creates:
#   scripts/.venv/ — Python venv with requirements.txt
#
# System tools expected on PATH (checked, not installed):
#   - python3 3.10+
#   - soffice (LibreOffice; required by xlsx_recalc.py to populate cached
#     formula values that openpyxl cannot compute itself)
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

find_soffice() {
    for p in \
        "$(command -v soffice 2>/dev/null || true)" \
        /Applications/LibreOffice.app/Contents/MacOS/soffice \
        /opt/homebrew/bin/soffice \
        /usr/local/bin/soffice \
        /usr/bin/soffice ; do
        if [ -n "$p" ] && [ -x "$p" ]; then echo "$p"; return 0; fi
    done
    return 1
}

if SOFFICE=$(find_soffice); then
    say "soffice: $SOFFICE"
else
    warn "soffice (LibreOffice) NOT FOUND."
    warn "Required by:  xlsx_recalc.py (populates cached formula values)"
    warn "Install:"
    warn "  macOS:   brew install --cask libreoffice"
    warn "  Debian:  sudo apt install libreoffice --no-install-recommends"
    warn "  Fedora:  sudo dnf install libreoffice"
    missing_host=1
fi

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

echo ""
if [ "$missing_host" -eq 0 ]; then
    say "All dependencies installed and verified."
else
    warn "Local deps OK, but soffice is missing (xlsx_recalc.py will fail until installed)."
fi
echo ""
say "Usage:"
say "  ./.venv/bin/python scripts/csv2xlsx.py INPUT.csv OUTPUT.xlsx"
say "  ./.venv/bin/python scripts/xlsx_recalc.py WORKBOOK.xlsx                 # needs soffice"
say "  ./.venv/bin/python scripts/xlsx_validate.py WORKBOOK.xlsx --fail-empty"
