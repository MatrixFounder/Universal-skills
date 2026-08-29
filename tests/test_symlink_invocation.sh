#!/usr/bin/env bash
# Regression guard for the symlinked-invocation class of defect.
#
# Every skill is installed by symlink, e.g.
#   ~/.claude/skills/pdf -> <repo>/skills/pdf
# A test harness that derives the repo root with bash's LOGICAL pwd keeps the
# symlinked prefix, so "$SKILL_DIR/../../.." escapes the repository entirely
# (it lands in ~/.claude). In the office suites that made `source
# "$ROOT/tests/visual/_visual_helper.sh"` fail, which under `set -e` aborted
# the whole suite — and, because of the EXIT trap, still exited 0.
#
# CI only ever invokes the suites from the repo root, where logical and
# physical pwd coincide, so nothing caught it. This test invokes each suite
# THROUGH A SYMLINK, which is what actually happens in use.
#
# It does not run the suites: each one exits right after its preamble when
# E2E_PREAMBLE_ONLY is set, printing the paths it resolved. The invariant
# asserted here is simply: no resolved path may point outside the repository.
#
# Run:  bash tests/test_symlink_invocation.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/.." && pwd -P)"
LINKS="$(mktemp -d -t skill_symlink_XXXX)"
trap 'rm -rf "$LINKS"' EXIT

pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

echo "symlinked-invocation path resolution:"

for suite in "$ROOT"/skills/*/scripts/tests/test_e2e.sh; do
    [ -f "$suite" ] || continue
    skill="$(basename "$(dirname "$(dirname "$(dirname "$suite")")")")"

    # Stand up a symlink that mimics the installed layout.
    ln -sfn "$ROOT/skills/$skill" "$LINKS/$skill"
    linked="$LINKS/$skill/scripts/tests/test_e2e.sh"

    if [ ! -f "$linked" ]; then
        nok "$skill: symlink fixture" "$linked not reachable"
        continue
    fi

    out=$(E2E_PREAMBLE_ONLY=1 bash "$linked" 2>&1)
    rc=$?

    if [ "$rc" -ne 0 ]; then
        nok "$skill: preamble through symlink" "exit=$rc out=$out"
        continue
    fi

    paths=$(printf '%s\n' "$out" | grep '^E2E_SELFTEST_PATH ')
    if [ -z "$paths" ]; then
        nok "$skill: self-test hook" "suite printed no E2E_SELFTEST_PATH line; out=$out"
        continue
    fi

    # Every reported path must resolve inside the repository. Read line by
    # line and strip the prefix literally: a checkout path may contain
    # spaces (word-splitting would shred it) or glob metacharacters (a
    # `case` pattern would interpret them rather than match literally).
    escaped=""
    while IFS= read -r line; do
        kv="${line#E2E_SELFTEST_PATH }"
        val="${kv#*=}"
        if [ "$val" = "$ROOT" ] || [ "${val#"$ROOT"/}" != "$val" ]; then
            continue
        fi
        escaped="$escaped $kv"
    done <<INNER_EOF
$paths
INNER_EOF

    if [ -n "$escaped" ]; then
        nok "$skill: resolved paths stay inside the repo" "escaped:$escaped (repo=$ROOT)"
    else
        ok "$skill: resolved paths stay inside the repo"
    fi
done

# A suite that dies mid-run must not report success. The office suites used
# `trap 'rm -rf "$TMP"' EXIT`, and on bash 3.2 (macOS default) a set -e abort
# reaches the EXIT trap with $? already reset to 0 — so the suite exited 0
# after aborting. The sentinel in the trap is what makes that honest.
echo "abort must not report success:"
for suite in "$ROOT"/skills/*/scripts/tests/test_e2e.sh; do
    [ -f "$suite" ] || continue
    skill="$(basename "$(dirname "$(dirname "$(dirname "$suite")")")")"
    grep -q "trap " "$suite" || { ok "$skill: no EXIT trap to mask an abort"; continue; }
    if grep -q 'FINISHED' "$suite"; then
        ok "$skill: EXIT trap carries the abort sentinel"
    else
        nok "$skill: EXIT trap carries the abort sentinel" "trap can mask a set -e abort as exit 0"
    fi
done

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
