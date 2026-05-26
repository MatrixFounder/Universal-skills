# Task 015.09 — Extract `commands/register_summary.py`

## Use Case Connection
- UC-3 (adversarial register-summary smoke).

## Task Goal

Move `cmd_register_summary` — the largest single command (~204 LoC) and
the one with the most security surface (inbox containment, sensitive-path
blocklist, structural frontmatter rewrite).

## Changes Description

### New Files

- `wiki_ingest/commands/register_summary.py` (≤350 LoC, expected ~220).
- `tests/commands/test_register_summary.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `commands/register_summary.py`:**

- `SUMMARY_KIND_HINTS`
- `cmd_register_summary` → `execute`.

Argparse block (including `--inbox-root`) moves into `register(sub)`.

### Component Integration

Imports from `_safety` (`die`, `_safe_name`, `slugify`, `_is_relative_to`,
`read_text`, `write_text`, `_safe_for_json`, `_CTRL_CHARS_RE`,
`MAX_SUMMARY_BYTES`), `_frontmatter` (`split_frontmatter`,
`_splice_frontmatter_fields`), `_vault` (`ensure_schema`).

## Test Cases

### Unit Tests

None at the unit level — the function is a glue path. All coverage at
E2E.

### End-to-end Tests (in `tests/commands/test_register_summary.py`)

1. **TC-E2E-09-1**: `test_register_summary_happy_path` — fixture summary
   under `tests/fixtures/inbox/`; assert `_sources/<slug>.md` created
   with expected content.

2. **TC-E2E-09-2**: `test_register_summary_inbox_containment` — set
   `WIKI_INGEST_INBOX_ROOT=/tmp/safe`; attempt to register
   `/etc/hostname`; assert exit code 8 + stderr mentions "outside inbox
   root". Locks S-M1.

3. **TC-E2E-09-3**: `test_register_summary_sensitive_path_blocklist` —
   no inbox env; attempt to register a path containing `/.ssh/`; assert
   exit code 8. Locks S-M1.

4. **TC-E2E-09-4**: `test_register_summary_size_cap` — supply a path
   pointing to a file > MAX_SUMMARY_BYTES; assert exit code 6.

5. **TC-E2E-09-5**: `test_register_summary_structural_fm_rewrite_prefix_overlap`
   — fixture with `concepts: ["Railway 24/7", "Railway 24/7 Deployment"]`;
   assert both rewrites land cleanly with no `str.replace`-style
   prefix-overlap mangling. Locks L-H5.

6. **TC-E2E-09-6**: `test_register_summary_symlink_refusal` —
   `summary-path` is a symlink; assert exit code 8.

### Regression Tests

- `tests.test_r11_byte_identity` still green.
- `test_architecture` still green.

## Acceptance Criteria

- [ ] Command file ≤350 LoC; expected ~220.
- [ ] All 6 E2E tests pass.
- [ ] R11 gate green; `validate_skill.py` exits 0.
