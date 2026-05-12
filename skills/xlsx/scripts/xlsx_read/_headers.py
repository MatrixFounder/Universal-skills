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

from typing import Any, Literal

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

    # Find the maximum row touched by any column-spanning merge
    # whose anchor is INSIDE the region's top rows. A column-spanning
    # merge on row K implies row K+1 is the sub-labels row (the
    # natural Excel banner-over-detail pattern). So the header band
    # extends through `max_merge_row + 1`.
    #
    # **L-H1 fix:** require `merge.min_row >= region.top_row`. A merge
    # that *starts above* the region (and only crosses into it via
    # `max_row >= region.top_row`) is NOT a header signal for *this*
    # region — it belongs to an enclosing super-region whose
    # tightening produced this one.
    max_merge_row: int = region.top_row - 1  # "no merges found" sentinel
    for merge in ws.merged_cells.ranges:
        if merge.min_col == merge.max_col:
            continue  # vertical-only merge — not a header signal
        if merge.min_col < region.left_col or merge.max_col > region.right_col:
            continue
        if merge.min_row < region.top_row or merge.min_row > region.bottom_row:
            continue
        # Track the lowest row covered by the merge.
        max_merge_row = max(max_merge_row, merge.max_row)

    if max_merge_row < region.top_row:
        # No column-spanning merges anchored in the region → default
        # to a single header row (conservative; callers can override
        # via explicit int hint).
        return 1

    # Header band runs from `region.top_row` through `max_merge_row +
    # 1` (the row of per-column sub-labels under the banner). Clamp to
    # the region's bottom.
    band_end = min(max_merge_row + 1, region.bottom_row)
    return max(band_end - region.top_row + 1, 1)


def flatten_headers(
    rows: list[list[Any]],
    header_rows: int,
    separator: str = HEADER_SEPARATOR,
) -> tuple[list[str], list[str]]:
    """Flatten top→bottom keys with sticky-fill-left.

    The `rows` parameter receives the post-merge-policy grid, i.e.
    cells inside a merge range are already `None` (anchor-only) or
    pre-filled with the anchor value (fill). For the auto-detected
    header band, the natural Excel pattern is **anchor-only**: a
    horizontal merge's anchor carries the label, the rest are empty
    cells. Sticky-fill-left propagates the leftmost non-empty value
    rightward so each column inherits its banner.

    Returns `(flattened_keys, warnings)`.
    """
    if header_rows <= 0 or not rows:
        return ([], [])

    n_cols = max(len(r) for r in rows[:header_rows])
    # First pass — sticky-fill-left per header row.
    filled: list[list[str]] = []
    for r in rows[:header_rows]:
        padded = [r[i] if i < len(r) else None for i in range(n_cols)]
        last: str = ""
        out_row: list[str] = []
        for cell in padded:
            if cell is None or cell == "":
                out_row.append(last)
            else:
                last = str(cell)
                out_row.append(last)
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
