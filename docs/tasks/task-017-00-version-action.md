# Task 017.00 — `__version__ = "1.1.0"` + `wiki_ops.py --version`

## Use Case Connection

- **UC-1** Main scenario step 2 (the bridge's first call is
  `wiki-ingest --version`; this bead makes that call exit 0 with a
  parseable format).
- Smoke-gate for every downstream bead (017.01..017.09 all assume
  `--version` works).

## Task Goal

Add the single source-of-truth version constant
`wiki_ingest/__init__.py::__version__ = "1.1.0"` and a top-level
`--version` `argparse.Action` in `wiki_ops.py` that prints
`wiki-ingest 1.1.0\n` to stdout and exits 0. NO subcommand-level
behavioural change.

Per Stub-First, this is a substrate bead — no stubs, no two-pass needed
(it is a 1-LoC constant + 3-LoC argparse action). Test-first: write the
assertion ("`wiki_ops.py --version` exits 0 with the exact string"),
confirm Red, then add the constant + action.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/test_cli_wrapper.py` — new test
  module for CLI-wrapper-adjacent smoke tests. This bead adds the
  version assertions; 017.01 extends with wrapper-specific cases.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/__init__.py`

- Add the line: `__version__ = "1.1.0"`.
- File was previously empty / package-marker only. Keep total LoC ≤ 30
  (architecture §3.2 budget).

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

- At the top of the file (after existing stdlib imports), add:
  `from wiki_ingest import __version__ as _WIKI_INGEST_VERSION`.
- In `build_parser()` (the existing argparse builder), add to the
  top-level `ArgumentParser`:
  `parser.add_argument("--version", action="version",
  version=f"wiki-ingest {_WIKI_INGEST_VERSION}")`.
- The `action="version"` exits 0 after printing — no additional code
  needed. The format is EXACTLY `wiki-ingest 1.1.0\n` (CONTRACT §7
  minimum-version check uses string-prefix matching).
- LoC budget stays ≤ 200 (this adds ~2 LoC).

### Component Integration

- `wiki_ops.py` already imports the `wiki_ingest` package. The new
  import is one symbol; no architectural surface change.
- The `argparse.Action`-of-type-version is stdlib; NO new dep.
- `--version` is mutually exclusive with subcommands by argparse design
  (an action-of-type-version exits before subcommand dispatch).

## Test Cases

### End-to-end Tests

1. **TC-E2E-017-00-01:** `wiki_ops.py --version` exit format
   - Run: `python3 skills/wiki-ingest/scripts/wiki_ops.py --version`
   - Expected: stdout exactly `wiki-ingest 1.1.0\n`; exit 0; stderr empty.
2. **TC-E2E-017-00-02:** Minimum-version assertion (CONTRACT §7)
   - Parse stdout: `parts = stdout.strip().split()`.
   - Expected: `parts[0] == "wiki-ingest"` AND tuple of ints from
     `parts[1].split(".")[:2] >= (1, 1)`.

### Unit Tests (`tests/test_cli_wrapper.py` — new)

1. **TC-UNIT-017-00-01:** `__version__` constant present and well-formed
   - Import `wiki_ingest`, read `__version__`.
   - Expected: matches regex `^\d+\.\d+\.\d+$`; tuple of ints ≥ `(1, 1, 0)`.
2. **TC-UNIT-017-00-02:** No eager command import on `--version`
   - Run `wiki_ops.py --version` as a subprocess with a `WIKI_INGEST_TRACE_IMPORTS=1`
     env var (the test's setUp installs a `sitecustomize.py` shim that records
     module imports to a temp file). Verify NONE of `wiki_ingest.commands.*`
     modules are loaded.
   - Reason: keeps `--version` snappy (≤ 50 ms per architecture §8) and
     defends the perf budget against future regressions.

### Regression Tests

- Run all existing tests from `skills/wiki-ingest/scripts/tests/` —
  no regression to TASK 015/016 surface.

## Acceptance Criteria

- [ ] `wiki_ingest/__init__.py::__version__ == "1.1.0"`.
- [ ] `python3 wiki_ops.py --version` exits 0 with exact stdout
      `wiki-ingest 1.1.0\n`.
- [ ] `tests/test_cli_wrapper.py` green (TC-UNIT-017-00-01, -02 + the
      two E2E cases).
- [ ] All TASK 015/016 existing tests still green.
- [ ] `wiki_ops.py` total LoC ≤ 200 (architecture §3.2 budget).
- [ ] `tests/test_architecture.py` green (unchanged; bead does not touch
      the import graph).

## Notes

- Single source of truth: the version lives in `wiki_ingest/__init__.py`
  ONLY. SKILL.md and `references/manifest_schema.md` (added in 017-04)
  cite the constant indirectly ("see `wiki_ingest/__init__.py`"); no
  duplicate hardcoded value to drift.
- Future bumps: update `__init__.py` once; all consumers re-read
  automatically. The `tests/test_cli_wrapper.py::TC-UNIT-017-00-01`
  minimum-version assertion stays loose (`>= (1, 1, 0)`) so a future
  1.2.x bump does not regress.
