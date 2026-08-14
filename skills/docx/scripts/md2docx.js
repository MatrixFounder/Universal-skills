// md2docx.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const marked = require('marked');
const sizeOf = require('image-size').imageSize;
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, HeadingLevel, BorderStyle, WidthType, ShadingType, LevelFormat, AlignmentType, Header, Footer, PageNumber, PageOrientation, ImportedXmlComponent } = require('docx');
const mathLib = require('./_math_lib');

// Parse CLI arguments: node md2docx.js <input.md> <output.docx>
//   [--header "text"] [--footer "text"] [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]
const USAGE = 'Usage: node md2docx.js <input.md> <output.docx> [--header "text"] [--footer "text"] [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]\n'
    + '       [--no-math] [--strict-math]\n'
    + '       [--obsidian [--vault-root DIR] [--frontmatter table|render|strip] [--lang ru|en|auto]\n'
    + '                   [--links text|italic] [--inline-tags strip|keep] [--transclude] [--strict-assets]]';
const args = process.argv.slice(2);
let inputFile, outputFile, headerText, footerText;
let pageSizeArg = 'letter';   // default US Letter (backward-compatible)
let landscape = false;
let marginsArg = null;        // null → default 1440 dxa on all sides
// TASK 031 — math ($…$/$$…$$) support. On by default; --no-math restores literal-text
// pre-TASK-031 behaviour byte-for-byte. --strict-math turns a KaTeX render failure into a
// hard exit instead of the default degrade-to-literal-text-plus-warning.
let noMath = false;
let strictMath = false;
// TASK 030 — Obsidian pre-processing. Off by default; without --obsidian this script
// behaves exactly as before, except for the unescaped-spaces warning below (which is a
// diagnostic for plain-CommonMark authors too, so it is deliberately NOT gated).
let obsidian = false;
let obsidianOpts = { vaultRoot: null, frontmatter: 'table', lang: 'auto', links: 'text', inlineTags: 'strip', transclude: false, strictAssets: false };
// Which Obsidian flags the user actually TYPED. The value-carrying ones have non-null
// defaults, so `obsidianOpts` alone cannot tell "not given" from "given the default" — and
// the first version of the stray check therefore accepted and silently discarded
// `--frontmatter`, `--lang`, `--links` and `--inline-tags` without `--obsidian`, while
// SKILL.md claimed every Obsidian flag was rejected.
const obsidianFlagsSeen = [];
const OBSIDIAN_CHOICES = { '--frontmatter': ['table', 'render', 'strip'], '--lang': ['ru', 'en', 'auto'], '--links': ['text', 'italic'], '--inline-tags': ['strip', 'keep'] };
const positional = [];
// `--vault-root` and friends are KNOWN value-flags, so a bare `--vault-root DIR` never
// reports as "unknown" (the precedent at line 26 above) and the DIR is never mistaken for
// a positional. Whether the flag is USABLE is a separate check, after the loop, so flag
// order does not matter.
const VALUE_FLAGS = new Set(['--header', '--footer', '--page-size', '--margins',
    '--vault-root', '--frontmatter', '--lang', '--links', '--inline-tags']);
