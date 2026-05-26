# Task 016.04 — `lint.py` extensions (invariant-enforcement net)

## Use Case Connection
- **UC-3** primary (lint detects cross-course duplicates + invariant
  violations).
- Foundation safeguard for **UC-1** / **UC-2** — every state-mutating
  bead from 016.06 onward runs `lint` against the two-course fixture and
  asserts zero `invariant_violation` findings.

## Task Goal

Extend `commands/lint.py` with the cross-course + two-tier-aware finding
categories so the invariant-net is LIVE before any state-mutating bead
ships (A-M-1 resolution). The lint command becomes the regression
boundary for every subsequent bead.

## Changes Description

### New Files
- None (extends existing `lint.py`).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/lint.py`

**Function `register(sub)`:**
- Add new optional flag: `--limit N` (int, default `None`) — cap the
  number of findings emitted per category (TASK §8 risk 3 mitigation).
  When omitted, no cap.
- Add `--two-tier` flag (default auto-detect): force the two-tier
  scan path even if the operator passes a course root.

**Function `execute(args) -> int`:**

Existing behaviour for the four v1 categories (orphans, dangling,
contradictions, missing pages) is preserved byte-identically when the
vault is single-course (no root schema). For two-tier vaults, the JSON
output gains two additional categories:

1. **`cross_course_duplicate`** (R6.1):
   - Algorithm: call `find_vault_root(args.vault)`. If `vault_root` is
     `None` (single-course), skip the cross-course scan and behave as v1.
     If `vault_root` is set, call `discover_courses(vault_root)` →
     `course_roots`. For each course root, collect `_concepts/*.md` and
     `_entities/*.md` filenames. Build a `dict[name → list[path]]`. Any
     entry where `len(paths) >= 2` becomes a finding.
   - JSON shape per finding:
     ```json
     {"name": "Sharpe Score", "kind": "concept",
      "courses": ["Lessons/Course A/_concepts/Sharpe Score.md",
                  "Lessons/Course B/_concepts/Sharpe Score.md"],
      "suggest": "wiki-ingest promote \"Sharpe Score\""}
     ```
   - Sort the findings list alphabetically by `name` (m-A-5
     / m-5 sort discipline).
   - Each finding's `courses` list also sorted alphabetically by path.

2. **`invariant_violation`** (R6.2):
   - Algorithm: build a `set` of names present at the root
     (`<vault_root>/_concepts/*.md` + `<vault_root>/_entities/*.md`). For
     each course's `_concepts/`/`_entities/`, check intersection.
   - JSON shape per finding:
     ```json
     {"name": "Sharpe Score", "kind": "concept",
      "root_path": "_concepts/Sharpe Score.md",
      "course_paths": ["Lessons/Course A/_concepts/Sharpe Score.md"],
      "suggest": "wiki-ingest promote \"Sharpe Score\" or demote it"}
     ```
   - Sorted by `name`.
   - **Exit code**: if ANY `invariant_violation` finding exists, exit
     code is non-zero (hard failure; R6.2). The existing exit-code logic
     for v1 lint stays put; this is additive.

3. **Cross-layer dangling-link refinement** (R6.3):
   - Existing dangling-link logic considers a `[[Foo]]` reference
     dangling if `Foo.md` doesn't exist in the course. The refinement:
     when the vault has a root schema, ALSO check `<vault_root>/_concepts/`
     and `<vault_root>/_entities/` before flagging as dangling. A
     course→root reference is NOT dangling.
   - When `[[Bar]]` exists ONLY in some OTHER course's `_concepts/`
     (i.e., not in this course, not at root), it IS dangling — the
     existing logic already flags this; add a hint string to the finding:
     `"hint": "exists in <other_course>; consider 'wiki-ingest promote
     \"Bar\"' to share"`.

4. **Root-page footnote-format check (R6.4)**:
   - New category `root_footnote_format_warning`.
   - Algorithm: for each `<vault_root>/_concepts/*.md` and
     `_entities/*.md`, scan footnote definitions. Any `[^src-<slug>]:
     [[<target>]] — <Title>` whose `<target>` is a BARE filename (i.e.,
     does not start with `<course_rel>/_sources/` for any
     `course_rel ∈ {c.relative_to(vault_root) for c in
     discover_courses(vault_root)}`) becomes a finding.
   - JSON shape per finding:
     ```json
     {"page": "_concepts/Sharpe Score.md", "footnote": "[^src-foo]",
      "current_target": "[[foo]]",
      "expected_pattern": "<course_rel>/_sources/<slug>",
      "severity": "warning"}
     ```
   - This is a `warning` (not error) per Q-9 — exit code unaffected.

**Honest-scope note**: the existing four v1 categories (`orphans`,
`dangling_links`, `open_contradictions`, `missing_concept_pages`) keep
their semantics on the COURSE layer; the cross-layer refinement applies
only to dangling-link detection.

**Sort discipline (m-5)**: every list in the JSON output is sorted to
preserve byte-identity across runs. Lock with a fixture-based test.

### Component Integration

- `lint.py` LoC budget extended to ≤450 (architecture §3.2; current
  ~300).
- Consumes `_vault.discover_courses` and `_vault.find_vault_root` (added
  in 016.00).
- No new module-level imports beyond the two new `_vault` names.
- Existing test `tests/test_r11_byte_identity.py` must still pass — the
  v1 single-course path is byte-identical when no root schema is present.

## Test Cases

### Unit Tests (`tests/commands/test_lint.py` — extended)

1. **TC-UNIT-016-04-01:** Cross-course duplicate detection
   - Fixture: two-course vault with `_concepts/Sharpe Score.md` in both.
   - Run: `lint <vault>`.
   - Expected: JSON includes `cross_course_duplicate` finding with both
     paths sorted alphabetically.
2. **TC-UNIT-016-04-02:** Invariant violation detection + non-zero exit
   - Fixture: vault with `_concepts/Sharpe Score.md` at root AND in
     `Lessons/Course A/_concepts/`.
   - Run: `lint <vault>`.
   - Expected: JSON includes `invariant_violation`; exit code is
     non-zero.
3. **TC-UNIT-016-04-03:** Dangling-link refinement (course → root OK)
   - Fixture: course-local page links `[[Sharpe Score]]`; root has
     `_concepts/Sharpe Score.md`; no course-local `Sharpe Score.md`.
   - Run: `lint <vault>`.
   - Expected: `dangling_links` does NOT include `Sharpe Score`.
4. **TC-UNIT-016-04-04:** Dangling-link cross-course flagged with hint
   - Fixture: Course A page links `[[Bar]]`; Course B has
     `_concepts/Bar.md`; root has nothing.
   - Run: `lint <vault>`.
   - Expected: `dangling_links` includes `Bar` with `hint` field naming
     Course B.
5. **TC-UNIT-016-04-05:** Root-page footnote-format warning
   - Fixture: root `_concepts/Sharpe Score.md` has
     `[^src-foo]: [[foo]] — Title` (short form).
   - Run: `lint <vault>`.
   - Expected: `root_footnote_format_warning` finding emitted; exit code
     unaffected (warning not error).
6. **TC-UNIT-016-04-06:** Single-course vault byte-identity
   - Fixture: existing v1 single-course test fixture.
   - Run: `lint <vault>`.
   - Expected: JSON output byte-identical to v1 (no new categories
     present; existing ones unchanged). Use `diff -q` against a frozen
     baseline.
7. **TC-UNIT-016-04-07:** Sort discipline
   - Fixture: 3-course vault with multiple cross-course duplicates.
   - Run: `lint <vault>` twice in random `os.walk` order (simulate via
     fixture).
   - Expected: identical JSON output (sort-by-name discipline).
8. **TC-UNIT-016-04-08:** `--limit N` caps findings per category
   - Fixture: vault with 5 cross-course duplicates.
   - Run: `lint <vault> --limit 2`.
   - Expected: only 2 `cross_course_duplicate` findings in output; a
     `truncated: true` marker is added to the JSON for that category.
9. **TC-UNIT-016-04-09:** Cross-layer non-`Lessons/` path discovery
   - Fixture: vault with courses at `<vault>/Hermes/` (no `Lessons/`).
   - Run: `lint <vault>`.
   - Expected: cross-course detection works (Q-8 — `Lessons/` not
     hardcoded).

### Regression Tests
- `tests/test_r11_byte_identity.py` passes on the existing single-course
  fixture (TC-UNIT-016-04-06 is the strict version).
- `tests/test_architecture.py` passes.
- `validate_skill.py` exits 0.

## Acceptance Criteria
- [ ] All 9 unit tests pass.
- [ ] `lint.py` LoC ≤ 450.
- [ ] Single-course byte-identity preserved (TC-UNIT-016-04-06).
- [ ] Invariant-violation exit code is non-zero (R6.2 hard failure).
- [ ] Sort discipline locked by TC-UNIT-016-04-07.
- [ ] `--limit N` flag works per TC-UNIT-016-04-08.
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.

## Notes
- **A-M-1 critical**: this bead LANDS BEFORE any state-mutating bead.
  After 016.04 merges, every subsequent bead's CI gate runs
  `lint <fixture>` and asserts zero `invariant_violation` findings.
- **A-M-2**: the root-page footnote-format check (R6.4) uses
  `{c.relative_to(vault_root) for c in discover_courses(vault_root)}`
  to compute the valid prefix set — NOT a literal `Lessons/` prefix.
- **Q-9**: the new root-footnote check is a `warning`, not an `error`.
  Exit code stays zero unless an `invariant_violation` exists.
- Honest-scope: ONLY the four new categories are added. No predicate
  extraction (Q-10 deferred to 016.06 promote-time logic), no
  source-slug collision detection (R13.3 honest-scope).
