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
  split.pdf      — a table row cut in half by a page break, plus the two shapes
                   that look identical and must NOT be counted (a crosstab's
                   blank corner cell, and a table whose first column is blank
                   by design).
  columns.pdf    — a two-column page whose columns share baselines (so
                   extraction interleaves them) and a one-column control.
  glyphs.pdf     — an emoji-sized raster inline on a text line, with two
                   same-sized controls that are pictures rather than glyphs.
  blankraster.pdf— a page whose only raster decodes to a single flat colour
                   (the "blank page that says: run OCR" case), plus a control.
  ruling.pdf     — table ruling that clusters into a page-wide "figure"
                   enclosing the whole body text.
  links.pdf      — `/URI` link annotations over text and over an image, plus a
                   page with none.

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


def build_orphanfar_pdf(path: Path) -> None:
    """Bare markers that `--y-tolerance` cannot rescue — the arXiv shape.

    Dogfooding an arXiv HTML-to-PDF export found bullets sitting alone not
    because of the 3 pt line grouping but because the exporter interposes a
    "Report issue for preceding element" line BETWEEN the marker and its item.
    No line-grouping tolerance merges across that, so the hint's advice is
    wrong there — and this fixture is what makes the hint say so instead of
    naming a flag that does nothing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    # Page 1 carries no markers at all, so the probe has to *find* page 2
    # rather than read the first pages it is handed — a mutation that dropped
    # the "affected pages only" filter survived until this page existed.
    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "Ordinary prose, no list and no markers on this page.")
    c.drawString(72, 720, "It exists so the affected page is not page 1.")
    c.showPage()

    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "List whose markers are cut off from their items.")
    y = 700
    for item in ("Quantitative analysis of related work.",
                 "Analysis of governance mechanisms.",
                 "Proposals to improve deliberation."):
        # `*`, not `\u2022`: the core Helvetica of a reportlab fixture has no
        # bullet glyph, and the extractor would see `(cid:127)` — a fixture
        # artefact that would quietly stop this fixture reproducing anything.
        c.drawString(72, y, "*")
        c.drawString(72, y - 16, "Report issue for preceding element")
        c.drawString(72, y - 32, item)
        y -= 60
    c.showPage()
    c.save()


OCRLIKE_LINES = [
    "Recognised text sitting on top of the page image, the way ocrmypdf",
    "writes it: the raster is still page-sized, so no artwork can be",
    "extracted from this page, and the run has to say so out loud.",
]

ONECOL_TABLE = [["Показатель"], ["Доступность"], ["RTO"], ["RPO"]]


def build_ocrlike_pdf(path: Path) -> None:
    """A page-sized raster WITH a text layer over it — the shape of a scan that
    has already been through `pdf_ocr.py`.

    `scanlike.pdf` cannot cover this: it has no text, so it exits 10 and the
    image warnings are deliberately suppressed on that path. After OCR the same
    document exits 0, and then `--extract-images` writes nothing (its only
    raster is a page-sized background) while the directory it created stays
    empty. Six documents in one dogfood run landed exactly here, and the run
    said nothing at all — which is what this fixture now keeps from coming
    back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    png = path.parent / "_ocrlike_page.png"
    Image.new("RGB", (850, 1100), "white").save(png)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawImage(str(png), 0, 0, width=letter[0], height=letter[1])
    c.setFont("Helvetica", 11)
    for i, line in enumerate(OCRLIKE_LINES):
        c.drawString(72, 700 - i * 16, line)
    c.showPage()
    c.save()
    png.unlink(missing_ok=True)


