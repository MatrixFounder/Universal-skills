// docx → markdown CLI. Main entry; orchestrates the pipeline and delegates
// domain logic to ./docx2md/_{util,probes,assets,shapes,markdown}.js.
//
// Flow:
//   1. Probe external tools (soffice, poppler) and load npm deps.
//   2. Create output assets dir (refusing symlinks).
//   3. Build shared ctx (paths, counters, dedup maps, tool handles).
//   4. Mammoth: docx → HTML (with image callback that stores assets via ctx).
//   5. Turndown: HTML → markdown with custom table rules.
//   6. In parallel: extract header/footer images + extract shape drawings from XML.
//   7. Batch-convert collected EMFs to PNG; rewrite markdown refs.
//   8. Prepend header/footer image block; inject shape-group diagrams.
//   9. Collapse duplicate image runs; apply TOC-derived heading numbering;
//      inject TOC anchors.
//   10. Write final markdown.

const fs = require("fs");
const path = require("path");

const { loadDependency } = require("./docx2md/_util");
const { findSoffice, findPoppler } = require("./docx2md/_probes");
const {
    storeOrDedup,
    batchConvertEmfToPng,
    rewriteEmfHrefsToPng,
    extractHeaderFooterImages,
} = require("./docx2md/_assets");
const {
    extractBodyDrawings,
    injectMissingShapeDiagrams,
} = require("./docx2md/_shapes");
const {
    collapseDuplicateImageRuns,
    applyHeadingNumberingFromTOC,
    injectTocAnchors,
    dropEmptyHeadings,
    dropTinyImageRefs,
} = require("./docx2md/_markdown");

// ---- CLI args ------------------------------------------------------------

const inputDocx = process.argv[2];
const outputMd = process.argv[3];
if (!inputDocx || !outputMd) {
    console.error("Usage: node docx2md.js <input.docx> <output.md>");
    process.exit(1);
}

// ---- Load npm deps (via loader with auto-install fallback) ---------------

const SCRIPTS_DIR = __dirname;
const mammoth = loadDependency("mammoth", SCRIPTS_DIR);
const TurndownService = loadDependency("turndown", SCRIPTS_DIR);
const turndownPluginGfm = loadDependency("turndown-plugin-gfm", SCRIPTS_DIR);
loadDependency("jszip", SCRIPTS_DIR); // prewarm for _assets / _shapes

// ---- External tool probes ------------------------------------------------

const soffice = findSoffice();
if (soffice) {
    console.log(`[docx-to-md] soffice detected (${soffice}) — EMF will be converted to PNG in one batch.`);
} else {
    console.log("[docx-to-md] soffice not found — EMF images stay as .x-emf (may not render in viewers).");
}

const poppler = findPoppler();
if (poppler && soffice) {
    console.log("[docx-to-md] poppler detected — shape-group diagrams will render via PDF crop (high fidelity, includes shape text).");
} else if (soffice && !poppler) {
    console.log("[docx-to-md] poppler not found — shape-group diagrams will render via LibreOffice HTML (geometry only, text labels separated). For full fidelity: brew install poppler.");
}

// ---- Output paths + shared ctx -------------------------------------------

const outputDir = path.dirname(path.resolve(outputMd));
const baseName = path.basename(outputMd, ".md");
const imagesDirName = `${baseName}_images`;
const imagesDirPath = path.join(outputDir, imagesDirName);

const ctx = {
    inputDocx,
    imagesDirName,
    imagesDirPath,
    installDir: SCRIPTS_DIR,
    soffice,
    poppler,
    seenHashes: new Map(),
    emfFilenames: [],
    counter: (() => {
        let n = 1;
        return { next() { return n++; } };
    })(),
};

// ---- Prepare images dir --------------------------------------------------

// Refuse to delete a symlink (could wipe unrelated content).
if (fs.existsSync(imagesDirPath)) {
    const stat = fs.lstatSync(imagesDirPath);
    if (stat.isSymbolicLink()) {
        console.error(`[docx-to-md] Refusing to remove symlink at ${imagesDirPath} — resolve manually.`);
        process.exit(1);
    }
    fs.rmSync(imagesDirPath, { recursive: true, force: true });
}
fs.mkdirSync(imagesDirPath, { recursive: true });

