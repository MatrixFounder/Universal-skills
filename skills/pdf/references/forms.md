# PDF forms: detecting and filling

PDF forms come in two incompatible flavours:

1. **AcroForm** — the original format, fields stored as PDF objects.
   Supported by nearly every reader and editable with `pypdf`.
2. **XFA** (XML Forms Architecture) — Adobe LiveCycle-era. Fields
   stored as XML blobs inside the PDF. Not supported by most open-
   source tooling; needs commercial solutions or the JavaScript
   library `pdf-lib` in limited cases.

## Always detect first — never assume the path

Form filling has two distinct code paths: the AcroForm path
(programmatic field fill via `pypdf`) and the visual-overlay path
(draw text onto the page). Which path to take depends entirely on
whether the file has `/AcroForm` and fillable widgets — so run a
detection script as the first step every time. Do not pick a path
based on the filename, the user's phrasing, or a guess; the AcroForm
check is the gate.

## Detecting which kind you have

```python
from pypdf import PdfReader
reader = PdfReader("form.pdf")

acroform = reader.trailer["/Root"].get("/AcroForm")
if acroform:
    fields = reader.get_form_text_fields() or {}
    print(f"AcroForm with {len(fields)} text fields")
    xfa = acroform.get("/XFA")
    if xfa:
        print("Note: also contains XFA data")
else:
    print("No form fields found")
```

If `/AcroForm` is absent the file has no fillable fields at all; you
can still overlay text at known coordinates using `reportlab` and
`pypdf.page.merge_page`. See [library-selection.md](library-selection.md).

## Filling an AcroForm

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("form.pdf")
writer = PdfWriter(clone_from=reader)

data = {
    "customer_name": "Acme Inc.",
    "invoice_date": "2026-04-24",
    "agree_terms": "/Yes",   # checkbox export value, not True/False
}

for page in writer.pages:
    writer.update_page_form_field_values(page, data)

with open("filled.pdf", "wb") as fh:
    writer.write(fh)
```

Field names come from `reader.get_fields()`. Checkboxes need the
export value as a name object (`"/Yes"` / `"/Off"`). Radio button
values are the export value of the chosen button, not its index.

## Flattening

"Flattening" bakes the field values into the page content so they
can't be edited anymore. `pypdf` supports this via
`writer.remove_links()` and by explicitly dropping the form
dictionary:

```python
if "/AcroForm" in writer._root_object:
    del writer._root_object["/AcroForm"]
```

This is surgical; for a full flatten (draw the field text onto the
page as static content) consider `pdf-lib` in Node or `pikepdf` in
Python. Plain `pypdf` leaves the value in the field dictionary but
removes the interactive form.

## Visual overlay fallback

When a "form" is actually a non-interactive layout where users are
expected to print and handwrite, you can still fill it
programmatically by drawing text at known coordinates:

```python
from io import BytesIO
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

overlay_buf = BytesIO()
c = canvas.Canvas(overlay_buf, pagesize=(612, 792))
c.setFont("Helvetica", 11)
c.drawString(120, 680, "Acme Inc.")
c.showPage()
c.save()

base = PdfReader("template.pdf")
overlay = PdfReader(BytesIO(overlay_buf.getvalue()))
writer = PdfWriter(clone_from=base)
writer.pages[0].merge_page(overlay.pages[0])
with open("filled.pdf", "wb") as fh:
    writer.write(fh)
```

You need to know the coordinates (y from bottom, Helvetica is the
safe default). For more than a couple of fields use
[check_bounding_boxes.py-style](https://example.invalid) tooling to
inspect the PDF first — this skill does not include such a helper in
the MVP, but `pdfplumber`'s `page.chars` gives you word coordinates
from which you can infer where to place text.

## Two-stage coordinate extraction for non-fillable forms

When the detection step shows no `/AcroForm`, work out field
coordinates in two stages — structure extraction first, image-based
extraction only as a fallback:

1. **Structure extraction via `pdfplumber`.** Read labels,
   underscore-lines, rectangles, and checkbox positions from the PDF
   object model. Cheap, exact, and deterministic when a text layer
   exists.
2. **Image-based fallback.** If the extracted text is dominated by
   `(cid:N)` tokens, the document is a scan or uses custom-encoded
   fonts with no ToUnicode map — there is no usable text layer.
   Render the page with `pdf2image` at 2-3x zoom and locate fields
   visually (OpenCV contour detection, or OCR via Tesseract).

Do not jump straight to the image path: structure extraction is an
order of magnitude faster and produces pixel-accurate coordinates
when it works.

### Hybrid detection for circular/colored checkboxes

Structure extraction reliably finds plain rectangular, uncolored
checkboxes (drawn as `/Rect` widgets or black outlines). It tends to
miss circular checkboxes (drawn as `/Circle` annotations or vector
curves) and filled/colored boxes (the fill colour masks the outline
heuristics). For those specific field types, run a hybrid: keep
`pdfplumber` for prose and layout, but rasterize the page and use
image-based detection (Hough circles, color-threshold contours) to
locate just the checkbox glyphs.

## Pre-fill validation of `fields.json`

Before rendering a filled PDF, validate the `fields.json`
structurally — visual checks after rendering are expensive:

- **No bounding-box intersections.** Any two field bboxes that
  overlap will collide once filled. Reject the JSON if an
  axis-aligned intersection is found.
- **Box large enough for its font size.** Compute a rough glyph
  extent (`font_size * 0.6 * len(value)` wide, `font_size * 1.2`
  tall) and reject fields whose declared box cannot hold it.

Catching both at the JSON stage turns a slow render-and-eyeball loop
into a fast precondition check.

## Coordinate-system consistency in `fields.json`

A `fields.json` must commit to one coordinate system end-to-end.
Pick exactly one:

- **PDF points.** Signal by including top-level `pdf_width` and
  `pdf_height` keys. All field bboxes are then in points, origin
  bottom-left.
- **Image pixels.** Signal by including top-level `image_width` and
  `image_height` keys (the rasterization size). All field bboxes
  are then in pixels, origin top-left.

Mixing the two — e.g. declaring `pdf_height` while some bboxes are in
pixels — silently produces misplaced text because the fill script
has no way to tell which unit a given bbox uses. The fill script
should assert that exactly one of the two signal pairs is present
and reject the file otherwise.

## XFA forms

If `/AcroForm/XFA` is set, `pypdf` can read the XML blob but not
reliably fill it. Your options:

1. Ask the user to re-export the form from Adobe as a flat AcroForm.
2. Use `pdf-lib` in a Node script if the XFA form is relatively simple.
3. Commercial tooling: Adobe Acrobat Pro SDK, PDFtron, iText
   (AGPL — be careful).

This skill does not ship XFA support; surface the limitation to the
user rather than silently producing an unchanged file.

## Checklist

- [ ] Confirm the form has `/AcroForm` before promising the user you
      can fill it.
- [ ] Pull field names via `reader.get_fields()` and match them to the
      JSON keys.
- [ ] Map checkbox/radio values to their export values, not
      `True`/`False`.
- [ ] Decide whether to flatten — if the user will email the filled
      PDF, flatten it so recipients can't edit fields.
- [ ] Open the filled file in Adobe Reader or Preview.app to confirm
      the values render.
