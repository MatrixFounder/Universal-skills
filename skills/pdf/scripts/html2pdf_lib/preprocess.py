"""HTML preprocessing pipeline applied before weasyprint render.

Eleven independent regex/scan passes that fix real-world compatibility
issues (CSS Color Level 5, draw.io foreignObject, oversized inline SVGs,
site-CSS layout bugs, table-based code blocks, ad/icon strip, interactive
chrome). Composed into `preprocess_html()` which is called from
`render.convert()` for every input format.

Each fix is independently testable and idempotent on already-clean HTML.
"""
from __future__ import annotations

import html as html_module
import re

from .dom_utils import find_all_elements
from .normalize_css import NORMALIZE_CSS


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


def strip_all_fontfaces(css: str) -> str:
    """Remove all @font-face blocks from CSS.

    Web fonts served from CDN are often subset with remapped glyph
    indices, and the URL hashes in the webarchive's font-face declarations
    rarely match the actual woff2 files captured as subresources. weasyprint
    falls back to fetching from CDN and may receive the wrong subset —
    producing garbled Latin text (e.g. "SMlc Та St Та" for "Claude Code").
    Stripping all @font-face blocks forces weasyprint to use system fonts
    (Helvetica/Arial/Liberation) which have correct, stable glyph mappings.

    Public — also called from `archives._fixup_css_subresources` to clean
    extracted .css subresources before weasyprint loads them.
    """
    return re.sub(
        r"@font-face\s*\{[^}]*\}",
        "",
        css,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_all_fontfaces_in_styles(html: str) -> str:
    """Apply strip_all_fontfaces to every <style> block in the HTML."""
    def _fix_style(m: re.Match) -> str:
        tag, content, close = m.group(1), m.group(2), m.group(3)
        return tag + strip_all_fontfaces(content) + close

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

    # IGNORECASE matters: SVG spec is camelCase `<foreignObject>`, but the
    # HTML5 serializer (used by browsers' "Save Page As → Webpage, Complete")
    # lowercases tag names → `<foreignobject>`. Confluence .html exports hit
    # this path; .mhtml archives preserve the original namespace casing and
    # don't. Without IGNORECASE the regex misses 100 % of HTML5-serialized
    # diagrams, weasyprint silently drops the foreignObject content, and the
    # PDF renders all draw.io blocks as empty boxes.
    return re.sub(
        r"<foreignObject[^>]*>.*?</foreignObject>",
        _replace,
        html,
        flags=re.DOTALL | re.IGNORECASE,
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
    `reader_mode._strip_reader_widgets` but with an ad-specific keyword list.
    Applied unconditionally in `preprocess_html`, before reader-mode root
    extraction and before weasyprint render — keeps ads from pushing real
    content off the first page in regular mode.
    """
    matches = find_all_elements(html, class_substring_any=_AD_STRIP_KEYWORDS)
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
      * Our NORMALIZE_CSS (chrome strip),
      * Inline `<style>` blocks (structural styles like table layout, which
        usually work fine — Confluence's content survives intact).
    Tested across Confluence, Хабр, vc.ru, mobile-review, generic blogs:
    output is more consistent, faster, and content-complete.
    """
    # `<link rel="stylesheet">` plus ALL `<link rel="preload">` variants
    # (preload covers as="style", as="font", as="image", as="script", etc.).
    # Preloads are hints to the browser to fetch resources we either embed
    # locally OR refuse via offline_url_fetcher anyway, so dropping all of
    # them is safe and avoids edge cases where preload-as=style ships the
    # main stylesheet via the lazy-loaded variant.
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
        # Numeric width/height attrs (px or unit-less). Rule: ALL declared
        # explicit numeric dims must be ≤ _ICON_SVG_MAX_PX. UI icons that
        # constrain only ONE dimension (Mintlify anchor links:
        # `<svg height="12px" viewBox="0 0 576 512">`) still match because
        # only one is checked. Content SVGs with mixed dims like
        # 50×500 (legitimate vertical timeline / progress bar) FAIL because
        # height=500 > 64. Earlier "EITHER axis ≤ 64" rule wrongly stripped
        # those. (VDD-iter-5 fix.)
        wm = re.search(r'\bwidth\s*=\s*["\']?(\d+)(?:px)?\b', svg_open_tag)
        hm = re.search(r'\bheight\s*=\s*["\']?(\d+)(?:px)?\b', svg_open_tag)
        explicit_dims = [m for m in (wm, hm) if m]
        if explicit_dims:
            try:
                if all(int(m.group(1)) <= _ICON_SVG_MAX_PX for m in explicit_dims):
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
    # Self-closing `<svg .../>` is also legal SVG/XHTML and must be handled
    # separately — otherwise depth never reaches 0, the loop hits
    # `if depth != 0: break` and EVERY SVG after the first self-closing one
    # leaks through unstripped (silent regression of giant-icon bug).
    # (VDD-iter-5 fix.)
    out: list[str] = []
    pos = 0
    open_re = re.compile(r"<svg\b[^>]*?(/?)>", re.IGNORECASE)
    close_re = re.compile(r"</svg\s*>", re.IGNORECASE)
    while True:
        m = open_re.search(html, pos)
        if not m:
            out.append(html[pos:])
            break
        out.append(html[pos:m.start()])
        is_self_closing = m.group(1) == "/"
        if is_self_closing:
            # `<svg .../>` is its own complete element; no body to scan.
            if not _is_icon(m.group(0)):
                out.append(m.group(0))
            pos = m.end()
            continue
        # Find matching </svg> with depth tracking.
        depth = 1
        scan = m.end()
        while depth > 0 and scan < len(html):
            o = open_re.search(html, scan)
            c = close_re.search(html, scan)
            if c is None:
                break
            if o is not None and o.start() < c.start():
                # Nested open — but skip self-closing nested too.
                if o.group(1) != "/":
                    depth += 1
                scan = o.end()
            else:
                depth -= 1
                scan = c.end()
        if depth != 0:
            # Unclosed SVG (malformed input). Don't lose the rest of the
            # document — keep the SVG verbatim and resume scanning AFTER
            # its open tag so subsequent SVGs still get processed.
            out.append(m.group(0))
            pos = m.end()
            continue
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
    ...</code></pre>` that paginates cleanly via the bundled `NORMALIZE_CSS`.

    Honest scope: shiki / Prism inline `<span style="color:#...">` token
    highlighting is STRIPPED — output is monochrome. weasyprint cannot
    paginate complex nested span-styled <pre> reliably across pages
    (this is the bug being worked around), and re-emitting the styles
    would risk reintroducing the same interleaving problem. If syntax
    colours matter more than completeness, a future iteration could
    preserve token <span>s and pin the table to a single page via
    `page-break-inside: avoid` — but loses content past one page.
    """
    # Match a <table> wrapper that's an obvious code-block table:
    # contains <tr class="*code-block-line*"> or similar markers.
    table_re = re.compile(
        r'<table\b[^>]*>(.*?)</table>',
        re.DOTALL | re.IGNORECASE,
    )

    # Pre-compiled element-anchored matchers — substring-anywhere
    # ('code-block-line' in inner) was a false positive risk: a
    # documentation page with `<table>` containing inline `<a class="line-link">`
    # AND any element with `class*=highlight` would misclassify as code and
    # get flattened to plain text. Anchor at `<tr>` / `<span>` boundaries.
    # (VDD-iter-5 fix.)
    _tr_code_re = re.compile(
        r'<tr\b[^>]*\bclass="[^"]*(?:code-block-line|hl-row)\b',
        re.IGNORECASE,
    )
    _span_line_re = re.compile(r'<span\b[^>]*\bclass="line"', re.IGNORECASE)

    def _is_code_table(inner: str) -> bool:
        # Mintlify/Fern: <tr class="code-block-line">
        # Docusaurus:    <tr class="hl-row">
        if _tr_code_re.search(inner):
            return True
        # Pygments: <span class="line"> directly + 'highlight' marker.
        if _span_line_re.search(inner) and 'highlight' in inner:
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

    Two-stage scan to avoid the O(n×k) backtracking that the previous combined
    regex `<a\\b[^>]*\\bhref...#[^"']*["'][^>]*>` exhibited on TOC pages with
    thousands of `<a href="https://...">` (no #) anchors. The hash-href check
    now runs as a Python predicate per matched <a>, not as part of the master
    regex. (VDD-iter-5 fix.)
    """
    def _maybe_drop(m: re.Match) -> str:
        opener_attrs = m.group(1)
        body = m.group(2)
        # Fast pre-check: does this anchor have a hash href? If not, keep.
        if not re.search(r'\bhref\s*=\s*["\']#', opener_attrs):
            return m.group(0)
        text = re.sub(r"<[^>]+>", "", body).strip()
        return "" if not text else m.group(0)

    return re.sub(
        r'<a\b([^>]*)>(.*?)</a>',
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
    # Iterative <button> unwrap: handles nested buttons (illegal HTML5 but
    # observed in some Mintlify "expand-all" wrappers). Single regex.sub with
    # non-greedy `.*?` matches at the FIRST `</button>` after a `<button>`
    # open, leaving stray `</button>` tags on nested input. Repeat until
    # stable: each pass unwraps the innermost button (because non-greedy
    # picks the smallest body), the next pass unwraps the now-innermost,
    # and so on. (VDD-iter-5 fix.)
    while True:
        new_html = re.sub(
            r"<button\b[^>]*>(.*?)</button>",
            r"\1",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if new_html == html:
            break
        html = new_html
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


def preprocess_html(html: str) -> str:
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
        html = html.replace("</head>", NORMALIZE_CSS + "</head>", 1)
    elif "<body" in html:
        idx = html.index("<body")
        html = html[:idx] + NORMALIZE_CSS + html[idx:]
    else:
        html = NORMALIZE_CSS + html

    return html