// ---- Mammoth document transform: collapse duplicate adjacent runs --------
//
// Some docx authoring tools (and human copy/paste) leave a paragraph with
// adjacent <w:r> runs that have identical short text — e.g. a numbering
// cell with two runs both containing "2", which mammoth concatenates to
// "22". Collapse such runs in the AST so the converter sees the visible
// value once. Universal: applies to every paragraph, no per-doc hacks.
function getRunPlainText(run) {
    if (!run.children) return null;
    let text = "";
    for (const c of run.children) {
        if (c.type !== "text") return null;
        text += c.value;
    }
    return text;
}

function collapseDuplicateAdjacentRuns(paragraph) {
    const kids = paragraph.children;
    if (!kids || kids.length < 2) return paragraph;
    const out = [];
    for (const child of kids) {
        const last = out[out.length - 1];
        if (last && last.type === "run" && child.type === "run") {
            const t1 = getRunPlainText(last);
            const t2 = getRunPlainText(child);
            // Only collapse short, identical, non-empty plain-text runs.
            // Length cap keeps the heuristic safe — duplicating a long
            // identical phrase across two runs would be a real authoring
            // intent, not a stutter artefact.
            if (t1 && t2 && t1 === t2 && t1.length <= 3) {
                continue;
            }
        }
        out.push(child);
    }
    paragraph.children = out;
    return paragraph;
}

// ---- Mammoth image convertor (routes through _assets/storeOrDedup) -------

const mammothOptions = {
    convertImage: mammoth.images.inline((element) =>
        element.read().then((imageBuffer) => {
            const ext = (element.contentType || "image/png").split("/")[1] || "png";
            const filename = storeOrDedup(ctx, imageBuffer, ext);
            return { src: encodeURI(path.posix.join(imagesDirName, filename)) };
        }),
    ),
    styleMap: [
        "p[style-name='Heading 1'] => h1:fresh",
        "p[style-name='Heading 2'] => h2:fresh",
        "p[style-name='Heading 3'] => h3:fresh",
        "p[style-name='Heading 4'] => h4:fresh",
        "p[style-name='Heading 5'] => h5:fresh",
        "p[style-name='Heading 6'] => h6:fresh",
        "p[style-name='Code'] => pre > code:fresh",
    ],
    transformDocument: mammoth.transforms.paragraph(collapseDuplicateAdjacentRuns),
};

// ---- Turndown (HTML → markdown) with merge-aware table rules ------------

// Walk a <table> node and expand rowspan/colspan into a flat grid.
// Markdown has no native rowspan support; we represent merged cells by
// placing the value in the FIRST row/column of the merge and leaving
// subsequent cells empty (but defined, so column count stays consistent
// across rows). This preserves the docx semantics: a rowspan=6 numbered
// "1" is ONE logical entry with 6 sub-events — not 6 entries each
// numbered "1".
function expandTableToGrid(tableNode, turndownService) {
    const trNodes = [];
    (function collectTrs(node) {
        for (const child of node.childNodes || []) {
            if (child.nodeName === "TR") trNodes.push(child);
            else if (child.childNodes && child.childNodes.length) collectTrs(child);
        }
    })(tableNode);

    const grid = trNodes.map(() => []);
    for (let r = 0; r < trNodes.length; r++) {
        const cellNodes = (trNodes[r].childNodes || [])
            .filter((n) => n.nodeName === "TD" || n.nodeName === "TH");
        let col = 0;
        for (const cell of cellNodes) {
            // Skip past columns already filled by previous-row rowspans.
            while (grid[r][col] !== undefined) col += 1;
            const rowspan = parseInt((cell.getAttribute && cell.getAttribute("rowspan")) || "1", 10);
            const colspan = parseInt((cell.getAttribute && cell.getAttribute("colspan")) || "1", 10);
            // Convert the cell's inner HTML to inline markdown via the same
            // turndown service so formatting (bold/italic/links) survives.
            // Heading tags inside a cell would otherwise produce literal
            // `## ` prefixes in the markdown row (which renders as text,
            // not a heading) — downgrade <h*> to <strong> first so the
            // cell shows bold text instead. Newlines collapse to spaces
            // and pipes get escaped so the resulting row stays on one line.
            const innerHtml = (cell.innerHTML || "")
                .trim()
                .replace(/<h[1-6](\s[^>]*)?>/gi, "<strong>")
                .replace(/<\/h[1-6]>/gi, "</strong>");
            let cellMd = innerHtml ? turndownService.turndown(innerHtml) : "";
            cellMd = cellMd.trim().replace(/\n+/g, " ").replace(/\|/g, "\\|");
            // Place value in top-left of the merge, leave the rest empty
            // (but `defined`, so the slot-skip loop above works correctly).
            for (let dr = 0; dr < rowspan; dr++) {
                for (let dc = 0; dc < colspan; dc++) {
                    if (!grid[r + dr]) grid[r + dr] = [];
                    grid[r + dr][col + dc] = (dr === 0 && dc === 0) ? cellMd : "";
                }
            }
            col += colspan;
        }
    }

    const maxCols = Math.max(0, ...grid.map((row) => row.length));
    if (maxCols === 0) return "";
    for (const row of grid) {
        while (row.length < maxCols) row.push("");
        for (let i = 0; i < row.length; i++) {
            if (row[i] === undefined) row[i] = "";
        }
    }
    const lines = [];
    for (let r = 0; r < grid.length; r++) {
        lines.push("| " + grid[r].join(" | ") + " |");
        if (r === 0) lines.push("|" + "---|".repeat(maxCols));
    }
    return "\n\n" + lines.join("\n") + "\n\n";
}

