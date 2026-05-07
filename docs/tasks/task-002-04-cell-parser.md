# Task 002.4: Migrate `cell_parser.py` (F2)

## Use Case Connection
- I3 — Move the F2 region to a leaf module that depends only on `exceptions` and `lxml`.

## Task Goal
Move the F2 region (lines 359–516, cell-syntax parser + sheet
resolver) from `xlsx_add_comment.py` to
`xlsx_comment/cell_parser.py`. Update the shim to re-import the
public names so tests pass unchanged.

## Changes Description

### New Files
*(none — `cell_parser.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/cell_parser.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """Cell-syntax parser and sheet resolver (F2).

  Migrated from `xlsx_add_comment.py` F2 region during Task 002.

  Public API:
      parse_cell_syntax(text) -> tuple[str | None, str]
          Parses A1, Sheet2!B5, 'Q1 2026'!A1, 'Bob''s Sheet'!A1.
          Apostrophe escape `''` → `'`. Returns (None, ref) for
          unqualified, (sheet_name, ref) otherwise. Raises
          InvalidCellRef on syntax error.
      resolve_sheet(qualified, all_sheets) -> sheet_name
          Applies M2 first-VISIBLE-sheet rule when qualifier is None;
          case-sensitive lookup with M3 suggestion when qualifier is
          given; raises SheetNotFound or NoVisibleSheet.
      _load_sheets_from_workbook(workbook_xml_root) -> list[dict]
          Parses <sheet> elements from xl/workbook.xml; private but
          re-exported via xlsx_add_comment.py shim only because the
          test suite is currently the only direct caller.
  """
  ```
- `__all__ = ["parse_cell_syntax", "resolve_sheet"]`
  *(Note: `_load_sheets_from_workbook` is NOT in `__all__` — it is
  module-private. **Disagreement between docs (m2 from plan-review)**:
  ARCHITECTURE.md §3.2 row "cell_parser.py" lists
  `_load_sheets_from_workbook` under "Public API (selected)". A grep
  against the test file shows zero test imports
  (`grep '_load_sheets_from_workbook' tests/` returns no matches).
  This task therefore demotes it to private (does NOT re-export from
  the shim, NOT in `__all__`). The ARCHITECTURE row will be silently
  superseded — no edit required because §3.2 already qualifies the
  list with "(selected)". Tests that need it later use the explicit
  `xlsx_comment.cell_parser._load_sheets_from_workbook` path.)*
- Imports (sibling-relative per R4.b):
  ```python
  from __future__ import annotations
  import re
  from lxml import etree  # type: ignore
  from .exceptions import InvalidCellRef, NoVisibleSheet, SheetNotFound
  from .constants import SS_NS
  ```
  *(Note: SS_NS is needed by `_load_sheets_from_workbook` for the
  `<sheet>` namespace. Verify this against the moved code — if F2
  uses a different namespace constant, adjust.)*
- Body: byte-equivalent move of the F2 region (lines 363–515).

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F2 region (lines 359–516 inclusive of region markers).
- **Insert**, immediately after the `from xlsx_comment.exceptions
  import …` block added in Task 002.3, the re-imports:
  ```python
  from xlsx_comment.cell_parser import (  # noqa: F401
      parse_cell_syntax, resolve_sheet,
  )
  ```
- The remaining F3–F6 regions still call `parse_cell_syntax` and
  `resolve_sheet` — they resolve through the re-import (NOT via
  `from xlsx_add_comment import …`, which would be a cycle). The
  developer **must verify** that all F3–F6 internal references work
  by re-running the test suite.

### Component Integration
- `cell_parser.py` depends on `constants.py` + `exceptions.py` only
  (Stage 1 leaves). No upward dependency.
- `xlsx_add_comment.py` continues to invoke `parse_cell_syntax` /
  `resolve_sheet` from its remaining F3 / F6 regions — those
  references resolve via the new re-import.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run `bash skills/xlsx/scripts/tests/test_e2e.sh`.
  All 112 checks must remain green.

### Unit Tests
- **TC-UNIT-01:** All `tests/test_xlsx_add_comment.py::Test*CellParser*`
  cases (parse_cell_syntax: unqualified A5, Sheet2!B5, 'Q1 2026'!A1,
  apostrophe-escape, InvalidCellRef on bad syntax) pass unchanged.
- **TC-UNIT-02:** `Test*SheetResolution*` cases (NoVisibleSheet,
  SheetNotFound with `details.suggestion`, hidden-sheet skip) pass
  unchanged.

### Regression Tests
- Per per-task micro-cycle: unit + E2E green; counts match Task 002.1
  baseline.

## Acceptance Criteria
- [ ] `xlsx_comment/cell_parser.py` ≤ 200 LOC, has the docstring,
      `__all__`, sibling-relative imports, and the F2 body.
- [ ] `xlsx_add_comment.py` no longer contains lines that defined
      `parse_cell_syntax`, `resolve_sheet`, or
      `_load_sheets_from_workbook` directly — they are re-imports.
- [ ] R4.b lock holds: `grep -nE 'from xlsx_add_comment' xlsx_comment/*.py`
      still empty.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- **Verbatim-move discipline:** preserve all in-line comments
  in F2 (the `# M2 first-VISIBLE-sheet rule` comment, the apostrophe
  escape regex commentary, etc.). They explain WHY the code looks
  the way it does and are part of the contract.
- The `_load_sheets_from_workbook` function silently skips `<sheet>`
  elements missing a `name` attr (defensive vs forged workbooks; per
  session-state recent-decisions). This behaviour MUST move
  byte-equivalent — DO NOT "tighten" it during the move.
- Estimated effort: 1 h.
