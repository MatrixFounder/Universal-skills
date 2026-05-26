# Task 016.09 — `commands/upsert_page.py` root-aware lookup

## Use Case Connection
- **UC-4** Main scenario (ingest into a course whose concept is already
  shared at root) + A1 (page not at root → fall back to course-local).

## Task Goal

Extend `commands/upsert_page.py` so that, when upserting a
concept/entity, the code first calls `find_vault_root(args.vault)` and
checks the root layer (`<vault_root>/_concepts/` then
`<vault_root>/_entities/`). If a page with the canonical name exists at
root, the new fact/source row lands on the root page (not a course-local
copy). Footnote definitions on the root page are written in
vault-relative form (A-M-2). Behaviour is byte-identical to v1 when the
vault is single-course (no root schema).

## Changes Description

### New Files
- None (extends existing module).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/upsert_page.py`

**Function `execute(args) -> int`:**

Today, `upsert_page` resolves the page path as
`args.vault / f"_{args.kind}s" / f"{args.name}.md"`. The new logic
inserts a root-layer-first lookup:

1. **Discover vault root**:
   - `(course_root, vault_root) = find_vault_root(args.vault)`.
   - If `course_root != args.vault`, the operator passed a path inside
     a course — treat `args.vault` as the course root going forward.
     (Backwards-compat: existing callers pass the course root directly,
     so `course_root == args.vault`.)
   - **Bytecode parity**: when `vault_root is None`, the rest of the
     function executes exactly as v1 (no behaviour change). Locked by
     `tests/test_r11_byte_identity.py`.
2. **Root-first page lookup** (R8.1):
   - If `vault_root is not None`:
     - `root_concepts = vault_root / "_concepts" / f"{args.name}.md"`
     - `root_entities = vault_root / "_entities" / f"{args.name}.md"`
     - If either exists → set `target_path = <root_hit>` AND
       `target_is_shared = True`.
   - Else: `target_path = course_root / f"_{args.kind}s" / f"{args.name}.md"`
     AND `target_is_shared = False` (existing v1 behaviour).
3. **Footnote definition** (R8.2):
   - When writing a new footnote definition (via
     `_page_merge.upsert_footnote`), if `target_is_shared` use the
     vault-relative form:
     `[^src-<slug>]: [[<course_rel>/_sources/<slug>]] — <Title>`
     where `<course_rel> = course_root.relative_to(vault_root)`.
   - Else: use the short form (v1 behaviour).
4. **Log marker** (R8.3):
   - If `target_is_shared`, after the write completes, append a hint to
     the per-course `log.md` entry (the existing append-log logic
     captures `pages_touched`): mark the touched page as
     `<vault_rel>/_concepts/<name> (shared)` instead of just the bare
     path.
   - The `append-log` subcommand is a separate command — but the upsert
     path doesn't call `append-log`; the caller (ingest workflow) does.
     **Decision**: emit a `target_is_shared: true` field in the upsert
     JSON output so the caller can pass `--touched <vault_rel>/_concepts/<name>:shared`
     to `append-log`. The `(shared)` rendering happens in
     `append-log`'s log-line formatting — but this is a 1-line
     extension; lock with TC-UNIT-016-09-05.
5. **No auto-promotion** (R8.5): if `vault_root is not None` but the
   root page does NOT exist, the code path is identical to v1 (creates
   a course-local stub). Locked by TC-UNIT-016-09-03.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/append_log.py`

- Tiny extension: when a `--touched` argument value has the suffix
  `:shared`, render the log line as `<path> (shared)` and strip the
  suffix in the rendered output. (Decision per R8.3.)
- LoC budget unchanged (≤150).
- Test added to `tests/commands/test_append_log.py`.

### Component Integration

- `upsert_page.py` now imports `find_vault_root` from `_vault.py`.
- `_page_merge.upsert_footnote` continues to take the same arguments —
  but the *caller* (this module) decides between short and vault-
  relative form. The primitive itself is unchanged.
- LoC budget: ≤250 (architecture §3.2). Post-016.01 baseline is
  ~157 LoC (the four merge primitives — ~60 LoC — were extracted to
  `_page_merge.py`); adding ~50 LoC of root-aware branching lands at
  ~207, comfortably within budget.

## Test Cases

### Unit Tests (`tests/commands/test_upsert_page.py` — extended)

