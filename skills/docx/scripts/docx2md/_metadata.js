// docx2md sidecar metadata + footnote/endnote extraction.
//
// Mammoth strips <w:comment>, <w:ins>, <w:del> on its way to HTML, and turns
// <w:footnoteReference>/<w:endnoteReference> into <sup><a href="#fnN">…</a></sup>
// followed by an <ol class="footnotes"> list — after turndown that becomes
// `[1](#fn1) … 1. ↑ text`, which is noisy and not pandoc-compatible.
//
// This module:
//   1. Pulls comments + insertions/deletions out of the .docx as a JSON
//      sidecar (docx-4). Sidecar-only, never inline in the markdown — the
//      audit consumer wants a clean .md plus a structured locator file.
//   2. Replaces footnote/endnote references in document.xml with sentinel
//      tokens (⟦FN:N⟧ / ⟦EN:N⟧) BEFORE mammoth runs, and blanks out user
//      content in footnotes.xml/endnotes.xml so mammoth can't re-emit them.
//      After turndown, sentinels are swapped to pandoc `[^fn-N]` / `[^en-N]`
//      and definitions are appended at the end of the markdown (docx-5).
//
// The unicode brackets ⟦ (U+27E6) / ⟧ (U+27E7) are CJK punctuation rare
// enough to never collide with user content, and survive turndown verbatim
// (markdown does not interpret them). Verified by spike on Test_2.docx.
//
// Honest scope (v1):
//   - Comments: capture id/author/initials/date/text + paraId/parentParaId
//     (thread structure) + anchorText with 40-char before/after context
//     + paragraphIndex.
//   - Revisions: <w:ins> / <w:del> only. Formatting changes (rPrChange,
//     pPrChange) and content moves (moveFrom, moveTo) are COUNTED in the
//     `unsupported` field of the sidecar so callers see what was lost,
//     but not extracted (deferred to v2).
//   - Footnote/endnote text: plain-text concatenation of <w:t>. Formatting
//     inside footnotes (bold, links, nested lists) flattens. Word's
//     separator/continuationSeparator/continuationNotice entries are
//     filtered out as boilerplate.
//
// Not exported but used internally: cheerio xmlMode requires `:` in tag
// names to be CSS-escaped, so selectors look like `'w\\:p'`.

const cheerio = require("cheerio");

const SCHEMA_VERSION = 1;
const CONTEXT_CHARS = 40; // chars of before/after context for anchor locator
// VDD LOW-2: cap unbounded sibling walks when a comment range is malformed
// (commentRangeEnd missing). Bounded by paragraph length anyway, but a
// runaway capture would bloat the sidecar on pathological docs.
const ANCHOR_CAPTURE_CAP = 2000;

// Boilerplate footnote/endnote types Word always inserts; never user content.
const BOILERPLATE_NOTE_TYPES = new Set([
    "separator",
    "continuationSeparator",
    "continuationNotice",
]);

// --- Part loading ---------------------------------------------------------

// Read all parts we need from a JSZip instance into a plain object.
// Missing parts are reported as null (not all .docx have comments etc.).
async function loadDocxParts(zip) {
    async function readOpt(name) {
        const f = zip.file(name);
        return f ? await f.async("string") : null;
    }
    return {
        zip,
        documentXml:         await readOpt("word/document.xml"),
        commentsXml:         await readOpt("word/comments.xml"),
        commentsExtendedXml: await readOpt("word/commentsExtended.xml"),
        footnotesXml:        await readOpt("word/footnotes.xml"),
        endnotesXml:         await readOpt("word/endnotes.xml"),
    };
}

// --- Comments -------------------------------------------------------------

// Concat all <w:t>/<w:delText> descendants of `el` (cheerio object) as plain text.
function plainText($, el) {
    const $el = $(el);
    let txt = "";
    $el.find("w\\:t, w\\:delText").each((_, t) => {
        txt += $(t).text();
    });
    return txt;
}

// Find paragraph (cheerio element) ancestor of `el`. Returns null if `el` is
// not inside a <w:p>.
function paragraphAncestor($, el) {
    let cur = el.parent;
    while (cur) {
        if (cur.type === "tag" && cur.name === "w:p") return cur;
        cur = cur.parent;
    }
    return null;
}

