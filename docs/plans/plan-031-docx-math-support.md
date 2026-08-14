# PLAN 031 — docx: Math support (`$…$` / `$$…$$`) in `md2docx.js`

**TASK:** [`docs/TASK.md`](../tasks/task-031-docx-math-support.md) (TASK 031, RTM R1–R9) · **Mode:** Standard pipeline · **Date:** 2026-08-14
**Strategy:** Stub-First (`tdd-stub-first`). Phase 1 lays the `_math_lib.js` skeleton, the
fixture, and a RED test suite; Phase 2 fills logic bead by bead; Phase 3 wires `md2docx.js`,
dependencies, and gates.

---

## 0. Bead map

| Bead | Kind | RTM IDs | Deliverable |
|---|---|---|---|
| 031-01 | STUB+TEST | R1, R8 | `_math_lib.js` skeleton, `examples/fixture-math.md`, RED suite |
| 031-02 | LOGIC | R1, R2 | Extraction regexes, code-span/fence exclusion, sentinel substitution, dedup registry, dense-doc guard |
| 031-03 | LOGIC | R3 | KaTeX → MathML → `mathml2omml` batch render, per-formula failure capture |
| 031-04 | LOGIC | R4, R5 | `splitMathSentinels` wired into every run-bearing branch of `parseInlineText`; `restoreLiteral` for the two `ImageRun.altText` sinks; display-paragraph centering |
| 031-05 | LOGIC | R6 | `md2docx.js` CLI wiring: `--no-math`/`--strict-math`, call-site ordering, USAGE |
| 031-06 | INTEGRATION | R7 | `katex` + `mathml2omml` deps, `package.json`/`package-lock.json`, `THIRD_PARTY_NOTICES.md` |
| 031-07 | INTEGRATION | R8, R9 | `test_e2e.sh` wiring, `validate_skill.py`, reference-document manual run (A9), `SKILL.md`/`.AGENTS.md`/backlog docs |

Every RTM ID appears at least once. The stubs in 031-01 do not import `katex`/`mathml2omml`
yet, so 031-01/02 run before either package is installed (pure regex/registry logic needs
neither). The real `npm install katex mathml2omml` happens at the start of 031-03, the first
step that actually calls KaTeX — 031-06 is the commit-time confirmation that the resulting
`package.json`/`package-lock.json`/`THIRD_PARTY_NOTICES.md` changes are in order, not a second
install.

---

## 1. Phase 1 — Stubs and a RED suite

### Step 031-01 [STUB+TEST] — skeleton, fixture, failing tests (R1, R8)

- [ ] R1 `skills/docx/scripts/_math_lib.js` — exported surface, every function a stub:
      `preprocessMath(text, opts) → {text, formulas}`, `splitMathSentinels(text, formulas)`,
      `restoreLiteral(text, formulas)`, plus module-level regex constants
      `MATH_DISPLAY_RE`/`MATH_INLINE_RE`/`CODE_SPLIT_RE`/`MATH_DOLLAR_CAP`/`SENTINEL_OPEN`/
      `SENTINEL_CLOSE`.
