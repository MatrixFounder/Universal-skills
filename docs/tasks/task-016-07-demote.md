# Task 016.07 — `commands/demote.py` (full)

## Use Case Connection
- **UC-2** Main scenario + Alternative scenarios A1 (cross-course
  citation refusal), A2 (target course absent), A3 (page not at root).

## Task Goal

Implement `commands/demote.py` end-to-end (no Stub-First split — demote
is smaller and reversible). The command moves a root-level page back to
a target course's `_concepts/`/`_entities/`, refuses if any other course
cites it, rewrites footnotes to short form, strips `promoted_from:`,
updates indexes and logs.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/commands/demote.py` (≤300 LoC
  per architecture §3.2).
- `skills/wiki-ingest/scripts/tests/commands/test_demote.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

- Add `from wiki_ingest.commands import demote` to imports.
- Add `demote` to `_COMMAND_MODULES` tuple.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/demote.py` (new)

**Function `register(sub)`:**
- Subparser `demote`.
- Positional: `name` (canonical filename without `.md`).
- Required-named: `--vault <PATH>` (vault root), `--to <Course>` (target
  course name, NOT a path — resolved against `discover_courses` result;
  per A-M-2 the `Lessons/` convention is honoured but not hardcoded).
- Optional: `--dry-run` (off by default per Q-2b — demote is reversible,
  cheaper to undo, so no dry-run-by-default).
- Help-strings cite R5 / Q-2b for traceability.

**Function `execute(args) -> int`:**

1. **Vault validation** (R9.1, R9.2): same schema-peek as 016.05.
2. **Name sanitisation**: `_safe_name(args.name, kind="page")`.
3. **Target course resolution**:
   - `course_roots = discover_courses(args.vault)`.
   - Match by last path segment: `target = next((c for c in course_roots
     if c.name == args.to), None)`.
   - If not found → `die(f"target course not found: {args.to}",
     code=1)` (R5.1 alternative scenario A2).
4. **Root page lookup** (R5.1):
   - `root_candidates = [args.vault / "_concepts" / f"{args.name}.md",
     args.vault / "_entities" / f"{args.name}.md"]`.
   - `root_page = next((p for p in root_candidates if p.is_file()),
     None)`.
   - If `None` → `die("page is not at root; nothing to demote",
     code=1)` (A3).
   - `kind = "concept" if root_page.parent.name == "_concepts" else
     "entity"`.
5. **Read root page + parse**:
   - `content = read_text(root_page, max_bytes=MAX_PAGE_BYTES)`.
   - `fm, body = split_frontmatter(content)`.
6. **Cross-course citation scan** (R5.2 / A1):
   - Define: a citation = a `[^src-<slug>]: [[<target>]] — <Title>`
     definition on the root page whose `<target>` resolves to a file
     `<some_course_root>/_sources/<slug>.md`. (m-A-2 clarification.)
   - Extract every `[^src-<slug>]: [[<target>]]` line from `body`. For
     each, parse `<target>` and decompose into `<course_rel>/_sources/<slug>`.
   - For each citation whose `<course_rel>` is NOT
     `target.relative_to(args.vault)` → add to `conflicting_citations`.
   - If `conflicting_citations` is non-empty:
     - `die(f"refused: page is cited by sources outside {args.to}: "
       f"{conflicting_citations}", code=1)`.
   - Atomic: NO files touched (T16-S5 write-side discipline).
7. **Filter facts** (R5.5 — defensive):
   - After the precondition passes, all facts cite sources from the
     target course. The filter step is a no-op in the happy path but
     locked by an explicit pass that iterates `## Facts` lines and
     drops any whose `[^src-<slug>]` is not in the citation-allowlist.
8. **Rewrite footnotes back to short form** (R5.3):
   - For each `[^src-<slug>]: [[<course_rel>/_sources/<slug>]] — <Title>`
     line, rewrite to `[^src-<slug>]: [[<slug>]] — <Title>`.
   - Regex anchored to `^` + line-end (`re.M`) — same T16-S3 anchor
     discipline as 016.06.
9. **Strip `promoted_from:`** (R5.4):
   - Use `_splice_frontmatter_fields(content, {"promoted_from": None},
     fm)` — the existing remove-field path (validated by 016.02).
10. **Compute target path** (R5.0):
    - `target_path = target / f"_{kind}s" / f"{args.name}.md"`.
    - If `target_path.is_file()` → `die("target already has a
      course-local copy; demote would clobber", code=1)`. (Defensive —
      should be precluded by 016.04 lint invariant net, but lock here.)
11. **`--dry-run` path**: emit `DemotionPlan` JSON to stdout and exit 0;
    no writes.
12. **Apply path**:
    - `write_text(target_path, content)` via `_atomic_write_text`.
    - `os.unlink(root_page)` (`flock` discipline).
    - Update root `index.md`: remove the `[[<name>]]` row from
      `## Concepts` or `## Entities`. (Leave H2 even if empty — easier
      to add the next page.)
    - Update target course's `index.md`: remove the `[[<name>]]` row
      from `## Shared concepts referenced` / `## Shared entities
      referenced`; add it back to `## Concepts` / `## Entities`.
    - Append target course's `log.md`:
      ```markdown

      ## [YYYY-MM-DD] demote | <Name>
      - Source: _concepts/<Name>.md (vault root)
      - Destination: _concepts/<Name>.md
      - Citation guard: passed
      ```
    - Emit `{"applied": true, "moved_to": "...", "moved_from": "...",
      "kind": "<kind>"}` JSON.

