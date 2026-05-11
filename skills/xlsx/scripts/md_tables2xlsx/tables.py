"""xlsx-3 F3 (GFM pipe parser) + F4 (HTML <table> parser).

task-005-06: full parser bodies. Module-level `_HTML_PARSER`
singleton already constructed at import (ARCH M1 lock; established
in 005-01). Per-call `lxml.html.fragment_fromstring(...,
create_parent=False, parser=_HTML_PARSER)` invocations route through
the singleton — defense-in-depth against XXE + libxml2 huge-tree
expansion.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Literal, Optional

import lxml.html

from .inline import strip_inline_markdown
from .loaders import Block, HtmlTable, PipeTable


Alignment = Literal["left", "right", "center", "general"]


# ARCH M1 lock: module-level singleton with no-network + no-huge-tree
# + lenient HTML mode. DO NOT re-construct per-call.
_HTML_PARSER = lxml.html.HTMLParser(
    no_network=True,
    huge_tree=False,
    recover=True,
)

# vdd-multi review-fix (H1+M2/perf): hard ceiling on user-supplied
# colspan / rowspan values to prevent attacker-controlled memory
# allocation in `_expand_spans` (e.g. `<td colspan="999999999">`
# would otherwise allocate a 1-billion-cell grid). Excel's own
# column limit is 16384; mirrors it here.
_MAX_SPAN = 16384


def _parse_span(raw: object) -> int:
    """Parse a colspan/rowspan attribute value safely.

    Accepts:
      - Integer-looking strings (`"2"`, `"  3 "`).
      - Missing / `None` → 1.
      - Non-integer (`"abc"`, `"2.5"`, `""`) → 1 (defensive default).

    Clamps result to `[1, _MAX_SPAN]` (vdd-multi M2/perf review-fix).
    """
    if raw is None:
        return 1
    try:
        v = int(str(raw).strip())
    except (ValueError, TypeError):
        return 1
    if v < 1:
        return 1
    if v > _MAX_SPAN:
        return _MAX_SPAN
    return v


# ---------- data classes ----------


@dataclass(frozen=True)
class MergeRange:
    """1-indexed merge-range coords where row 1 is the header row.
    Emitted only by `parse_html_table` (GFM has no colspan/rowspan;
    R9.c lock).
    """
    start_row: int
    start_col: int
    end_row: int
    end_col: int


@dataclass(frozen=True)
class RawTable:
    """Output of `parse_pipe_table` / `parse_html_table`."""
    header: list[str]
    rows: list[list[str | None]]
    alignments: list[Alignment]
    merges: list[MergeRange]
    source: Literal["gfm", "html"]
    source_line: int


# ============================================================
# Public dispatcher (ARCH m2)
# ============================================================


def parse_table(block: Block) -> RawTable | None:
    """Dispatcher — `cli.py` orchestrator calls just this; isinstance
    branching lives here, not in the orchestrator (ARCH m2).
    """
    if isinstance(block, PipeTable):
        return parse_pipe_table(block)
    if isinstance(block, HtmlTable):
        return parse_html_table(block)
    raise TypeError(f"Unexpected Block type: {type(block).__name__}")


# ============================================================
# F3 — GFM pipe parser
# ============================================================


_GFM_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_SEP_CELL_RE = re.compile(r"^\s*(:?)-{3,}(:?)\s*$")


def _split_row(line: str) -> list[str]:
    """Split a `|`-pipe row honouring `\\|` escapes.

    - Strip leading whitespace + optional leading `|`.
    - Strip trailing optional `|` + whitespace.
    - Walk char-by-char; `\\|` → literal `|`, `|` → cell boundary.
    - Strip each cell's whitespace.
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _parse_alignment_marker(sep_line: str, n_cols: int) -> list[Alignment]:
    """Parse the GFM separator row `|---|---:|:--:|` into per-column
    alignment markers. If a cell's pattern doesn't match the strict
    separator-cell regex, falls back to `"general"`.
    """
    cells = _split_row(sep_line)
    out: list[Alignment] = []
    for cell in cells[:n_cols]:
        m = _SEP_CELL_RE.match(cell)
        if not m:
            out.append("general")
            continue
        left, right = m.group(1), m.group(2)
        if left and right:
            out.append("center")
        elif right:
            out.append("right")
        elif left:
            out.append("left")
        else:
            out.append("general")
    while len(out) < n_cols:
        out.append("general")
    return out


def parse_pipe_table(block: PipeTable) -> RawTable | None:
    """Parse a GFM pipe-table block. Returns None and emits a single
    stderr warning if the separator row's column count doesn't match
    the header row (R2.b — malformed-table skip).
    """
    raw = block.raw_lines
    if len(raw) < 2:
        return None
    header_cells = [strip_inline_markdown(c) for c in _split_row(raw[0])]
    sep_cells = _split_row(raw[1])
    if not _GFM_SEPARATOR_RE.match(raw[1]):
        # Not actually a separator → heuristic false-positive from F2.
        return None
    if len(header_cells) != len(sep_cells):
        print(
            f"warning: pipe table at line {block.line}: column count "
            f"mismatch (header={len(header_cells)}, sep={len(sep_cells)}); "
            "skipping",
            file=sys.stderr,
        )
        return None
    alignments = _parse_alignment_marker(raw[1], len(header_cells))
    rows: list[list[str | None]] = []
    for body_line in raw[2:]:
        cells = _split_row(body_line)
        cells = [strip_inline_markdown(c) for c in cells]
        # Pad / truncate to header width.
        if len(cells) < len(header_cells):
            cells = cells + [""] * (len(header_cells) - len(cells))
        elif len(cells) > len(header_cells):
            cells = cells[: len(header_cells)]
        # Empty cells → None.
        rows.append([(c if c != "" else None) for c in cells])
    return RawTable(
        header=header_cells,
        rows=rows,
        alignments=alignments,
        merges=[],
        source="gfm",
        source_line=block.line,
    )


