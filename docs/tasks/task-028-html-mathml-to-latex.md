# TASK 028 — `html`: convert arXiv/LaTeXML MathML (`<math alttext>`) to clean `$…$`/`$$…$$`

**Status:** ✅ COMPLETE (VDD — adversarial review converged 2026-07-09; 2 MED + 2 LOW fixed).
**Skill:** `html` (Proprietary). **Mode:** VDD (adversarial gate).
**Origin:** dogfood on `arxiv.org/abs/2510.08369` — all math came out as interleaved
Unicode-glyph + double-escaped-TeX garble. Root cause + fix location established by the
5-agent **cross-skill math-handling audit** (2026-07-09, high confidence).

---

## 0. Meta
- **Task ID:** 028 · **Slug:** `html-mathml-to-latex` · **Date:** 2026-07-09
- **Driver (RU):** «реализуй эту функциональность» (implement the MathML→`$` rule).
- **Affected file:** `skills/html/scripts/html_convert.js` — **html-authored, NOT a
  replication unit** (no docx/pdf/office gate; single-file change).

## 1. Problem

arXiv `/html/` (LaTeXML/ar5iv) renders every formula as
`<math class="ltx_Math" alttext="<clean LaTeX>" display="inline|block"> …presentation MathML… </math>`
(328 in the reference paper; **all** carry `alttext`, 314 inline / 11 block). The html skill's
**only** math rule (`htmlMath`, [html_convert.js:166](../skills/html/scripts/html_convert.js#L166))
matches **only** `<span|div class="math inline|display">` (Pandoc/MathJax), so a `<math>` node
matches nothing → turndown recurses and dumps the concatenated descendant text (flattened
presentation glyphs + the markdown-escaped `<annotation>` TeX), undelimited. `_normalize_math`
then no-ops (no `\(`/`\[` present). Neither downstream consumer recovers it: the **direct** html
`.md` has no downstream at all; the **wiki-import** path's `summarizing-meetings` R-7 presumes an
intact, already-delimited TeX body that html destroyed at convert time.

**Audit conclusion:** one missing turndown rule; the clean TeX is sitting in `alttext` (fallback:
the `<annotation encoding="application/x-tex">` child) ready to lift verbatim.

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | Verification |
|----|-------------|--------------|
| **R1** | Add a turndown DOM rule `htmlMathml` in `html_convert.js` filtering `nodeName === "math"` (**lowercase** — MathML foreign elements are not uppercased like HTML). Lift `alttext`; if absent, the `<annotation encoding="application/x-tex">` descendant's `textContent`. | `test_mathml_alttext_to_dollar`, `test_mathml_annotation_fallback` |
| **R2** | Emit `$…$` (inline) / `$$…$$` (display, keyed on `display="block"`) **directly** — NOT `\(…\)`/`\[…\]`: (a) a `<math>` IS math, so it must bypass `_normalize_math`'s `_looks_like_math` display gate ([md_clean.py:122](../skills/html/scripts/html2md/md_clean.py#L122)) which could silently drop a real display equation; (b) turndown does not re-escape a rule's raw return, so the lifted TeX lands **unescaped** (no `_MD_UNESCAPE` needed). | `test_mathml_alttext_to_dollar` (asserts no `\_`) |
| **R3** | Display math is emitted **context-aware** (vdd-multi 2026-07-09): INSIDE a GFM table cell → single-line `$$TeX$$` (the 11 arXiv display equations live inside `<table>` equation layouts, where the newline-wrapped block form would break the GFM row); OUTSIDE a cell → blank-line-wrapped block `$$\n…\n$$` (same shape as the `htmlMath` sibling). Cell context is detected via a `_cellDepth` re-entrancy flag around every cell innerHTML re-conversion (the core re-parses cells, severing `<td>` ancestry) + a DOM-ancestor walk. | `test_mathml_display_in_table_cell`, `test_mathml_alttext_to_dollar` (block form) |
| **R4** | **No glyph leak / no garble:** the presentation-MathML Unicode descendants must NOT appear in output; a `<math>` with neither `alttext` nor an x-tex annotation returns `""` (dropped, no stray `$$`, no glyph dump). | `test_mathml_alttext_to_dollar` (no `αk`), `test_mathml_empty_dropped` |
| **R5** | **No regression + no scope creep:** `htmlMath` and `_normalize_math` and `summarizing-meetings` R-7 **unchanged**; do NOT touch `web_clean/preprocess.py` (pdf-mastered) or `html2md_core.js` (docx-mastered). Full html suite + e2e diff-gate + `validate_skill` green; real arXiv dogfood yields clean, KaTeX-renderable math. | full suite + validator + dogfood |
| **R6** | **Algorithm/pseudocode listings render math.** arXiv Algorithm environments are `<div class="ltx_listing">` carrying inline `<math>` + `**bold**` keywords (Input/Output/while/return) — NOT real code. The pre-existing `htmlLatexmlListing` rule fenced them as ``` code, where `$…$` can't render (raw LaTeX shows literally). Now the rule **branches on inline `<math>` presence** (`_descHasMath`): a math-bearing listing renders as TEXT via `_algoLine` — `<math>`→`$…$`, `ltx_font_bold`→`**…**`, gutter dropped, adjacent `$…$$…$` runs separated, lines joined with two-space hard breaks (md_clean-safe), NO fence — so KaTeX renders it; a math-free listing stays a fenced code block (`_listingText`, whose dead `<math>` branch was removed — unreachable by the gate). `_mathTex` is the shared TeX-lifter. Honest scope: LaTeXML algorithmic nesting is encoded as `ltx_minipage` pt-widths + SVG scope rules (no text indent exists), so loop bodies render flush-left. | `test_pseudocode_listing_renders_math`, `test_ltx_listing_code_no_math_stays_fenced`, `test_pseudocode_adjacent_math_separated` |
| **R7** | **vdd-multi hardening rounds (2026-07-09; 3-critic adversarial review of TASK 027+028, TWO iterations).** (a) *Pipe remap is cell-gated*: the previously-unconditional `\|`→`\Vert`/`|`→`\vert` corrupted `\begin{array}{c|c}` column specs (KaTeX column parser accepts only `l c r | :`) — now `_texPipesForCell` runs ONLY in table-cell context and EXEMPTS `\begin{array|darray|tabular}{…}` preambles (array-with-rules inside a GFM cell stays unrepresentable — honest scope). (b) *`$`-breakout neutralized* (shared `_dollarSafe`, hardened over 2 review iterations): every `$` in lifted TeX is made escaped and applied to BOTH the MathML rule and the sibling Pandoc `htmlMath` rule (same injection channel). Parity-aware (`(\\*)\$` → odd backslash run, identity on honest `\$`) so an EVEN backslash run (`\\$`) can't leave a live `$`; plus a trailing-odd-backslash guard (a space) so lifted TeX can't escape its own ABUTTING closing delimiter. NEL (U+0085, not matched by JS `\s`) folded into the whitespace collapse. A crafted `alttext`/math-span thus cannot terminate the `$…$` wrapper and inject live Markdown (exfil beacon). Iteration 3 fixed a regression where the cell pipe-map's trailing `.trim()` stripped the boundary guard (re-applied via `_boundaryGuard`); iteration 4 gave `htmlMath` the same interior-whitespace collapse (incl. NEL U+0085) as `_mathTex` so an interior blank line can't split the span into a paragraph and orphan the opening `$`. Verified by a whole-document escaped-aware oracle over 15+ attack vectors (all beacons stay inside a math span). (c) *acquire.py*: `_CTRL_CHAR_STRIP` extended to C1 controls (U+0080–9F); `_looks_like_image` accepts JP2 + extra HEIC brands + SVG-with-`<foreignObject>` (reject only when `<html` precedes `<svg`). Perf critic: bikeshedding-only (all paths linear). | `test_mathml_array_colspec_not_corrupted_outside_table`, `test_mathml_array_preamble_exempt_from_cell_pipe_map`, `test_mathml_dollar_injection_neutralized`, `test_looks_like_image_matrix` (extended), `test_redact_strips_control_chars` (C1) |

## 3. Scope / non-goals
- **In scope:** one DOM rule + a `_findXtexAnnotation` helper in `html_convert.js`, + tests.
- **Out of scope (audit `do_not`):** editing the pdf-mastered `web_clean/preprocess.py` or
  docx-mastered `html2md_core.js`; expanding `summarizing-meetings` R-7 (can't reach the direct
  `.md`, operates on already-destroyed input); building a presentation-MathML→LaTeX glyph parser
  (lift `alttext` instead); pdf/docx math code (wrong direction, TeX→MathML).

## 4. Definition of Done
1. R1–R5 verifications green (new tests + full suite).
2. `validate_skill.py skills/html` exit 0; e2e `diff -q` gate green.
3. Real dogfood: `arxiv.org/abs/2510.08369` (or the webarchive) → inline `$…$` + display
   `$$…$$` with single-backslash TeX, no Unicode-glyph interleaving.
4. Adversarial review converges (0 CRITICAL, no legitimate findings).
5. `docs/KNOWN_ISSUES.md` gains a resolved **HTML2MD-12** note; TASK 028 archived.
