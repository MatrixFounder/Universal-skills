"""F4 — GFM pipe-table emitter. LIVE since task 012-04.

Pure GFM table serialisation for a single ``TableData``.

Implements:
- :func:`emit_gfm_table` — main entry: header + separator + body rows.
- :func:`_emit_header_row_gfm` — write ``| h1 | h2 | ... |`` + separator.
- :func:`_emit_body_row_gfm` — write one body row, routing each cell
  through :mod:`inline`.
- :func:`_apply_gfm_merge_policy` — ``duplicate`` / ``blank`` transforms
  for body-merge spans.

Hyperlinks (Path C′ from task 012-04)
--------------------------------------
``emit_gfm_table`` receives a ``hyperlinks_map`` parameter populated by
:func:`xlsx2md.dispatch._extract_hyperlinks_for_region` — a parallel
pass over the same region accessing the underlying openpyxl Workbook
to pull ``cell.hyperlink.target``. The map is keyed by ``(r_offset,
c_offset)`` within the region body. Display text comes through
``TableData.rows`` (dispatch calls ``read_table`` with
``include_hyperlinks=False`` so the URL does NOT replace the text).
Result: GFM emits ``[display text](https://...)`` with both pieces
preserved. Scheme-allowlist filter (R10a / D-A15) is applied at the
dispatch boundary — blocked-scheme cells are dropped from the map
and emit through the no-hyperlink branch as plain text.

Key emit rules (ARCH §2.1 F4, locked):
- ``|`` in cell text → ``\\|`` (ARCH D-A9, via :func:`inline._escape_pipe_gfm`).
- ``\\n`` in cell text → ``<br>`` (D-A12, via :func:`inline._newlines_to_br`).
- Hyperlinks → ``[display text](url)`` in GFM (D5 lock + Path C′,
  scheme-filtered at dispatch via
  :func:`xlsx2md.dispatch._extract_hyperlinks_for_region`).
- ``None`` → ``""`` (empty cell, via :func:`inline.render_cell_value`).
- Multi-row headers (`` › `` separator): flatten to single header row
  with `` › `` preserved (D6 lock); emit ``UserWarning`` for downstream
  logging.
- GFM merge policy (D3): ``duplicate`` / ``blank`` → lossy GFM + warning.
  ``fail`` raise-site lives in ``emit_hybrid.select_format`` (012-06).

Merge heuristic (honest scope, ARCH §10 A-A3 / task 012-04)
------------------------------------------------------------
``TableData`` does not carry a direct merge-spans attribute. The ``None``-
run heuristic is used instead: a contiguous run of ``None`` values after a
non-``None`` anchor in the same row is treated as a horizontal merge span.
A cell explicitly set to ``None`` in the source (not a merge child) is
indistinguishable from a merge child under this heuristic. This is a
documented limitation; ``duplicate``/``blank`` policy is opt-in and the
lossy transformation is clearly warranted by the warning emitted.

Vertical merge detection is deferred (012-04 honest scope); only horizontal
``None``-run detection is applied.

``GfmMergesRequirePolicy`` raise-site
--------------------------------------
Per task 012-04 scope, ``_apply_gfm_merge_policy`` handles ONLY the
``duplicate`` and ``blank`` transforms. The ``fail``-policy raise-site
is intentionally located in ``emit_hybrid.select_format`` (012-06), which
has access to the full merge-detection context before output is written.
"""
from __future__ import annotations

import warnings
from typing import IO, Any

from . import inline


