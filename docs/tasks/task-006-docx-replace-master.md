# Task 006 — docx-6 — `docx_replace.py` (точечный edit `.docx` без шаблона)

> **Backlog row:** `docx-6` (`docs/office-skills-backlog.md` §docx, p.171).
> **Predecessor / sibling references (MERGED, traceability anchors):**
> - `skills/docx/scripts/docx_add_comment.py` — anchor-finding pattern
>   (`_wrap_anchors_in_paragraph` cursor-loop, `_merge_adjacent_runs`,
>   `_is_simple_text_run`). Source of truth for the run-merge protocol.
> - `skills/docx/scripts/docx_fill_template.py` — `{{placeholder}}` swap
>   pattern via `_fill_paragraph` (body + tables + headers/footers walk).
> - `skills/docx/scripts/docx_merge.py` — body-tree splicing + relationship-
>   shifting precedent for `--insert-after` (we DO NOT relocate rels in v1,
>   only literal `<w:p>` block-paste from md2docx subprocess).
> - `skills/docx/scripts/md2docx.js` — Node converter used as a subprocess
>   to materialise MD source for `--insert-after`.
>
> **Status (2026-05-12):** ✅ **MERGED** (11-sub-task chain + VDD-Multi
> Phase-3 hardening + post-hoc honest-scope recommendations applied).
> See §11 Implementation Summary at the end of this document for actuals
> (LOC, test counts, fixes landed). Body below is the historical
> Analysis-phase technical specification — preserved verbatim for design
> traceability.

---

## 0. Meta Information

- **Task ID:** `006`
- **Slug:** `docx-replace`
- **Backlog row:** `docx-6` (`docs/office-skills-backlog.md` §docx, p.171).
- **Effort estimate (backlog):** **M (per backlog row docx-6)** — anchor-
  finding pattern already proven in `docx_add_comment.py`. v1 LOC budget
  (architect to refine): shim/script ≤ 600 LOC + tests ≤ 500 LOC. Adds
  ~ 4 Python modules at most (paragraph-locator, action dispatcher,
  MD-source loader, CLI).
- **Value (backlog):** **H** — closes "edit existing `.docx` without
  losing run-level formatting" gap. Current agent workflow forces a
  `docx2md → правка → md2docx` round-trip that strips styling, list
  numbering, and inline run formatting. `docx_replace.py` keeps the
  source workbook byte-identical except at the anchor point.
- **License:** Proprietary (per `CLAUDE.md` §3 — `skills/docx/` is
  in the proprietary subset; new files inherit the docx skill's
  `LICENSE` / `NOTICE`).
- **Decisions locked from `/vdd-start-feature` Q&A (2026-05-11):**

  | D | Decision | Rationale |
  |---|---|---|
  | **D1** | `--insert-after PATH` materialises markdown through a **`md2docx.js` subprocess** → unpack the tmp `.docx` → splice body `<w:p>` blocks AFTER the anchor's containing paragraph. | Single source of truth (`md2docx.js`). Full markdown semantics (headings, lists, **bold**, *italic*, `code`, links, tables). Cost: one extra `subprocess.run(["node", "md2docx.js", ...])` per call; Node already required by the docx skill. |
  | **D2** | Anchor-search scope = **body + headers + footers + footnotes/endnotes**. | Covers boilerplate edits (company name in header, footnote correction) that agents commonly request. Implementation = iterate every `word/{document,header*,footer*,footnotes,endnotes}.xml` part discovered via `[Content_Types].xml` + the corresponding `_rels`. Header/footer parts also enumerated through `word/_rels/document.xml.rels` for completeness. |
  | **D3** | `--anchor X --replace ""` (empty replacement) is **allowed** — anchor text is stripped, paragraph survives, surrounding runs untouched. | Mirrors find-and-replace semantics; agents use this to "delete this sentence but keep formatting". `<w:t>` may end up empty; that is OOXML-legal and `office.validate` accepts it. |
  | **D4** | `--all` is **supported across all three actions** (replace / insert-after / delete-paragraph). With `--all` + `--delete-paragraph`, every paragraph containing the anchor is removed; with `--all` + `--insert-after`, the MD source is materialised once and inserted after each matched paragraph (literal N×duplication). | Backlog explicitly calls out `--all` as a single uniform multi-match flag (parity with docx-1). User accepts the blast-radius warning; we document the danger of `--all --delete-paragraph` with common words in `--help`. |
  | **D5** | Exactly **one** of `--replace` / `--insert-after` / `--delete-paragraph` per invocation (mutually exclusive). | Cleanest CLI surface; agents chain invocations for compound edits. Mirrors `docx_add_comment.py --anchor-text vs --parent` mutex. |
  | **D6** | **Run-boundary policy = B (paragraph-level ops cross runs; `--replace` stays single-run, honest scope):** `--insert-after` and `--delete-paragraph` locate anchor via **whole-paragraph concatenated `<w:t>` text** (cross-run anchors OK — no rPr-merge ambiguity, as the action does not rewrite runs). `--replace` keeps `docx_add_comment.py` honest scope: anchor must fit within ONE `<w:t>` after `_merge_adjacent_runs` → otherwise `AnchorNotFound` exit 2. Documented in CLI `--help` and `SKILL.md`. | Best fidelity / complexity trade-off. `--replace` has rPr-inheritance ambiguity if span crosses formatting boundaries; paragraph-level ops do not. Lossless for the dominant use case. |
  | **D7** | `--insert-after -` reads markdown from **stdin**. | Parity with xlsx-2/-3/csv2xlsx stdin convention. Implementation: detect `-` → read `sys.stdin.buffer` into `tempfile.NamedTemporaryFile(suffix=".md")` → pass that path to `md2docx.js`. Same tmpdir cleanup as zip-mode. |
  | **D8** | Success log = **one-line stderr summary, exit 0** (mirrors docx-1). Failures use `--json-errors` cross-5 envelope (`{v:1, error, code, type, details}`). | Agent-friendly; consistent with sibling docx scripts. No JSON-success envelope (json-errors stays failure-only across the docx skill). |

