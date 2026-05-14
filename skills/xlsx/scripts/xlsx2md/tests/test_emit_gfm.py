"""Unit tests for xlsx2md/emit_gfm.py — GFM emitter (012-04).

12 tests per TASK §5.2:
1.  TC-UNIT-01 — single-row header + 2 data rows (basic GFM output).
2.  TC-UNIT-02 — pipe escape in cell (| → \\|).
3.  TC-UNIT-03 — newline → <br> in cell.
4.  TC-UNIT-04 — hyperlink inline form [text](url) via hyperlink_href.
5.  TC-UNIT-05 — multi-row header (›) flatten + warning.
6.  TC-UNIT-06 — multi-row header emits warning to stderr.
7.  TC-UNIT-07 — synthetic header (col_1/col_2) visible row + separator.
8.  TC-UNIT-08 — merge-policy duplicate repeats anchor.
9.  TC-UNIT-09 — merge-policy blank leaves empty.
10. TC-UNIT-10 — separator row has correct column count.
11. TC-UNIT-11 — empty table body emits header + separator only.
12. TC-UNIT-12 — hyperlink blocked-scheme emits plain text.
"""
from __future__ import annotations

import io
import sys
import unittest
import warnings
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from xlsx_read import TableData, TableRegion
from xlsx2md.emit_gfm import (
    _apply_gfm_merge_policy,
    _emit_header_row_gfm,
    emit_gfm_table,
)

_DEFAULT_SCHEMES = frozenset({"http", "https", "mailto"})

# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def _make_region(
    sheet: str = "Sheet1",
    top_row: int = 1,
    left_col: int = 1,
    bottom_row: int = 3,
    right_col: int = 2,
    name: str | None = None,
) -> TableRegion:
    return TableRegion(
        sheet=sheet,
        top_row=top_row,
        left_col=left_col,
        bottom_row=bottom_row,
        right_col=right_col,
        source="gap_detect",
        name=name,
    )


def _make_table(
    headers: list[str],
    rows: list[list],
    region: TableRegion | None = None,
) -> TableData:
    if region is None:
        region = _make_region(right_col=len(headers))
    return TableData(region=region, headers=headers, rows=rows)


def _emit(table_data: TableData, **kwargs) -> str:
    """Call emit_gfm_table and return the output as a string."""
    out = io.StringIO()
    kwargs.setdefault("hyperlink_allowlist", _DEFAULT_SCHEMES)
    emit_gfm_table(table_data, out, **kwargs)
    return out.getvalue()


# ---------------------------------------------------------------------------
# TC-UNIT-01 — single-row header + 2 data rows (basic)
# ---------------------------------------------------------------------------

class TestEmitGfmBasic(unittest.TestCase):
    """TC-UNIT-01 — basic GFM output shape."""

    def test_single_row_header_two_data_rows(self) -> None:
        td = _make_table(
            headers=["Name", "Score"],
            rows=[["Alice", 90], ["Bob", 85]],
        )
        output = _emit(td)
        lines = output.strip().splitlines()
        self.assertEqual(len(lines), 4, f"Expected 4 lines; got:\n{output!r}")
        # Header row
        self.assertEqual(lines[0], "| Name | Score |")
        # Separator row
        self.assertIn("---", lines[1])
        # Data rows
        self.assertIn("Alice", lines[2])
        self.assertIn("Bob", lines[3])

    def test_header_pipe_present_in_output(self) -> None:
        td = _make_table(headers=["A", "B"], rows=[["x", "y"]])
        output = _emit(td)
        self.assertTrue(output.startswith("| A | B |"))


# ---------------------------------------------------------------------------
# TC-UNIT-02 — pipe escape in cell
# ---------------------------------------------------------------------------

