#!/usr/bin/env bash
# design-md E2E entrypoint.
#
# Every assertion below is a contract the skill's own prose states as fact. The point
# is not coverage for its own sake: each one corresponds to a defect this skill has
# actually shipped at least once —
#
#   * a documented extract-palette invocation whose default threshold silently hid
#     the accent colour it then told the agent to find (the --min-share regression)
#   * check-contrast over-gating one token name and under-gating another
#   * a component class (backgroundColor with no textColor) that no rule checked
#   * templates drifting off lint-clean
#   * a file with no tokens at all linting at zero errors (the fabrication gate)
#
# Fixtures are built here rather than committed, so the suite is self-contained and
# runs the same way inside a packaged .skill archive.
#
# Requires network on first run: `lint` shells out to npx @google/design.md@0.4.0.
# A missing npx FAILS rather than skips — a green gate that tested nothing is worse
# than a red one.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"   # scripts/
SKILL="$(cd "$HERE/.." && pwd -P)"                            # skills/design-md/
WORK="$(mktemp -d)"
trap 'rc=$?; rm -rf "$WORK"; [ "${FINISHED:-0}" = 1 ] || rc=1; exit $rc' EXIT
cd "$HERE"

# Path-resolution self-test hook (tests/test_symlink_invocation.sh).
if [ -n "${E2E_PREAMBLE_ONLY:-}" ]; then
    echo "E2E_SELFTEST_PATH SKILL=$SKILL"
    echo "E2E_SELFTEST_PATH HERE=$HERE"
    FINISHED=1
    exit 0
fi

fail=0
checks=0

ok()   { checks=$((checks+1)); printf '  ok    %s\n' "$1"; }
bad()  { checks=$((checks+1)); fail=1; printf '  FAIL  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; }

# exit_is <label> <expected> <cmd...>
exit_is() {
  local label="$1" want="$2"; shift 2
  "$@" >"$WORK/out" 2>"$WORK/err"; local got=$?
  if [ "$got" = "$want" ]; then ok "$label"
  else bad "$label" "expected exit $want, got $got; last line: $(tail -1 "$WORK/out" "$WORK/err" 2>/dev/null | tail -1)"; fi
}

# says <label> <needle> <cmd...>
says() {
  local label="$1" needle="$2"; shift 2
  local out; out="$("$@" 2>&1)"
  if grep -qF -- "$needle" <<<"$out"; then ok "$label"
  else bad "$label" "output did not contain: $needle"; fi
}

echo "== design-md E2E =="
echo "   skill: $SKILL"

# ---------------------------------------------------------------------------
echo "== 0. toolchain =="
if command -v npx >/dev/null 2>&1; then ok "npx present"
else bad "npx present" "lint cannot run; this suite refuses to report green without it"; fi
PY="./.venv/bin/python"; [ -x "$PY" ] || PY=python3
ok "python: $PY"

# ---------------------------------------------------------------------------
echo "== 1. lint contracts (SKILL.md 'Validation Evidence') =="
# lint_is <file> <errors> <warnings> <infos> <expected-exit>
lint_is() {
  local f="$1" e="$2" w="$3" i="$4" xc="$5"
  local base; base="$(basename "$f")"
  ./lint "$f" --json >"$WORK/lint.json" 2>/dev/null; local got=$?
  local sum
  sum="$("$PY" -c "
import json,sys
try: d=json.load(open('$WORK/lint.json'))['summary']
except Exception as exc: print('unparseable:',exc); raise SystemExit
print(f\"{d['errors']}/{d['warnings']}/{d['infos']}\")" 2>/dev/null)"
  if [ "$sum" = "$e/$w/$i" ] && [ "$got" = "$xc" ]; then ok "$base -> $sum, exit $got"
  else bad "$base" "expected $e/$w/$i exit $xc, got ${sum:-<none>} exit $got"; fi
}
lint_is ../examples/fixture-clean.md            0 0 1 0
lint_is ../examples/fixture-broken.md           1 6 1 1
lint_is ../assets/template-skeleton.md          0 0 1 0
lint_is ../assets/template-product-saas.md      0 0 1 0
lint_is ../assets/template-editorial.md         0 0 1 0
lint_is ../assets/template-cyrillic.md          0 0 1 0
lint_is ../examples/example-saas-dashboard.md   0 0 2 0

# ---------------------------------------------------------------------------
echo "== 2. check-contrast =="
SAAS=../examples/example-saas-dashboard.md
exit_is "--self-test reproduces the WCAG known answers" 0 ./check-contrast --self-test
# A clean lint is not a clean file: fixture-clean lints 0/0 and still fails a pair.
exit_is "fixture-clean fails a gated pair (the skill's central claim)" 1 ./check-contrast ../examples/fixture-clean.md
exit_is "example-saas-dashboard passes its gates" 0 ./check-contrast "$SAAS"
# --pair bypasses classification and MD3 pairing: the seam WI-031 (i) opened.
exit_is "--pair on a passing pair"        0 ./check-contrast "$SAAS" --pair tertiary,surface
exit_is "--pair on a failing pair"        1 ./check-contrast "$SAAS" --pair outline,surface
exit_is "--pair on an unknown token name" 2 ./check-contrast "$SAAS" --pair nosuchtoken,surface
says    "--pair prints the measured ratio" "6.39" ./check-contrast "$SAAS" --pair tertiary,surface
# WI-031 (c): a fill with no label colour is checked by nothing, and silence read
# as a pass. It must be named out loud.
says    "UNCHECKED FILLS section is present" "UNCHECKED FILLS" ./check-contrast "$SAAS"

# ---------------------------------------------------------------------------
echo "== 3. extract-palette =="
"$PY" - "$WORK/bands.png" <<'PYEOF'
import struct, sys, zlib
# 200x100 three-band PNG: the fixture scripts/README.md documents.
W, H = 200, 100
BANDS = [((0x1a, 0x1c, 0x1e), 34), ((0x6c, 0x72, 0x78), 33), ((0xb8, 0x42, 0x2e), 33)]
rows = []
for colour, n in BANDS:
    rows += [bytes(colour) * W] * n
rows += [bytes(BANDS[-1][0]) * W] * (H - len(rows))
stream = b"".join(b"\x00" + r for r in rows)
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(stream, 9))
png += chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
PYEOF
says "three-band fixture -> 3 of 3 clusters" "3 of 3 clusters" ./extract-palette "$WORK/bands.png"
says "three-band fixture -> 100.0% covered" "100.0%"          ./extract-palette "$WORK/bands.png"
exit_is "three-band fixture exits 0" 0 ./extract-palette "$WORK/bands.png"

