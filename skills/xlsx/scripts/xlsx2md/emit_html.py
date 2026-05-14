"""F5 — HTML ``<table>`` emitter. LIVE since task 012-05.

HTML ``<table>`` serialisation for a single ``TableData``.

Key emit rules (locked at Architecture phase):

- Text content → ``html.escape(text)`` (ARCH D-A9, stdlib only, no lxml).
- URL in href → ``html.escape(url, quote=True)`` (ARCH D-A9).
- ``\\n`` in cell text → ``<br>`` (D-A12).
- Formula strings → ``data-formula="=..."`` attribute when
  ``include_formulas=True`` (R12.b).
- Multi-row ``<thead>``: `` › ``-split reconstruction from flat
  ``TableData.headers`` (D12 / D-A11 algorithm in :mod:`headers`).
- ``headerRowCount=0`` (synthetic headers): synthetic ``<thead>`` with
  ``col_1..col_N`` ``<th>`` cells emitted (D13); warning always surfaced.

Honest-scope deferrals
-----------------------
- **Body-cell colspan/rowspan**: ``TableData`` has no merge-span
  attribute (xlsx-10.A frozen API). Accurate body ``colspan``/``rowspan``
  requires a ``reader.merges_in_region(...)`` call (not in xlsx_read
  public API). Deferred to v2 / xlsx-10.B. Body cells always emit
  ``<td>`` without colspan/rowspan attributes for now.
- **Formula extraction via data-formula attr**: ``data-formula`` is
  wired but the ``formula`` value must be passed in via a side-channel
  (e.g. a test mock); ``TableData`` does not carry formula strings in
  the current xlsx_read API when ``include_formulas=True`` is passed
  to ``read_table`` — it only affects cached-value resolution. Full
  formula-string extraction is deferred to 012-08 / v2.

NOTE: ``lxml`` is NOT imported here. xlsx-9 emits HTML, does not parse it
(D-A4). stdlib ``html.escape`` is the only escaper needed.
"""
from __future__ import annotations

import html
from typing import IO, Any

import openpyxl.utils as _xl_utils  # type: ignore[import-untyped]

from . import inline
from .headers import compute_colspan_spans, split_headers_to_rows, validate_header_depth_uniformity


def emit_html_table(
    table_data: object,
    out: IO[str],
    *,
    include_formulas: bool = False,
    hyperlink_allowlist: frozenset[str] | None,
    hyperlinks_map: dict[tuple[int, int], str] | None = None,
    cell_addr_prefix: str = "",
) -> None:
    """Write ``<table>``, ``<thead>``, ``<tbody>`` blocks to ``out``.

    Parameters
    ----------
    table_data:
        A ``TableData`` instance (``region``, ``headers``, ``rows``).
        Display text lives in ``rows`` (dispatch calls ``read_table``
        with ``include_hyperlinks=False`` so the URL doesn't replace it).
    out:
        Writable text stream.
    include_formulas:
        If ``True``, emit ``data-formula`` attribute when a formula is
        supplied via the side-channel (see honest-scope note above).
    hyperlink_allowlist:
        ``None`` → allow all; ``frozenset()`` → block all; otherwise
        a frozenset of lowercase scheme strings. Forwarded to
        :func:`inline.render_cell_value` for hyperlink cells.
    hyperlinks_map:
        ``(r_offset, c_offset) -> href`` mapping populated by
        :func:`xlsx2md.dispatch._extract_hyperlinks_for_region`
        (Path C′). ``None`` or empty ``{}`` → no hyperlinks rendered.
        Keys are 0-based offsets within the full region (header band
        INCLUDED — row 0 is the first region row).
    cell_addr_prefix:
        Prefix for cell-address strings in warning messages (e.g. sheet
        name + ``"!"``). Empty string by default.
    """
    headers = list(table_data.headers)  # type: ignore[attr-defined]
    region = table_data.region  # type: ignore[attr-defined]
    rows = list(table_data.rows)  # type: ignore[attr-defined]

    # header_band: number of rows in the region before the body rows.
    # Same calculation as emit_gfm: total region rows minus body rows.
    total_rows = (
        getattr(region, "bottom_row", 0) - getattr(region, "top_row", 0) + 1
    )
    header_band = max(0, total_rows - len(rows))

    hl_map: dict[tuple[int, int], str] = hyperlinks_map or {}

    out.write("<table>\n")
    _emit_thead(headers, region, out)
    _emit_tbody(
        rows,
        region,
        out,
        include_formulas=include_formulas,
        hyperlinks_map=hl_map,
        header_band=header_band,
        allowed_schemes=hyperlink_allowlist,
        cell_addr_prefix=cell_addr_prefix,
    )
    out.write("</table>\n")


