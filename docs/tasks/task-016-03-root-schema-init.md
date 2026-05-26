# Task 016.03 — Root-schema scaffold (`init --root`)

## Use Case Connection
- Precondition for **UC-1** (operator scaffolds vault root before first
  `promote`) and **UC-3** (lint requires a root schema to detect
  `invariant_violation`).

## Task Goal

Extend `commands/init.py` with a `--root` flag (Q-1 resolution) that
scaffolds a vault-root layer: `WIKI_SCHEMA.md` (schema_version: 2.0,
kind: vault-root), empty `_concepts/` and `_entities/` directories, and
an optional `index.md`. Idempotent — never overwrites existing files.
Existing `init <vault>` (no `--root`) behaviour is unchanged.

## Changes Description

### New Files

- `skills/wiki-ingest/assets/WIKI_SCHEMA.root.template.md` — bundled
  template for the vault-root schema. Frontmatter shape:
  ```yaml
  ---
  schema_version: "2.0"
  kind: vault-root
  description: "Vault-root schema for two-tier (cross-course) wiki-ingest. See cross_course_promotion.md."
  ---
  ```
  Body: brief explanation of cross-course promotion rules, link to
  `cross_course_promotion.md` (added in 016.10). Sized to a screen
  (~30–50 lines).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/init.py`

**Function `register(sub)`:**
- Add `parser.add_argument("--root", action="store_true",
  help="Scaffold a vault-ROOT schema (schema_version: 2.0) instead of a
  course-local one.")`.

**Function `execute(args) -> int`:**
- Branch on `args.root`:
  - `args.root == False` (default): existing v1 behaviour — scaffold
    course-local `WIKI_SCHEMA.md`, `_sources/`, `_concepts/`,
    `_entities/`, `index.md`, `log.md`. No change.
  - `args.root == True`: new branch:
    1. Verify the target directory exists (`die` if not).
    2. Write `<vault>/WIKI_SCHEMA.md` from
       `assets/WIKI_SCHEMA.root.template.md` — **skip if file exists**
       (idempotent; R2.2).
    3. Create `<vault>/_concepts/` and `<vault>/_entities/` via
       `os.makedirs(..., exist_ok=True)` — no sentinel files
       (m-A-3 resolution).
    4. Create `<vault>/index.md` only if `args.with_index` is passed
       (optional — see below) OR skip entirely (operator can add later).
       **Decision for v1**: do NOT auto-create `index.md` on
       `init --root`; the first `promote` creates it. Document in
       SKILL.md.
    5. **Do NOT create** `_sources/` or `log.md` at the vault root —
       spec §2.5 ("sources never live at root") and R13.2 (no root log).
    6. Emit JSON: `{"created": [<list of paths>], "skipped": [<list of
       paths>], "kind": "vault-root"}` to stdout.
  - Re-running `init --root` is a clean no-op: `created == []`,
    `skipped == [WIKI_SCHEMA.md, _concepts/, _entities/]`.

**Loading the template**:
- Reuse the existing `load_asset` helper from `_vault.py` (which already
  reads from `ASSETS_DIR`). Add the new template name to the constants
  block of `_vault.py` if a constant is preferred (otherwise hardcode in
  `init.py`).

### Component Integration

- `init.py` LoC budget extended to ≤150 (architecture §3.2; current
  ~100).
- `_vault.py` gains a constant `SCHEMA_ROOT_TEMPLATE = "WIKI_SCHEMA.root.template.md"`
  (optional; keeps the call site clean).
- Existing `tests/commands/test_init.py` test cases for the
  course-local path MUST still pass.

## Test Cases

### Unit Tests (`tests/commands/test_init.py` — extended)

1. **TC-UNIT-016-03-01:** `init <empty_dir> --root` happy path
   - Pre: empty directory.
   - Run: `init <dir> --root`.
   - Expected: stdout JSON `{"created": ["WIKI_SCHEMA.md", "_concepts/",
     "_entities/"], "skipped": [], "kind": "vault-root"}`; on disk: the
     three artefacts exist; `WIKI_SCHEMA.md` schema_version is 2.0.
2. **TC-UNIT-016-03-02:** `init <dir> --root` is idempotent
   - Pre: directory already initialised via 016-03-01.
   - Run: re-execute.
   - Expected: `created == []`, `skipped == [WIKI_SCHEMA.md, _concepts/,
     _entities/]`; no file mutated.
3. **TC-UNIT-016-03-03:** `init <dir> --root` never overwrites a
   user-edited schema
   - Pre: `WIKI_SCHEMA.md` exists with `schema_version: 99.0`.
   - Run: `init <dir> --root`.
   - Expected: schema file unchanged; JSON reports it under `skipped`.
4. **TC-UNIT-016-03-04:** `init <dir> --root` does NOT create `_sources/`
   or `log.md`
   - Pre: empty directory.
   - Run: `init <dir> --root`.
   - Expected: only `WIKI_SCHEMA.md`, `_concepts/`, `_entities/` on disk.
5. **TC-UNIT-016-03-05:** `init <dir>` (no `--root`) preserves v1 behaviour
   - Pre: empty directory.
   - Run: `init <dir>` (no flag).
   - Expected: byte-identical to v1 — `WIKI_SCHEMA.md` (1.x), `_sources/`,
     `_concepts/`, `_entities/`, `index.md`, `log.md` created.
6. **TC-UNIT-016-03-06:** `init --root` refuses non-existent target
   - Pre: target directory does not exist.
   - Run: `init <nonexistent> --root`.
   - Expected: `die(..., code=1)`; SystemExit captured.
7. **TC-UNIT-016-03-07:** Schema file declares `kind: vault-root`
   - Inspect generated `WIKI_SCHEMA.md` frontmatter: `kind` is
     `vault-root` (case-sensitive marker).

### Regression Tests
- All existing `tests/commands/test_init.py` cases (course-local path)
  pass.
- `tests/test_r11_byte_identity.py` passes (no two-tier behaviour
  triggered).
- `tests/test_architecture.py` passes.

## Acceptance Criteria
- [ ] `init <vault> --root` works per the 7 unit tests above.
- [ ] Bundled `assets/WIKI_SCHEMA.root.template.md` exists.
- [ ] Existing `init <vault>` behaviour byte-identical to v1.
- [ ] `init.py` LoC ≤ 150.
- [ ] `validate_skill.py` exits 0.
- [ ] `tests/test_architecture.py` green.
- [ ] `tests/test_r11_byte_identity.py` green.

## Notes
- The `--root` flag is the Q-1 resolution: extend `init` instead of
  adding a sibling `init-root` subcommand. Smaller surface, fewer test
  variants.
- `index.md` at the vault root is intentionally NOT created here. The
  first `promote --apply` (Task 016.06) creates it lazily.
- The template body should mention the cross-course-promotion reference
  but not link to a file that doesn't exist yet (`cross_course_promotion.md`
  is added in Task 016.10). Use a placeholder text the operator can read
  even before 016.10 lands.
