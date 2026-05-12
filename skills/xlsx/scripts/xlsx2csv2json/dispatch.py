"""F2 — reader-glue and sheet/table name validation.

Drives the xlsx-10.A :mod:`xlsx_read` foundation library. Responsibilities:

* :func:`iter_table_payloads` — open-already-by-caller workbook,
  enumerate sheets per ``--sheet`` selector, detect regions per
  ``--tables`` mode (with the 4→3 enum mapping for ``gap``), iterate
  per region, yield ``(sheet_name, region, table_data, hyperlinks_map)``.
* :func:`_resolve_tables_mode` — maps the shim's 4-valued ``--tables``
  enum to the library's 3-valued :data:`xlsx_read.TableDetectMode`
  plus a region-source post-filter (D-A2).
* :func:`_validate_sheet_path_components` — cross-platform reject
  list for sheet / table names used as filesystem path components.
* :func:`_extract_hyperlinks_for_region` — parallel openpyxl pass
  that maps ``(row_idx, col_idx)`` → ``href`` for cells with a
  ``cell.hyperlink.target``. Needed because the library's
  ``include_hyperlinks=True`` mode REPLACES cell value with the URL;
  emit_json / emit_csv need BOTH text and URL.
"""
from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from typing import Any

from .exceptions import (
    InvalidSheetNameForFsPath,
    MultiSheetRequiresOutputDir,
    MultiTableRequiresOutputDir,
)


# Cross-platform reject list for sheet / table names destined to
# become a single path component of an emit-time file path. See
# `docs/TASK.md §4.2` and ARCH §4.2 for the rationale of each entry.
_FORBIDDEN_CHARS = frozenset({
    "/", "\\", "\x00",
    ":", "*", "?", "<", ">", "|", '"',
})
_FORBIDDEN_NAMES = frozenset({".", "..", ""})


def _validate_sheet_path_components(name: str) -> None:
    """Reject sheet / table names that are unsafe as filesystem path components.

    Raises:
        InvalidSheetNameForFsPath: ``name`` carries a forbidden char
            or is one of the degenerate names (``""``, ``"."``,
            ``".."``).
    """
    if name in _FORBIDDEN_NAMES:
        raise InvalidSheetNameForFsPath(
            f"Name unsafe for filesystem (reserved): {name!r}"
        )
    bad = _FORBIDDEN_CHARS.intersection(name)
    if bad:
        chars = "".join(sorted(bad))
        raise InvalidSheetNameForFsPath(
            f"Name unsafe for filesystem (forbidden chars {chars!r}): {name!r}"
        )
    if ".." in name:
        raise InvalidSheetNameForFsPath(
            f"Name unsafe for filesystem (contains '..'): {name!r}"
        )


def _resolve_tables_mode(arg_tables: str) -> tuple[str, Callable[[Any], bool]]:
    """Map shim ``--tables`` (4-val) to library mode (3-val) + post-filter.

    Returns ``(library_mode, predicate)`` where ``predicate(region)``
    decides whether to keep a region after library detection.

    Mapping (D-A2):

    * ``whole`` → library ``"whole"``, no filter.
    * ``listobjects`` → library ``"tables-only"``, no filter
      (Tier-2 sheet-scope named ranges are silently bundled with
      Tier-1 ListObjects — see TASK §1.4 (l)).
    * ``gap`` → library ``"auto"``, filter to keep only regions whose
      ``source == "gap_detect"``.
    * ``auto`` → library ``"auto"``, no filter.
    """
    if arg_tables == "whole":
        return ("whole", _accept_all)
    if arg_tables == "listobjects":
        return ("tables-only", _accept_all)
    if arg_tables == "gap":
        return ("auto", _accept_gap_only)
    if arg_tables == "auto":
        return ("auto", _accept_all)
    raise ValueError(f"Unknown --tables: {arg_tables!r}")


def _accept_all(region: Any) -> bool:
    return True


def _accept_gap_only(region: Any) -> bool:
    return region.source == "gap_detect"


def _extract_hyperlinks_for_region(reader: Any, region: Any) -> dict[tuple[int, int], str]:
    """Parallel pass: extract ``(row_idx, col_idx) -> href`` for the region.

    The xlsx_read library's ``include_hyperlinks=True`` mode replaces
    the cell value with the URL — fine for "tell me the URL" but not
    what xlsx-8 needs for ``{"value", "href"}`` (JSON) and
    ``[text](url)`` (CSV) emission.

    Returns a mapping keyed by ``(0-based row within the region,
    0-based column within the region)``. Cells without a hyperlink are
    absent from the map.
    """
    result: dict[tuple[int, int], str] = {}
    # Access the underlying openpyxl worksheet via reader._wb (private
    # attribute, but the reader exposes no public worksheet handle by
    # design — closed-API purity per xlsx_read §D-A3). This is the one
    # legitimate cross-the-fence use because hyperlinks need cell-
    # object access, not just values.
    wb = getattr(reader, "_wb", None)
    if wb is None:
        return result
    ws = wb[region.sheet]
    for row_offset, row_cells in enumerate(
        ws.iter_rows(
            min_row=region.top_row, max_row=region.bottom_row,
            min_col=region.left_col, max_col=region.right_col,
            values_only=False,
        )
    ):
        for col_offset, cell in enumerate(row_cells):
            hl = getattr(cell, "hyperlink", None)
            if hl is None:
                continue
            target = getattr(hl, "target", None)
            if target:
                result[(row_offset, col_offset)] = str(target)
    return result


