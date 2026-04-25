# Choosing a PDF library

PDF tooling is fragmented. There is no single library that does
everything; the skill leans on five, each for what it does best.

## Quick decision table

| Task | Recommended tool |
|---|---|
| Markdown → PDF | `weasyprint` (via [scripts/md2pdf.py](../scripts/md2pdf.py)) |
| HTML (with modern CSS/JS) → PDF | `playwright` (not bundled — add if needed) |
| Merge, split, rotate | `pypdf` (via [scripts/pdf_merge.py](../scripts/pdf_merge.py), [scripts/pdf_split.py](../scripts/pdf_split.py)) |
| Fill AcroForm fields | `pypdf` (via [scripts/pdf_fill_form.py](../scripts/pdf_fill_form.py); XFA refused with exit 11, no-form refused with exit 12) |
| Encrypt / decrypt PDF | `pypdf.PdfWriter.encrypt` (NOT wrapped by a bundled script — drop into Python directly; the office skills' `office_passwd.py` is OOXML-only and does not apply to PDFs) |
| Extract text preserving layout | `pdfplumber` |
| Extract tables | `pdfplumber.extract_tables()` or Tabula (Java) |
| Create PDF from scratch programmatically | `reportlab` (not bundled) |
| OCR a scanned PDF | `ocrmypdf` (CLI) or `pytesseract` + `pdf2image` |
| Render PDF to PNG/JPEG | `pdf2image` (uses Poppler) |

## What `pypdf` does well

- Merge, split, rotate, concatenate — fast and lossless.
- Read metadata (`/Title`, `/Author`, etc.) and update it.
- Fill AcroForm fields (plain PDF forms).
- Encrypt/decrypt (RC4-128, AES-128, AES-256).
- Preserve bookmarks (outlines) through merges.

What it does *not* do:

- Good text extraction — you'll get garbled runs on most files. Use
  `pdfplumber` instead.
- Fill XFA forms (the XML-based Adobe LiveCycle kind). Those need
  commercial tooling or `pdf-lib` via Node.
- Render pages — use `pdf2image` or `pdfplumber` for that.

## What `pdfplumber` does well

Built on top of `pdfminer.six`, tuned for extraction:

- Text with coordinates (`page.extract_words()`) — useful for
  building OCR overlays.
- Tables (`page.extract_tables()`), with configurable
  line-detection heuristics.
- Preserve layout (`page.extract_text(layout=True)`) so columns
  don't merge.

Weakness: creation. `pdfplumber` is read-only.

## What `weasyprint` does well

- HTML + CSS (including `@page`, `@media print`, counters, columns) →
  PDF, no headless browser required.
- Fast startup (~50ms), great for server-side rendering.
- Full support for modern CSS layout: flexbox, grid, columns, `@page`
  size/margins, page breaks (`break-before: page`), running headers.

Weakness: CSS3 animations, JavaScript, web components. For those,
reach for `playwright`.

## What `reportlab` does well

- Low-level PDF canvas API for precise positioning — good for
  invoices, certificates, reports with strict brand layout.
- Platypus (document model) for multi-page reports with flowables.

Weakness: steep learning curve. If your content starts as Markdown
or HTML, weasyprint is faster to reach for.

### ReportLab Unicode subscript/superscript gotcha

ReportLab's built-in Type 1 fonts do not include the Unicode
subscript (`₁₂₃`) or superscript (`¹²³`) glyph range. Drawing a
literal `₂` or `²` through `canvas.drawString` renders a black box.
Use the `<sub>...</sub>` and `<super>...</super>` tags inside a
`Paragraph` flowable instead — they scale the surrounding font rather
than rely on dedicated glyphs:

```python
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
styles = getSampleStyleSheet()
p = Paragraph("H<sub>2</sub>O, E = mc<super>2</super>", styles["BodyText"])
```

## External tools

- **Poppler** (`pdftotext`, `pdftoppm`, `pdfimages`): GPL, ubiquitous,
  command-line. `pdf2image` uses Poppler under the hood.
- **qpdf**: Apache-2.0, fast CLI merge/split/linearize. Useful for
  CI pipelines; same jobs as `pypdf` but faster and without Python.
  Commonly used invocations:
  ```bash
  qpdf --check input.pdf                      # validate structure
  qpdf --fix-qdf input.pdf output.pdf         # repair common corruption
  qpdf --linearize input.pdf output.pdf       # optimize for web streaming
  qpdf --split-pages=N input.pdf output.pdf   # faster than pdf_split.py on large files
  ```
- **`pdftotext -bbox-layout`** (poppler-utils): emits text together
  with per-word bounding boxes as HTML. Significantly faster than
  `pdfplumber` for 100+ page documents where you only need text plus
  coordinates; reach for it before `pdfplumber` on very large inputs.
- **Ghostscript** (`gs`): AGPL for the open-source build — be careful
  if your product is commercial. Good for compression
  (`-dPDFSETTINGS=/ebook`) and format conversion.
- **Tesseract**: Apache-2.0. The underlying OCR engine behind
  `pytesseract` and `ocrmypdf`.
- **ocrmypdf**: MPL-2.0. Wraps Tesseract + Ghostscript + Poppler for
  the specific "add a text layer to a scan" task. Usually the right
  starting point for OCR.

## Installation shortcuts

macOS:
```bash
brew install poppler qpdf ghostscript tesseract
pip install pypdf pdfplumber weasyprint markdown2
```

Debian/Ubuntu:
```bash
sudo apt install poppler-utils qpdf ghostscript tesseract-ocr tesseract-ocr-rus
pip install pypdf pdfplumber weasyprint markdown2
```

weasyprint has native dependencies (`cairo`, `pango`, `gdk-pixbuf`);
on macOS `brew install pango` is usually all you need.

## Encrypted PDFs

Before any read, check `reader.is_encrypted` and decrypt if needed.
Skipping this causes silent failures — `pypdf` returns empty text or
empty `reader.pages` for encrypted documents without raising:

```python
from pypdf import PdfReader
reader = PdfReader("secret.pdf")
if reader.is_encrypted:
    if not reader.decrypt(password):
        raise ValueError("wrong password")
# only now is it safe to read pages / fields / metadata
```

Treat the `is_encrypted` check as the first line of every extraction
or form-fill script.
