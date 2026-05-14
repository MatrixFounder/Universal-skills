"""Dispatch library-glue tests for xlsx-9 (task 012-03).

All tests use a hand-written ``MockReader`` to avoid building real .xlsx
fixtures. Real fixtures land in 012-08 with the full E2E cluster.

Test classes and counts:
  - TestResolveReadOnlyMode   — 3 tests  (TC-UNIT-01..03)
  - TestDetectModeForArgs     — 3 tests  (TC-UNIT-04..06)
  - TestResolveHyperlinkAllowlist — 4 tests (TC-UNIT-07..10)
  - TestCoerceHeaderRows      — 3 tests  (internal)
  - TestIterTablePayloads     — 14 tests (TC-UNIT-11..24 + fixture pin)
Total: 27 tests (≥ 24 required).
"""
from __future__ import annotations

import argparse
import sys
import unittest
from unittest.mock import patch
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from xlsx2md.cli import build_parser
from xlsx2md.dispatch import (
    _coerce_header_rows,
    _detect_mode_for_args,
    _extract_hyperlinks_for_region,
    _gap_fallback_if_empty,
    _resolve_hyperlink_allowlist,
    _resolve_read_only_mode,
    iter_table_payloads,
)
from xlsx_read import SheetInfo, SheetNotFound, TableData, TableRegion


# ---------------------------------------------------------------------------
# MockReader
# ---------------------------------------------------------------------------