- [ ] R8(a) `skills/docx/examples/fixture-math.md` — inline math, display math alone on a
      paragraph, display math inside a 4-column equation table (mirrors the reference
      document's shape: `|  | $$…$$ |  | (N) |`), a formula inside `**bold**`, an escaped
      `\$5` and a bare `$5` (negative cases), a formula inside a fenced code block, one
      intentionally-malformed TeX string (e.g. an unclosed `\left(`).
- [ ] R8(b) `skills/docx/scripts/tests/test_md2docx_math.py` in the style of
      `test_md2docx_pagesize.py` — A1–A11 and every lettered sub-feature of R1–R6 as a named
      test, **all written and all failing on assertions** (stubs throw `Not implemented` or
      return empty) — not skipped, not commented out, not gated behind a skip decorator.
      Phase 2 turns each one GREEN in place as its logic lands; none is ever marked skip.

**Verification:** `node -e "require('./scripts/_math_lib.js')"` exits 0 (module loads); the
test suite runs and fails on assertions, not on import errors. A suite that errors on import
is not RED, it is broken.

---

## 2. Phase 2 — Logic

### Step 031-02 [LOGIC] — extraction, sentinel substitution, dedup, DoS guard (R1, R2)

- [ ] R1(a) port `_MATH_DISPLAY_RE`/`_MATH_INLINE_RE`/`_CODE_SPLIT_RE` from
      `pdf/md2pdf.py` into JS (lookbehind/lookahead syntax is a direct carry-over — Node's
      regex engine supports both).
- [ ] R1(b) split the input on `CODE_SPLIT_RE` first; scan for math only in the even-indexed
      (non-code) segments.
- [ ] R1(c)(d)(e) escaped-`$`, bare-`$5`, and display-before-inline ordering — direct
      consequences of the ported regex, verified by R8's negative-case fixture rows (A11).
- [ ] R2 strip any pre-existing U+E000/U+E001 byte from the input first; build the
      `formulas[]` registry keyed by unique `(tex, display)`; substitute each match with
      `<N>`.
- [ ] R2(c) `$` count > `MATH_DOLLAR_CAP` (10000) → return input unchanged plus a stderr
      warning, before any KaTeX call.
- [ ] The R1/R2 tests written in 031-01 turn GREEN.

### Step 031-03 [LOGIC] — KaTeX → MathML → OMML batch render (R3)

- [ ] `npm install katex mathml2omml --save` inside `skills/docx/scripts/` (bead 031-06's
      dependency work pulled forward here so this step can run for real — see §0 note).
- [ ] R3 for each unique registry entry: `katex.renderToString(tex, {output:"mathml",
      displayMode: display, throwOnError: true, strict: false, trust: false})`, strip
      `<annotation>`, extract the bare `<math>…</math>` (KaTeX wraps it in
      `<span class="katex">` — confirmed in the TASK §1 feasibility spike), pass to
      `mathml2omml.mml2omml()`, cache the result on `formulas[N].omml`.
- [ ] R3(a) wrap the per-formula render in try/catch; on throw, set `formulas[N].error` and
      continue the batch — never abort on one bad formula.
- [ ] R3(b) `--strict-math` plumbed as an option to `preprocessMath`; when set, the first
      `error` throws out of the batch with the offending TeX in the message.
- [ ] R3(c) without `--strict-math`: a failed formula's splice site (031-04) falls back to
      `formulas[N].raw`, plus one stderr warning per failed formula naming the TeX — never a
      silent drop (covered by A3).
- [ ] The R3 tests written in 031-01 turn GREEN.

### Step 031-04 [LOGIC] — splice into `md2docx.js`'s run builder (R4, R5)

- [ ] Add `ImportedXmlComponent` to the `require('docx')` destructure at `md2docx.js:8` (not
      currently imported — the whole point of this bead).
- [ ] R4(a) `splitMathSentinels(text, formulas)` — tokenises on `(\d+)`, returns
      `Array<{type:'text', text} | {type:'math', index}>`.
- [ ] R4(b) wire it into `parseInlineText`'s text/escape/html branch (incl. the `<br>`
      sub-split — split on `<br>` first, then run each part through the splitter), the
      strong/em/link branches, and the `image` token's remote/data-URL `TextRun` fallback
      (`md2docx.js:361`). Each `{type:'math'}` piece becomes a fresh
      `ImportedXmlComponent.fromXmlString(formulas[index].omml)` (or, if `formulas[index].error`
      is set and `--strict-math` was not given, the literal `formulas[index].raw` text instead).
- [ ] R5(a) `restoreLiteral` wired into `buildImageRun()`'s three `ImageRun.altText` string
      arguments only (`md2docx.js:324-328`) — the one context that cannot hold a spliced run.
