# Task 015.07 — Extract `commands/upsert_page.py` + `commands/update_index.py`

## Use Case Connection
- UC-3 (additive-upsert flow remains byte-identical).

## Task Goal

Move the two mid-complexity commands that drive concept/entity page
mutation. Each depends on `_markdown`, `_frontmatter`, `_safety`, `_vault`.

## Changes Description

### New Files

- `wiki_ingest/commands/upsert_page.py` (≤250 LoC) — includes the
  command-local helpers `render_stub_page`, `page_path`,
  `upsert_source_row`, `append_fact`, `append_contradiction`,
  `upsert_footnote` (these are only used by `cmd_upsert_page` and have
  no other call site).
- `wiki_ingest/commands/update_index.py` (≤150 LoC) — includes
  command-local `add_index_row`, `INDEX_SECTIONS`. **`_collect_names`
  is imported from `_safety` (centralised in 015.01) — NOT duplicated.**
- `tests/commands/test_upsert_page.py`.
- `tests/commands/test_update_index.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `commands/upsert_page.py`:**

| Symbol                        |
|-------------------------------|
| `CONCEPT_KIND`, `ENTITY_KIND` |
| `KIND_TO_SUBDIR`              |
| `page_path`                   |
| `render_stub_page`            |
| `upsert_source_row`           |
| `append_fact`                 |
| `append_contradiction`        |
| `upsert_footnote`             |
| `cmd_upsert_page` → `execute` |

**Symbols to move to `commands/update_index.py`:**

| Symbol               |
|----------------------|
| `INDEX_SECTIONS`     |
| `add_index_row`      |
| `cmd_update_index` → `execute` |

`_collect_names` was moved to `_safety.py` in 015-01 (because it's
shared by `cmd_update_index` AND `cmd_append_log`, and duplicating
across commands would violate the "single source of truth" principle).
Both commands import it from `_safety`.

Replace bodies + their `argparse` blocks with the
`register(sub)` / `execute(args)` shape.

### Component Integration

Imports per command (subset rule from R7.2):
- `commands/upsert_page.py`: imports from `_safety`, `_markdown`,
  `_frontmatter`, `_vault`.
- `commands/update_index.py`: imports from `_safety`, `_markdown`,
  `_vault`.

## Test Cases

### Unit Tests

1. **TC-UNIT-07-1**: `test_render_stub_page_substitution_singlepass` —
   given `name="{{KIND}}"` would be a template-injection but it's blocked
   by `_safe_name`; instead test with a benign name and assert the
   placeholders are substituted exactly once.
2. **TC-UNIT-07-2**: `test_upsert_source_row_idempotent` — call
   `upsert_source_row` twice with same args; assert the result is
   unchanged on the second call.
3. **TC-UNIT-07-3**: `test_add_index_row_dedupe_by_list_items_not_substring` — locks L-H3.

### End-to-end Tests

1. **TC-E2E-07-1**: `test_upsert_page.test_create_then_additive_update` —
   init vault, upsert a concept twice with two different sources, assert:
   - definition preserved
   - 2 footnotes
   - 2 unique source rows
   - no duplicates in `## Sources mentioning this`
2. **TC-E2E-07-2**: `test_update_index.test_add_new_concept_row` —
   assert the new row appears under `## Concepts` and is not duplicated
   on second invocation.

### Regression Tests

- `tests.test_r11_byte_identity` still green.
- `test_architecture` still green (no new cross-command imports).

## Acceptance Criteria

- [ ] Both command files within their LoC ceilings; tests pass.
- [ ] R11 gate green; `validate_skill.py` exits 0.
- [ ] `_collect_names` is imported from `_safety` (centralised in 015.01),
      NOT duplicated.
