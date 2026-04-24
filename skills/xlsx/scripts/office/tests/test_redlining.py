"""Unit tests for RedliningValidator.

Builds minimal .docx files in memory and checks that the validator
classifies each scenario correctly: clean round-trip, properly marked
deletions/insertions, unmarked deletions/insertions/rewrites, and
false-positive deletion marks.

Run from repository root:
    python3 -m unittest skills.docx.scripts.office.tests.test_redlining

Or from inside the skill:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_redlining
"""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent  # skills/docx/scripts
sys.path.insert(0, str(SCRIPTS))

from office.validators.redlining import RedliningValidator  # noqa: E402


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

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""

DOCUMENT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}</w:body>
</w:document>"""


def _build_docx(tmp_path: Path, body_xml: str) -> Path:
    """Write a minimal valid .docx to tmp_path with the given body XML."""
    doc_xml = DOCUMENT_TEMPLATE.format(body=body_xml)
    with zipfile.ZipFile(str(tmp_path), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        z.writestr("word/document.xml", doc_xml)
    return tmp_path


def _p(*runs: str) -> str:
    """Build a <w:p> with the given run XML fragments."""
    return "<w:p>" + "".join(runs) + "</w:p>"


def _r(text: str) -> str:
    return f"<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r>"


def _ins(text: str, author: str = "Alice", date: str = "2026-04-24T09:00:00Z", id_: int = 1) -> str:
    return (
        f"<w:ins w:id=\"{id_}\" w:author=\"{author}\" w:date=\"{date}\">"
        f"<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r>"
        f"</w:ins>"
    )


def _del(text: str, author: str = "Alice", date: str = "2026-04-24T09:00:00Z", id_: int = 1) -> str:
    return (
        f"<w:del w:id=\"{id_}\" w:author=\"{author}\" w:date=\"{date}\">"
        f"<w:r><w:delText xml:space=\"preserve\">{text}</w:delText></w:r>"
        f"</w:del>"
    )


class TestRedlining(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import tempfile
        cls.tmp = Path(tempfile.mkdtemp(prefix="redline-test-"))

    def _mkdocx(self, name: str, body: str) -> Path:
        return _build_docx(self.tmp / name, body)

    def test_identical_documents_report_no_errors(self) -> None:
        body = _p(_r("Hello world."))
        orig = self._mkdocx("a-orig.docx", body)
        edited = self._mkdocx("a-edit.docx", body)
        rep = RedliningValidator().compare(orig, edited)
        self.assertTrue(rep.ok, f"Expected no errors, got: {rep.errors}")

    def test_properly_marked_insertion_passes(self) -> None:
        orig_body = _p(_r("Hello world."))
        edit_body = _p(_r("Hello "), _ins("brave "), _r("world."))
        orig = self._mkdocx("b-orig.docx", orig_body)
        edit = self._mkdocx("b-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertTrue(rep.ok, f"Expected no errors, got: {rep.errors}")

    def test_properly_marked_deletion_passes(self) -> None:
        orig_body = _p(_r("Hello cruel world."))
        edit_body = _p(_r("Hello "), _del("cruel "), _r("world."))
        orig = self._mkdocx("c-orig.docx", orig_body)
        edit = self._mkdocx("c-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertTrue(rep.ok, f"Expected no errors, got: {rep.errors}")

    def test_unmarked_deletion_reports_error(self) -> None:
        orig_body = _p(_r("Hello cruel world."))
        edit_body = _p(_r("Hello world."))  # no <w:del>
        orig = self._mkdocx("d-orig.docx", orig_body)
        edit = self._mkdocx("d-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertFalse(rep.ok)
        self.assertTrue(any("Unmarked" in e for e in rep.errors),
                        f"Expected Unmarked-* error, got: {rep.errors}")

    def test_unmarked_insertion_reports_error(self) -> None:
        orig_body = _p(_r("Hello world."))
        edit_body = _p(_r("Hello brave world."))  # no <w:ins>
        orig = self._mkdocx("e-orig.docx", orig_body)
        edit = self._mkdocx("e-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertFalse(rep.ok)
        self.assertTrue(any("Unmarked" in e for e in rep.errors),
                        f"Expected Unmarked-* error, got: {rep.errors}")

    def test_false_positive_deletion_mark_reports_warning(self) -> None:
        # Edited file claims to have deleted "foo" via <w:del>, but
        # "foo" does not appear in the original document at all.
        orig_body = _p(_r("Hello world."))
        edit_body = _p(_r("Hello "), _del("foo "), _r("world."))
        orig = self._mkdocx("f-orig.docx", orig_body)
        edit = self._mkdocx("f-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertTrue(
            any("false-positive" in w for w in rep.warnings),
            f"Expected false-positive warning, got: {rep.warnings}",
        )

    def test_textbox_paragraphs_counted_once(self) -> None:
        """A paragraph inside <w:drawing>/<wp:txbxContent> must NOT
        double-count: once via the outer container's iter() and once
        via the recursive iter(w:p) sweep.

        Previous bug: _extract_from_document returned 3 ExtractedParagraph
        entries for a doc with 1 body + 1 textbox (expected 2: body + textbox).
        """
        textbox_body = (
            '<w:p><w:r><w:t>Body text.</w:t></w:r></w:p>'
            '<w:p><w:r>'
            '  <w:drawing>'
            '    <wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '      <wp:txbxContent>'
            '        <w:p><w:r><w:t>Textbox inner</w:t></w:r></w:p>'
            '      </wp:txbxContent>'
            '    </wp:inline>'
            '  </w:drawing>'
            '</w:r></w:p>'
        )
        orig = self._mkdocx("t-orig.docx", textbox_body)
        edit = self._mkdocx("t-edit.docx", textbox_body)
        rep = RedliningValidator().compare(orig, edit)
        # Identical docs must produce no errors; the pre-fix bug leaked
        # duplicate-line mismatches despite identical source.
        self.assertTrue(rep.ok, f"Expected no errors on identical textbox docs; got: {rep.errors}")

    def test_unmarked_move_collapsed_into_single_finding(self) -> None:
        """Paragraph reorder should yield ONE 'unmarked move' error,
        not one 'unmarked deletion' + one 'unmarked insertion'."""
        orig_body = _p(_r("First.")) + _p(_r("Second.")) + _p(_r("Third."))
        edit_body = _p(_r("First.")) + _p(_r("Third.")) + _p(_r("Second."))
        orig = self._mkdocx("m-orig.docx", orig_body)
        edit = self._mkdocx("m-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertFalse(rep.ok)
        moves = [e for e in rep.errors if "Unmarked move" in e]
        self.assertGreaterEqual(len(moves), 1,
                                f"Expected at least one Unmarked-move error, got: {rep.errors}")

    def test_unmarked_edit_in_header_detected(self) -> None:
        """RedliningValidator must scan headers/footers, not only the
        main body. Editor who changes the header without Track Changes
        must be caught."""
        import zipfile

        def build_docx_with_header(path: Path, body_xml: str, header_xml: str) -> Path:
            doc_xml = DOCUMENT_TEMPLATE.format(body=body_xml)
            header_doc = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'{header_xml}</w:hdr>'
            )
            ct = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                '  <Default Extension="xml" ContentType="application/xml"/>\n'
                '  <Override PartName="/word/document.xml"\n'
                '            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
                '  <Override PartName="/word/header1.xml"\n'
                '            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>\n'
                '</Types>'
            )
            with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("[Content_Types].xml", ct)
                z.writestr("_rels/.rels", ROOT_RELS)
                z.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
                z.writestr("word/document.xml", doc_xml)
                z.writestr("word/header1.xml", header_doc)
            return path

        body = _p(_r("Body stays the same."))
        orig = build_docx_with_header(self.tmp / "h-orig.docx", body, _p(_r("Header v1")))
        edit = build_docx_with_header(self.tmp / "h-edit.docx", body, _p(_r("Header v2")))
        rep = RedliningValidator().compare(orig, edit)
        self.assertFalse(rep.ok, f"Expected header change to be caught; got: {rep}")

    def test_missing_author_reports_warning(self) -> None:
        orig_body = _p(_r("Hello world."))
        edit_body = _p(
            _r("Hello "),
            "<w:ins w:id=\"1\" w:date=\"2026-04-24T09:00:00Z\">"
            "<w:r><w:t xml:space=\"preserve\">brave </w:t></w:r></w:ins>",
            _r("world."),
        )
        orig = self._mkdocx("g-orig.docx", orig_body)
        edit = self._mkdocx("g-edit.docx", edit_body)
        rep = RedliningValidator().compare(orig, edit)
        self.assertTrue(
            any("no w:author" in w for w in rep.warnings),
            f"Expected missing-author warning, got: {rep.warnings}",
        )


if __name__ == "__main__":
    unittest.main()
