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

/* ── 4a. Confluence Server's `<main id="main" style="margin-left:430px">`
        and `<div id="main-header-placeholder" style="padding-top:55px;
        height:100px">` carry inline geometry that compensates for the
        fixed left sidebar (430 px) and top header (55 px). After §3
        hides those nav containers and §7d hides the rest of the
        sidebar, the article body still has the offsets and gets
        squeezed into a narrow right column with the title inline-
        wrapping into the version-table area on page 1 (US-Отчет
        Полнотекстовый поиск and similar Confluence pages, observed
        2026-05-04). Override the inline styles so the article reclaims
        the full page width. We target `<main>` / `#main` /
        `#main-content` / `#content` plus the header-placeholder
        explicitly — generic `body > *` would over-strip legitimate
        layout.

        Scope of reset (load-bearing only — verified empirically against
        the ELMA365 Confluence corpus, 2026-05-05):
          * `margin-left: 0` — overrides `margin-left: 430px` on `<main>`
            (the actual cause of the squeezed-column rendering).
          * `padding-top: 0` — overrides `padding-top: 55px` on
            `#main-header-placeholder` (the top-banner reservation).
          * `top: 0` — neutralises `top: 55px` from `position: fixed`
            elements after §4 resets them to `position: static`.
          * `height/min-height: auto/0` — lifts the inline
            `height: 100px` cap on `#main-header-placeholder`.
          * `width/max-width: auto/100%` — lifts the inline
            `width: 1064px` (sidebar-anchored) on `#main-header`.
        Deliberately NOT reset:
          * `padding-left/right` — `#content` is a generic ID widely
            used outside Confluence (Sphinx, MkDocs, Hugo, GitHub
            README pages). Stripping horizontal padding made article
            text touch the page-margin edges, a typographic regression
            on every non-Confluence page that uses `#content`. The
            sidebar offset is purely `margin-left`; padding was never
            the cause. */
main, #main, #main-content, #content,
#main-header, #main-header-placeholder {
    margin-left: 0 !important;
    padding-top: 0 !important;
    top: 0 !important;
    height: auto !important;
    min-height: 0 !important;
    width: auto !important;
    max-width: 100% !important;
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

/* ── 7d. Confluence Server / Atlassian DC chrome strip.
        Confluence Server pages embed many UI containers around the
        article body that, once site CSS is stripped, ALL render
        visibly into the PDF — leaking sidebars, page-tree data tables,
        page-action toolbars, AUI dropdowns, etc.

        Three categories:

        (a) AUI dropdowns and overlay layers. `<div id="action-menu"
            class="aui-dropdown2 aui-layer …">` is absolutely positioned
            in the source HTML and contains the page-actions list (Save
            for later / Watching / Share / Page History / Export to PDF /
            …). The AUI runtime keeps it `display:none` until the user
            clicks the trigger; once site CSS is stripped, every
            `.aui-dropdown2` and `.aui-layer` panel becomes visible.
            Same applies to share menus, JIRA-issue popups, etc.
        (b) Left-rail sidebar. `<div class="ia-fixed-sidebar"
            role="complementary">` wraps the space logo, "Pages / Blog /
            Calendars / Analytics" navigation, "Quick links" widget, and
            the page-tree component. Without site CSS its absolute
            position is lost and it stacks on top of the article — first
            two PDF pages become a list of sibling page titles instead of
            article content (observed on ELMA365 ↔ 3CX wiki, 2026-05-04).
        (c) Page-action toolbar `<div id="navigation"
            class="content-navigation view" role="region">` containing
            `<ul class="ajs-menu-bar">` with Edit / View comments / Save
            for later / Watching / Share / JIRA links. Different from the
            #action-menu dropdown (a) — this is the always-visible icon
            toolbar above the page title.
        (d) Page-tree macro `<div class="plugin_pagetree">` with its
            `data-*` config attributes. The pageTree plugin renders the
            tree via JS at runtime; the static HTML it ships contains
            only configuration data (URLs, page IDs, "Loading…" / "Could
            not load page tree" error strings) wrapped in invisible
            divs that become visible cells once CSS is stripped.

        Comprehensive selector list — overlapping by design (a Confluence
        page typically uses 3-4 of these containers nested), so a single
        broad `display: none !important` is the cheapest valid reset.
        Mirror of html2docx's preprocess `stripConfluenceChromeIds` +
        `stripAriaLandmarks` stages.

        Note: do NOT include `#title-heading` here — its `<h1>` is the
        article's actual page title (extracted separately into the docx
        via `extractPageTitle()`; in html2pdf it remains in the article
        flow because we don't narrow the root the same way).

        Honest scope (over-strip trade-offs accepted, 2026-05-05):
          * `[role="banner|complementary|contentinfo|search"]` are
            stripped GLOBALLY (not scoped to body-level). ARIA spec
            allows these roles inside article content (e.g. an
            accessibility tutorial demonstrating `role="search"`, or
            a `<aside role="complementary">` "Tip" callout that's part
            of the article body). For our corpus all four roles
            consistently mark site-level chrome; an article-internal
            usage would be lost. If a future fixture exercises this
            edge case, narrow via `:not(article …)` or scope to
            `body > [role="…"]`.
          * `#navigation`, `#breadcrumbs`, `#header`, `#footer` are
            generic IDs that legitimate non-Confluence sites might use.
            A blog whose only breadcrumb container is `#breadcrumbs`
            loses navigation context. We accept this — the alternative
            (per-platform CSS scoping with `[class^="atlassian"]`
            ancestors) is fragile across Confluence Server versions
            and useless against other CMSes that emit identical IDs. */
