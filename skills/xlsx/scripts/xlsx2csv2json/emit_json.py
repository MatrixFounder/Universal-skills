"""F3 — JSON emitter (010-05).

Builds the JSON shape per ``docs/ARCHITECTURE.md §4.1`` and writes it
to a file or stdout. The shape rules (R11 a–e) are:

1. **Single sheet, single region:** flat ``[{...}, ...]``.
2. **Multi-sheet, single region per sheet:** ``{"S1": [...], "S2": [...]}``.
3. **Multi-sheet, multi-region per sheet:** nested
   ``{"S1": {"tables": {"T1": [...], "T2": [...]}}, "S2": [...]}``.
4. **Single sheet, multi-region:** ``{"T1": [...], "T2": [...]}`` (no
   enclosing sheet key — backward-compat-style flat).

Hyperlink cells (when ``include_hyperlinks=True``) become a
``{"value": "<text>", "href": "<url>"}`` object replacing the raw
value.

Multi-row header rendering:

* ``header_flatten_style="string"`` (default): keys are the
  ``U+203A``-joined flat strings produced by xlsx_read.
* ``header_flatten_style="array"``: keys are split on ``U+203A`` and
  the row becomes a list of ``{"key": [...], "value": v}`` entries
  (locked v1 shape; documented in
  ``skills/xlsx/references/json-shapes.md`` by 010-07).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Iterator

_HEADER_SEPARATOR = " › "  # ' › '

# **xlsx-8a-08 (R10, D-A18)** — sentinel returned by
# `_shape_for_payloads` when the payload list is the R11.1
# single-sheet single-region case. `emit_json` checks for it and
# dispatches to `_stream_single_region_json` instead of building
# a full `shape` dict + serialising it. Closes PERF-HIGH-2 for
# the most common large-table case (peak RSS ≤ 200 MB on 3M
# cells vs 1-1.5 GB in v1). The sentinel is module-private; no
# external surface change.
_R11_1_STREAM_SENTINEL = object()


def _json_default(value: Any) -> Any:
    """Fallback serialiser for ``json.dumps``.

    Handles the value types xlsx_read can produce that the stdlib
    ``json.JSONEncoder`` does not natively support:

    * ``datetime.datetime`` / ``datetime.date`` / ``datetime.time`` —
      arises when ``--datetime-format raw`` is requested. We emit
      ISO-8601 via ``.isoformat()`` (a stable, well-defined string
      form). This is a soft contract: ``raw`` was advertised as
      "native Python datetime" but ``json.dumps`` can't represent
      that without coercion, so we coerce at the boundary rather than
      raise. Locked in TASK §1.4 honest scope (m).
    * ``datetime.timedelta`` — Excel "elapsed time" cells.

    Any other unserialisable type raises :class:`TypeError` per
    standard ``json`` behaviour.
    """
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable"
    )


def emit_json(
    payloads: Iterator[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    output: Path | None,
    sheet_selector: str,
    tables_mode: str,
    header_flatten_style: str,
    include_hyperlinks: bool,
    datetime_format: str,  # noqa: ARG001  -- reserved for future shape switches
    drop_empty_rows: bool = False,
) -> int:
    """Materialise payloads into JSON and write to ``output`` or stdout.

    Returns ``0`` on success.
    """
    payloads_list = list(payloads)
    shape = _shape_for_payloads(
        payloads_list,
        sheet_selector=sheet_selector,
        tables_mode=tables_mode,
        header_flatten_style=header_flatten_style,
        include_hyperlinks=include_hyperlinks,
        drop_empty_rows=drop_empty_rows,
    )

    # **xlsx-8a-08 (R10, D-A18)** — R11.1 single-sheet single-region
    # streaming dispatch. `_shape_for_payloads` returns the sentinel;
    # we route directly to `_stream_single_region_json` and bypass
    # the full-shape `json.dump(fp)` path. Peak RSS ≤ 200 MB on
    # 3M-cell payloads (vs ~1-1.5 GB v1).
    if shape is _R11_1_STREAM_SENTINEL:
        return _stream_single_region_json(
            payloads_list[0],
            output_path=output,
            header_flatten_style=header_flatten_style,
            include_hyperlinks=include_hyperlinks,
            drop_empty_rows=drop_empty_rows,
        )

    if output is None:
        # Stdout path: build the string then write. Pipe consumers
        # buffer the output downstream anyway, so the memory benefit
        # of streaming-to-pipe is downstream-dependent — keep the
        # existing newline contract here. (D-A17 asymmetric.)
        text = json.dumps(
            shape,
            ensure_ascii=False, indent=2, sort_keys=False,
            default=_json_default,
        )
        sys.stdout.write(text + "\n")
    else:
        # **xlsx-8a-07 (R9, PERF-HIGH-2 partial)**: stream-serialise
        # directly to the file descriptor. Drops the intermediate
        # `text = json.dumps(...)` string buffer (~300-500 MB on a
        # 3M-cell payload). The `shape` dict itself remains in RAM
        # for R11.2-4 shapes — full closure of PERF-HIGH-2 for
        # R11.1 single-region is the 011-08 streaming refactor.
        with output.open("w", encoding="utf-8") as fp:
            json.dump(
                shape, fp,
                ensure_ascii=False, indent=2, sort_keys=False,
                default=_json_default,
            )
            fp.write("\n")
    return 0


def _shape_for_payloads(
    payloads_list: list[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    sheet_selector: str,
    tables_mode: str,
    header_flatten_style: str,
    include_hyperlinks: bool,
    drop_empty_rows: bool = False,
) -> Any:
    """Pure function — build the JSON shape from payloads.

    Empty payloads → ``[]`` (matches xlsx-2 "empty workbook" convention).

    **xlsx-8a-08 (R10, D-A18)**: returns
    :data:`_R11_1_STREAM_SENTINEL` for the R11.1 single-sheet
    single-region case so the caller (:func:`emit_json`) can
    dispatch to the streaming helper instead of materialising the
    full row-list. R11.2-4 branches still build the dict-shape
    eagerly (the dict-of-arrays shapes cannot be RFC-8259-streamed
    without a non-canonical chunked-encoding contract).
    """
    if not payloads_list:
        return []

    # Group by sheet, preserving doc-order via dict insertion.
    by_sheet: dict[str, list[tuple[Any, Any, Any]]] = {}
    for sheet_name, region, table_data, hl_map in payloads_list:
        by_sheet.setdefault(sheet_name, []).append((region, table_data, hl_map))

    n_sheets = len(by_sheet)
    single_sheet = (n_sheets == 1)
    # Within each sheet, count regions.
    is_multi_region = {s: len(rs) > 1 for s, rs in by_sheet.items()}

    if single_sheet:
        only_sheet = next(iter(by_sheet))
        regions = by_sheet[only_sheet]
        if is_multi_region[only_sheet]:
            # Rule 4: single-sheet, multi-region → flat {Name: [...]}.
            # xlsx-8a-08: `_rows_to_dicts` returns an iterator; wrap
            # in `list(...)` so the dict comprehension produces a
            # JSON-serialisable shape (json.dump cannot serialise
            # generators).
            return {
                _region_key(r): list(_rows_to_dicts(
                    td, hl, header_flatten_style,
                    include_hyperlinks, drop_empty_rows,
                ))
                for r, td, hl in regions
            }
        # Rule 1: single-sheet, single-region → flat array.
        # **xlsx-8a-08 (R10, D-A18)** — route to streaming helper.
        # The caller (`emit_json`) detects the sentinel and calls
        # `_stream_single_region_json` directly with `payloads_list[0]`.
        return _R11_1_STREAM_SENTINEL

    # Multi-sheet — Rule 2 or Rule 3 (mixed per sheet).
    out: dict[str, Any] = {}
    for sheet_name, regions in by_sheet.items():
        if is_multi_region[sheet_name]:
            # Rule 3 per-sheet: {"tables": {Name: [...], ...}}.
            out[sheet_name] = {
                "tables": {
                    _region_key(r): list(_rows_to_dicts(
                        td, hl, header_flatten_style,
                        include_hyperlinks, drop_empty_rows,
                    ))
                    for r, td, hl in regions
                }
            }
        else:
            # Rule 2 per-sheet: flat [...]
            r, td, hl = regions[0]
            out[sheet_name] = list(_rows_to_dicts(
                td, hl, header_flatten_style,
                include_hyperlinks, drop_empty_rows,
            ))
    return out


def _region_key(region: Any) -> str:
    """Map a ``TableRegion`` to its dict-key.

    Uses ``region.name`` (set by library for listobject / named_range
    / gap_detect — gap_detect uses ``Table-N``).
    """
    return region.name or "Table-?"


def _rows_to_dicts(
    table_data: Any,
    hl_map: dict[tuple[int, int], str] | None,
    header_flatten_style: str,
    include_hyperlinks: bool,
    drop_empty_rows: bool = False,
) -> Iterator[Any]:
    """Convert ``TableData`` rows to an **iterator** of dicts (or
    list-of-{key,value}-pairs in ``"array"`` style).

    **xlsx-8a-08 (R10, D-A18)**: returns an iterator (was list).
    Callers in R11.2-4 branches must wrap with ``list(...)`` to
    materialise; the R11.1 single-region streaming path consumes
    the iterator one row at a time via :func:`_stream_single_region_json`.

    ``hl_map`` is keyed by ``(row_offset_within_region, col_offset_within_region)``
    where row 0 is the FIRST row of the region (which may be a header
    row). We translate to ``(data_row_index, col_offset)`` here.
    """
    headers = list(table_data.headers)
    rows = list(table_data.rows)

    # Header band length within the region is the number of rows
    # consumed before data rows started. For ListObject regions with
    # synthetic headers (headerRowCount=0), no rows were consumed; for
    # regular regions, the library consumed `len(headers_band)` rows.
    # The library does not expose this directly, but we can infer:
    # total region rows = bottom_row - top_row + 1; data rows = len(rows).
    # So header band = total - data_rows.
    region = table_data.region
    total_rows = region.bottom_row - region.top_row + 1
    header_band = total_rows - len(rows)

    if header_flatten_style == "array":
        return _rows_to_array_style(
            headers, rows, hl_map, header_band, include_hyperlinks,
            drop_empty_rows=drop_empty_rows,
        )
    return _rows_to_string_style(
        headers, rows, hl_map, header_band, include_hyperlinks,
        drop_empty_rows=drop_empty_rows,
    )


def _rows_to_string_style(
    headers: list[str],
    rows: list[list[Any]],
    hl_map: dict[tuple[int, int], str] | None,
    header_band: int,
    include_hyperlinks: bool,
    *,
    drop_empty_rows: bool = False,
) -> Iterator[dict[str, Any]]:
    """Default JSON shape: ``[{header: value, ...}, ...]``.

    **xlsx-8a-08 (R10, D-A18)**: now a generator. Callers wrap with
    ``list(...)`` at R11.2-4 sites; R11.1 streaming path consumes
    the generator one row at a time via
    :func:`_stream_single_region_json`.

    **vdd-adversarial follow-up (R27):** when two or more headers
    collide (e.g. a wide title merge sticky-fills the same value
    across N columns of a layout-heavy report), naive
    ``d[header] = value`` silently overwrites earlier columns —
    JSON dict-of-row data loss. On the masterdata fixture this
    dropped 5 of 7 columns per Timesheet row. The fix disambiguates
    duplicate headers by appending ``__2``, ``__3``, ... to the 2nd-
    and-later occurrences (mirrors the M2 vdd-multi precedent set
    by ``_emit_multi_region`` for colliding per-region file paths).
    """
    dedup_headers = _disambiguate_duplicate_headers(headers)

    for r_idx, row in enumerate(rows):
        d: dict[str, Any] = {}
        for c_idx, header in enumerate(dedup_headers):
            value = row[c_idx] if c_idx < len(row) else None
            if include_hyperlinks and hl_map is not None:
                # Position in the region is (header_band + r_idx, c_idx).
                href = hl_map.get((header_band + r_idx, c_idx))
                if href is not None:
                    d[header] = {"value": value, "href": href}
                    continue
            d[header] = value
        # **TASK 010 §11.7 R28 fix:** drop rows where every value is
        # None/"" — layout-heavy reports (gap rows, trailing empties
        # left by Excel) produce noisy mostly-null dict blobs by
        # default. Conservative: a row with even one non-null cell
        # is kept. Hyperlink-wrapper dicts (`{"value": V, "href":...}`)
        # count as non-empty (the href payload is real content).
        if drop_empty_rows and _is_dict_row_empty(d):
            continue
        yield d


def _is_dict_row_empty(d: dict[str, Any]) -> bool:
    """A row-dict is "empty" iff every value is None or empty string.

    Hyperlink-wrapper cells (`{"value": V, "href": ...}`) are treated
    as non-empty because the `href` payload is real content even
    when `value` is None / "".
    """
    for v in d.values():
        if isinstance(v, dict) and "href" in v:
            return False
        if v not in (None, ""):
            return False
    return True


def _disambiguate_duplicate_headers(headers: list[str]) -> list[str]:
    """Append ``__2``, ``__3``, ... to repeated entries in ``headers``.

    First occurrence keeps its bare name; subsequent occurrences get
    a numeric suffix. Cost: O(n_cols) once per region. Caller is
    responsible for using the returned list for ALL row-build passes
    so the suffix scheme is consistent across the emitted dataset.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for h in headers:
        count = seen.get(h, 0) + 1
        seen[h] = count
        out.append(h if count == 1 else f"{h}__{count}")
    return out