- **Cross-cutting parity (carried from docx-1):**
  - **Cross-3** (`assert_not_encrypted`): exit 3 + `EncryptedFileError`.
  - **Cross-4** (`warn_if_macros_will_be_dropped`): stderr warning on `.docm` input.
  - **Cross-5** (`--json-errors`): JSON envelope on every failure.
  - **Cross-7** (H1 same-path guard): exit 6 + `SelfOverwriteRefused`, `Path.resolve()` follows symlinks.

---

## 1. General Description

### 1.1. Problem Statement

The docx skill currently has **no way to edit a live `.docx` without
either (a) a pre-marked `{{placeholder}}` template (`docx_fill_template.py`)
or (b) a destructive `docx2md → markdown edit → md2docx` round-trip
that loses run-level formatting, numbering, inline styles, and tracked-
change history.** Agents that need to apply a one-off correction to a
contract, spec, or template — for example, "in the line that starts
with 'Effective Date:', change the date" — currently have to:

1. Convert `.docx` → `.md` via `docx2md.js` (strips run formatting).
2. Hand-edit the markdown.
3. Convert back via `md2docx.js` (regenerates a stylistically-different `.docx`).

The lossy round-trip is the wrong tool for surgical edits. `docx-6`
ships `docx_replace.py` — a CLI that locates a **text anchor** inside
the OOXML body (plus headers/footers/footnotes/endnotes) and performs
one of three minimal-impact actions:

1. **`--replace TEXT`** — in-place text swap inside the run, preserving
   `<w:rPr>` (bold, italic, fontsize, colour, run-level styles).
2. **`--insert-after PATH`** — splice one or more new paragraph(s)
   (materialised from a markdown file via `md2docx.js`) AFTER the
   paragraph that contains the anchor.
3. **`--delete-paragraph`** — remove the entire `<w:p>` element that
   contains the anchor.

The source `.docx` is otherwise byte-identical (modulo zip-time
ordering — pack() is deterministic but normalises timestamps).

### 1.2. Connection with the Existing System

- **Reuses `office.unpack` / `office.pack`** (cross-skill OOXML helper)
  — same protocol as `docx_add_comment.py` / `docx_merge.py` /
  `docx_fill_template.py`. Module is NOT modified — purely consumed.
- **Reuses `_errors.py`** — `add_json_errors_argument` + `report_error`
  for the cross-5 envelope.
- **Reuses `office._encryption.assert_not_encrypted` + `office._macros.
  warn_if_macros_will_be_dropped`** — cross-3 / cross-4 parity.
- **Reuses the run-merge pattern from `docx_add_comment.py`** —
  `_is_simple_text_run`, `_rpr_key`, `_merge_adjacent_runs`,
  `_wrap_anchors_in_paragraph` (cursor-loop, intra-run multi-match).
  These helpers are a **candidate refactor** into a shared private
  module (`docx_anchor.py` — docx-only, NOT under `office/`, so the
  cross-skill replication boundary in `CLAUDE.md` §2 is preserved) so
  both `docx_add_comment.py` and `docx_replace.py` import them. **The
  extraction is contingent on Architect decision Q-A2 (§6.1):** the
  refactor MAY ship as part of docx-6's atomic chain, OR be deferred
  to a follow-up task. If extracted: byte-identical functions move to
  the new module; behaviour is unchanged; `docx_add_comment.py`'s E2E
  suite must continue to pass without edits. If deferred:
  `docx_replace.py` duplicates the helpers for v1 (acknowledged tech-
  debt, documented in `scripts/.AGENTS.md`).
- **Calls `md2docx.js` as a subprocess** (no JS rewrite, no in-process
  Node embedding). Subprocess discipline: capture stderr, propagate
  non-zero exit codes as a cross-5 envelope (`Md2DocxFailed`).
- **Composes with `docx_add_comment.py`** — agents typically run
  `docx_replace.py` first (surgical edit), then `docx_add_comment.py`
  to leave a comment trail explaining the change.

### 1.3. Goal of Development

Ship `skills/docx/scripts/docx_replace.py` plus shared
`docx_anchor.py` helper, with full cross-cutting parity (cross-3, -4,
-5, -7), 100 %-mark E2E coverage of the three action modes × two
`--all` settings × four exit codes, and a `validate_skill.py` pass.

---

## 2. List of Use Cases

### 2.1. UC-1 — Replace text inside a run (preserve formatting)

#### 2.1.1. Actors
- **Agent / user:** Editor agent issuing a surgical contract correction.
- **System:** `docx_replace.py` CLI; `office.unpack` / `office.pack`;
  `lxml.etree`.

#### 2.1.2. Preconditions
- Input `.docx` exists and is a valid OOXML wordprocessing document.
- Input is NOT encrypted (else exit 3, cross-3).
- Output path differs from input path (else exit 6, cross-7).
- Anchor substring fits within a single `<w:t>` after `_merge_adjacent_runs`.

#### 2.1.3. Main Scenario
1. Agent invokes:
   `docx_replace.py contract.docx contract.out.docx --anchor "May 2024" --replace "April 2025"`.
2. CLI validates flags (cross-3, cross-7 pre-flight).
3. CLI unpacks the docx into a temp tree.
4. CLI iterates every searchable XML part (body, headers, footers,
   footnotes, endnotes — see §11.1 for ordering).
5. For each part: walk every `<w:p>` → run `_merge_adjacent_runs(p)`
   → call `_replace_in_run(p, anchor, replacement, all=False)`.
6. First match wins (no `--all`): the run's `<w:t>` text is rewritten
   via cursor-loop (`text.find(anchor, cursor)`), the surrounding text
   preserved, run's `<w:rPr>` untouched.
7. CLI packs the tree → `output.docx`.
8. CLI prints to stderr:
   `contract.out.docx: replaced 1 anchor (anchor='May 2024' → 'April 2025')`.
