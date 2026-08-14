# TASK 031 — docx: Math support (`$…$` / `$$…$$`) in `md2docx.js`

**Status:** DONE 2026-08-14. All of §4's A1–A11 pass; A9 (manual gate, the reference document)
converts to 328 native `<m:oMath>` objects, `office/validate.py` → `OK`, spot-checked via
`preview.py`. Every phase gate (task-reviewer, architecture-reviewer, plan-reviewer) returned
WARNING on its first pass with concrete, real findings — a genuine correctness bug (a math
formula inside a remote-image `TextRun` fallback was assigned to the wrong safety-net branch
in the first RTM draft), broken cross-references, and acceptance-criteria commands that don't
do what they claim (`grep -c` counting lines, not occurrences) — all fixed before proceeding.
One additional defect surfaced only at the A9 manual gate, after all three reviews: the
Pandoc equation-table shape clipped every non-trivial formula to 1/4 of the page width under
an equal 4-column split; fixed with an asymmetric-width heuristic, regression-locked in
`test_md2docx_math.py`.
**Skill:** `docx` (**Proprietary** — per-skill `LICENSE`/`NOTICE`; CLAUDE.md §3).
**Mode:** Standard pipeline (`01-04`), not VDD — no `/vdd` invoked for this task.

---

## 0. Meta Information

- **Task ID:** 031 · **Slug:** `docx-math-support` · **Date:** 2026-08-14
- **Driver (RU):** «реализуй [docx-11] и для примера используй документ для конвертации в docx
  `tmp15/Направляемая звёздообразная маскированная диффузия.md`»
- **Backlog origin:** [`docs/office-skills-backlog.md`](../office-skills-backlog.md) row `docx-11`
  — Effort L, Value M. Deferred out of TASK 030 (spec §8 R-3) as its own task; TASK 030 §5
  records the deferral: *"Math `$…$` → OMML/PNG (spec R-3) — Deferred… Filed as docx-11"*.
- **Affected code surface:** `skills/docx/` only — new `scripts/_math_lib.js`, modified
  `scripts/md2docx.js`, modified `scripts/package.json`/`package-lock.json` (two new runtime
  deps), new `scripts/tests/test_md2docx_math.py`, new fixture `examples/fixture-math.md`,
  `SKILL.md`, `scripts/.AGENTS.md`, `scripts/tests/test_e2e.sh`, root
  `THIRD_PARTY_NOTICES.md`. Outside the code surface: `docs/ARCHITECTURE.md` +
  `docs/architectures/architecture-011-docx-skill.md` (script table, deps, command list),
  `docs/office-skills-backlog.md` row `docx-11` (status update on close-out).
- **Replication units touched:** none. `scripts/office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`, `html2md_core.js`, `_venv_bootstrap.py` are all untouched —
  `md2docx.js` is not a master of anything (same finding as TASK 030). No `diff -q` gate applies.
- **Reference/acceptance document (read-only, outside the repo tree):**
  `tmp15/Направляемая звёздообразная маскированная диффузия.md` — a Russian-language ML paper,
  659 lines, **328 formula occurrences** measured by the extraction regex named in §1 (315
  inline `$…$`, 13 display `$$…$$`; 197 distinct `(tex, display)` pairs after R2(a)'s dedup —
  most repeated occurrences are inline notation like `$\mathbf{x}_{t}$`, no display formula
  repeats). Every display equation sits inside its own single-row, 4-column GFM table
  (`|  | $$…$$ |  | (N) |`) — the Pandoc LaTeX→Markdown equation-with-number convention. No
  fenced code blocks in the document. Used as both the design-validation corpus (§1) and the
  manual acceptance gate (A9).

## 1. Problem Description

`md2docx.js` has no math support: `grep -i "katex\|mathml" skills/docx/scripts/md2docx.js` = 0
hits. `$…$` and `$$…$$` reach the output as literal text — `marked` has no math extension
loaded, so `$x^2$` lexes as an ordinary `text` token and is written to the `.docx` byte-for-byte
as typed. The `pdf` skill solved the same problem for its own renderer via a pre-render pass
(`katex_render.js` + `md2pdf.py::preprocess_math`): batch-render `$…$`/`$$…$$` to MathML via a
bundled KaTeX, which weasyprint then typesets natively. `docx` has no HTML/CSS rendering layer
to hand MathML to — its output is OOXML built directly through the `docx` npm library.

