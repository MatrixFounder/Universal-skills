#!/usr/bin/env bash
# Run E2E smoke suites for all 4 office skills sequentially.
#
# Each per-skill suite is self-contained — assertions count themselves
# and exit non-zero on first failure. This wrapper just records pass/
# fail per skill and prints a summary; it does NOT abort on first skill
# failure so you can see what's broken across the whole repo in one run.
#
# Usage:
#   bash tests/run_all_e2e.sh
#
# Exit 0 iff every suite was green.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

results=()
overall=0
for skill in docx pptx xlsx pdf; do
    suite="skills/$skill/scripts/tests/test_e2e.sh"
    if [ ! -x "$suite" ]; then
        printf '\n=== %s ===\n%s\n' "$skill" "skipped (no test_e2e.sh)"
        results+=("$skill: SKIPPED")
        continue
    fi
    printf '\n=== %s ===\n' "$skill"
    if bash "$suite"; then
        results+=("$skill: PASS")
    else
        results+=("$skill: FAIL")
        overall=1
    fi
done

echo
echo "==================================="
for r in "${results[@]}"; do
    printf '  %s\n' "$r"
done
echo "==================================="

exit "$overall"