def iter_table_payloads(
    args: Any,
    reader: Any,
    *,
    format: str | None = None,
) -> Iterator[tuple[str, Any, Any, dict[tuple[int, int], str] | None]]:
    """Yield ``(sheet_name, region, table_data, hyperlinks_map)`` per region.

    The 4-tuple shape preserves doc-order. ``hyperlinks_map`` is
    ``None`` unless ``args.include_hyperlinks`` is set; when set, the
    map is keyed by ``(row_offset_within_region, col_offset_within_region)``
    so the emitter can reconstruct the dict-shape / markdown-link
    cells without re-reading openpyxl.

    Pre-flight invariants raised here (post sheet enumeration):

    * :class:`MultiSheetRequiresOutputDir` — ``--sheet all`` ∧ CSV ∧
      no ``--output-dir`` ∧ > 1 visible sheet.
    * :class:`MultiTableRequiresOutputDir` — CSV ∧
      ``--tables != whole`` ∧ no ``--output-dir`` ∧ ≥ 1 sheet produces
      > 1 region.

    Pre-flight path-component validation (D-A8 first-line defence):
    when the eventual layout will be a CSV subdirectory, every
    sheet / table name is passed through
    :func:`_validate_sheet_path_components` BEFORE yielding.
    """
    from xlsx_read import SheetNotFound

    library_mode, post_filter = _resolve_tables_mode(args.tables)
    is_csv = (format == "csv")
    csv_multi_file = is_csv and (args.output_dir is not None)

    # Sheet selection.
    sheet_infos = reader.sheets()
    if args.sheet == "all":
        selected = [
            s for s in sheet_infos
            if args.include_hidden or s.state == "visible"
        ]
        # Multi-sheet CSV without output-dir: raise eagerly so the
        # emitter doesn't even start writing. The conservative parse-
        # time check in cli.py only fires on explicit "-" output;
        # this is the real check.
        if is_csv and not csv_multi_file and len(selected) > 1:
            raise MultiSheetRequiresOutputDir(
                f"CSV cannot multiplex {len(selected)} visible sheets into "
                f"a single stream. Use --output-dir or --sheet <NAME>."
            )
    else:
        # Validate by selecting; library raises SheetNotFound on miss.
        matching = [s for s in sheet_infos if s.name == args.sheet]
        if not matching:
            raise SheetNotFound(args.sheet)
        if not args.include_hidden and matching[0].state != "visible":
            # Caller asked for a specific sheet that is hidden; we
            # honour the explicit name (the hidden filter is for "all").
            pass
        selected = matching

    # Resolve header_rows for `read_table`. `1` (default) and `"auto"`
    # are both legal; `int` other than 1 was guarded by `cli._validate_flag_combo`
    # against multi-table mode.
    header_rows_arg = args.header_rows

    for sheet_info in selected:
        sheet_name = sheet_info.name
        regions = reader.detect_tables(
            sheet_name,
            mode=library_mode,
            gap_rows=args.gap_rows,
            gap_cols=args.gap_cols,
        )
        regions = [r for r in regions if post_filter(r)]

        # R12.d enforcement: CSV multi-region without output-dir.
        if is_csv and args.tables != "whole" and len(regions) > 1 and not csv_multi_file:
            raise MultiTableRequiresOutputDir(
                f"CSV with --tables={args.tables!r} produced {len(regions)} "
                f"regions on sheet {sheet_name!r}; --output-dir is required."
            )

        # D-A8 first-line defence: validate sheet name when emitting
        # to subdir layout. Region names validated per region below.
        if csv_multi_file:
            _validate_sheet_path_components(sheet_name)

        for i, region in enumerate(regions):
            # Region name defensive default — library should always
            # set `.name` (gap_detect → "Table-N", listobject → table
            # name, named_range → range name). The fallback is purely
            # belt-and-braces.
            region_name = region.name or f"Table-{i + 1}"

            if csv_multi_file:
                _validate_sheet_path_components(region_name)

            # The library's `include_hyperlinks=True` REPLACES value
            # with URL; we always read text via `include_hyperlinks
            # =False` and do a parallel hyperlink pass when the user
            # asked for them.
            table_data = reader.read_table(
                region,
                header_rows=header_rows_arg,
                merge_policy=args.merge_policy,
                include_hyperlinks=False,
                include_formulas=args.include_formulas,
                datetime_format=args.datetime_format,
            )

            hyperlinks_map: dict[tuple[int, int], str] | None = None
            if args.include_hyperlinks:
                hyperlinks_map = _extract_hyperlinks_for_region(reader, region)

            # H2 (vdd-multi): the library appends soft warnings to
            # `TableData.warnings` (list[str]) without calling
            # `warnings.warn`. Re-emit them here so the shim's outer
            # `warnings.catch_warnings(record=True)` block in cli.py can
            # see them and route to stderr per HS-7.
            for msg in getattr(table_data, "warnings", None) or ():
                warnings.warn(msg, UserWarning, stacklevel=2)

            yield (sheet_name, region, table_data, hyperlinks_map)
