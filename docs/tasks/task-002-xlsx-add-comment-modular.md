# TASK: xlsx-6.refactor — Modularize `xlsx_add_comment.py`

## 0. Meta Information

- **Task ID:** 002
- **Slug:** `xlsx-add-comment-modular`
- **Backlog item:** Internal follow-up to xlsx-6 (Task 001). Recorded
  in [`task-001-xlsx-add-comment-master.md`](tasks/task-001-xlsx-add-comment-master.md)
  open-tail decisions: *"User-deferred Task 2.11 (xlsx_add_comment.py
  module split: exceptions/cell_parser/batch/ooxml_editor/merge_dup)"*.
- **Status:** DRAFT v2 (Analysis Phase, VDD — round 2 after task-reviewer round 1).
- **Mode:** VDD (Verification-Driven Development).
- **Skill:** `skills/xlsx/`.
- **License scope:** Proprietary (per-skill `LICENSE`, see CLAUDE.md §3).
- **Predecessor:** Task 001 (xlsx-6) — MERGED. Final-state file is 2339 LOC
  with `# region — F1..F6 + Helpers` markers; this task does **NOT** add
  features, only restructures.
- **Round-1 review:** [`docs/reviews/task-002-review.md`](reviews/task-002-review.md) — APPROVED-WITH-COMMENTS; this revision addresses M1 (full re-export list inlined), M2 (ARCHITECTURE override note added), m1–m3 (RTM Q1/Q2 dependency note, "chain" gloss, AGENTS.md existence verified), and n1–n3 (`__init__.py` policy reconciled, R5.b wording aligned with I11).

## 1. General Description

### Goal
Split [`skills/xlsx/scripts/xlsx_add_comment.py`](../skills/xlsx/scripts/xlsx_add_comment.py)
(2339 LOC, `# region`-delimited monolith) into a **package of cohesive
modules** under `skills/xlsx/scripts/` so that:

1. Each module has a single responsibility (≤ ~500 LOC; the public CLI
   shim stays under 200 LOC).
2. The full **public-facing CLI surface is preserved byte-for-byte**:
   `python3 scripts/xlsx_add_comment.py …` accepts the identical flag
   set, produces identical output workbooks, identical exit codes, and
   identical JSON-error envelopes.
3. **All existing tests pass without rewrites** (112 E2E + 75 unit +
   golden diffs). Test code currently does
   `from xlsx_add_comment import parse_cell_syntax, SheetNotFound, …`
   — those symbols MUST remain importable from `xlsx_add_comment`
   after the split (re-exports from the shim).
4. `validate_skill.py skills/xlsx` continues to exit 0.
5. Future development of xlsx-6 (e.g., R9.f `--default-initials`, R9.g
   `--unpacked-dir`, parentId reply-threads, custom VML offsets) is
   localized to the right module without scrolling 2k+ lines.

