# Task 1.02: [STUB CREATION] E2E test scaffolding (16 ACs, red on stubs)

## Use Case Connection
- All E2E ACs from TASK §3 (clean-no-comments, existing-legacy preserve, threaded, threaded-rel-attachment, multi-sheet, merged-cell-target, merged-cell-redirect, batch-50, batch-50-with-existing-vml, apostrophe-sheet, same-path, encrypted, macro `.xlsm`, hidden-first-sheet, idmap-conflict, BatchTooLarge).
- RTM: prepares R1, R3, R4, R6, R7, R8 verification.

## Task Goal
Extend `skills/xlsx/scripts/tests/test_e2e.sh` with a new `xlsx_add_comment` block containing 16 named E2E test cases. At the end of this task each test runs and **passes against the stub** (the task-1.01 stub copies input to output — so the tests assert "output exists" and "exit code = 0", NOT real comment content). Real assertions arrive in the matching Stage-2 logic tasks.

## Changes Description

### New Files
- `skills/xlsx/scripts/tests/fixtures/xlsx_add_comment/` — directory of input fixtures referenced from test_e2e.sh. Most fixtures come from task 1.04 (golden); this task creates `examples/comments-batch.json` placeholder + a couple synthetic .xlsx via openpyxl in shell snippet form.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append a new section `# --- xlsx_add_comment ---` with 16 test cases following the existing `ok` / `nok` pattern. Each test has the shape:

```bash
"$PY" xlsx_add_comment.py "$IN" "$OUT" --cell A5 --author "Q" --text "msg" >/dev/null 2>&1 \
    && [ -s "$OUT" ] && ok "T-NAME (stub)" \
    || nok "T-NAME" "<error context>"
```

The 16 named cases are listed below; precise assertions are TODO-marked for the matching logic task:

1. `T-clean-no-comments` (stub: file produced; real: `xl/comments1.xml`, `xl/drawings/vmlDrawing1.xml`, both Overrides, both rels — task 2.04).
2. `T-existing-legacy-preserve` (stub: file produced; real: original 2 comments unmodified — task 2.04).
3. `T-threaded` (stub: file produced; real: personList present with stable UUIDv5(displayName) — task 2.05).
4. `T-thread-linkage` (stub: file produced; real: 2 threadedComment with same ref, same personId, distinct id — task 2.05).
5. `T-threaded-rel-attachment` (stub: file produced; real: personList rel in `xl/_rels/workbook.xml.rels` — task 2.05).
6. `T-multi-sheet` (stub: produced; real: commentsN binds to Sheet2 via `xl/_rels/sheet2.xml.rels`, N may be 1 — task 2.04).
7. `T-merged-cell-target` (stub: produced; real: exit 2 `MergedCellTarget` envelope — task 2.07).
8. `T-merged-cell-redirect` (stub: produced; real: exit 0 + info `MergedCellRedirect` to stderr — task 2.07).
9. `T-batch-50` (stub: produced; real: 50 comments across 3 sheets, no `o:idmap` data collisions, no `o:spid` collisions — task 2.06).
10. `T-batch-50-with-existing-vml` (stub: produced; real: existing `<o:idmap data="1"/>` and `_x0000_s1025` preserved; new uses disjoint integers — task 2.06).
11. `T-apostrophe-sheet` (stub: produced; real: comment lands on `Bob's Sheet!A1` — task 2.02).
12. `T-same-path` (stub: produced; real: exit 6 `SelfOverwriteRefused` envelope — task 2.01).
13. `T-encrypted` (stub: produced; real: exit 3 `EncryptedFileError` envelope — task 2.01).
14. `T-macro-xlsm` (stub: produced; real: `xl/vbaProject.bin` preserved + warning to stderr — task 2.01/2.08).
15. `T-hidden-first-sheet` (stub: produced; real: `--cell A5` (no qualifier) on workbook with hidden Sheet1 → comment lands on Sheet2 — task 2.02).
16. `T-idmap-conflict` (stub: produced; real: pre-existing `<o:idmap data="1"/>` → new uses `data="2"+`; pre-existing `_x0000_s1025` → new uses `2049+` or workbook-wide max+1 per m-1 — task 2.03).
17. `T-BatchTooLarge` (stub: produced; real: 9 MiB batch JSON → exit 2 `BatchTooLarge` envelope; size measured pre-parse via `Path.stat().st_size` — task 2.06).

(That's 17 — the +1 is for `T-BatchTooLarge` which the TASK §6 R10 AC counts separately. Plan covers ≥ 16; one extra is fine.)

### Component Integration
- The bash test runner already sources `_visual_helper.sh`; xlsx_add_comment tests do not need visual helpers.
- Each test routes its output through `>/dev/null 2>&1` and uses the `ok`/`nok` pass/fail counters already defined.

## Test Cases

### End-to-end Tests
*(see Changes — the 17 cases above ARE the test cases for this stage.)*

### Unit Tests
*(not in this task — see 1.03)*

### Regression Tests
- Existing tests in `test_e2e.sh` (csv2xlsx, xlsx_recalc, xlsx_validate, xlsx_add_chart) MUST stay green.

## Acceptance Criteria
- [ ] 17 new named test cases appended to `test_e2e.sh`.
- [ ] `bash skills/xlsx/scripts/tests/test_e2e.sh` exits 0 (all stub assertions pass).
- [ ] Each test has a TODO comment referencing the Stage-2 task that will replace the stub assertion.
- [ ] Existing csv2xlsx + xlsx_validate etc. tests still pass.
- [ ] A `T-` test name prefix is used consistently for the new block (so it's visually distinct from existing tests).
- [ ] No edits to `skills/docx/scripts/office/` (CLAUDE.md §2).

## Notes
- "Red on stubs" is interpreted here as **green-on-stub-but-asserting-stubbed-shape**: the stubs pass, but the assertions are weak. They become real (and remain green) as Stage 2 lands.
- For tests that need `.xlsx` fixtures, use openpyxl one-liners inline in the shell where possible; fall back to fixtures from task 1.04 for cases that need real Excel-authored input.
