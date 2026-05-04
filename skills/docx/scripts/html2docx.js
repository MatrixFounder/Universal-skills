// html2docx.js — Arbitrary HTML → .docx (CLI entry).
//
// Parallel to md2docx.js but accepts HTML on input (e.g. Confluence /
// CMS exports). Converts the input to a cheerio DOM, walks it via
// _html2docx_walker.js, and emits the same docx-js objects md2docx
// produces, so output styling is consistent across both pipelines.
//
// Supported input formats:
//   * Plain `.html` / `.htm` — relative `<img>` paths resolved from the
//     directory of the HTML file (works with Chrome "Save Page As Webpage,
//     Complete" output where assets live in `<page>_files/`).
//   * Safari `.webarchive` (Apple binary plist) — extracted via
//     _html2docx_archive.js: main HTML pulled from `WebMainResource`,
//     image sub-resources dumped to a temp dir, URLs mapped via
//     `WebResourceURL`.
//   * Chrome `.mhtml` / `.mht` (MIME multipart/related) — extracted via
//     _html2docx_archive.js: main `text/html` part decoded
//     (quoted-printable / base64), image parts dumped, URLs mapped via
//     `Content-Location`.
//
// Honest scope (see references/html-conversion.md):
//   * Inline `style=""` attributes and CSS classes are ignored.
//   * `<table>` rowspan/colspan are NOT reproduced (each cell stands alone).
//   * Confluence `<ac:*>` macros are stripped with a single warning.
//   * Remote `<img src="https://...">` are skipped (alt-text retained as text).
//
// Inline-SVG rendering (drawio / mermaid / PlantUML):
//   Two-tier rasteriser, see _html2docx_svg_render.js. Tier 1 = headless
//   Chrome / Chromium / Edge / Brave (auto-detected from conventional
//   install paths or HTML2DOCX_BROWSER) gives pixel-perfect CSS layout
//   including foreignObject labels and word-wrap. Tier 2 = @resvg/resvg-js
//   fallback for hosts without a browser, with foreignObject → SVG <text>
//   conversion in _html2docx_walker.js that synthesises a viewBox on
//   canvas-clipped diagrams (5% expansion absorbs drawio's edge-overshoot
//   artifact), preserves drawio's centring math (margin-left = container
//   left edge, x-anchor shifted to left+width/2 for justify-content:center),
//   and word-wraps long Cyrillic / Latin labels at the wrapper's `width:Npx`
//   so text fits inside its box.
//
// Optional flags:
//   --reader-mode   Replaces the default Confluence-priority candidate
//                   list with a curated reader-mode list:
//                     * Confluence/wiki selectors (#main-content, .wiki-
//                       content) — accepted at any text length.
//                     * CMS/blog classes (.entry, .post-content, …) — must
//                       have ≥500 chars to filter out archive-page excerpts.
//                     * Generic semantics (article, [role=main]) — ≥500
//                       chars; bare `<main>` deliberately omitted because
//                       on news/blog sites it wraps the entire chrome.
//                   Within each candidate, picks the LONGEST match — handles
//                   archive pages with multiple `.entry` divs and Disqus
//                   threads where comment <article>s would otherwise beat
//                   the post body.
//
// Environment variables:
//   HTML2DOCX_BROWSER          /path/to/chrome — explicit override; setting
//                              it to a non-existent path forces Tier-2
//                              (resvg-js) for CI determinism.
//   HTML2DOCX_ALLOW_NO_SANDBOX 1 — drop Chrome's --no-sandbox guard.
//                              Default leaves the sandbox enabled. Only
//                              set inside a trusted CI container; untrusted
//                              SVG (Confluence drawio can include external
//                              xlink images) under --no-sandbox would let
//                              any browser-process exploit reach the host.

const fs = require('fs');
const path = require('path');
const cheerio = require('cheerio');
const {
    Document, Packer, Paragraph, TextRun, Header, Footer, PageNumber,
    LevelFormat, AlignmentType, HeadingLevel,
} = require('docx');

const archive = require('./_html2docx_archive');
const walker = require('./_html2docx_walker');

// --- CLI parsing ---------------------------------------------------------
const argv = process.argv.slice(2);
let inputFile, outputFile, headerText, footerText;
let jsonErrors = false;
let readerMode = false;
const positional = [];
for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--header' && i + 1 < argv.length) headerText = argv[++i];
    else if (argv[i] === '--footer' && i + 1 < argv.length) footerText = argv[++i];
    else if (argv[i] === '--json-errors') jsonErrors = true;
    else if (argv[i] === '--reader-mode') readerMode = true;
    else positional.push(argv[i]);
}
inputFile = positional[0];
outputFile = positional[1];

// --- cross-5 envelope ----------------------------------------------------
// Mirrors scripts/_errors.py shape: single line, schema-versioned (v=1).
function reportError(msg, code, type, details) {
    if (code === 0) {
        details = Object.assign({ coerced_from_zero: true }, details || {});
        code = 1;
    }
    if (jsonErrors) {
        const env = { v: 1, error: String(msg), code };
        if (type) env.type = type;
        if (details && Object.keys(details).length) env.details = details;
        process.stderr.write(JSON.stringify(env) + '\n');
    } else {
        process.stderr.write(String(msg) + '\n');
    }
    process.exit(code);
}

