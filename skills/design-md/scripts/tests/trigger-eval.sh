#!/usr/bin/env bash
# trigger-eval.sh — does the design-md description fire when it should, and stay
# quiet when it should not?
#
# This is a DIFFERENT question from test_e2e.sh. That suite asks whether the skill's
# scripts honour their contracts. This one asks whether the skill is ever reached:
# every guarantee the skill makes is conditional on the description winning the
# routing decision, and a description that never fires is a skill that does not
# exist. It matters more here than usual because the description is bilingual, so a
# regression can be silent in one language and total in the other.
#
# MANUAL AND OPT-IN, BY DESIGN. It is not wired into CI and must not be: every query
# is a real, billed `claude -p` invocation, and the repository's convention is that
# anything costing money or running on a schedule is the user's explicit choice
# rather than a side effect of pushing a commit.
#
#   bash tests/trigger-eval.sh                 # all queries
#   bash tests/trigger-eval.sh --only positive # just the should-fire set
#   bash tests/trigger-eval.sh --model sonnet  # cheaper sweep
#   bash tests/trigger-eval.sh --repeat 3      # majority of 3, for a stable reading
#
# Routing is not perfectly deterministic: the same query can fire on one run and
# not the next. Treat a single borderline result as noise and re-check it with
# --repeat before editing the description on the strength of it.
#
# Exit 0 when every query matched its expectation, 1 otherwise, 2 on a setup problem.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERIES="$HERE/trigger-queries.json"
SKILL_NAME="design-md"
ONLY=""
MODEL=""
REPEAT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --only)  ONLY="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --repeat) REPEAT="${2:-1}"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

command -v claude >/dev/null 2>&1 || { echo "trigger-eval: the claude CLI is not on PATH" >&2; exit 2; }
[ -f "$QUERIES" ] || { echo "trigger-eval: $QUERIES not found" >&2; exit 2; }

# The skill must be reachable from wherever `claude -p` runs, or every query fails
# for a reason that has nothing to do with the description.
if [ ! -e "$HOME/.claude/skills/$SKILL_NAME" ] && [ ! -e "$HOME/.claude/plugins/$SKILL_NAME" ]; then
  echo "trigger-eval: $SKILL_NAME is not installed under ~/.claude/skills — the run would" >&2
  echo "              measure its absence, not its description. Install it first." >&2
  exit 2
fi

# A query that names an artifact must supply it. Asking about "the screenshot" with
# no screenshot present measures whether the model asks for the missing file, not
# whether the description routed — both original misses in this set were that.
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT
python3 - "$FIXTURE_DIR/screenshot.png" <<'PYEOF'
import struct, sys, zlib
W, H = 240, 120
BANDS = [((0x14, 0x24, 0x24), 24), ((0xf7, 0xf4, 0xef), 72), ((0xe2, 0x5a, 0x3c), 24)]
rows = []
for colour, n in BANDS:
    rows += [bytes(colour) * W] * n
stream = b"".join(b"\x00" + r for r in rows)
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(stream, 9))
png += chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
PYEOF
cat >"$FIXTURE_DIR/theme.css" <<'CSS'
:root {
  --color-bg: #f7f4ef;
  --color-surface: #ffffff;
  --color-ink: #1b2226;
  --color-accent: #e25a3c;
  --radius: 0;
  --space-1: 8px;
  --space-2: 16px;
  --space-3: 32px;
}
.btn-primary { background: var(--color-accent); color: #fff; padding: var(--space-1) var(--space-2); border-radius: var(--radius); }
.card { background: var(--color-surface); border: 1px solid #ded8ce; padding: 20px; }
body { background: var(--color-bg); color: var(--color-ink); font-family: system-ui, sans-serif; }
CSS

cat >"$FIXTURE_DIR/DESIGN.md" <<'MD'
---
version: alpha
name: Sample System
colors:
  primary: "#e25a3c"
  surface: "#ffffff"
  on-surface: "#1b2226"
spacing:
  sm: 8px
  md: 16px
rounded:
  none: 0px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
---

## Overview

A sample system used only as a trigger-eval fixture.

## Colors

One accent on a white ground.
MD

# fired <query> -> prints "yes" or "no"
fired() {
  local q="${1//\{\{IMAGE\}\}/$FIXTURE_DIR/screenshot.png}"
  q="${q//\{\{CSS\}\}/$FIXTURE_DIR/theme.css}"
  q="${q//\{\{DESIGN\}\}/$FIXTURE_DIR/DESIGN.md}"
  local args=(-p "$q" --output-format stream-json --verbose --max-turns 2)
  [ -n "$MODEL" ] && args+=(--model "$MODEL")
  # Run from /tmp so nothing in a project directory nudges the routing decision.
  (cd /tmp && claude "${args[@]}" 2>/dev/null) | python3 -c "
import json, sys
for line in sys.stdin:
    try: ev = json.loads(line)
    except ValueError: continue
    if ev.get('type') != 'assistant': continue
    for c in ev.get('message', {}).get('content', []):
        if c.get('type') == 'tool_use' and c.get('name') == 'Skill':
            if (c.get('input') or {}).get('skill') == '$SKILL_NAME':
                print('yes'); raise SystemExit
print('no')"
}

run_set() {  # $1 = positive|negative
  local set="$1" want
  [ "$set" = positive ] && want=yes || want=no
  local n
  n="$(python3 -c "import json;print(len(json.load(open('$QUERIES'))['$set']))")"
  echo "== $set ($n queries; expecting fired=$want) =="
  local i
  for ((i = 0; i < n; i++)); do
    local q probes got
    q="$(python3 -c "import json;print(json.load(open('$QUERIES'))['$set'][$i]['q'])")"
    probes="$(python3 -c "import json;print(json.load(open('$QUERIES'))['$set'][$i]['probes'])")"
    local yes=0 r
    for ((r = 0; r < REPEAT; r++)); do
      [ "$(fired "$q")" = yes ] && yes=$((yes + 1))
    done
    # Majority vote; a tie on an even --repeat counts as not fired, the stricter reading.
    if [ $((yes * 2)) -gt "$REPEAT" ]; then got=yes; else got=no; fi
    local vote=""
    [ "$REPEAT" -gt 1 ] && [ "$yes" -ne 0 ] && [ "$yes" -ne "$REPEAT" ] && vote=" (split $yes/$REPEAT)"
    total=$((total + 1))
    if [ "$got" = "$want" ]; then
      printf '  ok    %s%s\n' "$probes" "$vote"
    else
      miss=$((miss + 1))
      printf '  MISS  %s%s\n        query: %s\n        fired=%s, expected %s\n' "$probes" "$vote" "$q" "$got" "$want"
    fi
  done
}

total=0
miss=0
echo "trigger-eval: $SKILL_NAME${MODEL:+ (model: $MODEL)}"
echo "              every query below is a billed API call"
echo
[ "$ONLY" = negative ] || run_set positive
[ "$ONLY" = positive ] || run_set negative

echo
if [ "$total" -eq 0 ]; then
  echo "trigger-eval: FAIL — no queries ran"
  exit 1
fi
echo "trigger-eval: $((total - miss))/$total matched expectation"
if [ "$miss" -gt 0 ]; then
  echo
  echo "  A missed POSITIVE means the description does not claim territory it should:"
  echo "  add the vocabulary the query used. A missed NEGATIVE means it claims too much"
  echo "  and will burn context on unrelated work: narrow the phrase that over-reaches."
  echo "  Edit only \`description:\` in SKILL.md; the body does not affect routing."
  exit 1
fi
echo "trigger-eval: PASS"
