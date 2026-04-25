// Shape-group extraction + rendering. The flow:
//
//   1. extractBodyDrawings(docxPath) — parses word/document.xml and pulls
//      each <w:drawing> with its <wp:extent> (EMU size), <wp:effectExtent>
//      (shadow/stroke padding), and <wp:positionH/V> (frame-relative
//      offsets). Returns Array<Drawing>.
//
//   2. renderViaLibreOfficeHtml(docxPath, ctx) — exports the same docx
//      through soffice's HTML filter to get ordered <img> references with
//      anchor text. LO HTML is our POSITION ORACLE — it tells us where
//      shapes appear in paragraph-flow order; we use that to locate them
//      in the mammoth-produced markdown.
//
//   3. renderShapesViaPdfCrop(docxPath, loImages, drawings, ctx) —
//      converts docx→PDF via soffice, parses per-page text bboxes via
//      pdftotext -bbox-layout, and for each drawing uses its extent + the
//      anchor paragraph's PDF position to crop exactly the shape region
//      via pdftoppm -x -y -W -H. Returns {srcToPng, tmpDir}.
//
//   4. injectMissingShapeDiagrams(markdown, bodyDrawings, ctx) — splices
//      the rendered images into the markdown at the right paragraph
//      boundaries and drops the stranded shape-text labels mammoth left
//      behind.

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const os = require("os");
const { execFileSync } = require("child_process");

const { normalizeForMatching } = require("./_util");

// ---- Drawing extraction from docx XML ------------------------------------

// Walk word/document.xml and pull every <w:drawing> with its <wp:extent>
// (size in EMU; 12700 EMU = 1pt) plus the descriptive text that precedes
// the drawing. Source-of-truth for diagram DIMENSIONS; the PDF is only
// used for positioning.
//
// Word shape groups carry NESTED <w:p> elements inside text-frames
// (<w:txbxContent>), so a naïve "split by <w:p>" breaks. We locate each
// <w:drawing> by absolute offset, take a sliding window of XML before it,
// scrub earlier drawings/picts out of the window (their text-frame content
// would pollute the anchor), and pull <w:t> tokens from what remains.
// -- Helpers: namespace- and attribute-order-tolerant matchers ------------

// Strip namespace prefixes so the same regex works whether the doc uses
// `w:drawing`, `wx:drawing`, or unprefixed `drawing`. Strip is carefully
// scoped to TAG INTERNALS only — we never touch text content, because
// text can legitimately contain "word:word" patterns (e.g., "Process:
// approved"). Doing a global `\s+WORD:` strip would eat those.
function stripOoxmlNamespacePrefixes(xml) {
    // Tag-name prefixes. Tag syntax is strict: always `<NAME` or `</NAME`
    // with no whitespace between `<` and name — so matching `<w:` or
    // `</w:` inside text content is essentially impossible (would require
    // a literal `<` character in text, which is always XML-escaped as
    // `&lt;`). Safe to replace globally.
    xml = xml.replace(/<(\/?)[a-zA-Z][a-zA-Z0-9]*:/g, "<$1");
    // Attribute-name prefixes. Scope the strip to inside each tag's angle
    // brackets so we don't match text like "Process: approved". The inner
    // regex matches `(space)WORD:ATTR=` and drops WORD+colon.
    xml = xml.replace(/<[^>]+>/g, (tag) =>
        tag.replace(/(\s)[a-zA-Z][a-zA-Z0-9]*:([a-zA-Z][a-zA-Z0-9]*=)/g, "$1$2"),
    );
    return xml;
}

// Read a named attribute from a tag matched by a regex. Works regardless
// of attribute order.
function readAttr(tagText, attrName) {
    const re = new RegExp(`\\b${attrName}="([^"]*)"`);
    const m = re.exec(tagText);
    return m ? m[1] : null;
}

// -- Document XML parsing --------------------------------------------------

