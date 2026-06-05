#!/usr/bin/env bash
# Bootstrap local dependencies for the docx skill.
#
# Creates:
#   scripts/.venv/          — Python venv with requirements.txt
#   scripts/node_modules/   — npm packages from package.json (local, not global)
#
# System tools expected on PATH (checked, not installed):
#   - node 18+
#   - python3 3.10+
#   - soffice   (LibreOffice; required by docx_accept_changes.py and by the
#               shape-group fallback in docx2md.js)
#   - pdftoppm + pdftotext (poppler; OPTIONAL — enables high-fidelity
#               shape-group rendering in docx2md.js. Without poppler we fall
#               back to LibreOffice HTML GIF export, which captures geometry
#               only and separates shape labels from the bitmap.)
#   - Chrome / Chromium / Edge / Brave (OPTIONAL — html2docx.js auto-detects
#               a Chromium-family browser and uses headless rendering for
#               inline SVG diagrams (drawio, mermaid, etc.) so foreignObject
#               + CSS layout reproduce exactly. Without one, html2docx falls
#               back to the @resvg/resvg-js parser, which handles geometry
#               but degrades on rich HTML labels inside SVG. Override the
#               auto-detect with HTML2DOCX_BROWSER=/path/to/chrome.)
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

if ! command -v node >/dev/null 2>&1; then
    die "node not found. Install Node 18+ from https://nodejs.org/."
fi
NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    die "Node 18+ required; found v$NODE_MAJOR."
fi
say "node:    $(node --version)"

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
    warn "Required by:  docx_accept_changes.py and the docx2md.js shape-group fallback."
    warn "Install:"
    warn "  macOS:   brew install --cask libreoffice"
    warn "  Debian:  sudo apt install libreoffice --no-install-recommends"
    warn "  Fedora:  sudo dnf install libreoffice"
    missing_host=1
fi

# Chromium-family browser is optional — html2docx.js detects it at
# runtime and uses headless rendering for inline SVG diagrams (drawio /
# mermaid / etc.) when found. Without one, html2docx falls back to the
# bundled @resvg/resvg-js parser. Override auto-detect with
# HTML2DOCX_BROWSER=/path/to/chrome.
HTML2DOCX_BROWSER_FOUND=""
case "$(uname -s 2>/dev/null || echo unknown)" in
    Darwin)
        for p in \
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
            "/Applications/Chromium.app/Contents/MacOS/Chromium" \
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" ; do
            if [ -x "$p" ]; then HTML2DOCX_BROWSER_FOUND="$p"; break; fi
        done
        ;;
    *)
        for n in google-chrome google-chrome-stable chromium chromium-browser chrome microsoft-edge brave-browser; do
            if command -v "$n" >/dev/null 2>&1; then
                HTML2DOCX_BROWSER_FOUND="$(command -v "$n")"
                break
            fi
        done
        ;;
esac
if [ -n "$HTML2DOCX_BROWSER_FOUND" ]; then
    say "browser: $HTML2DOCX_BROWSER_FOUND (used by html2docx.js for SVG rendering)"
else
    warn "Chrome / Chromium NOT FOUND on host."
    warn "OPTIONAL: html2docx.js renders SVG diagrams via @resvg/resvg-js fallback;"
    warn "rich foreignObject content (drawio HTML labels) may degrade."
    warn "Install ANY ONE of:"
    warn "  macOS:   brew install --cask google-chrome    (or chromium / brave-browser)"
    warn "  Debian:  sudo apt install chromium            (or chromium-browser)"
    warn "  Fedora:  sudo dnf install chromium"
    warn "Or set HTML2DOCX_BROWSER=/path/to/chrome to override the auto-detector."
fi

# Poppler is optional — only needed for highest-fidelity shape-group
# rendering in docx2md.js. We probe but never fail without it.
if command -v pdftoppm >/dev/null 2>&1 && command -v pdftotext >/dev/null 2>&1; then
    say "poppler: pdftoppm + pdftotext OK ($(pdftoppm -v 2>&1 | head -1))"
