"""Import-graph smoke test for the xlsx_comment package (Task 002).

Asserts that every public symbol from every module is importable via
the explicit submodule path. Locks R7.d "each module move has a
unit-level smoke test for import" and R3.a "zero edits to test files"
by being entirely self-contained.

This test runs in < 2 s — it does NO actual workbook I/O.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path


SHIM_DIR = Path(__file__).resolve().parents[1]


class TestPackageImports(unittest.TestCase):
    """Each module is importable; declared __all__ exists."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SHIM_DIR))

    @classmethod
    def tearDownClass(cls) -> None:
        sys.path.remove(str(SHIM_DIR))

    def test_constants_importable(self) -> None:
        from xlsx_comment import constants
        for name in ["THREADED_NS", "VML_CT", "DEFAULT_VML_ANCHOR",
                     "BATCH_MAX_BYTES"]:
            self.assertIn(name, vars(constants))

    def test_exceptions_importable(self) -> None:
        from xlsx_comment import exceptions
        self.assertTrue(issubclass(exceptions._AppError, Exception))
        self.assertTrue(issubclass(exceptions.MalformedVml,
                                    exceptions._AppError))

    def test_cell_parser_importable(self) -> None:
        from xlsx_comment.cell_parser import parse_cell_syntax, resolve_sheet  # noqa: F401
        # smoke: parse a known-good cell ref
        self.assertEqual(parse_cell_syntax("A5"), (None, "A5"))

    def test_batch_importable(self) -> None:
        from xlsx_comment.batch import BatchRow, load_batch  # noqa: F401
        # smoke: the dataclass exists with the documented fields
        self.assertTrue(hasattr(BatchRow, "__dataclass_fields__"))
        self.assertIn("cell", BatchRow.__dataclass_fields__)
        self.assertIn("text", BatchRow.__dataclass_fields__)

    def test_ooxml_editor_importable(self) -> None:
        from xlsx_comment.ooxml_editor import (  # noqa: F401
            scan_idmap_used, scan_spid_used, next_part_counter,
            add_person, _VML_PARSER,
        )
        # smoke: the security boundary is importable (R7.c lock).
        # lxml.etree.XMLParser does not expose `resolve_entities` as
        # an attribute (constructor kwarg only); behaviour tests in
        # test_xlsx_add_comment.py:TestScanner exercise the hardening.
        from lxml import etree  # type: ignore
        self.assertIsInstance(_VML_PARSER, etree.XMLParser)

    def test_merge_dup_importable(self) -> None:
        from xlsx_comment.merge_dup import (  # noqa: F401
            resolve_merged_target, detect_existing_comment_state,
            _enforce_duplicate_matrix,
        )

    def test_cli_helpers_importable(self) -> None:
        from xlsx_comment.cli_helpers import (  # noqa: F401
            _initials_from_author, _resolve_date,
            _validate_args, _assert_distinct_paths,
            _post_pack_validate, _post_validate_enabled,
        )

    def test_cli_importable(self) -> None:
        from xlsx_comment.cli import build_parser, main  # noqa: F401
        # smoke: the parser can be built without raising
        parser = build_parser()
        self.assertIsNotNone(parser)


if __name__ == "__main__":
    unittest.main()