### Why now
- File grew from the architecture-budgeted ~1100 LOC (matching
  `docx_add_comment.py`) to **2339 LOC** during xlsx-6 development
  (cross-cutting hardening, batch mode, threaded mode, post-pack
  validation, honest-scope locks). The YAGNI argument in current
  ARCHITECTURE.md §3.1 ("Fragmenting into a sub-package would break
  convention without payoff") is **factually invalidated** by the
  resulting file size: navigation cost on a 2339-LOC monolith is
  measurable.

> **ARCHITECTURE.md override (M2 from round-1 review):** This TASK
> formally **supersedes ARCHITECTURE.md §2.1** ("NOT a multi-module
> package — YAGNI") and **§3.1** ("Fragmenting into a sub-package
> would break this convention without payoff") **for the xlsx skill
> only**. The premise of those sections — that xlsx-6 would land at
> ~1100 LOC like docx — has been falsified by the as-delivered 2339
> LOC. The Architecture phase that follows this TASK MUST update
> §2.1 + §3.1 (and add a Component-S table entry for the new
> `xlsx_comment/` package) to reflect the new decision; this TASK
> is the authoritative input that drives that update. The
> single-file convention remains the rule for `docx_add_comment.py`,
> `xlsx_add_chart.py`, `xlsx_recalc.py`, `xlsx_validate.py`,
> `csv2xlsx.py`, and the pptx scripts — all of which remain under
> 1100 LOC and below the navigability threshold.
- xlsx-7 (`xlsx_check_rules.py`) is the next backlog item and is the
  primary downstream consumer (envelope mode in batch). Stable internal
  APIs reduce coupling risk between the two scripts.
- Honest-scope v2 features (R9.f, R9.g, parentId reply-threads, rich
  text) all touch the OOXML editor region (current F4 ≈ 776 LOC).
  Splitting F4 first means each v2 task lands in a focused file with
  its own tests, instead of bloating a single file past 3k LOC.

### Connection with existing system
- Touches **only** `skills/xlsx/scripts/xlsx_add_comment.py` and a new
  package directory next to it (`skills/xlsx/scripts/xlsx_comment/`,
  see §3 / I1).
- **No changes** to `skills/docx/scripts/office/` or
  `skills/docx/scripts/_soffice.py` → CLAUDE.md §2 office-replication
  protocol does NOT trigger.
- **No changes** to `_errors.py`, `preview.py`, `office_passwd.py` →
  CLAUDE.md §2 cross-skill replication does NOT trigger.
- **No changes** to `requirements.txt`. Same dependency set.
- **No changes** to public CLI surface defined in
  `skills/xlsx/SKILL.md` §4 / §10.

### Reference scope (mirrors `docx_add_comment.py` policy)
`docx_add_comment.py` is 1101 LOC and is **NOT** modular — it stays a
single file because that size remains navigable. `xlsx_add_comment.py`
crossed the navigability threshold during xlsx-6 because it implements
**three superset features** that docx does not have: threaded comments,
batch mode, VML drawing (with the `<o:idmap data>` workbook-wide
invariants). The split does NOT change docx; the office-skills
convention remains "single file when it fits, package when it doesn't".

## 2. Requirements Traceability Matrix (RTM)

Granularity: every Requirement decomposes into ≥ 3 testable sub-features.

> **Q1/Q2 dependency note (m1 from review):** R1.f and R1.j wording
> below assumes Q1 (single-file `ooxml_editor.py` vs `ooxml/`
> sub-package) and Q2 (`cli.py` vs split `cli.py` + `orchestrator.py`)
> close per analyst recommendation (single-file in both cases). If
> the architect picks the alternative for either, the corresponding
> RTM rows + §2.5 file table update before the Planning phase.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | Module decomposition | YES | a) Create `skills/xlsx/scripts/xlsx_comment/` package directory with `__init__.py`; b) Migrate F-Constants region (lines 140-178) to `xlsx_comment/constants.py`; c) Migrate F-Errors region (lines 181-356) to `xlsx_comment/exceptions.py`; d) Migrate F2 region (lines 359-516, cell parser + sheet resolver) to `xlsx_comment/cell_parser.py`; e) Migrate F3 region (lines 519-644, batch loader + `BatchRow`) to `xlsx_comment/batch.py`; f) Migrate F4 region (lines 647-1423, OOXML editor) to `xlsx_comment/ooxml_editor.py` (or sub-package — see Q1); g) Migrate F5 region (lines 1426-1583, merged-cell + duplicate matrix) to `xlsx_comment/merge_dup.py`; h) Migrate F-Helpers region (lines 1586-1663, `_initials_from_author`, `_resolve_date`, `_validate_args`, `_assert_distinct_paths`) to `xlsx_comment/cli_helpers.py`; i) Migrate F1 region (lines 1666-1757, `build_parser`) to `xlsx_comment/cli.py`; j) Migrate F6 region (lines 1760-2339, `main`, `single_cell_main`, `batch_main`, `_post_pack_validate`) to `xlsx_comment/cli.py` (or `xlsx_comment/orchestrator.py` — see Q2). |
| **R2** | Public CLI shim preservation | YES | a) `skills/xlsx/scripts/xlsx_add_comment.py` becomes a **thin shim** (≤ 200 LOC) whose only behaviour is `from xlsx_comment.cli import main` + `if __name__ == "__main__": sys.exit(main())`; b) The shim **also re-exports** every symbol currently imported by the test suite (see §5 list) so `from xlsx_add_comment import parse_cell_syntax` still works without test edits; c) The shim's docstring is migrated to `xlsx_comment/__init__.py` with a one-line summary kept on `xlsx_add_comment.py` pointing at the package; d) The shim retains the `#!/usr/bin/env python3` shebang and remains executable. |
| **R3** | Test backward-compatibility (no test rewrites) | YES | a) Run `./.venv/bin/python -m unittest discover -s tests` — all 75 unit tests pass with **zero edits to test files**; b) Run `bash tests/test_e2e.sh` — all 112 E2E checks pass; c) Re-run E2E with `XLSX_ADD_COMMENT_POST_VALIDATE=1` exported — still passes (post-pack validate path unaffected); d) Goldens at `tests/golden/outputs/` either remain bit-equal OR the structural diff helper (`tests/_golden_diff.py`) reports zero structural delta (UUIDv4 in `<threadedComment id>` is the only honest-scope source of byte-non-determinism, R9.e). |
| **R4** | Internal API stability between modules | YES | a) Each new module declares its public API via `__all__` (explicit list, no leading-underscore symbols cross-module); b) Cross-module imports go through the package root or sibling-module form (`from .exceptions import _AppError`), NOT through the shim (`from xlsx_add_comment import _AppError` is **forbidden** inside the package — would create a re-import cycle); c) The `_AppError` base + 14 typed errors live in `exceptions.py`; every module that raises them imports from there; d) Module-private helpers keep their `_` prefix and are **not** included in `__all__`. |
| **R5** | Documentation & navigation | YES | a) Each new module gets a top-of-file docstring (≤ 30 LOC) explaining responsibility, the F-region it migrated from, and the public API surface; b) `skills/xlsx/scripts/.AGENTS.md` (verified to exist at TASK draft v2 time) is updated by the **developer agent ONLY** (per `artifact-management` SKILL § Local .AGENTS.md "Single Writer" rule) with a "Files" section listing every new module with a one-line responsibility summary; c) `skills/xlsx/SKILL.md` does **NOT** change (the user-facing CLI surface is unchanged); d) `skills/xlsx/references/comments-and-threads.md` gains a brief §6 "Internal module map" pointing at the new package layout (≤ 20 LOC, mainly for future contributors). |
| **R6** | Validator + repo health | YES | a) `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0; b) `git status` after the refactor shows only the expected file moves + the shim + the package + .AGENTS.md edits + the tiny SKILL.md/references edit (R5.d); c) No new dependencies in `requirements.txt`; d) `find skills/xlsx/scripts -type d -name __pycache__ -exec rm -rf {} +` runs clean before commit (no stale bytecode shipped); e) `office/` stays byte-identical across the four office skills (this refactor does not touch it; verified by `diff -qr` per CLAUDE.md §2). |
| **R7** | Reversibility & atomicity | YES | a) The refactor is delivered as a **single self-contained PR or task-chain** (where "chain" refers to a Claude Code per-task chain in this VDD pipeline — multiple atomic tasks landing under one PR via `/vdd-develop-all`) — no half-states landed on `main`; b) `git diff main..HEAD --stat` shows the file moves are clean (no accidental re-formatting of other scripts); c) Migrated code is moved **byte-equivalent where possible** — function bodies are not re-indented, re-flowed, or re-named beyond what the new namespace requires; d) Each module move has a corresponding **unit-level smoke test** that imports the module and calls one symbol — locks the move at the import-graph level even if higher-level tests would mask a regression. |
| **R8** | Honest-scope (v1 of refactor) — explicit non-goals | YES | a) **Behaviour change is forbidden** — no bug fixes, no API tweaks, no new flags. Pure restructuring. Any logic-bug encountered during the move is either reproduced verbatim (with an `# XXX(task-002):` marker) or carved into a separate follow-up TASK; b) `office/` is untouched (CLAUDE.md §2 protocol does NOT activate); c) `_errors.py` / `preview.py` / `office_passwd.py` are untouched (3-skill / 4-skill replication does NOT activate); d) `docx_add_comment.py` and `pptx_*` scripts are untouched (the docx single-file convention stays); e) v2 follow-ups (R9.f `--default-initials`, R9.g `--unpacked-dir`, parentId, rich text) are explicitly **out of scope** and tracked in the post-task open-tail of session state, not implemented here. |

