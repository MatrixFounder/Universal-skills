# TASK: xlsx-6 — `xlsx_add_comment.py`

## 0. Meta Information

- **Task ID:** 001
- **Slug:** `xlsx-add-comment`
- **Backlog item:** [`docs/office-skills-backlog.md`](office-skills-backlog.md) §xlsx-6
- **Status:** DRAFT v2 (Analysis Phase, VDD — round 2 after task-reviewer round 1)
- **Mode:** VDD (Verification-Driven Development)
- **Skill:** `skills/xlsx/`
- **License scope:** Proprietary (per-skill `LICENSE`, see CLAUDE.md §3)
- **Round-1 review:** [`docs/reviews/task-001-review.md`](reviews/task-001-review.md) — BLOCKING; this revision addresses C1, C2, C3, M1–M8, m1, m2, m4, m5, m7.

## 1. General Description

### Goal
Ship a CLI **`skills/xlsx/scripts/xlsx_add_comment.py`** that inserts a
Microsoft Excel comment into a target cell, achieving feature parity
with `docx_add_comment.py` and closing the most visible xlsx pipeline
gap. The tool MUST be production-ready in the same sense as
`docx_add_comment.py`: deterministic, validator-clean, hostile-input-safe,
and cross-skill-consistent (same-path / encryption / macros / JSON-errors
contracts).

### Why now
- Pure feature-parity gap: docx already has anchored-comment insertion.
- **Pipeline enabler for xlsx-7** (`xlsx_check_rules.py`): the validator
  emits a `findings` envelope; xlsx-6 is the canonical sink that
  materialises those findings as Excel comments on the offending cells.
  xlsx-7 is **blocked on xlsx-6** (backlog Dep column).
- Use-case: a validation agent reviews a timesheet/budget/CRM-export and
  drops machine-authored remarks directly on the bad cells, producing a
  workbook a human can open and triage in Excel.

### Connection with existing system
- Reuses `office/unpack` + `office/pack` (single OOXML helper, master in
  `skills/docx/scripts/office/`, byte-identical mirror in xlsx).
- Reuses `office._encryption.assert_not_encrypted` (cross-3 contract).
- Reuses `office._macros.warn_if_macros_will_be_dropped` (cross-4 contract).
- Reuses `_errors.add_json_errors_argument` / `report_error` (cross-5).
- Mirrors `docx_add_comment.py`'s "exit-6 SelfOverwriteRefused" guard
  (cross-7 H1).
- Output is verifiable through existing tooling: `office/validate.py`
  for structural OOXML correctness and `xlsx_validate.py --fail-empty`
  (skills/xlsx/scripts/xlsx_validate.py:66) for formula-error scan.
- Lives next to `xlsx_add_chart.py`, `xlsx_validate.py`, `xlsx_recalc.py`
  in `skills/xlsx/scripts/`. Listed in `skills/xlsx/SKILL.md` §4 +
  §10 Quick Reference + §12 Resources.

### Reference use-case (from backlog §xlsx-6 Notes)
> «validation-агент (xlsx-7 pipe) расставляет замечания на проблемные
> ячейки timesheet/budget/CRM-export» — i.e. an automated agent runs
> `xlsx_check_rules.py --json` against a workbook, pipes the resulting
> findings envelope into `xlsx_add_comment.py --batch -`, and produces
> a workbook a human auditor can open in Excel and triage cell-by-cell.

## 2. Requirements Traceability Matrix (RTM)

