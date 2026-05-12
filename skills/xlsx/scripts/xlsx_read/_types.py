"""Public dataclass + enum + WorkbookReader contract for xlsx_read.

Dataclasses are `frozen=True` at the outer level only — inner sequences
(`rows`, `headers`, `warnings`) are mutable Python lists by design
(M3 + R2-M6 honest scope: deep-freeze adds caller-side ergonomic
friction with no performance win — `tuple()` and `list()` constructors
are both O(n)). Caller MUST NOT mutate these lists; library does not
deepcopy on read.

WorkbookReader exposes the public method surface; in this task all
methods are stubs (`NotImplementedError` or sentinel returns).
Subsequent tasks (009-02..009-08) replace the stubs with real logic
without changing the public signatures or `__all__`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MergePolicy = Literal["anchor-only", "fill", "blank"]
TableDetectMode = Literal["auto", "tables-only", "whole"]
DateFmt = Literal["ISO", "excel-serial", "raw"]


@dataclass(frozen=True)
class SheetInfo:
    """Metadata about a single worksheet."""

    name: str
    index: int
    state: Literal["visible", "hidden", "veryHidden"]


@dataclass(frozen=True)
class TableRegion:
    """Rectangular region on a sheet considered "a table"."""

    sheet: str
    top_row: int
    left_col: int
    bottom_row: int
    right_col: int
    source: Literal["listobject", "named_range", "gap_detect"]
    name: str | None = None
    listobject_header_row_count: int | None = None


@dataclass(frozen=True)
class TableData:
    """Materialised payload of a single region.

    Outer struct is immutable; `rows`, `headers`, `warnings` are
    intentionally mutable lists (see module docstring).
    """

    region: TableRegion
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkbookReader:
    """Bound reader over an open workbook.

    NOT thread-safe — openpyxl `Workbook` is not thread-safe. Caller
    is responsible for per-thread / per-process instances. There are
    no module-level mutable singletons in xlsx_read; this class itself
    is the only state holder.

    All methods on this class are **stubs** in task 009-01 and are
    replaced with real logic in tasks 009-02..009-08:

    - `sheets()` → 009-03 wires to `_sheets.enumerate_sheets`.
    - `detect_tables()` → 009-05 wires to `_tables.detect_tables`.
    - `read_table()` → 009-08 wires F3 + F5 + F6 dispatch.
    - `close()` → 009-02 wires to `self._wb.close()`.
    """

    path: Path
    _wb: Any = None
    _read_only: bool = False
    _keep_formulas: bool = False
    _closed: bool = False
    # Per-sheet memo for `_overlapping_merges_check` (P-H1 / S-L3 fix).
    # An overlapping-merge detection is a static property of the sheet
    # — running it once per `read_table` call wastes O(n²) work when
    # the caller reads multiple regions. We memoize on sheet name and
    # invalidate on `close()`.
    _overlap_checked: set[str] = field(default_factory=set)

    def sheets(self) -> list[SheetInfo]:
        """Enumerate sheets in document order.

        Wired to `_sheets.enumerate_sheets(self._wb)` since 009-03.
        Caller filters by `info.state` as needed (UC-02 main scenario
        step 3).
        """
        # Imported inside the method to keep the dataclass module free
        # of circular-import surface (`_sheets` imports `_types`).
        from ._sheets import enumerate_sheets

        if self._wb is None:
            return []
        return enumerate_sheets(self._wb)

    def detect_tables(
        self,
        sheet: str,
        *,
        mode: TableDetectMode = "auto",
        gap_rows: int = 2,
        gap_cols: int = 1,
    ) -> list[TableRegion]:
        """Detect tables via 3-tier strategy (LIVE since 009-05)."""
        from ._tables import detect_tables

        if self._wb is None:
            return []
        return detect_tables(
            self._wb, sheet, mode=mode, gap_rows=gap_rows, gap_cols=gap_cols
        )

    def read_table(
        self,
        region: TableRegion,
        *,
        header_rows: int | Literal["auto"] = "auto",
        merge_policy: MergePolicy = "anchor-only",
        include_hyperlinks: bool = False,
        include_formulas: bool = False,
        datetime_format: DateFmt = "ISO",
    ) -> TableData:
        """Materialise a region into `TableData` (LIVE since 009-08).

        Pipeline: overlap-check → parse merges → slice region grid →
        apply merge policy → resolve header band (incl. synthetic
        col_1..col_N for listobject_header_row_count=0) → flatten
        headers → extract values per cell, lifting warnings.
        """
        from ._headers import (
            _ambiguous_boundary_check,
            detect_header_band,
            flatten_headers,
            synthetic_headers,
        )
        from ._merges import (
            apply_merge_policy,
            parse_merges,
            _overlapping_merges_check,
        )
        from ._values import extract_cell

        if self._wb is None:
            return TableData(region=region)

        ws = self._wb[region.sheet]
        # P-H1 / S-L3 fix (iter-3 NEW-S-M1 soundness regression fix):
        # run the O(n²) overlap detector ONCE per **sheet** across the
        # reader's lifetime — the overlap property is static. The
        # earlier iter-2 region-filter optimisation broke the fail-
        # loud contract for multi-region readers (region B's overlaps
        # were silently skipped after region A's call). Now we check
        # the entire sheet's merges on the cold pass; bounded by
        # Excel's practical merge cap (typically < 100 per sheet).
        if region.sheet not in self._overlap_checked:
            _overlapping_merges_check(list(ws.merged_cells.ranges))
            self._overlap_checked.add(region.sheet)
        merges = parse_merges(ws)

        # Stream the region via `iter_rows(...)` (P-C2 fix). The
        # historical nested `ws.cell(r, c)` pattern is fatal in
        # openpyxl `read_only=True` mode (each call re-walks the sheet
        # XML stream). `iter_rows` is the documented streaming entry.
        warnings_list: list[str] = []
        values_grid: list[list[Any]] = []
        n_cols_expected = region.right_col - region.left_col + 1
        for row_cells in ws.iter_rows(
            min_row=region.top_row, max_row=region.bottom_row,
            min_col=region.left_col, max_col=region.right_col,
            values_only=False,
        ):
            row_vals: list[Any] = []
            for cell in row_cells:
                v, w = extract_cell(
                    cell,
                    include_formulas=include_formulas,
                    include_hyperlinks=include_hyperlinks,
                    datetime_format=datetime_format,
                )
                if w is not None:
                    warnings_list.append(w)
                row_vals.append(v)
            # Pad short rows (sparse streaming may yield fewer cells).
            if len(row_vals) < n_cols_expected:
                row_vals.extend([None] * (n_cols_expected - len(row_vals)))
            values_grid.append(row_vals)
        # Pad missing rows (iter_rows skips entirely-empty rows in
        # read_only mode on some openpyxl versions).
        n_rows_expected = region.bottom_row - region.top_row + 1
        while len(values_grid) < n_rows_expected:
            values_grid.append([None] * n_cols_expected)
        values_grid = apply_merge_policy(
            values_grid, merges, merge_policy,
            top_row=region.top_row, left_col=region.left_col,
        )

        # Header resolution.
        if (
            region.source == "listobject"
            and region.listobject_header_row_count == 0
        ):
            width = region.right_col - region.left_col + 1
            headers = synthetic_headers(width)
            warnings_list.append(
                f"Table {region.name!r} had no headers; "
                f"emitted synthetic col_1..col_{width}"
            )
            data_rows = values_grid
        else:
            if (
                region.source == "listobject"
                and region.listobject_header_row_count is not None
                and region.listobject_header_row_count > 0
                and header_rows == "auto"
            ):
                hdr = region.listobject_header_row_count
            else:
                hdr = detect_header_band(ws, region, header_rows)
            if hdr == 0:
                width = region.right_col - region.left_col + 1
                headers = synthetic_headers(width)
                data_rows = values_grid
            else:
                ambig = _ambiguous_boundary_check(
                    list(ws.merged_cells.ranges), region, hdr
                )
                if ambig is not None:
                    warnings_list.append(ambig)
                headers, hdr_warnings = flatten_headers(values_grid[:hdr], hdr)
                warnings_list.extend(hdr_warnings)
                data_rows = values_grid[hdr:]

        return TableData(
            region=region,
            headers=headers,
            rows=data_rows,
            warnings=warnings_list,
        )

    def close(self) -> None:
        """Release the underlying openpyxl Workbook.

        Idempotent: second call is a no-op. After 009-02, this actually
        invokes `self._wb.close()` (which releases the underlying
        file handle in `read_only=True` streaming mode and is harmless
        in `read_only=False`).
        """
        if self._closed:
            return
        wb = self._wb
        if wb is not None and hasattr(wb, "close"):
            wb.close()
        # Drop the per-sheet overlap-check memo so a future caller
        # (which would have to recreate the reader anyway) gets a fresh
        # check pass.
        self._overlap_checked.clear()
        self._closed = True

    def __enter__(self) -> WorkbookReader:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
