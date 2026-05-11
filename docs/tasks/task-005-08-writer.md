# Task 005.08: `writer.py` — Workbook assembly + styling + merges (F8)

## Use Case Connection
- UC-1 (HAPPY PATH) — writes the actual `.xlsx` file.
- UC-3 (HTML colspan/rowspan) — `_apply_merges` translates to openpyxl ranges.
- R6.c (per-column alignment); R7 (all styling sub-features); R10.c (zero-row table contract); R9.e (no formula evaluation).

## Task Goal

Fill `writer.py` with full workbook-assembly logic. Style constants
were copied in 005.01; this task adds the actual cell-writing,
header-row styling, merge-range application, alignment, column
sizing, freeze pane, auto-filter, and parent-dir auto-create.

After this task, workbook-output fixtures fully exercise the
parser → coercer → namer → writer pipeline. The orchestrator
(005.09) glues them together, and most E2E cases turn green there.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/writer.py`

**Style constants (already copied in 005.01):**

```python
# Mirrors csv2xlsx.py — keep visually identical.
HEADER_FILL = PatternFill("solid", fgColor="F2F2F2")
HEADER_FONT = Font(bold=True)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
MAX_COL_WIDTH = 50
```

**Main entry point:**

```python
def write_workbook(
    tables: list[ParsedTable], output: Path, opts: WriterOptions,
) -> None:
    if not tables:
        if not opts.allow_empty:
            raise NoTablesFound(...)  # orchestrator catches earlier
        # Empty workbook with placeholder sheet (ARCH A6):
        wb = Workbook(); ws = wb.active; ws.title = "Empty"
        output.parent.mkdir(parents=True, exist_ok=True)  # A8 lock
        wb.save(str(output))
        return

    wb = Workbook()
    # The default sheet "Sheet" is replaced by the first table's sheet:
    wb.remove(wb.active)

    for tbl in tables:
        ws = wb.create_sheet(title=tbl.sheet_name)
        _build_sheet(ws, tbl)

    output.parent.mkdir(parents=True, exist_ok=True)  # ARCH A8
    wb.save(str(output))
```

**`_build_sheet(ws, tbl: ParsedTable) -> None`:**

- Header row (row 1):
  - For each header cell value: `cell = ws.cell(row=1, column=col_idx); cell.value = str(header)`; force `cell.data_type = "s"` (prevents `"=foo"` style being typed as formula; R9.e lock).
  - Apply `HEADER_FILL`, `HEADER_FONT`, `HEADER_ALIGN`.
- Data rows (row 2+):
  - For each coerced value in each column: `cell.value = value`; if `value is None` skip (openpyxl writes blank); if `isinstance(value, str)` force `cell.data_type = "s"` (also R9.e lock — a string starting with `=` MUST NOT be typed as formula).
  - If GFM source AND alignment marker is `"left"`/`"right"`/`"center"`: `cell.alignment = Alignment(horizontal=...)`.
- Apply merges via `_apply_merges`.
- Apply per-column alignment via `_apply_alignment` (HTML mode never has GFM alignment markers — applies only to GFM tables).
- Auto column widths via `_size_columns`.
- Freeze pane (if `opts.freeze` and ≥ 1 data row): `ws.freeze_panes = "A2"`.
- Auto-filter (if `opts.auto_filter` and ≥ 1 data row): `ws.auto_filter.ref = ws.dimensions`.

**Helpers:**

- `_apply_merges(ws, merges: list[MergeRange]) -> None`:
  - For each merge: `try: ws.merge_cells(start_row=m.start_row, start_column=m.start_col, end_row=m.end_row, end_column=m.end_col)`.
  - `except ValueError as exc:` → emit single-line stderr warning (R9.h lock; honest-scope §11.8): `print(f"warning: overlapping merge range dropped: {m}", file=sys.stderr)`; continue.

- `_apply_alignment(ws, alignments: list[Alignment], n_rows: int) -> None`:
  - For each column with a non-`"general"` alignment, walk rows 2..n_rows and set `cell.alignment = openpyxl.styles.Alignment(horizontal=alignments[col_idx])`.

- `_size_columns(ws, tbl: ParsedTable) -> None`:
  - For each column `c`: `header_len = len(str(tbl.raw.header[c]))`; `data_len = max((len(str(v)) for v in tbl.coerced_columns[c] if v is not None), default=0)`; `width = min(max(header_len, data_len) + 2, MAX_COL_WIDTH)`; `ws.column_dimensions[get_column_letter(c+1)].width = width`.

**Style-constant drift assertion (ARCH m8 import-path lock) — lands in `tests/`, NOT `writer.py`:**

In `tests/test_md_tables2xlsx.py::TestStyleConstantDrift`:

```python
def test_header_fill_matches_csv2xlsx(self):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from csv2xlsx import HEADER_FILL as _CSV_FILL
    from md_tables2xlsx.writer import HEADER_FILL as _MD_FILL
    self.assertIn(_CSV_FILL.fgColor.rgb, ("F2F2F2", "00F2F2F2"))
    self.assertEqual(_CSV_FILL.fgColor.rgb, _MD_FILL.fgColor.rgb)

