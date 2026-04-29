// _html2docx_walker.js — HTML DOM (cheerio) → docx-js block tree.
//
// Self-contained walker. Pass `{ root, $, inputDir, extractedImages }`
// and receive `{ children, numberedListConfigs }` ready to drop into a
// docx Document section. Mirrors the styling decisions in md2docx.js
// (page width 9360 DXA, Arial 24, table header shading, bullets/numbers
// numbering config) so HTML→docx and Markdown→docx outputs look alike.

const fs = require('fs');
const path = require('path');
const cheerio = require('cheerio');
const sizeOf = require('image-size').imageSize;
const {
    Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, ExternalHyperlink,
    InternalHyperlink, Bookmark,
    HeadingLevel, BorderStyle, WidthType, ShadingType, LevelFormat, AlignmentType
} = require('docx');
const svgRender = require('./_html2docx_svg_render');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const contentWidthDxa = 9360;

const INLINE_STYLE_TAGS = {
    strong: { bold: true }, b: { bold: true },
    em: { italics: true }, i: { italics: true },
    u: { underline: true },
    s: { strike: true }, strike: { strike: true }, del: { strike: true },
    code: { code: true },
};

function isRemoteOrDataUrl(ref) {
    return /^https?:\/\//i.test(ref) || /^data:/i.test(ref);
}

// 1×1 fully transparent PNG. docx-js requires a raster fallback for
// `type: 'svg'` ImageRuns so legacy Word (pre-2016) has something to
// render. Modern Word/LibreOffice display the SVG itself.
const _TRANSPARENT_PNG = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64'
);

// Pull a length in pixels from common SVG / CSS forms ("955", "955px",
// "955.04px"). Returns null if the value can't be parsed. Percentages
// are explicitly rejected — the previous greedy regex matched "100" out
// of "100%" (which drawio uses for both SVG width and height attrs)
// and that propagated into Chrome's --window-size as 100×100, leaving
// the renderer to fall back to its default 1280×720 viewport and
// emit a wrong-aspect cropped PNG.
function _parsePixelLength(s) {
    if (!s) return null;
    const str = String(s).trim();
    if (/%/.test(str)) return null;
    const m = str.match(/^(-?\d+(?:\.\d+)?)\s*(px|pt)?$/i);
    if (!m) return null;
    let n = parseFloat(m[1]);
    if ((m[2] || '').toLowerCase() === 'pt') n = n * 96 / 72;
    if (!isFinite(n) || n <= 0) return null;
    return n;
}

