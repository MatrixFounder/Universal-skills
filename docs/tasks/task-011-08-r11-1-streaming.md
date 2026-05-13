# Task 011.08 — [R10] R11.1 single-region JSON streaming

## Use Case Connection
- UC-07: Large-table JSON emit, R11.1 single-region (`xlsx-8a-08`)

## Task Goal
Refactor the row-emit pipeline in
[`emit_json.py`](../../skills/xlsx/scripts/xlsx2csv2json/emit_json.py)
so that the R11.1 single-region shape (`[{...},{...},...]`) is
streamed row-by-row to disk, closing PERF-HIGH-2 for the most
common large-table case (peak RSS ≤ 200 MB on 3M cells vs.
1-1.5 GB in v1).

**Three coordinated changes:**

1. Convert `_rows_to_dicts`, `_rows_to_string_style`,
   `_rows_to_array_style` from `list`-returning to
   `Iterator[dict]`-yielding (generators). Callers in R11.2-4
   branches consume eagerly via `list(...)` at the call site —
   preserves the v1 dict-of-arrays semantics.

2. New helper `_stream_single_region_json(payload, output_path,
   ...)` writes the R11.1 shape row-by-row. **Per arch-review M3
   fix**, the helper handles the empty-payload case via
   `try/except StopIteration` so the output is byte-identical to
   v1 `json.dumps([], indent=2) + "\n"` = `"[]\n"`.

3. `_shape_for_payloads` early-detects R11.1
   (`single_sheet ∧ not is_multi_region[only_sheet]`) and
   dispatches to `_stream_single_region_json`. R11.2-4 paths
   continue through the existing `_shape_for_payloads` →
   `emit_json` → (R9 from 011-07) `json.dump(fp)` route.

**Dependencies:**
- 011-06 (fixture-timing prerequisite for the 3M-cell test).
- 011-07 (recommended ordering — R9's simpler refactor stabilises
  the file-output path before R10 layers the generator refactor).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_json.py`

**Function `_rows_to_string_style` (lines ~211-255) — generator
conversion:**
- Change signature return type:
  `-> list[dict[str, Any]]` → `-> Iterator[dict[str, Any]]`.
- Replace `out: list[dict] = []; ... out.append(d)` with `yield d`
  at the corresponding line.
- Drop the trailing `return out`.
- The `drop_empty_rows` filter (R28) becomes a `continue` (skip
  yield) — semantically equivalent.

**Function `_rows_to_array_style` (lines ~290-319) — generator
conversion:**
- Same pattern: `-> Iterator[list[dict[str, Any]]]`; `yield cells`
  instead of `out.append(cells)`.

**Function `_rows_to_dicts` (lines ~172-208) — generator passthrough:**
- Return type: `-> Iterator[Any]`.
- The body already dispatches to `_rows_to_string_style` /
  `_rows_to_array_style` — those become generators, so
  `_rows_to_dicts` returns whichever generator it dispatched to.
  (Python: `return generator_func()` from inside a function makes
  `_rows_to_dicts` itself a normal function returning a generator
  — semantically OK; not a generator-function per se.)

**Function `_shape_for_payloads` (lines ~102-160) — R11.1
early-detect:**

Add at the top of the function (after the `if not payloads_list:`
early-return):

```python
# R10 / xlsx-8a-08: detect R11.1 (single sheet, single region)
# and signal upstream that streaming should be used. We do NOT
# build the shape here — `emit_json` reads the sentinel and
# dispatches to `_stream_single_region_json`.
if len(by_sheet) == 1:
    only_sheet = next(iter(by_sheet))
    if len(by_sheet[only_sheet]) == 1:
        return _R11_1_STREAM_SENTINEL  # module-level constant
