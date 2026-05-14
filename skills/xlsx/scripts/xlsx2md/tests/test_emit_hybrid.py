"""Unit tests for xlsx2md/emit_hybrid.py — format selector + orchestrator (012-06).

15 tests per TASK §5.2 (TC-UNIT-01..15):

1.  TC-UNIT-01 — select_format hybrid, no merges, no formula → "gfm"
2.  TC-UNIT-02 — select_format hybrid + body merges → "html"
3.  TC-UNIT-03 — select_format hybrid + multi-row header → "html"
4.  TC-UNIT-04 — select_format hybrid + include_formulas=True + formula cell → "html"
5.  TC-UNIT-05 — select_format hybrid + formula cell + include_formulas=False → "gfm"
6.  TC-UNIT-06 — select_format hybrid + synthetic header → "html"
7.  TC-UNIT-07 — select_format explicit "gfm" overrides all promotion rules
8.  TC-UNIT-08 — select_format explicit "html" overrides all promotion rules
9.  TC-UNIT-09 — emit_workbook_md multi-sheet H2 order
10. TC-UNIT-10 — emit_workbook_md multi-table H3 order
11. TC-UNIT-11 — single-sheet mode suppresses ## H2
12. TC-UNIT-12 — GfmMergesRequirePolicy raised (format=gfm + merges + fail policy)
13. TC-UNIT-13 — GfmMergesRequirePolicy NOT raised when policy=duplicate
14. TC-UNIT-14 — _gap_detect_label resets counter on sheet change
15. TC-UNIT-15 — --no-split region with name=None emits ### Table-1 H3
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from xlsx_read import TableData, TableRegion, SheetInfo
from xlsx2md.cli import build_parser
from xlsx2md.emit_hybrid import (
    _gap_detect_label,
    _has_body_merges,
    _has_formula_cells,
    _is_multi_row_header,
    _is_synthetic_header,
    emit_workbook_md,
    select_format,
)
from xlsx2md.exceptions import GfmMergesRequirePolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_region(
    sheet: str = "Sheet1",
    top_row: int = 1,
    left_col: int = 1,
    bottom_row: int = 10,
    right_col: int = 3,
    source: str = "gap_detect",
    name: str | None = None,
    header_count: int | None = None,
) -> TableRegion:
    return TableRegion(
        sheet=sheet,
        top_row=top_row,
        left_col=left_col,
        bottom_row=bottom_row,
        right_col=right_col,
        source=source,  # type: ignore[arg-type]
        name=name,
        listobject_header_row_count=header_count,
    )


def _make_td(
    headers: list[str] | None = None,
    rows: list[list] | None = None,
    source: str = "gap_detect",
    header_count: int | None = None,
    name: str | None = None,
) -> TableData:
    region = _make_region(source=source, header_count=header_count, name=name)
    return TableData(
        region=region,
        headers=headers if headers is not None else ["A", "B", "C"],
        rows=rows if rows is not None else [],
    )


def _args(**overrides) -> object:
    """Build a parsed-args namespace with sensible defaults."""
    base = build_parser().parse_args(["dummy.xlsx"])
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _make_sheet_info(name: str) -> SheetInfo:
    return SheetInfo(name=name, index=0, state="visible")


def _make_payload(
    sheet_name: str = "Sheet1",
    table_name: str | None = None,
    headers: list[str] | None = None,
    rows: list[list] | None = None,
    source: str = "gap_detect",
    header_count: int | None = None,
) -> tuple:
    """Build a 4-tuple (SheetInfo, TableRegion, TableData, hyperlinks_map)."""
    sheet_info = _make_sheet_info(sheet_name)
    region = _make_region(
        sheet=sheet_name, source=source, name=table_name,
        header_count=header_count,
    )
    td = TableData(
        region=region,
        headers=headers if headers is not None else ["Col"],
        rows=rows if rows is not None else [["val"]],
    )
    return (sheet_info, region, td, {})


# ---------------------------------------------------------------------------
# TC-UNIT-01..08: select_format predicates
# ---------------------------------------------------------------------------

class TestSelectFormatPredicates(unittest.TestCase):
    """TC-UNIT-01..08 — select_format with all promotion rules."""

    def test_tc_unit_01_hybrid_no_merges_returns_gfm(self) -> None:
        """TC-UNIT-01 — hybrid, clean table → gfm."""
        td = _make_td(rows=[["a", "b", "c"]])
        args = _args(format="hybrid", include_formulas=False)
        self.assertEqual(select_format(td, args), "gfm")

    def test_tc_unit_02_hybrid_body_merges_returns_html(self) -> None:
        """TC-UNIT-02 — hybrid + None in col>0 (merge child) → html."""
        td = _make_td(rows=[["a", None, "c"]])
        args = _args(format="hybrid", include_formulas=False)
        self.assertEqual(select_format(td, args), "html")

    def test_tc_unit_03_hybrid_multi_row_header_returns_html(self) -> None:
        """TC-UNIT-03 — hybrid + header containing ' › ' → html."""
        td = _make_td(headers=["a › b", "c"])
        args = _args(format="hybrid", include_formulas=False)
        self.assertEqual(select_format(td, args), "html")

    def test_tc_unit_04_hybrid_formula_include_true_returns_html(self) -> None:
        """TC-UNIT-04 — hybrid + include_formulas=True + formula cell → html."""
        td = _make_td(rows=[["=A1+B1", "x"]])
        args = _args(format="hybrid", include_formulas=True)
        self.assertEqual(select_format(td, args), "html")

    def test_tc_unit_05_hybrid_formula_include_false_returns_gfm(self) -> None:
        """TC-UNIT-05 — hybrid + formula cell + include_formulas=False → gfm.

        When include_formulas=False the library surfaces the cached value;
        the formula string is not present in rows, so no promotion.
        But even if a literal '=...' string exists in rows, no promotion
        because the predicate is gated by include_formulas flag.
        """
        td = _make_td(rows=[["=A1+B1"]])
        args = _args(format="hybrid", include_formulas=False)
        self.assertEqual(select_format(td, args), "gfm")

    def test_tc_unit_06_hybrid_synthetic_header_returns_html(self) -> None:
        """TC-UNIT-06 — hybrid + listobject_header_row_count=0 → html."""
        td = _make_td(source="listobject", header_count=0)
        args = _args(format="hybrid", include_formulas=False)
        self.assertEqual(select_format(td, args), "html")

    def test_tc_unit_07_explicit_gfm_overrides_all(self) -> None:
        """TC-UNIT-07 — --format=gfm short-circuits before any promotion rule."""
        # Build table that would trigger every promotion rule.
        td = _make_td(
            headers=["a › b"],
            rows=[["=SUM(A1)", None]],
            source="listobject",
            header_count=0,
        )
        args = _args(format="gfm", include_formulas=True)
        self.assertEqual(select_format(td, args), "gfm")

    def test_tc_unit_08_explicit_html_overrides_all(self) -> None:
        """TC-UNIT-08 — --format=html short-circuits before any promotion rule."""
        td = _make_td(rows=[["plain", "clean"]])
        args = _args(format="html", include_formulas=False)
        self.assertEqual(select_format(td, args), "html")


# ---------------------------------------------------------------------------
# TC-UNIT-09..13: emit_workbook_md orchestrator
# ---------------------------------------------------------------------------

class TestEmitWorkbookMd(unittest.TestCase):
    """TC-UNIT-09..13 — orchestrator H2/H3/raise behaviour."""

    def _run(self, payloads: list[tuple], **arg_overrides) -> str:
        """Patch iter_table_payloads to return *payloads* and collect output."""
        args = _args(**arg_overrides)
        out = io.StringIO()
        with patch("xlsx2md.dispatch.iter_table_payloads", return_value=payloads):
            emit_workbook_md(None, args, out)
        return out.getvalue()

    def test_tc_unit_09_multi_sheet_h2_order(self) -> None:
        """TC-UNIT-09 — 3 sheets → ## Sales, ## Costs, ## Summary in order."""
        payloads = [
            _make_payload(sheet_name="Sales", table_name="T1"),
            _make_payload(sheet_name="Costs", table_name="T2"),
            _make_payload(sheet_name="Summary", table_name="T3"),
        ]
        output = self._run(payloads, sheet="all")
        # All three H2 headings must be present in order.
        pos_sales = output.index("## Sales")
        pos_costs = output.index("## Costs")
        pos_summary = output.index("## Summary")
        self.assertLess(pos_sales, pos_costs)
        self.assertLess(pos_costs, pos_summary)

    def test_tc_unit_10_multi_table_h3_order(self) -> None:
        """TC-UNIT-10 — 2 named tables on 1 sheet → ### RevenueTable, ### CostsTable."""
        payloads = [
            _make_payload(sheet_name="Sheet1", table_name="RevenueTable"),
            _make_payload(sheet_name="Sheet1", table_name="CostsTable"),
        ]
        output = self._run(payloads, sheet="all")
        pos_rev = output.index("### RevenueTable")
        pos_costs = output.index("### CostsTable")
        self.assertLess(pos_rev, pos_costs)

    def test_tc_unit_11_single_sheet_mode_suppresses_h2(self) -> None:
        """TC-UNIT-11 — args.sheet != 'all' → no ## heading emitted."""
        payloads = [_make_payload(sheet_name="Sheet1", table_name="T1")]
        output = self._run(payloads, sheet="Sheet1")
        self.assertNotIn("## Sheet1", output)
        self.assertIn("### T1", output)

    def test_tc_unit_12_gfm_merges_require_policy_raises(self) -> None:
        """TC-UNIT-12 — format=gfm + merge + policy=fail → GfmMergesRequirePolicy."""
        # Row has None at col 1 (merge heuristic).
        payloads = [_make_payload(
            sheet_name="Sheet1",
            table_name="MergeTable",
            rows=[["anchor", None, "x"]],
        )]
        args = _args(format="gfm", gfm_merge_policy="fail", sheet="all")
        out = io.StringIO()
        with patch("xlsx2md.dispatch.iter_table_payloads", return_value=payloads):
            with self.assertRaises(GfmMergesRequirePolicy):
                emit_workbook_md(None, args, out)

    def test_tc_unit_13_gfm_merge_policy_duplicate_no_raise(self) -> None:
        """TC-UNIT-13 — format=gfm + merge + policy=duplicate → no raise."""
        payloads = [_make_payload(
            sheet_name="Sheet1",
            table_name="MergeTable",
            rows=[["anchor", None, "x"]],
        )]
        args = _args(format="gfm", gfm_merge_policy="duplicate", sheet="all")
        out = io.StringIO()
        with patch("xlsx2md.dispatch.iter_table_payloads", return_value=payloads):
            # Must complete without raising.
            result = emit_workbook_md(None, args, out)
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
# TC-UNIT-14: _gap_detect_label
# ---------------------------------------------------------------------------

