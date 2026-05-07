# Task 2.08 [R8]: [LOGIC IMPLEMENTATION] Output integrity & idempotency hooks

## Use Case Connection
- I3.2 (Output validates clean).
- R8 (output integrity + deterministic-where-possible).
- R8.b (pre-existing comments byte-equivalent).
- R8.c (`.xlsm` macros preserved).
- RTM: R8.

## Task Goal
Wire post-write integrity verification: every E2E that produces a workbook ALSO verifies the result via `office/validate.py` and `xlsx_validate.py --fail-empty`. Add a regression-grade test for `.xlsm` macro preservation. Document and lock the determinism scope from R8.d (UUIDv4 non-determinism on `<threadedComment id>` is acknowledged honest-scope; everything else is deterministic).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

**Modify the xlsx_add_comment block:** every test that produces a `$OUT` file now runs an additional validation pair AFTER its existing assertions:

```bash
"$PY" -m office.validate "$OUT" >/dev/null 2>&1 \
    && ok "T-NAME — office.validate green" \
    || nok "T-NAME — office.validate" "rejected the produced .xlsx"

"$PY" xlsx_validate.py "$OUT" --fail-empty >/dev/null 2>&1 \
    && ok "T-NAME — xlsx_validate --fail-empty green" \
    || nok "T-NAME — xlsx_validate --fail-empty" "produced workbook has empty cached values"
```

Run this validation pair on at least: `T-clean-no-comments`, `T-threaded`, `T-multi-sheet`, `T-batch-50`, `T-batch-50-with-existing-vml`, `T-existing-legacy-preserve`. (Skipping it on intentional-failure tests like `T-encrypted` / `T-merged-cell-target` — those don't produce a file.)

**New test `T-macro-xlsm-preserves`:** Input `golden/inputs/macro.xlsm` + `--cell A5 --author Q --text "msg" --output out.xlsm`:
- Exit 0.
- Produced `out.xlsm` has `xl/vbaProject.bin` byte-equivalent to input's (or at least non-empty + identical-content; use `unzip -p macro.xlsm xl/vbaProject.bin | sha256sum` and compare).
- Stderr does NOT have a macro-loss warning (since extension is preserved).

**New test `T-macro-xlsm-warns`:** Same input but `--output out.xlsx`:
- Exit 0 (warning is non-fatal per cross-4 contract).
- Stderr contains warning text mentioning "macros".
- Produced `out.xlsx` does NOT contain `xl/vbaProject.bin` (LibreOffice/openpyxl would drop it; xlsx-6's behaviour is to let the existing macro-aware unpacker handle it).

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**No new functions** — this task is mostly test-side. BUT add a tiny post-pack assertion inside `main()` for defence-in-depth:

```python
# After office.pack():
from office.validate import validate_xlsx_structure  # if exposed; else subprocess call
result = validate_xlsx_structure(args.output)
if not result.ok:
    raise OutputIntegrityFailure(result.errors)  # exit 1 IOError class
```

If `office.validate` doesn't expose a Python API (it's a CLI), use `subprocess.run([sys.executable, "-m", "office.validate", str(args.output)], capture_output=True)` and check exit code. **Important:** this guard catches developer errors during xlsx-6 implementation, not user input — it's a paranoid post-condition, not a substitute for input validation.

### Component Integration
- `office/validate.py` and `xlsx_validate.py` are existing tools; this task only wires them into the integrity verification.
- The post-pack assertion is opt-in via an env var `XLSX_ADD_COMMENT_POST_VALIDATE=1` so production runs aren't slowed by an extra subprocess invocation. CI / E2E tests set the env var.

## Test Cases

### End-to-end Tests
- All produced-file tests now have integrity-pair assertions.
- **TC-E2E-T-macro-xlsm-preserves** (new).
- **TC-E2E-T-macro-xlsm-warns** (new).

### Unit Tests
- New: `TestPostValidateGuard.test_env_var_off_skips_validation`: `XLSX_ADD_COMMENT_POST_VALIDATE` unset → no subprocess call (mock `subprocess.run`).
- New: `TestPostValidateGuard.test_env_var_on_runs_validation`: env var set → subprocess called once.

### Regression Tests
- All previous tests stay green.
- **R8.b lock:** modify `T-existing-legacy-preserve` to use `lxml.etree.tostring(method='c14n')` to compare the original 2 `<comment>` elements byte-for-byte (canonical form) before and after — only the new 3rd `<comment>` should differ.

## Acceptance Criteria
- [ ] Every produce-and-pass E2E has an integrity-pair assertion.
- [ ] `T-macro-xlsm-preserves` passes (vbaProject.bin sha256 unchanged).
- [ ] `T-macro-xlsm-warns` passes (warning emitted, no exit 1).
- [ ] R8.b byte-equivalence test on `T-existing-legacy-preserve` passes.
- [ ] Post-pack guard implemented (gated by env var).
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The opt-in post-pack guard is intentionally NOT default-on — it doubles invocation latency for the user's no-op case. CI is the right place to enforce it.
- Macro preservation depends on `office.pack` and `office.unpack` correctly round-tripping `xl/vbaProject.bin` (which they do — the existing test in `office/tests/` confirms it). If this test fails, the bug is in `office/`, not in xlsx_add_comment, and would be a CLAUDE.md §2 cross-skill issue.
