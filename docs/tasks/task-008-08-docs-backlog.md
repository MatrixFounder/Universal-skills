# Task 008-08: Docs + backlog + validator + cross-skill `diff -q`

## Use Case Connection
- All UCs — finalization / honest-scope catalogue update / cross-skill replication gate.

## Task Goal
Mechanical finalization sub-task. Update all documentation surfaces to reflect that asset relocation is now in scope. Flip backlog rows. Update `.AGENTS.md` LOC + test counts. Run validator + cross-skill `diff -q` gates. After this task: `docx-6.5` and `docx-6.6` rows are ✅ DONE; the only remaining `docx-6` honest-scope item is R10.a (cross-run anchor).

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/SKILL.md`

**Section: `docx_replace.py` row, "Honest scope (v1)" sentence:**

Locate the existing sentence in the `docx_replace.py` row that mentions:
> "anchor должен помещаться в один `<w:t>` после run-merge — cross-run anchor не поддерживается; ... inserted MD body со ссылками на images / charts / OLE / SmartArt не копирует relationship-targets ... numbering definitions remain in insert tree"

Reword to:
> "Honest scope (v2): anchor должен помещаться в один `<w:t>` после run-merge — cross-run anchor не поддерживается (R10.a); документировано в `--help`. Images, charts, OLE objects, SmartArt diagrams, and numbered/bulleted lists ARE relocated from MD source into the base document (R10.b + R10.e closed in docx-008, 2026-05-12)."

Update any version annotation (e.g. "✅ DONE 2026-05-12 (v1 + docx-008 relocators)") to reflect the new shipped state.

#### File: `docs/office-skills-backlog.md`

**Row `docx-6.5` (line 172):**

Currently starts with: `| docx-6.5 | Image relocator для `--insert-after` | ...`

Flip to: `| docx-6.5 | Image relocator для `--insert-after` ✅ DONE 2026-05-12 (Task 008) | ...`

Optionally append delivery actuals (LOC, tests, gates) at end of cell, mirroring the `docx-6.7 ✅ DONE` cell pattern (lines 174).

**Row `docx-6.6` (line 173):**

Same treatment. Flip to: `| docx-6.6 | Numbering definitions relocation для `--insert-after` ✅ DONE 2026-05-12 (Task 008) | ...`

#### File: `skills/docx/scripts/.AGENTS.md`

Add or update a row covering the new `_relocator.py` module + its tests. Mirror the existing row pattern. Include:
- File: `_relocator.py`
- Purpose: "Asset relocator for `docx_replace.py --insert-after` (image/rel + numbering + content-types + chart/OLE/SmartArt parts). docx-only sibling; pattern source `docx_merge.py` (re-used by copy per Decision D3)."
- LOC: actual final LOC after 008-07 (likely ~450-500).
- Functions: `relocate_assets`, `_copy_extra_media`, `_max_existing_rid`, `_merge_relationships`, `_copy_nonmedia_parts`, `_read_rel_targets`, `_apply_nonmedia_rename_to_rels`, `_remap_rids_in_clones`, `_merge_content_types_defaults`, `_merge_numbering`, `_ensure_numbering_part`, `_remap_numid_in_clones`, `_assert_safe_target`.

Also sync test counts in the `tests/` row:
- `test_docx_relocator.py` — new file, count actual at-task-end (≥ 40 tests).
- Total unit tests: 108 (existing) + 40+ = 148+.
- Total E2E cases: 22 unchanged + 4 new (image-relocated, numbering-relocated, image-and-numbering, path-traversal**) + 2 rewritten = **28 cases**.

  **Footnote**: if 008-07 placed path-traversal as unit-test instead of shell-E2E, E2E count is 22 + 3 new + 2 rewritten = 27 cases.

#### File: `skills/docx/scripts/docx_replace.py`

**`--help` text polish:**

Locate the existing `--help`/argparse description that mentions:
- "image r:embed not wired"
- "`<w:numId>` rendering as plain text"

Remove these substrings. Optionally add one new line documenting the relocator behavior:
- "`--insert-after`: images, charts, OLE, SmartArt, and numbered lists are relocated from MD source into the base document."

#### File: `docs/ARCHITECTURE.md`

**§9 NIT n1 reconciliation:**

The §9 line currently reads "11 (actual count 12, see §9 NIT n1 reconciliation handoff)". Replace with "12" throughout that block (lines 1092–1101 of the current file). Specifically:
- Update the comment block to read "12 invocations" without the conditional language.
- Remove the "NIT n1" reference if it no longer adds value.

MIN-5 from prior architecture-review propagation.

### Component Integration
- No code changes in this sub-task. Pure docs + finalization.
- After this sub-task: TASK 008 is fully MERGED-equivalent (all gates green).

## Test Cases

### Unit Tests
- None new.

### End-to-end Tests
- Run full E2E suite, confirm all green.

### Regression Tests
- Run `validate_skill.py skills/docx` — exit 0 (G8).
- Run all 12 `diff -q` invocations from CLAUDE.md §2 — all silent (G7).
- Run `python3 -m unittest discover -s tests` in `skills/docx/scripts/` — exit 0 with ≥ 148 tests green (G6).

## Acceptance Criteria
- [ ] `skills/docx/SKILL.md` updated: only R10.a remains in honest scope; relocators advertised.
- [ ] `docs/office-skills-backlog.md` rows `docx-6.5` and `docx-6.6` flipped to ✅ DONE 2026-05-12.
- [ ] `skills/docx/scripts/.AGENTS.md` updated with `_relocator.py` row + synced test counts.
- [ ] `docx_replace.py --help` no longer mentions "image r:embed not wired" or "`<w:numId>` rendering as plain text".
- [ ] `docs/ARCHITECTURE.md` §9 NIT n1 reconciliation: count reads "12" (not "11 (actual count 12)").
- [ ] **TASK §7 G6**: ≥ 148 unit tests green via `python3 -m unittest discover -s tests`.
- [ ] **TASK §7 G7**: all 12 `diff -q` invocations silent.
- [ ] **TASK §7 G8**: `validate_skill.py skills/docx` exit 0.
- [ ] **TASK §7 G9**: git diff on SKILL.md + backlog + .AGENTS.md shows expected updates.

## Verification Commands
```bash
# G6 — full unit test suite
cd skills/docx/scripts
./.venv/bin/python -m unittest discover -s tests -v