/* (a) AUI dropdowns + overlay layers + edit toolbar. */
#action-menu, #share-menu, #share-on-page,
.aui-dropdown2, .aui-layer, .aui-toolbar2,
#likes-and-labels-container, #labels-section, #labels-section-panel,
#space-tools-menu,
/* (b) Left-rail sidebar (everything inside .ia-fixed-sidebar +
       role=complementary covers the same region twice — Confluence
       sometimes wraps it without setting role, sometimes the inverse). */
.ia-fixed-sidebar, .ia-splitter-handle,
[role="complementary"], [role="banner"], [role="contentinfo"],
[role="search"],
.acs-side-bar, .acs-nav-wrapper, .acs-nav-children-pages,
.ia-secondary-container, .ia-secondary-content,
.space-tools-section,
/* (c) Page-action icon toolbar (`<ul class="ajs-menu-bar">`). The wrapper
       `<div id="navigation" role="region">` is the Confluence page nav
       toolbar — distinct from semantic `<nav>` and from the AUI
       dropdown above. We also strip `[role="navigation"]` and `<nav>`
       in §3, which catches some variants but not the `role="region"`
       wrapper. */
#navigation, .content-navigation, .ajs-menu-bar,
[role="region"][aria-label*="страниц"],
[role="region"][aria-label*="Pages"],
/* (d) Page-tree macro static HTML config (visible cells without site CSS). */
.plugin_pagetree, .plugin_pagetree_children,
/* Generic Confluence chrome IDs not yet covered. */
#header, #footer, #breadcrumb-section, #breadcrumbs,
#page-metadata, #comments-section, #footer-logo,
.page-metadata, .pageSection.group,
/* Page-metadata banner row. Confluence renders system metadata (Pinned,
   page restrictions, attachment counter, JIRA links, watching, etc.) as
   `<ul class="banner"> <li id="system-content-items"> … <li
   id="content-metadata-jira-wrapper"> …`. The `.banner` class is too
   generic to strip wholesale (real article banners exist), but its
   children IDs and `.page-metadata-item` are distinctive enough. */
.page-metadata-item, #system-content-items,
#content-metadata-jira-wrapper, #content-metadata-jira,
#content-metadata-page-restrictions,
ul.banner > li[id^="content-metadata-"],
ul.banner > li[id="system-content-items"] {
    display: none !important;
}
</style>
"""
