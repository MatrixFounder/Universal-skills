# Task 016.06 — `promote --apply` write path + footnote rewrite + log append

## Use Case Connection
- **UC-1** Main scenario steps 7–8 + Alternative scenarios A4 (contradiction
  at merge time) and A7 (idempotent re-run).

## Task Goal

Phase 2 of the Stub-First two-pass for `promote`. Replace the 016.05
stub `die("--apply not implemented")` with the real write path: read
N course-local copies, union frontmatter (including `promoted_from:`
via 016.02), additive-merge body (via 016.01's `_page_merge` primitives),
rewrite footnotes to vault-relative form (A-M-2), write the root page,
delete the course-local copies, update each affected course's `index.md`
+ `log.md`, update root `index.md` (create if absent).

This is the **first state-mutating bead**. The 016.04 invariant-net is
already live; every test gate runs `lint <fixture>` and asserts zero
`invariant_violation`.

## Changes Description

### New Files
- None (extends 016.05 skeleton).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/promote.py`

**Function `execute(args) -> int` — `--apply` branch:**

1. **Re-run preconditions** (same as dry-run path — no shortcuts).
2. **Read all course-local copies** (and root copy if `mode ==
   "merge_into_root"`):
   - For each path, `read_text(path, max_bytes=MAX_PAGE_BYTES)`.
   - `split_frontmatter(content)` → `(fm, body)`.
3. **Union frontmatter** (R3.3):
   - `created` = earliest of all `created:` values (parse as ISO date;
     compare lexically — ISO is sortable).
   - `description` = LONGER of all `description:` values (Q-6
     resolution). Ties broken by first source course (sorted).
   - `kind` = the agreed kind (already validated).
   - All other simple fields: take the first source's value; if absent
     in first, fall back to next, etc.
   - **`promoted_from`** field: list-of-dicts. For each contributing
     course, add `{"course": <course_root.name>, "date": <today>}`. If
     the root copy already has a `promoted_from` list, MERGE with the
     new entries (deduplicate by `(course, date)` tuple).
4. **Additive body merge** (R3.4):
   - Initialise `merged_body` from the FIRST source's body (sorted by
     course path so the merge order is deterministic).
   - For each subsequent source's body:
     - For each known section (`## Definition`, `## Facts`,
       `## Sources mentioning this`), call the appropriate `_page_merge`
       primitive (`upsert_source_row`, `append_fact`).
     - For custom sections (defined per the course's WIKI_SCHEMA.md or
       discovered as non-default H2s), append the source's section body
       under the same H2 in `merged_body` (or create the H2 if absent).
   - **Contradiction detection** (R3.6, Q-10 literal-line-diff):
     - For each pair of `## Facts` lines in different source bodies
       with the same `[^src-<slug>]` citation removed (i.e., the
       fact-text prefix), if the texts differ literally → call
       `append_contradiction(merged_body, claim_existing, fact_new,
       source_slug_new)`. Increment `contradictions_raised`.
     - Honest-scope: no semantic predicate extraction.
5. **Rewrite footnotes to vault-relative form** (R3.5, A-M-2):
   - For each footnote definition `[^src-<slug>]: [[<target>]] — <Title>`
     on `merged_body`, look up which source course originally cited that
     slug (the source course is the one whose `_sources/<slug>.md`
     exists). Rewrite:
     ```
     [^src-foo]: [[<course_rel>/_sources/foo]] — Foo Title
     ```
     where `<course_rel> = source_course_root.relative_to(args.vault)`.
   - Use a regex anchored to `^` + line-end (`re.M`) to prevent
     "second-definition smuggling" (TASK §4.2 / T16-S3). Lock with a
     unit test.
6. **Write root page** (R3.6 invariant):
   - `write_text(merge_to_path, _serialize(fm, merged_body))` via
     `_atomic_write_text` (T16-S5).
