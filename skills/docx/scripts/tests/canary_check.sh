#!/usr/bin/env bash
# canary_check.sh — q-7 LOW-3 verification.
#
# Sabotages individual preprocessing stages in `_html2docx_preprocess.js`
# one at a time, runs the regression battery, and asserts that the
# battery FAILS for each sabotage. Restores the file after each round.
# This is the meta-test: it verifies the battery is actually able to
# detect known-bad changes — without it, a green battery is consistent
# with both "no regression" AND "battery is permanently broken".
#
# Sabotage rounds (each sabotage is a single one-line change that
# disables one preprocessing rule):
#
#   1. Icon-strip rule 6 (viewBox-only fallback) — would let small
#      decorative SVGs leak into output. Caught by `min_images=1` on
#      the regression-icon-svg-mintlify fixture (which would produce
#      26 images instead of 1).
#   2. Mintlify Steps flatten — would lose the "1. Install" / "2. Configure"
#      heading prefixes. Caught by required_needles on the
#      regression-mintlify-steps fixture.
#   3. Reader-mode keyword strip — would let reaction widgets / share
#      bars survive into reader-mode output. Caught by forbidden_needles
#      on the regression-reader-mode-vcru reader entry.
#
# Usage:
#   bash skills/docx/scripts/tests/canary_check.sh
#
# Exit codes:
#   0 — all sabotages were caught (battery is healthy)
#   1 — one or more sabotages went undetected (battery has coverage gap)
#   2 — environment problem (missing .venv / file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PP="$SKILL_DIR/_html2docx_preprocess.js"
PY="$SKILL_DIR/.venv/bin/python"
BACKUP="$(mktemp -t pp_backup_XXXX).js"
trap 'cp "$BACKUP" "$PP"; rm -f "$BACKUP" "${PP}.bak"' EXIT INT TERM

[ -f "$PP" ] || { echo "ERROR: $PP not found" >&2; exit 2; }
[ -x "$PY" ] || { echo "ERROR: $PY not executable" >&2; exit 2; }

cp "$PP" "$BACKUP"

cd "$SKILL_DIR"

failures=0
rounds=0

run_round() {
    local name="$1"; shift
    local sabotage_cmd="$1"; shift
    rounds=$((rounds + 1))
    cp "$BACKUP" "$PP"
    eval "$sabotage_cmd"
    if ! grep -q "CANARY_SABOTAGE" "$PP"; then
        echo "  ✗ $name: sabotage marker not present — sed pattern did not match"
        failures=$((failures + 1))
        return
    fi
    if "$PY" -m unittest tests.test_battery > /tmp/canary-out 2>&1; then
        echo "  ✗ $name: battery passed despite sabotage — coverage gap"
        failures=$((failures + 1))
    else
        echo "  ✓ $name: battery correctly FAILED"
    fi
}

echo "canary check (q-7 LOW-3):"

run_round "icon-strip rule 6 (viewBox-only fallback disabled)" \
    "sed -i.bak \"s|if (Math.max(parts\\[2\\], parts\\[3\\]) <= _ICON_MAX_PX) return true;|/* CANARY_SABOTAGE */ return false;|\" \"\$PP\""

run_round "Mintlify Steps flatten (h4 → p)" \
    "sed -i.bak \"s|pieces.push(\\\`<h4>\\\${n}\\. \\\${titleHtml}</h4>\\\`)|/* CANARY_SABOTAGE */ pieces.push(\\\`<p>\\\${titleHtml}</p>\\\`)|\" \"\$PP\""

run_round "reader-mode keyword strip (no-op)" \
    'sed -i.bak "s|stripSelector).remove();|stripSelector); /* CANARY_SABOTAGE */|" "$PP"'

# Restore (trap also fires) and report.
cp "$BACKUP" "$PP"

echo
if [ "$failures" -eq 0 ]; then
    echo "canary: $rounds/$rounds sabotages detected — battery is healthy"
    exit 0
else
    echo "canary: $failures/$rounds sabotages went undetected — battery has coverage gaps"
    exit 1
fi
