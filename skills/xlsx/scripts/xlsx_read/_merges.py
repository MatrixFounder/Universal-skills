"""F3 — merge resolution + policy + overlap detector.

Three concerns:

1. `parse_merges(ws)` materialises openpyxl's `ws.merged_cells.ranges`
   into a `MergeMap` (anchor `(row, col)` → bottom-right `(row, col)`,
   inclusive 1-based). Stable, plain-Python representation that
   downstream code (`_overlapping_merges_check`, `apply_merge_policy`)
   can iterate without poking at openpyxl types.

2. `apply_merge_policy(rows, merges, policy)` is a **pure** function:
   it returns a *new* row-grid, never mutates the input. Three policies
   per ARCHITECTURE §4.1:
       - "anchor-only" — top-left carries the value; rest is `None`.
       - "fill"        — anchor value broadcast to every cell.
       - "blank"       — semantic alias of "anchor-only" in v1.

3. `_overlapping_merges_check(ranges)` performs an O(n²) pairwise
   intersection test (M8 + D4 fix). openpyxl 3.1.5 was empirically
   confirmed to silently accept overlapping merges (test_workbook.py
   `TestOpenpyxlOverlappingMergesBehaviour`), so explicit detection
   is the **only** way the library can fail loud on corrupted inputs.
"""

from __future__ import annotations

from typing import Any, Iterable

from ._exceptions import OverlappingMerges, TooManyMerges
from ._types import MergePolicy

# anchor (row, col) → bottom-right (row, col); both inclusive, 1-based.
MergeMap = dict[tuple[int, int], tuple[int, int]]

# xlsx-8a-02 (R2) — Sec-MED-3 memory-exhaustion mitigation. Bounded
# merge-count in `parse_merges`: a hand-crafted OOXML workbook with
# millions of `<mergeCell>` entries would otherwise materialise an
# unbounded Python dict in RAM before any `apply_merge_policy` work.
# Cap fires on the (cap+1)-th iteration per TASK D2 / ARCH D-A14.
# Practical real-world max is ~8K merges; 100K gives 10× headroom.
# Policy-locked; no CLI / env-var override (TASK Q-1 precedent).
_MAX_MERGES: int = 100_000


def parse_merges(ws: Any) -> MergeMap:
    """Build the anchor→bottom-right map for every merge range on `ws`.

    xlsx-8a-02 (R2, Sec-MED-3): bounded at `_MAX_MERGES` (=100_000)
    entries. Hand-crafted OOXML with millions of `<mergeCell>` is
    refused with `TooManyMerges` before the dict balloons RAM. Cap
    fires on the 100_001st insertion.
    """
    out: MergeMap = {}
    for r in ws.merged_cells.ranges:
        out[(r.min_row, r.min_col)] = (r.max_row, r.max_col)
        if len(out) > _MAX_MERGES:
            raise TooManyMerges(
                f"Worksheet {getattr(ws, 'title', '?')!r}: more than "
                f"{_MAX_MERGES} merge ranges; aborting to protect memory."
            )
    return out


def apply_merge_policy(
    rows: list[list[Any]],
    merges: MergeMap,
    policy: MergePolicy,
    *,
    top_row: int = 1,
    left_col: int = 1,
) -> list[list[Any]]:
    """Apply `policy` to a 2-D grid; never mutate the input.

    The grid is 0-indexed but merge anchors are 1-based (openpyxl
    convention). `top_row` / `left_col` carry the absolute 1-based
    coordinate of `rows[0][0]` so callers reading a sub-region of the
    sheet do not need to renumber merge anchors.

    Out-of-range merges (anchors outside the supplied grid) are
    silently skipped — the caller is responsible for supplying a
    region that covers the merges it cares about.
    """
    if policy not in ("anchor-only", "fill", "blank"):
        raise ValueError(f"Unknown merge policy: {policy!r}")
    if not rows:
        return []
    n_rows = len(rows)
    n_cols = max((len(r) for r in rows), default=0)
    # **P-M1 fix** (iter-3: include inner-row copy for full purity).
    # Short-circuit when no merges apply, but still copy each row so
    # the caller cannot mutate the input through the returned outer
    # list. The cost is O(n_cells) which is the same as the merge
    # path; the original "row if len(row) == n_cols else …" form
    # aliased input rows on the fast path and was a latent contract
    # leak (logic-iter2 L-N1 / perf-iter2 L-perf-iter2-1).
    if not merges:
        return [list(row) + [None] * (n_cols - len(row)) for row in rows]
    # Defensive copy at the row level; cell values are primitives.
    out = [list(row) + [None] * (n_cols - len(row)) for row in rows]

    for (ar, ac), (br, bc) in merges.items():
        # Convert absolute 1-based anchor / bottom-right to grid-local
        # 0-based indices. Skip merges that fall outside the supplied
        # grid entirely.
        ar0 = ar - top_row
        ac0 = ac - left_col
        br0 = br - top_row
        bc0 = bc - left_col
        if ar0 < 0 or ac0 < 0 or br0 >= n_rows or bc0 >= n_cols:
            # Either the anchor or the bottom-right falls outside the
            # supplied grid — skip rather than partially-apply, which
            # would produce inconsistent state at the boundary.
            continue
        anchor_value = out[ar0][ac0]
        for ri in range(ar0, br0 + 1):
            for ci in range(ac0, bc0 + 1):
                if ri == ar0 and ci == ac0:
                    continue
                if policy == "fill":
                    out[ri][ci] = anchor_value
                else:  # "anchor-only" or "blank" — semantic alias in v1.
                    out[ri][ci] = None
    return out


def _overlapping_merges_check(ranges: Iterable[Any]) -> None:
    """Raise `OverlappingMerges` on the first intersecting pair.

    openpyxl exposes each range with `.min_row`, `.min_col`, `.max_row`,
    `.max_col` (1-based, inclusive) — sufficient for a straightforward
    box-intersection test. The check is O(n²); for the bounded merge
    counts present in real workbooks (typically < 50) this is faster
    than the constant overhead of a sweep-line for the same input.

    NOTE (M8 fix): runs **before** `apply_merge_policy`. The detector
    cannot rely on openpyxl raising — empirical test (009-02
    TC-SPIKE-01) confirmed openpyxl 3.1.5 silently accepts overlapping
    merges, so we MUST detect explicitly here.
    """
    rs = list(ranges)
    for i in range(len(rs)):
        ai = rs[i]
        ar1, ac1, ar2, ac2 = ai.min_row, ai.min_col, ai.max_row, ai.max_col
        for j in range(i + 1, len(rs)):
            bi = rs[j]
            br1, bc1, br2, bc2 = bi.min_row, bi.min_col, bi.max_row, bi.max_col
            # Boxes overlap iff they overlap on BOTH axes.
            if ar1 <= br2 and br1 <= ar2 and ac1 <= bc2 and bc1 <= ac2:
                raise OverlappingMerges(
                    f"Overlapping merges: {ai!s} ∩ {bi!s}"
                )
