"""Unit tests for :mod:`xlsx2csv2json.dispatch` (010-04).

Covers ``iter_table_payloads`` (reader-glue trampoline) and
``_resolve_tables_mode`` (4→3 enum mapping).
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _args(**overrides) -> argparse.Namespace:
    """Default Namespace matching cli.build_parser defaults."""
    base = dict(
        sheet="all",
        include_hidden=False,
        header_rows=1,
        header_flatten_style="string",
        merge_policy="anchor-only",
        tables="whole",
        gap_rows=2,
        gap_cols=1,
        include_hyperlinks=False,
        include_formulas=False,
        datetime_format="ISO",
        output=None,
        output_flag=None,
        output_dir=None,
        json_errors=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ===========================================================================
# _resolve_tables_mode
# ===========================================================================
class TestResolveTablesMode(unittest.TestCase):

    def test_whole(self) -> None:
        from xlsx2csv2json.dispatch import _resolve_tables_mode
        mode, pred = _resolve_tables_mode("whole")
        self.assertEqual(mode, "whole")
        self.assertTrue(pred(_FakeRegion("listobject")))
        self.assertTrue(pred(_FakeRegion("gap_detect")))

    def test_listobjects(self) -> None:
        from xlsx2csv2json.dispatch import _resolve_tables_mode
        mode, pred = _resolve_tables_mode("listobjects")
        self.assertEqual(mode, "tables-only")
        # Library mode `tables-only` returns Tier-1 + Tier-2 together;
        # the predicate accepts all (Tier-2 named ranges silently
        # bundled per TASK §1.4 (l)).
        self.assertTrue(pred(_FakeRegion("listobject")))
        self.assertTrue(pred(_FakeRegion("named_range")))

    def test_gap_filter(self) -> None:
        from xlsx2csv2json.dispatch import _resolve_tables_mode
        mode, pred = _resolve_tables_mode("gap")
        self.assertEqual(mode, "auto")
        self.assertTrue(pred(_FakeRegion("gap_detect")))
        self.assertFalse(pred(_FakeRegion("listobject")))
        self.assertFalse(pred(_FakeRegion("named_range")))

    def test_auto(self) -> None:
        from xlsx2csv2json.dispatch import _resolve_tables_mode
        mode, pred = _resolve_tables_mode("auto")
        self.assertEqual(mode, "auto")
        self.assertTrue(pred(_FakeRegion("listobject")))
        self.assertTrue(pred(_FakeRegion("gap_detect")))

    def test_unknown_raises(self) -> None:
        from xlsx2csv2json.dispatch import _resolve_tables_mode
        with self.assertRaises(ValueError):
            _resolve_tables_mode("bogus")


class _FakeRegion:
    def __init__(self, source: str):
        self.source = source


# ===========================================================================
# iter_table_payloads — driven through real xlsx_read via fixtures
# ===========================================================================
class TestIterTablePayloads(unittest.TestCase):

    def _open(self, fixture: str):
        from xlsx_read import open_workbook
        return open_workbook(_FIXTURES / fixture)

    def test_single_sheet_whole_yields_one_triple(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("single_sheet_simple.xlsx") as reader:
            triples = list(iter_table_payloads(_args(), reader, format="json"))
        self.assertEqual(len(triples), 1)
        sheet, region, data, hl = triples[0]
        self.assertEqual(sheet, "Data")
        self.assertEqual(region.source, "gap_detect")  # whole mode → 1 region
        self.assertEqual(data.headers, ["id", "name", "score"])
        self.assertEqual(len(data.rows), 3)
        self.assertIsNone(hl)

    def test_multi_sheet_all_visible(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("two_sheets_simple.xlsx") as reader:
            triples = list(iter_table_payloads(_args(), reader, format="json"))
        names = [t[0] for t in triples]
        self.assertEqual(names, ["SheetA", "SheetB"])

    def test_hidden_sheet_skipped_by_default(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("hidden_sheet.xlsx") as reader:
            triples = list(iter_table_payloads(_args(), reader, format="json"))
        names = [t[0] for t in triples]
        self.assertEqual(names, ["Visible"])

    def test_include_hidden_yields_all(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("hidden_sheet.xlsx") as reader:
            triples = list(iter_table_payloads(_args(include_hidden=True), reader, format="json"))
        names = [t[0] for t in triples]
        self.assertEqual(sorted(names), ["HiddenOne", "VeryHiddenOne", "Visible"])

    def test_sheet_named_filter(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("two_sheets_simple.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(sheet="SheetB"), reader, format="json"
            ))
        names = [t[0] for t in triples]
        self.assertEqual(names, ["SheetB"])

    def test_sheet_not_found(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        from xlsx_read import SheetNotFound
        with self._open("two_sheets_simple.xlsx") as reader:
            with self.assertRaises(SheetNotFound):
                list(iter_table_payloads(
                    _args(sheet="DoesNotExist"), reader, format="json"
                ))

    def test_listobjects_mode_two_tables(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        # When tables != whole, header_rows must be "auto" (H3 rule);
        # cli._validate_flag_combo enforces this, but we set it manually
        # at the dispatch-test level.
        with self._open("multi_table_listobjects.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(tables="listobjects", header_rows="auto", output_dir="/tmp/ignore"),
                reader,
                format="json",
            ))
        regions = [(t[0], t[1].name, t[1].source) for t in triples]
        # Expect 2 regions on 1 sheet, both listobject source.
        self.assertEqual(len(regions), 2)
        for _, _, source in regions:
            self.assertEqual(source, "listobject")
        names = {r[1] for r in regions}
        self.assertEqual(names, {"RevenueTable", "CostsTable"})

    def test_gap_mode_filters_out_listobjects(self) -> None:
        """gap mode → only gap_detect regions yielded.

        The multi_table_listobjects fixture has 2 ListObjects; in gap
        mode, the library returns auto (which yields ListObjects) but
        our post-filter strips them. Expected: 0 regions.
        """
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("multi_table_listobjects.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(tables="gap", header_rows="auto"),
                reader,
                format="json",
            ))
        self.assertEqual(len(triples), 0)

    def test_csv_multi_region_without_output_dir_raises(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        from xlsx2csv2json import MultiTableRequiresOutputDir
        with self._open("multi_table_listobjects.xlsx") as reader:
            with self.assertRaises(MultiTableRequiresOutputDir):
                list(iter_table_payloads(
                    _args(tables="listobjects", header_rows="auto"),
                    reader,
                    format="csv",
                ))

    def test_csv_multi_sheet_without_output_dir_raises(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        from xlsx2csv2json import MultiSheetRequiresOutputDir
        with self._open("two_sheets_simple.xlsx") as reader:
            with self.assertRaises(MultiSheetRequiresOutputDir):
                list(iter_table_payloads(_args(), reader, format="csv"))

    def test_csv_multi_sheet_with_output_dir_ok(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("two_sheets_simple.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(output_dir="/tmp/out"), reader, format="csv"
            ))
        self.assertEqual(len(triples), 2)

    def test_csv_single_sheet_no_output_dir_ok(self) -> None:
        """A single visible sheet does NOT need --output-dir for CSV."""
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("single_sheet_simple.xlsx") as reader:
            triples = list(iter_table_payloads(_args(), reader, format="csv"))
        self.assertEqual(len(triples), 1)

    def test_hyperlinks_map_populated_when_opted_in(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("with_hyperlinks.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(include_hyperlinks=True), reader, format="json"
            ))
        self.assertEqual(len(triples), 1)
        _, _, _, hl = triples[0]
        self.assertIsNotNone(hl)
        # Headers are at row 0; hyperlinks are in data rows.
        # The fixture has hyperlinks at A2 and B3 (1-indexed).
        # Within region offsets (header at row 0; data starts at row 1):
        # A2 → (data_row 0, col 0); B3 → (data_row 1, col 1).
        # But the hyperlinks map is keyed by offset within the region
        # BEFORE header removal — region top is row 1 (A1), so:
        # A2 → (row_offset 1, col 0), B3 → (row_offset 2, col 1).
        self.assertIn((1, 0), hl)
        self.assertIn((2, 1), hl)
        self.assertEqual(hl[(1, 0)], "https://example.com/a")
        self.assertEqual(hl[(2, 1)], "https://example.com/b")

    def test_hyperlinks_map_none_when_off(self) -> None:
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("with_hyperlinks.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(include_hyperlinks=False), reader, format="json"
            ))
        _, _, _, hl = triples[0]
        self.assertIsNone(hl)

    def test_csv_subdir_validates_sheet_name(self) -> None:
        """When CSV subdir layout is active, sheet names get validated.

        The `special_char_sheet_name.xlsx` fixture has sheet name
        `"Q1 - Q2 split"` (only safe chars — `-` and space). Should
        pass.
        """
        from xlsx2csv2json.dispatch import iter_table_payloads
        with self._open("special_char_sheet_name.xlsx") as reader:
            triples = list(iter_table_payloads(
                _args(output_dir="/tmp/out"), reader, format="csv"
            ))
        self.assertEqual(len(triples), 1)


if __name__ == "__main__":
    unittest.main()
