# Development Plan: Task 008 — docx-6.5 + docx-6.6 — `--insert-after` Asset Relocators

> **Status:** DRAFT (Planner phase output, awaiting plan-reviewer gate).
>
> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 008, APPROVED by task-reviewer (no CRITs; 8 MAJORs fixed).
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §12 — APPROVED by architecture-reviewer (no CRITs; 4 MAJORs + 4 minors fixed).
> - **Predecessor PLAN.md** archived at [`docs/plans/plan-006-docx-replace.md`](plans/plan-006-docx-replace.md).
>
> **Decomposition shape (locked by ARCH §12.11):** **8 sub-tasks** —
> 1 Stub-First scaffolding task (Stage 0 / Phase 1) + 1 security-primitive
> task (Stage 1a) + 6 logic tasks (Stage 1b / Phase 2) + 1 finalization
> task (Stage 2).
>
> **Dependencies (locked by ARCH §12.11):** 008-01a precedes everything;
> 008-01b precedes 008-02 + 008-03 (path-traversal guard is a prereq for
> F12 + F13); 008-02 precedes 008-03 (rid_offset / `_merge_relationships`
> consumed by `_copy_nonmedia_parts`); 008-04 precedes 008-05 (signature
> change must land before E2 wiring); 008-05 precedes 008-06; 008-06
> precedes 008-07; 008-07 precedes 008-08.

---

## Task Execution Sequence

### Stage 0 — Stub-First Scaffolding (Phase 1: Red E2E tests + stubs Green)

- **Task 008-01a** — `_relocator.py` skeleton + `RelocationReport` dataclass + Stub-First scaffolding
  - RTM Coverage (preparatory, no logic): module surface only — sets up the call-sites for R1–R15 + R3.5.
  - Description File: [`docs/tasks/task-008-01a-relocator-skeleton.md`](tasks/task-008-01a-relocator-skeleton.md)
  - Priority: Critical
  - Dependencies: none
  - Gate: existing docx-6 unit + E2E tests pass unchanged (TASK §7 G1 partial).

### Stage 1a — Security Primitive (Phase 2: F16 logic green)

- **Task 008-01b** — `_assert_safe_target` + path-traversal unit tests
  - [F16] Implements `_assert_safe_target` security primitive (TASK §3.2; M7 from TASK review).
  - Description File: [`docs/tasks/task-008-01b-assert-safe-target.md`](tasks/task-008-01b-assert-safe-target.md)
  - Priority: Critical
  - Dependencies: 008-01a
  - Gate: 5 new unit tests green (relative OK, absolute reject, `..` reject, drive-letter reject, outside-base reject); T-docx-insert-after-path-traversal still failing (no wiring yet — proves test scaffolding is real).

### Stage 1b — Logic Implementation (Phase 2: Epic E1 then Epic E2)

#### Epic E1 — Image / Relationship Relocator (docx-6.5)

- **Task 008-02** — Image relocator core (F10 + F11 + F12 + R1–R5)
  - [R1] Media file copy with `insert_` prefix and collision-safe counter loop (F10).
  - [R2] Max-rId scan over base rels (F11).
  - [R3] Append mergeable relationships to base rels with offset + path-traversal guard (F12).
  - [R4] Remap `r:embed/r:link/r:id/r:dm/r:lo/r:qs/r:cs` inside cloned `<w:p>` blocks (`_remap_rids_in_clones`).
  - [R5] Merge `[Content_Types].xml` `<Default Extension>` entries (`_merge_content_types_defaults`).
  - Description File: [`docs/tasks/task-008-02-image-relocator.md`](tasks/task-008-02-image-relocator.md)
  - Priority: High
  - Dependencies: 008-01a, 008-01b
  - Gate: ≥ 15 new unit tests covering R1–R5 green; existing docx-6 tests still green.