def build_onecol_pdf(path: Path) -> None:
    """A genuinely *ruled* one-column table — the false positive the
    `single_column_tables` hint cannot avoid.

    Shading read as a table and a real single-column table are indistinguishable
    once extraction is done: both arrive as rows of one cell. This fixture is
    the honest half of that pair — the hint fires here and is WRONG, and the
    tests say so out loud rather than pretending the signal is precise. It is
    also the only fixture where the count survives `--table-strategy
    lines_strict` (the ruling is stroked, so strict keeps it), which is what
    makes it the test for the hint's strategy gate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "A real one-column table, drawn with stroked rules.")
    _draw_ruled_table(c, 72, 620, 160, 24, ONECOL_TABLE)
    c.showPage()
    c.save()


SPLIT_HEADER_ROW = ["Step", "Task Description"]
# The label the page break strands: the producer draws the row's first cell at
# the bottom of page 1 and its text on page 2, so `2.11` reaches the dump as a
# line of flat `text` and the continuation row arrives with an empty first cell.
SPLIT_DANGLING_LABEL = "2.11"
SPLIT_CONTINUATION = "Communicate RFC Approval to the requester"
# Page 4's crosstab corner: the shape the counter must NOT read as a split,
# because page 3 ends no table for it to continue.
SPLIT_CROSSTAB = [["", "Q1", "Q2"], ["North", "100", "120"]]
# Pages 5-6: a table whose first column is blank in nearly every row (a merged
# category column). Blank-first is this table's own shape, not a page break.
SPLIT_CATEGORY_ROWS = [["Group", "Metric", "Value"],
                       ["", "Latency", "120 ms"],
                       ["", "Throughput", "900 rps"]]
SPLIT_CATEGORY_TAIL = [["", "Availability", "99.9 %"],
                       ["", "Error rate", "0.1 %"]]


def build_split_pdf(path: Path) -> None:
    """A table row cut in half by a page break — and the two shapes that look
    like one but are not (PDF-EXTRACT-DOGFOOD-CYCLE2-RESIDUALS residual 1).

    Measured on four dogfood documents in two forms: the row's label stays
    behind in the previous page's flat ``text`` while its content opens the
    next page's table with an EMPTY first cell (``change-management`` pages
    26-27, three times), or the whole row disappears from ``tables`` and only
    the orphaned tail arrives (``test-1`` pages 14-15, where question ОВ-9 is
    in no structured table at all). Nothing in the dump said so, and an agent
    composing Markdown from ``tables`` silently dropped the row.

    Six pages, three behaviours:

    * 1-2 — the split itself: page 1's table ends with rows carrying labels,
      the stranded label is the last line of its text, and page 2 repeats the
      header and opens with ``["", …]``. This must be counted and named.
    * 3-4 — a crosstab whose header row starts with a blank corner cell
      (``["", "Q1", "Q2"]``), following a page with NO table. The same row
      shape, no page break behind it: it must stay uncounted, which is what
      makes the "previous page ends a table" conjunct load-bearing.
    * 5-6 — a table whose first column is blank in most rows (a merged
      category column) continuing across the break. Blank-first is this
      table's own shape, so the continuation must stay uncounted too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)

    # 1 — the table whose last row the break cuts in half.
    c.setFont("Helvetica", 10)
    c.drawString(72, 750, "Change process steps, continued overleaf.")
    _draw_ruled_table(c, 72, 600, 200, 24, [
        SPLIT_HEADER_ROW,
        ["2.9", "Return RFC to the requester"],
        ["2.10", "Was the RFC retrospective?"],
    ])
    # The stranded label: drawn in the label column's x position, BELOW the
    # table's bottom rule, so it reaches the dump as flat text and not as a
    # table cell — exactly what the measured producer emits.
    c.drawString(76, 575, SPLIT_DANGLING_LABEL)
    c.drawString(270, 60, "1 / 6")
    c.showPage()

    # 2 — the continuation: repeated header, then the label-less row.
    c.setFont("Helvetica", 10)
    _draw_ruled_table(c, 72, 620, 200, 24, [
        SPLIT_HEADER_ROW,
        ["", SPLIT_CONTINUATION],
        ["2.12", "Close the request"],
    ])
    c.drawString(270, 60, "2 / 6")
    c.showPage()

    # 3 — prose, no table: nothing for page 4's corner cell to continue.
    c.setFont("Helvetica", 11)
    y = 720
    for i in range(20):
        c.drawString(72, y, f"Line {i} of ordinary prose with no table on it.")
        y -= 20
    c.showPage()

    # 4 — a crosstab with a blank corner header cell (the false positive).
    c.setFont("Helvetica", 10)
    c.drawString(72, 750, "Quarterly figures by region.")
    _draw_ruled_table(c, 72, 620, 120, 24, SPLIT_CROSSTAB)
    c.showPage()

    # 5 — a table whose first column is blank in most rows.
    c.setFont("Helvetica", 10)
    c.drawString(72, 750, "Service levels, part one.")
    _draw_ruled_table(c, 72, 620, 140, 24, SPLIT_CATEGORY_ROWS)
    c.showPage()

    # 6 — its continuation: blank-first again, but that is the table's shape.
    c.setFont("Helvetica", 10)
    _draw_ruled_table(c, 72, 640, 140, 24, SPLIT_CATEGORY_TAIL)
    c.showPage()
    c.save()


