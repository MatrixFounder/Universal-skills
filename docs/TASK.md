# TASK 013 — pdf-12: PDF → Markdown extraction guidance + `pdf_extract.py` helper

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 — pending Task-Reviewer approval.
> **Predecessors (context, not dependencies):**
> - pdf-8 / pdf-9 / pdf-10 / pdf-11 — `html2pdf.py` hardening line — ✅ MERGED.
> - The pdf skill's `references/library-selection.md` and `references/forms.md`
>   established the "pick the library, not the script" prompt-first pattern this
>   task extends.

---

## 0. Meta Information

- **Task ID:** `013`
- **Slug:** `pdf-to-markdown`
- **Target skill:** `skills/pdf/` (Proprietary — see root `CLAUDE.md` §3,
  `skills/pdf/LICENSE` / `skills/pdf/NOTICE`).
- **Backlog row:** `pdf-12` — **already exists** in
  `docs/office-skills-backlog.md` (P0 "agentic read-loop" tier). It was
  originally scoped as *two* scripts (`pdf_extract_text.py` /
  `pdf_extract_tables.py`) including a `--format markdown` mode. TASK 013
  **refines** that scope: one `pdf_extract.py` JSON-dump (a script never emits
  Markdown) + the `pdf-to-markdown.md` reference. R13 **updates** the existing
  pdf-12 row to the refined design and marks it done at merge.
- **Cross-skill replication:** **None.** This task adds files **only** under
  `skills/pdf/`. The new helper `pdf_extract.py` *imports* `skills/pdf/scripts/_errors.py`
  (the 4-skill byte-identical `--json-errors` envelope helper) **read-only** — it
  does NOT modify `_errors.py`, `preview.py`, `office/`, `_soffice.py`, or
  `office_passwd.py`. The CLAUDE.md §2 replication protocol is therefore **not
  triggered**. The cross-skill `diff -q` matrix MUST remain silent after this
  task lands:
  ```bash
  diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
  diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
  ```
  Both MUST produce no output.
- **Mode flag:** Standard VDD (no `[LIGHT]`).
- **New dependency:** **None.** `pdfplumber` is already a declared pdf-skill
  dependency (`skills/pdf/scripts/requirements.txt`; see `SKILL.md` §6). No
  change to `requirements.txt`, `LICENSE`, `NOTICE`, or root
  `THIRD_PARTY_NOTICES.md` is required.
