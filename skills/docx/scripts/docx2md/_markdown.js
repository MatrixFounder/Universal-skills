// Pure markdown post-processing passes. Each takes the markdown string
// (and sometimes minor options) and returns a transformed markdown string.
// No disk IO, no external tools — fully unit-testable on synthetic input.

const { normalizeForMatching } = require("./_util");

// Lookup-key helper for TOC↔heading matching. Word's TOC field renders
// the resolved plain text, while body headings carry markdown emphasis
// markers (`_..._`, `*..*`) wherever Word styled a span as italic/bold.
// Comparing raw strings fails on any heading with internal italics
// (e.g. `## CHG 1.1 Sub-Process: _RFC Creation (Process)_` vs the TOC's
// `CHG 1.1 Sub-Process: RFC Creation (Process)`). Strip emphasis from
// both sides before keying.
function tocMatchKey(text) {
    return normalizeForMatching(text).toLowerCase();
}

// Mammoth emits one <img> per shape-drawing reference, even when the same
// physical media file is referenced N times. We dedup the FILE via SHA1
// upstream, but the markdown still has N back-to-back identical
// ![](same-href) tokens. Collapse to a single ref.
function collapseDuplicateImageRuns(markdown) {
    const re = /(!\[[^\]]*\]\([^)]+\))(?:\1)+/g;
    let collapsed = 0;
    const out = markdown.replace(re, (_match, first) => {
        collapsed += 1;
        return first;
    });
    if (collapsed > 0) {
        console.log(`[docx-to-md] Collapsed ${collapsed} run(s) of duplicate image refs.`);
    }
    return out;
}

// Word's Heading 1/2/3 often carries auto-numbering via <w:numPr>, which
// mammoth drops. The TOC, however, renders the resolved numbers (e.g.
// "1.0 PURPOSE"). We parse TOC entries (format: `[N.N TEXT PAGE](#anchor)`)
// to build a heading→number map and rewrite unnumbered headings.
// Idempotent: already-numbered headings are left alone.
function applyHeadingNumberingFromTOC(markdown) {
    const lines = markdown.split("\n");
    // Mammoth often escapes dots in markdown (e.g. "1." → "1\."). The
    // regex must accept all of: "1", "1.", "1\.", "1.0", "1.1", "1\.1",
    // "1.0.1", "1\.0\.1". We allow optional backslash before each dot,
    // and an optional trailing dot (with or without backslash).
    const tocEntryRe = /^\[(\d+(?:\\?\.\d+)*\\?\.?)\s+(.+?)\s+\d+\]\([^)]+\)\s*$/;
    const headingToNumber = new Map();
    for (const raw of lines) {
        const m = raw.trim().match(tocEntryRe);
        if (!m) continue;
        // Strip backslash-escapes and trailing dot for canonical form
        // (so "1\." and "1." and "1" all become "1" in the heading).
        const number = m[1].replace(/\\/g, "").replace(/\.+$/, "");
        const text = m[2].trim();
        const key = tocMatchKey(text);
        if (!headingToNumber.has(key)) {
            headingToNumber.set(key, number);
        }
    }
    if (headingToNumber.size === 0) return markdown;

    const headingRe = /^(#{1,6})\s+(.+?)\s*$/;
    // Already-numbered headings are skipped; accept the same loose
    // numbering format as the TOC regex.
    const leadingNumberRe = /^\d+(?:\\?\.\d+)*\\?\.?(?:\s|$)/;
    let rewrites = 0;
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(headingRe);
        if (!m) continue;
        const hashes = m[1];
        const rawText = m[2].trim();
        if (leadingNumberRe.test(tocMatchKey(rawText))) continue;
        const num = headingToNumber.get(tocMatchKey(rawText));
        if (!num) continue;
        lines[i] = `${hashes} ${num} ${rawText}`;
        rewrites += 1;
    }
    if (rewrites > 0) {
        console.log(`[docx-to-md] Applied TOC-based numbering to ${rewrites} heading(s).`);
    }
    return lines.join("\n");
}