@dataclass
class MockReader:
    """Minimal WorkbookReader-shaped mock. Tracks calls for assertions."""

    sheets_data: list[SheetInfo] = field(default_factory=list)
    # regions_by_sheet: sheet_name -> list returned by detect_tables
    # Key '' is used for whole-mode fallback calls if needed.
    regions_by_sheet: dict[str, list[TableRegion]] = field(default_factory=dict)
    # whole_regions_by_sheet: separate bucket for mode="whole" calls
    whole_regions_by_sheet: dict[str, list[TableRegion]] = field(
        default_factory=dict
    )
    table_data_by_key: dict[tuple[str, int, int], TableData] = field(
        default_factory=dict
    )
    detect_calls: list[dict] = field(default_factory=list)
    read_table_calls: list[dict] = field(default_factory=list)

    def sheets(self) -> list[SheetInfo]:
        return list(self.sheets_data)

    def detect_tables(
        self,
        sheet: str,
        *,
        mode: str = "auto",
        gap_rows: int = 2,
        gap_cols: int = 1,
    ) -> list[TableRegion]:
        self.detect_calls.append(
            {"sheet": sheet, "mode": mode, "gap_rows": gap_rows, "gap_cols": gap_cols}
        )
        if mode == "whole":
            return list(self.whole_regions_by_sheet.get(sheet, []))
        return list(self.regions_by_sheet.get(sheet, []))

    def read_table(self, region: TableRegion, **kwargs: Any) -> TableData:
        self.read_table_calls.append({"region": region, **kwargs})
        key = (region.sheet, region.top_row, region.left_col)
        return self.table_data_by_key.get(key, TableData(region=region))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _make_region(
    sheet: str = "Sheet1",
    top_row: int = 1,
    left_col: int = 1,
    bottom_row: int = 2,
    right_col: int = 2,
    source: str = "gap_detect",
) -> TableRegion:
    return TableRegion(
        sheet=sheet,
        top_row=top_row,
        left_col=left_col,
        bottom_row=bottom_row,
        right_col=right_col,
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# TestResolveReadOnlyMode
# ---------------------------------------------------------------------------

class TestResolveReadOnlyMode(unittest.TestCase):
    """TC-UNIT-01..03 — _resolve_read_only_mode mapping."""

    def _args(self, mode: str) -> argparse.Namespace:
        return _parse(["dummy.xlsx", f"--memory-mode={mode}"])

    def test_resolve_read_only_mode_auto_returns_none(self) -> None:
        """TC-UNIT-01."""
        self.assertIsNone(_resolve_read_only_mode(self._args("auto")))

    def test_resolve_read_only_mode_streaming_returns_true(self) -> None:
        """TC-UNIT-02."""
        self.assertIs(_resolve_read_only_mode(self._args("streaming")), True)

    def test_resolve_read_only_mode_full_returns_false(self) -> None:
        """TC-UNIT-03."""
        self.assertIs(_resolve_read_only_mode(self._args("full")), False)


# ---------------------------------------------------------------------------
# TestDetectModeForArgs
# ---------------------------------------------------------------------------

class TestDetectModeForArgs(unittest.TestCase):
    """TC-UNIT-04..06 — _detect_mode_for_args mapping."""

    def test_detect_mode_no_split_returns_whole_with_passthrough_filter(
        self,
    ) -> None:
        """TC-UNIT-04 — --no-split → mode="whole", filter always True."""
        args = _parse(["dummy.xlsx", "--no-split"])
        mode, filt = _detect_mode_for_args(args)
        self.assertEqual(mode, "whole")
        # filter must accept any region (pass-through)
        r = _make_region(source="gap_detect")
        self.assertTrue(filt(r))
        r2 = _make_region(source="listobject")
        self.assertTrue(filt(r2))

    def test_detect_mode_no_table_autodetect_returns_auto_with_gap_filter(
        self,
    ) -> None:
        """TC-UNIT-05 — --no-table-autodetect → mode="auto", gap-only filter."""
        args = _parse(["dummy.xlsx", "--no-table-autodetect"])
        mode, filt = _detect_mode_for_args(args)
        self.assertEqual(mode, "auto")
        self.assertTrue(filt(_make_region(source="gap_detect")))
        self.assertFalse(filt(_make_region(source="listobject")))
        self.assertFalse(filt(_make_region(source="named_range")))

    def test_detect_mode_default_returns_auto_with_passthrough_filter(
        self,
    ) -> None:
        """TC-UNIT-06 — default → mode="auto", filter always True."""
        args = _parse(["dummy.xlsx"])
        mode, filt = _detect_mode_for_args(args)
        self.assertEqual(mode, "auto")
        self.assertTrue(filt(_make_region(source="listobject")))
        self.assertTrue(filt(_make_region(source="gap_detect")))


# ---------------------------------------------------------------------------
# TestResolveHyperlinkAllowlist
# ---------------------------------------------------------------------------

class TestResolveHyperlinkAllowlist(unittest.TestCase):
    """TC-UNIT-07..10 — _resolve_hyperlink_allowlist."""

    def _args_with_allowlist(self, value: str) -> argparse.Namespace:
        return _parse(["dummy.xlsx", f"--hyperlink-scheme-allowlist={value}"])

    def test_resolve_hyperlink_allowlist_default_three_schemes(self) -> None:
        """TC-UNIT-07 — default CSV → frozenset of 3 schemes."""
        args = _parse(["dummy.xlsx"])
        result = _resolve_hyperlink_allowlist(args)
        self.assertEqual(result, frozenset({"http", "https", "mailto"}))

    def test_resolve_hyperlink_allowlist_star_returns_none_sentinel(
        self,
    ) -> None:
        """TC-UNIT-08 — '*' → None (allow all)."""
        args = _parse(["dummy.xlsx", "--hyperlink-scheme-allowlist=*"])
        self.assertIsNone(_resolve_hyperlink_allowlist(args))

    def test_resolve_hyperlink_allowlist_empty_returns_empty_frozenset(
        self,
    ) -> None:
        """TC-UNIT-09 — '' → frozenset() (block all)."""
        args = _parse(["dummy.xlsx", "--hyperlink-scheme-allowlist="])
        result = _resolve_hyperlink_allowlist(args)
        self.assertEqual(result, frozenset())

    def test_resolve_hyperlink_allowlist_case_insensitive_lowercased(
        self,
    ) -> None:
        """TC-UNIT-10 — 'HTTP,Mailto' → {'http', 'mailto'}."""
        args = _parse(["dummy.xlsx", "--hyperlink-scheme-allowlist=HTTP,Mailto"])
        result = _resolve_hyperlink_allowlist(args)
        self.assertEqual(result, frozenset({"http", "mailto"}))


# ---------------------------------------------------------------------------
# TestCoerceHeaderRows
# ---------------------------------------------------------------------------

class TestCoerceHeaderRows(unittest.TestCase):
    """Internal helper — _coerce_header_rows."""

    def test_coerce_header_rows_auto_passthrough(self) -> None:
        self.assertEqual(_coerce_header_rows("auto"), "auto")

    def test_coerce_header_rows_smart_passthrough(self) -> None:
        self.assertEqual(_coerce_header_rows("smart"), "smart")

    def test_coerce_header_rows_int_passthrough(self) -> None:
        # argparse already converts "2" → int(2) via _header_rows_type.
        self.assertEqual(_coerce_header_rows(2), 2)


# ---------------------------------------------------------------------------
# TestIterTablePayloads
# ---------------------------------------------------------------------------

class TestIterTablePayloads(unittest.TestCase):
    """TC-UNIT-11..24 + fixture pin — iter_table_payloads integration."""

    def _make_args(self, **overrides: Any) -> argparse.Namespace:
        args = _parse(["dummy.xlsx"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def _single_sheet_reader(
        self, regions: list[TableRegion] | None = None
    ) -> MockReader:
        if regions is None:
            r = _make_region()
            regions = [r]
        return MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={"Sheet1": regions},
        )

    # TC-UNIT-11
    def test_iter_payloads_single_sheet_single_region(self) -> None:
        reader = self._single_sheet_reader()
        args = self._make_args()
        payloads = list(iter_table_payloads(reader, args))
        self.assertEqual(len(payloads), 1)
        sheet, region, td, hl_map = payloads[0]
        self.assertEqual(sheet.name, "Sheet1")
        self.assertIsInstance(td, TableData)
        # Path C′ (012-04): MockReader has no _wb attribute, so the
        # parallel pass returns an empty hl_map.
        self.assertEqual(hl_map, {})

    # TC-UNIT-12
    def test_iter_payloads_multi_sheet_all_visible(self) -> None:
        """2 visible + 1 hidden; sheet='all', include_hidden=False → 2 triples."""
        r1 = _make_region(sheet="Sheet1")
        r2 = _make_region(sheet="Sheet2")
        reader = MockReader(
            sheets_data=[
                SheetInfo(name="Sheet1", index=0, state="visible"),
                SheetInfo(name="Sheet2", index=1, state="visible"),
                SheetInfo(name="_Internal", index=2, state="hidden"),
            ],
            regions_by_sheet={"Sheet1": [r1], "Sheet2": [r2], "_Internal": []},
        )
        args = self._make_args(sheet="all", include_hidden=False)
        triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 2)
        names = [t[0].name for t in triples]
        self.assertNotIn("_Internal", names)

    # TC-UNIT-13
    def test_iter_payloads_include_hidden_includes_hidden(self) -> None:
        """include_hidden=True → 3 triples."""
        r1 = _make_region(sheet="Sheet1")
        r2 = _make_region(sheet="Sheet2")
        r3 = _make_region(sheet="_Internal")
        reader = MockReader(
            sheets_data=[
                SheetInfo(name="Sheet1", index=0, state="visible"),
                SheetInfo(name="Sheet2", index=1, state="visible"),
                SheetInfo(name="_Internal", index=2, state="hidden"),
            ],
            regions_by_sheet={
                "Sheet1": [r1],
                "Sheet2": [r2],
                "_Internal": [r3],
            },
        )
        args = self._make_args(sheet="all", include_hidden=True)
        triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 3)
        names = [t[0].name for t in triples]
        self.assertIn("_Internal", names)

    # TC-UNIT-14
    def test_iter_payloads_sheet_named_single_match(self) -> None:
        reader = MockReader(
            sheets_data=[
                SheetInfo(name="Sheet1", index=0, state="visible"),
                SheetInfo(name="Sheet2", index=1, state="visible"),
            ],
            regions_by_sheet={
                "Sheet1": [_make_region(sheet="Sheet1")],
                "Sheet2": [_make_region(sheet="Sheet2")],
            },
        )
        args = self._make_args(sheet="Sheet2")
        triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 1)
        self.assertEqual(triples[0][0].name, "Sheet2")

    # TC-UNIT-15
    def test_iter_payloads_sheet_named_not_found_raises_SheetNotFound(
        self,
    ) -> None:
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")]
        )
        args = self._make_args(sheet="MissingSheet")
        with self.assertRaises(SheetNotFound):
            list(iter_table_payloads(reader, args))

    # TC-UNIT-16
    def test_iter_payloads_gap_filter_only_passes_gap_detect(self) -> None:
        """--no-table-autodetect: 2 gap_detect + 1 listobject → 2 yielded."""
        regions = [
            _make_region(source="gap_detect", top_row=1),
            _make_region(source="gap_detect", top_row=5),
            _make_region(source="listobject", top_row=10),
        ]
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={"Sheet1": regions},
        )
        args = self._make_args(no_table_autodetect=True)
        triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 2)
        for _, region, _, _ in triples:
            self.assertEqual(region.source, "gap_detect")

    # TC-UNIT-17
    def test_iter_payloads_gap_fallback_when_filter_empty(self) -> None:
        """R8.f: --no-table-autodetect + all listobject → fallback to whole."""
        whole_region = _make_region(sheet="Sheet1", source="gap_detect", top_row=1)
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            # Only listobject regions → gap filter discards all
            regions_by_sheet={"Sheet1": [_make_region(source="listobject")]},
            whole_regions_by_sheet={"Sheet1": [whole_region]},
        )
        args = self._make_args(no_table_autodetect=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            triples = list(iter_table_payloads(reader, args))
        # One triple from the fallback whole-region.
        self.assertEqual(len(triples), 1)
        # Warning about fallback emitted.
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            any("whole-sheet" in str(w.message) for w in user_warnings),
            f"Expected whole-sheet fallback warning; got: {[str(w.message) for w in user_warnings]}",
        )
        # detect_tables was called with mode="whole" for the fallback.
        whole_calls = [c for c in reader.detect_calls if c["mode"] == "whole"]
        self.assertEqual(len(whole_calls), 1)

    # TC-UNIT-18
    def test_iter_payloads_no_split_yields_whole_mode_single_region(
        self,
    ) -> None:
        """--no-split → detect_tables called with mode='whole'."""
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={},
            whole_regions_by_sheet={
                "Sheet1": [_make_region(sheet="Sheet1", source="gap_detect")]
            },
        )
        args = self._make_args(no_split=True)
        triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 1)
        # Verify the detect call was mode="whole".
        modes = [c["mode"] for c in reader.detect_calls]
        self.assertIn("whole", modes)

    # TC-UNIT-19
    def test_iter_payloads_passes_header_rows_smart_to_read_table(
        self,
    ) -> None:
        """'smart' passes through verbatim to reader.read_table."""
        reader = self._single_sheet_reader()
        args = self._make_args(header_rows="smart")
        list(iter_table_payloads(reader, args))
        self.assertEqual(len(reader.read_table_calls), 1)
        self.assertEqual(reader.read_table_calls[0]["header_rows"], "smart")

    # TC-UNIT-20
    def test_iter_payloads_passes_header_rows_int_to_read_table(
        self,
    ) -> None:
        """Integer header_rows (post-argparse coercion) passes as int."""
        reader = self._single_sheet_reader()
        # argparse _header_rows_type already returns int(2).
        args = self._make_args(header_rows=2)
        list(iter_table_payloads(reader, args))
        self.assertEqual(len(reader.read_table_calls), 1)
        self.assertEqual(reader.read_table_calls[0]["header_rows"], 2)

    # TC-UNIT-21 (Path C′ — refactored 012-04)
    def test_iter_payloads_read_table_uses_include_hyperlinks_false(self) -> None:
        """Path C′ (D5 + 012-04): dispatch calls read_table with
        include_hyperlinks=False so display text survives. The href map
        is built via the parallel _extract_hyperlinks_for_region pass.
        """
        reader = self._single_sheet_reader()
        args = self._make_args()
        list(iter_table_payloads(reader, args))
        self.assertFalse(
            reader.read_table_calls[0]["include_hyperlinks"],
            "Path C′: read_table must NOT use include_hyperlinks=True; "
            "dispatch does a parallel pass via reader._wb instead so "
            "display text survives in TableData.rows.",
        )

    # TC-UNIT-21b (Path C′ — new)
    def test_iter_payloads_yields_4_tuple_with_hyperlinks_map(self) -> None:
        """Path C′: emit-side receives (sheet, region, table_data, hl_map)."""
        reader = self._single_sheet_reader()
        args = self._make_args()
        payloads = list(iter_table_payloads(reader, args))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(len(payloads[0]), 4, "Must be a 4-tuple")
        sheet, region, td, hl_map = payloads[0]
        self.assertIsInstance(hl_map, dict)

    # TC-UNIT-22
    def test_iter_payloads_passes_datetime_format(self) -> None:
        """args.datetime_format forwarded verbatim to read_table."""
        reader = self._single_sheet_reader()
        args = self._make_args(datetime_format="excel-serial")
        list(iter_table_payloads(reader, args))
        self.assertEqual(
            reader.read_table_calls[0]["datetime_format"], "excel-serial"
        )

    # TC-UNIT-23
    def test_iter_payloads_emits_streaming_hyperlink_warning_when_read_only_mode_true(
        self,
    ) -> None:
        """R20a: streaming-mode warning emitted EXACTLY ONCE per call.

        Dedup contract: even across multiple sheets and multiple regions per
        sheet, the warning fires once total (per iter_table_payloads call).
        Sarcasmotron-driven hardening — was assertGreaterEqual; now locked
        to assertEqual with a multi-region multi-sheet fan-out fixture so a
        future regression that fans the warning out per-region or
        per-sheet fails-loud.
        """
        # Two sheets, two regions each → 4 read_table calls. Dedup must
        # collapse the streaming warning to exactly 1.
        region_a = TableRegion(
            sheet="Sheet1", top_row=1, left_col=1,
            bottom_row=2, right_col=2, source="gap_detect",
        )
        region_b = TableRegion(
            sheet="Sheet1", top_row=5, left_col=1,
            bottom_row=6, right_col=2, source="gap_detect",
        )
        region_c = TableRegion(
            sheet="Sheet2", top_row=1, left_col=1,
            bottom_row=2, right_col=2, source="gap_detect",
        )
        region_d = TableRegion(
            sheet="Sheet2", top_row=5, left_col=1,
            bottom_row=6, right_col=2, source="gap_detect",
        )
        reader = MockReader(
            sheets_data=[
                SheetInfo(name="Sheet1", index=0, state="visible"),
                SheetInfo(name="Sheet2", index=1, state="visible"),
            ],
            regions_by_sheet={
                "Sheet1": [region_a, region_b],
                "Sheet2": [region_c, region_d],
            },
        )
        args = self._make_args()
        args._read_only_mode_resolved = True
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            triples = list(iter_table_payloads(reader, args))
        self.assertEqual(len(triples), 4, "fan-out fixture must yield 4 triples")
        streaming_warnings = [
            w for w in caught
            if issubclass(w.category, UserWarning)
            and "streaming mode" in str(w.message)
        ]
        self.assertEqual(
            len(streaming_warnings), 1,
            f"streaming-mode warning must dedup to exactly 1, got "
            f"{len(streaming_warnings)}",
        )

    # TC-UNIT-24
    def test_iter_payloads_listobjects_zero_header_count_propagates(
        self,
    ) -> None:
        """Dispatch does NOT swallow TableData.warnings from the library."""
        region = TableRegion(
            sheet="Sheet1",
            top_row=1,
            left_col=1,
            bottom_row=3,
            right_col=2,
            source="listobject",
            name="MyTable",
            listobject_header_row_count=0,
        )
        # Mock read_table returning a TableData with a synthetic-header warning.
        synthetic_warning = "Table 'MyTable' had no headers; emitted synthetic col_1..col_2"
        td_with_warning = TableData(
            region=region,
            headers=["col_1", "col_2"],
            rows=[["a", "b"]],
            warnings=[synthetic_warning],
        )
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={"Sheet1": [region]},
            table_data_by_key={("Sheet1", 1, 1): td_with_warning},
        )
        args = self._make_args()
        payloads = list(iter_table_payloads(reader, args))
        self.assertEqual(len(payloads), 1)
        _, _, td, _ = payloads[0]
        # Warning must still be present — dispatch must not swallow it.
        self.assertTrue(
            any("synthetic" in w for w in td.warnings),
            f"Expected synthetic-header warning in TableData.warnings; got {td.warnings!r}",
        )

    # Stub-First gate update §2.4 — fixture pin
    def test_dispatch_yields_4tuple_for_single_cell_fixture(self) -> None:
        """Stub-first §2.4: dispatch yields one 4-tuple for single_cell.xlsx."""
        from xlsx_read import open_workbook  # noqa: PLC0415

        fixture = (
            Path(__file__).resolve().parent / "fixtures" / "single_cell.xlsx"
        )
        args = _parse([str(fixture)])
        args._read_only_mode_resolved = None
        with open_workbook(fixture) as reader:
            payloads = list(iter_table_payloads(reader, args))
        self.assertEqual(len(payloads), 1)
        sheet, region, td, hl_map = payloads[0]
        self.assertEqual(sheet.name, "Sheet1")
        # single_cell.xlsx has one cell "hello" at A1; no hyperlink.
        # Path C′: hl_map is empty dict (no hyperlinks in this fixture).
        self.assertEqual(hl_map, {})
        # The library detects the single row as the header row (auto-mode);
        # assert the shape: either headers or rows contains "hello".
        all_values = td.headers + [v for row in td.rows for v in row]
        self.assertIn("hello", all_values)