# The --min-share regression, portable. An accent occupying 0.48% of the frame sits
# BELOW the 0.50% default: the documented Route 2 pin of --min-share 0.1 is the only
# thing that keeps it in the report. Route 2's prose depends on this holding.
"$PY" - "$WORK/faint.png" <<'PYEOF'
import struct, sys, zlib
W, H = 1000, 100                      # 100_000 px
ACCENT, N = (0xe2, 0x5a, 0x3c), 480   # 0.48% of the frame
GROUND = (0xff, 0xff, 0xff)
flat = [GROUND] * (W * H)
flat[:N] = [ACCENT] * N
rows = [b"".join(bytes(p) for p in flat[y * W:(y + 1) * W]) for y in range(H)]
stream = b"".join(b"\x00" + r for r in rows)
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(stream, 9))
png += chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
PYEOF
if ./extract-palette "$WORK/faint.png" --max-samples 0 2>/dev/null | grep -qi "e25a3c"; then
  bad "a 0.48% accent is dropped by the DEFAULT threshold" \
      "it was reported; the default is no longer 0.50% and Route 2's prose needs revisiting"
else
  ok "a 0.48% accent is dropped by the DEFAULT threshold"
fi
says "the documented --min-share 0.1 recovers it" "e25a3c" \
     ./extract-palette "$WORK/faint.png" --max-samples 0 --min-share 0.1

# ---------------------------------------------------------------------------
echo "== 4. check-fabrication (the gate the linter cannot be) =="
"$PY" - "$WORK" <<'PYEOF'
import struct, sys, zlib
out = sys.argv[1]
W, H = 300, 120
PAPER, INK = (0xff, 0xff, 0xff), (0x1b, 0x22, 0x26)

