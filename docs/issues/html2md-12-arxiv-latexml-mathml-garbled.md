---
id: HTML2MD-12
type: known-issue
status: fixed
opened_at: 2026-07-09
resolved_at: 2026-07-09
resolved_by: TASK 028
category: correctness
severity: SEV-2
component: html
slug: html2md-12-arxiv-latexml-mathml-garbled
---

# HTML2MD-12 — arXiv/LaTeXML MathML (`<math alttext>`) came out as garbled glyphs — RESOLVED (TASK 028, 2026-07-09)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** ✅ RESOLVED (TASK 028; delete this entry when the fix commits). **Was:** every formula
on an arXiv `/html/` (LaTeXML/ar5iv) page — 328 in the reference paper — rendered as interleaved
presentation-MathML Unicode glyphs + the markdown-escaped `<annotation>` TeX, undelimited and
unrenderable (`wt′∑i=1L…\\sum\_{i=1}^{L}…`). Root cause (found by a 5-agent cross-skill math audit):
the html skill's only math rule (`htmlMath`) matches Pandoc `<span class="math inline|display">`,
never a MathML `<math>` node, so turndown dumped the subtree's `textContent`; `_normalize_math`
then no-op'd (no `\(`/`\[`), and `summarizing-meetings` R-7 couldn't help (it presumes an intact,
delimited TeX body html had already destroyed). **Fix (one html-owned file,
`skills/html/scripts/html_convert.js`, NOT a replication unit):** a new `htmlMathml` turndown rule
(filter `nodeName==="math"`, lowercase — MathML foreign elements aren't uppercased) lifts the clean
LaTeX that already ships in `alttext` (fallback: the `<annotation encoding="application/x-tex">`
child, exact-match) and emits `$…$` / single-line `$$…$$` (display keyed on `display="block"`)
**directly** — bypassing `_normalize_math`'s `_looks_like_math` display gate and its escaping, since
turndown does not re-escape a rule's raw return. Reuses the existing normalizers (unchanged) and a
shared `_mathTex` helper; the pre-existing `htmlLatexmlListing` rule (arXiv Algorithm blocks) routes
through the same helper so math inside code listings is clean too. Two adversarial-review hardenings:
(a) `|`/`\|` in math are pre-mapped to pipe-free `\vert`/`\Vert` so the GFM table-cell escaper
(display equations live in `<table>` cells) cannot corrupt norm/abs/conditional bars into `\|`
(KaTeX line-break); (b) presentation-only MathML with no recoverable TeX (hand-authored
Wikipedia/MDN) keeps the default glyph rendering rather than vanishing silently. **Do-not:** put the
rule in `web_clean/preprocess.py` (pdf-mastered gate; pdf may want MathML retained) or
`html2md_core.js` (docx-mastered); expand R-7 (can't reach the direct `.md`, works on destroyed
input); build a presentation-MathML→LaTeX glyph parser (lift `alttext`). **Also (R6):** arXiv **Algorithm/pseudocode** blocks (`ltx_listing` carrying inline `<math>`) used to
be fenced as ``` code, where `$…$` shows as literal LaTeX; the `htmlLatexmlListing` rule now branches
on inline-`<math>` presence and renders pseudocode as text (`$…$` math + `**bold**` keywords + hard
line breaks, no fence), while math-free real-code listings stay fenced. **vdd-multi hardening
round (2026-07-09, 3 parallel critics: logic/security/performance):** (a) the pipe remap in (a)
above turned out to be over-broad — it corrupted `\begin{array}{c|c}` column specs (KaTeX's
column parser accepts only `l c r | :`; `\vert` throws) — it is now **cell-gated**
(`_texPipesForCell` runs only in table-cell context, detected via a `_cellDepth` re-entrancy flag
around every cell innerHTML re-conversion + a `<td>/<th>` ancestor walk) and **exempts**
`\begin{array|darray|tabular}{…}` preambles; outside cells pipes pass through verbatim; (b)
display math OUTSIDE a cell is now blank-line-wrapped `$$\n…\n$$` (same shape as `htmlMath`),
single-line only inside cells; (c) **`$`-breakout injection closed** (shared `_dollarSafe`,
hardened across BOTH vdd-multi review iterations): every `$` in lifted TeX is made escaped, on
BOTH the MathML rule AND the sibling Pandoc `htmlMath` rule (identical channel). The neutralizer
is **parity-aware** (`(\\*)\$` — a naive `/\\?\$/g` was a no-op on an EVEN backslash run like
`\\$`, leaving the `$` live) and guards a **trailing odd-backslash** run (which would escape the
rule's own abutting closing delimiter, leaving the span unterminated) with a TeX-insignificant
space; NEL (U+0085, not matched by JS `\s`) is folded into the whitespace collapse. So a crafted
`alttext="x$ ![](evil) $y"` — or any backslash-parity variant — can no longer terminate the
`$…$`/`$$…$$` wrapper and inject a live Markdown exfil beacon. Two further adversarial
iterations closed a boundary regression (the cell pipe-map's trailing `.trim()` stripped the
guard space → re-applied via `_boundaryGuard`) and gave `htmlMath` the same interior-whitespace
collapse as `_mathTex` (an interior blank line would otherwise split the inline span into a new
paragraph, orphaning the opening `$`). Verified by a whole-document escaped-aware oracle over
15+ attack vectors — all beacons stay inside a math span; (d) `acquire.py` `_CTRL_CHAR_STRIP`
extended to C1 controls (U+0080–9F, 8-bit CSI), `_looks_like_image` accepts JP2 + extra HEIC
brands + SVG-with-`<foreignObject>` (rejects only when `<html` precedes `<svg`). Residual
honest-scope (documented, accepted): array-with-rules inside a GFM cell is unrepresentable
(no pipe-free column-rule spelling exists); presentation-only MathML (MathJax v3 assistive MML,
hand-authored MDN) has no TeX to lift → glyph fallback (rebuilding TeX from presentation MathML
is an explicit non-goal); LaTeXML algorithm indentation is pt-width-encoded → flush-left.
**Verification:** 13 regression tests (`test_convert.py::test_mathml_*`,
`test_pseudocode_*`, `test_ltx_listing_*`) + full suite (293) + e2e diff-gate + `validate_skill`
green; live dogfood on the reference paper → **all 328 formulas strict-KaTeX-valid** (validated
with the pdf skill's bundled KaTeX; zero `\|` inside any math span), including the 2 Algorithm
blocks; a non-arXiv universal fixture (W3C alttext / MediaWiki annotation-only / display-block /
presentation-only / pipes-in-cell / Pandoc span / MathJax-v3 container / zero-width garbage)
converts 8/8 with byte-identical re-runs. RTM:
[`docs/tasks/task-028-html-mathml-to-latex.md`](../tasks/task-028-html-mathml-to-latex.md).
