# Task 009-07: F6 `_values.py` — extraction + number-format + datetime + hyperlink [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-04** Alternatives A3 (stale-cache), A4 (rich-text), A5
  (hyperlink), A6 (formula passthrough).

## RTM Coverage
- **[R8]** Cell value extraction — formula vs cached toggle, number-
  format heuristic, datetime conversion, hyperlink, rich-text
  spans, stale-cache detection.

## Task Goal

Replace `_values.extract_cell` stub (currently `return cell.value`
pass-through) with the full extraction pipeline:
- **Formula handling:** if `include_formulas=True` and
  `cell.data_type == "f"` → return the formula string (with leading
  `=` preserved). Otherwise return the cached value.
- **Stale-cache detection:** if `cell.data_type == "f"` AND
  `cell.value is None` → emit a stale-cache warning via the
  caller-visible warnings list. (This module returns a tuple
  `(value, warning_or_None)` — caller appends to the running list.)
- **Number-format heuristic:**
  - `#,##0[.0+]` → formatted string with thousands separator.
  - `0%[.0+]` → percent string with the indicated decimals.
  - Date formats (heuristic regex matching `y`/`m`/`d`/`h`/`s`
    placeholders) → routed to `_apply_datetime_format`.
  - Leading-zero formats (`"0+"`) → string-coerce with zero-pad to
    `len(format_str)`.
  - All else → raw `cell.value`.
- **Datetime conversion:** `ISO` (default) → `dt.isoformat()`;
  `excel-serial` → numeric serial (`(dt - datetime(1899,12,30))
  .total_seconds() / 86400.0`); `raw` → native `datetime`.
- **Hyperlink:** if `include_hyperlinks=True` and `cell.hyperlink
  is not None` → return `cell.hyperlink.target` instead of value.
- **Rich-text:** if `cell.value` is an `openpyxl.cell.rich_text
  .CellRichText` instance → concatenate `.text` of each `TextBlock`
  span.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/values_numformat.xlsx`
  — workbook with 8 cells exhibiting each number-format pattern:
  `1234.5` with `#,##0.00`; `0.05` with `0.0%`;
  `datetime(2026,3,5)` with `yyyy-mm-dd`; `"00042"` with `00000`;
  bare `42` with default; etc.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/values_formula_cached.xlsx`
  — cell with formula `=A1+B1` and cached value `7`.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/values_stale_cache.xlsx`
  — cell with formula `=A1+B1` and **no** cached value
  (`cell.value is None` with `data_type=="f"`).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/values_hyperlink.xlsx`
  — one cell with `cell.hyperlink.target = "https://example.com"`
  and display text `"Click here"`.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/values_richtext.xlsx`
  — one cell with rich-text spans (`"Bold"` bold + `" then plain"`).
- `skills/xlsx/scripts/xlsx_read/tests/test_values.py` — unit + E2E.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_values.py`
- Update signature: `def extract_cell(cell, *, include_formulas:
  bool = False, include_hyperlinks: bool = False, datetime_format:
  DateFmt = "ISO") -> tuple[Any, str | None]` (tuple form returns
  optional warning so caller can append to `TableData.warnings`).
- Implement helpers:
  - `_apply_number_format(value, number_format) -> Any`.
  - `_apply_datetime_format(dt, fmt) -> str | float | datetime`.
  - `_extract_hyperlink(cell) -> str | None`.
  - `_flatten_rich_text(value) -> str`.
  - `_stale_cache_warning(cell) -> str | None`.
- Document a **divergence list** in the module docstring listing
  any number-format heuristic differences from xlsx-7's
  `cell_types.py` (per D-A5 — fresh implementation, documented
  divergence).

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_values.py`)

1. **TC-E2E-01 (numformat_decimal_thousands):** Cell `1234.5`
   with format `#,##0.00` → `"1,234.50"`.
2. **TC-E2E-02 (numformat_percent_1dp):** Cell `0.05` with
   `0.0%` → `"5.0%"`.
3. **TC-E2E-03 (numformat_date_iso):** Cell `datetime(2026,3,5)`
   with `yyyy-mm-dd` and `datetime_format="ISO"` → `"2026-03-05"`.
4. **TC-E2E-04 (numformat_date_serial):** Same cell with
   `datetime_format="excel-serial"` → `46091.0` (float).
5. **TC-E2E-05 (numformat_date_raw):** Same cell with
   `datetime_format="raw"` → `datetime(2026,3,5)` instance.
6. **TC-E2E-06 (numformat_leading_zero):** Cell `42` with format
   `00000` → `"00042"`.
7. **TC-E2E-07 (formula_cached):** Cell with formula `=A1+B1`,
   cached `7`, `include_formulas=False` → `(7, None)`.
8. **TC-E2E-08 (formula_emitted):** Same cell with
   `include_formulas=True` → `("=A1+B1", None)`.
9. **TC-E2E-09 (stale_cache_warning):** Cell with formula and
   `cell.value is None` → returns `(None, str)` where the warning
   string contains `"stale cache"` substring.
10. **TC-E2E-10 (hyperlink_off):** `include_hyperlinks=False` →
    returns display text `"Click here"`, no hyperlink.
11. **TC-E2E-11 (hyperlink_on):** `include_hyperlinks=True` →
    returns `"https://example.com"`.
12. **TC-E2E-12 (richtext_flatten):** Returns
    `"Bold then plain"` (concatenated).

### Unit Tests

1. **TC-UNIT-01 (`_apply_number_format` decimal regex):** Cover
   `#,##0`, `#,##0.0`, `#,##0.00`, `#,##0.000` (varying precision).
2. **TC-UNIT-02 (`_apply_number_format` percent regex):** Cover
   `0%`, `0.0%`, `0.00%`.
3. **TC-UNIT-03 (`_apply_datetime_format` excel-serial roundtrip):**
   `datetime(1900,1,1)` → `2.0`; `datetime(1899,12,30)` → `0.0`
   (Excel epoch reference; verify against known anchor).
4. **TC-UNIT-04 (`_extract_hyperlink` None passthrough):** Cell
   without hyperlink → returns `None`.
5. **TC-UNIT-05 (`_flatten_rich_text` plain string passthrough):**
   Non-CellRichText input → returns input unchanged.
6. **TC-UNIT-06 (`_stale_cache_warning` false for non-formula):**
   `data_type != "f"` → returns `None` regardless of `cell.value`.

### Regression Tests
- 009-02..009-06 green.
- 12-line `diff -q` silent.

## Acceptance Criteria

- [ ] All 12 TC-E2E and 6 TC-UNIT cases pass.
- [ ] Number-format heuristic divergences from xlsx-7 documented
  in the module docstring (per D-A5).
- [ ] `extract_cell` returns the documented `(value, warning_or_None)`
  tuple (caller responsibility to lift warning into
  `TableData.warnings`).
- [ ] `ruff` + `validate_skill.py` exit 0; 12-line silent.

## Notes

- Excel's date epoch is `1899-12-30` (not `1900-01-01`) due to
  Excel's leap-year bug — the off-by-2 is intentional. Test
  TC-UNIT-03 anchors against this.
- The "leading-zero" detection regex must match `0+` literal
  (e.g. `00000`, `000`) but NOT `0.0%` etc. Use anchored regex.
- The tuple return shape is **internal** — `WorkbookReader.read_table`
  unpacks it. Callers of the public surface (R1) never see the
  tuple form.
