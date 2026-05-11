# Task 004.08: Post-validate hook logic + synthetic round-trip green + remaining E2E green

## Use Case Connection
- **UC-5** (synthetic xlsx-8 round-trip green), R10 (post-validate hook full logic), and final E2E completion across all UCs.

## Task Goal
Implement F6 post-validate logic in `cli_helpers.run_post_validate` (subprocess invocation of `office/validators/xlsx.py` with 60 s timeout). Finalise the synthetic xlsx-8 round-trip E2E (`T-roundtrip-xlsx8-synthetic` from 004.02) — green assertion against `tests/golden/json2xlsx_xlsx8_shape.json`. Confirm cleanup-on-failure (output unlinked when post-validate fails). **At task-end, every E2E case from 004.02 is GREEN.**

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/cli_helpers.py`

Replace `run_post_validate` stub:

```python
def run_post_validate(output: Path) -> tuple[bool, str]:
    """Invoke office/validators/xlsx.py on `output` via subprocess.

    Returns (passed: bool, captured_output: str). Captured output is
    truncated to 8192 bytes by the caller before being placed in the
    envelope details.

    Hermeticity: env is constructed from scratch (not `os.environ.copy()`)
    so the post-validate hook can't accidentally recurse into another
    XLSX_JSON2XLSX_POST_VALIDATE=1 invocation. Mirrors xlsx-6
    `_run_post_validate` precedent.
    """
    # Locate the validator. It lives at office/validators/xlsx.py
    # relative to the scripts/ directory (i.e., next to this module's
    # package).
    pkg_dir = Path(__file__).resolve().parent  # …/json2xlsx
    scripts_dir = pkg_dir.parent                # …/scripts
    validator = scripts_dir / "office" / "validators" / "xlsx.py"

    if not validator.is_file():
        # Defensive: validator missing means the skill is broken;
        # report rather than crash.
        return False, f"validator not found: {validator}"

    # Use the same Python that's running us (the active venv).
    proc = subprocess.run(
        [sys.executable, str(validator), str(output)],
        capture_output=True,
        timeout=60,
        env={"PATH": os.environ.get("PATH", ""),
             "PYTHONPATH": str(scripts_dir)},
        check=False,
    )
    captured = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    return proc.returncode == 0, captured
```

#### File: `skills/xlsx/scripts/tests/test_json2xlsx.py`

Finalise `T-roundtrip-xlsx8-synthetic` test (was scaffolded RED in 004.02):

```python
class TestRoundTripXlsx8(unittest.TestCase):
    """Synthetic xlsx-8 round-trip — locks UC-5 contract in v1.
    Live wiring (T-roundtrip-xlsx8-live) is gated by AQ-5
    @unittest.skipUnless until xlsx-8 lands.
    """
    GOLDEN = Path(__file__).parent / "golden" / "json2xlsx_xlsx8_shape.json"

    def test_synthetic_roundtrip(self):
        # Use the public helper for programmatic use.
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            rc = convert_json_to_xlsx(str(self.GOLDEN), str(out))
            self.assertEqual(rc, 0)
            wb = openpyxl.load_workbook(out)
            self.assertEqual(wb.sheetnames, ["Employees", "Departments"])
            emp = wb["Employees"]
            self.assertEqual([c.value for c in emp[1]], ["Name", "Hired", "Salary", "Active"])
            self.assertEqual(emp["A2"].value, "Alice")
            self.assertEqual(emp["B2"].value, date(2024, 1, 15))
            self.assertEqual(emp["C2"].value, 100000)
            self.assertIs(emp["D2"].value, True)
            self.assertIsNone(emp["C4"].value)  # Carol's null salary
            self.assertIs(emp["D4"].value, False)
            dept = wb["Departments"]
            self.assertEqual([c.value for c in dept[1]], ["Dept", "Head", "HC"])
        finally:
            out.unlink(missing_ok=True)

    @unittest.skipUnless(_xlsx2json_available(), "xlsx-8 not landed yet")
    def test_live_roundtrip(self):
        """Live test: xlsx2json(original) → JSON → json2xlsx → assert
        structural equivalence. Activated automatically when xlsx-8
        lands and importing `xlsx2json` succeeds.
        """
        # Implementation reserved for xlsx-8's merge commit.
        self.skipTest("Implementation deferred to xlsx-8 merge commit.")


