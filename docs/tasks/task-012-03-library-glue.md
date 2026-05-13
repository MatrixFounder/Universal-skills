# Task 012-03 [LOGIC IMPLEMENTATION]: `dispatch.py` — library-glue, memory-mode, sheet/table enumeration

> **Predecessor:** 012-02.
> **RTM:** [R5], [R8] (3-tier detection, post-call filter,
> `--no-split`, R8.f fallback), [R9] (gap-rows/cols),
> [R14a/b/f] (pass-through), [R14g] (`smart` pass-through),
> [R17] (datetime-format pass-through), [R19] (datetime-format
> enum), [R20] (number-format heuristic delegated to library —
> verified by 012-08 regression), [R20a] (`--memory-mode`
> mapping).
> **UCs:** UC-02 (multi-sheet), UC-03 (multi-table detect),
> UC-05 (multi-row library call), UC-11 (synthetic headers
> feed).

## Use Case Connection

- UC-02 — sheet enumeration with `--sheet`, hidden filter,
  `--include-hidden`.
- UC-03 — multi-table detection (3-tier) with
  `--no-table-autodetect` and `--no-split` flag handling.
- UC-05 — multi-row header library call (`reader.read_table(...,
  header_rows="auto")` returns ` › `-joined `headers`).
- UC-11 — `headerRowCount=0` listobject → library returns
  synthetic headers + warning; xlsx-9 passes through to emit.

## Task Goal

Implement `dispatch.py` per ARCH §2.1 F2. This is the *only*
module in `xlsx2md/` that calls `xlsx_read` directly (D-A5
closed-API consumer). It:

1. Maps `--memory-mode` to `xlsx_read.open_workbook(read_only_mode=...)`
   (R20a + D-A14).
2. Enumerates sheets via `reader.sheets()`; filters by
   `--sheet NAME|all` and `--include-hidden`.
3. Detects regions via `reader.detect_tables(sheet, mode=...,
   gap_rows=N, gap_cols=N)` with the post-call filter for
   `--no-table-autodetect` (D-A2) and `--no-split`
   (`mode="whole"`).
4. Reads each region via `reader.read_table(region, header_rows=...,
   merge_policy=..., include_hyperlinks=True, include_formulas=...,
   datetime_format=...)`.
5. Surfaces info warning when `--no-table-autodetect` gap-filter
   yields zero regions (R8.f fallback to whole-sheet emission).
6. Yields `(sheet_info, region, table_data)` triples to the
   emitter loop in 012-06 `emit_hybrid.emit_workbook_md`.

The emitters in 012-04 / 012-05 remain STUBs after this task; the
output is empty (or sentinel) but the dispatch pipeline produces
correctly-shaped triples that 012-06's orchestration loop will
consume.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2md/dispatch.py`

**Imports added:**

```python
from __future__ import annotations
from collections.abc import Iterator, Callable
from typing import Any
import warnings

