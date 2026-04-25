# OOXML basics for .docx

A `.docx` is a ZIP archive of XML parts that conform to
[ECMA-376](https://ecma-international.org/publications-and-standards/standards/ecma-376/)
Part 1 (WordprocessingML) and Part 2 (Open Packaging Conventions).
Understanding what lives where is enough for most editing tasks.

## ZIP layout at a glance

```
input.docx
├── [Content_Types].xml         # MIME types for every part; ECMA-376 Part 2 §10
├── _rels/
│   └── .rels                   # top-level relationships; points at word/document.xml
└── word/
    ├── document.xml            # the actual body content — §17 WordprocessingML
    ├── styles.xml              # paragraph/character/table styles
    ├── numbering.xml           # list definitions (abstractNum + num)
    ├── settings.xml            # compat flags, view settings, rsids
    ├── fontTable.xml           # referenced fonts
    ├── theme/theme1.xml        # DrawingML theme (colors, fonts)
    ├── media/                  # embedded images, charts, etc.
    ├── _rels/
    │   └── document.xml.rels   # relationships out of document.xml
    ├── comments.xml            # optional; only if the file has comments
    ├── commentsExtended.xml    # optional; threaded replies
    ├── commentsIds.xml         # optional; paraId mapping for Word 365
    ├── commentsExtensible.xml  # optional; durable IDs
    ├── people.xml              # authors used by tracked changes / comments
    ├── header1.xml, footer1.xml
    └── ...
```

## Minimum viable document

A valid `.docx` only needs four parts:

1. `[Content_Types].xml` declaring at least
   `word/document.xml` → `application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml`.
2. `_rels/.rels` with one relationship pointing at `word/document.xml`.
3. `word/_rels/document.xml.rels` (even if empty).
4. `word/document.xml` with a `<w:body>` containing at least one `<w:p>`.

Anything else (styles, numbering, theme) is optional — Word will
generate defaults when opening the file.

## Most-referenced namespaces

| Prefix | Namespace URI | Used for |
|---|---|---|
| `w`   | `http://schemas.openxmlformats.org/wordprocessingml/2006/main` | Body, paragraphs, runs, styles |
| `r`   | `http://schemas.openxmlformats.org/officeDocument/2006/relationships` | Relationship references (`r:id`) |
| `a`   | `http://schemas.openxmlformats.org/drawingml/2006/main` | DrawingML (images, shapes, colours) |
| `wp`  | `http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing` | Drawing anchors in Word |
| `pic` | `http://schemas.openxmlformats.org/drawingml/2006/picture` | Picture wrapper for images |
| `mc`  | `http://schemas.openxmlformats.org/markup-compatibility/2006` | `<mc:AlternateContent>` |
| `w14` | `http://schemas.microsoft.com/office/word/2010/wordml` | Math and new Word features from 2010+ |

Modern Word writes additional `w15`, `w16cid`, `w16cex`, `w16du`, and
`w16sdt*` namespaces for features added in later yearly releases.
Treat anything you don't understand as opaque and preserve it on
round-trip; blind removal breaks files.

## Units

- **EMU** (English Metric Unit): 914,400 EMU = 1 inch. Used by DrawingML
  positions and sizes.
- **DXA** (twentieths of a point): 1,440 DXA = 1 inch. Used by page
  size, margins, table widths, indentation.
- **Half-points**: font sizes. `<w:sz w:val="24"/>` = 12 pt.

Common page sizes in DXA:

| Page | Width × Height (DXA) |
|---|---|
| US Letter | 12240 × 15840 |
| A4        | 11906 × 16838 |
| Legal     | 12240 × 20160 |

## Element order in `<w:pPr>` and `<w:rPr>`

WordprocessingML is strict about child ordering (ECMA-376 Part 1 §17.3).
If you add a child element to `<w:pPr>` or `<w:rPr>` in the wrong
position, some Word versions silently drop your change. Keep a
reference handy while hand-editing — `office/validate.py` does not
catch every ordering issue because XSD validation is optional unless
you bundle the full schema pack.

The `<w:pPr>` children most people touch have this required sequence:

1. `pStyle`
2. `numPr`
3. `spacing`
4. `ind`
5. `jc`
6. `rPr`

Reverse any two of these and Word accepts the file but quietly drops
the misplaced children on the next save — the paragraph re-renders
without your style, numbering, or alignment. When patching by hand,
keep the order above. (The full XSD content model has more slots —
borders, shading, frame properties — but for everyday editing these
six cover most work.)

## Cell margins are internal padding

`<w:tcMar>` entries (top/left/bottom/right on a table cell, or a
table-wide `<w:tblCellMar>`) set the INTERNAL padding between the
cell's border and its content. They shrink the usable content area
inside the cell; they do NOT extend the cell outward. This differs
from CSS `margin`, where margins push siblings apart. Cell width
continues to be determined by `<w:tblGrid>` / `<w:gridCol>` and the
per-cell `<w:tcW>`. If your text feels cramped after adding margins,
widen the column — don't expect the cell to grow.

## Smart-quote entity round-trips

`office/unpack.py` deliberately rewrites `"`, `"`, `'`, `'`, `–`, `—`,
`…` into `&#x201C;` etc. before you edit. Reason: regex tooling and
Python string handling of raw UTF-8 quotation marks is inconsistent,
and editors sometimes "autocorrect" them. Entities survive the edit
cycle untouched. `office/pack.py` reverses the transformation.

## Further reading

- ECMA-376 Part 1 (WordprocessingML): https://ecma-international.org/publications-and-standards/standards/ecma-376/
- `[MS-DOCX]` (Microsoft): https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/
- Open Packaging Conventions: ECMA-376 Part 2.
