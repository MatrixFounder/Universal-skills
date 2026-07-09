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

const { buildTurndown, expandTableToGrid } = require("./html2md_core");

// Min length (chars) of a `data:` image URI to treat it as CONTENT (kept) rather than a
// tiny icon/mascot/tracking-pixel blob (dropped). ~1 KB of URI ≈ ≥0.7 KB decoded — well
// below any real diagram, well above a 1px PNG (~70 chars). Keep in sync with emit.py's
// _DATA_URI_MIN_LEN.
const DATA_URI_MIN_LEN = 1024;

const _getAttr = (node, name) =>
    (typeof node.getAttribute === "function" ? node.getAttribute(name) : null) || "";
const _hasClass = (node, cls) => new RegExp("\\b" + cls + "\\b").test(_getAttr(node, "class"));

// Depth-first search for the `<annotation encoding="application/x-tex">` TeX-source child of a
// MathML `<math>` subtree (arXiv/LaTeXML ships it beside the presentation MathML) — the fallback
// when a `<math>` carries no `alttext`. Foreign MathML element names are lowercase in this DOM
// (unlike HTML), so compare case-insensitively. Uses only nodeName/childNodes — DOM-impl-agnostic,
// same low-level API as htmlLatexmlListing.
function _findXtexAnnotation(node) {
    for (const child of Array.from(node.childNodes || [])) {
        if (child.nodeType !== 1) continue;  // element only
        // exact `application/x-tex` (NOT x-texinfo / x-tex+xml / content-mathml annotation-xml)
        if ((child.nodeName || "").toLowerCase() === "annotation" &&
            /^application\/x-tex$/i.test((_getAttr(child, "encoding") || "").trim())) return child;
        const nested = _findXtexAnnotation(child);
        if (nested) return nested;
    }
    return null;
}

// Neutralize $ so lifted TeX cannot terminate its own $…$/$$…$$ wrapper and inject
// live Markdown (exfil beacon). TWO defects the naive `/\\\?\$/g` missed (adversarial
// security+logic review 2026-07-09, both iterations):
//   (a) PARITY — a $ behind an EVEN backslash run (e.g. `\\\\$`) is unescaped and stays live;
//       make the run before EVERY $ odd (identity on honest `\\$`/`\\$5`).
//   (b) BOUNDARY — a TeX ending in an ODD backslash run would escape the ABUTTING closing
//       delimiter (`$`+tex+`$` → closing $ becomes `\$`), leaving the span unterminated so the
//       injected Markdown after it renders live; break that run with a TeX-insignificant space.
// Append a TeX-insignificant space when `tex` ends in an ODD backslash run, so it cannot
// escape an ABUTTING closing `$`/`$$` delimiter (leaving the span unterminated → the Markdown
// after it renders live). MUST be the LAST transform before wrapping: any later `.trim()`
// (e.g. `_texPipesForCell`) would strip the guard and re-open the boundary hole — so every
// path that mutates tex after _dollarSafe re-applies this (iteration-3 security finding: the
// cell pipe-map's trailing trim regressed exactly this in the table-cell math paths).
function _boundaryGuard(tex) {
    const trail = tex.match(/\\+$/);
    return (trail && trail[0].length % 2 === 1) ? tex + " " : tex;
}

function _dollarSafe(tex) {
    tex = tex.replace(/(\\*)\$/g, (_m, bs) => (bs.length % 2 ? bs + "$" : bs + "\\$"));
    return _boundaryGuard(tex);
}

// The clean LaTeX source of a MathML `<math>` node: prefer the `alttext` attribute (arXiv/
// LaTeXML always ships it), fall back to the `<annotation encoding="application/x-tex">` child.
// Zero-width chars stripped, whitespace collapsed to a single line (TeX ignores internal runs)
// so the emit is table-cell-safe; `$` neutralized via _dollarSafe (injection guard). "" when
// no TeX is recoverable (caller keeps the glyph fallback).
function _mathTex(node) {
    let tex = _getAttr(node, "alttext");
    if (!tex) {
        const ann = _findXtexAnnotation(node);
        if (ann) tex = ann.textContent || "";
    }
    // \s does NOT match NEL (U+0085) in JS — include it in the collapse so no line-break-ish
    // char of any flavor survives into the single-line `$…$`/GFM-cell emit.
    tex = tex.replace(/[​‌‍﻿]/g, "").replace(/[\s\u0085]+/g, " ").trim();
    return _dollarSafe(tex);
}