Granularity: every Requirement decomposes into ≥ 3 testable sub-features.
Every sub-feature is mapped to a Use Case in §3 and at least one E2E
fixture in §6.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | Insert a single legacy `<comment>` into a target cell | YES | a) Parse `--cell A5` (default first **visible** sheet); b) Resolve target sheet (default = first visible — see M2 in §5); c) Locate or create `xl/commentsN.xml` (N = next free part-counter, NOT sheet-index); d) Append `<comment ref="A5" authorId="...">` with body; e) Update `<authors>` (deduplicate case-sensitive by displayName string — see m5); f) Patch `[Content_Types].xml` Override + `xl/_rels/sheetS.xml.rels` Relationship; g) Add VML shape in `xl/drawings/vmlDrawingK.xml` (K = next free part-counter, binding via same sheet rels); h) Pick non-colliding **`<o:idmap data="N">`** value at the `<o:shapelayout>` root (workbook-wide scan — must not duplicate any `data` value already used by other `vmlDrawing*.xml` parts) AND a non-colliding **`<v:shape id="_x0000_sNNNN" o:spid="...">`** integer NNNN (workbook-wide scan across all VML parts). |
| **R2** | Cross-sheet & quoted-sheet cell syntax | YES | a) `--cell Sheet2!B5` (A1-style cross-sheet); b) `--cell 'Q1 2026'!A1` (quoted name); c) Apostrophe-escape `''` inside quoted name (`'Bob''s Sheet'!A1`); d) Unknown sheet → exit 2 `SheetNotFound` envelope; e) Cell out of A1 syntax → exit 2 `InvalidCellRef`. |
| **R3** | Threaded mode (Excel 365) | YES | a) `--threaded` flag → write modern `xl/threadedComments<M>.xml` (legacy-stub policy decided by Q7); b) Build/extend `xl/persons/personList.xml` with synthetic `<person displayName="..." id="UUIDv5(NAMESPACE_URL, displayName)" userId="<casefold>" providerId="None"/>` (see I1.4 step 4 for `casefold()` rationale); c) **personList obligatory** when threaded — without it Excel won't render the thread; d) Patch `[Content_Types].xml` Override + workbook-level rels for `personList` AND sheet rels for `threadedComment` (see M6 / I1.4 step 6); e) Multiple comments on the same cell → append to existing thread. |
| **R4** | Batch mode (two input shapes, auto-detected) | YES | a) `--batch path.json` accepts JSON file; b) Flat-array shape `[{cell, author, text, [initials], [threaded]}, ...]`; c) **xlsx-7 envelope shape** `{ok, summary, findings: [...]}`: map `cell ← findings[i].cell`, `text ← findings[i].message`, `author ← --default-author` (REQUIRED with envelope shape), `initials` derived from `--default-author`, `threaded ← --default-threaded`; d) Auto-detect shape by JSON root type (list vs object); e) **Skip group-findings** with `row: null` (no single-anchor cell), counted in `summary.skipped_grouped`; f) Anything else → exit 2 `InvalidBatchInput`; g) Author deduplication across the batch: one `<person>` per unique `displayName`; h) Shape-ID / `o:idmap` / `authorId` collision-free across the batch. |
| **R5** | Duplicate-cell semantics | YES | a) Threaded mode: append a new `<threadedComment>` to the existing thread on that cell; b) Legacy-only mode (`--no-threaded`, see Q7 / §2.5 CLI table) + duplicate cell: exit 2 `DuplicateLegacyComment`. *(Note: R5.c "mixed legacy+threaded on same cell" rule deferred — see M4 / Q7; once Q7 is closed in ARCHITECTURE.md it becomes a corollary, not a free-standing rule.)* |
| **R6** | Merged-cell target policy | YES | a) Default fail-fast: cell is a non-anchor of a merged range → exit 2 `MergedCellTarget` envelope (visual-offset bug); b) `--allow-merged-target` opt-out → auto-redirect to anchor cell of merged range, emit info `MergedCellRedirect` (mirrors xlsx-7 §4.4 merge-resolution); c) Cell IS the anchor of a merged range → write directly (no redirect, no error). |
| **R7** | Cross-cutting hardening (3/4/5/6/7-H1) | YES | a) Encrypted / legacy `.xls` input → exit 3 `EncryptedFileError` (cross-3); b) `.xlsm` macro-enabled input → emit warning to stderr when output extension would drop macros (cross-4); c) `--json-errors` flag → emit single-line JSON envelope on stderr for every failure path, schema `v=1` (cross-5); d) `INPUT == OUTPUT` (incl. symlink, compare via `Path.resolve()`) → exit 6 `SelfOverwriteRefused` (cross-7 H1); e) Argparse usage errors routed through the JSON envelope when `--json-errors` is set. |
| **R8** | Output integrity & deterministic-where-possible | YES | a) Output workbook validates clean under `office/validate.py` and `xlsx_validate.py`; b) Pre-existing comments are preserved byte-equivalent (XML diff: only added nodes); c) `.xlsm` round-trip preserves `xl/vbaProject.bin` (warning still emitted on `.xlsm → .xlsx`); d) Re-running the script on identical INPUT NEVER produces a corrupt file. **Determinism scope is explicit:** `<person id>` (UUIDv5 of displayName) is stable; `<o:idmap data>` and `o:spid` allocators are deterministic max+1; `--date` pins `<threadedComment dT>`. **Non-deterministic by design (R9.e):** `<threadedComment id>` is UUIDv4 — re-running produces non-byte-equivalent output even with `--date` pinned (M1 — analyst-acknowledged, locked into honest-scope). |
| **R9** | Honest scope (v1) — explicit non-goals | YES | a) **Reply-threads** (`parentId` linkage): NOT implemented in v1, every threadedComment is top-level; b) **Rich-text bodies**: plain text only — no bold/italic/links; c) **Drawing positioning**: default VML anchor only — no custom offsets; d) **Excel-365 round-trip mutation**: Excel may silently convert legacy → threaded on save → goldens are agent-output-only, never Excel-touched; e) **`<threadedComment id>` is UUIDv4** — re-running on identical input produces non-byte-equivalent output even with `--date` pinned (UUIDv5 is reserved for `<person id>` where stability matters for thread→author resolution); f) **Per-row `initials` override** in batch mode comes from `BatchRow.initials` only; envelope-mode uses initials derived from `--default-author` (a separate `--default-initials` flag is deferred to v2 — fixes M5); g) **`--unpacked-dir DIR` library mode** (parity feature with `docx_add_comment.py`) deferred to v2 — pipeline integration in v1 is via `--batch path.json`; h) Limitations documented in module docstring AND locked in by regression tests. |
| **R10** | Tests, validation evidence, docs | YES | a) ≥ 9 E2E checks added to `skills/xlsx/scripts/tests/test_e2e.sh` (or split file); b) Unit tests for cell-parser, batch-shape detector, person-id derivation, part-counter selector, merged-cell resolver; c) `skills/xlsx/SKILL.md` §4 + §10 + §12 updated; d) `skills/xlsx/references/` gets a short `comments-and-threads.md` reference (OOXML mapping, honest-scope notes); e) `skill-creator/scripts/validate_skill.py` exits 0 on `skills/xlsx`; f) Examples directory (`skills/xlsx/examples/`) gets a tiny `comments-batch.json` fixture. |

