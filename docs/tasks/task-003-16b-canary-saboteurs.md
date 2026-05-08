# Task 003.16b: 10 canary saboteurs functional + meta-test green

> **Split origin:** plan-reviewer M-3 split. 003.16a delivered the perf fixture, the xlsx-6 envelope cross-skill tests, and the final battery xfail sweep. This task implements the 10 canary saboteurs and verifies the meta-test (`bash tests/canary_check.sh`) exits 0 — meaning every saboteur successfully breaks a specific battery test.

## Use Case Connection
- **I9.3** (canary saboteurs functional).
- **R10.e** (`summary.aggregate_cache_hits` saboteur anchor).
- **R12.b** (10 canary saboteurs in `tests/canary_check.sh`).

## Task Goal
Implement the 10 canary saboteurs in `tests/canary_check.sh` per SPEC §13.3. Each saboteur (a) saves the source file, (b) patches it (`sed -i` or similar) to break a specific invariant, (c) runs `python -m unittest tests.test_battery -k <fixture>` and **asserts the test FAILED** (the saboteur successfully broke the battery), (d) reverts the source file via `trap`. Final exit 0 from the script means every saboteur did its job — the battery is not silently passing.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/canary_check.sh`

Replace the 003.02 skeleton with all 10 functional saboteurs. Each maps to SPEC §13.3:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPTS=skills/xlsx/scripts
PKG="$SCRIPTS/xlsx_check_rules"
PY="$SCRIPTS/.venv/bin/python"

# Helper: patch a file, run a battery test, expect FAILURE, revert.
_run_saboteur() {
    local id="$1"; local desc="$2"; local file="$3"
    local pattern="$4"; local replacement="$5"; local fixture="$6"
    cp "$file" "$file.bak"
    trap "mv '$file.bak' '$file'" RETURN
    sed -i.tmp "s|$pattern|$replacement|" "$file"
    rm -f "$file.tmp"
    if (cd "$SCRIPTS" && "$PY" -m unittest "tests.test_battery.${fixture}" 2>/dev/null); then
        echo "FAIL: saboteur $id ($desc) did NOT break $fixture"
        return 1
    fi
    echo "OK: saboteur $id ($desc) broke $fixture"
}

# Saboteur 01: regex matcher always True -> fixtures #2, #22 fail
_run_saboteur 01 "regex always True" \
    "$PKG/evaluator.py" \
    "regex_compile(pattern).fullmatch" \
    "(lambda *a, **kw: True)" \
    "test_fixture_22_regex_dos"

# Saboteur 02: sum_by ignores group key -> fixture #11 fails
_run_saboteur 02 "sum_by ignore key" \
    "$PKG/aggregates.py" \
    "def eval_group_by" \
    "def _disabled_group_by" \
    "test_fixture_11_mixed_types_aggregate"

# Saboteur 03: text-stored dates always parse (bypass §5.4.1 path-4 opt-in)
# -> fixture #15 (must misfire WITHOUT flag) and #16 (must fire WITH flag) both invariants break
_run_saboteur 03 "auto-parse text dates" \
    "$PKG/cell_types.py" \
    "treat_text_as_date.*opts" \
    "True or False  # SABOTEUR" \
    "test_fixture_15_localized_dates_ru_text"

# Saboteur 04: skip merged-cell detection in headers -> fixture #5 silent misfire
_run_saboteur 04 "skip merged header check" \
    "$PKG/scope_resolver.py" \
    "raise MergedHeaderUnsupported" \
    "pass  # SABOTEUR" \
    "test_fixture_5_multi_row_headers"

# Saboteur 05: disable ruamel.yaml AliasEvent rejection -> fixture #23 no longer exits 2
_run_saboteur 05 "no AliasEvent reject" \
    "$PKG/rules_loader.py" \
    "if isinstance(ev, AliasEvent)" \
    "if False" \
    "test_fixture_23_billion_laughs"

# Saboteur 06: disable D5 ReDoS pattern lint -> fixture #22 fails or timeout > 100 ms
_run_saboteur 06 "no ReDoS lint" \
    "$PKG/dsl_parser.py" \
    "raise RegexLintFailed" \
    "pass  # SABOTEUR" \
    "test_fixture_22_regex_dos"

# Saboteur 07: disable composite depth cap -> fixture #27 no longer exits 2
_run_saboteur 07 "no composite depth cap" \
    "$PKG/dsl_parser.py" \
    "if depth > COMPOSITE_MAX_DEPTH" \
    "if False" \
    "test_fixture_27_deep_composite"

# Saboteur 08: skip cell-error auto-emit -> fixture #10 missing cell-error rule_id
_run_saboteur 08 "no cell-error auto-emit" \
    "$PKG/evaluator.py" \
    'rule_id="cell-error"' \
    'rule_id="suppressed-by-saboteur"' \
    "test_fixture_10_errors_as_values"

# Saboteur 09: disable aggregate cache -> fixture #19 aggregate_cache_hits == 0
_run_saboteur 09 "no aggregate cache" \
    "$PKG/aggregates.py" \
    "entry.cache_hits += 1" \
    "pass  # SABOTEUR" \
    "test_fixture_19_aggregate_cache"

# Saboteur 10: use str.format instead of string.Template
# -> fixture #29 leaks Python attribute access in message
_run_saboteur 10 "str.format injection" \
    "$PKG/evaluator.py" \
    "string.Template(template_str).safe_substitute" \
    "template_str.format" \
    "test_fixture_29_format_string_injection"

echo
echo "All 10 canary saboteurs successfully broke the battery — meta-test PASSED."
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Add a `TestCanaryMeta` class with one method:
- `test_canary_check_sh_exits_zero` — runs `bash skills/xlsx/scripts/tests/canary_check.sh` via subprocess; asserts exit 0. Skips on CI if `RUN_CANARY_META_TEST=0` is set (gate; default ON locally and in CI).

## Test Cases
- Unit: 1 new test (the meta-test wrapper).
- Battery: no changes (003.16a sweep already removed all xfails).
- Canary: `bash tests/canary_check.sh` exits 0 (every saboteur breaks its target fixture).

## Acceptance Criteria
- [ ] `tests/canary_check.sh` has 10 functional saboteur blocks per SPEC §13.3.
- [ ] `bash tests/canary_check.sh` exits 0; each saboteur's STDOUT line `OK: saboteur NN (desc) broke fixture_NN` is printed.
- [ ] Each saboteur uses `trap` cleanup so source files are reverted even on partial failure.
- [ ] `TestCanaryMeta` test green.
- [ ] `validate_skill.py` exits 0.

## Notes
- The `sed -i.tmp` pattern is portable across BSD sed (macOS) and GNU sed; the `.tmp` extension is required by BSD sed even when nothing is done with the backup. The `rm -f "$file.tmp"` line discards it.
- For saboteur 03 (text-as-date auto-parse) the patched line MUST keep Python parseable — `True or False  # SABOTEUR` is a no-op syntactically but flips the gate semantically. If the original code is more complex, adjust the regex.
- For saboteur 09 (disable cache hits): the test needs to detect `summary.aggregate_cache_hits == 0`. The existing fixture #19 expected envelope has `aggregate_cache_hits: 4`; with the saboteur in place it becomes `0`, the assertion fails, the saboteur succeeds.
- If a saboteur's `sed` pattern doesn't match (because the source file changed shape), the saboteur runs the test with NO patch applied — the test passes — the script reports FAIL: did NOT break. This is a useful signal that the patterns need updating, not a false alarm.
- `_run_saboteur` uses `trap ... RETURN` (bash function-scoped trap, not EXIT) so each saboteur's revert happens before the next one runs. EXIT trap would queue all reverts to script-end which races.