class TestEmitGfmPipeEscape(unittest.TestCase):
    """TC-UNIT-02 — | in cell → \\|."""

    def test_pipe_escaped_in_body(self) -> None:
        td = _make_table(
            headers=["Col"],
            rows=[["a|b|c"]],
        )
        output = _emit(td)
        # The pipe characters inside the cell should be escaped.
        self.assertIn(r"a\|b\|c", output)

    def test_pipe_escaped_in_header(self) -> None:
        td = _make_table(
            headers=["Col|Header"],
            rows=[["data"]],
        )
        output = _emit(td)
        lines = output.splitlines()
        self.assertIn(r"Col\|Header", lines[0])


# ---------------------------------------------------------------------------
# TC-UNIT-03 — newline → <br> in cell
# ---------------------------------------------------------------------------

class TestEmitGfmNewlineToBr(unittest.TestCase):
    """TC-UNIT-03 — \\n in cell → <br>."""

    def test_newline_replaced_with_br(self) -> None:
        td = _make_table(
            headers=["Text"],
            rows=[["first\nsecond"]],
        )
        output = _emit(td)
        self.assertIn("first<br>second", output)

    def test_multiple_newlines(self) -> None:
        td = _make_table(
            headers=["Multi"],
            rows=[["a\nb\nc"]],
        )
        output = _emit(td)
        self.assertIn("a<br>b<br>c", output)


# ---------------------------------------------------------------------------
# TC-UNIT-04 — hyperlink inline form via hyperlink_href
# ---------------------------------------------------------------------------

