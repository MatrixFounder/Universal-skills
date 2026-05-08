#!/usr/bin/env bash
# Canary saboteur runner for xlsx-7 regression battery.
#
# Each saboteur:
#   1. Saves the source file (cp <file> <file>.bak).
#   2. Patches the source via sed (BSD/GNU portable: -i.tmp + rm).
#   3. Runs `python -m unittest tests.test_battery.<TestClass>.<test>`
#      and asserts the test FAILED (the saboteur successfully broke
#      the battery).
#   4. Reverts via function-scoped trap.
#
# Final exit 0 means every ATTEMPTED saboteur broke its target
# (skipped saboteurs whose 003.04b fixtures are pending DON'T
# count as failures). A non-zero exit means at least one ACTIVE
# saboteur did NOT break the battery — the battery is silently
# passing.
#
# Saboteurs whose target fixtures are NOT yet authored (003.04b
# pending) are SKIPPED with a clear message; they'll activate when
# the manifests land.
#
# PRECONDITION (003.04b authors): every saboteur-targeted manifest
# MUST set `xfail: false`. With xfail: true the wrapped test exits 0
# even when the saboteur breaks it (unittest reports "expected
# failure"), and exits 1 when it PASSES (unittest reports
# "unexpected success"). The detection logic below grep'ses
# unittest output for explicit `FAILED (failures=` /
# `FAILED (errors=` and rejects `unexpected success` so xfail
# saboteurs surface as FAIL rather than as silent ✓ broke.
#
# Run:  bash skills/xlsx/scripts/tests/canary_check.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG="$SCRIPTS_DIR/xlsx_check_rules"
PY="$SCRIPTS_DIR/.venv/bin/python"
MANIFESTS="$SCRIPT_DIR/golden/manifests"

PASS=0
FAIL=0
SKIP=0

_skip_if_missing_manifest() {
    # If the manifest file doesn't exist, the saboteur cannot run —
    # 003.04b authors the missing fixture. Skip gracefully.
    local manifest_stem="$1"
    if [ ! -f "$MANIFESTS/${manifest_stem}.yaml" ]; then
        echo "  - SKIP saboteur (fixture ${manifest_stem}.yaml not yet authored — 003.04b dep)"
        SKIP=$((SKIP + 1))
        return 0
    fi
    return 1
}

_run_saboteur() {
    local id="$1" desc="$2" file="$3"
    local pattern="$4" replacement="$5" test_dotted="$6"

    if [ ! -f "$file" ]; then
        echo "  ✗ saboteur $id ($desc): SOURCE NOT FOUND $file"
        FAIL=$((FAIL + 1))
        return 0
    fi

    cp "$file" "$file.bak"
    # Function-scoped trap registered IMMEDIATELY after .bak exists
    # (Sarcasmotron Issue 3 — close the un-trapped window). Revert ON
    # RETURN (NOT on EXIT — RETURN fires when this function returns,
    # BEFORE the next saboteur touches the same file). Drop the
    # `|| true` swallower so revert failure surfaces as exit code.
    trap "mv '$file.bak' '$file'; rm -f '$file.tmp'" RETURN

    # BSD-portable in-place sed: write to .tmp then drop it.
    if ! sed -i.tmp "s|$pattern|$replacement|" "$file" 2>/dev/null; then
        echo "  ✗ saboteur $id ($desc): SED PATTERN FAILED"
        FAIL=$((FAIL + 1))
        return 0
    fi
    rm -f "$file.tmp"

    # Sarcasmotron BLOCKER 2: sed exits 0 when pattern doesn't match
    # (only invalid regex syntax fails). Confirm the file ACTUALLY
    # changed — otherwise the saboteur is a no-op and any subsequent
    # test failure is unrelated to the patch.
    if cmp -s "$file" "$file.bak"; then
        echo "  ✗ saboteur $id ($desc): SED MATCHED ZERO LINES (pattern '$pattern' absent from $file)"
        FAIL=$((FAIL + 1))
        return 0
    fi

    # Sarcasmotron BLOCKER 1: rc-only is fooled by xfail wrapping.
    # An xfail-decorated test that stays-failing after sabotage
    # exits 0 (expected failure); an xfail test that PASSES after
    # sabotage exits 1 (unexpected success) — which the saboteur
    # would mis-report as "broke." Capture unittest's textual
    # outcome and require an explicit "FAILED (failures=" or
    # "FAILED (errors=" — those are the ONLY outcomes that prove
    # the saboteur corrupted the targeted code path.
    local out
    out="$(cd "$SCRIPTS_DIR" && "$PY" -m unittest "$test_dotted" 2>&1 || true)"
    if echo "$out" | grep -qE 'FAILED \((failures|errors)='; then
        echo "  ✓ saboteur $id ($desc): broke $test_dotted"
        PASS=$((PASS + 1))
    elif echo "$out" | grep -qE 'unexpected success'; then
        # xfail target that flipped to pass — saboteur did NOT
        # corrupt the path; it removed an unrelated guard letting
        # the body succeed. Treat as failure of the saboteur.
        echo "  ✗ saboteur $id ($desc): unexpected success on xfail target — saboteur path mismatch"
        FAIL=$((FAIL + 1))
    else
        echo "  ✗ saboteur $id ($desc): did NOT break $test_dotted (unittest: OK or expected-failure)"
        FAIL=$((FAIL + 1))
    fi
}

echo "canary_check.sh — 10 saboteurs per SPEC §13.3"
echo

