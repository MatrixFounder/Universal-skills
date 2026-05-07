"""Honest-scope regression locks for Task 002 (xlsx_add_comment.py refactor).

Locks the post-refactor structural invariants. If any of these fails,
Task 002's R8.a "no behaviour change beyond restructuring" is violated
or Task 002's R2.a/b shim contract has drifted.
"""
from __future__ import annotations
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SHIM = REPO_ROOT / "skills" / "xlsx" / "scripts" / "xlsx_add_comment.py"


class TestRefactorHonestScope(unittest.TestCase):
    """Lock the Task-002 structural invariants."""

    def test_shim_loc_under_200(self) -> None:
        """R2.a: the shim is ≤ 200 LOC."""
        loc = sum(1 for _ in SHIM.read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(loc, 200, f"shim is {loc} LOC, must be ≤ 200")

    def test_shim_reexports_full_test_compat_surface(self) -> None:
        """R2.b / R3.a: the 35-symbol test-compat surface is preserved.

        Spot-check the most commonly imported names — full re-export is
        sanity-tested by tests/test_xlsx_comment_imports.py too.
        """
        sys.path.insert(0, str(SHIM.parent))
        try:
            import xlsx_add_comment as shim
            for name in [
                # constants (representative)
                "THREADED_NS", "DEFAULT_VML_ANCHOR", "VML_CT",
                # exceptions (representative)
                "SheetNotFound", "MalformedVml",
                "DuplicateLegacyComment", "DuplicateThreadedComment",
                # cell_parser
                "parse_cell_syntax", "resolve_sheet",
                # batch
                "load_batch",
                # ooxml_editor (incl. underscore-prefixed test-touched)
                "scan_idmap_used", "add_person",
                "_make_relative_target", "_allocate_rid",
                # merge_dup
                "resolve_merged_target", "_enforce_duplicate_matrix",
                # cli_helpers
                "_post_pack_validate",
                # cli
                "main",
            ]:
                self.assertTrue(
                    hasattr(shim, name),
                    f"shim missing re-export: {name}",
                )
        finally:
            sys.path.pop(0)

    def test_help_description_matches_shim_docstring(self) -> None:
        """Task 002 vdd-adversarial finding #1: lock --help description
        against the shim's first-line docstring so the literal in
        `cli.build_parser` cannot drift away from the user-facing summary.
        """
        sys.path.insert(0, str(SHIM.parent))
        try:
            import xlsx_add_comment as shim
            from xlsx_comment.cli import build_parser
            shim_first_line = (shim.__doc__ or "").splitlines()[0].strip()
            self.assertEqual(
                build_parser().description, shim_first_line,
                "build_parser().description has drifted from "
                "xlsx_add_comment.__doc__'s first line — update either "
                "cli.build_parser's `description=` literal or the shim "
                "docstring to keep --help in sync.",
            )
        finally:
            sys.path.pop(0)

    def test_office_byte_identity_preserved(self) -> None:
        """R6.e / R8.b: office/ is byte-identical across docx -> xlsx + pptx.

        pdf is excluded — it has no `skills/pdf/scripts/office/` directory
        (pdf does not use OOXML/LibreOffice; encryption is via pypdf
        PdfWriter.encrypt, not msoffcrypto-tool). Verified during Task
        002.1 baseline capture.
        """
        for skill in ("xlsx", "pptx"):
            result = subprocess.run(
                ["diff", "-qr",
                 str(REPO_ROOT / "skills" / "docx" / "scripts" / "office"),
                 str(REPO_ROOT / "skills" / skill / "scripts" / "office")],
                capture_output=True, text=True,
            )
            # __pycache__ directories are build artefacts; filter them out.
            stdout_real = "\n".join(
                line for line in result.stdout.splitlines()
                if "__pycache__" not in line
            )
            self.assertEqual(
                stdout_real, "",
                f"office/ diverged for {skill}: {stdout_real}",
            )


if __name__ == "__main__":
    unittest.main()
