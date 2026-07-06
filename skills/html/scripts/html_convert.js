"use strict";
// html_convert.js — html-OWNED turndown wrapper (NOT a replication unit, NOT gated).
//
// It require()s the docx-mastered, byte-identical `html2md_core.buildTurndown()` and
// EXTENDS it with markdown-oriented rules that web pages need but docx (mammoth's clean
// semantic HTML) does not — so these live here, never in the gated core:
//
//   • ARIA-role tables (role="table"/"row"/"columnheader"/"cell") — used by GitBook,
//     Mintlify, Fern, etc. — turndown only understands real <table>, so without this
//     every cell flattens to a stray paragraph. We rebuild a GFM table from the DOM.
//   • Leaf chrome buttons ("Copy", "Ask AI", "Copy page", …) whose label text otherwise
//     leaks into the Markdown above code blocks.
//   • Inline-collapsed links (block-content nav anchors) + dropped icon/zero-width anchors.
//   • `data:` URI links dropped (→ plain text); `data:` URI images kept when content-sized
//     (≥ DATA_URI_MIN_LEN, localized to _attachments/ by emit.py), tiny icon blobs dropped.
//   • arXiv/LaTeXML (ar5iv) `div.ltx_listing` code listings → fenced code blocks, dropping
//     the line-number gutter span (mirrors docx `_html2docx_walker.emitLatexmlListing`).
//
// Pure stdin → stdout filter, same contract as html2md_core.js. The Python bridge
// (core_bridge.py) spawns THIS file.

const { buildTurndown } = require("./html2md_core");

// Min length (chars) of a `data:` image URI to treat it as CONTENT (kept) rather than a
// tiny icon/mascot/tracking-pixel blob (dropped). ~1 KB of URI ≈ ≥0.7 KB decoded — well
// below any real diagram, well above a 1px PNG (~70 chars). Keep in sync with emit.py's
// _DATA_URI_MIN_LEN.
const DATA_URI_MIN_LEN = 1024;

const _getAttr = (node, name) =>
    (typeof node.getAttribute === "function" ? node.getAttribute(name) : null) || "";
const _hasClass = (node, cls) => new RegExp("\\b" + cls + "\\b").test(_getAttr(node, "class"));

// CommonMark-valid link/image destination. Archive extraction localizes subresources
// to their DECODED filenames (e.g. Confluence attachments: "Снимок экрана … 12.58.03.png"),
// so a src/href can legitimately contain spaces or parens — emitted bare, that destination
// is invalid Markdown and downstream localization (emit.py _IMG_RE) silently skips it.
// Wrap such destinations in <…> (percent-encoding the bracket-terminating chars). First
// mirror the URL spec's whitespace handling: strip ALL tabs/newlines, and trim leading/
// trailing C0-control/space (a href="  /path" is junk padding, not part of the URL).
function _mdDest(url) {
    const u = String(url || "")
        .replace(/[\t\r\n]/g, "")
        .replace(/^[\x00-\x20]+|[\x00-\x20]+$/g, "");
    if (!/[\s()<>]/.test(u)) return u;
    // Backslash is an ESCAPE inside <…> (CommonMark): a trailing "\" reads as "\>"
    // and unterminates the destination (whole link lost); "\." collapses to "." in
    // spec parsers (silent retarget). Percent-encode it with the bracket chars —
    // emit.py's unquote() restores it for local file resolution.
    return "<" + u.replace(/\\/g, "%5C").replace(/</g, "%3C").replace(/>/g, "%3E") + ">";
}

// Convert a cell element's inner HTML to single-line inline Markdown.
function _cellMd(td, el) {
    const html = el && el.innerHTML ? el.innerHTML : "";
    let md = "";
    try {
        md = html ? td.turndown(html) : "";
    } catch (e) {
        md = el && el.textContent ? el.textContent : "";
    }
    return md.trim().replace(/\s*\n+\s*/g, " ").replace(/\|/g, "\\|");
}

// Column headers from the nearest PRECEDING sibling header group. GitBook keeps the
// header row in a sibling role="rowgroup" (not inside role="table"); we take exactly
// ONE group — never every columnheader in the parent (which would let a headerless
// table borrow a neighbouring table's headers).
function _siblingHeaders(node) {
    let sib = node.previousElementSibling;
    while (sib) {
        const chs = Array.from(sib.querySelectorAll('[role="columnheader"]'));
        if (chs.length) return chs;
        sib = sib.previousElementSibling;
    }
    return [];
}

