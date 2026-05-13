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
    CollisionSuffixExhausted,
    MultiTableRequiresOutputDir,
    OutputPathTraversal,
)


# xlsx-8a-01 (R1) — Sec-HIGH-3 DoS mitigation. Bounded suffix loop
# in ``_emit_multi_region``: a crafted workbook with > 1000
# regions sharing the same ``(sheet, region_name)`` would force
# an unbounded O(N²) ``Path.resolve()`` + ``is_relative_to`` loop.
# Cap fires on the (cap+1)-th iteration per TASK D1 / ARCH D-A14.
# Policy-locked; no CLI / env-var override (TASK Q-15-1).
_MAX_COLLISION_SUFFIX: int = 1000

# xlsx-8a-04 (R4) — OWASP CSV-injection sentinels (D-A13).
# Cells whose stringified form begins with one of these are
# defanged by `_apply_formula_escape` under ``quote`` / ``strip``
# modes. Unicode lookalikes (`＝` U+FF1D, `＋` U+FF0B) are out
# of scope — D-A13 / TASK §6.3 honest-scope.
_FORMULA_SENTINELS: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def _apply_formula_escape(value: Any, mode: str) -> Any:
    """Defang CSV-injection-prone cell values per OWASP recipe.

    xlsx-8a-04 (R4, Sec-MED-1):

    - ``mode='off'``: passthrough (caller is expected to bypass
      this helper, but this branch is defence-in-depth).
    - ``mode='quote'``: prepend ``'`` if ``str(value)`` begins
      with a sentinel char. Excel renders the leading ``'`` as
      a literal-string escape (cell value displays as the
      original text, NOT as a formula).
    - ``mode='strip'``: replace the cell with ``""`` if
      sentinel-prefixed.

    Non-string and ``None`` values are returned unchanged.
    Numeric cells never start with a sentinel char and are
    handled by the early-return; that path keeps numeric
    round-trips byte-identical to xlsx-8 output under ``off``.
    """
    if mode == "off" or value is None:
        return value
    s = value if isinstance(value, str) else str(value)
    if not s or s[0] not in _FORMULA_SENTINELS:
        return value
    if mode == "quote":
        return "'" + s
    # mode == "strip"
    return ""


