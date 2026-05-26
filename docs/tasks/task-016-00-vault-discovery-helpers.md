# Task 016.00 — `find_vault_root` + `discover_courses` in `_vault.py`

## Use Case Connection
- Foundation for **UC-1..UC-5** — every command in this task chain consumes
  one of the two new helpers.

## Task Goal

Add two complementary vault-discovery helpers to
`skills/wiki-ingest/scripts/wiki_ingest/_vault.py`:

- `find_vault_root(start: Path) -> tuple[Path, Path | None]` — walks UP
  from a path inside a course to discover `(course_root, vault_root_or_None)`.
- `discover_courses(vault_root: Path) -> list[Path]` — walks DOWN from a
  vault root to enumerate every descendant course root.

No behavioural change to any existing command — the helpers are added,
unit-tested, and committed. Consumer beads (016.04, 016.05, 016.06,
016.07, 016.08, 016.09) wire them in.

## Changes Description

### New Files
- None.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_vault.py`

**Function `find_vault_root(start: Path) -> tuple[Path, Path | None]`:**
- New top-level function.
- Algorithm:
  1. Resolve `start` to its absolute path (`start.resolve()`).
  2. Walk up from `start` toward the filesystem root. For each ancestor
     directory, check `(ancestor / "WIKI_SCHEMA.md").is_file()`.
  3. The FIRST match → `course_root` candidate.
  4. From `course_root.parent`, continue walking up. For each ancestor,
     check `(ancestor / "WIKI_SCHEMA.md").is_file()`.
  5. The second match: peek its `schema_version` (via cheap
     `split_frontmatter` on the first ~1 KiB). If `2.0` → that's
     `vault_root`. If `1.x` or absent → `vault_root = None` and the second
     schema is reported as malformed (no walk continues).
  6. Refuse during the walk to cross a symlinked directory (call
     `_skip_symlink`); refuse to cross a filesystem boundary (compare
     `os.stat(ancestor).st_dev` with the starting device — abort cleanly
     with `vault_root = None`).
  7. If NO `WIKI_SCHEMA.md` is found on the walk up from `start`,
     `die("vault not found from {start}", code=2)`.
- Returns: `(course_root, vault_root)` where `vault_root` is `None` for
  single-course vaults (R1.2 + R9.3 backwards-compat).
- Tested by `tests/test__vault.py` (see Test Cases below).

**Function `discover_courses(vault_root: Path) -> list[Path]`:**
- New top-level function.
- Algorithm:
  1. Verify the input is a vault root: `(vault_root / "WIKI_SCHEMA.md")`
     must exist and the schema's `schema_version` must equal `2.0`
     (otherwise `die("not a vault root: {vault_root}", code=2)`).
  2. Use `os.walk(vault_root, followlinks=False)` (note `followlinks=False`
     enforces OVERLAP-5).
  3. For each `(dirpath, dirnames, filenames)`:
     - Skip the vault root itself (don't return it as a course).
     - If `WIKI_SCHEMA.md in filenames`, peek `schema_version`. If `1.x` →
       add `Path(dirpath)` to result list. Do NOT prune `dirnames` —
       continue descending so nested course schemas are also discovered
       (A-M-4 nested-schema support).
     - Filter `dirnames` to drop symlinked subdirectories (OVERLAP-5
       carry-over).
  4. Return the result list sorted alphabetically by `str(path)`.
- Returns: `list[Path]` of every descendant course root.
- Tested by `tests/test__vault.py`.

**Module-level helper (`_peek_schema_version`)**:
- Add a small private function:
  ```python
  def _peek_schema_version(schema_path: Path) -> str | None:
      """Return `schema_version` field from a WIKI_SCHEMA.md frontmatter, or None."""
  ```
- Implementation: open the file, read up to 1 KiB, run
  `split_frontmatter` on the chunk, return `fm.get("schema_version")` or
  `None` on parse failure. No raise on malformed content (defensive).
- Used by both `find_vault_root` and `discover_courses` to avoid
  re-parsing schemas.

### Component Integration

Existing `_vault.py` functions (`_walk_pages`, `load_vault_pages`,
`ensure_schema`, `load_asset`, `tail_log`) are unchanged. New helpers are
strictly additive. No existing call site is modified in this bead.

The layered DAG remains: `_vault.py` (F3-helper) imports `_safety` (F1)
+ `_frontmatter` (F2) + `_markdown` (F2). The new helpers add only stdlib
imports (`os.walk` is already implicitly available via `pathlib`; explicit
`import os` may be needed).

## Test Cases

### Unit Tests (`tests/test__vault.py` — extended)

1. **TC-UNIT-016-00-01:** `find_vault_root` on a single-course vault
   - Input: a vault with `WIKI_SCHEMA.md` (v1.x) at `/tmp/v/course-a/` and
     no parent schema; `start = /tmp/v/course-a/_concepts/Foo.md`.
   - Expected: `(Path("/tmp/v/course-a"), None)`.
2. **TC-UNIT-016-00-02:** `find_vault_root` on a two-tier vault
   - Input: vault root at `/tmp/v/` (schema_version=2.0), course at
     `/tmp/v/Lessons/Hermes/` (schema_version=1.0); `start = /tmp/v/Lessons/Hermes/_sources/foo.md`.
   - Expected: `(Path("/tmp/v/Lessons/Hermes"), Path("/tmp/v"))`.
3. **TC-UNIT-016-00-03:** `find_vault_root` with mismatched root schema
   - Input: vault root has `schema_version: 1.5` (not 2.0).
   - Expected: returns `(course_root, None)` — outer schema treated as
     "not a vault root."
4. **TC-UNIT-016-00-04:** `find_vault_root` with no schema anywhere
   - Input: `start` deep inside a directory tree with no `WIKI_SCHEMA.md`.
   - Expected: `die(..., code=2)` — SystemExit raised, captured in test.
5. **TC-UNIT-016-00-05:** `find_vault_root` refuses symlink ancestor
   - Input: symlink at one of the ancestor positions.
   - Expected: walk treats it as crossing-boundary; either returns
     `vault_root=None` or aborts cleanly. Documented in test.
6. **TC-UNIT-016-00-06:** `discover_courses` on a two-tier vault
   - Input: vault root with 3 courses under `Lessons/`.
   - Expected: returns sorted list of 3 course paths.
7. **TC-UNIT-016-00-07:** `discover_courses` with non-`Lessons/` layout
   - Input: vault root with courses at `Hermes/`, `OpenClaw/` directly
     (no `Lessons/` parent).
   - Expected: returns both (Q-8 — `Lessons/` not hardcoded).
8. **TC-UNIT-016-00-08:** `discover_courses` with nested course schemas
   - Input: vault has `Lessons/2026/Spring/Hermes/` with its own schema
     AND `Lessons/2026/Fall/OpenClaw/` with its own schema.
   - Expected: both course paths returned independently (A-M-4 nested
     support).
9. **TC-UNIT-016-00-09:** `discover_courses` skips symlinked subdirs
   - Input: vault has a symlinked subdir.
   - Expected: symlinked subdir's contents NOT walked; result list does
     not contain anything under it (OVERLAP-5).
10. **TC-UNIT-016-00-10:** `discover_courses` refuses non-root input
    - Input: a course root (schema_version=1.0).
    - Expected: `die(..., code=2)`.

### Regression Tests
- All existing `tests/test__vault.py` tests still pass (existing helpers
  untouched).
- `tests/test_architecture.py` passes (no new imports outside the layered DAG).
- `tests/test_r11_byte_identity.py` passes (single-course CLI behaviour
  byte-identical — no caller has been wired yet).

## Acceptance Criteria
- [ ] `find_vault_root` and `discover_courses` exist at module level in
      `_vault.py` with the signatures specified above.
- [ ] All 10 new unit tests pass.
- [ ] Existing `tests/test__vault.py` suite still green.
- [ ] `tests/test_architecture.py` still green.
- [ ] `tests/test_r11_byte_identity.py` still green.
- [ ] `validate_skill.py` still exits 0.
- [ ] `_vault.py` LoC ≤ 250 (architecture budget; current ~173).
- [ ] No behavioural change to any CLI subcommand (helpers are unused
      by all callers in this bead).

## Notes
- This bead is pure additive — no caller is wired yet. The next consumer
  is Task 016.04 (lint cross-course).
- The same `_peek_schema_version` helper will be reused by
  `commands/reindex.py` in 016.08 for M-4 mode detection. Keep it private
  (`_peek_*`) but stable in signature so it can be re-imported cleanly.
- Performance: `find_vault_root` is O(depth-to-root); `discover_courses`
  is O(directories under vault_root). Both well within TASK §4.1
  ≤0.5 s budget.