```

The R11.2-4 branches that follow are unchanged.

**New module-level sentinel:**
- `_R11_1_STREAM_SENTINEL = object()` — a unique singleton used
  to signal R11.1 dispatch without building the shape.

**Function `emit_json` (lines ~64-99) — R11.1 dispatch:**

After the `shape = _shape_for_payloads(...)` call, add:

```python
if shape is _R11_1_STREAM_SENTINEL:
    # R10: stream R11.1 directly to output.
    # The payload list has exactly one entry (verified by
    # _shape_for_payloads's R11.1 detect).
    return _stream_single_region_json(
        payloads_list[0],
        output_path=output,
        header_flatten_style=header_flatten_style,
        include_hyperlinks=include_hyperlinks,
        drop_empty_rows=drop_empty_rows,
    )

# R11.2-4 paths continue through the existing R9 file-output /
# stdout branches (set by 011-07).
text = json.dumps(...)
# ... (unchanged from 011-07)
```

**New function `_stream_single_region_json`** (per ARCH §15.10.2 M3
fix):

```python
def _stream_single_region_json(
    payload: tuple[str, Any, Any, dict[tuple[int, int], str] | None],
    *,
    output_path: Path | None,
    header_flatten_style: str,
    include_hyperlinks: bool,
    drop_empty_rows: bool = False,
) -> int:
    """Stream the R11.1 single-region JSON shape `[{...},...]`
    row-by-row, closing PERF-HIGH-2 for the most common
    large-table case.

    Byte-identical to v1 `json.dumps(shape, indent=2) + "\\n"` on
    every R11.1 fixture, including the empty-payload case
    (`"[]\\n"`).

    stdout path: writes to `sys.stdout` directly. The pipe
    consumer buffers the output downstream regardless; the
    streaming preserves **producer-side** RSS bounds (Q-15-6).
    """
    sheet_name, region, table_data, hl_map = payload
    rows_iter = iter(_rows_to_dicts(
        table_data, hl_map, header_flatten_style,
        include_hyperlinks, drop_empty_rows,
    ))

    # Determine the output stream
    if output_path is None:
        fp = sys.stdout
        close_fp = False
    else:
        fp = output_path.open("w", encoding="utf-8")
        close_fp = True

    try:
        # Empty-payload early-exit — v1-byte-identical "[]\n".
        try:
            first_row = next(rows_iter)
        except StopIteration:
            fp.write("[]\n")
            return 0

        fp.write("[\n  ")
        first_row_json = json.dumps(
            first_row, ensure_ascii=False, indent=2,
            default=_json_default,
        ).replace("\n", "\n  ")
        fp.write(first_row_json)

        for row_dict in rows_iter:
            row_json = json.dumps(
                row_dict, ensure_ascii=False, indent=2,
                default=_json_default,
            ).replace("\n", "\n  ")
            fp.write(",\n  ")
            fp.write(row_json)

        fp.write("\n]\n")
        return 0
    finally:
        if close_fp:
            fp.close()
