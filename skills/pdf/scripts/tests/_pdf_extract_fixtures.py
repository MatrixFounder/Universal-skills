"""Generate the `pdf_extract.py` test fixtures.

Fourteen fixtures, all built deterministically from code (no opaque binary blobs —
this builder IS the provenance, per TASK 013 R11.3):

  digital.pdf    — 2 pages of real selectable text + one ruled 3x3 table.
  scanlike.pdf   — 1 page that is a single full-page raster image with NO text
                   layer (zero extractable characters; `page.images` non-empty).
  encrypted.pdf  — the digital PDF, encrypted with the password ``test-pw``.
  glued.pdf      — 1 page reproducing the LaTeX/academic word-gluing bug: words
                   are positioned with a sub-3pt gap and NO space glyphs, so
                   pdfplumber's absolute tolerance glues them
                   (``ASurveyonBlockchain``) while the font-relative
                   ``x_tolerance_ratio`` splits them correctly. A second line of
                   real-space text is the no-regression control.
  unmapped.pdf   — PDF-EXTRACT-UNMAPPED-FONT-TEXT-LOSS: base-14 Helvetica (not
                   embedded, WinAnsiEncoding, no /ToUnicode) asked to draw
                   Cyrillic. The producer substitutes a placeholder glyph, so
                   the dump reads as plausible text (``nnnnnn 1. nnnnn``) — the
                   nastier of the two degradation modes, and the reason the
                   detector reads font metadata rather than text shape.
  embedded.pdf   — the no-regression control for the above: the same page drawn
                   in reportlab's bundled Bitstream Vera TrueType, which is
                   embedded (FontFile2) AND carries /ToUnicode, so
                   `text_layer_lossy` must stay False.
  bullets.pdf    — PDF-EXTRACT-TOLERANCE-ARTIFACTS half A: list markers set at
                   ``BULLET_SIZE`` against ``BULLET_BODY_SIZE`` body text put
                   the marker's box top ~4 pt below the line's, over
                   pdfplumber's absolute 3 pt ``y_tolerance`` — so each marker
                   is read as its own line and sorted AFTER the line it belongs
                   to. ``--y-tolerance 5`` reunites them; a trailing paragraph
                   is the no-merge control.
  shaded.pdf     — PDF-EXTRACT-TOLERANCE-ARTIFACTS half B, both symptoms:
                   page 1 is zebra-shaded paragraphs with NO ruled table, which
                   the default ``lines`` strategy returns as a phantom table;
                   page 2 is a real ruled 3x3 table with an x-aligned shaded
                   paragraph beneath it, which ``lines`` glues on as a bogus
                   4th row. ``lines_strict`` returns 0 tables and the correct
                   3 rows respectively.
  figure.pdf     — PDF-EXTRACT-FIGURE-PAGE-UNFLAGGED, one page per measured
                   case: (1) prose, (2) a raster diagram under a running header
                   only, (3) a *vector* diagram under a running header + short
                   caption, (4) a screenshot beside plenty of live prose,
                   (5) a heavily ruled table page. Only pages 2 and 3 are
                   figure-dominant; 4 and 5 are the false-positive controls for
                   the coverage and char-count conjuncts respectively. Pages 6
                   and 7 add the page-sized background wash, without and with a
                   figure on top. It doubles as the `--extract-images` fixture:
                   one raster page, two vector-figure pages, the same raster
                   placed twice (the sha1-dedup case) and two pages that must
                   yield nothing.
  shifted.pdf    — a vector figure on a page whose MediaBox does not start at
                   (0, 0): the crop-geometry regression for pdf-13, where an
                   uncorrected transform silently frames the wrong region.
  flatfill.pdf   — a pie chart of unoutlined filled wedges: the measured COST of
                   pdf-13's stroked-path test. Neither extracted nor flagged
                   `figure_dominant`; the fixture pins that honest-scope claim
                   so it cannot quietly become false.

The fixtures live under ``tests/fixtures/`` (gitignored — the skill ignores
``*.pdf``); re-run this module (``python3 _pdf_extract_fixtures.py``) to
regenerate them in place.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import reportlab  # type: ignore
from PIL import Image, ImageDraw, ImageFont  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
from pypdf.generic import NameObject, NumberObject  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.pagesizes import letter  # type: ignore
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
from reportlab.pdfbase import pdfmetrics  # type: ignore
from reportlab.pdfbase.pdfmetrics import stringWidth  # type: ignore
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.platypus import (  # type: ignore
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ENCRYPTED_PASSWORD = "test-pw"

# The no-space-glyph title baked into glued.pdf, and the real-space control line.
# Tests assert that the default (ratio-on) extraction recovers GLUED_WORDS joined
# by single spaces, while the disabled mode reproduces the glued concatenation.
GLUED_WORDS = ["A", "Survey", "on", "Blockchain", "Interoperability"]
GLUED_CONTROL_LINE = "This line uses real spaces between words"
GLUED_FONT = "Helvetica"
GLUED_SIZE = 10
# Inter-word gap in points: below pdfplumber's absolute default (3) so legacy
# extraction glues, above the ratio threshold (0.15 * 10 = 1.5) so the default
# splits. Intra-word letters abut (gap ≈ 0) and stay together under both.
GLUED_GAP = 2.0

# The 3x3 table baked into digital.pdf page 1 — tests assert against this.
DIGITAL_TABLE = [
    ["Region", "Q1", "Q2"],
    ["North", "100", "120"],
    ["South", "90", "95"],
]

# --- unmapped.pdf / embedded.pdf --------------------------------------------
# A Latin line (survives) and a Cyrillic line (does NOT — base-14 Helvetica has
# no Cyrillic code point, so reportlab writes a placeholder glyph). Tests assert
# the Latin line comes back and the Cyrillic one does not.
UNMAPPED_LATIN_LINE = "Section 1. Overview"
UNMAPPED_CYRILLIC_LINE = "Раздел 1. Обзор системы"
# reportlab bundles the Bitstream Vera faces; embedding one is how `embedded.pdf`
# gets a font with FontFile2 + /ToUnicode without depending on a system font.
EMBEDDED_FONT_NAME = "VeraFixture"
EMBEDDED_FONT_PATH = (
    Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf")

# --- bullets.pdf ------------------------------------------------------------
# 7 pt marker against 12 pt body text puts the marker's box top ~3.97 pt below
# the line's — over pdfplumber's absolute 3 pt y_tolerance, under the 5 pt the
# fix uses. An ASCII marker keeps the assertions readable (the geometry, not the
# glyph, is what reproduces the defect).
BULLET_SIZE = 7
BULLET_BODY_SIZE = 12
BULLET_MARKER = "*"
BULLET_ITEMS = [
    "First bullet item.",
    "Second bullet item.",
    "Third bullet item.",
]
BULLET_TRAILING_LINE = "Trailing paragraph line."

# --- shaded.pdf -------------------------------------------------------------
SHADED_ZEBRA_ROWS = ["Alpha paragraph.", "Beta paragraph.", "Gamma paragraph."]
SHADED_NOTE_LINE = "Shaded note, not a table row"

# --- figure.pdf -------------------------------------------------------------
FIGURE_HEADER = "Confidential - Example Corp LLC"
FIGURE_CAPTION = "Figure 2. Component interaction overview for the platform."
# Page indices (1-based) that must come back `figure_dominant`.
FIGURE_DOMINANT_PAGES = [2, 3, 7]
# Pages 6 and 7 carry a page-sized unstroked fill behind their content — the
# background wash Google Docs Renderer (and others) paint on every page. Page 6
# is prose behind it (must stay unflagged), page 7 is a real figure behind it
# (must still be flagged).
FIGURE_BACKDROP_PAGES = [6, 7]


def build_digital_pdf(path: Path) -> None:
    """A 2-page born-digital PDF: real text + one ruled table (page 1),
    a heading + paragraph (page 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Quarterly Report", styles["Title"]),
        Paragraph(
            "This is the first paragraph of the digital PDF fixture. "
            "It contains real, selectable text that pdfplumber extracts.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]
    table = Table(DIGITAL_TABLE)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ]))
    story.append(table)
    story.append(PageBreak())
    story.append(Paragraph("Appendix", styles["Heading1"]))
    story.append(Paragraph(
        "Second page paragraph — more selectable text so page_count is 2.",
        styles["BodyText"],
    ))
    doc.build(story)