- [ ] R4(d) in the main token loop: a `paragraph` token (or a table cell's sole inline token)
      whose trimmed text is exactly one sentinel referencing a `display: true` formula gets a
      dedicated `new Paragraph({alignment: AlignmentType.CENTER, children: [mathRun]})`
      instead of the ambient default-left paragraph.
- [ ] The R4/R5 tests written in 031-01 turn GREEN, including A5's sentinel-leak
      regression and A11's negative cases.

### Step 031-05 [LOGIC] — `md2docx.js` CLI wiring (R6)

- [ ] R6(a) call `preprocessMath()` on `markdown` (the post-frontmatter-strip variable, right
      after `md2docx.js:154`), before `marked.lexer()`.
- [ ] R6(b) add `--no-math` (boolean) and `--strict-math` (boolean) to the flag parser
      alongside the existing `--landscape`.
- [ ] R3(d) `--no-math` set → `preprocessMath()` returns `{text, formulas: []}`
      unchanged, skipping R1–R4 entirely — the regression lock A7 checks.
- [ ] R6(c) update the `USAGE` string.
- [ ] R6(d) confirm (via A8) that a `$`-free document takes the early-return path in both
      `preprocessMath` and the dense-doc guard, so `md2docx.js`'s existing test suite
      (`test_md2docx_pagesize.py` etc.) stays green with zero changes to its own expectations.
- [ ] The R6 tests written in 031-01 turn GREEN.

---

## 3. Phase 3 — Integration and gates

### Step 031-06 [INTEGRATION] — dependencies and licensing (R7)

- [ ] R7(a) `katex` and `mathml2omml` present in `skills/docx/scripts/package.json` +
      `package-lock.json` (already installed live in Step 031-03; this step is the
      commit-time confirmation, not a second install).
- [ ] R7(b) `THIRD_PARTY_NOTICES.md`: add a `mathml2omml` row; extend the existing `katex`
      row's "Used by" column with `docx/_math_lib.js`.
- [ ] Confirm no `LICENSE`/`NOTICE` changes are needed in `skills/docx/` itself (per-skill
      files are untouched by CLAUDE.md §3 — only root `THIRD_PARTY_NOTICES.md` changes),
      consistent with R7(c)'s LGPL-3.0 precedent rationale.

### Step 031-07 [INTEGRATION] — tests, validator, docs, backlog (R8, R9)

- [ ] R8(c) `skills/docx/scripts/tests/test_e2e.sh` gains the new `T-docx-math-*` suite.
- [ ] R8(d) / A10 `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx`
      exits 0.
- [ ] A9 manual gate: `node scripts/md2docx.js "tmp15/Направляемая звёздообразная
      маскированная диффузия.md" out.docx --page-size A4`; verify exit 0, `<m:oMath`
      occurrence count ≥ 300, `office/validate.py` → `OK`, and a `preview.py` spot-check.
- [ ] R9(a) `SKILL.md` §2, §4, §6 updated.
- [ ] R9(b) `SKILL.md` §1 Red Flags gains the pre-feature silent-loss entry.
- [ ] R9(c) `scripts/.AGENTS.md` documents `_math_lib.js`.
- [ ] R9(d) `docs/office-skills-backlog.md` row `docx-11` marked done.
- [ ] `docs/architectures/architecture-011-docx-skill.md` §9 status line flipped from
      PLANNED to Shipped (the flip TASK.md §0 and architecture-011:667-672 already name as
      the affected-outside-code-surface work); the three `[PLANNED, TASK 031, not yet
      merged]` / `[PLANNED, TASK 031]` markers at architecture-011:48, :67 removed; the
      matching `docs/ARCHITECTURE.md` chunk-catalog row (§4) and skill-tree row (§3.1) lose
      their "planned"/"(TASK 031 planned)" qualifiers.
- [ ] Full suite green: `scripts/tests/test_e2e.sh`, `test_md2docx_math.py`, and the
      pre-existing `md2docx.js` suites (regression check on R6(d)).

**Verification (task close-out):** all of §4's A1–A11 pass; `validate_skill.py` exits 0;
`docs/TASK.md` archives to `docs/tasks/task-031-docx-math-support.md` and this file archives
to `docs/plans/plan-031-docx-math-support.md` in lockstep (`skill-archive-task`).