if (!inputFile || !outputFile) {
    reportError(
        'Usage: node html2docx.js <input.html|.htm|.webarchive|.mhtml> <output.docx> [--header "text"] [--footer "text"] [--reader-mode] [--json-errors]',
        2, 'UsageError'
    );
}

const inputFileAbs = path.resolve(inputFile);
const outputFileAbs = path.resolve(outputFile);

// --- cross-7 H1 same-path guard ------------------------------------------
function realPathOrSelf(p) {
    try { return fs.realpathSync.native(p); } catch (_) { return p; }
}
if (realPathOrSelf(inputFileAbs) === realPathOrSelf(outputFileAbs)) {
    reportError(
        `Refusing to overwrite input file: ${inputFile}`,
        6, 'SelfOverwriteRefused',
        { input: inputFileAbs, output: outputFileAbs }
    );
}

if (!fs.existsSync(inputFileAbs)) {
    reportError(`Input HTML not found: ${inputFile}`, 1, 'FileNotFound', { path: inputFileAbs });
}

// --- format dispatch -----------------------------------------------------
let rawHtml;
let inputDir = path.dirname(inputFileAbs);
const fmt = archive.detectInputFormat(inputFileAbs);
if (fmt === 'webarchive') {
    const ex = archive.extractWebArchive(inputFileAbs, reportError);
    rawHtml = ex.html;
    inputDir = ex.tmpDir;
} else if (fmt === 'mhtml') {
    const ex = archive.extractMhtml(inputFileAbs, reportError);
    rawHtml = ex.html;
    inputDir = ex.tmpDir;
} else {
    rawHtml = fs.readFileSync(inputFileAbs, 'utf-8');
}

// --- parse + sanitize ---------------------------------------------------
const $ = cheerio.load(rawHtml, { decodeEntities: true });
$('script, style, head, form, input, textarea, select, noscript, template, link, meta').remove();

// Drop site-injected anchor / "copy heading link" / sort-UI / "expand
// source" buttons WHOLE before the generic button-unwrap below. These
// elements are pure UI chrome — leaving them as text leaks "Copy" /
// "Скопировано!" / "Копировать как текст" / "Развернуть исходный код"
// into the body of the document. Mirrors the PDF skill's
// `_NORMALIZE_CSS` rule #7 (display:none) — for docx we drop the nodes
// outright since there's no CSS layer.
//
// Match conventions across the corpus:
//   * Confluence: `.copy-heading-link-container/button`,
//     `.collapse-source.expand-control`, `.expand-control-text`,
//     `<a class="copy-link-button">`, `<button class="anchor-link">`,
//     code-panel header chrome (`.codeHeader span.expand-control`).
//   * Confluence DC: `[class*="buttonContainer"]` (hashed wrapper around
//     "Включить перенос текста" / "Копировать как текст" buttons inside
//     the new editor's code blocks; literal `.buttonContainer` would
//     NOT match because Atlassian hashes the class).
//   * Sphinx / MkDocs: `.headerlink`, `a.anchor`, `.anchor-link`.
//   * GitHub / Octicon: `.octicon-link`.
//   * Mintlify / Docusaurus: `.heading-anchor`, `button.anchorjs-link`.
//   * Universal: `<button>` inside any `<h1>…<h6>` (anchor-link buttons).
const CHROME_BUTTON_SELECTORS = [
    '.copy-heading-link-container', '.copy-heading-link-button',
    '.copy-link-button', '.copy-button', '.copybtn',
    '.headerlink', '.anchor-link', 'a.anchor', '.octicon-link',
    '.heading-anchor', 'button.anchorjs-link',
    '.collapse-source.expand-control', '.expand-source.expand-control',
    '.expand-control-text', '.expand-source-text',
    '[class*="buttonContainer"]',                  // Confluence DC code panel
    'h1 > button', 'h2 > button', 'h3 > button',
    'h4 > button', 'h5 > button', 'h6 > button',
    // GitBook "Copy page" / "Copy as Markdown" button at page header
    // (NOT marked `print:hidden`, so the print-hidden strip below
    // misses it). Anchored selectors — substring `*="Copy"` would
    // strip a substantive button labelled "Copy of contract" /
    // "Copy editor". Patterns covered:
    //   * exact "Copy" / "Copied" / "Скопировать" (lone-word UI chrome)
    //   * "Copy <something>" prefix: "Copy page", "Copy code",
    //     "Copy URL", "Copy as Markdown", "Copy link", "Copy snippet".
    //   * data-testid hooks shipped by Mintlify, Fern, Docusaurus.
    'button[aria-label="Copy"]',
    'button[aria-label="Copied"]',
    'button[aria-label="Скопировать"]',
    'button[aria-label="Скопировано"]',
    'button[aria-label^="Copy "]',
    'button[aria-label^="Скопировать "]',
    'button[data-testid="copy-code-button"]',
    'button[data-testid="copy-button"]',
];
$(CHROME_BUTTON_SELECTORS.join(',')).remove();

