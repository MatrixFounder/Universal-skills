# Task 017.05 — `commands/ingest.py` skeleton (Phase 1)

## Use Case Connection

- **UC-3** Main + Alternatives (strict-mode vault_id: exit 23 / 24 / 25 — see [`references/exit_codes.md`](../../skills/wiki-ingest/references/exit_codes.md)).
- **UC-4** Main scenario (source-hash short-circuit: emits empty
  `written[]` + `action: "unchanged"`).
- Scaffolding for **UC-1** / **UC-2** / **UC-5** (full pipeline in 017-06).

## Task Goal

Create `wiki_ingest/commands/ingest.py` with the `register`/`execute`
contract. Phase 1 ships:

- Argparse contract complete (R5.1 — all flags wired).
- `find_vault_root` + `read_vault_id` (+ optional `--vault-id`
  validation routing to exit 23/24/25 per UC-3).
- Source-hash idempotency short-circuit (R9.3 → UC-4).
- TTY-check / `--quiet` discipline (R10.1, R10.2).
- Manifest emission well-formed (R6 — including
  `manifest_version: "1.1"` sentinel per Arch-M-3), but `written[]` is
  hardcoded empty (this is the Phase-1 stub).

Phase 2 (017-06) replaces the empty `written[]` with real composition
via `_dispatch.dispatch()`.

Per Stub-First (PLAN §2), this is Phase 1: skeleton + tests assert the
manifest contract on the empty-write path. The §1 example block from
017-04 is the fixture for shape validation.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/commands/ingest.py`
  (≤ 250 LoC at this bead; ≤ 400 final after 017-06 + 017-07).
- `skills/wiki-ingest/scripts/tests/commands/test_ingest.py` —
  Phase-1 unit tests (manifest shape, vault_id routing, source-hash
  short-circuit).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

- Add `from wiki_ingest.commands import ingest` to the existing
  command import block.
- Add `ingest` to the existing `_COMMAND_MODULES` tuple (or whatever
  the TASK 015 dispatch table is called — preserve the existing
  pattern).
- LoC budget stays ≤ 200.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/ingest.py` (new)

**Function `register(sub: argparse._SubParsersAction) -> None`:**
- Create subparser `ingest`.
- Required-named flags:
  - `--source <PATH>` (required) — absolute path to the raw input
    (transcript / article / pre-made summary).
  - `--vault <PATH>` (required) — absolute path to the vault root.
- Optional:
  - `--output-format {human,json}` (default `human`).
  - `--vault-id <SLUG>` (validator; routes to exit 23/24/25 per UC-3).
  - `--known-concepts-file <PATH>` / `--known-concepts-stdin`
    (mutually exclusive — argparse `add_mutually_exclusive_group`).
    Phase 1 accepts the flags but does NOT consume them (Phase 2 wiring
    in 017-07).
  - `--source-hash <HEX>` — sha256 hex; validated by Phase-1 via
    `^[0-9a-fA-F]{64}$` regex.
  - `--config <PATH>` — Phase-1 accepts but does NOT parse (017-07).
  - `--timeout-seconds <N>` — Phase-1 accepts but does NOT enforce
    (017-07).
  - `--quiet` — Phase-1 honours immediately (TTY check + force-quiet).

**Function `execute(args: argparse.Namespace) -> int`:**

Skeleton (Phase 1 — NO writes, NO dispatch):

1. **Source path validation**:
   - `source = Path(args.source).resolve()`.
   - If not `source.is_file()`:
     `die(f"source not found: {source}", code=EXIT_GENERIC)`.
2. **Vault discovery** (R5.2(a)):
   - `course_root, vault_root_or_none = _vault.find_vault_root(args.vault)`.
   - Resolve effective `vault_root`:
     `vault_root = vault_root_or_none if vault_root_or_none is not None else course_root`.
3. **`vault_id` resolution + routing** (R3 + UC-3):
   - `vault_id_from_fm = _vault.read_vault_id(vault_root)`.
   - If `vault_id_from_fm is not None`:
     `_vault.validate_vault_id_pattern(vault_id_from_fm)`
     (exits 7 on malformed — fires regardless of `--vault-id`).
   - If `args.vault_id` is given:
     - `_vault.validate_vault_id_pattern(args.vault_id)` (exits 7 if
       caller-supplied slug is malformed).
     - If `vault_id_from_fm is None`:
       `die(_emit_error_envelope({"code":"MISSING_VAULT_ID", ...}),
       code=EXIT_MISSING_VAULT_ID)` (exits 23).
     - Elif `vault_id_from_fm != args.vault_id`:
       `die(_emit_error_envelope({"code":"VAULT_ID_FLAG_MISMATCH",
       "in_frontmatter":vault_id_from_fm, "from_flag":args.vault_id}),
       code=EXIT_VAULT_ID_MISMATCH)` (exits 25).
   - `effective_vault_id = vault_id_from_fm` (may be `None`).
