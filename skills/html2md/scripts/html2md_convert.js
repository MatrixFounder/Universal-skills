"use strict";
// html2md_convert.js — html2md-OWNED turndown wrapper (NOT a replication unit, NOT gated).
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
//
// Pure stdin → stdout filter, same contract as html2md_core.js. The Python bridge
// (core_bridge.py) spawns THIS file.

const { buildTurndown } = require("./html2md_core");

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
    td.addRule("html2mdInlineLink", {
        filter: "a",
        replacement: (content, node) => {
            const href = (typeof node.getAttribute === "function" && node.getAttribute("href")) || "";
            const text = content
                .replace(/[​‌‍﻿]/g, "")  // zero-width chars
                .replace(/\s+/g, " ")
                .trim();
            if (!text) return "";                 // icon-only / empty anchor → drop
            if (!href) return text;               // anchor with no target → plain text
            return `[${text}](${href})`;
        },
    });
    // ARIA-role tables → GFM (the core only handles real <table>).
    td.addRule("html2mdAriaTable", {
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
