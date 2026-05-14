"""Unit tests for xlsx2md/emit_html.py — HTML table emitter (012-05).

14 tests (TC-UNIT-01..14); TC-UNIT-02/03/04 skipped — body
colspan/rowspan deferred to 012-08 (needs xlsx_read merge-span API).

Test groups:
1.  TC-UNIT-01 — single-row header + simple body.
2.  TC-UNIT-02 — horizontal merge colspan anchor    [SKIP: 012-08]
3.  TC-UNIT-03 — horizontal merge child suppressed  [SKIP: 012-08]
4.  TC-UNIT-04 — vertical merge rowspan anchor      [SKIP: 012-08]
5.  TC-UNIT-05 — data-formula attr emitted.
6.  TC-UNIT-06 — stale-cache class on empty formula cell.
7.  TC-UNIT-07 — newline → <br> in cell.
8.  TC-UNIT-08 — hyperlink <a href> form.
9.  TC-UNIT-09 — hyperlink blocked-scheme → text only.
10. TC-UNIT-10 — html escape <script> → &lt;script&gt;.
11. TC-UNIT-11 — thead multi-row with colspan.
12. TC-UNIT-12 — synthetic thead when headerRowCount=0.
13. TC-UNIT-13 — attribute escape " in href → &quot;.
14. TC-UNIT-14 — attribute escape in data-formula.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from xlsx_read import TableData, TableRegion
from xlsx2md.emit_html import (
    _build_td_attrs,
    _emit_thead,
    _format_cell_html,
    emit_html_table,
)

_DEFAULT_SCHEMES = frozenset({"http", "https", "mailto"})

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_region(
    sheet: str = "Sheet1",
    top_row: int = 1,
    left_col: int = 1,
    bottom_row: int = 3,
    right_col: int = 2,
    source: str = "gap_detect",
    name: str | None = None,
    listobject_header_row_count: int | None = None,
) -> TableRegion:
    kwargs: dict = dict(
        sheet=sheet,
        top_row=top_row,
        left_col=left_col,
        bottom_row=bottom_row,
        right_col=right_col,
        source=source,
        name=name,
    )
    if listobject_header_row_count is not None:
        kwargs["listobject_header_row_count"] = listobject_header_row_count
    return TableRegion(**kwargs)


def _make_table(
    headers: list[str],
    rows: list[list],
    region: TableRegion | None = None,
) -> TableData:
    if region is None:
        n_cols = len(headers)
        n_rows = len(rows) + 1  # 1 header + body rows
        region = _make_region(right_col=n_cols, bottom_row=n_rows)
    return TableData(region=region, headers=headers, rows=rows)


def _emit(table_data: TableData, **kwargs) -> str:
    """Call emit_html_table and return the output as a string."""
    out = io.StringIO()
    kwargs.setdefault("hyperlink_allowlist", _DEFAULT_SCHEMES)
    emit_html_table(table_data, out, **kwargs)
    return out.getvalue()


# ---------------------------------------------------------------------------
# TC-UNIT-01 — single-row header + simple body
# ---------------------------------------------------------------------------


class TestEmitHtmlBasic(unittest.TestCase):
    """TC-UNIT-01 — basic HTML output shape."""

    def test_single_row_header_simple_body(self) -> None:
        """TC-UNIT-01: single header row + 2 data rows → correct HTML skeleton."""
        td = _make_table(
            headers=["Name", "Score"],
            rows=[["Alice", 90], ["Bob", 85]],
        )
        out = _emit(td)
        self.assertIn("<table>", out)
        self.assertIn("</table>", out)
        self.assertIn("<thead>", out)
        self.assertIn("</thead>", out)
        self.assertIn("<tbody>", out)
        self.assertIn("</tbody>", out)
        # Headers
        self.assertIn("<th>Name</th>", out)
        self.assertIn("<th>Score</th>", out)
        # Body rows
        self.assertIn("<td>Alice</td>", out)
        self.assertIn("<td>90</td>", out)
        self.assertIn("<td>Bob</td>", out)
        self.assertIn("<td>85</td>", out)
        # Structure order
        thead_pos = out.index("<thead>")
        tbody_pos = out.index("<tbody>")
        self.assertLess(thead_pos, tbody_pos)

    def test_empty_body_emits_thead_only(self) -> None:
        """No body rows → <thead> emitted, <tbody> present but empty."""
        td = _make_table(headers=["Col"], rows=[])
        out = _emit(td)
        self.assertIn("<thead>", out)
        self.assertIn("<th>Col</th>", out)
        self.assertIn("<tbody>\n</tbody>", out)

    def test_table_wrapper_lines(self) -> None:
        """<table> on its own line followed by </table>\\n."""
        td = _make_table(headers=["X"], rows=[["v"]])
        out = _emit(td)
        self.assertTrue(out.startswith("<table>\n"))
        self.assertTrue(out.endswith("</table>\n"))


# ---------------------------------------------------------------------------
# TC-UNIT-02, 03, 04 — body merge colspan/rowspan (DEFERRED)
# ---------------------------------------------------------------------------


class TestBodyMergesDeferredToXlsx10B(unittest.TestCase):
    """TC-UNIT-02/03/04: body colspan/rowspan deferred to 012-08.

    TableData has no merge-span attribute (xlsx-10.A frozen API).
    Accurate body colspan/rowspan requires reader.merges_in_region()
    which is not in xlsx_read public API. See module docstring for
    honest-scope note.
    """

    @unittest.skip(
        "colspan/rowspan body merges deferred — needs xlsx_read API extension "
        "for merge spans; see TODO 012-08"
    )
    def test_emit_html_horizontal_merge_colspan_anchor(self) -> None:
        """TC-UNIT-02: anchor cell emits <td colspan="2">."""
        pass  # TODO 012-08

    @unittest.skip(
        "colspan/rowspan body merges deferred — needs xlsx_read API extension "
        "for merge spans; see TODO 012-08"
    )
    def test_emit_html_horizontal_merge_child_cell_suppressed(self) -> None:
        """TC-UNIT-03: child cell is omitted from the <tr>."""
        pass  # TODO 012-08

    @unittest.skip(
        "colspan/rowspan body merges deferred — needs xlsx_read API extension "
        "for merge spans; see TODO 012-08"
    )
    def test_emit_html_vertical_merge_rowspan_anchor(self) -> None:
        """TC-UNIT-04: anchor cell emits <td rowspan="N">."""
        pass  # TODO 012-08


# ---------------------------------------------------------------------------
# TC-UNIT-05 — data-formula attr
# ---------------------------------------------------------------------------


class TestDataFormulaAttr(unittest.TestCase):
    """TC-UNIT-05: data-formula attr emitted via _format_cell_html side-channel."""

    def test_data_formula_attr_emitted(self) -> None:
        """TC-UNIT-05: formula kwarg produces data-formula attribute."""
        result = _format_cell_html(
            42,
            formula="=A3+B3",
            include_formulas=True,
        )
        self.assertIn('data-formula="=A3+B3"', result)
        self.assertIn("42", result)

    def test_no_data_formula_when_include_formulas_false(self) -> None:
        """No data-formula attr when include_formulas=False."""
        result = _format_cell_html(
            42,
            formula="=A3+B3",
            include_formulas=False,
        )
        self.assertNotIn("data-formula", result)
        self.assertIn("42", result)

    def test_no_data_formula_when_formula_none(self) -> None:
        """No data-formula attr when formula=None even if include_formulas=True."""
        result = _format_cell_html(
            99,
            formula=None,
            include_formulas=True,
        )
        self.assertNotIn("data-formula", result)


# ---------------------------------------------------------------------------
# TC-UNIT-06 — stale-cache class
# ---------------------------------------------------------------------------


class TestStaleCacheClass(unittest.TestCase):
    """TC-UNIT-06: class="stale-cache" on formula cell with no cached value."""

    def test_stale_cache_class_on_empty_formula_cell(self) -> None:
        """TC-UNIT-06: value=None + formula → class="stale-cache"."""
        result = _format_cell_html(
            None,
            formula="=A3*B3",
            include_formulas=True,
        )
        self.assertIn('class="stale-cache"', result)
        self.assertIn('data-formula="=A3*B3"', result)

    def test_no_stale_cache_when_value_present(self) -> None:
        """No stale-cache class when value is not None."""
        result = _format_cell_html(
            42,
            formula="=A3+B3",
            include_formulas=True,
        )
        self.assertNotIn("stale-cache", result)


# ---------------------------------------------------------------------------
# TC-UNIT-07 — newline → <br>
# ---------------------------------------------------------------------------


class TestNewlineToBr(unittest.TestCase):
    """TC-UNIT-07: newline in cell text → <br>."""

    def test_newline_to_br_in_cell(self) -> None:
        """TC-UNIT-07: newline character in cell value → <br> in HTML output."""
        td = _make_table(
            headers=["Notes"],
            rows=[["line one\nline two"]],
        )
        out = _emit(td)
        self.assertIn("line one<br>line two", out)

    def test_no_br_when_no_newline(self) -> None:
        """No <br> when cell has no newline."""
        td = _make_table(headers=["Col"], rows=[["no newline here"]])
        out = _emit(td)
        self.assertNotIn("<br>", out)


# ---------------------------------------------------------------------------
# TC-UNIT-08 — hyperlink <a href> form
# ---------------------------------------------------------------------------


class TestHyperlinkAnchorTag(unittest.TestCase):
    """TC-UNIT-08: hyperlink → <a href="...">text</a>."""

    def test_hyperlink_anchor_tag_form(self) -> None:
        """TC-UNIT-08: hyperlinks_map produces <a href="..."> in output."""
        td = _make_table(
            headers=["Link"],
            rows=[["Click here"]],
        )
        # Region: 1 header row + 1 body row → top_row=1, bottom_row=2.
        # header_band = max(0, total_rows - len(rows)) = max(0, 2-1) = 1.
        # hyperlinks_map key for body row 0, col 0 = (header_band + 0, 0) = (1, 0).
        region = _make_region(top_row=1, bottom_row=2, right_col=1)
        td2 = TableData(region=region, headers=["Link"], rows=[["Click here"]])
        out = _emit(
            td2,
            hyperlinks_map={(1, 0): "https://example.com"},
        )
        self.assertIn('<a href="https://example.com">Click here</a>', out)

    def test_no_hyperlink_when_map_empty(self) -> None:
        """No <a> when hyperlinks_map is empty."""
        td = _make_table(headers=["Link"], rows=[["plain text"]])
        out = _emit(td, hyperlinks_map={})
        self.assertNotIn("<a ", out)


# ---------------------------------------------------------------------------
# TC-UNIT-09 — blocked scheme → text only
# ---------------------------------------------------------------------------


class TestHyperlinkBlockedScheme(unittest.TestCase):
    """TC-UNIT-09: blocked scheme → plain text only, no <a href>."""

    def test_blocked_scheme_emits_text_only(self) -> None:
        """TC-UNIT-09: javascript: scheme blocked → plain text in <td>."""
        import warnings
        region = _make_region(top_row=1, bottom_row=2, right_col=1)
        td = TableData(region=region, headers=["Link"], rows=[["bad link"]])
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            out = _emit(
                td,
                hyperlinks_map={(1, 0): "javascript:alert(1)"},
                hyperlink_allowlist=frozenset({"http", "https"}),
            )
        self.assertNotIn("<a ", out)
        self.assertIn("bad link", out)
        self.assertTrue(any("javascript" in str(w.message) for w in ws))


# ---------------------------------------------------------------------------
# TC-UNIT-10 — html escape <script>
# ---------------------------------------------------------------------------


class TestHtmlEscapeInCellText(unittest.TestCase):
    """TC-UNIT-10: HTML special chars in cell text are escaped."""

    def test_lt_gt_escaped_in_cell(self) -> None:
        """TC-UNIT-10: <script> literal → &lt;script&gt; in output."""
        td = _make_table(
            headers=["Code"],
            rows=[["<script>alert(1)</script>"]],
        )
        out = _emit(td)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out)

    def test_ampersand_escaped(self) -> None:
        """& in cell text → &amp;."""
        td = _make_table(headers=["Text"], rows=[["A & B"]])
        out = _emit(td)
        self.assertIn("A &amp; B", out)


# ---------------------------------------------------------------------------
# TC-UNIT-11 — thead multi-row with colspan
# ---------------------------------------------------------------------------


class TestTheadMultiRowColspan(unittest.TestCase):
    """TC-UNIT-11: multi-row <thead> with colspan for banner row."""

    def test_thead_two_row_with_colspan(self) -> None:
        """TC-UNIT-11: 2-level header → 2 <tr>; banner <th> has colspan=3."""
        td = _make_table(
            headers=[
                "2026 plan › Q1",
                "2026 plan › Q2",
                "2026 plan › Q3",
            ],
            rows=[["100", "200", "300"]],
        )
        out = _emit(td)
        # Two <tr> in <thead>
        thead_start = out.index("<thead>")
        thead_end = out.index("</thead>")
        thead_block = out[thead_start:thead_end]
        self.assertEqual(thead_block.count("<tr>"), 2)
        # Banner row has colspan=3
        self.assertIn('<th colspan="3">2026 plan</th>', out)
        # Leaf row has Q1, Q2, Q3
        self.assertIn("<th>Q1</th>", out)
        self.assertIn("<th>Q2</th>", out)
        self.assertIn("<th>Q3</th>", out)

    def test_thead_mixed_banner_groups(self) -> None:
        """Two different banner groups each with colspan=2."""
        headers = [
            "A › X",
            "A › Y",
            "B › X",
            "B › Y",
        ]
        td = _make_table(headers=headers, rows=[])
        out = _emit(td)
        self.assertIn('<th colspan="2">A</th>', out)
        self.assertIn('<th colspan="2">B</th>', out)
        # Suppressed positions should not appear as separate <th> in banner row
        # Count occurrences of banner-level <th> for A and B
        # Banner row should have exactly 2 <th> cells (one per group)
        thead_start = out.index("<thead>")
        thead_end = out.index("</thead>")
        thead_block = out[thead_start:thead_end]
        rows_in_thead = thead_block.count("<tr>")
        self.assertEqual(rows_in_thead, 2)


# ---------------------------------------------------------------------------
# TC-UNIT-12 — synthetic thead (headerRowCount=0)
# ---------------------------------------------------------------------------


class TestSyntheticThead(unittest.TestCase):
    """TC-UNIT-12: D13 lock — headerRowCount=0 → <thead> with col_1..col_N."""

    def test_synthetic_thead_when_header_row_count_zero(self) -> None:
        """TC-UNIT-12: synthetic col_1..col_2 headers still emit <thead>."""
        region = _make_region(
            top_row=1,
            bottom_row=3,
            right_col=2,
            source="listobject",
            listobject_header_row_count=0,
        )
        td = TableData(
            region=region,
            headers=["col_1", "col_2"],
            rows=[["val1", "val2"]],
        )
        out = _emit(td)
        self.assertIn("<thead>", out)
        self.assertIn("<th>col_1</th>", out)
        self.assertIn("<th>col_2</th>", out)

    def test_synthetic_thead_no_colspan_attrs(self) -> None:
        """Synthetic (single-row) headers have no colspan attribute."""
        region = _make_region(source="listobject", listobject_header_row_count=0)
        td = TableData(
            region=region,
            headers=["col_1", "col_2"],
            rows=[],
        )
        out = _emit(td)
        self.assertNotIn("colspan", out)


# ---------------------------------------------------------------------------
# TC-UNIT-13 — attribute escape " in href → &quot;
# ---------------------------------------------------------------------------


class TestAttributeEscapeHref(unittest.TestCase):
    """TC-UNIT-13: double-quote in href → &quot;."""

    def test_double_quote_in_href_escaped(self) -> None:
        """TC-UNIT-13: href containing " → &quot; in <a href> attribute."""
        import warnings
        region = _make_region(top_row=1, bottom_row=2, right_col=1)
        td = TableData(
            region=region,
            headers=["Link"],
            rows=[["Text"]],
        )
        # URL with double-quote (unusual but must be escaped)
        bad_href = 'https://example.com/path?q="value"'
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            out = _emit(
                td,
                hyperlinks_map={(1, 0): bad_href},
                hyperlink_allowlist=None,  # allow all
            )
        self.assertNotIn('href="https://example.com/path?q="value"', out)
        self.assertIn("&quot;", out)