def _rows_to_array_style(
    headers: list[str],
    rows: list[list[Any]],
    hl_map: dict[tuple[int, int], str] | None,
    header_band: int,
    include_hyperlinks: bool,
    *,
    drop_empty_rows: bool = False,
) -> Iterator[list[dict[str, Any]]]:
    """Array-style: ``[ [ {"key": [parts...], "value": v}, ... ], ... ]``.

    **xlsx-8a-08 (R10, D-A18)**: now a generator.

    Keys are split on the U+203A separator to expose multi-row header
    structure. Single-row headers produce one-element ``key`` arrays.
    """
    for r_idx, row in enumerate(rows):
        cells: list[dict[str, Any]] = []
        for c_idx, header in enumerate(headers):
            key_parts = [p.strip() for p in header.split("›")]
            value = row[c_idx] if c_idx < len(row) else None
            cell: dict[str, Any] = {"key": key_parts, "value": value}
            if include_hyperlinks and hl_map is not None:
                href = hl_map.get((header_band + r_idx, c_idx))
                if href is not None:
                    cell["value"] = {"value": value, "href": href}
            cells.append(cell)
        if drop_empty_rows and _is_array_row_empty(cells):
            continue
        yield cells


def _is_array_row_empty(cells: list[dict[str, Any]]) -> bool:
    """Array-style row is empty iff every cell's `value` is None/"".

    Hyperlink-wrapper cells (`{"value": {"value": V, "href": ...}}`)
    are treated as non-empty (the `href` payload is real content).
    """
    for cell in cells:
        v = cell.get("value")
        if isinstance(v, dict) and "href" in v:
            return False
        if v not in (None, ""):
            return False
    return True


