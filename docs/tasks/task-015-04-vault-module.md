# Task 015.04 — Extract `_vault.py`

## Use Case Connection
- UC-2 (per-module critic loop).

## Task Goal

Relocate vault-layout constants + walk + asset/schema loaders into
`wiki_ingest/_vault.py`. Imports from `_safety` + `_frontmatter`.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/_vault.py` (≤150 LoC).
- `skills/wiki-ingest/scripts/tests/test__vault.py` (≥3 tests).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `wiki_ingest/_vault.py`:**

| Symbol                |
|-----------------------|
| `DEFAULT_SUBDIRS`     |
| `SUBDIR_TO_KIND`      |
| `SUBDIR_TO_DISPLAY`   |
| `SCHEMA_FILE`         |
| `INDEX_FILE`          |
| `LOG_FILE`            |
| `ASSETS_DIR`          |
| `_walk_pages`         |
| `load_vault_pages`    |
| `ensure_schema`       |
| `load_asset`          |
| `tail_log`            |

`SCRIPT_DIR` and `SKILL_DIR` stay in `wiki_ops.py` (they're path
constants tied to the shim's location). `ASSETS_DIR` is recomputed in
`_vault.py` as `Path(__file__).resolve().parent.parent.parent / "assets"`
(two levels up from `wiki_ingest/_vault.py` lands on `scripts/`; one
more lands on the skill root).

Replace bodies with `from wiki_ingest._vault import (…)`.

### Component Integration

`_vault.py` imports `_skip_symlink` from `_safety` and `split_frontmatter`
from `_frontmatter` (for `load_vault_pages`'s frontmatter parse).

## Test Cases

### Unit Tests

1. **TC-UNIT-04-1**: `test_walk_pages_skips_symlinks` — set up a vault
   with `_concepts/MALICIOUS.md` symlinked to `/etc/passwd` (or any
   target outside the vault); assert `list(_walk_pages(vault))` does
   NOT contain `MALICIOUS.md`. Locks OVERLAP-5.

2. **TC-UNIT-04-2**: `test_load_vault_pages_subdir_buckets` — populate
   a vault with one source, two concepts, one entity, one root-level
   stray page; assert the returned dict has the right counts in each
   bucket.

3. **TC-UNIT-04-3**: `test_tail_log_ignores_fenced_code_examples` —
   given a `log.md` with `## [2024-01-01] real` outside any fence AND
   an example `## [2024-02-02] fake` inside a fenced ```` ```md ````
   block, assert `tail_log(vault, 5)` returns only `real`. Locks L-M6.

4. **TC-UNIT-04-4**: `test_load_asset_resolves_via_assets_dir` — assert
   `load_asset("index.template.md")` returns a non-empty string starting
   with the template's expected first line.

5. **TC-UNIT-04-5**: `test_ensure_schema_dies_when_absent` — assert
   `ensure_schema(empty_vault)` calls `sys.exit(2)`.

### Regression Tests

- `tests.test_r11_byte_identity` still green.

## Acceptance Criteria

- [ ] `_vault.py` ≤150 LoC; ≥3 unit tests pass.
- [ ] R11 gate green; `validate_skill.py` exits 0.