1. **TC-UNIT-016-09-01:** Root-first lookup hits (R8.1)
   - Fixture: vault with `_concepts/Sharpe Score.md` at root; Course C
     has no `_concepts/Sharpe Score.md`.
   - Run: `upsert-page <Lessons/Course C> --kind concept
     --name "Sharpe Score" --source-slug foo --source-title "Foo"
     --source-date 2026-05-26 --fact "X = 42"`.
   - Expected: root page has new fact + new source row + footnote;
     Course C's `_concepts/` does NOT contain a Sharpe Score page.
2. **TC-UNIT-016-09-02:** Root-first lookup misses (A1 / R8.4)
   - Fixture: vault with no `Sharpe Score.md` at root.
   - Run: same as 01.
   - Expected: course-local `Lessons/Course C/_concepts/Sharpe Score.md`
     created (v1 behaviour).
3. **TC-UNIT-016-09-03:** No auto-promotion (R8.5)
   - Fixture: Courses A + B both have `_concepts/Pipeline.md`; root
     does NOT.
   - Run: upsert-page into Course C with `--name Pipeline --fact "..."`.
   - Expected: Course C gains a course-local `_concepts/Pipeline.md`.
     No root page is created. (`lint` will flag the cross-course
     duplicate after; operator decides whether to promote.)
4. **TC-UNIT-016-09-04:** Footnote on root page uses vault-relative form
   (R8.2 / A-M-2)
   - Post TC-UNIT-016-09-01: scan root page footnotes; the new
     definition is `[^src-foo]: [[Lessons/Course C/_sources/foo]] —
     Foo` (or whatever `course_root.relative_to(vault_root)` produces
     for the test fixture).
5. **TC-UNIT-016-09-05:** `target_is_shared: true` propagates to
   append-log (R8.3)
   - Post-upsert JSON includes `"target_is_shared": true`.
   - When the caller runs `append-log --touched
     "_concepts/Sharpe Score:shared"`, the rendered log entry has
     `Pages touched: _concepts/Sharpe Score (shared)`.
6. **TC-UNIT-016-09-06:** Single-course byte-identity (TASK §4.4)
   - Fixture: existing v1 single-course test fixture (no root schema).
   - Run: all existing v1 upsert-page test cases.
   - Expected: byte-identical output and filesystem effects;
     `tests/test_r11_byte_identity.py`-style assertion.
7. **TC-UNIT-016-09-07:** Non-`Lessons/` layout (Q-8 / A-M-2)
   - Fixture: course at `<vault>/Hermes/`; root has the page.
   - Run: upsert into `<vault>/Hermes`.
   - Expected: footnote definition uses `Hermes/_sources/<slug>` form.
8. **TC-UNIT-016-09-08:** `lint` clean post-upsert
   - After TC-UNIT-016-09-01, `lint <vault>` reports zero
     `invariant_violation` (the operation hit root, not course; no
     duplicate created).

### Regression Tests
- `tests/test_r11_byte_identity.py` passes (TC-UNIT-016-09-06 strict
  version).
- `tests/test_architecture.py` passes.
- `tests/commands/test_promote.py`, `test_demote.py`, `test_lint.py`,
  `test_reindex.py` all pass.

## Acceptance Criteria
- [ ] All 8 unit tests pass.
- [ ] `upsert_page.py` LoC ≤ 250 (architecture budget §3.2).
- [ ] `append_log.py` `:shared` suffix handling locked
      (TC-UNIT-016-09-05).
- [ ] Single-course byte-identity preserved (TC-UNIT-016-09-06).
- [ ] No auto-promotion locked (TC-UNIT-016-09-03).
- [ ] Footnote vault-relative form per A-M-2 (TC-UNIT-016-09-04,
      TC-UNIT-016-09-07).
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.
- [ ] `lint <fixture>` post-upsert is clean.

## Notes
- The `find_vault_root` call is cheap (O(depth)) and run once per
  upsert. Acceptable overhead.
- **R8.5 honest-scope**: NO auto-promotion. If two courses independently
  ingest the same concept BEFORE the operator runs `promote`, two
  course-local copies are created. `lint` will then detect the
  `cross_course_duplicate` finding. This is the documented workflow.
- The `:shared` suffix on `--touched` is a tiny CLI convention. An
  alternative would be a `--touched-shared <path>` separate flag. The
  suffix is chosen for minimal CLI grammar change and is locked by a
  test. If the operator hand-edits the value, no harm — it's just a
  rendering hint.