# --- columns.pdf ------------------------------------------------------------
# Two columns of body text with a gutter wide enough to see and narrow enough
# to be realistic. Measured on a real OCR'd bilingual contract: the gutter was
# 6-7 pt, and every recognised text line spanned BOTH columns, so pdfplumber
# read the two columns as one interleaved line each.
COLUMNS_GUTTER_X = 306.0
COLUMNS_LEFT = "Left column line {i} of the Russian half of the page."
COLUMNS_RIGHT = "Right column line {i} of the English half here."
COLUMNS_ROWS = 30
# Page 3's ruled table: enough rows that its column gap is a full-height band.
COLUMNS_TABLE_ROWS = 20


def build_columns_pdf(path: Path) -> None:
    """A two-column page whose columns share baselines, and a one-column
    control (residual 6).

    pdfplumber groups characters into lines by their Y position, so two columns
    printed at the same baselines come back interleaved — left-column words and
    right-column words alternating inside one line — and nothing in the dump
    says so. ``--layout``, which §3.1 of the reference names as the remedy,
    preserves the visual arrangement but does NOT separate the columns; the
    measured repair is cropping the page at the gutter, which is why the hint
    reports the gutter's x coordinate rather than a flag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 9)
    y = 740
    for i in range(COLUMNS_ROWS):
        c.drawString(72, y, COLUMNS_LEFT.format(i=i))
        c.drawString(COLUMNS_GUTTER_X + 8, y, COLUMNS_RIGHT.format(i=i))
        y -= 20
    c.showPage()

    # The control: the same amount of text, one column, no gutter.
    c.setFont("Helvetica", 9)
    y = 740
    for i in range(COLUMNS_ROWS):
        c.drawString(72, y, f"Single-column body line {i} running the full "
                            f"width of the text block without any gutter.")
        y -= 20
    c.showPage()

    # Page 3 — a two-column ruled TABLE. Its inter-column gap is a full-height
    # gutter by exactly the definition `_page_gutters` uses, which is why a
    # page carrying a table is not examined at all: telling the caller to crop
    # a table into columns would be worse than saying nothing. Without this
    # page the "pages with tables are skipped" guard could be deleted and every
    # test would still pass — measured: that mutant survived until this page
    # existed.
    c.setFont("Helvetica", 9)
    _draw_ruled_table(
        c, 72, 740 - COLUMNS_TABLE_ROWS * 24, 200, 24,
        [[f"left cell {i}", f"right cell {i}"]
         for i in range(COLUMNS_TABLE_ROWS)])
    c.showPage()
    c.save()


# --- glyphs.pdf -------------------------------------------------------------
# An emoji drawn by a colour font is a raster XObject, so a naive extractor
# writes one PNG per ⚠ / ✅ in the text. Measured: 10 of 15 files on `test-1`,
# every one of them 10x10 or 11x11 pt, square, sitting on a text line whose
# median font size equals the image's height.
GLYPH_BODY_SIZE = 11
GLYPH_LINE = "Status ready for review"
GLYPH_STANDALONE_SIDE = 11    # points — the SAME size as the inline glyph


def _icon_png(path: Path, colour: str = "red") -> None:
    """A small square raster — the emoji-glyph shape (and, placed away from
    text, the meaningful-icon control)."""
    img = Image.new("RGB", (160, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, 140, 140], fill=colour, outline="black", width=8)
    img.save(path)


def build_glyphs_pdf(path: Path) -> None:
    """An inline emoji-sized raster on a text line, and two same-sized controls
    that are NOT glyphs (residual 3).

    The rule under test is "a glyph", not "a small image": the filter may only
    reject a raster that is square, as tall as the text it sits in, and
    adjacent to characters on that line. Page 2 places an image of exactly the
    same size where no text shares its band, and page 1 also carries a
    larger version of the same artwork inline — both must survive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # Three DIFFERENT images on purpose: identical bytes would collapse
        # into one file under the sha1 dedup and the test could no longer see
        # which of the three the filter kept.
        glyph = Path(tmp) / "glyph.png"
        big = Path(tmp) / "big.png"
        alone = Path(tmp) / "alone.png"
        _icon_png(glyph, colour="red")
        _icon_png(big, colour="green")
        _icon_png(alone, colour="blue")
        c = canvas.Canvas(str(path), pagesize=letter)

        # 1 — the glyph: 11x11 pt, inline, on an 11 pt text line.
        c.setFont("Helvetica", GLYPH_BODY_SIZE)
        c.drawString(72, 700, GLYPH_LINE)
        text_w = stringWidth(GLYPH_LINE, "Helvetica", GLYPH_BODY_SIZE)
        c.drawImage(str(glyph), 72 + text_w + 3, 698,
                    width=GLYPH_BODY_SIZE, height=GLYPH_BODY_SIZE)
        # …and the control that keeps the test honest: the same artwork four
        # times the line height, still beside text. Big enough to be a
        # picture, so the height test must keep it.
        c.drawImage(str(big), 72, 560, width=48, height=48)
        c.setFont("Helvetica", GLYPH_BODY_SIZE)
        c.drawString(130, 580, "Prose beside the larger picture.")
        c.showPage()

        # 2 — an 11x11 pt image with no text on its line at all.
        c.setFont("Helvetica", GLYPH_BODY_SIZE)
        c.drawString(72, 740, "The icon below shares its line with nothing.")
        c.drawImage(str(alone), 300, 500,
                    width=GLYPH_STANDALONE_SIDE, height=GLYPH_STANDALONE_SIDE)
        c.showPage()
        c.save()


