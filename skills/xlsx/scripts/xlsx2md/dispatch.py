"""F2 — Reader-glue / dispatch. LIVE since task 012-03 (4-tuple in 012-04).

Opens the workbook via ``xlsx_read.open_workbook`` (with
``read_only_mode`` resolved from ``--memory-mode``), enumerates sheets,
detects regions, and yields ``(sheet_info, region, table_data,
hyperlinks_map)`` **4-tuples** to the emitter. The 4th element is the
parallel-pass hyperlink map keyed by ``(row_offset, col_offset)``
within the region — see :func:`_extract_hyperlinks_for_region`.

Functions:
  - :func:`_resolve_read_only_mode` — maps ``--memory-mode`` to
    ``open_workbook(read_only_mode=...)`` (R20a / D-A14).
  - :func:`_detect_mode_for_args` — maps ``--no-split`` /
    ``--no-table-autodetect`` to ``(TableDetectMode, post_filter)``
    (D-A2 4-state → 3-state).
  - :func:`_resolve_hyperlink_allowlist` — parses
    ``--hyperlink-scheme-allowlist`` CSV into ``frozenset[str] | None``.
  - :func:`_coerce_header_rows` — converts ``args.header_rows`` to the
    type expected by ``reader.read_table``.
  - :func:`_gap_fallback_if_empty` — R8.f fallback: when
    ``--no-table-autodetect`` filter yields zero regions, fall back to
    ``mode="whole"``.
  - :func:`_extract_hyperlinks_for_region` — Path C′ (mirror of
    xlsx-8 ``_extract_hyperlinks_for_region`` at
    [xlsx2csv2json/dispatch.py:102-176](../xlsx2csv2json/dispatch.py));
    parallel pass over the same region accessing the underlying
    openpyxl Workbook via ``reader._wb`` to pull ``cell.hyperlink.target``.
    Needed because ``xlsx_read.read_table(include_hyperlinks=True)``
    REPLACES display text with the URL; xlsx-9 needs both for
    ``[click here](https://...)`` (GFM) and
    ``<a href="...">click here</a>`` (HTML). Applies
    ``--hyperlink-scheme-allowlist`` filter at the dispatch boundary
    (R10a / D-A15 / Sec-MED-2) — blocked-scheme cells are dropped from
    the map, so emit-side renders them as plain text via the
    no-hyperlink branch. Per-distinct-scheme deduped ``warnings.warn``.
  - :func:`iter_table_payloads` — top-level generator; calls all of
    the above and yields ``(SheetInfo, TableRegion, TableData,
    hyperlinks_map)`` 4-tuples. ``read_table`` is called with
    ``include_hyperlinks=False`` so display text survives; hyperlinks
    arrive via the parallel pass.
"""
from __future__ import annotations

import argparse
import warnings
from collections.abc import Callable, Iterator
from typing import Any

from xlsx_read import (
    SheetInfo,
    SheetNotFound,
    TableData,
    TableDetectMode,
    TableRegion,
    WorkbookReader,
)


def _resolve_read_only_mode(args: Any) -> bool | None:
    """Map ``--memory-mode`` to ``open_workbook(read_only_mode=...)``.

    Mapping (R20a / D-A14):
      - ``"auto"``      → ``None``  (library default; ≥ 100 MiB → streaming).
      - ``"streaming"`` → ``True``  (force openpyxl read_only=True).
      - ``"full"``      → ``False`` (force read_only=False, correct merges).

    Raises:
        ValueError: if ``args.memory_mode`` is not one of the three
            accepted values (argparse ``choices=`` should prevent this at
            runtime; the guard exists for programmatic callers).
    """
    mode = args.memory_mode
    if mode == "auto":
        return None
    if mode == "streaming":
        return True
    if mode == "full":
        return False
    raise ValueError(
        f"Unknown --memory-mode value {mode!r}; "
        "expected one of: 'auto', 'streaming', 'full'"
    )


