# Task 002.11: `.AGENTS.md` + references doc + final repo-health gates

## Use Case Connection
- I10 — Validator + clean-tree gate.
- I11 — `.AGENTS.md` update.

## Task Goal
Final pass: update local memory (`skills/xlsx/scripts/.AGENTS.md`)
to reflect the new module layout, append §6 "Internal module map"
to `references/comments-and-threads.md`, and run the five
repo-health gates that prove the refactor did not corrupt
unrelated parts of the tree.

## Changes Description

### New Files
*(none)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/.AGENTS.md`

Per `artifact-management` SKILL "Local .AGENTS.md (Per-Directory)" and
"Single Writer" (developer-only) rules. Add (or update if a stale
section exists) a "Files" subsection listing every Task-002 module
with a one-line responsibility summary:

```markdown
## Files

### `xlsx_add_comment.py`
Thin shim — re-exports the 35-symbol test-compat surface and
delegates `main()` to `xlsx_comment.cli`. ≤ 200 LOC.

### `xlsx_comment/__init__.py`
Package marker. Near-empty (Q4=A); no re-exports here. Programmatic
callers use the explicit submodule path.

### `xlsx_comment/constants.py`
XML namespaces (SS_NS, R_NS, etc.), OOXML rel-types,
content-type strings, `DEFAULT_VML_ANCHOR`, `BATCH_MAX_BYTES`.

### `xlsx_comment/exceptions.py`
`_AppError` base + 14 typed leaves (UsageError, SheetNotFound,
NoVisibleSheet, InvalidCellRef, MergedCellTarget, EmptyCommentBody,
InvalidBatchInput, BatchTooLarge, MissingDefaultAuthor,
DuplicateLegacyComment, DuplicateThreadedComment, SelfOverwriteRefused,
OutputIntegrityFailure, MalformedVml). Each carries `code` (exit code)
and `envelope_type` (JSON envelope `type` field) class attributes.

### `xlsx_comment/cell_parser.py`
Cell-syntax parser (A1, Sheet2!B5, 'Q1 2026'!A1, 'Bob''s Sheet'!A1)
and sheet resolver (M2 first-VISIBLE-sheet rule, M3 case-sensitive
lookup with suggestion).

### `xlsx_comment/batch.py`
`BatchRow` dataclass + `load_batch` (8 MiB cap, flat-array vs
xlsx-7 envelope auto-detect, group-finding skip).

### `xlsx_comment/ooxml_editor.py`
The OOXML mutation core. Scanners (`scan_idmap_used`,
`scan_spid_used` — workbook-wide invariants C1 + M-1), part-counter
(`next_part_counter`, `_allocate_new_parts`), cell-ref helpers,
target/path resolution, rels + Content_Types patching, legacy
comment writers (`add_legacy_comment`, `add_vml_shape`), threaded
comment writers (`add_threaded_comment`, `add_person`).
Hosts `_VML_PARSER` — the lxml hardened parser (defense vs
billion-laughs / XXE on tampered VML); DO NOT mutate constructor.

### `xlsx_comment/merge_dup.py`
Merged-cell resolver (`resolve_merged_target` — fail-fast on
non-anchor unless `--allow-merged-target`) and duplicate-cell
matrix (`detect_existing_comment_state`,
`_enforce_duplicate_matrix`).

### `xlsx_comment/cli_helpers.py`
Pure utilities: `_initials_from_author`, `_resolve_date`,
`_validate_args`, `_assert_distinct_paths`, `_content_types_path`,
`_post_validate_enabled`, `_post_pack_validate`. Q3=helpers
relocated `_post_*_validate` here from F6 during Task 002.

### `xlsx_comment/cli.py`
F1 (`build_parser` argparse) + F6 (`main`, `single_cell_main`,
`batch_main`) merged per Q2=A. The unified `try/except _AppError`
handler for typed exit codes lives here.
```

If the existing `.AGENTS.md` has out-of-date entries for
`xlsx_add_comment.py` (from Task 001), **replace** them with the
above. Other directories' entries (e.g. `xlsx_add_chart.py`,
`xlsx_validate.py`) stay untouched.

#### File: `skills/xlsx/references/comments-and-threads.md`

Append a new top-level section (`## 6. Internal module map`):

```markdown
## 6. Internal module map (Task 002 — module split)

The `xlsx_add_comment.py` script is a **thin shim** (≤ 200 LOC) that
delegates to the `xlsx_comment/` package next to it. Public CLI
behaviour is unchanged from xlsx-6 (Task 001); the split exists to
make further development of the script tractable. See
`docs/ARCHITECTURE.md` §3 / §8 for the design and Q1/Q2/Q3 closure.

| Module | Responsibility |
|---|---|
| `xlsx_comment/constants.py` | OOXML namespaces, content-types, anchor + cap constants |
| `xlsx_comment/exceptions.py` | `_AppError` + 14 typed leaves |
| `xlsx_comment/cell_parser.py` | `--cell` syntax parser + sheet resolver |
| `xlsx_comment/batch.py` | `--batch` JSON loader (flat-array vs envelope) |
| `xlsx_comment/ooxml_editor.py` | OOXML mutations (largest module — scanners, part-counter, rels, legacy + threaded writers, `_VML_PARSER` security boundary) |
| `xlsx_comment/merge_dup.py` | Merged-cell resolver + duplicate-cell matrix |
| `xlsx_comment/cli_helpers.py` | Validation + date + post-pack validate utilities |
| `xlsx_comment/cli.py` | argparse + `main` + `single_cell_main` + `batch_main` |

Future contributors: when adding a v2 feature (R9.f
`--default-initials`, R9.g `--unpacked-dir`, parentId reply-threads,
rich text), land it in the **single** appropriate module above —
DO NOT spread changes across files. If a v2 feature pushes
`ooxml_editor.py` past ~1200 LOC, reconsider the Q1=A "single-file"
decision (see ARCHITECTURE §8 override clause).
```

