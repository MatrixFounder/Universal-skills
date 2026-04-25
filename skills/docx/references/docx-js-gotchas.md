# docx-js gotchas

[`dolanmiu/docx`](https://github.com/dolanmiu/docx) (the `docx` npm
package, imported by `md2docx.js`) is the most widely-used library for
assembling Word documents from JavaScript. It is generally excellent,
but certain defaults and APIs routinely surprise people. This file
records the pitfalls that matter in practice.

## Page size defaults to A4

`new Document({ sections: [...] })` with no page size information
produces an A4 document. For US Letter, set it explicitly on the
section properties:

```js
sections: [{
  properties: {
    page: {
      size: { width: 12240, height: 15840 },  // DXA, US Letter
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
    },
  },
  children: [...],
}]
```

`md2docx.js` accepts `--size letter` and does this for you.

### Landscape orientation — pass PORTRAIT dimensions

Give `page.size` the PORTRAIT dimensions (short edge as `width`, long
edge as `height`) and add `orientation: PageOrientation.LANDSCAPE`.
The library performs the axis swap internally when it emits
`<w:pgSz w:orient="landscape"/>`:

```js
page: {
  size: {
    width: 12240,    // portrait short edge (8.5 in)
    height: 15840,   // portrait long edge (11 in)
    orientation: PageOrientation.LANDSCAPE,
  },
}
```

**Common mistake — the double swap.** Passing the already-rotated
dimensions (`width: 15840, height: 12240`) together with the
orientation flag makes the library swap a second time. The resulting
page geometry disagrees with the orientation attribute and Word either
renders a broken layout or refuses to open the file. Always feed
portrait numbers.

## `<w:pPr>` child-element ordering

Word silently drops paragraph properties when their children are out
of sequence (ECMA-376 Part 1 §17.3.1.26). The required order inside
`<w:pPr>` is `pStyle`, `numPr`, `spacing`, `ind`, `jc`, `rPr`. If you
assemble the tree by hand (or patch an unpacked document) and reverse
two of these, Word accepts the file but discards the misplaced nodes
on the next save:

```xml
<w:pPr>
  <w:pStyle w:val="Heading1"/>
  <w:numPr>...</w:numPr>
  <w:spacing w:before="240" w:after="120"/>
  <w:ind w:left="720"/>
  <w:jc w:val="center"/>
  <w:rPr>...</w:rPr>
</w:pPr>
```

## Table shading — always `ShadingType.CLEAR`

`ShadingType.SOLID` makes Word paint the cell black regardless of the
`color` / `fill` values you pass. Use `ShadingType.CLEAR` for any
normal coloured background:

```js
shading: { type: ShadingType.CLEAR, color: "auto", fill: "FFE599" }
```

## Table width unit — prefer `WidthType.DXA`

Express table and cell widths in `WidthType.DXA` (twentieths of a
point). `WidthType.PERCENTAGE` is legal OOXML and Word accepts it,
but Google Docs imports mangle column layout on percentage-based
tables. DXA round-trips cleanly through every mainstream viewer.

## Cell margins are internal padding, not CSS margin

`tableCellMargin` / per-cell `margins` set the INTERNAL padding
between cell borders and the cell's content; they shrink the usable
content area and do NOT enlarge the cell. The cell's outer width
stays whatever the column definition says. This surprises people
porting HTML/CSS layouts where `margin` pushes siblings apart.

```xml
<w:tcPr>
  <w:tcMar>
    <w:top    w:w="100" w:type="dxa"/>
    <w:left   w:w="100" w:type="dxa"/>
    <w:bottom w:w="100" w:type="dxa"/>
    <w:right  w:w="100" w:type="dxa"/>
  </w:tcMar>
</w:tcPr>
```

## `PageBreak` must live inside a `Paragraph`

A `PageBreak` is a run-level element and must be nested inside a
`Paragraph` (typically wrapped in a run). Emitting it as a top-level
child of the section produces XML that some readers silently drop
(mammoth, pandoc) while others refuse to open (strict OOXML
validators). Wrap it:

