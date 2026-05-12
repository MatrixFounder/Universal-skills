# Task 009-03: F2 `_sheets.py` — enumerate + resolve [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-02** (Enumerate sheets — visible + hidden + special-char names).

## RTM Coverage
- **[R4]** `sheets()` + `SheetInfo` + resolver (`name | all |
  missing`) + `SheetNotFound`.

## Task Goal

Replace stubs in `_sheets.py` with real logic:
- `enumerate_sheets(wb)` reads `wb.sheetnames` in document order
  and returns `list[SheetInfo]` with `name`, `index`, `state`
  fields. `state` derived via `wb[name].sheet_state` mapping to
  the public `Literal["visible","hidden","veryHidden"]`.
- `resolve_sheet(wb, query)` returns the matched sheet name (str)
  for a single-name query, the full ordered list of visible+hidden
  names for `query == "all"`, or raises `SheetNotFound` otherwise.
- Wire `WorkbookReader.sheets()` to call into this module.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/three_sheets_mixed.xlsx`
  — 3 sheets: `Visible1` (visible), `Hidden1` (hidden), `Special / Name`
  (visible; contains slash to test verbatim-preservation).
- `skills/xlsx/scripts/xlsx_read/tests/test_sheets.py` — unit + E2E.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_sheets.py`
- **Replace** stub with:
  - `def enumerate_sheets(wb) -> list[SheetInfo]`:
    - `return [SheetInfo(name=n, index=i,
      state=_state_from_openpyxl(wb[n])) for i, n in
      enumerate(wb.sheetnames)]`.
  - `def resolve_sheet(wb, query: str) -> str | list[str]`:
    - If `query == "all"`: return `list(wb.sheetnames)`.
    - Elif `query in wb.sheetnames`: return `query`.
    - Else: raise `SheetNotFound(f"Sheet not found: {query!r}")`.
  - `def _state_from_openpyxl(ws) ->
    Literal["visible","hidden","veryHidden"]`:
    - openpyxl returns one of the three string literals directly via
      `ws.sheet_state`; pass-through with a guard that raises
      `RuntimeError` if openpyxl ever returns an unexpected value
      (defence-in-depth — should not happen in practice).

#### File: `skills/xlsx/scripts/xlsx_read/_types.py` (UPDATE — append)
- Add `WorkbookReader.sheets()` implementation:
  `return enumerate_sheets(self._wb)`.

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_sheets.py`)

1. **TC-E2E-01 (enumerate_three_mixed):** Open
   `three_sheets_mixed.xlsx`; `reader.sheets()` returns a list of
   exactly 3 `SheetInfo` objects; document order preserved
   (`Visible1`, `Hidden1`, `Special / Name`); states are
   `visible`, `hidden`, `visible`.
2. **TC-E2E-02 (resolver_NAME):** `_sheets.resolve_sheet(wb,
   "Hidden1")` returns `"Hidden1"`.
3. **TC-E2E-03 (resolver_all):** `_sheets.resolve_sheet(wb, "all")`
   returns `["Visible1", "Hidden1", "Special / Name"]` in document
   order.
4. **TC-E2E-04 (resolver_missing):** `_sheets.resolve_sheet(wb,
   "Nonexistent")` raises `SheetNotFound`; message contains the
   queried name in `repr` form.

### Unit Tests

1. **TC-UNIT-01 (`_state_from_openpyxl`):** Truth-table for each of
   the three valid states (mock a `Worksheet` object with
   `sheet_state` attribute set to each value); plus one negative
   case asserting `RuntimeError` on an invalid value.
2. **TC-UNIT-02 (empty_workbook):** A workbook with one default
   sheet returns a single `SheetInfo` with `index=0`,
   `state="visible"`.
3. **TC-UNIT-03 (special_char_name_verbatim):** Sheet name
   `"Special / Name"` is preserved byte-for-byte in `SheetInfo.name`.

### Regression Tests

- TC-E2E-01 of 009-02 still passes (smoke import).
- 12-line cross-skill `diff -q` silent.

## Acceptance Criteria

- [ ] `_sheets.enumerate_sheets` returns ordered list with correct
  `name`/`index`/`state` for all three sheets.
- [ ] `_sheets.resolve_sheet` covers single-NAME, "all", missing
  paths.
- [ ] `WorkbookReader.sheets()` wired to call into `_sheets.py`.
- [ ] All 4 TC-E2E and 3 TC-UNIT cases pass.
- [ ] `ruff check` + `validate_skill.py` exit 0; 12-line silent.

## Notes

- No state filtering happens in the library — caller decides. This
  matches UC-02 main scenario step 3.
- `SheetInfo` is frozen; tests that mutate are expected to raise
  `FrozenInstanceError`.