// TOC entries mammoth extracts look like `[1.0 PURPOSE 4](#_Toc173719255)`.
// `_Toc...` is Word's bookmark id — markdown renderers generate their own
// slugs from heading text instead, so the href 404s. Inline an explicit
// `<a id="_TocXXX" name="_TocXXX"></a>` anchor at the start of the
// heading text so the original hrefs resolve in every renderer:
//
//   ## <a id="_Toc173"></a>1.0 PURPOSE
//
// Inlining (vs a separate line above) puts the anchor INSIDE the
// rendered <h*> element, so renderers that wrap stand-alone HTML in
// <p> (markdown-it) or strip it (sanitizers) still keep the heading
// itself as the scroll target. `name=` is the legacy attribute kept
// for renderers that strip `id` on inline `<a>`. Idempotent on re-run.
function injectTocAnchors(markdown) {
    const lines = markdown.split("\n");
    // Number prefix pattern accepts "1", "1.", "1\.", "1.1", "1\.1", etc.
    const tocEntryRe = /^\[(?:\d+(?:\\?\.\d+)*\\?\.?\s+)?(.+?)\s+\d+\]\(#(_Toc[\w-]+)\)\s*$/;
    const headingRe = /^(#{1,6}\s+)(.+?)\s*$/;
    const tocAnchorByHeading = new Map();
    for (const raw of lines) {
        const m = raw.trim().match(tocEntryRe);
        if (!m) continue;
        const tocId = m[2];
        const key = tocMatchKey(m[1]);
        if (!tocAnchorByHeading.has(key)) {
            tocAnchorByHeading.set(key, tocId);
        }
    }
    if (tocAnchorByHeading.size === 0) return markdown;

    const out = [];
    let inserted = 0;
    const usedIds = new Set();
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(headingRe);
        if (!m) { out.push(lines[i]); continue; }
        const hashes = m[1];
        const headingBody = m[2];
        // Idempotency: skip if heading already starts with our anchor.
        const idempotent = headingBody.trim().match(/^<a\s+id="(_Toc[\w-]+)"/i);
        if (idempotent) {
            usedIds.add(idempotent[1]);
            out.push(lines[i]);
            continue;
        }
        // Body headings may carry "1.0" numbering from
        // applyHeadingNumberingFromTOC; TOC entries also have it. Try both
        // — with and without leading number — when looking up.
        const norm = tocMatchKey(headingBody);
        const stripped = norm.replace(/^\d+(?:\.\d+)*\.?\s+/, "");
        const tocId = tocAnchorByHeading.get(norm) || tocAnchorByHeading.get(stripped);
        if (tocId && !usedIds.has(tocId)) {
            out.push(`${hashes}<a id="${tocId}" name="${tocId}"></a>${headingBody}`);
            usedIds.add(tocId);
            inserted += 1;
        } else {
            out.push(lines[i]);
        }
    }

    // Second pass: TOC entries can also point at role/term names that
    // mammoth flattened into table cells (heading style downgraded to
    // bold by docx2md). For each remaining unresolved TOC id, scan
    // table-row lines for the first `**TEXT**` whose normalized text
    // matches the TOC key, and inject the anchor inside that bold span.
    let cellInserted = 0;
    const remaining = new Map();
    for (const [key, id] of tocAnchorByHeading.entries()) {
        if (!usedIds.has(id)) remaining.set(key, id);
    }
    if (remaining.size > 0) {
        const boldRe = /\*\*([^*]+?)\*\*/g;
        for (let i = 0; i < out.length; i++) {
            const line = out[i];
            if (!line.startsWith("|")) continue;
            let mutated = false;
            const replaced = line.replace(boldRe, (match, inner) => {
                if (mutated) return match;
                if (/<a\s+id="_Toc[\w-]+"/i.test(inner)) return match;
                const key = tocMatchKey(inner);
                const id = remaining.get(key);
                if (!id || usedIds.has(id)) return match;
                usedIds.add(id);
                remaining.delete(key);
                mutated = true;
                cellInserted += 1;
                return `**<a id="${id}" name="${id}"></a>${inner}**`;
            });
            if (mutated) out[i] = replaced;
            if (remaining.size === 0) break;
        }
    }

    if (inserted + cellInserted > 0) {
        const total = inserted + cellInserted;
        const cellNote = cellInserted > 0 ? ` (${cellInserted} inside table cells)` : "";
        console.log(`[docx-to-md] Inlined ${total} TOC anchor(s) so [text](#_TocN) links resolve${cellNote}.`);
    }
    return out.join("\n");
}

// Drop heading lines whose body is empty (mammoth produces these from
// docx paragraphs styled as "Heading X" but containing no text — common
// between sub-sections). They render as visible blank slots in markdown
// viewers and break outline navigation.
function dropEmptyHeadings(markdown) {
    const lines = markdown.split("\n");
    const out = [];
    let dropped = 0;
    for (const line of lines) {
        if (/^#{1,6}\s*$/.test(line)) {
            dropped += 1;
            continue;
        }
        out.push(line);
    }
    if (dropped > 0) {
        console.log(`[docx-to-md] Dropped ${dropped} empty heading line(s).`);
    }
    return out.join("\n");
}

// Strip image references that point at near-empty assets (e.g. 1×1 pixel
// spacers, sub-500-byte placeholder images that mammoth extracts from the
// docx). `imagesDirPath` is required so we can stat the target files;
// `imagesDirName` is the basename used in the markdown href.
function dropTinyImageRefs(markdown, ctx, sizeThresholdBytes = 500) {
    const fs = require("fs");
    const path = require("path");
    const segment = ctx.imagesDirName + "/";
    const lines = markdown.split("\n");
    let removed = 0;
    const cleaned = lines.map((line) =>
        line.replace(/!\[[^\]]*\]\(([^)]+)\)/g, (token, href) => {
            const decoded = decodeURIComponent(href);
            const idx = decoded.indexOf(segment);
            if (idx < 0) return token;
            const filename = decoded.slice(idx + segment.length);
            try {
                const size = fs.statSync(path.join(ctx.imagesDirPath, filename)).size;
                if (size < sizeThresholdBytes) {
                    removed += 1;
                    return "";
                }
            } catch (_) { /* missing — leave the broken ref alone */ }
            return token;
        }),
    );
    if (removed > 0) {
        console.log(`[docx-to-md] Dropped ${removed} near-empty image ref(s) (< ${sizeThresholdBytes} bytes).`);
    }
    // After removal lines may be blank; compact double-blank runs.
    const compacted = [];
    let prevBlank = false;
    for (const line of cleaned) {
        const blank = line.trim() === "";
        if (blank && prevBlank) continue;
        compacted.push(line);
        prevBlank = blank;
    }
    return compacted.join("\n");
}

module.exports = {
    collapseDuplicateImageRuns,
    applyHeadingNumberingFromTOC,
    injectTocAnchors,
    dropEmptyHeadings,
    dropTinyImageRefs,
};
