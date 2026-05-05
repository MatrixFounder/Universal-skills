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
# Optional flag:
#   --with-chrome   also install Playwright + bundled Chromium (~150 MB) for
#                   the optional chrome render engine (html2pdf --engine chrome).
#                   See requirements-chrome.txt for the dependency.
#
# Idempotent; safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

WITH_CHROME=0
for arg in "$@"; do
    case "$arg" in
        --with-chrome) WITH_CHROME=1 ;;
        --help|-h)
            cat <<EOF
Usage: bash install.sh [--with-chrome]

Options:
  --with-chrome   Install Playwright + Chromium for the optional chrome
                  render engine (html2pdf --engine chrome). Adds ~150 MB.
EOF
            exit 0
            ;;
    esac
done

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

# --- Optional Node deps: mermaid-cli for fenced mermaid code blocks ---
# md2pdf.py preprocesses fenced mermaid code blocks via mmdc → SVG before
# handing the markdown to weasyprint. Without mmdc, those blocks render
# as code (graceful degradation, not an error).
if command -v npm >/dev/null 2>&1; then
    if [ -f package.json ]; then
        say "Installing Node deps (mermaid-cli) into scripts/node_modules/..."
        npm install --silent --no-audit --no-fund
        if [ -x "node_modules/.bin/mmdc" ]; then
            say "mmdc: OK ($(./node_modules/.bin/mmdc --version 2>/dev/null | tail -1))"
        else
            warn "mmdc binary missing after npm install — mermaid blocks will fall back to code."
        fi
    fi
else
    warn 'npm not found — skipping mermaid-cli. Install Node.js if you want fenced mermaid blocks rendered as diagrams.'
fi

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

# --- Optional: Playwright + Chromium for --engine chrome (pdf-11) ---
# Gated behind --with-chrome because the bundled Chromium is ~150 MB
# and most users only need the default weasyprint engine. Idempotent:
# the playwright install command is a no-op when the binary is current.
if [ "$WITH_CHROME" -eq 1 ]; then
    say "Installing Playwright (chrome engine) ..."
    ./.venv/bin/pip install --quiet -r requirements-chrome.txt
    say "Downloading Chromium (~150 MB; cached after first run) ..."
    if ./.venv/bin/playwright install chromium; then
        say "Playwright + Chromium: OK"
    else
        warn "Playwright install completed but 'playwright install chromium' failed."
        warn "The chrome engine will refuse to run until the binary is present."
        missing_host=1
    fi
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
if [ "$WITH_CHROME" -eq 1 ]; then
    say "  ./.venv/bin/python scripts/html2pdf.py IN.webarchive OUT.pdf --engine chrome"
fi