# ---------------------------------------------------------------------------
# TC-UNIT-14 — attribute escape in data-formula
# ---------------------------------------------------------------------------


class TestAttributeEscapeDataFormula(unittest.TestCase):
    """TC-UNIT-14: double-quote in formula → &quot; in data-formula attr."""

    def test_double_quote_in_formula_escaped(self) -> None:
        """TC-UNIT-14: formula with " → &quot; in data-formula attribute."""
        result = _format_cell_html(
            "result",
            formula='=CONCATENATE(A1,"hello")',
            include_formulas=True,
        )
        self.assertIn("&quot;", result)
        self.assertNotIn('data-formula="=CONCATENATE(A1,"', result)

    def test_lt_gt_in_formula_escaped(self) -> None:
        """< and > in formula → &lt;&gt; in data-formula attribute."""
        result = _format_cell_html(
            1,
            formula="=IF(A1<B1,1,0)",
            include_formulas=True,
        )
        self.assertIn("&lt;", result)


# ---------------------------------------------------------------------------
# TC-UNIT-BONUS — _build_td_attrs helper
# ---------------------------------------------------------------------------


class TestBuildTdAttrs(unittest.TestCase):
    """Extra tests for _build_td_attrs internals."""

    def test_empty_attrs_for_plain_cell(self) -> None:
        """Plain cell: no formula, no colspan → empty string."""
        attrs = _build_td_attrs(value="x", formula=None, include_formulas=False)
        self.assertEqual(attrs, "")

    def test_colspan_attr(self) -> None:
        """colspan > 1 → colspan attr prepended."""
        attrs = _build_td_attrs(
            value="x", formula=None, include_formulas=False, colspan=3
        )
        self.assertEqual(attrs, ' colspan="3"')

    def test_rowspan_attr(self) -> None:
        """rowspan > 1 → rowspan attr prepended."""
        attrs = _build_td_attrs(
            value="x", formula=None, include_formulas=False, rowspan=2
        )
        self.assertEqual(attrs, ' rowspan="2"')

    def test_colspan_and_rowspan_combined(self) -> None:
        """colspan + rowspan → both attrs present."""
        attrs = _build_td_attrs(
            value="x", formula=None, include_formulas=False, colspan=2, rowspan=3
        )
        self.assertIn('colspan="2"', attrs)
        self.assertIn('rowspan="3"', attrs)


if __name__ == "__main__":
    unittest.main()
