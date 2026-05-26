# Task 016.05 — `commands/promote.py` skeleton + dry-run path

## Use Case Connection
- **UC-1** Main scenario steps 1–6 (operator runs `promote`, sees the
  dry-run plan).
- Stubs the `promote` surface so 016.06 can replace the dry-run with the
  apply path.

## Task Goal

Create `wiki_ingest/commands/promote.py` with the `register`/`execute`
contract. The first bead implements ONLY the dry-run path (R4.1) and the
pre-condition checks (R3.1, R3.2, R3.7, R9.1, R9.2). Writing logic is
stubbed — emit a structured `PromotionPlan` JSON envelope but do NOT
delete files or write the root page.

Per Stub-First (PLAN §2), this is Phase 1: skeleton + tests assert the
dry-run JSON contract. Phase 2 (016.06) replaces the stub with real
computation + `--apply` write path.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/commands/promote.py` (skeleton,
  ≤200 LoC at this bead; ≤400 final after 016.06).
- `skills/wiki-ingest/scripts/tests/commands/test_promote.py` — unit
  tests for dry-run cases.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

- Add `from wiki_ingest.commands import promote` to the import block.
- Add `promote` to the `_COMMAND_MODULES` tuple (existing pattern from
  PLAN 015).

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/promote.py` (new)

**Function `register(sub: argparse._SubParsersAction) -> None`:**
- Create subparser `promote`.
- Positional: `name` (the canonical concept/entity filename without
  `.md`).
- Required-named: `--vault <PATH>` (the vault root).
- Optional: `--kind {concept,entity}` (default = auto-infer from
  duplicates).
- Optional: `--apply` (default off — dry-run is default per Q-2 / R4.1).
- Help-strings cite R3 / R4 / Q-2 for traceability.

**Function `execute(args: argparse.Namespace) -> int`:**

Skeleton (logic stubbed):

1. **Vault validation** (R9.1, R9.2):
   - Run `_peek_schema_version(args.vault / "WIKI_SCHEMA.md")`.
   - If file absent → `die("vault root WIKI_SCHEMA.md absent; run init
     --root first", code=2)`.
   - If `schema_version != "2.0"` → `die("vault root schema must declare
     schema_version: 2.0 (got: <X>)", code=2)`.
2. **Name sanitisation**: `_safe_name(args.name, kind="page")` (rejects
   traversal, control chars, NFKC variants).
3. **Discover courses**: `course_roots = discover_courses(args.vault)`.
4. **Collect course-local copies**:
   - For each `course_root`, check
     `course_root / "_concepts" / f"{args.name}.md"` and
     `course_root / "_entities" / f"{args.name}.md"`. Collect the hits
     into a dict `{course_root: (kind, path)}`.
5. **Check root layer**: also check `args.vault / "_concepts" / f"{args.name}.md"`
   and `args.vault / "_entities" / f"{args.name}.md"`. If present, set
   `root_kind` + `root_path`.
6. **Pre-conditions**:
   - **R3.1 no duplicates**: if `len(course_hits) == 0` AND no root copy
     → `die("no duplicates found; nothing to promote", code=1)`.
   - **R3.7 re-promote**: if `len(course_hits) >= 1` AND a root copy
     exists → mode = `"merge_into_root"`; OK to proceed.
   - **R3.1 strict**: if `len(course_hits) >= 2` AND no root copy →
     mode = `"first_promote"`; OK.
   - **Else**: `len(course_hits) == 1` AND no root copy →
     `die("only one course-local copy; need ≥2 OR an existing root
     version", code=1)`.
   - **R3.2 kind**: if `args.kind` is None, auto-infer from the
     `(kind, path)` tuples. If course hits disagree on kind →
     `die("kind mismatch: Course A treats <name> as concept, Course B as
     entity; reconcile manually before promoting", code=1)`.
7. **Dry-run plan (stub)**:
   - Compute `merge_to = args.vault / f"_{kind}s" / f"{args.name}.md"`.
   - Compute `merge_from = [path for (_, path) in course_hits.values()]`
     sorted.
   - Stub: `contradictions_raised = 0` (real computation lands in 016.06).
   - Emit JSON to stdout:
     ```json
     {
       "applied": false,
       "mode": "first_promote",
       "name": "Sharpe Score",
       "kind": "concept",
       "merge_from": ["..."],
       "merge_to": "_concepts/Sharpe Score.md",
       "delete": ["..."],
       "index_updates": [...],
       "log_appends": [...],
       "contradictions_raised": 0
     }
     ```
   - All paths in the JSON are vault-relative (computed via
     `path.relative_to(args.vault)`).
8. **If `args.apply`**: `die("--apply path not implemented yet (016.05
   stub); waits for 016.06", code=3)`. **Exit code 3** = "feature not
   yet implemented" — a new code in the wiki-ingest vocabulary; document
   in SKILL.md exit-code table (added in 016.10). This stub is REQUIRED
   to lock the contract that a hostile caller passing `--apply` here
   doesn't silently overwrite files.

**Return value**: `0` on successful dry-run; non-zero on precondition
failure.

### Component Integration

