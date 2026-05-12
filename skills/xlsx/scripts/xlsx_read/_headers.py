"""F5 — header detection + flatten + synthetic + ambiguous-boundary.

`detect_header_band(ws, region, hint)` returns the number of header
rows at the top of the region. When `hint == "auto"`, we scan the top
rows for **column-spanning merges** (width ≥ 2) confined to the
region's column span; the first row WITHOUT such a merge ends the
header band (minimum 1 row).

`flatten_headers(header_grid, header_rows, separator=" › ")` joins
top→bottom keys with U+203A (R7), applying sticky-fill LEFT for cells
that look empty (the natural Excel pattern: leftmost cell of a
horizontal merge carries the label; the rest are blank XML).

`synthetic_headers(width)` is the **final** form (already in 009-01).

`_ambiguous_boundary_check(merges, region, header_rows)` returns a
warning string (or `None`) if any merge straddles the header/body
boundary at `region.top_row + header_rows - 1` ↔ `region.top_row +
header_rows`.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from ._types import TableRegion

# U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK — chosen because
# it does not collide with any legitimate spreadsheet header content
# (unlike `/` which appears in headers like "Q1 / Q2 split", R7 fix).
HEADER_SEPARATOR = " › "


def detect_header_band(
    ws: Any,
    region: TableRegion,
    hint: int | Literal["auto"],
) -> int:
    """Detect the number of header rows. See module docstring."""
    if isinstance(hint, int):
        if hint < 0:
            raise ValueError(f"header_rows hint must be >= 0, got {hint!r}")
        return hint
    if hint != "auto":
        raise ValueError(f"header_rows hint must be int or 'auto', got {hint!r}")

    # Index eligible merges by anchor row for O(1) per-row lookup.
    # Eligible = column-spanning (width ≥ 2) AND fully contained in the
    # region's column span AND anchor row inside the region's row span.
    #
    # **L-H1 fix:** require `merge.min_row >= region.top_row`. A merge
    # that *starts above* the region (and only crosses into it via
    # `max_row >= region.top_row`) is NOT a header signal for *this*
    # region — it belongs to an enclosing super-region whose
    # tightening produced this one.
    eligible_by_anchor: dict[int, list[Any]] = {}
    for merge in ws.merged_cells.ranges:
        if merge.min_col == merge.max_col:
            continue  # vertical-only merge — not a header signal
        if merge.min_col < region.left_col or merge.max_col > region.right_col:
            continue
        if merge.min_row < region.top_row or merge.min_row > region.bottom_row:
            continue
        eligible_by_anchor.setdefault(merge.min_row, []).append(merge)

    # **TASK 010 §11 patch:** walk top-down with contiguous-from-top
    # semantics matching this module's docstring ("the first row WITHOUT
    # such a merge ends the header band"). A row is part of the header
    # band iff (a) it has an eligible merge anchored on it, OR (b) it
    # is covered by a merge anchored above it (cursor ≤ deepest_max_row).
    # The first row that satisfies NEITHER ends the band. Scattered
    # merges deep inside the body — e.g. totals-block banners 50 rows
    # below the real header — no longer inflate the band.
    deepest_max_row: int = region.top_row - 1  # "no merges found" sentinel
    cursor = region.top_row
    while cursor <= region.bottom_row:
        anchored = eligible_by_anchor.get(cursor)
        if anchored is None and cursor > deepest_max_row:
            break
        if anchored is not None:
            deepest_max_row = max(
                deepest_max_row, max(m.max_row for m in anchored)
            )
        cursor += 1

    if deepest_max_row < region.top_row:
        # No column-spanning merges anchored in the region → default
        # to a single header row (conservative; callers can override
        # via explicit int hint).
        return 1

    # Header band runs from `region.top_row` through `deepest_max_row
    # + 1` (the row of per-column sub-labels under the banner). Clamp
    # to the region's bottom.
    band_end = min(deepest_max_row + 1, region.bottom_row)
    return max(band_end - region.top_row + 1, 1)


def flatten_headers(
    rows: list[list[Any]],
    header_rows: int,
    separator: str = HEADER_SEPARATOR,
    *,
    merges: Mapping[tuple[int, int], tuple[int, int]] | None = None,
    region_top_row: int = 1,
    region_left_col: int = 1,
) -> tuple[list[str], list[str]]:
    """Flatten top→bottom keys with merge-scoped sticky-fill-left.

    The `rows` parameter receives the post-merge-policy grid, i.e.
    cells inside a merge range are already `None` (anchor-only) or
    pre-filled with the anchor value (fill). For the auto-detected
    header band, the natural Excel pattern is **anchor-only**: a
    horizontal merge's anchor carries the label, the rest are empty
    cells. Sticky-fill-left then propagates the anchor value rightward
    so each merged-cell column inherits its banner.

    **TASK 010 §11 patch v2:** when `merges` is supplied, sticky-fill
    is scoped to merge column-spans only. Cells outside any horizontal
    merge return empty (no inheritance from arbitrary left-side
    cells). Without this guard, a title merge `A1:F1` would propagate
    across all 25 columns of a 25-wide region, producing 25 identical
    header keys. The legacy unconditional sticky-fill is preserved as
    fallback when `merges=()` (default) so synthetic test fixtures
    that don't model merge ranges continue to work.

    `merges` is the `MergeMap` produced by `parse_merges(ws)`: a dict
    mapping anchor `(min_row, min_col)` (1-based) to bottom-right
    `(max_row, max_col)` (1-based). `region_top_row` / `region_left_col`
    translate absolute merge coordinates into grid-relative 0-based
    indices.

    Returns `(flattened_keys, warnings)`.
    """
    if header_rows <= 0 or not rows:
        return ([], [])

    n_cols = max(len(r) for r in rows[:header_rows])

    # Build per-header-row maps: covered_col_0based → anchor_col_0based.
    # Only horizontal merges (width ≥ 2) whose anchor row is inside the
    # header band contribute. Cells outside the maps will NOT inherit
    # from their left neighbour.
    merge_maps: list[dict[int, int]] = [{} for _ in range(header_rows)]
    if merges:
        for (min_row, min_col), (_max_row, max_col) in merges.items():
            if min_col == max_col:
                continue  # vertical-only — not a header-fill signal
            row_idx = min_row - region_top_row
            if row_idx < 0 or row_idx >= header_rows:
                continue  # merge doesn't anchor in the header band
            col_anchor = min_col - region_left_col
            col_end = max_col - region_left_col
            if col_anchor < 0 or col_anchor >= n_cols:
                continue
            for c in range(col_anchor + 1, min(col_end + 1, n_cols)):
                merge_maps[row_idx][c] = col_anchor

    # **vdd-multi-2 MED fix:** legacy fallback fires ONLY when the
    # caller passes no merge info at all (`merges is None`). An empty
    # dict or a dict whose merges don't anchor in the header band
    # means the caller HAS merge knowledge and is asserting "no
    # horizontal merge anchors this header row" — in which case we
    # must NOT silently inherit values across un-merged cells (that
    # would re-introduce the title-spillover bug for sheets whose
    # only merges live in the body). The previous `not any(merge_maps)`
    # clause was too permissive.
    legacy_sticky = merges is None

    # First pass — merge-scoped (or legacy) sticky-fill-left.
    filled: list[list[str]] = []
    for r_idx, r in enumerate(rows[:header_rows]):
        padded = [r[i] if i < len(r) else None for i in range(n_cols)]
        out_row: list[str] = []
        last: str = ""
        for c_idx, cell in enumerate(padded):
            if cell is not None and cell != "":
                last = str(cell)
                out_row.append(last)
                continue
            if legacy_sticky:
                out_row.append(last)
                continue
            anchor_col = merge_maps[r_idx].get(c_idx)
            if anchor_col is None:
                # Outside any horizontal merge — no inheritance.
                last = ""
                out_row.append("")
                continue
            # Inside a horizontal merge: fill with the anchor's value
            # (which may itself be None if the source cell was empty).
            anchor_val = padded[anchor_col]
            if anchor_val is None or anchor_val == "":
                out_row.append("")
            else:
                out_row.append(str(anchor_val))
        filled.append(out_row)

    # Second pass — join top→bottom per column with the separator;
    # drop empty levels (e.g. when level-0 is blank under a level-1
    # label) so the final key is clean.
    keys: list[str] = []
    for col in range(n_cols):
        parts = [filled[lvl][col] for lvl in range(header_rows) if filled[lvl][col]]
        # Deduplicate consecutive repeats — when a single-cell label
        # gets sticky-filled into both levels, `["X", "X"]` flattens
        # to "X" not "X › X".
        deduped: list[str] = []
        for p in parts:
            if not deduped or deduped[-1] != p:
                deduped.append(p)
        keys.append(separator.join(deduped))
    return (keys, [])


def synthetic_headers(width: int) -> list[str]:
    """Emit synthetic `col_1..col_N` headers. **FINAL** form."""
    if width < 0:
        raise ValueError(f"synthetic_headers: width must be >= 0, got {width!r}")
    return [f"col_{i + 1}" for i in range(width)]


def _ambiguous_boundary_check(
    merges: Any,
    region: TableRegion,
    header_rows: int,
) -> str | None:
    """Return a warning string iff any merge straddles the header/body cut.

    The cut sits between absolute rows `region.top_row + header_rows
    - 1` (last header row) and `region.top_row + header_rows` (first
    body row). A merge straddles iff `min_row <= cut_above` AND
    `max_row >= cut_below`.
    """
    if header_rows <= 0:
        return None
    cut_above = region.top_row + header_rows - 1
    cut_below = region.top_row + header_rows
    if cut_below > region.bottom_row:
        return None
    for m in merges:
        if (
            m.min_row <= cut_above
            and m.max_row >= cut_below
            and m.min_col >= region.left_col
            and m.max_col <= region.right_col
        ):
            return (
                f"Ambiguous header boundary: merge {m!s} straddles "
                f"rows {cut_above}/{cut_below} of region "
                f"{region.name!r}"
            )
    return None