# G7 — cross-skill replication boundary (12 diff -q checks)
cd /Users/sergey/dev-projects/Universal-skills
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
for s in xlsx pptx pdf; do
    diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
    diff -q skills/docx/scripts/preview.py  skills/$s/scripts/preview.py
done
diff -q skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
diff -q skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py

# G8 — validator
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx

# Full E2E + hermetic POST_VALIDATE
cd skills/docx/scripts
bash tests/test_e2e.sh
DOCX_REPLACE_POST_VALIDATE=1 bash tests/test_e2e.sh
```

## Notes
- **No code changes.** This is a docs / finalization sub-task. Any test failure here = bug in 008-01..007; fix there + come back.
- **`.AGENTS.md` is Developer-managed** per `artifact-management` skill. Developer adds the `_relocator.py` row. The LOC count must match the actual final LOC count (post-007).
- **`--help` polish minimal.** The previous architect note in TASK §3.4 suggested adding one positive line about relocation; this is optional. If added, keep it under 80 chars to fit the argparse-help column width.
- **MIN-5 propagation:** the "eleven (actual count 12)" reconciliation note in ARCH §9 is a leftover from the 006-09 docs review NIT n1. Now that the developer is editing ARCH §9 anyway (to add `_relocator.py` to the docx-only list — already done by the architect in §12.7), updating the "eleven" wording is a 1-line fix.
- **Cross-skill replication preserved:** `_relocator.py` is **docx-only**. It is NOT in any of the replicated sets. The 12 `diff -q` checks remain silent because nothing in `office/` / `_soffice.py` / `_errors.py` / `preview.py` / `office_passwd.py` was edited in Task 008.
- **After this task:** session state should be updated to "Task-008-Merged"; backlog should reflect that the only remaining `docx-6` v2 follow-up is the optional v3 items (TASK §9 H1–H5).