def build_scanlike_pdf(path: Path) -> None:
    """A 1-page image-only PDF: text is rendered to a raster image and embedded
    full-page, so there is NO text layer (extract_text() yields "")."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # ~US-Letter at 150 dpi.
    img = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # very old Pillow without the size kwarg
        font = ImageFont.load_default()
    lines = [
        "SCANNED DOCUMENT",
        "",
        "This page is a single raster image with no text layer.",
        "pdfplumber.extract_text() returns nothing for this page.",
        "A tool that does not detect this would emit empty output.",
    ]
    y = 150
    for line in lines:
        draw.text((120, y), line, fill="black", font=font)
        y += 90

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        img.save(png_path)
        c = canvas.Canvas(str(path), pagesize=letter)
        c.drawImage(png_path, 0, 0, width=letter[0], height=letter[1])
        c.save()
    finally:
        os.unlink(png_path)


def build_glued_pdf(path: Path) -> None:
    """A 1-page PDF reproducing the LaTeX/academic word-gluing bug.

    Each word in ``GLUED_WORDS`` is drawn at an explicit x-position with a
    ``GLUED_GAP`` (< 3 pt) positional gap and NO space glyph between words —
    exactly how LaTeX/academic exporters encode inter-word spacing. pdfplumber's
    absolute 3 pt ``x_tolerance`` therefore glues the whole line
    (``ASurveyonBlockchainInteroperability``), while the font-relative
    ``x_tolerance_ratio`` (default 0.15 → 1.5 pt threshold at 10 pt) splits the
    words back apart. A second line of ordinary real-space text is the control:
    it must extract identically in both modes (a space glyph always splits)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont(GLUED_FONT, GLUED_SIZE)
    x, y = 72, 720
    for word in GLUED_WORDS:
        c.drawString(x, y, word)
        x += stringWidth(word, GLUED_FONT, GLUED_SIZE) + GLUED_GAP
    c.setFont(GLUED_FONT, GLUED_SIZE)
    c.drawString(72, 700, GLUED_CONTROL_LINE)
    c.showPage()
    c.save()


