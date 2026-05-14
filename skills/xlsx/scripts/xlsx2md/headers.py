"""F7 — Multi-row ``<thead>`` reconstruction. LIVE since task 012-05.

Emit-side reconstruction of multi-row ``<thead>`` from the flat
`` › ``-joined ``TableData.headers`` list. This is a pure emit-side
concern (the library does not expose raw per-row header data, per D12).

D-A11 algorithm (locked at Architecture phase):

1. Count `` › `` separators in each header cell.
2. All counts must be identical; if not, raise
   :class:`.exceptions.InconsistentHeaderDepth` (second safety layer
   after ``xlsx_read`` upstream uniformity guarantee).
3. Split each header string on `` › ``; the result is a list of N rows
   where row 0 is the top header band and row N-1 is the leaf header.
4. Compute ``colspan`` for row 0..N-2: for each position in the top
   band, count how many consecutive leaf positions share the same
   prefix path; colspan = that count (omit if 1).

Edge case (A-A3, accepted): if a workbook contains a header cell whose
text includes U+203A (`` › ``) as plain content (not as a separator),
the reconstruction will misinterpret it. This is documented as an
accepted edge case; no special handling is applied.
"""
from __future__ import annotations

from .exceptions import InconsistentHeaderDepth

_SEP = " › "  # " › " — D6 lock: canonical separator


def validate_header_depth_uniformity(headers: list[str]) -> int:
    """Return depth N (number of `` › `` separators + 1).

    Raises :class:`.exceptions.InconsistentHeaderDepth` if headers
    differ in separator count (D-A11 defensive check).

    Parameters
    ----------
    headers:
        Flat header list from ``TableData.headers``.

    Returns
    -------
    int
        Depth N: ``1`` for single-row headers, ``2`` for two-level, etc.
    """
    if not headers:
        return 1
    counts = [h.count(_SEP) for h in headers]
    first = counts[0]
    if any(c != first for c in counts):
        levels_repr = list(dict.fromkeys(counts))  # unique counts, insertion-ordered
        raise InconsistentHeaderDepth(
            f"Header depth not uniform: levels={sorted(levels_repr)!r} "
            f"(expected all {first})"
        )
    return first + 1


def split_headers_to_rows(headers: list[str]) -> list[list[str]]:
    """Split each header string on `` › `` separator; return a list of rows.

    Row 0 is the top header band; row N-1 is the leaf (deepest) header.
    Validates depth uniformity via
    :func:`validate_header_depth_uniformity` — raises
    :class:`.exceptions.InconsistentHeaderDepth` on non-uniform depth.

    Parameters
    ----------
    headers:
        Flat header list from ``TableData.headers``.

    Returns
    -------
    list[list[str]]
        ``rows[i][j]`` is the i-th header level of the j-th column.
        Single-row case: ``[["a", "b", "c"]]``.
        Two-level case: ``[["2026 plan", "2026 plan"], ["Q1", "Q2"]]``.

    Example::

        split_headers_to_rows(["2026 plan › Q1", "2026 plan › Q2"])
        # => [["2026 plan", "2026 plan"], ["Q1", "Q2"]]
    """
    if not headers:
        return [[]]

    depth = validate_header_depth_uniformity(headers)

    if depth == 1:
        return [list(headers)]

    # Split each header on separator; result is depth segments per header.
    split_cols: list[list[str]] = [h.split(_SEP) for h in headers]

    # Transpose: rows[i] = [split_cols[j][i] for j in range(n_cols)]
    n_cols = len(headers)
    rows: list[list[str]] = []
    for level in range(depth):
        rows.append([split_cols[j][level] for j in range(n_cols)])
    return rows


def compute_colspan_spans(header_rows: list[list[str]]) -> list[list[int]]:
    """Compute ``colspan`` for each cell in each header row.

    Returns a parallel list of lists with the same shape as
    ``header_rows``. Each value is the column span for that cell:

    - ``>= 1``: the ``<th>`` should emit with this colspan (omit the
      ``colspan`` attribute if value is 1).
    - ``0``: this position is covered by an earlier ``<th>`` with
      colspan > 1 in the same row — emit nothing (sentinel).

    Leaf row (last row): always ``1`` for each position.
    Non-leaf rows: consecutive positions that share an identical
    **prefix path** (values at row 0 through row i-1 are all equal)
    AND have the same value at row i are merged into one span.

    Parameters
    ----------
    header_rows:
        Output of :func:`split_headers_to_rows`.

    Returns
    -------
    list[list[int]]
        Parallel spans array with same shape as ``header_rows``.

    Example::

        compute_colspan_spans([["2026 plan", "2026 plan"], ["Q1", "Q2"]])
        # => [[2, 0], [1, 1]]
        # Top band: "2026 plan" spans 2 columns; second position suppressed.
        # Leaf row: each column spans 1 (always).
    """
    if not header_rows:
        return []

    n_rows = len(header_rows)
    n_cols = len(header_rows[0]) if header_rows else 0

    if n_cols == 0:
        return [[] for _ in header_rows]

    spans: list[list[int]] = [[1] * n_cols for _ in range(n_rows)]

    leaf_idx = n_rows - 1

    for row_idx in range(n_rows):
        if row_idx == leaf_idx:
            # Leaf row: always colspan=1 for each position.
            spans[row_idx] = [1] * n_cols
            continue

        # For non-leaf rows: compute spans using prefix path grouping.
        # Two positions j and k (k > j) can be merged at row_idx iff:
        #   - For all level r in 0..row_idx-1: header_rows[r][j] == header_rows[r][k]
        #   - header_rows[row_idx][j] == header_rows[row_idx][k]
        #
        # Algorithm: scan left-to-right; for each start of a run,
        # count consecutive positions with same prefix path.

        result_row = [0] * n_cols  # default: suppressed (0)
        j = 0
        while j < n_cols:
            # Determine the prefix path for position j up to row_idx (inclusive).
            path_j = tuple(header_rows[r][j] for r in range(row_idx + 1))

            # Count how far this run extends.
            run_end = j + 1
            while run_end < n_cols:
                path_k = tuple(header_rows[r][run_end] for r in range(row_idx + 1))
                if path_k != path_j:
                    break
                run_end += 1

            run_length = run_end - j
            result_row[j] = run_length  # anchor: emit with colspan=run_length
            for k in range(j + 1, run_end):
                result_row[k] = 0  # suppressed: covered by anchor

            j = run_end

        spans[row_idx] = result_row

    return spans