// Strip duplicate floating header rows emitted by Confluence's
// tablesorter plugin (`<thead class="tableFloatingHeader">` is a
// JS-cloned copy of `tableFloatingHeaderOriginal` for sticky-scroll;
// in docx both render → user sees every column header twice).
// Also drop any element with inline `display: none` — same `tablesorter`
// ships the cloned thead with `style="display: none"` on initial load.
// Plus any element class-marked `print:hidden` (Tailwind 3+ print
// modifier) — GitBook's hover-revealed "Copy" button on every code
// block uses exactly this class; a docx is a printable export, so the
// design intent matches removal.
$('thead.tableFloatingHeader, [style*="display: none"], [style*="display:none"], [class*="print:hidden"]').remove();

// Strip UI icon `<svg>`s — anchor markers, copy-code overlays, callout
// glyphs, sparkle icons. Without site CSS these render at their declared
// viewBox size and pepper the document with full-paragraph icons. Mirror
// the PDF skill's `_strip_icon_svgs` (commit 3857d6d + iter-5 fixes):
//
//   1. `aria-hidden="true"` is the W3C-standard decorative marker.
//   2. FontAwesome `prefix="fa*"` attribute is always an icon.
//   3. ALL declared explicit numeric width/height ≤ 64 px.
//      AND-rule (not OR): single-axis-small SVGs (50×500 vertical
//      timeline) are content. Both axes must be small to qualify.
//   4. Tailwind `h-N`/`w-N`/`size-N` class with N ≤ 16 (= 64 px).
//   5. Inline `style:width/height ≤ 64 px` (both axes).
//   6. ViewBox max-dim ≤ 64 fallback (Mintlify info-callout pattern:
//      `<svg viewBox="0 0 20 20" aria-label="Info">` has no explicit
//      dims and would otherwise render at 100 % of its container).
//   7. GitBook-specific `gb-icon` class — ships with Tailwind sizes
//      that don't match rule 4 (`size-text-lg`, `size-text-base`).
//   8. SVG with no dims AND no viewBox AND content is `<mask>` or
//      `<image>` referencing FontAwesome / icon fonts (FontAwesome 7
//      "kit" pattern: <svg><mask><image href="…fontawesome…"/></mask>).
const _ICON_MAX_PX = 64;
const _TAILWIND_ICON_RE = /\b(?:[hw]-|size-)(?:[1-9]|1[0-6])\b/;
const _GBOOK_ICON_RE = /\bgb-icon\b/;
function _isIconSvg($svg) {
    const ariaHidden = ($svg.attr('aria-hidden') || '').toLowerCase();
    if (ariaHidden === 'true') return true;
    const prefix = ($svg.attr('prefix') || '').toLowerCase();
    if (/^f[arsblkd]+$/.test(prefix)) return true;
    const wAttr = $svg.attr('width');
    const hAttr = $svg.attr('height');
    const num = (s) => {
        if (!s) return null;
        const m = String(s).match(/^(\d+(?:\.\d+)?)(?:px)?$/);
        return m ? parseFloat(m[1]) : null;
    };
    const wn = num(wAttr), hn = num(hAttr);
    const explicit = [wn, hn].filter(v => v !== null);
    if (explicit.length && explicit.every(v => v <= _ICON_MAX_PX)) {
        return true;
    }
    const cls = $svg.attr('class') || '';
    if (_TAILWIND_ICON_RE.test(cls)) return true;
    if (_GBOOK_ICON_RE.test(cls)) return true;
    const style = $svg.attr('style') || '';
    const sw = style.match(/\bwidth\s*:\s*(\d+(?:\.\d+)?)\s*(?:px|em|rem)?/i);
    const sh = style.match(/\bheight\s*:\s*(\d+(?:\.\d+)?)\s*(?:px|em|rem)?/i);
    if (sw && sh) {
        if (parseFloat(sw[1]) <= _ICON_MAX_PX && parseFloat(sh[1]) <= _ICON_MAX_PX) {
            return true;
        }
    }
    // Final fallback: small viewBox with no explicit dims AND no Tailwind
    // class — Mintlify "Info" callouts ship as
    // `<svg viewBox="0 0 20 20" aria-label="Info">`.
    if (explicit.length === 0 && !_TAILWIND_ICON_RE.test(cls) && (!sw || !sh)) {
        const vb = $svg.attr('viewBox');
        if (vb) {
            const parts = vb.trim().split(/[\s,]+/).map(parseFloat);
            if (parts.length === 4 && !parts.some(isNaN)) {
                if (Math.max(parts[2], parts[3]) <= _ICON_MAX_PX) return true;
            }
        }
    }
    // FontAwesome-7 "kit" pattern: <svg> with no dims AND no viewBox
    // containing a <mask> (the FA kit always uses <mask> with an inner
    // <image href="…fontawesome…"/>). Restricted to `<mask>` only —
    // `<image>` alone could be a content raster wrapped in SVG, and
    // `<use>` alone is the standard sprite pattern (logo / illustration
    // sites legitimately ship `<svg><use href="#sprite-logo"/></svg>`).
    if (explicit.length === 0 && !$svg.attr('viewBox')) {
        if ($svg.find('mask').length) return true;
    }
    return false;
}
$('svg').each((_, el) => {
    const $svg = $(el);
    if (_isIconSvg($svg)) $svg.remove();
});

