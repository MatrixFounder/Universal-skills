# Task 016.08 — `commands/reindex.py` extensions (Shared sections + root mode + cascade)

## Use Case Connection
- **UC-5** Main scenario (reindex builds `## Shared * referenced`
  sections in a course's `index.md`) + A1 (reindex on vault root rebuilds
  root `index.md`).

## Task Goal

Extend `commands/reindex.py` with three additive behaviours:

1. When run on a **course** in a two-tier vault, scan the course's
   `_sources/` for footnote-slug references and add a
   `## Shared concepts referenced` / `## Shared entities referenced`
   section to the course's `index.md` for each root page that this
   course's sources cite (R7.1).
2. When run on the **vault root** (detected via M-4 schema-peek), rebuild
   the root `index.md` from disk — `## Concepts` and `## Entities` only
   (no `## Sources`) — preserving custom sections (R7.2).
3. Optional `--cascade` flag triggers reindex on every discovered course
   after the root rebuild (R7.2).

Existing v1 behaviour is preserved for course-mode invocations.

## Changes Description

### New Files
- None (extends existing `reindex.py`).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/reindex.py`

**Function `register(sub)`:**
- Add `--cascade` flag (action="store_true", default False).
- Update help-string to reflect the two-tier behaviour.

**Function `execute(args) -> int`:**

1. **Mode detection** (M-4 resolution):
   - Read `<args.vault>/WIKI_SCHEMA.md` via `_peek_schema_version`.
   - `2.0` → root mode.
   - `1.x` → course mode (existing v1 behaviour).
   - Missing or mismatched → existing v1 `die` message.
2. **Course mode** (existing behaviour + new section):
   - Existing logic rebuilds `## Sources` / `## Concepts` / `## Entities`
     from disk and preserves all other sections (R7.3).
   - **NEW** (R7.1): after the existing rebuild, run an extra scan:
     - `course_root = args.vault` (course mode).
     - Call `find_vault_root(course_root)` to get `vault_root`. If
       `vault_root is None` → skip the shared-referenced step (single-
       course vault).
     - For each `.md` file under `course_root / "_sources/"`, parse its
       slug (filename without `.md`).
     - For each root concept/entity page (under `vault_root /
       "_concepts/"` and `_entities/`), extract footnote definitions via
       `_extract_wikilinks_with_anchors(body)` or the existing footnote
       parser. For each definition citing a slug that matches a
       course-local source file → the root page is referenced by this
       course.
     - Add `## Shared concepts referenced` / `## Shared entities
       referenced` sections to the course's `index.md`, listing the
       referenced root pages as `- [[<name>]] — (shared)`.
     - Sort alphabetically. Idempotent (re-run is a no-op).
     - Honest-scope: the existing v1 `index.md` write path runs via
       `_atomic_write_text` — extend the same write.
   - **NEW** in JSON output: add `"shared_referenced": {"concepts":
     [...], "entities": [...]}` field (R7.4).
3. **Root mode** (new):
   - `vault_root = args.vault`.
   - Read `vault_root / "_concepts/"` and `_entities/`; build sorted row
     lists.
   - Open existing `<vault_root>/index.md` if it exists; otherwise
     create from a minimal in-memory template (`## Concepts\n\n##
     Entities\n`).
   - Rebuild `## Concepts` and `## Entities` rows (replace the section
     bodies — same idiom as v1 course mode).
   - Preserve all custom sections (any H2 other than `## Concepts` and
     `## Entities`).
   - Do NOT rebuild `## Sources` — sources never live at the root
     (spec §2.5).
   - **If `--cascade`**: after root rebuild, run
     `discover_courses(vault_root)`. For each course root, run the
     course-mode logic above (with the shared-referenced extension).
   - JSON output: `{"mode": "root", "concepts": <n>, "entities": <n>,
     "cascaded": [<course_paths>], "preserved_sections": [...]}`.

### Component Integration

- F3 driver. Imports: `_safety`, `_markdown`, `_frontmatter`, `_vault`
  (now includes `find_vault_root`, `discover_courses`, and the private
  `_peek_schema_version`).
- LoC budget: ≤350 (architecture §3.2; current ~250).
- Reuses the existing v1 course-rebuild logic without modification —
  the shared-referenced section is added in a follow-up pass after
  the v1 rebuild completes.

## Test Cases

### Unit Tests (`tests/commands/test_reindex.py` — extended)

