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
