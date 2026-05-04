"""Injected print-normalization stylesheet for html2pdf.

A single CSS string injected into every rendered document just before
weasyprint runs. It fixes layout bugs that browser CSS hides (height: 100vh
on body, position:fixed nav bars, multi-column flex wrappers, oversized
inline SVGs) and styles ARIA-role tables / code blocks / anchor buttons.

Pure data — no logic. Imported by `preprocess.preprocess_html()`.
"""

NORMALIZE_CSS = """\
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
    /* `white-space: pre-wrap` preserves leading indentation; `overflow-wrap:
       break-word` lets long unbreakable tokens (URLs, base64) wrap at the page-
       width boundary instead of clipping past the right margin. PDFs can't
       scroll, so `overflow-x: auto` (the browser default) silently drops
       content past the box. We deliberately do NOT use `word-break: break-word`
       — weasyprint rejects this CSS-WG-deprecated alias as an invalid value
       (verified empirically; logs `Ignored 'word-break: break-word'`); only
       the standard `overflow-wrap: break-word` carries the wrap behaviour. */
    white-space: pre-wrap !important;
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

/* ── 7a-bis. Block-level code (Prism / Confluence DC).
        Newer Confluence editors and many docs sites use a Prism-style code
        block WITHOUT a wrapping <pre>:
            <div class="codeBlockContainer_HASH"><code class="language-sql"
                  style="white-space: pre;">…spans…</code></div>
        The inline `white-space: pre` overflows long source lines past the
        right margin (PDFs cannot scroll, so content is silently clipped and
        un-copyable). Force `pre-wrap` so weasyprint wraps the lines at the
        page boundary.

        Selector notes:
          * `code[class*="language-"]` — Prism / shiki / highlight.js
            convention, present in Mintlify, Docusaurus, MkDocs, the new
            Confluence DC editor, and many vendors. This is the load-bearing
            selector — it catches the inner <code> regardless of parent.
          * `.code.panel code` — Confluence's classic chained-class wrapper
            (`<div class="code panel pdl conf-macro output-block">…</div>`);
            narrow on purpose.
          * `[class*="codeBlockContainer"] code` — Confluence DC ships hashed
            class names like `codeBlockContainer_yyk2gsoAwjaamghp6yoO-Q==`.
            CSS class selectors do NOT prefix-match, so a literal
            `.codeBlockContainer` would be DEAD — we use the attribute-
            substring selector to catch every hash variant.

        Why no `display: block` / `background` / `padding` here: in non-
        reader mode the document contains absolute-positioned chrome whose
        containing-block resolves through these inline `<code>` elements;
        switching them to block layout triggers a weasyprint regression
        (`absolute_block: 'NoneType' object has no attribute 'width'`,
        verified on US-Отчёт regular render). The visual envelope users
        see (light-grey rounded box around the code) comes from
        Confluence's preserved inline `<style>` blocks, NOT from us — our
        scope is wrap-only. `word-break: break-word` is intentionally
        absent (see §7a comment). Latent-failure mode out of scope: if
        upstream ever ships `style="white-space: pre !important"` inline,
        CSS spec says inline `!important` beats stylesheet `!important`
        and our wrap silently regresses. Today no fixture does this. */
code[class*="language-"],
.code.panel code,
[class*="codeBlockContainer"] code {
    white-space: pre-wrap !important;
    overflow-wrap: break-word !important;
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