// Drop INACTIVE Radix / Headless-UI tab triggers. SPA tab widgets
// (Fern's `<button role="tab">`, Mintlify, Docusaurus) only render the
// *active* tabpanel into the DOM — inactive panels are loaded on click
// via JS and don't exist in a saved webarchive. Leaving the inactive
// tab buttons in place leaks their labels ("TypeScript (fetch)",
// "Shell") into the document body as orphaned headings with no code
// content beneath. Strip them. The single `aria-selected="true"` tab
// still acts as the language label for the visible code block.
$('[role="tab"][aria-selected="false"], [role="tab"][data-state="inactive"]').remove();

// Flatten shiki / Fern-style table-based code blocks. Modern syntax
// highlighters (shiki, prism-react, fern) render `<pre>` containing a
// `<table>` where each `<tr>` is one source line: `<td>` gutter
// (line number) + `<td>` content. The walker's emitPre uses
// `$(el).text()` which concatenates all descendant text without
// preserving table-row boundaries — output looks like
// "1import requests2import json3 4response = requests.post(...".
// Fix: walk each `<tr>`, take the LAST `<td>`'s text (last column is
// always the content; first is the gutter when `<tr>` has 2 cells),
// join with `\n`, replace the entire `<pre>` body with that plain text.
//
// Gate strictly on a code-highlighter marker so that a docs page
// demonstrating raw `<table>` markup INSIDE `<pre>` (legit ASCII-art
// example) is not silently rebuilt. Markers cover the common
// highlighters: shiki / prism / Fern / Mintlify (`code-block-*`,
// `language-*`, `shiki`, `prism-code`, `fern-code-content`).
const _CODE_PRE_MARKER = /\b(shiki|prism-code|prism-react-renderer|fern-code|code-block(-root|-line-group|-content)?|language-)/;
$('pre').each((_, pre) => {
    const $pre = $(pre);
    const cls = $pre.attr('class') || '';
    if (!_CODE_PRE_MARKER.test(cls)) {
        // Also accept when the inner <table> carries the marker
        // (Fern renders `<table class="code-block-line-group">`).
        const $tbl = $pre.find('table').first();
        if (!$tbl.length || !_CODE_PRE_MARKER.test($tbl.attr('class') || '')) {
            return;
        }
    }
    const $rows = $pre.find('tr');
    if (!$rows.length) return;
    const lines = [];
    $rows.each((__, tr) => {
        const $tds = $(tr).children('td');
        if ($tds.length === 0) return;
        // If 2+ cells assume first is gutter; take last. If 1 cell, use it.
        const $content = $tds.length >= 2 ? $tds.last() : $tds.first();
        lines.push($content.text());
    });
    if (lines.length) {
        $pre.empty().text(lines.join('\n'));
    }
});

// Convert ARIA-role tables to real <table>s. GitBook (and some Notion /
// Material themes) build their data tables out of
// `<div role="table">` / `<div role="row">` / `<div role="cell">`
// instead of native HTML. The W3C ARIA spec says these MUST be visually
// equivalent to a `<table>`, so we honour the contract universally
// rather than per-platform. Without this rewrite, the walker treats
// each div as block-flow and emits one cell per paragraph — collapsing
// 3-column field tables (Name / Type / Description) to a tall vertical
// strip. Mirrors the PDF skill `_NORMALIZE_CSS` rule #7c (commit
// `a7fbc9f`); for docx we rewrite the DOM since there's no CSS layer.
$('[role="table"]').each((_, el) => { el.tagName = 'table'; });
$('[role="rowgroup"]').each((_, el) => {
    // Heuristic: rowgroups containing role=columnheader are <thead>;
    // others become <tbody>. drawio / Mintlify don't emit rowgroups
    // explicitly (rows are direct children of the table), so this only
    // fires on GitBook-style tables which have explicit grouping.
    el.tagName = $(el).find('[role="columnheader"]').length ? 'thead' : 'tbody';
});
$('[role="row"]').each((_, el) => { el.tagName = 'tr'; });
$('[role="columnheader"]').each((_, el) => { el.tagName = 'th'; });
$('[role="cell"]').each((_, el) => { el.tagName = 'td'; });