from xlsx_read import (
    WorkbookReader,
    SheetInfo,
    TableRegion,
    TableData,
    SheetNotFound,
    TableDetectMode,
)
```

**Function `_resolve_read_only_mode(args) -> bool | None`:**

- R20a / D-A14 mapping:
  - `args.memory_mode == "auto"` → return `None` (library
    default; size-threshold ≥ 100 MiB → streaming).
  - `args.memory_mode == "streaming"` → return `True`.
  - `args.memory_mode == "full"` → return `False`.
  - Any other value → `argparse.choices` should have rejected it
    upstream; raise `ValueError` defensively.

**Function `_detect_mode_for_args(args) -> tuple[TableDetectMode,
Callable[[TableRegion], bool]]`:**

- D-A2 4-state → 3-state mapping for `--no-table-autodetect` /
  `--no-split`:
  - `args.no_split` → return `("whole", lambda r: True)`.
  - `args.no_table_autodetect` → return
    `("auto", lambda r: r.source == "gap_detect")`.
  - Default → return `("auto", lambda r: True)`.

**Function `_resolve_hyperlink_allowlist(args) -> frozenset[str] | None`:**

- Parse `--hyperlink-scheme-allowlist` CSV value into
  `frozenset[str]` (lower-cased schemes; whitespace stripped).
- Special values: `'*'` → return `None` sentinel (consumed by
  `inline._render_hyperlink` to mean "allow all schemes");
  `""` (empty) → return `frozenset()` (block all).
- This helper is consumed by 012-04's emit-side (via `args.scheme_allowlist`
  attached to `args` by `iter_table_payloads` setup or via direct
  call from emit). For 012-03 it's a pure parser used by tests;
  no behaviour change at the dispatch boundary.

**Function `iter_table_payloads(reader, args) -> Iterator[tuple[SheetInfo,
TableRegion, TableData]]`:**

- Logic:

  ```text
  library_mode, post_filter = _detect_mode_for_args(args)
  all_sheets = reader.sheets()

  if args.sheet == "all":
      if args.include_hidden:
          selected = all_sheets
      else:
          selected = [s for s in all_sheets if s.state == "visible"]
  else:
      matched = [s for s in all_sheets if s.name == args.sheet]
      if not matched:
          raise SheetNotFound(args.sheet)
      selected = matched

  hyperlink_allowlist = _resolve_hyperlink_allowlist(args)
  # Attach to args so emit-side (012-04/012-05 via inline.py) can read it.
  args._hyperlink_allowlist = hyperlink_allowlist

  read_only_mode = getattr(args, "_read_only_mode_resolved", None)
  # (resolved up-stream in main() when open_workbook is called; the
  # dispatch helper just consumes the already-opened reader.)

  header_rows = _coerce_header_rows(args.header_rows)
  # _coerce_header_rows handles the str→int OR
  # str-literal→str pass-through ("auto", "smart"). argparse
  # already validates against the allowed set.

  for sheet in selected:
      regions = reader.detect_tables(
          sheet.name,
          mode=library_mode,
          gap_rows=args.gap_rows,
          gap_cols=args.gap_cols,
      )
      regions = [r for r in regions if post_filter(r)]
      regions, fell_back = _gap_fallback_if_empty(
          regions, sheet, reader, args, library_mode
      )
      if fell_back:
          warnings.warn(
              f"no gap-detected tables found; emitting whole-sheet "
              f"markdown for {sheet.name!r}",
              UserWarning,
              stacklevel=2,
          )
      for region in regions:
          table_data = reader.read_table(
              region,
              header_rows=header_rows,
              merge_policy="anchor-only",  # D2 hybrid baseline
              include_hyperlinks=True,     # D5 always-on
              include_formulas=args.include_formulas,
              datetime_format=args.datetime_format,
          )
          # R20a interaction with hyperlinks (D5 + memory-mode):
          # If --memory-mode != "full" AND library auto-switched to
          # streaming (size threshold), hyperlinks are unreliable in
          # openpyxl ReadOnlyCell. Surface warning if any cell
          # value was lost (heuristic: empty `cell.hyperlink` map
          # on a sheet that the user knows has hyperlinks is hard
          # to detect post-hoc; the warning is emitted unconditionally
          # in streaming mode where read_only_mode==True).
          if read_only_mode is True:
              warnings.warn(
                  "hyperlinks unreliable in streaming mode; "
                  "pass --memory-mode=full or extract on a "
                  "smaller workbook",
                  UserWarning,
                  stacklevel=2,
              )
          yield (sheet, region, table_data)
  ```

**Function `_gap_fallback_if_empty(regions, sheet, reader, args,
library_mode) -> tuple[list[TableRegion], bool]`:**

- R8.f: if `args.no_table_autodetect` is True AND `regions` is
  empty (post-call filter dropped all to zero regions, e.g. dense
  data with no gap separator), fall back to whole-sheet emission:
  call `reader.detect_tables(sheet.name, mode="whole")` and
  return `(fallback_regions, True)`. Otherwise return `(regions,
  False)`.

**Function `_coerce_header_rows(value)`:**

- Argparse stores `--header-rows` as a string (because the
  parser accepts `int|"auto"|"smart"`). This helper coerces:
  - `"auto"` → `"auto"` (pass-through).
  - `"smart"` → `"smart"` (pass-through).
  - Any string matching `\d+` → `int(value)`.
  - Other → raise `argparse.ArgumentTypeError` (caught upstream
    or surfaced as terminal `InternalError`).

#### File: `skills/xlsx/scripts/xlsx2md/cli.py`

**Function `main()`:**

- BEFORE `with open_workbook(input_path) as reader:`, compute
  `read_only_mode = _resolve_read_only_mode(args)` (imported
  from `dispatch`) and pass to `open_workbook(input_path,
  read_only_mode=read_only_mode)`.
- Attach to `args` for downstream visibility:
  `args._read_only_mode_resolved = read_only_mode`.
- NO behaviour change to the envelope catch sites declared in
  012-02.

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_dispatch.py`

