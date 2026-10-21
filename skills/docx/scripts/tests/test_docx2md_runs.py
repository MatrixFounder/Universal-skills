"""Regression tests: docx2md.js emits the text a reader of the document sees, run by run.

Two run-level rules, both measured against what Word displays:
  - Identical neighbouring runs are content. Word splits a typed number across sibling
    <w:r> runs whenever an edit changes the rsid, so "11" is routinely stored as run "1" +
    run "1"; dropping the second one silently turns requirement BR-11 into BR-1.
  - Hidden runs (<w:vanish/>, direct or through a style) are not shown or printed by Word,
    so they are dropped by default; `--keep-hidden-text` keeps them.
Fixtures are built in memory as raw WordprocessingML (stdlib zipfile), so the XML is exactly
the one Word writes, then converted through `node docx2md.js`.

Run::  cd skills/docx/scripts && ./.venv/bin/python -m unittest tests.test_docx2md_runs -v
"""

import os
import subprocess
import tempfile
import unittest
import zipfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
DOCX2MD = os.path.join(SCRIPTS, "docx2md.js")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WML_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml"

LANG_EN = '<w:rPr><w:lang w:val="en-US"/></w:rPr>'
VANISH = "<w:rPr><w:vanish/></w:rPr>"

STYLE_NORMAL = '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
STYLE_HIDDEN_BASE = (
    '<w:style w:type="character" w:styleId="HiddenBase"><w:name w:val="Hidden Base"/>'
    "<w:rPr><w:vanish/></w:rPr></w:style>"
)
STYLE_HIDDEN_CHILD = (
    '<w:style w:type="character" w:styleId="HiddenChild"><w:name w:val="Hidden Child"/>'
    '<w:basedOn w:val="HiddenBase"/></w:style>'
)
STYLE_HIDDEN_PARA = (
    '<w:style w:type="paragraph" w:styleId="HiddenPara"><w:name w:val="Hidden Para"/>'
    "<w:rPr><w:vanish/></w:rPr></w:style>"
)
STYLE_VISIBLE_CHAR = (
    '<w:style w:type="character" w:styleId="VisibleChar"><w:name w:val="Visible Char"/>'
    '<w:rPr><w:vanish w:val="0"/></w:rPr></w:style>'
)
STYLE_VISIBLE_PARA = (
    '<w:style w:type="paragraph" w:styleId="VisiblePara"><w:name w:val="Visible Para"/>'
    '<w:rPr><w:vanish w:val="0"/></w:rPr></w:style>'
)
DOC_DEFAULTS_HIDDEN = "<w:docDefaults><w:rPrDefault><w:rPr><w:vanish/></w:rPr></w:rPrDefault></w:docDefaults>"


def _run(text, rpr=""):
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _styled(text, style_id, extra_rpr=""):
    return _run(text, f'<w:rPr><w:rStyle w:val="{style_id}"/>{extra_rpr}</w:rPr>')


def _para(*runs, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return "<w:p>" + ppr + "".join(runs) + "</w:p>"


def _field(instr, result, rpr=""):
    def fld(kind):
        return f'<w:r>{rpr}<w:fldChar w:fldCharType="{kind}"/></w:r>'

    return (
        fld("begin")
        + f'<w:r>{rpr}<w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
        + fld("separate")
        + _run(result, rpr)
        + fld("end")
    )


def _build_docx(path, body, styles=None, footnotes=None):
    overrides = [("/word/document.xml", f"{WML_CT}.document.main+xml")]
    rels = []
    if styles is not None:
        overrides.append(("/word/styles.xml", f"{WML_CT}.styles+xml"))
        rels.append(("styles", "styles.xml"))
    if footnotes is not None:
        overrides.append(("/word/footnotes.xml", f"{WML_CT}.footnotes+xml"))
        rels.append(("footnotes", "footnotes.xml"))
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(f'<Override PartName="{p}" ContentType="{ct}"/>' for p, ct in overrides)
        + "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL_NS}/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="{REL_NS}/{kind}" Target="{target}"/>'
            for i, (kind, target) in enumerate(rels, start=1)
        )
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr(
            "word/document.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>',
        )
        if styles is not None:
            z.writestr("word/styles.xml", f'<w:styles xmlns:w="{W_NS}">{styles}</w:styles>')
        if footnotes is not None:
            z.writestr("word/footnotes.xml", f'<w:footnotes xmlns:w="{W_NS}">{footnotes}</w:footnotes>')


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


