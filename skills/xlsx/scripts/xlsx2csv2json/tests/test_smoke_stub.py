"""Smoke E2E for stage 1 — asserts hardcoded sentinel behaviour.

Per :file:`tdd-stub-first §1`, this test passes on stubs and is
**updated** in later tasks (010-02, 010-03) to assert intermediate
sentinels (-998 / -997) and finally real behaviour.

Stage-1 expectations:

* The package is importable.
* ``__all__`` matches the locked 12-name list (ARCH §2.1 F5).
* Every shim-level exception class declares ``CODE`` per ARCH §2.1 F6.
* The public helpers ``convert_xlsx_to_csv`` / ``convert_xlsx_to_json``
  return ``-999`` (010-01 sentinel).
* ``main(...)`` returns ``-999`` (010-01 sentinel).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make scripts/ importable so `import xlsx2csv2json` works when the
# test runs from anywhere.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


class TestSkeletonStubs(unittest.TestCase):
    """Regression net around the frozen public surface (ARCH §2.1 F5)."""

    def test_package_importable(self) -> None:
        import xlsx2csv2json
        self.assertIsNotNone(xlsx2csv2json)

    def test_all_public_symbols_present(self) -> None:
        import xlsx2csv2json
        expected = {
            "main", "convert_xlsx_to_csv", "convert_xlsx_to_json",
            "_AppError", "SelfOverwriteRefused",
            "MultiTableRequiresOutputDir", "MultiSheetRequiresOutputDir",
            "HeaderRowsConflict", "InvalidSheetNameForFsPath",
            "OutputPathTraversal", "FormatLockedByShim",
            "PostValidateFailed",
        }
        self.assertEqual(set(xlsx2csv2json.__all__), expected)

    def test_exception_codes_locked(self) -> None:
        from xlsx2csv2json import (
            SelfOverwriteRefused, MultiTableRequiresOutputDir,
            MultiSheetRequiresOutputDir, HeaderRowsConflict,
            InvalidSheetNameForFsPath, OutputPathTraversal,
            FormatLockedByShim, PostValidateFailed,
        )
        self.assertEqual(SelfOverwriteRefused.CODE, 6)
        self.assertEqual(MultiTableRequiresOutputDir.CODE, 2)
        self.assertEqual(MultiSheetRequiresOutputDir.CODE, 2)
        self.assertEqual(HeaderRowsConflict.CODE, 2)
        self.assertEqual(InvalidSheetNameForFsPath.CODE, 2)
        self.assertEqual(OutputPathTraversal.CODE, 2)
        self.assertEqual(FormatLockedByShim.CODE, 2)
        self.assertEqual(PostValidateFailed.CODE, 7)

    def test_helpers_marshal_to_argv_and_fail_on_missing_input(self) -> None:
        """010-03: helpers now call main() which parses argv. Passing a
        non-existent input path surfaces FileNotFoundError → envelope
        code 1 (not the stub sentinel).
        """
        from xlsx2csv2json import convert_xlsx_to_csv, convert_xlsx_to_json
        # Suppress stderr noise from the envelope.
        import io
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            rc_csv = convert_xlsx_to_csv("/nonexistent.xlsx")
            rc_json = convert_xlsx_to_json("/nonexistent.xlsx")
        finally:
            sys.stderr = old
        self.assertEqual(rc_csv, 1)
        self.assertEqual(rc_json, 1)

    def test_main_missing_input_argv_returns_2(self) -> None:
        """010-03: argparse usage error (no positional INPUT) → exit 2."""
        from xlsx2csv2json import main
        import io
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            rc = main([], format_lock="csv")
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