## 2.5 Module surface (authoritative file list)

> **Why this section:** task-reviewer-style C3 — module names + LOC
> budgets MUST be enumerated so the developer is not inventing them
> mid-implementation. The Architect (next phase) closes Q1, Q2, Q3 and
> may reshape this list — until then, this is the analyst's recommendation.

### Files CREATED

| Path | Purpose | LOC budget | Migrated from |
|---|---|---|---|
| `skills/xlsx/scripts/xlsx_comment/__init__.py` | Package marker. Per Q4 recommendation (closed below) the `__init__.py` is **near-empty** — only a 1-line docstring naming the package; **NO** re-exports. The test-compat re-export surface lives on `xlsx_add_comment.py` (the shim), not on the package root, so `from xlsx_comment import parse_cell_syntax` is intentionally NOT supported; programmatic callers use the explicit submodule path (`from xlsx_comment.cell_parser import parse_cell_syntax`). If the architect overturns Q4 in favour of policy B (re-export from `__init__.py`), this row's LOC budget rises to ≤ 60. | ≤ 10 | new |
| `skills/xlsx/scripts/xlsx_comment/constants.py` | XML namespaces, Content-Type strings, Rel-Type strings, `DEFAULT_VML_ANCHOR`, `BATCH_MAX_BYTES`. Pure constants, zero imports beyond stdlib. | ≤ 60 | F-Constants (lines 140-178) |
| `skills/xlsx/scripts/xlsx_comment/exceptions.py` | `_AppError` base + 14 typed errors (`UsageError`, `SheetNotFound`, `NoVisibleSheet`, `InvalidCellRef`, `MergedCellTarget`, `EmptyCommentBody`, `InvalidBatchInput`, `BatchTooLarge`, `MissingDefaultAuthor`, `DuplicateLegacyComment`, `DuplicateThreadedComment`, `SelfOverwriteRefused`, `OutputIntegrityFailure`, `MalformedVml`). | ≤ 220 | F-Errors (lines 181-356) |
| `skills/xlsx/scripts/xlsx_comment/cell_parser.py` | `parse_cell_syntax`, `_load_sheets_from_workbook`, `resolve_sheet`. | ≤ 200 | F2 (lines 359-516) |
| `skills/xlsx/scripts/xlsx_comment/batch.py` | `BatchRow` dataclass, `load_batch` (8 MiB cap, flat-array vs envelope auto-detect, group-finding skip). | ≤ 160 | F3 (lines 519-644) |
| `skills/xlsx/scripts/xlsx_comment/ooxml_editor.py` *or* `xlsx_comment/ooxml/` sub-package (Q1) | Scanners (`scan_idmap_used`, `scan_spid_used`, `_vml_part_paths`, `_parse_vml`), part-counter (`next_part_counter`, `_allocate_new_parts`), cell-ref helpers (`_column_letters_to_index`, `_cell_ref_to_zero_based`), target/path resolution (`_resolve_target`, `_make_relative_target`, `_resolve_workbook_rels`, `_sheet_part_path`, `_sheet_rels_path`), rels/CT (`_open_or_create_rels`, `_allocate_rid`, `_find_rel_of_type`, `_patch_sheet_rels`, `_patch_content_types`), legacy (`ensure_legacy_comments_part`, `add_legacy_comment`, `ensure_vml_drawing`, `add_vml_shape`, `_xml_serialize`), threaded (`ensure_threaded_comments_part`, `ensure_person_list`, `add_person`, `add_threaded_comment`). | ≤ 850 (single-file option) **or** 4 files of ~200 LOC each (sub-package option) | F4 (lines 647-1423) |
| `skills/xlsx/scripts/xlsx_comment/merge_dup.py` | `_parse_merge_range`, `_anchor_of_range`, `resolve_merged_target`, `detect_existing_comment_state`, `_enforce_duplicate_matrix`. | ≤ 200 | F5 (lines 1426-1583) |
| `skills/xlsx/scripts/xlsx_comment/cli_helpers.py` | `_initials_from_author`, `_resolve_date`, `_validate_args`, `_assert_distinct_paths`, `_content_types_path`, `_post_validate_enabled`, `_post_pack_validate`. | ≤ 150 | F-Helpers (lines 1586-1663) + a few from F6 (`_post_pack_validate`, `_post_validate_enabled` at 1768-1844) |
| `skills/xlsx/scripts/xlsx_comment/cli.py` | `build_parser`, `main`, `single_cell_main`, `batch_main` (Q2: may move `single_cell_main`/`batch_main` to a separate `orchestrator.py`). | ≤ 700 | F1 (lines 1666-1757) + F6 (lines 1760-2339) |