**Feasibility spike (done during analysis, not reused as shipped code).** Ran the full
candidate pipeline — KaTeX (`output:"mathml"`) → `mathml2omml` (npm, pure JS, zero deps) →
`docx`'s `ImportedXmlComponent.fromXmlString()` pushed directly into `Paragraph.children` — end
to end:

- Extracted all 328 formula occurrences (197 unique) from the reference document with a JS
  port of `pdf`'s `_MATH_DISPLAY_RE`/`_MATH_INLINE_RE`/`_CODE_SPLIT_RE` regex trio (pandoc's
  currency-avoidance heuristic: opening `$` not followed by whitespace, closing `$` not
  preceded by whitespace, `\$` never a delimiter, code spans/fences excluded). **197/197
  unique formulas rendered without error**, zero `mathml2omml` warnings.
- A minimal two-formula `.docx` built this way passed `office/validate.py` (`OK`) and rendered
  correctly in a LibreOffice preview: real fractions, subscripts, an n-ary sum with limits,
  italic math variables — genuine editable Word math objects, not a raster. (Two dot/mid-pipe
  operators showed as missing-glyph boxes in the local LibreOffice preview because this Mac has
  no "Cambria Math" font installed — a local rendering artifact, not an OMML defect; consistent
  with the existing [[project-visual-goldens-linux-baseline]] convention that local previews are
  not the correctness bar.)

This resolves the backlog's "two honest options" (OMML via the `docx` library, or a PNG raster)
in favour of **OMML**: it is proven end-to-end on the actual acceptance document, produces
real editable Word-native math (searchable, stylable, no reflow/DPI concerns a raster would
carry), and needs no new rendering surface — the docx skill already depends on `docx`-js.

## 2. Goal and Scope

**Goal.** `$…$` and `$$…$$` in a Markdown source convert to native OOXML math objects
(`<m:oMath>`) in the output `.docx`, indistinguishable in Word from a formula authored with
Word's own equation editor — inline math stays inline, display math is visually distinguished
from surrounding prose.

