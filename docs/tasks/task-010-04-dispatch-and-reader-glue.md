# Task 010-04 [LOGIC IMPLEMENTATION]: `dispatch.py` — reader-glue (xlsx_read consumption)

## Use Case Connection
- UC-03 (multi-table JSON detect modes)
- UC-04 (multi-region CSV path-component validate)
- UC-05 (multi-row header pass-through)
- UC-01..UC-02 (single-sheet single-region happy paths)

## Task Goal

Implement `dispatch.py` per ARCH §2.1 F2: open the workbook (already
opened by `cli._dispatch_to_emit`), enumerate sheets, detect regions
per `--tables` mode with the 4→3 mapping (D-A2), read each region via
`xlsx_read.read_table`, yield `(sheet_name, region, table_data)`
triples to the emitter. Also enforce sheet-name path-component
validation when CSV multi-region mode is in effect (D-A8 partial).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/dispatch.py`

**Functions:**

- Implement `iter_table_payloads(args, reader) -> Iterator[tuple[str, TableRegion, TableData]]`
  - Parameters:
    - `args` — parsed `argparse.Namespace` from `cli.build_parser`.
    - `reader` — `xlsx_read.WorkbookReader` (already opened by caller).
  - Yields: `(sheet_name, region, table_data)` triples in document
    order.
  - Logic:
    1. Enumerate sheets via `reader.sheets()`.
    2. Filter by `args.sheet`:
       - `args.sheet == "all"`: visible sheets only (unless
         `args.include_hidden`, then include hidden + veryHidden).
       - `args.sheet == "<NAME>"`: select the single matching sheet;
         missing → re-raise as `SheetNotFound` (xlsx_read exception,
         caught by `_run_with_envelope` → exit 2).
    3. Resolve `(library_mode, post_filter)` via `_resolve_tables_mode(args.tables)`.
    4. For each selected sheet:
       a. `regions = reader.detect_tables(sheet_name, mode=library_mode, gap_rows=args.gap_rows, gap_cols=args.gap_cols)`.
       b. `regions = [r for r in regions if post_filter(r)]`.
       c. **R12.d enforcement (deferred from cli):** if `args.format == "csv"` (or `format_lock == "csv"`) AND `args.tables != "whole"` AND `len(regions) > 1` AND `args.output_dir is None` → raise `MultiTableRequiresOutputDir`.
       d. **D-A8 path-component validation:** if multi-region CSV
          mode (`args.output_dir is not None` AND format=="csv"):
          call `_validate_sheet_path_components(sheet_name)` then
          `_validate_sheet_path_components(region.name)` per region
          before yielding.
       e. Resolve `header_rows` value: `int(args.header_rows)` or
          `"auto"`.
       f. Resolve `merge_policy: MergePolicy` from `args.merge_policy`
          (`"anchor-only" | "fill" | "blank"` — direct passthrough).
       g. Resolve `datetime_format: DateFmt` from
          `args.datetime_format` (`"ISO" | "excel-serial" | "raw"`).
       h. For each region: `table_data = reader.read_table(
          region, header_rows=hdr, merge_policy=mp,
          include_hyperlinks=args.include_hyperlinks,
          include_formulas=args.include_formulas,
          datetime_format=dfmt)`.
       i. Yield `(sheet_name, region, table_data)`.

- Add `_resolve_tables_mode(arg_tables: str) -> tuple[str, Callable[[TableRegion], bool]]`
  - Logic:
    ```python
    if arg_tables == "whole":
        return ("whole", lambda r: True)
    if arg_tables == "listobjects":
        # library mode `tables-only` returns Tier-1 + Tier-2.
        # Per TASK §1.4 (l), Tier-2 sheet-scope named ranges are
        # silently bundled (honest scope).
        return ("tables-only", lambda r: True)
    if arg_tables == "gap":
        # library has no `gap-only` mode; use `auto` then filter.
        return ("auto", lambda r: r.source == "gap_detect")
    if arg_tables == "auto":
        return ("auto", lambda r: True)
    raise ValueError(f"Unknown --tables: {arg_tables!r}")
    ```

- `_validate_sheet_path_components` already implemented in 010-02.
  This task **adds call sites** in `iter_table_payloads` (step 4.d).

**Imports added:**
```python
from __future__ import annotations

