# Task 017.08 — `commands/init.py` extension (`--vault-id <slug>` flag)

## Use Case Connection

- **UC-1** precondition (operator scaffolds a vault with `vault_id:` in
  the root schema BEFORE running `/wiki-enrich` for the first time).

## Task Goal

Extend `commands/init.py` with a `--vault-id <slug>` flag. The flag is
only valid in combination with `--root` (TASK 016 added the `--root`
scaffold path). When given, the scaffold writes `vault_id: <slug>` into
the new root `WIKI_SCHEMA.md`'s frontmatter; the slug is validated via
`_vault.validate_vault_id_pattern` (017-02) before any I/O.

Without `--root`, `--vault-id` is rejected as a usage error (exit 2).
Without `--vault-id` BUT with `--root`, the existing TASK 016 scaffold
runs unchanged — no `vault_id:` line in the root schema. Standalone
users see no breaking change.

Per Stub-First, this is a small flag extension — Test-First. Write the
assertions (flag accepted only with `--root`; slug validated; written
into schema), confirm Red, then implement.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/commands/test_init_vault_id.py` —
  unit-test module dedicated to the new flag.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/init.py`

**`register(sub)` extended**:
- Add `parser.add_argument("--vault-id", metavar="SLUG", default=None,
  help="set vault_id in the root WIKI_SCHEMA.md scaffold; requires --root")`.

**`execute(args)` extended**:
- After argparse parsing, BEFORE any scaffold writes:
  - If `args.vault_id is not None and not args.root`:
    `die("--vault-id requires --root", code=_safety.EXIT_USAGE)`.
  - If `args.vault_id is not None`:
    `_vault.validate_vault_id_pattern(args.vault_id)` (exits 7 on
    malformed — before any I/O).
- In the existing `--root` branch:
  - After loading the existing `assets/WIKI_SCHEMA.root.template.md`
    template (TASK 016 added this asset), if `args.vault_id` is set:
    inject `vault_id: <slug>\n` into the frontmatter via
    `_frontmatter._splice_frontmatter_fields(...)` (the helper the
    TASK 016 `promoted_from:` work installed; the existing scalar-add
    code path supports a `(key, value)` tuple). The injected line goes
    AFTER the existing `schema_version:` line (deterministic position).
  - Idempotency: if the operator re-runs `init --root --vault-id <slug>`
    on an already-scaffolded vault and the schema already has the SAME
    `vault_id`, the re-run is a no-op (TASK 016 R2.4 idempotency
    preserved). If the schema has a DIFFERENT `vault_id`, the bead
    exits with `EXIT_GENERIC` and a clear message
    (`vault_id mismatch: existing <a>, requested <b>; edit by hand if
    intentional`). Operator-judgement gate — we do NOT silently
    overwrite an existing slug.
- LoC budget extended to ≤ 180 (was ≤ 150 after TASK 016).

### Component Integration

- F3 driver. Imports unchanged from TASK 016: `_safety`, `_vault`,
  `_frontmatter`. No new edges.
- The `_vault.validate_vault_id_pattern` import is new at the
  module-top — already F3-helper tier, allowed.
- The flag's `argparse` definition is alphabetical alongside the
  existing `--root` flag (R12.6 — `.AGENTS.md` updated in 017-09 to
  reflect the new flag).

## Test Cases

### Unit Tests (`tests/commands/test_init_vault_id.py` — new)

1. **TC-UNIT-017-08-01:** `init --root --vault-id trade-agents` writes
   the schema with the slug
   - Setup: empty target directory.
   - Run: `wiki-ingest init <dir> --root --vault-id trade-agents`.
   - Expected: exit 0; `<dir>/WIKI_SCHEMA.md` exists; frontmatter has
     `schema_version: 2.0`, `kind: vault-root`, `vault_id: trade-agents`.
     The `vault_id:` line is AFTER `schema_version:` (deterministic
     position).