Unit tests using a minimal mock `WorkbookReader` (in-process
Python class) so the dispatch logic can be exercised without
real fixtures.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/two_sheets_one_hidden.xlsx`

Hand-built workbook: visible `Sheet1` and `Sheet2` (each with 1
header + 2 data rows) + hidden `_Internal`. Used by sheet-filter
tests.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/two_tables_gap.xlsx`

Hand-built: 1 sheet `"Budget"`, two tables separated by 3 empty
rows (R9 default `--gap-rows=2` triggers split).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/two_listobjects.xlsx`

Hand-built: 1 sheet `"Summary"` with two `xl/tables/tableN.xml`
ListObjects (`RevenueTable`, `CostsTable`). Used by UC-03 +
R8(a) detection tests.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/listobject_header_zero.xlsx`

Hand-built: 1 sheet with a ListObject configured
`headerRowCount="0"` (raw XML edit if openpyxl doesn't expose
this directly). Used by UC-11 synthetic-headers test.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/single_row_gap.xlsx`

Hand-built: 1 sheet with a single empty row INSIDE one table
(default `--gap-rows=2` does NOT split). Used by E2E #19.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/two_row_gap.xlsx`

Hand-built: 1 sheet with two consecutive empty rows between
two tables (default `--gap-rows=2` DOES split). Used by E2E #20.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/metadata_banner_header.xlsx`

Hand-built: 6-row metadata banner (`Author: ...`, `Date: ...`,
etc.) above row 7 unmerged single-row header + 10 data rows.
Used by `--header-rows=smart` test.

### Component Integration

- `dispatch.iter_table_payloads` is the only call site of
  `xlsx_read.WorkbookReader.read_table` in `xlsx2md/`. ruff
  banned-api enforces no `from xlsx_read._*` imports.
- Hyperlinks are always extracted (D5): `include_hyperlinks=True`
  is hard-coded in the `reader.read_table` call. The
  `--hyperlink-scheme-allowlist` filtering happens emit-side
  (012-04 / 012-05 via `inline._render_hyperlink`).
- `args._hyperlink_allowlist` and `args._read_only_mode_resolved`
  attributes are set by dispatch / cli respectively; consumed by
  emit-side. Internal-only namespace via `_` prefix.

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 5 | `T-hidden-sheet-skipped-default` | `two_sheets_one_hidden.xlsx` | `python3 xlsx2md.py two_sheets_one_hidden.xlsx out.md` → out.md has exactly 2 `## ` headings; `## _Internal` absent. | 0 |
| 6 | `T-hidden-sheet-included-with-flag` | `two_sheets_one_hidden.xlsx` | `python3 xlsx2md.py two_sheets_one_hidden.xlsx out.md --include-hidden` → out.md has 3 `## ` headings; `## _Internal` present. | 0 |
| 19 | `T-gap-detect-default-no-split-on-1-row` | `single_row_gap.xlsx` | `python3 xlsx2md.py single_row_gap.xlsx out.md` → out.md has exactly 1 `### Table-1` (or whole-sheet shape). | 0 |
| 20 | `T-gap-detect-splits-on-2-empty-rows` | `two_row_gap.xlsx` | `python3 xlsx2md.py two_row_gap.xlsx out.md` → out.md has 2 `### Table-` headings. | 0 |
| 25 | `T-no-autodetect-empty-fallback-whole-sheet` | dense 1-sheet workbook with no gaps + ListObjects (reuse `two_listobjects.xlsx`) | `python3 xlsx2md.py two_listobjects.xlsx out.md --no-table-autodetect` → `_gap_fallback_if_empty` fires; out.md emits whole-sheet markdown; stderr contains the info warning. | 0 |
| 26 | `T-header-rows-smart-skips-metadata-block` | `metadata_banner_header.xlsx` | `python3 xlsx2md.py metadata_banner_header.xlsx out.md --header-rows=smart` → out.md emits flat leaf-key header (NOT the metadata-block keys `["От","До"]`-style). | 0 |
| 28 | `T-memory-mode-streaming-bounds-peak-rss` | hand-built 15 MB workbook | `python3 xlsx2md.py large.xlsx out.md --memory-mode=streaming` → peak RSS ≤ 200 MB via `tracemalloc`; `@unittest.skipUnless(SLOW)` gate (slow test). | 0 |
| 29 | `T-memory-mode-auto-respects-library-default-100mib-threshold` | small workbook (< 100 MiB) | mock or assert `_resolve_read_only_mode(args)` returns `None` (library default respected) when `args.memory_mode == "auto"`. | 0 |