- F3 driver. Imports: `_safety`, `_markdown`, `_frontmatter`, `_vault`,
  `_page_merge` (per architecture §3.2 import budget). The skeleton
  only uses `_safety` (die / _safe_name) + `_vault` (discover_courses,
  _peek_schema_version) — `_markdown`/`_frontmatter`/`_page_merge`
  arrive in 016.06.
- Does NOT import from any other `commands/*.py` (R12.5 / import-graph
  invariant).
- `wiki_ops.py` shim gains one import + one tuple entry.

## Test Cases

### Unit Tests (`tests/commands/test_promote.py` — new)

1. **TC-UNIT-016-05-01:** Dry-run on 2-course fixture (happy path)
   - Fixture: two-course vault with `Sharpe Score.md` in both
     `Lessons/Course A/_concepts/` and `Lessons/Course B/_concepts/`.
   - Run: `wiki_ops.py promote "Sharpe Score" --vault <vault>` (no
     `--apply`).
   - Expected: exit 0; stdout JSON has `applied: false`,
     `mode: "first_promote"`, `merge_from` has 2 sorted paths,
     `merge_to: "_concepts/Sharpe Score.md"`.
2. **TC-UNIT-016-05-02:** No-duplicate refusal (R3.1)
   - Fixture: vault with `Sharpe Score.md` in ONLY one course.
   - Run: promote.
   - Expected: exit non-zero; stderr contains "no duplicates found".
3. **TC-UNIT-016-05-03:** Kind mismatch refusal (R3.2)
   - Fixture: Course A has `_concepts/Pipeline.md`; Course B has
     `_entities/Pipeline.md`.
   - Run: promote without `--kind`.
   - Expected: exit non-zero; stderr contains "kind mismatch".
4. **TC-UNIT-016-05-04:** Re-promote mode (R3.7)
   - Fixture: `_concepts/Foo.md` at root AND in Course C's
     `_concepts/`.
   - Run: promote (no `--apply`).
   - Expected: exit 0; JSON has `mode: "merge_into_root"`, `merge_from`
     contains only Course C's path.
5. **TC-UNIT-016-05-05:** No root schema refusal (R9.1)
   - Fixture: vault with no `WIKI_SCHEMA.md` at root.
   - Run: promote.
   - Expected: `die(..., code=2)`; stderr "vault root WIKI_SCHEMA.md
     absent".
6. **TC-UNIT-016-05-06:** Wrong root schema version (R9.2)
   - Fixture: root schema declares `schema_version: 1.5`.
   - Run: promote.
   - Expected: `die(..., code=2)`; stderr "schema_version: 2.0".
7. **TC-UNIT-016-05-07:** `--apply` against stub
   - Fixture: 2-course happy path.
   - Run: promote with `--apply`.
   - Expected: `die(..., code=3)`; stderr "not implemented yet". No
     files mutated.
8. **TC-UNIT-016-05-08:** `--kind concept` overrides auto-infer
   - Fixture: 2-course vault (both `_concepts/`).
   - Run: promote with `--kind concept`.
   - Expected: same JSON as TC-01.
9. **TC-UNIT-016-05-09:** Name traversal rejected
   - Run: `promote ../Foo --vault <vault>`.
   - Expected: `_safe_name` raises; exit non-zero.
10. **TC-UNIT-016-05-10:** Vault-relative path computation (A-M-2)
    - Fixture: vault has a course at `<vault>/Hermes/` (no `Lessons/`).
    - Run: promote (assuming `Sharpe Score.md` in two non-`Lessons/`
      courses).
    - Expected: `merge_from` paths are `Hermes/_concepts/Sharpe Score.md`,
      not `Lessons/Hermes/...`.

### Regression Tests
- `tests/test_r11_byte_identity.py` passes (no v1 surface change; new
  command was added but doesn't affect existing CLI).
- `tests/commands/test_lint.py` passes (no regression).
- `tests/test_architecture.py` passes (`promote.py` correctly imports
  only from F1/F2/F3-helpers; no cross-command import).

## Acceptance Criteria
- [ ] `promote.py` created with `register` + `execute`; ≤200 LoC for the
      skeleton.
- [ ] `wiki_ops.py` gains the import + tuple entry.
- [ ] All 10 unit tests pass.
- [ ] `--apply` stub exits 4 with the documented message (no files
      mutated).
- [ ] `tests/test_architecture.py` green.
- [ ] `tests/test_r11_byte_identity.py` green.
- [ ] `lint <fixture>` (from 016.04) reports zero `invariant_violation`
      after this bead lands.
- [ ] `validate_skill.py` exits 0.

## Notes
- This is Phase 1 of the Stub-First two-pass for `promote`. The dry-run
  JSON is hardcoded-shaped but contains real precondition logic — that
  way 016.06 only needs to replace the stub `contradictions_raised: 0`
  with real computation + add the write path.
- The `--apply` stub raise (TC-UNIT-016-05-07) is intentional. It locks
  the contract that a hostile or premature operator invocation between
  016.05 merging and 016.06 landing cannot silently corrupt the vault.
- The bead is independently revertable: removing the new files +
  reverting the `wiki_ops.py` import + tuple changes restores v1
  behaviour.
