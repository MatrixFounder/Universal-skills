# Task 016.10 — End-to-end round-trip + documentation + validators

## Use Case Connection
- **All five UCs** exercised together in `tests/test_e2e_promotion.py`.

## Task Goal

Final bead of the TASK 016 chain. Ships:

1. The two-course fixture (`tests/fixtures/two_course_vault/`) that the
   earlier beads have been using.
2. The end-to-end round-trip test
   (`tests/test_e2e_promotion.py`) that drives the full ingest → lint →
   promote → lint → demote → lint cycle against the fixture.
3. SKILL.md updates documenting the two new subcommands and the
   two-tier model.
4. A new reference doc
   (`skills/wiki-ingest/references/cross_course_promotion.md`) with the
   operator playbook + edge cases + spec §6 gotchas.
5. Extended schema reference
   (`skills/wiki-ingest/references/wiki_schema.md`) with the v2.0 root
   schema definition.
6. Updated `.AGENTS.md` (`skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`)
   reflecting the two new commands + the `_page_merge` module.
7. Validator green: `validate_skill.py` exit 0, `skill-validator`
   reports SAFE, cross-skill `diff -q` matrix silent.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/fixtures/two_course_vault/` — minimal
  fixture with:
  - `WIKI_SCHEMA.md` (root, schema_version 2.0).
  - `Lessons/Course A/` (course schema 1.0; `_sources/foo.md`,
    `_concepts/Sharpe Score.md` mentioning Sharpe with the fact "X = 42").
  - `Lessons/Course B/` (course schema 1.0; `_sources/bar.md`,
    `_concepts/Sharpe Score.md` mentioning Sharpe with a different fact
    "Y = 7" so the round-trip exercises contradiction detection).
  - Each course has its own `index.md` and `log.md` (static — no
    timestamps).
- `skills/wiki-ingest/scripts/tests/test_e2e_promotion.py` — round-trip
  driver.
- `skills/wiki-ingest/references/cross_course_promotion.md` — operator
  playbook (R11.2).

### Changes in Existing Files

#### File: `skills/wiki-ingest/SKILL.md`

- **§4 Script Contract**: add two new subcommand rows:
  ```
  - `python3 scripts/wiki_ops.py promote <Name> --vault <vault> [--kind concept|entity] [--apply]` …
  - `python3 scripts/wiki_ops.py demote <Name> --vault <vault> --to <Course> [--dry-run]` …
  ```
  Also document the new exit-code: `code=3` = "feature not yet
  implemented" (used by 016.05 stub gate; will be unused once 016.06
  ships, but stays in the vocabulary for future stubs).
  Also document the `append-log --touched <path>:shared` suffix
  convention introduced by 016.09 (R8.3): the suffix `(shared)` is
  rendered into the log line; the suffix is stripped from the path.
  Plus a one-paragraph "Two-Tier Vault Model" section before §4 (or
  inside §2 Capabilities) describing the root vs course layers.
- **§7 Instructions**: add Phase P — Promote/Demote subsection.
  - When to use: lint reports `cross_course_duplicate` + operator
    confirms semantic identity.
  - Step-by-step: `promote --dry-run`, review plan, `--apply`, verify
    via lint.
- **§9 Best Practices**: add row "Promote AFTER seeing the duplicate in
  lint — never speculatively. Demote when the cross-share turns out to
  be one-course-only."
- **§11 Resources**: add `references/cross_course_promotion.md`.

#### File: `skills/wiki-ingest/references/wiki_schema.md`

- Add new section "Root schema (v2.0)":
  - Frontmatter shape: `schema_version: 2.0`, `kind: vault-root`.
  - Layout: `<vault>/WIKI_SCHEMA.md`, `<vault>/_concepts/`,
    `<vault>/_entities/`, optional `<vault>/index.md`. NO `_sources/`,
    NO `log.md`.
  - One-page-one-place invariant: a given canonical filename lives in
    either some course's `_concepts/`/`_entities/` OR the root's, never
    both.
  - Footnote vault-relative form: `[^src-<slug>]:
    [[<course_rel>/_sources/<slug>]] — <Title>`.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`

- "What lives where" table: add rows for `_page_merge.py`,
  `commands/promote.py`, `commands/demote.py`.
- "Adding a new command" section: no change.
- Note the layered DAG is intact:
  `commands/promote.py` and `commands/demote.py` import from
  `_safety` + `_markdown` + `_frontmatter` + `_vault` + `_page_merge`
  — never from another `commands/*`.

#### File: `skills/wiki-ingest/references/cross_course_promotion.md` (new)

Operator playbook covering:

1. **When to promote** — operator runs `lint`, sees
   `cross_course_duplicate` for a concept that semantically describes
   the same thing across courses.
2. **How to promote** — `wiki-ingest promote "<Name>" --vault <vault>`
   (dry-run by default). Review plan, then `--apply`.
3. **Inspecting the merged page** — frontmatter `promoted_from:` lists
   every contributing course; footnotes are vault-relative.
4. **Re-promoting (R3.7)** — when a third course later gets its own
   copy, `promote --apply` again folds it in.
5. **Demoting** — when the cross-share is no longer needed. Refuses if
   any non-target course cites the page.
6. **Lint discipline** — every cross-course operation should be
   bracketed by `lint <vault>` checks: clean before, clean after.