// True when the node sits inside a GFM table cell — the ONLY context whose Markdown escaper
// rewrites `|`→`\|` (html2md_core cell escaper), corrupting math pipes. TWO signals are
// needed because cell content is converted by RE-PARSING its innerHTML (html2md_core.js:52
// for <table>, _cellMd below for ARIA tables), which severs the <td>/<th> ancestry:
//   • _cellDepth — set around every cell re-conversion (the htmlTableCellContext wrapper
//     rule + _cellMd), covers the re-parsed pass that actually produces the emitted text;
//   • the ancestor walk — covers the outer discarded pass (turndown builds then throws away
//     `content` for a table subtree) plus any non-re-parsed path. Bounded by DOM depth;
//     runs only inside math/listing replacements, never in a filter.
let _cellDepth = 0;
function _inTableCell(node) {
    if (_cellDepth > 0) return true;
    for (let p = node.parentNode; p; p = p.parentNode) {
        const n = (p.nodeName || "").toUpperCase();
        if (n === "TD" || n === "TH") return true;
    }
    return false;
}

// Make TeX pipe-free for a GFM table cell: `\|`→`\Vert` (‖), bare `|`→`\vert` (|) — both
// semantically identical — so the core cell escaper (`|`→`\|`, which KaTeX misreads as
// `\\`+`|`) has nothing to touch. A `\begin{array|darray|tabular}{…}` column preamble is
// EXEMPT: there `|` is a vertical RULE and KaTeX's column parser accepts only `l c r | :`
// (`\vert`/`\|` throw "Unknown column alignment"), so preamble pipes pass through untouched.
// The cell escaper then still breaks that rare×rare combination (array-with-rules INSIDE a
// GFM cell) — accepted honest-scope: no pipe-free spelling of a column rule exists, so it is
// unrepresentable either way. Outside cells this mapping never runs (adversarial logic
// finding 2026-07-09: the previously-unconditional remap corrupted standalone `{c|c}`).
// The preamble matcher handles SINGLE-level colspecs (`{c|c}`, `{|c|c|}`); a nested-brace
// colspec (`{>{\raggedright}p{2cm}|c}`) isn't protected, so its rule-`|` gets mapped — but
// KaTeX rejects such colspecs regardless, so this fails safely (no crash — the restore no-ops
// when nothing was saved; iteration-2 logic finding, accepted honest-scope).
function _texPipesForCell(tex) {
    const saved = [];
    // NUL is unreachable in parsed attribute/text content (HTML parsing maps raw NUL and
    // `&#0;` to U+FFFD), so it is a collision-free placeholder.
    let out = tex.replace(
        /\\begin\{(?:array|darray|tabular)\*?\}(?:\s*\[[^\]]*\])?\s*\{[^{}]*\}/g,
        (m) => { saved.push(m); return "\x00" + (saved.length - 1) + "\x00"; });
    out = out.replace(/\\\|/g, "\\Vert ").replace(/\|/g, "\\vert ");
    // The `.trim()` here can strip _dollarSafe's boundary-guard space → re-apply it LAST so a
    // trailing odd-backslash can't escape the abutting closing delimiter (iteration-3 finding).
    return _boundaryGuard(out.replace(/\x00(\d+)\x00/g, (_m, i) => saved[+i]).trim());
}

// textContent for a LaTeXML listing-line subtree, dropping the line-number gutter at any
// depth. Runs ONLY on the math-free fenced-code path — the pseudocode branch is gated on
// `lineEls.some(_descHasMath)`, so by construction no `<math>` node can reach here (a math
// branch existed and was removed as dead code — adversarial logic finding 2026-07-09).
function _listingText(node) {
    if (node.nodeType === 3) return node.nodeValue || "";  // text node
    if (node.nodeType !== 1) return "";
    if (_hasClass(node, "ltx_tag_listingline")) return "";  // drop line-number gutter at any depth
    let out = "";
    for (const child of Array.from(node.childNodes || [])) out += _listingText(child);
    return out;
}