for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--landscape') {
        landscape = true;
    } else if (a === '--no-math') {
        noMath = true;
    } else if (a === '--strict-math') {
        strictMath = true;
    } else if (a === '--obsidian') {
        obsidian = true;
    } else if (a === '--transclude') {
        obsidianOpts.transclude = true;
        obsidianFlagsSeen.push(a);
    } else if (a === '--strict-assets') {
        obsidianOpts.strictAssets = true;
        obsidianFlagsSeen.push(a);
    } else if (VALUE_FLAGS.has(a)) {
        if (i + 1 >= args.length) {
            // TASK 019: a known flag without its value gets a precise diagnostic (not "unknown").
            console.error(`Missing value for ${a}`);
            console.error(USAGE);
            process.exit(1);
        }
        const v = args[++i];
        if (OBSIDIAN_CHOICES[a] && !OBSIDIAN_CHOICES[a].includes(v)) {
            console.error(`Invalid value for ${a}: "${v}" (expected ${OBSIDIAN_CHOICES[a].join('|')}).`);
            process.exit(1);
        }
        if (OBSIDIAN_CHOICES[a] || a === '--vault-root') obsidianFlagsSeen.push(a);
        if (a === '--header') headerText = v;
        else if (a === '--footer') footerText = v;
        else if (a === '--page-size') pageSizeArg = v;
        else if (a === '--vault-root') obsidianOpts.vaultRoot = v;
        else if (a === '--frontmatter') obsidianOpts.frontmatter = v;
        else if (a === '--lang') obsidianOpts.lang = v;
        else if (a === '--links') obsidianOpts.links = v;
        else if (a === '--inline-tags') obsidianOpts.inlineTags = v;
        else marginsArg = v;  // --margins
    } else if (a.startsWith('--')) {
        // TASK 019: reject unknown flags instead of silently treating them as positionals.
        console.error(`Unknown option: ${a}`);
        console.error(USAGE);
        process.exit(1);
    } else {
        positional.push(a);
    }
}
inputFile = positional[0];
outputFile = positional[1];

if (!inputFile || !outputFile) {
    console.error(USAGE);
    process.exit(1);
}

// The Obsidian flags only mean something with --obsidian. Checked AFTER the parse loop so
// `--vault-root DIR --obsidian` and `--obsidian --vault-root DIR` behave identically.
// Exit 1 is this script's code for every usage error (see line 36); exit 2 is
// obsidian2md.js's convention and is deliberately not back-ported here.
if (!obsidian && obsidianFlagsSeen.length) {
    const stray = [...new Set(obsidianFlagsSeen)];
    console.error(`${stray.join(', ')} requires --obsidian`);
    console.error(USAGE);
    process.exit(1);
}

let inputFileAbs = path.resolve(inputFile);
let inputDir = path.dirname(inputFileAbs);
let obsidianTmpDir = null;

let rawMarkdown = fs.readFileSync(inputFileAbs, 'utf-8');

// TASK 030 — Obsidian pre-processing (R11). The library runs IN-PROCESS (no subprocess);
// its output goes to a temp directory so the intermediate never litters the vault. Image
// destinations it emits are absolute, so resolving them against inputDir still works.
if (obsidian) {
    const obsidianLib = require('./_obsidian_lib');
    let result;
    try {
        result = obsidianLib.convert(rawMarkdown, {
            notePath: inputFileAbs,
            vaultRoot: obsidianOpts.vaultRoot,
            frontmatter: obsidianOpts.frontmatter,
            lang: obsidianOpts.lang,
            links: obsidianOpts.links,
            inlineTags: obsidianOpts.inlineTags,
            transclude: obsidianOpts.transclude,
        });
    } catch (e) {
        console.error(`Obsidian pre-processing failed: ${e.message}`);
        process.exit(1);
    }
    for (const w of result.warnings) console.error(`warning: ${w}`);
    if (obsidianOpts.strictAssets && result.missing.length) {
        console.error(`${result.missing.length} attachment(s) not found: ${result.missing.join(', ')}`);
        process.exit(8);
    }
    obsidianTmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'md2docx-obsidian-'));
    // Cleaned in the `finally` of the writer at the bottom of this file, and on every
    // early exit through process.on('exit') — a temp dir that survives a failed run is a
    // leak that only shows up under a full disk, i.e. never during testing.
    process.on('exit', () => {
        if (obsidianTmpDir) {
            try { fs.rmSync(obsidianTmpDir, { recursive: true, force: true }); } catch (e) { /* best effort */ }
        }
    });
    const generated = path.join(obsidianTmpDir, path.basename(inputFileAbs));
    fs.writeFileSync(generated, result.markdown, 'utf-8');
    inputFileAbs = generated;
    // inputDir deliberately KEEPS pointing at the real note's directory. The converter
    // absolutises the destinations it rewrites, but a note may also carry ordinary
    // CommonMark `![alt](img/pic.png)` — Obsidian emits exactly that when "Use
    // [[Wikilinks]]" is off. Re-basing on the temp dir resolved those against an empty
    // directory and `buildImageRun` threw, so `--obsidian` turned a document that converted
    // fine into a hard exit 1. The intermediate .md is the only file in the temp dir; there
    // is nothing there to resolve against anyway.
    rawMarkdown = result.markdown;
}

