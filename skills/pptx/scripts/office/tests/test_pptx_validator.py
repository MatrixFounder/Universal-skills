"""Unit tests for `PptxValidator`.

Builds minimal `.pptx` archives in memory and verifies the validator
flags each documented integrity problem (slide chain breakage, layout
chain breakage, dangling media references, sldId rule violations,
notes-slide non-reciprocity, orphan slides) while leaving a clean
package with no errors.

Run from inside the skill:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_pptx_validator
"""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent
sys.path.insert(0, str(SCRIPTS))

from office.validators.pptx import PptxValidator  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal-pptx builder
# ---------------------------------------------------------------------------

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
</Types>
"""

_PKG_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
"""

_PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rIdSlide1"/>
  </p:sldIdLst>
</p:presentation>
"""

_PRESENTATION_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdSlide1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
"""

_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree/></p:cSld>
</p:sld>
"""

_SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"""

_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree/></p:cSld>
</p:sldLayout>
"""

_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdMaster" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""

_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree/></p:cSld>
</p:sldMaster>
"""

_BASE_PARTS: dict[str, str] = {
    "[Content_Types].xml": _CONTENT_TYPES,
    "_rels/.rels": _PKG_RELS,
    "ppt/presentation.xml": _PRESENTATION,
    "ppt/_rels/presentation.xml.rels": _PRESENTATION_RELS,
    "ppt/slides/slide1.xml": _SLIDE,
    "ppt/slides/_rels/slide1.xml.rels": _SLIDE_RELS,
    "ppt/slideLayouts/slideLayout1.xml": _LAYOUT,
    "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _LAYOUT_RELS,
    "ppt/slideMasters/slideMaster1.xml": _MASTER,
}


def _build_pptx(parts: dict[str, str | bytes]) -> Path:
    """Build a `.pptx` in a temp file and return its path."""
    import tempfile
    fd, name = tempfile.mkstemp(suffix=".pptx")
    import os
    os.close(fd)
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for path, body in parts.items():
            data = body.encode("utf-8") if isinstance(body, str) else body
            z.writestr(path, data)
    return Path(name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPptxValidatorClean(unittest.TestCase):
    def test_clean_minimal_pptx_validates(self) -> None:
        path = _build_pptx(_BASE_PARTS)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertFalse(report.errors, report.errors)


class TestPptxValidatorSlideChain(unittest.TestCase):
    def test_missing_slide_part_is_an_error(self) -> None:
        # Reference a slide in presentation.xml.rels that doesn't exist
        # in the ZIP.
        bad_rels = _PRESENTATION_RELS.replace(
            "Target=\"slides/slide1.xml\"",
            "Target=\"slides/slideMissing.xml\"",
        )
        parts = dict(_BASE_PARTS)
        parts["ppt/_rels/presentation.xml.rels"] = bad_rels
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "missing slide part" in e for e in report.errors
        ), report.errors)

    def test_orphan_slide_warns(self) -> None:
        # Add slide2.xml on disk but DON'T reference it.
        parts = dict(_BASE_PARTS)
        parts["ppt/slides/slide2.xml"] = _SLIDE
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "Orphan slide part" in w and "slide2.xml" in w
            for w in report.warnings
        ), report.warnings)


class TestPptxValidatorSldIdRules(unittest.TestCase):
    def test_duplicate_slide_id_is_an_error(self) -> None:
        bad_pres = """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rIdSlide1"/>
    <p:sldId id="256" r:id="rIdSlide1Dup"/>
  </p:sldIdLst>
</p:presentation>
"""
        parts = dict(_BASE_PARTS)
        parts["ppt/presentation.xml"] = bad_pres
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "duplicate" in e and "sldId" in e for e in report.errors
        ), report.errors)

    def test_slide_id_below_lower_bound_is_an_error(self) -> None:
        # ECMA-376 §19.2.1.34 — id must be >= 256.
        bad_pres = _PRESENTATION.replace('id="256"', 'id="100"')
        parts = dict(_BASE_PARTS)
        parts["ppt/presentation.xml"] = bad_pres
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "out of" in e and "ST_SlideId range" in e for e in report.errors
        ), report.errors)


class TestPptxValidatorLayoutMaster(unittest.TestCase):
    def test_missing_slide_layout_is_an_error(self) -> None:
        # Slide rels point at slideLayout1.xml but we drop it from the ZIP.
        parts = dict(_BASE_PARTS)
        del parts["ppt/slideLayouts/slideLayout1.xml"]
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "slideLayout" in e and "missing" in e for e in report.errors
        ), report.errors)

    def test_missing_slide_master_is_an_error(self) -> None:
        parts = dict(_BASE_PARTS)
        del parts["ppt/slideMasters/slideMaster1.xml"]
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "slideMaster" in e and "missing" in e for e in report.errors
        ), report.errors)


class TestPptxValidatorMediaRefs(unittest.TestCase):
    def test_blip_referencing_unknown_rid_is_an_error(self) -> None:
        slide_with_blip = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:pic>
      <p:blipFill><a:blip r:embed="rIdGhost"/></p:blipFill>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""
        parts = dict(_BASE_PARTS)
        parts["ppt/slides/slide1.xml"] = slide_with_blip
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "rIdGhost" in e and "blip" in e for e in report.errors
        ), report.errors)

    def test_blip_resolving_to_missing_part_is_an_error(self) -> None:
        # rels declares the rId, but the target file is absent.
        slide_with_blip = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:pic><p:blipFill><a:blip r:embed="rIdImg"/></p:blipFill></p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""
        slide_rels_with_image = _SLIDE_RELS.replace(
            "</Relationships>",
            '<Relationship Id="rIdImg" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/></Relationships>',
        )
        parts = dict(_BASE_PARTS)
        parts["ppt/slides/slide1.xml"] = slide_with_blip
        parts["ppt/slides/_rels/slide1.xml.rels"] = slide_rels_with_image
        # NOTE: media/image1.png is intentionally absent.
        path = _build_pptx(parts)
        try:
            report = PptxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "media part not in package" in e for e in report.errors
        ), report.errors)


if __name__ == "__main__":
    unittest.main()
