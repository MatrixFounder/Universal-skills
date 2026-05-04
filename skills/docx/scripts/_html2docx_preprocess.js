// _html2docx_preprocess.js — DOM preprocessing pipeline for html2docx.
//
// Extracted from html2docx.js (q-7) so each preprocessing stage is
// independently exercisable from tests/test_html2docx_preprocess.test.js.
// Each exported function takes a cheerio instance `$` and mutates the
// DOM in-place — same semantics as the inline code that lived directly
// after `cheerio.load()` in the CLI script.
//
// The orchestrator `preprocessDom($, { readerMode, onWarn })` runs the
// stages in the canonical order and returns `{ originalBodyText }`, the
// snapshot of `$('body').text().trim().length` taken between the chrome
// strip and the reader-mode keyword strip (used by pickContentRoot's
// body-ratio guard in html2docx.js — measuring after-strip body would
// drift the calibration as the keyword list grows).

// --- Stage 1: chrome buttons --------------------------------------------
//
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
    // misses it).
    //
    // q-7 MED-2 fix: prefix-anchored `aria-label^="Copy "` matched ANY
    // button starting with "Copy " — including substantive labels like
    // "Copy of contract" / "Copy editor" — and silently shredded the
    // text. Replaced with an explicit allowlist of known chrome
    // variants. False-negative (a future "Copy GraphQL" chrome variant
    // we forgot to add) is preferable to false-positive (silently
    // destroying body content).
    //
    // Coverage:
    //   * exact "Copy" / "Copied" / "Скопировать" / "Скопировано"
    //     (lone-word UI chrome).
    //   * "Copy <target>" enumerated explicitly per real-world corpus:
    //     "Copy page" / "code" / "URL" / "link" / "snippet" /
    //     "command" / "to clipboard" / "as Markdown" / "as JSON".
    //   * Russian variants: "Скопировать ссылку" / "код" / "команду" /
    //     "в буфер".
    //   * data-testid hooks shipped by Mintlify, Fern, Docusaurus.
    'button[aria-label="Copy"]',
    'button[aria-label="Copied"]',
    'button[aria-label="Скопировать"]',
    'button[aria-label="Скопировано"]',
    'button[aria-label="Copy page"]',
    'button[aria-label="Copy code"]',
    'button[aria-label="Copy URL"]',
    'button[aria-label="Copy link"]',
    'button[aria-label="Copy snippet"]',
    'button[aria-label="Copy command"]',
    'button[aria-label="Copy to clipboard"]',
    'button[aria-label="Copy as Markdown"]',
    'button[aria-label="Copy as JSON"]',
    'button[aria-label="Скопировать ссылку"]',
    'button[aria-label="Скопировать код"]',
    'button[aria-label="Скопировать команду"]',
    'button[aria-label="Скопировать в буфер"]',
    'button[data-testid="copy-code-button"]',
    'button[data-testid="copy-button"]',
];

function stripChromeButtons($) {
    $(CHROME_BUTTON_SELECTORS.join(',')).remove();
}

// --- Stage 2: duplicate / hidden chrome ----------------------------------
//
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
function stripDuplicateAndHiddenChrome($) {
    $('thead.tableFloatingHeader, [style*="display: none"], [style*="display:none"], [class*="print:hidden"]').remove();
}

// --- Stage 3: icon SVG strip --------------------------------------------
//
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

function stripIconSvgs($) {
    $('svg').each((_, el) => {
        const $svg = $(el);
        if (_isIconSvg($svg)) $svg.remove();
    });
}

// --- Stage 4: inactive Radix / Headless-UI tab triggers -----------------
//
// Drop INACTIVE Radix / Headless-UI tab triggers. SPA tab widgets
// (Fern's `<button role="tab">`, Mintlify, Docusaurus) only render the
// *active* tabpanel into the DOM — inactive panels are loaded on click
// via JS and don't exist in a saved webarchive. Leaving the inactive
// tab buttons in place leaks their labels ("TypeScript (fetch)",
// "Shell") into the document body as orphaned headings with no code
// content beneath. Strip them. The single `aria-selected="true"` tab
// still acts as the language label for the visible code block.
function stripInactiveRadixTabs($) {
    $('[role="tab"][aria-selected="false"], [role="tab"][data-state="inactive"]').remove();
}