- **Task 008-03** — Non-media part copy (F13 + R3.5)
  - [R3.5] Copy chart (`chartN.xml` + `chartN.xml.rels`), OLE (`oleObject*`), and SmartArt (`diagrams/*`) parts from insert to base; rename only on collision; copy sibling `_rels/*.rels` verbatim (D7).
  - Includes the two helpers `_read_rel_targets` and `_apply_nonmedia_rename_to_rels` (added in §12.6 surface).
  - Description File: [`docs/tasks/task-008-03-nonmedia-parts.md`](tasks/task-008-03-nonmedia-parts.md)
  - Priority: High
  - Dependencies: 008-02
  - Gate: 5 new unit tests (chart copy, OLE copy, SmartArt copy, sibling-rels verbatim, collision-rename) green.

- **Task 008-04** — `_extract_insert_paragraphs` signature change + E1 wiring + R6
  - [R6] Widen `_extract_insert_paragraphs(insert_tree_root, base_tree_root) -> tuple[clones, RelocationReport]`; delete R10.b WARNING line in `_actions.py`; thread `base_tree_root` from `_do_insert_after` caller.
  - Wires `relocator.relocate_assets(...)` into `_extract_insert_paragraphs`.
  - Rewrites E2E `T-docx-insert-after-image-warns` → GREEN-path test (image relocated, no WARNING).
  - Adds new E2E `T-docx-insert-after-image-relocated` (TASK §7 G2).
  - Description File: [`docs/tasks/task-008-04-e1-wiring.md`](tasks/task-008-04-e1-wiring.md)
  - Priority: Critical
  - Dependencies: 008-03
  - Gate: G2 + G5 (image-relocated + rewritten warn cases) green; G1 holds for all other Task 006 E2E cases.

#### Epic E2 — Numbering Relocator (docx-6.6)

- **Task 008-05** — Numbering relocator core (F14 + F15 + R9–R13)
  - [R9] Read insert tree `word/numbering.xml`.
  - [R10] Compute `anum_offset` and `num_offset` from base.
  - [R11] Clone + offset-shift `<w:abstractNum>` + `<w:num>` into base, preserving ECMA-376 §17.9.20 ordering (abstractNum-before-num).
  - [R12] If base has no `numbering.xml`: install insert's verbatim and call `_ensure_numbering_part`.
  - [R13] Rewrite `<w:numId w:val>` inside cloned `<w:p>` blocks (`_remap_numid_in_clones`).
  - Description File: [`docs/tasks/task-008-05-numbering-relocator.md`](tasks/task-008-05-numbering-relocator.md)
  - Priority: High
  - Dependencies: 008-04
  - Gate: ≥ 10 unit tests including the ECMA-376 §17.9.20 ordering regression-lock green.

- **Task 008-06** — E2 wiring + R14
  - [R14] Call numbering relocator after image relocator in `relocate_assets`; delete R10.e WARNING line.
  - Rewrites E2E `T-docx-numid-survives-warning` → GREEN-path test (list rendered with bullets/numbers, no WARNING).
  - Adds new E2E `T-docx-insert-after-numbering-relocated` (TASK §7 G3).
  - Adds new E2E `T-docx-insert-after-image-and-numbering` (TASK §7 G4 — E1+E2 integration).
  - Description File: [`docs/tasks/task-008-06-e2-wiring.md`](tasks/task-008-06-e2-wiring.md)
  - Priority: Critical
  - Dependencies: 008-05
  - Gate: G3 + G4 + G5 (numbering-relocated + image-and-numbering + rewritten numid case) green.

### Stage 1c — Security E2E + Q-A2 + Idempotency (Phase 2 close)

- **Task 008-07** — Path-traversal E2E + success-line annotation + idempotency unit test
  - [R15.e] New E2E `T-docx-insert-after-path-traversal` (TASK §7 G11): malicious insert rels with `Target="../../etc/passwd"` → exit 1 `Md2DocxOutputInvalid`.
  - Q-A2 success-line annotation: append `[relocated K media, A abstractNum, X numId]` to stderr success line when any count > 0; suppress when all zero (back-compat for plain-text inserts).
  - Q-A3 idempotency unit test: `test_relocator_idempotent_on_same_inputs`.
  - `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` run hermetic (TASK §7 G10).
  - Description File: [`docs/tasks/task-008-07-path-traversal-success-line.md`](tasks/task-008-07-path-traversal-success-line.md)
  - Priority: Medium
  - Dependencies: 008-06
  - Gate: G10 + G11 green.