## 2.5 CLI surface (authoritative flag table)

> **Why this table:** task-reviewer C3 — flags MUST be enumerated in the
> TASK so the developer is not reverse-engineering them from prose.
> Mirrors the role of `parser.add_argument` in `docx_add_comment.py`,
> but expressed as a contract before code exists. Defaults marked
> `(Q7)` etc. are decided by ARCHITECTURE.md once the open questions
> close; this table only enumerates the flag *exists*.

### Positional arguments
| Name | Type | Required | Description |
|---|---|---|---|
| `INPUT` | `Path` | YES | Input `.xlsx`/`.xlsm`. |
| `OUTPUT` | `Path` | YES | Output path (must differ from INPUT — see cross-7 H1). |

### Single-cell mode (mutex group A: `--cell` XOR `--batch`)
| Flag | Type | Default | Required-when | Description |
|---|---|---|---|---|
| `--cell REF` | `str` | — | `--batch` not given | Target cell. Forms: `A5`, `Sheet2!B5`, `'Q1 2026'!A1` (apostrophe-escape `''`). See I1.1. |
| `--text MSG` | `str` | — | `--cell` given | Comment body (plain text; multiline via `\n` in shell-quoted form). Empty/whitespace-only → exit 2 `EmptyCommentBody` (Q2 resolution). |
| `--author NAME` | `str` | — | `--cell` given | Display name. |
| `--initials INI` | `str` | derived from `--author` | optional | Override initials. |

### Batch mode (mutex group A)
| Flag | Type | Default | Required-when | Description |
|---|---|---|---|---|
| `--batch FILE` | `Path` or `-` | — | `--cell` not given | Path to JSON file (or `-` for stdin). Auto-detects flat-array vs xlsx-7 envelope (I2.1). 8 MiB pre-parse cap → `BatchTooLarge` exit 2 (m2). |
| `--default-author NAME` | `str` | — | `--batch` envelope shape | Required only when batch root is xlsx-7 envelope; ignored otherwise. |
| `--default-threaded` | flag | `false` | optional | Default `threaded` for envelope-shape rows (per-row override possible only in flat-array shape). |

### Threaded-mode group (mutex group B: `--threaded` XOR `--no-threaded`)
| Flag | Type | Default | Required-when | Description |
|---|---|---|---|---|
| `--threaded` | flag | (Q7) | optional | Force threaded write (writes `xl/threadedComments<M>.xml` + `xl/persons/personList.xml`; legacy-stub policy decided in Q7). |
| `--no-threaded` | flag | — | optional | Force legacy-only write (no threaded part, no personList). Same role as `--legacy-only` in earlier draft; renamed for clarity (C2). Duplicate-cell on `--no-threaded` → exit 2 `DuplicateLegacyComment` (R5.b). |

### Cross-cutting & cell-policy flags
| Flag | Type | Default | Description |
|---|---|---|---|
| `--allow-merged-target` | flag | `false` | Redirect comment to anchor cell of merged range instead of failing fast (R6.b). Emits info `MergedCellRedirect`. |
| `--date ISO` | `str` (ISO-8601) | `datetime.now(UTC).isoformat()` | Override timestamp on `<threadedComment dT=...>` for deterministic test goldens (Q5 resolution; mirrors `docx_add_comment.py --date`). |
| `--json-errors` | flag | `false` | Emit failures as single-line JSON envelope on stderr, schema `v=1` (cross-5). Argparse usage errors routed through this envelope (`type:"UsageError"`). |

### Mutex / dependency rules (must be enforced in argparse)
- **MX-A:** `--cell` XOR `--batch` (one is required, both is `UsageError`).
- **MX-B:** `--threaded` XOR `--no-threaded` (default decided per Q7).
- **DEP-1:** `--text` and `--author` REQUIRED iff `--cell` given.
- **DEP-2:** `--default-author` REQUIRED iff `--batch` and root JSON is the xlsx-7 envelope shape.
- **DEP-3:** `--default-threaded` MUST NOT be passed with `--cell` (no semantic).
- **DEP-4:** When `--json-errors` is set, even argparse usage errors must surface through the `_errors.report_error` helper (cross-5 contract, mirrors `docx_add_comment.py`).

### Exit codes
| Code | Class | Triggering envelopes |
|---|---|---|
| 0 | success | — |
| 1 | I/O / pack failure / malformed OOXML / post-pack guard | `IOError`, `BadZipFile`, lxml parse errors, `MalformedVml`, `OutputIntegrityFailure` (2.08 paranoid post-validate, env-gated by `XLSX_ADD_COMMENT_POST_VALIDATE`) |
| 2 | usage / not-found / batch-shape / duplicate-cell | `UsageError`, `SheetNotFound`, `InvalidCellRef`, `MergedCellTarget`, `EmptyCommentBody`, `InvalidBatchInput`, `BatchTooLarge`, `MissingDefaultAuthor`, `DuplicateLegacyComment`, `DuplicateThreadedComment` (M-2 / ARCH §6.2 — refuses legacy-only write over an existing thread) |
| 3 | encrypted / legacy CFB | `EncryptedFileError` (cross-3) |
| 6 | INPUT == OUTPUT | `SelfOverwriteRefused` (cross-7 H1) |