# --- blankraster.pdf --------------------------------------------------------
# Measured on `change-management` page 9: `scanned: true`, image_coverage 0.63,
# and the extracted 816x1056 PNG held nothing but white. The page is blank; the
# scan signal sent the reader to OCR something that is not there.
BLANK_RASTER_SIZE = (816, 1056)


def build_blankraster_pdf(path: Path) -> None:
    """A page whose only artwork is a uniform white raster, and a control page
    whose raster carries content (residual 5).

    The blank raster is deliberately NOT page-sized (0.63 of the sheet, as
    measured), so the backdrop rule does not catch it and the naive extractor
    writes a file with nothing in it while `scanned` tells the caller to run
    OCR."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        blank = Path(tmp) / "blank.png"
        real = Path(tmp) / "real.png"
        Image.new("RGB", BLANK_RASTER_SIZE, "white").save(blank)
        _diagram_png(real)
        c = canvas.Canvas(str(path), pagesize=letter)

        # 1 — the blank raster, no text: a page with nothing on it.
        c.drawImage(str(blank), 72, 150, width=468, height=500)
        c.showPage()

        # 2 — the control: a raster with content, same extraction path.
        c.setFont("Helvetica", 11)
        c.drawString(72, 740, "This page's image is not blank.")
        c.drawImage(str(real), 72, 250, width=468, height=364)
        c.showPage()

        # 3 — a blank raster on a page of live prose. The raster carries
        # nothing and is dropped, but the PAGE is perfectly readable: this is
        # what keeps "the artwork is blank" from being reported as "the page
        # is blank".
        c.setFont("Helvetica", 11)
        y = 740
        for i in range(20):
            c.drawString(72, y, f"Line {i} of prose beside a white "
                                f"placeholder image.")
            y -= 20
        c.drawImage(str(blank), 72, 120, width=300, height=200)
        c.showPage()
        c.save()


# --- ruling.pdf -------------------------------------------------------------
RULING_ROWS = 20
RULING_COLS = 4
# How far the unresolvable ruling runs past the grid. The containment test
# rejects a cluster that is >= 90 % inside a detected table, so the tail has to
# be more than a ninth of the cluster's height for the defect to reproduce —
# 600 pt of grid needs > 67 pt of tail; the measured page's gap was 78.
RULING_TAIL_PT = 90


def build_ruling_pdf(path: Path) -> None:
    """Table ruling that clusters into a page-wide "figure" (residual 4).

    Measured on `test-1` pages 10 and 14 and `elma365-3cx-target` pages 8 and
    12: a 345-385 KB PNG that turns out to be a crop of the whole text area,
    whose only vector graphics is the table's ruling. `_is_figure_cluster`
    rejects a cluster that lies inside a detected table, but here the header
    and footer rules merge with the grid into one box BIGGER than the table, so
    the containment test misses it and the page's entire body text is written
    out as a picture.

    The distinguishing measurement is what the cluster encloses: 1656-1974
    characters against 0-36 for every genuine vector figure in the corpus.

    Reproducing it needs the cluster to be *bigger* than the table: on the
    measured page `find_tables()` stopped at y=702 while the ruling ran on to
    y=780, which put the containment ratio at 0.89 — a hair under the 0.9 the
    rejection needs. Here the same gap comes from an unfinished last row: two
    verticals continue below the grid with no closing rule, so pdfplumber
    cannot make a row of them and the table box ends above them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.7)
    x0, y0, cell_w, row_h = 60, 150, 123, 30
    grid_w = cell_w * RULING_COLS
    c.setFont("Helvetica", 8)
    for r in range(RULING_ROWS + 1):
        c.line(x0, y0 + r * row_h, x0 + grid_w, y0 + r * row_h)
    for col in range(RULING_COLS + 1):
        c.line(x0 + col * cell_w, y0, x0 + col * cell_w, y0 + RULING_ROWS * row_h)
    for r in range(RULING_ROWS):
        for col in range(RULING_COLS):
            c.drawString(x0 + col * cell_w + 3, y0 + r * row_h + 11,
                         f"row {r} column {col} body text")
    # The unfinished row: ruling that continues past what `find_tables` can
    # resolve into a table, so the cluster outgrows the table box.
    c.line(x0, y0, x0, y0 - RULING_TAIL_PT)
    c.line(x0 + grid_w, y0, x0 + grid_w, y0 - RULING_TAIL_PT)
    c.showPage()
    c.save()