// Drawio renders text labels as <foreignObject><div>…</div></foreignObject>
// (HTML-in-SVG). resvg-rust does not support foreignObject, so without
// pre-processing every label vanishes and shapes look like empty boxes.
// We can't easily reflow rich HTML, but Confluence's drawio output uses
// a predictable wrapper-div + nested-<div>/<br> pattern for line breaks
// that we can transcribe to a multi-line SVG <text> element with
// <tspan> rows.
//
// Honest scope: deeply-nested rich content (mixed-font/colour runs,
// embedded HTML lists, tables) is flattened to plain text per line.
function _drawioForeignObjectsToText(cheerio, svgXml) {
    if (!svgXml || svgXml.indexOf('<foreignObject') === -1) return svgXml;
    let $$;
    try {
        $$ = cheerio.load(svgXml, { xmlMode: true });
    } catch (_) {
        return svgXml;
    }
    function extractPx(style, prop) {
        if (!style) return null;
        // Unit MUST be present and MUST be px / pt. Drawio always emits px;
        // making the unit mandatory means em / rem / % / vw values return
        // null instead of being silently treated as raw pixels (a label
        // wrapper with `width: 5em` for a 14em label previously produced
        // `containerWidth=5` and mis-positioned anchors).
        const m = style.match(
            new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*(-?\\d+(?:\\.\\d+)?)\\s*(px|pt)\\b`, 'i')
        );
        if (!m) return null;
        let v = parseFloat(m[1]);
        if (m[2].toLowerCase() === 'pt') v = v * 96 / 72;
        return v;
    }
    function extractStyleProp(style, prop) {
        if (!style) return null;
        const m = style.match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, 'i'));
        return m ? m[1].trim() : null;
    }
    function escapeXml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
    }
    // cheerio's xmlMode does not decode HTML named entities (&nbsp; etc.)
    // — only the XML-standard set. drawio's HTML labels carry &nbsp;
    // freely, and without this map every non-breaking space stays as the
    // literal 7-character sequence in the rendered SVG.
    const _HTML_NAMED = {
        nbsp: 0xA0, ndash: 0x2013, mdash: 0x2014, hellip: 0x2026,
        lsquo: 0x2018, rsquo: 0x2019, ldquo: 0x201C, rdquo: 0x201D,
        laquo: 0xAB, raquo: 0xBB, copy: 0xA9, reg: 0xAE, trade: 0x2122,
        middot: 0xB7, bull: 0x2022, deg: 0xB0, times: 0xD7, divide: 0xF7,
    };
    function decodeHtmlEntities(s) {
        return s.replace(/&([a-zA-Z][a-zA-Z0-9]+);/g, (m, name) => {
            const code = _HTML_NAMED[name];
            return code !== undefined ? String.fromCharCode(code) : m;
        });
    }
    // Soft-wrap a single line so it fits within `maxWidthPx` at the given
    // `fontSize`. Drawio's HTML labels often have a long single-span body
    // with no <br> — without this the converted SVG <text> is one wide
    // line that overflows the shape's bounding box. Browsers handle this
    // via CSS `width:Npx; word-wrap`; resvg doesn't, so we approximate
    // here.
    //
    // Char-width is approximated as `fontSize × ratio`. Cyrillic glyphs
    // are noticeably wider than Latin in Helvetica/Arial, so detect them
    // and bump the ratio. The ratio is intentionally on the high side so
    // estimated lines fit slightly under the actual width — overflowing
    // a box is much more visually offensive than a half-character gap.
    function wrapText(text, maxWidthPx, fontSize) {
        if (!maxWidthPx || maxWidthPx <= 1) return [text];
        const hasCyrillic = /[Ѐ-ӿ]/.test(text);
        const charW = fontSize * (hasCyrillic ? 0.62 : 0.55);
        const maxChars = Math.max(5, Math.floor(maxWidthPx / charW));
        const words = text.split(/\s+/).filter(Boolean);
        if (!words.length) return [text];
        const lines = [];
        let current = '';
        for (const w of words) {
            const trial = current ? current + ' ' + w : w;
            if (trial.length <= maxChars) {
                current = trial;
            } else {
                if (current) lines.push(current);
                current = w;
            }
        }
        if (current) lines.push(current);
        return lines.length ? lines : [text];
    }

    // Walk the foreignObject DOM and split it into visual lines following
    // drawio's HTML conventions: <br> always starts a new line; sibling
    // block elements (<div>, <p>, <li>) close the current line and open
    // a new one. Inline elements (<span>, <font>) just contribute text.
    function extractLines(rootNode) {
        const lines = [''];
        function newline() {
            if (lines[lines.length - 1].trim() !== '') lines.push('');
        }
        function walk(n) {
            if (n.type === 'text') {
                lines[lines.length - 1] += n.data;
                return;
            }
            if (n.type !== 'tag') return;
            const name = (n.name || '').toLowerCase();
            if (name === 'br') { lines.push(''); return; }
            if (/^(div|p|li|tr|h[1-6])$/.test(name)) {
                newline();
                for (const c of n.children || []) walk(c);
                newline();
                return;
            }
            for (const c of n.children || []) walk(c);
        }
        walk(rootNode);
        return lines
            .map(l => decodeHtmlEntities(l).replace(/[ \t]+/g, ' ').trim())
            .filter(Boolean);
    }

    $$('foreignObject').each((_, el) => {
        const $fo = $$(el);
        // Outer wrapper div carries margin-left / padding-top + flex
        // alignment. Drawio always places exactly one wrapper div inside
        // foreignObject, but be defensive against missing children.
        const wrap = $fo.children().first();
        const wrapStyle = wrap.attr('style') || '';
        // margin-left is the LEFT EDGE of the flex container, NOT the text
        // anchor x. For justify-content:center the SVG anchor sits at
        // (left + width/2); for flex-end at (left + width). Treating
        // margin-left as the anchor x with text-anchor=middle would centre
        // every label at the container's left edge — labels uniformly
        // shifted left by half their box width.
        const xLeft = extractPx(wrapStyle, 'margin-left') || 0;
        const containerWidth = extractPx(wrapStyle, 'width') || 0;
        const y = extractPx(wrapStyle, 'padding-top') || 0;
        const justify = extractStyleProp(wrapStyle, 'justify-content') || '';
        const align = extractStyleProp(wrapStyle, 'align-items') || '';

        // Find the deepest div whose style sets font-family / font-size —
        // that is the run-style block drawio uses for the label.
        let runStyle = '';
        $fo.find('div').each((_, d) => {
            const s = $$(d).attr('style') || '';
            if (/font-family|font-size|font-weight/i.test(s)) runStyle = s;
        });
        const fontFamily = (extractStyleProp(runStyle, 'font-family') || 'Helvetica')
            .replace(/['"]/g, '');
        // <font style="font-size: 12px;"> wraps the size in some templates;
        // prefer it if present, else use the run-style size.
        const fontEl = $fo.find('font').last();
        const fontElSize = fontEl.length ? extractPx(fontEl.attr('style') || '', 'font-size') : null;
        const runSize = extractPx(runStyle, 'font-size');
        const fontSize = fontElSize || (runSize && runSize > 1 ? runSize : 12);
        const fontWeight = (extractStyleProp(runStyle, 'font-weight') || 'normal').replace(/\s/g, '');
        const color = extractStyleProp(runStyle, 'color') || '#000000';

        // Drawio uses `width: 1px` as the unconstrained-width marker; some
        // foreignObjects omit `width:Npx` entirely (extractPx → null → 0).
        // In both cases applying center/end math with width≈0 collapses the
        // anchor onto xLeft and reintroduces the pre-fix bug (text-anchor=
        // middle centred at the container's left edge → label drifts left
        // by half a viewport). Fall back to a left-anchored render so the
        // label stays near its declared position; visually correct for
        // every drawio template I've inspected with width:1px (column
        // headers, swimlane titles, free-floating annotations).
        let textAnchor = 'start';
        let textX = xLeft;
        if (containerWidth > 1) {
            if (/center/.test(justify)) {
                textAnchor = 'middle';
                textX = xLeft + containerWidth / 2;
            } else if (/flex-end|end/.test(justify)) {
                textAnchor = 'end';
                textX = xLeft + containerWidth;
            }
        }
        let baseline = 'central';
        if (/flex-start|start/.test(align)) baseline = 'hanging';
        else if (/flex-end|end/.test(align)) baseline = 'alphabetic';

        const rawLines = extractLines($fo[0]);
        if (rawLines.length === 0) {
            $fo.remove();
            return;
        }
        // Apply soft-wrap to each explicit line. drawio sometimes emits a
        // long single-span label without internal <br>; without wrapping
        // the rendered SVG <text> overflows the box. Skipped when
        // containerWidth is the unconstrained marker (≤1).
        const lines = [];
        for (const ln of rawLines) {
            for (const w of wrapText(ln, containerWidth, fontSize)) lines.push(w);
        }

        // Multi-line block: emit each line as a <tspan> with vertical
        // step. Shift the anchor up by half the block height when the
        // block is centered (drawio's `align-items: center`) so the
        // visual centerline still hits the original Y.
        const lineHeight = fontSize * 1.2;
        let anchorY = y;
        if (lines.length > 1 && baseline === 'central') {
            anchorY = y - (lines.length - 1) * lineHeight / 2;
        } else if (lines.length > 1 && baseline === 'alphabetic') {
            anchorY = y - (lines.length - 1) * lineHeight;
        }

        let inner;
        if (lines.length === 1) {
            inner = escapeXml(lines[0]);
        } else {
            inner = lines.map((line, idx) => {
                const dy = idx === 0 ? 0 : lineHeight;
                return `<tspan x="${textX}" dy="${dy}">${escapeXml(line)}</tspan>`;
            }).join('');
        }

        const replacement =
            `<text x="${textX}" y="${anchorY}" font-family="${escapeXml(fontFamily)}" font-size="${fontSize}" ` +
            `font-weight="${escapeXml(fontWeight)}" fill="${escapeXml(color)}" ` +
            `text-anchor="${textAnchor}" dominant-baseline="${baseline}">${inner}</text>`;
        $fo.replaceWith(replacement);
    });
    return $$.xml();
}

// Balance-aware resolver for CSS color functions resvg can't handle.
// Replaces every occurrence of `light-dark(LIGHT, DARK)` with its first
// (light-mode) argument and every `var(--name [, fallback])` with the
// fallback (or `currentColor` if none). The scanner walks the string
// once, opening a window when it spots a known function name, then
// counting nested parens until balanced — that lets it cope with
// `light-dark(rgb(0,0,0), rgb(255,255,255))` which the previous regex
// implementation tripped on, leaving the original `light-dark(...)`
// expression in place and making resvg fall back to black fills.
function _resolveCssFunctions(input) {
    const FNS = ['light-dark', 'var'];
    let out = '';
    let i = 0;
    let safety = 0;
    while (i < input.length) {
        if (++safety > 1e7) break; // belt-and-braces against runaway loops
        let matched = null;
        for (const fn of FNS) {
            if (input.startsWith(fn, i) && input[i + fn.length] === '(' ||
                (input.startsWith(fn, i) && /\s/.test(input[i + fn.length]) && input.indexOf('(', i + fn.length) === i + fn.length + (input.slice(i + fn.length).match(/^\s*/)[0].length))) {
                matched = fn;
                break;
            }
        }
        if (!matched) {
            out += input[i++];
            continue;
        }
        // Find the opening paren and the balanced closing paren.
        const parenStart = input.indexOf('(', i);
        let j = parenStart + 1;
        let depth = 1;
        while (j < input.length && depth > 0) {
            const ch = input[j];
            if (ch === '(') depth++;
            else if (ch === ')') depth--;
            if (depth === 0) break;
            j++;
        }
        if (depth !== 0) {
            // Unbalanced — give up on this match, copy verbatim.
            out += input[i++];
            continue;
        }
        const inner = input.slice(parenStart + 1, j);
        // Split on commas at depth 0.
        const parts = [];
        let buf = '';
        let d = 0;
        for (const ch of inner) {
            if (ch === '(') { d++; buf += ch; }
            else if (ch === ')') { d--; buf += ch; }
            else if (ch === ',' && d === 0) { parts.push(buf.trim()); buf = ''; }
            else buf += ch;
        }
        if (buf.length || parts.length) parts.push(buf.trim());

        let replacement;
        if (matched === 'light-dark') {
            // light-dark(LIGHT, DARK) → LIGHT
            replacement = parts[0] !== undefined && parts[0].length ? parts[0] : 'currentColor';
        } else { // var
            // var(--name, fallback?) → fallback / currentColor
            replacement = parts[1] !== undefined && parts[1].length ? parts[1] : 'currentColor';
        }
        // Recursively resolve in case the chosen branch itself contains
        // another light-dark() / var() (drawio nests them: the dark
        // branch of a light-dark call is often a `var(--ds-surface, …)`).
        replacement = _resolveCssFunctions(replacement);
        out += replacement;
        i = j + 1;
    }
    return out;
}

// Map of common HTML named entities resvg's strict XML parser doesn't
// know. Used by _prepareSvgForResvg() — drawio SVGs frequently include
// &nbsp; etc. inside text labels.
const _NAMED_ENTITIES_FOR_RESVG = {
    nbsp: 0xA0, ndash: 0x2013, mdash: 0x2014, hellip: 0x2026,
    lsquo: 0x2018, rsquo: 0x2019, ldquo: 0x201C, rdquo: 0x201D,
    laquo: 0xAB, raquo: 0xBB, copy: 0xA9, reg: 0xAE, trade: 0x2122,
    middot: 0xB7, bull: 0x2022, deg: 0xB0, plusmn: 0xB1, times: 0xD7,
    divide: 0xF7, larr: 0x2190, uarr: 0x2191, rarr: 0x2192, darr: 0x2193,
    harr: 0x2194, infin: 0x221E, sect: 0xA7, para: 0xB6,
};

// Apply every walker-side fixup needed to make a drawio SVG palatable
// to resvg-rust: namespace declarations, HTML named entity decode,
// foreignObject → SVG <text> conversion, and CSS color-function
// resolution. Tier-1 (Chrome) skips this entirely — Chrome handles
// everything natively — so we keep it factored out and called lazily
// only on the resvg fallback path.
function _prepareSvgForResvg(rawSvgXml) {
    let svgXml = rawSvgXml;
    // Inject xmlns / xmlns:xlink if cheerio's serializer dropped them.
    svgXml = svgXml.replace(/<svg\b([^>]*)>/i, (_m, attrs) => {
        let augmented = attrs;
        if (!/\sxmlns\s*=/.test(attrs)) augmented += ' xmlns="http://www.w3.org/2000/svg"';
        if (!/\sxmlns:xlink\s*=/.test(attrs)) augmented += ' xmlns:xlink="http://www.w3.org/1999/xlink"';
        return `<svg${augmented}>`;
    });
    // Replace HTML named entities (&nbsp; etc.) with numeric refs so
    // resvg's XML parser doesn't choke. Standard XML entities pass
    // through unchanged; unknown names get dropped.
    svgXml = svgXml.replace(/&([a-zA-Z][a-zA-Z0-9]+);/g, (m, name) => {
        if (name === 'amp' || name === 'lt' || name === 'gt' ||
            name === 'quot' || name === 'apos') return m;
        const code = _NAMED_ENTITIES_FOR_RESVG[name];
        return code !== undefined ? `&#${code};` : '';
    });
    // foreignObject → <text> (loses CSS layout, drawio labels at least
    // appear). When Chrome is rendering, this whole step is skipped.
    svgXml = _drawioForeignObjectsToText(cheerio, svgXml);
    // light-dark() / var() → light-mode value / fallback.
    svgXml = _resolveCssFunctions(svgXml);
    return svgXml;
}