// --- Stage 5: shiki / Fern table-based code flatten ---------------------
//
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

function flattenTableBasedCode($) {
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
}

// --- Stage 6: ARIA-role tables → real <table>s --------------------------
//
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
function convertAriaTables($) {
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
}

// --- Stage 7: Mintlify Steps flatten ------------------------------------
//
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
function flattenMintlifySteps($) {
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
}

// --- Stage 8: generic ARIA list/listitem → <ol>/<li> --------------------
//
// Generic ARIA-list conversion for role="list"/listitem that is NOT
// a Mintlify Steps component (ARIA recommends them for any visually
// list-styled set). Emitting an actual `<ol>`/`<ul>` lets the walker
// preserve the bullet/number layout. (Plain text-only items work fine
// inside the walker's emitList; only nested-block-in-li loses fidelity.)
function convertAriaLists($) {
    $('[role="list"]').each((_, el) => { el.tagName = 'ol'; });
    $('[role="listitem"]').each((_, el) => { el.tagName = 'li'; });
}

// --- Stage 9: <button> unwrap -------------------------------------------
//
// Unwrap <button> rather than removing it. Confluence's tablesorter wraps
// the header text of every <th> in <button class="headerButton">…</button>
// — stripping the button kills the column titles. Unwrap = keep children,
// drop the tag.
function unwrapInlineButtons($) {
    $('button').each((_, el) => $(el).replaceWith($(el).contents()));
}

// --- Stage 10: ARIA landmark chrome strip -------------------------------
//
// Strip site chrome by ARIA landmark roles. Confluence wraps the
// header/sidebar/footer in role=banner / complementary / contentinfo /
// navigation / search — none of which belong in an exported article.
function stripAriaLandmarks($) {
    $('[role="banner"], [role="complementary"], [role="contentinfo"], [role="navigation"], [role="search"]').remove();
}

// --- Stage 11: Confluence chrome by ID/class ----------------------------
//
// Confluence-specific chrome IDs that escape the role sweep above
// (e.g. legacy templates that don't apply ARIA roles). NOTE: we
// intentionally do NOT include #title-heading here — its <h1> is the
// article's actual page title, extracted separately by html2docx.js.
function stripConfluenceChromeIds($) {
    $('#header, #footer, #navigation, #navigation-next, #breadcrumb-section, #breadcrumbs, #page-metadata, #likes-and-labels-container, .page-metadata, .pageSection.group, .acs-side-bar, .ia-secondary-content, .acs-nav-children-pages, #comments-section, #footer-logo, #space-tools-menu').remove();
}

// --- Stage 12 (gated): reader-mode keyword strip ------------------------
//
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

function stripReaderModeChrome($) {
    const stripSelector = READER_STRIP_KEYWORDS
        .map(kw => `[class*="${kw}"]`)
        .join(',');
    $(stripSelector).remove();
}

// --- Stage 13: Prism / Confluence DC inline-code → <pre><code> ----------
//
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
function wrapInlineCodeBlocks($) {
    $('code[class*="language-"], .code.panel code, [class*="codeBlockContainer"] code').each((_, el) => {
        const $code = $(el);
        if ($code.parents('pre').length) return;       // already in <pre>
        if ($code.parents('code').length) return;      // nested <code>: skip
        $code.wrap('<pre></pre>');
    });
}

// --- Stage 14: hoist <pre> out of inline ancestors ----------------------
//
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

function hoistPreFromInlineAncestors($) {
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
}

// --- Stage 15: Confluence TOC double-numbering fix ----------------------
//
// Confluence TOC double-numbering fix: the macro emits an <ol> wrapping
// links whose label often ALREADY starts with "3.", "4.1.1" etc. (because
// the wiki author numbered the source heading). Add to that the auto
// numbering my walker applies to <ol>, and the result is "4. 3. Heading"
// (visible as "43. Heading" once spaces collapse). Convert toc <ol>'s to
// <ul> so the wrapping stays as a bullet list and the existing in-text
// numbers carry the hierarchy alone. Also drop <span class="toc-outline">
// (Confluence's pre-computed outline number) which is redundant with the
// numeric prefix already in the heading.
function flattenTocDoubleNumbering($) {
    $('.toc-macro ol').each((_, el) => { el.name = 'ul'; });
    $('.toc-outline').remove();
}