1. **TC-UNIT-016-08-01:** Course mode adds `## Shared concepts referenced`
   - Fixture: two-tier vault from a post-016.06 state; Course A's
     `_sources/foo.md` exists; root page `_concepts/Sharpe Score.md`
     has footnote `[^src-foo]: [[Course A/_sources/foo]] — Title`.
   - Run: `reindex <vault>/Lessons/Course A`.
   - Expected: Course A's `index.md` gains `## Shared concepts
     referenced` containing `- [[Sharpe Score]] — (shared)`.
2. **TC-UNIT-016-08-02:** Course mode without two-tier vault — no
   regression
   - Fixture: single-course vault (no root schema).
   - Run: `reindex <vault>`.
   - Expected: byte-identical to v1 (no `## Shared *` sections added);
     `tests/test_r11_byte_identity.py`-style assertion.
3. **TC-UNIT-016-08-03:** Root mode rebuilds `## Concepts` / `## Entities`
   - Fixture: vault root with 3 concept files + 2 entity files; existing
     `index.md` has stale rows + a `## Notes` custom section.
   - Run: `reindex <vault>` (vault root).
   - Expected: `## Concepts` and `## Entities` rebuilt; `## Notes`
     preserved verbatim.
4. **TC-UNIT-016-08-04:** Root mode creates `index.md` if absent
   - Fixture: vault root without `index.md`.
   - Run: `reindex <vault>`.
   - Expected: `<vault>/index.md` created; populated with
     `## Concepts` and `## Entities`.
5. **TC-UNIT-016-08-05:** `--cascade` reindexes every course
   - Fixture: 3-course vault.
   - Run: `reindex <vault> --cascade`.
   - Expected: root `index.md` rebuilt; all 3 course `index.md` files
     rebuilt (with `## Shared * referenced` if applicable); JSON
     `cascaded` lists all 3 course paths.
6. **TC-UNIT-016-08-06:** Mode detection via schema peek (M-4)
   - Fixture: vault root with `schema_version: 2.0`.
   - Run: `reindex <vault>`.
   - Expected: root mode triggered.
   - Counter-fixture: course root with `schema_version: 1.0`.
   - Run: `reindex <course_root>`.
   - Expected: course mode triggered.
   - Counter-fixture: directory with no schema.
   - Run: `reindex <dir>`.
   - Expected: existing v1 `die` message.
7. **TC-UNIT-016-08-07:** No `## Sources` H2 written at root
   - Fixture: root `index.md` does NOT have `## Sources` before or after
     rebuild.
   - Even if a root page contains the literal string `## Sources` in its
     body, the root `index.md` does not gain such an H2.
8. **TC-UNIT-016-08-08:** Idempotency
   - Run `reindex` twice in a row.
   - Expected: second run produces byte-identical `index.md`s; no
     duplicate rows in `## Shared *` sections.
9. **TC-UNIT-016-08-09:** Custom sections in course mode preserved
   - Existing test from 015 — must still pass on a course with custom
     sections.
10. **TC-UNIT-016-08-10:** Non-`Lessons/` layout (Q-8 / A-M-2)
    - Fixture: vault with course at `<vault>/Hermes/`.
    - Run: `reindex <vault> --cascade`.
    - Expected: `<vault>/Hermes/` reindexed; `## Shared *` references
      computed with `Hermes/_sources/<slug>` (not `Lessons/Hermes/...`).

### Regression Tests
- `tests/test_r11_byte_identity.py` passes (v1 single-course mode is
  byte-identical, TC-UNIT-016-08-02).
- `tests/test_architecture.py` passes.
- `lint <fixture>` post-reindex is clean.
- `tests/commands/test_promote.py` passes.

## Acceptance Criteria
- [ ] All 10 unit tests pass.
- [ ] `reindex.py` LoC ≤ 350.
- [ ] Single-course vault byte-identity preserved (TC-UNIT-016-08-02).
- [ ] Custom sections preserved in both root and course modes.
- [ ] Mode detection per M-4 schema peek (TC-UNIT-016-08-06).
- [ ] `--cascade` triggers course reindex per TC-UNIT-016-08-05.
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.

## Notes
- M-4 resolution: mode detection is by `schema_version` peek, NOT by a
  `--root` flag. This makes the CLI surface unchanged for v1 callers.
- Honest-scope: no rebuild of `_sources/` at the root (sources never
  live there per spec §2.5). The `## Sources` H2 is absent from the
  root `index.md` template.
- Q-7 honest-scope: full-path links `[[Course A/Foo]]` in custom
  sections are LEFT ALONE — not normalised.
- The shared-referenced computation may be slow on large vaults
  (O(courses × sources × root_pages × footnotes)). Use the
  `_extract_wikilinks_with_anchors` mask-once helper to keep it O(N)
  in pages (TASK §4.1 budget ≤ 1 s on 5×100 fixture; documented).