class TestEmitGfmHyperlinkInlineForm(unittest.TestCase):
    """TC-UNIT-04 — hyperlink [text](url) when hyperlink_href provided.

    Since _build_hyperlinks_map always returns {} (current xlsx_read API),
    we test this path by using render_cell_value directly with hyperlink_href.
    The emit-side path uses _build_hyperlinks_map; this TC verifies the
    inline module is wired correctly by testing render_cell_value with href.
    """

    def test_render_cell_value_with_href(self) -> None:
        """render_cell_value with hyperlink_href produces [text](url)."""
        from xlsx2md.inline import render_cell_value

        result = render_cell_value(
            "click me",
            mode="gfm",
            hyperlink_href="https://example.com",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[click me](https://example.com)")

    def test_body_row_with_url_as_plain_value(self) -> None:
        """URLs in body rows emitted as plain text (current API: URL=cell value)."""
        td = _make_table(
            headers=["URL"],
            rows=[["https://example.com"]],
        )
        output = _emit(td)
        # URL is emitted as plain text (no link wrapper) since no href map.
        self.assertIn("https://example.com", output)


# ---------------------------------------------------------------------------
# TC-UNIT-05 — multi-row header flatten with › + warning
# ---------------------------------------------------------------------------

class TestEmitGfmMultiRowHeaderFlatten(unittest.TestCase):
    """TC-UNIT-05 — multi-row headers (›) pass through with warning."""

    def test_multi_row_header_preserved_in_output(self) -> None:
        td = _make_table(
            headers=["2026 plan › Q1", "2026 plan › Q2", "2026 plan › Q3"],
            rows=[["10", "20", "30"]],
            region=_make_region(right_col=3),
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            output = _emit(td)
        # The › separator must appear in the header row.
        lines = output.splitlines()
        self.assertIn("›", lines[0])

    def test_separator_row_has_three_columns(self) -> None:
        td = _make_table(
            headers=["2026 plan › Q1", "2026 plan › Q2", "2026 plan › Q3"],
            rows=[["1", "2", "3"]],
            region=_make_region(right_col=3),
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            output = _emit(td)
        lines = output.splitlines()
        sep = lines[1]
        self.assertEqual(sep.count("---"), 3)


# ---------------------------------------------------------------------------
# TC-UNIT-06 — multi-row header warning emitted
# ---------------------------------------------------------------------------

class TestEmitGfmMultiRowHeaderWarning(unittest.TestCase):
    """TC-UNIT-06 — multi-row header triggers UserWarning."""

    def test_multi_row_header_emits_userwarning(self) -> None:
        td = _make_table(
            headers=["A › B", "C › D"],
            rows=[["1", "2"]],
            region=_make_region(right_col=2),
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _emit(td)
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            len(user_warnings) >= 1,
            "Expected UserWarning for multi-row header",
        )
        texts = [str(w.message) for w in user_warnings]
        self.assertTrue(
            any("multi-row header" in t or "flatten" in t.lower() for t in texts),
            f"Expected 'multi-row header' in warning; got {texts!r}",
        )

    def test_single_row_header_no_warning(self) -> None:
        td = _make_table(headers=["Name", "Value"], rows=[["a", "1"]])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _emit(td)
        gfm_warnings = [
            w for w in caught
            if issubclass(w.category, UserWarning)
            and "multi-row" in str(w.message)
        ]
        self.assertEqual(len(gfm_warnings), 0)


# ---------------------------------------------------------------------------
# TC-UNIT-07 — synthetic header (col_1/col_2) visible row + separator
# ---------------------------------------------------------------------------

class TestEmitGfmSyntheticHeader(unittest.TestCase):
    """TC-UNIT-07 — synthetic headers (col_N) are emitted as visible header row."""

    def test_synthetic_headers_appear_in_output(self) -> None:
        td = _make_table(
            headers=["col_1", "col_2", "col_3"],
            rows=[["a", "b", "c"]],
            region=_make_region(right_col=3),
        )
        output = _emit(td)
        lines = output.splitlines()
        self.assertEqual(lines[0], "| col_1 | col_2 | col_3 |")
        # Separator must follow header.
        self.assertIn("---", lines[1])

    def test_synthetic_headers_separator_column_count(self) -> None:
        td = _make_table(
            headers=["col_1", "col_2"],
            rows=[["x", "y"]],
        )
        output = _emit(td)
        lines = output.splitlines()
        sep = lines[1]
        self.assertEqual(sep.count("---"), 2)


# ---------------------------------------------------------------------------
# TC-UNIT-08 — merge-policy duplicate repeats anchor
# ---------------------------------------------------------------------------

class TestEmitGfmMergePolicyDuplicate(unittest.TestCase):
    """TC-UNIT-08 — duplicate policy fills None with anchor value."""

    def test_duplicate_fills_none(self) -> None:
        rows = [["Total", None, None]]
        result = _apply_gfm_merge_policy(rows, None, "duplicate")
        self.assertEqual(result, [["Total", "Total", "Total"]])

    def test_duplicate_emits_warning(self) -> None:
        rows = [["A", None]]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _apply_gfm_merge_policy(rows, None, "duplicate")
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            len(user_warnings) >= 1,
            "Expected UserWarning for duplicate policy",
        )

    def test_duplicate_no_none_no_warning(self) -> None:
        rows = [["A", "B"]]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _apply_gfm_merge_policy(rows, None, "duplicate")
        self.assertEqual(result, [["A", "B"]])
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertEqual(len(user_warnings), 0)

    def test_duplicate_via_emit_gfm_table(self) -> None:
        """duplicate policy wired through emit_gfm_table."""
        td = _make_table(
            headers=["Value", "Merged"],
            rows=[["Total", None]],
        )
        output = _emit(td, gfm_merge_policy="duplicate")
        lines = output.splitlines()
        # Body row must contain "Total" twice.
        body = lines[2]
        self.assertEqual(body.count("Total"), 2, f"Body: {body!r}")


# ---------------------------------------------------------------------------
# TC-UNIT-09 — merge-policy blank leaves empty
# ---------------------------------------------------------------------------

class TestEmitGfmMergePolicyBlank(unittest.TestCase):
    """TC-UNIT-09 — blank policy leaves None cells as empty string."""

    def test_blank_policy_rows_unchanged(self) -> None:
        rows = [["Total", None, None]]
        result = _apply_gfm_merge_policy(rows, None, "blank")
        # Rows are structurally the same (None stays None, rendered as "").
        self.assertEqual(result, [["Total", None, None]])

    def test_blank_emits_warning_when_none_present(self) -> None:
        rows = [["A", None]]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _apply_gfm_merge_policy(rows, None, "blank")
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(len(user_warnings) >= 1)

    def test_blank_policy_none_renders_as_empty_in_output(self) -> None:
        td = _make_table(
            headers=["Value", "Merged"],
            rows=[["Total", None]],
        )
        output = _emit(td, gfm_merge_policy="blank")
        lines = output.splitlines()
        body = lines[2]
        # The cell with None should render as empty between pipes.
        self.assertIn("|  |", body, f"Expected empty cell; body: {body!r}")


# ---------------------------------------------------------------------------
# TC-UNIT-10 — separator row has correct column count
# ---------------------------------------------------------------------------

class TestEmitGfmSeparatorColumnCount(unittest.TestCase):
    """TC-UNIT-10 — separator row has same column count as headers."""

    def test_separator_matches_3_columns(self) -> None:
        out = io.StringIO()
        _emit_header_row_gfm(["A", "B", "C"], out)
        lines = out.getvalue().splitlines()
        sep = lines[1]
        self.assertEqual(sep.count("---"), 3)

    def test_separator_matches_1_column(self) -> None:
        out = io.StringIO()
        _emit_header_row_gfm(["Single"], out)
        lines = out.getvalue().splitlines()
        sep = lines[1]
        self.assertEqual(sep.count("---"), 1)

    def test_separator_via_emit_gfm_table(self) -> None:
        td = _make_table(
            headers=["X", "Y", "Z", "W"],
            rows=[["1", "2", "3", "4"]],
            region=_make_region(right_col=4),
        )
        output = _emit(td)
        lines = output.splitlines()
        sep = lines[1]
        self.assertEqual(sep.count("---"), 4)


# ---------------------------------------------------------------------------
# TC-UNIT-11 — empty body emits header + separator only
# ---------------------------------------------------------------------------

class TestEmitGfmEmptyBody(unittest.TestCase):
    """TC-UNIT-11 — empty body (no data rows) → header + separator only."""

    def test_empty_body_two_lines_only(self) -> None:
        td = _make_table(headers=["Col1", "Col2"], rows=[])
        output = _emit(td)
        lines = output.strip().splitlines()
        self.assertEqual(len(lines), 2, f"Expected 2 lines; got:\n{output!r}")
        self.assertEqual(lines[0], "| Col1 | Col2 |")
        self.assertIn("---", lines[1])


# ---------------------------------------------------------------------------
# TC-UNIT-12 — hyperlink blocked-scheme emits plain text
# ---------------------------------------------------------------------------

class TestEmitGfmHyperlinkBlockedScheme(unittest.TestCase):
    """TC-UNIT-12 — blocked hyperlink scheme emits plain text (via render_cell_value)."""

    def test_blocked_scheme_plain_text(self) -> None:
        """render_cell_value with javascript: href + default allowlist → plain text."""
        from xlsx2md.inline import render_cell_value

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = render_cell_value(
                "click",
                mode="gfm",
                hyperlink_href="javascript:alert(1)",
                allowed_schemes=_DEFAULT_SCHEMES,
            )
        self.assertEqual(result, "click")
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            len(user_warnings) >= 1,
            "Expected UserWarning for blocked javascript: scheme",
        )

    def test_empty_allowlist_blocks_all_in_table(self) -> None:
        """frozenset() allowlist → all cells emitted as plain text."""
        from xlsx2md.inline import render_cell_value

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = render_cell_value(
                "safe link",
                mode="gfm",
                hyperlink_href="https://example.com",
                allowed_schemes=frozenset(),
            )
        self.assertEqual(result, "safe link")
        self.assertTrue(
            any(issubclass(w.category, UserWarning) for w in caught),
        )


class TestEmitGfmPathCprimeEndToEnd(unittest.TestCase):
    """Path C′ end-to-end: dispatch._extract_hyperlinks_for_region produces
    the href map; emit_gfm_table consumes it and renders ``[text](href)``.

    This is the user-visible proof that the Path C′ refactor delivers the
    contract TASK said it would (display text preserved, allowlist
    enforced at dispatch boundary).
    """

    _FIXTURES = (
        Path(__file__).resolve().parent / "fixtures"
    )

    def test_emit_gfm_table_with_real_hyperlinks_map(self) -> None:
        """Full Path C′ pipeline: real fixture → dispatch yields hl_map
        → emit_gfm_table produces ``[safe link](https://...)`` form.
        """
        from xlsx_read import open_workbook  # noqa: PLC0415
        from xlsx2md.dispatch import _extract_hyperlinks_for_region

        fixture = self._FIXTURES / "hyperlink_various_schemes.xlsx"
        with open_workbook(fixture) as reader:
            sheet_name = reader.sheets()[0].name
            regions = reader.detect_tables(sheet_name, mode="whole")
            self.assertEqual(len(regions), 1)
            region = regions[0]
            # Path C′: include_hyperlinks=False so display text survives.
            table_data = reader.read_table(region, include_hyperlinks=False)
            # Parallel pass: extract hrefs via reader._wb, allowlist=*.
            hl_map = _extract_hyperlinks_for_region(
                reader, region, scheme_allowlist=None,
            )

        out = io.StringIO()
        emit_gfm_table(
            table_data, out,
            hyperlink_allowlist=None,  # allow-all sentinel
            hyperlinks_map=hl_map,
        )
        output = out.getvalue()
        # Path C′ delivers: display text in the visible markdown,
        # href in the parenthetical — the contract TASK promised.
        self.assertIn("[safe link](https://ok.example.com)", output)
        self.assertIn("[mail](mailto:x@y.example.com)", output)

    def test_emit_gfm_table_default_allowlist_blocks_javascript(self) -> None:
        """Path C′ + default allowlist: javascript: blocked at dispatch,
        cell renders as plain ``unsafe link`` (no ``[](javascript:...)``).
        """
        from xlsx_read import open_workbook  # noqa: PLC0415
        from xlsx2md.dispatch import _extract_hyperlinks_for_region

        fixture = self._FIXTURES / "hyperlink_various_schemes.xlsx"
        default_allowlist = frozenset({"http", "https", "mailto"})
        with open_workbook(fixture) as reader:
            sheet_name = reader.sheets()[0].name
            regions = reader.detect_tables(sheet_name, mode="whole")
            region = regions[0]
            table_data = reader.read_table(region, include_hyperlinks=False)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                hl_map = _extract_hyperlinks_for_region(
                    reader, region, scheme_allowlist=default_allowlist,
                )

        # javascript: dropped from the map at dispatch boundary.
        self.assertNotIn("javascript:alert(1)", hl_map.values())
        # Warning fired once for the blocked scheme.
        blocked_warnings = [
            w for w in caught
            if "disallowed scheme" in str(w.message) and "javascript" in str(w.message)
        ]
        self.assertEqual(len(blocked_warnings), 1)

        out = io.StringIO()
        emit_gfm_table(
            table_data, out,
            hyperlink_allowlist=default_allowlist,
            hyperlinks_map=hl_map,
        )
        output = out.getvalue()
        # https + mailto rendered as links; javascript: cell is plain text.
        self.assertIn("[safe link](https://ok.example.com)", output)
        self.assertIn("[mail](mailto:x@y.example.com)", output)
        self.assertNotIn("javascript:", output)
        # Display text for blocked cell survives as plain markdown.
        self.assertIn("unsafe link", output)


if __name__ == "__main__":
    unittest.main()