// Mintlify Steps component (also Fern, Docusaurus): a numbered
// procedure rendered as
//   <div role="list" class="steps">
//     <div role="listitem" class="step">
//       <div data-component-part="step-line">…</div>     ← decorative bar
//       <div data-component-part="step-number">1</div>   ← number badge
//       <div>
//         <p data-component-part="step-title">Title</p>
//         <div data-component-part="step-content">…</div>
//       </div>
//     </div>
//     …
//   </div>
// Flatten each step to a `<h4>N. Title</h4>` followed by the step
// content. We can NOT convert `role="list"` → `<ol>` here because the
// walker's emitList walks each `<li>`'s children via walkInline only —
// any block content inside (`<pre>` code, multiple `<p>`s) gets
// squished into a single inline-only list-item paragraph, losing
// monospace formatting and paragraph breaks. Flattening to `<h4>` +
// siblings sidesteps that limitation: each step's content remains at
// the document root and renders with its native block semantics
// (Courier-shaded `<pre>`, separate paragraphs, etc.).
$('[data-component-part="step-line"], [data-component-part="step-number"]').remove();
$('[role="list"]:has([data-component-part="step-title"])').each((_, list) => {
    const $list = $(list);
    const pieces = [];
    let n = 0;
    $list.children('[role="listitem"]').each((__, item) => {
        n++;
        const $item = $(item);
        // Use .html() to preserve inline markup in titles (`<code>npm
        // install</code>`, `<strong>note</strong>`) — Mintlify allows
        // arbitrary inline content inside <Step title="…">. .text()
        // would silently strip it. The literal "N. " prefix is plain
        // text appended in front of the inner HTML.
        const titleHtml = ($item.find('[data-component-part="step-title"]').first().html() || '').trim();
        const $content = $item.find('[data-component-part="step-content"]').first();
        pieces.push(`<h4>${n}. ${titleHtml}</h4>`);
        if ($content.length) pieces.push($content.html() || '');
    });
    $list.replaceWith(pieces.join('\n'));
});
// Generic ARIA-list conversion for role="list"/listitem that is NOT
// a Mintlify Steps component (ARIA recommends them for any visually
// list-styled set). Emitting an actual `<ol>`/`<ul>` lets the walker
// preserve the bullet/number layout. (Plain text-only items work fine
// inside the walker's emitList; only nested-block-in-li loses fidelity.)
$('[role="list"]').each((_, el) => { el.tagName = 'ol'; });
$('[role="listitem"]').each((_, el) => { el.tagName = 'li'; });

// Unwrap <button> rather than removing it. Confluence's tablesorter wraps
// the header text of every <th> in <button class="headerButton">…</button>
// — stripping the button kills the column titles. Unwrap = keep children,
// drop the tag.
$('button').each((_, el) => $(el).replaceWith($(el).contents()));

// Strip site chrome by ARIA landmark roles. Confluence wraps the
// header/sidebar/footer in role=banner / complementary / contentinfo /
// navigation / search — none of which belong in an exported article.
$('[role="banner"], [role="complementary"], [role="contentinfo"], [role="navigation"], [role="search"]').remove();

// Confluence-specific chrome IDs that escape the role sweep above
// (e.g. legacy templates that don't apply ARIA roles). NOTE: we
// intentionally do NOT include #title-heading here — its <h1> is the
// article's actual page title, extracted separately below.
$('#header, #footer, #navigation, #navigation-next, #breadcrumb-section, #breadcrumbs, #page-metadata, #likes-and-labels-container, .page-metadata, .pageSection.group, .acs-side-bar, .ia-secondary-content, .acs-nav-children-pages, #comments-section, #footer-logo, #space-tools-menu').remove();

// Snapshot the original body-text length BEFORE the reader-mode chrome
// strip. pickContentRoot's `<main>` body-ratio guard compares
// main_text / body_text — if we measured body AFTER stripping, the
// denominator is already shrunken by however much chrome we removed,
// and the empirically-calibrated 0.95 threshold drifts as the keyword
// list grows. Capture once, before any reader-mode-specific strip.
const _originalBodyText = $('body').text().trim().length || 1;

