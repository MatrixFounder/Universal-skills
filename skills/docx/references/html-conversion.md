# HTML → `.docx` (`html2docx.js`)

Parallel to `md2docx.js` for inputs that arrive as HTML rather than
Markdown — typically Confluence / CMS exports. Built on the same
`docx@8.5.0` writer so output styling matches md2docx (Arial 24,
9360 DXA content width, table header shading, bullets/numbers config).

## Supported input formats

| Extension | Source | What's recovered |
|---|---|---|
| `.html` / `.htm` | Plain HTML or Chrome "Save Page As, Webpage Complete" | Inline images via the `<page>_files/` sibling directory (relative `<img src>` paths). |
| `.webarchive` | Safari "Save As, Web Archive" (Apple binary plist) | Main HTML pulled from `WebMainResource`; image sub-resources extracted to a temp dir; URLs (full + path-only) mapped to local paths. |
| `.mhtml` / `.mht` | Chrome "Save Page As, Webpage Single File" / IE / Outlook | MIME multipart/related parsed; main `text/html` part decoded (quoted-printable / base64); image parts extracted to a temp dir; URLs mapped via `Content-Location`. |

Format detection is by extension first, with a `bplist00` magic-byte
fallback for webarchives that lost their extension during download.

## Element coverage

**Block**: `<h1>`–`<h6>`, `<p>`, `<ul>`/`<ol>`/`<li>` (up to 3 nesting
levels), `<table>`/`<thead>`/`<tbody>`/`<tr>`/`<th>`/`<td>`,
`<blockquote>`, `<pre>`/`<code>`, `<hr>`, `<div>`/`<section>`/
`<article>`/`<main>`/`<header>`/`<footer>`/`<aside>`/`<nav>`
(transparent containers — children inlined).

**Inline**: `<strong>`/`<b>`, `<em>`/`<i>`, `<u>`,
`<s>`/`<strike>`/`<del>`, `<code>`, `<a href>` (external `http(s)://`
hrefs become docx hyperlinks; other hrefs become styled text), `<br>`,
`<img>` (with magic-byte fallback for extension-less Confluence assets
like `atl.site.logo`).

**Stripped**: `<script>`, `<style>`, `<head>`, `<form>`, `<input>`,
`<button>`, `<textarea>`, `<select>`, plus any element whose tag
contains a colon (Confluence's `<ac:structured-macro>` /
`<ri:user>` / etc. — warned once).

## Honest scope (v1)

- **Inline `style=""` and CSS classes are ignored** — formatting comes
  from the tag, not the stylesheet. That keeps the walker compact at
  the cost of dropping bespoke colors / fonts.
- **`rowspan` / `colspan` are dropped** — every cell stands alone.
  Documents that depend on table merges will look split.
- **Confluence `<ac:*>` macros are stripped** — info / warning / panel
  content disappears, replaced by surrounding text. The single warning
  is printed to stderr.
- **Remote `<img src="https://...">` are skipped**; the alt text (if
  present) is emitted as a fallback so the layout doesn't collapse.
- **Data-URI `<img src="data:image/...">`** — same skip-with-alt
  treatment. Future versions may decode common types.
- **Nested tables** — inside a `<td>`, one extra level is rendered;
  deeper nesting flattens to text.

## CLI

```bash
node scripts/html2docx.js \
    <input.html|.htm|.webarchive|.mhtml|.mht> \
    <output.docx> \
    [--header "page header"] \
    [--footer "page footer"] \
    [--reader-mode] \
    [--json-errors]
```

Same-path I/O (input and output resolve to the same file) → exit 6
with envelope `{"type":"SelfOverwriteRefused"}`. Missing input → exit
1 / `FileNotFound`. Argparse failures → exit 2 / `UsageError`.

`--json-errors` emits a single-line JSON envelope on stderr with
`{v:1, error, code, type, details?}` matching the cross-5 schema used
by the Python CLIs.

### `--reader-mode`

Replaces the default Confluence-priority article-root candidate list
with a curated reader-mode list ordered by specificity:

1. **High-confidence** (`#main-content`, `.wiki-content`,
   `#content .pageSection`, `#content`) — accepted at any text length.
   Diagram-heavy KB pages legitimately have very little body text; we
   trust the selector.
2. **CMS / blog classes** (`.entry`, `.post-content`,
   `.article-content`, `.main-content`, `div.article`) — require ≥500
   chars to filter out archive-page excerpts.
3. **Generic semantics** (`article`, `[role="main"]`, `main[role="main"]`,
   `main#main`) — also ≥500 chars.

Within each candidate, the LONGEST match wins — handles archive pages
with multiple `.entry` divs and Disqus-style threads where comment
`<article>`s would otherwise beat the post body.

Bare `<main>` is **deliberately omitted** in reader-mode: on news /
blog sites it commonly wraps the entire site (header + body + footer +
recommendations) so it would defeat `.entry` and reintroduce the chrome
the flag was meant to strip.

Default mode (no flag) keeps the existing Confluence-priority
first-match behaviour for backward compatibility.

## Module layout

- `scripts/html2docx.js` — CLI entry: argv parsing, error envelope,
  same-path guard, format dispatch, document assembly, packing.
- `scripts/_html2docx_archive.js` — `.webarchive` (bplist) and
  `.mhtml` (MIME multipart) extractors. Owns the
  `extractedImages: Map<url, localPath>` populated from each bundle
  and consumed by the walker.
