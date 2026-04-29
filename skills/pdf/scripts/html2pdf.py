#!/usr/bin/env python3
"""Render a web page or HTML document to a typeset PDF via weasyprint.

Supported input formats:

  .html / .htm    — standard HTML file with optional sibling assets.
  .mhtml / .mht   — MIME HTML archive (browser "Save as → Webpage, Single File").
  .webarchive     — Apple WebKit archive (Safari "Save as → Web Archive").

Parallel of `md2pdf.py` for HTML inputs — common for BI-dashboard
exports, Confluence pages, pre-rendered reports, and saved web pages.
Reuses md2pdf's `DEFAULT_CSS` so an unstyled `<h1>…<p>` renders the
same as Markdown output; embedded `<style>` blocks cascade after the
weasyprint stylesheet and naturally override defaults.

Usage:
    python3 html2pdf.py INPUT OUTPUT.pdf
        [--page-size letter|a4|legal] [--css EXTRA.css]
        [--base-url DIR] [--no-default-css] [--reader-mode]

For .mhtml and .webarchive inputs, sub-resources (images, CSS, fonts)
are extracted to a temporary directory that is removed after conversion.
`--base-url` is still accepted and overrides the automatic base for
plain .html inputs; it is ignored for archive formats (the extracted
temp dir always serves as the base).

`--no-default-css` skips the bundled stylesheet for HTML that ships
its own complete styling (BI dashboards, branded reports). The
`--css EXTRA.css` flag is independent and stacks regardless.
Structural normalisation CSS (_NORMALIZE_CSS) is always injected
regardless of `--no-default-css` — it fixes layout bugs, not
visual styling.

`--reader-mode` extracts the main article content (first <article>,
<main>, or known content container) and renders it with only the
bundled clean CSS — strips navigation, ads, and sidebars.

Pre-render preprocessing handles real-world compatibility issues
automatically (no flags needed):

  - draw.io / Confluence inline SVG diagrams: foreignObject labels are
    converted to SVG <text> elements (weasyprint discards foreignObject
    content), and oversized diagrams get a synthesised viewBox so they
    scale to fit the page instead of being clipped.
  - CSS light-dark() is resolved to the light variant (weasyprint does
    not implement CSS Color Level 5).
  - Web-font @font-face declarations are stripped; system fonts are used
    instead to avoid garbled glyphs from CDN-subsetted fonts.

Same-path I/O (input == output, including via symlink) is refused
with exit 6 / SelfOverwriteRefused.
"""
from __future__ import annotations

import argparse
import email
import email.policy
import html as html_module
import os
import plistlib
import re
import shutil
import signal
import sys
import tempfile
import urllib.parse
from pathlib import Path

from weasyprint import CSS, HTML, default_url_fetcher  # type: ignore

# Reuse md2pdf's CSS + page-size constants — keeps the two CLIs
# visually consistent without duplicating ~85 lines of CSS that
# would silently drift. md2pdf imports markdown2 at module load,
# a small one-time cost; no behavioural side effects.
from md2pdf import DEFAULT_CSS, PAGE_SIZES

from _errors import add_json_errors_argument, report_error

SUPPORTED_EXTENSIONS = (".html", ".htm", ".mhtml", ".mht", ".webarchive")

# ── print normalization CSS (injected into every page) ────────────────────────
_NORMALIZE_CSS = """\
<style id="html2pdf-normalize">
/* ── 1. Body / overflow: SPA pages cap body height to 100vh and set
        overflow:clip which makes weasyprint see only 1 page of content. */
html, body {
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
    overflow-clip-margin: unset !important;
}

/* ── 2. Confluence / draw.io diagrams + all viewBox SVGs: scale to fit page
        width and prevent edge clipping.
        .drawio-macro is the Confluence draw.io container. Its inline style
        carries fixed pixel width/height; we reset both so the SVG inside
        drives the layout via its viewBox aspect ratio (_fix_svg_viewport adds
        viewBox to SVGs that lack one). overflow:visible prevents the
        container from clipping labels that slightly overshoot the canvas.
        svg[viewBox] catches all other diagram SVGs (Mermaid, PlantUML, etc.)
        regardless of their wrapper element or Confluence version. */
.drawio-macro {
    overflow: visible !important;
    max-width: 100% !important;
    height: auto !important;
}
.drawio-macro svg,
svg[viewBox] {
    min-width: 0 !important;
    max-width: 100% !important;
    height: auto !important;
    overflow: visible !important;
}

/* ── 3. Hide application chrome that is useless / harmful in PDF:
        site-level headers, nav bars, sidebars, action buttons, cookie
        banners, ads. Use EXACT class-token selectors only — [class*=…]
        wildcards are dangerous (e.g. tm-page__main_has-sidebar contains
        "sidebar" but is the main content wrapper on Habr). */
/* Atlassian / Confluence chrome */
.aui-header, #header, #header-menu, #app-switcher,
#footer, .footer,
#sidebar, .aui-sidebar, #left-navigation, .left-navigation,
#helpSection, #help-section,
.page-menu, .page-restrictions-link,
.noprint, .no-print,
/* Habr (Хабр) right sidebar */
.tm-page__sidebar,
/* vc.ru left nav + right sidebar (exact class tokens) */
.aside--left, .sidebar, .aside,
/* vc.ru site-level header and navigation bars */
.header, .supbar, .bar--top,
/* Yandex AI advertising banner embedded in vc.ru pages */
.ya-ai__container,
/* Generic print-suppressed widgets */
.sticky-sidebar, .widget-area,
/* Generic site navigation bars: hide entirely rather than position:static
   so they don't consume vertical space in the PDF. */
header, nav, .navbar, .topbar, .top-bar,
.sticky-header, .fixed-header, #top-bar {
    display: none !important;
}

/* ── 4. Some elements use position:fixed/sticky but are NOT navigation
        (e.g. breadcrumb rows, Confluence page header rows). Reset
        position so they sit in normal document flow instead of
        overlapping content. */
[style*="position:fixed"], [style*="position: fixed"],
[style*="position:sticky"], [style*="position: sticky"] {
    position: static !important;
    top: auto !important;
}

/* ── 5. Collapse multi-column article layouts to single column.
        SPA pages (vc.ru, Habr) use flex/grid to place an author card
        to the left of the article body. In print this creates a narrow
        content column squeezed by the author panel.
        We reset the top-level flex to block so children stack vertically.
        This only affects the outermost layout wrapper, not inline flex
        elements inside the article body. */
/* vc.ru: .entry > .content is the flex row with author card (left) + article (right) */
.entry > .content,
.content-header, .content-wrapper, .post-header, .entry-header,
[class="layout"], [class="layout__content"] {
    display: block !important;
    width: 100% !important;
}

/* ── 6. Prevent images and root SVGs from bleeding past the page margin. */
img, video, canvas {
    max-width: 100% !important;
    height: auto !important;
}

/* ── 7a. Code block styling (markdown-preview parity).
        Modern docs sites (Mintlify, MkDocs, Docusaurus) wrap code blocks in
        nested div trees with shiki/prism inline styles. After our preprocessing
        strips external CSS and unwraps buttons, the bare <pre> is left. Apply
        a minimal markdown-preview look: light grey background, thin border,
        rounded corners, monospace inheritance, scoped padding. */
pre {
    background: #f6f8fa !important;
    border: 1px solid #e1e4e8 !important;
    border-radius: 6px !important;
    padding: 12px 16px !important;
    margin: 12px 0 !important;
    /* white-space: pre-wrap + word-break: break-word makes long source lines
       wrap to the next line at the page-width boundary instead of being clipped
       past the right margin. PDFs can't scroll, so `overflow-x: auto` (the
       browser default) silently drops content past the box. We preserve all
       leading indentation via `pre-wrap` and break only at word/symbol
       boundaries — keeps the visual indentation of nested code intact while
       making sure no line goes past the page edge. */
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace !important;
    font-size: 0.85em !important;
    line-height: 1.45 !important;
}
pre code {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    font-size: inherit !important;
    color: inherit !important;
    white-space: inherit !important;
}
:not(pre) > code {
    background: #f6f8fa !important;
    border-radius: 3px !important;
    padding: 0.2em 0.4em !important;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace !important;
    font-size: 0.9em !important;
}

/* ── 7b. Blockquote styling (markdown-preview parity). GitHub-style left
        border + grey text. */
blockquote {
    border-left: 4px solid #dfe2e5 !important;
    padding: 0 1em !important;
    color: #6a737d !important;
    margin: 12px 0 !important;
}

/* ── 7c. ARIA-role tables. GitBook (and some Notion / Material themes) build
        their data tables out of <div role="table">/<div role="row">/
        <div role="cell"> markup instead of native <table>. After the site
        CSS is stripped, those divs collapse to vertical block flow — every
        cell on its own line — making 3-column field tables (Name / Type /
        Description) impossible to read. Render the ARIA-table tree as a
        real CSS table; the W3C ARIA spec says these roles MUST be visually
        equivalent to a <table>, so we honour that universally. */
[role="table"] {
    display: table !important;
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 8px 0 !important;
}
[role="rowgroup"] { display: table-row-group !important; }
[role="row"]      { display: table-row !important; }
[role="columnheader"], [role="cell"] {
    display: table-cell !important;
    padding: 6px 10px !important;
    border: 1px solid #e1e4e8 !important;
    vertical-align: top !important;
}
[role="columnheader"] {
    font-weight: 600 !important;
    background: #f6f8fa !important;
    text-align: left !important;
}

/* ── 7. Hide site-injected anchor / "copy heading link" buttons next to
        headings. Confluence injects <button class="copy-heading-link-button">,
        Sphinx/MkDocs use .headerlink, GitHub uses .anchor / .octicon-link.
        Browsers normally style these as tiny icon buttons via the site CSS;
        when reader-mode strips <link rel=stylesheet>, the default <button>
        styling renders them as visible grey rounded rectangles next to every
        heading. Same logic for Confluence's anchor-toggle buttons inside
        headings, and the print-suppress-by-class convention used by many
        wikis. */
.copy-heading-link-container, .copy-heading-link-button,
.headerlink, .anchor-link, a.anchor, .octicon-link,
.heading-anchor, button.anchorjs-link,
h1 button, h2 button, h3 button, h4 button, h5 button, h6 button {
    display: none !important;
}
</style>
"""


