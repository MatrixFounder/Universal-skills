# Task 017.02 — `_safety.EXIT_*` constants + `vault_id` helpers in `_vault.py`

## Use Case Connection

- **UC-3** (strict-mode `vault_id` enforcement) — Main + Alternatives
  (flag mismatch / invalid pattern) — requires the pattern validator
  + frontmatter peek helper.
- **UC-5** (partial-success exit 20) — the dispatch helper + orchestrator
  reference `EXIT_PARTIAL` by name.
- **UC-6** (timeout exit 26 — split per Arch-M-4) — references
  `EXIT_TIMEOUT`.
- Foundation for 017.03 (dispatch error envelopes), 017.05/06
  (orchestrator exit-code routing), 017.08 (`init --vault-id`).

## Task Goal

Extend the F1 safety layer and the F3 `_vault.py` helper with two
substrate additions:

1. **`_safety.EXIT_*` constants** — symbolic names for every exit code
   in the v1.1 matrix (0..9). Replaces magic-number literals scattered
   across the orchestrator and helpers. `die(msg, code=…)` continues
   to accept ints (no signature change).
2. **`_vault.read_vault_id(vault_root) → str | None`** — frontmatter
   peek; returns the slug if present, else `None`. No exception for
   absent — that is the "emit, don't enforce" contract (R3).
3. **`_vault.validate_vault_id_pattern(slug) → None`** — raises
   `die("INVALID_VAULT_ID", code=EXIT_INVALID_VAULT_ID)` if the slug
   violates the pattern. Stays silent on valid input.
4. **`_vault._VAULT_ID_RE`** — module-level compiled regex:
   `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` with `--` substring rejected
   separately (the regex alone permits `--` per its bracket class;
   the helper rejects it post-match).

Per Stub-First, helpers go Test-First: write the assertions, confirm
Red, then implement.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/test__vault_id.py` — new unit-test
  module targeting `read_vault_id` + `validate_vault_id_pattern` + the
  pattern regex.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_safety.py`

**Module-level constants (added after the existing `MAX_*` constants):**

```python
EXIT_OK                  = 0
EXIT_GENERIC             = 1
EXIT_USAGE               = 2
EXIT_PARTIAL             = 3
EXIT_SUBPROCESS          = 4
EXIT_LLM                 = 5
EXIT_MISSING_VAULT_ID    = 6
EXIT_INVALID_VAULT_ID    = 7
EXIT_VAULT_ID_MISMATCH   = 8
EXIT_TIMEOUT             = 9
```

- `die(msg, code=1)` is unchanged — the constants are passable as the
  `code=` argument by callers; no signature change.