// Walk forward through siblings of startNode (NOT descending) capturing
// concatenated text content until we hit a node matching stopName, or we
// run out of siblings. Returns the captured text. Used to grab the body
// of a comment range when both markers live in the same paragraph.
//
// VDD LOW-2: malformed docs may have <w:commentRangeStart> without a
// matching End, which would cause us to slurp the rest of the paragraph
// (or, in cross-paragraph ranges, beyond). Cap at ANCHOR_CAPTURE_CAP.
function captureBetweenSiblings($, startNode, stopName) {
    let txt = "";
    let cur = startNode.next;
    while (cur) {
        if (cur.type === "tag" && cur.name === stopName) break;
        if (cur.type === "tag") {
            txt += $(cur).text();
            if (txt.length > ANCHOR_CAPTURE_CAP) {
                return txt.slice(0, ANCHOR_CAPTURE_CAP) + "…[truncated]";
            }
        }
        cur = cur.next;
    }
    return txt;
}

// Build a paragraph-index map: every <w:p> in document order gets a 0-based
// index; the map is keyed by the underlying DOM node so we can look up an
// arbitrary descendant's owning paragraph in O(1).
function buildParagraphIndexMap($) {
    const map = new Map();
    $("w\\:p").each((idx, p) => {
        map.set(p, idx);
    });
    return map;
}

// Compact whitespace (newlines, multiple spaces) for cleaner anchor text.
function collapseWhitespace(s) {
    return s.replace(/\s+/g, " ").trim();
}

// VDD LOW-3: cheerio's attr() returns "" for `w:id=""`, which Number("")
// silently coerces to 0 — colliding with a real id-0 comment. Treat
// blank/missing the same.
function parseIntId(raw) {
    if (raw == null || raw === "") return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
}

// Extract context (before/after) of a node within its paragraph's plain text.
// We collect the paragraph's full text once, then split it at the anchor's
// position. Cheap on small paragraphs; for huge paragraphs, still O(N) per
// comment.
function extractContext($, anchorEl, anchorText, paragraphEl) {
    if (!paragraphEl) return { before: "", after: "" };
    const fullText = collapseWhitespace(plainText($, paragraphEl));
    const cleanAnchor = collapseWhitespace(anchorText);
    if (!cleanAnchor) return { before: "", after: "" };
    const idx = fullText.indexOf(cleanAnchor);
    if (idx < 0) return { before: "", after: "" };
    const before = fullText.slice(Math.max(0, idx - CONTEXT_CHARS), idx);
    const after = fullText.slice(idx + cleanAnchor.length, idx + cleanAnchor.length + CONTEXT_CHARS);
    return { before, after };
}