def _detect_mode_for_args(
    args: Any,
) -> tuple[TableDetectMode, Callable[[TableRegion], bool]]:
    """Return ``(library_mode, post_filter_predicate)`` for ``args``.

    D-A2 4-state → 3-state mapping:
      - ``--no-split`` → ``("whole", lambda r: True)``
      - ``--no-table-autodetect`` →
        ``("auto", lambda r: r.source == "gap_detect")``
      - default → ``("auto", lambda r: True)``
    """
    if getattr(args, "no_split", False):
        return ("whole", lambda r: True)
    if getattr(args, "no_table_autodetect", False):
        return ("auto", lambda r: r.source == "gap_detect")
    return ("auto", lambda r: True)


def _resolve_hyperlink_allowlist(args: Any) -> frozenset[str] | None:
    """Parse ``--hyperlink-scheme-allowlist`` CSV into ``frozenset[str] | None``.

    Special cases:
      - ``"*"``  → ``None`` sentinel (allow all schemes; consumed by
        ``inline._render_hyperlink``).
      - ``""``   → ``frozenset()`` (block all hyperlinks → plain text).
      - Otherwise: split on ``","``, strip whitespace, lower-case each
        token → ``frozenset``.
    """
    raw: str = getattr(args, "hyperlink_scheme_allowlist", "http,https,mailto")
    if raw == "*":
        return None
    if raw == "":
        return frozenset()
    return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())


def _coerce_header_rows(value: Any) -> int | str:
    """Coerce ``args.header_rows`` to ``int | "auto" | "smart"``.

    ``_header_rows_type`` in ``cli.py`` already converts the raw string
    to ``int | "auto" | "smart"`` at parse time. This helper handles
    the case where the value arrives as an ``int`` (already coerced by
    argparse), as one of the two string literals, or — defensively — as
    a raw numeric string.

    Raises:
        argparse.ArgumentTypeError: on an unrecognised non-numeric string.
    """
    if isinstance(value, int):
        return value
    if value in ("auto", "smart"):
        return value
    # Defensive: raw numeric string (should not happen after argparse).
    try:
        n = int(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            f"--header-rows must be 'auto', 'smart', or an integer >= 1; "
            f"got {value!r}"
        ) from exc
    return n


def _gap_fallback_if_empty(
    regions: list[TableRegion],
    sheet: SheetInfo,
    reader: WorkbookReader,
    args: Any,
    library_mode: TableDetectMode,
) -> tuple[list[TableRegion], bool]:
    """R8.f: fall back to whole-sheet when gap-filter yields zero regions.

    If ``--no-table-autodetect`` is set AND ``regions`` is empty (the
    post-call filter dropped all regions), re-call
    ``reader.detect_tables(sheet.name, mode="whole")`` to emit the sheet
    as a single table. Returns ``(regions, fell_back)``; ``fell_back``
    is ``True`` iff the fallback path was taken.
    """
    if getattr(args, "no_table_autodetect", False) and not regions:
        fallback = reader.detect_tables(sheet.name, mode="whole")
        return (fallback, True)
    return (regions, False)


