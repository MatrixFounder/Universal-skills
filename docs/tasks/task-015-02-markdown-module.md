# Task 015.02 — Extract `_markdown.py`

## Use Case Connection
- UC-2 (per-module critic loop).

## Task Goal

Relocate all markdown-shape primitives (code-fence masking, section
locators, wiki-link extraction, sentence segmentation) into
`wiki_ingest/_markdown.py`. `_markdown.py` imports only from `_safety`.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/_markdown.py` (≤350 LoC).
- `skills/wiki-ingest/scripts/tests/test__markdown.py` (≥3 unit tests).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `wiki_ingest/_markdown.py`:**

| Symbol                                    |
|-------------------------------------------|
| `_mask_code_fences`                       |
| `_mask_inline_constructs`                 |
| `_INLINE_CODE_RE`                         |
| `_HTML_COMMENT_INLINE_RE`                 |
| `SECTION_BOUNDARY_RE`                     |
| `_H2_HEADER_RE`                           |
| `_ensure_masked`                          |
| `find_section`                            |
| `find_all_sections`                       |
| `get_all_section_bodies`                  |
| `get_section_body`                        |
| `replace_section_body`                    |
| `insert_section_before`                   |
| `_PLACEHOLDER_LINES`                      |
| `_is_placeholder_line`                    |
| `_existing_lines`                         |
| `WIKILINK_RE`                             |
| `WIKILINK_ANCHOR_RE`                      |
| `WORD_RE`                                 |
| `_extract_wikilinks_with_anchors`         |
| `_HTML_COMMENT_RE`                        |
| `_TLDR_BOLD_RE`                           |
| `_ABBREV_RE`                              |
| `_first_sentence`                         |

Replace bodies with `from wiki_ingest._markdown import (…)`.

### Component Integration

`_markdown.py` imports `die` from `_safety` (only when fatal-error
guard is hit — currently no fatal paths in this module, but keep
`from wiki_ingest._safety import die` for future-proofing). No other
cross-module imports.

## Test Cases

### Unit Tests (in `tests/test__markdown.py`)

1. **TC-UNIT-02-1**: `test_offsets_under_mask` — assert `len(masked) == len(original)` and that every `\n` in original is at the same offset in masked (proves the offset-stability invariant from ARCHITECTURE §4.5.1).

2. **TC-UNIT-02-2**: `test_section_boundary_no_longer_includes_triple_dash` — given `"## Notes\n\nfoo\n\n---\n\nbar\n"`, assert `get_section_body(text, "Notes")` returns the entire body INCLUDING the `---` line and `bar`. Locks L-C3.

3. **TC-UNIT-02-3**: `test_find_all_sections_mask_once_invariant` — given a 5000-`## ` header document, assert `find_all_sections(text, "Foo")` returns in linear-time AND that passing a pre-computed `masked=` argument yields identical output. Locks OVERLAP-3 mask-once.

4. **TC-UNIT-02-4**: `test_extract_wikilinks_with_anchors_skips_inline_code_and_comments` — given `"Real [[Foo]] but \`[[Bar]]\` and <!-- [[Baz]] -->"`, assert result `{"Foo": {""}}`.

5. **TC-UNIT-02-5**: `test_first_sentence_handles_abbreviations` — assert `_first_sentence("Dr. Smith proposed a method. The method worked.")` returns `"Dr. Smith proposed a method."` (not `"Dr."`).

### Regression Tests

- `tests.test_r11_byte_identity` still green.

## Acceptance Criteria

- [ ] `_markdown.py` ≤350 LoC; ≥3 unit tests pass.
- [ ] `wiki_ops.py` no longer defines any moved symbol.
- [ ] R11 gate green; `validate_skill.py` exits 0.

## Notes

- Re-exports stay in `wiki_ops.py` for the duration of this bead (and
  through 015.05) so internal call sites continue to work; trimmed in
  015.12.
