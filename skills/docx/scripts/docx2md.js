// docx → markdown CLI. Main entry; orchestrates the pipeline and delegates
// domain logic to ./docx2md/_{util,probes,assets,shapes,markdown,metadata}.js.
//
// Flow:
//   1. Probe external tools (soffice, poppler) and load npm deps.
//   2. Create output assets dir (refusing symlinks).
//   3. Build shared ctx (paths, counters, dedup maps, tool handles).
//   4. Read .docx into a JSZip; pull metadata sidecar (comments + revisions)
//      and footnote/endnote definitions; rewrite footnote/endnote references
//      in document.xml to ⟦FN:N⟧ / ⟦EN:N⟧ sentinels (docx-4 + docx-5).
//   5. Mammoth: modified docx buffer → HTML (with image callback).
//   6. Turndown: HTML → markdown with custom table rules.
//   7. In parallel: extract header/footer images + extract shape drawings.
//   8. Batch-convert collected EMFs to PNG; rewrite markdown refs.
//   9. Prepend header/footer block; inject shape diagrams.
//  10. Collapse duplicate image runs; apply TOC numbering; inject TOC anchors.
//  11. Restore footnote/endnote sentinels to pandoc `[^fn-N]` / `[^en-N]`
//      and append definitions block.
//  12. Write final markdown + (if non-empty) the sidecar JSON.

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
const metadataMod = require("./docx2md/_metadata");

// ---- CLI args ------------------------------------------------------------
//
// Positional: <input.docx> <output.md>.
// Flags:
//   --metadata-json PATH   override sidecar path (default: <output.md base>.docx2md.json)
//   --no-metadata          skip comment/revision extraction; do not write sidecar
//   --no-footnotes         skip footnote/endnote conversion; behave like pre-docx-5
//   --json-errors          emit single-line JSON envelope on stderr for top-level failures

const argv = process.argv.slice(2);
let inputDocx, outputMd;
let metadataJsonPath = null;
let extractMetadataFlag = true;
let convertFootnotesFlag = true;
let jsonErrors = false;
{
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === "--metadata-json") {
            // VDD MED-2: refuse to swallow the next flag as our path.
            const v = argv[i + 1];
            if (v == null || v.startsWith("--")) {
                // jsonErrors flag may not yet be set; fall back to plain text
                // here intentionally — UsageError envelope is reported below
                // through the regular reportError path.
                process.stderr.write("--metadata-json requires a path argument\n");
                process.exit(2);
            }
            metadataJsonPath = v;
            i += 1;
        }
        else if (a === "--no-metadata")  extractMetadataFlag = false;
        else if (a === "--no-footnotes") convertFootnotesFlag = false;
        else if (a === "--json-errors")  jsonErrors = true;
        else positional.push(a);
    }
    inputDocx = positional[0];
    outputMd  = positional[1];
}

// Single-line JSON envelope for top-level errors. Mirrors scripts/_errors.py
// shape and html2docx.js (cross-5). Defensive `code === 0` coerce to 1.
function reportError(msg, code, type, details) {
    if (code === 0) {
        details = Object.assign({ coerced_from_zero: true }, details || {});
        code = 1;
    }
    if (jsonErrors) {
        const env = { v: 1, error: String(msg), code };
        if (type) env.type = type;
        if (details && Object.keys(details).length) env.details = details;
        process.stderr.write(JSON.stringify(env) + "\n");
    } else {
        process.stderr.write(String(msg) + "\n");
    }
    process.exit(code);
}

if (!inputDocx || !outputMd) {
    reportError(
        "Usage: node docx2md.js <input.docx> <output.md> [--metadata-json PATH] [--no-metadata] [--no-footnotes] [--json-errors]",
        2, "UsageError",
    );
}

