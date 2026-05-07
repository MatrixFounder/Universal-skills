# Task 2.02 [R2]: [LOGIC IMPLEMENTATION] Cell-syntax parser + sheet resolver

## Use Case Connection
- I1.1 (cell-syntax parser, all 7 alternatives).
- M2 (first-VISIBLE sheet rule).
- M3 (case-sensitive lookup with `details.suggestion`).
- RTM: R2 — cell-syntax (cross-sheet, quoted, apostrophe-escape).

## Task Goal
Replace stubs `parse_cell_syntax` and `resolve_sheet` with real implementations that handle all 7 alternative scenarios from TASK I1.1, plus the M2/M3 fixes (first-VISIBLE rule + case-sensitive lookup with suggestion). Cell parser is pure-Python (no XML); sheet resolver reads `xl/workbook.xml` from the unpacked tree.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `parse_cell_syntax(text: str) -> tuple[str | None, str]`:**
- Parameters: `text` — raw `--cell` argument.
- Returns: `(sheet_name | None, cell_ref)`. `sheet_name=None` means default-sheet (first visible).
- Logic:
  1. Strip whitespace.
  2. If text starts with `'` (single quote) → quoted-sheet form. Find the matching closing `'` followed by `!`. Within the quoted region, `''` (two single quotes) → `'`. Examples: `'Q1 2026'!A1` → `("Q1 2026", "A1")`; `'Bob''s Sheet'!A1` → `("Bob's Sheet", "A1")`. Malformed quoting (missing closing `'`, missing `!`) → raise `InvalidCellRef`.
  3. Else if text contains `!` → unquoted-sheet form: `text.split("!", 1)` → `(sheet, ref)`.
  4. Else → unqualified: `(None, text)`.
  5. Validate `cell_ref` matches `^[A-Z]+[0-9]+$` (uppercase letters then digits) — else raise `InvalidCellRef`.

**Function `resolve_sheet(workbook_root, qualified, all_sheets) -> str`:**
- Parameters:
  - `workbook_root`: lxml root of `xl/workbook.xml`.
  - `qualified`: `Optional[str]` — sheet name from `parse_cell_syntax`, or `None` for default.
  - `all_sheets`: `list[dict]` with `{name, sheetId, rId, state}` for every `<sheet>` in document order.
- Returns: sheet name (string).
- Logic:
  1. Build `name_map = {s.name: s for s in all_sheets}`.
  2. **If `qualified is None` (default-sheet):** iterate `all_sheets` in document order; return first `s.name` where `s.state in (None, "", "visible")`. If none, raise `NoVisibleSheet` envelope (exit 2). The user's `--cell HiddenSheet!A1` qualifier path is the explicit-bypass form (case 4).
  3. **If `qualified in name_map`:** return `qualified`. If the resolved sheet has `state in ("hidden", "veryHidden")`, emit info-level note to stderr but proceed.
  4. **If `qualified not in name_map`:** case-insensitive scan for a `details.suggestion` candidate (`s.name.lower() == qualified.lower()`). Build envelope:
     ```python
     details = {"available": [s.name for s in all_sheets]}
     if suggestion := next((s.name for s in all_sheets if s.name.lower() == qualified.lower()), None):
         details["suggestion"] = suggestion
     ```
     Raise `SheetNotFound` envelope (exit 2) with these details.

**Helper `_load_sheets_from_workbook(tree_root) -> list[dict]`:**
- Parses `xl/workbook.xml` `<sheet>` children in document order.
- Reads `name`, `sheetId`, `r:id` (with `xmlns:r=...`), and `state` attributes.
- Returns the list.

### Component Integration
- Called from `single_cell_main(args, tree)` and `batch_main(args, tree)` (Q-Q3 — still stubs in this task; full wiring lands in 2.08).
- Reuses lxml import from 1.01.

## Test Cases

### End-to-end Tests
- **TC-E2E-T-apostrophe-sheet:** `--cell "'Bob''s Sheet'!A1"` → comment lands on the sheet whose name is literally `Bob's Sheet` (a fixture `bobs.xlsx` with such a sheet name needs to be added inline in the test).
- **TC-E2E-T-hidden-first-sheet:** `--cell A5` against `golden/inputs/hidden_first.xlsx` (Sheet1 hidden, Sheet2 visible) → comment lands on Sheet2.
- **TC-E2E-T-multi-sheet:** `--cell Sheet2!B5` → comment binds via `xl/_rels/sheet2.xml.rels`. (Full assertion still needs 2.04 to land; here we just verify parser/resolver doesn't error.)

### Unit Tests
Remove `skipTest` and implement bodies for all 9 `TestCellSyntaxParser` tests:
- `test_simple_a1`: `parse_cell_syntax("A5") == (None, "A5")`.
- `test_qualified_sheet`: `parse_cell_syntax("Sheet2!B5") == ("Sheet2", "B5")`.
- `test_quoted_sheet_with_space`: `parse_cell_syntax("'Q1 2026'!A1") == ("Q1 2026", "A1")`.
- `test_apostrophe_escape`: `parse_cell_syntax("'Bob''s Sheet'!A1") == ("Bob's Sheet", "A1")`.
- `test_invalid_cell_ref`: `parse_cell_syntax("ZZ")` raises `InvalidCellRef`.
- `test_unknown_sheet_includes_available`: `resolve_sheet(...)` with non-existent sheet → `SheetNotFound` with `details.available = ["Sheet1","Sheet2"]`.
- `test_case_mismatch_includes_suggestion`: `resolve_sheet(..., qualified="sheet2", all_sheets=[{name:"Sheet2",...}])` → `SheetNotFound` with `details.suggestion = "Sheet2"`.
- `test_first_visible_skips_hidden`: `resolve_sheet(..., qualified=None, all_sheets=[hidden, visible])` → returns visible's name.
- `test_no_visible_sheet_envelope`: all sheets hidden → raises `NoVisibleSheet` (exit 2).

### Regression Tests
- All existing E2E and unit tests stay green.

## Acceptance Criteria
- [ ] All 9 unit tests in `TestCellSyntaxParser` pass (no skips).
- [ ] `T-apostrophe-sheet`, `T-hidden-first-sheet` E2E pass.
- [ ] `parse_cell_syntax` is pure (no I/O, no XML) — testable without a workbook.
- [ ] `resolve_sheet` raises typed envelopes only via the local exception classes (consumed by `main`'s cross-5 wrapper).
- [ ] Hidden-sheet stderr info note appears when the user explicitly qualifies a hidden sheet (`--cell Hidden!A1`).
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The apostrophe-escape rule `''` → `'` is the same Excel formula-syntax convention; mirroring it keeps the CLI feeling familiar to Excel power users.
- `_load_sheets_from_workbook` will be reused in 2.04 / 2.05 — keep it factored out as a separate helper, not inlined.
