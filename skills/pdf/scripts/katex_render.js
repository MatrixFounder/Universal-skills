"use strict";
// katex_render.js — batch TeX → MathML for md2pdf's math preprocessing (pdf-owned).
//
// Reads a JSON array of {tex, display} on stdin, renders each with KaTeX to MathML, and
// writes a JSON array of {mathml} | {error} (same order) on stdout. One Node process for
// the whole document (per-formula process startup would dominate runtime on math-heavy
// papers). weasyprint (md2pdf's renderer) typesets MathML natively but has NO JS engine,
// so client-side KaTeX/MathJax is impossible — server-side MathML is the only path.
//
// The `<annotation encoding="application/x-tex">` element KaTeX adds for accessibility is
// STRIPPED: weasyprint renders its text content, which would duplicate the raw TeX next to
// the typeset math. throwOnError is off → a bad formula renders in red instead of aborting
// the batch; we still report it so the caller can keep the literal `$…$` if preferred.
const katex = require("./node_modules/katex");

const ANNOTATION = /<annotation\b[^>]*>[\s\S]*?<\/annotation>/gi;

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => { raw += c; });
process.stdin.on("end", () => {
    let items;
    try {
        items = JSON.parse(raw);
    } catch (e) {
        process.stderr.write("katex_render: invalid JSON input\n");
        process.exit(2);
    }
    const out = items.map((it) => {
        try {
            const html = katex.renderToString(String(it.tex), {
                output: "mathml",
                displayMode: !!it.display,
                throwOnError: true,
                strict: false,
                // SECURITY (do not remove): trust:false makes KaTeX REJECT \href, \url,
                // \includegraphics, \htmlData etc. The TeX here is untrusted page/markdown
                // content; with trust:true those commands would emit MathML with external
                // refs that weasyprint then fetches (SSRF / data exfiltration). Pinned
                // explicitly rather than relying on the library default.
                trust: false,
            });
            return { mathml: html.replace(ANNOTATION, "") };
        } catch (e) {
            return { error: String((e && e.message) || e) };
        }
    });
    process.stdout.write(JSON.stringify(out));
});
