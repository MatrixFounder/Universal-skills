# Task 005.02: Test scaffolding — 13 E2E + 35 unit cases + fixtures + drift-detection

## Use Case Connection
- UC-1, UC-2, UC-3, UC-4 — every UC has at least one E2E case in the scaffolding.

## Task Goal

Write the test files and fixture markdown documents that will go
RED on the stubs from 005.01 and turn GREEN as each Phase-2 task
lands. ≥ 35 unit cases organized in 6 classes (`TestPipeParser`,
`TestHtmlParser`, `TestInlineStrip`, `TestCoerce`, `TestSheetNaming`,
`TestExceptions`/`TestPublicSurface`); ≥ 13 named E2E cases in
`tests/test_e2e.sh` with stable `T-*` tags. Drift-detection
assertions land on day 1 so any later `csv2xlsx.py` style edit (or
`json2xlsx/writer.py` edit) fires a clear test failure. Five fixture
markdown files in `examples/`.

## Changes Description

### New Files

- `skills/xlsx/scripts/tests/test_md_tables2xlsx.py` — ~ 600 LOC; ≥ 35 unit cases distributed across 6 classes (per TASK §5 budget). Every test method uses `@unittest.skipUnless(False, ...)` decoration in the scaffolding form, OR raises `unittest.SkipTest("xlsx-3 stub — task-005-NN")` so the suite is red-but-uniform.
- `skills/xlsx/examples/md_tables_simple.md` — 3 GFM tables under 3 `##` headings (UC-1 fixture).
- `skills/xlsx/examples/md_tables_html.md` — 1 GFM + 1 `<table>` with colspan/rowspan (UC-3 fixture).
- `skills/xlsx/examples/md_tables_fenced.md` — markdown with a pipe-table-looking block inside a ```` ```text … ``` ```` fence (T-fenced-code-table-only fixture).
- `skills/xlsx/examples/md_tables_no_tables.md` — prose only (T-no-tables fixture).
- `skills/xlsx/examples/md_tables_sheet_naming_edge.md` — headings with `[Q1]:* / `, duplicate `## Results` headings, `## History`, a 32-char emoji heading (T-sheet-name-* fixtures).

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

- Append a new section header `# ---------- xlsx-3 / md_tables2xlsx ----------`.
- Append ≥ 14 named cases (stable T-tags; 13 from TASK §5 + 1 from plan-review m3 fix), each currently emitting `echo "SKIP T-<name> (xlsx-3 stub — task-005-NN)"`:
  1. `T-happy-gfm` — UC-1 happy path
  2. `T-happy-html` — UC-3 happy path
  3. `T-stdin-dash` — UC-2 stdin pipe
  4. `T-same-path` — UC-4 collision → exit 6
  5. `T-no-tables` — T-no-tables fixture → exit 2 `NoTablesFound`
  6. `T-no-tables-allow-empty` — same fixture + `--allow-empty` → exit 0, sheet `Empty`
  7. `T-fenced-code-table-only` — fenced-code fixture → exit 2 (skipped because table is inside fence)
  8. `T-html-comment-table-only` — html comment fixture → exit 2
  9. `T-coerce-leading-zero` — column `"007"`/`"042"` stays text
  10. `T-coerce-iso-date` — column `2026-05-11` → Excel date cell
  11. `T-sheet-name-sanitisation` — heading `## Q1: [Budget]` → sheet `Q1_ _Budget_`
  12. `T-sheet-name-dedup` — two `## Results` headings → `Results` + `Results-2`
  13. `T-envelope-cross5-shape` — any failure with `--json-errors` → `{v, error, code, type, details}` JSON on stderr
  14. `T-indented-code-block-skip` (plan-review m3 fix — ARCH Q1 default YES) — markdown with a 4-space-indented pipe-table-looking block ONLY → exit 2 `NoTablesFound` (block stripped by pre-scan).
- Each scaffolded case is wrapped in `if false; then ... fi` OR uses an `echo SKIP` marker so the script exit code is 0 with all tests skipped.

### Component Integration

`test_md_tables2xlsx.py` adds `from md_tables2xlsx import (...)` at
the top. Drift-detection: `from csv2xlsx import HEADER_FILL as
_CSV_FILL; from json2xlsx.writer import HEADER_FILL as _JSON_FILL`
(uses ARCH m8 import-path lock). Drift assertions are skip-stubbed
for now — they'll turn green in 005.08 when `writer.py` lands.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `bash skills/xlsx/scripts/tests/test_e2e.sh` exits 0 with all 13 new T-tagged cases reporting SKIP.

### Unit Tests

1. **TC-UNIT-01:** `python3 -m unittest discover -s skills/xlsx/scripts/tests` reports ≥ 35 skipped tests for `test_md_tables2xlsx` (the scaffolding) AND ≥ 0 failures (regressions).
2. **TC-UNIT-02 (TestPublicSurface, NOT skipped):** Re-asserts the 3 unit cases from 005.01 (importability + signature + parser-instance) so they stay live as Phase 1 gates.

### Regression Tests

- Run all existing tests; ensure no regression from adding new imports (`from md_tables2xlsx import …`).

## Acceptance Criteria

- [ ] `test_md_tables2xlsx.py` exists with 6 test classes, ≥ 35 method stubs total, each raises `unittest.SkipTest` or is decorated `@unittest.skip`.
- [ ] `test_e2e.sh` has the 14 new T-tagged cases as SKIP markers (13 from TASK §5 + 1 from plan-review m3).
- [ ] All 5 fixture markdown files exist with the documented structure.
- [ ] Drift-detection imports work (`from csv2xlsx import HEADER_FILL`; `from json2xlsx.writer import HEADER_FILL`).
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

The 13-case lock is per TASK §5. The 35-case lock is per TASK §5
unit-test budget. These counts are minimums, NOT targets — adding
more skip-stubs early is cheaper than retrofitting later. Each
fixture file is small (≤ 50 lines); the goal is **enough variety to
exercise every R/UC path**, not exhaustive coverage. Per-edge-case
fixtures are added inline in subsequent tasks (e.g., 005.07 adds
a UTF-16 emoji-collision fixture for the M3 regression test).