// Reader-mode-only chrome strips. Match SPA-blog inline widgets that
// `.entry` / `<article>` wrappers commonly include alongside the post
// body — vc.ru's `<div class="entry">` contains the article PLUS a
// recommendation carousel, a comments thread, and a related-articles
// block all as siblings. Without this strip, --reader-mode picks
// `.entry` correctly but the resulting docx still has 3-4× the
// legitimate text.
//
// Universal keyword-pattern matching via the CSS `[class*=KEYWORD]`
// substring selector — catches any class name containing the keyword
// regardless of prefix/suffix (e.g. `reaction` matches `reaction`,
// `content__reactions`, `reactions-bar`, `like-reaction`). Covers
// vc.ru, Habr, generic WordPress / blog frameworks without naming
// each variant.
//
// Substring vs. word-boundary trade-off: word-boundary correctly
// rejects BEM modifier positions (`tm-page__main_has-sidebar` won't
// match `sidebar`) but also rejects plural / morphological variants
// (`content__reactions` doesn't match the keyword `reaction`).
// Real-world widget classes are overwhelmingly plurals/compound
// nouns; BEM-modifier collisions are confined to a small set of
// generic words. We therefore use substring matching but EXCLUDE
// the generic words known to collide (`sidebar`, `widget`, `share`,
// `meta`, `tags`) from the keyword list and target their compound
// forms explicitly (`share-button`, `post-meta`, `entry-tags`, etc.).
//
// Default mode skips this strip because Confluence content uses
// `#main-content` which already excludes these wrappers; default-mode
// users see no benefit and lose the safety margin.
if (readerMode) {
    const READER_STRIP_KEYWORDS = [
        // Recommendation widgets / related-articles blocks
        'rotator', 'recommend', 'related-post', 'related-article',
        // Comment threads (whole section — not the single `<a href="#comments">`
        // counter link, which is small and harmless once unwrapped from
        // its hyperlink in the walker)
        'comments', 'discussion-list', 'replies-list',
        // Post-footer meta widgets: tags, share, subscribe, author bio
        'post-meta', 'entry-meta', 'post-tags', 'entry-tags',
        'post-share', 'entry-share', 'share-button', 'share-bar',
        'social-share', 'social-button',
        'subscribe-block', 'subscribe-form', 'newsletter',
        // vc.ru-style article-footer engagement widgets: emoji reactions
        // (`.content__reactions`), floating engagement bar
        // (`.content__floating`), and the post footer with comment-counter
        // and share buttons (`.content-footer`). Same patterns appear on
        // generic blogs as `.entry-footer` / `.post-footer`.
        'reaction', 'floating-bar', 'floating-engage',
        'content-footer', 'post-footer', 'entry-footer',
        // Ad / promo / sponsored blocks
        'ad-banner', 'ad-block', 'advert', 'sponsor-block',
        'promo-block', 'ya-ai',
        // Cookie / GDPR consent prompts
        'cookie-banner', 'cookie-consent', 'gdpr-',
        // NB: deliberately NOT including `sidebar`, `widget`, or
        // `share`/`meta`/`tags` alone — those substrings appear in BEM
        // modifier positions on Habr (e.g. `tm-page__main_has-sidebar`
        // is the MAIN article wrapper, not a sidebar) and would strip
        // legitimate body content. Use compound forms (`share-button`,
        // `post-meta`) to target the actual widget classes.
        // Honest scope: substring matching can over-strip on niche
        // articles where the topic literally mentions the keyword
        // (e.g. a chemistry article with `<figure class="reaction-
        // diagram">`). Reader-mode is an opt-in degraded view; users
        // who need precise control should use default mode and
        // post-process.
    ];
    const stripSelector = READER_STRIP_KEYWORDS
        .map(kw => `[class*="${kw}"]`)
        .join(',');
    $(stripSelector).remove();
}

// Promote Prism / Confluence DC code blocks to <pre>. Newer Confluence
// editors and many docs sites (Mintlify, Docusaurus, MkDocs, the new
// Atlassian DC editor) ship code as
//     <div class="codeBlockContainer_HASH">
//       <code class="language-sql" style="white-space: pre;">…spans…</code>
//     </div>
// or
//     <div class="code panel pdl conf-macro output-block">…<code>…</code>…</div>
// — WITHOUT a wrapping <pre>. The walker's default branch then treats
// the <code> as inline content and flattens 50+ lines of SQL into a
// single Arial-12pt paragraph (no monospace, no preserved newlines, no
// indentation). This mirrors the PDF skill's commit 29bc370 wrap fix
// — but for docx the "wrap" is conceptual: route the code through
// emitPre so it renders as a Courier-10pt shaded block. We use
// `code[class*="language-"]` (the Prism / shiki / highlight.js
// convention) plus the two Confluence-specific class chains;
// `[class*="codeBlockContainer"]` matches the hashed Confluence DC
// form (`codeBlockContainer_yyk2gsoAwjaamghp6yoO-Q==`) which a literal
// `.codeBlockContainer` selector would NOT (CSS class selectors don't
// prefix-match).
$('code[class*="language-"], .code.panel code, [class*="codeBlockContainer"] code').each((_, el) => {
    const $code = $(el);
    if ($code.parents('pre').length) return;       // already in <pre>
    if ($code.parents('code').length) return;      // nested <code>: skip
    $code.wrap('<pre></pre>');
});

// Hoist any <pre> that landed inside an inline ancestor up to its
// nearest block ancestor. Confluence DC wraps Prism code in
// `<span data-code-lang="sql" class="prismjs">…<code>…</code>…</span>`
// — once we wrap that <code> in <pre>, the result is `<pre>` inside
// `<span>`. The walker dispatches on tagName: at the block level it
// sees `<span>` and falls into the inline path (walkInline), which
// emits ALL descendant text as one paragraph — newlines collapsed,
// monospace lost, 50+ lines of SQL flattened to a single block.
// Repeatedly unwrap inline ancestors of every <pre> until its parent
// is a block element. Safe because the inline ancestors here are
// pure markup wrappers (data-* attrs, class) with no semantic meaning
// for a docx renderer; we keep ALL their text content (children move
// up). Run this AFTER the wrap step so newly-created <pre>s are
// caught too.
const _INLINE_RE = /^(span|a|em|strong|b|i|u|sup|sub|small|mark|font|code|cite|q|abbr|kbd|var|samp|time)$/;
$('pre').each((_, pre) => {
    const $pre = $(pre);
    while (true) {
        const $parent = $pre.parent();
        if (!$parent.length) break;
        const tag = ($parent.prop('tagName') || '').toLowerCase();
        if (!_INLINE_RE.test(tag)) break;
        $parent.replaceWith($parent.contents());
    }
});

