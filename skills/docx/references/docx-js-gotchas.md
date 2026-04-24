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

`md2docx.js` accepts `--size letter` and does this for you. For
landscape orientation, swap width/height AND add
`orientation: PageOrientation.LANDSCAPE`.

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

## Reference

- dolanmiu/docx issue tracker: <https://github.com/dolanmiu/docx/issues>
- ECMA-376 Part 1 §17 (WordprocessingML)
- ECMA-376 Part 1 §20 (DrawingML) for images