from collections.abc import Iterator, Callable

from xlsx_read import (
    WorkbookReader,
    TableRegion,
    TableData,
    SheetNotFound,
)

from .exceptions import (
    MultiTableRequiresOutputDir,
    InvalidSheetNameForFsPath,
)
```

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Wire** `_dispatch_to_emit` to actually call `iter_table_payloads`
and pass payloads to the emit stubs:

```python
def _dispatch_to_emit(args, format: str) -> int:
    from xlsx_read import open_workbook
    from . import dispatch, emit_csv, emit_json

    input_path = Path(args.input).resolve(strict=True)
    with open_workbook(input_path, keep_formulas=args.include_formulas) as reader:
        payloads = dispatch.iter_table_payloads(args, reader)
        if format == "json":
            return emit_json.emit_json(
                payloads,
                output=Path(args.output).resolve() if args.output and args.output != "-" else None,
                sheet_selector=args.sheet,
                tables_mode=args.tables,
                header_flatten_style=args.header_flatten_style,
                include_hyperlinks=args.include_hyperlinks,
                datetime_format=args.datetime_format,
            )
        elif format == "csv":
            return emit_csv.emit_csv(
                payloads,
                output=Path(args.output).resolve() if args.output and args.output != "-" else None,
                output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
                sheet_selector=args.sheet,
                tables_mode=args.tables,
                include_hyperlinks=args.include_hyperlinks,
                datetime_format=args.datetime_format,
            )
        raise ValueError(f"Unknown format: {format!r}")
```

(The `Path.resolve()` chain on output paths goes through
`_resolve_paths` in production — for this task's wiring it's inlined;
010-05/06 refactor to call `_resolve_paths` directly.)

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_dispatch.py`

Unit tests for `dispatch.py`:

1. **TC-UNIT-01 (`test_resolve_tables_mode_whole`):** `_resolve_tables_mode("whole")` → `("whole", <id-filter>)`.
2. **TC-UNIT-02 (`test_resolve_tables_mode_listobjects`):** → `("tables-only", <id-filter>)`.
3. **TC-UNIT-03 (`test_resolve_tables_mode_gap_filter`):** → `("auto", <filter that accepts only source='gap_detect'>)`.
4. **TC-UNIT-04 (`test_resolve_tables_mode_auto`):** → `("auto", <id-filter>)`.
5. **TC-UNIT-05 (`test_resolve_tables_mode_unknown`):** → raises `ValueError`.
6. **TC-UNIT-06 (`test_iter_table_payloads_single_sheet_whole`):** mock reader returning 1 sheet + 1 region; iterator yields exactly 1 triple with that region.
7. **TC-UNIT-07 (`test_iter_table_payloads_multi_sheet_all_visible`):** mock reader with 2 visible + 1 hidden sheet; `args.sheet="all"`, `include_hidden=False` → yields triples for 2 sheets only.
8. **TC-UNIT-08 (`test_iter_table_payloads_include_hidden`):** `include_hidden=True` → all 3 sheets.
9. **TC-UNIT-09 (`test_iter_table_payloads_sheet_named`):** `args.sheet="Sheet2"` → only Sheet2 yielded.
10. **TC-UNIT-10 (`test_iter_table_payloads_sheet_not_found`):** `args.sheet="Bogus"` → `SheetNotFound` propagates.
11. **TC-UNIT-11 (`test_iter_table_payloads_gap_filter`):** mock reader returns 3 regions (2 gap_detect, 1 listobject); `args.tables="gap"` → only the 2 gap_detect yielded.
12. **TC-UNIT-12 (`test_iter_table_payloads_listobjects_includes_named_ranges`):** mock reader returns 1 listobject + 1 named_range; `args.tables="listobjects"` → both yielded (Tier-2 bundling honest-scope from TASK §1.4 (l)).
13. **TC-UNIT-13 (`test_iter_table_payloads_csv_multi_region_without_output_dir`):** mock reader 2 regions; `args.tables="listobjects"`, `args.output_dir=None`, `format_lock="csv"` (via test arg helper) → raises `MultiTableRequiresOutputDir`.
14. **TC-UNIT-14 (`test_iter_table_payloads_path_component_validation_invalid_sheet`):** mock reader sheet named `"bad/name"`; CSV multi-region mode → raises `InvalidSheetNameForFsPath`.
15. **TC-UNIT-15 (`test_iter_table_payloads_path_component_validation_invalid_table`):** mock reader region.name `"bad..name"`; CSV multi-region mode → raises `InvalidSheetNameForFsPath`.
16. **TC-UNIT-16 (`test_iter_table_payloads_passthrough_kwargs`):** verify `reader.read_table` is called with `header_rows`, `merge_policy`, `include_hyperlinks`, `include_formulas`, `datetime_format` per args.