// Rebuild a GFM table from an ARIA role="table" subtree (or "" if it has no rows).
// querySelectorAll is recursive, so every selection is scoped to THIS table — rows,
// cells and headers that actually belong to a NESTED role="table" are excluded (else
// the inner table would be merged into the outer grid and its cells converted twice).
function _ariaTableToGrid(td, node) {
    const ownTable = (el) => !el.closest || el.closest('[role="table"]') === node;
    let headerEls = Array.from(node.querySelectorAll('[role="columnheader"]')).filter(ownTable);
    if (headerEls.length === 0) headerEls = _siblingHeaders(node);
    let header = headerEls.map((h) => _cellMd(td, h));
    const bodyRows = Array.from(node.querySelectorAll('[role="row"]'))
        .filter((r) => ownTable(r) && r.querySelector('[role="cell"]'))
        .map((r) => Array.from(r.querySelectorAll('[role="cell"]'))
            .filter((c) => !c.closest || c.closest('[role="row"]') === r)
            .map((c) => _cellMd(td, c)));

    if (header.length === 0) {
        if (bodyRows.length === 0) return "";
        header = bodyRows.shift(); // no explicit header → promote the first row
    }
    const ncols = Math.max(header.length, ...bodyRows.map((r) => r.length), 1);
    const pad = (row) => {
        const r = row.slice();
        while (r.length < ncols) r.push("");
        return r;
    };
    const lines = ["| " + pad(header).join(" | ") + " |", "|" + "---|".repeat(ncols)];
    for (const r of bodyRows) lines.push("| " + pad(r).join(" | ") + " |");
    return "\n\n" + lines.join("\n") + "\n\n";
}

