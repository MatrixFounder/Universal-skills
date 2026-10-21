"""Regression tests: docx2md.js keeps every visible run's text, including identical neighbours.

Word splits a typed number across sibling <w:r> runs whenever an edit changes the rsid, so
"11" is routinely stored as run "1" + run "1". Word renders both runs, and so must the
converter: dropping the second one silently turns requirement BR-11 into BR-1 and 100 into 10.
Fixtures are built in memory as raw WordprocessingML (stdlib zipfile), so the run split is
exactly the one Word writes, then converted through `node docx2md.js`.

Run::  cd skills/docx/scripts && ./.venv/bin/python -m unittest tests.test_docx2md_runs -v
"""

import os
import subprocess
import tempfile
import unittest
import zipfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
DOCX2MD = os.path.join(SCRIPTS, "docx2md.js")

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{body}</w:body></w:document>"
)
LANG_EN = '<w:rPr><w:lang w:val="en-US"/></w:rPr>'


def _run(text, rpr=""):
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _para(*runs):
    return "<w:p>" + "".join(runs) + "</w:p>"


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_node(), "node not on PATH")
class IdenticalAdjacentRunsSurvive(unittest.TestCase):
    """Identical neighbouring runs are content, not a stutter to collapse."""

    def _convert(self, *paragraphs):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "runs.docx")
            with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("[Content_Types].xml", CONTENT_TYPES)
                z.writestr("_rels/.rels", ROOT_RELS)
                z.writestr("word/document.xml", DOCUMENT.format(body="".join(paragraphs)))
            out = os.path.join(tmp, "runs.md")
            proc = subprocess.run(
                ["node", DOCX2MD, src, out], capture_output=True, text=True, cwd=SCRIPTS
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, encoding="utf-8") as f:
                return f.read()

    def test_requirement_id_eleven(self):
        md = self._convert(_para(_run("BR-"), _run("1"), _run("1"), _run(". Анализ обращений")))
        self.assertIn("BR-11. Анализ обращений", md)

    def test_section_number_eleven(self):
        md = self._convert(_para(_run("1"), _run("1"), _run(".3. Аналитические маркеры")))
        self.assertIn("11.3. Аналитические маркеры", md)

    def test_number_split_into_three_runs(self):
        md = self._convert(_para(_run("SLA: "), _run("1"), _run("0"), _run("0"), _run(" мин")))
        self.assertIn("SLA: 100 мин", md)

    def test_runs_with_different_properties(self):
        # tmp/test-data/Test_2.docx row-number cell: Word and LibreOffice both render "22".
        md = self._convert(_para(_run("2", LANG_EN), _run("2")))
        self.assertIn("22", md)

    def test_identical_short_words(self):
        md = self._convert(_para(_run("ha"), _run("ha"), _run("!")))
        self.assertIn("haha!", md)


if __name__ == "__main__":
    unittest.main()
