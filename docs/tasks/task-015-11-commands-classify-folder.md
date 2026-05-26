# Task 015.11 — Extract `commands/classify_folder.py`

## Use Case Connection
- UC-3 (classify-folder smoke).

## Task Goal

Move the final subcommand. After this bead, every command lives in its
own module; `wiki_ops.py` contains only argparse glue + dispatch.

## Changes Description

### New Files

- `wiki_ingest/commands/classify_folder.py` (≤200 LoC).
- `tests/commands/test_classify_folder.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `commands/classify_folder.py`:**

- `cmd_classify_folder` → `execute`.

The block of `_classify.py` helpers (moved in 015-05) is imported via:
```python
from wiki_ingest._classify import (
    _OFFICE_EXTS, _IMAGE_EXTS, _METADATA_EXTS, _TEXT_EXTS, _SKIP_EXTS,
    _SKIP_NAMES, _UNGROUPED_SENTINEL, _UNGROUPED_LABEL,
    _PREFIX_REGEX, _classify_one_file, _detect_grouping, _group_files,
    _pick_primary, _count_md_structure,
)
```

### Component Integration

Imports from `_safety` (`die`, `_safe_for_json`), `_classify` (the
helpers above), `_vault` (`SCHEMA_FILE`). Argparse block including
`--group-by` and `--force` moves into `register`.

## Test Cases

### Unit Tests

(Most classify-folder unit tests live in `tests/test__classify.py` from
015-05.)

1. **TC-UNIT-11-1**: `test_classify_folder_refuses_vault_root` — point
   at a folder containing `WIKI_SCHEMA.md` without `--force`; assert
   exit code 2.

### End-to-end Tests

1. **TC-E2E-11-1**: `test_classify_folder.test_byte_identity_against_fixture`
   — subprocess; stdout matches `tests/fixtures/expected/classify.json`.
   (Redundant with R11 but kept as a per-command smoke.)

2. **TC-E2E-11-2**: `test_classify_folder.test_user_group_by_regex` —
   pass `--group-by '^(\d+)\s*-\s*'`; assert grouping uses operator
   override.

### Regression Tests

- `tests.test_r11_byte_identity` still green.
- `test_architecture` still green.

## Acceptance Criteria

- [ ] Command file ≤200 LoC; tests pass.
- [ ] After this bead, `wiki_ops.py` contains 0 (zero) `cmd_*` functions.
- [ ] R11 gate green; `validate_skill.py` exits 0.