// Make a drawio / Confluence inline SVG render predictably regardless of
// renderer tier:
//
//   Case 1 — SVG already carries a viewBox: expand it by 5% in both axes.
//   Drawio's auto-generated diagrams sometimes place arrow heads / shape
//   borders 1-2px past the declared canvas right/bottom edge; without
//   breathing room the renderer clips them.
//
//   Case 2 — SVG has no viewBox: synthesise one from the natural pixel
//   dimensions returned by _svgDimensions. Without a viewBox, Chrome's
//   `width:100%; height:100%` wrapper and resvg's fitTo:width both keep
//   the SVG coordinate space at its 1:1 pixel size — content beyond the
//   wrapper viewport simply clips. Adding a viewBox makes the SVG scale
//   proportionally instead.
//
// Skip rules:
//   * Self-closing `<svg .../>` tags preserve their `/>` — the regex
//     captures the trailing slash separately so the rewritten tag stays
//     valid XML (an earlier version corrupted self-closing tags by
//     letting `[^>]*` greedily eat the slash, producing invalid markup
//     resvg refused to parse).
//   * Small SVGs are left untouched on BOTH axes — natural pixel size ≤
//     200 (typically an inline icon) AND viewBox ≤ 200 user units. Tools
//     like Material Symbols use 40×40 rendered with viewBox 1024×1024,
//     which would otherwise hit Case 1 expansion and gain a 2-3px white
//     margin. Checking both signals independently protects against either
//     class of icon.
//   * `trustDims=false` (caller passes 0/0): _svgDimensions hit its
//     {600,400} sentinel fallback. Case 2 is skipped — synthesising a
//     viewBox from fictional dimensions would crop SVGs whose true
//     coordinate space exceeds 600×400.
function _ensureViewBox(svgXml, naturalW, naturalH, trustDims) {
    const VB_EXPAND = 1.05;
    const SMALL = 200;
    const renderedSmall = trustDims && (naturalW <= SMALL || naturalH <= SMALL);
    return svgXml.replace(/<svg\b([^>]*?)(\/?)>/i, (whole, attrs, selfClose) => {
        // Case 1: existing viewBox.
        const vbMatch = attrs.match(/\sviewBox\s*=\s*(["'])([^"']+)\1/i);
        if (vbMatch) {
            const parts = vbMatch[2].trim().split(/[\s,]+/).map(parseFloat);
            if (parts.length !== 4 || !parts.every(Number.isFinite)) return whole;
            const [vx, vy, vw, vh] = parts;
            // Skip when EITHER signal indicates an icon: tiny rendered size
            // or tiny viewBox extent.
            if (renderedSmall || vw <= SMALL || vh <= SMALL) return whole;
            const expanded =
                `viewBox="${vx} ${vy} ${(vw * VB_EXPAND).toFixed(1)} ${(vh * VB_EXPAND).toFixed(1)}"`;
            const newAttrs = attrs.replace(vbMatch[0], ' ' + expanded);
            return `<svg${newAttrs}${selfClose}>`;
        }
        // Case 2: synthesise. Need trusted natural dims; never extrapolate
        // from the {600,400} fallback sentinel because the SVG's real
        // coordinate space could be any size.
        if (!trustDims || naturalW <= SMALL || naturalH <= SMALL) return whole;
        const vbW = (naturalW * VB_EXPAND).toFixed(1);
        const vbH = (naturalH * VB_EXPAND).toFixed(1);
        return `<svg${attrs} viewBox="0 0 ${vbW} ${vbH}"${selfClose}>`;
    });
}

function _svgDimensions($svg, parentEl) {
    // Try in order: explicit svg width/height attrs → viewBox → parent
    // div's inline style — drawio-macro uses fixed pixel sizes there.
    const widthAttr = _parsePixelLength($svg.attr('width'));
    const heightAttr = _parsePixelLength($svg.attr('height'));
    if (widthAttr && heightAttr) return { w: widthAttr, h: heightAttr, fallback: false };
    const vb = ($svg.attr('viewBox') || '').trim().split(/[\s,]+/).map(parseFloat);
    if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
        return { w: vb[2], h: vb[3], fallback: false };
    }
    if (parentEl) {
        const style = (parentEl.attribs && parentEl.attribs.style) || '';
        const wMatch = style.match(/(?:^|;)\s*width\s*:\s*([^;]+)/i);
        const hMatch = style.match(/(?:^|;)\s*height\s*:\s*([^;]+)/i);
        const w = wMatch ? _parsePixelLength(wMatch[1]) : null;
        const h = hMatch ? _parsePixelLength(hMatch[1]) : null;
        if (w && h) return { w, h, fallback: false };
    }
    // Sentinel fallback: callers (notably _ensureViewBox) MUST treat this
    // as "dimensions unknown" rather than "natural size is 600×400". An SVG
    // whose content actually spans 0–10000 user units would be silently
    // cropped if a viewBox of 600×400 was synthesised.
    return { w: 600, h: 400, fallback: true };
}

function detectImageType(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    if (ext === '.png') return 'png';
    if (ext === '.jpg' || ext === '.jpeg') return 'jpg';
    if (ext === '.gif') return 'gif';
    if (ext === '.bmp') return 'bmp';
    if (ext === '.svg') return 'svg';
    if (ext === '.webp') return 'webp';
    // Confluence-style assets (atl.site.logo, global.logo) ship without
    // an extension; sniff the magic bytes as a fallback.
    try {
        const fd = fs.openSync(filePath, 'r');
        const buf = Buffer.alloc(16);
        fs.readSync(fd, buf, 0, 16, 0);
        fs.closeSync(fd);
        if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4E && buf[3] === 0x47) return 'png';
        if (buf[0] === 0xFF && buf[1] === 0xD8 && buf[2] === 0xFF) return 'jpg';
        if (buf.slice(0, 4).toString('ascii') === 'GIF8') return 'gif';
        if (buf[0] === 0x42 && buf[1] === 0x4D) return 'bmp';
        // WebP: RIFF????WEBP (4-byte size between RIFF and WEBP markers)
        if (buf.slice(0, 4).toString('ascii') === 'RIFF' &&
            buf.slice(8, 12).toString('ascii') === 'WEBP') return 'webp';
        const head = buf.toString('ascii');
        if (head.startsWith('<?xml') || head.startsWith('<svg')) return 'svg';
    } catch (_) { /* fall through */ }
    return null;
}

// docx-js v8.5 hardcodes `.png` as the image extension and the
// [Content_Types].xml lists only png/jpeg/jpg/bmp/gif — no webp. Embedding
// raw WebP bytes into a `.png` stream gives Word a broken image icon. We
// transcode WebP → PNG on disk via whatever system tool is available,
// then load the PNG bytes.
//
// Detection order: macOS `sips` (always present), `dwebp` (libwebp on
// Linux when libwebp-tools is installed), `convert` / `magick` (ImageMagick
// fallback). If none are available, the caller logs a warning and skips
// the image — better than silently embedding a corrupt PNG.
let _webpToolPath = undefined;  // undefined = not probed; null = none; string = path
function _findWebpConverter() {
    if (_webpToolPath !== undefined) return _webpToolPath;
    const candidates = [
        // [tool, args-template factory(input, output) → string[]]
        ['/usr/bin/sips',           (i, o) => ['-s', 'format', 'png', i, '--out', o]],
        ['/usr/local/bin/dwebp',    (i, o) => [i, '-o', o]],
        ['/opt/homebrew/bin/dwebp', (i, o) => [i, '-o', o]],
        ['/usr/bin/dwebp',          (i, o) => [i, '-o', o]],
        ['/usr/local/bin/magick',   (i, o) => ['convert', i, o]],
        ['/usr/bin/convert',        (i, o) => [i, o]],
    ];
    for (const [bin, argsFn] of candidates) {
        try {
            if (fs.statSync(bin).isFile()) {
                _webpToolPath = { bin, argsFn };
                return _webpToolPath;
            }
        } catch (_) { /* not present */ }
    }
    _webpToolPath = null;
    return null;
}

function _transcodeWebpToPng(srcPath) {
    const tool = _findWebpConverter();
    if (!tool) {
        throw new Error('WebP conversion unavailable: install libwebp (dwebp), ImageMagick, or run on macOS (sips)');
    }
    const dst = srcPath + '.transcoded.png';
    if (fs.existsSync(dst)) return dst;  // cache from earlier call this run
    const { spawnSync } = require('child_process');
    const r = spawnSync(tool.bin, tool.argsFn(srcPath, dst), { timeout: 30000 });
    if (r.status !== 0 || !fs.existsSync(dst)) {
        throw new Error(`WebP→PNG conversion failed (${tool.bin}): ${(r.stderr || '').toString().slice(0, 200)}`);
    }
    return dst;
}

// Insert zero-width spaces inside long unbreakable runs so Word/LibreOffice
// can wrap them at common syntactic boundaries. Word does not break a
// "word" without whitespace, so a 60-char CamelCase identifier or query
// string overflows the page margin. We trigger on any 26+ char run with
// no whitespace, then break it after `.`/`/`/`_`/`-`/`?`/`=`/`&`/`#`/`:`/`;`,
// before each capital letter following a lowercase one (CamelCase), and —
// as a last resort — every 30 characters.
function insertSoftWraps(text) {
    if (!text) return text;
    return text.replace(/\S{26,}/g, run => {
        let out = run.replace(/([./\\_?=&#:;,@%])/g, '$1​');
        out = out.replace(/([a-z])([A-Z])/g, '$1​$2');
        out = out.replace(/([^​\s]{30})/g, '$1​');
        return out;
    });
}

function makeRun(text, style) {
    const opts = {
        text: insertSoftWraps(text),
        font: style.code ? "Courier New" : "Arial",
        size: style.code ? 22 : 24,
    };
    if (style.bold) opts.bold = true;
    if (style.italics) opts.italics = true;
    if (style.underline) opts.underline = {};
    if (style.strike) opts.strike = true;
    if (style.color) opts.color = style.color;
    return new TextRun(opts);
}

function collapseWs(s) {
    return s.replace(/\s+/g, ' ');
}

function buildBody({ $, root, inputDir, extractedImages }) {
    const children = [];
    const numberedListConfigs = [];
    let numberedListCounter = 0;
    // Rebound when entering a table cell so emit-helpers push into the
    // cell's paragraph list instead of the document body.
    let target = children;

    // Anchor management for internal links. Word bookmark names must
    // start with a letter, contain only [A-Za-z0-9_], and be ≤40 chars
    // long. Confluence IDs are URI-encoded and frequently exceed 40
    // chars (e.g. "id-Интеграция…-Описание интеграционного…"), so we
    // normalize via a stable hash and remember the rawId→sanitized map
    // so later <a href="#rawId"> lookups can find the same anchor name.
    const anchorIds = new Map();
    function sanitizeAnchor(rawId) {
        if (!rawId) return null;
        if (anchorIds.has(rawId)) return anchorIds.get(rawId);
        let crypto;
        try { crypto = require('crypto'); } catch (_) { crypto = null; }
        let sanitized;
        if (crypto) {
            // 8-char hex prefix keeps anchor names < 40 chars and uniquely
            // tied to the original id (collisions are negligibly likely
            // for the document sizes we handle).
            const hash = crypto.createHash('sha1').update(rawId).digest('hex').slice(0, 8);
            sanitized = `a_${hash}`;
        } else {
            // Fallback if crypto is unavailable: monotonic counter.
            sanitized = `a_${anchorIds.size + 1}`;
        }
        anchorIds.set(rawId, sanitized);
        return sanitized;
    }

    function resolveLocalImagePath(rawHref) {
        if (!rawHref) return null;
        if (extractedImages.has(rawHref)) return extractedImages.get(rawHref);
        // Try the URL-encoded form too: HTML attributes carry raw spaces
        // (`/path with space.webp`) but `_html2docx_archive` stores keys
        // under `URL.pathname` which percent-encodes them
        // (`/path%20with%20space.webp`). Without this both forms must be
        // probed or 1/3 of real-world archive images go unmapped.
        let encoded;
        try { encoded = encodeURI(rawHref); } catch (_) { encoded = rawHref; }
        if (encoded !== rawHref && extractedImages.has(encoded)) {
            return extractedImages.get(encoded);
        }
        let href;
        try { href = decodeURI(rawHref); } catch (_) { href = rawHref; }
        if (extractedImages.has(href)) return extractedImages.get(href);
        if (!href) return null;
        if (isRemoteOrDataUrl(href)) return null;
        // Strip query/fragment before treating the URL as a filesystem
        // path. Files don't have `?v=1` in their basename — without this
        // we end up with a non-existent path AND a misleading
        // "Unsupported format" error from detectImageType.
        const pathOnly = href.split('?')[0].split('#')[0];
        if (path.isAbsolute(pathOnly)) return pathOnly;
        return path.resolve(inputDir, pathOnly);
    }

    function buildImageRun(localPath, altText) {
        // Order matters: existence first → if missing, the user gets the
        // accurate "Local image not found" instead of "Unsupported format"
        // from a magic-byte sniff that couldn't open the file.
        if (!fs.existsSync(localPath)) throw new Error(`Local image not found: ${localPath}`);
        let imageType = detectImageType(localPath);
        if (!imageType) throw new Error(`Unsupported image format: ${localPath}`);
        // docx-js v8.5 hardcodes `.png` extension regardless of the `type`
        // we pass and the package's [Content_Types].xml only lists png /
        // jpeg / bmp / gif. WebP bytes embedded as `.png` give Word a
        // broken-image icon. Transcode to PNG via system tool (sips on
        // macOS, dwebp/convert on Linux) before reading the bytes.
        if (imageType === 'webp') {
            localPath = _transcodeWebpToPng(localPath);
            imageType = 'png';
        }
        const imgData = fs.readFileSync(localPath);
        const dims = sizeOf(imgData);
        const maxWidth = 620;
        const maxHeight = 800;
        let w = dims.width || maxWidth;
        let h = dims.height || 400;
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
                name: path.basename(localPath),
            }
        });
    }

    function walkInline(node, style, runs, opts) {
        opts = opts || { preserveWs: false };
        if (node.type === 'text') {
            const raw = node.data || '';
            if (!raw) return;
            const text = opts.preserveWs ? raw : collapseWs(raw);
            if (text === '' || (text === ' ' && runs.length === 0)) return;
            runs.push(makeRun(text, style));
            return;
        }
        if (node.type !== 'tag') return;
        const name = (node.name || '').toLowerCase();

        if (name === 'br') {
            runs.push(new TextRun({ text: '', break: 1 }));
            return;
        }
        if (name === 'svg') {
            // Inline SVG (drawio / mermaid / etc.) — embed as ImageRun
            // and stop descending into <g>/<text>/<path> children, which
            // would otherwise dump every label as standalone text.
            // Pass the parent element so _svgDimensions can read the
            // wrapping `<div class="drawio-macro" style="width: 955px; …">`
            // when the SVG itself uses `width="100%"` (drawio's default).
            try {
                runs.push(buildSvgRun(node, node.parent || null));
            } catch (err) {
                console.warn(`html2docx: SVG embed failed (${err.message}) — skipping`);
            }
            return;
        }
        if (name === 'img') {
            const src = $(node).attr('src') || '';
            const alt = $(node).attr('alt') || '';
            const localPath = resolveLocalImagePath(src);
            if (localPath === null) {
                if (alt) runs.push(makeRun(alt, style));
                return;
            }
            try {
                runs.push(buildImageRun(localPath, alt));
            } catch (err) {
                console.warn(`html2docx: ${err.message} (skipping image)`);
                if (alt) runs.push(makeRun(alt, style));
            }
            return;
        }
        if (name === 'a') {
            const href = $(node).attr('href') || '';
            const isExternal = href && /^(https?:|mailto:|tel:)/i.test(href);
            // Internal anchor: any href whose hash points back into the
            // document. Confluence TOC emits absolute URLs whose
            // fragment IS the heading anchor; turn those into in-doc
            // jumps so we don't open a browser to the live wiki.
            const hashIdx = href.indexOf('#');
            const isInternal = !isExternal && hashIdx !== -1 && href.length > hashIdx + 1;
            const innerRuns = [];
            const linkStyle = Object.assign({}, style, { underline: true },
                (isExternal || isInternal) ? { color: "0563C1" } : {});
            for (const c of node.children || []) walkInline(c, linkStyle, innerRuns, opts);
            if (innerRuns.length === 0) return;
            // docx-js v8.5 emits `<a:hlinkClick r:id="rId…"/>` inside the
            // image's `<wp:docPr>` whenever an `ImageRun` is rendered with
            // an `ExternalHyperlink` OR `InternalHyperlink` ancestor in
            // the prepForXml context stack. For ImageRun:
            //   * Inside ExternalHyperlink: the linkId IS registered as a
            //     hyperlink relationship → works correctly.
            //   * Inside InternalHyperlink: the linkId is for a bookmark
            //     anchor (no rels entry). docx-js still emits the rId on
            //     the image's docPr but the rels file has no matching
            //     Relationship → Word reports "unreadable content"
            //     ("содержимое, которое не удалось прочитать") and offers
            //     recovery. Real-world trigger: vc.ru's
            //     `<a href="/post#comments">` comment-counter link
            //     wrapping `<svg>icon</svg>60`.
            //
            // Workaround: split innerRuns into images vs. non-images. The
            // hyperlink wraps ONLY non-image runs (text); images are
            // emitted as siblings of the hyperlink, losing their (rarely-
            // useful-in-docx) click target but never producing a dangling
            // rId. ExternalHyperlink wrapping images would technically
            // work, but applying the same rule to both types keeps the
            // behaviour predictable and side-steps any other docx-js
            // surprises with image-in-hyperlink.
            const imageRuns = innerRuns.filter(r => r instanceof ImageRun);
            const nonImageRuns = innerRuns.filter(r => !(r instanceof ImageRun));
            if ((isExternal || isInternal) && nonImageRuns.length > 0) {
                if (isExternal) {
                    runs.push(new ExternalHyperlink({ link: href, children: nonImageRuns }));
                } else {
                    const fragment = decodeURIComponent(href.slice(hashIdx + 1));
                    runs.push(new InternalHyperlink({
                        anchor: sanitizeAnchor(fragment),
                        children: nonImageRuns,
                    }));
                }
                for (const r of imageRuns) runs.push(r);
            } else if (isExternal || isInternal) {
                // image-only or empty after filtering — push images directly
                for (const r of imageRuns) runs.push(r);
            } else {
                for (const r of innerRuns) runs.push(r);
            }
            return;
        }
        if (INLINE_STYLE_TAGS[name]) {
            const childStyle = Object.assign({}, style, INLINE_STYLE_TAGS[name]);
            for (const c of node.children || []) walkInline(c, childStyle, runs, opts);
            return;
        }
        for (const c of node.children || []) walkInline(c, style, runs, opts);
    }

    function inlineRunsFor(el, opts) {
        const runs = [];
        for (const c of el.children || []) walkInline(c, {}, runs, opts);
        return runs;
    }

    function emitParagraphFromInline(el, paragraphOpts) {
        const runs = inlineRunsFor(el);
        if (runs.length === 0) return;
        target.push(new Paragraph(Object.assign({ children: runs }, paragraphOpts || {})));
    }

    function emitHeading(el, depth) {
        // Heading runs intentionally carry NO font/size of their own. The
        // walker's default makeRun() applies Arial 24 to every TextRun,
        // which overrides the Heading1/2/3 paragraph style (32/28/24 +
        // bold) defined at Document level — leaving headings looking
        // identical to body text. Build flat runs from the heading's text
        // so the paragraph style wins.
        const text = $(el).text().replace(/\s+/g, ' ').trim();
        if (!text) return;
        let hLevel;
        if (depth === 1) hLevel = HeadingLevel.HEADING_1;
        else if (depth === 2) hLevel = HeadingLevel.HEADING_2;
        else if (depth === 3) hLevel = HeadingLevel.HEADING_3;
        else if (depth === 4) hLevel = HeadingLevel.HEADING_4;
        else if (depth === 5) hLevel = HeadingLevel.HEADING_5;
        else hLevel = HeadingLevel.HEADING_6;
        // If the heading carries an HTML id (Confluence puts a unique
        // id on every <h1-h6>), wrap its run in a Bookmark so internal
        // <a href="#id"> hyperlinks elsewhere in the document can
        // resolve to it. Without this, TOC links land nowhere.
        const rawId = $(el).attr('id');
        const baseRun = new TextRun({ text });
        let headingChildren;
        if (rawId) {
            const anchor = sanitizeAnchor(rawId);
            headingChildren = [new Bookmark({ id: anchor, children: [baseRun] })];
        } else {
            headingChildren = [baseRun];
        }
        target.push(new Paragraph({ heading: hLevel, children: headingChildren }));
    }

    function emitBlockquote(el) {
        const blockBorder = {
            left: { style: BorderStyle.SINGLE, size: 3, color: "AAAAAA", space: 8 }
        };
        let collectedInline = [];
        const flush = () => {
            if (collectedInline.length === 0) return;
            target.push(new Paragraph({
                children: collectedInline,
                indent: { left: 720 },
                spacing: { before: 120, after: 120 },
                border: blockBorder,
            }));
            collectedInline = [];
        };
        for (const c of (el.children || [])) {
            if (c.type === 'tag' && /^(p|div)$/i.test(c.name)) {
                flush();
                const runs = inlineRunsFor(c);
                if (runs.length) {
                    target.push(new Paragraph({
                        children: runs,
                        indent: { left: 720 },
                        spacing: { before: 120, after: 120 },
                        border: blockBorder,
                    }));
                }
            } else {
                walkInline(c, {}, collectedInline);
            }
        }
        flush();
    }

    function emitPre(el) {
        const text = $(el).text();
        const lines = text.replace(/\n+$/, '').split('\n');
        for (const line of lines) {
            // Soft-wrap long unbreakable identifiers / URLs so the page
            // margin doesn't get blown out (the offending case was
            // VolpFreeMethodsHttpCallHandler-style class names).
            const wrapped = insertSoftWraps(line) || ' ';
            target.push(new Paragraph({
                children: [new TextRun({ text: wrapped, font: "Courier New", size: 20 })],
                spacing: { before: 0, after: 0 },
                shading: { type: ShadingType.CLEAR, fill: "F5F5F5" },
                indent: { left: 360 }
            }));
        }
    }

    function emitHr() {
        target.push(new Paragraph({
            children: [],
            spacing: { before: 200, after: 200 },
            border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC", space: 4 } }
        }));
    }

    function buildSvgRun(svgNode, parentEl) {
        // Two-tier rasterizer (see _html2docx_svg_render.js):
        //   1. Headless Chrome / Chromium / Edge if found on host →
        //      true CSS layout, foreignObject + word-wrap render exactly
        //      like Confluence shows them. Renders at an inflated
        //      viewport and trims trailing white so a drawio macro's
        //      `overflow: hidden` clipping doesn't drop content.
        //   2. resvg-js with all the SVG sanitization the walker has
        //      accumulated for drawio quirks (xlink namespace inject,
        //      named-entity decode, foreignObject → <text> conversion,
        //      CSS color-function resolution).
        // Embed sizing uses the ACTUAL post-render PNG dimensions so
        // trimming-induced shrinkage is honoured; aspect ratio always
        // matches what the renderer produced.
        const $svg = $(svgNode);
        const dims = _svgDimensions($svg, parentEl);
        // Ensure a viewBox before either tier renders the SVG. Both Chrome
        // (`width:100%; height:100%`) and resvg (`fitTo:width`) need a
        // viewBox to scale content proportionally; without one, drawio
        // diagrams whose content reaches the canvas edge get clipped.
        // `trustDims=!fallback` so _ensureViewBox won't synthesise a
        // viewBox from the {600,400} sentinel (which has nothing to do
        // with the SVG's actual coordinate space).
        const rawSvgXml = _ensureViewBox($.html(svgNode), dims.w, dims.h, !dims.fallback);
        const png = svgRender.render({
            chromeReadySvg: () => rawSvgXml,
            resvgReadySvg: () => _prepareSvgForResvg(rawSvgXml),
            width: dims.w,
            height: dims.h,
        });
        // Inspect the produced PNG so we know how big the trimmed image
        // really is; assume 2× device-scale-factor (chrome path) /
        // 2× fitTo (resvg path), so logical px = pixel / 2.
        let pxW = dims.w * 2, pxH = dims.h * 2;
        try {
            const meta = sizeOf(png);
            if (meta.width && meta.height) { pxW = meta.width; pxH = meta.height; }
        } catch (_) { /* fall back to expected */ }
        const logicalW = pxW / 2;
        const logicalH = pxH / 2;
        const maxW = 620, maxH = 800;
        const scale = Math.min(1, maxW / logicalW, maxH / logicalH);
        const w = Math.max(1, Math.round(logicalW * scale));
        const h = Math.max(1, Math.round(logicalH * scale));

        return new ImageRun({
            type: 'png',
            data: png,
            transformation: { width: w, height: h },
            altText: { title: 'Diagram', description: 'Rendered SVG diagram', name: 'diagram' },
        });
    }

    function emitSvg(node, parentEl) {
        try {
            target.push(new Paragraph({
                spacing: { before: 120, after: 120 },
                children: [buildSvgRun(node, parentEl)],
            }));
        } catch (err) {
            console.warn(`html2docx: SVG embed failed (${err.message}) — skipping`);
        }
    }

    function cellParagraphs(cellEl) {
        const out = [];
        const blockChildren = (cellEl.children || []).filter(c =>
            c.type === 'tag' && /^(p|div|ul|ol|blockquote|pre|table|h[1-6])$/i.test(c.name)
        );
        if (blockChildren.length === 0) {
            const runs = inlineRunsFor(cellEl);
            out.push(new Paragraph({ children: runs.length ? runs : [] }));
            return out;
        }
        const savedTarget = target;
        target = out;
        try {
            for (const c of cellEl.children || []) walkBlock(c);
        } finally {
            target = savedTarget;
        }
        if (out.length === 0) out.push(new Paragraph({}));
        return out;
    }

    function emitTable(el) {
        const $el = $(el);
        const trs = $el.find('tr').toArray();
        if (trs.length === 0) return;

        const headerSet = new Set();
        $el.find('thead tr').each((_, tr) => headerSet.add(tr));
        for (const tr of trs) {
            const cells = $(tr).children('th,td').toArray();
            if (cells.length && cells.every(c => c.name === 'th')) headerSet.add(tr);
        }

        const numCols = trs.reduce((n, tr) => Math.max(n, $(tr).children('th,td').length), 0);
        if (numCols === 0) return;
        const colWidth = Math.floor(contentWidthDxa / numCols);
        const colWidthsArray = Array(numCols).fill(colWidth);

        const tableRows = trs.map(tr => {
            const isHeader = headerSet.has(tr);
            const cells = $(tr).children('th,td').toArray();
            const padded = cells.slice();
            while (padded.length < numCols) padded.push(null);
            return new TableRow({
                children: padded.map(cell => {
                    const cellChildren = cell ? cellParagraphs(cell) : [new Paragraph({})];
                    const shading = isHeader
                        ? { fill: "D5E8F0", type: ShadingType.CLEAR }
                        : { type: ShadingType.CLEAR };
                    return new TableCell({
                        borders,
                        width: { size: colWidth, type: WidthType.DXA },
                        shading,
                        margins: { top: 80, bottom: 80, left: 120, right: 120 },
                        children: cellChildren,
                    });
                })
            });
        });

        target.push(new Table({
            width: { size: contentWidthDxa, type: WidthType.DXA },
            columnWidths: colWidthsArray,
            rows: tableRows,
        }));
        target.push(new Paragraph({ spacing: { after: 240 } }));
    }

    function emitList(el, level, parentRef, parentOrdered) {
        const ordered = (el.name || '').toLowerCase() === 'ol';
        let listRef;
        if (ordered) {
            // Inherit parent's reference only when the parent was ALSO an
            // ordered list (so multi-level <ol><li><ol> shares a numbering
            // tree). For <ol> nested under <ul> the parent ref is "bullets" —
            // sharing it would render the nested ol as bullets too. Allocate
            // a fresh numbers_N config in that case (and at top level).
            if (level > 0 && parentOrdered) {
                listRef = parentRef;
            } else {
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
            }
        } else {
            listRef = "bullets";
        }

        const items = (el.children || []).filter(c =>
            c.type === 'tag' && (c.name || '').toLowerCase() === 'li'
        );
        for (const li of items) {
            const inlinePieces = [];
            const nestedLists = [];
            for (const c of li.children || []) {
                if (c.type === 'tag' && /^(ul|ol)$/i.test(c.name)) nestedLists.push(c);
                else inlinePieces.push(c);
            }
            const runs = [];
            for (const piece of inlinePieces) walkInline(piece, {}, runs);
            // For ordered lists nested under unordered ones we just allocated
            // a fresh ref above — render the nested ol from level 0 of its
            // own ref, not parent's level. parentOrdered carries the
            // information we need.
            const renderLevel = ordered && !parentOrdered && level > 0 ? 0 : Math.min(level, 2);
            if (runs.length) {
                target.push(new Paragraph({
                    numbering: { reference: listRef, level: renderLevel },
                    children: runs,
                    spacing: { before: 60, after: 60 }
                }));
            }
            for (const nested of nestedLists) {
                emitList(nested, level + 1, listRef, ordered);
            }
        }
    }

    function walkBlock(node) {
        if (node.type === 'text') {
            const text = collapseWs(node.data || '').trim();
            if (text) {
                target.push(new Paragraph({
                    children: [makeRun(text, {})],
                    spacing: { before: 120, after: 120 }
                }));
            }
            return;
        }
        if (node.type !== 'tag') return;
        const name = (node.name || '').toLowerCase();
        switch (name) {
            case 'h1': return emitHeading(node, 1);
            case 'h2': return emitHeading(node, 2);
            case 'h3': return emitHeading(node, 3);
            case 'h4': return emitHeading(node, 4);
            case 'h5': return emitHeading(node, 5);
            case 'h6': return emitHeading(node, 6);
            case 'p':
                return emitParagraphFromInline(node, { spacing: { before: 120, after: 120 } });
            case 'ul':
            case 'ol':
                return emitList(node, 0, null, false);
            case 'table':
                return emitTable(node);
            case 'blockquote':
                return emitBlockquote(node);
            case 'pre':
                return emitPre(node);
            case 'hr':
                return emitHr();
            case 'svg':
                return emitSvg(node, node.parent || null);
            case 'div':
            case 'section':
            case 'article':
            case 'main':
            case 'header':
            case 'footer':
            case 'aside':
            case 'nav':
            case 'body':
            case 'html':
                for (const c of node.children || []) walkBlock(c);
                return;
            default: {
                // The default branch handles two distinct cases:
                //  (a) A bare inline element (`<img>`, `<span>`, `<a>`,
                //      `<br>`) that lives directly under <body>. In this
                //      case the *node itself* is the run-source — calling
                //      `inlineRunsFor` would walk its children (often
                //      empty) and silently drop the image.
                //  (b) An unknown block-level tag — treat its content
                //      transparently.
                // We can cover both with a single walkInline on the node.
                const runs = [];
                walkInline(node, {}, runs);
                if (runs.length) {
                    target.push(new Paragraph({
                        children: runs,
                        spacing: { before: 120, after: 120 }
                    }));
                }
                return;
            }
        }
    }

    for (const c of (root.children || [])) walkBlock(c);
    return { children, numberedListConfigs };
}

module.exports = {
    buildBody,
    // Test-only exports — exercised by tests/test_e2e.sh.
    _ensureViewBox,
    _svgDimensions,
    _drawioForeignObjectsToText,
};