2. **TC-UNIT-017-08-02:** `init <dir> --vault-id <slug>` (no `--root`)
   → exit 2
   - Run.
   - Expected: SystemExit code 2; stderr contains `--vault-id requires
     --root`. NO files written.
3. **TC-UNIT-017-08-03:** Malformed slug → exit 24 before any I/O
   - Run: `init <dir> --root --vault-id 1bad`.
   - Expected: SystemExit code 24; `<dir>` is unchanged (no schema
     file). Verified by `os.listdir(dir) == []`.
4. **TC-UNIT-017-08-04:** Idempotent re-run with SAME slug → no-op
   - Setup: directory already scaffolded with `vault_id: trade-agents`.
   - Run: `init <dir> --root --vault-id trade-agents`.
   - Expected: exit 0; schema file's content is byte-identical to
     pre-run (assert via sha256 round-trip).
5. **TC-UNIT-017-08-05:** Re-run with DIFFERENT slug → exit 1, no
   overwrite
   - Setup: scaffolded with `vault_id: trade-agents`.
   - Run: `init <dir> --root --vault-id other-vault`.
   - Expected: exit 1; stderr contains the "mismatch" envelope;
     schema file unchanged (sha256 round-trip identical).
6. **TC-UNIT-017-08-06:** `init <dir> --root` (no `--vault-id`)
   preserves TASK 016 behaviour
   - Setup: empty directory.
   - Run.
   - Expected: exit 0; schema present; frontmatter has NO `vault_id:`
     line. Confirms backwards compatibility.
7. **TC-UNIT-017-08-07:** Round-trip with `read_vault_id`
   - Run TC-UNIT-017-08-01.
   - Then call `_vault.read_vault_id(<dir>)`.
   - Expected: returns `"trade-agents"` (exact echo). Confirms
     write/read symmetry.
8. **TC-UNIT-017-08-08:** Slug validation happens BEFORE template load
   (perf + safety)
   - Run: `init /nonexistent/path --root --vault-id 1bad`.
   - Expected: exit 24 with the validation message — NOT a path-error
     message. Confirms the validation order locks the
     "no I/O on malformed slug" property.

### Regression Tests

- All TASK 015/016 + 017-00..07 tests still green.
- `tests/commands/test_init.py` (TASK 016 `--root` scaffold tests) —
  still green; the new flag is additive.

## Acceptance Criteria

- [ ] `--vault-id` flag accepted only with `--root` (TC-UNIT-017-08-02).
- [ ] Malformed slug → exit 24 with no I/O (TC-UNIT-017-08-03 + -08).
- [ ] Happy path writes `vault_id:` after `schema_version:`
      (TC-UNIT-017-08-01).
- [ ] Idempotent on same slug; refuses on mismatch
      (TC-UNIT-017-08-04..05).
- [ ] Backwards compatible without the flag (TC-UNIT-017-08-06).
- [ ] Round-trip via `read_vault_id` works (TC-UNIT-017-08-07).
- [ ] `commands/init.py` ≤ 180 LoC.
- [ ] All TASK 015/016 + 017-00..07 tests still green.

## Notes

- The "exit 1 on slug mismatch" choice (TC-UNIT-017-08-05) is
  deliberate: we do NOT route to exit 25 (VAULT_ID_FLAG_MISMATCH), which
  is reserved for the `ingest` orchestrator's strict-mode comparison.
  Exit 1 is the generic-error code; the stderr envelope explains the
  conflict so the operator can edit by hand or pick a different slug.
- The flag is documented in SKILL.md and `references/wiki_schema.md`
  §"vault_id field (v1.1)" — but those doc edits live in 017-09 (the
  final documentation sweep). This bead only ships the code + tests.
- A future task could expose a separate `wiki-ingest set-vault-id`
  command for the "rename my vault" case; that is OUT OF SCOPE here
  (R15 honest-scope lock). The current bead supports the "scaffold
  fresh" path only.