else
    warn "poppler (pdftoppm + pdftotext) NOT FOUND."
    warn "OPTIONAL: enables high-fidelity shape-group rendering in docx2md.js."
    warn "Without it, shape diagrams render as geometry-only GIF (text labels separated)."
    warn "Install:"
    warn "  macOS:   brew install poppler"
    warn "  Debian:  sudo apt install poppler-utils"
    warn "  Fedora:  sudo dnf install poppler-utils"
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

# --- npm install ---
if [ ! -f "package.json" ]; then
    die "package.json missing in $SCRIPT_DIR."
fi
say "Installing npm dependencies into scripts/node_modules/ ..."
npm install --no-fund --no-audit --silent

# --- Verify Python deps actually import (catches silent wheel-build failures,
#     e.g. Pillow/lxml lacking prebuilt wheels on fresh interpreters like 3.14) ---
say "Verifying Python dependencies import..."
if ! miss=$(./.venv/bin/python - <<'PY'
import importlib.util, sys                       # NOT bare `import importlib` — .util must be explicit
# Import names for every requirements.txt wheel (Pillow→PIL, python-docx→docx, msoffcrypto-tool→msoffcrypto)
missing = [m for m in ("PIL", "lxml", "defusedxml", "docx", "msoffcrypto") if importlib.util.find_spec(m) is None]
print(",".join(missing))
sys.exit(1 if missing else 0)
PY
); then
    die "Python dependency import check failed (missing: ${miss:-unknown}). Re-run install or check the wheel build."
fi

# --- Smoke-test the SKILL.md-documented commands. Proves the self-bootstrap fix:
#     a BARE `python3 scripts/X.py` must work even when python3 != .venv. ---
say "Smoke-testing documented commands (md2docx -> validate [-> preview])..."
SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT
if ! node md2docx.js ../examples/fixture-simple.md "$SMOKE_DIR/smoke.docx" >/dev/null 2>"$SMOKE_DIR/err"; then
    cat "$SMOKE_DIR/err" >&2; die "md2docx.js smoke-test failed."
fi
# DELIBERATELY bare `python3` (not ./.venv/bin/python): this run IS the proof of the self-bootstrap fix.
if ! python3 office/validate.py "$SMOKE_DIR/smoke.docx" >/dev/null 2>"$SMOKE_DIR/err"; then
    cat "$SMOKE_DIR/err" >&2
    if grep -q "ModuleNotFoundError" "$SMOKE_DIR/err"; then
        die "office/validate.py failed with ModuleNotFoundError — the self-bootstrap is broken."
    fi
    die "office/validate.py smoke-test failed."
fi
if [ -n "${SOFFICE:-}" ]; then
    if ! python3 preview.py "$SMOKE_DIR/smoke.docx" "$SMOKE_DIR/smoke.jpg" >/dev/null 2>"$SMOKE_DIR/err"; then
        cat "$SMOKE_DIR/err" >&2
        if grep -q "ModuleNotFoundError" "$SMOKE_DIR/err"; then
            die "preview.py failed with ModuleNotFoundError — the self-bootstrap is broken."
        fi
        die "preview.py smoke-test failed."
    fi
    say "Smoke-test PASS (md2docx + validate + preview, all via bare python3)."
else
    say "Smoke-test PASS (md2docx + validate via bare python3; preview skipped — soffice absent)."
fi

echo ""
if [ "$missing_host" -eq 0 ]; then
    say "All dependencies installed and verified."
else
    warn "Local deps OK, but some system tools are missing (see warnings above)."
fi
echo ""
say "Usage:"
say "  node scripts/md2docx.js INPUT.md OUTPUT.docx [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]"
say "  node scripts/docx2md.js INPUT.docx OUTPUT.md"
say "  ./.venv/bin/python scripts/docx_fill_template.py TPL.docx DATA.json OUT.docx"
say "  ./.venv/bin/python scripts/docx_accept_changes.py IN.docx OUT.docx   # needs soffice"
