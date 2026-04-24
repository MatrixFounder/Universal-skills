// md2docx.js
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const marked = require('marked');
const sizeOf = require('image-size').imageSize;
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, HeadingLevel, BorderStyle, WidthType, ShadingType, LevelFormat, AlignmentType, Header, Footer, PageNumber } = require('docx');

// Parse CLI arguments: node md2docx.js <input.md> <output.docx> [--header "text"] [--footer "text"]
const args = process.argv.slice(2);
let inputFile, outputFile, headerText, footerText;
const positional = [];
for (let i = 0; i < args.length; i++) {
    if (args[i] === '--header' && i + 1 < args.length) {
        headerText = args[++i];
    } else if (args[i] === '--footer' && i + 1 < args.length) {
        footerText = args[++i];
    } else {
        positional.push(args[i]);
    }
}
inputFile = positional[0];
outputFile = positional[1];

if (!inputFile || !outputFile) {
    console.error("Usage: node md2docx.js <input.md> <output.docx> [--header \"text\"] [--footer \"text\"]");
    process.exit(1);
}

const inputFileAbs = path.resolve(inputFile);
const inputDir = path.dirname(inputFileAbs);

const rawMarkdown = fs.readFileSync(inputFileAbs, 'utf-8');
const markdown = rawMarkdown.replace(/^---\n[\s\S]*?\n---\n/, '');
const tokens = marked.lexer(markdown);

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

const contentWidthDxa = 9360;

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
    // Content width: 9360 DXA = 5,943,600 EMU; docx-js: 1px = 9525 EMU; max ~624px
    const maxWidth = 620;
    // US Letter height 15840 DXA - 2×1440 margins = 12960 DXA usable ≈ 865px at 96dpi.
    // Leave headroom for a caption/paragraph, cap images at ~800px tall.
    const maxHeight = 800;
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

function parseInlineText(rawText) {
    const inlineTokens = marked.Lexer.lexInline(rawText);
    const runs = [];
    for (const t of inlineTokens) {
        if (t.type === 'strong') {
            runs.push(new TextRun({ text: t.text, font: "Arial", size: 24, bold: true }));
        } else if (t.type === 'em') {
            runs.push(new TextRun({ text: t.text, font: "Arial", size: 24, italics: true }));
        } else if (t.type === 'codespan') {
            runs.push(new TextRun({ text: t.text, font: "Courier New", size: 22 }));
        } else if (t.type === 'link') {
            runs.push(new TextRun({ text: t.text, font: "Arial", size: 24, underline: true, color: "0000FF" }));
        } else if (t.type === 'image') {
            const localPath = resolveLocalImagePath(t.href);
            if (localPath === null) {
                // Keep previous permissive behavior for remote/data refs: write alt text only.
                runs.push(new TextRun({ text: t.text || t.href, font: "Arial", size: 24 }));
            } else {
                runs.push(buildImageRun(localPath, t.text));
            }
        } else if (t.type === 'text' || t.type === 'escape' || t.type === 'html') {
            if (t.raw.includes('<br>')) {
                const parts = t.raw.split('<br>');
                for (let i = 0; i < parts.length; i++) {
                    runs.push(new TextRun({ text: parts[i].trim(), font: "Arial", size: 24 }));
                    if (i < parts.length - 1) {
                        runs.push(new TextRun({ text: "", break: 1 }));
                    }
                }
            } else {
                runs.push(new TextRun({ text: t.text || t.raw, font: "Arial", size: 24 }));
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
                    const mmdMaxWidth = 620;
                    // Tall flowcharts can easily exceed page height after a
                    // width-only downscale — bound both dimensions.
                    const mmdMaxHeight = 800;
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
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
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