// --- Stage 16: Confluence namespaced elements (ac:* / ri:*) -------------
//
// Strip Confluence's `<ac:foo>` / `<ri:bar>` macro markers. Issued ONCE
// regardless of how many such elements were dropped (otherwise the user
// sees a flood of identical warnings on a heavily Confluence-flavoured
// page). Pass an `onWarn` callback so html2docx.js can route the warning
// through `console.warn` while tests can capture and assert on it.
function stripConfluenceNamespacedElements($, options = {}) {
    // q-7 LOW-2: default to console.warn rather than a silent no-op.
    // Pre-q-7 the inline html2docx.js code at the call site always
    // emitted `console.warn(...)`. After the refactor, callers that
    // skip the orchestrator (composing only some stages directly)
    // would have lost the warning if we defaulted to no-op. Tests
    // pass `onWarn: () => warnCount++` to capture and count.
    const onWarn = options.onWarn || ((msg) => console.warn(msg));
    let warned = false;
    $('*').each((_, el) => {
        if (el.type === 'tag' && el.name && el.name.includes(':')) {
            if (!warned) {
                onWarn('html2docx: stripped Confluence-style namespaced elements (ac:*, ri:*, etc.)');
                warned = true;
            }
            $(el).remove();
        }
    });
}

// --- Orchestrator -------------------------------------------------------
//
// Runs every stage in the canonical order and returns the
// originalBodyText snapshot used by pickContentRoot's body-ratio
// guard. The snapshot is taken between the chrome strip and the
// reader-mode keyword strip — see comment at the snapshot point in
// the function body for the calibration rationale.
function preprocessDom($, options = {}) {
    const readerMode = !!options.readerMode;
    const onWarn = options.onWarn || ((msg) => console.warn(msg));

    stripChromeButtons($);
    stripDuplicateAndHiddenChrome($);
    stripIconSvgs($);
    stripInactiveRadixTabs($);
    flattenTableBasedCode($);
    convertAriaTables($);
    flattenMintlifySteps($);
    convertAriaLists($);
    unwrapInlineButtons($);
    stripAriaLandmarks($);
    stripConfluenceChromeIds($);

    // Snapshot the original body-text length BEFORE the reader-mode chrome
    // strip. pickContentRoot's `<main>` body-ratio guard compares
    // main_text / body_text — if we measured body AFTER stripping, the
    // denominator is already shrunken by however much chrome we removed,
    // and the empirically-calibrated 0.95 threshold drifts as the keyword
    // list grows. Capture once, before any reader-mode-specific strip.
    const originalBodyText = $('body').text().trim().length || 1;

    if (readerMode) stripReaderModeChrome($);

    wrapInlineCodeBlocks($);
    hoistPreFromInlineAncestors($);
    flattenTocDoubleNumbering($);
    stripConfluenceNamespacedElements($, { onWarn });

    return { originalBodyText };
}

module.exports = {
    // Orchestrator (used by html2docx.js).
    preprocessDom,
    // Individual stages (used by tests/test_html2docx_preprocess.test.js).
    stripChromeButtons,
    stripDuplicateAndHiddenChrome,
    stripIconSvgs,
    stripInactiveRadixTabs,
    flattenTableBasedCode,
    convertAriaTables,
    flattenMintlifySteps,
    convertAriaLists,
    unwrapInlineButtons,
    stripAriaLandmarks,
    stripConfluenceChromeIds,
    stripReaderModeChrome,
    wrapInlineCodeBlocks,
    hoistPreFromInlineAncestors,
    flattenTocDoubleNumbering,
    stripConfluenceNamespacedElements,
    // Internal helpers exposed for white-box testing.
    _isIconSvg,
    CHROME_BUTTON_SELECTORS,
    READER_STRIP_KEYWORDS,
};