### Stage 2 — Documentation, Backlog & Cross-Skill Replication (Phase 2 finalization)

- **Task 008-08** — Docs + backlog + validator + cross-skill `diff -q`
  - [R15.f] Update `SKILL.md` (`docx_replace.py` row: only R10.a remains in honest scope; image + numbering + chart + OLE + SmartArt relocated).
  - [R15.f] Flip `docs/office-skills-backlog.md` rows `docx-6.5` and `docx-6.6` to `✅ DONE 2026-05-12`.
  - [R15.f] Update `skills/docx/scripts/.AGENTS.md` with docx-6.5/6.6 row + sync LOC + test counts.
  - Update `docx_replace.py --help` (remove "image r:embed not wired" / "<w:numId> rendering as plain text"; optionally add one line on relocation).
  - Run `validate_skill.py skills/docx` → exit 0 (TASK §7 G8).
  - Run all 12 `diff -q` cross-skill invocations → silent (TASK §7 G7).
  - **MIN-5 propagation:** while editing ARCH §9 "eleven (actual count 12)" reconciliation NIT n1 — replace with "12" everywhere.
  - Description File: [`docs/tasks/task-008-08-docs-backlog.md`](tasks/task-008-08-docs-backlog.md)
  - Priority: Medium
  - Dependencies: 008-07
  - Gate: G6 + G7 + G8 + G9 green.

---

## RTM Coverage Matrix

| RTM ID (TASK §5) | Sub-feature anchor | Closing task |
|---|---|---|
| **R1** (Media file copy with collision-safe prefix) | F10 `_copy_extra_media` | 008-02 |
| **R2** (Max-rId scan over base rels) | F11 `_max_existing_rid` | 008-02 |
| **R3** (Append mergeable rels with offset + path guard) | F12 `_merge_relationships` (with R3.(g) path-traversal call) | 008-02 (R3.a-f) + 008-01b (R3.(g) primitive in F16) |
| **R3.5** (Non-media part copy) | F13 `_copy_nonmedia_parts` + `_read_rel_targets` + `_apply_nonmedia_rename_to_rels` | 008-03 |
| **R4** (Remap `r:embed/r:link/r:id` in clones) | `_remap_rids_in_clones` | 008-02 |
| **R5** (Merge Content-Types `<Default>`) | `_merge_content_types_defaults` | 008-02 |
| **R6** (Wire E1 relocator into `_extract_insert_paragraphs`) | `_actions.py` signature change | 008-04 |
| **R7** (E1 unit tests) | `test_docx_relocator.py` E1 tests | 008-01a (scaffolding) + 008-01b (F16 tests Green) + 008-02 (E1 core Green) + 008-03 (non-media Green) |
| **R8** (E1 E2E test `T-docx-insert-after-image-relocated`) | `tests/test_e2e.sh` | 008-04 |
| **R9** (Read insert numbering.xml) | F14 part 1 | 008-05 |
| **R10** (Compute anum/num offsets from base) | F14 part 2 | 008-05 |
| **R11** (Clone + offset-shift defs; ECMA-376 §17.9.20 order) | F14 part 3 | 008-05 |
| **R12** (Install verbatim if base has no numbering) | F14 + `_ensure_numbering_part` | 008-05 |
| **R13** (Rewrite `<w:numId w:val>` in clones) | F15 `_remap_numid_in_clones` | 008-05 |
| **R14** (Wire E2 relocator + delete R10.e WARNING) | `relocate_assets` E2 branch | 008-06 |
| **R15** (E2 unit + E2E tests + integration + path-traversal + docs sync) | `test_docx_relocator.py` E2; `T-docx-insert-after-numbering-relocated`; `T-docx-insert-after-image-and-numbering`; `T-docx-insert-after-path-traversal`; SKILL.md / backlog / .AGENTS.md | 008-05 + 008-06 + 008-07 + 008-08 |