- **Naming note (resolved assumption A-1):** The user request refers to "the
  pdf skill's `CLAUDE.md` §3 / §7.1". The pdf skill has **no** `CLAUDE.md` —
  the only `CLAUDE.md` is the repo root. The §3 ("Execution Mode —
  `prompt-first with library references for extraction`") and §7.1 ("Pick the
  library, not the script first — Extraction … not in the bundled scripts
  deliberately") clauses live in [`skills/pdf/SKILL.md`](../skills/pdf/SKILL.md).
  All "link from CLAUDE.md" requirements in this TASK therefore target
  `skills/pdf/SKILL.md`. See Open Question Q-1 (low priority, resolved).
- **Reference docs:**
  - Existing prompt-first reference: [`skills/pdf/references/library-selection.md`](../skills/pdf/references/library-selection.md).
  - Existing prompt-first reference: [`skills/pdf/references/forms.md`](../skills/pdf/references/forms.md).
  - `--json-errors` envelope contract: [`skills/pdf/scripts/_errors.py`](../skills/pdf/scripts/_errors.py).
  - Exit-code convention precedent (custom codes ≥ 10): [`skills/pdf/scripts/pdf_fill_form.py`](../skills/pdf/scripts/pdf_fill_form.py) (`--check` → 0/11/12).
  - New reference created by this task: `skills/pdf/references/pdf-to-markdown.md`.
  - New helper created by this task: `skills/pdf/scripts/pdf_extract.py`.

---

## 1. General Description

### 1.1. Goal

PDF→Markdown is a frequent agent request. Today the pdf skill **deliberately**
ships no extraction-to-Markdown script — extraction is too document-dependent to
freeze into one recipe (`SKILL.md` §3, §7.1). The agent therefore improvises a
`pdfplumber` script every time. Two consequences:

1. **Quality variance** — every improvisation differs.
2. **Silent failure on scans** — on an image-only (scanned) PDF, `pdfplumber`
   returns empty text **without raising**; the agent risks shipping an empty or
   broken Markdown deliverable with no error signal.

This task closes both gaps **without** building a misleading "universal
converter". It delivers, in two parts:

- **Part 1 (mandatory)** — a reference document
  `skills/pdf/references/pdf-to-markdown.md` that standardises the extraction
  *approach* (decision tree, recipe, pitfalls) so the agent stops improvising
  from scratch.
- **Part 2 (in scope — user-confirmed 2026-05-21)** — a helper script
  `skills/pdf/scripts/pdf_extract.py` that is a **structured dump**, not a
  converter: per-page text + tables as JSON, with **scan detection** as its
  defining feature — turning the silent-empty failure into a loud, machine-
  readable signal.

### 1.2. What is deliberately NOT being built (Non-goals)

These are first-class requirements — the design must actively avoid them:

- **No `pdf2md.py`.** No script that promises "PDF → finished Markdown". The
  helper is named `pdf_extract.py` precisely so the name makes no such promise.
- **No bundled OCR.** Scanned PDFs are **detected** and the agent is **pointed
  at** OCR (`ocrmypdf`) or the Read tool's page-render-as-image path. OCR
  tooling is NOT added to the skill.
- **No auto-inference of document semantics.** Heading hierarchy, reading order
  across multi-column layouts, cross-page table stitching, and image/diagram
  description remain **LLM judgement** — the final Markdown assembly is the
  agent's responsibility, not the script's. PDF is positioned glyphs with no
  semantic model; a "magic converter" is explicitly out of scope **permanently**
  (contrast `.docx`, which has a semantic model and for which a `docx-to-md`
  script is justified).

### 1.3. Connection with the existing system

**Extends (no modification):**
- `skills/pdf/SKILL.md` §3 / §7.1 prompt-first-for-extraction stance — this task
  *honours* it: the reference is prompt-first, and the helper is a dump (not a
  converter), so extraction-as-judgement is preserved.
- `references/library-selection.md` — gains a cross-link to the new reference;
  its existing "Extract text preserving layout → `pdfplumber`" / "OCR a scanned
  PDF → `ocrmypdf`" rows are the foundation the decision tree builds on.

**Imports (consumed read-only, not modified):**
- `_errors.report_error`, `_errors.add_json_errors_argument` — the cross-skill
  `--json-errors` envelope (schema `v=1`). Used exactly as `pdf_split.py` /
  `pdf_merge.py` / `pdf_fill_form.py` use it.
- `pdfplumber` — already an installed pdf-skill dependency.

**Out of scope (do NOT touch):**
- `html2pdf.py` / `html2pdf_lib/` and the pdf-8..pdf-11 line.
- `md2pdf.py`, `pdf_merge.py`, `pdf_split.py`, `pdf_watermark.py`,
  `pdf_fill_form.py`, `preview.py` — no behavioural change to any existing
  script.
- The other three office skills (`docx`, `xlsx`, `pptx`) — untouched.

### 1.4. Honest scope (v1 — explicitly out of scope or deferred)

Each item below MUST be documented in the relevant file (reference prose and/or
the helper's module docstring) so documentation never overstates the deliverable.

- **(a)** Final Markdown composition (heading levels, reading order, table
  stitching, image/diagram prose description) — agent judgement, not scripted.
  Stated explicitly in both the reference and the helper docstring.
- **(b)** OCR — not bundled; detection + pointer only.
- **(c)** Non-default table-detection tuning (`snap_tolerance`, text-vs-lines
  strategy, explicit vertical/horizontal edges) — the helper uses **default**
  `extract_tables()` settings; when defaults miss a borderless table the agent
  drops to inline `pdfplumber` code per the reference. The helper is a dump, not
  a tuning console.
- **(d)** Image / figure extraction or rasterisation — the helper reports
  `has_images` (boolean) per page but does NOT extract image bytes. Visual
  inspection stays with `preview.py` / the Read tool.
- **(e)** Form fields — covered by `references/forms.md` + `pdf_fill_form.py`;
  not in this task's surface.
- **(f)** Encrypted-PDF *cracking* — out of scope. The helper detects encryption
  and fails loudly (R6.4); supplying a known password via `--password` is
  supported.
- **(g)** Multi-column reading-order *reconstruction* — the helper exposes a
  `--layout` pass-through to `extract_text(layout=True)` so column separation is
  preserved as whitespace, but it does NOT re-flow columns into logical order.

---

## 2. Requirements Traceability Matrix (RTM)

Requirements are grouped into **3 Epics**. MVP column: ✅ = required for this
task to be "done"; ⬜ = nice-to-have / may defer.

### Epic E1 — Part 1: `references/pdf-to-markdown.md` (mandatory)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R1** | Decision tree: when `pdfplumber` applies, when it does not | ✅ | (1.1) Digital/born-digital PDF → `pdfplumber` per-page extraction. (1.2) Scanned / image-only PDF → Read tool page-render-as-image **or** OCR (`ocrmypdf`); `pdfplumber` will return empty — do not use it. (1.3) Complex layout (heavy multi-column, rotated text, forms) → caveats + inline tuning or alternative tools. (1.4) Rendered as an explicit, followable tree (not prose), keyed on document type. |
| **R2** | Extraction recipe for the digital-PDF branch | ✅ | (2.1) Per-page `page.extract_text()` + `page.extract_tables()`. (2.2) Dump to an intermediate structured form (the `pdf_extract.py` JSON, or equivalent inline structure). (2.3) Composition step is a **separate** agent step on top of the dump. (2.4) Shows both paths: run `pdf_extract.py` for the dump, or write inline `pdfplumber` when tuning is needed. (2.5) Notes `extract_text(layout=True)` for column-bearing pages. |
| **R3** | Pitfalls catalogue ("грабли") | ✅ | (3.1) Multi-column pages & reading order — text comes out interleaved; mitigation. (3.2) Borderless tables — `extract_tables()` misses them; `snap_tolerance` / text strategy. (3.3) Table split across a page boundary — needs agent stitching; how to recognise it. (3.4) Image-only / scanned pages inside an otherwise-digital PDF. (3.5) Heading extraction — no `<h1>` in PDF; font-size/weight heuristics, and that this is agent judgement. (3.6) Encrypted PDFs — cross-link to `library-selection.md` `is_encrypted` guidance. (3.7) Table dialect — the reference recommends **GFM pipe tables** as the default Markdown table form (HTML `<table>` only when a table needs `colspan`/`rowspan`); final dialect choice stays agent judgement per R4. |
| **R4** | Explicit "MD assembly is the agent's responsibility" framing + Non-goals | ✅ | (4.1) A dedicated, unmissable statement that the script never produces finished Markdown. (4.2) Restates the Non-goals from §1.2 (no `pdf2md.py`, no bundled OCR, no semantic auto-inference). (4.3) Contrasts with `.docx` (semantic model exists) to explain *why* PDF gets no converter script. |
| **R5** | Linkage / discoverability | ✅ | (5.1) `SKILL.md` §7.1 links to `references/pdf-to-markdown.md` (resolved target — see Meta A-1). (5.2) `SKILL.md` §12 Resources gains an entry. (5.3) `references/library-selection.md` cross-links to the new reference from its extraction rows. (5.4) The reference back-links to `library-selection.md` and `forms.md`. |

### Epic E2 — Part 2: `scripts/pdf_extract.py` helper (in scope)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R6** | Per-page extraction core | ✅ | (6.1) `pdfplumber`, per page: `extract_text()` (default settings) + `extract_tables()` (default settings). (6.2) `--layout` flag → `extract_text(layout=True)` pass-through. (6.3) `text` normalised to `""` when a page yields `None`. (6.4) Encrypted PDF: detect (`is_encrypted`), accept `--password PW`; on encryption-without-valid-password fail loudly (NOT silent empty output). |
| **R7** | Structured JSON output | ✅ | (7.1) Schema (all fields are contract): `{ "page_count": int, "doc_scanned": bool, "scanned_pages": [int,…], "pages": [ { "n": int, "text": str, "tables": [[[cell,…],…],…], "char_count": int, "has_images": bool, "scanned": bool } ] }`. (7.2) `tables` is `extract_tables()` raw form (list of row-lists of cell strings; `null` for empty cells). (7.3) Default output = JSON to **stdout**; `-o OUT.json` writes to a file. (7.4) `n` is 1-indexed; pages emitted in document order. (7.5) `scanned_pages` is the 1-indexed list of pages with `scanned:true` — it is a contract field (the partial-scan stderr warning of R8.4 derives from it), not optional. |
| **R8** | Scan detection (the defining feature) | ✅ | (8.1) Per-page `scanned` = `char_count` below a tunable threshold **AND** `has_images` true (a genuinely blank page — no text, no images — is `scanned: false`). (8.1a) **Threshold is auditable, not magic:** the chosen threshold value, its unit (see Q-3 — default: absolute extractable-char count per page), and its rationale ("header/footer artefact text on a scan is typically < N chars") MUST be documented in the helper module docstring AND in `references/pdf-to-markdown.md`. The scan-like fixture (R11.2) MUST sit clearly on the scanned side of the threshold — not borderline. (8.2) `doc_scanned` is true **iff** at least one page is `scanned` **AND** no page yields meaningful text (every page's `char_count` is at/below threshold). (8.2a) **Blank-page boundary rule:** a document with zero `scanned` pages is `doc_scanned:false` regardless of how many blank pages it has — an all-blank (or blank-only) PDF is NOT a scanned document and MUST exit 0, never exit 10 (pointing the agent at OCR for a blank document is wrong remediation). (8.3) Whole-document scan (`doc_scanned:true`) → **loud signal**: non-zero exit (custom code, see R9.3) + stderr remediation message pointing at OCR / the Read tool. (8.4) Partial scan (some pages scanned, some digital) → exit 0, per-page `scanned` flags set, stderr warning listing the `scanned_pages` numbers. (8.5) The dump JSON is still emitted on a whole-doc scan (diagnostic value); the non-zero exit is the signal, not output suppression. |
| **R9** | Skill / CLI contract | ✅ | (9.1) `argparse` CLI: `pdf_extract.py INPUT.pdf [-o OUT.json] [--layout] [--password PW] [--json-errors]`. (9.2) `--json-errors` → single-line JSON envelope on stderr, schema `v=1`, via `_errors.add_json_errors_argument` / `report_error`. (9.3) Exit codes: `0` success; `1` generic failure (input missing / not a PDF / unreadable / encrypted-without-valid-password, envelope `type` distinguishes, e.g. `EncryptedPDF`); `2` usage error (argparse, routed through the envelope as `UsageError`); `10` `DocumentScanned` (whole-doc scan, R8.3). (9.4) Idempotency: re-running overwrites `-o` output; stdout mode is naturally idempotent. (9.5) Clear human-readable error to stderr in default (non-JSON) mode. |
| **R10** | Naming & honesty discipline | ✅ | (10.1) File named `pdf_extract.py` — NOT `pdf2md.py` / `pdf2markdown.py`. (10.2) Module docstring states plainly: produces a structured **dump**, NOT finished Markdown; final composition is the caller's job. (10.3) `--help` text carries the same disclaimer. (10.4) No Markdown is emitted by the script — output is JSON only. |

### Epic E3 — Tests, fixtures, skill integration

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R11** | Test fixtures | ✅ | (11.1) One **digital** PDF fixture: real text + at least one table; small, committed under `skills/pdf/scripts/tests/fixtures/`. (11.2) One **scan-like** PDF fixture: image-only page(s) with `char_count` clearly **at or below** the R8.1 threshold (not borderline) — so the scan signal is unambiguous. (11.3) Fixture generation is reproducible and documented (a small builder script or a documented recipe — no opaque binary blobs without provenance). (11.4) One **encrypted** PDF fixture (a copy of the digital fixture with a known password) for the R12.7 success-path test. |
| **R12** | E2E tests in `scripts/tests/` | ✅ | (12.1) Digital PDF → structured dump is correct: `doc_scanned=false`, `page_count` right, table content present, non-empty `text`. (12.2) Scan-like PDF → loud signal: exit `10`, `doc_scanned=true`, pages `scanned=true`, stderr names OCR / Read tool. (12.3) `--json-errors` envelope shape asserted (`v`, `error`, `code`, `type`) for a domain failure (e.g. missing input) **and** for an argparse usage error (exit `2`, `type:"UsageError"`). (12.4) Idempotency asserted (two runs → identical `-o` output). (12.5) Exit-code matrix asserts all four codes — `0` (success), `1` (missing/unreadable input), `2` (usage error), `10` (whole-doc scan). (12.6) Tests wired so `bash scripts/tests/test_e2e.sh` exercises them (new `test_pdf_extract.py` and/or a smoke line in `test_e2e.sh`). (12.7) Encrypted-fixture **success path**: encrypted PDF + correct `--password` → exit `0`, correct dump; encrypted PDF + missing/wrong password → exit `1`, `type:"EncryptedPDF"`. |
| **R13** | `validate_skill.py` green + SKILL.md surface + backlog | ✅ | (13.1) `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pdf` exits 0. (13.2) `SKILL.md` updated for the helper: §2 Capabilities, §4 Script Contract (command line + exit codes), §10 Quick Reference row, §12 Resources entry. (13.3) `SKILL.md` §1 Red Flags / §3 Execution Mode reviewed for consistency (the skill still says "extraction not bundled" — reconcile: the helper is a *dump*, not a converter; the prompt-first stance for *composition* stands). (13.4) `docs/office-skills-backlog.md` — the **existing** `pdf-12` row is updated to the refined design (single `pdf_extract.py` dump + the `pdf-to-markdown.md` reference; no `--format markdown` script mode) and marked done at merge. (13.5) Cross-skill `diff -q` on `_errors.py` / `preview.py` stays silent (Meta). |

**RTM coverage:** 13 requirements across 3 Epics, all MVP-✅, no orphan requirements.

---

## 3. List of Use Cases

### UC-1 — Agent converts a digital PDF to Markdown (the common path)

#### 3.1.1. Actors
- **Agent** (Claude Code, the consumer of the skill).
- **System** (the `pdf` skill: `references/pdf-to-markdown.md` + `pdf_extract.py`).
- **User** (asked "convert this PDF to markdown").

#### 3.1.2. Preconditions
- A born-digital PDF with a real text layer.
- The pdf skill is installed (`pdfplumber` available).

#### 3.1.3. Main Scenario
1. User asks the agent to convert `report.pdf` to Markdown.
2. Agent reads `references/pdf-to-markdown.md`, follows the decision tree (R1),
   classifies the input as digital → `pdfplumber` branch.
3. Agent runs `python3 scripts/pdf_extract.py report.pdf -o dump.json`.
4. System emits the structured per-page dump; exit 0; `doc_scanned=false`.
5. Agent reads `dump.json`, and following the recipe (R2) composes the final
   Markdown — choosing heading levels, ordering content, rendering tables as GFM
   — applying its own judgement (R4).
6. Agent returns the `.md` to the user.

#### 3.1.4. Alternative Scenarios
- **A1 — Borderless table missed.** `extract_tables()` returns nothing for a
  table the agent can see in the text. Agent follows R3.2 and writes inline
  `pdfplumber` code with a tuned `table_settings` (`snap_tolerance`, text
  strategy).
- **A2 — Table split across pages.** A table's rows continue on the next page.
  Agent recognises it per R3.3 and stitches the two `tables` fragments into one
  Markdown table.
- **A3 — Multi-column page.** Reading order is interleaved. Agent re-runs with
  `--layout` (R6.2) and/or follows R3.1 to reorder.

#### 3.1.5. Postconditions
- A Markdown document faithful to the PDF's content, with tables correctly
  assembled.

#### 3.1.6. Acceptance Criteria
- ✅ Following `references/pdf-to-markdown.md`, the agent produces correct
  Markdown with correctly-assembled tables on the digital fixture (R1, R2, R3).
- ✅ `pdf_extract.py` on the digital fixture emits a correct structured dump,
  exit 0 (R6, R7, R12.1).

### UC-2 — Agent runs `pdf_extract.py` on a scanned PDF (the silent-failure fix)

#### 3.2.1. Actors
- **Agent**, **System**, **User** (asked to convert a scanned PDF).

#### 3.2.2. Preconditions
- An image-only / scanned PDF — no text layer, ~0 extractable characters.

#### 3.2.3. Main Scenario
1. Agent runs `python3 scripts/pdf_extract.py scan.pdf`.
2. System extracts per page: `char_count ≈ 0`, `has_images=true` → every page
   `scanned=true`, `doc_scanned=true`.
3. System emits the dump (diagnostic), writes a remediation message to stderr
   ("document appears to be scanned/image-only; use OCR (`ocrmypdf`) or render
   pages as images with the Read tool"), and **exits 10** (`DocumentScanned`).
4. Agent sees the non-zero exit + message, does NOT ship empty Markdown, and
   pivots to OCR or the Read-tool render path per R1.2.

#### 3.2.4. Alternative Scenarios
- **A1 — `--json-errors` consumer.** A wrapper passes `--json-errors`; the
  scanned signal is delivered as the JSON envelope (`code:10`,
  `type:"DocumentScanned"`).
- **A2 — Mixed document.** 8 digital pages + 2 scanned pages → exit 0,
  `doc_scanned=false`, `scanned_pages=[9,10]`, stderr warns "pages 9, 10
  appear scanned" (R8.4). Agent extracts pages 1–8 and OCRs 9–10.
- **A3 — All-blank document.** A PDF whose pages have no text *and* no images
  (e.g. an empty template) → every page `scanned=false`, `scanned_pages=[]`,
  `doc_scanned=false`, **exit 0** (R8.2a). The helper does NOT mistake a blank
  document for a scanned one and does NOT point the agent at OCR.

#### 3.2.5. Postconditions
- The scanned input never produces a silent empty/broken deliverable; the
  failure is loud and machine-readable. A blank document is never misreported
  as scanned.

#### 3.2.6. Acceptance Criteria
- ✅ `pdf_extract.py` on the scan-like fixture exits `10`, sets
  `doc_scanned=true`, and the stderr message names OCR / the Read tool
  (R8.3, R12.2).
- ✅ With `--json-errors`, the scanned signal is a valid `v=1` envelope with
  `code:10` (R9.2, R12.3).
- ✅ The scan-detection threshold value, unit, and rationale are documented in
  both the helper module docstring and `references/pdf-to-markdown.md`; the
  scan-like fixture sits clearly on the scanned side of it (R8.1a, R11.2).
- ✅ An all-blank PDF exits `0` with `doc_scanned=false` — never `10`
  (R8.2a, A3).
- ✅ An encrypted PDF + correct `--password` exits `0` with a correct dump; the
  same PDF without a valid password exits `1` with `type:"EncryptedPDF"`
  (R6.4, R12.7).

### UC-3 — Maintainer validates the skill after the change

#### 3.3.1. Actors
- **Maintainer / CI**, **System**.

#### 3.3.2. Preconditions
- TASK 013 implemented on a branch.

#### 3.3.3. Main Scenario
1. Maintainer runs `bash skills/pdf/scripts/tests/test_e2e.sh`.
2. All pre-existing pdf tests still pass; the new `pdf_extract` E2E coverage
   passes (R12).
3. Maintainer runs
   `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pdf`.
4. Exit 0 (R13.1).
5. Maintainer runs the cross-skill `diff -q` on `_errors.py` / `preview.py` —
   silent (R13.5).

#### 3.3.4. Alternative Scenarios
- **A1 — Validator flags a structural issue** (e.g. SKILL.md links a file that
  does not exist) → fix the link/file, re-run until exit 0.

#### 3.3.5. Postconditions
- The skill is structurally valid and the cross-skill replication invariant
  holds.

#### 3.3.6. Acceptance Criteria
- ✅ `validate_skill.py skills/pdf` exits 0 (R13.1).
- ✅ `test_e2e.sh` passes including the new coverage (R12.6).
- ✅ `diff -q` on `_errors.py` and `preview.py` is silent (R13.5).

---

## 4. Non-functional Requirements

- **Performance:** `pdf_extract.py` processes a typical document (≤ ~50 pages)
  in seconds; no specific throughput target. Avoid loading the whole PDF twice —
  one `pdfplumber.open()` pass.
- **Security:** No remote fetches. Operates only on the path given on the
  command line. Encrypted PDFs are detected, never silently bypassed. No shell
  interpolation of file contents. Output path is overwritten without prompting
  (consistent with the other pdf scripts; documented).
- **Compatibility:** Pure-Python, `pdfplumber` only — no new system dependency.
  Python version per the skill's existing baseline. `_errors.py` consumed
  read-only — must not drift from the docx master copy.
- **Maintainability:** The helper is a single self-contained script in the style
  of `pdf_split.py` / `pdf_fill_form.py` (argparse `main()`, `_errors`
  integration). The reference is a standalone Markdown doc in the style of
  `references/library-selection.md`.

## 5. Constraints and Assumptions

### Constraints
- **C-1** Files are added **only** under `skills/pdf/`. No cross-skill
  replication is triggered (Meta).
- **C-2** The helper MUST NOT be a converter. Output is JSON only; no Markdown
  is emitted by the script (R10.4).
- **C-3** OCR is not bundled (Non-goal §1.2).
- **C-4** The pdf skill is Proprietary; new files inherit `skills/pdf/LICENSE` /
  `NOTICE`. No new third-party dependency → no `THIRD_PARTY_NOTICES.md` change.
- **C-5** `pdf_extract.py` must not regress any existing pdf script or test.

### Assumptions
- **A-1 (resolved)** "the pdf skill's CLAUDE.md §3/§7.1" = `skills/pdf/SKILL.md`
  §3/§7.1 (the pdf skill has no `CLAUDE.md`). All linkage requirements target
  `SKILL.md`. See Q-1.
- **A-2** `pdfplumber` is and remains a declared pdf-skill dependency
  (confirmed: `SKILL.md` §6 lists it among installed packages).
- **A-3** The whole-document-scan signal is delivered as a **non-zero exit code**
  (`10`) — the strongest loud signal — *in addition to* a stderr message and the
  still-emitted dump. The user phrasing "громкий warn / ненулевой exit" is read
  as "warn **and** non-zero exit". See Q-2.
- **A-4** The per-page `scanned` threshold (R8.1, "~0 extractable chars") is a
  small tunable constant pinned during Architecture/Planning, not hard-coded
  magic. Default expectation: a handful of characters (header/footer artefacts)
  on an otherwise-image page still counts as scanned.

## 6. Open Questions

> All questions are **resolved with a documented default** and are **non-
> blocking** — listed for the Task-Reviewer / Architect to confirm or override.

- **Q-1 (low, resolved → A-1):** The request says "CLAUDE.md §3/§7.1" but the
  pdf skill has no `CLAUDE.md`. Resolved: linkage targets `skills/pdf/SKILL.md`
  §3/§7.1 + §12. Override only if a per-skill `CLAUDE.md` is intended to be
  created (not assumed — would be scope creep).
- **Q-2 (low, resolved → A-3):** Whole-document-scan behaviour — pure stderr
  warn (exit 0) vs non-zero exit. Resolved: **non-zero exit `10`** + stderr
  message + dump still emitted. This makes the signal impossible for an agent
  wrapper to miss, which is the entire point of the feature. Override to "exit 0
  + warn only" only if a non-zero exit would break an intended pipeline use.
- **Q-3 (low, resolved → A-4):** Unit of the scan-detection threshold (R8.1a) —
  absolute extractable-char count per page vs chars-normalised-by-page-area.
  Resolved: **absolute extractable-char count per page** (simplest, no page-
  geometry dependency; a scan's only text is occasional OCR-less header/footer
  artefacts, which are few in absolute terms regardless of page size). The
  Architect pins the concrete integer; this TASK fixes only the unit. Override
  to an area-normalised metric only if a real fixture proves absolute count
  misclassifies.

---

## 7. Definition of Done

- All 13 RTM requirements satisfied; all Acceptance Criteria in UC-1..UC-3 pass.
- `references/pdf-to-markdown.md` exists, is linked from `SKILL.md` §7.1/§12 and
  from `references/library-selection.md`.
- `scripts/pdf_extract.py` exists, named honestly, dump-only, with the R9
  contract; loud non-zero signal on whole-doc scans.
- E2E tests + the two fixtures committed; `test_e2e.sh` exercises them.
- `validate_skill.py skills/pdf` exits 0; cross-skill `diff -q` silent.
- `docs/office-skills-backlog.md` `pdf-12` row added.
