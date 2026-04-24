# weasyprint setup and CSS tips

`weasyprint` renders HTML + CSS to PDF without a headless browser.
That makes it fast and deterministic, but it also means it only
supports the CSS features it has implemented — no JavaScript, no
CSS animations, no web components.

## Installation

macOS:
```bash
brew install pango gdk-pixbuf libffi
pip install weasyprint
```

Debian/Ubuntu:
```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                 libfontconfig1 libcairo2 libgdk-pixbuf2.0-0
pip install weasyprint
```

If `weasyprint` fails with "cannot find library pango", set
`DYLD_LIBRARY_PATH=/opt/homebrew/lib` on Apple Silicon or
`LD_LIBRARY_PATH` on Linux.

## Page size and margins

Use `@page`:

```css
@page {
    size: letter;                  /* or A4, legal, or "8.5in 11in" */
    margin: 18mm 20mm 22mm 20mm;   /* top right bottom left */
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #6b7280;
    }
    @top-left {
        content: element(running-header);
    }
}
```

`@top-*`, `@bottom-*`, `@left-*`, `@right-*` can hold running headers
and footers. Define a named running element with
`position: running(name)` and reference it via `content: element(name)`.

## Fonts

`weasyprint` uses system fonts (via Fontconfig). To guarantee a
specific typeface:

```css
@font-face {
    font-family: "IBM Plex Sans";
    src: url("./fonts/IBMPlexSans-Regular.ttf") format("truetype");
    font-weight: 400;
}
@font-face {
    font-family: "IBM Plex Sans";
    src: url("./fonts/IBMPlexSans-Bold.ttf") format("truetype");
    font-weight: 700;
}
html { font-family: "IBM Plex Sans", sans-serif; }
```

Pass `--base-url` to `md2pdf.py` (or `HTML(base_url=...)`) so
relative URLs like `./fonts/IBMPlexSans-Regular.ttf` resolve against
the right directory.

## Page breaks

Force a break before a section:
```css
h1 { break-before: page; }
```

Prevent a table from splitting across pages:
```css
table, pre, blockquote { page-break-inside: avoid; break-inside: avoid; }
```

## Code highlighting

weasyprint has no built-in syntax highlighter. Pre-render HTML with
`pygments`:

```python
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter

snippet = highlight(code_source, PythonLexer(), HtmlFormatter())
css = HtmlFormatter(style="tango").get_style_defs(".highlight")
```

Include `css` in the stylesheet, embed `snippet` in the HTML body.

## Known quirks

- Viewport-relative units (`vw`, `vh`) do not behave intuitively —
  they resolve against page size, not screen.
- `position: fixed` is ignored; use `@page` running elements instead.
- Float layouts around images sometimes need explicit
  `shape-outside: none` to render predictably.
- Emoji support depends on the presence of a colour-emoji font
  (Noto Color Emoji is the safest bet on Linux).

## Testing a stylesheet

The fastest feedback loop is writing a minimal HTML file, running
`weasyprint file.html file.pdf`, and opening the result. Do this
before integrating with `md2pdf.py` so you don't chain two failure
modes.

## When to switch to `playwright` instead

- Your page uses flexbox/grid in ways weasyprint doesn't handle.
- The source is a React SPA that only renders after JavaScript.
- You need headers/footers from a `<template>` element referenced by
  Chrome's `page.pdf({ headerTemplate })`.

Trade-off: `playwright` pulls a 200+ MB Chromium install. Worth it
only when weasyprint genuinely cannot render your input.