def _emit_thead(
    headers: list[str],
    region: object,
    out: IO[str],
) -> None:
    """Reconstruct multi-row ``<tr>`` rows inside ``<thead>``.

    Uses the D-A11 algorithm: split each header string on `` › ``
    separators and group into N rows (N = max separator count + 1);
    then compute ``colspan`` spans for row 0..N-2.

    D13 lock: when ``region.source == "listobject"`` and
    ``region.listobject_header_row_count == 0``, headers will be
    ``["col_1", "col_2", ...]`` (synthetic). The ``<thead>`` block
    still emits — a ``<table>`` without ``<thead>`` is ambiguous for
    downstream parsers. No special branch needed; the standard
    single-row path handles it.

    Parameters
    ----------
    headers:
        Flat header list from ``TableData.headers``.
    region:
        ``TableRegion`` (currently unused; reserved for future context).
    out:
        Writable text stream.
    """
    if not headers:
        return  # Defensive: should not happen after xlsx_read resolution.

    depth = validate_header_depth_uniformity(headers)

    out.write("<thead>\n")
    if depth == 1:
        out.write("<tr>")
        for h in headers:
            out.write(f"<th>{html.escape(h, quote=False)}</th>")
        out.write("</tr>\n")
    else:
        header_rows = split_headers_to_rows(headers)
        spans = compute_colspan_spans(header_rows)
        for row_idx, row in enumerate(header_rows):
            out.write("<tr>")
            for col_idx, text in enumerate(row):
                colspan = spans[row_idx][col_idx]
                if colspan == 0:
                    continue  # Suppressed: covered by earlier <th> with colspan > 1.
                attr = f' colspan="{colspan}"' if colspan > 1 else ""
                out.write(f"<th{attr}>{html.escape(text, quote=False)}</th>")
            out.write("</tr>\n")
    out.write("</thead>\n")


def _emit_tbody(
    rows: list[list[Any]],
    region: object,
    out: IO[str],
    *,
    include_formulas: bool,
    hyperlinks_map: dict[tuple[int, int], str],
    header_band: int,
    allowed_schemes: frozenset[str] | None,
    cell_addr_prefix: str = "",
) -> None:
    """Emit ``<tbody>`` with ``<tr>/<td>`` for each body row.

    Body-cell colspan/rowspan: DEFERRED to v2 / xlsx-10.B (needs
    ``reader.merges_in_region()`` from xlsx_read public API). All body
    cells emit plain ``<td>`` without colspan/rowspan attributes.

    Parameters
    ----------
    rows:
        Body data rows from ``TableData.rows``.
    region:
        ``TableRegion`` for the table; used for cell-address computation.
    out:
        Writable text stream.
    include_formulas:
        If ``True``, emit ``data-formula`` attr when formula side-channel
        provides a value.
    hyperlinks_map:
        ``(region_r_idx, c_idx) -> href`` mapping. Keys include the
        header band offset (row 0 = first region row).
    header_band:
        Number of header rows in the region; used to offset ``r_idx``
        for ``hyperlinks_map`` lookup so it matches the region-relative
        key.
    allowed_schemes:
        Forwarded to :func:`inline.render_cell_value`.
    cell_addr_prefix:
        Prefix for cell-address strings in warnings.
    """
    top_row = getattr(region, "top_row", 1) if region is not None else 1
    left_col = getattr(region, "left_col", 1) if region is not None else 1

    out.write("<tbody>\n")
    for r_idx, row in enumerate(rows):
        out.write("<tr>")
        abs_row = top_row + header_band + r_idx

        # M6 fix: precompute lazy cell_addr factory; only invoked when
        # a hyperlink is present (warning-path only). See emit_gfm.py
        # for the rationale — saves O(cells) get_column_letter +
        # f-string allocations per workbook.
        def _make_cell_addr(c_idx: int, _abs: int = abs_row) -> str | None:
            try:
                col_letter = _xl_utils.get_column_letter(left_col + c_idx)
                return f"{cell_addr_prefix}{col_letter}{_abs}"
            except Exception:  # noqa: BLE001
                return None

        for c_idx, value in enumerate(row):
            # Region-relative key: add header_band so lookup matches dispatch map.
            hl_href = hyperlinks_map.get((header_band + r_idx, c_idx))
            cell_addr = _make_cell_addr(c_idx) if hl_href is not None else None

            cell_text = inline.render_cell_value(
                value,
                mode="html",
                hyperlink_href=hl_href,
                allowed_schemes=allowed_schemes,
                cell_addr=cell_addr,
            )

            # M1 fix: detect formula strings surfaced by xlsx_read when
            # the workbook was opened with `keep_formulas=True` (which
            # cli.py now does when `args.include_formulas` is set). In
            # that mode, formula cells carry the formula string (e.g.
            # ``"=A1+B1"``) as their value. Emit as ``data-formula``
            # attribute; the cell visible content becomes empty
            # (data_only=False discards the cached value — TASK §1.4(g)
            # honest-scope: "stale" formula cell emits empty + stale-
            # cache class). Without ``--include-formulas``, the workbook
            # is opened with ``data_only=True`` and cell values are the
            # cached scalar — no formula string survives, so this branch
            # never fires (`isinstance(value, str) and value.startswith`
            # short-circuits cleanly).
            formula: str | None = None
            if (
                include_formulas
                and isinstance(value, str)
                and value.startswith("=")
            ):
                formula = value
                # M-NEW-1 fix (iter 2): preserve hyperlink AND formula
                # when a cell has both. Previously `cell_text = ""`
                # blindly overwrote the `<a href>` produced by
                # render_cell_value above — silently dropping the link.
                # Now: if a hyperlink is attached, keep the rendered
                # link (display text = formula string, wrapped in <a>);
                # otherwise the cell content is blank (stale-cache
                # honest scope §1.4(g)). Either way, the `data-formula`
                # attribute is emitted on the <td>.
                if hl_href is None:
                    cell_text = ""
                # else: `cell_text` already contains
                # `<a href="...">html.escape(formula)</a>` from
                # render_cell_value (the formula string was used as
                # display text in the hyperlink rendering).
            attrs = _build_td_attrs(
                value=value if formula is None else None,
                formula=formula,
                include_formulas=include_formulas,
            )
            out.write(f"<td{attrs}>{cell_text}</td>")
        out.write("</tr>\n")
    out.write("</tbody>\n")