### Files MODIFIED (not created)

| Path | Modification |
|---|---|
| `skills/xlsx/scripts/xlsx_add_comment.py` | **Reduce to ≤ 200 LOC**: keep shebang + module docstring (1-line + pointer to package) + re-imports from `xlsx_comment.*` so the **existing test surface keeps working without test edits**, ending with `if __name__ == "__main__": sys.exit(main())`. |
| `skills/xlsx/scripts/.AGENTS.md` (existing — verify) | Add "Files" entries for the new `xlsx_comment/` package per `artifact-management` skill. If file does not exist, create it. |
| `skills/xlsx/references/comments-and-threads.md` | Append §6 "Internal module map" (≤ 20 LOC). Optional but recommended for future contributors. |

### Files NOT MODIFIED (explicit non-touch list — review-evidence)

- `skills/docx/scripts/office/**`, `skills/xlsx/scripts/office/**`,
  `skills/pptx/scripts/office/**`, `skills/pdf/scripts/office/**`
  — CLAUDE.md §2 protocol does NOT activate.
- `skills/{docx,xlsx,pptx,pdf}/scripts/_errors.py` — 4-skill replication
  does NOT activate.
- `skills/{docx,xlsx,pptx,pdf}/scripts/preview.py` — 4-skill replication
  does NOT activate.
- `skills/{docx,xlsx,pptx}/scripts/office_passwd.py` — 3-skill OOXML
  replication does NOT activate.
- `skills/xlsx/SKILL.md` (sections §2/§4/§10/§12) — public CLI is
  unchanged; the §12 link to `references/comments-and-threads.md`
  already exists.
- `skills/xlsx/scripts/requirements.txt` — no new deps.
- `skills/xlsx/scripts/tests/**` — **NO EDITS** to test files; that is
  the whole point of the shim re-exports (R3.a).
- `docs/PLAN.md`, `docs/tasks/task-001-*.md` — historical artifacts of
  Task 001; this task creates its own PLAN.md in the Planning phase.

### Re-export contract (the test-compat surface) — AUTHORITATIVE

> **Source of truth for what the shim MUST re-export.** Derived
> deterministically by a grep of every `from xlsx_add_comment import …`
> statement (single-line and parenthesised multi-line) inside
> `skills/xlsx/scripts/tests/test_xlsx_add_comment.py`, then the
> imported names extracted and de-duplicated. **Total: 35 symbols**
> across constants (9), exceptions (10), and helpers/functions (16).
> Reproducible command:
>
> ```bash
> grep -hE "from xlsx_add_comment import" \
>     skills/xlsx/scripts/tests/test_xlsx_add_comment.py | \
>     awk -F'import' '{print $2}' | tr ',()' ' \n ' | \
>     sed -E 's/\\\\?$//; s/^[[:space:]]+//; s/[[:space:]]+$//' | \
>     awk '/^[A-Za-z_]/ {print}' | sort -u
> ```
>
> The shim re-exports this **exact** symbol set. Adding a new public
> symbol to `xlsx_comment/` does NOT obligate it to land on the shim
> — only the test-imported ones do.

**Re-export list (frozen as of TASK draft v2; developer MUST re-run the
grep at Stage 1 and update this list verbatim if any new symbol has
been added to a test file since this TASK was written; the list, not
the grep, is the canonical contract going forward):**

```python
# In skills/xlsx/scripts/xlsx_add_comment.py — required surface (35 names):

# --- from xlsx_comment.constants (9) ---
from xlsx_comment.constants import (  # noqa: F401
    SS_NS, R_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS,
    THREADED_NS, VML_CT, DEFAULT_VML_ANCHOR,
)
# (R_NS is included even though tests don't directly import it today;
#  excluded from the count above. Tests-only set is the 9 listed:
#  SS_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS, THREADED_NS, VML_CT,
#  DEFAULT_VML_ANCHOR. Developer may trim R_NS if strictly minimising.)

# --- from xlsx_comment.exceptions (10) ---
from xlsx_comment.exceptions import (  # noqa: F401
    SheetNotFound, NoVisibleSheet, InvalidCellRef,
    MergedCellTarget, InvalidBatchInput, BatchTooLarge,
    DuplicateLegacyComment, DuplicateThreadedComment,
    OutputIntegrityFailure, MalformedVml,
)

# --- from xlsx_comment.cell_parser (2) ---
from xlsx_comment.cell_parser import (  # noqa: F401
    parse_cell_syntax, resolve_sheet,
)

# --- from xlsx_comment.batch (1) ---
from xlsx_comment.batch import load_batch  # noqa: F401

# --- from xlsx_comment.ooxml_editor (8) ---
from xlsx_comment.ooxml_editor import (  # noqa: F401
    next_part_counter, scan_idmap_used, scan_spid_used,
    add_person, add_legacy_comment, add_vml_shape,
    _make_relative_target, _allocate_rid, _patch_content_types,
)

# --- from xlsx_comment.merge_dup (2) ---
from xlsx_comment.merge_dup import (  # noqa: F401
    resolve_merged_target, _enforce_duplicate_matrix,
)

# --- from xlsx_comment.cli_helpers (1) ---
from xlsx_comment.cli_helpers import _post_pack_validate  # noqa: F401

# --- from xlsx_comment.cli (1) ---
from xlsx_comment.cli import main  # noqa: F401
```