# ── HTML preprocessing ────────────────────────────────────────────────────────

def _fix_light_dark(html: str) -> str:
    """Replace CSS light-dark(light, dark) with the light colour.

    weasyprint does not implement CSS Color Level 5, so every use of
    light-dark() renders as transparent/black. We scan linearly, tracking
    parenthesis depth, to handle nested functions like
    `light-dark(rgb(0,0,0), var(--c, #1d2125))` correctly.
    """
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"light-dark\(", html):
        out.append(html[pos : m.start()])
        start = m.end()
        depth = 1
        j = start
        first_comma = -1
        while j < len(html) and depth > 0:
            c = html[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            elif c == "," and depth == 1 and first_comma == -1:
                first_comma = j
            j += 1
        if first_comma != -1 and depth == 0:
            out.append(html[start:first_comma].strip())
            pos = j + 1          # skip past closing )
        else:
            out.append("light-dark(")  # leave untouched if malformed
            pos = m.end()
    out.append(html[pos:])
    return "".join(out)


def _strip_all_fontfaces(css: str) -> str:
    """Remove all @font-face blocks from CSS.

    Web fonts served from CDN are often subset with remapped glyph
    indices, and the URL hashes in the webarchive's font-face declarations
    rarely match the actual woff2 files captured as subresources. weasyprint
    falls back to fetching from CDN and may receive the wrong subset —
    producing garbled Latin text (e.g. "SMlc Та St Та" for "Claude Code").
    Stripping all @font-face blocks forces weasyprint to use system fonts
    (Helvetica/Arial/Liberation) which have correct, stable glyph mappings.
    """
    return re.sub(
        r"@font-face\s*\{[^}]*\}",
        "",
        css,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_all_fontfaces_in_styles(html: str) -> str:
    """Apply _strip_all_fontfaces to every <style> block in the HTML."""
    def _fix_style(m: re.Match) -> str:
        tag, content, close = m.group(1), m.group(2), m.group(3)
        return tag + _strip_all_fontfaces(content) + close

    return re.sub(
        r"(<style[^>]*>)(.*?)(</style>)",
        _fix_style,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _fo_to_svg_text(html: str) -> str:
    """Convert draw.io <foreignObject> text labels to SVG <text> elements.

    weasyprint silently discards <foreignObject> content.  draw.io stores ALL
    node labels inside <foreignObject> divs using a flex-box encoding:

      padding-top  → absolute y-centre of the shape in the current SVG
                     coordinate space (inside the enclosing <g> transform)
      margin-left  → LEFT EDGE of the text container div (always); the actual
                     SVG text-anchor x is derived as:
                       center   → margin_left + container_width / 2
                       flex-end → margin_left + container_width
                       flex-start → margin_left
      width        → text-container width for word-wrap (draw.io uses 1px for
                     unconstrained / content-sized labels)
      font-size    → LAST occurrence in the foreignObject (the outermost div
                     often carries a layout/spacing size; the innermost span
                     carries the actual label size)

    Multiple <text> elements are emitted for labels that need word-wrapping
    (container width > 1 px), each vertically centred as a block around y.
    """
    def _wrap(text: str, max_width: float, font_size: int) -> list[str]:
        if max_width <= 1:
            return [text]
        char_w = font_size * 0.58       # empirical Helvetica avg char width
        max_chars = max(5, int(max_width / char_w))
        words = text.split()
        lines: list[str] = []
        current = ""
        for w in words:
            trial = (current + " " + w).strip()
            if len(trial) <= max_chars:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines or [text]

    def _replace(m: re.Match) -> str:
        fo = m.group(0)
        raw = re.sub(r"<[^>]+>", " ", fo)
        text = html_module.unescape(" ".join(raw.split())).replace("\xa0", " ")
        if not text:
            return ""

        # Independent searches — don't assume CSS property order in the DOM.
        pt_m = re.search(r"padding-top:\s*([\d.]+)px", fo)
        ml_m = re.search(r"margin-left:\s*([\d.]+)px", fo)
        if not pt_m or not ml_m:
            return ""
        y = float(pt_m.group(1))
        x_left = float(ml_m.group(1))  # margin-left = left edge of container div

        # Container width — needed for both word-wrap and x-anchor calculation.
        w_m = re.search(r"width:\s*([\d.]+)px", fo)
        cw = float(w_m.group(1)) if w_m else 0

        # SVG text-anchor and x position mirror the flex justify-content.
        # margin-left is always the LEFT EDGE; shift x to the actual anchor.
        jc_m = re.search(
            r"justify-content:\s*(?:unsafe\s+)?(flex-start|flex-end|center)", fo,
        )
        jc = jc_m.group(1) if jc_m else "center"
        if jc == "center":
            x, anchor = x_left + cw / 2, "middle"
        elif jc == "flex-end":
            x, anchor = x_left + cw, "end"
        else:  # flex-start
            x, anchor = x_left, "start"

        # Use the LAST (innermost) font-size; the outer div may carry a smaller
        # layout/spacing size that does not match the visible label.
        all_fs = re.findall(r"font-size:\s*([\d.]+)px", fo)
        fs = round(float(all_fs[-1])) if all_fs else 12
        bold = (' font-weight="bold"'
                if re.search(r'font-weight\s*:\s*(bold|[6-9]\d{2}|bolder)', fo, re.IGNORECASE)
                or re.search(r"<b[\s>]|<strong[\s>]", fo) else "")

        lines = _wrap(text, cw, fs)
        lh = fs * 1.25
        start_y = y - (len(lines) - 1) * lh / 2

        out = []
        for j, line in enumerate(lines):
            ly = start_y + j * lh
            out.append(
                f'<text x="{x:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                f'dominant-baseline="middle" font-family="Helvetica" '
                f'font-size="{fs}"{bold} fill="#000000">'
                f"{html_module.escape(line)}</text>"
            )
        return "\n".join(out)

    return re.sub(
        r"<foreignObject[^>]*>.*?</foreignObject>",
        _replace,
        html,
        flags=re.DOTALL,
    )


def _fix_svg_viewport(html: str) -> str:
    """Make large inline SVGs responsive by ensuring they carry a viewBox.

    Two cases:

    Case 1 — SVG with explicit pixel ``width`` attribute and an existing
    ``viewBox``:  set ``width="100%"``, remove ``height``, expand the viewBox
    by 5 % in both dimensions so that content marginally overshooting the
    declared canvas right/bottom boundary (a draw.io artefact) is not clipped.

    Case 2 — draw.io Confluence pattern: the SVG has NO ``viewBox`` and uses
    ``style="width:100%; height:100%; min-width:Wpx; min-height:Hpx;"``
    inside a fixed-pixel-size container div.  Without a viewBox,
    ``max-width:100%`` just creates a smaller viewport into the same 1:1
    coordinate space — content beyond the viewport is clipped.  We synthesise
    ``viewBox="0 0 W H"`` from those style values; combined with the CSS rules
    for ``.drawio-macro svg`` (``min-width:0; height:auto``), this makes the
    SVG scale proportionally to the page content width.

    Small inline icons (width ≤ 200 px, or min-width ≤ 200 px) are left
    untouched.
    """
    _VB_EXPAND = 1.05

    def _expand(vb_inner: str) -> str:
        parts = vb_inner.split()
        if len(parts) != 4:
            return vb_inner
        try:
            x, y, w, h = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
            return f"{x} {y} {w * _VB_EXPAND:.1f} {h * _VB_EXPAND:.1f}"
        except ValueError:
            return vb_inner

    def _patch(m: re.Match) -> str:
        tag = m.group(0)

        # ── Case 1: explicit pixel width attribute + existing viewBox ──────────
        w_attr_m = re.search(r'\bwidth\s*=\s*["\']?([\d.]+)["\']?', tag)
        vb_found = None
        for vb_pat in (r'\bviewBox\s*=\s*"([^"]+)"', r"\bviewBox\s*=\s*'([^']+)'"):
            vb_found = re.search(vb_pat, tag, re.IGNORECASE)
            if vb_found:
                break

        if w_attr_m and float(w_attr_m.group(1)) > 200 and vb_found:
            new_inner = _expand(vb_found.group(1))
            tag = tag[: vb_found.start(1)] + new_inner + tag[vb_found.end(1):]
            tag = re.sub(
                r'\bwidth\s*=\s*["\']?[^"\'>\s]+["\']?', 'width="100%"', tag, count=1,
            )
            tag = re.sub(r'\bheight\s*=\s*["\']?[\d.%]+["\']?', '', tag, count=1)
            return tag

        # ── Case 2: no viewBox — draw.io Confluence inline-SVG pattern ────────
        # The SVG carries its natural pixel size in min-width/min-height
        # inline-style values.  Synthesise a viewBox from those so the CSS
        # height:auto rule can derive the correct aspect ratio.
        if vb_found:
            return tag  # already has viewBox, nothing to synthesise
        style_m = re.search(r'\bstyle\s*=\s*"([^"]*)"', tag)
        if not style_m:
            return tag
        style = style_m.group(1)
        mw_m = re.search(r'\bmin-width\s*:\s*([\d.]+)px', style)
        mh_m = re.search(r'\bmin-height\s*:\s*([\d.]+)px', style)
        if not mw_m or not mh_m:
            return tag
        mw, mh = float(mw_m.group(1)), float(mh_m.group(1))
        if mw <= 200:
            return tag
        new_vb = f'viewBox="0 0 {mw * _VB_EXPAND:.1f} {mh * _VB_EXPAND:.1f}"'
        # Handle both `>` and `/>` closing forms (XHTML/XML SVGs).
        if tag.endswith("/>"):
            return tag[:-2] + f' {new_vb}>'
        return tag[:-1] + f' {new_vb}>'

    return re.sub(r'<svg\b[^>]*>', _patch, html, flags=re.IGNORECASE | re.DOTALL)


# Universal ad-block class substrings, matched against the `class=` attribute
# of any element. Removed in BOTH regular and reader modes — ads are never
# legitimate content on any site, and they otherwise consume the first PDF
# page (e.g. Хабр's ".tm-header-banner" + ".adfox-banner-placeholder" stack
# pushes the article body to page 2).
#
# Patterns are deliberately conservative substrings of well-known ad-network
# / sponsor markers that have no legitimate semantic-content overlap:
#   * adfox — Yandex AdFox
#   * googletag, gpt-ad — Google Publisher Tag
#   * taboola, outbrain — recommendation networks
#   * sponsor-mark, sponsor-block, sponsored- — explicit sponsor labels
#   * adfox-banner, banner-target, banner-slider, banner-container — Хабр-style
#     banner wrappers (compound classes; bare "banner" alone is too generic
#     and would match e.g. `.user-banner` profile pictures)
_AD_STRIP_KEYWORDS: list[str] = [
    "adfox", "googletag", "gpt-ad", "taboola", "outbrain",
    "sponsor-mark", "sponsor-block", "sponsored-",
    "adfox-banner", "banner-target", "banner-slider",
    "banner-container", "banner-placeholder", "header-banner",
    "tm-header-banner", "tm-banner",
    "ya-ai",
]


def _strip_universal_ads(html: str) -> str:
    """Remove ad-network / sponsor wrappers from HTML in-place.

    Reuses the same outermost-only depth-tracked stripping logic as
    `_strip_reader_widgets` but with an ad-specific keyword list. Applied
    unconditionally in `_preprocess_html`, before reader-mode root extraction
    and before weasyprint render — keeps ads from pushing real content off
    the first page in regular mode.
    """
    matches = _find_all_elements(html, class_substring_any=_AD_STRIP_KEYWORDS)
    if not matches:
        return html
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    out = html
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def _strip_external_stylesheets(html: str) -> str:
    """Remove `<link rel="stylesheet">` references — universal compatibility fix.

    Site-shipped CSS is the leading cause of weasyprint rendering bugs in
    real-world inputs:
      * Хабр's main stylesheet contains a layout rule that makes weasyprint
        silently drop the 4th `<p>` in `.article-formatted-body` (paragraphs
        after a tall figure go missing — confirmed by bisection).
      * vc.ru's deeply-nested flex/grid CSS sends weasyprint's layout engine
        into multi-minute CPU loops on otherwise-modest HTML (~330 KB).
      * Many sites ship `@font-face` declarations with CDN-subset glyph maps
        that don't match the woff2 files captured in the webarchive,
        producing garbled Latin text.
    Stripping `<link rel=stylesheet>` lets weasyprint render with only:
      * The bundled DEFAULT_CSS (typography),
      * Our _NORMALIZE_CSS (chrome strip),
      * Inline `<style>` blocks (structural styles like table layout, which
        usually work fine — Confluence's content survives intact).
    Tested across Confluence, Хабр, vc.ru, mobile-review, generic blogs:
    output is more consistent, faster, and content-complete.
    """
    # `<link rel="stylesheet" href="...">` and the lazy-loaded variant
    # `<link rel="preload" as="style">` (often used to defer-load same file).
    html = re.sub(
        r'<link\b[^>]*\brel\s*=\s*["\']?(?:stylesheet|preload)["\']?[^>]*/?>',
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Defensive: also catch `<link href="*.css">` without explicit rel=
    # (rare but seen on some legacy templates).
    html = re.sub(
        r'<link\b(?=[^>]*\.css)[^>]*/?>',
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html


# Threshold for "icon-sized" SVGs. Real diagrams (drawio, mermaid, plant-UML)
# always exceed this; UI icons (anchor links, copy buttons, AI sparkles,
# expand/collapse arrows, callout markers) almost never do.
_ICON_SVG_MAX_PX = 64


def _strip_icon_svgs(html: str) -> str:
    """Remove small decorative `<svg>` elements (UI icons), keep large diagrams.

    Modern docs sites (Mintlify, MkDocs Material, Docusaurus, Anthropic docs)
    inject inline `<svg>` icons everywhere: anchor-link icons next to headings,
    copy-to-clipboard buttons on code blocks, "AI explain" sparkles, callout
    markers (info/warn/note), expand/collapse arrows. Without site CSS to
    position and size them, weasyprint renders each on its own line as a
    visible glyph, scattering the layout.

    A real content SVG (architecture diagram, flow chart) is at least a few
    hundred pixels per side. UI icons are 16/24/32 px. Strip only icons whose
    declared `width` AND `height` (in pixels) are both ≤ _ICON_SVG_MAX_PX.

    SVGs without explicit pixel dimensions (style-only sizing or 100%) are
    KEPT — they may be content. The trade-off is conservative; we'd rather
    leave a few decorative icons than drop a legitimate diagram.
    """
    # Tailwind size utility classes that map to ≤ 64 px:
    # h-1=4, h-2=8, h-3=12, h-4=16, h-5=20, h-6=24, h-7=28, h-8=32, h-10=40,
    # h-12=48, h-14=56, h-16=64. Same for w-* width and size-* (sets BOTH
    # width and height to the given size). `size-5` is the standard Mintlify
    # icon size — appears in Discord/Berachain "Info" callouts.
    _tw_icon_re = re.compile(
        r'\bclass\s*=\s*["\'][^"\']*\b(?:[hw]-|size-)(?:[1-9]|1[0-6])\b',
        re.IGNORECASE,
    )

    def _is_icon(svg_open_tag: str) -> bool:
        # `aria-hidden="true"` is the W3C-standard marker for decorative
        # content. Combined with `<svg>` it's a universal "this is an icon"
        # signal — Font Awesome, Heroicons, Phosphor, Lucide, custom site
        # icon sprites all set it. Real diagrams omit aria-hidden (they
        # have semantic content). Catches OpenRouter / Mintlify icons that
        # have no explicit pixel dimensions and would otherwise render at
        # full viewBox size (page-filling).
        if re.search(r'\baria-hidden\s*=\s*["\']?true', svg_open_tag, re.IGNORECASE):
            return True
        # Font Awesome prefix attribute (`prefix="far"`, `"fas"`, `"fab"`,
        # `"fal"`, `"fa"`, `"fak"`, `"fad"`). These are always icons.
        if re.search(r'\bprefix\s*=\s*["\']f[arsblkd]+["\']', svg_open_tag, re.IGNORECASE):
            return True
        # Numeric width/height attrs (px or unit-less). Match if EITHER axis
        # is small — UI icons frequently constrain only one dimension and
        # let the other derive from `viewBox` aspect ratio (e.g. Mintlify
        # anchor links: `<svg height="12px" viewBox="0 0 576 512">`).
        # Content diagrams typically declare both dimensions at full size.
        wm = re.search(r'\bwidth\s*=\s*["\']?(\d+)(?:px)?\b', svg_open_tag)
        hm = re.search(r'\bheight\s*=\s*["\']?(\d+)(?:px)?\b', svg_open_tag)
        for m in (wm, hm):
            if m:
                try:
                    if int(m.group(1)) <= _ICON_SVG_MAX_PX:
                        return True
                except ValueError:
                    pass
        # Tailwind/utility class with h-/w- size token ≤ 16 (= 64 px).
        if _tw_icon_re.search(svg_open_tag):
            return True
        # Inline style with small width/height (px or em).
        sm = re.search(r'\bstyle\s*=\s*["\']([^"\']*)["\']', svg_open_tag)
        if sm:
            style = sm.group(1)
            sw = re.search(r'\bwidth\s*:\s*(\d+(?:\.\d+)?)\s*(?:px|em|rem)?', style)
            sh = re.search(r'\bheight\s*:\s*(\d+(?:\.\d+)?)\s*(?:px|em|rem)?', style)
            if sw and sh:
                try:
                    if float(sw.group(1)) <= _ICON_SVG_MAX_PX and float(sh.group(1)) <= _ICON_SVG_MAX_PX:
                        return True
                except ValueError:
                    pass
        # Final fallback: small viewBox (no explicit dimensions, no recognizable
        # icon class). Mintlify "info" callouts ship as
        # `<svg viewBox="0 0 20 20" class="..." aria-label="Info">` where
        # `aria-label` (semantic content!) is not the W3C decorative marker.
        # Such SVGs without explicit pixel dims default to 100% of the
        # containing block, painting page-filling glyphs in PDF. A viewBox
        # whose max dimension is ≤ 64 px is iconographic per design (real
        # diagrams have viewBox 0 0 600 400 or similar).
        vbm = re.search(r'\bviewBox\s*=\s*["\'][^"\']*["\']', svg_open_tag)
        if vbm:
            parts = re.findall(r'-?\d+(?:\.\d+)?', vbm.group(0))
            if len(parts) == 4:
                try:
                    w, h = float(parts[2]), float(parts[3])
                    # Has no explicit dims (we're past the numeric / Tailwind
                    # / inline-style checks) and a small viewBox — icon.
                    if max(w, h) <= _ICON_SVG_MAX_PX:
                        return True
                except ValueError:
                    pass
        return False

    # Match `<svg ...>...</svg>` with depth-tracked end (SVGs can nest).
    out: list[str] = []
    pos = 0
    open_re = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
    close_re = re.compile(r"</svg\s*>", re.IGNORECASE)
    while True:
        m = open_re.search(html, pos)
        if not m:
            out.append(html[pos:])
            break
        out.append(html[pos:m.start()])
        # Find matching </svg> with depth tracking.
        depth = 1
        scan = m.end()
        while depth > 0 and scan < len(html):
            o = open_re.search(html, scan)
            c = close_re.search(html, scan)
            if c is None:
                break
            if o is not None and o.start() < c.start():
                depth += 1
                scan = o.end()
            else:
                depth -= 1
                scan = c.end()
        if depth != 0:
            out.append(html[m.start():])
            break
        if _is_icon(m.group(0)):
            pass  # drop entire SVG
        else:
            out.append(html[m.start():scan])
        pos = scan
    return "".join(out)


def _flatten_table_code_blocks(html: str) -> str:
    """Convert table-based syntax-highlighting blocks to plain `<pre><code>`.

    Fern, Mintlify, GitBook, MkDocs Material, and many docs platforms render
    code with line numbers as a `<pre><table><tr class="code-block-line">`
    structure (one row per source line, gutter `<td>` for line number,
    content `<td>` for code). weasyprint mishandles `<table>` inside `<pre>`
    when the table needs to paginate: subsequent block siblings interleave
    horizontally with mid-table rows, producing scrambled output (lines 16+
    of a code block end up mixed with the next paragraph).

    Detect these patterns by `<tr>` with `class*="code-block-line"` (Fern /
    Mintlify), `class*="line"` inside `<table class*="highlight">` (Pygments),
    or `class*="hl-row"` (Docusaurus). Extract the line content cell from
    each row, join with `\\n`, and emit a clean `<pre><code>line1\\nline2\\n
    ...</code></pre>` that paginates cleanly via the bundled `_NORMALIZE_CSS`.
    """
    # Match a <table> wrapper that's an obvious code-block table:
    # contains <tr class="*code-block-line*"> or similar markers.
    table_re = re.compile(
        r'<table\b[^>]*>(.*?)</table>',
        re.DOTALL | re.IGNORECASE,
    )

    def _is_code_table(inner: str) -> bool:
        if 'code-block-line' in inner:        # Fern, Mintlify
            return True
        if 'class="line"' in inner and 'highlight' in inner:  # Pygments
            return True
        if 'hl-row' in inner:                  # Docusaurus
            return True
        return False

    # Per-row extractor: prefer the *content* cell (skips line-number gutter).
    line_re = re.compile(
        r'<tr\b[^>]*\bclass="[^"]*(?:code-block-line|hl-row|line)[^"]*"[^>]*>(.*?)</tr>',
        re.DOTALL | re.IGNORECASE,
    )
    content_cell_re = re.compile(
        r'<td\b[^>]*\bclass="[^"]*(?:code-block-line-content|hl-content|content)[^"]*"[^>]*>(.*?)</td>',
        re.DOTALL | re.IGNORECASE,
    )

    def _replace_table(m: re.Match) -> str:
        inner = m.group(1)
        if not _is_code_table(inner):
            return m.group(0)
        lines: list[str] = []
        for row in line_re.finditer(inner):
            row_html = row.group(1)
            cell = content_cell_re.search(row_html)
            text_html = cell.group(1) if cell else row_html
            # Collapse any inner <span class="line">…</span> to plain text;
            # strip ALL tags for clean monospace rendering. weasyprint can't
            # paginate complex nested span styling reliably across pages
            # — better to flatten than risk another interleaving bug.
            text = re.sub(r'<[^>]+>', '', text_html)
            # html_module.unescape() converts &lt; / &amp; / &nbsp; back to
            # literal characters so the <pre> shows the actual source code.
            text = html_module.unescape(text).replace('\xa0', ' ')
            # Trim trailing whitespace; preserve leading indentation.
            lines.append(text.rstrip())
        if not lines:
            return m.group(0)
        # Use html_module.escape() to re-escape for embedding in <pre>:
        # only `<`, `>`, `&` need escaping; whitespace including newlines
        # is preserved by <pre>.
        body = html_module.escape('\n'.join(lines), quote=False)
        return f'<pre><code>{body}</code></pre>'

    return table_re.sub(_replace_table, html)


def _strip_empty_anchor_links(html: str) -> str:
    """Remove `<a href="#...">…</a>` whose visible content is empty after icon strip.

    Modern docs sites (Mintlify, MkDocs, Docusaurus, GitBook) wrap each heading
    in a hash-link anchor whose body is just an SVG icon. After `_strip_icon_svgs`
    drops the icon, the anchor has empty content but still renders as an
    inline element with default `<a>` styling — sometimes leaving a tiny
    visible artifact. Drop the empty wrapper too.

    Conservative: only matches anchors whose body, after tag-stripping, has no
    non-whitespace text. External links and meaningful in-text anchors survive.
    """
    def _maybe_drop(m: re.Match) -> str:
        body = m.group(1)
        text = re.sub(r"<[^>]+>", "", body).strip()
        return "" if not text else m.group(0)

    return re.sub(
        r'<a\b[^>]*\bhref\s*=\s*["\']#[^"\']*["\'][^>]*>(.*?)</a>',
        _maybe_drop,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_interactive_chrome(html: str) -> str:
    """Universal removal of interactive UI chrome that renders as grey blocks.

    Browsers paint empty/icon-only `<button>` elements, `<video>` players,
    `<audio>` players, and `<iframe>` placeholders as grey rounded rectangles
    when their site CSS is stripped. None of these can be meaningfully
    interacted with in a PDF, so we replace them with their renderable
    content (text inside) or remove them outright.

      * `<button>`: UNWRAP — keep inner text/markup, drop the tag. Confluence
        wraps `<th>` cell titles in `<button class="headerButton">`; vc.ru
        wraps share/follow CTAs in `<button>`; Хабр wraps voting controls.
        Unwrap preserves any text content while killing the grey-rectangle
        rendering. Empty/icon-only buttons collapse to empty spans (invisible).
      * `<video>`, `<audio>`: REMOVE entirely. The element body holds only
        `<source>` / track refs that can't render in PDF, and the controls
        bar always renders as a grey block.
      * `<iframe>`: REMOVE entirely. Cross-origin embeds (YouTube, Twitter,
        Yandex AdFox) are blocked by our offline_url_fetcher anyway and
        render as a grey placeholder.
    """
    html = re.sub(
        r"<button\b[^>]*>(.*?)</button>",
        r"\1",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r"<video\b[^>]*>.*?</video>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r"<audio\b[^>]*>.*?</audio>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r"<iframe\b[^>]*>.*?</iframe>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Self-closing forms of the same elements.
    html = re.sub(
        r"<(video|audio|iframe)\b[^>]*/?>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    return html


def _preprocess_html(html: str) -> str:
    """Apply weasyprint-compatibility fixes before rendering.

    Applied unconditionally to every input format so that real-world
    browser-saved pages render correctly without manual intervention.
    """
    html = _fix_light_dark(html)
    html = _strip_external_stylesheets(html)
    html = _strip_all_fontfaces_in_styles(html)
    html = _strip_interactive_chrome(html)
    html = _strip_icon_svgs(html)
    html = _strip_empty_anchor_links(html)
    html = _flatten_table_code_blocks(html)
    html = _strip_universal_ads(html)
    html = _fo_to_svg_text(html)
    html = _fix_svg_viewport(html)

    # Inject normalization CSS into <head>; fall back to before <body>
    # or prepend if neither tag is present.
    if "</head>" in html:
        html = html.replace("</head>", _NORMALIZE_CSS + "</head>", 1)
    elif "<body" in html:
        idx = html.index("<body")
        html = html[:idx] + _NORMALIZE_CSS + html[idx:]
    else:
        html = _NORMALIZE_CSS + html

    return html


# ── reader mode ───────────────────────────────────────────────────────────────

# Tiered article-root selectors with per-row text-length thresholds.
#
#   * High-confidence (Confluence/wiki conventions): `min_text=1` because
#     diagram-heavy KB pages legitimately have <500 chars and we trust the
#     selector. `id="main-content"` / `.wiki-content` rarely false-positive.
#   * Specific CMS / blog classes: `min_text=500` to skip excerpts on archive
#     index pages and small metadata divs (`.entry-meta`, `.post-meta`).
#   * Generic semantics (`<article>`, `[role=main]`): `min_text=500` because
#     false positives are common (sites use `<article>` for comments, etc.).
#   * Bare `<main>` is INTENTIONALLY OMITTED — it's tried separately with a
#     body-ratio guard (see `_reader_mode_html`). On news/blog SPAs `<main>`
#     often wraps the entire site (header + body + footer + recommendations).
#
# Within each row, the LONGEST qualifying match wins — handles archive pages
# with multiple `.entry` divs (post body is longer than excerpts) and Disqus
# comment threads (post body is longer than any single comment article).
_READER_CANDIDATES: list[dict] = [
    {"lookup": {"attr_name": "id",   "attr_value": "main-content"},   "min_text": 1},
    {"lookup": {"class_token": "wiki-content"},                       "min_text": 1},
    {"lookup": {"attr_name": "id",   "attr_value": "content"},        "min_text": 1},
    {"lookup": {"class_token": "entry"},                              "min_text": 500},
    {"lookup": {"class_token": "post-content"},                       "min_text": 500},
    {"lookup": {"class_token": "article-content"},                    "min_text": 500},
    {"lookup": {"class_token": "main-content"},                       "min_text": 500},
    {"lookup": {"tag": "div", "class_token": "article"},              "min_text": 500},
    {"lookup": {"tag": "article"},                                    "min_text": 500},
    {"lookup": {"attr_name": "role", "attr_value": "main"},           "min_text": 500},
]

# Reader-mode-only widget strip. Match SPA-blog inline widgets that
# `.entry` / `<article>` wrappers commonly include alongside the post body
# — vc.ru's `<div class="entry">` contains the article PLUS recommendation
# carousels, comments threads, and emoji-reaction bars all as siblings.
# Without this strip, reader-mode picks `.entry` correctly but the resulting
# PDF still has 3-4× the legitimate text plus tail emoji counters.
#
# Substring matching via class= contains (mirror of CSS [class*=KEYWORD]) —
# catches plurals and compound forms (`reaction` matches `content__reactions`,
# `reactions-bar`, `like-reaction`). Generic words (`sidebar`, `widget`,
# `share`, `meta`, `tags`) are EXCLUDED because they appear in BEM modifier
# positions on Habr (e.g. `tm-page__main_has-sidebar` is the MAIN article
# wrapper, not a sidebar). Use compound forms (`share-button`, `post-meta`)
# to target actual widget classes.
#
# Honest scope: substring matching can over-strip on niche articles where the
# topic literally mentions the keyword (e.g. a chemistry article with
# `<figure class="reaction-diagram">`). Reader-mode is an opt-in degraded view.
_READER_STRIP_KEYWORDS: list[str] = [
    # Recommendation widgets / related-articles blocks
    "rotator", "recommend", "related-post", "related-article",
    # Comment threads (whole section)
    "comments", "discussion-list", "replies-list",
    # Post-footer meta widgets: tags, share, subscribe
    "post-meta", "entry-meta", "post-tags", "entry-tags",
    "post-share", "entry-share", "share-button", "share-bar",
    "social-share", "social-button",
    "subscribe-block", "subscribe-form", "newsletter",
    # vc.ru-style article-footer engagement widgets: emoji reactions
    # (`.content__reactions`), floating engagement bar
    # (`.content__floating`), and post-footer with comment-counter +
    # share buttons. Same patterns appear on generic blogs as
    # `.entry-footer` / `.post-footer`.
    "reaction", "floating-bar", "floating-engage",
    "content-footer", "post-footer", "entry-footer",
    # Ad / promo / sponsored blocks
    "ad-banner", "ad-block", "advert", "sponsor-block",
    "promo-block", "ya-ai",
    # Cookie / GDPR consent prompts
    "cookie-banner", "cookie-consent", "gdpr-",
]

# Bare `<main>` body-ratio threshold: if `<main>` text is ≥95% of the
# original `<body>` text, `<main>` is wrapping the entire site (chrome
# included) and we reject it. Calibrated empirically — mobile-review's
# article-only `<main>` is ~89% of body; chrome-wrapping `<main>` on
# tested SPA blogs sits at 96-99%.
_MAIN_BODY_RATIO_MAX = 0.95

# Generic any-tag opener — captures tag name, attribute blob, and the
# self-closing slash. Used to enumerate every element start, then per-match
# attribute checks decide which ones to keep.
_ANY_OPEN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?(/?)>", re.DOTALL)

# HTML void elements that have no closing tag (skip depth tracking).
_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})


def _attr_value(attrs: str, name: str) -> str | None:
    """Return the value of attribute `name` from a tag's attribute blob, or None."""
    m = re.search(
        rf'\b{re.escape(name)}\s*=\s*["\']([^"\']*)["\']',
        attrs,
        flags=re.IGNORECASE,
    )
    return m.group(1) if m else None


def _find_all_elements(
    html: str,
    *,
    tag: str | None = None,
    class_token: str | None = None,
    class_substring_any: list[str] | None = None,
    attr_name: str | None = None,
    attr_value: str | None = None,
) -> list[tuple[int, int]]:
    """Find all elements matching the given constraints; depth-tracked.

    Returns a list of (start, end) byte offsets into `html` for the outer
    HTML of each match. Multiple constraints AND together. Returns nested
    matches too (parent + child both included if both qualify); callers
    decide whether to keep all (longest-match) or only outermost (strip).

      * `tag`                 → tag name equals (case-insensitive).
      * `class_token`         → class= attribute contains exact token (CSS `.X`).
      * `class_substring_any` → class= attribute contains ANY of the given
                                substrings as substring (CSS `[class*=X]`).
      * `attr_name`+`attr_value` → exact attribute value match (id, role, …).
    """
    out: list[tuple[int, int]] = []
    for m in _ANY_OPEN_RE.finditer(html):
        name = m.group(1).lower()
        if name in _VOID_ELEMENTS:
            continue
        attrs = m.group(2) or ""
        if m.group(3) == "/":          # self-closing form, no body
            continue
        if tag and name != tag.lower():
            continue
        if class_token is not None:
            cv = _attr_value(attrs, "class") or ""
            if class_token not in cv.split():
                continue
        if class_substring_any:
            cv = _attr_value(attrs, "class") or ""
            if not any(kw in cv for kw in class_substring_any):
                continue
        if attr_name and attr_value is not None:
            av = _attr_value(attrs, attr_name)
            if av is None or av.strip() != attr_value:
                continue
        # Find the matching close tag with depth tracking.
        start = m.start()
        pos = m.end()
        depth = 1
        open_n = re.compile(
            rf"<{re.escape(name)}(?:\s[^>]*)?(/?)>",
            re.IGNORECASE,
        )
        close_n = re.compile(rf"</{re.escape(name)}\s*>", re.IGNORECASE)
        while pos < len(html) and depth > 0:
            o = open_n.search(html, pos)
            c = close_n.search(html, pos)
            if c is None:
                break
            if o is not None and o.start() < c.start():
                if o.group(1) != "/":
                    depth += 1
                pos = o.end()
            else:
                depth -= 1
                pos = c.end()
        if depth == 0:
            out.append((start, pos))
    return out


def _text_length(fragment: str) -> int:
    """Length of `fragment` after stripping all tags, leading/trailing whitespace."""
    return len(re.sub(r"<[^>]+>", "", fragment).strip())


def _body_text_length(html: str) -> int:
    """Text-content length of the document `<body>` (or whole doc if no body)."""
    body_m = re.search(r"<body\b[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    inner = body_m.group(1) if body_m else html
    return max(1, _text_length(inner))


def _strip_reader_widgets(html: str) -> str:
    """Remove elements whose class= attr contains any _READER_STRIP_KEYWORDS substring.

    Outermost-only: when a stripped element contains another stripped element,
    only the outer one is removed (the inner range is already gone). Splices
    from the END of the document backwards so offsets remain valid.
    """
    matches = _find_all_elements(html, class_substring_any=_READER_STRIP_KEYWORDS)
    if not matches:
        return html
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    out = html
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def _reader_mode_html(html: str) -> str:
    """Extract main article content and return a clean HTML document.

    Pipeline:
      1. Snapshot body-text length BEFORE the widget strip — the bare-`<main>`
         body-ratio guard compares against the original body, otherwise the
         empirically-calibrated 0.95 threshold drifts as the keyword list grows.
      2. Strip widget keywords (recommendation carousels, share bars, comment
         threads, etc.) from the full document — vc.ru's `.entry` wrapper
         contains them as siblings of the article body, so they survive the
         later root-extraction step unless removed first.
      3. Walk `_READER_CANDIDATES` in priority order; within each row pick the
         LONGEST qualifying match (handles archive pages with multiple
         `.entry` divs and Disqus comment threads).
      4. If nothing matched, try bare `<main>` with body-ratio guard.
      5. Fall back to the full HTML if still nothing qualifies.

    The returned document keeps the original `<head>` (for charset/lang) but
    strips `<link rel=stylesheet>` and `<script>` tags so the PDF is rendered
    with only the bundled default CSS and _NORMALIZE_CSS — clean, consistent
    typography free of site-specific layout rules.
    """
    body_text_len = _body_text_length(html)
    html = _strip_reader_widgets(html)

    best = ""
    selector_used = ""
    for cand in _READER_CANDIDATES:
        matches = _find_all_elements(html, **cand["lookup"])
        if not matches:
            continue
        qualifying = [
            (s, e) for s, e in matches
            if _text_length(html[s:e]) >= cand["min_text"]
        ]
        if not qualifying:
            continue
        s, e = max(qualifying, key=lambda se: se[1] - se[0])
        best = html[s:e]
        selector_used = repr(cand["lookup"])
        break

    if not best:
        # Bare `<main>` with body-ratio guard. HTML5 forbids multiple `<main>`
        # per document but real-world pages violate this — prefer the FIRST
        # `<main>` satisfying the guard.
        for s, e in _find_all_elements(html, tag="main"):
            t_len = _text_length(html[s:e])
            if t_len >= 500 and t_len / body_text_len < _MAIN_BODY_RATIO_MAX:
                best = html[s:e]
                selector_used = f"main (body-ratio<{_MAIN_BODY_RATIO_MAX})"
                break

    if not best:
        return html  # nothing qualified: return unchanged (full HTML + CSS)

    # Strip site-injected styling from the extracted article body. Reader
    # mode renders with only DEFAULT_CSS + _NORMALIZE_CSS for clean,
    # consistent typography — site stylesheets reintroduce the chrome we
    # are trying to remove. Universal across sites:
    #
    #   * <style> blocks survive head-strip below; sites also embed style
    #     blocks INSIDE the article body (Confluence's tablesorter, GitHub
    #     <details>, etc.) which paint grey rounded rectangles on table
    #     headers, button-shaped <th>s, "copy heading link" hover targets.
    #   * <button> elements are NEVER article content — they're voting
    #     widgets (Хабр), share/anchor toggles (Confluence), navigation
    #     ("back to top", prev/next), "copy code" overlays. Default <button>
    #     styling renders as a grey rounded rectangle when the site CSS is
    #     stripped, so they appear as visible blank pills next to headings
    #     and at article boundaries.
    #   * Inline `style="..."` attributes on tags inside the body that
    #     reference colors / backgrounds / fonts can also leak; we keep
    #     them for now (some are legitimate, e.g. cell alignment) and rely
    #     on _NORMALIZE_CSS overriding the worst offenders with !important.
    best = re.sub(
        r"<style\b[^>]*>.*?</style>",
        "",
        best,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # NB: <button>/<video>/<audio>/<iframe> chrome strip is handled by
    # `_strip_interactive_chrome` in `_preprocess_html` (universal — applies
    # in regular mode too). No reader-specific duplicate needed here.

    # Preserve original <head> for charset/lang but strip ALL external CSS
    # AND inline <style> blocks. Reader mode uses only our bundled default
    # CSS + _NORMALIZE_CSS so the PDF has clean, consistent typography
    # regardless of source site.
    head_m = re.search(r"<head[^>]*>.*?</head>", html, re.DOTALL | re.IGNORECASE)
    if head_m:
        head = re.sub(
            r"<(link|script|style)\b[^>]*>(?:.*?</\1>)?",
            "",
            head_m.group(0),
            flags=re.DOTALL | re.IGNORECASE,
        )
    else:
        head = '<head><meta charset="utf-8"></head>'

    print(f"html2pdf: reader-mode root via {selector_used}", file=sys.stderr)
    return f"<!DOCTYPE html>\n{head}\n<body>\n{best}\n</body>\n</html>"


# ── format extractors ─────────────────────────────────────────────────────────

def _make_absolute_urls(text: str, page_url: str) -> str:
    """Rewrite root-relative (/) and protocol-relative (//) URLs to absolute.

    Root-relative paths like /assets/app.css appear in HTML attribute values
    and CSS url() calls, but the webarchive/MHTML subresource map stores full
    absolute URLs. Converting them here makes _rewrite_urls able to match and
    localise them.

    page_url is the archive's declared origin URL (e.g. https://vc.ru/).
    """
    parsed = urllib.parse.urlparse(page_url)
    if not parsed.scheme or not parsed.netloc:
        return text
    origin = f"{parsed.scheme}://{parsed.netloc}"
    scheme = parsed.scheme

    def _fix_url(url: str) -> str:
        if url.startswith("//"):
            return scheme + ":" + url
        if url.startswith("/"):
            return origin + url
        return url

    def _fix_attr(m: re.Match) -> str:
        return m.group(1) + _fix_url(m.group(2)) + m.group(3)

    def _fix_css_url(m: re.Match) -> str:
        return m.group(1) + _fix_url(m.group(2)) + m.group(3)

    # HTML attributes: href="...", src="...", action="...", data-src="..."
    text = re.sub(
        r'((?:href|src|action|data-src)\s*=\s*["\'])([^"\']*?)(["\'])',
        _fix_attr,
        text,
        flags=re.IGNORECASE,
    )
    # CSS url() values (handles quoted and unquoted)
    text = re.sub(
        r'(url\s*\(\s*["\']?)([^"\')\s]+)(["\']?\s*\))',
        _fix_css_url,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _rewrite_urls(text: str, url_map: dict[str, str]) -> str:
    """Replace every key in url_map with its local filename in text."""
    for url, local in url_map.items():
        text = text.replace(url, local)
    return text


def _fixup_css_subresources(
    css_parts: list[tuple[Path, bytes]],
    page_url: str,
    url_map: dict[str, str],
) -> None:
    """Rewrite URL references inside extracted CSS files in-place.

    Called by both _extract_mhtml and _extract_webarchive after all
    sub-resources have been written to disk. Strips @font-face blocks
    and rewrites absolute/root-relative URLs to local filenames so
    weasyprint can resolve @font-face / background-image without
    a network round-trip.
    """
    for css_path, css_raw in css_parts:
        css_text = css_raw.decode("utf-8", errors="replace")
        css_text = _make_absolute_urls(css_text, page_url)
        css_text = _strip_all_fontfaces(css_text)
        css_text = _rewrite_urls(css_text, url_map)
        css_path.write_text(css_text, encoding="utf-8")


def _extract_mhtml(src: Path, work_dir: Path) -> tuple[str, str]:
    """Parse a MIME HTML archive into work_dir.

    Returns (html_text, base_url) where base_url is str(work_dir).
    Sub-resources are written to work_dir; relative URL references in
    the HTML are rewritten to their local filenames so weasyprint can
    resolve them without a network. CSS subresources also have their
    URLs rewritten so embedded @font-face / background-image references
    resolve correctly from the temp dir.
    """
    raw = src.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    html_bytes: bytes | None = None
    page_url: str = ""
    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []   # (dest_path, raw_bytes)

    for part in msg.walk():
        ct      = part.get_content_type()
        loc     = part.get("Content-Location", "")
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if ct == "text/html" and html_bytes is None:
            html_bytes = payload
            page_url = loc  # origin URL for root-relative resolution
        elif loc:
            fname = Path(urllib.parse.unquote(loc.split("?")[0])).name or "resource"
            dest  = work_dir / fname
            idx   = 0
            while dest.exists():          # deduplicate on collision
                idx += 1
                dest = work_dir / f"{idx}_{fname}"
            dest.write_bytes(payload)
            url_map[loc] = dest.name
            if ct == "text/css":
                css_parts.append((dest, payload))

    if html_bytes is None:
        raise ValueError(f"no text/html part found in {src.name}")

    html_text = html_bytes.decode("utf-8", errors="replace")
    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)

    _fixup_css_subresources(css_parts, page_url, url_map)
    return html_text, str(work_dir)


def _extract_webarchive(src: Path, work_dir: Path) -> tuple[str, str]:
    """Parse an Apple WebKit binary-plist archive into work_dir.

    Returns (html_text, base_url) where base_url is str(work_dir).
    Sub-resources (images, CSS, fonts) are written to work_dir and
    absolute URLs in the HTML are rewritten to their local filenames.
    CSS subresources also have their URLs rewritten so embedded
    @font-face / background-image references resolve correctly.
    """
    with open(src, "rb") as f:
        plist = plistlib.load(f)

    main = plist.get("WebMainResource", {})
    html_data = main.get("WebResourceData", b"")
    enc       = main.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
    page_url  = main.get("WebResourceURL", "")
    html_text = (
        html_data.decode(enc, errors="replace")
        if isinstance(html_data, bytes)
        else str(html_data)
    )

    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []

    for sub in plist.get("WebSubresources", []):
        url  = sub.get("WebResourceURL", "")
        mime = sub.get("WebResourceMIMEType", "")
        data = sub.get("WebResourceData", b"")
        if not url or not isinstance(data, bytes) or not data:
            continue
        # Skip data: URIs — they are already inline in the HTML/CSS.
        if url.startswith("data:"):
            continue
        fname = Path(urllib.parse.unquote(url.split("?")[0])).name or "resource"
        dest  = work_dir / fname
        idx   = 0
        while dest.exists():
            idx += 1
            dest = work_dir / f"{idx}_{fname}"
        dest.write_bytes(data)
        url_map[url] = dest.name
        if mime == "text/css":
            css_parts.append((dest, data))

    # Resolve root-relative (/path) and protocol-relative (//host) URLs to
    # absolute before URL rewriting — the subresource map stores full URLs,
    # so root-relative paths in the HTML would never match otherwise.
    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)

    _fixup_css_subresources(css_parts, page_url, url_map)
    return html_text, str(work_dir)


# ── core renderer ─────────────────────────────────────────────────────────────

def _offline_url_fetcher(url: str) -> dict:
    """weasyprint URL fetcher that refuses remote (http/https) URLs.

    Default weasyprint behaviour is to fetch any external URL with no timeout
    (urllib's blocking call). On real-world web pages with dozens of CDN
    references (fonts, analytics pixels, social-media badges) this hangs the
    whole conversion for 10+ minutes per stalled request.

    Local schemes (`file://`, `data:`) fall through to weasyprint's default —
    we explicitly raise to force weasyprint to skip the remote resource and
    continue rendering. Skipped resources produce an "Failed to load X"
    weasyprint warning to stderr but the PDF still renders with whatever
    fonts / images were resolvable locally.
    """
    if url.startswith(("file://", "data:")):
        return default_url_fetcher(url)
    raise ValueError(f"remote fetch refused (offline mode): {url}")


class RenderTimeout(Exception):
    """Raised when weasyprint render exceeds the watchdog deadline."""


def _install_render_watchdog(seconds: int):
    """Install a SIGALRM-based watchdog that raises RenderTimeout after `seconds`.

    Returns the previous handler so the caller can restore it after the
    protected region. macOS / Linux only (signal.alarm is POSIX); on Windows
    the install is a no-op and the watchdog disables itself.

    SIGALRM interrupts blocking syscalls AND fires between Python bytecodes,
    so it can break weasyprint out of pure-Python layout loops as well as
    network reads. Pathological CSS layouts on SPA pages can otherwise hold
    the GIL for tens of minutes — the watchdog turns those into a clean
    timeout error rather than a stalled pipeline.
    """
    if not hasattr(signal, "SIGALRM") or seconds <= 0:
        return None

    def _on_alarm(signum, frame):
        raise RenderTimeout(
            f"weasyprint render exceeded {seconds}s — "
            "input may be too large or its CSS pathological for layout. "
            "Try --reader-mode (strips site CSS) or set HTML2PDF_TIMEOUT=0 "
            "to disable the watchdog."
        )

    prev = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    return prev


def _clear_render_watchdog(prev) -> None:
    if not hasattr(signal, "SIGALRM"):
        return
    signal.alarm(0)
    if prev is not None:
        signal.signal(signal.SIGALRM, prev)


def convert(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    extra_css_path: Path | None,
    use_default_css: bool,
    reader_mode: bool = False,
    timeout: int = 0,
) -> None:
    if reader_mode:
        html_text = _reader_mode_html(html_text)
    html_text = _preprocess_html(html_text)
    stylesheets = []
    if use_default_css:
        css = DEFAULT_CSS.replace("{page_size}", PAGE_SIZES.get(page_size, "letter"))
        stylesheets.append(CSS(string=css))
    if extra_css_path is not None:
        stylesheets.append(CSS(filename=str(extra_css_path)))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prev_handler = _install_render_watchdog(timeout)
    try:
        HTML(
            string=html_text,
            base_url=base_url,
            url_fetcher=_offline_url_fetcher,
        ).write_pdf(str(output_path), stylesheets=stylesheets)
    finally:
        _clear_render_watchdog(prev_handler)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "input", type=Path,
        help="Source file: .html/.htm, .mhtml/.mht, or .webarchive",
    )
    parser.add_argument("output", type=Path, help="Destination .pdf file")
    parser.add_argument("--page-size", choices=list(PAGE_SIZES.keys()), default="letter")
    parser.add_argument("--css", type=Path, default=None,
                        help="Extra CSS file appended after defaults.")
    parser.add_argument("--base-url", default=None,
                        help="Base URL for resolving relative assets in plain "
                             ".html inputs (default: input's directory). "
                             "Ignored for .mhtml / .webarchive — the extracted "
                             "temp dir is used automatically.")
    parser.add_argument("--no-default-css", dest="no_default_css",
                        action="store_true",
                        help="Skip the bundled stylesheet (use only the "
                             "input's embedded styles + --css if given). "
                             "Structural normalisation CSS is still injected.")
    parser.add_argument("--reader-mode", dest="reader_mode",
                        action="store_true",
                        help="Extract only the main article content before "
                             "rendering (like Safari Reader View). Strips "
                             "navigation, ads, and sidebars by finding the "
                             "first <article>, <main>, or known content "
                             "container. Implies --no-default-css is NOT set "
                             "— the bundled clean stylesheet is always used.")
    # Watchdog default: 180s. SPA pages with pathological CSS (vc.ru-style
    # nested flex/grid layouts) can hang weasyprint's box-layout engine for
    # tens of minutes on otherwise-modest HTML — without a timeout the whole
    # pipeline stalls. Override via --timeout SECONDS or HTML2PDF_TIMEOUT env;
    # set to 0 to disable. Honest scope: timeout fires only on POSIX
    # (signal.SIGALRM); on Windows it's a no-op.
    parser.add_argument(
        "--timeout", dest="timeout", type=int,
        default=int(os.environ.get("HTML2PDF_TIMEOUT", "180")),
        help="Render watchdog deadline in seconds (default 180; "
             "$HTML2PDF_TIMEOUT overrides; 0 disables). Kills weasyprint "
             "if its layout exceeds the deadline (POSIX only).",
    )
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    ext = args.input.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return report_error(
            f"Unsupported input format {ext!r}. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
            code=1, error_type="UnsupportedFormat",
            details={"path": str(args.input), "ext": ext}, json_mode=je,
        )

    if args.css is not None and not args.css.is_file():
        return report_error(
            f"CSS file not found: {args.css}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.css)}, json_mode=je,
        )

    # cross-7 H1 same-path guard (catches symlinks via .resolve()).
    try:
        same = args.input.resolve() == args.output.resolve()
    except OSError:
        same = False
    if same:
        return report_error(
            f"INPUT and OUTPUT resolve to the same path: {args.input.resolve()} "
            "(would corrupt the source mid-write).",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": str(args.input), "output": str(args.output)},
            json_mode=je,
        )

    tmp_dir: str | None = None
    try:
        if ext in (".html", ".htm"):
            html_text = args.input.read_text(encoding="utf-8")
            base_url  = args.base_url or str(args.input.parent.resolve())
        elif ext in (".mhtml", ".mht"):
            tmp_dir   = tempfile.mkdtemp(prefix="html2pdf_mhtml_")
            html_text, base_url = _extract_mhtml(args.input, Path(tmp_dir))
        else:  # .webarchive
            tmp_dir   = tempfile.mkdtemp(prefix="html2pdf_webarchive_")
            html_text, base_url = _extract_webarchive(args.input, Path(tmp_dir))

        convert(
            html_text, args.output,
            base_url=base_url,
            page_size=args.page_size,
            extra_css_path=args.css,
            use_default_css=not args.no_default_css,
            reader_mode=args.reader_mode,
            timeout=args.timeout,
        )
    except RenderTimeout as exc:
        return report_error(
            str(exc), code=1, error_type="RenderTimeout",
            details={"timeout": args.timeout}, json_mode=je,
        )
    except Exception as exc:
        return report_error(
            f"Conversion failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
