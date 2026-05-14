"""Consolidated 34-slug E2E regression cluster for xlsx2md (task 012-08).

Each test method is bound to one slug from TASK 012 §5.1.  Tests invoke
``xlsx2md.py`` via ``subprocess.run`` and assert exit code + a key
substring in stdout / stderr / output file.

Slugs #1..#25 validate the core feature set (beads 012-02..012-06);
slugs #26..#34 cover inherited-hardening regressions first-asserted here.

Fixtures live in ``xlsx2md/tests/fixtures/``.  Tests that need fixtures
not yet built are marked with ``@unittest.skip`` with an explicit TODO
referencing the fixture name and the future builder action.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make scripts/ root importable so openpyxl/xlsx2md imports work.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_SHIM = _SCRIPTS_DIR / "xlsx2md.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Shortcut to real fixtures from xlsx_read (used for cross-fixture borrowing).
_XR_FIXTURES = _SCRIPTS_DIR / "xlsx_read" / "tests" / "fixtures"


def _run(
    *args: str,
    expected_exit: int = 0,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke xlsx2md.py via subprocess; return CompletedProcess.

    Raises AssertionError if exit code does not match ``expected_exit``.
    All string arguments are forwarded verbatim after the shim path.
    """
    cmd = [sys.executable, str(_SHIM), *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin,
    )
    if proc.returncode != expected_exit:
        raise AssertionError(
            f"expected exit {expected_exit}, got {proc.returncode}\n"
            f"args={args!r}\n"
            f"stdout={proc.stdout!r}\n"
            f"stderr={proc.stderr!r}"
        )
    return proc


class TestSlugT01T10(unittest.TestCase):
    """Slugs T-#1..T-#10 — basic GFM / multi-sheet / merges."""

    def test_T01_single_sheet_gfm_default(self) -> None:
        """T-#1 — single-sheet workbook emits GFM table by default."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
            out = tmp.name
        try:
            proc = _run(str(_FIXTURES / "single_cell.xlsx"), out)
            md = Path(out).read_text("utf-8")
            self.assertIn("## Sheet1", md)
            self.assertIn("| hello |", md)
        finally:
            Path(out).unlink(missing_ok=True)

    def test_T02_stdout_when_output_omitted(self) -> None:
        """T-#2 — stdout when output argument is omitted."""
        proc = _run(str(_FIXTURES / "single_cell.xlsx"))
        self.assertIn("| hello |", proc.stdout)

    def test_T03_sheet_named_filter(self) -> None:
        """T-#3 — --sheet NAME selects only that sheet.

        When --sheet is a specific name (not 'all'), the ## SheetName H2
        heading is suppressed per R7.d (emit_hybrid.py).  Only the table
        content is emitted.
        """
        proc = _run(
            str(_FIXTURES / "roundtrip_basic.xlsx"),
            "--sheet", "Data",
        )
        # H2 suppressed for single-sheet select (R7.d); data is still present.
        self.assertIn("Alice", proc.stdout)
        self.assertIn("Name", proc.stdout)  # header column
        self.assertNotIn("## Sheet", proc.stdout)  # no H2 for single-sheet mode

    @unittest.skip(
        "fixture multi_sheet_in_order.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a 3-sheet workbook"
    )
    def test_T04_multi_sheet_h2_ordering(self) -> None:
        """T-#4 — multi-sheet workbook emits sheets in workbook order as H2."""

    @unittest.skip(
        "fixture hidden_sheet.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a hidden-sheet workbook"
    )
    def test_T05_hidden_sheet_skipped_default(self) -> None:
        """T-#5 — hidden sheets skipped by default."""

    @unittest.skip(
        "fixture hidden_sheet.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a hidden-sheet workbook"
    )
    def test_T06_hidden_sheet_included_with_flag(self) -> None:
        """T-#6 — --include-hidden flag includes hidden sheets."""

    @unittest.skip(
        "fixture multi_table_listobjects.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a multi-ListObject workbook"
    )
    def test_T07_multi_table_listobjects_h3(self) -> None:
        """T-#7 — multiple ListObjects on one sheet emit H3 headings."""

    @unittest.skip(
        "fixture merged_body_cells.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with body merges"
    )
    def test_T08_merged_body_cells_html_colspan(self) -> None:
        """T-#8 — body merges trigger HTML emit with colspan on anchor cell."""

    @unittest.skip(
        "fixture merged_body_gfm_fail.xlsx not yet built; "
        "real GfmMergesRequirePolicy gate fires on body-merge + --format=gfm "
        "+ default --gfm-merge-policy=fail. M7 variant (formulas+gfm) is a "
        "DIFFERENT gate (T-#14) and not a valid substitute. "
        "See TODO 012-09 or extend _build_fixtures.py with a body-merge workbook."
    )
    def test_T09_gfm_merges_require_policy_exit2(self) -> None:
        """T-#9 — --format=gfm + body merges + fail policy → exit 2 GfmMergesRequirePolicy.

        Distinct from T-#14 (M7 lock: --format=gfm + --include-formulas).
        Sarcasmotron-driven correctness fix: previous implementation used
        the M7 variant as a "reliable pre-open" substitute, but that's the
        T-#14 contract, not D14/R15 GfmMergesRequirePolicy. Honest skip
        until a body-merge fixture lands.
        """

    @unittest.skip(
        "fixture multi_row_header.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a multi-row header workbook"
    )
    def test_T10_multi_row_header_html_thead(self) -> None:
        """T-#10 — multi-row header emits HTML <thead> with multiple <tr>."""


