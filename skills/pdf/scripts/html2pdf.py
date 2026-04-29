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
        [--base-url DIR] [--no-default-css]

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

Same-path I/O (input == output, including via symlink) is refused
with exit 6 / SelfOverwriteRefused.
"""
from __future__ import annotations

import argparse
import email
import email.policy
import html as html_module
import plistlib
import re
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

from weasyprint import CSS, HTML  # type: ignore

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

    weasyprint silently discards <foreignObject> content. draw.io stores ALL
    node text labels inside <foreignObject> divs. This function extracts the
    visible text and the anchor coordinates (padding-top → y, margin-left → x
    from the inner flex container) and emits an SVG <text> element.

    Position accuracy is approximate (~2px): the padding-top / margin-left
    values in draw.io foreignObject always represent the visual centre of the
    shape, so text-anchor="middle" + dominant-baseline="middle" lands the
    label correctly for the common case.
    """
    def _replace(m: re.Match) -> str:
        fo = m.group(0)
        # Extract all visible text (strip HTML tags, collapse whitespace).
        raw = re.sub(r"<[^>]+>", " ", fo)
        text = html_module.unescape(" ".join(raw.split()))
        if not text:
            return ""

        # Anchor: padding-top → y, margin-left → x (draw.io flex-centre div).
        pos = re.search(
            r"padding-top:\s*([\d.]+)px.*?margin-left:\s*([\d.]+)px",
            fo, re.DOTALL,
        )
        if not pos:
            return ""
        y = float(pos.group(1))
        x = float(pos.group(2))

        fs_m = re.search(r"font-size:\s*([\d.]+)px", fo)
        fs = int(float(fs_m.group(1))) if fs_m else 12
        bold = ' font-weight="bold"' if "font-weight: bold" in fo else ""

        return (
            f'<text x="{x}" y="{y}" text-anchor="middle" '
            f'dominant-baseline="middle" font-family="Helvetica" '
            f'font-size="{fs}"{bold} fill="#000000">'
            f"{html_module.escape(text)}</text>"
        )

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
            tag = re.sub(r'\bheight\s*=\s*["\']?[\d.]+["\']?', '', tag, count=1)
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
        return tag[:-1] + f' {new_vb}>'

    return re.sub(r'<svg\b[^>]*>', _patch, html, flags=re.IGNORECASE | re.DOTALL)


def _preprocess_html(html: str) -> str:
    """Apply weasyprint-compatibility fixes before rendering.

    Applied unconditionally to every input format so that real-world
    browser-saved pages render correctly without manual intervention.
    """
    html = _fix_light_dark(html)
    html = _strip_all_fontfaces_in_styles(html)
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

# Priority-ordered list of (tag, class_token) content candidates.
# Empty class_token matches any element of that tag.
_READER_CANDIDATES: list[tuple[str, str]] = [
    ("article", ""),        # HTML5 <article> — blogs / news / wikis
    ("main", ""),           # HTML5 <main> — docs / portals
    ("div", "entry"),       # vc.ru article wrapper
    ("div", "post-content"),
    ("div", "article-content"),
    ("div", "main-content"),
    ("div", "article"),
]
_READER_MIN_TEXT = 500      # minimum character count for a candidate to qualify


def _extract_element(html: str, tag: str, class_token: str = "") -> str:
    """Return the outer HTML of the first element matching tag (and class).

    Handles nested same-tag elements by tracking depth. Returns empty string
    when no match is found or the closing tag cannot be located.
    """
    if class_token:
        open_pat = re.compile(
            rf"<{re.escape(tag)}(?=[^>]*\b{re.escape(class_token)}\b)[^>]*>",
            re.IGNORECASE | re.DOTALL,
        )
    else:
        open_pat = re.compile(
            rf"<{re.escape(tag)}(?:\s[^>]*)?>",
            re.IGNORECASE | re.DOTALL,
        )

    m = open_pat.search(html)
    if not m:
        return ""

    start = m.start()
    pos = m.end()
    depth = 1
    any_open = re.compile(rf"<{re.escape(tag)}[\s>]", re.IGNORECASE)
    any_close = re.compile(rf"</{re.escape(tag)}\s*>", re.IGNORECASE)

    while pos < len(html) and depth > 0:
        o = any_open.search(html, pos)
        c = any_close.search(html, pos)
        if c is None:
            return ""
        if o is not None and o.start() < c.start():
            depth += 1
            pos = o.end()
        else:
            depth -= 1
            pos = c.end()

    return html[start:pos] if depth == 0 else ""


def _reader_mode_html(html: str) -> str:
    """Extract the main article content and return a clean HTML document.

    Searches content candidates in priority order, picks the first with more
    than _READER_MIN_TEXT characters of text (tags stripped). Falls back to
    the full HTML if nothing qualifying is found.

    The returned document preserves the original <head> (for charset/lang)
    but strips all <link rel=stylesheet> and <script> tags so the PDF is
    rendered with only the bundled default CSS and _NORMALIZE_CSS — giving
    clean, consistent typography free of site-specific layout rules.
    """
    best = ""
    for tag, cls in _READER_CANDIDATES:
        element = _extract_element(html, tag, cls)
        if element:
            text_len = len(re.sub(r"<[^>]+>", "", element))
            if text_len >= _READER_MIN_TEXT:
                best = element
                break

    if not best:
        return html  # nothing found: return unchanged (full HTML + CSS)

    # Preserve the original <head> but strip external resources so the PDF
    # uses only our clean default CSS.
    head_m = re.search(r"<head[^>]*>.*?</head>", html, re.DOTALL | re.IGNORECASE)
    if head_m:
        head = re.sub(
            r"<(link|script)\b[^>]*>(?:.*?</\1>)?",
            "",
            head_m.group(0),
            flags=re.DOTALL | re.IGNORECASE,
        )
    else:
        head = '<head><meta charset="utf-8"></head>'

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

    # Rewrite URLs inside CSS subresources so @font-face / background-image
    # references resolve to local files instead of the original CDN.
    for css_path, css_raw in css_parts:
        css_text = css_raw.decode("utf-8", errors="replace")
        css_text = _make_absolute_urls(css_text, page_url)
        css_text = _strip_all_fontfaces(css_text)
        css_text = _rewrite_urls(css_text, url_map)
        css_path.write_text(css_text, encoding="utf-8")

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

    # Rewrite URLs inside CSS subresources (font-face, background-image).
    for css_path, css_raw in css_parts:
        css_text = css_raw.decode("utf-8", errors="replace")
        css_text = _make_absolute_urls(css_text, page_url)
        css_text = _strip_all_fontfaces(css_text)
        css_text = _rewrite_urls(css_text, url_map)
        css_path.write_text(css_text, encoding="utf-8")

    return html_text, str(work_dir)


# ── core renderer ─────────────────────────────────────────────────────────────

def convert(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    extra_css_path: Path | None,
    use_default_css: bool,
    reader_mode: bool = False,
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
    HTML(string=html_text, base_url=base_url).write_pdf(
        str(output_path), stylesheets=stylesheets,
    )


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