# ============================================================
# F4 — HTML <table> parser
# ============================================================


def _walk_rows(table_el) -> list:
    """Iterate `<tr>` elements honouring `<thead>` / `<tbody>` /
    direct-child order. Returns a flat list of <tr> elements.

    vdd-multi M2 review-fix: also includes direct `./tr` children
    even when `<thead>`/`<tbody>` exist, so legacy / hand-written
    markup like `<table><thead>…</thead><tr>data</tr></table>` does
    not silently drop the direct row(s).
    """
    rows = []
    # Look for thead first; rows from thead come first.
    for thead in table_el.xpath(".//thead"):
        rows.extend(thead.xpath(".//tr"))
    for tbody in table_el.xpath(".//tbody"):
        rows.extend(tbody.xpath(".//tr"))
    # Direct-child <tr> elements (NOT inside thead/tbody) — merge in
    # document order. Use a set of identities to avoid duplication.
    seen_ids = {id(r) for r in rows}
    for direct_tr in table_el.xpath("./tr"):
        if id(direct_tr) not in seen_ids:
            rows.append(direct_tr)
    return rows


def _expand_spans(
    rows_raw: list[list[tuple[str, int, int]]],
) -> tuple[list[list[str | None]], list[MergeRange]]:
    """Convert a list of rows (each cell = (text, colspan, rowspan))
    into a rectangular grid + list of MergeRange records (1-indexed
    coords where row 1 = header).

    Algorithm: maintain a `occupied` set of (row_idx, col_idx) tuples
    representing cells already claimed by an earlier rowspan. For
    each new cell, find the next free column, write the text at
    (r, c), and mark spans.
    """
    if not rows_raw:
        return [], []
    n_rows = len(rows_raw)
    # Determine grid width: sum of colspans in each row; use the max.
    # vdd-multi M2/perf review-fix: also clamp the row-level sum so a
    # row with many narrow cells × bounded individual colspan still
    # can't blow past the Excel column ceiling.
    width = 0
    for row in rows_raw:
        row_w = sum(cs for (_, cs, _) in row)
        width = max(width, row_w)
    width = min(width, _MAX_SPAN)
    grid: list[list[str | None]] = [
        [None] * width for _ in range(n_rows)
    ]
    occupied: set[tuple[int, int]] = set()
    merges: list[MergeRange] = []
    for r, row in enumerate(rows_raw):
        c = 0
        for (text, cs, rs) in row:
            # Advance past occupied cells (from previous rowspans).
            while (r, c) in occupied:
                c += 1
            if c >= width:
                break
            grid[r][c] = text if text != "" else None
            # Mark span occupancy + emit merge if span > 1×1.
            for rr in range(r, min(r + rs, n_rows)):
                for cc in range(c, min(c + cs, width)):
                    if (rr, cc) != (r, c):
                        occupied.add((rr, cc))
            if cs > 1 or rs > 1:
                merges.append(
                    MergeRange(
                        start_row=r + 1,
                        start_col=c + 1,
                        end_row=min(r + rs, n_rows),
                        end_col=min(c + cs, width),
                    )
                )
            c += cs
    return grid, merges


def parse_html_table(block: HtmlTable) -> Optional[RawTable]:
    """Parse a `<table>` fragment via the module-level `_HTML_PARSER`
    (ARCH M1 lock — no_network=True, huge_tree=False, recover=True).
    Returns None on empty/malformed `<table>` (vdd-multi M3 fix).
    """
    fragment = lxml.html.fragment_fromstring(
        block.fragment, create_parent=False, parser=_HTML_PARSER,
    )
    rows_el = _walk_rows(fragment)
    rows_raw: list[list[tuple[str, int, int]]] = []
    for tr in rows_el:
        cells_in_row: list[tuple[str, int, int]] = []
        for cell in tr.xpath("./*[self::th or self::td]"):
            text = (cell.text_content() or "").strip()
            text = strip_inline_markdown(text)
            # vdd-multi H1 review-fix: safe parse + clamp.
            colspan = _parse_span(cell.get("colspan"))
            rowspan = _parse_span(cell.get("rowspan"))
            cells_in_row.append((text, colspan, rowspan))
        rows_raw.append(cells_in_row)
    if not rows_raw:
        # vdd-multi M3 review-fix: empty <table> (no <tr> at all)
        # treated as malformed-skip — orchestrator emits stderr
        # warning and falls through to NoTablesFound / next table.
        print(
            f"warning: HTML table at line {block.line}: no <tr> rows found; skipping",
            file=sys.stderr,
        )
        return None  # type: ignore[return-value]
    grid, merges = _expand_spans(rows_raw)
    if not grid or not grid[0]:
        # vdd-multi M3 review-fix: every <tr> had zero cells.
        print(
            f"warning: HTML table at line {block.line}: zero cells; skipping",
            file=sys.stderr,
        )
        return None  # type: ignore[return-value]
    header = [(c if c is not None else "") for c in grid[0]]
    body = [list(r) for r in grid[1:]]
    alignments: list[Alignment] = ["general"] * len(header)
    return RawTable(
        header=header,
        rows=body,
        alignments=alignments,
        merges=merges,
        source="html",
        source_line=block.line,
    )