class TestExtractHyperlinksForRegion(unittest.TestCase):
    """Path C′ — parallel hyperlink-extraction pass via reader._wb.

    Mirrors xlsx-8's ``_extract_hyperlinks_for_region`` pattern. Tests
    use the real ``values_hyperlink.xlsx`` and
    ``hyperlink_various_schemes.xlsx`` fixtures because the function's
    contract is "iterate openpyxl cells in the region and read
    ``cell.hyperlink.target``" — there's nothing meaningful to mock
    without re-implementing openpyxl's worksheet API.
    """

    _FIXTURES = Path(__file__).resolve().parent / "fixtures"

    def test_extract_hyperlinks_returns_href_map_for_real_fixture(self) -> None:
        """Path C′ smoke: dispatch helper returns {(r,c): href} for hyperlinks."""
        from xlsx_read import open_workbook  # noqa: PLC0415

        # Reuse xlsx_read's own hyperlink fixture (display="Click here",
        # href="https://example.com") to avoid extra fixture generation.
        fixture = (
            Path(__file__).resolve().parent.parent.parent
            / "xlsx_read" / "tests" / "fixtures" / "values_hyperlink.xlsx"
        )
        with open_workbook(fixture) as reader:
            regions = reader.detect_tables(reader.sheets()[0].name, mode="whole")
            hl_map = _extract_hyperlinks_for_region(reader, regions[0])
        # Exactly one hyperlink cell; key = (0, 0) within the region.
        self.assertEqual(hl_map, {(0, 0): "https://example.com"})

    def test_extract_hyperlinks_separates_display_text_from_href(self) -> None:
        """Path C′ core: dispatch yields (sheet, region, td, hl_map) where
        ``td.rows`` contains the *display text* and ``hl_map`` contains the
        *href* — so emit-side can produce ``[display text](href)``.
        """
        from xlsx_read import open_workbook  # noqa: PLC0415

        fixture = self._FIXTURES / "hyperlink_various_schemes.xlsx"
        args = _parse([str(fixture), "--hyperlink-scheme-allowlist=*"])  # allow all
        args._read_only_mode_resolved = None
        with open_workbook(fixture) as reader:
            payloads = list(iter_table_payloads(reader, args))
        self.assertEqual(len(payloads), 1)
        sheet, region, td, hl_map = payloads[0]
        # Display text preserved (NOT replaced by URL) — this is the win.
        all_values = td.headers + [v for row in td.rows for v in row]
        self.assertIn("safe link", all_values)
        self.assertIn("unsafe link", all_values)
        self.assertIn("mail", all_values)
        # Hrefs available separately via the parallel-pass map.
        href_set = set(hl_map.values())
        self.assertIn("https://ok.example.com", href_set)
        self.assertIn("javascript:alert(1)", href_set)  # allow-all sentinel passes through
        self.assertIn("mailto:x@y.example.com", href_set)

    def test_extract_hyperlinks_javascript_scheme_blocked_by_default(self) -> None:
        """R10a / D-A15 / Sec-MED-2: default allowlist blocks ``javascript:``."""
        from xlsx_read import open_workbook  # noqa: PLC0415

        fixture = self._FIXTURES / "hyperlink_various_schemes.xlsx"
        # Default allowlist (no flag override) = http,https,mailto.
        args = _parse([str(fixture)])
        args._read_only_mode_resolved = None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with open_workbook(fixture) as reader:
                payloads = list(iter_table_payloads(reader, args))
        sheet, region, td, hl_map = payloads[0]
        # javascript: is dropped from the map; https + mailto pass through.
        href_set = set(hl_map.values())
        self.assertIn("https://ok.example.com", href_set)
        self.assertIn("mailto:x@y.example.com", href_set)
        self.assertNotIn("javascript:alert(1)", href_set,
                         "javascript: must be blocked by default allowlist")
        # Per-distinct-scheme dedup warning fired exactly once.
        scheme_warnings = [
            w for w in caught
            if issubclass(w.category, UserWarning)
            and "disallowed scheme" in str(w.message)
            and "javascript" in str(w.message)
        ]
        self.assertEqual(
            len(scheme_warnings), 1,
            "expected exactly one 'disallowed scheme javascript' warning; "
            f"got {[str(w.message) for w in caught]}",
        )

    def test_extract_hyperlinks_no_wb_returns_empty_map(self) -> None:
        """Defensive: reader without ``_wb`` attribute returns empty map.

        MockReader (no ``_wb``) traversing a region must NOT crash; it
        returns ``{}`` so emit-side renders cells as plain text.
        """
        region = TableRegion(
            sheet="Sheet1", top_row=1, left_col=1,
            bottom_row=2, right_col=2, source="gap_detect",
        )
        reader = MockReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={"Sheet1": [region]},
        )
        hl_map = _extract_hyperlinks_for_region(reader, region)
        self.assertEqual(hl_map, {})