function extractComments(parts) {
    const out = [];
    if (!parts.commentsXml) return out;

    const $c = cheerio.load(parts.commentsXml, { xmlMode: true, decodeEntities: false });

    // Build paraId → parentParaId map from commentsExtended.xml.
    const threadMap = new Map();
    if (parts.commentsExtendedXml) {
        const $cx = cheerio.load(parts.commentsExtendedXml, { xmlMode: true, decodeEntities: false });
        $cx("w15\\:commentEx").each((_, el) => {
            const pid = $cx(el).attr("w15:paraId");
            const parent = $cx(el).attr("w15:paraIdParent") || null;
            if (pid) threadMap.set(pid, parent);
        });
    }

    // Anchor lookup over document.xml: id → {anchorText, paraIndex}.
    const anchorMap = new Map();
    if (parts.documentXml) {
        const $d = cheerio.load(parts.documentXml, { xmlMode: true, decodeEntities: false });
        const paraIdx = buildParagraphIndexMap($d);
        $d("w\\:commentRangeStart").each((_, startEl) => {
            const id = $d(startEl).attr("w:id");
            if (id == null) return;
            const anchorText = collapseWhitespace(captureBetweenSiblings($d, startEl, "w:commentRangeEnd"));
            const para = paragraphAncestor($d, startEl);
            const paraIndex = para ? paraIdx.get(para) : null;
            const ctx = extractContext($d, startEl, anchorText, para);
            anchorMap.set(id, {
                anchorText,
                anchorTextBefore: ctx.before,
                anchorTextAfter: ctx.after,
                paragraphIndex: typeof paraIndex === "number" ? paraIndex : null,
            });
        });
    }

    $c("w\\:comment").each((_, el) => {
        const $el = $c(el);
        const idRaw = $el.attr("w:id");
        const paraId = $el.find("w\\:p").first().attr("w14:paraId") || null;
        const text = collapseWhitespace(plainText($c, el));
        const anchorInfo = anchorMap.get(idRaw) || {};
        out.push({
            id: parseIntId(idRaw),
            paraId,
            parentParaId: paraId ? (threadMap.get(paraId) || null) : null,
            author: $el.attr("w:author") || null,
            initials: $el.attr("w:initials") || null,
            date: $el.attr("w:date") || null,
            text,
            anchorText: anchorInfo.anchorText || "",
            anchorTextBefore: anchorInfo.anchorTextBefore || "",
            anchorTextAfter: anchorInfo.anchorTextAfter || "",
            paragraphIndex: anchorInfo.paragraphIndex == null ? null : anchorInfo.paragraphIndex,
        });
    });

    // Sort by document order (paragraphIndex), nulls last; tie-break on id.
    out.sort((a, b) => {
        const ai = a.paragraphIndex == null ? Number.MAX_SAFE_INTEGER : a.paragraphIndex;
        const bi = b.paragraphIndex == null ? Number.MAX_SAFE_INTEGER : b.paragraphIndex;
        if (ai !== bi) return ai - bi;
        return (a.id || 0) - (b.id || 0);
    });
    return out;
}

// --- Revisions (track-changes) -------------------------------------------

// Element name → unsupported revision counter key.
const UNSUPPORTED_REVISION_TAGS = {
    "w:rPrChange":  "rPrChange",
    "w:pPrChange":  "pPrChange",
    "w:moveFrom":   "moveFrom",
    "w:moveTo":     "moveTo",
    "w:cellIns":    "cellIns",
    "w:cellDel":    "cellDel",
};

function extractRevisions(parts) {
    const out = [];
    const unsupported = {
        rPrChange: 0, pPrChange: 0, moveFrom: 0, moveTo: 0, cellIns: 0, cellDel: 0,
    };
    if (!parts.documentXml) return { revisions: out, unsupported };

    const $ = cheerio.load(parts.documentXml, { xmlMode: true, decodeEntities: false });
    const paraIdx = buildParagraphIndexMap($);

    // <w:ins> and <w:del>: capture id/author/date/text + paraIndex/runIndex.
    function collectRevs(selector, type, textSelector) {
        $(selector).each((_, el) => {
            const $el = $(el);
            // Skip nested ins/del (e.g. ins inside del — Word's "rejected
            // insertion" rendering); only top-level revision wrappers matter
            // for v1 sidecar count.
            if ($el.parents("w\\:ins, w\\:del").length > 0) return;
            const para = paragraphAncestor($, el);
            const paraIndex = para ? paraIdx.get(para) : null;
            // runIndex: position of THIS revision among siblings of the
            // owning paragraph that are runs / ins / del.
            let runIndex = -1;
            if (para) {
                let n = 0;
                for (const sib of para.children || []) {
                    if (sib.type !== "tag") continue;
                    if (sib === el) { runIndex = n; break; }
                    if (sib.name === "w:r" || sib.name === "w:ins" || sib.name === "w:del") n += 1;
                }
            }
            const text = $el.find(textSelector).text();
            out.push({
                type,
                id: parseIntId($el.attr("w:id")),
                author: $el.attr("w:author") || null,
                date: $el.attr("w:date") || null,
                text,
                paragraphIndex: typeof paraIndex === "number" ? paraIndex : null,
                runIndex: runIndex >= 0 ? runIndex : null,
            });
        });
    }
    collectRevs("w\\:ins", "insertion", "w\\:t");
    collectRevs("w\\:del", "deletion",  "w\\:delText");

    // Count unsupported revision tags (formatting changes, moves, table cell ins/del).
    for (const [tag, key] of Object.entries(UNSUPPORTED_REVISION_TAGS)) {
        const escaped = tag.replace(":", "\\:");
        unsupported[key] = $(escaped).length;
    }

    out.sort((a, b) => {
        const ai = a.paragraphIndex == null ? Number.MAX_SAFE_INTEGER : a.paragraphIndex;
        const bi = b.paragraphIndex == null ? Number.MAX_SAFE_INTEGER : b.paragraphIndex;
        if (ai !== bi) return ai - bi;
        const ar = a.runIndex == null ? Number.MAX_SAFE_INTEGER : a.runIndex;
        const br = b.runIndex == null ? Number.MAX_SAFE_INTEGER : b.runIndex;
        if (ar !== br) return ar - br;
        return (a.id || 0) - (b.id || 0);
    });
    return { revisions: out, unsupported };
}