const markdown = rawMarkdown.replace(/^---\n[\s\S]*?\n---\n/, '');

// TASK 031 — math preprocessing runs on the frontmatter-stripped text, after --obsidian
// pre-processing (obsidian2md.js never touches `$`, so there is no ordering conflict) and
// before marked.lexer(), so substitution happens before CommonMark's `_`/`*` emphasis-pairing
// rules ever see the text. --no-math skips this entirely: mathText === markdown, formulas
// stays empty, and every downstream call becomes a no-op (R6(d)).
let mathText = markdown;
let mathFormulas = [];
if (!noMath) {
    try {
        const mathResult = mathLib.preprocessMath(markdown, { strict: strictMath });
        mathText = mathResult.text;
        mathFormulas = mathResult.formulas;
    } catch (e) {
        console.error(e && e.message ? e.message : e);
        process.exit(1);
    }
}

const tokens = marked.lexer(mathText);

// TASK 030 R6(c) — the silent-loss guard. `![a](my folder/pic.png)` is legal-looking
// Markdown that `marked` reports as a `text` token, so the image is dropped and the run
// still exits 0. This warns for EVERY caller, not only --obsidian ones: a plain-CommonMark
// author writing a path with a space hits exactly the same loss.
// Honest scope: docx_replace.py --insert-after spawns this script through _actions.py with
// capture_output=True and reads stderr only on a non-zero return code, so on that path the
// warning is captured and discarded. Routing it through _actions.py is out of scope here.
// The destination must NOT start with `<`: the angle-bracket form carries spaces legally
// and DOES lex as an image, so matching it would warn about images that arrived intact —
// which is exactly what obsidian2md.js emits.
const UNPARSED_IMAGE = /!\[[^\]]*\]\((?!<)[^)<>]*\s[^)]*\)/;
(function warnUnparsedImages(list) {
    for (const tok of list || []) {
        // Only an INLINE `text` token (no child tokens) can be a failed image: a block-level
        // paragraph carries the same characters in `.raw` even when the image parsed fine.
        if (tok.type === 'text' && !tok.tokens && typeof tok.raw === 'string') {
            const m = UNPARSED_IMAGE.exec(tok.raw);
            if (m) {
                console.error('warning: image link with unescaped spaces was not parsed as '
                    + `an image: ${m[0]}`);
            }
        }
        if (tok.tokens) warnUnparsedImages(tok.tokens);
        if (tok.items) warnUnparsedImages(tok.items);
        // A `table` token keeps its text in header/row CELLS, not in `.tokens`, so the walk
        // used to stop at the table and an unparsed image inside one was dropped in silence
        // — the very outcome this guard exists to announce.
        if (tok.header) for (const cell of tok.header) warnUnparsedImages(cell.tokens);
        if (tok.rows) for (const row of tok.rows) for (const cell of row) warnUnparsedImages(cell.tokens);
    }
})(tokens);

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

// --- Page geometry (TASK 019) — derive EVERYTHING from the resolved page; no Letter literals ---
const PAGE_SIZES = { letter: { w: 12240, h: 15840 }, a4: { w: 11906, h: 16838 } };
const sizeKey = String(pageSizeArg).toLowerCase();
if (!Object.prototype.hasOwnProperty.call(PAGE_SIZES, sizeKey)) {
    console.error(`Invalid --page-size "${pageSizeArg}" (expected A4 or Letter).`);
    process.exit(1);
}
// Keep PORTRAIT dims for the section `size`; docx-js swaps them for landscape when given
// `orientation: LANDSCAPE` (verified). Content geometry uses orientation-aware effective dims.
const pageW = PAGE_SIZES[sizeKey].w;
const pageH = PAGE_SIZES[sizeKey].h;
const effW = landscape ? pageH : pageW;
const effH = landscape ? pageW : pageH;