## 3. Epics & Use Cases

> **VDD constraint:** Each Epic groups Issues that are jointly testable.
> Each Issue maps to ≥ 1 Use Case with verifiable Acceptance Criteria.
> Granularity: an issue is "atomic" when one developer-day produces a
> stub + E2E red→green pair.

### Epic E1 — Single-comment insertion (legacy + threaded)

Maps to: R1, R2, R3, R5, R6 (single-cell paths).

#### Issue I1.1 — Cell-syntax parser (`--cell`)

Use Case: **Parse target cell reference**.

- **Actors:** CLI invoker (script consumer), System.
- **Preconditions:** A valid `.xlsx` file exists on disk.
- **Main scenario:**
  1. User runs `xlsx_add_comment.py IN.xlsx OUT.xlsx --cell A5 --author "Q" --text "msg"`.
  2. System parses `A5` as `(sheet=<first-visible>, ref="A5")`.
  3. System resolves `<first-visible>` by reading `xl/workbook.xml` `<sheet>` order and selecting the first whose `state` is absent or `"visible"` (skipping `state="hidden"` and `state="veryHidden"` — fix for M2). Sheet-name lookup is **case-sensitive** (fix for M3).
  4. If ALL sheets are hidden/veryHidden → exit 2 `NoVisibleSheet` envelope.
- **Alternative scenarios:**
  - **A1.1.a:** `--cell Sheet2!B5` → `(sheet="Sheet2", ref="B5")`.
  - **A1.1.b:** `--cell 'Q1 2026'!A1` → `(sheet="Q1 2026", ref="A1")` (apostrophe wrapper unwrapped).
  - **A1.1.c:** `--cell 'Bob''s Sheet'!A1` → `(sheet="Bob's Sheet", ref="A1")` (escape `''` → `'`).
  - **A1.1.d:** `--cell GhostSheet!A1` and no such sheet → exit 2 `SheetNotFound`, `details.available: ["Sheet1","Sheet2"]`.
  - **A1.1.e:** `--cell ZZ` (no row digits) → exit 2 `InvalidCellRef`.
  - **A1.1.f:** `--cell sheet2!A1` against `<sheet name="Sheet2">` (case-mismatch) → exit 2 `SheetNotFound`, `details.suggestion: "Sheet2"` (M3).
  - **A1.1.g:** `--cell HiddenSheet!A1` against `<sheet state="hidden">` → succeed but emit info-level note to stderr (target IS explicit; default-sheet rule does NOT apply here).
- **Postconditions:** `(sheet_index, sheet_name, cell_ref)` tuple is resolved or the script exited with a typed envelope.
- **Acceptance criteria:**
  - ✅ All 7 parse cases above produce the exact tuple/envelope specified.
  - ✅ Apostrophe escape `''` → `'` is documented and tested.
  - ✅ Unknown-sheet error includes the available sheet names in `details.available`; case-mismatch produces a `details.suggestion`.
  - ✅ E2E `hidden-first-sheet`: workbook with Sheet1 `state="hidden"`, Sheet2 visible → `--cell A5` (no qualifier) targets Sheet2.

#### Issue I1.2 — Part-counter resolution (`commentsN`, `vmlDrawingK`)

Use Case: **Allocate next free OOXML part name**.

- **Actors:** System.
- **Preconditions:** Workbook is unpacked.
- **Main scenario:**
  1. System scans `[Content_Types].xml` for existing `Override PartName="/xl/comments*.xml"`.
  2. System picks the next free integer N (max+1, starting at 1 if none).
  3. Same logic for `vmlDrawingK.xml` — independent counter.
  4. Comment-to-sheet binding goes through `xl/_rels/sheet<S>.xml.rels`, NOT through filename collision with `<S>`.
- **Alternative scenarios:**
  - **A1.2.a:** Workbook has `xl/comments1.xml` already bound to Sheet3 → adding a comment to Sheet1 picks `xl/comments2.xml` and binds it via Sheet1's rels (NOT N==1).
  - **A1.2.b:** No existing comments parts → N = 1 even if target is Sheet3.
- **Postconditions:** New part name doesn't collide with any existing Override or filename.
- **Acceptance criteria:**
  - ✅ E2E fixture: workbook with 3 sheets, only Sheet3 has comments → adding to Sheet2 yields `xl/comments2.xml` whose `Relationship` lives in `xl/_rels/sheet2.xml.rels`.
  - ✅ E2E fixture: clean workbook, target = Sheet2 → N = 1 (NOT 2).
  - ✅ Unit test asserts the counter is independent for `commentsN` vs `vmlDrawingK`.

#### Issue I1.3 — Legacy comment XML write path (`xl/commentsN.xml`)

Use Case: **Emit a legacy comment with author dedup + VML shape**.