# Saboteur 04: skip merged-cell detection in headers (fixture #5 = multi-row-headers, EXISTS in 003.04a)
echo "Saboteur 04: skip merged-header check"
_skip_if_missing_manifest "multi-row-headers" || _run_saboteur 04 "skip merged-header check" \
    "$PKG/scope_resolver.py" \
    "raise MergedHeaderUnsupported" \
    'pass  # SABOTEUR' \
    "tests.test_battery.BatteryTestCase.test_multi_row_headers"

# Saboteur 07: disable composite depth cap (fixture #27 = deep-composite, 003.04b PENDING)
echo "Saboteur 07: disable composite depth cap"
if _skip_if_missing_manifest "deep-composite"; then :; else
    _run_saboteur 07 "disable composite depth cap" \
        "$PKG/dsl_parser.py" \
        "if depth >= COMPOSITE_MAX_DEPTH" \
        "if False" \
        "tests.test_battery.BatteryTestCase.test_deep_composite"
fi

# Saboteur 01: regex matcher always True (fixture #22 = regex-dos, 003.04b PENDING)
echo "Saboteur 01: regex always True"
if _skip_if_missing_manifest "regex-dos"; then :; else
    _run_saboteur 01 "regex always True" \
        "$PKG/evaluator.py" \
        "cached.fullmatch(value, timeout=" \
        "(lambda *a, **kw: True)(value, timeout=" \
        "tests.test_battery.BatteryTestCase.test_regex_dos"
fi

# Saboteur 02: sum_by ignores group key (fixture #11 = mixed-types-aggregate or aggregate-cache, 003.04b PENDING)
echo "Saboteur 02: sum_by ignores group key"
if _skip_if_missing_manifest "aggregate-cache"; then :; else
    _run_saboteur 02 "sum_by ignores group key" \
        "$PKG/aggregates.py" \
        "def eval_group_by" \
        "def _disabled_eval_group_by" \
        "tests.test_battery.BatteryTestCase.test_aggregate_cache"
fi

# Saboteur 03: text-stored dates always parse (fixture #15 = localized-dates-ru-text, 003.04b PENDING)
echo "Saboteur 03: auto-parse text dates"
if _skip_if_missing_manifest "localized-dates-ru-text"; then :; else
    _run_saboteur 03 "auto-parse text dates" \
        "$PKG/cell_types.py" \
        "_column_in_set(col, treat_text)" \
        "True  # SABOTEUR" \
        "tests.test_battery.BatteryTestCase.test_localized_dates_ru_text"
fi

# Saboteur 05: disable AliasEvent reject (fixture #23 = billion-laughs, 003.04b PENDING)
echo "Saboteur 05: disable YAML AliasEvent reject"
if _skip_if_missing_manifest "billion-laughs"; then :; else
    _run_saboteur 05 "disable YAML AliasEvent reject" \
        "$PKG/rules_loader.py" \
        "if isinstance(ev, AliasEvent):" \
        "if False:" \
        "tests.test_battery.BatteryTestCase.test_billion_laughs"
fi

# Saboteur 06: disable D5 ReDoS lint (fixture #22 = regex-dos, 003.04b PENDING)
echo "Saboteur 06: disable D5 ReDoS lint"
if _skip_if_missing_manifest "regex-dos"; then :; else
    _run_saboteur 06 "disable D5 ReDoS lint" \
        "$PKG/dsl_parser.py" \
        "raise RegexLintFailed" \
        "pass  # SABOTEUR" \
        "tests.test_battery.BatteryTestCase.test_regex_dos"
fi

# Saboteur 08: skip cell-error auto-emit (fixture #10 = errors-as-values, 003.04b PENDING)
echo "Saboteur 08: skip cell-error auto-emit"
if _skip_if_missing_manifest "errors-as-values"; then :; else
    _run_saboteur 08 "skip cell-error auto-emit" \
        "$PKG/evaluator.py" \
        'rule_id="cell-error"' \
        'rule_id="suppressed-by-saboteur"' \
        "tests.test_battery.BatteryTestCase.test_errors_as_values"
fi

# Saboteur 09: disable aggregate cache (fixture #19 = aggregate-cache, 003.04b PENDING)
echo "Saboteur 09: disable aggregate cache hits counter"
if _skip_if_missing_manifest "aggregate-cache"; then :; else
    _run_saboteur 09 "disable aggregate cache hits" \
        "$PKG/aggregates.py" \
        "ctx.aggregate_cache_hits += 1" \
        "pass  # SABOTEUR" \
        "tests.test_battery.BatteryTestCase.test_aggregate_cache"
fi

# Saboteur 10: str.format instead of string.Template (fixture #29 = format-string-injection, 003.04b PENDING)
echo "Saboteur 10: str.format injection"
if _skip_if_missing_manifest "format-string-injection"; then :; else
    _run_saboteur 10 "str.format injection" \
        "$PKG/evaluator.py" \
        "template.safe_substitute(mapping)" \
        "template_str.format(**mapping)" \
        "tests.test_battery.BatteryTestCase.test_format_string_injection"
fi

echo
echo "canary_check.sh: PASS=$PASS FAIL=$FAIL SKIP=$SKIP (active saboteurs verify the battery; skips clear once 003.04b ships)"

# Exit 0 iff no saboteur failed (skipped saboteurs DON'T fail the run).
if [ "$FAIL" -eq 0 ]; then
    if [ "$PASS" -gt 0 ]; then
        echo "All ACTIVE saboteurs broke their target fixture — meta-test PASSED."
    else
        echo "WARNING: zero active saboteurs (003.04b fixtures all pending)"
    fi
    exit 0
fi
echo "Meta-test FAILED: $FAIL saboteur(s) did NOT break the battery"
exit 1