# ===========================================================================
# xlsx-8a-08 (R10, PERF-HIGH-2 closure for R11.1) — streaming helper
# ===========================================================================
def _stream_single_region_json(
    payload: tuple[str, Any, Any, dict[tuple[int, int], str] | None],
    *,
    output_path: Path | None,
    header_flatten_style: str,
    include_hyperlinks: bool,
    drop_empty_rows: bool = False,
) -> int:
    """Stream the R11.1 single-region JSON shape ``[{...},...]``
    row-by-row, closing PERF-HIGH-2 for the most common
    large-table case.

    **Byte-identical to v1** ``json.dumps(shape, indent=2) + "\\n"``
    on every R11.1 fixture, INCLUDING the empty-payload case
    (``"[]\\n"`` — per arch-review M3 fix). The empty-payload
    early-exit uses ``try/except StopIteration`` on the first
    ``next(rows_iter)`` call.

    For non-empty payloads, the indent strategy is:

    * Wrapper ``[`` and ``]`` at column 0 (depth-0).
    * Each row-dict re-indented to depth-1 via
      ``json.dumps(...indent=2).replace("\\n", "\\n  ")``.
    * Separator ``,\\n  `` between rows.
    * Final ``\\n]\\n`` closer.

    stdout path: writes to ``sys.stdout`` directly. The pipe
    consumer buffers the output downstream regardless; streaming
    preserves **producer-side** RSS bounds (Q-15-6). For
    ``output_path=None``, the helper writes to ``sys.stdout`` and
    does NOT close it.

    Returns ``0`` on success (matches the
    :func:`emit_json.emit_json` return contract).
    """
    # Only `table_data` and `hl_map` are needed for the row stream;
    # `sheet_name` / `region` are unpacked-and-discarded by design.
    _, _, table_data, hl_map = payload
    rows_iter = iter(_rows_to_dicts(
        table_data, hl_map, header_flatten_style,
        include_hyperlinks, drop_empty_rows,
    ))

    # Determine output sink.
    if output_path is None:
        fp = sys.stdout
        close_fp = False
    else:
        fp = output_path.open("w", encoding="utf-8")
        close_fp = True

    try:
        # **Empty-payload early-exit** (arch-review M3 fix):
        # without this guard, the helper would emit
        # ``"[\\n  \\n]\\n"`` (7 bytes) which breaks the
        # byte-identity invariant against v1
        # ``json.dumps([], indent=2) + "\\n" = "[]\\n"`` (3 bytes).
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