class TestSmartShiftHyperlinkAlignment(unittest.TestCase):
    """Sarcasmotron H1 fix: when ``--header-rows=smart`` shifts the region
    past a metadata banner, ``_extract_hyperlinks_for_region`` must be
    called with the SHIFTED region (``table_data.region``) so that map
    keys align with the emit-side ``header_band`` math.

    Before the fix, dispatch passed the ORIGINAL region to the helper.
    A workbook with a metadata banner at rows 1-3, header at row 4, and
    body hyperlinks at rows 5+ would produce a hyperlinks_map keyed
    against `top_row=1`; emit would look up via `header_band+r_idx`
    keys relative to the SHIFTED `top_row=4`, so hyperlinks would
    silently misalign or disappear.
    """

    def test_iter_payloads_passes_shifted_region_to_hyperlink_extractor(
        self,
    ) -> None:
        """Mock ``read_table`` returning a TableData with a SHIFTED region;
        assert that ``_extract_hyperlinks_for_region`` was invoked with the
        SHIFTED region, not the original from ``detect_tables``.
        """
        original_region = TableRegion(
            sheet="Sheet1", top_row=1, left_col=1,
            bottom_row=10, right_col=2, source="listobject",
        )
        # Simulates smart-mode shift: dispatch sees this region in the
        # `read_table_calls` history, but read_table returns a TableData
        # whose `.region` has top_row=4 (banner rows 1-3 stripped).
        shifted_region = TableRegion(
            sheet="Sheet1", top_row=4, left_col=1,
            bottom_row=10, right_col=2, source="listobject",
        )
        shifted_table_data = TableData(
            region=shifted_region,
            headers=["Name", "URL"],
            rows=[["item1", "ignored"], ["item2", "ignored"]],
        )

        # MockReader that records WHICH region was passed to read_table
        # AND emulates the smart-mode shift by returning a TableData with
        # a different `.region` than the input.
        observed_extract_regions: list[TableRegion] = []

        class _ShiftingReader(MockReader):
            def detect_tables(
                self, sheet: str, **kwargs: object,
            ) -> list[TableRegion]:
                # Mode-agnostic for this test: always return the
                # pre-shift original region regardless of `mode=`
                # passed by dispatch.
                self.detect_calls.append({"sheet": sheet, **kwargs})
                return [original_region]

            def read_table(
                self, region: TableRegion, **kwargs: object,
            ) -> TableData:
                # Record + return the shifted TableData (simulates smart-
                # mode behaviour from xlsx_read._types.read_table).
                self.read_table_calls.append({"region": region, **kwargs})
                return shifted_table_data

        # Patch _extract_hyperlinks_for_region at the module level to
        # observe which region it receives.
        from xlsx2md import dispatch as _dispatch_mod

        original_extract = _dispatch_mod._extract_hyperlinks_for_region

        def _spy_extract(reader_arg, region_arg, **kwargs):
            observed_extract_regions.append(region_arg)
            return original_extract(reader_arg, region_arg, **kwargs)

        reader = _ShiftingReader(
            sheets_data=[SheetInfo(name="Sheet1", index=0, state="visible")],
            regions_by_sheet={"Sheet1": [original_region]},
        )
        args = _parse([
            "dummy.xlsx", "--header-rows=smart",
            "--no-split",  # forces mode="whole"; bypasses any gating
        ])
        with patch.object(
            _dispatch_mod, "_extract_hyperlinks_for_region", _spy_extract,
        ):
            payloads = list(iter_table_payloads(reader, args))

        self.assertEqual(len(payloads), 1)
        # H1 ASSERTION: the helper must have been called with the SHIFTED
        # region (top_row=4), not the original (top_row=1).
        self.assertEqual(
            len(observed_extract_regions), 1,
            "_extract_hyperlinks_for_region must be called exactly once "
            "per region per iter_table_payloads invocation",
        )
        passed_region = observed_extract_regions[0]
        self.assertEqual(
            passed_region.top_row, 4,
            f"H1 FIX: _extract_hyperlinks_for_region must receive SHIFTED "
            f"region (top_row=4 after smart-mode shift), got "
            f"top_row={passed_region.top_row}. This is the off-by-shift "
            f"bug — see Sarcasmotron H1 finding.",
        )
        self.assertIs(
            passed_region, shifted_table_data.region,
            "Must pass table_data.region (the post-shift instance), "
            "not the pre-shift region from detect_tables",
        )


if __name__ == "__main__":
    unittest.main()