// --margins "T,R,B,L" in dxa; each value optionally suffixed "mm" (1 mm ≈ 56.7 dxa).
function parseMarginToken(tok) {
    const m = String(tok).trim().match(/^(\d+(?:\.\d+)?)(mm)?$/);
    if (!m) return null;
    const v = parseFloat(m[1]);
    return m[2] ? Math.round(v * 56.7) : Math.round(v);
}
let marginT = 1440, marginR = 1440, marginB = 1440, marginL = 1440;
if (marginsArg !== null) {
    const parts = marginsArg.split(',');
    const vals = parts.length === 4 ? parts.map(parseMarginToken) : null;
    if (!vals || vals.some(v => v === null)) {
        console.error(`Invalid --margins "${marginsArg}" (expected T,R,B,L in dxa, optional "mm" suffix).`);
        process.exit(1);
    }
    [marginT, marginR, marginB, marginL] = vals;
}

// contentWidthDxa was a hardcoded 9360 (Letter − 2×1440). Now derived from the resolved
// page so tables/images never overflow a narrower page (A4 content width = 9026 dxa).
// 1 dxa = 635 EMU, 1 px = 9525 EMU ⇒ px = dxa / 15 (geometrically exact).
const contentWidthDxa = effW - marginL - marginR;
const maxWidthPx = Math.floor(contentWidthDxa / 15);
const maxHeightPx = Math.floor((effH - marginT - marginB) / 15);
// TASK 019: guard nonsensical margins (would yield negative geometry → a cryptic docx-lib
// error). Fail with a clear message instead.
if (contentWidthDxa <= 0 || (effH - marginT - marginB) <= 0) {
    console.error(`Margins leave no content area on the ${sizeKey}${landscape ? ' landscape' : ''} page (${effW}×${effH} dxa).`);
    process.exit(1);
}

function isRemoteOrDataUrl(ref) {
    return /^https?:\/\//i.test(ref) || /^data:/i.test(ref);
}

function detectImageType(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    if (ext === '.png') return 'png';
    if (ext === '.jpg' || ext === '.jpeg') return 'jpg';
    if (ext === '.gif') return 'gif';
    if (ext === '.bmp') return 'bmp';
    if (ext === '.svg') return 'svg';
    return null;
}

function resolveLocalImagePath(rawHref) {
    const href = rawHref ? decodeURI(rawHref) : '';
    if (!href) {
        throw new Error("Empty image path in markdown image token.");
    }
    if (isRemoteOrDataUrl(href)) {
        return null;
    }
    if (path.isAbsolute(href)) {
        return href;
    }
    return path.resolve(inputDir, href);
}

// TASK 030 R3(g)/(h) — the Obsidian `![[pic.png|300]]` width hint. CommonMark cannot
// express it, so obsidian2md.js parks it on a reserved alt-text prefix and this is where
// it is consumed. The hint is an UPPER BOUND and never upscales, which keeps the
// `Math.min(1, …)` invariant below intact; Obsidian itself does upscale, so a source
// narrower than the hint renders smaller here than in the vault (documented in SKILL.md).
const SIZE_HINT = /^w=(\d+)(?:x(\d+))?\|/;

function parseSizeHint(altText) {
    if (typeof altText !== 'string') return { hint: null, alt: altText };
    const m = SIZE_HINT.exec(altText);
    if (!m) return { hint: null, alt: altText };
    return {
        hint: { w: parseInt(m[1], 10), h: m[2] ? parseInt(m[2], 10) : null },
        alt: altText.slice(m[0].length),
    };
}

