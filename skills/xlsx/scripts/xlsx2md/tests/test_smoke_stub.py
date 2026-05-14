"""Smoke E2E for task 012-01 — asserts hardcoded sentinel behaviour.

Per ``tdd-stub-first §1``, this test passes on stubs and is
**updated** in later tasks (012-02..012-07) to assert real behaviour.

Stage-1 expectations (all 7 tests must pass on stubs):

1. ``import xlsx2md`` succeeds (package importable).
2. ``set(xlsx2md.__all__)`` matches the 10-name frozen surface.
3. Each exception class has the locked ``CODE`` attribute per ARCH §2.1 F8.
4. ``xlsx2md.convert_xlsx_to_md("ignored")`` returns ``-999`` (sentinel).
5. ``xlsx2md.main([])`` returns ``-999`` (sentinel).
6. ``python3 xlsx2md.py --help`` (subprocess) exits 0 AND stdout
   contains all 14 required flag names from ARCH §5.1.
7. Count of non-blank non-comment lines in ``xlsx2md.py`` is ≤ 60 (R1.d).
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

# Make scripts/ importable so `import xlsx2md` works when the test
# runs from anywhere.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_SHIM_PATH = _SCRIPTS_DIR / "xlsx2md.py"


class TestSkeletonStubs(unittest.TestCase):
    """Regression net around the frozen public surface (ARCH §2.1 F9)."""

    def test_package_importable(self) -> None:
        """TC-UNIT-01 — package must be importable without error."""
        import xlsx2md  # noqa: PLC0415
        self.assertIsNotNone(xlsx2md)

    def test_all_public_symbols_present(self) -> None:
        """TC-UNIT-02 — ``__all__`` must match the 10-name frozen surface."""
        import xlsx2md  # noqa: PLC0415
        expected = {
            "main",
            "convert_xlsx_to_md",
            "_AppError",
            "SelfOverwriteRefused",
            "GfmMergesRequirePolicy",
            "IncludeFormulasRequiresHTML",
            "PostValidateFailed",
            "InconsistentHeaderDepth",
            "HeaderRowsConflict",
            "InternalError",
        }
        self.assertEqual(set(xlsx2md.__all__), expected)

    def test_exception_codes_locked(self) -> None:
        """TC-UNIT-03 — each exception class must carry the locked CODE attribute."""
        from xlsx2md import (  # noqa: PLC0415
            _AppError,
            GfmMergesRequirePolicy,
            HeaderRowsConflict,
            IncludeFormulasRequiresHTML,
            InconsistentHeaderDepth,
            InternalError,
            PostValidateFailed,
            SelfOverwriteRefused,
        )
        self.assertEqual(_AppError.CODE, 1)
        self.assertEqual(SelfOverwriteRefused.CODE, 6)
        self.assertEqual(GfmMergesRequirePolicy.CODE, 2)
        self.assertEqual(IncludeFormulasRequiresHTML.CODE, 2)
        self.assertEqual(PostValidateFailed.CODE, 7)
        self.assertEqual(InconsistentHeaderDepth.CODE, 2)
        self.assertEqual(HeaderRowsConflict.CODE, 2)
        self.assertEqual(InternalError.CODE, 7)

    def test_convert_helper_envelope_path(self) -> None:
        """TC-UNIT-04 (post-012-02) — convert_xlsx_to_md routes through main().

        Per `tdd-stub-first §2.4`, the 012-01 sentinel assertion is REPLACED
        by a real-behaviour assertion now that the envelope pipeline is wired.
        Non-existent path triggers FileNotFoundError -> terminal catch-all ->
        InternalError code 7. The test verifies a non-stub return; specific
        cross-3 envelope-shape assertions live in test_cli_envelopes.py.
        """
        from xlsx2md import convert_xlsx_to_md  # noqa: PLC0415
        result = convert_xlsx_to_md("/tmp/nonexistent_xlsx2md_smoke.xlsx")
        self.assertEqual(result, 7, "FileNotFoundError -> InternalError code 7")

    def test_main_m7_lock_exits_2(self) -> None:
        """TC-UNIT-05 (post-012-02) — main() enforces M7 lock before file I/O.

        Per `tdd-stub-first §2.4`, the 012-01 sentinel assertion is REPLACED.
        `--format=gfm --include-formulas` raises IncludeFormulasRequiresHTML
        (code 2) in `_validate_flag_combo`, BEFORE any workbook open. The
        fixture path is irrelevant because the gate fires first.
        """
        from xlsx2md import main  # noqa: PLC0415
        result = main([
            "/tmp/never_opened.xlsx",
            "--format=gfm",
            "--include-formulas",
        ])
        self.assertEqual(result, 2, "M7 lock should exit 2 pre-open")

    def test_shim_help_lists_all_flags(self) -> None:
        """TC-UNIT-06 — python3 xlsx2md.py --help must exit 0 and list all 14 flags."""
        required_flags = [
            "--sheet",
            "--include-hidden",
            "--format",
            "--header-rows",
            "--memory-mode",
            "--hyperlink-scheme-allowlist",
            "--no-table-autodetect",
            "--no-split",
            "--gap-rows",
            "--gap-cols",
            "--gfm-merge-policy",
            "--datetime-format",
            "--include-formulas",
            "--json-errors",
        ]
        proc = subprocess.run(
            [sys.executable, str(_SHIM_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"--help exited {proc.returncode}; stderr: {proc.stderr!r}",
        )
        for flag in required_flags:
            self.assertIn(
                flag,
                proc.stdout,
                f"--help output missing flag {flag!r}",
            )

    def test_shim_loc_le_60(self) -> None:
        """TC-UNIT-07 — xlsx2md.py must be <= 60 non-blank non-comment lines (R1.d)."""
        lines = [
            line
            for line in _SHIM_PATH.read_text("utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertLessEqual(
            len(lines),
            60,
            f"shim has {len(lines)} non-blank non-comment lines (limit: 60)",
        )


    def test_convert_xlsx_to_md_end_to_end_single_cell_produces_complete_doc(
        self,
    ) -> None:
        """TC-UNIT-08 (012-06) — real .xlsx → real markdown full pipeline.

        tdd-stub-first §2.4 final gate: single_cell.xlsx produces a complete
        markdown document with ## Sheet1 H2, ### Table-1 H3, and the data
        cell value.
        """
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        import xlsx2md  # noqa: PLC0415

        fixture = (
            Path(__file__).resolve().parent / "fixtures" / "single_cell.xlsx"
        )
        with tempfile.NamedTemporaryFile(
            mode="r", suffix=".md", delete=False
        ) as tmp:
            out_path = tmp.name
        try:
            result = xlsx2md.convert_xlsx_to_md(str(fixture), out_path)
            self.assertEqual(result, 0)
            content = Path(out_path).read_text("utf-8")
            self.assertIn("## Sheet1", content)
            self.assertIn("### Table-1", content)
            self.assertIn("| hello |", content)  # the only data cell
        finally:
            Path(out_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