// True if a subtree contains a MathML `<math>` descendant → the listing is pseudocode/algorithm
// (arXiv Algorithm env), NOT real code, so its math should render rather than be fenced literal.
function _descHasMath(node) {
    if ((node.nodeName || "").toLowerCase() === "math") return true;
    for (const child of Array.from(node.childNodes || [])) {
        if (child.nodeType === 1 && _descHasMath(child)) return true;
    }
    return false;
}

// Markdown for ONE pseudocode line: drop the line-number gutter, render a `<math>` as inline
// `$…$` (so it displays, unlike inside a code fence), a `ltx_font_bold` span (Input:/Output:/
// while/return keywords) as `**…**`, everything else as text. `inCell` gates the pipe→\vert
// remap (needed only under a GFM cell escaper). Honest scope: LaTeXML algorithmic nesting is
// encoded as ltx_minipage pt-WIDTHS + decorative SVG scope rules (no text indentation exists
// in the markup), so loop/if bodies render flush-left — parsing widths back into indent
// levels is out of scope (adversarial logic finding 2026-07-09, accepted).
function _algoLine(node, inCell) {
    if (node.nodeType === 3) return node.nodeValue || "";
    if (node.nodeType !== 1) return "";
    if (_hasClass(node, "ltx_tag_listingline")) return "";  // line-number gutter
    if ((node.nodeName || "").toLowerCase() === "math") {
        let tex = _mathTex(node);
        if (tex && inCell) tex = _texPipesForCell(tex);
        return tex ? "$" + tex + "$" : (node.textContent || "");
    }
    let inner = "";
    for (const child of Array.from(node.childNodes || [])) {
        const piece = _algoLine(child, inCell);
        // Two adjacent inline `<math>` siblings with no separating text would emit `$a$$b$`
        // — an ambiguous delimiter run KaTeX may parse as one display block. Keep distinct.
        if (piece.startsWith("$") && inner.endsWith("$")) inner += " ";
        inner += piece;
    }
    if (_hasClass(node, "ltx_font_bold")) {
        const t = inner.trim();
        return t ? "**" + t + "** " : inner;
    }
    return inner;
}

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