async function extractBodyDrawings(docxPath, ctx) {
    const JSZip = require("jszip");
    const data = fs.readFileSync(docxPath);
    const zip = await JSZip.loadAsync(data);
    const entry = zip.file("word/document.xml");
    if (!entry) return [];
    const rawXml = await entry.async("string");
    // Strip OOXML namespace prefixes once so every downstream regex works
    // whether the doc uses `w:`, `wp:`, `w14:`, or no prefix at all.
    const xml = stripOoxmlNamespacePrefixes(rawXml);
    const decode = (s) => s
        .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"').replace(/&#39;/g, "'");

    // Multi-section docs have multiple <sectPr> blocks with their own
    // <pgMar>/<pgSz>. Each section applies from the previous section's
    // position onward. We collect (endOffset, leftPt, topPt, widthPt,
    // heightPt) tuples and resolve per-drawing by looking up the section
    // whose range covers the drawing's offset.
    const sections = [];
    const sectPrRe = /<sectPr\b[^>]*>[\s\S]*?<\/sectPr>/g;
    let sm;
    while ((sm = sectPrRe.exec(xml)) !== null) {
        const sect = sm[0];
        const mar = /<pgMar\b([^/]*)\/?>/.exec(sect);
        const sz = /<pgSz\b([^/]*)\/?>/.exec(sect);
        // twentieths-of-a-point → pt
        const leftTw = mar ? readAttr("<m " + mar[1], "left") : null;
        const topTw = mar ? readAttr("<m " + mar[1], "top") : null;
        const wTw = sz ? readAttr("<s " + sz[1], "w") : null;
        const hTw = sz ? readAttr("<s " + sz[1], "h") : null;
        sections.push({
            endOffset: sm.index + sm[0].length,
            leftMarginPt: leftTw ? parseInt(leftTw, 10) / 20 : 72,
            topMarginPt:  topTw  ? parseInt(topTw, 10)  / 20 : 72,
            pageWidthPt:  wTw    ? parseInt(wTw, 10)    / 20 : 612,
            pageHeightPt: hTw    ? parseInt(hTw, 10)    / 20 : 792,
        });
    }
    // A drawing at offset X takes the section whose endOffset >= X (first
    // match in document order). If no section follows, use the last
    // section's geometry (the doc-wide section at the end of body).
    function sectionForOffset(offset) {
        for (const s of sections) {
            if (s.endOffset >= offset) return s;
        }
        return sections.length > 0
            ? sections[sections.length - 1]
            : { leftMarginPt: 72, topMarginPt: 72, pageWidthPt: 612, pageHeightPt: 792 };
    }

    const drawingRe = /<drawing\b[^>]*>[\s\S]*?<\/drawing>/g;
    const extentTagRe = /<extent\b([^/>]*)\/?>/;
    const effectExtentTagRe = /<effectExtent\b([^/>]*)\/?>/;
    const positionVRe = /<positionV\b([^>]*)>([\s\S]*?)<\/positionV>/;
    const positionHRe = /<positionH\b([^>]*)>([\s\S]*?)<\/positionH>/;
    const posOffsetRe = /<posOffset>(-?\d+)<\/posOffset>/;
    const alignRe = /<align>([^<]+)<\/align>/;

    const drawings = [];
    let m;
    while ((m = drawingRe.exec(xml)) !== null) {
        const extTag = extentTagRe.exec(m[0]);
        if (!extTag) continue;
        const cx = readAttr("<e " + extTag[1], "cx");
        const cy = readAttr("<e " + extTag[1], "cy");
        if (!cx || !cy) continue;

        // Shape-group detection. The poppler PDF-crop pipeline is only
        // appropriate for multi-shape diagrams that mammoth flattens to
        // disjointed text. Plain `<pic:pic>` images and single-shape
        // drawings (one `<wsp>`, typical for decorative banners or
        // single-text-frame callouts) are NOT shape groups: mammoth
        // already handles `<pic:pic>` as embedded images, and tiny
        // single-shape drawings risk wrong crops because their position
        // resolution is fragile. After namespace strip, multi-shape
        // groups have either an explicit `<wgp>` (group container) or
        // multiple `<wsp>` siblings.
        const hasGroup = /<wgp\b|<group\b/.test(m[0]);
        const hasWsps = (m[0].match(/<wsp\b/g) || []).length;
        const isShapeGroup = hasGroup || hasWsps >= 2;
        if (!isShapeGroup) continue;

        const effTag = effectExtentTagRe.exec(m[0]);
        const effectLeftPt   = effTag ? Math.max(0, parseInt(readAttr("<e " + effTag[1], "l") || "0", 10)) / 12700 : 0;
        const effectTopPt    = effTag ? Math.max(0, parseInt(readAttr("<e " + effTag[1], "t") || "0", 10)) / 12700 : 0;
        const effectRightPt  = effTag ? Math.max(0, parseInt(readAttr("<e " + effTag[1], "r") || "0", 10)) / 12700 : 0;
        const effectBottomPt = effTag ? Math.max(0, parseInt(readAttr("<e " + effTag[1], "b") || "0", 10)) / 12700 : 0;

        const section = sectionForOffset(m.index);

        // --- Vertical position: resolve all frames, not just "paragraph" ---
        const posV = positionVRe.exec(m[0]);
        let yTopAbsPt = null;          // absolute PDF Y for drawing top (if resolvable here)
        let posOffsetParaPt = null;    // paragraph-relative offset (resolved in crop fn)
        if (posV) {
            const vFrame = readAttr("<p " + posV[1], "relativeFrom");
            const vAlign = alignRe.exec(posV[2]);
            const vOffsetMatch = posOffsetRe.exec(posV[2]);
            const vOffsetPt = vOffsetMatch ? parseInt(vOffsetMatch[1], 10) / 12700 : null;
            if (vAlign) {
                // <align>top|center|bottom|inside|outside</align>
                // We treat center/top identically at crop time — anchor-
                // block position from the PDF is our fallback.
                if (vFrame === "page" && vAlign[1] === "top") yTopAbsPt = 0;
                else if (vFrame === "page" && vAlign[1] === "bottom") yTopAbsPt = section.pageHeightPt - parseInt(cy, 10) / 12700;
                // other combinations: leave null → PDF fallback
            } else if (vOffsetPt !== null) {
                if (vFrame === "page") {
                    yTopAbsPt = vOffsetPt;
                } else if (vFrame === "margin" || vFrame === "topMargin") {
                    yTopAbsPt = section.topMarginPt + vOffsetPt;
                } else if (vFrame === "paragraph") {
                    posOffsetParaPt = vOffsetPt;
                }
                // "line", "bottomMargin", "insideMargin", "outsideMargin":
                // leave unresolved and fall back to PDF-anchor estimation.
            }
        }

        // --- Horizontal position: resolve all frames ---
        const posH = positionHRe.exec(m[0]);
        let xLeftPt = null;
        if (posH) {
            const hFrame = readAttr("<p " + posH[1], "relativeFrom");
            const hAlign = alignRe.exec(posH[2]);
            const hOffsetMatch = posOffsetRe.exec(posH[2]);
            const hOffsetPt = hOffsetMatch ? parseInt(hOffsetMatch[1], 10) / 12700 : null;
            const widthPt = parseInt(cx, 10) / 12700;
            const textAreaWidthPt = section.pageWidthPt - 2 * section.leftMarginPt;
            if (hAlign) {
                // <align>left|center|right|inside|outside</align>
                const a = hAlign[1];
                if (hFrame === "page" && a === "left") xLeftPt = 0;
                else if (hFrame === "page" && a === "right") xLeftPt = section.pageWidthPt - widthPt;
                else if (hFrame === "page" && a === "center") xLeftPt = (section.pageWidthPt - widthPt) / 2;
                else if (a === "left") xLeftPt = section.leftMarginPt;
                else if (a === "right") xLeftPt = section.leftMarginPt + textAreaWidthPt - widthPt;
                else if (a === "center") xLeftPt = section.leftMarginPt + (textAreaWidthPt - widthPt) / 2;
            } else if (hOffsetPt !== null) {
                if (hFrame === "page") {
                    xLeftPt = hOffsetPt;
                } else if (hFrame === "column" || hFrame === "margin" || hFrame === "leftMargin") {
                    xLeftPt = section.leftMarginPt + hOffsetPt;
                } else if (hFrame === "rightMargin") {
                    xLeftPt = section.pageWidthPt - section.leftMarginPt + hOffsetPt;
                }
                // "character", "insideMargin", "outsideMargin": leave null.
            }
        }

        // --- Descriptive anchor text ---
        const windowStart = Math.max(0, m.index - 8000);
        let pre = xml.slice(windowStart, m.index)
            .replace(/<drawing\b[^>]*>[\s\S]*?<\/drawing>/g, "")
            .replace(/<pict\b[^>]*>[\s\S]*?<\/pict>/g, "");
        const textRe = /<t\b[^>]*>([^<]*)<\/t>/g;
        const tokens = [];
        let tm;
        while ((tm = textRe.exec(pre)) !== null) {
            tokens.push(decode(tm[1]));
        }
        const allText = tokens.join(" ").replace(/\s+/g, " ").trim();
        const anchorText = allText.slice(-300);

        drawings.push({
            anchorText,
            widthPt: parseInt(cx, 10) / 12700,
            heightPt: parseInt(cy, 10) / 12700,
            effectLeftPt, effectRightPt, effectTopPt, effectBottomPt,
            posOffsetPt: posOffsetParaPt, // legacy name kept for callers
            yTopAbsPt,   // absolute PDF Y if resolved from page/margin/topMargin frame
            xLeftPt,     // resolved X or null for fallback
        });
    }
    return drawings;
}