// VDD HIGH-1: cross-7 H1 same-path guard. Without this, `node docx2md.js
// foo.docx foo.docx` would overwrite the input docx with markdown text and
// destroy it irrecoverably (verified). realpath catches symlinks pointing
// at the same inode.
const inputAbs = path.resolve(inputDocx);
const outputAbs = path.resolve(outputMd);
function realPathOrSelf(p) {
    try { return fs.realpathSync.native(p); } catch (_) { return p; }
}
if (realPathOrSelf(inputAbs) === realPathOrSelf(outputAbs)) {
    reportError(
        `Refusing to overwrite input file: ${inputDocx}`,
        6, "SelfOverwriteRefused",
        { input: inputAbs, output: outputAbs },
    );
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

(async () => {
    // Read input as a buffer once. The buffer flows through metadata
    // extraction → sentinel injection → mammoth, so we never touch disk
    // for the same bytes more than necessary. (VDD LOW-5: async read so
    // big inputs don't block the event loop.)
    let inputBuffer;
    try {
        inputBuffer = await fs.promises.readFile(inputDocx);
    } catch (e) {
        reportError(`Cannot read input: ${e.message}`, 1, "InputReadError", { path: inputDocx });
    }

    const JSZip = loadDependency("jszip", SCRIPTS_DIR);
    const zip = await JSZip.loadAsync(inputBuffer);
    const parts = await metadataMod.loadDocxParts(zip);

    // docx-4: build sidecar from comments + revisions (sidecar-only, no
    // markdown pollution).
    let sidecar = null;
    if (extractMetadataFlag) {
        sidecar = metadataMod.buildSidecar(parts, path.basename(inputDocx));
    }

    // docx-5: extract footnote/endnote definitions BEFORE mutating XML
    // (the strip pass blanks bodies). Inject sentinels into document.xml
    // and silence mammoth's own footnote rendering.
    let notes = { footnotes: [], endnotes: [] };
    let mammothInput = { path: inputDocx };
    if (convertFootnotesFlag) {
        notes = metadataMod.extractFootnotesAndEndnotes(parts);
        if (notes.footnotes.length > 0 || notes.endnotes.length > 0) {
            metadataMod.injectFootnoteSentinels(parts, notes);
            const modBuf = await metadataMod.repackToBuffer(parts);
            mammothInput = { buffer: modBuf };
        }
    }

    let result;
    try {
        result = await mammoth.convertToHtml(mammothInput, mammothOptions);
    } catch (err) {
        reportError(`Mammoth failed: ${err.message}`, 1, "MammothError");
    }
    if (result.messages.length > 0) {
        console.warn("Mammoth notices:");
        result.messages.forEach((m) => console.warn(` - ${m.type}: ${m.message}`));
    }
    const bodyMarkdown = buildTurndown().turndown(result.value);

    const [hfImages, bodyDrawings] = await Promise.all([
        extractHeaderFooterImages(ctx, inputDocx),
        extractBodyDrawings(inputDocx, ctx),
    ]);
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

    // docx-5 post-pass: ⟦FN:N⟧ → [^fn-N], append definitions block.
    if (convertFootnotesFlag) {
        markdown = metadataMod.restoreFootnoteSentinels(markdown, notes);
    }

    fs.writeFileSync(outputMd, markdown, "utf8");

    // docx-4: write sidecar only if non-empty (avoid clutter on clean docs).
    if (sidecar) {
        const sidecarPath = metadataJsonPath
            ? path.resolve(metadataJsonPath)
            : path.join(outputDir, `${baseName}.docx2md.json`);
        fs.writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2) + "\n", "utf8");
        console.log(
            `Wrote sidecar: ${sidecarPath} ` +
            `(${sidecar.comments.length} comment(s), ${sidecar.revisions.length} revision(s)).`,
        );
    }

    console.log(
        `\nSuccessfully converted. Extracted ${ctx.seenHashes.size} unique image(s); ` +
        `header/footer assets: ${hfImages.length}; EMF converted to PNG: ${conversions.size}/${ctx.emfFilenames.length}` +
        (notes.footnotes.length || notes.endnotes.length
            ? `; footnotes: ${notes.footnotes.length}, endnotes: ${notes.endnotes.length}.`
            : "."),
    );
})().catch((err) => {
    reportError(`Error during conversion: ${err.message || err}`, 1, "ConversionError");
});