9. Exit 0.

#### 2.1.4. Alternative Scenarios

- **Alt-1 (Anchor not found anywhere):**
  Step 6 returns 0 matches across all parts.
  → `report_error` exit 2, `AnchorNotFound`, envelope `{v:1, code:2,
  type:"AnchorNotFound", details:{anchor:"May 2024"}}`. No output written.
- **Alt-2 (Anchor spans formatting boundary, single-run policy):**
  Anchor substring not found in any single `<w:t>` after run-merge,
  even though it would match across runs. → `AnchorNotFound` exit 2.
  `--help` and `SKILL.md` document the workaround: use a shorter,
  formatting-uniform anchor; or use a paragraph-level action
  (`--insert-after` / `--delete-paragraph` for cross-run anchors).
- **Alt-3 (Empty replacement, `--replace ""`):**
  Anchor stripped; run's `<w:t>` may end up empty or shrink. Paragraph
  survives. Validation passes. stderr: `replaced 1 anchor → ''`.
- **Alt-4 (`--all` with multiple matches in same paragraph):**
  Same cursor-loop as `_wrap_anchors_in_paragraph` (docx-1) — every
  occurrence in every paragraph is replaced. Counter incremented per
  match.
- **Alt-5 (Encrypted input):** Exit 3, `EncryptedFileError`.
- **Alt-6 (`.docm` input):** stderr warning (macros will be dropped),
  but proceed; output is `.docx` (no `.docm` round-trip in v1).
- **Alt-7 (Same-path I/O, including symlink):** Exit 6, `SelfOverwriteRefused`.
- **Alt-8 (Malformed OOXML):** Exit 1, `MalformedOOXML` with `details:{detail}`.

#### 2.1.5. Postconditions
- `output.docx` exists, validates via `office/validate.py`.
- Run-level formatting at the anchor position is identical to source
  (verified by extracting the touched run's `<w:rPr>` from input and
  output trees and comparing `etree.tostring(rPr, method="c14n")`).
- Source file unchanged on disk.

#### 2.1.6. Acceptance Criteria
- ✅ Anchor "May 2024" inside a bold run becomes "April 2025" still bold.
- ✅ Anchor at start of run preserves leading whitespace handling
  (`xml:space="preserve"` re-set when needed).
- ✅ `--replace ""` produces empty `<w:t>` and exit 0.
- ✅ `--all` on a paragraph with 3 occurrences produces 3 replacements,
  cursor advances past each replacement (no infinite loop).
- ✅ Anchor not found → exit 2 + `AnchorNotFound` JSON envelope.

---

### 2.2. UC-2 — Insert paragraph(s) after the anchor's containing `<w:p>`

#### 2.2.1. Actors
- **Agent / user:** Editor agent appending a clause after a known section.
- **System:** `docx_replace.py`; `md2docx.js` (subprocess); `office.unpack`.

#### 2.2.2. Preconditions
- Same as UC-1.
- `--insert-after` PATH points to an existing markdown file, OR is `-`
  (stdin). Empty MD → exit 2 `EmptyInsertSource`.
- Node + `md2docx.js` reachable (else exit 1, `Md2DocxNotAvailable`).

#### 2.2.3. Main Scenario
1. `docx_replace.py contract.docx contract.out.docx --anchor "Article 5." --insert-after addendum.md`.
2. CLI runs `node md2docx.js addendum.md /tmp/.../insert.docx` (timeout 60 s).
3. CLI unpacks `insert.docx` into a sibling temp tree.
4. CLI unpacks `contract.docx` into the main temp tree.
5. CLI locates the anchor's containing `<w:p>` via **whole-paragraph
   concat-text matching** (D6 policy B — cross-run OK).
6. CLI extracts the body `<w:p>` children from `insert.docx`'s
   `word/document.xml` (skipping `<w:sectPr>` at the tail; honest scope
   §11.2 — we do NOT carry over section properties, headers, footers,
   or relationships from the MD source in v1).
7. CLI inserts the extracted paragraphs (deep-cloned) into the main
   tree IMMEDIATELY AFTER the anchor's `<w:p>` (in document order).
8. CLI packs → `output.docx`.
9. stderr: `output.docx: inserted N paragraph(s) after anchor 'Article 5.' (1 match)`.
10. Exit 0.

#### 2.2.4. Alternative Scenarios

- **Alt-1 (Stdin):** `--insert-after -` reads `sys.stdin.buffer` into
  a temp `.md` file, passes to step 2. Empty stdin → `EmptyInsertSource`.
- **Alt-2 (md2docx subprocess fails):** Non-zero rc from Node →
  `Md2DocxFailed` exit 1, `details:{stderr:<captured>, returncode}`.
- **Alt-3 (md2docx subprocess produces invalid docx):**
  `office.unpack` raises → `Md2DocxOutputInvalid` exit 1.
- **Alt-4 (Anchor crosses runs):** UC-2 uses paragraph-level concat-
  text matching (D6 / B) — anchor is found, insert proceeds.
- **Alt-5 (`--all`):** Insert MD content (deep-cloned per match) AFTER
  every paragraph containing the anchor. Test asserts N×duplication.
- **Alt-6 (MD source contains images / numbering / styles):** Honest
  scope §11.3 — images NOT copied across in v1 (relocator deferred to v2);
  `<w:numId>` references kept as-is (will resolve against the BASE
  doc's numbering definitions if present, otherwise plain text — same
  honest-scope as docx_merge iter-2). Stderr warning if relationship
  refs are detected in extracted body. v2 ticket: cross-skill helper
  `_docx_relocate_relationships`.
- **Alt-7 (Anchor not found):** Exit 2, `AnchorNotFound`.
- **Alt-8 (PATH does not exist or unreadable):** Exit 1, `FileNotFound`.

#### 2.2.5. Postconditions
- `output.docx` validates via `office/validate.py`.
- Insert paragraphs appear in document order immediately after the
  anchor's `<w:p>`, before the next existing block.