4. **Source-hash short-circuit** (R9 → UC-4):
   - If `args.source_hash` is given:
     - Validate format (T17-S4): `re.fullmatch(r"^[0-9a-fA-F]{64}$",
       args.source_hash)` else `die("INVALID_SOURCE_HASH", code=EXIT_USAGE)`.
     - `recorded = _read_source_footer_hash(source_slug, course_root)`
       (the helper reads `_sources/<slug>.md` footer if present;
       returns `None` if absent).
     - If `recorded == args.source_hash.lower()`:
       emit `{"manifest_version":"1.1", "status":"ok",
       "action":"unchanged", "vault_id":..., "vault_root":...,
       "written":[], "created":[], "touched":[], "contradictions":0,
       "summary_path": <existing-path-or-null>, "log_event": null,
       "llm_tokens_used":{"input":0, "output":0, "model":null}}`
       to stdout (when `--output-format json`); exit 0.
5. **Manifest emission stub** (Phase 1):
   - Build manifest dict per Architecture §4.5.5 with EMPTY `written[]`
     / `created[]` / `touched[]` / `contradictions:0` / `log_event:None`.
   - `summary_path` is set to `null` in Phase 1 (NOT a placeholder
     string — a consumer parsing the Phase-1 manifest must NOT see a
     path that does not resolve on disk; Phase 2 (017-06) fills in the
     real post-write path). This locks the contract: a non-null
     `summary_path` value is a written-file commitment. TC-UNIT-017-05-01
     asserts `manifest["summary_path"] is None` at Phase 1.
   - Stamp `manifest_version: "1.1"` (Arch-M-3).
   - If `args.output_format == "json"`: pass manifest dict through
     `_emit_manifest(manifest)` (calls `_safe_for_json` recursively
     before `json.dump(sys.stdout, manifest)`).
   - Else (`human`): emit a 3-line summary to stdout
     (`Source: …`, `Vault: …`, `Phase 1 stub — no writes`).
   - Exit `EXIT_OK`.

**Helper functions inside `commands/ingest.py`**:
- `_emit_error_envelope(payload: dict) -> str` — JSON-serialises a
  `{status:"error", code:..., ...}` payload via `_safe_for_json` and
  returns the string for `die` to use. Used by exit 23/24/25 paths.
- `_emit_manifest(manifest: dict) -> None` — writes
  `_safe_for_json`-scrubbed dict to stdout via `json.dump`.
- `_read_source_footer_hash(slug: str, course_root: Path) -> str | None`
  — reads `course_root / "_sources" / f"{slug}.md"` if present; finds
  the existing footer hash (TASK 015 register-summary writes it as
  `<!-- source_hash: <hex> -->` near EOF). Returns `None` on absent
  file or absent footer. Hex returned in lowercase.

### Component Integration

- F3 driver. Imports: `_safety` (`die`, `EXIT_*`, `_safe_for_json`),
  `_frontmatter` (`split_frontmatter` via `_read_source_footer_hash`),
  `_vault` (`find_vault_root`, `read_vault_id`,
  `validate_vault_id_pattern`), `_dispatch` (imported but UNUSED in
  Phase 1 — 017-06 wires it).
- Does NOT import any other `commands/*.py` (R14.5 invariant).
- `wiki_ops.py` shim gains one import + one tuple entry.

## Test Cases

### Unit Tests (`tests/commands/test_ingest.py` — new)

1. **TC-UNIT-017-05-01:** Phase-1 manifest shape (JSON output, two-tier fixture)
   - Fixture: `tests/fixtures/two_course_vault/` (TASK 016).
   - Run: `wiki-ingest ingest --source <fixture-source.md> --vault
     <vault> --output-format json` (no `--source-hash`, no
     `--vault-id`).
   - Expected: exit 0; stdout is parseable JSON; keys ⊇ the manifest
     contract key set (per `tests/test_manifest_schema.py`
     TC-UNIT-017-04-02); `manifest_version == "1.1"`; `written: []`
     (Phase-1 stub); `summary_path is None` (Phase-1 commitment —
     Phase 2 fills with real post-write path); `vault_id` matches the
     fixture's frontmatter value.
