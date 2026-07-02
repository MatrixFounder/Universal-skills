"""Unit tests for docx_accept_changes.verify_no_tracked_changes.

Locks the LOUD-failure contract for the LibreOffice 26.2 silent no-op
(CLI macro:/// dropped, soffice exits 0, output = unmodified copy):
verification must catch EVERY OOXML revision-marker family, not just
<w:ins>/<w:del> — tracked moves, tracked formatting changes and
table-cell revisions ship in real documents whose only edits are a
bolded word or a moved paragraph (VDD finding, 2026-07-02).

Run:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest tests.test_docx_accept_verify
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent  # skills/docx/scripts
sys.path.insert(0, str(SCRIPTS))

from docx_accept_changes import (  # noqa: E402
    AcceptChangesVerificationError,
    verify_no_tracked_changes,
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                Target="word/document.xml"/>
</Relationships>"""

DOC_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}</w:body>
</w:document>"""

REV = 'w:id="1" w:author="A" w:date="2026-04-24T09:00:00Z"'


class TestVerifyNoTrackedChanges(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="accept-verify-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _docx(self, body: str, name: str = "t.docx") -> Path:
        path = self.tmp / name
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", DOC_TEMPLATE.format(body=body))
        return path

    def _assert_raises(self, body: str) -> None:
        with self.assertRaises(AcceptChangesVerificationError):
            verify_no_tracked_changes(self._docx(body))

    # --- revision families that MUST be detected -----------------------
    def test_insertion_detected(self) -> None:
        self._assert_raises(f"<w:p><w:ins {REV}><w:r><w:t>x</w:t></w:r></w:ins></w:p>")

    def test_deletion_detected(self) -> None:
        self._assert_raises(
            f'<w:p><w:del {REV}><w:r><w:delText xml:space="preserve">x</w:delText></w:r></w:del></w:p>'
        )

    def test_move_detected(self) -> None:
        self._assert_raises(
            f'<w:p><w:moveFromRangeStart {REV} w:name="m1"/>'
            f"<w:moveFrom {REV}><w:r><w:t>x</w:t></w:r></w:moveFrom>"
            f'<w:moveFromRangeEnd w:id="1"/></w:p>'
        )

    def test_move_to_detected(self) -> None:
        self._assert_raises(f"<w:p><w:moveTo {REV}><w:r><w:t>x</w:t></w:r></w:moveTo></w:p>")

    def test_run_format_change_detected(self) -> None:
        """A document whose ONLY revision is tracked formatting (user
        bolded a word with Track Changes on) — the exact silent-no-op
        residue the original <w:ins|w:del>-only regex shipped."""
        self._assert_raises(
            f"<w:p><w:r><w:rPr><w:b/><w:rPrChange {REV}><w:rPr/></w:rPrChange></w:rPr>"
            f"<w:t>x</w:t></w:r></w:p>"
        )

    def test_paragraph_format_change_detected(self) -> None:
        self._assert_raises(
            f"<w:p><w:pPr><w:pPrChange {REV}><w:pPr/></w:pPrChange></w:pPr></w:p>"
        )

    def test_cell_insertion_detected(self) -> None:
        self._assert_raises(
            f"<w:tbl><w:tr><w:tc><w:tcPr><w:cellIns {REV}/></w:tcPr>"
            f"<w:p/></w:tc></w:tr></w:tbl>"
        )

    def test_newline_split_attributes_detected(self) -> None:
        """Legal XML: whitespace (incl. newline) between tag name and
        attributes must still match — [\\s>/], not [ >/]."""
        self._assert_raises(f"<w:p><w:ins\n    {REV}><w:r><w:t>x</w:t></w:r></w:ins></w:p>")

    def test_foreign_prefix_detected(self) -> None:
        """The WML namespace may be bound to a non-'w' prefix by
        non-Word producers; detection is prefix-agnostic."""
        path = self.tmp / "prefix.docx"
        doc = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<x:document xmlns:x="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<x:body><x:p><x:ins {REV.replace("w:", "x:")}>'
            "<x:r><x:t>t</x:t></x:r></x:ins></x:p></x:body></x:document>"
        )
        with zipfile.ZipFile(str(path), "w") as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", doc)
        with self.assertRaises(AcceptChangesVerificationError):
            verify_no_tracked_changes(path)

    def test_header_part_scanned(self) -> None:
        path = self._docx("<w:p><w:r><w:t>clean body</w:t></w:r></w:p>")
        # append a header part carrying a revision
        with zipfile.ZipFile(str(path), "a") as z:
            z.writestr(
                "word/header1.xml",
                DOC_TEMPLATE.format(
                    body=f"<w:p><w:ins {REV}><w:r><w:t>h</w:t></w:r></w:ins></w:p>"
                ),
            )
        with self.assertRaises(AcceptChangesVerificationError):
            verify_no_tracked_changes(path)

    # --- clean content that must NOT false-positive ---------------------
    def test_clean_document_passes(self) -> None:
        verify_no_tracked_changes(
            self._docx("<w:p><w:r><w:t>No revisions here.</w:t></w:r></w:p>")
        )

    def test_table_borders_not_false_positive(self) -> None:
        """<w:insideH>/<w:insideV> share the 'ins' prefix but are plain
        table borders."""
        verify_no_tracked_changes(
            self._docx(
                "<w:tbl><w:tblPr><w:tblBorders>"
                '<w:insideH w:val="single"/><w:insideV w:val="single"/>'
                "</w:tblBorders></w:tblPr><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>"
            )
        )


if __name__ == "__main__":
    unittest.main()