// ---- LibreOffice HTML export as position oracle --------------------------

// LibreOffice HTML export renders each <w:drawing> as an inline <img>, in
// document order, surrounded by its source paragraph text. We use that as
// a POSITION oracle (not a render — geometry-only bitmaps). Returns
// { images: Array<{src, absPath, anchor}>, htmlDir }. Caller owns htmlDir
// cleanup.
function renderViaLibreOfficeHtml(docxPath, ctx) {
    if (!ctx.soffice) return { images: [], htmlDir: null };
    const htmlDir = fs.mkdtempSync(path.join(os.tmpdir(), "docx2md-lohtml-"));
    const copy = path.join(htmlDir, "source.docx");
    fs.copyFileSync(docxPath, copy);
    try {
        execFileSync(
            ctx.soffice,
            ["--headless", "--convert-to", "html", "--outdir", htmlDir, copy],
            { stdio: "ignore", timeout: 180000 },
        );
    } catch (e) {
        console.warn(`[docx-to-md] soffice HTML export failed: ${e.message} — shape-group diagrams may be missing.`);
        return { images: [], htmlDir };
    }
    const htmlPath = path.join(htmlDir, "source.html");
    if (!fs.existsSync(htmlPath)) return { images: [], htmlDir };
    const html = fs.readFileSync(htmlPath, "utf8");
    const stripTagsAndEntities = (s) =>
        s.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
         .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
         .replace(/<[^>]+>/g, " ")
         .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
         .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
         .replace(/&nbsp;|&#160;/g, " ")
         .replace(/\s+/g, " ")
         .trim();
    const images = [];
    const imgRe = /<img\b[^>]*\bsrc="([^"]+)"[^>]*>/gi;
    let lastIdx = 0;
    let m;
    while ((m = imgRe.exec(html)) !== null) {
        const src = m[1];
        const before = html.slice(lastIdx, m.index);
        const anchor = stripTagsAndEntities(before).slice(-240);
        const absPath = path.join(htmlDir, src);
        if (fs.existsSync(absPath)) {
            images.push({ src, absPath, anchor });
        }
        lastIdx = m.index + m[0].length;
    }
    return { images, htmlDir };
}

