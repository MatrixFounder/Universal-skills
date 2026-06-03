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
# Optional flags:
#   --with-chrome   also install Playwright + bundled Chromium (~150 MB) for
#                   the optional chrome render engine (html2pdf --engine chrome).
#                   See requirements-chrome.txt for the dependency.
#   --with-ocr      also install ocrmypdf (pdf_ocr.py / pdf-4) into the venv and
#                   PROBE the required system tools (tesseract + eng/rus
#                   traineddata, ghostscript) — checked, not installed.
#                   See requirements-ocr.txt for the dependency.
#
# Idempotent; safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

WITH_CHROME=0
WITH_OCR=0
for arg in "$@"; do
    case "$arg" in
        --with-chrome) WITH_CHROME=1 ;;
        --with-ocr) WITH_OCR=1 ;;
        --help|-h)
            cat <<EOF
Usage: bash install.sh [--with-chrome] [--with-ocr]

Options:
  --with-chrome   Install Playwright + Chromium for the optional chrome
                  render engine (html2pdf --engine chrome). Adds ~150 MB.
  --with-ocr      Install ocrmypdf (pdf_ocr.py) into the venv and probe the
                  required system tools (tesseract + eng/rus, ghostscript).
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
    # --upgrade so a re-run lifts an already-present too-old Playwright to the
    # requirements-chrome.txt floor (>=1.42 — needed for page.pdf outline,
    # pdf-7). Plain `pip install -r` does not upgrade a satisfied package.
    ./.venv/bin/pip install --quiet --upgrade -r requirements-chrome.txt
    say "Downloading Chromium (~150 MB; cached after first run) ..."
    if ./.venv/bin/playwright install chromium; then
        say "Playwright + Chromium: OK"
    else
        warn "Playwright install completed but 'playwright install chromium' failed."
        warn "The chrome engine will refuse to run until the binary is present."
        missing_host=1
    fi
fi

# --- Optional: ocrmypdf + system OCR tools for pdf_ocr.py (pdf-4) ---
# Gated behind --with-ocr because most users do not need OCR and the system
# tools (tesseract + language packs + ghostscript) are a heavier ask. We INSTALL
# the Python wheel into the venv but only PROBE the system tools (install is the
# user's choice — parity with the weasyprint native-libs probe).
if [ "$WITH_OCR" -eq 1 ]; then
    say "Installing ocrmypdf (OCR engine) into scripts/.venv/ ..."
    # --upgrade so a re-run lifts an already-present too-old ocrmypdf to the
    # requirements-ocr.txt floor. Plain `pip install -r` does not upgrade a
    # satisfied package.
    ./.venv/bin/pip install --quiet --upgrade -r requirements-ocr.txt
    if ./.venv/bin/python -c 'import ocrmypdf' 2>/dev/null; then
        say "ocrmypdf: OK ($(./.venv/bin/python -c 'import ocrmypdf; print(ocrmypdf.__version__)' 2>/dev/null))"
    else
        warn "ocrmypdf installed but cannot import — check the pip output above."
        missing_host=1
    fi

    # Probe system tesseract + the eng/rus language packs.
    if command -v tesseract >/dev/null 2>&1; then
        say "tesseract: $(tesseract --version 2>&1 | head -1)"
        # `--list-langs` writes to stderr on some tesseract builds and stdout on
        # others — merge both so the eng/rus probe is not falsely negative. Skip
        # the banner by content ("List of available languages …"), not by a
        # positional `tail` (after the 2>&1 merge the banner order is not fixed) —
        # mirrors the pdf_ocr.py _installed_languages parser.
        langs=$(tesseract --list-langs 2>&1 | grep -ivE '^list of')
        for need in eng rus; do
            if printf '%s\n' "$langs" | grep -qx "$need"; then
                say "tesseract lang '$need': OK"
            else
                warn "tesseract language pack '$need' MISSING (needed by default --lang eng+rus)."
                missing_host=1
            fi
        done
    else
        warn "tesseract not found — pdf_ocr.py cannot run."
        missing_host=1
    fi

    # Probe ghostscript (ocrmypdf hard dependency).
    if command -v gs >/dev/null 2>&1; then
        say "ghostscript: $(gs --version 2>/dev/null)"
    else
        warn "ghostscript (gs) not found — ocrmypdf cannot run."
        missing_host=1
    fi

    if [ "$missing_host" -ne 0 ]; then
        warn "Install the missing OCR system tools:"
        warn "  macOS:   brew install tesseract tesseract-lang ghostscript"
        warn "  Debian:  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus ghostscript"
        warn "  Fedora:  sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-rus ghostscript"
        warn "After installing, re-run 'bash install.sh --with-ocr' to verify."
    fi
fi

echo ""
if [ "$missing_host" -eq 0 ]; then
    say "All dependencies installed and verified."
else
    warn "Local deps OK, but some optional/native tools are missing (see warnings above)."
fi
echo ""
say "Usage:"
say "  ./.venv/bin/python scripts/md2pdf.py INPUT.md OUTPUT.pdf     # needs pango+cairo"
say "  ./.venv/bin/python scripts/pdf_merge.py OUT.pdf A.pdf B.pdf"
say "  ./.venv/bin/python scripts/pdf_split.py INPUT.pdf --each-page OUTDIR/"
if [ "$WITH_CHROME" -eq 1 ]; then
    say "  ./.venv/bin/python scripts/html2pdf.py IN.webarchive OUT.pdf --engine chrome"
fi
if [ "$WITH_OCR" -eq 1 ]; then
    say "  ./.venv/bin/python scripts/pdf_ocr.py SCAN.pdf SCAN.ocr.pdf   # OCR eng+rus"
fi