- Pre-existing content is byte-identical except for the splice point.

#### 2.2.6. Acceptance Criteria
- ✅ MD `# H1\n\nbody`  → two `<w:p>` (heading + body) inserted in order.
- ✅ Stdin source via `-` produces identical output to file source.
- ✅ Empty stdin / empty MD file → exit 2 `EmptyInsertSource`.
- ✅ `--all` produces N copies of the MD content (test with 2 matches).
- ✅ Subprocess failure surfaces stderr in cross-5 envelope.

---

### 2.3. UC-3 — Delete the paragraph containing the anchor

#### 2.3.1. Actors
- **Agent / user:** Editor agent removing a deprecated clause.
- **System:** `docx_replace.py`; `office.unpack`.

#### 2.3.2. Preconditions
- Same as UC-1.
- Anchor matches at least one `<w:p>` (concat-text policy D6 / B).

#### 2.3.3. Main Scenario
1. `docx_replace.py contract.docx contract.out.docx --anchor "DEPRECATED CLAUSE" --delete-paragraph`.
2. CLI unpacks.
3. CLI walks every searchable part; for each `<w:p>` concat-text run a
   substring check; if matched, remove `<w:p>` from its parent.
4. Without `--all`, FIRST match wins; with `--all`, every match removed.
5. CLI packs → `output.docx`.
6. stderr: `output.docx: deleted 1 paragraph (anchor='DEPRECATED CLAUSE')`.
7. Exit 0.

#### 2.3.4. Alternative Scenarios

