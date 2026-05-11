# Task 004.06: `writer.py` — Workbook builder + styling + multi-sheet + sheet-name validation

## Use Case Connection
- **UC-1** (single-sheet styled output), **UC-2** (multi-sheet output + sheet-name validation), **UC-3** (JSONL → single sheet, same writer path), and the styling/freeze/auto-filter acceptance criteria across all UCs.

## Task Goal
Implement F4 in `json2xlsx/writer.py`: take a `ParsedInput` + per-call `CoerceOptions`, produce a styled `openpyxl.Workbook`, and save to disk. Header rows union-merged in first-seen order (R5). Style constants copied from `csv2xlsx.py` (NOT imported — see ARCH §3.2 writer policy). Sheet-name Excel-rule validation (R7.b). **All `TestWriter` unit tests + most happy-path E2E tests turn green** (E2E full-green pending CLI in 004.07).

**Closes AQ-1 effectively** — drift-detection unit test (`test_style_constants_drift_csv2xlsx`) is now bilateral: both csv2xlsx and writer.py have the constants; assertion verifies equality.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/writer.py`

Replace stub bodies with full F4 implementation:

```python
"""Workbook writer (F4).

Takes a ParsedInput (from F2 loaders) and produces a styled .xlsx
file on disk. Per-cell typing routed through F3 (coerce). Visual
contract mirrors csv2xlsx 1:1.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook  # type: ignore
from openpyxl.styles import Alignment, Font, PatternFill  # type: ignore
from openpyxl.utils import get_column_letter  # type: ignore
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore

from .coerce import CoerceOptions, CellContext, coerce_cell
from .exceptions import InvalidSheetName
from .loaders import ParsedInput


# Mirrors csv2xlsx.py — keep visually identical.
# Drift detection lives in tests/test_json2xlsx.py::test_style_constants_drift_csv2xlsx
# which accepts both 6-char ("F2F2F2") and 8-char ("00F2F2F2") forms
# (openpyxl normalises lazily; see ARCH §3.2 writer policy).
HEADER_FILL = PatternFill("solid", fgColor="F2F2F2")
HEADER_FONT = Font(bold=True)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
MAX_COL_WIDTH = 50


_FORBIDDEN_SHEET_CHARS = set("[]:*?/\\")
_RESERVED_SHEET_NAMES = frozenset({"History"})  # case-insensitive match below


def write_workbook(
    parsed: ParsedInput,
    output: Path,
    *,
    freeze: bool = True,
    auto_filter: bool = True,
    sheet_override: str | None = None,
    coerce_opts: CoerceOptions,
) -> None:
    """Build the workbook in memory, then `wb.save(output)`.

    For shape `array_of_objects` and `jsonl`, the single sheet name
    is `sheet_override` if provided else "Sheet1" (the default key
    in ParsedInput.sheets).

    For shape `multi_sheet_dict`, sheet_override is ignored — the
    caller logs a warning at the CLI layer (R7.d).
    """
    wb = Workbook()
    # Workbook() creates a default sheet; we'll rename or delete.
    default_ws = wb.active

    first = True
    for raw_name, rows in parsed.sheets.items():
        if parsed.shape != "multi_sheet_dict" and sheet_override is not None:
            sheet_name = sheet_override
        else:
            sheet_name = raw_name
        _validate_sheet_name(sheet_name)

        if first:
            default_ws.title = sheet_name
            ws = default_ws
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)

        _build_sheet(ws, rows, coerce_opts, sheet_name)

        if freeze:
            ws.freeze_panes = "A2"
        if auto_filter and len(rows) > 0:
            ws.auto_filter.ref = ws.dimensions

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output))


def _build_sheet(
    ws: Worksheet,
    rows: list[dict[str, Any]],
    coerce_opts: CoerceOptions,
    sheet_name: str,
) -> None:
    headers = _union_headers(rows)

    # Header row.
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = str(header)
        cell.data_type = "s"  # force string (avoid Excel-error misclassification)
    _style_header_row(ws, len(headers))

    # Data rows.
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, header in enumerate(headers, start=1):
            value = row.get(header)
            if value is None and header not in row:
                # missing key — leave cell empty (no value set)
                continue
            ctx = CellContext(
                sheet=sheet_name, row=row_idx - 1,  # 1-indexed data row
                column=get_column_letter(col_idx),
            )
            payload = coerce_cell(value, coerce_opts, ctx=ctx)
            cell = ws.cell(row=row_idx, column=col_idx)
            if payload.value is None:
                continue
            cell.value = payload.value
            if payload.number_format is not None:
                cell.number_format = payload.number_format
            if isinstance(payload.value, str):
                cell.data_type = "s"

    _size_columns(ws, headers, rows)


def _union_headers(rows: list[dict[str, Any]]) -> list[str]:
    """First-seen wins (R5.b). Row 1's keys come first; new keys from
    row 2 are appended; etc.
    """
    seen: dict[str, None] = {}
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen[k] = None
    return list(seen.keys())


def _style_header_row(ws: Worksheet, header_count: int) -> None:
    for col_idx in range(1, header_count + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN


def _size_columns(
    ws: Worksheet,
    headers: list[str],
    rows: list[dict[str, Any]],
) -> None:
    # Signature matches ARCH §F4 exactly — `coerce_opts` / `sheet_name`
    # are intentionally NOT parameters. Column width is computed off
    # the raw string length of the JSON value, not the coerced cell
    # value. If a future change wants coerce-aware width (e.g. format
    # dates with override before measuring length), that's a v2 concern.
    for col_idx, header in enumerate(headers, start=1):
        header_len = len(str(header))
        max_val_len = 0
        for row in rows:
            v = row.get(header)
            if v is None:
                continue
            s = str(v)
            if len(s) > max_val_len:
                max_val_len = len(s)
        width = min(max(header_len, max_val_len) + 2, MAX_COL_WIDTH)
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _validate_sheet_name(name: str) -> None:
    if not name:
        raise InvalidSheetName(name=name, reason="empty")
    if len(name) > 31:
        raise InvalidSheetName(name=name, reason=f"length {len(name)} exceeds Excel limit of 31")
    if any(c in _FORBIDDEN_SHEET_CHARS for c in name):
        bad = sorted({c for c in name if c in _FORBIDDEN_SHEET_CHARS})
        raise InvalidSheetName(name=name, reason=f"contains forbidden character(s) {bad}")
    if name.lower() in {n.lower() for n in _RESERVED_SHEET_NAMES}:
        raise InvalidSheetName(name=name, reason=f"reserved sheet name (case-insensitive)")
```

### Component Integration

- `cli._run` (004.07) will call:
  ```
  coerce_opts = CoerceOptions(
      date_coerce=not args.no_date_coerce,
      strict_dates=args.strict_dates,
      date_format_override=args.date_format,
  )
  write_workbook(parsed, output=Path(args.output),
                 freeze=not args.no_freeze, auto_filter=not args.no_filter,
                 sheet_override=args.sheet, coerce_opts=coerce_opts)
  ```
- The multi-sheet `--sheet` warning (R7.d) is emitted in the CLI layer, not here.

## Test Cases

### Unit Tests (turn green in this task)

All `TestWriter` cases from 004.02 turn green:

1. `test_union_headers_first_seen_order` — `[{a:1},{b:2,a:3}]` → headers `["a","b"]`.
2. `test_validate_sheet_name_ok` — "Employees" passes.
3. `test_validate_sheet_name_empty` — "" raises with reason "empty".
4. `test_validate_sheet_name_too_long` — 32-char name raises.
5. `test_validate_sheet_name_invalid_chars` — "Q1/Q2" raises mentioning `/`.
6. `test_validate_sheet_name_reserved` — "history" / "History" raises.
7. `test_style_header_row_bold_grey_centre` — cell A1 bold, fill F2F2F2, centre.
8. `test_size_columns_caps_at_max` — long string column capped at 50.
9. `test_style_constants_drift_csv2xlsx` — (AQ-1 lock) — imports `csv2xlsx` via sys.path injection, asserts `csv2xlsx.HEADER_FILL.fgColor.rgb in ("F2F2F2", "00F2F2F2")` AND `writer.HEADER_FILL.fgColor.rgb in (same set)`, plus equality of `HEADER_FONT.bold`, `HEADER_ALIGN.horizontal`, `MAX_COL_WIDTH`.
10. `test_write_workbook_freeze_pane_a2` — output file has `freeze_panes == "A2"`.
11. `test_write_workbook_auto_filter_set` — `auto_filter.ref` covers data range.
12. `test_write_workbook_multi_sheet_preserves_order` — `{"A":[…],"B":[…]}` → `wb.sheetnames == ["A","B"]`.
13. `test_write_workbook_single_sheet_with_sheet_override` — override sets the title.
14. `test_write_workbook_single_sheet_default_name` — default "Sheet1" when no override.
15. `test_write_workbook_missing_keys_empty_cells` — row missing a key → cell is empty.
16. `test_write_workbook_bool_cell_is_bool` — Bool value preserved as boolean cell (`data_type == "b"` after save+reload).
17. `test_write_workbook_date_cell_number_format` — Date value has `number_format == "YYYY-MM-DD"`.

### E2E Tests
- `T-happy-single-sheet` — turns full-green once 004.07 lands the CLI.
- `T-happy-multi-sheet` — same.
- `T-happy-jsonl` — same.
- `T-iso-dates` — same.

### Regression Tests
- All xlsx existing tests pass.

## Acceptance Criteria

- [ ] `writer.py` implements `write_workbook`, `_build_sheet`, `_union_headers`, `_style_header_row`, `_size_columns`, `_validate_sheet_name` per signatures locked in ARCH §5.
- [ ] Style constants `HEADER_FILL`, `HEADER_FONT`, `HEADER_ALIGN`, `MAX_COL_WIDTH` defined with the `# Mirrors csv2xlsx.py — keep visually identical.` comment.
- [ ] All 17 TestWriter cases green; `test_style_constants_drift_csv2xlsx` (AQ-1) PASSES.
- [ ] LOC count of `writer.py` ≤ 220.
- [ ] No openpyxl import outside `writer.py` (verified by grep on the package).
- [ ] `validate_skill.py` green; eleven `diff -q` silent.

## Notes

- The "missing key vs JSON null" distinction:
  - `row = {"a": 1}`, header "b" not in row → empty cell (`if value is None and header not in row: continue`).
  - `row = {"a": 1, "b": None}` → `value is None and header in row` → still empty cell (skip), per R3.d.
  - In current implementation both branches result in empty cells (the `continue` triggers either way), which is correct. The condition `header not in row` is kept to make intent explicit and to flag any future divergence.
- `_validate_sheet_name` checks case-INSENSITIVE "History" reservation because Excel itself does (verified in xlsx-6 reference; csv2xlsx doesn't enforce, so this is one place xlsx-2 is stricter — documented in TASK §R7.a).
- The `data_type = "s"` force on header strings is identical to csv2xlsx logic — prevents openpyxl's type-inference from treating headers like `"#REF!"` as cached formula errors.