2. **TC-UNIT-017-05-02:** Source-hash short-circuit → `action:"unchanged"`
   - Fixture: existing `_sources/<slug>.md` with a known footer hash.
   - Run: `wiki-ingest ingest --source <source> --vault <vault>
     --source-hash <matching-hex> --output-format json`.
   - Expected: exit 0; manifest has `action:"unchanged"`; `written: []`;
     NO downstream subprocess invocation (assert via a mock that
     no-op'd).
3. **TC-UNIT-017-05-03:** UC-3 missing vault_id with `--vault-id` →
   exit 23
   - Fixture: vault root with `WIKI_SCHEMA.md` lacking `vault_id:` line.
   - Run: `… --vault-id trade-agents`.
   - Expected: exit 23; stderr envelope has `"code":"MISSING_VAULT_ID"`.
4. **TC-UNIT-017-05-04:** UC-3 vault_id flag mismatch → exit 25
   - Fixture: `vault_id: foo` in root schema; caller passes
     `--vault-id bar`.
   - Expected: exit 25; envelope has `"code":"VAULT_ID_FLAG_MISMATCH"`,
     `"in_frontmatter":"foo"`, `"from_flag":"bar"`.
5. **TC-UNIT-017-05-05:** UC-3 invalid frontmatter pattern → exit 24
   regardless of `--vault-id`
   - Fixture: `vault_id: 1bad` in root schema.
   - Run-A: without `--vault-id` flag.
   - Run-B: with `--vault-id foo`.
   - Expected: both runs exit 24 (validation fires on frontmatter read).
6. **TC-UNIT-017-05-06:** `--vault-id` malformed (caller-supplied) → exit 24
   - Fixture: vault with frontmatter `vault_id: good-slug`; caller
     passes `--vault-id 1bad`.
   - Expected: exit 24 (caller-side validation also routes to 24 —
     malformed-input wins over mismatch comparison).
7. **TC-UNIT-017-05-07:** Standalone user without `--vault-id` → exit
   0 with `vault_id: null`
   - Fixture: single-course vault, no root schema.
   - Run: `… --output-format json` (no `--vault-id`).
   - Expected: exit 0; manifest has `vault_id: null` AND `course:
     null` AND every `written[].scope == "course"` shape (Phase-1
     `written` is empty so this asserts only on the schema). Confirms
     Q-5.
8. **TC-UNIT-017-05-08:** `--source-hash` format check (T17-S4)
   - Run: `… --source-hash deadbeef` (only 8 chars).
   - Expected: exit 2; envelope has `"code":"INVALID_SOURCE_HASH"`.
9. **TC-UNIT-017-05-09:** `--quiet` suppresses decorative stdout
   - Run: `--output-format human --quiet`. Stdout is empty (no
     "Source:" / "Vault:" / "Phase 1 stub" lines). Logs route to stderr
     if at all.
10. **TC-UNIT-017-05-10:** TTY check forces quiet when stdout piped
    - Run inside a `subprocess.PIPE`-captured invocation; expect
      `os.isatty(1) == False` → same suppression as `--quiet`.
11. **TC-UNIT-017-05-11:** `_safe_for_json` is applied to every scalar
    in the manifest
    - Fixture: a vault path containing control characters (NFKC
      normalised away) — assert that the manifest's `vault_root` is
      the resolved-sanitised value, not the raw input.
12. **TC-UNIT-017-05-12:** Mutually-exclusive `--known-concepts-*`
    - Run: both flags together.
    - Expected: exit 2 (argparse mutual-exclusion).

### Regression Tests

- Run all TASK 015/016 existing tests — no regression.
- `tests/test_architecture.py` green — `commands/ingest.py` imports
  `_dispatch` (F3 helper, allowed) but NOT another command module.

## Acceptance Criteria

- [ ] `commands/ingest.py` ≤ 250 LoC at this bead.
- [ ] Argparse contract complete (R5.1).
- [ ] Manifest shape validated against `references/manifest_schema.md`
      §1 example block (TC-UNIT-017-05-01).
- [ ] UC-3 exit-code routing complete (6, 7, 8 — TC-UNIT-017-05-03..06).
- [ ] UC-4 source-hash short-circuit emits `action:"unchanged"` + empty
      `written[]` (TC-UNIT-017-05-02).
- [ ] `--quiet` + TTY-check honour decorum (TC-UNIT-017-05-09..10).
- [ ] `--source-hash` format validated (TC-UNIT-017-05-08).
- [ ] `manifest_version == "1.1"` stamped (Arch-M-3 verified by 04-03).
- [ ] All TASK 015/016 tests still green.
- [ ] `tests/test_architecture.py` green.

## Notes

- Phase 1 deliberately accepts but does NOT consume the flags wired in
  017-07 (`--known-concepts-*`, `--config`, `--timeout-seconds`). They
  appear in argparse so the contract is locked from day 1, but their
  bodies are no-ops at this bead. Tests in 017-07 assert their actual
  behaviour.
- The source-hash short-circuit must run AFTER vault_id validation —
  otherwise a malformed vault_id would silently re-emit the unchanged
  envelope without surfacing the data-integrity issue.
- For TC-UNIT-017-05-02, the "no downstream subprocess" assertion uses
  `unittest.mock.patch` on `subprocess.run` at the module level and
  verifies `mock.call_count == 0`. This locks the perf-critical
  short-circuit path (architecture §8 ≤150 ms budget).
- The `_emit_error_envelope` JSON for exit 23/24/25 is intentionally
  written to stderr (via `die`), NOT stdout. `--output-format json`
  applies only to the SUCCESS / partial-success manifest; errors are
  unstructured stderr envelopes for stdout/stderr separation.
