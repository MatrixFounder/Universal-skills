#!/usr/bin/env bash
# Bootstrap the OPTIONAL local dependencies of the design-md skill.
#
# Creates:
#   scripts/.venv/   Python virtual environment holding Pillow
#
# Nothing here is required to use the skill. scripts/extract-palette reads
# non-interlaced PNG with no third-party code at all; Pillow only widens the
# accepted input formats (JPEG, WebP, TIFF, BMP, GIF, interlaced PNG) and moves
# decoding into C. See requirements.txt for the exact degradation matrix.
#
# The design.md CLI itself is NOT installed by this script and never bundled:
# it is fetched on demand by npx and pinned at the call site
# (npx --yes @google/design.md@0.4.0). That package is Apache-2.0, Google LLC.
#
# Idempotent: safe to re-run. Installs nothing globally and installs no system
# packages — missing system tools are reported as hints, not actions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
say() { printf '[install.sh] %s\n' "$*"; }
warn() { printf '[install.sh] %s\n' "$*" >&2; }

say "design-md skill — local bootstrap"
say "target: $VENV"
echo

# ---------------------------------------------------------------------------
# 1. Host Python
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    warn "ERROR: python3 not found on PATH."
    warn "       Install Python 3.9 or newer, then re-run this script."
    exit 1
fi

PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    warn "ERROR: Python 3.9+ required; found $PY_VER."
    exit 1
fi
say "python3: $PY_VER ($(command -v python3))"

# ---------------------------------------------------------------------------
# 2. Virtual environment (created once, reused afterwards)
# ---------------------------------------------------------------------------
if [ -x "$VENV/bin/python" ]; then
    VENV_VER="$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if [ "$VENV_VER" != "$PY_VER" ]; then
        warn "NOTE: existing venv is Python $VENV_VER but python3 is now $PY_VER."
        warn "      extract-palette only imports a venv matching the running"
        warn "      interpreter, so this one would be ignored. Recreating it."
        rm -rf "$VENV"
    fi
fi

if [ -x "$VENV/bin/python" ]; then
    say "venv: already present, reusing it"
else
    say "venv: creating with 'python3 -m venv'"
    if ! python3 -m venv "$VENV"; then
        warn "ERROR: could not create the virtual environment."
        warn "       On Debian/Ubuntu this usually means the venv module is a"
        warn "       separate package. HINT (not run for you):"
        warn "         sudo apt-get install python3-venv"
        exit 1
    fi
fi

PY="$VENV/bin/python"
say "venv python: $("$PY" -c 'import sys; print(sys.version.split()[0])')"

# ---------------------------------------------------------------------------
# 3. Dependencies — into the venv only, never globally
# ---------------------------------------------------------------------------
say "pip: upgrading inside the venv"
"$PY" -m pip install --quiet --upgrade pip

say "pip: installing requirements.txt into the venv"
if ! "$PY" -m pip install --quiet --requirement "$SCRIPT_DIR/requirements.txt"; then
    warn "NOTE: Pillow did not install. This is not fatal."
    warn "      extract-palette still reads non-interlaced PNG with no"
    warn "      third-party code. JPEG and WebP input will exit 3."
    warn "      A source build of Pillow needs image libraries. HINTS"
    warn "      (nothing is installed for you):"
    warn "        macOS          brew install libjpeg zlib libtiff webp"
    warn "        Debian/Ubuntu  sudo apt-get install libjpeg-dev zlib1g-dev \\"
    warn "                                            libtiff-dev libwebp-dev"
    exit 1
fi

PILLOW_VER="$("$PY" -c 'import PIL; print(PIL.__version__)')"
say "Pillow: $PILLOW_VER"
echo

# ---------------------------------------------------------------------------
# 4. Smoke test — a known-answer image built with the standard library alone
#
# Three flat bands in exact 50 % / 30 % / 20 % proportions. The script must
# recover all three hex values and all three shares, on BOTH decode paths.
# ---------------------------------------------------------------------------
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

"$PY" - "$WORK/smoke.png" <<'PYEOF'
import struct
import sys
import zlib

W, H = 200, 100
BANDS = [(50, (0x0F, 0x14, 0x19)), (30, (0xF5, 0xF2, 0xEC)), (20, (0xE2, 0x54, 0x2C))]

rows = []
for y in range(H):
    edge = 0
    colour = BANDS[-1][1]
    for rows_pct, rgb in BANDS:
        edge += H * rows_pct // 100
        if y < edge:
            colour = rgb
            break
    rows.append(bytes(colour) * W)

stream = bytearray()
for row in rows:
    stream.append(0)  # filter type 0 (None)
    stream += row


def chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(bytes(stream), 9))
png += chunk(b"IEND", b"")
with open(sys.argv[1], "wb") as fh:
    fh.write(png)
PYEOF

cat > "$WORK/assert.py" <<'PYEOF'
import json
import sys

label = sys.argv[1]
report = json.load(sys.stdin)
got = [(c["hex"], round(c["share_pct"], 1)) for c in report["colors"]]
want = [("#0f1419", 50.0), ("#f5f2ec", 30.0), ("#e2542c", 20.0)]
if got != want:
    sys.stderr.write("[install.sh] ERROR: smoke test (%s) recovered %r, expected %r\n"
                     % (label, got, want))
    raise SystemExit(1)
print("[install.sh] smoke test (%s): %s -- OK" % (label, got))
PYEOF

check() {
    label="$1"
    interpreter="$2"
    decoder="$3"
    set +e
    out="$("$interpreter" "$SCRIPT_DIR/extract-palette" "$WORK/smoke.png" \
            --decoder "$decoder" --json 2>"$WORK/err.txt")"
    rc=$?
    set -e
    if [ "$rc" -ne 0 ]; then
        warn "ERROR: smoke test ($label) exited $rc"
        warn "$(cat "$WORK/err.txt")"
        exit 1
    fi
    printf '%s' "$out" | "$PY" "$WORK/assert.py" "$label"
}

check "built-in PNG decoder, host python3" "$(command -v python3)" "stdlib-png"
check "Pillow, venv python" "$PY" "pillow"
echo

# ---------------------------------------------------------------------------
# 5. Hints for host tools this script deliberately does not install
# ---------------------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
    say "node: $(node --version) (npx will fetch @google/design.md@0.4.0 on demand)"
else
    warn "HINT: node is not on PATH. The design.md linter is reached through"
    warn "      'npx --yes @google/design.md@0.4.0', which needs Node 18+."
    warn "      Install it from https://nodejs.org/ — not installed for you."
    warn "      extract-palette is unaffected and works without Node."
fi

echo
say "done. Nothing was installed outside $VENV."
say "usage:"
say "  scripts/extract-palette /abs/path/screenshot.png"
say "  scripts/extract-palette /abs/path/screenshot.png --ignore-edges 8 --json"
say "  scripts/extract-palette --help"