// Top-level: build the v1 sidecar object. Returns null when there is nothing
// worth writing (no comments, no revisions, all unsupported counters zero).
function buildSidecar(parts, sourceBasename) {
    const comments = extractComments(parts);
    const { revisions, unsupported } = extractRevisions(parts);
    const allZero = Object.values(unsupported).every((n) => n === 0);
    if (comments.length === 0 && revisions.length === 0 && allZero) {
        return null;
    }
    return {
        v: SCHEMA_VERSION,
        source: sourceBasename,
        comments,
        revisions,
        unsupported,
    };
}

// --- Footnotes / endnotes ------------------------------------------------

// Extract user-content footnote/endnote definitions: id → plain text.
// Word's separator/continuationSeparator/continuationNotice are filtered.
//
// VDD MED-1: empty bodies are KEPT (mapped to ""). Skipping them caused
// dangling pandoc refs because injectFootnoteSentinels still replaced the
// reference in document.xml — leaving `[^fn-N]` in markdown with no
// `[^fn-N]:` definition. Emitting an empty definition keeps the reference
// resolvable.
function extractNotesFromXml(xml, _rootSelector, itemSelector) {
    if (!xml) return new Map();
    const $ = cheerio.load(xml, { xmlMode: true, decodeEntities: false });
    const notes = new Map();
    $(itemSelector).each((_, el) => {
        const $el = $(el);
        const type = $el.attr("w:type") || "";
        if (BOILERPLATE_NOTE_TYPES.has(type)) return;
        const id = $el.attr("w:id");
        if (id == null || id === "") return;
        const text = collapseWhitespace(plainText($, el));
        notes.set(id, text);
    });
    return notes;
}

function extractFootnotesAndEndnotes(parts) {
    const fn = extractNotesFromXml(parts.footnotesXml, "w\\:footnotes", "w\\:footnote");
    const en = extractNotesFromXml(parts.endnotesXml,   "w\\:endnotes",   "w\\:endnote");
    return {
        footnotes: [...fn.entries()].map(([id, text]) => ({ id: Number(id), text })),
        endnotes:  [...en.entries()].map(([id, text]) => ({ id: Number(id), text })),
    };
}

// --- Footnote/endnote sentinel injection (pre-mammoth) -------------------

// Replace <w:footnoteReference w:id="N"/> in document.xml with a literal
// text run carrying ⟦FN:N⟧, and same for endnoteReference → ⟦EN:N⟧.
// Also blanks user-content <w:footnote>/<w:endnote> bodies in their XML
// parts so mammoth doesn't render its own <ol class="footnotes">.
//
// `notes` is the {footnotes, endnotes} object from extractFootnotesAndEndnotes;
// only references whose `w:id` resolves to a known footnote/endnote definition
// are sentinel'd. Orphan refs (id with no <w:footnote> body) are left alone —
// otherwise we'd emit pandoc `[^fn-N]` markers without matching definitions
// (VDD MED-1 dangling reference).
//
// Mutates `parts.documentXml`, `parts.footnotesXml`, `parts.endnotesXml`
// in place. Idempotent on parts that have no references (no-op).
function injectFootnoteSentinels(parts, notes) {
    if (!parts.documentXml) return;
    const knownFn = new Set((notes.footnotes || []).map((f) => String(f.id)));
    const knownEn = new Set((notes.endnotes  || []).map((e) => String(e.id)));

    const $d = cheerio.load(parts.documentXml, { xmlMode: true, decodeEntities: false });
    let touched = false;

    $d("w\\:footnoteReference").each((_, el) => {
        const id = $d(el).attr("w:id");
        if (id == null || id === "" || !knownFn.has(id)) return;
        $d(el).replaceWith(`<w:r><w:t xml:space="preserve">⟦FN:${id}⟧</w:t></w:r>`);
        touched = true;
    });
    $d("w\\:endnoteReference").each((_, el) => {
        const id = $d(el).attr("w:id");
        if (id == null || id === "" || !knownEn.has(id)) return;
        $d(el).replaceWith(`<w:r><w:t xml:space="preserve">⟦EN:${id}⟧</w:t></w:r>`);
        touched = true;
    });

    if (touched) {
        parts.documentXml = $d.xml();
    }

    // Strip user content from footnotes.xml so mammoth has nothing to emit.
    parts.footnotesXml = stripUserNoteContent(parts.footnotesXml, "w\\:footnotes", "w\\:footnote");
    parts.endnotesXml  = stripUserNoteContent(parts.endnotesXml,  "w\\:endnotes",  "w\\:endnote");
}