- LoC budget extended to ≤ 350 (was ≤ 300; the constants net <20 LoC).

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_vault.py`

**Function `read_vault_id(vault_root: Path) -> str | None`:**
- Parameters:
  - `vault_root` — absolute path to the directory containing the root
    `WIKI_SCHEMA.md`.
- Returns: the `vault_id` slug from the root schema frontmatter if
  present; `None` if the field is absent OR the schema file itself is
  absent (caller decides whether absence is fatal).
- Logic:
  1. `schema_path = vault_root / SCHEMA_FILE`.
  2. If not `schema_path.is_file()`: return `None`.
  3. Read via `_safety.read_text(schema_path)`; on `OSError` return `None`.
  4. `fm, _, _ = split_frontmatter(content)`.
  5. `value = fm.get("vault_id")`.
  6. If `value` is not a string: return `None`.
  7. Return `value.strip()` (frontmatter parser already strips quotes).

**Function `validate_vault_id_pattern(slug: str) -> None`:**
- Parameters:
  - `slug` — the candidate vault_id.
- Returns: `None` on valid; raises `die(...)` on invalid (NO exception
  type — `die` exits via stderr + `sys.exit`).
- Logic:
  1. If not `_VAULT_ID_RE.fullmatch(slug)`:
     `die(f"INVALID_VAULT_ID: {slug!r} does not match {_VAULT_ID_RE.pattern}",
     code=EXIT_INVALID_VAULT_ID)`.
  2. If `"--"` in `slug`:
     `die(f"INVALID_VAULT_ID: {slug!r} contains '--'", code=EXIT_INVALID_VAULT_ID)`.
  3. Else return.

**Module-level constant:**
```python
_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
```
- The regex enforces length 3..32 (1 leading + 1..30 middle + 1 trailing)
  and lowercase-ASCII kebab-case. `--` is checked separately.
- LoC budget extended to ≤ 300 (was ≤ 250 after TASK 016; new helpers
  net <50 LoC).

### Component Integration

- `_safety.py` stays F1 (no imports beyond stdlib).
- `_vault.py` keeps its F3-helper position (imports `_safety`,
  `_frontmatter`). `validate_vault_id_pattern` calls `_safety.die` for
  the failure path — consistent with the rest of the codebase.
- Neither helper writes anything; both are read-only.

## Test Cases

### Unit Tests (`tests/test__vault_id.py` — new)

1. **TC-UNIT-017-02-01:** Valid pattern — round-trip
   - Inputs: `"trade-agents"`, `"abc"` (min len 3), `"a" + "b"*30 + "c"` (max len 32).
   - Expected: `validate_vault_id_pattern(slug)` returns `None`; no exit.
2. **TC-UNIT-017-02-02:** Length boundaries
   - Inputs: `"ab"` (too short), `"a" + "b"*32 + "c"` (too long, 34 chars).
   - Expected: SystemExit raised with `code == EXIT_INVALID_VAULT_ID == 7`.
3. **TC-UNIT-017-02-03:** Leading-digit rejected
   - Input: `"1bad"`.
   - Expected: SystemExit, code 24.
4. **TC-UNIT-017-02-04:** Trailing-dash rejected
   - Input: `"trade-"`.
   - Expected: SystemExit, code 24.
5. **TC-UNIT-017-02-05:** Double-dash rejected
   - Input: `"trade--agents"`.
   - Expected: SystemExit, code 24; stderr contains `"--"`.
6. **TC-UNIT-017-02-06:** Uppercase / unicode rejected
   - Inputs: `"Trade"`, `"trade-аgents"` (Cyrillic а).
   - Expected: SystemExit, code 24.
7. **TC-UNIT-017-02-07:** Control-char / path-separator rejected
   - Inputs: `"a/b"`, `"a\x00b"`, `"a b"`.
   - Expected: SystemExit, code 24.
8. **TC-UNIT-017-02-08:** `read_vault_id` happy path
   - Fixture: vault with root `WIKI_SCHEMA.md` containing
     `vault_id: trade-agents` in frontmatter.
   - Expected: `read_vault_id(vault_root) == "trade-agents"`.
9. **TC-UNIT-017-02-09:** `read_vault_id` absent field → `None`
   - Fixture: root schema without `vault_id:` line.
   - Expected: `read_vault_id(vault_root) is None`. NO exit, NO die.
10. **TC-UNIT-017-02-10:** `read_vault_id` absent schema file → `None`
    - Fixture: empty directory (no `WIKI_SCHEMA.md`).
    - Expected: `None`.
11. **TC-UNIT-017-02-11:** `read_vault_id` does NOT validate the
    pattern (separation of concerns)
    - Fixture: root schema with `vault_id: 1bad` (malformed).
    - Expected: `read_vault_id(vault_root) == "1bad"` (returns the
      string verbatim; pattern validation is the caller's job).
12. **TC-UNIT-017-02-12:** `EXIT_*` constants are wired
    - For each `(name, value)` in the matrix table — assert
      `getattr(_safety, name) == value`. Locks the numeric assignments.

### Regression Tests

- Run all TASK 015/016 existing tests — no regression. `die()` callers
  using literal `code=1` / `code=2` continue to work (constants are
  additive, not replacing).
- `tests/test_architecture.py` green (no new top-level imports).

## Acceptance Criteria

- [ ] `_safety.EXIT_*` constants present and numerically correct (per
      TC-UNIT-017-02-12).
- [ ] `_vault.read_vault_id` returns slug-or-None per TC-UNIT-017-02-08
      / -09 / -10 / -11.
- [ ] `_vault.validate_vault_id_pattern` exits with `EXIT_INVALID_VAULT_ID` (24) on every
      negative case (TC-UNIT-017-02-02..-07).
- [ ] `_vault._VAULT_ID_RE.pattern == "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"`.
- [ ] `_vault.py` total LoC ≤ 300 (architecture §3.2 extended budget).
- [ ] `_safety.py` total LoC ≤ 350 (architecture §3.2 extended budget).
- [ ] All TASK 015/016 tests still green.
- [ ] `tests/test_architecture.py` green.

## Notes

- Separation of concerns is load-bearing: `read_vault_id` returns
  whatever is in the file (R3 "emit, don't enforce"); the orchestrator
  decides when to validate. UC-3 alternative "invalid pattern (exit 24)" (see [`references/exit_codes.md`](../../skills/wiki-ingest/references/exit_codes.md) for the full matrix)
  fires from EITHER caller-passed `--vault-id` OR frontmatter-read
  value — both go through `validate_vault_id_pattern`. TC-UNIT-017-02-11
  locks the "read does not validate" contract so future maintainers do
  not silently couple the two.
- The pattern allows length 3..32 (1 + 1..30 + 1 = 3..32 inclusive).
  The double-dash check is a separate predicate so the error message
  can be more specific (TC-UNIT-017-02-05 verifies the stderr hint).
- No new dependency: `re` is stdlib; `_VAULT_ID_RE` compiles once at
  module load.
