# Task 015.03 — Extract `_frontmatter.py`

## Use Case Connection
- UC-2 (per-module critic loop).

## Task Goal

Relocate YAML frontmatter parsing + structural rewrite into
`wiki_ingest/_frontmatter.py`. Imports only from `_safety`.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/_frontmatter.py` (≤300 LoC).
- `skills/wiki-ingest/scripts/tests/test__frontmatter.py` (≥3 tests).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `wiki_ingest/_frontmatter.py`:**

| Symbol                              |
|-------------------------------------|
| `_strip_quotes`                     |
| `_parse_flow_list`                  |
| `_FM_CLOSER_RE`                     |
| `_FM_KEY_RE`                        |
| `_strip_trailing_comment`           |
| `_strip_frontmatter_fast`           |
| `split_frontmatter`                 |
| `_serialize_yaml_list_field`        |
| `_splice_frontmatter_fields`        |

Replace bodies with `from wiki_ingest._frontmatter import (…)`.

### Component Integration

`_frontmatter.py` imports `die` from `_safety` (the `_safe_inline` guard
isn't called from here — it lives in commands; just the fatal-error path).

## Test Cases

### Unit Tests

1. **TC-UNIT-03-1**: `test_close_delimiter_line_anchored` — given a YAML
   block scalar value containing `\n---` (e.g. `description: |\n  ---\n  more`),
   assert the frontmatter close delimiter is detected at the actual
   `^---$` line, not at the substring. Locks L-C2.

2. **TC-UNIT-03-2**: `test_split_frontmatter_warnings_out_parameter` —
   given a malformed line like `concepts;wrong`, pass `warnings=[]` and
   assert the warning is appended (locks L-M5).

3. **TC-UNIT-03-3**: `test_splice_preserves_unchanged_fields` — given
   `concepts: [a, b]`, `title: "x"`, `date: "2024-01-01"`, call
   `_splice_frontmatter_fields(text, ["concepts"], {"concepts": ["a-new"]})`.
   Assert: `concepts` rebuilt; `title` and `date` lines byte-identical
   to input; body unchanged.

4. **TC-UNIT-03-4**: `test_splice_keeps_closer_newline` — regression for
   the `Normal Name---` collision bug found in interactive smoke test
   during the May VDD fix loop. Assert the rebuilt frontmatter has
   exactly one `\n` before the closing `---`.

5. **TC-UNIT-03-5**: `test_parse_flow_list_quoted_with_commas` — given
   `key: [a, "b, c", d]`, assert result is `["a", "b, c", "d"]`.

### Regression Tests

- `tests.test_r11_byte_identity` still green.

## Acceptance Criteria

- [ ] `_frontmatter.py` ≤300 LoC; ≥3 unit tests pass.
- [ ] R11 gate green; `validate_skill.py` exits 0.