def build_encrypted_pdf(path: Path, password: str = ENCRYPTED_PASSWORD) -> None:
    """The digital PDF, encrypted with `password`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        plain_path = tmp.name
    try:
        build_digital_pdf(Path(plain_path))
        reader = PdfReader(plain_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)
        with open(path, "wb") as fh:
            writer.write(fh)
    finally:
        os.unlink(plain_path)


def build_unmapped_pdf(path: Path) -> None:
    """A 1-page PDF whose non-Latin text was destroyed *when the file was
    written* (PDF-EXTRACT-UNMAPPED-FONT-TEXT-LOSS).

    base-14 Helvetica is not embedded and is addressed through
    `WinAnsiEncoding`, which has no Cyrillic code points, so reportlab
    substitutes a placeholder glyph for every Cyrillic character. Extraction
    then returns `nnnnnn 1. nnnnn nnnnnnn` — indistinguishable from prose by any
    statistic over the text, which is exactly why the detector reads font
    metadata instead."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(72, 700, UNMAPPED_LATIN_LINE)
    c.drawString(72, 680, UNMAPPED_CYRILLIC_LINE)
    c.showPage()
    c.save()


def build_embedded_pdf(path: Path) -> None:
    """The no-regression control for `unmapped.pdf`: the same Latin line drawn
    in reportlab's bundled Bitstream Vera TrueType, which reportlab embeds
    (FontFile2) with a /ToUnicode CMap. `text_layer_lossy` must stay False."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont(EMBEDDED_FONT_NAME, str(EMBEDDED_FONT_PATH)))
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont(EMBEDDED_FONT_NAME, 12)
    c.drawString(72, 700, UNMAPPED_LATIN_LINE)
    c.showPage()
    c.save()


def build_bullets_pdf(path: Path) -> None:
    """A 1-page PDF reproducing the orphaned-list-marker defect
    (PDF-EXTRACT-TOLERANCE-ARTIFACTS half A).

    Each marker is drawn on its item's baseline at `BULLET_SIZE` while the item
    text is `BULLET_BODY_SIZE`. The smaller font's ascent puts the marker's box
    top ~3.97 pt below the text's — past pdfplumber's absolute 3 pt
    `y_tolerance` — so the marker becomes its own line and, having the larger
    `doctop`, sorts AFTER the item it introduces. `BULLET_TRAILING_LINE` is the
    control: raising the tolerance to 5 must not merge it into anything."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 700
    for item in BULLET_ITEMS:
        c.setFont("Helvetica", BULLET_SIZE)
        c.drawString(72, y, BULLET_MARKER)
        c.setFont("Helvetica", BULLET_BODY_SIZE)
        c.drawString(90, y, item)
        y -= 30
    c.setFont("Helvetica", BULLET_BODY_SIZE)
    c.drawString(72, y - 20, BULLET_TRAILING_LINE)
    c.showPage()
    c.save()