// ---- PDF bbox parsing ----------------------------------------------------

// Parse XHTML produced by `pdftotext -bbox-layout`. Returns an array of
// pages, each with width/height and a list of text blocks (bbox + joined
// word string). Coordinates are PDF points, top-left origin.
function parseBboxLayout(xhtml) {
    const pages = [];
    const pageRe = /<page\s+width="([\d.]+)"\s+height="([\d.]+)"[^>]*>([\s\S]*?)<\/page>/g;
    const blockRe = /<block\s+xMin="([\d.]+)"\s+yMin="([\d.]+)"\s+xMax="([\d.]+)"\s+yMax="([\d.]+)"[^>]*>([\s\S]*?)<\/block>/g;
    const wordRe = /<word[^>]*>([^<]*)<\/word>/g;
    const decode = (s) => s
        .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
        .replace(/&nbsp;|&#160;/g, " ");
    let pm;
    let pageNum = 0;
    while ((pm = pageRe.exec(xhtml)) !== null) {
        pageNum += 1;
        const width = parseFloat(pm[1]);
        const height = parseFloat(pm[2]);
        const body = pm[3];
        const blocks = [];
        let bm;
        blockRe.lastIndex = 0;
        while ((bm = blockRe.exec(body)) !== null) {
            const xMin = parseFloat(bm[1]);
            const yMin = parseFloat(bm[2]);
            const xMax = parseFloat(bm[3]);
            const yMax = parseFloat(bm[4]);
            const inner = bm[5];
            const words = [];
            let wm;
            wordRe.lastIndex = 0;
            while ((wm = wordRe.exec(inner)) !== null) {
                words.push(decode(wm[1]));
            }
            blocks.push({ xMin, yMin, xMax, yMax, text: words.join(" ") });
        }
        pages.push({ pageNum, width, height, blocks });
    }
    return pages;
}

// Locate the anchor paragraph in parsed PDF bbox-layout pages. Tries
// progressively shorter suffixes of the anchor text and reverse-iterates
// pages (body matches beat accidental earlier-page substring matches).
function findAnchorBlockInPdf(pages, anchorText) {
    if (!anchorText) return null;
    const SUFFIX_LENGTHS = [200, 140, 100, 70, 50];
    for (const len of SUFFIX_LENGTHS) {
        const needle = normalizeForMatching(anchorText.slice(-len));
        if (needle.length < 15) continue;
        for (let p = pages.length - 1; p >= 0; p--) {
            const page = pages[p];
            for (let b = page.blocks.length - 1; b >= 0; b--) {
                if (normalizeForMatching(page.blocks[b].text).includes(needle)) {
                    return { page, block: page.blocks[b] };
                }
            }
        }
    }
    return null;
}

// Compute the PDF crop region for one drawing. Position resolution
// precedence:
//   1. drawing.yTopAbsPt — if the XML specified a "page"/"margin"/
//      "topMargin" relativeFrom, we have an exact page-absolute Y.
//   2. drawing.posOffsetPt — "paragraph" relativeFrom: offset from
//      anchor.yMin.
//   3. Label-inset inference from the drawing's own text labels as found
//      in the PDF (symmetric inset between extent and labels span).
//   4. Line-height fallback when the drawing has no labels.
//
// Size comes from the drawing's <wp:extent> + <wp:effectExtent>. Breathing
// room comes from the anchor block's own line height.
function computeDrawingCropBbox(pages, drawing) {
    const hit = findAnchorBlockInPdf(pages, drawing.anchorText);
    if (!hit) return null;
    const { page, block } = hit;

    const blockHeight = block.yMax - block.yMin;
    const linesInBlock = Math.max(1, Math.round(blockHeight / 14));
    const lineHeightPt = blockHeight / linesInBlock;

    // Labels candidate set: text blocks BELOW the anchor AND within the
    // drawing's expected vertical range (extent + small buffer). This
    // bounding is critical: an unbounded "all blocks below anchor" search
    // would treat regular body prose as if it were drawing labels —
    // pdftotext can't tell the difference, so we use the drawing's own
    // <wp:extent> as the boundary.
    const below = page.blocks
        .filter((b) =>
            b.yMin > block.yMax &&
            b.yMin < block.yMax + drawing.heightPt + lineHeightPt * 2,
        )
        .sort((a, b) => a.yMin - b.yMin);

    let drawingTopPt;
    if (drawing.yTopAbsPt !== null && drawing.yTopAbsPt !== undefined) {
        // Absolute frame (page/margin/topMargin): trust directly.
        drawingTopPt = drawing.yTopAbsPt;
    } else if (below.length > 0) {
        // Labels found inside the drawing's expected region. The
        // symmetric-inset method gives us the drawing's top: drawing
        // wraps its labels with equal padding on each side, so
        // inset = (extent - labelsSpan) / 2.
        const firstLabel = below[0];
        const lastLabel = below[below.length - 1];
        const labelsSpan = lastLabel.yMax - firstLabel.yMin;
        // Sanity: labels can't physically span more than the drawing's
        // own extent. If somehow labelsSpan > extent, our search bound
        // failed; bail to the GIF fallback rather than risk a wrong crop.
        if (labelsSpan > drawing.heightPt) return null;
        const insetPt = Math.max(0, (drawing.heightPt - labelsSpan) / 2);
        drawingTopPt = firstLabel.yMin - insetPt;
    } else if (drawing.heightPt < 100) {
        // Small drawing with no labels in its expected region — likely
        // an icon. Place at paragraph cursor; misplacement is bounded
        // by the drawing's small height.
        drawingTopPt = block.yMax + lineHeightPt;
    } else {
        // Larger drawing with no labels in the expected region — most
        // commonly an inline raster (photo, chart screenshot, etc.) that
        // mammoth already extracts as `<pic:pic>`. We don't have a
        // reliable PDF position; abort the crop so the injection
        // pipeline falls back to the LO HTML GIF.
        return null;
    }
    const drawingBottomPt = drawingTopPt + drawing.heightPt + drawing.effectBottomPt;

    const breathingPt = lineHeightPt;
    const yTop = Math.max(
        0,
        Math.max(block.yMax, drawingTopPt - breathingPt - drawing.effectTopPt),
    );
    const yBottom = Math.min(page.height, drawingBottomPt + breathingPt);

    const xLeftPt = drawing.xLeftPt !== null ? drawing.xLeftPt : block.xMin;
    const xLeft = Math.max(0, xLeftPt - drawing.effectLeftPt);
    const widthPt = drawing.widthPt + drawing.effectLeftPt + drawing.effectRightPt;
    const xRight = Math.min(page.width, xLeft + widthPt);

    return {
        pageNum: page.pageNum,
        x: xLeft,
        y: yTop,
        width: xRight - xLeft,
        height: yBottom - yTop,
    };
}

// Pair an LO HTML <img> (position-oracle) to one of the docx body drawings
// (extent-oracle) by longest tail of the drawing's anchorText found inside
// loImg's preceding-text anchor.
function matchLoImgToDrawing(loImg, drawings) {
    const normLoAnchor = normalizeForMatching(loImg.anchor);
    let best = null;
    let bestNeedleLen = 0;
    for (const d of drawings) {
        const normDraw = normalizeForMatching(d.anchorText);
        if (normDraw.length < 15) continue;
        const needle = normDraw.slice(-Math.min(80, normDraw.length));
        if (normLoAnchor.includes(needle) && needle.length > bestNeedleLen) {
            bestNeedleLen = needle.length;
            best = d;
        }
    }
    return best;
}

// ---- Poppler PDF-crop rendering ------------------------------------------

// Renders each shape-group diagram by cropping its exact region from a
// rasterised PDF page. Returns { srcToPng: Map<loImg.src, absPngPath>,
// tmpDir } or null on failure. Caller owns tmpDir cleanup.
function renderShapesViaPdfCrop(docxPath, loImages, drawings, ctx) {
    if (!ctx.poppler || !ctx.soffice) return null;
    if (!drawings || drawings.length === 0) return null;
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "docx2md-pdfshape-"));
    try {
        const srcCopy = path.join(tmpDir, "source.docx");
        fs.copyFileSync(docxPath, srcCopy);
        const env = { ...process.env };
        if (process.platform !== "darwin") env.SAL_USE_VCLPLUGIN = "svp";
        execFileSync(
            ctx.soffice,
            ["--headless", "--convert-to", "pdf", "--outdir", tmpDir, srcCopy],
            { stdio: "ignore", timeout: 180000, env },
        );
        const pdfPath = path.join(tmpDir, "source.pdf");
        if (!fs.existsSync(pdfPath)) throw new Error("soffice did not produce source.pdf");

        const bboxPath = path.join(tmpDir, "bbox.html");
        execFileSync(
            ctx.poppler.pdftotext,
            ["-bbox-layout", pdfPath, bboxPath],
            { stdio: "ignore", timeout: 60000 },
        );
        const pages = parseBboxLayout(fs.readFileSync(bboxPath, "utf8"));
        if (pages.length === 0) throw new Error("no pages parsed from bbox-layout");

        const DPI = 150;
        const scale = DPI / 72;
        const srcToPng = new Map();
        for (const loImg of loImages) {
            const drawing = matchLoImgToDrawing(loImg, drawings);
            if (!drawing) continue;
            const bbox = computeDrawingCropBbox(pages, drawing);
            if (!bbox) continue;
            const xPx = Math.max(0, Math.floor(bbox.x * scale));
            const yPx = Math.max(0, Math.floor(bbox.y * scale));
            const wPx = Math.floor(bbox.width * scale);
            const hPx = Math.floor(bbox.height * scale);
            if (wPx < 50 || hPx < 50) continue;
            const prefix = path.join(tmpDir, `shape_p${bbox.pageNum}_y${yPx}`);
            try {
                execFileSync(
                    ctx.poppler.pdftoppm,
                    [
                        "-r", String(DPI),
                        "-png",
                        "-f", String(bbox.pageNum),
                        "-l", String(bbox.pageNum),
                        "-x", String(xPx),
                        "-y", String(yPx),
                        "-W", String(wPx),
                        "-H", String(hPx),
                        pdfPath, prefix,
                    ],
                    { stdio: "ignore", timeout: 60000 },
                );
            } catch (_) { continue; }
            const base = path.basename(prefix);
            const produced = fs.readdirSync(tmpDir).filter(
                (f) => f.startsWith(`${base}-`) && f.endsWith(".png"),
            );
            if (produced.length > 0) {
                srcToPng.set(loImg.src, path.join(tmpDir, produced[0]));
            }
        }
        return { srcToPng, tmpDir };
    } catch (e) {
        console.warn(`[docx-to-md] poppler PDF-crop render failed: ${e.message}`);
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) { /* best-effort */ }
        return null;
    }
}