def emit_gfm_table(
    table_data: object,
    out: IO[str],
    *,
    gfm_merge_policy: str = "fail",
    hyperlink_allowlist: frozenset[str] | None,
    hyperlinks_map: dict[tuple[int, int], str] | None = None,
    cell_addr_prefix: str = "",
) -> None:
    """Write header row + ``|---|`` separator + body rows to ``out``.

    Parameters
    ----------
    table_data:
        A ``TableData`` instance (``region``, ``headers``, ``rows``).
        Display text lives in ``rows`` (dispatch calls ``read_table``
        with ``include_hyperlinks=False`` so the URL doesn't replace it).
    out:
        Writable text stream.
    gfm_merge_policy:
        One of ``"fail"`` / ``"duplicate"`` / ``"blank"``. Only
        ``"duplicate"`` and ``"blank"`` are handled here; the ``"fail"``
        raise-site is in ``emit_hybrid.select_format`` (012-06).
    hyperlink_allowlist:
        ``None`` → allow all; ``frozenset()`` → block all; otherwise
        a frozenset of lowercase scheme strings. Forwarded to
        :func:`inline.render_cell_value` for cells lookup-hit in
        ``hyperlinks_map``. Note: dispatch-side already filters by
        allowlist; this is a defensive second-pass for cells passed
        in via tests or direct callers.
    hyperlinks_map:
        ``(r_offset, c_offset) -> href`` mapping populated by
        :func:`xlsx2md.dispatch._extract_hyperlinks_for_region`
        (Path C′ from task 012-04). ``None`` or empty ``{}`` →
        no cell will be rendered as a hyperlink. Keys are 0-based
        offsets within the BODY (header rows not counted).
    cell_addr_prefix:
        Prefix for cell-address strings in warning messages (e.g. sheet
        name + ``"!"``). Empty string by default.
    """
    headers = list(table_data.headers)  # type: ignore[attr-defined]
    region = table_data.region  # type: ignore[attr-defined]

    # Multi-row detection: if any header contains the " › " separator,
    # the header was flattened by xlsx_read. GFM cannot represent multi-
    # row headers — emit as-is (the › chars remain) + warn.
    is_multi_row = any(" › " in h for h in headers)
    if is_multi_row:
        table_name = getattr(region, "name", None) or getattr(region, "sheet", "?")
        warnings.warn(
            f"Table {table_name!r} has multi-row header; GFM output "
            f"flattened with ' › ' separator",
            UserWarning,
            stacklevel=2,
        )

    rows = list(table_data.rows)  # type: ignore[attr-defined]
    rows = _apply_gfm_merge_policy(rows, region, gfm_merge_policy)

    _emit_header_row_gfm(headers, out)
    hl_map: dict[tuple[int, int], str] = hyperlinks_map or {}

    # Header band offset for hyperlinks_map lookup. The dispatch helper
    # `_extract_hyperlinks_for_region` keys the map by region-relative
    # offsets (header band INCLUDED — row 0 is the first region row).
    # `r_idx` here is 0-indexed into the BODY rows, so we add the
    # header band length to map back to region-coords. Pattern lifted
    # from xlsx-8's `emit_csv._format_region_csv` (header_band offset).
    total_rows = (
        getattr(region, "bottom_row", 0) - getattr(region, "top_row", 0) + 1
    )
    header_band = max(0, total_rows - len(rows))

    for r_idx, row in enumerate(rows):
        _emit_body_row_gfm(
            row,
            r_idx,
            hl_map,
            headers,
            out=out,
            allowed_schemes=hyperlink_allowlist,
            cell_addr_prefix=cell_addr_prefix,
            region=region,
            header_band=header_band,
        )


def _emit_header_row_gfm(headers: list[str], out: IO[str]) -> None:
    """Write ``| h1 | h2 | ... |`` and ``|---|---|...|`` separator.

    Header strings are passed through :func:`inline._escape_pipe_gfm`
    to protect against literal ``|`` inside a flattened header string.
    """
    if not headers:
        return
    escaped = [inline._escape_pipe_gfm(h) for h in headers]
    out.write("| " + " | ".join(escaped) + " |\n")
    out.write("|" + "|".join("---" for _ in headers) + "|\n")


def _emit_body_row_gfm(
    row: list[Any],
    r_idx: int,
    hyperlinks_map: dict[tuple[int, int], str],
    headers: list[str],
    *,
    out: IO[str],
    allowed_schemes: frozenset[str] | None,
    cell_addr_prefix: str = "",
    region: object = None,
    header_band: int = 1,
) -> None:
    """Write one body data row as a GFM pipe-table row.

    Parameters
    ----------
    row:
        List of cell values (one per column).
    r_idx:
        0-based row index within the BODY (header rows not counted).
    hyperlinks_map:
        ``(region_r_idx, c_idx) -> href`` mapping populated by
        :func:`xlsx2md.dispatch._extract_hyperlinks_for_region`. Keys
        are region-relative (header band INCLUDED), so this function
        adds ``header_band`` to ``r_idx`` before the lookup.
    headers:
        Header list (used for column-count guard).
    out:
        Writable text stream.
    allowed_schemes:
        Forwarded to :func:`inline.render_cell_value`.
    cell_addr_prefix:
        Prefix for cell-address strings in warnings.
    region:
        ``TableRegion`` used to compute absolute row numbers for cell
        addresses in warnings.
    header_band:
        Number of header rows in the region; used to offset
        ``r_idx`` for the ``hyperlinks_map`` lookup so it matches the
        region-relative key used by dispatch. Default ``1`` (single-row
        header) for back-compat with callers that don't pass it.
    """
    import openpyxl.utils as _xl_utils  # type: ignore[import-untyped]

    # Absolute row number for warning messages: region.top_row +
    # header_band + r_idx (1-based row number in the workbook).
    top_row = getattr(region, "top_row", 1) if region is not None else 1
    abs_row = top_row + header_band + r_idx

    # M6 fix: precompute the per-row immutable parts; cell_addr is now
    # built ONLY for cells that have a hyperlink (the only path where
    # inline._render_hyperlink might emit a warning that consumes the
    # address). Previously this was O(cells) of get_column_letter +
    # f-string allocations per row, all discarded for cells without a
    # hyperlink (the 99.999% case). Saves ~3M unnecessary ops on a
    # 100K×30 workbook.
    left_col = (
        getattr(region, "left_col", 1) if region is not None else 1
    )

    def _make_cell_addr(c_idx: int) -> str | None:
        try:
            col_letter = _xl_utils.get_column_letter(left_col + c_idx)
            return f"{cell_addr_prefix}{col_letter}{abs_row}"
        except Exception:  # noqa: BLE001
            return None

    cell_strs: list[str] = []
    for c_idx, cell in enumerate(row):
        # Region-relative key: r_idx is body-relative, so add header_band.
        hl_href = hyperlinks_map.get((header_band + r_idx, c_idx))
        # Build cell address ONLY if a hyperlink exists (warning-path).
        cell_addr = _make_cell_addr(c_idx) if hl_href is not None else None

        cell_str = inline.render_cell_value(
            cell,
            mode="gfm",
            hyperlink_href=hl_href,
            allowed_schemes=allowed_schemes,
            cell_addr=cell_addr,
        )
        cell_strs.append(cell_str)

    out.write("| " + " | ".join(cell_strs) + " |\n")


