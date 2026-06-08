"""Build-at-runtime fixture decks for the pptx2md test suite.

Decks are synthesised with python-pptx into a caller-supplied temp dir (never
committed). Kept deliberately small and deterministic so assertions are stable.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Emu, Inches


def _png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (32, 32)) -> bytes:
    """Return PNG bytes of a solid-colour image (stable, tiny)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def build_minimal_deck(path: Path) -> Path:
    """A 1-slide deck: title + a 2-level bullet body. No images, no notes."""
    prs = Presentation()
    layout = prs.slide_layouts[1]  # Title and Content
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Hello Title"
    body = slide.placeholders[1].text_frame
    body.text = "First bullet"
    p = body.add_paragraph()
    p.text = "Nested bullet"
    p.level = 1
    prs.save(str(path))
    return path


def build_deck_with_duplicate_image(path: Path) -> tuple[Path, bytes]:
    """A 2-slide deck embedding the SAME image blob on both slides (dedup test)."""
    blob = _png_bytes((10, 20, 30))
    prs = Presentation()
    blank = prs.slide_layouts[6]
    for _ in range(2):
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(io.BytesIO(blob), Inches(1), Inches(1),
                                 width=Emu(914400), height=Emu(914400))
    prs.save(str(path))
    return path, blob


def build_deck_with_jpeg(path: Path) -> Path:
    """A 1-slide deck embedding a JPEG image (ext-routing test → .jpg)."""
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 100, 50)).save(buf, "JPEG")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(io.BytesIO(buf.getvalue()), Inches(1), Inches(1),
                             width=Emu(914400), height=Emu(914400))
    prs.save(str(path))
    return path


def build_deck_with_two_images(path: Path) -> Path:
    """A 1-slide deck with TWO distinct images (exercises --jobs parallel OCR)."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for color, x in ((10, 1), (200, 3)):
        slide.shapes.add_picture(io.BytesIO(_png_bytes((color, color, color))),
                                 Inches(x), Inches(1), width=Emu(914400), height=Emu(914400))
    prs.save(str(path))
    return path


def build_deck_with_picture_placeholder(path: Path) -> Path:
    """A 1-slide deck whose image lives in a PICTURE PLACEHOLDER (shape_type ==
    PLACEHOLDER, but `isinstance(shape, Picture)` is True) — Fix A regression."""
    from pptx.enum.shapes import PP_PLACEHOLDER

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[8])  # "Picture with Caption"
    for ph in slide.placeholders:
        if ph.placeholder_format.type == PP_PLACEHOLDER.PICTURE:
            ph.insert_picture(io.BytesIO(_png_bytes((1, 2, 3))))
            break
    prs.save(str(path))
    return path


def build_deck_with_background_image(path: Path) -> Path:
    """A 1-slide deck whose whole slide is a BACKGROUND image (`p:cSld/p:bg` blip,
    no shapes) — like a marp/exported deck. Fix B regression."""
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import qn

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _part, rid = slide.part.get_or_add_image_part(io.BytesIO(_png_bytes((50, 60, 70))))
    nsd = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    bg = parse_xml(
        f'<p:bg {nsd}><p:bgPr><a:blipFill><a:blip r:embed="{rid}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></a:blipFill><a:effectLst/></p:bgPr></p:bg>'
    )
    slide._element.find(qn("p:cSld")).insert(0, bg)  # p:bg must be first child of cSld
    prs.save(str(path))
    return path


def build_deck_with_notes(path: Path) -> Path:
    """A 1-slide deck whose slide carries non-empty speaker notes."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Noted slide"
    slide.notes_slide.notes_text_frame.text = "Rehearse this point."
    prs.save(str(path))
    return path


def build_deck_with_table(path: Path) -> Path:
    """A 1-slide deck with a 2x2 table (header row + one body row)."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    gf = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(1))
    tbl = gf.table
    tbl.cell(0, 0).text = "H1"
    tbl.cell(0, 1).text = "H2"
    tbl.cell(1, 0).text = "a|b"        # pipe must be escaped in GFM
    tbl.cell(1, 1).text = "line1\nline2"  # newline → <br>
    prs.save(str(path))
    return path


def build_deck_with_hidden_slide(path: Path) -> Path:
    """A 2-slide deck whose SECOND slide is hidden (p:sld @show='0')."""
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Visible"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Hidden"
    s2._element.set("show", "0")
    prs.save(str(path))
    return path