# --- links.pdf --------------------------------------------------------------
LINK_TARGETS = [
    ("https://example.com/first", "the first anchor"),
    ("https://example.com/second", "second anchor here"),
]
# A link laid over the image rather than over text: its anchor text is None,
# which is information (match it to the image placement), not a failure.
LINK_IMAGE_URI = "https://example.com/picture"
# The internal `/GoTo` link: a real annotation that must stay OUT of `links`.
LINK_INTERNAL_DEST = "inner-destination"
LINK_INTERNAL_ANCHOR = "jump inside this document"


def build_links_pdf(path: Path) -> None:
    """Link annotations with anchor text, and one over an image (residual 2).

    The dump had no `links` key at all: 578 `/URI` annotations across the
    20-document dogfood corpus reached the caller as nothing, and for a
    web-page-printed-to-PDF — which this repository's own `html2pdf.py`
    produces — losing every URL is losing content, not formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        _icon_png(Path(png_path), colour="blue")
        c = canvas.Canvas(str(path), pagesize=letter)
        c.setFont("Helvetica", 11)
        y = 720
        for uri, anchor in LINK_TARGETS:
            c.drawString(72, y, anchor)
            width = stringWidth(anchor, "Helvetica", 11)
            c.linkURL(uri, (72, y - 2, 72 + width, y + 11), relative=0)
            y -= 40
        c.drawString(72, y, "The picture below is itself a link.")
        c.drawImage(png_path, 72, y - 120, width=100, height=100)
        c.linkURL(LINK_IMAGE_URI, (72, y - 120, 172, y - 20), relative=0)
        # An INTERNAL link, so the documented omission can be pinned: the dump
        # reports `/URI` annotations and not `/GoTo` destinations, and this is
        # the annotation that must NOT appear in `links`.
        c.bookmarkPage(LINK_INTERNAL_DEST)
        c.drawString(72, y - 150, LINK_INTERNAL_ANCHOR)
        c.linkAbsolute(LINK_INTERNAL_ANCHOR, LINK_INTERNAL_DEST,
                       (72, y - 152, 260, y - 139))
        c.showPage()

        # A second page with no annotations at all: `links` must be an empty
        # list there, which is a different statement from "did not look".
        c.setFont("Helvetica", 11)
        c.drawString(72, 740, "No links on this page.")
        c.showPage()
        c.save()
    finally:
        os.unlink(png_path)


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
        # Drawn content, not a flat fill: a single-colour raster is rejected
        # as blank (residual 5), and this fixture is about the size
        # declaration, not about what the pixels hold.
        shadowed = Image.new("RGB", (400, 300), (120, 40, 160))
        ImageDraw.Draw(shadowed).ellipse([60, 60, 340, 240],
                                         outline="white", width=12)
        shadowed.save(png_path)
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
    own recursive key list.

    The raster carries a drawn shape rather than a flat fill. That is not
    decoration: a single-colour raster is rejected as blank (residual 5), and a
    fixture whose nesting test depends on a colour swatch would be measuring
    the blank rule instead of the nesting it exists for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        nested = Image.new("RGB", (300, 200), (30, 160, 90))
        ImageDraw.Draw(nested).rectangle([40, 40, 260, 160],
                                         outline="white", width=10)
        nested.save(png_path)
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
        "onecol": fixtures_dir / "onecol.pdf",
        "orphanfar": fixtures_dir / "orphanfar.pdf",
        "ocrlike": fixtures_dir / "ocrlike.pdf",
        "split": fixtures_dir / "split.pdf",
        "columns": fixtures_dir / "columns.pdf",
        "glyphs": fixtures_dir / "glyphs.pdf",
        "blankraster": fixtures_dir / "blankraster.pdf",
        "ruling": fixtures_dir / "ruling.pdf",
        "links": fixtures_dir / "links.pdf",
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
    build_onecol_pdf(paths["onecol"])
    build_orphanfar_pdf(paths["orphanfar"])
    build_ocrlike_pdf(paths["ocrlike"])
    build_split_pdf(paths["split"])
    build_columns_pdf(paths["columns"])
    build_glyphs_pdf(paths["glyphs"])
    build_blankraster_pdf(paths["blankraster"])
    build_ruling_pdf(paths["ruling"])
    build_links_pdf(paths["links"])
    return paths


if __name__ == "__main__":
    out = build_all(Path(__file__).resolve().parent / "fixtures")
    for name, p in out.items():
        print(f"{name}: {p}")
