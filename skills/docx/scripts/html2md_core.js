"use strict";
// html2md_core.js — the HTML → GFM Markdown core (turndown + merge-aware tables).
//
// MASTER = docx. This module is the single source of truth for the turndown stage
// that was historically inlined in docx2md.js (buildTurndown + expandTableToGrid).
// docx2md.js now require()s it; the html2md skill carries a BYTE-IDENTICAL replica
// (CLAUDE.md §2 — `diff -q` gated). Keep this file pure: HTML in → Markdown out,
// no file/frontmatter/image logic, so the two copies never drift.
//
// Run directly as a pure stdin → stdout filter:  node html2md_core.js < in.html > out.md

const TurndownService = require("turndown");
const turndownPluginGfm = require("turndown-plugin-gfm");

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
    // Drop non-content elements so their raw text never bleeds into the
    // Markdown. (No-op for docx, whose mammoth output is a body fragment with
    // none of these; required for html2md, whose cleaned HTML may carry an
    // injected <style> normalize-sheet and page <script>/<noscript> blocks.)
    turndownService.remove(["title", "style", "script", "noscript"]);
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

// Convenience: one-shot HTML → Markdown (the html2md skill's bridge calls this
// via the stdin/stdout filter below; docx2md.js uses buildTurndown() directly).
function htmlToMarkdown(html) {
    return buildTurndown().turndown(html);
}

module.exports = { buildTurndown, expandTableToGrid, htmlToMarkdown };

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