// Convert a cell element's inner HTML to single-line inline Markdown. The re-parse severs
// DOM ancestry, so _cellDepth marks the cell context for the math/listing rules.
function _cellMd(td, el) {
    const html = el && el.innerHTML ? el.innerHTML : "";
    let md = "";
    _cellDepth++;
    try {
        md = html ? td.turndown(html) : "";
    } catch (e) {
        md = el && el.textContent ? el.textContent : "";
    } finally {
        _cellDepth--;
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
    // Shadow the core's <table> rule (same delegation to the exported expandTableToGrid —
    // the docx-mastered core stays untouched) purely to mark the cell context: the core
    // converts each cell by re-parsing its innerHTML (html2md_core.js:52), which severs the
    // <td> ancestry the math/listing rules need to decide pipe-remapping and display shape.
    // Added after the core's rule → turndown prepends it → this wrapper wins.
    td.addRule("htmlTableCellContext", {
        filter: (node) => node.nodeName === "TABLE",
        replacement: (_content, node) => {
            _cellDepth++;
            try {
                return expandTableToGrid(node, td);
            } finally {
                _cellDepth--;
            }
        },
    });
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
            // Collapse ALL interior whitespace (incl. NEL U+0085, which JS `\s` misses) to a
            // single space, self-defending rather than relying on turndown's own collapse: an
            // interior blank line would otherwise be a BLOCK paragraph split, orphaning the
            // opening `$` and rendering the rest as live Markdown (adversarial security finding
            // 2026-07-09). TeX ignores internal whitespace, so this is lossless for math.
            let tex = (node.textContent || "").replace(/[​‌‍﻿]/g, "").replace(/[\s\u0085]+/g, " ").trim();
            tex = tex
                .replace(/^\\\(([\s\S]*)\\\)$/, "$1")   // \( … \)
                .replace(/^\\\[([\s\S]*)\\\]$/, "$1")   // \[ … \]
                .replace(/^\$\$([\s\S]*)\$\$$/, "$1")    // $$ … $$
                .replace(/^\$([\s\S]*)\$$/, "$1")        // $ … $
                .trim();
            if (!tex) return "";
            // Same $-breakout hardening as _mathTex: this rule also lifts untrusted
            // textContent raw into a $…$ wrapper (adversarial security finding 2026-07-09).
            tex = _dollarSafe(tex);
            return _hasClass(node, "display") ? "\n\n$$\n" + tex + "\n$$\n\n" : "$" + tex + "$";
        },
    });
    // arXiv / LaTeXML (ar5iv) render EVERY formula as raw MathML: `<math class="ltx_Math"
    // alttext="<clean LaTeX>" display="inline|block"> …presentation glyphs… </math>` (no
    // class="math" span, so htmlMath above never fires). With no rule, turndown recurses and
    // dumps the flattened presentation Unicode glyphs + the markdown-escaped <annotation> TeX,
    // undelimited — unrenderable garble that md_clean._normalize_math then no-ops on. Lift the
    // clean TeX that already ships in `alttext` (fallback: the <annotation encoding=
    // "application/x-tex"> child) and emit `$`-delimited DIRECTLY:
    //   • $ directly, NOT \(…\)/\[…\] — a <math> IS math, so it must NOT pass through
    //     md_clean's _looks_like_math DISPLAY gate (which could silently drop a real equation);
    //     and turndown does not re-escape a rule's raw return, so the TeX stays unescaped.
    //   • display INSIDE a GFM table cell → SINGLE-LINE `$$…$$` with pipe-free TeX
    //     (_texPipesForCell): arXiv display equations sit in <table> layouts where the
    //     newline-wrapped block form (and a raw `|`) would break the GFM row.
    //   • display OUTSIDE a cell → blank-line-wrapped block `$$\n…\n$$` (same shape as the
    //     htmlMath sibling above), pipes UNTOUCHED — `\begin{array}{c|c}` column specs stay
    //     KaTeX-valid. A block equation authored WITHOUT display="block" renders inline —
    //     accepted honest-scope (the attribute is the only signal the markup gives us).
    //   • presentation-only MathML (no alttext, no x-tex annotation — e.g. MathJax v3
    //     assistive MML, hand-authored MDN/Wikipedia) → glyph fallback (_content), never a
    //     silent drop: clean TeX is recoverable ⇔ the source ships it; rebuilding TeX from
    //     presentation MathML is an explicit non-goal (TASK 028 audit `do_not`).
    // MathML foreign-element nodeName is LOWERCASE here (`math`, not `MATH`). html-owned rule.
    td.addRule("htmlMathml", {
        filter: (node) => (node.nodeName || "").toLowerCase() === "math",
        replacement: (_content, node) => {
            let tex = _mathTex(node);
            // no recoverable TeX (presentation-only MathML, e.g. hand-authored Wikipedia/MDN) →
            // keep turndown's default glyph rendering rather than silently dropping the formula.
            if (!tex) return _content;
            const display = _getAttr(node, "display") === "block";
            if (_inTableCell(node)) {
                tex = _texPipesForCell(tex);
                return display ? "$$" + tex + "$$" : "$" + tex + "$";
            }
            return display ? "\n\n$$\n" + tex + "\n$$\n\n" : "$" + tex + "$";
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
            // A listing carrying inline <math> is PSEUDOCODE (arXiv Algorithm env), not real code:
            // render it as text with rendered `$…$` math + `**bold**` keywords + hard line breaks
            // so the math DISPLAYS (a ``` fence would show it as literal LaTeX). A math-free
            // listing is real code → keep the fenced block (raw, monospace).
            if (lineEls.some(_descHasMath)) {
                const inCell = _inTableCell(node);
                const algo = lineEls
                    .map((line) => _algoLine(line, inCell).replace(/[ \t]+/g, " ").trim())
                    .filter((s) => s);
                // two-space hard breaks survive md_clean; blank-line-wrapped as its own block
                return "\n\n" + algo.join("  \n") + "\n\n";
            }
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
                    text += _listingText(child);  // ltx_lst_space spaces preserved (no math here — gated above)
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
