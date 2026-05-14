"""Unit tests for xlsx2md/headers.py — multi-row header reconstruction (012-05).

8 tests per TASK §5.2:
1. TC-UNIT-01 — single-row passthrough: no separator → [[h1, h2, h3]].
2. TC-UNIT-02 — two-level separator split.
3. TC-UNIT-03 — three-level separator split.
4. TC-UNIT-04 — compute_colspan top-row groups consecutive identical values.
5. TC-UNIT-05 — compute_colspan leaf row always 1 for each position.
6. TC-UNIT-06 — compute_colspan intermediate row groups by prefix path.
7. TC-UNIT-07 — validate_header_depth_uniformity returns N.
8. TC-UNIT-08 — validate_header_depth_uniformity raises InconsistentHeaderDepth.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from xlsx2md.exceptions import InconsistentHeaderDepth
from xlsx2md.headers import (
    compute_colspan_spans,
    split_headers_to_rows,
    validate_header_depth_uniformity,
)


class TestSplitHeadersToRows(unittest.TestCase):
    """TC-UNIT-01 through TC-UNIT-03 — split_headers_to_rows."""

    def test_single_row_passthrough(self) -> None:
        """TC-UNIT-01: no separator → single-row matrix [[h1, h2, h3]]."""
        headers = ["Alpha", "Beta", "Gamma"]
        result = split_headers_to_rows(headers)
        self.assertEqual(result, [["Alpha", "Beta", "Gamma"]])

    def test_two_level_separator_split(self) -> None:
        """TC-UNIT-02: two-level headers split into 2 rows."""
        headers = ["2026 plan › Q1", "2026 plan › Q2", "2026 plan › Q3"]
        result = split_headers_to_rows(headers)
        self.assertEqual(result, [
            ["2026 plan", "2026 plan", "2026 plan"],
            ["Q1", "Q2", "Q3"],
        ])

    def test_three_level_separator_split(self) -> None:
        """TC-UNIT-03: three-level headers split into 3 rows."""
        headers = ["A › B › X", "A › B › Y", "A › C › Z"]
        result = split_headers_to_rows(headers)
        self.assertEqual(result, [
            ["A", "A", "A"],
            ["B", "B", "C"],
            ["X", "Y", "Z"],
        ])

    def test_empty_headers_returns_empty_row(self) -> None:
        """Edge case: empty list returns [[]]."""
        result = split_headers_to_rows([])
        self.assertEqual(result, [[]])

    def test_single_column_single_row(self) -> None:
        """Single column with no separator → [[value]]."""
        result = split_headers_to_rows(["Total"])
        self.assertEqual(result, [["Total"]])

    def test_raises_on_inconsistent_depth(self) -> None:
        """Non-uniform depths raise InconsistentHeaderDepth."""
        with self.assertRaises(InconsistentHeaderDepth):
            split_headers_to_rows(["A › B", "C"])  # depths 2 and 1


class TestComputeColspanSpans(unittest.TestCase):
    """TC-UNIT-04 through TC-UNIT-06 — compute_colspan_spans."""

    def test_top_row_groups_consecutive_identical(self) -> None:
        """TC-UNIT-04: top-row runs of identical values produce colspan > 1."""
        header_rows = [
            ["2026 plan", "2026 plan", "2026 plan"],
            ["Q1", "Q2", "Q3"],
        ]
        spans = compute_colspan_spans(header_rows)
        # Top row: "2026 plan" × 3 → span [3, 0, 0]
        self.assertEqual(spans[0], [3, 0, 0])

    def test_leaf_row_always_one(self) -> None:
        """TC-UNIT-05: leaf row always colspan=1 for every position."""
        header_rows = [
            ["2026 plan", "2026 plan", "2026 plan"],
            ["Q1", "Q2", "Q3"],
        ]
        spans = compute_colspan_spans(header_rows)
        # Leaf row: each column spans 1
        self.assertEqual(spans[1], [1, 1, 1])

    def test_intermediate_row_groups_by_prefix_path(self) -> None:
        """TC-UNIT-06: intermediate row groups columns by full prefix path.

        Three-level header:
          Row 0: [A, A, A, A]
          Row 1: [B, B, C, C]
          Row 2 (leaf): [X, Y, Z, W]

        Row 1 grouping:
          - Col 0,1 share prefix (A,B) → span [2, 0]
          - Col 2,3 share prefix (A,C) → span [2, 0]
          Result: [2, 0, 2, 0]
        """
        header_rows = [
            ["A", "A", "A", "A"],
            ["B", "B", "C", "C"],
            ["X", "Y", "Z", "W"],
        ]
        spans = compute_colspan_spans(header_rows)
        # Row 0: A × 4 → [4, 0, 0, 0]
        self.assertEqual(spans[0], [4, 0, 0, 0])
        # Row 1: (A,B) × 2, (A,C) × 2 → [2, 0, 2, 0]
        self.assertEqual(spans[1], [2, 0, 2, 0])
        # Row 2 (leaf): [1, 1, 1, 1]
        self.assertEqual(spans[2], [1, 1, 1, 1])

    def test_mixed_banner_row_different_values(self) -> None:
        """Top row with alternating different values: each gets span=1."""
        header_rows = [
            ["Apples", "Bananas"],
            ["Qty", "Qty"],
        ]
        spans = compute_colspan_spans(header_rows)
        self.assertEqual(spans[0], [1, 1])
        self.assertEqual(spans[1], [1, 1])

    def test_single_row_all_ones(self) -> None:
        """Single-row (leaf) header: all spans 1."""
        header_rows = [["a", "b", "c"]]
        spans = compute_colspan_spans(header_rows)
        self.assertEqual(spans, [[1, 1, 1]])

    def test_empty_header_rows(self) -> None:
        """Empty input returns empty list."""
        self.assertEqual(compute_colspan_spans([]), [])

    def test_prefix_path_breaks_run(self) -> None:
        """Run broken when prefix path differs even with same current value.

        Row 0: [P, Q, P]
        Row 1: [X, X, X]  <- all same, but prefix paths differ at col 2

        Row 0 spans: P=1 at col 0, Q=1 at col 1, P=1 at col 2 (no run across different values)
        Row 1 spans: col 0 and col 1 share prefix (row0: P,Q no! they differ)
          Actually col 0 prefix=(P,), col 1 prefix=(Q,), col 2 prefix=(P,)
          → col 0 and col 2 have same prefix path (P,X) but are not consecutive
          → col 0 alone: span=1; col 1 alone: span=1; col 2 alone: span=1
          Row 1 (leaf): all 1
        """
        header_rows = [
            ["P", "Q", "P"],
            ["X", "X", "X"],
        ]
        spans = compute_colspan_spans(header_rows)
        # Row 0: no consecutive identical values in order → [1, 1, 1]
        self.assertEqual(spans[0], [1, 1, 1])
        # Row 1 (leaf): [1, 1, 1]
        self.assertEqual(spans[1], [1, 1, 1])


class TestValidateHeaderDepthUniformity(unittest.TestCase):
    """TC-UNIT-07 and TC-UNIT-08 — validate_header_depth_uniformity."""

    def test_returns_depth_single_level(self) -> None:
        """TC-UNIT-07: single-level headers (no separator) → depth 1."""
        self.assertEqual(validate_header_depth_uniformity(["a", "b", "c"]), 1)

    def test_returns_depth_two_levels(self) -> None:
        """TC-UNIT-07 variant: two-level headers → depth 2."""
        self.assertEqual(
            validate_header_depth_uniformity(["A › B", "A › C"]), 2
        )

    def test_returns_depth_three_levels(self) -> None:
        """TC-UNIT-07 variant: three-level headers → depth 3."""
        self.assertEqual(
            validate_header_depth_uniformity(["A › B › X", "A › B › Y"]), 3
        )

    def test_raises_on_inconsistent_depth(self) -> None:
        """TC-UNIT-08: non-uniform depths raise InconsistentHeaderDepth."""
        with self.assertRaises(InconsistentHeaderDepth) as ctx:
            validate_header_depth_uniformity(["A › B", "C"])
        self.assertIn("not uniform", str(ctx.exception))

    def test_raises_carries_code_2(self) -> None:
        """InconsistentHeaderDepth has CODE=2 per exceptions catalogue."""
        with self.assertRaises(InconsistentHeaderDepth) as ctx:
            validate_header_depth_uniformity(["A › B › C", "D › E"])
        self.assertEqual(ctx.exception.CODE, 2)

    def test_empty_headers_returns_1(self) -> None:
        """Empty header list → depth 1 (no separators)."""
        self.assertEqual(validate_header_depth_uniformity([]), 1)

    def test_single_header_no_sep(self) -> None:
        """Single header with no separator → depth 1."""
        self.assertEqual(validate_header_depth_uniformity(["Total"]), 1)

    def test_single_header_with_sep(self) -> None:
        """Single header with separator is trivially uniform → depth 2."""
        self.assertEqual(
            validate_header_depth_uniformity(["Group › Sub"]), 2
        )


if __name__ == "__main__":
    unittest.main()
