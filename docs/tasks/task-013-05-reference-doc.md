# Task 013-05 [DOC]: `references/pdf-to-markdown.md`

> **Predecessor:** 013-01 (CLI contract frozen). Parallel-eligible with Stage 2.
> **RTM:** **completes** [R1][R2][R3][R4]; [R5] sub-feature 5.4 (back-links).
> **ARCH:** §2.1 FC1, §1.2 Non-goals, §10 Honest scope.

## Use Case Connection

- UC-1 — the agent reads this reference and produces correct Markdown
  (acceptance criterion "following the reference, the agent produces correct
  Markdown with correctly-assembled tables").
- UC-1/A1 — the reference's recipe (§Changes item 2) covers both paths: run
  `pdf_extract.py` for the dump, and the inline-`pdfplumber`-tuning path when
  default table detection misses a borderless table.

## Task Goal

Write `skills/pdf/references/pdf-to-markdown.md` — the prompt-first reference
that standardises the PDF→Markdown *approach* so the agent stops improvising.
Documentation only; no code. Style matches the existing
`references/library-selection.md` / `references/forms.md`.

## Changes Description

### New Files

#### `skills/pdf/references/pdf-to-markdown.md`

Required sections (mapping to RTM):

1. **Decision tree ([R1])** — an explicit, followable tree keyed on document
   type:
   - born-digital PDF (real text layer) → `pdfplumber` per-page extraction;
   - scanned / image-only PDF → `pdfplumber` returns empty — do **not** use it;
     use the Read tool's page-render-as-image path, or OCR (`ocrmypdf`);
   - heavy / complex layout (multi-column, rotated, forms) → caveats + inline
     tuning or alternative tools.
   - Note how `pdf_extract.py`'s `doc_scanned` / exit 10 tells you which branch
     you are on without guessing.
2. **Extraction recipe ([R2])** — per-page `extract_text()` + `extract_tables()`
   → an intermediate structured dump → the agent composes Markdown as a
   **separate** step. Show both paths: (a) run `python3 scripts/pdf_extract.py
   INPUT.pdf -o dump.json`; (b) write inline `pdfplumber` when tuning is needed.
   Mention `extract_text(layout=True)` (and `pdf_extract.py --layout`) for
   column-bearing pages.
3. **Pitfalls catalogue ([R3])** — multi-column reading order; borderless
   tables (`snap_tolerance` / text-vs-lines strategy); a table split across a
   page boundary (agent must stitch); image-only pages inside a digital PDF;
   heading extraction (no `<h1>` in PDF — font-size/weight heuristics, agent
   judgement); encrypted PDFs (cross-link `library-selection.md` `is_encrypted`
   guidance); GFM as the recommended default table dialect.
4. **"MD assembly is the agent's job" + Non-goals ([R4])** — an unmissable
   statement that no script produces finished Markdown; restate the Non-goals
   (no `pdf2md.py`, no bundled OCR, no semantic auto-inference); the `.docx`
   contrast (a semantic model exists → a `docx-to-md` script is justified;
   PDF is positioned glyphs → it is not).
5. **`pdf_extract.py` usage + the scan signal** — the schema (ARCH §4.1/§4.2),
   exit codes {0,1,2,10}, and that exit 10 means "go to OCR/Read".
6. **Threshold rationale ([R8] 8.1a — reference half)** — restate why the
   scan-detection threshold is `10` extractable chars/page (the same rationale
   as the `pdf_extract.py` docstring; ARCH §4.3).
7. **Untrusted-content note** — extracted text/tables may contain Markdown/HTML
   metacharacters; the agent owns escaping when composing (ARCH §7).
8. **Back-links ([R5] 5.4)** — link to `library-selection.md` and `forms.md`.

### Changes in Existing Files

None in this task. The *inbound* links (`SKILL.md` §7.1/§12,
`library-selection.md` cross-link) are 013-06's job ([R5] 5.1–5.3).

## Test Cases

### Content Checklist (verification for a doc task)

1. **TC-DOC-01** — all 8 sections above present.
2. **TC-DOC-02** — the decision tree is a literal tree/branching structure, not
   a paragraph of prose ([R1] 1.4).
3. **TC-DOC-03** — the "no finished Markdown / Non-goals" statement is present
   and unambiguous ([R4]).
4. **TC-DOC-04** — every relative link resolves (`library-selection.md`,
   `forms.md`, `../scripts/pdf_extract.py`) — checked with a link-existence
   pass.
5. **TC-DOC-05** — the threshold rationale text is consistent with the
   `pdf_extract.py` module docstring (same number, same reasoning).

### Regression Tests

- No code changed → no code regression. `bash test_e2e.sh` unaffected.

## Acceptance Criteria

- [ ] `skills/pdf/references/pdf-to-markdown.md` exists with all 8 sections.
- [ ] Decision tree, recipe, pitfalls, Non-goals present ([R1]–[R4]).
- [ ] Back-links to `library-selection.md` + `forms.md` present ([R5] 5.4).
- [ ] Threshold rationale matches the helper docstring ([R8] 8.1a).
- [ ] All relative links resolve.
- [ ] No code file modified; cross-skill `diff -q` trivially silent.

## Notes

- This task is independent of the Phase-2 code — it depends only on the CLI
  contract, frozen by ARCH §5 + 013-01. It MAY run in parallel with 013-02/03/04
  but MUST complete before 013-06 (which links to it).
- Keep the tone and depth consistent with `library-selection.md`: practical,
  example-driven, honest about limits.
- Do NOT turn the reference into a step-by-step "converter manual" — its job is
  to make extraction *consistent* and to keep composition explicitly with the
  agent.