function buildImageRun(localPath, rawAltText) {
    const { hint, alt: altText } = parseSizeHint(rawAltText);
    const imageType = detectImageType(localPath);
    if (!imageType) {
        throw new Error(`Unsupported image format for markdown image: ${localPath}`);
    }
    if (!fs.existsSync(localPath)) {
        throw new Error(`Local image not found: ${localPath}`);
    }

    const imgData = fs.readFileSync(localPath);
    const dims = sizeOf(imgData);
    // TASK 019: caps derived from the resolved page geometry (px = dxa/15), not Letter
    // constants — so images fit the chosen page (A4 content width 9026 dxa < Letter 9360).
    const maxWidth = maxWidthPx;
    const maxHeight = maxHeightPx;
    let w = dims.width || maxWidth;
    let h = dims.height || 400;
    if (hint) {
        if (hint.h) {
            // Both dimensions given explicitly: honour them as written, still bounded by
            // the natural size so the hint cannot upscale.
            w = Math.min(hint.w, w);
            h = Math.min(hint.h, h);
        } else {
            // Width only: height follows the source aspect ratio.
            const target = Math.min(hint.w, w);
            h = Math.round(h * (target / w));
            w = target;
        }
    }
    // Scale proportionally so the image fits BOTH dimensions.
    const scale = Math.min(1, maxWidth / w, maxHeight / h);
    if (scale < 1) {
        w = Math.round(w * scale);
        h = Math.round(h * scale);
    }

    // TASK 031 R5 — ImageRun.altText's three fields are plain strings, not run children, so
    // there is nowhere to splice a math object into. A formula here falls back to its
    // original literal source text instead — the ONE sink in this file that needs
    // restoreLiteral rather than mathAwareRuns.
    const literalAltText = mathLib.restoreLiteral(altText || path.basename(localPath), mathFormulas);

    return new ImageRun({
        type: imageType,
        data: imgData,
        transformation: { width: w, height: h },
        altText: {
            title: literalAltText,
            description: literalAltText,
            name: path.basename(localPath)
        }
    });
}

// marked's inline lexer HTML-escapes the .text of text/codespan/strong/em/link
// tokens (& < > " '). The docx TextRun layer escapes again for XML, so source
// text like `<TBD: ФИО>` or `Q&A` rendered as literal `&lt;TBD: ФИО&gt;` /
// `Q&amp;A` in Word (ROADMAP N21a, found by the deal-zero render QA).
// Decode exactly once here; ampersand MUST be decoded last.
function decodeEntities(s) {
    if (typeof s !== 'string') return s;
    return s
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'")
        .replace(/&amp;/g, '&');
}

// ImportedXmlComponent.fromXmlString() wraps its result in a container whose own rootKey is
// undefined — it supports parsing a multi-root fragment, so the container's `.root` array
// holds each top-level node. Our OMML strings are always exactly one root element
// (<m:oMath>…</m:oMath>), so pushing the wrapper itself as a paragraph child serializes as a
// bogus `<undefined>` XML element (verified against this docx version — .root[0] is the real,
// correctly-keyed `m:oMath` component).
function importedMathComponent(omml) {
    return ImportedXmlComponent.fromXmlString(omml).root[0];
}

// TASK 031 — splits `text` on math sentinels (mathFormulas is populated once, near the top
// of the script, by preprocessMath() before marked ever runs) and returns an array of
// ParagraphChild: TextRun for each literal piece (using styleOpts — the same options every
// call site already passed to `new TextRun`), a fresh ImportedXmlComponent per math piece.
// Every run-bearing branch of parseInlineText calls this instead of building a TextRun
// directly, so a formula sitting inside **bold**/*italic*/a link still renders as a real
// (unstyled) math object rather than leaking raw sentinel bytes (R4(b)).
function mathAwareRuns(text, styleOpts) {
    const pieces = mathLib.splitMathSentinels(text, mathFormulas);
    const out = [];
    for (const piece of pieces) {
        if (piece.type === 'math') {
            out.push(importedMathComponent(piece.formula.omml));
        } else if (piece.text) {
            out.push(new TextRun(Object.assign({ text: piece.text }, styleOpts)));
        }
    }
    return out;
}