```js
new Paragraph({ children: [new PageBreak()] })
```

## What `pack.py` auto-repair does NOT fix

`scripts/office/pack.py` applies two narrow repairs on repack:

1. Rewrites `durableId` attribute values that exceed the 32-bit
   signed positive range (≥ `0x7FFFFFFF`) down into a valid range.
2. Adds `xml:space="preserve"` to `<w:t>` / `<w:delText>` elements
   whose content has leading or trailing whitespace.

It does **not** repair:

- Malformed XML (unclosed tags, illegal characters, broken
  CDATA sections). Fix those by re-running your editor's XML
  linter before packing.
- Incorrect element nesting (for example, `<w:commentRangeStart>`
  placed inside `<w:r>`, or out-of-order `<w:pPr>` children).
- Missing `.rels` relationships — if `document.xml` references
  `rId99` and `document.xml.rels` doesn't declare it, pack.py
  will cheerfully ZIP the broken pair.
- Content-type omissions in `[Content_Types].xml`.

Treat pack.py as packaging glue, not as a validator. Run
`office/validate.py` (and, when available, XSD validation) for the
structural checks.

## Numbered and bulleted lists

Use `LevelFormat.BULLET` or `LevelFormat.DECIMAL`, never hand-typed
Unicode bullets. Numbering lives in a document-level `numbering` map
that every list paragraph references by a shared name. Skipping the
numbering definition works for bullets in some viewers but breaks in
others.

```js
numbering: {
  config: [{
    reference: "bullet",
    levels: [
      { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT },
      { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT },
    ],
  }],
}
```

## Tables need dual widths

OOXML table rendering reads both `columnWidths` on the table and
`width` on each cell. Set both in DXA units:

```js
new Table({
  columnWidths: [3000, 6000, 3000],
  rows: rows.map(r => new TableRow({
    children: r.map((text, i) => new TableCell({
      width: { size: [3000, 6000, 3000][i], type: WidthType.DXA },
      children: [new Paragraph({ children: [new TextRun(text)] })],
    })),
  })),
})
```

Only setting `columnWidths` or only setting per-cell `width` makes
Word's column layout go wild, especially for tables wider than the
page.

## Images require `altText` with all three fields

The library lets you pass `altText` as an object; accessibility tools
(and certain Word builds) complain if any of the three keys is missing:

```js
new ImageRun({
  type: "png",  // or "jpg", "gif", "bmp", "svg"
  data: fs.readFileSync("chart.png"),
  transformation: { width: 400, height: 300 },
  altText: {
    title: "Q4 Revenue",
    description: "Bar chart comparing quarterly revenue across regions.",
    name: "Q4 Revenue Chart",
  },
})
```

The `type` field is mandatory and must match the actual data. Passing
PNG bytes with `type: "jpg"` renders as a broken image.

## TOC entries need clean `HeadingLevel`

`docx-js` only picks up entries for a table of contents if paragraphs
use `HeadingLevel.HEADING_1..9` *without* a custom style override.
Adding `style: "MyHeading"` to the same paragraph disables TOC
detection. Also ensure the heading paragraph has an `outlineLevel`
matching the heading number (`outlineLevel: 0` for Heading 1).

## Image embedding at the XML layer

If you're building images outside `docx-js` (for example, after
`unpack.py`), remember the three changes needed:

1. Add the file to `word/media/`.
2. Add a relationship in `word/_rels/document.xml.rels`:
   `<Relationship Id="rId42" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/chart.png"/>`
3. Add a content type in `[Content_Types].xml` for the extension if it
   isn't already declared: `<Default Extension="png" ContentType="image/png"/>`.
4. Reference the relationship inside a `<w:drawing>` /
   `<wp:inline>` / `<a:graphic>` chain, with `<a:blip r:embed="rId42"/>`.

Missing any of these makes Word open the document with a "can't
display image" placeholder.

## rsids and durable IDs

