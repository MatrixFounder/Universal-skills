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
const positional = [];
for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--header' && i + 1 < argv.length) headerText = argv[++i];
    else if (argv[i] === '--footer' && i + 1 < argv.length) footerText = argv[++i];
    else if (argv[i] === '--json-errors') jsonErrors = true;
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
        'Usage: node html2docx.js <input.html|.htm|.webarchive|.mhtml> <output.docx> [--header "text"] [--footer "text"] [--json-errors]',
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

// Find the article-content root. Try the most specific selectors first
// so we cleanly skip everything outside the article body even if the
// ARIA / chrome strip above missed something. Falls back to <body>.
function pickContentRoot($) {
    const candidates = [
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
    for (const sel of candidates) {
        const hit = $(sel).first();
        if (hit.length && hit.text().trim().length > 0) {
            return { node: hit[0], selector: sel };
        }
    }
    return { node: $('body').length ? $('body')[0] : $.root()[0], selector: 'body' };
}

const picked = pickContentRoot($);
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
