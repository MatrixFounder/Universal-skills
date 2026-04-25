# pptxgenjs basics

[`pptxgenjs`](https://gitbrent.github.io/PptxGenJS/) is a MIT-licensed
JavaScript library that assembles `.pptx` files without needing
PowerPoint or LibreOffice. The `md2pptx.js` script wraps it so
Markdown → slides works in one command. This note is for the cases
where you need to step out of the wrapper and call the library
directly.

## Slide dimensions and layouts

PowerPoint measures everything in inches. Standard layouts:

| Layout | Width × Height (inches) |
|---|---|
| 16:9 (widescreen, default) | 10 × 5.625 |
| 4:3 (classic)              | 10 × 7.5 |
| 16:10                      | 10 × 6.25 |
| Letter                     | 8.5 × 11 |
| A4                         | 8.27 × 11.69 |

Set via `pres.layout = "LAYOUT_16x9"` / `"LAYOUT_4x3"` / `"LAYOUT_WIDE"`,
or define a custom one with
`pres.defineLayout({ name: "CUSTOM", width: 10, height: 6 })` and then
`pres.layout = "CUSTOM"`.

## Core constructor

```js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
const slide = pres.addSlide();
slide.background = { color: "FFFFFF" };
slide.addText("Hello", { x: 0.5, y: 0.3, w: 9, h: 1, fontSize: 32, bold: true });
await pres.writeFile({ fileName: "out.pptx" });
```

All measurements (`x`, `y`, `w`, `h`) are inches.

## Text objects

`addText` accepts either a single string or an array of `{text, options}`
objects. The array form is how you style runs within a single text
box:

```js
slide.addText([
  { text: "Revenue grew ", options: {} },
  { text: "24%", options: { bold: true, color: "2563EB" } },
  { text: " year over year." },
], { x: 0.5, y: 1.0, w: 9, h: 0.6, fontSize: 18 });
```

Common options: `fontSize`, `fontFace`, `color`, `bold`, `italic`,
`underline`, `align` (`"left"|"center"|"right"`), `valign`
(`"top"|"middle"|"bottom"`), `fill` (background of the text box),
`hyperlink: { url: "..." }`.

## Bullet and numbered lists

Pass `bullet: true` (or `bullet: { type: "number" }`) and optionally
`indentLevel` (0-based):

```js
slide.addText(
  [{ text: "First", options: { bullet: true } },
   { text: "Second", options: { bullet: true } },
   { text: "Sub-item", options: { bullet: true, indentLevel: 1 } }],
  { x: 0.5, y: 1.2, w: 9, h: 2.5, fontSize: 16 },
);
```

## Tables

```js
slide.addTable([
  [{ text: "Metric", options: { bold: true } },
   { text: "Q4", options: { bold: true } },
   { text: "Q1", options: { bold: true } }],
  ["Revenue", "840k", "915k"],
  ["Churn", "3.2%", "2.8%"],
], { x: 0.5, y: 1.5, w: 9, h: 2.0, colW: [3, 3, 3], fontSize: 14 });
```

`colW` accepts an array (fixed widths) or a number (uniform). Set
`border: { type: "solid", color: "E5E7EB", pt: 0.5 }` for subtle
dividers.

## Images

```js
slide.addImage({
  path: "./chart.png",
  x: 5, y: 1, w: 4, h: 3,
});
```

Use `data` instead of `path` for base64-encoded data URLs. `sizing`
(`{ type: "contain", w, h }`) fits the image into a box preserving
aspect ratio.

## Common pitfalls

1. **Invisible padding.** Text boxes have an internal margin that
   prevents you from visually aligning a text's baseline with the
   edge of a shape. Set `margin: 0` on the text options to disable it.
2. **Dark text on dark background.** `pptxgenjs` does not auto-invert
   colour. If you set a dark slide background, also set `color: "FFFFFF"`
   on every text object.
3. **Fonts not installed on the reader's machine.** `.pptx` does not
   embed the font itself — it just references the face name. If your
   deck uses an exotic font, include a fallback or use a web-safe face
   (Calibri, Arial, Helvetica, Georgia, Cambria).
4. **`addSlide({ masterName })` requires `defineSlideMaster` first.**
   Masters are useful for backgrounds and logos applied to many
   slides; define them at the top of your script.
5. **Option objects are mutated in place.** `pptxgenjs` rewrites inch
   values to EMUs on first use. Reusing the same `shadow`, `line`, or
   `fill` object across two `addShape` calls means the second call
   receives an already-converted object and renders incorrectly or
   corrupts the file. Build a fresh object per call, or clone:
   ```js
   const shadow = { type: "outer", blur: 8, offset: 3, angle: 90, color: "000000", opacity: 0.3 };
   slide.addShape(pres.ShapeType.rect, { x: 1, y: 1, w: 2, h: 1, shadow: structuredClone(shadow) });
   slide.addShape(pres.ShapeType.rect, { x: 4, y: 1, w: 2, h: 1, shadow: structuredClone(shadow) });
   ```
6. **Hex colours must be bare.** Write `"FF6B35"`, never `"#FF6B35"`.
   The `#` prefix produces a file some viewers silently ignore and
   others refuse to open. Opacity is NOT encoded as an 8-character
   hex value either — express it with the separate `opacity` property
   (`0.0`–`1.0`).
7. **`rectRadius` is shape-type-specific.** It only takes effect on
   `ROUNDED_RECTANGLE`. On plain `RECTANGLE` it is silently ignored —
   no warning, no error. If you want rounded corners, switch the
   shape type, don't just set the radius.
8. **`charSpacing`, not `letterSpacing`.** The CSS-style name is
   silently dropped. Use `charSpacing: 2` (units: hundredths of a
   point) on the text options.
9. **`lineSpacing` inflates bullet gaps.** Applied to bulleted text
   it produces excessive space between bullets. For tight bullet
   spacing, reach for `paraSpaceAfter` (points) instead — it operates
   on the paragraph boundary and leaves line height alone.
10. **`shadow.offset` must be non-negative.** Negative offsets corrupt
    the file. To cast a shadow pointing up, keep `offset` positive
    and set `angle: 270`; similarly `angle: 180` points left,
    `angle: 0` (or omitted) points right. Express direction through
    the angle, never through a negative offset.

## Writing async

`pres.writeFile()` returns a Promise. Use `await` or `.then()`. A
common bug is to let the Node process exit before the write finishes;
always `await` it or handle the promise explicitly.

## Resources

- pptxgenjs docs: <https://gitbrent.github.io/PptxGenJS/>
- Source: <https://github.com/gitbrent/PptxGenJS>
- Examples for complex layouts (image grids, charts, icons) are in
  the library's own `demos/` directory.