// Returns a new XML string with user-content notes replaced by an empty
// <w:p/>. Boilerplate (separator/continuationSeparator/continuationNotice)
// is preserved as-is — Word requires those entries to be present even on
// docs that have zero user footnotes.
function stripUserNoteContent(xml, _rootSelector, itemSelector) {
    if (!xml) return xml;
    const $ = cheerio.load(xml, { xmlMode: true, decodeEntities: false });
    let stripped = false;
    $(itemSelector).each((_, el) => {
        const $el = $(el);
        const type = $el.attr("w:type") || "";
        if (BOILERPLATE_NOTE_TYPES.has(type)) return;
        // Replace inner content with an empty paragraph; preserve the
        // <w:footnote w:id="N"> wrapper so id-resolution stays valid in
        // case mammoth still does a lookup.
        $el.empty();
        $el.append("<w:p/>");
        stripped = true;
    });
    return stripped ? $.xml() : xml;
}

// --- Markdown post-pass: sentinel → pandoc footnote ---------------------

// Replace ⟦FN:N⟧ / ⟦EN:N⟧ in markdown with pandoc-style [^fn-N] / [^en-N]
// markers, and append a definitions block at end. Returns the transformed
// markdown.
//
// `notes` shape: { footnotes: [{id, text}], endnotes: [{id, text}] }.
// Markers in the document that don't have a matching definition are left
// in place as-is (degraded gracefully). Definitions for ids that never
// appear in the markdown are still appended (they exist in the docx, the
// caller may want them).
function restoreFootnoteSentinels(markdown, notes) {
    if (!notes) return markdown;
    let out = markdown
        .replace(/⟦FN:(\d+)⟧/g, (_m, id) => `[^fn-${id}]`)
        .replace(/⟦EN:(\d+)⟧/g, (_m, id) => `[^en-${id}]`);

    const defs = [];
    for (const f of notes.footnotes || []) {
        defs.push(`[^fn-${f.id}]: ${f.text}`);
    }
    for (const e of notes.endnotes || []) {
        defs.push(`[^en-${e.id}]: ${e.text}`);
    }
    if (defs.length === 0) return out;
    if (!out.endsWith("\n")) out += "\n";
    return `${out}\n${defs.join("\n")}\n`;
}

// --- Repack ---------------------------------------------------------------

// Apply (possibly mutated) parts back to the JSZip and emit a buffer mammoth
// can consume. Only writes parts that have a non-null XML payload, so
// missing optional parts (e.g. no comments) stay missing.
async function repackToBuffer(parts) {
    if (parts.documentXml != null)         parts.zip.file("word/document.xml",  parts.documentXml);
    if (parts.footnotesXml != null)        parts.zip.file("word/footnotes.xml", parts.footnotesXml);
    if (parts.endnotesXml != null)         parts.zip.file("word/endnotes.xml",  parts.endnotesXml);
    return await parts.zip.generateAsync({ type: "nodebuffer" });
}

module.exports = {
    SCHEMA_VERSION,
    loadDocxParts,
    extractComments,
    extractRevisions,
    buildSidecar,
    extractFootnotesAndEndnotes,
    injectFootnoteSentinels,
    restoreFootnoteSentinels,
    repackToBuffer,
};