// ---- Markdown helpers used during injection ------------------------------

// Find the best markdown line to inject an image below, using the LO anchor.
// Reverse-iterates so body matches win over TOC matches when a heading text
// appears in both.
function findAnchorInsertionLine(normalizedLines, anchor) {
    for (const len of [160, 120, 80, 60, 40]) {
        const needle = normalizeForMatching(anchor.slice(-len));
        if (needle.length < 15) continue;
        for (let i = normalizedLines.length - 1; i >= 0; i--) {
            if (normalizedLines[i].includes(needle)) {
                return i + 1;
            }
        }
    }
    return -1;
}

// Return true if any markdown image ref within ±window of `line` points at
// an asset >= sizeThreshold bytes. Used to skip LO injection where a real
// diagram is already present (mammoth-extracted EMF that's been PNG-converted).
function nearbyHasSubstantialImage(lines, line, sizeThresholdBytes, ctx) {
    const lo = Math.max(0, line - 2);
    const hi = Math.min(lines.length, line + 20);
    const imgRe = /!\[[^\]]*\]\(([^)]+)\)/g;
    const segment = ctx.imagesDirName + "/";
    for (let i = lo; i < hi; i++) {
        let m;
        imgRe.lastIndex = 0;
        while ((m = imgRe.exec(lines[i])) !== null) {
            const href = decodeURIComponent(m[1]);
            const idx = href.indexOf(segment);
            if (idx < 0) continue;
            const filename = href.slice(idx + segment.length);
            try {
                const size = fs.statSync(path.join(ctx.imagesDirPath, filename)).size;
                if (size >= sizeThresholdBytes) return true;
            } catch (_) { /* missing asset — not substantial */ }
        }
    }
    return false;
}