def _xlsx2json_available() -> bool:
    try:
        import xlsx2json  # noqa: F401
        return True
    except ImportError:
        return False
```

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Activate `T-roundtrip-xlsx8-synthetic` in the xlsx-2 block: full assertion vs `tests/golden/json2xlsx_xlsx8_shape.json` (sheet names, headers, A2/B2/C2/D2 cell values, null preservation, bool preservation).

Add a new E2E case `T-post-validate-on-good-workbook`:
- Set `XLSX_JSON2XLSX_POST_VALIDATE=1`; run on valid input; exit 0; output file remains.

Add a new E2E case `T-post-validate-on-bad-workbook`:
- Mock failure path: this is harder to trigger in pure E2E because xlsx-2 produces structurally valid xlsx. Use a unit-test alternative `TestCliHelpers::test_run_post_validate_failure_unlinks_output` that monkeypatches `run_post_validate` to return `(False, "synthetic failure")` and asserts the output file is unlinked + exit 7 + envelope `type: PostValidateFailed`.

(11 cases → 12 cases.)

### Component Integration

- The post-validate hook is **off by default**. It's exercised by the env-gated tests in this task and never activated in CI by default. Matches xlsx-6 / xlsx-7 precedent.

## Test Cases

### Unit Tests (turn green in this task)

1. `test_run_post_validate_success` — on a valid xlsx (built by json2xlsx), returns `(True, "")`.
2. `test_run_post_validate_missing_validator` — temporarily renames the validator; returns `(False, "validator not found: …")` (defensive path).
3. `test_run_post_validate_failure_unlinks_output` — monkeypatch returns failure; CLI's `_run` unlinks output + returns exit 7 envelope.
4. `test_run_post_validate_truthy_off_skips_invocation` — `XLSX_JSON2XLSX_POST_VALIDATE=` (empty) → `run_post_validate` NOT called (verified by mock-spy).
5. `test_post_validate_timeout_safety` — synthetic subprocess that sleeps 90 s → `subprocess.TimeoutExpired` raised; caller handles → exit 7. (Optional: may be marked skip if the 60 s wall makes CI slow; use a unit-test-only timeout override env var if needed.)

### E2E Tests (turn green this task)

- `T-roundtrip-xlsx8-synthetic` — full green; assertion against golden.
- `T-post-validate-on-good-workbook` — green.
- All other E2E cases from 004.02 verified still-green (regression check).

### Live test (skipped until xlsx-8 lands)

- `test_live_roundtrip` — skipped with reason "xlsx-8 not landed yet" (AQ-5 closure).

### Regression Tests
- All xlsx existing tests pass.

## Acceptance Criteria

- [ ] `run_post_validate` implemented with 60 s subprocess timeout + hermetic env construction.
- [ ] **11 E2E cases green** + **1 dedicated post-validate unit test (`test_run_post_validate_failure_unlinks_output`) for the cleanup path**. The bad-workbook E2E case is intentionally substituted by a monkeypatch unit test because xlsx-2 emits structurally valid workbooks; triggering a real validator failure in pure E2E is infeasible without hand-crafting a broken xlsx, which is a separate xlsx-7 / xlsx_validate concern. Plan-reviewer #5 honesty fix.
- [ ] Cleanup-on-failure verified by `test_run_post_validate_failure_unlinks_output`.
- [ ] Live round-trip test scaffolded, currently skipped (AQ-5 closure).
- [ ] `validate_skill.py` green; eleven `diff -q` silent.

## Notes

- The post-validate hook's subprocess invocation reads `office/validators/xlsx.py` from the same `scripts/` directory. This is a **read-only** access (we never write to `office/`), which is why the cross-skill `diff -q` × 11 stays silent — we touch nothing in the replication boundary.
- `subprocess.run(..., env={...})` constructs a minimal env containing only `PATH` and a fresh `PYTHONPATH` pointing at scripts/. This prevents post-validate recursion (a runaway scenario where the validator itself sets `XLSX_JSON2XLSX_POST_VALIDATE=1` and re-invokes us).
- The `timeout=60` is a reasonable cap; the validator should complete in milliseconds on small workbooks. If a 60 s timeout fires in CI, that's a bug in the validator, not in xlsx-2.
- This task is **purely additive**: no behaviour change in the happy path; the post-validate code is unreachable without the env var set.