function parseInlineText(rawText) {
    const inlineTokens = marked.Lexer.lexInline(rawText);
    const runs = [];
    for (const t of inlineTokens) {
        if (t.type === 'strong') {
            runs.push(...mathAwareRuns(decodeEntities(t.text), { font: "Arial", size: 24, bold: true }));
        } else if (t.type === 'em') {
            runs.push(...mathAwareRuns(decodeEntities(t.text), { font: "Arial", size: 24, italics: true }));
        } else if (t.type === 'codespan') {
            // No mathAwareRuns here: R1(b) excludes code spans from math scanning before
            // marked ever sees the text, so a sentinel can never reach this branch.
            runs.push(new TextRun({ text: decodeEntities(t.text), font: "Courier New", size: 22 }));
        } else if (t.type === 'link') {
            runs.push(...mathAwareRuns(decodeEntities(t.text), { font: "Arial", size: 24, underline: true, color: "0000FF" }));
        } else if (t.type === 'image') {
            const localPath = resolveLocalImagePath(t.href);
            if (localPath === null) {
                // Keep previous permissive behavior for remote/data refs: write alt text
                // only. This is an ordinary TextRun sink (not ImageRun.altText), so a
                // formula here gets the same mathAwareRuns treatment as any other text (R4(b)).
                runs.push(...mathAwareRuns(decodeEntities(t.text) || t.href, { font: "Arial", size: 24 }));
            } else {
                runs.push(buildImageRun(localPath, decodeEntities(t.text)));
            }
        } else if (t.type === 'text' || t.type === 'escape' || t.type === 'html') {
            if (t.raw.includes('<br>')) {
                const parts = t.raw.split('<br>');
                for (let i = 0; i < parts.length; i++) {
                    runs.push(...mathAwareRuns(decodeEntities(parts[i].trim()), { font: "Arial", size: 24 }));
                    if (i < parts.length - 1) {
                        runs.push(new TextRun({ text: "", break: 1 }));
                    }
                }
            } else {
                runs.push(...mathAwareRuns(decodeEntities(t.text || t.raw), { font: "Arial", size: 24 }));
            }
        }
    }
    return runs;
}

// TASK 031 R4(d) — a paragraph or table-cell text whose ENTIRE trimmed content is exactly one
// sentinel referencing a DISPLAY formula gets a dedicated centered paragraph, so `$$…$$` alone
// between blank lines reads visually distinct from surrounding prose the way Word's own
// display equations do. Returns null when `text` doesn't have that exact shape (mixed
// content, an inline formula, or a formula whose render failed and fell back to literal text)
// — callers fall through to their normal paragraph-building path, which still renders the
// formula correctly, just inline and left-flowing rather than centered.
function buildDisplayMathParagraph(text) {
    const pieces = mathLib.splitMathSentinels(text.trim(), mathFormulas);
    if (pieces.length === 1 && pieces[0].type === 'math' && pieces[0].formula.display) {
        return new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 120, after: 120 },
            children: [importedMathComponent(pieces[0].formula.omml)]
        });
    }
    return null;
}

function cellIsBlank(cellTokens) {
    if (!cellTokens || cellTokens.length === 0) return true;
    return cellTokens.every(t => !(t.text || t.raw || '').trim());
}

function renderCellTokens(tokens) {
    const paragraphs = [];
    if (!tokens) return [new Paragraph({ children: [] })];
    for (const token of tokens) {
        if (token.type === 'paragraph' || token.type === 'text') {
            paragraphs.push(buildDisplayMathParagraph(token.text)
                || new Paragraph({ children: parseInlineText(token.text) }));
        } else if (token.type === 'space') {
            continue;
        } else {
            paragraphs.push(new Paragraph({ children: parseInlineText(token.raw) }));
        }
    }
    if (paragraphs.length === 0) paragraphs.push(new Paragraph({}));
    return paragraphs;
}