```

**Callers in R11.2-4 branches** (inside `_shape_for_payloads`,
lines ~141-160):
- Replace `_rows_to_dicts(...)` calls with `list(_rows_to_dicts(...))`
  to materialise the generator into the old list-shape that the
  dict-builder expects. Two locations: the "Rule 3 per-sheet"
  branch and the "Rule 2 per-sheet" branch.

#### File: `docs/KNOWN_ISSUES.md`

**Narrow the `PERF-HIGH-2` entry**:
- Status line: change from "Deferred" to "**Partially closed
  (2026-05-13, xlsx-8a-07/08)**. R11.1 single-region JSON path
  is now fully streamed via `_stream_single_region_json`. R9 also
  drops the `json.dumps` string-buffer copy for all file outputs.
  **Residual**: R11.2-4 multi-sheet / nested-dict shapes still
  materialise the `shape` dict in memory."
- Location subsection: **delete** the `emit_json.py:79` reference
  (R10 closes that path). **Narrow** the `emit_csv.py:59`
  reference to: "`payloads_list = list(payloads)` —
  **region-list materialisation only**; per-row writes already
  stream via `csv.writer.writerow`."
- Related line: add a reference to `xlsx-8c-multi-sheet-stream`
  (the new backlog row created in this task) as the follow-up
  carrier.

#### File: `docs/office-skills-backlog.md`

**Create new backlog row stub**:

Add a new row in the xlsx section (after `xlsx-8a`):

```
| **xlsx-8c-multi-sheet-stream** | per-sheet JSON streaming for
R11.2 (multi-sheet single-region) | refactor `_shape_for_payloads`
R11.2 branch to per-sheet append: open `{`, for each sheet write
`"name": [` + stream rows + `]` + `,`/`}`. R11.3-4 (nested-dict
multi-region) cannot be RFC-8259-streamed without a chunked-
encoding contract — out of scope. | M | M | xlsx-8a (✅ DONE) |
Stub created 2026-05-13 by 011-08 as a follow-up carrier for the
narrowed PERF-HIGH-2 entry. Open if a real R11.2 large-table
workload (multi-sheet, ≥ 1M cells per sheet) is observed. | open |
```

### Component Integration

- The generator refactor is internal to `emit_json.py`. Callers
  upstream (`cli._dispatch_to_emit`) don't change.
- The `_R11_1_STREAM_SENTINEL` is a private module-level object;
  external `xlsx2csv2json.__all__` is unchanged.
- The `_stream_single_region_json` helper is private (`_`-prefix);
  not exposed.

## Test Cases

### End-to-end Tests

Hosted in `xlsx2csv2json/tests/test_streaming.py` (new file).

1. **TC-E2E-01:** `test_R10_stream_byte_identical_to_v1_single_sheet_single_region`
   - Approach: for every fixture in
     `xlsx2csv2json/tests/fixtures/` that produces R11.1 shape
     (single sheet, `--tables whole` mode), run both:
     (a) the streaming path (current R10 behaviour) — write to
     temp file A.
     (b) the v1 reference path (held inline in the test as
     `_v1_emit_via_dumps`) — write to temp file B.
     Assert `diff -q A B` returns no output.
   - Coverage: includes empty-table fixture, single-row fixture,
     multi-row fixture, fixture with hyperlinks, fixture with
     unicode cells.

2. **TC-E2E-02:** `test_R10_stream_3M_cells_peak_rss_below_200MB`
   - Fixture: synthetic 100K × 30 single-sheet workbook.
   - Invocation: `python3 xlsx2json.py big.xlsx --output out.json`
     under `tracemalloc.start()` instrumentation.
   - Expected: peak RSS during `_stream_single_region_json` is
     ≤ 200 MB (excludes openpyxl loading peak).
   - Honest scope: measures only the emit-pass peak, not the full
     CLI peak. `tracemalloc` snapshot taken before and after the
     emit call.

3. **TC-E2E-03:** `test_R10_stream_with_hyperlinks`
   - Fixture: single-sheet workbook with hyperlink cells.
   - Expected: streaming output contains the `{value, href}`
     wrapper dicts for hyperlink cells (passes through the
     generator unchanged).

4. **TC-E2E-04:** `test_R10_stream_array_style`
   - Fixture: same R11.1 workbook.
   - Invocation: `--header-flatten-style array`.
   - Expected: streaming output via `_rows_to_array_style`
     generator; byte-identical to v1 `array` style.

5. **TC-E2E-05:** `test_R10_stream_empty_table`
   - Fixture: workbook with one sheet, no data (just empty cells
     or no headers).
   - Expected: output is exactly `"[]\n"` (3 bytes) — the M3
     early-exit guard fires.

6. **TC-E2E-06:** `test_R10_R11_2_to_4_unchanged`
   - For every multi-sheet AND/OR multi-region fixture, verify
     output is identical between the post-011-08 build and the
     pre-011-08 (post-011-07) build. Asserts the R11.2-4 paths
     are not affected by the generator refactor.

7. **TC-E2E-07** (optional): `test_R10_post_validate_passes_on_r11_1_streaming`
   - Set env `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1`; run the shim
     on an R11.1 fixture; assert exit 0 (round-trip via
     `json.loads()` succeeds).

### Unit Tests

1. **TC-UNIT-01:** `test_R10_rows_to_dicts_is_generator`
   - Call `_rows_to_dicts(...)`; assert the result has a
     `__next__` attribute (i.e. is an iterator, not a list).

2. **TC-UNIT-02:** `test_R10_stream_helper_empty_branch`
   - Direct call to `_stream_single_region_json` with a `payload`
     whose `table_data.rows` is empty; assert output file content
     is exactly `"[]\n"`.

### Regression Tests
- All existing `test_emit_json.py` tests green (R11.1 fixtures
  via the new streaming path; R11.2-4 via the unchanged R9
  path).
- `test_R9_file_byte_identical_to_v1` and
  `test_R9_file_output_no_string_buffer` from 011-07 remain
  green (R9 is only used for R11.2-4 now).
- `test_e2e.py::test_roundtrip_xlsx_2` green.
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `grep -n "_stream_single_region_json"
  skills/xlsx/scripts/xlsx2csv2json/emit_json.py` returns ≥ 2 hits
  (definition + caller in `emit_json`).
- [ ] `_rows_to_dicts` returns an iterator (TC-UNIT-01 asserts).
- [ ] All 6 mandatory E2E + 2 unit tests green (TC-E2E-07 is
  optional).
- [ ] `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1` env-flag round-trip
  passes on every R11.1 fixture.
- [ ] R11.2-4 fixtures byte-identical pre/post (TC-E2E-06).
- [ ] `docs/KNOWN_ISSUES.md` PERF-HIGH-2 entry narrowed (status,
  location, related — all three subsections updated).
- [ ] `docs/office-skills-backlog.md` carries the new
  `xlsx-8c-multi-sheet-stream` row.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `validate_skill.py skills/xlsx` exit 0.
- [ ] Full regression suite green (`xlsx_read/tests/` +
  `xlsx2csv2json/tests/`).
- [ ] 12-line cross-skill `diff -q` gate silent.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Convert `_rows_to_dicts` / `_rows_to_string_style` /
   `_rows_to_array_style` to generators.
2. Add `list(...)` wrappers at the R11.2-4 call sites in
   `_shape_for_payloads`.
3. Add `_R11_1_STREAM_SENTINEL` constant.
4. Add `_shape_for_payloads` R11.1 early-detect dispatch
   (returns the sentinel).
5. Add `_stream_single_region_json` function with **stub body**:
   ```python
   raise NotImplementedError("011-08 Pass 2 not yet landed")
   ```
6. Add `emit_json` sentinel-dispatch branch (calls the stub).
7. Write all 6 E2E + 2 unit tests.
   - TC-UNIT-01 passes (generator confirmation).
   - TC-E2E-06 (R11.2-4 unchanged) passes (R11.1 dispatch returns
     sentinel; R11.2-4 fixtures go through R9 unchanged).
   - TC-E2E-01..05 + TC-UNIT-02 FAIL Red (NotImplementedError on
     R11.1 dispatch).

### Pass 2 — Logic + Green E2E
1. Replace the `NotImplementedError` stub body with the real
   `_stream_single_region_json` implementation (per M3 fix —
   `try/except StopIteration` empty-payload guard).
2. Re-run all tests — Green.
3. Update `docs/KNOWN_ISSUES.md` PERF-HIGH-2 entry (status,
   location, related).
4. Add `xlsx-8c-multi-sheet-stream` stub row to
   `docs/office-skills-backlog.md`.

## Notes
- The byte-identity invariant is the **highest-risk** item. A
  1-character indent drift or trailing-newline drift breaks every
  R11.1 regression test. Run TC-E2E-01 frequently during Pass 2.
- The `tracemalloc` budget in TC-E2E-02 (200 MB) is sized for the
  emit-pass peak only. Openpyxl loading + workbook parsing peak
  separately at ~300 MB on a 100K × 30 fixture; that's NOT in the
  budget.
- The R11.2-4 path uses `list(generator)` materialisation at the
  call sites — same memory characteristics as v1 (the
  generator-vs-list distinction only matters for the R11.1
  streaming path). This is intentional per D-A18.
- Effort: L (~6 hours). Diff size: ~120 LOC across 1 source file
  + ~300 LOC test file + `KNOWN_ISSUES.md` edit + backlog row
  addition.