When round-tripping a document, `rsid*` attributes on `<w:p>`, `<w:r>`,
`<w:rPr>` are opaque 8-hex-digit session IDs. Preserve them verbatim
on unpack/repack cycles — don't try to "clean them up". For tracked
changes, `w:id` must be unique and `durableId` must be a 32-bit signed
positive integer (< `0x7FFFFFFF`). `office/validate.py` checks for
duplicate IDs but not for value ranges.

## Shape-group rendering (docx2md)

Mammoth only extracts embedded `<pic:pic>` / `<w:pict>` as images. Word
SmartArt and hand-composed shape groups (`<w:drawing>` containing many
`<wps:wsp>` rectangles + connectors + text-boxes) are NOT surfaced as
one image — mammoth flattens their `<w:txbxContent>` text into
disjointed inline paragraphs, so the diagram disappears.

`docx2md.js` recovers shape groups in two phases:

1. **Locate** each shape group via LibreOffice HTML export
   (`soffice --headless --convert-to html`). The exported HTML
   contains an `<img>` for every `<w:drawing>`, in document order,
   surrounded by the source paragraph text. We harvest those `<img>`
   tags as anchor candidates and only keep the ones whose surrounding
   text doesn't already coincide with a mammoth-extracted image.
2. **Render** the bitmap. Two paths, picked at runtime by tool
   detection:

### Preferred: poppler PDF crop

When `pdftoppm` and `pdftotext` are on `PATH`, the renderer:

1. Converts the docx to PDF via `soffice --convert-to pdf`.
2. Runs `pdftotext -bbox-layout` to map every text block on every
   page to its (xMin, yMin, xMax, yMax) in PDF points.
3. For each LO HTML anchor, finds the matching block on a page and
   crops from `anchor.yMax` down to either the first "real prose"
   block (xMax-xMin > 450pt — full text-area width) or the bottom of
   the last post-anchor block on the page, whichever comes first.
4. Calls `pdftoppm -r 150 -png -f N -l N -x X -y Y -W W -H H` to
   raster-crop only that region.

Why prose detection by width: mammoth has already extracted the
shape-group's text into the markdown as stranded labels, so we can't
reliably distinguish "real paragraph" from "diagram label" by string
match (the labels self-match). Width is a robust discriminator for
Letter/A4 docs with normal margins — a paragraph spans ~470pt of
text-area, a diagram label is rarely wider than 350pt.

The result is a PNG that includes both the shape geometry AND the
text labels, because PDF rasterisation flattens the two layers into
one bitmap.

### Fallback: LibreOffice HTML GIF

When poppler is missing, we use the LO HTML export's GIF directly.
Limits:

- **Geometry only**: LO HTML rasterises the drawing layer but flows
  the text-box content as separate `<p>` elements. The bitmap shows
  empty boxes; the labels end up below as stranded paragraphs (which
  we then drop).
- **Do NOT run `soffice --convert-to png` on the standalone GIF**:
  soffice treats it as a Writer document and wraps it on a letter-
  size page, producing a mostly-empty 816×1056 bitmap. The native
  GIF dimensions (~500px for typical groups) are correct and every
  mainstream markdown viewer (GitHub, VSCode, Typora, Obsidian)
  renders GIF natively. If you must standardise on PNG, use a bitmap
  tool — macOS `sips -s format png`, Linux `magick`, Node `sharp` —
  not a document converter.

### Cleanup pass

After injection (poppler or fallback), `docx2md.js` drops the
"stranded label" paragraphs mammoth left behind (`**RFC**`,
`**Creation**`, bare digits, etc.). Scan stops at the first heading,
table row, bullet, TOC link, blockquote, or horizontal rule — real
body content is preserved. Then `collapseDuplicateImageRuns`
collapses runs of identical `![](href)` tokens on a single line
(common with stranded marker icons).

## Reference

- dolanmiu/docx issue tracker: <https://github.com/dolanmiu/docx/issues>
- ECMA-376 Part 1 §17 (WordprocessingML)
- ECMA-376 Part 1 §20 (DrawingML) for images