#### `skills/xlsx/scripts/xlsx2csv2json/tests/fixtures/single_sheet_simple.xlsx`

Hand-built: 1 sheet "Data", header row `["id", "name", "score"]`, 3
data rows. Used in TC-UNIT-06 and across later tasks for the
single-region happy path.

#### `skills/xlsx/scripts/xlsx2csv2json/tests/fixtures/multi_table_listobjects.xlsx`

Hand-built: 1 sheet "Summary" with two ListObjects
(`RevenueTable` 3×3, `CostsTable` 2×3) separated by 3 empty rows.
Used by TC-UNIT-12 + 010-05 + 010-07 multi-table E2E.

### Component Integration

- `dispatch.iter_table_payloads` is the **only** call site of
  `xlsx_read.WorkbookReader.read_table` in the package — keeps the
  library boundary tight.
- 010-05 / 010-06 consume `iter_table_payloads` output; they do NOT
  call `xlsx_read` directly.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `python3 xlsx2json.py fixtures/single_sheet_simple.xlsx
   /tmp/out.json` → exit 0; `/tmp/out.json` exists (content asserted by
   010-05 — for now, the emit stub returns 0 → exit 0 is the gate).
   (Until 010-05 lands, emit_json stub returns `-997`; this E2E
   confirmed via the per-task gate in 010-05.)

### Unit Tests

(16 listed above.)

### Regression Tests

- All previous tests green.
- `ruff check scripts/` green.

## Acceptance Criteria

- [ ] `dispatch.iter_table_payloads` implemented.
- [ ] `_resolve_tables_mode` returns the correct (library_mode,
  filter) tuple per the 4-val → 3-val mapping.
- [ ] `iter_table_payloads` raises `MultiTableRequiresOutputDir`
  when CSV multi-region mode lacks `--output-dir`.
- [ ] `iter_table_payloads` validates sheet + table names as
  path components when CSV multi-region mode is in effect.
- [ ] `iter_table_payloads` propagates `SheetNotFound` from
  `xlsx_read`.
- [ ] `cli._dispatch_to_emit` wires the trampoline; emit functions
  return their (still stubbed) `-997` sentinel.
- [ ] All 16 unit tests in `test_dispatch.py` pass.
- [ ] 2 new fixtures added.
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent.

## Notes

- **Test strategy:** unit tests in `test_dispatch.py` use a minimal
  mock `WorkbookReader` (Python class with `sheets`, `detect_tables`,
  `read_table` methods) rather than real fixtures, EXCEPT where the
  fixture exercise downstream xlsx_read behaviour (e.g.
  `multi_table_listobjects.xlsx` is hand-built to verify the real
  `xlsx_read.detect_tables(mode="tables-only")` returns both
  ListObjects).
- The Tier-2 named-range bundling (TASK §1.4 (l)) is intentional and
  documented; TC-UNIT-12 locks the behaviour.
- `--include-formulas` requires `keep_formulas=True` at workbook
  open — wired in `cli._dispatch_to_emit` (`open_workbook(...,
  keep_formulas=args.include_formulas)`).
