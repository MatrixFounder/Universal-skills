# Task 017.07 — `--known-concepts-*` + `--source-hash` + `--config` + `--quiet` + `--timeout-seconds`

## Use Case Connection

- **UC-1** Main scenario step 3 (`--known-concepts-stdin` injection
  from the bridge's DB query).
- **UC-1** Main scenario step 4 (full flag set on the wrapped call).
- **UC-6** (planner-split from UC-5 — timeout overrun: exit 26 +
  `phase:"timeout"` envelope).

## Task Goal

Wire the flag bodies that 017-05 accepted but did not consume:

- **`--known-concepts-stdin` / `--known-concepts-file`** (R7) — load
  the JSON payload, merge with `scan`-derived concepts, pass the
  merged list to the synthesis subprocess.
- **`--source-hash`** (R9.1, R9.2, R9.4) — when present and the
  short-circuit does NOT fire (no recorded hash, or mismatch), use the
  supplied hash for the new footer write + log-event details.
- **`--config <PATH>`** (R11) — load via the hand-rolled YAML subset
  parser (Arch-M-6 / T17-S5); merge with built-in defaults; CLI flags
  override file values.
- **`--timeout-seconds`** (R10.3, R10.4) — enforce via
  `subprocess.run(timeout=N)` for the synthesis subprocess + a
  Python-side wall-clock guard. On overrun: exit 26 +
  `phase:"timeout"` (Arch-M-4).

`--quiet` was already honoured in Phase 1 (017-05). This bead adds the
explicit test for "quiet honours both TTY check and the flag".

Per Stub-First, all flag wiring is incremental — argparse already
accepts the flags from Phase 1; this bead replaces the no-op bodies
with real logic. Test-First: write the assertions for each flag's
behaviour, confirm Red, then implement.

## Changes Description

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/ingest.py`

**New helpers**:

- `_read_known_concepts_stdin() -> list[dict]` — reads stdin up to
  `WIKI_INGEST_KNOWN_CONCEPTS_MAX_BYTES` (default `1048576` = 1 MiB,
  T17-S2). On overrun: `die("INPUT_TOO_LARGE", code=EXIT_GENERIC)`.
  `json.loads`, validate the array-of-objects shape (each entry has
  `slug`, `name`, optional `aliases`). Return the list.
- `_read_known_concepts_file(path: Path) -> list[dict]` — same shape
  via `_safety.read_text(path, max_bytes=1<<20)`. No
  `_is_relative_to(vault)` check (T17-S3 — caller-trusted).
- `_merge_known_concepts(scan_derived: list, supplied: list) -> list`
  — dict-keyed by `slug`; supplied entry wins on collision (R7.4 —
  DB authoritative); returns a sorted list (determinism).
- `_validate_source_hash(hex_str: str) -> str` — regex check
  `^[0-9a-fA-F]{64}$` (T17-S4); returns the lowercased value. On
  malformed: `die("INVALID_SOURCE_HASH", code=EXIT_USAGE)`.
- `_parse_config_subset(path: Path) -> dict` — hand-rolled YAML subset
  parser (Arch-M-6 / T17-S5). Supports: scalar keys + scalar values
  (`key: value`), flat lists (`key:\n  - item\n  - item`), one level
  of nesting (`section:\n  subkey: value`). Unknown keys → log a
  warning to stderr (not error); return value omits them.
- `_apply_config_overrides(args, config_dict) -> argparse.Namespace`
  — merges with precedence `CLI > config > defaults` (R11.2). The
  built-in defaults dict lives at module scope:
  `_DEFAULTS = {"timeout_seconds": 600, ...}`.
- `_run_with_timeout(cmd: list[str], timeout: int) -> subprocess.CompletedProcess`
  — wraps `subprocess.run(cmd, timeout=timeout, check=False)`. On
  `subprocess.TimeoutExpired`: kill the subprocess via
  `Popen.kill()` (T17-S6); raise a sentinel `_TimeoutError(phase:"…")`
  the caller catches to emit the partial envelope with exit 26.

**`execute(args)` extended**:

1. Right after argparse parsing, BEFORE source-hash check:
   - If `args.config`: `config = _parse_config_subset(Path(args.config))`;
     `args = _apply_config_overrides(args, config)`.
   - If `WIKI_INGEST_TIMEOUT` env var is set AND `args.timeout_seconds`
     is the default: `args.timeout_seconds = int(env_val)` (R10.4).
2. The Phase 1 source-hash format check is replaced by
   `_validate_source_hash` (returns the normalised hex; use it
   downstream).
3. After the source-hash short-circuit decision, BEFORE summary
   synthesis:
   - Load known concepts: if `args.known_concepts_stdin`:
     `known = _read_known_concepts_stdin()`; elif
     `args.known_concepts_file`: `known = _read_known_concepts_file(
     Path(args.known_concepts_file))`; else: `known = None`.
   - Run `scan` against the vault (existing helper or `_dispatch.dispatch
     ("scan", ...)` — wait: `scan` is NOT in the dispatch whitelist
     (017-03). For 017-07, call the scan command directly via local
     import inside `commands/ingest.py` (the import-graph invariant
     allows F3-helper imports but forbids command-to-command imports
     at module level; using `_dispatch` for `scan` would require
     adding it to the whitelist, which is a deliberate refactor). The
     cleanest alternative: extract the scan logic to `_vault.scan_vault_pages`
     as an F3 helper, then both `commands/scan.py` and `commands/ingest.py`
     consume it via the helper layer.
   - **Decision (locked at this bead)**: extract `scan_vault_pages` into
     `_vault.py` as a new helper (≤ 30 LoC); refactor `commands/scan.py`
     to delegate to it; `commands/ingest.py` consumes the helper
     directly. This adds ≤ 30 LoC to `_vault.py` (within the ≤ 300
     budget after 017-02), zero LoC to the dispatch whitelist, and
     keeps the architecture clean.
   - `scan_derived = _vault.scan_vault_pages(vault_root, ...)`.
   - `merged = _merge_known_concepts(scan_derived, known) if known else scan_derived`.
   - Pass `merged` to the synthesis subprocess via its existing
     known-concepts input channel.
4. Summary synthesis subprocess wrapped in `_run_with_timeout`:
   - `result = _run_with_timeout(cmd, timeout=args.timeout_seconds)`.
   - On `_TimeoutError`: emit partial envelope with `phase:"timeout"`,
     `code:"TIMEOUT"`, exit `EXIT_TIMEOUT` (9). (Arch-M-4.)
   - On non-zero exit from subprocess (NOT timeout): exit
     `EXIT_SUBPROCESS` (4) with `phase:"summarize"`.
   - On exit 0 from subprocess: parse the JSON output for
     `llm_tokens_used` and feed it into the manifest.
5. `--source-hash` integration with the footer write:
   - When the orchestrator writes `_sources/<slug>.md` via
     `register-summary` dispatch, the `register-summary` command
     already supports `--source-hash` (TASK 015 surface). Pass
     `args.source_hash` through to that dispatch step's namespace.
     Without the flag, `register-summary` computes the hash itself
     (existing behaviour).

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_vault.py`

**New helper `scan_vault_pages(vault_root: Path, *, course_root: Path | None = None) -> list[dict]`:**
- Logic extracted from `commands/scan.py` (existing TASK 015 logic):
  walk the vault's `_concepts/` + `_entities/` (per layer), return a
  sorted `list[dict]` of `{slug, name, kind, aliases}` (where
  `aliases` defaults to `[]` if none in frontmatter).
- LoC budget extended to ≤ 320 (was ≤ 300 after 017-02).

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/scan.py`

- Refactor `execute(args)` to delegate to
  `_vault.scan_vault_pages(...)`. Existing byte-identical output
  preserved (TASK 015 R11). The command remains the public CLI; the
  helper is the reusable layer.

### Component Integration

- All flag wiring stays inside `commands/ingest.py` (Phase 2 body).
- New `_vault.scan_vault_pages` helper preserves the import-graph
  invariant: `commands/ingest.py` → `_vault` (F3 helper, allowed).
  `commands/scan.py` already imports `_vault`, so no new edge.
- `_run_with_timeout` lives in `commands/ingest.py` (it's
  orchestrator-specific). If a future task needs timeouts elsewhere,
  promote it to `_safety.py`.
- `_parse_config_subset` lives in `commands/ingest.py` (orchestrator-
  specific). No `PyYAML` import anywhere (Arch-M-6).

## Test Cases

### Unit Tests (`tests/commands/test_ingest.py` — extended)

1. **TC-UNIT-017-07-01:** `--known-concepts-stdin` merges with scan
   output (DB wins on collision)
   - Fixture: vault with `_concepts/Sharpe.md` (scan finds slug
     `sharpe`).
   - Stdin: `[{"slug":"sharpe", "name":"Sharpe Ratio", "aliases":["Sharpe Score"]}]`.
   - Run: `ingest …` with stdin piped.
   - Expected: merged list passed downstream has the DB version's
     name + aliases.
2. **TC-UNIT-017-07-02:** `--known-concepts-stdin` size cap
   - Stdin: 2 MiB of valid JSON.
   - Expected: exit 1; envelope contains `INPUT_TOO_LARGE`.
   - Cap is configurable: `WIKI_INGEST_KNOWN_CONCEPTS_MAX_BYTES=4194304`
     env var → 2 MiB stdin passes.
3. **TC-UNIT-017-07-03:** `--known-concepts-*` mutual exclusion
   - Run with both: exit 2 (argparse).
4. **TC-UNIT-017-07-04:** `--source-hash` normalised lowercase
   - Run: `--source-hash DEADBEEF…` (uppercase, 64 chars).
   - Expected: footer write contains the lowercase hex.
5. **TC-UNIT-017-07-05:** `--source-hash` malformed → exit 2
   - Run: `--source-hash xyz`.
   - Expected: exit 2; envelope has `INVALID_SOURCE_HASH`.
6. **TC-UNIT-017-07-06:** `--config` overrides defaults
   - Config file: `timeout_seconds: 300`.
   - Run with NO `--timeout-seconds` flag.
   - Expected: effective timeout is 300.
7. **TC-UNIT-017-07-07:** CLI flag overrides `--config`
   - Config file: `timeout_seconds: 300`.
   - Run: `--timeout-seconds 30`.
   - Expected: effective timeout is 30.
8. **TC-UNIT-017-07-08:** `--config` unknown key → warning, not error
   - Config file: `not_a_real_key: 42`.
   - Run.
   - Expected: stderr contains the warning string `unknown config
     key: not_a_real_key`; exit 0 (or whatever the regular path
     produces); the key is not surfaced in the merged args.
9. **TC-UNIT-017-07-09:** `--config` rejects YAML tag-construction
   (T17-S5)
   - Config file: `key: !!python/object/apply:os.system ["echo pwned"]`.
   - Expected: the parser treats the value literally (a string
     `"!!python/object/apply:os.system ["echo pwned"]"`) OR rejects
     the line as malformed — but does NOT exec it. Test asserts
     `subprocess.run` was NOT called by any `os.system`-equivalent
     during parsing.
10. **TC-UNIT-017-07-10:** `--timeout-seconds 1` → exit 26 +
    `phase:"timeout"`
    - Inject a synthesis subprocess that sleeps 5 s (mock).
    - Run: `--timeout-seconds 1`.
    - Expected: exit 26; partial envelope has `phase:"timeout"` and
      `code:"TIMEOUT"`; the subprocess is killed (verify via no zombie
      `pgrep` for the mock).
11. **TC-UNIT-017-07-11:** `WIKI_INGEST_TIMEOUT` env var fallback
    - No `--timeout-seconds` flag; env: `WIKI_INGEST_TIMEOUT=42`.
    - Expected: effective timeout = 42.
12. **TC-UNIT-017-07-12:** `_vault.scan_vault_pages` preserves byte-
    identity with `commands/scan.py` output
    - Run `wiki-ingest scan <fixture>` → capture stdout.
    - Call `_vault.scan_vault_pages(<fixture>)` → JSON-serialise via
      the same path.
    - Expected: identical output. Locks TASK 015 R11 against the
      refactor.

### Regression Tests

- All TASK 015/016 tests still green.
- `tests/test_architecture.py` green (no new module-level command
  imports; `_vault.scan_vault_pages` is F3-helper).
- `tests/commands/test_scan.py` (existing TASK 015) — still green
  with the refactored delegating `commands/scan.py`.

## Acceptance Criteria

- [ ] `--known-concepts-stdin/file` merge + size cap working
      (TC-UNIT-017-07-01..03).
- [ ] `--source-hash` validation + lowercase normalisation
      (TC-UNIT-017-07-04..05).
- [ ] `--config` precedence chain + unknown-key warning + no exec-tag
      (TC-UNIT-017-07-06..09).
- [ ] `--timeout-seconds` enforced; overrun → exit 26 +
      `phase:"timeout"`; subprocess killed cleanly (TC-UNIT-017-07-10).
- [ ] `WIKI_INGEST_TIMEOUT` env var fallback (TC-UNIT-017-07-11).
- [ ] `_vault.scan_vault_pages` refactor preserves byte-identity
      (TC-UNIT-017-07-12).
- [ ] `commands/ingest.py` ≤ 400 LoC (or escape valve via
      `_ingest_helpers.py` if exceeded — and the new helper module
      lives at F2 tier).
- [ ] `_vault.py` ≤ 320 LoC.
- [ ] All TASK 015/016 + 017-00..06 tests still green.

**Atomicity escape valve (pre-authorised by Plan-reviewer 2026-05-27)**:
if the Developer's test plan against this bead grows beyond ~15
test cases OR the bead's net LoC delta crosses ~400, split the
`_vault.scan_vault_pages` extraction (+ the `commands/scan.py`
refactor + TC-UNIT-017-07-12 byte-identity test) into a separate
sub-bead `017-07a-scan-helper-extraction.md`. The remaining flag
families stay in `017-07`. No other split is pre-authorised; further
restructuring requires a re-plan loop.

## Notes

- **Why `_vault.scan_vault_pages` instead of `_dispatch.dispatch("scan", …)`**:
  adding `scan` to the dispatch whitelist would expand the
  orchestrator's call surface (T17-S9 audit point) for one consumer.
  Extracting the logic to a helper preserves the whitelist's
  "atomic-ops only" purity AND lets `commands/scan.py` benefit from
  the helper's testability.
- **Hand-rolled YAML subset rationale**: the cost is ~50 LoC for a
  bounded grammar that we control. `PyYAML` is ~3 MB of optional
  dependency, has a known exec-tag CVE class, and adds a `pip install`
  step the rest of the skill avoids. The subset parser is tested by
  TC-UNIT-017-07-06..09 and the "no exec" property is asserted by
  TC-UNIT-017-07-09.
- **Subprocess kill discipline**: `subprocess.run(timeout=N)` returns
  `subprocess.TimeoutExpired` after sending SIGKILL by default on
  POSIX. The wrapper catches the exception, re-confirms the process
  is gone (`Popen.poll() is not None`), and surfaces the partial
  envelope. The test pgrep check uses a unique sentinel argv string
  for the mock subprocess so we can detect leaks deterministically.