**Underscore-prefixed symbols on the list**
(`_make_relative_target`, `_allocate_rid`, `_patch_content_types`,
`_enforce_duplicate_matrix`, `_post_pack_validate`) are tested as
internal helpers and therefore must remain importable through the shim.
This is a **conscious exception** to R4.a's "no leading-underscore
symbols cross-module"; tests are not "cross-module" in the normal
sense — they're a third party that observes the shim. R4.a still
applies inside the package itself (modules don't import another
module's `_`-prefixed names; tests do, via the shim).

**Verification:** R3.a requires running the grep above (or the
deterministic equivalent) before AND after the refactor; the resulting
sorted-uniq list must be the **same** before and after. Mismatch → the
shim re-exports list is out of sync and the task is not done.

## 3. Epics & Use Cases

### Epic E1 — Pure structural extraction (R1, R2, R4, R5)

> Maps to: R1 (decomposition), R2 (shim), R4 (internal APIs), R5 (docs).
> The whole epic is "move code without changing it"; verification is
> green tests on top of the unchanged behaviour.

#### Issue I1 — Create the package skeleton

Use Case: **Add the `xlsx_comment/` directory with all module stubs**.

- **Actors:** Developer.
- **Preconditions:** Working tree clean; Task 001 archive sealed.
- **Main scenario:**
  1. `mkdir skills/xlsx/scripts/xlsx_comment`.
  2. Create empty stubs for every module listed in §2.5 (file CREATED
     table) — each stub has only its docstring and `pass` / no symbols.
  3. Add `__init__.py` exporting nothing yet.
  4. Run `./.venv/bin/python -c "import xlsx_comment"` from
     `skills/xlsx/scripts/` — must succeed.
- **Alternative scenarios:**
  - **A1.a:** Q1 chooses sub-package option → `mkdir
    xlsx_comment/ooxml` and split F4 into 4 stub files instead of 1.
- **Postconditions:** Package importable; all tests still pass against
  the **unchanged** `xlsx_add_comment.py`.
- **Acceptance criteria:**
  - ✅ `python3 -c "import xlsx_comment"` exits 0.
  - ✅ `validate_skill.py skills/xlsx` exits 0.
  - ✅ Running existing tests still passes (no behavioural change yet).

#### Issue I2 — Migrate `constants.py` and `exceptions.py`

Use Case: **Move the two leaf modules with zero internal dependencies first**.

- **Main scenario:**
  1. Move F-Constants (lines 140-178 of current file) → `constants.py`
     **byte-equivalent**.
  2. Move F-Errors (lines 181-356) → `exceptions.py`. Replace the
     `# region` markers with module-level docstring + `__all__`.
  3. In `xlsx_add_comment.py`, replace the deleted regions with
     `from xlsx_comment.constants import *` (or explicit names) and
     `from xlsx_comment.exceptions import *`.
  4. Run unit tests + E2E.
- **Alternative scenarios:**
  - **A2.a:** Symbol resolution fails (e.g., `MalformedVml` referenced
    but not imported) → fix the explicit import list, re-test.
- **Acceptance criteria:**
  - ✅ All 75 unit tests pass without test-file edits.
  - ✅ All 112 E2E checks pass.
  - ✅ `git diff` shows ONLY (a) deletion of the two regions in
    `xlsx_add_comment.py`, (b) addition of the two new modules,
    (c) re-imports in the shim. No re-indentation of moved code.

#### Issue I3 — Migrate `cell_parser.py` (F2)

Use Case: **Move the F2 region to a leaf module that depends only on
`exceptions` and `lxml`**.

- **Main scenario:** Same pattern as I2. F2 imports `SheetNotFound`,
  `NoVisibleSheet`, `InvalidCellRef` from `..exceptions`.
- **Acceptance criteria:**
  - ✅ Tests pass.
  - ✅ Re-export contract preserves
    `from xlsx_add_comment import parse_cell_syntax, resolve_sheet,
    SheetNotFound, NoVisibleSheet, InvalidCellRef`.

#### Issue I4 — Migrate `batch.py` (F3)

Use Case: **Move F3 (BatchRow + load_batch).**

- **Main scenario:** Same pattern. Imports `_AppError`,
  `BatchTooLarge`, `InvalidBatchInput`, `MissingDefaultAuthor` from
  `..exceptions`. `BATCH_MAX_BYTES` from `..constants`.
- **Acceptance criteria:** Tests green; shim still resolves the
  symbol set used by tests.

#### Issue I5 — Migrate `ooxml_editor.py` (F4) — **largest move**

Use Case: **Relocate the OOXML editing core**.

- **Preconditions:** Q1 closed by Architecture phase
  (single-file vs `ooxml/` sub-package).
- **Main scenario (single-file option):**
  1. Move F4 (lines 647-1423) → `ooxml_editor.py` byte-equivalent.
  2. Imports: `_AppError`, `MalformedVml` from `..exceptions`;
     `O_NS`, `V_NS`, `X_NS`, `R_NS`, `PR_NS`, `CT_NS`, content-type
     constants from `..constants`.
  3. Update shim re-exports.
- **Alternative scenarios:**
  - **A5.a (sub-package option, Q1=B):** split into
    `ooxml/scanners.py` (`scan_idmap_used`, `scan_spid_used`,
    `next_part_counter`, `_allocate_new_parts`),
    `ooxml/rels.py` (`_resolve_workbook_rels`, `_sheet_part_path`,
    `_sheet_rels_path`, `_open_or_create_rels`, `_allocate_rid`,
    `_find_rel_of_type`, `_patch_sheet_rels`, `_patch_content_types`),
    `ooxml/legacy.py` (`ensure_legacy_comments_part`,
    `add_legacy_comment`, `ensure_vml_drawing`, `add_vml_shape`,
    `_xml_serialize`),
    `ooxml/threaded.py` (`ensure_threaded_comments_part`,
    `ensure_person_list`, `add_person`, `add_threaded_comment`).
- **Acceptance criteria:**
  - ✅ Tests pass (especially the dense F4-touching tests:
    `scan_idmap_used`, `scan_spid_used`, `next_part_counter`,
    `add_person`).
  - ✅ Shim re-exports preserved.
  - ✅ Module-level docstring lists the C1 + M-1 invariants
    (workbook-wide `<o:idmap data>` LIST, workbook-wide `o:spid`
    integers — these are TWO collision domains).

#### Issue I6 — Migrate `merge_dup.py` (F5)

Use Case: **Move F5 (merged-cell + duplicate-cell matrix).**

- **Main scenario:** F5 imports `MergedCellTarget`,
  `DuplicateLegacyComment`, `DuplicateThreadedComment` from
  `..exceptions`. Calls `add_threaded_comment` etc. via
  `..ooxml_editor` imports.
- **Acceptance criteria:** Tests pass.

#### Issue I7 — Migrate `cli_helpers.py` (F-Helpers)

Use Case: **Move the cross-cutting glue (`_initials_from_author`,
`_resolve_date`, `_validate_args`, `_assert_distinct_paths`,
`_post_validate_enabled`, `_post_pack_validate`).**

- **Note:** `_post_pack_validate` and `_post_validate_enabled` are
  currently in F6 region but logically belong with helpers (they're
  pure utilities, not orchestration). Moving them to `cli_helpers.py`
  is a clean-up the analyst recommends; if the architect rules
  otherwise, they stay in `cli.py`.
- **Acceptance criteria:** Tests pass.

#### Issue I8 — Migrate `cli.py` (F1 + F6) — **last move**

Use Case: **Move CLI orchestration (`build_parser`, `main`,
`single_cell_main`, `batch_main`) and reduce the shim to ≤ 200 LOC**.

- **Preconditions:** Q2 closed by Architecture phase (single
  `cli.py` vs split `cli.py` + `orchestrator.py`).
- **Main scenario:**
  1. Move F1 (lines 1666-1757) → `cli.py` (top: argparse).
  2. Move F6 (lines 1760-2339) → `cli.py` (bottom: `main`,
     `single_cell_main`, `batch_main`).
  3. Replace `xlsx_add_comment.py` body with: shebang + 1-line
     docstring + `from xlsx_comment.cli import main` +
     `from xlsx_comment.<modules> import <test-imported names>` +
     `if __name__ == "__main__": sys.exit(main())`.
  4. Run full test suite + `validate_skill.py`.
- **Alternative scenarios:**
  - **A8.a:** `single_cell_main`/`batch_main` extracted to
    `orchestrator.py` per Q2=split. `cli.py` then imports both.
- **Acceptance criteria:**
  - ✅ `xlsx_add_comment.py` ≤ 200 LOC (verified via `wc -l`).
  - ✅ All tests pass.
  - ✅ `python3 scripts/xlsx_add_comment.py --help` produces
    **byte-identical** output (capture before-refactor and
    after-refactor; diff is empty).

### Epic E2 — Verification & sign-off (R3, R6, R7)

#### Issue I9 — Test-suite full-pass evidence

Use Case: **Capture green-build evidence as a regression-lock**.

- **Main scenario:**
  1. Pre-refactor: capture E2E output (count + hash of "OK" lines) and
     unit-test summary into `docs/reviews/task-002-baseline.txt`.
  2. Post-refactor: re-capture; diff against baseline; expect no
     decrease in OK count.
  3. Capture `xlsx_add_comment.py --help` before and after; diff
     empty.
- **Acceptance criteria:**
  - ✅ E2E OK-count post ≥ E2E OK-count pre.
  - ✅ Unit-test count post == unit-test count pre.
  - ✅ `--help` byte-equal.

#### Issue I10 — Validator + clean-tree gate

Use Case: **Final repo-health checks**.

- **Main scenario:**
  1. `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
  2. `find skills/xlsx -name __pycache__ -type d -exec rm -rf {} +`.
  3. `git status` shows only the expected file moves + new package.
  4. `for s in docx xlsx pptx pdf; do diff -qr skills/docx/scripts/office skills/$s/scripts/office; done` → empty (no accidental office/ touch).
  5. `for s in xlsx pptx pdf; do diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py; done` → empty.
- **Acceptance criteria:**
  - ✅ All five sub-steps pass.

#### Issue I11 — `.AGENTS.md` update (per `artifact-management`)

Use Case: **Persist the new module map to local memory**.

- **Main scenario:** Update `skills/xlsx/scripts/.AGENTS.md` with a
  "Files" section listing each module + one-line responsibility. Per
  `artifact-management` skill, ONLY the developer agent writes this.
- **Acceptance criteria:** File reflects new package layout.

### Epic E3 — Honest scope locks (R8)

#### Issue I12 — Locked non-goals as regression tests

Use Case: **Prevent silent scope creep**.

- **Main scenario:**
  1. Add a single small test (`tests/test_refactor_honest_scope.py`,
     ~30 LOC) asserting:
     - `wc -l skills/xlsx/scripts/xlsx_add_comment.py` ≤ 200 (R2.a).
     - `from xlsx_add_comment import parse_cell_syntax,
       SheetNotFound, scan_idmap_used, add_person, main` succeeds
       (re-export contract — R3.a).
     - `office/` byte-equality across docx/xlsx/pptx/pdf is held
       (single-line `subprocess.check_call` of `diff -qr`).
- **Acceptance criteria:**
  - ✅ The 3 honest-scope assertions pass.
  - ✅ The test runs in < 2 s (no actual workbook I/O).

## 4. Non-functional Requirements

### Performance
- Cold-import overhead of `xlsx_add_comment.py` (i.e., parse-time of
  `python3 -c "import xlsx_add_comment"`) MUST stay within ±20 % of
  the pre-refactor baseline. Splitting a 2339 LOC file into 9 modules
  measurably changes only first-import path resolution; the bytecode
  size is identical. Measurement: `python3 -X importtime -c "import
  xlsx_add_comment" 2>&1 | tail -5` before/after.
- E2E suite wall-clock MUST stay within ±15 % of pre-refactor. Reason:
  E2E is dominated by LibreOffice + zip I/O, not by import.

### Correctness / Compatibility
- Public CLI surface (flags, exit codes, JSON envelope schema) is
  byte-identical pre/post. `--help` output is the verification artefact.
- Output workbooks for the same input are bit-equal pre/post **except**
  where the original file produced UUIDv4-based bytes (R9.e). Those
  bytes remain non-deterministic in the same way as before — refactor
  does not introduce *new* sources of non-determinism.
- All existing `# XXX` / `# NOTE` / `# region` comments inside moved
  code blocks are preserved. Region markers are converted to module
  docstrings.

### Security
- No new untrusted input paths.
- `_VML_PARSER` (lxml hardened: `resolve_entities=False`,
  `no_network=True`, `load_dtd=False`, `huge_tree=False`) MUST be
  preserved verbatim in `ooxml_editor.py`. Any deviation re-opens
  the billion-laughs/XXE class that Task 2.04 closed.

### Cross-skill compatibility
- **Strict CLAUDE.md §2 lock:** no edits under
  `skills/{docx,xlsx,pptx,pdf}/scripts/office/` or to the four
  cross-skill helpers. The post-task `diff -qr` evidence in I10 is the
  hard gate.

## 5. Constraints and Assumptions

### Technical constraints
- Python ≥ 3.10 (project baseline).
- Same dependencies as Task 001 (`openpyxl`, `lxml`, `defusedxml`,
  `msoffcrypto-tool`). **No new runtime deps.**
- Test discovery is `unittest discover -s tests`. The new
  `xlsx_comment/` package is **not** a test root; tests stay under
  `tests/` and import from `xlsx_add_comment` (via re-export) and
  optionally directly from `xlsx_comment.*` for new tests.
- License scope: every new file inherits `skills/xlsx/LICENSE`
  (Proprietary). Per-skill `NOTICE` does not change.

### Business constraints
- Strict no-feature-creep — see R8.

### Assumptions
- The 9-module split (`constants`, `exceptions`, `cell_parser`,
  `batch`, `ooxml_editor`, `merge_dup`, `cli_helpers`, `cli`,
  `__init__`) is the analyst's recommendation. The Architect may
  collapse or further-split via Q1, Q2, Q3 below. The RTM rows refer
  to the recommendation; if the architect picks the sub-package
  option (Q1 = B), R1.f is delivered as `xlsx_comment/ooxml/*.py`
  instead and the LOC budget is split accordingly.
- The shim re-export list (§2.5) is derived from a static grep of
  `tests/test_xlsx_add_comment.py` and is **frozen as of TASK draft
  v2** (35 symbols across 8 modules; the explicit list is in §2.5).
  The developer MUST re-grep at Stage 1 to catch any new test imports
  landed between TASK draft v2 and the start of implementation.
- Goldens **may** become bit-equal if the refactor is byte-pure (zero
  re-indentation). If not (e.g., black/ruff post-format changes),
  the structural diff helper is the fallback (R3.d).
- `skills/xlsx/scripts/.AGENTS.md` **exists** as of TASK draft v2
  (verified by `ls`). R5.b is therefore an **update**, not a create.
  Q7 is now closed (no longer open).

## 6. Open Questions

> **Architecture-blockers (must be closed in ARCHITECTURE.md before
> the Planning phase):** Q1, Q2.

- **Q1 — Single-file `ooxml_editor.py` (~850 LOC) or `ooxml/`
  sub-package (4 files of ~200 LOC each)?**
  Trade-off: the 850-LOC file matches `cli.py` in size and remains
  one navigation hop from `cli.py`'s perspective. The sub-package
  costs one extra `__init__.py` and a directory but isolates the
  four sub-concerns (scanners / rels / legacy / threaded) cleanly.
  **Recommendation: single-file** for v1 of the refactor — apply
  YAGNI a second time on the sub-package; we can split later if and
  when v2 features (parentId, rich text) bloat one of the four
  sub-concerns. **Status: ARCHITECTURE-BLOCKER (affects file count).**
- **Q2 — `cli.py` carries `main` + `single_cell_main` + `batch_main`,
  or split orchestration into `orchestrator.py`?**
  Trade-off: keeping all in `cli.py` is ≤ 700 LOC and groups the
  argparse-touching code. Splitting gives `cli.py` ≤ 200 LOC (just
  argparse) and `orchestrator.py` ≤ 500 LOC (the unpack/mutate/pack
  pipeline). The orchestrator needs ALL F2-F5 modules anyway, so the
  split saves nothing on import graph.
  **Recommendation: keep merged in `cli.py`** — argparse and main
  share too much state (the `args` namespace, the `je = args.json_errors`
  flag, the `try/except _AppError` wrapper). **Status: ARCHITECTURE-BLOCKER.**
- **Q3 — `cli_helpers.py` includes `_post_pack_validate` /
  `_post_validate_enabled`, or those stay in `cli.py`?**
  Currently they're in F6 region. Logically pure utilities. The split
  is cosmetic. **Recommendation: move to `cli_helpers.py`** — keeps
  `cli.py` argparse+main only.
- **Q4 — Public-API exposure via `xlsx_comment/__init__.py`?**
  ~~Two policies: (A) `__init__.py` exposes nothing (all imports go
  through `xlsx_comment.<module>`); (B) `__init__.py` re-exports the
  test-touched names so `from xlsx_comment import parse_cell_syntax`
  works directly.~~ **CLOSED in draft v2 — Policy A (near-empty
  `__init__.py`).** Rationale: (i) the test-compat surface already
  lives on `xlsx_add_comment.py` (the shim), so re-exporting on
  `__init__.py` would be the SECOND copy of the same contract — a
  drift hazard; (ii) the shim is the **single** documented entry
  point per §1; (iii) future programmatic callers use the explicit
  submodule path (`from xlsx_comment.cell_parser import …`), which
  reads more clearly at the call site than `from xlsx_comment import …`.
  §2.5 row 1 has been edited to reflect this.
- **Q5 — Should `BatchRow` be re-exported from the shim?**
  Currently tests don't import it, but xlsx-7 (next backlog item)
  almost certainly will when it gains an `--add-comments` integration.
  **Recommendation: NO for this refactor; YES via the explicit
  `from xlsx_comment.batch import BatchRow` form.** xlsx-6 shim's job
  is preserving the **existing** test surface, not pre-creating an
  xlsx-7 surface.
- **Q6 — Do we add a `tests/test_xlsx_comment_imports.py` smoke test?**
  Trivial — 30 LOC, asserts that every public symbol from every new
  module is importable. Cheap insurance against accidental
  refactor-time import-graph regressions. **Recommendation: YES**
  (already in I12).
- **Q7 — Is there an existing `skills/xlsx/scripts/.AGENTS.md`?**
  ~~The analyst has not verified.~~ **CLOSED in draft v2 — file
  exists** (verified by `ls skills/xlsx/scripts/.AGENTS.md`).
  R5.b is therefore an **update**, not a create.

> **Closed by this TASK** (no longer open):
> - **Q4** (closed in draft v2 per round-1 review n1) — `__init__.py`
>   is near-empty; no re-exports.
> - **Q7** (closed in draft v2 per round-1 review m3) — `.AGENTS.md`
>   exists; R5.b is an update.
> - Decision on file granularity (5 vs 9 modules): the analyst's
>   recommendation is 9 (with a sub-package option for F4 deferred to
>   Q1). The session-state hint
>   ("exceptions/cell_parser/batch/ooxml_editor/merge_dup") was a
>   minimum decomposition; the analyst expanded it to also extract
>   `constants`, `cli_helpers`, and `cli` because those regions are
>   independently sized and locking them inside `xlsx_add_comment.py`
>   would defeat the goal of a ≤ 200 LOC shim.
> - Whether to mutate the test suite: NO (R3.a is the lock).

---

## Appendix A — Traceability map

| RTM row | Issue | E2E / unit / structural artefact |
|---|---|---|
| R1.a | I1 | `python3 -c "import xlsx_comment"` exits 0 |
| R1.b–R1.j | I2–I8 | Per-module green-test acceptance |
| R2.a | I8 | `wc -l xlsx_add_comment.py` ≤ 200 |
| R2.b | I8 | grep of `tests/test_xlsx_add_comment.py` imports satisfied |
| R2.c | I1 | shim docstring inspection |
| R2.d | I8 | `chmod -v +x xlsx_add_comment.py && ./xlsx_add_comment.py --help` |
| R3.a | I9 | unit-test count delta = 0 |
| R3.b | I9 | E2E OK-count delta ≥ 0 |
| R3.c | I9 | E2E with POST_VALIDATE=1 still passes |
| R3.d | I9 | golden bit-equal OR `_golden_diff.py` zero structural delta |
| R4.a–R4.d | I2–I8 | code review checks `__all__` lists, no shim re-imports inside package |
| R5.a–R5.d | I11 | docstring inspection + `.AGENTS.md` diff |
| R6.a–R6.e | I10 | each sub-step is a single command with a binary outcome |
| R7.a–R7.d | I9 + I12 | git log + import smoke + structural compare |
| R8.a–R8.e | I12 | three-assertion regression test + diff-evidence in I10 |

## Appendix B — Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hidden circular import (e.g., `cli_helpers` ↔ `cli`) | M | H — refactor blocks until untangled | Plan landing order: leaf modules first (constants, exceptions), then F2/F3, F4, F5, then F-helpers, then cli last. R4.b forbids the shim being part of any import path inside the package. |
| Test imports a name not in the recommended re-export list | M | M — single-test failure | Stage 1 of the developer's PLAN re-greps `tests/` for `from xlsx_add_comment import` and pads the shim accordingly. R2.b is the canonical spec. |
| Black/ruff/pre-commit hook reformats moved code (R7.c violation) | L | M — bigger diff, harder review | Use `git mv`-style operations (cat regions to new files, delete from old, NO formatter pass during this task). Disable pre-commit auto-formatters for this PR. |
| `office/` accidentally touched | L | H — triggers 4-skill replication | I10 step 4 hard-gate: `diff -qr` evidence MUST be empty in PR description. |
| `xlsx_add_comment.py` shim grows past 200 LOC | M | L — cosmetic but undermines goal | R2.a numeric gate; if shim must exceed 200, fold the surplus into `cli.py` and re-export. |
| Cold-import latency regression > 20 % | L | L — non-functional | Measure once at I9; if regressed, collapse two modules with the most fan-in (likely `constants` + `exceptions`). |
| Goldens drift in non-determinism way (UUIDv4 churn) | L | M — false-positive failure | `_golden_diff.py` already strips ephemeral `<threadedComment id>`; verify in Stage 0 before refactor. |