### Component Integration

- F3 driver; imports `_safety`, `_markdown`, `_frontmatter`, `_vault`,
  `_page_merge` (any of the four primitives if needed, e.g., for
  re-deduping after the footnote rewrite — likely not).
- Does NOT import from any other `commands/*.py`.
- Inline row-management helpers for `index.md` updates (consistent
  decision with 016.06).
- `_atomic_write_text` discipline on every write (T16-S5).

## Test Cases

### Unit Tests (`tests/commands/test_demote.py` — new)

1. **TC-UNIT-016-07-01:** Happy path (R5.0)
   - Fixture: vault from a successful 016-06-01 promote of `Sharpe Score`.
   - Simulate Course B's footnotes have been manually cleaned out (only
     Course A cites the page now).
   - Run: `demote "Sharpe Score" --vault <v> --to "Course A"`.
   - Expected: root page deleted; `Lessons/Course A/_concepts/Sharpe
     Score.md` exists with short-form footnotes; root `index.md` row
     removed; Course A's `index.md` has the row back under `## Concepts`;
     `log.md` entry appended.
2. **TC-UNIT-016-07-02:** Cross-course citation refusal (R5.2 / A1)
   - Fixture: root page with citations from both Course A AND Course B
     `_sources/`.
   - Run: `demote "Sharpe Score" --to "Course A"`.
   - Expected: exit non-zero; stderr lists the Course B
     `(course, source-slug)` pairs; no files touched.
3. **TC-UNIT-016-07-03:** Target course absent (A2)
   - Run: `demote "Foo" --to "Course Z"` where "Course Z" doesn't exist.
   - Expected: `die(..., code=1)`; "target course not found".
4. **TC-UNIT-016-07-04:** Page not at root (A3)
   - Fixture: page lives only in a course.
   - Run: `demote "Foo" --to "Course A"`.
   - Expected: `die(..., code=1)`; "page is not at root".
5. **TC-UNIT-016-07-05:** Footnote rewrite to short form (R5.3)
   - Pre: root page has `[^src-foo]: [[Course A/_sources/foo]] — Title`.
   - Post-demote: target page has `[^src-foo]: [[foo]] — Title`.
6. **TC-UNIT-016-07-06:** `promoted_from:` removed (R5.4)
   - Pre: root page frontmatter has
     `promoted_from: [{course: "Course A", date: "2026-05-26"}]`.
   - Post-demote: target page frontmatter does NOT have
     `promoted_from`.
7. **TC-UNIT-016-07-07:** Round-trip (`promote → demote → ?`) preserves
   short-form footnotes
   - Fixture: start from a clean 2-course vault (one course's copy);
     `promote --apply` (cross-course-promote-by-deleting-one-side fails
     R3.1 — need to set up the fixture so the page exists in both
     courses; demote pulls back to one). Refine fixture in
     `tests/fixtures/`.
   - Assertion: after round-trip, the demoted page's footnote lines are
     byte-identical to a fresh course-local copy.
8. **TC-UNIT-016-07-08:** `--dry-run` writes nothing (Q-2b not default,
   but supported)
   - Run: `demote "Sharpe Score" --to "Course A" --dry-run`.
   - Expected: stdout has the plan; no files touched.
9. **TC-UNIT-016-07-09:** Non-`Lessons/` layout (Q-8 / A-M-2)
   - Fixture: vault has Course A at `<vault>/Hermes/`.
   - Run: `demote "Foo" --to "Hermes"`.
   - Expected: works correctly; target path resolves to
     `<vault>/Hermes/_concepts/Foo.md`; footnotes rewritten to short
     form.
10. **TC-UNIT-016-07-10:** `lint` post-demote is clean
    - After TC-UNIT-016-07-01, `lint <vault>` reports zero
      `invariant_violation` and zero `cross_course_duplicate`.

### Regression Tests
- `tests/test_r11_byte_identity.py` passes (v1 surface unchanged).
- `tests/test_architecture.py` passes.
- `tests/commands/test_promote.py` passes (no regression).
- `tests/commands/test_lint.py` passes.

## Acceptance Criteria
- [ ] All 10 unit tests pass.
- [ ] `demote.py` LoC ≤ 300.
- [ ] `lint <fixture>` post-demote is clean.
- [ ] Cross-course citation refusal locked (TC-UNIT-016-07-02).
- [ ] Footnote rewrite round-trips byte-identically with a fresh
      course-local page (TC-UNIT-016-07-07).
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.

## Notes
- Demote is intentionally NOT split into stub + apply. It is smaller,
  reversible (just `promote --apply` again), and the cross-course
  citation scan is the dominant logic — no value in a separate skeleton
  bead.
- m-A-2 resolution: "a citation = a `[^src-<slug>]` reference on the
  root page whose `<slug>.md` file lives in any course's `_sources/`
  directory other than the `--to` target."
- Q-2b: demote does NOT default to dry-run. Operators who want a preview
  pass `--dry-run` explicitly.
- The inline `index.md` row-management helpers are the same shape as
  the ones in 016.06 — if duplication exceeds ~40 LoC across both
  commands, consider promoting to a `_vault.py` helper in a follow-up
  task (NOT in this bead — scope discipline).