- **Actors:** System.
- **Preconditions:** Sheet, cell ref, author, body are resolved.
- **Main scenario:**
  1. Open or create `xl/commentsN.xml` (root: `<comments>` with `<authors>` + `<commentList>`).
  2. Insert author into `<authors>` if absent (**dedup key = case-sensitive identity comparison on `displayName` string**, matching `<person>` dedup in I1.4 — m5); reuse index if present (`authorId` is the position).
  3. Append `<comment ref="A5" authorId="..."><text><r><t>...</t></r></text></comment>`.
  4. Open or create `xl/drawings/vmlDrawingK.xml`. The drawing root carries `<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="N"/></o:shapelayout>`; **N must not duplicate any `data` value already used by other `vmlDrawing*.xml` parts in the workbook** (workbook-wide pre-scan). Per-shape `<v:shape id="_x0000_sNNNN" o:spid="...">`: NNNN is the next free integer **across all VML parts in the workbook** (mirrors Excel's own `_x0000_s1025`-then-`_x0000_s1026` scheme).
  5. Update `[Content_Types].xml` Override entries for both new parts (idempotent: skip if present).
  6. Update `xl/_rels/sheet<S>.xml.rels` with two new `Relationship`s (`comments` + `vmlDrawing`); reuse rId scheme `rIdN+1`.
- **Alternative scenarios:**
  - **A1.3.a:** Sheet already has comments → preserve existing nodes byte-equivalent (only add new `<comment>` + `<v:shape>` + author if new).
- **Postconditions:** `office/validate.py` exits 0 on the produced file.
- **Acceptance criteria:**
  - ✅ E2E "clean-no-comments": new file has `xl/commentsN.xml`, `xl/drawings/vmlDrawingK.xml`, both Overrides, both rels entries.
  - ✅ E2E "existing-legacy preserve": adding a 3rd comment leaves the original 2 comments unmodified (XML diff: only added nodes).
  - ✅ E2E "idmap-conflict" (C1 fix): workbook with pre-existing `vmlDrawing1.xml` having `<o:idmap data="1"/>` → adding a comment to a different sheet allocates `<o:idmap data="2"/>` (or higher) AND uses shape IDs in the `_x0000_s2049+` range so no collision against existing `_x0000_s1025`.
  - ✅ Unit test for the `<o:idmap>` workbook-wide scanner (returns max+1 across all VML parts).
  - ✅ Unit test for the `o:spid` workbook-wide scanner.

#### Issue I1.4 — Threaded comment write path (`xl/threadedComments<M>.xml` + `personList.xml`)

Use Case: **Emit a threaded comment + person record (Excel 365)**.

- **Actors:** System.
- **Preconditions:** `--threaded` flag set OR batch row's `threaded: true` OR `--default-threaded`.
- **Main scenario (Q7-dependent — see §6 Open Questions):**
  1. **Legacy-stub policy:** the rule for whether `--threaded` ALSO writes a legacy `<comment>` stub is **OPEN — see Q7**. Two options on the table: (A) Excel-365 fidelity — write both legacy + threaded; (B) threaded-only — write only `xl/threadedComments<M>.xml` + `xl/persons/personList.xml`. ARCHITECTURE.md MUST close Q7 before development starts. This Use Case is described against the threaded part shape; the legacy-stub addendum is conditional on Q7.
  2. Open or create `xl/threadedComments<M>.xml` (root: `<ThreadedComments xmlns="...">`).
  3. Append `<threadedComment ref="A5" dT="..." personId="{...}" id="{UUIDv4}">{text}</threadedComment>`. **`id` is UUIDv4 — non-deterministic by design** (R9.e).
  4. Open or create `xl/persons/personList.xml`; insert `<person displayName="<author>" id="{UUIDv5(NAMESPACE_URL, displayName)}" userId="<author casefold>" providerId="None"/>` if absent. **`providerId="None"` is the literal string** (not Python `None`) — meaning "no SSO provider", avoids Excel's "unknown user" warning. **`userId` derived via `str.casefold()`** for non-ASCII parity (Q6 resolution; locks German ß → ss, Cyrillic Ё → ё, etc. — m1).
  5. Patch `[Content_Types].xml` Override for both new parts.
  6. Patch rels:
     - `xl/_rels/sheet<S>.xml.rels` gains the `threadedComment` Relationship.
     - **`xl/_rels/workbook.xml.rels` (NOT a sheet rels file) gains the `personList` Relationship** (M6 — workbook-scoped per ECMA-376 + MS-XLSX threaded-comments extension).
- **Alternative scenarios:**
  - **A1.4.a:** Same author appears twice in a batch → only one `<person>` (deduped case-sensitive on `displayName` string; `userId` is derived from `displayName` so the two are consistent).
  - **A1.4.b:** Threaded duplicate-cell → append a new `<threadedComment>` referencing the same `ref` (forms a thread; v1 does NOT set `parentId` — see R9.a).
- **Postconditions:** Excel 365 renders the thread.
- **Acceptance criteria:**
  - ✅ E2E "threaded": personList contains exactly the unique authors, ids are stable UUIDv5(displayName).
  - ✅ E2E "thread linkage": two comments on same cell → both `<threadedComment>` nodes with same `ref`, distinct `id`s, both `personId` resolve to the same `<person>`.
  - ✅ E2E "threaded-rel-attachment" (M6): produced workbook has the `personList` rel in `xl/_rels/workbook.xml.rels`, and each `threadedComment` rel in the corresponding `xl/_rels/sheet<S>.xml.rels`.
  - ✅ Unit test asserts `providerId="None"` is the literal string (not Python `None`).
  - ✅ Unit test on `casefold()`-derived userId for `displayName="STRAẞE"` → expected `"strasse"` (m1 lock).

#### Issue I1.5 — Merged-cell target resolution

Use Case: **Refuse or redirect comment on non-anchor merged cell**.

- **Actors:** System.
- **Preconditions:** Target cell falls inside a `<mergeCell ref="A1:C3">` range.
- **Main scenario (default):**
  1. System detects target cell ≠ top-left anchor of merged range.
  2. System emits `MergedCellTarget` envelope (exit 2) with `details: {anchor: "A1", target: "B2", range: "A1:C3"}`.
- **Alternative scenarios:**
  - **A1.5.a:** Target IS anchor (`A1` for `A1:C3`) → proceed normally, no warning.
  - **A1.5.b:** `--allow-merged-target` set → redirect to anchor, write the comment there, emit info-level `MergedCellRedirect` to stderr (and JSON details when `--json-errors`).
- **Postconditions:** Comment lands on anchor cell or script fails fast.
- **Acceptance criteria:**
  - ✅ E2E "merged-cell-target": `--cell B2` on `A1:C3` merged → exit 2 `MergedCellTarget`.
  - ✅ E2E `--allow-merged-target` flag flips behaviour to redirect with info message.

### Epic E2 — Batch mode (xlsx-7 pipeline integration)

Maps to: R4, R5 (batch dedup), R6 (batch can hit merged cells).

#### Issue I2.1 — Batch shape auto-detection

Use Case: **Distinguish flat-array vs xlsx-7 envelope**.

- **Main scenario:**
  1. `--batch path.json` is supplied (or `-` for stdin).
  2. **Pre-parse size cap:** `Path(path).stat().st_size > 8 MiB` → exit 2 `BatchTooLarge` with `details.size_bytes` (m2). For stdin, the cap is enforced post-read by buffering up to 8 MiB and rejecting if more remains.
  3. Load JSON; inspect root type.
  4. `list` → flat-array shape; iterate items as `{cell, author, text, [initials], [threaded]}`.
  5. `dict` with keys `{ok, summary, findings}` → xlsx-7 envelope shape; iterate `findings`.
  6. Anything else → exit 2 `InvalidBatchInput`.
- **Acceptance criteria:**
  - ✅ Both shapes produce the same internal `BatchRow` list before write.
  - ✅ Mistyped envelope (missing `findings` key) → typed `InvalidBatchInput` envelope, not a crash.
  - ✅ E2E `BatchTooLarge`: 9 MiB JSON file → exit 2 `BatchTooLarge` envelope; size measured pre-parse via `Path.stat().st_size` (m2).

#### Issue I2.2 — Envelope-mode field mapping

Use Case: **Hydrate BatchRow from xlsx-7 finding**.

- **Main scenario:**
  1. `cell ← finding.cell`.
  2. `text ← finding.message`.
  3. `author ← --default-author` (REQUIRED in envelope mode; else exit 2 `MissingDefaultAuthor`).
  4. `initials ← first letter of each whitespace-separated token in --default-author`.
  5. `threaded ← --default-threaded` (default `false`).
- **Alternative scenarios:**
  - **A2.2.a:** Finding has `row: null` (group-finding) → SKIP, increment `summary.skipped_grouped` in stderr report.
- **Acceptance criteria:**
  - ✅ E2E "envelope-mode": pass an xlsx-7 output file → workbook gains exactly N comments where N = `findings | filter(row != null) | count`.
  - ✅ Unit test for skipped-grouped counter.

#### Issue I2.3 — Batch dedup & no-collision guarantees

Use Case: **Insert 50 comments without rId / shape-ID / `o:idmap` collisions**.

- **Main scenario:**
  1. **Pre-scan once** across the whole workbook before any write:
     - existing `<o:idmap data="...">` values across all `vmlDrawing*.xml` parts → `idmap_used: set[int]`;
     - existing `<v:shape id="_x0000_sNNNN">` integers across all VML parts → `spid_used: set[int]`;
     - existing `<authors>/<author>` displayName lists per `commentsN.xml` (case-sensitive — m5);
     - existing `<person>` displayNames in `xl/persons/personList.xml` if present.
  2. Allocate fresh `<o:idmap data=N>` for each NEW vmlDrawing part as `max(idmap_used)+1`, `+2`, … . Allocate fresh `o:spid` integers as `max(spid_used)+1`, `+2`, … (mirrors Excel's own `_x0000_s1025`-then-`_x0000_s1026` allocator).
  3. Single open/save cycle (no re-unpack per row); rels and Content_Types updates are applied incrementally to the in-memory model and serialised once.
- **Acceptance criteria:**
  - ✅ E2E "batch-50": 50 comments across 3 sheets → `office/validate.py` exits 0; no two `<v:shape>` share `o:spid`; no two `vmlDrawing*.xml` parts share an `<o:idmap data>` value.
  - ✅ E2E "batch-50-with-existing-vml": same as above but starting from a workbook that already has `vmlDrawing1.xml` with `<o:idmap data="1"/>` and `_x0000_s1025` — produced workbook keeps existing values intact and new ones use disjoint integers.
  - ✅ Unit test for both collision scanners.
  - ✅ MX-A guard (C3): `--cell --batch` together → `UsageError` envelope (M8).

### Epic E3 — Cross-cutting hardening

Maps to: R7, R8.

#### Issue I3.1 — Encryption / macro / same-path / json-errors gates

Use Case: **Match cross-3/4/5/7-H1 contracts byte-for-byte with docx**.

- **Main scenario:**
  1. `assert_not_encrypted(input)` → exit 3 `EncryptedFileError`.
  2. `warn_if_macros_will_be_dropped(input, output, sys.stderr)` for `.xlsm` → `.xlsx` paths.
  3. `Path(input).resolve() == Path(output).resolve()` → exit 6 `SelfOverwriteRefused` (catches symlinks).
  4. `--json-errors` routes ALL failure paths through the `_errors.report_error` helper (schema `v=1`).
- **Acceptance criteria:**
  - ✅ E2E "encrypted-input → exit 3" envelope.
  - ✅ E2E ".xlsm preserves macros + warns".
  - ✅ E2E "same-path → exit 6" (file path AND symlink).
  - ✅ Argparse usage errors emit JSON envelope when `--json-errors` is set (`type:"UsageError"`).

#### Issue I3.2 — Output validates clean

Use Case: **Generated file passes office/validate.py and xlsx_validate.py**.

- **Acceptance criteria:**
  - ✅ Every E2E that produces a file ALSO runs `office/validate.py` and `xlsx_validate.py --fail-empty` against it.

### Epic E4 — Honest-scope regression locks + Docs

Maps to: R9, R10.

#### Issue I4.1 — Honest-scope regression tests

Use Case: **Lock the v1 limitations so they can't silently grow into bugs**.

- **Main scenario:**
  1. Tests assert `parentId` is NOT present on threaded comments (R9.a).
  2. Tests assert body is plain text (R9.b) — no rich-run wrappers.
  3. Tests assert default VML anchor (R9.c).
  4. Goldens are agent-output-only — never round-tripped through Excel (R9.d). `tests/golden/README.md` documents this protocol explicitly: "DO NOT open these files in Excel. Excel may silently mutate legacy → threaded on save and break the goldens. To regenerate, re-run `xlsx_add_comment.py` with the documented fixture inputs and `--date` pinned" (m4).
  5. Test asserts `--threaded` does NOT accept `--unpacked-dir` (R9.g — feature deferred to v2).
- **Acceptance criteria:**
  - ✅ Each limitation has a dedicated unit/E2E test named `Test*HonestScope*`.
  - ✅ `tests/golden/README.md` exists and is referenced from `tests/test_e2e.sh`.

#### Issue I4.2 — Skill docs + reference

Use Case: **Make the script discoverable through SKILL.md**.

- **Main scenario:**
  1. `skills/xlsx/SKILL.md` §2 capabilities adds the comment-insertion bullet.
  2. §4 Script Contract adds the CLI signature (full flag list, mirrors §2.5 of this TASK).
  3. §10 Quick Reference table adds a row using the existing two-column schema (`| Task | Command |`) — m6.
  4. §12 Resources adds the script + new reference doc.
  5. `skills/xlsx/references/comments-and-threads.md` describes OOXML mapping, A1-syntax, honest-scope, **and the C1 OOXML pitfalls (`<o:idmap data>` workbook-wide vs `o:spid` per-shape)**.
  6. `examples/comments-batch.json` ships a tiny illustrative batch (flat-array shape, ≤ 5 rows).
- **Acceptance criteria:**
  - ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
  - ✅ `references/comments-and-threads.md` is linked from SKILL.md §12.
  - ✅ §10 Quick Reference row added with two-column shape: `\| Insert comment(s) \| python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --cell A5 --author "..." --text "..." [--threaded]` (or, for batch use, `python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --batch findings.json --default-author "..."`) `\|`.

## 4. Non-functional Requirements

### Performance
- Insertion of 1 comment on a ~10 MB workbook (~50 sheets, ~1k rows each) MUST complete in ≤ 5 s on a laptop, including unpack/pack roundtrip. (Reference: existing `xlsx_add_chart.py` benchmark on a similar fixture.)
- Batch-50 MUST complete in ≤ 8 s on the same fixture (single unpack/pack cycle).

### Correctness / Compatibility
- Output validates under both `office/validate.py` AND Excel 365 / LibreOffice 24+ (manual spot-check on at least one fixture per release).
- Pre-existing comments preserved byte-equivalent (XML diff: only added nodes).
- `.xlsm` macros (`xl/vbaProject.bin`) preserved when output extension is `.xlsm`.

### Security
- Input is unpacked with `office/unpack.py` (existing zip-bomb / path-traversal protections — already in place).
- JSON batch input is parsed with `json` (stdlib); size capped at 8 MiB to avoid OOM (reject with `BatchTooLarge` envelope).
- No remote fetches; no shell execution; no `os.system`.
- Author / text strings inserted into XML via lxml `etree.SubElement` + `.text` assignment (XML-escaping handled by lxml — NOT string concat).

### Cross-skill compatibility
- Strict adherence to **CLAUDE.md §2** office-shared rules: any change under `skills/docx/scripts/office/` MUST replicate to xlsx & pptx; xlsx-6 SHOULD NOT need such changes (operates only on xlsx-specific OOXML parts), but if it does, the protocol is mandatory.

## 5. Constraints and Assumptions

### Technical constraints
- Python ≥ 3.10 (project baseline).
- Dependencies already in `skills/xlsx/scripts/requirements.txt`: `openpyxl`, `lxml`, `defusedxml`. **No new runtime deps**.
- Implementation goes through `office/unpack` + `lxml` direct edit + `office/pack` (mirrors `docx_add_comment.py`'s pattern). **NOT** through openpyxl's `Comment` API — openpyxl's API does not support threaded comments and produces non-deterministic VML.
- License scope: the new file inherits `skills/xlsx/LICENSE` (Proprietary).

### Business constraints
- v1 ships within the same VDD pass; v2 (`parentId` reply chains, rich-text, custom VML offsets) is a separate backlog item — do NOT silently expand scope.

### Assumptions
- `personList.xml` is the only blocker for Excel-365 thread rendering — confirmed by xlsx-rules-format §13.2 cross-ref noted in the backlog row. Blueprint test "thread renders in Excel 365" is a manual spot-check, NOT an E2E.
- Excel 365 may silently rewrite legacy → threaded on save → **goldens stay agent-only**, never round-tripped through Excel. Test fixture `tests/golden/README.md` documents this protocol (m4).
- VML shape geometry (default anchor) is acceptable; users complaining about positioning go to v2.
- **"First sheet" rule (M2):** `<sheet>` order in `xl/workbook.xml`, **filtering out `state="hidden"` and `state="veryHidden"`** — i.e. "first VISIBLE sheet". A workbook with all sheets hidden → exit 2 `NoVisibleSheet`. Explicit qualifier (`Hidden!A1`) bypasses the visibility filter and emits an info-level note.
- **Sheet-name lookup is case-sensitive.** `--cell sheet2!A1` against `<sheet name="Sheet2">` → exit 2 `SheetNotFound` with `details.suggestion: "Sheet2"` (M3).

## 6. Open Questions

> **Architecture-blockers (must be closed in ARCHITECTURE.md before
> development):** Q2, Q5, Q7. The remainder are tractable as default
> decisions to be locked by the Architect.

- **Q2 — Empty-text policy?** What if `text == ""` or whitespace-only? Reject with `EmptyCommentBody` envelope (exit 2), or accept silently? (Recommendation: REJECT — empty comments are almost always a bug, mirrors `docx_add_comment.py`'s `--comment` required-non-empty check.) **Status: ARCHITECTURE-BLOCKER (affects CLI surface).**
- **Q3 — `--dry-run`?** Should the script support a dry-run mode (parse + plan, no write)? (Recommendation: NO for MVP — out of scope, adds surface without payoff. Trivial to add later if asked.)
- **Q4 — `BatchTooLarge` cap?** Confirm 8 MiB cap on batch JSON. xlsx-7 typical envelope is ≤ 1 MiB even at 100k findings, so 8 MiB is generous. (Recommendation: 8 MiB. AC already locked in I2.1.)
- **Q5 — Date attribute?** Legacy `<comment>` has no native timestamp; threaded `<threadedComment>` has `dT="ISO-8601"`. Default to `datetime.now(timezone.utc).isoformat()`? Or accept `--date` for determinism in tests? (Recommendation: BOTH — default to UTC now, allow `--date ISO` override for determinism, mirrors `docx_add_comment.py --date`.) **Status: ARCHITECTURE-BLOCKER (affects CLI surface — `--date` flag).**
- **Q6 — Person userId fallback?** Spec says `userId="<author lowercase>"`. For non-ASCII (Cyrillic, CJK, German ß) `str.lower()` and `str.casefold()` differ. (Recommendation: `str.casefold()` — already wired into I1.4 step 4 + AC m1 lock; document as honest-scope if any downstream tool complains.)
- **Q7 — Threaded mode write semantics: legacy stub or threaded-only?** When `--threaded` is set, do we ALSO write a legacy `<comment>` stub (Excel-365 fidelity — Option A) or ONLY `xl/threadedComments<M>.xml` + `xl/persons/personList.xml` (Option B, minimal)? Backlog mandates only that **personList is obligatory when threaded is used**, leaving the legacy-stub policy open. Affects `--no-threaded` semantics, R5 duplicate-cell rules, and the I1.4 main-scenario step 1. (Recommendation: **Option A** — Excel itself writes both parts when it creates a threaded comment, so fidelity is the safer default; `--no-threaded` then *suppresses* the threaded part, mirroring Excel's own toggling behaviour.) **Status: ARCHITECTURE-BLOCKER (affects R5, I1.4, CLI surface).**

> **Closed by this revision** (no longer open):
> - Q1 (separate `--default-initials`): moved to R9.f as v2-deferred, NOT MVP — fixes M5.