function buildConverter() {
    const td = buildTurndown();
    // Strip chrome controls whose label text otherwise leaks into the Markdown:
    // <button> tags + any "Copy"-labelled control. A role="button" DIV is removed only
    // when it is a LEAF (no element children) — so accordion summaries that wrap real
    // prose in role="button" keep their content.
    td.remove((node) => {
        if (node.nodeName === "BUTTON") return true;
        if (typeof node.getAttribute !== "function") return false;
        if (/^copy\b/i.test(node.getAttribute("aria-label") || "")) return true;
        if (node.getAttribute("role") === "button") {
            return !node.children || node.children.length === 0;
        }
        return false;
    });
    // Inline-collapse links. Doc-site nav/heading anchors wrap block elements
    // (<a><div>…text…</div></a>) or an icon-only hash link, so turndown's default
    // emits a link whose text is split across lines ("[\n\ntext\n\n](url)") — broken
    // Markdown. Collapse the (already-converted) inner content to ONE line, and DROP
    // anchors whose visible text is empty / zero-width only (icon/hash-link chrome);
    // an emptied heading anchor then leaves a bare "## " that md_clean merges with its
    // title.
    td.addRule("htmlInlineLink", {
        filter: "a",
        replacement: (content, node) => {
            const href = (typeof node.getAttribute === "function" && node.getAttribute("href")) || "";
            const text = content
                .replace(/[​‌‍﻿]/g, "")  // zero-width chars
                .replace(/\s+/g, " ")
                .trim();
            if (!text) return "";                 // icon-only / empty anchor → drop
            if (!href || /^data:/i.test(href)) return text;  // no target / data: blob → plain text
            return `[${text}](${_mdDest(href)})`;
        },
    });
    // ARIA-role tables → GFM (the core only handles real <table>).
    td.addRule("htmlAriaTable", {
        filter: (node) =>
            node.nodeName !== "TABLE" &&
            typeof node.getAttribute === "function" &&
            node.getAttribute("role") === "table",
        replacement: (_content, node) => {
            try {
                return _ariaTableToGrid(td, node);
            } catch (e) {
                // Never abort the whole conversion on one malformed table.
                return node && node.textContent ? "\n\n" + node.textContent.trim() + "\n\n" : "";
            }
        },
    });
    // MathJax/Pandoc math → Obsidian/KaTeX `$…$` (inline) / `$$…$$` (display).
    // Pandoc & friends emit `<span class="math inline">\(TeX\)</span>` and
    // `class="math display">\[TeX\]`. With no rule, turndown markdown-escapes the TeX
    // (`\_` `\*` `\[` → broken subscripts/operators) AND leaves the `\(…\)` delimiters that
    // Obsidian can't render. We take the RAW textContent (turndown does NOT re-escape a
    // rule's return value), strip the wrapping delimiters, and re-emit `$`-delimited — which
    // renders natively in Obsidian and VS Code's built-in Markdown preview, no extension.
    td.addRule("htmlMath", {
        // Require the Pandoc pairing `math` + (`inline`|`display`). Matching bare `math`
        // would false-positive on classes like `not-math` / `post-math` (\bmath\b treats
        // `-` as a boundary), wrapping non-TeX text in `$…$`.
        filter: (node) =>
            (node.nodeName === "SPAN" || node.nodeName === "DIV") &&
            _hasClass(node, "math") &&
            (_hasClass(node, "inline") || _hasClass(node, "display")),
        replacement: (_content, node) => {
            let tex = (node.textContent || "").replace(/[​‌‍﻿]/g, "").trim();
            tex = tex
                .replace(/^\\\(([\s\S]*)\\\)$/, "$1")   // \( … \)
                .replace(/^\\\[([\s\S]*)\\\]$/, "$1")   // \[ … \]
                .replace(/^\$\$([\s\S]*)\$\$$/, "$1")    // $$ … $$
                .replace(/^\$([\s\S]*)\$$/, "$1")        // $ … $
                .trim();
            if (!tex) return "";
            return _hasClass(node, "display") ? "\n\n$$\n" + tex + "\n$$\n\n" : "$" + tex + "$";
        },
    });
    // `data:` URI images: keep CONTENT-sized blobs (real diagrams are often inlined as
    // base64, e.g. static blogs / ENS `.eth.limo` / Notion exports), drop only tiny
    // icon/mascot/tracking-pixel blobs. Downstream (emit.py): --download-images (default)
    // decodes a surviving data: URI → `_attachments/`; --no-download (file mode) keeps it as
    // a self-contained inline link; --stdout strips it (no localization → would be base64
    // bloat in the agent stream). The length gate here governs ALL modes, so tiny icons
    // never reach the Markdown. Keep this threshold in sync with emit.py's _DATA_URI_MIN_LEN.
    td.addRule("htmlImage", {
        filter: "img",
        replacement: (_content, node) => {
            let src = _getAttr(node, "src");
            if (!src) return "";
            if (/^data:/i.test(src)) {
                // Collapse any internal whitespace (HTML attributes may wrap a long base64
                // payload across lines) so the single-line Markdown link stays parseable by
                // emit.py's _IMG_RE, which stops at whitespace.
                src = src.replace(/\s+/g, "");
                if (src.length < DATA_URI_MIN_LEN) return "";  // tiny icon blob
            }
            const alt = _getAttr(node, "alt");
            const title = _getAttr(node, "title");
            return `![${alt}](${_mdDest(src)}${title ? ` "${title}"` : ""})`;
        },
    });
    // arXiv / LaTeXML (ar5iv) code listings render as <div class="ltx_listing"> wrapping
    // one <div class="ltx_listingline"> per source line (inline <span> tokens, NOT <pre>).
    // turndown would explode every token onto its own paragraph and glue the line-number
    // gutter onto the first token ("1PROMPT_TEMPLATE"). Rebuild a fenced code block,
    // dropping the gutter span — mirrors docx's _html2docx_walker.emitLatexmlListing.
    td.addRule("htmlLatexmlListing", {
        filter: (node) => node.nodeName === "DIV" && _hasClass(node, "ltx_listing"),
        replacement: (content, node) => {
            const lineEls = Array.from(node.children || []).filter((c) => _hasClass(c, "ltx_listingline"));
            if (!lineEls.length) return content;
            const lines = lineEls.map((line) => {
                let text = "";
                for (const child of Array.from(line.childNodes || [])) {
                    if (child.nodeType === 3) {                  // text node
                        const d = child.nodeValue || "";
                        if (d.trim() !== "") text += d;          // skip pretty-print whitespace
                        continue;
                    }
                    if (child.nodeType !== 1) continue;          // element only
                    if (_hasClass(child, "ltx_tag_listingline")) continue;  // drop line-number gutter
                    text += child.textContent || "";            // ltx_lst_space spaces preserved
                }
                return text.replace(/\s+$/, "");
            });
            return "\n\n```\n" + lines.join("\n") + "\n```\n\n";
        },
    });
    return td;
}

function htmlToMarkdown(html) {
    return buildConverter().turndown(html);
}

module.exports = { htmlToMarkdown, buildConverter };

// Pure stdin → stdout filter when executed directly.
if (require.main === module) {
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { input += chunk; });
    process.stdin.on("end", () => {
        try {
            process.stdout.write(htmlToMarkdown(input));
        } catch (e) {
            process.stderr.write(String((e && e.message) || e) + "\n");
            process.exit(1);
        }
    });
}
