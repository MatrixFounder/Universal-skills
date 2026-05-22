"""Generate the `pdf_extract.py` test fixtures.

Three fixtures, all built deterministically from code (no opaque binary blobs —
this builder IS the provenance, per TASK 013 R11.3):

  digital.pdf    — 2 pages of real selectable text + one ruled 3x3 table.
  scanlike.pdf   — 1 page that is a single full-page raster image with NO text
                   layer (zero extractable characters; `page.images` non-empty).
  encrypted.pdf  — the digital PDF, encrypted with the password ``test-pw``.

The fixtures are committed under ``tests/fixtures/`` for test speed; re-run this
module (``python3 _pdf_extract_fixtures.py``) to regenerate them in place.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.pagesizes import letter  # type: ignore
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
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

# The 3x3 table baked into digital.pdf page 1 — tests assert against this.
DIGITAL_TABLE = [
    ["Region", "Q1", "Q2"],
    ["North", "100", "120"],
    ["South", "90", "95"],
]


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


def build_all(fixtures_dir: Path) -> dict[str, Path]:
    """Build all three fixtures into `fixtures_dir`; return the path map."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "digital": fixtures_dir / "digital.pdf",
        "scanlike": fixtures_dir / "scanlike.pdf",
        "encrypted": fixtures_dir / "encrypted.pdf",
    }
    build_digital_pdf(paths["digital"])
    build_scanlike_pdf(paths["scanlike"])
    build_encrypted_pdf(paths["encrypted"])
    return paths


if __name__ == "__main__":
    out = build_all(Path(__file__).resolve().parent / "fixtures")
    for name, p in out.items():
        print(f"{name}: {p}")