def _build_td_attrs(
    *,
    value: Any,
    formula: str | None,
    include_formulas: bool,
    colspan: int = 1,
    rowspan: int = 1,
) -> str:
    """Build the attribute string for a ``<td>`` element.

    Returns a string like ``' data-formula="=A1+B1"'`` or ``''``.
    The string starts with a space when non-empty (ready for
    ``f"<td{attrs}>"``)

    Parameters
    ----------
    value:
        Cell value; ``None`` indicates stale formula (no cached value).
    formula:
        Formula string from side-channel, or ``None``.
    include_formulas:
        If ``True``, emit ``data-formula`` attr (when ``formula`` given)
        and ``class="stale-cache"`` (when formula given + value is None).
    colspan, rowspan:
        Merge spans (deferred; always 1 for this bead).
    """
    parts: list[str] = []
    if colspan > 1:
        parts.append(f'colspan="{colspan}"')
    if rowspan > 1:
        parts.append(f'rowspan="{rowspan}"')
    if include_formulas and formula is not None:
        parts.append(f'data-formula="{html.escape(formula, quote=True)}"')
        if value is None:
            parts.append('class="stale-cache"')
    if not parts:
        return ""
    return " " + " ".join(parts)


def _format_cell_html(
    value: Any,
    *,
    formula: str | None = None,
    include_formulas: bool = False,
    hyperlink_href: str | None = None,
    allowed_schemes: frozenset[str] | None = frozenset({"http", "https", "mailto"}),
    is_anchor: bool = False,
    colspan: int = 1,
    rowspan: int = 1,
) -> str:
    """Format a single cell value as a complete ``<td>`` HTML fragment.

    Convenience wrapper consumed by unit tests for granular ``<td>``
    shape assertions.

    Parameters
    ----------
    value:
        Raw cell value (``None`` → ``""``).
    formula:
        Formula string for ``data-formula`` attr (side-channel).
    include_formulas:
        If ``True``, include ``data-formula`` / ``stale-cache`` attrs.
    hyperlink_href:
        If not ``None``, render ``value`` as ``<a href="...">text</a>``.
    allowed_schemes:
        Scheme allowlist forwarded to :func:`inline.render_cell_value`.
    is_anchor:
        Ignored for now (future merge-anchor marker). Reserved.
    colspan, rowspan:
        Merge spans (deferred; currently only 1 is supported via body emit).
    """
    cell_text = inline.render_cell_value(
        value,
        mode="html",
        hyperlink_href=hyperlink_href,
        allowed_schemes=allowed_schemes,
        cell_addr=None,
    )
    attrs = _build_td_attrs(
        value=value,
        formula=formula,
        include_formulas=include_formulas,
        colspan=colspan,
        rowspan=rowspan,
    )
    return f"<td{attrs}>{cell_text}</td>"
