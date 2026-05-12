"""F4 — CSV emitter (010-06).

Single-region: write to ``output`` or stdout via
``csv.writer(quoting=QUOTE_MINIMAL, lineterminator="\\n")``.

Multi-region: each region lands at ``<output-dir>/<sheet>/<table>.csv``
(D5 — subdirectory schema; sheet names with ``__`` do NOT clash with
a non-existent ``__`` separator).

Hyperlink cells (when ``include_hyperlinks=True``) emit as
``[text](url)`` markdown-link-as-text (R10.c, R10.d — NEVER
``=HYPERLINK()`` formula).

Path-traversal guard (D-A8): every computed write-path passes
``Path.resolve().is_relative_to(output_dir.resolve())`` before the
file is opened for write. A sheet/table name that survived
:func:`dispatch._validate_sheet_path_components` may still result in
a target that escapes the output-dir if a symlink under the dir
points outside — the guard catches that case.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Iterator

from .exceptions import (
    MultiTableRequiresOutputDir,
    OutputPathTraversal,
)


def emit_csv(
    payloads: Iterator[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    output: Path | None,
    output_dir: Path | None,
    sheet_selector: str,  # noqa: ARG001  -- reserved for future selectors
    tables_mode: str,  # noqa: ARG001  -- reserved
    include_hyperlinks: bool,
    datetime_format: str,  # noqa: ARG001  -- library handles datetime emit
) -> int:
    """Drive single-file or multi-file CSV emission.

    Returns ``0`` on success.

    Raises:
        MultiTableRequiresOutputDir: defensive — ``dispatch`` should
            have raised first. Catches the case where a caller bypasses
            dispatch and produces a > 1-region payload list with no
            output dir.
        OutputPathTraversal: a computed per-region path escapes
            ``output_dir`` after canonical resolve.
    """
    payloads_list = list(payloads)
    n_regions = len(payloads_list)

    if n_regions == 0:
        # Empty workbook — no output; mirror xlsx-2 convention.
        return 0

    if n_regions == 1 and output_dir is None:
        _emit_single_region(
            payloads_list[0],
            output=output,
            include_hyperlinks=include_hyperlinks,
        )
        return 0

    if output_dir is None:
        # n_regions > 1 with no output-dir is a defensive bug surface;
        # dispatch already raises in this case but we re-raise here so
        # direct callers of emit_csv (tests / Python helpers) see the
        # same envelope.
        raise MultiTableRequiresOutputDir(
            f"CSV emit received {n_regions} regions with no --output-dir."
        )

    _emit_multi_region(
        payloads_list,
        output_dir=output_dir,
        include_hyperlinks=include_hyperlinks,
    )
    return 0


def _emit_single_region(
    payload: tuple[str, Any, Any, dict[tuple[int, int], str] | None],
    *,
    output: Path | None,
    include_hyperlinks: bool,
) -> None:
    """Write one region to ``output`` (or stdout if None)."""
    _, _, table_data, hl_map = payload
    if output is None:
        _write_region_csv(
            sys.stdout, table_data, hl_map=hl_map,
            include_hyperlinks=include_hyperlinks,
        )
    else:
        with output.open("w", encoding="utf-8", newline="") as fp:
            _write_region_csv(
                fp, table_data, hl_map=hl_map,
                include_hyperlinks=include_hyperlinks,
            )


def _emit_multi_region(
    payloads_list: list[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    output_dir: Path,
    include_hyperlinks: bool,
) -> None:
    """Write each region to ``<output_dir>/<sheet>/<table>.csv``.

    Path-traversal guard (D-A8) runs per-region before open.
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # M2 (vdd-multi): de-duplicate colliding `<sheet>/<region>.csv` targets
    # within this emit pass. Two regions with the same (sheet, region_name)
    # would otherwise silently overwrite each other — most commonly with
    # `gap_detect` fallback names (`Table-1`, `Table-2`, ...) accidentally
    # colliding with a ListObject named `Table-1`. We track resolved
    # write-paths in a set and append a numeric suffix on collision.
    written: set[Path] = set()

    for i, (sheet_name, region, table_data, hl_map) in enumerate(payloads_list):
        region_name = region.name or f"Table-{i + 1}"
        target = (output_dir / sheet_name / f"{region_name}.csv").resolve()
        if not target.is_relative_to(output_dir):
            raise OutputPathTraversal(
                f"Computed write-path escapes --output-dir: {target}"
            )
        # Collision suffix loop (bounded by region count).
        suffix = 2
        while target in written:
            target = (
                output_dir / sheet_name / f"{region_name}__{suffix}.csv"
            ).resolve()
            if not target.is_relative_to(output_dir):
                raise OutputPathTraversal(
                    f"Computed write-path escapes --output-dir: {target}"
                )
            suffix += 1
        written.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as fp:
            _write_region_csv(
                fp, table_data, hl_map=hl_map,
                include_hyperlinks=include_hyperlinks,
            )


def _write_region_csv(
    fp: Any,
    table_data: Any,
    *,
    hl_map: dict[tuple[int, int], str] | None,
    include_hyperlinks: bool,
) -> None:
    """Common writer body — emit header row + data rows."""
    writer = csv.writer(fp, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    headers = list(table_data.headers)
    writer.writerow(headers)

    region = table_data.region
    total_rows = region.bottom_row - region.top_row + 1
    header_band = total_rows - len(table_data.rows)

    for r_idx, row in enumerate(table_data.rows):
        out_row: list[Any] = []
        for c_idx in range(len(headers)):
            value = row[c_idx] if c_idx < len(row) else None
            if include_hyperlinks and hl_map is not None:
                href = hl_map.get((header_band + r_idx, c_idx))
                if href is not None:
                    out_row.append(_format_hyperlink_csv(value, href))
                    continue
            out_row.append(value)
        writer.writerow(out_row)


def _format_hyperlink_csv(value: Any, href: str) -> str:
    """Format a hyperlink cell as a markdown link ``[text](url)``.

    Per R10.c, R10.d (D7): NEVER emit ``=HYPERLINK("url","text")``
    formula syntax — Excel reopen would interpret the leading ``=`` as
    a formula trigger.

    Edge: empty ``value`` → ``[](url)`` (valid markdown — UC-06 A2).
    Non-string values are str()-coerced for the text part.
    """
    text = "" if value is None else str(value)
    return f"[{text}]({href})"