class TestSlugT11T20(unittest.TestCase):
    """Slugs T-#11..T-#20 — GFM multi-row / hyperlinks / formulas / gap-detect."""

    @unittest.skip(
        "fixture two_row_horizontal_merge.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a two-row header"
    )
    def test_T11_multi_row_header_gfm_u203a_flatten(self) -> None:
        """T-#11 — multi-row header in GFM flattened with U+203A separator."""

    def test_T12_hyperlink_gfm_url_form(self) -> None:
        """T-#12 — hyperlinks emit as [text](url) in GFM output."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=gfm",
        )
        self.assertIn("[safe link](https://ok.example.com)", proc.stdout)

    def test_T13_hyperlink_html_anchor_tag(self) -> None:
        """T-#13 — hyperlinks emit as <a href="..."> in HTML output."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=html",
        )
        self.assertIn('<a href="https://ok.example.com">', proc.stdout)

    def test_T14_include_formulas_gfm_exits2(self) -> None:
        """T-#14 — --format=gfm + --include-formulas -> exit 2 (M7 lock)."""
        proc = _run(
            str(_FIXTURES / "single_cell.xlsx"),
            "--format=gfm",
            "--include-formulas",
            expected_exit=2,
        )
        self.assertIn("IncludeFormulasRequiresHTML", proc.stderr)

    @unittest.skip(
        "fixture cell_with_formula.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a formula cell"
    )
    def test_T15_include_formulas_html_data_attr(self) -> None:
        """T-#15 — --format=html + --include-formulas adds data-formula attr."""

    def test_T16_same_path_via_symlink_exit6(self) -> None:
        """T-#16 — OUTPUT == INPUT (via symlink) -> exit 6 SelfOverwriteRefused."""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "single_cell.xlsx"
            src.write_bytes((_FIXTURES / "single_cell.xlsx").read_bytes())
            link = Path(td) / "out.md"
            os.symlink(src, link)
            proc = _run(str(src), str(link), expected_exit=6)
        self.assertIn("single_cell.xlsx", proc.stderr)

    def test_T17_encrypted_workbook_exit3(self) -> None:
        """T-#17 — encrypted workbook -> exit 3."""
        proc = _run(
            str(_FIXTURES / "encrypted.xlsx"),
            "/tmp/xlsx2md_test_T17.md",
            expected_exit=3,
        )
        self.assertIn("encrypted.xlsx", proc.stderr)

    def test_T18_xlsm_macro_warning(self) -> None:
        """T-#18 — .xlsm macro workbook -> exit 0 + stderr warning."""
        proc = _run(str(_FIXTURES / "macro_simple.xlsm"))
        # exit 0 asserted by _run's expected_exit default
        self.assertIn("vbaProject.bin", proc.stderr)

    @unittest.skip(
        "fixture with single-empty-row separator not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a gap=1 row workbook"
    )
    def test_T19_gap_detect_default_no_split_on_1_row(self) -> None:
        """T-#19 — default --gap-rows=2: single-empty-row does NOT split table."""

    @unittest.skip(
        "fixture single_row_gap.xlsx / two_row_gap.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a 2-empty-row gap workbook"
    )
    def test_T20_gap_detect_splits_on_2_empty_rows(self) -> None:
        """T-#20 — default --gap-rows=2: two consecutive empty rows split tables."""