function buildTurndown() {
    const turndownService = new TurndownService({
        headingStyle: "atx",
        codeBlockStyle: "fenced",
    });
    turndownService.use(turndownPluginGfm.gfm);
    // Override the table rule to handle rowspan/colspan correctly.
    // Per-cell and per-row rules become unused, but we keep table-section
    // pass-through so <thead>/<tbody>/<tfoot> don't add stray content.
    turndownService.addRule("table", {
        filter: (node) => node.nodeName === "TABLE",
        replacement: (_content, node) => expandTableToGrid(node, turndownService),
    });
    turndownService.addRule("tableSection", {
        filter: ["thead", "tbody", "tfoot"],
        replacement: (content) => content,
    });
    return turndownService;
}

// ---- Build header/footer prefix block -----------------------------------

function buildHeaderFooterPrefix(hfImages, conversions) {
    if (hfImages.length === 0) return "";
    const hfFinal = hfImages.map((img) => ({
        source: img.source,
        filename: conversions.get(img.filename) || img.filename,
    }));
    const grouped = hfFinal.reduce((acc, img) => {
        (acc[img.source] = acc[img.source] || []).push(img.filename);
        return acc;
    }, {});
    const parts = ["<!-- Document header/footer images extracted from the source .docx. -->"];
    for (const src of Object.keys(grouped).sort()) {
        parts.push(`<!-- ${src} -->`);
        for (const fn of grouped[src]) {
            parts.push(`![](${encodeURI(path.posix.join(imagesDirName, fn))})`);
        }
    }
    return parts.join("\n") + "\n\n";
}

// ---- Main pipeline -------------------------------------------------------

console.log(`Converting:\n  Input:  ${inputDocx}\n  Output: ${outputMd}`);
mammoth
    .convertToHtml({ path: inputDocx }, mammothOptions)
    .then((result) => {
        if (result.messages.length > 0) {
            console.warn("Mammoth notices:");
            result.messages.forEach((m) => console.warn(` - ${m.type}: ${m.message}`));
        }
        const bodyMarkdown = buildTurndown().turndown(result.value);

        return Promise.all([
            extractHeaderFooterImages(ctx, inputDocx),
            extractBodyDrawings(inputDocx, ctx),
        ]).then(([hfImages, bodyDrawings]) => {
            const conversions = batchConvertEmfToPng(ctx);
            const patchedBody = rewriteEmfHrefsToPng(ctx, bodyMarkdown, conversions);
            const prefix = buildHeaderFooterPrefix(hfImages, conversions);

            let markdown = prefix + patchedBody;
            markdown = injectMissingShapeDiagrams(markdown, bodyDrawings, ctx);
            markdown = collapseDuplicateImageRuns(markdown);
            markdown = dropTinyImageRefs(markdown, ctx);
            markdown = dropEmptyHeadings(markdown);
            markdown = applyHeadingNumberingFromTOC(markdown);
            markdown = injectTocAnchors(markdown);

            fs.writeFileSync(outputMd, markdown, "utf8");
            console.log(
                `\nSuccessfully converted. Extracted ${ctx.seenHashes.size} unique image(s); ` +
                `header/footer assets: ${hfImages.length}; EMF converted to PNG: ${conversions.size}/${ctx.emfFilenames.length}.`,
            );
        });
    })
    .catch((err) => {
        console.error("Error during conversion:", err);
        process.exit(1);
    });