def _apply_gfm_merge_policy(
    rows: list[list[Any]],
    region: object,
    policy: str,
) -> list[list[Any]]:
    """Resolve body-row ``None``-runs per ``duplicate`` / ``blank`` policy.

    **``fail`` policy**: NOT raised here. The raise-site is in
    ``emit_hybrid.select_format`` (012-06), which has access to the full
    merge-detection context before any output is written. This function
    passes through rows unchanged for ``policy == "fail"``.

    **``duplicate`` policy**: copy anchor value into each ``None`` cell
    that follows the anchor in the same row (horizontal-merge heuristic).
    Emits a ``UserWarning`` with the count of cells filled.

    **``blank`` policy**: leave ``None`` cells as ``""`` — already the
    behaviour of :func:`inline.render_cell_value` for ``None`` values;
    no structural change needed. Emits a ``UserWarning`` with the count
    of ``None`` cells found.

    Merge detection heuristic (honest scope):
    - A contiguous run of ``None`` values after a non-``None`` anchor in
      the same row is treated as a horizontal merge span.
    - A cell explicitly set to ``None`` in the source (not a merge child)
      is indistinguishable. This is a documented limitation (012-04).
    - Vertical merge detection is deferred.

    ``GfmMergesRequirePolicy`` raise-site is in ``emit_hybrid.select_format``
    (012-06) — not here (012-04 scope).

    Parameters
    ----------
    rows:
        Body data rows from ``TableData.rows``.
    region:
        ``TableRegion`` for the table (currently unused; reserved for
        future merge-span metadata).
    policy:
        One of ``"fail"`` / ``"duplicate"`` / ``"blank"``.
    """
    if policy == "fail" or policy not in ("duplicate", "blank"):
        return rows

    if policy == "duplicate":
        result: list[list[Any]] = []
        filled_count = 0
        for row in rows:
            new_row: list[Any] = []
            anchor: Any = None
            for cell in row:
                if cell is not None:
                    anchor = cell
                    new_row.append(cell)
                else:
                    # None cell after a non-None anchor → treat as merge child.
                    if anchor is not None:
                        new_row.append(anchor)
                        filled_count += 1
                    else:
                        new_row.append(None)
            result.append(new_row)
        if filled_count > 0:
            warnings.warn(
                f"GFM merge-policy 'duplicate': {filled_count} merge-child "
                f"cell(s) filled with anchor value (lossy)",
                UserWarning,
                stacklevel=2,
            )
        return result

    else:  # policy == "blank"
        blank_count = sum(
            1 for row in rows for cell in row if cell is None
        )
        if blank_count > 0:
            warnings.warn(
                f"GFM merge-policy 'blank': {blank_count} merge-child "
                f"cell(s) left empty (lossy)",
                UserWarning,
                stacklevel=2,
            )
        # No structural change needed; inline.render_cell_value renders
        # None as "" already.
        return rows


def _build_hyperlinks_map(
    table_data: object,
) -> dict[tuple[int, int], str]:
    """DEPRECATED (012-04 Path C′). Always returns ``{}``.

    Hyperlinks for the region are now extracted by
    :func:`xlsx2md.dispatch._extract_hyperlinks_for_region` (parallel
    pass over openpyxl cells via ``reader._wb``) and passed to
    :func:`emit_gfm_table` via the ``hyperlinks_map`` parameter.
    ``TableData`` itself carries no hyperlink data because dispatch
    calls ``read_table`` with ``include_hyperlinks=False`` (so display
    text survives in ``rows``).

    Retained as a no-op for any callers that construct a ``TableData``
    in isolation (e.g. unit tests) and want to invoke
    :func:`emit_gfm_table` without a pre-built map — they can either
    omit ``hyperlinks_map`` (defaults to ``None`` → ``{}``) or build
    one manually.
    """
    return {}
