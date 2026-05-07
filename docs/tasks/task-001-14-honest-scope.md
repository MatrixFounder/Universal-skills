# Task 2.09 [R9]: [LOGIC IMPLEMENTATION] Honest-scope regression locks

## Use Case Connection
- I4.1 (Honest-scope regression tests).
- R9.a–R9.g (all v1 limitations).
- RTM: R9.

## Task Goal
Convert all six honest-scope unit tests from skipped (Stage 1) to actually-asserting tests that lock the v1 limitations into the regression suite. These tests prevent silent scope-creep — if a future change accidentally adds `parentId`, rich-text, custom anchors, or a `--default-initials` flag, these tests fail loudly.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_xlsx_add_comment.py`

**Class `TestHonestScope`** — remove `skipTest` from each test and implement assertions:

**`test_HonestScope_no_parentId` (R9.a):**
- Run xlsx_add_comment.py twice on the same cell with `--threaded` (forming a thread).
- Parse produced `xl/threadedComments1.xml`; assert NO `<threadedComment>` has a `parentId` attribute.

**`test_HonestScope_plain_text_body` (R9.b):**
- Run with `--text "msg"` `--threaded`.
- Parse `<threadedComment>` body — assert direct text node, NO `<r>`, NO `<rPr>`, NO any rich-run wrappers.
- Same check for legacy `<comment><text><r><t>` body — `<t>` text is the literal `msg`, no nested formatting elements beyond the standard `<r><t>`.

**`test_HonestScope_default_vml_anchor` (R9.c):**
- Run any single-cell test producing VML.
- Parse `<v:shape>` `<x:Anchor>` element — assert it equals `"3, 15, 0, 5, 5, 31, 4, 8"` (the locked default).

**`test_HonestScope_threadedComment_id_is_uuidv4` (R9.e):**
- Run with `--threaded --date 2026-01-01T00:00:00Z` twice on different cells.
- Parse both `<threadedComment id>` values.
- Assert each matches `^\{[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}\}$` (UUIDv4 pattern: `4` in 13th hex, `[89AB]` in 17th hex).
- Assert the two ids are DIFFERENT (non-determinism lock — re-running ≠ byte-equal).

**`test_HonestScope_no_unpacked_dir_flag` (R9.g):**
- `python3 xlsx_add_comment.py --help` → grep stdout; assert `--unpacked-dir` NOT in help text.
- `python3 xlsx_add_comment.py file.xlsx out.xlsx --unpacked-dir /tmp/foo --cell A5 --author Q --text msg` → exit 2 `UsageError` (argparse rejects unknown flag).

**`test_HonestScope_no_default_initials_flag` (R9.f):**
- `python3 xlsx_add_comment.py --help` → assert `--default-initials` NOT in help text.

**(New) `test_HonestScope_goldens_README_exists`** (R9.d / m4):
- Assert `tests/golden/README.md` exists and contains the literal string `"DO NOT open these files in Excel"` (the agent-output-only protocol marker).

### Component Integration
- All tests use `subprocess.run` against the installed CLI (`./.venv/bin/python xlsx_add_comment.py ...`), NOT in-process `main(argv)` — so they verify the user-facing surface, not just the helpers.

## Test Cases

### End-to-end Tests
- The honest-scope unit tests above ARE the E2E story for R9. Adding a redundant `T-` E2E in `test_e2e.sh` is unnecessary.

### Unit Tests
- All 7 `TestHonestScope` tests pass.

### Regression Tests
- All Stage-2 tests stay green.
- The honest-scope tests should NOT cause regressions in other tests (they may need to share fixtures).

## Acceptance Criteria
- [ ] 7 unit tests in `TestHonestScope` pass.
- [ ] R9.a parentId-absent lock confirmed on a 2-comment-same-cell scenario.
- [ ] R9.e UUIDv4 pattern + non-determinism lock confirmed.
- [ ] R9.f / R9.g no-flag locks confirmed via `--help` text inspection.
- [ ] R9.d goldens README protocol marker confirmed.
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The UUIDv4 pattern regex is the canonical way to verify v4-not-v5 — the `4` and `[89AB]` bits are the version+variant markers per RFC 4122.
- If a future enhancement intentionally lifts one of these limitations (e.g. v2 adds `parentId`), the corresponding test gets removed in the same commit — so the test acts as a scope-creep alarm AND as a documentation marker for what's locked.
- `tests/golden/README.md` was created in 1.04; this task only re-asserts its presence + protocol-marker text.