### Component Integration
- `.AGENTS.md` is local memory; no functional code change.
- `references/comments-and-threads.md` is documentation; no code.
- `SKILL.md` is **NOT** modified — TASK R5.c is a verification gate
  (the user-facing CLI is unchanged, so SKILL.md's §2/§4/§10/§12
  stay verbatim).

## Steps

1. Update `skills/xlsx/scripts/.AGENTS.md` per the body above.
2. Append §6 to `skills/xlsx/references/comments-and-threads.md`.
3. **Run the five repo-health gates** (TASK §3 I10):
   ```bash
   # I10.1 — validate_skill clean
   python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx
   # Expected: exit 0

   # I10.2 — clean __pycache__
   find skills/xlsx -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

   # I10.3 — git status review (manual): only expected file moves
   #         + new package + .AGENTS.md + references edit + new test
   #         files + baseline + postcheck + plan-review trail.
   git status

   # I10.4 — office/ byte-identity across the THREE skills that have office/.
   # Per CLAUDE.md §2: docx (master) -> xlsx + pptx (mirrors). pdf has
   # NO skills/pdf/scripts/office/ directory — it is outside the
   # office-replication scope (verified during Task 002.1 execution).
   for s in xlsx pptx; do
       diff -qr skills/docx/scripts/office skills/$s/scripts/office
   done
   # Expected: every diff is empty.

   # I10.5 — cross-skill helpers byte-identity.
   # 4-skill scope: _errors.py + preview.py (incl. pdf).
   for s in xlsx pptx pdf; do
       diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
       diff -q skills/docx/scripts/preview.py skills/$s/scripts/preview.py
   done
   # 3-skill scope: office_passwd.py (pdf uses pypdf PdfWriter.encrypt
   # for its own encryption; not in this replication scope).
   for s in xlsx pptx; do
       diff -q skills/docx/scripts/office_passwd.py skills/$s/scripts/office_passwd.py
   done
   # Expected: every diff is empty.
   ```
4. **Verify SKILL.md non-touch** (R5.c gate):
   ```bash
   git diff --stat skills/xlsx/SKILL.md
   ```
   Expected: empty (file unchanged).
5. **Verify docx_add_comment / pptx non-touch** (R8.d gate):
   ```bash
   git diff --stat skills/docx/scripts/docx_add_comment.py \
       skills/pptx/scripts/ skills/pdf/scripts/
   ```
   Expected: empty.
6. **Verify requirements.txt non-touch** (R6.c gate):
   ```bash
   git diff --stat skills/xlsx/scripts/requirements.txt
   ```
   Expected: empty.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** One last full E2E run — confirms the docs edits
  did not (somehow) break anything:
  ```bash
  bash skills/xlsx/scripts/tests/test_e2e.sh 2>&1 | tail -3
  ```
  Must end OK with the baseline OK-count.

### Unit Tests
- **TC-UNIT-01:** Full unit suite passes (75 + 11 = 86).

### Regression Tests
- `validate_skill.py skills/xlsx` exits 0.
- All five `diff` gates produce empty output.

## Acceptance Criteria
- [ ] `skills/xlsx/scripts/.AGENTS.md` updated with the new "Files"
      subsection (no stale Task-001 entries left).
- [ ] `skills/xlsx/references/comments-and-threads.md` has a new
      §6 "Internal module map" (~20 LOC).
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] `office/` byte-identical across the three skills that have it (docx → xlsx + pptx; pdf has no `office/` subdir).
- [ ] `_errors.py` / `preview.py` / `office_passwd.py` byte-identical
      across the relevant skill set (4 / 4 / 3).
- [ ] `SKILL.md`, `requirements.txt`, `docx_add_comment.py`, all
      `pptx_*` and `pdf/scripts/*` are byte-identical to pre-refactor.
- [ ] All unit (86) + E2E (~112) green.
- [ ] `git status` shows only the expected file set; no orphan
      changes.

## Notes
- This task is intentionally low-risk and short (~30 min). It runs
  the cross-cutting gates that are not amortizable across earlier
  tasks (e.g., the office/ diff gates would catch a regression
  introduced anywhere from Task 002.3 onward, but they live here as
  a single audit point so the result is committed alongside the
  documentation refresh).
- Per `artifact-management` SKILL **single-writer rule**, this
  task's `.AGENTS.md` edit is the ONLY edit to that file across the
  whole 11-task chain. Tasks 002.3-002.10 do NOT touch it even
  though they introduce the modules being documented — that's by
  design (one writer = one diff).
- After this task lands, Task 002 is COMPLETE and the chain is
  ready for `/vdd-develop-all` close-out (or, if executed manually,
  for PR merge).