**Coverage check:** Every RTM row maps to ≥ 1 closing task. The 16
RTM rows distribute as: 008-02 owns R1+R2+R3+R4+R5; 008-03 owns R3.5;
008-04 owns R6+R8; 008-05 owns R9+R10+R11+R12+R13; 008-06 owns R14;
008-01a + 008-02 + 008-03 + 008-05 + 008-06 collectively own R7
(scaffolding + Green per epic); 008-08 owns R15.f docs items. No
gaps; no double-allocation.

---

## Use Case Coverage

| Use Case (TASK §2) | Tasks |
|---|---|
| **UC-1** — `--insert-after` with image in MD source | 008-02, 008-03, 008-04 |
| **UC-2** — `--insert-after` with numbered/bulleted list in MD source | 008-05, 008-06 |
| **UC-3** — UC-1 + UC-2 integration | 008-06 (E2E `T-docx-insert-after-image-and-numbering`) |
| **UC-4** — Backward-compat regression (plain text, no rels) | 008-04 + 008-06 (regression assertion via existing T-docx-insert-after-{file,stdin,empty-stdin,all-duplicates}) |

---

## Phase-Boundary Gates

Each sub-task MUST pass the following before its commit lands:

| Gate | Pass condition | Owner sub-task |
|---|---|---|
| **G-Stub** | After 008-01a: `_relocator.py` importable; `python3 -m unittest discover -s skills/docx/scripts/tests -p "test_docx_relocator.py"` collects ≥ 25 skipped tests; existing 108 docx-6 unit tests + 24 E2E cases pass unchanged. | 008-01a |
| **G-F16** | After 008-01b: 5 `test_assert_safe_target_*` tests green; details.reason tokens match the four cases. | 008-01b |
| **G-E1-core** | After 008-02: ≥ 15 E1 unit tests green; F10–F12 + R4 + R5 helpers implemented. | 008-02 |
| **G-E1-nonmedia** | After 008-03: 5 non-media-copy unit tests green; F13 + helpers implemented. | 008-03 |
| **G-E1-wiring** | After 008-04: TASK §7 G2 + G5 (image-relocated + rewritten warn case) green; `_extract_insert_paragraphs` new signature live. | 008-04 |
| **G-E2-core** | After 008-05: ≥ 10 E2 unit tests green, including ECMA-376 §17.9.20 ordering regression-lock. | 008-05 |
| **G-E2-wiring** | After 008-06: TASK §7 G3 + G4 + G5 (numbering + image-and-numbering + rewritten numid case) green. | 008-06 |
| **G-Security-E2E** | After 008-07: TASK §7 G10 + G11 green (POST_VALIDATE hermetic; path-traversal test exit 1). | 008-07 |
| **G-Finalize** | After 008-08: TASK §7 G6 + G7 + G8 + G9 green. | 008-08 |

---

## Acceptance Gates Map (TASK §7 ↔ closing task)

| TASK §7 Gate | Pass condition (TASK §7) | Closing task |
|---|---|---|
| **G1** All Task 006 E2E cases unchanged except 2 rewritten | 22 unchanged + 2 rewritten = 24 passing | 008-04 + 008-06 |
| **G2** `T-docx-insert-after-image-relocated` green | E2E exit 0 + assertions in TASK §2.1 hold | 008-04 |
| **G3** `T-docx-insert-after-numbering-relocated` green | E2E exit 0 + assertions in TASK §2.2 hold | 008-06 |
| **G4** `T-docx-insert-after-image-and-numbering` green | E2E exit 0 + UC-3 assertions | 008-06 |
| **G5** Rewritten E2E cases assert GREEN path | T-docx-insert-after-image-warns + T-docx-numid-survives-warning both pass on GREEN path | 008-04 (image) + 008-06 (numbering) |
| **G6** Unit-test suite: ≥ 25 new tests; ≥ 100 total | `python3 -m unittest discover` exit 0 + count assertions | 008-08 |
| **G7** All 12 `diff -q` invocations silent | `bash` cross-skill replication check produces zero output | 008-08 |
| **G8** `validate_skill.py skills/docx` exit 0 | Script exit code 0 | 008-08 |
| **G9** Backlog + SKILL.md + .AGENTS.md updated | git diff shows expected updates | 008-08 |
| **G10** `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` exit 0 | Hermetic env-var-on run exit 0 | 008-07 |
| **G11** Path-traversal regression test | `T-docx-insert-after-path-traversal` exits 1 with `Md2DocxOutputInvalid` envelope | 008-07 |