// Confluence TOC double-numbering fix: the macro emits an <ol> wrapping
// links whose label often ALREADY starts with "3.", "4.1.1" etc. (because
// the wiki author numbered the source heading). Add to that the auto
// numbering my walker applies to <ol>, and the result is "4. 3. Heading"
// (visible as "43. Heading" once spaces collapse). Convert toc <ol>'s to
// <ul> so the wrapping stays as a bullet list and the existing in-text
// numbers carry the hierarchy alone. Also drop <span class="toc-outline">
// (Confluence's pre-computed outline number) which is redundant with the
// numeric prefix already in the heading.
$('.toc-macro ol').each((_, el) => { el.name = 'ul'; });
$('.toc-outline').remove();

let confluenceWarned = false;
$('*').each((_, el) => {
    if (el.type === 'tag' && el.name && el.name.includes(':')) {
        if (!confluenceWarned) {
            console.warn('html2docx: stripped Confluence-style namespaced elements (ac:*, ri:*, etc.)');
            confluenceWarned = true;
        }
        $(el).remove();
    }
});

// Find the article-content root. Two distinct modes:
//
//   Default: Confluence-priority list, first-match wins. Backwards
//            compatible with pre-reader-mode behaviour. No min-text
//            filter — Confluence pages with mostly diagrams (< 500
//            chars of body text) still get correctly extracted.
//
//   --reader-mode: curated list optimised for browser-saved blog /
//            news / wiki pages. Each candidate has its OWN min-text
//            threshold:
//              * High-confidence selectors (Confluence IDs, .wiki-content)
//                — minText:1 because diagram-heavy KB pages legitimately
//                have very little body text and we trust the selector.
//              * Specific blog/CMS classes (.entry, .post-content) —
//                minText:500 to skip excerpts on archive index pages.
//              * Generic semantics (article, [role=main], main#main) —
//                minText:500 to skip empty <article> shells in nav.
//              * Bare `<main>` is INTENTIONALLY OMITTED in reader mode:
//                on vc.ru / Habr / many news sites it wraps the entire
//                site (header + body + footer + recommendations), so
//                including it would defeat the whole point of the flag.
//            Within each selector, picks the LONGEST match — handles
//            archive pages with multiple `.entry` divs (the post body
//            is longer than each excerpt) and Disqus comment threads
//            (post body is longer than any single comment).
const _BASE_CANDIDATES = [
    '#main-content',          // Confluence (modern), GitLab wiki
    '[role="main"]',
    'main#main',
    'main[role="main"]',
    'article',
    '.wiki-content',          // Confluence (legacy / current)
    '#content .pageSection',  // Confluence fallback
    '#content',
    'main',
];

const _READER_CANDIDATES = [
    // High-confidence: Confluence/wiki conventions. No min-text — diagram-
    // heavy KB pages legitimately have < 500 chars and we trust the selector.
    { sel: '#main-content',          minText: 1 },
    { sel: '.wiki-content',          minText: 1 },
    { sel: '#content .pageSection',  minText: 1 },
    { sel: '#content',               minText: 1 },
    // Specific CMS / blog classes. Min-text filters out excerpts in archive
    // index pages and metadata divs (.entry-meta, .post-meta on some themes).
    { sel: '.entry',                 minText: 500 },
    { sel: '.post-content',          minText: 500 },
    { sel: '.article-content',       minText: 500 },
    { sel: '.main-content',          minText: 500 },
    { sel: 'div.article',            minText: 500 },
    // Generic semantics. Stronger filter because false positives are
    // common — sites use <article> for comments, [role=main] for nav.
    { sel: 'article',                minText: 500 },
    { sel: '[role="main"]',          minText: 500 },
    { sel: 'main[role="main"]',      minText: 500 },
    { sel: 'main#main',              minText: 500 },
    // Bare `main` deliberately omitted from this list — it's tried with a
    // body-ratio guard below, see pickContentRoot().
];