def _extract_hyperlinks_for_region(
    reader: WorkbookReader,
    region: TableRegion,
    *,
    scheme_allowlist: frozenset[str] | None = None,
) -> dict[tuple[int, int], str]:
    """Parallel pass: extract ``(row_offset, col_offset) -> href`` for the region.

    **Path C′ — mirrors xlsx-8 ``_extract_hyperlinks_for_region``** at
    [xlsx2csv2json/dispatch.py:102-176](../xlsx2csv2json/dispatch.py).
    Needed because ``xlsx_read.read_table(include_hyperlinks=True)``
    REPLACES the cell value with the URL — fine for "tell me the URL"
    but not what xlsx-9 needs for ``[click here](https://...)`` (GFM)
    and ``<a href="...">click here</a>`` (HTML) emission. We instead
    call ``read_table(include_hyperlinks=False)`` so display text
    survives, then this helper does a parallel openpyxl iteration to
    pull ``cell.hyperlink.target``.

    Returns a mapping keyed by ``(0-based row within the region,
    0-based column within the region)``. Cells without a hyperlink are
    absent from the map.

    **R10a / D-A15 / Sec-MED-2 — Hyperlink scheme allowlist**: if
    ``scheme_allowlist`` is given, each cell's hyperlink target is
    parsed via ``urllib.parse.urlsplit`` and the lower-cased scheme is
    checked against the allowlist; entries whose scheme is NOT in the
    allowlist are **dropped from the map entirely** (blocked-scheme
    cells then traverse the no-hyperlink emit branch unchanged — plain
    text). One ``warnings.warn`` line per distinct blocked scheme
    (deduped) is emitted before the function returns; the shim's outer
    ``warnings.catch_warnings(record=True)`` block in ``cli.main`` picks
    them up and routes to stderr. ``scheme_allowlist=None`` (sentinel
    for ``--hyperlink-scheme-allowlist='*'``) disables filtering;
    ``scheme_allowlist=frozenset()`` (empty allowlist from
    ``--hyperlink-scheme-allowlist=""``) blocks all schemes.

    **Closed-API exception (D-A5 honest scope)**: this is the one
    legitimate place in ``xlsx2md/`` where we cross the fence to
    ``reader._wb`` (the underlying openpyxl ``Workbook``). xlsx_read
    exposes no public worksheet handle by design; hyperlinks need
    cell-object access, not just values. Pattern + rationale inherited
    verbatim from xlsx-8.
    """
    result: dict[tuple[int, int], str] = {}
    blocked_by_scheme: dict[str, int] = {}
    wb = getattr(reader, "_wb", None)
    if wb is None:
        return result
    ws = wb[region.sheet]
    if scheme_allowlist is not None:
        from urllib.parse import urlsplit

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
            if not target:
                continue
            target_str = str(target)
            if scheme_allowlist is not None:
                scheme = urlsplit(target_str).scheme.lower()
                # Empty scheme → treat as http (relative URL convention,
                # mirrors inline._render_hyperlink R10a c).
                if not scheme:
                    scheme = "http"
                if scheme not in scheme_allowlist:
                    blocked_by_scheme[scheme] = (
                        blocked_by_scheme.get(scheme, 0) + 1
                    )
                    continue
            result[(row_offset, col_offset)] = target_str

    # R10a / Sec-MED-2: emit one warning per distinct blocked scheme.
    for scheme, count in blocked_by_scheme.items():
        warnings.warn(
            f"skipped {count} hyperlink(s) with disallowed "
            f"scheme {scheme!r}",
            UserWarning, stacklevel=2,
        )
    return result