def test_header_fill_matches_json2xlsx(self):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from json2xlsx.writer import HEADER_FILL as _JSON_FILL
    from md_tables2xlsx.writer import HEADER_FILL as _MD_FILL
    self.assertEqual(_JSON_FILL.fgColor.rgb, _MD_FILL.fgColor.rgb)
```

### Component Integration

Public surface: `write_workbook`, `WriterOptions`, `HEADER_FILL`
(for drift-detection). Consumed by `cli.py` orchestrator (005.09).

## Test Cases

### End-to-end Tests

- (E2E full-pipeline tests turn green in 005.09 once orchestrator wires loaders→tables→coerce→naming→writer.)

### Unit Tests

**TestWriter:**

1. **TC-UNIT-01 (test_basic_workbook):** Single `ParsedTable` → `write_workbook` produces a file with 1 sheet, header in row 1 (styled bold + filled).
2. **TC-UNIT-02 (test_multi_sheet):** 3 `ParsedTable` → workbook has 3 sheets in the input order.
3. **TC-UNIT-03 (test_default_sheet_removed):** Output workbook does NOT have the default "Sheet" sheet that openpyxl creates on `Workbook()`.
4. **TC-UNIT-04 (test_freeze_pane_applied):** `freeze=True` + ≥ 1 data row → `ws.freeze_panes == "A2"`.
5. **TC-UNIT-05 (test_freeze_pane_skipped_for_header_only):** Header-only table (zero data rows, R10.c) → workbook still has the sheet with header; freeze and auto-filter may or may not apply (Developer's call — recommend STILL apply `freeze="A2"` since header-only is a valid 1-row table; auto-filter on `A1:N1` is also valid).
6. **TC-UNIT-06 (test_auto_filter_applied):** `auto_filter=True` + ≥ 1 data row → `ws.auto_filter.ref` is non-None.
7. **TC-UNIT-07 (test_column_widths_capped):** Long-value column → width ≤ `MAX_COL_WIDTH=50`.
8. **TC-UNIT-08 (test_merge_cells_applied):** HTML source `ParsedTable` with 1 `MergeRange` → resulting `ws.merged_cells.ranges` contains the equivalent range.
9. **TC-UNIT-09 (test_merge_overlap_first_wins_stderr_warning):** Two overlapping merges → first applied, second dropped with stderr warning (R9.h lock).
10. **TC-UNIT-10 (test_gfm_alignment_left_right_center_applied):** GFM table with alignments `["left", "right", "center"]` → row-2 cells have matching `cell.alignment.horizontal`.
11. **TC-UNIT-11 (test_no_freeze_flag):** `freeze=False` → `ws.freeze_panes is None`.
12. **TC-UNIT-12 (test_no_filter_flag):** `auto_filter=False` → `ws.auto_filter.ref is None`.
13. **TC-UNIT-13 (TestHonestScopeLocks::test_no_formula_evaluation):** `ParsedTable` with cell value `"=SUM(A1:A3)"` (string) → output cell has `data_type == "s"` AND `value == "=SUM(A1:A3)"` (R9.e lock — literal text, NO formula evaluation).
14. **TC-UNIT-14 (test_allow_empty_with_zero_tables):** `write_workbook([], output, WriterOptions(allow_empty=True))` → 1 sheet named `"Empty"` (ARCH A6 lock).
15. **TC-UNIT-15 (test_parent_dir_auto_created):** `output = Path(tempdir) / "subdir/out.xlsx"` (subdir doesn't exist yet) → `write_workbook` creates it (ARCH A8 lock; csv2xlsx parity).

**TestStyleConstantDrift:**

1. **TC-UNIT-16 (test_header_fill_matches_csv2xlsx):** ARCH m8 drift-detection.
2. **TC-UNIT-17 (test_header_fill_matches_json2xlsx):** ARCH m8 drift-detection (3-way).

### Regression Tests

- Existing tests pass.
- json2xlsx and csv2xlsx output remain byte-stable.

## Acceptance Criteria

- [ ] All 17 unit tests pass.
- [ ] All four style constants (`HEADER_FILL`, `HEADER_FONT`, `HEADER_ALIGN`, `MAX_COL_WIDTH`) are byte-identical to csv2xlsx (drift-detection).
- [ ] R9.h overlap-merge stderr warning emitted; first valid merge wins.
- [ ] R9.e all string cells get `data_type = "s"` regardless of value (no `"=foo"` typed as formula).
- [ ] R10.c zero-row table writes the sheet with header only.
- [ ] ARCH A6 `allow_empty=True` + zero tables → placeholder `"Empty"` sheet.
- [ ] ARCH A8 parent-dir auto-created.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

The drift-detection tests (TC-UNIT-16, -17) are the **single canary**
against accidental style divergence between csv2xlsx / json2xlsx /
md_tables2xlsx. If any of the three style-constant tests fail, STOP
and investigate which CLI changed — drift in the styling family is
always a regression (csv2xlsx is the visual reference per ARCH §6).

The R9.e regression (TC-UNIT-13) is intentionally strict: even
when the user supplies a coerced numeric/date value, the writer
re-typing logic must not retroactively flip it back to formula
type. Set `data_type = "s"` only on `isinstance(value, str)` paths,
never on numeric/date paths.
