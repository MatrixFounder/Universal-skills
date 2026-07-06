// md2docx.js
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const marked = require('marked');
const sizeOf = require('image-size').imageSize;
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, HeadingLevel, BorderStyle, WidthType, ShadingType, LevelFormat, AlignmentType, Header, Footer, PageNumber, PageOrientation } = require('docx');

// Parse CLI arguments: node md2docx.js <input.md> <output.docx>
//   [--header "text"] [--footer "text"] [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]
const USAGE = 'Usage: node md2docx.js <input.md> <output.docx> [--header "text"] [--footer "text"] [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]';
const args = process.argv.slice(2);
let inputFile, outputFile, headerText, footerText;
let pageSizeArg = 'letter';   // default US Letter (backward-compatible)
let landscape = false;
let marginsArg = null;        // null → default 1440 dxa on all sides
const positional = [];
const VALUE_FLAGS = new Set(['--header', '--footer', '--page-size', '--margins']);
for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--landscape') {
        landscape = true;
    } else if (VALUE_FLAGS.has(a)) {
        if (i + 1 >= args.length) {
            // TASK 019: a known flag without its value gets a precise diagnostic (not "unknown").
            console.error(`Missing value for ${a}`);
            console.error(USAGE);
            process.exit(1);
        }
        const v = args[++i];
        if (a === '--header') headerText = v;
        else if (a === '--footer') footerText = v;
        else if (a === '--page-size') pageSizeArg = v;
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

const inputFileAbs = path.resolve(inputFile);
const inputDir = path.dirname(inputFileAbs);

const rawMarkdown = fs.readFileSync(inputFileAbs, 'utf-8');
const markdown = rawMarkdown.replace(/^---\n[\s\S]*?\n---\n/, '');
const tokens = marked.lexer(markdown);

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

function buildImageRun(localPath, altText) {
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
    // Scale proportionally so the image fits BOTH dimensions.
    const scale = Math.min(1, maxWidth / w, maxHeight / h);
    if (scale < 1) {
        w = Math.round(w * scale);
        h = Math.round(h * scale);
    }

    return new ImageRun({
        type: imageType,
        data: imgData,
        transformation: { width: w, height: h },
        altText: {
            title: altText || path.basename(localPath),
            description: altText || path.basename(localPath),
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

function parseInlineText(rawText) {
    const inlineTokens = marked.Lexer.lexInline(rawText);
    const runs = [];
    for (const t of inlineTokens) {
        if (t.type === 'strong') {
            runs.push(new TextRun({ text: decodeEntities(t.text), font: "Arial", size: 24, bold: true }));
        } else if (t.type === 'em') {
            runs.push(new TextRun({ text: decodeEntities(t.text), font: "Arial", size: 24, italics: true }));
        } else if (t.type === 'codespan') {
            runs.push(new TextRun({ text: decodeEntities(t.text), font: "Courier New", size: 22 }));
        } else if (t.type === 'link') {
            runs.push(new TextRun({ text: decodeEntities(t.text), font: "Arial", size: 24, underline: true, color: "0000FF" }));
        } else if (t.type === 'image') {
            const localPath = resolveLocalImagePath(t.href);
            if (localPath === null) {
                // Keep previous permissive behavior for remote/data refs: write alt text only.
                runs.push(new TextRun({ text: decodeEntities(t.text) || t.href, font: "Arial", size: 24 }));
            } else {
                runs.push(buildImageRun(localPath, decodeEntities(t.text)));
            }
        } else if (t.type === 'text' || t.type === 'escape' || t.type === 'html') {
            if (t.raw.includes('<br>')) {
                const parts = t.raw.split('<br>');
                for (let i = 0; i < parts.length; i++) {
                    runs.push(new TextRun({ text: decodeEntities(parts[i].trim()), font: "Arial", size: 24 }));
                    if (i < parts.length - 1) {
                        runs.push(new TextRun({ text: "", break: 1 }));
                    }
                }
            } else {
                runs.push(new TextRun({ text: decodeEntities(t.text || t.raw), font: "Arial", size: 24 }));
            }
        }
    }
    return runs;
}

function renderCellTokens(tokens) {
    const paragraphs = [];
    if (!tokens) return [new Paragraph({ children: [] })];
    for (const token of tokens) {
        if (token.type === 'paragraph' || token.type === 'text') {
            paragraphs.push(new Paragraph({ children: parseInlineText(token.text) }));
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
            children.push(new Paragraph({
                children: parseInlineText(token.text),
                spacing: { before: 120, after: 120 }
            }));
        } else if (token.type === 'table') {
            const headerCells = token.header;
            const rows = token.rows;

            const numCols = headerCells.length;
            const colWidth = Math.floor(contentWidthDxa / numCols);
            const colWidthsArray = Array(numCols).fill(colWidth);

            const tableRows = [];

            tableRows.push(new TableRow({
                children: headerCells.map(c => new TableCell({
                    borders,
                    width: { size: colWidth, type: WidthType.DXA },
                    shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    children: renderCellTokens(c.tokens)
                }))
            }));

            for (const row of rows) {
                tableRows.push(new TableRow({
                    children: row.map(c => new TableCell({
                        borders,
                        width: { size: colWidth, type: WidthType.DXA },
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
            const mmdFile = `temp_${imgCounter}.mmd`;
            const pngFile = `temp_${imgCounter}.png`;
            fs.writeFileSync(mmdFile, token.text);

            try {
                console.log(`Generating diagram ${imgCounter}...`);
                execSync(`npx -y @mermaid-js/mermaid-cli -i ${mmdFile} -o ${pngFile} -s 2 -b white -t neutral`, { stdio: 'inherit' });
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
                    fs.unlinkSync(pngFile);
                }
                fs.unlinkSync(mmdFile);
            } catch (err) {
                console.error(err);
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