// Detect stranded shape-text lines that mammoth extracts from
// <w:txbxContent>. After we inject the shape bitmap these labels become
// redundant. Stops at the first clear document-structure marker.
function findStrandedShapeTextLines(lines, startLine) {
    const MAX_SCAN = 150;
    const MAX_DROPS = 80;
    const toDrop = new Set();
    const end = Math.min(lines.length, startLine + MAX_SCAN);
    for (let i = startLine; i < end; i++) {
        if (toDrop.size >= MAX_DROPS) break;
        const trimmed = lines[i].trim();
        if (trimmed === "") continue;
        if (/^#{1,6}\s/.test(trimmed)) break;
        if (/^\|/.test(trimmed)) break;
        if (/^(\*|-|\d+\.)\s/.test(trimmed)) break;
        if (/^\[.+\]\(#/.test(trimmed)) break;
        if (/^>/.test(trimmed)) break;
        if (/^---+$|^\*\*\*+$/.test(trimmed)) break;
        if (/^!\[/.test(trimmed)) continue;
        toDrop.add(i);
    }
    return toDrop;
}

// ---- Top-level injection pipeline ----------------------------------------

// Mammoth misses shape-group / SmartArt drawings. We use LO HTML export to
// LOCATE them (ordered <img> + anchor text) and poppler PDF-crop to RENDER
// (includes text inside shapes). Fallback to LO HTML GIF (geometry only)
// when poppler is unavailable.
function injectMissingShapeDiagrams(markdown, bodyDrawings, ctx) {
    // No real shape groups in the source docx → LO HTML images that pass
    // our filter are page-level decorations / single-shape callouts /
    // duplicates of mammoth-extracted pictures. Injecting them via LO
    // HTML GIF produces near-empty bitmaps. Skip entirely.
    if (!bodyDrawings || bodyDrawings.length === 0) return markdown;
    const { images: loImages, htmlDir } = renderViaLibreOfficeHtml(ctx.inputDocx, ctx);
    let pdfRender = null;
    try {
        if (loImages.length === 0) return markdown;
        let lines = markdown.split("\n");
        const normalizedLines = lines.map(normalizeForMatching);

        const SUBSTANTIAL_ASSET_BYTES = 10 * 1024;
        const candidates = [];
        for (const loImg of loImages) {
            const line = findAnchorInsertionLine(normalizedLines, loImg.anchor);
            if (line < 0) continue;
            if (nearbyHasSubstantialImage(lines, line, SUBSTANTIAL_ASSET_BYTES, ctx)) continue;
            candidates.push({ line, loImg });
        }
        if (candidates.length === 0) return markdown;

        pdfRender = renderShapesViaPdfCrop(ctx.inputDocx, loImages, bodyDrawings, ctx);
        const srcToFilename = new Map();
        let pdfHits = 0;
        let fallbackHits = 0;
        for (const { loImg } of candidates) {
            if (srcToFilename.has(loImg.src)) continue;
            const pdfPath = pdfRender && pdfRender.srcToPng.get(loImg.src);
            const sourcePath = pdfPath || loImg.absPath;
            if (pdfPath) pdfHits += 1; else fallbackHits += 1;
            const buf = fs.readFileSync(sourcePath);
            const hash = crypto.createHash("sha1").update(buf).digest("hex");
            if (ctx.seenHashes.has(hash)) {
                srcToFilename.set(loImg.src, ctx.seenHashes.get(hash));
                continue;
            }
            const ext = path.extname(sourcePath).replace(/^\./, "").toLowerCase() || "png";
            const filename = `image_${String(ctx.counter.next()).padStart(3, "0")}.${ext}`;
            fs.writeFileSync(path.join(ctx.imagesDirPath, filename), buf);
            ctx.seenHashes.set(hash, filename);
            srcToFilename.set(loImg.src, filename);
        }

        candidates.sort((a, b) => b.line - a.line);
        let droppedLabelLines = 0;
        for (const { line, loImg } of candidates) {
            const filename = srcToFilename.get(loImg.src);
            if (!filename) continue;
            const href = encodeURI(path.posix.join(ctx.imagesDirName, filename));
            lines.splice(line, 0, "", `![](${href})`, "");
            const dropSet = findStrandedShapeTextLines(lines, line + 3);
            if (dropSet.size > 0) {
                const sorted = [...dropSet].sort((a, b) => b - a);
                for (const idx of sorted) {
                    lines.splice(idx, 1);
                    droppedLabelLines += 1;
                }
            }
        }
        // Compact double-blank runs.
        const compacted = [];
        let prevBlank = false;
        for (const line of lines) {
            const blank = line.trim() === "";
            if (blank && prevBlank) continue;
            compacted.push(line);
            prevBlank = blank;
        }
        lines = compacted;
        const totalLoImages = loImages.length;
        const skippedDueToExisting = totalLoImages - candidates.length;
        console.log(
            `[docx-to-md] Injected ${candidates.length} shape-group diagram(s)` +
            (pdfHits > 0 ? ` (${pdfHits} via poppler PDF-crop, ${fallbackHits} via LO HTML GIF)` : " (via LO HTML GIF)") +
            (skippedDueToExisting > 0 ? `; skipped ${skippedDueToExisting} LO image(s) already covered by mammoth-extracted assets` : "") +
            (droppedLabelLines > 0 ? `; removed ${droppedLabelLines} stranded label line(s).` : "."),
        );
        return lines.join("\n");
    } finally {
        if (htmlDir && fs.existsSync(htmlDir)) {
            try { fs.rmSync(htmlDir, { recursive: true, force: true }); } catch (_) { /* best-effort */ }
        }
        if (pdfRender && pdfRender.tmpDir && fs.existsSync(pdfRender.tmpDir)) {
            try { fs.rmSync(pdfRender.tmpDir, { recursive: true, force: true }); } catch (_) { /* best-effort */ }
        }
    }
}

module.exports = {
    extractBodyDrawings,
    parseBboxLayout,
    findAnchorBlockInPdf,
    computeDrawingCropBbox,
    matchLoImgToDrawing,
    injectMissingShapeDiagrams,
    findAnchorInsertionLine,
    nearbyHasSubstantialImage,
    findStrandedShapeTextLines,
};