def _draw_ruled_table(c, x0: float, y0: float, cell_w: float,
                      row_h: float, rows: list[list[str]]) -> None:
    """Draw `rows` as a genuinely *stroked* grid — real ruling lines, the kind
    `lines_strict` must keep."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    for r in range(len(rows) + 1):
        c.line(x0, y0 + r * row_h, x0 + cell_w * len(rows[0]), y0 + r * row_h)
    for col in range(len(rows[0]) + 1):
        c.line(x0 + col * cell_w, y0,
               x0 + col * cell_w, y0 + len(rows) * row_h)
    for r, row in enumerate(rows):
        for col, cell in enumerate(row):
            c.drawString(x0 + col * cell_w + 4,
                         y0 + (len(rows) - 1 - r) * row_h + 8, cell)


def build_shaded_pdf(path: Path) -> None:
    """A 2-page PDF reproducing BOTH phantom-table symptoms
    (PDF-EXTRACT-TOLERANCE-ARTIFACTS half B).

    Every shaded box is drawn `stroke=0, fill=1` — a background fill, not a
    border. The default `lines` strategy builds table edges from every rect
    regardless, so page 1 (zebra-shaded paragraphs, no table at all) comes back
    as a 3-row phantom table, and page 2's shaded paragraph — x-aligned with the
    real table above it — is glued on as a bogus 4th row, silently putting text
    into a structured table that was never in one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)

    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "Zebra-shaded paragraphs, no ruled table here.")
    y = 620
    for text in SHADED_ZEBRA_ROWS:
        c.setFillColor(colors.lightgrey)
        c.rect(72, y, 400, 40, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.drawString(80, y + 15, text)
        y += 40
    c.showPage()

    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "Real ruled table plus an x-aligned shaded note.")
    x0, y0, cell_w, row_h = 72, 640, 120, 24
    _draw_ruled_table(c, x0, y0, cell_w, row_h, DIGITAL_TABLE)
    c.setFillColor(colors.lightgrey)
    c.rect(x0, y0 - row_h, cell_w * 3, row_h, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.drawString(x0 + 4, y0 - row_h + 8, SHADED_NOTE_LINE)
    c.showPage()
    c.save()


def _draw_page_backdrop(c) -> None:
    """Paint the page-sized `stroke=0, fill=1` rectangle that several
    producers (Google Docs Renderer among them) put behind every page. It is a
    background wash, not artwork — `vector_coverage` must ignore it."""
    c.setFillColor(colors.Color(0.99, 0.99, 0.99))
    c.rect(0, 0, letter[0], letter[1], stroke=0, fill=1)
    c.setFillColor(colors.black)


def _diagram_png(path: Path) -> None:
    """A small raster diagram — boxes and connectors, no text — for the figure
    fixture's raster pages."""
    img = Image.new("RGB", (900, 700), "white")
    draw = ImageDraw.Draw(img)
    for i in range(5):
        draw.rectangle([60 + i * 150, 200, 180 + i * 150, 320],
                       outline="black", width=6)
        draw.line([180 + i * 150, 260, 210 + i * 150, 260],
                  fill="black", width=6)
    img.save(path)


def build_figure_pdf(path: Path) -> None:
    """A 7-page PDF, one page per case measured in
    PDF-EXTRACT-FIGURE-PAGE-UNFLAGGED.

    1. ordinary prose — no coverage, no flag;
    2. a raster diagram under a running header only (~35 % of the sheet, 33
       chars) — the case the old absolute-char heuristic misses because the
       header alone clears the 10-char threshold;
    3. a *vector* diagram under a header + caption (~31 % of the sheet, 90
       chars, zero images) — the case that a coverage signal counting only
       `page.images` misses entirely;
    4. a screenshot beside plenty of live prose (~14 %, ~1.6k chars) — the
       false positive the coverage threshold must reject;
    5. a heavily ruled table page (ruling clusters into ~58 % of the sheet,
       ~1.1k chars) — the false positive only the char-count conjunct rejects,
       which is why that conjunct is load-bearing rather than cosmetic;
    6. prose behind a page-sized unstroked fill — the background wash many
       producers paint on every sheet. Counting it as artwork reads a plain
       text page as 100 % artwork, so this page must measure ~0 and stay
       unflagged;
    7. the same background wash with a real vector figure on top and little
       text — excluding the wash must not cost us the figure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        _diagram_png(Path(png_path))
        c = canvas.Canvas(str(path), pagesize=letter)

        # 1 — prose
        c.setFont("Helvetica", 11)
        y = 720
        for i in range(30):
            c.drawString(72, y, f"Line {i} of ordinary body prose that fills "
                                f"this page with real text.")
            y -= 20
        c.showPage()

        # 2 — raster diagram under a running header only
        c.setFont("Helvetica", 9)
        c.drawString(72, 760, FIGURE_HEADER)
        c.drawString(540, 40, "2")
        c.drawImage(png_path, 72, 250, width=468, height=364)
        c.showPage()

        # 3 — vector diagram (paths only) + header + caption
        c.setFont("Helvetica", 10)
        c.drawString(72, 760, FIGURE_HEADER)
        c.drawString(72, 250, FIGURE_CAPTION)
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        cols, rows, box_w, box_h, gap_x, gap_y = 4, 3, 95, 70, 30, 55
        for j in range(rows):
            for i in range(cols):
                x = 80 + i * (box_w + gap_x)
                y = 300 + j * (box_h + gap_y)
                c.rect(x, y, box_w, box_h, stroke=1, fill=0)
                if i < cols - 1:      # connectors keep the diagram one cluster
                    c.line(x + box_w, y + box_h / 2,
                           x + box_w + gap_x, y + box_h / 2)
                if j < rows - 1:
                    c.line(x + box_w / 2, y + box_h,
                           x + box_w / 2, y + box_h + gap_y)
        c.showPage()

        # 4 — screenshot beside plenty of live prose
        c.setFont("Helvetica", 10)
        y = 740
        for i in range(22):
            c.drawString(72, y, f"Paragraph line {i} describing the screenshot "
                                f"in real narrative prose here.")
            y -= 16
        c.drawImage(png_path, 72, 120, width=300, height=233)
        c.showPage()

        # 5 — heavily ruled table page
        c.setFont("Helvetica", 9)
        x0, y0, cell_w, row_h, n_rows, n_cols = 60, 120, 82, 26, 22, 6
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.7)
        for r in range(n_rows + 1):
            c.line(x0, y0 + r * row_h, x0 + cell_w * n_cols, y0 + r * row_h)
        for col in range(n_cols + 1):
            c.line(x0 + col * cell_w, y0,
                   x0 + col * cell_w, y0 + n_rows * row_h)
        for r in range(n_rows):
            for col in range(n_cols):
                c.drawString(x0 + col * cell_w + 3, y0 + r * row_h + 9,
                             f"cell{r}-{col}")
        c.showPage()

        # 6 — prose sitting on a page-sized unstroked background fill
        _draw_page_backdrop(c)
        c.setFont("Helvetica", 11)
        y = 720
        for i in range(30):
            c.drawString(72, y, f"Line {i} of prose on a page that carries a "
                                f"full-sheet background wash.")
            y -= 20
        c.showPage()

        # 7 — the same wash, but a real vector figure on top of it
        _draw_page_backdrop(c)
        c.setFont("Helvetica", 10)
        c.drawString(72, 760, FIGURE_HEADER)
        c.drawString(72, 250, FIGURE_CAPTION)
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        for j in range(rows):
            for i in range(cols):
                x = 80 + i * (box_w + gap_x)
                y = 300 + j * (box_h + gap_y)
                c.rect(x, y, box_w, box_h, stroke=1, fill=0)
                if i < cols - 1:
                    c.line(x + box_w, y + box_h / 2,
                           x + box_w + gap_x, y + box_h / 2)
                if j < rows - 1:
                    c.line(x + box_w / 2, y + box_h,
                           x + box_w / 2, y + box_h + gap_y)
        c.showPage()
        c.save()
    finally:
        os.unlink(png_path)


# Declared side length for hugedecl.pdf: 40000x40000 = 1.6 G pixels, far
# past any real image and past `_IMAGE_MAX_PIXELS`.
HUGE_DECL_SIDE = 40000

SHIFTED_MEDIABOX = (20, -30, 632, 762)
# A CropBox deliberately DIFFERENT from the MediaBox. Poppler renders the
# MediaBox by default (`pdftocairo` needs `-cropbox` to do otherwise) and
# pdfplumber measures against it too, so the correct crop transform reads the
# MediaBox — reaching for the CropBox is the intuitive wrong choice, and
# without this divergence the two are indistinguishable.
SHIFTED_CROPBOX = (70, 20, 582, 692)


def build_shifted_pdf(path: Path) -> None:
    """A 1-page vector figure on a page whose MediaBox does NOT start at (0, 0).

    The regression fixture for the crop geometry (pdf-13). pdfplumber reports a
    path's `x` in absolute PDF space and its `y` relative to the page, while
    Poppler renders the MediaBox with its origin at the image's top-left, so the
    two frames drift apart by exactly the MediaBox origin. On the usual `(0, 0)`
    page the correction is the identity, which is why an uncorrected crop passes
    every other fixture and silently frames the wrong region here: measured on
    this box, a path pdfplumber puts at `(100, 142)` renders at `(78.7, 170.4)`.

    The page also carries a CropBox that differs from the MediaBox, so the
    fixture separates the two: Poppler renders the MediaBox unless asked
    otherwise, so a transform that reads `page.cropbox` — the intuitive choice
    for "the visible page" — mis-crops here and nowhere else.

    The figure is drawn well inside the shifted box so the crop has room, and it
    is the same stroked box-and-connector diagram as `figure.pdf` page 3 so the
    only variable between the two is the page geometry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        raw_path = tmp.name
    try:
        c = canvas.Canvas(raw_path, pagesize=letter)
        c.setFont("Helvetica", 10)
        c.drawString(100, 700, FIGURE_HEADER)
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        for i in range(3):
            x = 120 + i * 140
            c.rect(x, 380, 110, 80, stroke=1, fill=0)
            if i < 2:
                c.line(x + 110, 420, x + 140, 420)
        c.showPage()
        c.save()

        reader = PdfReader(raw_path)
        writer = PdfWriter()
        page = reader.pages[0]
        page.mediabox.lower_left = SHIFTED_MEDIABOX[:2]
        page.mediabox.upper_right = SHIFTED_MEDIABOX[2:]
        page.cropbox.lower_left = SHIFTED_CROPBOX[:2]
        page.cropbox.upper_right = SHIFTED_CROPBOX[2:]
        writer.add_page(page)
        with open(path, "wb") as fh:
            writer.write(fh)
    finally:
        os.unlink(raw_path)


def build_flatfill_pdf(path: Path) -> None:
    """A flat-fill pie chart: the measured cost of the stroked-path test.

    Four filled wedges with NO outline — matplotlib's and Excel's default pie —
    on an otherwise sparse page. `_is_figure_cluster` rejects it (0 stroked
    members) and it is too small a share of the sheet for `figure_dominant`
    (measured `vector_coverage` 0.0749 against the 0.25 threshold), so the
    figure appears nowhere in the dump. This fixture pins that honest-scope
    claim: if a future change starts extracting it, or starts flagging its
    page, the docstring and the reference are out of date and the test says so.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 11)
    c.drawString(72, 730, "Market share by segment")
    palette = [colors.Color(0.20, 0.45, 0.75), colors.Color(0.85, 0.35, 0.20),
               colors.Color(0.25, 0.60, 0.30), colors.Color(0.60, 0.45, 0.75)]
    start = 0
    for index, extent in enumerate((120, 95, 80, 65)):
        c.setFillColor(palette[index])
        wedge = c.beginPath()
        wedge.moveTo(300, 500)
        wedge.arcTo(200, 400, 400, 600, start, extent)
        wedge.close()
        c.drawPath(wedge, stroke=0, fill=1)
        start += extent
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(72, 360, "Figure 1. Share of revenue by segment, FY24.")
    c.showPage()
    c.save()


def build_shadowed_pdf(path: Path) -> None:
    """An image XObject carrying `/W` and `/H` ALONGSIDE `/Width`/`/Height`.

    The parser-differential fixture. pdfminer resolves the size through
    ``get_any(("W", "Width"))`` — first key present wins — while pypdf reads
    ``/Width`` only, so a 14-byte edit makes pdfplumber report 1x1 for an image
    pypdf decodes at full size. Anything that sizes the decode guard from
    pdfplumber's ``srcsize`` is therefore reading a number the attacker chose
    independently of the allocation. Measured on this file: srcsize (1, 1),
    real 400x300."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        Image.new("RGB", (400, 300), (120, 40, 160)).save(png_path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            raw_path = tmp.name
        try:
            c = canvas.Canvas(raw_path, pagesize=letter)
            c.drawImage(png_path, 60, 500, width=200, height=150)
            c.showPage()
            c.save()
            reader = PdfReader(raw_path)
            writer = PdfWriter()
            page = reader.pages[0]
            xobjects = page["/Resources"]["/XObject"]
            for key in list(xobjects.keys()):
                entry = xobjects[key].get_object()
                if entry.get("/Subtype") == "/Image":
                    entry[NameObject("/W")] = NumberObject(1)
                    entry[NameObject("/H")] = NumberObject(1)
            writer.add_page(page)
            with open(path, "wb") as fh:
                writer.write(fh)
        finally:
            os.unlink(raw_path)
    finally:
        os.unlink(png_path)


def build_nested_pdf(path: Path) -> None:
    """A raster that lives inside a Form XObject rather than at page level.

    The enumeration must walk into forms. A hand-rolled scan of
    ``/Resources/XObject`` sees only the form (``/Subtype /Form``) and loses the
    image entirely — verified — which is why enumeration goes through pypdf's
    own recursive key list."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        Image.new("RGB", (300, 200), (30, 160, 90)).save(png_path)
        c = canvas.Canvas(str(path), pagesize=letter)
        c.beginForm("innerform")
        c.drawImage(png_path, 0, 0, width=200, height=133)
        c.endForm()
        c.saveState()
        c.translate(80, 500)
        c.doForm("innerform")
        c.restoreState()
        c.showPage()
        c.save()
    finally:
        os.unlink(png_path)


def build_hugedecl_pdf(path: Path) -> None:
    """An image declaring an absurd `/Width` x `/Height` over a tiny stream.

    The decode allocation is driven by the declaration, so this is the file
    that separates "the guard runs before the decode" from "the guard runs
    after and merely declines to write the result"."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        Image.new("RGB", (40, 30), (200, 80, 20)).save(png_path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            raw_path = tmp.name
        try:
            c = canvas.Canvas(raw_path, pagesize=letter)
            c.drawImage(png_path, 60, 500, width=200, height=150)
            c.showPage()
            c.save()
            reader = PdfReader(raw_path)
            writer = PdfWriter()
            page = reader.pages[0]
            xobjects = page["/Resources"]["/XObject"]
            for key in list(xobjects.keys()):
                entry = xobjects[key].get_object()
                if entry.get("/Subtype") == "/Image":
                    entry[NameObject("/Width")] = NumberObject(HUGE_DECL_SIDE)
                    entry[NameObject("/Height")] = NumberObject(HUGE_DECL_SIDE)
            writer.add_page(page)
            with open(path, "wb") as fh:
                writer.write(fh)
        finally:
            os.unlink(raw_path)
    finally:
        os.unlink(png_path)


def build_all(fixtures_dir: Path) -> dict[str, Path]:
    """Build every fixture into `fixtures_dir`; return the path map."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "digital": fixtures_dir / "digital.pdf",
        "scanlike": fixtures_dir / "scanlike.pdf",
        "encrypted": fixtures_dir / "encrypted.pdf",
        "glued": fixtures_dir / "glued.pdf",
        "unmapped": fixtures_dir / "unmapped.pdf",
        "embedded": fixtures_dir / "embedded.pdf",
        "bullets": fixtures_dir / "bullets.pdf",
        "shaded": fixtures_dir / "shaded.pdf",
        "figure": fixtures_dir / "figure.pdf",
        "shifted": fixtures_dir / "shifted.pdf",
        "flatfill": fixtures_dir / "flatfill.pdf",
        "shadowed": fixtures_dir / "shadowed.pdf",
        "nested": fixtures_dir / "nested.pdf",
        "hugedecl": fixtures_dir / "hugedecl.pdf",
    }
    build_digital_pdf(paths["digital"])
    build_scanlike_pdf(paths["scanlike"])
    build_encrypted_pdf(paths["encrypted"])
    build_glued_pdf(paths["glued"])
    build_unmapped_pdf(paths["unmapped"])
    build_embedded_pdf(paths["embedded"])
    build_bullets_pdf(paths["bullets"])
    build_shaded_pdf(paths["shaded"])
    build_figure_pdf(paths["figure"])
    build_shifted_pdf(paths["shifted"])
    build_flatfill_pdf(paths["flatfill"])
    build_shadowed_pdf(paths["shadowed"])
    build_nested_pdf(paths["nested"])
    build_hugedecl_pdf(paths["hugedecl"])
    return paths


if __name__ == "__main__":
    out = build_all(Path(__file__).resolve().parent / "fixtures")
    for name, p in out.items():
        print(f"{name}: {p}")