**In scope:** inline `$…$` and display `$$…$$` math wherever `md2docx.js` currently builds
inline runs — paragraphs, headings, list items, blockquotes, table cells (the reference
document's actual shape: every display equation lives inside a table cell). Failure handling
(`--strict-math` / degrade-and-warn) and a `--no-math` opt-out, mirroring `pdf`'s
`--strict-math`/`--no-math` for a consistent user-facing contract across the two skills (no code
shared — two independent implementations, one on each side of a different rendering engine).

**Out of scope** (stated so the boundary is checkable, not aspirational):

- Word-native automatic equation numbering (`m:oMathPara` equation-array tab stops / `SEQ`
  fields). The reference document already carries its own numbers as ordinary text in an
  adjacent table cell (`(1)`, `(2)`, …) — those are outside the `$$…$$` delimiters entirely, so
  they convert today via the *existing* table path and are not touched or regenerated by this
  task. No requirement below manufactures new numbering.
- Math nested inside `**bold**`, `*italic*`, or `[link](...)` spans. `parseInlineText`'s
  strong/em/link branches gain the SAME sentinel-splitting treatment as the plain-text branch
  (R4(b)) so a formula in that position still renders as a real (unstyled) math object — it is
  **not** silently dropped or leaked as raw sentinel bytes — but it does not inherit the
  bold/italic styling. Documented, not aspirational: OOXML math runs do not take paragraph-level
  bold/italic the way `TextRun` does, and doing this properly means restyling individual
  `<m:r><m:rPr>` nodes inside the returned OMML, which is deferred.
  [[docx-11-math-followups]]
- Math inside a **locally-resolved** image's alt text (`![$x$](local.png)`) renders as the
  **original literal** `$x$` string, never a math object — `buildImageRun()`'s `ImageRun.altText`
  fields are plain strings, not run children, so there is nothing to splice a math object into
  (R5). This does NOT apply to a remote/data-URL image reference, which takes the ordinary
  `TextRun` fallback path and therefore gets the R4(b) treatment like any other text — a formula
  in THAT alt text renders as a real math object.
- `--obsidian` interaction is architecturally independent (obsidian2md.js never touches `$`,
  confirmed by grep — R9's rules target `==`, `%%`, `#tag`, task checkboxes only) but is not
  exercised by a combined fixture in this task; noted as a fast-follow gap, not a defect.
  [[docx-11-math-followups]]
- PNG raster fallback path. Rejected outright per §1 — OMML is strictly better once proven
  feasible, and it was.

<!-- contract:rtm -->
## 3. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| R1 | **New module** `scripts/_math_lib.js` — pre-lexer math extraction. Runs on the raw Markdown string BEFORE `marked.lexer()`, so substitution never interacts with CommonMark's `_`/`*` emphasis-pairing rules (a real risk: two adjacent `$x_i$ … $y_j$` formulas each carrying one literal underscore would otherwise present as two candidate emphasis markers to `marked`'s inline lexer and pair across unrelated prose). | YES | (a) `_MATH_DISPLAY_RE`/`_MATH_INLINE_RE`/`_CODE_SPLIT_RE` — direct JS port of `pdf/md2pdf.py`'s regex trio (not shared code — no replication unit, two independent implementations either side of a different renderer); (b) fenced (```` ``` ```` / `~~~`) and inline `` ` `` code spans excluded from math scanning before either regex runs; (c) `\$` (escaped) is never a delimiter; (d) a bare `$5` / `$10` (no closing `$` before whitespace) is not math — the pandoc heuristic; (e) `$$` scanned before `$` per segment, with matched display spans stripped from the segment before the inline scan runs, so a `$$…$$` block is never double-counted as two `$…$` |
| R2 | **Sentinel substitution.** Each matched span → `<N>` (Private-Use-Area markers, N = decimal index into a per-call `formulas[]` registry storing `{tex, raw, display}`). Any PRE-EXISTING U+E000/U+E001 byte in the source is stripped first — defence in depth, mirroring `_obsidian_lib.js`'s R10 control-character stripping precedent, in case a document legitimately carries PUA bytes (icon fonts sometimes do). | YES | (a) one registry entry per **unique** `(tex, display)` pair — repeated formulas render once; (b) sentinel carries no display/inline distinction of its own — that lives on `formulas[N].display`, looked up at splice time; (c) a `$-` dense document (>10000 `$` chars, mirroring `pdf`'s `_MATH_DOLLAR_CAP`) skips math preprocessing entirely with a stderr warning — DoS guard on the O(n²) inline scan, before KaTeX is ever invoked |
| R3 | **Batch render**, in-process (no subprocess — `md2docx.js` is already Node, unlike `pdf`'s Python↔Node bridge). KaTeX (`output:"mathml"`, `trust:false` — SECURITY, same reasoning as `pdf/katex_render.js`: untrusted document content must not reach `\href`/`\includegraphics`/`\htmlData`) → strip the `<annotation>` a11y node → extract the bare `<math>…</math>` (KaTeX wraps it in `<span class="katex">`, which `mathml2omml` cannot parse — measured directly in the feasibility spike, §1) → `mathml2omml.mml2omml()` → OMML string cached on `formulas[N].omml`. | YES | (a) one formula render failure never aborts the batch — caught per-formula, recorded as `formulas[N].error`; (b) `--strict-math` (new flag): any render failure → `process.exit(1)` with the formula's TeX in the message, mirroring `pdf`'s `--strict-math`; (c) without `--strict-math`: failed formulas fall back to their **original literal** `$…$`/`$$…$$` text (R2's `raw` field) at splice time, plus one stderr warning per failure — never a silent drop; (d) `--no-math` (new flag): skip R1–R4 entirely, byte-identical to pre-feature behaviour (regression lock, A7) |
| R4 | **Splice into paragraph children.** `ImportedXmlComponent.fromXmlString(formulas[N].omml)` — a **fresh instance per occurrence** (never reused across two splice points: `docx`-js composes its XML tree once at `Packer.toBuffer()`, and re-parsing a short XML string per occurrence is measured-cheap against reusing one object of uncertain aliasing safety). | YES | (a) `splitMathSentinels(text) → Array<{type:'text',text} \| {type:'math', index}>` — a small tokeniser used everywhere `parseInlineText` currently builds a `TextRun` from decoded text; (b) applied to **every** run-bearing branch: text/escape/html (including its `<br>` sub-split — each `<br>`-separated part is itself run through the splitter before its `TextRun`/math run is pushed), strong, em, link, **and** the `image` token's remote/data-URL fallback (`md2docx.js:361`, `runs.push(new TextRun({text: decodeEntities(t.text) \|\| t.href, …}))`) — that is a `TextRun`, not `ImageRun.altText`, so it is a splice-capable context like any other and takes the SAME treatment, not `restoreLiteral` (R5 corrects an earlier draft that assigned this branch to R5 by mistake); (c) **not** applied to `codespan` (R1(b) guarantees no sentinel can reach it); (d) a standalone paragraph/table-cell whose entire trimmed text is exactly one sentinel referencing a **display** formula gets a dedicated `Paragraph` (`alignment: CENTER`) instead of folding into the ambient paragraph's default-left flow — covers the common "$$…$$ alone between blank lines" shape; mixed-content display math (rare) still renders, just inline and left-flowing, not centered — documented degradation, not a crash; (e) **found during A9's manual reference-document run, not originally scoped:** a 4-column table whose 1st/3rd cells are blank and 2nd holds a formula (the Pandoc `|  | $$…$$ |  | (N) |` equation-array convention this task's own reference document uses throughout) gets asymmetric column widths (3%/80%/3%/14% of `contentWidthDxa`) instead of an equal 4-way split — measured on the reference document: an equal split left the formula column ~1/4 of the page width, clipping every non-trivial equation (verified via `preview.py`, fixed, re-verified). Applies to any table matching the shape, not gated on `--obsidian` or on the presence of math specifically |
| R5 | **Sentinel safety net.** No PUA sentinel byte may reach the emitted `.docx` under ANY code path, matching TASK 030's "exit 0 guarantees nothing" retirement in [[project-run-feedback-rollout-state\|the project's existing quality bar]]. | YES | (a) `restoreLiteral(text, formulas)` — replaces a sentinel with `formulas[N].raw` (the original `$…$`/`$$…$$` source text). Its **only** call sites are the three plain-string fields `buildImageRun()` passes to `ImageRun({altText: {title, description, name}})` (`md2docx.js:324-328`, the LOCAL-image path — a real `ImageRun` object has no run children to splice a math object into) and any other plain-string, non-run sink added later. Every run-bearing sink is R4(b)'s job, not this one; (b) regression test asserts zero U+E000/U+E001 bytes anywhere in `word/document.xml` of every fixture output, math-bearing or not — scoped to `document.xml` because `preprocessMath()`'s output never reaches any other OOXML part: headers/footers are literal `--header`/`--footer` CLI strings, never Markdown-body text |
| R6 | **`md2docx.js` wiring.** | YES | (a) `preprocessMath()` runs on `markdown` — the variable produced immediately AFTER the frontmatter-strip regex at `md2docx.js:154`, so math scanning never has to reason about YAML frontmatter content — and AFTER `--obsidian` pre-processing (obsidian2md.js never touches `$`, confirmed by grep — no ordering conflict), BEFORE `marked.lexer()`; (b) new flags `--no-math` / `--strict-math` added to `VALUE_FLAGS`/boolean-flag handling alongside the existing `--landscape`; (c) USAGE string updated; (d) zero behaviour change for a document with no `$` (R2's dense-doc guard and R1's extraction both short-circuit on `text.indexOf('$') === -1`) |
| R7 | **Dependencies.** | YES | (a) `katex` (MIT) and `mathml2omml` (LGPL-3.0-or-later) added to `skills/docx/scripts/package.json` — **docx's own copy**, not shared/symlinked with `pdf`'s existing `katex` install, per CLAUDE.md's "Независимость скиллов" (each skill installable/runnable in isolation, including as a packaged `.skill` archive); (b) `THIRD_PARTY_NOTICES.md` gains a `mathml2omml` row and the existing `katex` row's "Used by" column gains `docx/_math_lib.js`; (c) LGPL-3.0 precedent for an npm runtime dependency of a Proprietary skill already exists in this repo (FFmpeg, LGPL-2.1/GPL-2.0, `transcript-fetcher`) — used here the same way `docx` already shells out to LibreOffice (LGPLv3) via `_soffice.py`: as an external, dynamically-loaded component, never statically linked/modified |
| R8 | **Fixture + tests.** | YES | (a) `examples/fixture-math.md` — small, hand-written: inline math, display math on its own paragraph, display math inside a 4-column equation table (mirrors the reference document's actual shape), a formula inside `**bold**` (R4(b) coverage), an escaped `\$5` and a bare `$5` (R1(c)/(d) negative cases), a formula inside a fenced code block (must survive byte-identical — R1(b)), one intentionally-malformed TeX (`--strict-math` / degrade-and-warn coverage); (b) `scripts/tests/test_md2docx_math.py` in the style of `test_md2docx_pagesize.py`, covering R1–R6 and R5's sentinel-leak regression; (c) `scripts/tests/test_e2e.sh` gains the new suite; (d) `validate_skill.py skills/docx` exits 0 |
| R9 | **Documentation.** | YES | (a) `SKILL.md` §2 Capabilities, §4 Script Contract (`--no-math`/`--strict-math`), §6 Validation Evidence (one local-verification line, house pattern — the reference-document run, A9); (b) §1 Red Flags gains an entry naming the pre-feature silent-loss behaviour (`$x^2$` → literal text, exit 0); (c) `scripts/.AGENTS.md` documents `_math_lib.js`; (d) `docs/office-skills-backlog.md` row `docx-11` marked done on close-out, mirroring the `docx-10`/`docx-6` rows' convention |

### 3.1 Requirement → validation map

| RTM ID | Validated by |
|---|---|
| R1 | A1, A2, A11 (feasibility spike §1 is design-time evidence, not shipped-code evidence) |
| R2 | A1, A5, A11 |
| R3 | A1, A3, A6 |
| R4 | A1, A4, A6 |
| R5 | A5 |
| R6 | A2, A7, A8 |
| R7 | A10 |
| R8 | A1–A6, A11 collectively; A10 |
| R9 | A10 (`validate_skill.py` reads the documented structure) |

## 4. Acceptance Criteria

`<fixture>` = `examples/fixture-math.md` (R8a). `<ref>` = the reference document named in §0.
Where a check reads XML content, it means the Python test's extracted `word/document.xml`
string (house pattern: `test_md2docx_pagesize.py`'s `self._docxml(out)` helper), not a shell
pipeline over the packaged `.docx` — a `.docx` is a zip with per-entry timestamps, so comparing
raw package bytes across two runs is neither meaningful nor stable.

| # | Check | Expectation |
|---|---|---|
| A1 | `node scripts/md2docx.js <fixture> out.docx` | exit 0; `office/validate.py out.docx` → `OK` |
| A2 | count of `<m:oMath` occurrences in `word/document.xml` (`grep -o "<m:oMath" \| wc -l`, or the Python test's own substring count — `grep -c` is wrong here, it counts matching *lines* and `docx`-js emits `document.xml` as one unbroken line) | ≥ 4 — one per math-bearing fixture case (inline, display-paragraph, display-in-table, bold-wrapped) |
| A3 | fixture's intentionally-malformed TeX case, default flags | exit 0, stderr warning naming the formula, literal `$…$` text present in `word/document.xml` for that one case only |
| A4 | same malformed case, `--strict-math` | exit 1, message names the failing TeX |
| A5 | Python test decodes `word/document.xml` and asserts neither `"\ue000"` nor `"\ue001"` (the sentinel markers) occurs anywhere in it, for every fixture output, math-bearing or not | 0 occurrences — R5's sentinel-leak regression |
| A6 | fixture's fenced-code-block formula (`` ```\n$x$\n``` ``) | `word/document.xml` contains the literal text `$x$`, zero `<m:oMath` generated for it |
| A7 | `--no-math` on `<fixture>` | `word/document.xml` contains the literal `$…$`/`$$…$$` source text for every fixture formula, and zero `<m:oMath` occurrences anywhere (regression lock — the exact pre-TASK-031 shape) |
| A8 | a `$`-free fixture, two ways: (i) unit-level — `_math_lib.preprocessMath(text)` returns `formulas: []` and `text` unchanged (`===`, not just `==`); (ii) E2E — the SAME `$`-free fixture's `word/document.xml` is identical whether run with default flags or `--no-math` (proves the math code path is a true no-op on such input; sidesteps comparing against "a build from before this task", which is a temporal claim with no fixed target once this task merges) | (i) and (ii) both hold |
| A9 | `<ref>` via `node scripts/md2docx.js <ref> out.docx --page-size A4` — **manual/local gate, NOT wired into `test_e2e.sh`** (the reference file lives outside the repo, `tmp15/` is a scratch path) | exit 0; `<m:oMath` occurrence count (A2's counting method) ≥ 300 (formula count is corpus-derived — §0 measured 328 occurrences — not a hard literal); `office/validate.py` → `OK`; visual spot-check via `preview.py` on at least the first page |
| A10 | `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx` | exit 0 |
| A11 | fixture's escaped `\$5` and bare `$5` cases (R1(c)/(d) — the currency-avoidance negative cases R8a already puts in the fixture but which no earlier row exercised) | both remain literal `$5` text in `word/document.xml`; zero `<m:oMath` generated for either |

## 5. Rejected / Deferred

| Item | Decision | Reason |
|---|---|---|
| PNG raster fallback (backlog's second option) | **Rejected** | §1 feasibility spike proved OMML end-to-end on the actual acceptance document: 197/197 unique formulas (328 occurrences) rendered with zero warnings. A raster is strictly worse once OMML is known to work: not editable, not searchable, DPI/reflow concerns, and it still needs a rendering surface this skill does not otherwise have (no headless-Chrome/weasyprint equivalent already wired for docx). |
| Word-native equation numbering (`m:oMathPara` + `SEQ` fields) | **Deferred** | Not needed for the acceptance document — its numbers are already plain text outside the `$$…$$` delimiters and convert today via the existing table path. Filed as a follow-up if a future document needs Word to *generate* numbers rather than preserve authored ones. [[docx-11-math-followups]] |
| Math inside `**bold**`/`*italic*` inheriting the surrounding style | **Deferred** | Needs per-run `<m:rPr>` restyling inside returned OMML, not just wrapping. R4(b) already guarantees the formula still renders (unstyled) rather than being dropped, which closes the correctness gap; the cosmetic gap is a fast-follow. [[docx-11-math-followups]] |
| Sharing `_math_lib.js` logic with `pdf`'s `katex_render.js`/`preprocess_math` | **Rejected** | Different language (JS vs Python) and different output target (OMML vs MathML) — there is no common code to extract, only a shared *heuristic* (the regex trio), which is intentionally re-implemented rather than imported, matching CLAUDE.md's replication-unit boundaries (`md2docx.js` is not a master of anything). |

## 6. Open Questions

None blocking. One judgement call recorded here per `core-principles` §3:

- **Sentinel splitting extended to strong/em/link (R4(b)), not scoped out.** The obvious minimal
  cut was "math only in plain paragraph text, out of scope elsewhere" — but that leaves a
  silent-garbage-byte failure mode (raw PUA characters reaching the document) for any formula
  that happens to sit inside `**bold**` in someone's document, which is exactly the failure
  class TASK 030 exists to close for a different feature. Extending the splitter to every branch
  costs little and removes the failure mode entirely; only the styling-inheritance nicety is
  actually deferred (§5).