class _Docx2mdCase(unittest.TestCase):
    def _convert(self, *paragraphs, styles=None, footnotes=None, args=()):
        """Build a docx from `paragraphs`, convert it, return (markdown, stdout)."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "runs.docx")
            _build_docx(src, "".join(paragraphs), styles, footnotes)
            out = os.path.join(tmp, "runs.md")
            proc = subprocess.run(
                ["node", DOCX2MD, src, out, *args], capture_output=True, text=True, cwd=SCRIPTS
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, encoding="utf-8") as f:
                return f.read(), proc.stdout


@unittest.skipUnless(_have_node(), "node not on PATH")
class IdenticalAdjacentRunsSurvive(_Docx2mdCase):
    """Identical neighbouring runs are content, not a stutter to collapse."""

    def test_requirement_id_eleven(self):
        md, _ = self._convert(_para(_run("BR-"), _run("1"), _run("1"), _run(". Анализ обращений")))
        self.assertIn("BR-11. Анализ обращений", md)

    def test_section_number_eleven(self):
        md, _ = self._convert(_para(_run("1"), _run("1"), _run(".3. Аналитические маркеры")))
        self.assertIn("11.3. Аналитические маркеры", md)

    def test_number_split_into_three_runs(self):
        md, _ = self._convert(_para(_run("SLA: "), _run("1"), _run("0"), _run("0"), _run(" мин")))
        self.assertIn("SLA: 100 мин", md)

    def test_runs_with_different_properties(self):
        # tmp/test-data/Test_2.docx row-number cell: Word and LibreOffice both render "22".
        md, _ = self._convert(_para(_run("2", LANG_EN), _run("2")))
        self.assertIn("22", md)

    def test_identical_short_words(self):
        md, _ = self._convert(_para(_run("ha"), _run("ha"), _run("!")))
        self.assertIn("haha!", md)


@unittest.skipUnless(_have_node(), "node not on PATH")
class HiddenTextDropped(_Docx2mdCase):
    """Runs Word hides (<w:vanish/>) are dropped by default and kept by --keep-hidden-text.

    Expected visibility of every style combination was checked in Microsoft Word for Mac.
    """

    STYLES = (
        STYLE_NORMAL + STYLE_HIDDEN_BASE + STYLE_HIDDEN_CHILD + STYLE_HIDDEN_PARA
        + STYLE_VISIBLE_CHAR + STYLE_VISIBLE_PARA
    )

    def test_direct_vanish_dropped_and_reported(self):
        md, stdout = self._convert(_para(_run("visible "), _run("SECRET", VANISH), _run("tail")))
        self.assertIn("visible tail", md)
        self.assertNotIn("SECRET", md)
        self.assertIn("Dropped 1 hidden run(s)", stdout)

    def test_character_style_chain(self):
        md, _ = self._convert(
            _para(_run("shown "), _styled("BASE", "HiddenBase"), _styled("CHILD", "HiddenChild"), _run("end")),
            styles=self.STYLES,
        )
        self.assertIn("shown end", md)
        self.assertNotIn("BASE", md)
        self.assertNotIn("CHILD", md)

    def test_paragraph_style(self):
        md, _ = self._convert(
            _para(_run("WHOLE PARAGRAPH"), style="HiddenPara"),
            _para(_run("next paragraph")),
            styles=self.STYLES,
        )
        self.assertNotIn("WHOLE PARAGRAPH", md)
        self.assertIn("next paragraph", md)

    def test_hidden_character_style_toggles_hidden_paragraph_style(self):
        # vanish is a toggle property (ECMA-376 §17.7.3): hidden XOR hidden shows in Word.
        md, _ = self._convert(_para(_styled("TOGGLED", "HiddenBase"), style="HiddenPara"), styles=self.STYLES)
        self.assertIn("TOGGLED", md)

    def test_character_style_cannot_unhide_hidden_paragraph_style(self):
        # An explicit false in a style adds nothing to the XOR; Word keeps the run hidden.
        md, _ = self._convert(
            _para(_styled("STILLHIDDEN", "VisibleChar"), style="HiddenPara"),
            _para(_run("next paragraph")),
            styles=self.STYLES,
        )
        self.assertNotIn("STILLHIDDEN", md)
        self.assertIn("next paragraph", md)

    def test_doc_defaults_apply_only_without_style_setting(self):
        md, _ = self._convert(
            _para(_run("DEFAULTONLY")),
            _para(_styled("DEFAULTPLUSCHAR", "HiddenBase")),
            _para(_run("visible paragraph style"), style="VisiblePara"),
            _para(_run("direct off", '<w:rPr><w:vanish w:val="0"/></w:rPr>')),
            styles=DOC_DEFAULTS_HIDDEN + self.STYLES,
        )
        self.assertNotIn("DEFAULTONLY", md)
        self.assertNotIn("DEFAULTPLUSCHAR", md)
        self.assertIn("visible paragraph style", md)
        self.assertIn("direct off", md)

    def test_explicit_visible_overrides_hidden_style(self):
        md, _ = self._convert(
            _para(_styled("OVERRIDE", "HiddenBase", '<w:vanish w:val="0"/>')),
            styles=self.STYLES,
        )
        self.assertIn("OVERRIDE", md)

    def test_web_hidden_is_not_hidden(self):
        # TOC page numbers carry <w:webHidden/>: hidden in Web Layout only, printed as usual.
        md, _ = self._convert(_para(_run("Page "), _run("42", "<w:rPr><w:webHidden/></w:rPr>")))
        self.assertIn("Page 42", md)

    def test_hidden_field_keeps_following_field_intact(self):
        md, _ = self._convert(
            _para(
                _field('HYPERLINK "https://hidden.example"', "HIDDENLINK", VANISH),
                _run("before "),
                _field('HYPERLINK "https://visible.example"', "visible link"),
            )
        )
        self.assertNotIn("HIDDENLINK", md)
        self.assertIn("[visible link](https://visible.example)", md)

    def test_hidden_footnote_text(self):
        footnotes = (
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:id="1"><w:p>'
            + _run("Note ")
            + _run("NOTEHIDDEN", VANISH)
            + _run("text")
            + "</w:p></w:footnote>"
        )
        md, _ = self._convert(
            _para(_run("Body"), '<w:r><w:footnoteReference w:id="1"/></w:r>'), footnotes=footnotes
        )
        self.assertIn("Note text", md)
        self.assertNotIn("NOTEHIDDEN", md)

    def test_keep_hidden_text_flag(self):
        md, stdout = self._convert(
            _para(_run("visible "), _run("SECRET", VANISH), _styled(" STYLED", "HiddenBase")),
            styles=self.STYLES,
            args=("--keep-hidden-text",),
        )
        self.assertIn("visible SECRET STYLED", md)
        self.assertNotIn("hidden run", stdout)


if __name__ == "__main__":
    unittest.main()