def iter_table_payloads(
    reader: WorkbookReader,
    args: Any,
) -> Iterator[tuple[SheetInfo, TableRegion, TableData, dict[tuple[int, int], str]]]:
    """Yield ``(SheetInfo, TableRegion, TableData, hyperlinks_map)`` 4-tuples.

    This is the **only** call site of ``xlsx_read.WorkbookReader`` methods
    in ``xlsx2md/`` (D-A5 closed-API consumer, with the one documented
    exception in :func:`_extract_hyperlinks_for_region`). The emitters in
    ``emit_gfm`` / ``emit_html`` / ``emit_hybrid`` consume the 4-tuples
    produced here; they never call ``xlsx_read`` directly.

    Sheet selection:
      - ``args.sheet == "all"``: all visible sheets unless
        ``args.include_hidden`` is set (includes hidden + veryHidden).
      - ``args.sheet == NAME``: exactly that sheet; raises
        ``SheetNotFound`` if not present.

    Hyperlink handling (Path C′ / D5 / D-A15 / R10a):
      - ``read_table`` called with ``include_hyperlinks=False`` so
        display text survives in ``table_data.rows``.
      - Parallel pass via :func:`_extract_hyperlinks_for_region` pulls
        ``cell.hyperlink.target`` for the region; ``--hyperlink-scheme-allowlist``
        filter applied at the dispatch boundary (blocked schemes dropped
        from the map, emitted as plain text downstream).
      - Emit-side (``emit_gfm`` / ``emit_html``) looks up
        ``hyperlinks_map.get((r_offset, c_offset))`` per cell; non-None
        → ``[display_text](url)`` / ``<a href="url">display_text</a>``.

    Side-effects on ``args``:
      - ``args._hyperlink_allowlist`` is set (used by emit-side
        ``inline._render_hyperlink`` for the rare case of explicitly-
        passed hyperlinks bypassing dispatch, e.g. tests).
    """
    library_mode, post_filter = _detect_mode_for_args(args)
    all_sheets = reader.sheets()

    # --- Sheet selection ---
    if args.sheet == "all":
        if getattr(args, "include_hidden", False):
            selected = list(all_sheets)
        else:
            selected = [s for s in all_sheets if s.state == "visible"]
    else:
        matched = [s for s in all_sheets if s.name == args.sheet]
        if not matched:
            raise SheetNotFound(args.sheet)
        selected = matched

    # --- Hyperlink allowlist (attach to args for emit-side consumption) ---
    hyperlink_allowlist = _resolve_hyperlink_allowlist(args)
    args._hyperlink_allowlist = hyperlink_allowlist

    # --- read_only_mode: EFFECTIVE mode after open_workbook is consulted
    # (M3 fix). The previous `_read_only_mode_resolved` only reflected the
    # USER REQUEST (None/True/False from --memory-mode); when the library's
    # size-threshold heuristic auto-enabled read-only for a ≥ 100 MiB
    # workbook on the default `--memory-mode=auto`, the warning was
    # silently bypassed. cli.main() now sets `_read_only_effective` based
    # on `reader._read_only` post-open. Fall back to the resolved-request
    # value if the effective attr isn't set (test paths that bypass cli).
    read_only_effective = getattr(args, "_read_only_effective", None)
    if read_only_effective is None:
        read_only_effective = getattr(args, "_read_only_mode_resolved", None) is True
    read_only_mode = read_only_effective

    # --- header_rows coercion ---
    header_rows = _coerce_header_rows(args.header_rows)

    # Emit the streaming-hyperlink warning at most once per call.
    streaming_warning_emitted: bool = False

    for sheet in selected:
        regions = reader.detect_tables(
            sheet.name,
            mode=library_mode,
            gap_rows=getattr(args, "gap_rows", 2),
            gap_cols=getattr(args, "gap_cols", 1),
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
            # Path C′: read display text (include_hyperlinks=False),
            # then parallel pass for href map.
            table_data = reader.read_table(
                region,
                header_rows=header_rows,
                merge_policy="anchor-only",   # D2 hybrid baseline
                include_hyperlinks=False,      # display text survives
                include_formulas=getattr(args, "include_formulas", False),
                datetime_format=getattr(args, "datetime_format", "ISO"),
            )
            # H1 fix: use SHIFTED region (`table_data.region`) — `read_table`
            # may shift `region.top_row` when `header_rows="smart"` detects a
            # metadata banner (see xlsx_read/_types.py:174-188). The hyperlinks
            # map keys must be offsets within the SHIFTED region so the emit-
            # side `header_band = total_rows - len(rows)` math aligns.
            hyperlinks_map = _extract_hyperlinks_for_region(
                reader, table_data.region,
                scheme_allowlist=hyperlink_allowlist,
            )
            # R20a × D5 interaction: hyperlinks are unreliable in openpyxl
            # ReadOnlyCell (streaming mode). Warn once per iter call.
            if read_only_mode is True and not streaming_warning_emitted:
                warnings.warn(
                    "hyperlinks unreliable in streaming mode; "
                    "pass --memory-mode=full or extract on a "
                    "smaller workbook",
                    UserWarning,
                    stacklevel=2,
                )
                streaming_warning_emitted = True
            yield (sheet, region, table_data, hyperlinks_map)