### Unit Tests

In `test_dispatch.py` (≥ 18 tests — supplements TASK §5.2's
`dispatch.py` count; dispatch is not in §5.2's min table but
real test budget is high here):

1. **TC-UNIT-01** `test_resolve_read_only_mode_auto_returns_none`.
2. **TC-UNIT-02** `test_resolve_read_only_mode_streaming_returns_true`.
3. **TC-UNIT-03** `test_resolve_read_only_mode_full_returns_false`.
4. **TC-UNIT-04** `test_detect_mode_no_split_returns_whole_with_passthrough_filter`.
5. **TC-UNIT-05** `test_detect_mode_no_table_autodetect_returns_auto_with_gap_filter`.
6. **TC-UNIT-06** `test_detect_mode_default_returns_auto_with_passthrough_filter`.
7. **TC-UNIT-07** `test_resolve_hyperlink_allowlist_default_three_schemes`.
8. **TC-UNIT-08** `test_resolve_hyperlink_allowlist_star_returns_none_sentinel`.
9. **TC-UNIT-09** `test_resolve_hyperlink_allowlist_empty_returns_empty_frozenset`.
10. **TC-UNIT-10** `test_resolve_hyperlink_allowlist_case_insensitive_lowercased`
    (`HTTP,Mailto` → `{"http", "mailto"}`).
11. **TC-UNIT-11** `test_iter_payloads_single_sheet_single_region` (mock
    reader; assert one triple).
12. **TC-UNIT-12** `test_iter_payloads_multi_sheet_all_visible` (mock
    reader; 2 visible + 1 hidden; `args.sheet="all"` and
    `include_hidden=False` → 2 triples).
13. **TC-UNIT-13** `test_iter_payloads_include_hidden_includes_hidden` (3 triples).
14. **TC-UNIT-14** `test_iter_payloads_sheet_named_single_match` (1 triple).
15. **TC-UNIT-15** `test_iter_payloads_sheet_named_not_found_raises_SheetNotFound`.
16. **TC-UNIT-16** `test_iter_payloads_gap_filter_only_passes_gap_detect`
    (mock reader returns 3 regions: 2 `gap_detect`, 1 `listobject`;
    `args.no_table_autodetect=True` → only the 2 yielded).
17. **TC-UNIT-17** `test_iter_payloads_gap_fallback_when_filter_empty` (R8.f).
18. **TC-UNIT-18** `test_iter_payloads_no_split_yields_whole_mode_single_region`.
19. **TC-UNIT-19** `test_iter_payloads_passes_header_rows_smart_to_read_table`
    (mock reader; assert `reader.read_table.call_args.kwargs["header_rows"]
    == "smart"`).
20. **TC-UNIT-20** `test_iter_payloads_passes_header_rows_int_to_read_table`
    (when arg is `"2"`, helper coerces to `2`; mock assert).
21. **TC-UNIT-21** `test_iter_payloads_always_include_hyperlinks_true` (D5).
22. **TC-UNIT-22** `test_iter_payloads_passes_datetime_format` (`args.datetime_format`
    forwarded verbatim to `read_table`).
23. **TC-UNIT-23** `test_iter_payloads_emits_streaming_hyperlink_warning_when_read_only_mode_true`
    (R20a interaction).
24. **TC-UNIT-24** `test_iter_payloads_listobjects_zero_header_count_propagates`
    (mock reader returns a region with
    `listobject_header_row_count=0`; assert `read_table` returns
    `TableData.warnings` containing "synthetic col_1"; the dispatch
    helper does NOT swallow the warning).