def write(path, painter):
    px = [[PAPER] * W for _ in range(H)]
    painter(px)
    stream = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(stream, 9))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)

def bars(px):
    # Redaction blocks: every text-sized region completely fills its box.
    for i, wd in enumerate((120, 70, 95, 60)):
        for y in range(20 + i * 22, 20 + i * 22 + 11):
            for x in range(20, 20 + wd):
                px[y][x] = INK

def glyphs(px):
    # Crude letterforms (E, H, L). No font needed - what matters is that none of
    # these fills its bounding box, which is precisely what a glyph does not do.
    def vline(x, y0, y1):
        for y in range(y0, y1): px[y][x] = px[y][x + 1] = INK
    def hline(y, x0, x1):
        for x in range(x0, x1): px[y][x] = px[y + 1][x] = INK
    for k in range(6):
        ox = 20 + k * 40
        vline(ox, 20, 40); hline(20, ox, ox + 18); hline(29, ox, ox + 14); hline(38, ox, ox + 18)
        ox += 22
        vline(ox, 50, 70); vline(ox + 16, 50, 70); hline(59, ox, ox + 18)
        ox -= 22
        vline(ox, 80, 100); hline(98, ox, ox + 16)

write(f"{out}/redacted.png", bars)
write(f"{out}/glyphs.png", glyphs)
PYEOF

cat >"$WORK/asserts-type.md" <<'MD'
---
version: alpha
name: Asserts Typography
colors:
  primary: "#1b2226"
typography:
  h1:
    fontFamily: Inter
    fontSize: 44px
---

## Overview

Body.
MD
sed 's/^colors:/omitted:\n  - section: typography\n    reason: "Every text run is a redaction block."\ncolors:/' \
    "$WORK/asserts-type.md" >"$WORK/omits-type.md"
cat >"$WORK/prose-only.md" <<'MD'
# A design document with no tokens

All rationale, no frontmatter.
MD

exit_is "asserting typography over a redacted capture fails" 1 \
        ./tests/check-fabrication "$WORK/asserts-type.md" --image "$WORK/redacted.png"
says    "  ...and names the rule" "unsourced-type" \
        ./tests/check-fabrication "$WORK/asserts-type.md" --image "$WORK/redacted.png"
exit_is "declaring it in \`omitted\` instead passes" 0 \
        ./tests/check-fabrication "$WORK/omits-type.md" --image "$WORK/redacted.png"
# The negative control. Without it this check would demand `omitted` on every image,
# which would be a false-positive machine rather than a gate.
exit_is "asserting typography over a capture WITH glyphs passes" 0 \
        ./tests/check-fabrication "$WORK/asserts-type.md" --image "$WORK/glyphs.png"
exit_is "a file with no frontmatter fails" 1 \
        ./tests/check-fabrication "$WORK/prose-only.md"
says    "  ...and names the rule" "no-frontmatter" \
        ./tests/check-fabrication "$WORK/prose-only.md"

# An unsourced hex: #00ff00 appears in no fixture built above.
sed 's/"#1b2226"/"#00ff00"/' "$WORK/omits-type.md" >"$WORK/bad-hex.md"
exit_is "a hex absent from the source fails" 1 \
        ./tests/check-fabrication "$WORK/bad-hex.md" --image "$WORK/redacted.png"
says    "  ...and names the rule" "unsourced-hex" \
        ./tests/check-fabrication "$WORK/bad-hex.md" --image "$WORK/redacted.png"

# The skill's own shipped artifacts must survive their own gate.
for f in ../assets/template-*.md ../examples/example-saas-dashboard.md ../examples/fixture-clean.md; do
  exit_is "$(basename "$f") has frontmatter" 0 ./tests/check-fabrication "$f"
done

# ---------------------------------------------------------------------------
echo
if [ "$checks" -lt 30 ]; then
  echo "design-md test_e2e: FAIL — only $checks assertions ran; the suite did not execute"
  exit 1
fi
if [ "$fail" -eq 0 ]; then
  echo "design-md test_e2e: PASS ($checks assertions)"
else
  echo "design-md test_e2e: FAIL ($checks assertions)"
fi
FINISHED=1
exit $fail
