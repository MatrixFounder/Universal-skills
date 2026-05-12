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
    )

    text = json.dumps(
        shape,
        ensure_ascii=False, indent=2, sort_keys=False,
        default=_json_default,
    )

    if output is None:
        sys.stdout.write(text + "\n")
    else:
        output.write_text(text + "\n", encoding="utf-8")
    return 0


def _shape_for_payloads(
    payloads_list: list[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    sheet_selector: str,
    tables_mode: str,
    header_flatten_style: str,
    include_hyperlinks: bool,
) -> Any:
    """Pure function — build the JSON shape from payloads.

    Empty payloads → ``[]`` (matches xlsx-2 "empty workbook" convention).
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
            return {
                _region_key(r): _rows_to_dicts(td, hl, header_flatten_style, include_hyperlinks)
                for r, td, hl in regions
            }
        # Rule 1: single-sheet, single-region → flat array.
        r, td, hl = regions[0]
        return _rows_to_dicts(td, hl, header_flatten_style, include_hyperlinks)

    # Multi-sheet — Rule 2 or Rule 3 (mixed per sheet).
    out: dict[str, Any] = {}
    for sheet_name, regions in by_sheet.items():
        if is_multi_region[sheet_name]:
            # Rule 3 per-sheet: {"tables": {Name: [...], ...}}.
            out[sheet_name] = {
                "tables": {
                    _region_key(r): _rows_to_dicts(
                        td, hl, header_flatten_style, include_hyperlinks
                    )
                    for r, td, hl in regions
                }
            }
        else:
            # Rule 2 per-sheet: flat [...]
            r, td, hl = regions[0]
            out[sheet_name] = _rows_to_dicts(
                td, hl, header_flatten_style, include_hyperlinks
            )
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
) -> list[Any]:
    """Convert ``TableData`` rows to a list of dicts (or list of {key,value}
    pairs in ``"array"`` style).

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
            headers, rows, hl_map, header_band, include_hyperlinks
        )
    return _rows_to_string_style(
        headers, rows, hl_map, header_band, include_hyperlinks
    )


def _rows_to_string_style(
    headers: list[str],
    rows: list[list[Any]],
    hl_map: dict[tuple[int, int], str] | None,
    header_band: int,
    include_hyperlinks: bool,
) -> list[dict[str, Any]]:
    """Default JSON shape: ``[{header: value, ...}, ...]``."""
    out: list[dict[str, Any]] = []
    for r_idx, row in enumerate(rows):
        d: dict[str, Any] = {}
        for c_idx, header in enumerate(headers):
            value = row[c_idx] if c_idx < len(row) else None
            if include_hyperlinks and hl_map is not None:
                # Position in the region is (header_band + r_idx, c_idx).
                href = hl_map.get((header_band + r_idx, c_idx))
                if href is not None:
                    d[header] = {"value": value, "href": href}
                    continue
            d[header] = value
        out.append(d)
    return out


def _rows_to_array_style(
    headers: list[str],
    rows: list[list[Any]],
    hl_map: dict[tuple[int, int], str] | None,
    header_band: int,
    include_hyperlinks: bool,
) -> list[list[dict[str, Any]]]:
    """Array-style: ``[ [ {"key": [parts...], "value": v}, ... ], ... ]``.

    Keys are split on the U+203A separator to expose multi-row header
    structure. Single-row headers produce one-element ``key`` arrays.
    """
    out: list[list[dict[str, Any]]] = []
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
        out.append(cells)
    return out