- `scripts/_html2docx_walker.js` — cheerio DOM → docx-js block tree.
  Self-contained: takes `{ $, root, inputDir, extractedImages }` and
  returns `{ children, numberedListConfigs }`.
- `scripts/_html2docx_svg_render.js` — two-tier SVG → PNG rasterizer
  (see next section).

The split makes each file independently understandable and lets the
archive parsers + SVG rasterizer be unit-tested without instantiating
the whole walker.

## SVG rendering (drawio / mermaid / hand-drawn `<svg>`)

`_html2docx_svg_render.js` runs every inline SVG through one of two
rasterizers and embeds the resulting PNG into the docx:

| Tier | What | When | Quality |
|---|---|---|---|
| 1 | `chrome --headless --screenshot` via `spawnSync` | a Chromium-family browser is found on the host | 100% — real CSS layout, foreignObject + word-wrap render exactly like in the source page |
| 2 | `@resvg/resvg-js` (Rust, pre-built binary) + walker-side preprocessing (xlink namespace, named-entity decode, `<foreignObject>`→`<text>` conversion with drawio centring math + word-wrap, viewBox synthesis with 5% expansion for canvas-clipped diagrams, CSS `light-dark()` / `var()` resolution) | Tier 1 unavailable | ~95% — drawio Confluence diagrams render with all swim-lanes visible and labels word-wrapped to fit their boxes; nested rich-HTML labels (mixed-font runs, embedded lists) still flatten to plain text per line |

### Tier-2 drawio fixups (`_html2docx_walker.js`)

Tier 2 cannot run CSS layout, so the walker pre-processes every drawio
inline SVG before handing it to resvg:

- **`_ensureViewBox(svg, naturalW, naturalH, trustDims)`** — adds a viewBox
  to drawio Confluence SVGs that omit it (`style="width:100%; height:100%;
  min-width:Wpx; min-height:Hpx"`). Without a viewBox, content beyond the
  natural pixel canvas clips. The synthesised viewBox is expanded by 5% in
  both axes to absorb drawio's right/bottom-edge overshoot artifact.
  Self-closing `<svg ... />` tags preserve their `/>` form. Skipped for
  small SVGs (≤200px) — typically inline icons. Skipped on the
  `_svgDimensions` `{600,400}` fallback sentinel where natural dims are
  unknown — synthesising from fictional dims would crop the SVG.
- **`_drawioForeignObjectsToText` centring** — drawio's flex encoding puts
  `margin-left` at the LEFT EDGE of the label container and the actual
  visual anchor at `left + width/2` for `justify-content:center`. Using
  `margin-left` directly with `text-anchor=middle` would centre every label
  at its container's left edge.
- **Word-wrap (`wrapText`)** — long single-span labels without explicit
  `<br>` are split into multiple `<tspan>` rows so they fit inside the
  shape. Char-width is approximated as `fontSize × 0.62` for Cyrillic and
  `× 0.55` for Latin (Cyrillic glyphs are visibly wider in Helvetica/Arial).
  Skipped when `width:1px` (drawio's unconstrained-width marker).

### Browser detection

On first SVG, the renderer probes in this order and caches the result:

1. `$HTML2DOCX_BROWSER` environment variable (explicit override).
2. Conventional install paths for the OS (`/Applications/Google Chrome.app/...` on macOS; `C:\Program Files\Google\Chrome\Application\chrome.exe` on Windows).
3. PATH search via `which` / `where` for `google-chrome`,
   `chromium`, `chromium-browser`, `chrome`, `microsoft-edge`,
   `brave-browser`, plus their Windows counterparts.
4. `puppeteer.executablePath()` — picked up automatically if a project
   happens to have `puppeteer` installed (no hard dep added by html2docx).

Found path is logged once at start (`html2docx: SVG renderer = headless
Chrome (...)`); without it, a warning suggests installing one or
setting `HTML2DOCX_BROWSER`.

### Forcing a specific tier

- `HTML2DOCX_BROWSER=""` — empty string disables Tier 1 even if Chrome
  is on PATH (useful for benchmarking the resvg fallback).
- `HTML2DOCX_BROWSER=/abs/path/to/chrome` — pin to a specific binary;
  useful in CI where multiple Chromium variants exist.

### Forced-fallback behaviour

If Tier 1 is selected but Chrome exits non-zero (sandbox failure,
truncated SVG, etc.), the renderer logs the failure and re-runs the
SVG through Tier 2 transparently. The pipeline never aborts on render
failure — at worst, the diagram becomes a plain text-labelled
geometry render and conversion still succeeds.

## Examples

Round-trip the bundled fixture:

```bash
cd skills/docx/scripts
node html2docx.js ../examples/fixture-simple.html /tmp/out.docx
python3 -m office.validate /tmp/out.docx
node docx2md.js /tmp/out.docx /tmp/back.md
```

Convert a Safari webarchive (the temp dir for extracted assets is
printed on stderr; remove it after you're done if it bothers you):

```bash
node html2docx.js page.webarchive page.docx
# html2docx: extracted 22 image sub-resource(s) from .webarchive to
# /var/folders/.../html2docx-webarchive-XXXXXX
```

Convert a Chrome MHTML with header/footer:

```bash
node html2docx.js page.mhtml page.docx \
    --header "Confidential" --footer "Internal use only"
```