### Regression Tests

- 5-line `diff -q` silent gate.
- 012-01 + 012-02 tests still green.
- `ruff check skills/xlsx/scripts/` green (no `from xlsx_read._*`
  imports added).
- Existing xlsx test suites unchanged.

## Acceptance Criteria

- [ ] `_resolve_read_only_mode` correctly maps the 3 enum values
      to `None | True | False`.
- [ ] `_detect_mode_for_args` correctly maps `--no-split` → whole;
      `--no-table-autodetect` → `("auto", gap-only filter)`;
      default → `("auto", pass-through)`.
- [ ] `_resolve_hyperlink_allowlist` parses CSV with the special
      `'*'` (None sentinel) and `""` (empty frozenset) cases;
      case-insensitive.
- [ ] `iter_table_payloads` filters sheets by `--sheet` and
      `--include-hidden`; raises `SheetNotFound` for missing.
- [ ] `iter_table_payloads` calls `reader.detect_tables` with the
      mapped mode + gap-rows + gap-cols, then applies the
      post-call filter.
- [ ] `iter_table_payloads` falls back to `mode="whole"` when
      `--no-table-autodetect` filter yields zero (R8.f) and
      emits an info `UserWarning`.
- [ ] `iter_table_payloads` calls `reader.read_table` with
      `include_hyperlinks=True` always (D5).
- [ ] `iter_table_payloads` propagates `args.header_rows` value
      verbatim (`"auto"` / `"smart"` / int).
- [ ] `iter_table_payloads` emits the "hyperlinks unreliable in
      streaming mode" warning when `read_only_mode is True`.
- [ ] `cli.main()` resolves `read_only_mode` and passes it to
      `open_workbook`.
- [ ] All 8 E2E test slugs above bound and passing.
- [ ] All ≥ 24 unit tests pass.
- [ ] 012-01 + 012-02 tests still green; smoke E2E updated to
      assert the dispatch yields triples for the simple fixture.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green.
- [ ] No changes to `xlsx_read/`, `office/`,
      `_errors.py`, `_soffice.py`, `preview.py`,
      `office_passwd.py`, `requirements.txt`, `pyproject.toml`,
      `install.sh`, `xlsx2csv2json/`, `json2xlsx/`,
      `md_tables2xlsx/`.

## Stub-First Gate Update

The 012-01 + 012-02 smoke E2E assertions are updated per
`tdd-stub-first §2.4`:

- Asserting that `dispatch.iter_table_payloads(reader,
  parsed_args)` yields a non-empty iterator for the
  `single_cell.xlsx` fixture (was: yielding nothing in 012-01).
- The triple `(sheet_info, region, table_data)` shape is
  asserted: `sheet_info.name == "Sheet1"`,
  `len(table_data.headers) == 1`,
  `table_data.rows == [["hello"]]`.

## Notes

- **Mocking strategy:** for unit tests, build a minimal
  `MockReader` class in `test_dispatch.py` that implements
  `sheets()`, `detect_tables()`, `read_table()` — not a
  `Mock()` from `unittest.mock`. This makes assertions more
  readable and protects against API drift in `xlsx_read` (the
  mock has to track the real signatures by hand).
- The 15 MB workbook fixture for E2E #28 should be built on-the-fly
  in the test (don't commit a 15 MB blob). Use `openpyxl` (under
  `tracemalloc` measurement isolation — drop reference before
  measuring xlsx-9) to write a 50K × 30 cell `.xlsx` containing
  random short strings.
- The `args._hyperlink_allowlist` attribute is set here as a
  namespace-prefixed temp slot for emit-side consumption. An
  alternative would be to pass it as a separate parameter to
  `emit_workbook_md`; the chosen approach matches the existing
  xlsx-8 pattern (`args.hyperlink_scheme_allowlist` parsed into
  `frozenset` once by `cli._parse_scheme_allowlist`, then passed
  through).
- The R8.f info warning is emitted via `warnings.warn(...,
  UserWarning)` — captured by `cli._emit_warnings_to_stderr` and
  surfaced as a stderr line. It is NOT a `summary.warnings`
  list entry (xlsx-9 has no `summary` JSON output unlike xlsx-8).
- This task does NOT touch emit modules (012-04 / 012-05 / 012-06).