---

## Open-Question Closure Trail

| Q | Section in TASK | Section in ARCH §12 | Closing task |
|---|---|---|---|
| **Q-A1** Module placement | TASK §6.1 | §12.1, §12.2 (single `_relocator.py` sibling) | Closed in ARCH §12; ratified by 008-01a (module created with single-file layout) |
| **Q-A2** Success-summary annotation | TASK §6.1 | §12.1, §12.9 (annotate when ≥ 1 asset) | 008-07 |
| **Q-A3** Idempotency unit test | TASK §6.1 | §12.1 (included) | 008-07 |
| **Q-A4** Chart sub-rels recursion | TASK §6.1 | §12.1 (verbatim copy, D7 ratified) | Closed in ARCH §12; ratified by 008-03 (sibling rels copied verbatim, no recursion) |

---

## Honest-Scope Carry-Forward (TASK §9 + ARCH §10)

After Task 008 merges, the honest-scope catalogue is **shrunk**:

| Honest-scope item | Before docx-008 | After docx-008 |
|---|---|---|
| **R10.a** (cross-run anchor) | Locked | **Untouched** (preserved) |
| **R10.b** (image relocation gap) | Locked | **CLOSED** by 008-04 (warning deleted, image relocated) |
| **R10.c** (last-paragraph deletion) | Locked | **Untouched** (preserved) |
| **R10.d** (--all --delete-paragraph blast-radius) | Locked | **Untouched** (preserved) |
| **R10.e** (numbering relocation gap) | Locked | **CLOSED** by 008-06 (warning deleted, list rendered) |
| **ARCH §10 A1** | Locked | **Untouched** |
| **ARCH §10 A2** | Locked | **CLOSED** by §12 (full relocation shipped) |
| **ARCH §10 A3** | Already closed (docx-6.7) | No-op |
| **ARCH §10 A4** | Locked | **Untouched** |
| **ARCH §10 A5** | Already closed (UC-4 shipped in 006-07b) | No-op |
| **TASK §9 H1** (multi-level SmartArt sub-rels) | NEW (introduced by docx-008) | Documented v3 ticket |
| **TASK §9 H2** (hyperlink validation) | NEW | YAGNI v3 |
| **TASK §9 H3** (embedded fonts) | NEW | Out of backlog scope |
| **TASK §9 H4** (media dedup) | NEW | YAGNI v3 |
| **TASK §9 H5** (insert tree `<Override>` parts) | NEW | v3 ticket |

---

## Stub-First Methodology Application

| Phase | Sub-tasks | Output |
|---|---|---|
| **Phase 1 — Stubs & Tests (Red → Green)** | 008-01a | New module `_relocator.py` with all 13 functions as stubs returning zero/empty defaults. `test_docx_relocator.py` with ≥ 25 explicitly-skipped tests (`@unittest.skip("stub-first; logic lands in 008-02..008-06")`). |
| **Phase 2 — Logic Implementation (Green replacing stubs)** | 008-01b, 008-02, 008-03, 008-04, 008-05, 008-06, 008-07 | Per-sub-task: unskip 4–15 tests at a time as the corresponding logic lands. By 008-07's commit, all 25+ tests are unskipped and green. |
| **Phase 3 — Finalization** | 008-08 | Documentation, backlog, validator, cross-skill replication. |