7. **Delete course-local copies** (R3.6 invariant):
   - For each course-local source path: `os.unlink(path)`. Use
     `_atomic_write_text`'s deletion semantics if a wrapper exists;
     otherwise plain unlink under `flock` discipline.
   - **Crash safety**: if write_text fails AFTER root page written but
     BEFORE all course copies deleted, the vault is in an
     invariant-violation state. Document this in the function docstring
     and lock the gate via TC-UNIT-016-06-09 (partial-failure
     stress test).
8. **Update affected courses' `index.md`** (R3.8):
   - For each course in `merge_from`:
     - Read `course/index.md`; locate the row for `<name>` under
       `## Concepts` (or `## Entities`); remove it.
     - Add `[[<name>]] — (shared)` to `## Shared concepts referenced`
       (or `## Shared entities referenced`) — create the section if it
       doesn't yet exist (insert after `## Concepts`/`## Entities`).
     - Idempotent: re-running doesn't duplicate rows.
9. **Update root `index.md`** (R3.9):
   - If `<vault_root>/index.md` doesn't exist, create from the bundled
     root-index template (small file with just `## Concepts` and
     `## Entities` H2s).
   - Add `<name>` row under the right H2.
   - Idempotent.
10. **Append course `log.md`** (R3.10):
    - For each course in `merge_from`, append:
      ```markdown

      ## [YYYY-MM-DD] promote | <Name>
      - Merged from: <course_rel>/_concepts/<Name>.md, …
      - Destination: _concepts/<Name>.md (vault root)
      - Contradictions raised: <n>
      ```
    - Use existing `append_log` primitive (no new helper).
11. **Idempotency / no-op** (R4.3): if `--apply` re-run finds the page
    already at root and NO course-local copies remain, emit
    `{"applied": true, "noop": true}` and exit 0.
12. **Emit final JSON**: `{"applied": true, "noop": false, "merged_to":
    ..., "merged_from": [...], "contradictions_raised": <n>,
    "mode": "first_promote" | "merge_into_root"}`.

### Component Integration

- Now uses the full F2 stack: `_markdown` (section locators),
  `_frontmatter` (split + splice via 016.02 list-of-dicts), `_page_merge`
  (primitives via 016.01).
- Reuses `commands/append_log` and `commands/update_index` via
  *function imports* — but the architecture invariant forbids
  cross-command imports. **Workaround**: extract the row-add helper
  from `update_index.py` into `_vault.py` (or `_page_merge.py` if more
  appropriate) BEFORE this bead, or inline the row-add logic in
  `promote.py`. **Decision**: inline the row-add logic in `promote.py`
  for v1 (avoid the architecture change); revisit if it's >30 LoC.
  Document in the task file.
- `promote.py` LoC: ≤400 (architecture §3.2 final budget).

## Test Cases

### Unit Tests (`tests/commands/test_promote.py` — extended)

1. **TC-UNIT-016-06-01:** 2-course happy path (apply)
   - Fixture: 2-course vault with `Sharpe Score.md` in both.
   - Run: `promote "Sharpe Score" --vault <v> --apply`.
   - Expected: `<v>/_concepts/Sharpe Score.md` exists with merged body;
     both course copies deleted; both course `index.md`s updated;
     `<v>/index.md` created with the row; both `log.md`s gain the entry.
2. **TC-UNIT-016-06-02:** Footnote rewrite to vault-relative form (A-M-2)
   - Post-apply: scan the root page's footnote definitions; every
     `[^src-<slug>]: [[<target>]]` has `<target>` starting with
     `<course_rel>/_sources/<slug>` for the source's actual course
     (not literally `Lessons/`).
3. **TC-UNIT-016-06-03:** 3-course merge
   - Fixture: 3 courses with the same concept.
   - Expected: union frontmatter, additive body, 3 entries in
     `promoted_from`.
4. **TC-UNIT-016-06-04:** Contradiction detection (literal-line-diff,
   Q-10)
   - Fixture: Course A's body has `- Sharpe = (R-Rf)/σ [^src-a]`;
     Course B's has `- Sharpe = R/σ [^src-b]`.
   - Expected: merged page has a `## Contradictions` block; JSON has
     `contradictions_raised: 1`.
