"""Unit tests for the package-structure check in `office/validate.py`.

2026-05-12 scratch-leak follow-up. Validates that the new
`_check_package_structure` helper + the `--strict` integration in
`main()` correctly flag ZIP entries that do not live under the
canonical OOXML hierarchy. Catches the class of bug that allowed
`docx_replace.py --insert-after` to leak `insert.docx` and
`insert_unpacked/` into the final container undetected.

Runs against the docx/xlsx/pptx variants in parallel — the test file
is part of `office/` and is byte-replicated across the three OOXML
skills, so it must work for each.

Run from inside the skill:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_validate_package_structure
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent
sys.path.insert(0, str(SCRIPTS))

from office.validate import (  # noqa: E402
    _ALLOWED_PREFIXES_BY_EXT,
    _check_package_structure,
    main as validate_main,
)


_MIN_DOCX_PARTS: dict[str, str] = {
    "[Content_Types].xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        '</Types>'
    ),
    "_rels/.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    ),
    "word/document.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p/></w:body>'
        '</w:document>'
    ),
    "word/_rels/document.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    ),
}


def _build_zip(parts: dict[str, bytes | str], suffix: str = ".docx") -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for path, body in parts.items():
            data = body.encode("utf-8") if isinstance(body, str) else body
            z.writestr(path, data)
    return Path(name)


class TestCheckPackageStructureHelper(unittest.TestCase):
    """Unit-level: _check_package_structure() output."""

    def test_clean_package_returns_empty(self) -> None:
        path = _build_zip(_MIN_DOCX_PARTS)
        try:
            leaks = _check_package_structure(
                path, _ALLOWED_PREFIXES_BY_EXT[".docx"],
            )
        finally:
            path.unlink()
        self.assertEqual(leaks, [])

    def test_top_level_leak_detected(self) -> None:
        parts = dict(_MIN_DOCX_PARTS)
        parts["insert.docx"] = b"scratch-payload"
        path = _build_zip(parts)
        try:
            leaks = _check_package_structure(
                path, _ALLOWED_PREFIXES_BY_EXT[".docx"],
            )
        finally:
            path.unlink()
        self.assertEqual(leaks, ["insert.docx"])

    def test_nested_scratch_dir_detected(self) -> None:
        parts = dict(_MIN_DOCX_PARTS)
        parts["insert_unpacked/word/document.xml"] = b"<doc/>"
        path = _build_zip(parts)
        try:
            leaks = _check_package_structure(
                path, _ALLOWED_PREFIXES_BY_EXT[".docx"],
            )
        finally:
            path.unlink()
        self.assertEqual(leaks, ["insert_unpacked/word/document.xml"])

    def test_corrupt_zip_returns_empty_silently(self) -> None:
        """Non-ZIP / corrupt file is the per-format validator's job to
        diagnose; the package-structure helper must not raise."""
        fd, name = tempfile.mkstemp(suffix=".docx")
        try:
            os.close(fd)
            Path(name).write_bytes(b"not a zip at all")
            leaks = _check_package_structure(
                Path(name), _ALLOWED_PREFIXES_BY_EXT[".docx"],
            )
        finally:
            Path(name).unlink()
        self.assertEqual(leaks, [])

    def test_xlsx_prefix_set_routes_to_xl(self) -> None:
        """xlsx must accept `xl/` and reject `word/`."""
        prefixes = _ALLOWED_PREFIXES_BY_EXT[".xlsx"]
        self.assertIn("xl/", prefixes)
        self.assertNotIn("word/", prefixes)
        self.assertNotIn("ppt/", prefixes)

    def test_pptx_prefix_set_routes_to_ppt(self) -> None:
        """pptx must accept `ppt/` and reject `word/` and `xl/`."""
        prefixes = _ALLOWED_PREFIXES_BY_EXT[".pptx"]
        self.assertIn("ppt/", prefixes)
        self.assertNotIn("word/", prefixes)
        self.assertNotIn("xl/", prefixes)


class TestValidateCliStrictMode(unittest.TestCase):
    """End-to-end via main(): clean → exit 0, leak → warn (exit 0
    without --strict, exit 1 with --strict)."""

    def test_clean_docx_exits_zero(self) -> None:
        path = _build_zip(_MIN_DOCX_PARTS)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = validate_main([str(path)])
        finally:
            path.unlink()
        self.assertEqual(rc, 0)
        # No package-leak warning in clean output.
        self.assertNotIn("non-OOXML package member", buf.getvalue())

    def test_polluted_docx_warns_but_exits_zero_without_strict(self) -> None:
        parts = dict(_MIN_DOCX_PARTS)
        parts["insert.docx"] = b"scratch"
        parts["insert_unpacked/x"] = b"scratch"
        path = _build_zip(parts)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = validate_main([str(path)])
        finally:
            path.unlink()
        self.assertEqual(rc, 0, "Warnings alone must not fail without --strict")
        out = buf.getvalue()
        self.assertIn("non-OOXML package member: 'insert.docx'", out)
        self.assertIn("non-OOXML package member: 'insert_unpacked/x'", out)

    def test_polluted_docx_strict_exits_one(self) -> None:
        parts = dict(_MIN_DOCX_PARTS)
        parts["scratch_leftover.tmp"] = b"scratch"
        path = _build_zip(parts)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = validate_main([str(path), "--strict"])
        finally:
            path.unlink()
        self.assertEqual(
            rc, 1,
            "--strict must promote package-structure warning to exit 1",
        )


if __name__ == "__main__":
    unittest.main()