function renderList(listToken, level, target, parentRef) {
    let listRef;
    if (listToken.ordered) {
        if (level === 0) {
            // Each top-level ordered list gets its own numbering reference to restart from 1
            numberedListCounter++;
            listRef = `numbers_${numberedListCounter}`;
            numberedListConfigs.push({
                reference: listRef,
                levels: [
                    { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
                    { level: 1, format: LevelFormat.DECIMAL, text: "%2.", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
                    { level: 2, format: LevelFormat.DECIMAL, text: "%3.", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 2160, hanging: 360 } } } },
                ]
            });
        } else {
            listRef = parentRef;
        }
    } else {
        listRef = "bullets";
    }

    for (const item of listToken.items) {
        const textParts = item.tokens.filter(t => t.type !== 'list');
        const nestedLists = item.tokens.filter(t => t.type === 'list');

        const itemText = textParts.map(t => t.text || '').join(' ').trim();
        if (itemText) {
            target.push(new Paragraph({
                numbering: { reference: listRef, level: level },
                children: parseInlineText(itemText),
                spacing: { before: 60, after: 60 }
            }));
        }

        for (const nested of nestedLists) {
            renderList(nested, level + 1, target, listRef);
        }
    }
}

let children = [];
let imgCounter = 0;
let numberedListCounter = 0;
const numberedListConfigs = [];

