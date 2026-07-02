#!/usr/bin/env python3
"""Deterministic seeded-fixture generator for the docx accept-changes evals.

Revision markers are planted MECHANICALLY (ground truth by construction,
guide §6.5). Fixtures are deliberately MINIMAL 3-part packages
([Content_Types].xml + _rels/.rels + word/document.xml): a genuine
LibreOffice re-save always adds parts (styles, settings, docProps…), so
"output package grew" doubles as a cheap anti-tamper signal the grader
uses to tell a real accept from hand-stripped XML.

Run from this directory:
    python3 make_fixtures.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

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

REV = 'w:id="1" w:author="Alice" w:date="2026-04-24T09:00:00Z"'


def _build(name: str, body: str) -> None:
    with zipfile.ZipFile(str(HERE / name), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", DOC_TEMPLATE.format(body=body))


def make_tracked_insdel() -> None:
    """D-01: classic run insertion + deletion."""
    _build(
        "contract_tracked.docx",
        '<w:p><w:r><w:t xml:space="preserve">Оплата производится </w:t></w:r>'
        f'<w:ins {REV}><w:r><w:t xml:space="preserve">в течение 10 рабочих дней </w:t></w:r></w:ins>'
        f'<w:del {REV}><w:r><w:delText xml:space="preserve">немедленно </w:delText></w:r></w:del>'
        "<w:r><w:t>после подписания акта.</w:t></w:r></w:p>",
    )


def make_tracked_format_only() -> None:
    """D-02: the ONLY revision is tracked formatting (w:rPrChange) —
    the exact family the pre-fix verifier missed (VDD HIGH, 2026-07-02)."""
    _build(
        "report_fmt.docx",
        "<w:p><w:r><w:rPr><w:b/>"
        f"<w:rPrChange {REV}><w:rPr/></w:rPrChange>"
        '</w:rPr><w:t xml:space="preserve">Квартальные итоги</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>Выручка выросла на 12%.</w:t></w:r></w:p>",
    )


def make_clean() -> None:
    """D-03 (negative): no revisions at all — must not false-alarm."""
    _build(
        "clean.docx",
        "<w:p><w:r><w:t>Совершенно обычный документ без правок.</w:t></w:r></w:p>",
    )


if __name__ == "__main__":
    make_tracked_insdel()
    make_tracked_format_only()
    make_clean()
    print("fixtures written:", sorted(p.name for p in HERE.glob("*.docx")))
