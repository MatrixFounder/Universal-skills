# Task 015.00 — Determinism pre-check + fixture freeze

## Use Case Connection
- UC-3 (smoke E2E preservation across refactor).

## Task Goal

Lock the R11 byte-identity contract by:
1. Verifying that `scan`, `lint`, and `classify-folder` already produce
   deterministic stdout (sorted keys, sorted file iteration). Apply a
   minimal fix if drift is found.
2. Committing **frozen** fixture vaults / folders under
   `skills/wiki-ingest/scripts/tests/fixtures/` whose `log.md` is static
   (no `append-log` / `log-event` was run during fixture creation).
3. Capturing the **expected** stdout of each of the three commands run
   against the frozen fixtures under `tests/fixtures/expected/`.

After this task, every subsequent bead's R11 check is a single `diff -q`
against the captured expected files. The byte-identity contract becomes
mechanically enforceable.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/__init__.py` — empty marker.
- `skills/wiki-ingest/scripts/tests/fixtures/scan_vault/` — fixture vault
  for `scan` (frozen `log.md`, three concept pages, two source pages,
  one entity, deterministic frontmatter).
- `skills/wiki-ingest/scripts/tests/fixtures/scan_vault/WIKI_SCHEMA.md`,
  `index.md`, `log.md` (with **fixed** `## [2024-01-01] init |` heading),
  `_sources/*.md`, `_concepts/*.md`, `_entities/*.md`.
- `skills/wiki-ingest/scripts/tests/fixtures/lint_vault/` — fixture for
  `lint`: includes deliberately dangling links, an orphan concept, a
  contradiction block, a `concepts:` aggregation across two casings, and
  a wiki-link with `#anchor`.
- `skills/wiki-ingest/scripts/tests/fixtures/classify_folder/` — fixture
  folder for `classify-folder` (mix of `.txt`, `.md`, `.docx` stubs,
  with a `01-...`, `02-...` numbering pattern).
- `skills/wiki-ingest/scripts/tests/fixtures/expected/scan.json` —
  captured stdout from `python3 wiki_ops.py scan tests/fixtures/scan_vault`.
- `skills/wiki-ingest/scripts/tests/fixtures/expected/lint.json` — captured
  stdout from `python3 wiki_ops.py lint tests/fixtures/lint_vault`.
- `skills/wiki-ingest/scripts/tests/fixtures/expected/classify.json` —
  captured stdout from `python3 wiki_ops.py classify-folder
  tests/fixtures/classify_folder`.
- `skills/wiki-ingest/scripts/tests/test_r11_byte_identity.py` — the
  R11 gate: runs each of the three commands via `subprocess` against
  its fixture and asserts `stdout == expected.read_text()`. **This is
  the test that every subsequent bead re-runs.**

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

If the determinism check fails (e.g. unsorted file iteration in
`_walk_pages`, or `json.dumps` without `sort_keys=True` somewhere):

**Function `cmd_scan` / `cmd_lint` / `cmd_classify_folder` / `_walk_pages`** —
- Ensure `json.dumps(..., sort_keys=True, ...)` if not already set.
- Ensure `_walk_pages` yields paths in sorted order (already does via
  `sorted(d.glob("*.md"))`).
- Ensure dict iteration is deterministic (Python 3.7+ insertion-order
  guarantee covers this; just verify no `set` iteration leaks into JSON).

Likely fix: **none required** — code review during this task probably
finds the existing output is deterministic. If a fix IS needed, it lands
in this commit before the fixtures are captured.

### Component Integration

The fixtures become the contract that gates every bead. The R11 gate test
runs `wiki_ops.py` (or, after later beads, the dispatch through `wiki_ingest.commands.*`)
via `subprocess` and compares stdout against the captured expected file.
No internal API knowledge is required — the test treats the CLI as a
black box, which is exactly the right shape for a refactor-safety net.

## Test Cases

### End-to-end Tests

1. **TC-E2E-00-1**: `test_r11_byte_identity.test_scan_byte_identity`
   - Input: `tests/fixtures/scan_vault/`.
   - Expected: `stdout == tests/fixtures/expected/scan.json`.

2. **TC-E2E-00-2**: `test_r11_byte_identity.test_lint_byte_identity`
   - Input: `tests/fixtures/lint_vault/`.
   - Expected: `stdout == tests/fixtures/expected/lint.json`.

3. **TC-E2E-00-3**: `test_r11_byte_identity.test_classify_byte_identity`
   - Input: `tests/fixtures/classify_folder/`.
   - Expected: `stdout == tests/fixtures/expected/classify.json`.

### Unit Tests

None — this bead is purely contract-locking.

### Regression Tests

- Run `python3 wiki_ops.py scan/lint/classify-folder` against the fixtures
  10 consecutive times (in a loop in the test) and confirm stdout is
  identical across all 10 runs. **This is what proves determinism.**

## Acceptance Criteria

- [ ] All three fixture vaults / folders exist and are committed.
- [ ] All three expected JSON files exist and are committed.
- [ ] `python -m unittest tests.test_r11_byte_identity` passes 0/3 failures.
- [ ] Running each of the three commands 10× produces identical stdout
      (proven by the 10-iteration regression loop in the test).
- [ ] If any code change was required, the diff is ≤30 LoC and isolated
      to `wiki_ops.py`; no module split has happened yet.

## Notes

- **Fixture-vault content choices**: keep the vaults SMALL (≤10 files
  each). The point is to exercise edge cases (dangling links, anchor
  links, contradictions, missing concepts), not stress-test scale.
- The `## [YYYY-MM-DD]` heading in `log.md` is **frozen** at
  `## [2024-01-01] init | fixture seed`. Subsequent beads MUST NOT run
  `append-log` against the fixture vaults.
- This bead does NOT yet create `wiki_ingest/` — that begins in 015.01.