7. **Edge cases** (lifted from spec §6 + TASK §8):
   - Same name, different concepts (operator's responsibility).
   - Footnote slug collisions across courses (R13.3 honest-scope).
   - Cross-layer references span layers (`lint`-aware).
   - Custom page kinds (`Methods/`, `Decisions/`) not supported (v3+).

### Validators (run before declaring complete)

- `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest`
  → exit 0 (Gold Standard / CSO).
- `python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest`
  → reports `SAFE` (0 Critical / 0 Errors).
- Cross-skill `diff -q` matrix from TASK 015 §9 stays silent
  (wiki-ingest shares no files with docx/xlsx/pptx/pdf).
- `python -m unittest discover -s tests` from the per-skill venv
  → all green.

## Test Cases

### End-to-end Tests (`tests/test_e2e_promotion.py` — new)

1. **TC-E2E-016-10-01:** Full round-trip
   - Start from the static `two_course_vault/` fixture.
   - Step 1: `lint <vault>` → reports `cross_course_duplicate` for
     `Sharpe Score`.
   - Step 2: `promote "Sharpe Score" --vault <vault> --apply` →
     succeeds; `contradictions_raised: 1` (Course A vs Course B fact
     conflict).
   - Step 3: `lint <vault>` → reports zero `cross_course_duplicate` and
     zero `invariant_violation`.
   - Step 4: Inspect the merged page: vault-relative footnotes for both
     `foo` (Course A) and `bar` (Course B); `## Contradictions` block
     present; `promoted_from:` lists both courses.
   - Step 5: `demote "Sharpe Score" --to "Course A" --vault <vault>` →
     refuses (Course B's source still cites the page; A1 path).
   - Step 6: Clean Course B's citations (manually delete
     `Lessons/Course B/_sources/bar.md` in the test setup), then
     `demote "Sharpe Score" --to "Course A" --vault <vault>` → succeeds.
   - Step 7: `lint <vault>` → clean.
   - Final state: `Lessons/Course A/_concepts/Sharpe Score.md` exists
     with short-form footnotes; root `_concepts/Sharpe Score.md` is
     gone; root `index.md` no longer references it; Course A's
     `index.md` lists it under `## Concepts` again.
2. **TC-E2E-016-10-02:** Ingest after promote routes to root (R8 / UC-4)
   - Pre: post-promote state from TC-E2E-016-10-01 step 3.
   - Run: `upsert-page <Lessons/Course C> --kind concept --name "Sharpe
     Score" --source-slug baz --source-title "Baz" --fact "Z = 99"`.
   - Expected: root page gains the new fact + footnote (vault-
     relative); Course C does NOT gain a course-local Sharpe Score
     page; subsequent `lint` is clean.
3. **TC-E2E-016-10-03:** Reindex builds `## Shared * referenced` (UC-5)
   - Pre: post-promote state.
   - Run: `reindex <Lessons/Course A>`.
   - Expected: Course A's `index.md` contains
     `## Shared concepts referenced` with `[[Sharpe Score]] — (shared)`.
4. **TC-E2E-016-10-04:** `reindex --cascade` from root
   - Run: `reindex <vault> --cascade`.
   - Expected: root `index.md` rebuilt; all course `index.md`s
     rebuilt; JSON `cascaded` lists every course.
5. **TC-E2E-016-10-05:** `validate_skill.py` exit 0
   - Run: `python3 .claude/skills/skill-creator/scripts/validate_skill.py
     skills/wiki-ingest`.
   - Expected: exit code 0.
6. **TC-E2E-016-10-06:** `skill-validator` SAFE
   - Run: `python3 .claude/skills/skill-validator/scripts/validate.py
     skills/wiki-ingest`.
   - Expected: SAFE risk; 0 critical / 0 errors.
7. **TC-E2E-016-10-07:** Cross-skill `diff -q` silent
   - Run the matrix from TASK 015 §9 / CLAUDE.md §2 against
     `wiki-ingest`.
   - Expected: empty output (no shared files with docx/xlsx/pptx/pdf).

### Regression Tests
- `tests/test_r11_byte_identity.py` — single-course byte-identity
  preserved (gate on every earlier bead; here as a final regression
  check).
- All `tests/commands/test_*.py` pass.
- All `tests/test__*.py` pass.
- `tests/test_architecture.py` passes.

## Acceptance Criteria
- [ ] All 7 E2E tests pass.
- [ ] All earlier-bead tests still pass (no regression).
- [ ] `tests/fixtures/two_course_vault/` committed with frozen content
      (no timestamps in `log.md`).
- [ ] SKILL.md gains the `promote` / `demote` rows + Phase P
      subsection.
- [ ] `references/cross_course_promotion.md` exists and covers spec §6
      gotchas.
- [ ] `references/wiki_schema.md` extended with root-schema (v2.0)
      section.
- [ ] `.AGENTS.md` reflects the 3 new modules.
- [ ] `validate_skill.py` exits 0.
- [ ] `skill-validator/validate.py` reports SAFE.
- [ ] Cross-skill `diff -q` matrix silent.
- [ ] `python -m unittest discover -s tests` from the per-skill venv
      → all green.

## Notes
- This is the MERGE GATE. Anything that fails any acceptance criterion
  blocks merge.
- The fixture's `log.md` files MUST be static (no timestamps) — TASK 015
  R11 byte-identity discipline. New log entries written by `promote` /
  `demote` during the round-trip test are normalised by **post-processing
  the date pattern** (regex `\[\d{4}-\d{2}-\d{2}\]` → `[YYYY-MM-DD]`)
  before any `diff` assertion. No `freezegun` or similar test dep
  (TASK §0 "no new runtime dependency" applies to test-time deps too —
  pure stdlib `unittest` discipline).
- Honest-scope: the round-trip exercise DOES include the contradiction
  detection path (TC-E2E-016-10-01 step 2) — `contradictions_raised: 1`
  is the success criterion, not a failure.
- No new dependencies. No changes outside `skills/wiki-ingest/`.
- After this bead lands, archive TASK.md + PLAN.md via `skill-archive-task`
  (Analysis-phase rotation on the NEXT task; not in this bead).