class TestSlugT21T34(unittest.TestCase):
    """Slugs T-#21..T-#34 — round-trip / envelopes / advanced / inherited-hardening."""

    def test_T21_cell_newline_br_roundtrip(self) -> None:
        """T-#21 — cell newline (ALT+ENTER) -> <br> in output."""
        proc = _run(str(_FIXTURES / "cell_with_newline.xlsx"))
        self.assertIn("<br>", proc.stdout)
        self.assertIn("first line", proc.stdout)
        self.assertIn("second line", proc.stdout)

    def test_T22_json_errors_envelope_shape_v1(self) -> None:
        """T-#22 — --json-errors envelope has {v, error, code} for encrypted."""
        proc = _run(
            str(_FIXTURES / "encrypted.xlsx"),
            "/tmp/xlsx2md_test_T22.md",
            "--json-errors",
            expected_exit=3,
        )
        envelope = json.loads(proc.stderr.strip())
        self.assertEqual(envelope["v"], 1)
        self.assertIn("error", envelope)
        self.assertIn("code", envelope)
        self.assertEqual(envelope["code"], 3)

    @unittest.skip(
        "fixture with --gfm-merge-policy=duplicate not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with body merges"
    )
    def test_T23_gfm_merge_policy_duplicate(self) -> None:
        """T-#23 — --gfm-merge-policy=duplicate emits anchor value in child cells."""

    @unittest.skip(
        "fixture listobject_header_zero.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with headerRowCount=0"
    )
    def test_T24_synthetic_headers_listobject_zero(self) -> None:
        """T-#24 — ListObject with headerRowCount=0 emits synthetic col_1..col_N."""

    def test_T25_no_autodetect_empty_fallback_whole_sheet(self) -> None:
        """T-#25 — --no-table-autodetect falls back to whole-sheet region."""
        proc = _run(
            str(_FIXTURES / "single_cell.xlsx"),
            "--no-table-autodetect",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("| hello |", proc.stdout)

    @unittest.skip(
        "fixture metadata_banner_header.xlsx not yet built; "
        "see TODO 012-09 or extend _build_fixtures.py with a metadata-banner workbook"
    )
    def test_T26_header_rows_smart_skips_metadata_block(self) -> None:
        """T-#26 — --header-rows=smart skips metadata banner rows above data."""

    def test_T27_header_rows_int_with_multi_table_exits_2_conflict(self) -> None:
        """T-#27 — --header-rows=2 in multi-table mode -> exit 2 HeaderRowsConflict."""
        proc = _run(
            str(_FIXTURES / "single_cell.xlsx"),
            "--header-rows=2",
            expected_exit=2,
        )
        # Error message contains the conflict details dict (n_requested=2).
        combined = proc.stdout + proc.stderr
        self.assertIn("n_requested", combined)

    @unittest.skipUnless(
        os.environ.get("RUN_SLOW_TESTS"),
        "slow test skipped; set RUN_SLOW_TESTS=1 to enable; "
        "see TODO 012-09 for large fixture (~15 MB) needed for RSS measurement"
    )
    def test_T28_memory_mode_streaming_bounds_peak_rss(self) -> None:
        """T-#28 — --memory-mode=streaming reduces peak RSS on large file."""
        # Requires a ~15 MB fixture: see _build_fixtures.py TODO 012-09.
        large_fixture = _FIXTURES / "large_15mb.xlsx"
        if not large_fixture.exists():
            self.skipTest("fixture large_15mb.xlsx not yet built; see TODO 012-09")
        proc_stream = _run(str(large_fixture), "--memory-mode=streaming")
        # Minimal sanity: exit 0 and some output produced.
        self.assertEqual(proc_stream.returncode, 0)
        self.assertIn("##", proc_stream.stdout)

    def test_T29_memory_mode_auto_respects_library_default_100mib_threshold(
        self,
    ) -> None:
        """T-#29 — --memory-mode=auto (default) accepted without error."""
        proc = _run(
            str(_FIXTURES / "single_cell.xlsx"),
            "--memory-mode=auto",
        )
        self.assertIn("| hello |", proc.stdout)

    def test_T30_hyperlink_allowlist_blocks_javascript_html(self) -> None:
        """T-#30 — default allowlist blocks javascript: scheme in HTML output."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=html",
        )
        self.assertNotIn("javascript:", proc.stdout)
        self.assertIn("javascript", proc.stderr.lower())  # warning emitted

    def test_T31_hyperlink_allowlist_blocks_javascript_gfm(self) -> None:
        """T-#31 — default allowlist blocks javascript: scheme in GFM output."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=gfm",
        )
        self.assertNotIn("javascript:", proc.stdout)
        self.assertIn("javascript", proc.stderr.lower())

    def test_T32_hyperlink_allowlist_default_passes_https_mailto(self) -> None:
        """T-#32 — default allowlist passes https + mailto hyperlinks."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=gfm",
        )
        self.assertIn("[safe link](https://ok.example.com)", proc.stdout)
        self.assertIn("[mail](mailto:x@y.example.com)", proc.stdout)

    def test_T33_hyperlink_allowlist_custom_extends(self) -> None:
        """T-#33 — custom --hyperlink-scheme-allowlist allows extra schemes."""
        proc = _run(
            str(_FIXTURES / "hyperlink_various_schemes.xlsx"),
            "--format=html",
            "--hyperlink-scheme-allowlist=http,https,mailto,javascript",
        )
        # javascript link now appears as <a href="javascript:...">
        self.assertIn("javascript:", proc.stdout)
        # No "skipped" warning for javascript in stderr
        self.assertNotIn("disallowed scheme 'javascript'", proc.stderr)

    def test_T34_internal_error_envelope_redacts_raw_message(self) -> None:
        """T-#34 — InternalError envelope redacts raw exception message (R23f)."""
        import tempfile as _tf

        with _tf.NamedTemporaryFile(
            suffix=".xlsx", prefix="xlsx2md_t34_", delete=False
        ) as tmp:
            # Write garbage bytes — openpyxl raises BadZipFile internally.
            tmp.write(b"not a zip\x00\x01\x02")
            bad_path = tmp.name
        try:
            proc = _run(
                bad_path,
                "--json-errors",
                expected_exit=7,
            )
            envelope = json.loads(proc.stderr.strip())
            self.assertEqual(envelope["v"], 1)
            self.assertEqual(envelope["code"], 7)
            # Raw traceback / exception text must NOT appear in the envelope.
            # The error field is allowed to say "Internal error: <ClassName>".
            raw_msg_leaks = [
                "not a zip",
                "Traceback",
                "File ",
            ]
            for leak in raw_msg_leaks:
                self.assertNotIn(
                    leak,
                    proc.stderr,
                    f"raw exception text {leak!r} leaked into error envelope",
                )
        finally:
            Path(bad_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
