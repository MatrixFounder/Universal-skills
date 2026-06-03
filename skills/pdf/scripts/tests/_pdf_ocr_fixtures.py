"""Generate the `pdf_ocr.py` test fixtures (TASK 018 / pdf-4).

Two fixtures, both built deterministically from code (no opaque binary blobs —
this builder IS the provenance; the pdf skill `.gitignore` ignores `*.pdf`, so
these are build-at-runtime artifacts, never committed):

  scan.pdf     — 1 page that is a single full-page raster image with NO text
                 layer (zero extractable characters; `page.images` non-empty).
                 The rendered text carries the OCR needle (`OCR_NEEDLE_ASCII`
                 + `OCR_NEEDLE_CYRILLIC`) that the 018-03 composition E2E asserts
                 after OCR.
  digital.pdf  — a born-digital PDF with real selectable text (for the
                 `--skip-text` no-op / mixed-input path in 018-03).

Run `python3 _pdf_ocr_fixtures.py [OUT_DIR]` to (re)generate them (default
OUT_DIR = `tests/fixtures`). `test_e2e.sh` calls it with a tmp dir.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
from reportlab.lib.pagesizes import letter  # type: ignore
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.platypus import (  # type: ignore
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

# The OCR needle. The ASCII portion is rendered with the built-in bitmap font
# (reliably OCR-able by tesseract); the Cyrillic portion is best-effort (needs a
# Cyrillic-capable TrueType font on the host). The 018-03 E2E asserts the ASCII
# needle case-insensitively and the Cyrillic needle only when `rus` is installed.
OCR_NEEDLE_ASCII = "Invoice OCR 2026 hello world"
OCR_NEEDLE_CYRILLIC = "Привет мир ТЕСТ"

# Candidate Cyrillic-capable TrueType fonts (best-effort; falls back to the
# built-in bitmap font, which renders ASCII fine but not Cyrillic).
_TTF_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",                # Fedora
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)


def _load_font(size: int) -> ImageFont.ImageFont:
    """A Cyrillic-capable TrueType font if one is on the host, else the built-in
    bitmap font (ASCII-legible; Cyrillic glyphs may be missing)."""
    for candidate in _TTF_CANDIDATES:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without the size kwarg
        return ImageFont.load_default()


def build_scan_pdf(path: Path) -> None:
    """A 1-page image-only PDF: the OCR needle is rendered to a raster image and
    embedded full-page, so there is NO text layer (extract_text() yields "")."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # ~US-Letter at 150 dpi.
    img = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font(48)
    lines = [
        "SCANNED DOCUMENT",
        "",
        OCR_NEEDLE_ASCII,
        OCR_NEEDLE_CYRILLIC,
        "",
        "This page is a single raster image with no text layer.",
    ]
    y = 150
    for line in lines:
        draw.text((120, y), line, fill="black", font=font)
        y += 110

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name
    try:
        img.save(png_path)
        c = canvas.Canvas(str(path), pagesize=letter)
        c.drawImage(png_path, 0, 0, width=letter[0], height=letter[1])
        c.save()
    finally:
        os.unlink(png_path)


def build_digital_pdf(path: Path) -> None:
    """A born-digital PDF with real selectable text (no OCR needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Born-Digital Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "This paragraph is real, selectable vector text. With the default "
            "--skip-text mode pdf_ocr must leave it untouched (no destruction).",
            styles["BodyText"],
        ),
    ]
    doc.build(story)


def build_encrypted_scan(path: Path, password: str = "test-pw") -> None:
    """An image-only (scanned) PDF encrypted with `password` — for the
    `--password` (R5) decrypt path. Built with pypdf (base dep), so no OCR
    engine is needed to construct the fixture; pikepdf opens it for decryption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        plain = tmp.name
    try:
        build_scan_pdf(Path(plain))
        reader = PdfReader(plain)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)
        with open(path, "wb") as fh:
            writer.write(fh)
    finally:
        os.unlink(plain)


def build_all(out_dir: Path) -> dict[str, Path]:
    """Build both fixtures into `out_dir`; return the path map."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scan": out_dir / "scan.pdf",
        "digital": out_dir / "digital.pdf",
    }
    build_scan_pdf(paths["scan"])
    build_digital_pdf(paths["digital"])
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent / "fixtures"
    )
    built = build_all(target)
    for name, p in built.items():
        print(f"{name}: {p}")
