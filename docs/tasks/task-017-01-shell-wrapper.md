# Task 017.01 — Shell wrapper `scripts/wiki-ingest` (POSIX, no `.sh`)

## Use Case Connection

- **UC-1** Main scenario step 1+2 (the bridge invokes `wiki-ingest`
  by name from PATH; without this wrapper the binary does not exist
  on PATH).
- **UC-2** Main scenario step 1 (operator-direct ingest via the same
  command-line interface).

## Task Goal

Ship a POSIX shell wrapper at `skills/wiki-ingest/scripts/wiki-ingest`
(NO `.sh` suffix per R1.1 contract). The wrapper `exec`s
`python3 wiki_ops.py "$@"` after resolving its own path via
`readlink -f` (GNU + BusyBox) with a `python3 -c os.path.realpath`
fallback (macOS stock `readlink` lacks `-f` per T17-S8). The wrapper
is `chmod +x`; the install pattern is to symlink it into
`~/.local/bin/wiki-ingest`.

Per Stub-First, this is a one-file bead — no two-pass needed (the
wrapper is functionally minimal). Test-first: write the wrapper-runs
assertions, confirm Red, then add the wrapper file.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki-ingest` (no extension, `chmod +x`).
  Architecture §3.2 budget: ≤ 30 LoC shell.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/tests/test_cli_wrapper.py` (extended from 017-00)

- Add the wrapper-specific test cases below.

#### File: `skills/wiki-ingest/SKILL.md`

- Add a §"Install on PATH" subsection (3–5 lines) documenting the
  symlink pattern:
  ```
  ln -s "$PWD/skills/wiki-ingest/scripts/wiki-ingest" ~/.local/bin/wiki-ingest
  ```
- Note that `python3 wiki_ops.py …` continues to work unchanged (R1.3).
- Add an HTML comment marker at the section end:
  `<!-- finalised by 017-09 (do not edit out of band) -->` so the
  final documentation sweep (017-09) recognises the section as
  already-authoritative and only reconciles surrounding context, not
  the body. Prevents mid-chain conflicts if someone edits SKILL.md
  between 017-01 and 017-09.

### File contents (`scripts/wiki-ingest`)

```sh
#!/bin/sh
# wiki-ingest — thin wrapper that exec's wiki_ops.py with the same args.
# Cross-shell, symlink-safe; macOS readlink fallback per T17-S8.

set -eu

# Resolve absolute, symlink-canonical path of this script.
if SELF=$(readlink -f -- "$0" 2>/dev/null); then
    :
else
    # macOS stock readlink lacks -f; fall back to Python realpath.
    SELF=$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' -- "$0")
fi

DIR=$(dirname -- "$SELF")
exec python3 "$DIR/wiki_ops.py" "$@"
```

### Component Integration

- The wrapper is the SOLE new entry-point file under `scripts/` since
  TASK 015 (`wiki_ops.py` is the only other one).
- `chmod +x` is the wrapper's invariant — tests verify the bit; the
  bead's git commit captures it via `git update-index --chmod=+x`.
- `$@` is QUOTED to preserve arguments containing spaces / shell
  metacharacters (T17-S8 — no IFS/glob attack surface).

## Test Cases

### End-to-end Tests

1. **TC-E2E-017-01-01:** Wrapper smoke — `--version` round-trips
   - Run: `skills/wiki-ingest/scripts/wiki-ingest --version`.
   - Expected: stdout exactly `wiki-ingest 1.1.0\n`; exit 0.
2. **TC-E2E-017-01-02:** Wrapper subcommand dispatch ≡ direct call
   - Run-A: `skills/wiki-ingest/scripts/wiki-ingest scan <fixture-vault>`.
   - Run-B: `python3 skills/wiki-ingest/scripts/wiki_ops.py scan <fixture-vault>`.
   - Expected: identical stdout, identical stderr, identical exit code.
3. **TC-E2E-017-01-03:** Wrapper resolves from symlink with spaces in path
   - Setup: create `/tmp/dir with spaces/`; symlink the wrapper into it.
   - Run via the symlinked path: `/tmp/dir\ with\ spaces/wiki-ingest --version`.
   - Expected: same as TC-E2E-017-01-01. Verifies `readlink -f` + `"$@"`
     quoting cooperate.

### Unit Tests (`tests/test_cli_wrapper.py` — extended)

1. **TC-UNIT-017-01-01:** Wrapper file is executable
   - Read `scripts/wiki-ingest` mode bits via `os.stat`.
   - Expected: `mode & 0o111 != 0` (any execute bit set).
2. **TC-UNIT-017-01-02:** Wrapper has no shell-injection surface
   - Static-grep the wrapper for unquoted `$@` / unquoted `$0`.
   - Expected: ZERO matches. Locks the T17-S8 invariant.
3. **TC-UNIT-017-01-03:** Wrapper has a POSIX shebang
   - First line of the wrapper is exactly `#!/bin/sh`.
4. **TC-UNIT-017-01-04:** macOS-fallback path is exercised when needed
   - Mock `readlink -f` to fail (via a temp `PATH` that prepends a
     stub `readlink` script that exits 1). Run wrapper.
   - Expected: wrapper still succeeds via the Python-realpath fallback.

### Regression Tests

- Run all TASK 015/016 existing tests — no regression.
- `tests/test_architecture.py` green (wrapper is shell, not Python; the
  import-graph walker ignores non-`.py` files).

## Acceptance Criteria

- [ ] `scripts/wiki-ingest` exists, `chmod +x`, first line is `#!/bin/sh`.
- [ ] No shell-injection surface (TC-UNIT-017-01-02 grep silent).
- [ ] `wiki-ingest --version` round-trips per TC-E2E-017-01-01.
- [ ] `wiki-ingest <sub>` ≡ `python3 wiki_ops.py <sub>` per TC-E2E-017-01-02.
- [ ] Symlinked-with-spaces invocation works per TC-E2E-017-01-03.
- [ ] SKILL.md §"Install on PATH" added.
- [ ] All TASK 015/016 tests still green.

## Notes

- `readlink -f` is supported on GNU coreutils, BusyBox, and macOS via
  coreutils-brew (`greadlink`). Stock macOS `readlink` (BSD) requires
  the Python-realpath fallback — T17-S8. The wrapper picks whichever
  works at runtime; tests pass on both.
- The wrapper deliberately avoids `bash`-isms (`[[`, arrays). `#!/bin/sh`
  buys us BusyBox / Alpine / Docker-base portability for downstream
  packagers.
- Future packaging (a `.skill` archive per CLAUDE.md "Независимость
  скиллов") includes `scripts/wiki-ingest` with its executable bit.