try {
    for (const token of tokens) {
        if (token.type === 'heading') {
            let hLevel;
            if (token.depth === 1) hLevel = HeadingLevel.HEADING_1;
            else if (token.depth === 2) hLevel = HeadingLevel.HEADING_2;
            else if (token.depth === 3) hLevel = HeadingLevel.HEADING_3;
            else hLevel = HeadingLevel.HEADING_4;

            children.push(new Paragraph({
                heading: hLevel,
                children: parseInlineText(token.text)
            }));
        } else if (token.type === 'paragraph') {
            if (token.text.startsWith('<!--')) continue;
            children.push(buildDisplayMathParagraph(token.text) || new Paragraph({
                children: parseInlineText(token.text),
                spacing: { before: 120, after: 120 }
            }));
        } else if (token.type === 'table') {
            const headerCells = token.header;
            const rows = token.rows;

            const numCols = headerCells.length;
            // TASK 031 — the Pandoc LaTeX->Markdown "equation array" convention: a 4-column
            // table whose 1st/3rd columns are blank spacers, 2nd holds the formula (usually
            // display math), 4th a short number/label (`|  | $$…$$ |  | (N) |`). An equal
            // 4-way split leaves the formula only ~1/4 of the page width, clipping any
            // non-trivial equation — measured on the docx-11 acceptance document (TASK 031
            // A9). Every such table observed is a single-row (header-only) table, so
            // detecting the shape on the header row is sufficient.
            const isEquationArrayTable = numCols === 4
                && cellIsBlank(headerCells[0].tokens) && cellIsBlank(headerCells[2].tokens);

            let colWidthsArray;
            if (isEquationArrayTable) {
                colWidthsArray = [0.03, 0.80, 0.03, 0.14].map(f => Math.floor(contentWidthDxa * f));
                const roundedSum = colWidthsArray.reduce((a, b) => a + b, 0);
                colWidthsArray[3] += contentWidthDxa - roundedSum; // absorb rounding remainder
            } else {
                const colWidth = Math.floor(contentWidthDxa / numCols);
                colWidthsArray = Array(numCols).fill(colWidth);
            }

            const tableRows = [];

            tableRows.push(new TableRow({
                children: headerCells.map((c, i) => new TableCell({
                    borders,
                    width: { size: colWidthsArray[i], type: WidthType.DXA },
                    shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    children: renderCellTokens(c.tokens)
                }))
            }));

            for (const row of rows) {
                tableRows.push(new TableRow({
                    children: row.map((c, i) => new TableCell({
                        borders,
                        width: { size: colWidthsArray[i], type: WidthType.DXA },
                        shading: { type: ShadingType.CLEAR },
                        margins: { top: 80, bottom: 80, left: 120, right: 120 },
                        children: renderCellTokens(c.tokens)
                    }))
                }));
            }

            children.push(new Table({
                width: { size: contentWidthDxa, type: WidthType.DXA },
                columnWidths: colWidthsArray,
                rows: tableRows
            }));
            children.push(new Paragraph({ spacing: { after: 240 } }));
        } else if (token.type === 'code' && token.lang === 'mermaid') {
            imgCounter++;
            // DOCX-MERMAID-EXECSYNC: render inside an unpredictable per-diagram
            // scratch dir — never the CWD (no predictable-name pre-plant surface,
            // nothing left behind) — and exec in argv form (no shell string).
            const mmdScratch = fs.mkdtempSync(path.join(os.tmpdir(), 'md2docx-mmd-'));
            const mmdFile = path.join(mmdScratch, 'diagram.mmd');
            const pngFile = path.join(mmdScratch, 'diagram.png');
            fs.writeFileSync(mmdFile, token.text);

            try {
                console.log(`Generating diagram ${imgCounter}...`);
                execFileSync(process.platform === 'win32' ? 'npx.cmd' : 'npx',
                    ['-y', '@mermaid-js/mermaid-cli', '-i', mmdFile, '-o', pngFile,
                     '-s', '2', '-b', 'white', '-t', 'neutral'],
                    { stdio: 'inherit' });
                if (fs.existsSync(pngFile)) {
                    const imgData = fs.readFileSync(pngFile);
                    const dims = sizeOf(imgData);
                    // Bound both dimensions to the resolved page geometry (TASK 019) so
                    // tall flowcharts don't exceed page height after a width-only downscale.
                    const mmdMaxWidth = maxWidthPx;
                    const mmdMaxHeight = maxHeightPx;
                    let w = dims.width;
                    let h = dims.height;
                    const scale = Math.min(1, mmdMaxWidth / w, mmdMaxHeight / h);
                    if (scale < 1) {
                        w = Math.round(w * scale);
                        h = Math.round(h * scale);
                    }

                    children.push(new Paragraph({
                        spacing: { before: 120, after: 120 },
                        children: [new ImageRun({
                            type: "png",
                            data: imgData,
                            transformation: { width: w, height: h },
                            altText: { title: `Diagram ${imgCounter}`, description: "Process Diagram", name: "Diagram" }
                        })]
                    }));
                }
            } catch (err) {
                console.error(err);
            } finally {
                // Scratch removal replaces the old per-file unlinks: it runs on
                // BOTH success and render failure, so nothing ever leaks.
                fs.rmSync(mmdScratch, { recursive: true, force: true });
            }
        } else if (token.type === 'code' && token.lang !== 'mermaid') {
            const lines = token.text.split('\n');
            for (const line of lines) {
                children.push(new Paragraph({
                    children: [new TextRun({ text: line || ' ', font: "Courier New", size: 20 })],
                    spacing: { before: 0, after: 0 },
                    shading: { type: ShadingType.CLEAR, fill: "F5F5F5" },
                    indent: { left: 360 }
                }));
            }
        } else if (token.type === 'blockquote') {
            for (const inner of (token.tokens || [])) {
                const text = inner.text || inner.raw || '';
                if (!text.trim()) continue;
                children.push(new Paragraph({
                    children: parseInlineText(text),
                    indent: { left: 720 },
                    spacing: { before: 120, after: 120 },
                    border: { left: { style: BorderStyle.SINGLE, size: 3, color: "AAAAAA", space: 8 } }
                }));
            }
        } else if (token.type === 'hr') {
            children.push(new Paragraph({
                children: [],
                spacing: { before: 200, after: 200 },
                border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC", space: 4 } }
            }));
        } else if (token.type === 'list') {
            renderList(token, 0, children);
        }
    }
} catch (err) {
    console.error(err && err.message ? err.message : err);
    process.exit(1);
}

// Headers/footers must be at section level, NOT inside properties
const section = {
    properties: {
        page: {
            size: { width: pageW, height: pageH, orientation: landscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
            margin: { top: marginT, right: marginR, bottom: marginB, left: marginL }
        }
    },
    children: children
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
                    ...(footerText ? [new TextRun({ text: footerText, font: "Arial", size: 18, color: "888888" }), new TextRun({ text: "    ", font: "Arial", size: 18 })] : []),
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
                    { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
                    { level: 1, format: LevelFormat.BULLET, text: "\u2013", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
                    { level: 2, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
                      style: { paragraph: { indent: { left: 2160, hanging: 360 } } } },
                ]
            },
            ...numberedListConfigs
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
        console.error(err && err.message ? err.message : err);
        process.exit(1);
    });