**Critical Stub-First invariant:** every test scaffolding written in
008-01a uses `@unittest.skip` (NOT `assert True`); each implementation
sub-task removes the `@unittest.skip` decorator AS PART of landing the
logic. This ensures the Red→Green transition is auditable per
sub-task.

---

## File-Touchpoint Summary

| File | Action | Closing task(s) |
|---|---|---|
| `skills/docx/scripts/_relocator.py` | **CREATE** (new file, ≤ 500 LOC) | 008-01a (skeleton) + 008-01b (F16) + 008-02 (F10–F12, helpers) + 008-03 (F13, helpers) + 008-05 (F14, F15, `_ensure_numbering_part`) |
| `skills/docx/scripts/_actions.py` | **EDIT** (signature widen + WARNING delete) | 008-04 (E1 wiring) + 008-06 (E2 wiring) |
| `skills/docx/scripts/docx_replace.py` | **EDIT** (success-line annotation + `--help` text) | 008-07 (success-line) + 008-08 (`--help` polish) |
| `skills/docx/scripts/tests/test_docx_relocator.py` | **CREATE** (new file) | 008-01a (scaffolding) + 008-01b–008-06 (Green) |
| `skills/docx/scripts/tests/test_docx_replace.py` | **EDIT** (rewrite 2 warn tests as GREEN-path) | 008-04 (image) + 008-06 (numbering) |
| `skills/docx/scripts/tests/test_e2e.sh` | **EDIT** (rewrite 2 cases + add 4 new cases) | 008-04 (image-relocated + rewritten image-warns) + 008-06 (numbering-relocated + image-and-numbering + rewritten numid) + 008-07 (path-traversal) |
| `skills/docx/SKILL.md` | **EDIT** (honest-scope reword) | 008-08 |
| `skills/docx/scripts/.AGENTS.md` | **EDIT** (LOC + test count sync) | 008-08 |
| `docs/office-skills-backlog.md` | **EDIT** (flip 6.5 + 6.6 rows) | 008-08 |
| `docs/ARCHITECTURE.md` | **EDIT** (§9 NIT n1 reconciliation: eleven→12) | 008-08 |

---

## Estimated Effort

| Task | Effort | Notes |
|---|---:|---|
| 008-01a | 1 h | Mechanical stub creation + test scaffolding. |
| 008-01b | 0.5 h | Small, security-critical. 5 unit tests. |
| 008-02 | 2.5 h | Largest E1 task — 5 functions + ≥ 15 unit tests. |
| 008-03 | 1.5 h | F13 + 2 helpers + 5 unit tests. |
| 008-04 | 1.5 h | Signature change touches multiple callers; 2 E2E + 1 rewrite. |
| 008-05 | 2.5 h | Largest E2 task — F14 with ECMA ordering trap; ≥ 10 unit tests. |
| 008-06 | 1.5 h | E2 wiring + 2 E2E (1 new + 1 integration) + 1 rewrite. |
| 008-07 | 1 h | E2E + success-line annotation + idempotency. |
| 008-08 | 1 h | Mechanical docs + backlog + validator. |
| **Total** | **~13 h** | Within the M (Medium) per-row budget of the two backlog items combined. |

---

## References

- [`docs/TASK.md`](TASK.md) — Task 008 specification.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §12 — relocator architecture extension.
- [`docs/plans/plan-006-docx-replace.md`](plans/plan-006-docx-replace.md) — predecessor PLAN (archived).
- [`skills/docx/scripts/docx_merge.py`](../skills/docx/scripts/docx_merge.py) lines 109–544 — pattern source for relocator helpers.
- [`skills/docx/scripts/_actions.py`](../skills/docx/scripts/_actions.py) lines 255–358 — `_extract_insert_paragraphs` + `_do_insert_after` (sites of edit in 008-04 / 008-06).
- [`skills/docx/scripts/tests/test_e2e.sh`](../skills/docx/scripts/tests/test_e2e.sh) lines 1969 + 2239 — existing R10.b + R10.e regression-lock cases (sites of rewrite in 008-04 / 008-06).