5. **TC-UNIT-016-06-05:** Re-promote (R3.7)
   - Fixture: page already at root; Course C has a course-local copy
     with a new fact.
   - Expected: course C's content folded into root page; course C's
     copy deleted; root `index.md` unchanged (already listed);
     `promoted_from` gains the C entry.
6. **TC-UNIT-016-06-06:** Idempotency no-op (R4.3)
   - Fixture: after TC-UNIT-016-06-01, all course copies are gone.
   - Run: `promote "Sharpe Score" --apply` again.
   - Expected: exit 0; JSON has `"noop": true`; no files mutated.
7. **TC-UNIT-016-06-07:** `lint` post-promote reports clean
   - Run: after TC-UNIT-016-06-01, `lint <vault>`.
   - Expected: zero `invariant_violation` findings; zero
     `cross_course_duplicate` for `Sharpe Score`.
8. **TC-UNIT-016-06-08:** Atomic-write discipline (T16-S5)
   - Mock `_atomic_write_text` to simulate write failure; ensure tmp
     file is unlinked, root page not partially written, no course copy
     deleted.
9. **TC-UNIT-016-06-09:** Partial-failure observability
   - Simulate failure AFTER root page written and BEFORE all course
     copies deleted: lint MUST detect `invariant_violation` (T16-S5
     covered by 016.04 net).
10. **TC-UNIT-016-06-10:** Footnote regex anchoring (T16-S3)
    - Adversarial fixture: course body contains a deliberately
      malformed footnote line. The rewrite MUST process exactly one
      definition per `[^src-<slug>]` key per line — no second-definition
      smuggling.
11. **TC-UNIT-016-06-11:** `description:` merge takes LONGER (Q-6)
    - Fixture: course A's frontmatter has `description: "Short."`;
      course B has `description: "A long description with more detail."`.
    - Expected: root page's `description` is the longer one.
12. **TC-UNIT-016-06-12:** `_concepts/` vs `_entities/` kind preserved
    - Fixture: 2 courses both have the entity at `_entities/Hermes Agent.md`.
    - Expected: root page lands at `_entities/Hermes Agent.md`;
      `index.md` updated under `## Entities`.

### Regression Tests
- `tests/test_r11_byte_identity.py` passes on the v1 single-course
  fixture (no two-tier behaviour invoked there).
- `tests/test_architecture.py` passes.
- `tests/commands/test_lint.py` passes.
- `tests/commands/test_upsert_page.py` passes (the `_page_merge`
  primitives are unchanged from 016.01; this bead consumes them).
- `lint <two_course_fixture>` reports zero `invariant_violation`.

## Acceptance Criteria
- [ ] All 12 unit tests pass.
- [ ] Post-bead `lint <two_course_fixture>` is clean.
- [ ] `promote.py` LoC ≤ 400.
- [ ] No course-local file remains on disk after a successful apply.
- [ ] Idempotent re-run is a clean no-op.
- [ ] Footnote rewrite uses `course_root.relative_to(vault_root)` (A-M-2).
- [ ] `_atomic_write_text` discipline locked on every write (T16-S5).
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.

## Notes
- This is Phase 2 of `promote`'s Stub-First two-pass. After this bead,
  the dry-run path of 016.05 becomes a thin wrapper that computes the
  same plan but does NOT call the write helpers.
- The "inline row-add helper" decision (vs extracting from
  `commands/update_index.py`) keeps the architecture invariant intact
  but adds ~20–40 LoC duplication. Justified for v1; the planner notes
  in PLAN §7 risk 5 that this is a controlled trade-off.
- The crash-safety story (TC-UNIT-016-06-09) is honest-scope: a
  mid-promote failure leaves the vault in an invariant-violation state;
  the lint net detects it; the operator re-runs `promote --apply` which
  resumes (idempotent). No transactional rollback.
- All paths in the JSON are vault-relative (consistent with the dry-run
  envelope).