class TestGapDetectLabel(unittest.TestCase):
    """TC-UNIT-14 — _gap_detect_label counter behaviour."""

    def test_tc_unit_14_counter_increments_per_sheet(self) -> None:
        """TC-UNIT-14 — counter resets on sheet change (separate dict key)."""
        state: dict[str, int] = {}
        # First sheet gets Table-1, Table-2.
        self.assertEqual(_gap_detect_label(state, "Alpha"), "Table-1")
        self.assertEqual(_gap_detect_label(state, "Alpha"), "Table-2")
        # Different sheet gets its own Table-1.
        self.assertEqual(_gap_detect_label(state, "Beta"), "Table-1")
        # Back to Alpha → continues from Table-3.
        self.assertEqual(_gap_detect_label(state, "Alpha"), "Table-3")
        # Beta still gets Table-2.
        self.assertEqual(_gap_detect_label(state, "Beta"), "Table-2")


# ---------------------------------------------------------------------------
# TC-UNIT-15: --no-split H3
# ---------------------------------------------------------------------------

class TestNoSplitH3(unittest.TestCase):
    """TC-UNIT-15 — unnamed region with no_split=True → ### Table-1 H3."""

    def test_tc_unit_15_no_split_emits_table_1_h3(self) -> None:
        """TC-UNIT-15 — region.name=None with no_split → ### Table-1 in output."""
        # Unnamed region (gap_detect / whole-sheet mode).
        payloads = [_make_payload(
            sheet_name="Sheet1",
            table_name=None,  # no name → gap_detect_label path
        )]
        args = _args(no_split=True, sheet="all")
        out = io.StringIO()
        with patch("xlsx2md.dispatch.iter_table_payloads", return_value=payloads):
            result = emit_workbook_md(None, args, out)
        self.assertEqual(result, 0)
        content = out.getvalue()
        self.assertIn("### Table-1", content)


if __name__ == "__main__":
    unittest.main()
