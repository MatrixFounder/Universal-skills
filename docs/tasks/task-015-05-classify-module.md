# Task 015.05 — Extract `_classify.py`

## Use Case Connection
- UC-2 (per-module critic loop).

## Task Goal

Relocate folder-classification helpers (used only by `classify-folder`)
into `wiki_ingest/_classify.py`. Imports only from `_safety`.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/_classify.py` (≤350 LoC).
- `skills/wiki-ingest/scripts/tests/test__classify.py` (≥3 tests).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `wiki_ingest/_classify.py`:**

| Symbol                          |
|---------------------------------|
| `_OFFICE_EXTS`                  |
| `_IMAGE_EXTS`                   |
| `_METADATA_EXTS`                |
| `_TEXT_EXTS`                    |
| `_SKIP_EXTS`                    |
| `_SKIP_NAMES`                   |
| `_PRIMARY_HINTS`                |
| `_NON_PRIMARY_HINTS`            |
| `_PREFIX_REGEX`                 |
| `_UNGROUPED_SENTINEL`           |
| `_UNGROUPED_LABEL`              |
| `_EXTENSIONLESS_TEXT_NAMES`     |
| `_is_text_readable`             |
| `_count_md_structure`           |
| `_filename_hint_score`          |
| `_looks_like_wiki_summary`      |
| `_classify_one_file`            |
| `_detect_grouping`              |
| `_group_files`                  |
| `_pick_primary`                 |

`math` import that lived for `_pick_primary` moves to `_classify.py`.

Replace bodies with `from wiki_ingest._classify import (…)`.

### Component Integration

`_classify.py` imports only stdlib + nothing from sibling modules. The
`cmd_classify_folder` handler in `wiki_ops.py` continues to call these
symbols — until it moves in 015.11.

## Test Cases

### Unit Tests

1. **TC-UNIT-05-1**: `test_count_md_structure_rejects_binary_masquerade`
   — write a file containing a NUL byte; assert `_count_md_structure`
   returns `is_prose=False`. Locks L-M8.

2. **TC-UNIT-05-2**: `test_filename_hint_score_segment_aware` — assert
   `_filename_hint_score("speculation")` does NOT match the `spec`
   negative-hint substring (segment-aware split).

3. **TC-UNIT-05-3**: `test_detect_grouping_prefix_vs_sibling_vs_flat` —
   three scenarios; assert the right pattern label.

4. **TC-UNIT-05-4**: `test_ungrouped_sentinel_no_collision` — assert
   `_UNGROUPED_SENTINEL is not "_ungrouped"` and `_UNGROUPED_SENTINEL`
   is the same object across re-imports.

5. **TC-UNIT-05-5**: `test_looks_like_wiki_summary_streams_1kb` — write
   a 2 MB file whose first 1024 bytes contain `type: lesson-summary`;
   assert the function returns True without reading the full 2 MB
   (verifiable via a `monkeypatch` on `f.read` to assert the requested
   byte count is 1024).

### Regression Tests

- `tests.test_r11_byte_identity` still green — `classify.json` fixture
  must continue to byte-match.

## Acceptance Criteria

- [ ] `_classify.py` ≤350 LoC; ≥3 unit tests pass.
- [ ] R11 gate green; `validate_skill.py` exits 0.