def emit_csv(
    payloads: Iterator[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    output: Path | None,
    output_dir: Path | None,
    sheet_selector: str,  # noqa: ARG001  -- reserved for future selectors
    tables_mode: str,  # noqa: ARG001  -- reserved
    include_hyperlinks: bool,
    datetime_format: str,  # noqa: ARG001  -- library handles datetime emit
    encoding: str = "utf-8",
    delimiter: str = ",",
    drop_empty_rows: bool = False,
    escape_formulas: str = "off",
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
            encoding=encoding,
            delimiter=delimiter,
            drop_empty_rows=drop_empty_rows,
            escape_formulas=escape_formulas,
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
        encoding=encoding,
        delimiter=delimiter,
        drop_empty_rows=drop_empty_rows,
        escape_formulas=escape_formulas,
    )
    return 0


def _emit_single_region(
    payload: tuple[str, Any, Any, dict[tuple[int, int], str] | None],
    *,
    output: Path | None,
    include_hyperlinks: bool,
    encoding: str = "utf-8",
    delimiter: str = ",",
    drop_empty_rows: bool = False,
    escape_formulas: str = "off",
) -> None:
    """Write one region to ``output`` (or stdout if None).

    ``encoding`` applies to file output only. stdout retains its
    process-wide encoding (sys.stdout configuration) because injecting
    a BOM into a pipe is almost always a bug at the consumer side.
    ``delimiter`` is the CSV field separator (default ``,``).
    """
    _, _, table_data, hl_map = payload
    if output is None:
        _write_region_csv(
            sys.stdout, table_data, hl_map=hl_map,
            include_hyperlinks=include_hyperlinks,
            delimiter=delimiter,
            drop_empty_rows=drop_empty_rows,
            escape_formulas=escape_formulas,
        )
    else:
        with output.open("w", encoding=encoding, newline="") as fp:
            _write_region_csv(
                fp, table_data, hl_map=hl_map,
                include_hyperlinks=include_hyperlinks,
                delimiter=delimiter,
                drop_empty_rows=drop_empty_rows,
                escape_formulas=escape_formulas,
            )


def _emit_multi_region(
    payloads_list: list[tuple[str, Any, Any, dict[tuple[int, int], str] | None]],
    *,
    output_dir: Path,
    include_hyperlinks: bool,
    encoding: str = "utf-8",
    delimiter: str = ",",
    drop_empty_rows: bool = False,
    escape_formulas: str = "off",
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
        # Collision suffix loop. Bounded at ``_MAX_COLLISION_SUFFIX``
        # (xlsx-8a-01 R1, Sec-HIGH-3): a crafted workbook with > 1000
        # regions sharing ``(sheet, region_name)`` would otherwise force
        # an unbounded O(N²) ``Path.resolve()`` + ``is_relative_to`` loop.
        # Cap fires on the (cap+1)-th iteration per D-A14 semantics.
        suffix = 2
        while target in written:
            if suffix > _MAX_COLLISION_SUFFIX:
                raise CollisionSuffixExhausted(
                    f"Region {region_name!r} on sheet {sheet_name!r}: "
                    f"{_MAX_COLLISION_SUFFIX} collision suffixes "
                    f"exhausted; refusing to keep iterating."
                )
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
        with target.open("w", encoding=encoding, newline="") as fp:
            _write_region_csv(
                fp, table_data, hl_map=hl_map,
                include_hyperlinks=include_hyperlinks,
                delimiter=delimiter,
                drop_empty_rows=drop_empty_rows,
                escape_formulas=escape_formulas,
            )


def _write_region_csv(
    fp: Any,
    table_data: Any,
    *,
    hl_map: dict[tuple[int, int], str] | None,
    include_hyperlinks: bool,
    delimiter: str = ",",
    drop_empty_rows: bool = False,
    escape_formulas: str = "off",
) -> None:
    """Common writer body — emit header row + data rows.

    xlsx-8a-04 (R4): ``escape_formulas`` applies the OWASP
    CSV-injection defang to both header and data cells (a header
    cell ``="Total"`` is identical in attack surface to a data
    cell — Q-15-3 locked decision). Default ``"off"`` is
    byte-identical to xlsx-8 output. Hyperlink-formatted cells
    (``[text](url)``) are NOT mutated because the leading ``[``
    is not a sentinel char.
    """
    writer = csv.writer(
        fp, quoting=csv.QUOTE_MINIMAL, lineterminator="\n", delimiter=delimiter,
    )
    headers = list(table_data.headers)
    if escape_formulas != "off":
        headers = [_apply_formula_escape(h, escape_formulas) for h in headers]
    writer.writerow(headers)

    region = table_data.region
    total_rows = region.bottom_row - region.top_row + 1
    header_band = total_rows - len(table_data.rows)

    for r_idx, row in enumerate(table_data.rows):
        out_row: list[Any] = []
        for c_idx in range(len(table_data.headers)):
            value = row[c_idx] if c_idx < len(row) else None
            if include_hyperlinks and hl_map is not None:
                href = hl_map.get((header_band + r_idx, c_idx))
                if href is not None:
                    out_row.append(_format_hyperlink_csv(value, href))
                    continue
            out_row.append(value)
        # xlsx-8a-04 (R4): apply formula-escape AFTER hyperlink
        # wrapping. The `[text](url)` markdown form starts with
        # `[` which is never a sentinel, so wrapped cells are
        # naturally defanged. Bare cells with sentinel-prefixed
        # values get quoted / stripped per mode.
        if escape_formulas != "off":
            out_row = [
                _apply_formula_escape(v, escape_formulas) for v in out_row
            ]
        # **TASK 010 §11.7 R28 fix:** drop rows where every cell is
        # None/"" — matches the JSON path semantics. NOTE: this
        # runs AFTER `escape_formulas=strip`, so a row that became
        # all-empty due to stripping is also dropped.
        if drop_empty_rows and all(v in (None, "") for v in out_row):
            continue
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