function pickContentRoot($, opts) {
    const reader = !!(opts && opts.readerMode);
    if (reader) {
        // Reader mode: curated list, longest-within-selector, per-candidate
        // min-text. First selector that yields ANY qualifying match wins.
        for (const { sel, minText } of _READER_CANDIDATES) {
            let bestNode = null;
            let bestLen = 0;
            $(sel).each((_, el) => {
                const len = $(el).text().trim().length;
                if (len >= minText && len > bestLen) {
                    bestNode = el;
                    bestLen = len;
                }
            });
            if (bestNode) return { node: bestNode, selector: sel };
        }
        // Last-resort: bare `<main>` with a body-ratio guard. Used on
        // sites that have `<main>` but no other recognised wrapper class
        // (mobile-review.com, classic WP-block blogs). On vc.ru / Habr
        // `<main>` typically isn't present at all; on news SPAs that DO
        // use `<main>` to wrap the whole site (chrome included), its
        // text is ≥ 95-99% of `<body>`'s, so the ratio guard rejects it.
        // 0.95 was chosen empirically: mobile-review's article-only
        // `<main>` is ~89% of body (header+footer chrome outside is
        // ~11%); chrome-wrapping `<main>` on tested SPA blogs sits at
        // 96-99%. The denominator MUST be the original body text length
        // (captured before reader-mode strip) — measuring after-strip
        // body would drift the calibration as the keyword list grows.
        const bodyText = (opts && opts.originalBodyText) ||
                         ($('body').text().trim().length || 1);
        // HTML5 forbids multiple `<main>` per document but real-world
        // pages violate this (template injection, third-party widgets).
        // Prefer the FIRST `<main>` that satisfies the guard rather
        // than the longest — the first is far more likely to be the
        // primary article wrapper than a duplicate from a misbehaving
        // template.
        let pickedMain = null;
        $('main').each((_, el) => {
            if (pickedMain) return;
            const len = $(el).text().trim().length;
            if (len >= 500 && len / bodyText < 0.95) pickedMain = el;
        });
        if (pickedMain) return { node: pickedMain, selector: 'main (body-ratio<0.95)' };
    } else {
        // Default: Confluence-priority first-match (preserves the
        // pre-reader-mode behaviour byte-for-byte).
        for (const sel of _BASE_CANDIDATES) {
            const hit = $(sel).first();
            if (hit.length && hit.text().trim().length > 0) {
                return { node: hit[0], selector: sel };
            }
        }
    }
    return { node: $('body').length ? $('body')[0] : $.root()[0], selector: 'body' };
}

const picked = pickContentRoot($, {
    readerMode,
    originalBodyText: _originalBodyText,
});
if (picked.selector !== 'body') {
    console.log(`html2docx: article root detected via "${picked.selector}" (chrome stripped)`);
}
const root = picked.node;

// Extract the page title from outside #main-content (Confluence puts the
// real article title in <h1> inside #title-heading, which is a sibling
// of #main-content and would otherwise be lost when we narrow the root).
function extractPageTitle($) {
    const candidates = [
        '#title-text',
        '#title-heading h1',
        '#title-heading',
        'header.page-title h1',
        'header h1',
    ];
    for (const sel of candidates) {
        const node = $(sel).first();
        if (!node.length) continue;
        const text = node.text().replace(/\s+/g, ' ').trim();
        if (text && text.length < 500) return text;
    }
    return null;
}
const pageTitle = picked.selector !== 'body' ? extractPageTitle($) : null;

// --- walk + assemble -----------------------------------------------------
let body;
try {
    body = walker.buildBody({
        $, root, inputDir, extractedImages: archive.extractedImages,
    });
} catch (err) {
    reportError(err && err.message ? err.message : String(err), 1, 'WalkError');
}

// Prepend the page title as Heading 1 (if we sniffed one out from chrome
// before we narrowed the root). docx-js infers the H1 paragraph style
// from `heading: HeadingLevel.HEADING_1` plus the document-level
// paragraphStyles config (32pt, bold).
const documentChildren = [];
if (pageTitle) {
    documentChildren.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: pageTitle })],
    }));
}
documentChildren.push(...body.children);

const section = {
    properties: {
        page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
    },
    children: documentChildren.length ? documentChildren : [new Paragraph({ children: [] })]
};

if (headerText) {
    section.headers = {
        default: new Header({
            children: [new Paragraph({
                children: [new TextRun({ text: headerText, font: "Arial", size: 20, color: "888888" })],
                alignment: AlignmentType.RIGHT
            })]
        })
    };
}

if (footerText || headerText) {
    section.footers = {
        default: new Footer({
            children: [new Paragraph({
                children: [
                    ...(footerText ? [
                        new TextRun({ text: footerText, font: "Arial", size: 18, color: "888888" }),
                        new TextRun({ text: "    ", font: "Arial", size: 18 })
                    ] : []),
                    new TextRun({ text: "Стр. ", font: "Arial", size: 18, color: "888888" }),
                    new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: "888888" })
                ],
                alignment: footerText ? AlignmentType.CENTER : AlignmentType.RIGHT
            })]
        })
    };
}

const doc = new Document({
    numbering: {
        config: [
            {
                reference: "bullets",
                levels: [
                    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
                    { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
                    { level: 2, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 2160, hanging: 360 } } } },
                ]
            },
            ...body.numberedListConfigs
        ]
    },
    styles: {
        default: { document: { run: { font: "Arial", size: 24 } } },
        paragraphStyles: [
            {
                id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
                run: { size: 32, bold: true, font: "Arial" },
                paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 }
            },
            {
                id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
                run: { size: 28, bold: true, font: "Arial" },
                paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 }
            },
            {
                id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
                run: { size: 24, bold: true, font: "Arial" },
                paragraph: { spacing: { before: 120, after: 120 }, outlineLevel: 2 }
            },
        ]
    },
    sections: [section]
});

Packer.toBuffer(doc)
    .then(buffer => {
        fs.writeFileSync(outputFile, buffer);
        console.log(`Document generated at ${outputFile}`);
    })
    .catch(err => {
        reportError(err && err.message ? err.message : String(err), 1, 'PackError');
    });