- **Alt-1 (Anchor not found):** Exit 2, `AnchorNotFound`.
- **Alt-2 (Anchor matches a paragraph inside a table cell):** Paragraph
  removed; surrounding `<w:tbl>` / `<w:tc>` left intact. If cell becomes
  empty (no `<w:p>` children), an empty `<w:p>` placeholder is inserted
  to satisfy ECMA-376 §17.4.66 ("`<w:tc>` MUST contain at least one
  `<w:p>`"). Validation test enforces this.
- **Alt-3 (Anchor matches a paragraph that is the ONLY `<w:p>` in
  `word/document.xml` body):** Paragraph cannot be deleted (`<w:body>`
  MUST contain at least one block). → Exit 2,
  `LastParagraphCannotBeDeleted`. Honest-scope guard. v2: optional
  `--allow-empty-body` to insert an empty placeholder.
- **Alt-4 (`--all` matches every paragraph in body):** Same Alt-3 guard
  trips — refuse to empty the body. Exit 2.
- **Alt-5 (`<w:sectPr>` at end of body):** Last-body-paragraph guard
  ignores `<w:sectPr>` (it is body-level metadata, not content).

#### 2.3.5. Postconditions
- `output.docx` validates.
- Pre-existing content is byte-identical except for the removed paragraph.
- Table cells that lost their last paragraph carry a single empty
  placeholder `<w:p/>`.

#### 2.3.6. Acceptance Criteria
- ✅ Deleting a body paragraph reduces paragraph count by 1.
- ✅ `--all` removes every matching paragraph.
- ✅ Deleting the only body paragraph is refused (`LastParagraphCannotBeDeleted`).
- ✅ Deleting a paragraph from a table cell leaves a placeholder `<w:p/>`.

---

### 2.4. UC-4 — Library mode (operate on an already-unpacked OOXML tree)

> **Scope note (review-fix M1):** UC-4 is **NOT** explicitly requested
> by the backlog row docx-6. It mirrors `docx_add_comment.py`'s
> `--unpacked-dir` library mode (proven precedent) and is included
> here as an **Architect-discretionary** opt-in: if LOC budget pressure
> emerges in Planning, UC-4 is the FIRST candidate to defer to a v2
> follow-up backlog row. R8.g is correspondingly marked **MVP=No** in
> the RTM (§5).

#### 2.4.1. Actors
- **Agent / user:** Higher-level orchestrator that already unpacked a
  `.docx` and wants to chain multiple edits without repeated zip-cycle
  cost.
- **System:** `docx_replace.py --unpacked-dir TREE_ROOT`.

#### 2.4.2. Preconditions
- `--unpacked-dir` is a directory containing `word/document.xml`.
- `INPUT` / `OUTPUT` positional args must NOT be present.

#### 2.4.3. Main Scenario
- Same as UC-1 / UC-2 / UC-3 but no `unpack`/`pack` is performed.
- Tree is mutated in place.
- Same-path / encryption checks SKIPPED (the caller owns the tree).

#### 2.4.4. Alternative Scenarios

- **Alt-1 (Tree missing `word/document.xml`):** Exit 1, `NotADocxTree`.
- **Alt-2 (Positional + `--unpacked-dir`):** Exit 2, `UsageError`.

#### 2.4.5. Acceptance Criteria
- ✅ `--unpacked-dir TREE --anchor X --delete-paragraph` mutates TREE
  in place; subsequent `office.pack(TREE, ...)` produces a valid docx.

---

## 3. Non-functional Requirements

### 3.1. Performance
- Single `.docx` ≤ 5 MB, ≤ 10 000 paragraphs: end-to-end ≤ 3 s wall
  on M2-class hardware (including md2docx subprocess for UC-2).
- No quadratic algorithms on paragraph count (current docx-1 cursor-
  loop is linear; we inherit it).

### 3.2. Security
- **No shell injection:** md2docx invocation uses `subprocess.run(["node",
  ...], shell=False)` with argv list.
- **Subprocess timeout:** 60 s hard cap on md2docx (per docx-1 / xlsx-2
  precedent).
- **Temp file handling:** `tempfile.TemporaryDirectory(prefix=
  "docx_replace-")`, cleaned up on exit even on exceptions.
- **Stdin size cap (D7 follow-up):** Reject stdin > 16 MiB (uncompressed)
  → exit 2 `InsertSourceTooLarge`. Prevents DoS via piped fuzz.
- **Encrypted input:** cross-3 (exit 3 `EncryptedFileError`).
- **Macro warning:** cross-4 (stderr warning on `.docm`).
- **Same-path guard:** cross-7 (exit 6 `SelfOverwriteRefused`, symlink-
  aware via `Path.resolve(strict=False)`).
- **JSON-errors envelope:** cross-5 (`{v:1, error, code, type, details}`).
- **No network access** at any point.
- **No `eval` / `exec` / `__import__` shenanigans.**

### 3.3. Validation Hook
- `DOCX_REPLACE_POST_VALIDATE` env var (default OFF per xlsx-2/-3 D8
  precedent — review-fix M2 corrected the prefix; old draft had a
  misleading `XLSX_*` prefix). When `1/true/yes/on`: after pack,
  subprocess-invoke `python -m office.validate output.docx`. Validation
  failure → exit 7 + `unlink(output)`. Output integrity hook only.

### 3.4. Honest-Scope Documentation Requirement
- CLI `--help` MUST state:
  1. `--replace` anchor must fit within one `<w:t>` after run-merge.
  2. `--insert-after` does NOT copy images / charts / relationship
     targets in v1.
  3. `--delete-paragraph` refuses to empty the body.
  4. `--all --delete-paragraph` blast-radius warning.
- `SKILL.md` (docx skill) MUST gain a row in §1 "Red Flags" if v1 ships
  a behaviour that diverges from the docx-1 cookbook.

### 3.5. Compatibility
- Python ≥ 3.10 (per docx skill `requirements.txt`).
- Node + `md2docx.js` (already required by the docx skill).
- LibreOffice **NOT** required (we never call `_soffice.py`).

---

## 4. Constraints & Assumptions

### 4.1. Technical Constraints
- **Cross-skill replication boundary (`CLAUDE.md` §2)** must NOT be
  breached. New files live in `skills/docx/scripts/` outside `office/`.
  No edits to `office/`, `_soffice.py`, `_errors.py`, `preview.py`,
  `office_passwd.py` are required by docx-6. `diff -qr` checks remain
  silent.
- **`docx_anchor.py` extraction is docx-only** — file lives at
  `skills/docx/scripts/docx_anchor.py`, NOT under `office/`.
  `docx_add_comment.py` is refactored to import from it. xlsx / pptx /
  pdf do NOT get a copy.
- **Single source of truth for md2docx:** call `md2docx.js`, do not
  re-implement markdown parsing in Python.

### 4.2. Business Constraints
- License: Proprietary (per `LICENSE` / `NOTICE` of the docx skill).
- No new third-party dependencies. `lxml` / `python-docx` already in
  `requirements.txt`. Node deps unchanged.

### 4.3. Assumptions
- Agents calling docx-6 are aware of the `--all` blast radius for
  delete-paragraph (documented in `--help`).
- md2docx.js produces a body containing only paragraphs (and an
  optional `<w:sectPr>` at the tail) for typical markdown input. We
  do NOT support tables / images / charts that span complex
  relationship graphs in v1 (honest scope §11.3).
- The user understands that v1 keeps `<w:numId>` references on inserted
  paragraphs as-is and does NOT relocate numbering definitions from
  the MD-source tree (honest scope §11.4).

---

## 5. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | **`--replace` action** | ✅ Yes | R1.a in-place text swap inside `<w:t>`; R1.b preserve `<w:rPr>`; R1.c first-match default; R1.d cursor-loop multi-match within run (per docx-1 pattern); R1.e empty replacement allowed (D3); R1.f single-run honest scope (D6 / B); R1.g `xml:space="preserve"` set when needed. |
| **R2** | **`--insert-after` action** | ✅ Yes | R2.a subprocess invocation of `md2docx.js` (D1); R2.b unpack + extract body `<w:p>` blocks; R2.c skip trailing `<w:sectPr>` from MD source; R2.d deep-clone insert after anchor `<w:p>`; R2.e paragraph-level concat-text matching (D6 / B); R2.f `--all` produces N×duplication (D4); R2.g stdin `-` support (D7); R2.h stdin size cap 16 MiB. |
| **R3** | **`--delete-paragraph` action** | ✅ Yes | R3.a remove `<w:p>` from parent; R3.b paragraph-level concat-text matching; R3.c `--all` removes every match; R3.d refuse last-body-paragraph deletion (`LastParagraphCannotBeDeleted`); R3.e empty-cell placeholder rule (UC-3 Alt-2); R3.f preserve `<w:sectPr>` body-tail metadata. |
| **R4** | **Action mutex** | ✅ Yes | R4.a exactly one of replace/insert-after/delete-paragraph; R4.b otherwise exit 2 `UsageError`; R4.c `--anchor` required for all three actions. |
| **R5** | **Anchor-search scope (D2)** | ✅ Yes | R5.a `word/document.xml` body; R5.b `word/header*.xml`; R5.c `word/footer*.xml`; R5.d `word/footnotes.xml`; R5.e `word/endnotes.xml`; R5.f parts enumerated from `[Content_Types].xml`; R5.g part walk order = deterministic (document → headers (sorted by name) → footers (sorted by name) → footnotes → endnotes). |
| **R6** | **Run-merge & anchor-find helpers (`docx_anchor.py`)** | ✅ Yes | R6.a extract `_is_simple_text_run` / `_rpr_key` / `_merge_adjacent_runs` / `_replace_in_run` from `docx_add_comment.py`; R6.b `docx_add_comment.py` updated to import from `docx_anchor.py`; R6.c byte-identical behaviour (docx-1 E2E unchanged); R6.d new `_find_paragraph_containing_anchor(part_tree, anchor)` helper for paragraph-level matching; R6.e new `_concat_paragraph_text(p)` helper. |
| **R7** | **Cross-cutting parity** | ✅ Yes | R7.a cross-3 encryption guard exit 3; R7.b cross-4 macro stderr warning; R7.c cross-5 `--json-errors` envelope on every failure; R7.d cross-7 H1 same-path guard exit 6 (symlink-aware); R7.e `_errors.py` shared helpers imported (not copied); R7.f stdin `-` parity flag `--insert-after -`. |
| **R8** | **CLI surface** | ✅ Yes (R8.g = ❎ No, see UC-4 scope note) | R8.a positional INPUT / OUTPUT; R8.b `--anchor TEXT` required (with all three actions); R8.c `--replace TEXT` (empty allowed); R8.d `--insert-after PATH` (`-` for stdin); R8.e `--delete-paragraph` flag; R8.f `--all` flag (multi-match across all three actions); R8.g `--unpacked-dir TREE` library mode (UC-4, **MVP=No** per review-fix M1 — Architect-discretionary); R8.h `--json-errors` (cross-5); R8.i one-line stderr success log (D8); R8.j `--help` documents honest scope (§3.4); R8.k output extension preserved verbatim from OUTPUT positional (no `.docm` ↔ `.docx` auto-conversion; macro warning per cross-4 covers the lossy case — review-fix m4). |
| **R9** | **Output integrity** | ✅ Yes | R9.a `DOCX_REPLACE_POST_VALIDATE=1` env-opt-in calls `office/validate.py` (review-fix M2: renamed from `XLSX_DOCX_REPLACE_POST_VALIDATE`); R9.b validation failure → exit 7 + `unlink(output)`; R9.c subprocess.run env-override for hermetic tests; R9.d truthy allowlist `1/true/yes/on` (per xlsx-2 precedent). |
| **R10** | **Honest-scope regression locks** | ✅ Yes | R10.a `--replace` cross-run anchor → `AnchorNotFound` (test); R10.b `--insert-after` with image-bearing MD source → stderr warning emitted AND inserted `<w:p>` contains no live `r:embed` (refs stripped or text-only fallback) — consistent with §2.2.4 Alt-6 warn-and-proceed (review-fix M3 reworded; was "no `word/media/` parts in output"); R10.c `--delete-paragraph` last-body-paragraph refusal (test); R10.d `--all --delete-paragraph` on common word does NOT empty body (last-paragraph guard wins, test); R10.e `<w:numId>` survives in inserted paragraphs (test). |
| **R11** | **Testing scaffolding** | ✅ Yes | R11.a E2E suite in `tests/test_e2e.sh` mirroring docx-1 cadence (≥ 16 named cases); R11.b unit tests for `docx_anchor.py` extracted helpers (`tests/test_docx_anchor.py`, ≥ 20 tests); R11.c unit tests for `docx_replace.py` per-module (`tests/test_docx_replace.py`, ≥ 30 tests); R11.d fixtures derived from `md2docx.js` (no manually-crafted OOXML — same convention as docx-1); R11.e canary saboteur tests if applicable (docx-1 had none). |
| **R12** | **Docs & validators** | ✅ Yes | R12.a `SKILL.md` (docx) gains `docx_replace.py` row in scripts list; R12.b `scripts/.AGENTS.md` (docx) gains docx-6 row; R12.c `docs/office-skills-backlog.md` row docx-6 updated to "✅ DONE" with status line; R12.d `validate_skill.py skills/docx` exit 0; R12.e `tests/test_e2e.sh` exit 0; R12.f `eleven diff -q` cross-skill replication checks remain silent. |

---

## 6. Open Questions

> All scope-blocking ambiguities have been **locked at the
> `/vdd-start-feature` Q&A stage (D1–D8 above)**. Remaining items below
> are architecture-layer details for the Architect to close — they do
> NOT block TASK approval.

### 6.1. For the Architect

- **Q-A1 — Module split:** Should `docx_replace.py` be a single file
  (~ 600 LOC est.) or split into a small package (`docx_replace/`
  with `loaders.py` / `replace.py` / `insert.py` / `delete.py` /
  `cli.py`)? Precedent: xlsx-2 / xlsx-3 used a shim + package once
  CLI flag count crossed ~ 8; docx-1 is monolithic at 1101 LOC.
  docx-6 has 7 flags (--anchor, --replace, --insert-after, --delete-
  paragraph, --all, --unpacked-dir, --json-errors). Architect to lock
  the threshold and decision.
- **Q-A2 — `docx_anchor.py` extraction timing:** Do we ship the
  refactor of `docx_add_comment.py` in the **same atomic chain** as
  docx-6, or as a **pre-task** (separate task-007-docx-anchor-refactor)?
  Lower risk to ship together (single review cycle); higher risk if
  the refactor introduces a regression. Architect to decide.
- **Q-A3 — `<w:sectPr>` handling in MD-source insert:** docx_merge
  iter-2 had to strip paragraph-level `<w:sectPr>` from extra body.
  For docx-6 `--insert-after`, what about a `<w:sectPr>` at the END of
  the MD body (typical md2docx output)? Confirm: stripped (we are
  inserting INTO an existing section, not appending a new one).
- **Q-A4 — Numbering relocation:** Honest scope §11.4 says we do NOT
  relocate `<w:numId>` from the MD-source's `numbering.xml`. But if
  the BASE doc has no `numbering.xml` and the inserted MD content
  references `<w:numId="0">`, Word may show plain text instead of a
  bullet. Confirm: this is honest-scope (a warning to stderr is enough);
  v2 ticket = relocate numbering definitions.
- **Q-A5 — Empty-cell placeholder rule (UC-3 Alt-2):** ECMA-376 §17.4.66
  is the spec citation. Architect to verify exact path: when a `<w:tc>`
  loses its last `<w:p>`, do we insert `<w:p/>` or `<w:p><w:r><w:t/></w:r></w:p>`?
  (The former is shorter; both validate.)

### 6.2. For the User (non-blocking)

- **Q-U1 — Behaviour with tracked changes:** If the anchor is inside a
  `<w:ins>` or `<w:del>` revision, do we (a) match through revisions
  (treat `<w:ins>` content as live text), (b) skip revisions entirely,
  or (c) refuse with `AnchorInTrackedChange`? **Default proposal for
  v1:** (a) — match through `<w:ins>`, ignore `<w:del>` content
  (deleted text is not "live"). Refinement deferrable to v2 if needed.
- **Q-U2 — Behaviour with comments:** If the anchor is inside a
  comment range (`<w:commentRangeStart>` … `<w:commentRangeEnd>`), do
  we keep the range markers around the new replacement text? **Default
  proposal for v1:** yes (markers are siblings of the run, untouched
  by `<w:t>` rewrite).
- **Q-U3 — Reporting per-part match counts:** Stderr summary aggregates
  across all searched parts (body + headers + footers + footnotes +
  endnotes). Do we additionally print per-part counts? **Default
  proposal for v1:** no, single-line summary only (`replaced N
  anchor(s)`); per-part breakdown deferred to `--verbose` v2.

---

## 7. Verification Plan (Acceptance Gates)

A TASK passes review when **every RTM cell** has a corresponding
acceptance test in §11 of the upcoming Plan. The Architect / Planner
will translate this matrix into a Stub-First atomic chain (≈ 8–12 sub-
tasks, mirroring the xlsx-2 / xlsx-3 cadence).

| Gate | Pass condition |
|---|---|
| G1 (Cross-cutting) | cross-3 / cross-4 / cross-5 / cross-7 all green for docx_replace.py. |
| G2 (RTM coverage) | All R1–R12 sub-features have ≥ 1 E2E or unit test. |
| G3 (Honest-scope locks) | R10.a–e regression tests live (not skipped). |
| G4 (Refactor) | `docx_add_comment.py` E2E suite passes unchanged after `docx_anchor.py` extraction. |
| G5 (Validator) | `validate_skill.py skills/docx` exit 0. |
| G6 (Cross-skill drift) | All 11 `diff -q` parity checks silent. |
| G7 (Backlog) | `docs/office-skills-backlog.md` row docx-6 marked ✅ DONE with status line. |
| G8 (Docs) | `SKILL.md` + `scripts/.AGENTS.md` updated; `--help` documents honest scope (§3.4). |

---

## 8. Architecture Handoff Notes

Locked at Analysis (Architect must respect these unless reviewer overrides):

- **A1 — Shim + helper split:** `docx_replace.py` lives at
  `skills/docx/scripts/docx_replace.py`; helpers extracted to
  `skills/docx/scripts/docx_anchor.py` (docx-only, NOT under `office/`).
- **A2 — No new external dependencies.** `lxml`, `python-docx`, Node
  + `md2docx.js` already required.
- **A3 — No edits to `office/` / `_soffice.py` / `_errors.py` /
  `preview.py` / `office_passwd.py`.** All 11 `diff -q` checks remain
  silent.
- **A4 — Test layout:**
  - `tests/test_e2e.sh` — append a `# --- docx-6: docx_replace ---`
    block mirroring the docx-1 section's cadence.
  - `tests/test_docx_replace.py` — pure-Python unit tests for module
    internals.
  - `tests/test_docx_anchor.py` — unit tests for extracted helpers.
- **A5 — Atomic chain (Planner locks):** roughly 7–10 sub-tasks; first
  task ships skeleton + shim + 0-feature CLI; final task closes docs
  + backlog row. Mirrors xlsx-2 D5 pattern.

---

## 9. Honest-Scope Catalogue (v1 deliberate gaps)

> Added per review-fix m1 — earlier draft referenced §11.x without
> the section being present. Catalogue is the authoritative list of
> v1 limitations. Each gap is paired with a v2 ticket sketch.
>
> **Stable anchors:** the §11.1–§11.4 inline citations throughout the
> document remain valid by alias — they point at the matching bullet
> below. Renumbering here would invalidate ~ 6 cross-refs; aliasing
> is the lower-risk fix.

- **§11.1 — Part-walk ordering deterministic, NOT user-configurable.**
  Searched parts iterated in this fixed order: `word/document.xml`
  → headers (sorted by part name ascending) → footers (sorted by part
  name ascending) → `word/footnotes.xml` → `word/endnotes.xml`. The
  user cannot restrict search scope to a subset in v1 (e.g.
  "body-only"). v2: `--scope=body|all|body+headers|...`.
- **§11.2 — `<w:sectPr>` stripped from MD-source body before splice.**
  `md2docx.js` emits a section-properties element at the body tail.
  `--insert-after` MUST skip it (otherwise duplicate sectPr inside an
  existing section corrupts page layout — same lesson as docx_merge
  iter-2.2). Confirmed Q-A3 (§6.1).
- **§11.3 — Inserted MD content: images / charts / OLE / SmartArt NOT
  relocated.** v1 strips/warns on relationship-bearing runs from the
  MD-source body (R10.b regression lock + Alt-6 stderr warning).
  Reference: `docx_merge.py` iter-2.0 paved the relocator code path;
  copying it across to docx-6 is the v2 ticket
  `docx-6.5 — image-relocator for --insert-after`.
- **§11.4 — Numbering definitions NOT relocated.** Inserted `<w:numId>`
  references resolve against the BASE doc's `numbering.xml` if a
  matching abstractNumId exists; otherwise Word renders plain text
  (no bullet / number). v1 emits stderr warning when `<w:numId>` is
  seen in the inserted body and the BASE doc has no `numbering.xml`.
  v2 ticket: extend the docx-2 numbering-relocation logic to docx-6.

---

## 10. References

- **Sibling MERGED tasks (architecture precedent):**
  - `docs/architectures/architecture-003-json2xlsx.md` — shim + package
    + cross-5/cross-7 pattern.
  - `docs/architectures/architecture-005-md-tables2xlsx.md` — atomic
    chain cadence; preserved at task-005 archive.
- **Tasks history:**
  - `docs/tasks/task-005-md-tables2xlsx-master.md` — preceding task.
- **Source files to read before architecture:**
  - `skills/docx/scripts/docx_add_comment.py` (anchor-finding + run-
    merge precedent).
  - `skills/docx/scripts/docx_fill_template.py` (paragraph-walk +
    header/footer scope precedent).
  - `skills/docx/scripts/docx_merge.py` (body-tree splicing precedent).
  - `skills/docx/scripts/md2docx.js` (subprocess target for `--insert-after`).
  - `skills/docx/scripts/_errors.py` (cross-5 envelope helper).
  - `skills/docx/scripts/office/__init__.py` (unpack / pack signature).

---

> **TASK status (2026-05-12):** ✅ **MERGED**. See §11 Implementation
> Summary below for delivery actuals.

---

## 11. Implementation Summary (post-merge actuals, 2026-05-12)

### Chain delivered

- **11 sub-tasks merged** (006-01a, 006-01b, 006-02, 006-03, 006-04,
  006-05, 006-06, 006-07a, 006-07b, 006-08, 006-09). UC-4 library mode
  (R8.g) was originally `MVP=No` but shipped in 006-07b — LOC budget
  allowed the conditional landing. No deferral to `docx-6.4`.
- **VDD-Multi adversarial QA pass (post-merge):** 3 critics (logic +
  security + performance) found 1 CRIT + 4 HIGH + 6 MED real bugs in
  the merged chain. Phase-3 iter-1 applied 7 fixes; iter-2 caught a
  cross-fs `EXDEV` regression introduced by iter-1 FIX-6; iter-3
  closed it. Final convergence: logic clean, security confident,
  performance clean.
- **Post-VDD-Multi recommendations (this `/update-docs` cycle):**
  added `_try_unlink` helper to surface `output.unlink()` OSError in
  `details["unlink_error"]` (Logic-MED follow-up); `_run_post_validate`
  subprocess now uses `cwd=output.parent` (known-clean tmpdir) +
  `env["PYTHONPATH"]=scripts_dir` instead of `cwd=scripts_dir`
  (Security-MED-2 follow-up).

### Production code

| File | LOC | Cap (ARCH §3.2) | Notes |
|---|---:|---:|---|
| `skills/docx/scripts/docx_replace.py` | 434 | ≤ 600 | F1 + F7 + F8 orchestrator. |
| `skills/docx/scripts/docx_anchor.py` | 175 | ≤ 180 | 6 shared helpers (3 extracted from `docx_add_comment.py` + 3 new). |
| `skills/docx/scripts/_actions.py` | 409 | ≤ 600 | F2/F4/F5/F6; extracted at 006-07a per Q-A1 guardrail. |
| `skills/docx/scripts/_app_errors.py` | 64 | ≤ 80 | 10-class `_AppError` taxonomy. |
| **Total** | **1082** | — | — |

### Test surface

- **100 unit tests** total (28 in `test_docx_anchor.py` + 54 in
  `test_docx_replace.py` + 18 cross-skill `test_battery.py`),
  including 8 regression locks added during VDD-Multi Phase-3:
  empty-anchor guards, CT-no-WP fallback, generic-exception envelope,
  pack-validate-replace atomicity, cross-fs EXDEV fallback.
- **24 unique `T-docx-*` E2E cases** in `tests/test_e2e.sh`
  (T-docx-replace-*, T-docx-insert-after-*, T-docx-delete-paragraph-*,
  T-docx-unpacked-dir, T-docx-numid-survives-warning,
  T-docx-ins/del-content-matched). E2E total: 147 pass / 0 fail
  (122 pre-docx-6 + 25 new across all docx-6 sub-paths).
- **G4 regression:** docx-1..docx-5 E2E pass unchanged (122 → 147 with
  the docx-6 additions).

### Decisions delivered as-specified

D1 (md2docx subprocess), D2 (body + headers + footers + footnotes +
endnotes scope), D3 (empty replacement allowed), D4 (--all on all 3
actions), D5 (action mutex), D6 (run-boundary policy B: paragraph-level
ops cross runs; --replace single-run), D7 (stdin `-` support), D8
(one-line stderr summary). All D1–D8 + A1–A5 architecture handoff
hints honored without deviation.

### Honest-scope items deferred to v2 (visible in backlog)

- **docx-6.5** — image relocator for `--insert-after` (TASK §9 §11.3).
- **docx-6.6** — numbering definitions relocation (TASK §9 §11.4).
- **docx-6.7** — `--scope=body|all|...` filter (TASK §9 §11.1).
- v2-candidate code-level items (documented in honest-scope catalogue,
  no backlog row): Perf H1 deep-clone bomb under `--all --insert-after`,
  Perf H2 `_merge_adjacent_runs` always-c14n cost, Security LOW
  username paths in stderr, Logic LOW txbxContent-placeholder for
  non-`<w:tc>` containers, MIN cross-fs atomicity loss in `shutil.move`
  fallback branch.

### Gates at merge

| Gate | Status |
|---|---|
| G1 cross-cutting | ✅ all green |
| G2 RTM (R1–R12 + R11.e=N/A) | ✅ all covered |
| G3 honest-scope locks | ✅ R10.a-e + Q-U1 + A4 TOCTOU live |
| G4 docx-1..5 regression | ✅ 122 unchanged |
| G5 validator | ✅ `validate_skill.py skills/docx` exit 0 |
| G6 cross-skill `diff -q` | ✅ all 12 silent |
| G7 backlog | ✅ docx-6 row → ✅ DONE 2026-05-12 + 3 v2 follow-up rows |
| G8 docs | ✅ SKILL.md + scripts/.AGENTS.md updated; `--help` honest-scope substrings present |

### Reviews record

- `docs/reviews/task-006-review.md` — Analysis phase task-review (round 1).
- `docs/reviews/task-006-architecture-review.md` — Architecture phase (round 1).
- `docs/reviews/task-006-plan-review.md` — Planning phase (rounds 1 + 2).
- Per-sub-task Sarcasmotron reviews captured inline in the orchestrator
  session log; one sub-task (006-04) required iter-2 fixes; the
  remaining 10 sub-tasks passed iter-1 via Hallucination Convergence
  or with documented deviations.

---
