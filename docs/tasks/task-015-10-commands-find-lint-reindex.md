# Task 015.10 — Extract `commands/find.py` + `commands/lint.py` + `commands/reindex.py`

## Use Case Connection
- UC-3 (full E2E init → upsert → lint → reindex byte-identity).

## Task Goal

Move the three read-mostly subcommands. `lint` and `reindex` are the
performance-critical ones (mask-once invariants must be preserved).

## Changes Description

### New Files

- `wiki_ingest/commands/find.py` (≤150 LoC).
- `wiki_ingest/commands/lint.py` (≤300 LoC).
- `wiki_ingest/commands/reindex.py` (≤250 LoC) — includes the command-local
  `_first_sentence` and `_page_one_line` helpers (they're only called by
  `cmd_reindex`); `_first_sentence` already lives in `_markdown.py` after
  015-02, so `reindex.py` imports it from there. `_page_one_line` is
  reindex-local — keep it inline.
- `tests/commands/test_find.py`.
- `tests/commands/test_lint.py`.
- `tests/commands/test_reindex.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move:**

- `cmd_find` → `commands/find.py::execute`.
- `cmd_lint` → `commands/lint.py::execute`.
- `cmd_reindex` → `commands/reindex.py::execute`.
- `_page_one_line` (reindex-local) → `commands/reindex.py`.

### Component Integration

- `find.py`: imports `_safety` (`read_text`, `die`, `_safe_for_json`,
  `SUBDIR_TO_KIND` from `_vault`), `_frontmatter`
  (`split_frontmatter`, `_strip_frontmatter_fast`), `_vault` (`_walk_pages`).

- `lint.py`: imports `_safety` (`read_text`, `_safe_for_json`),
  `_markdown` (`_mask_code_fences`, `_mask_inline_constructs`,
  `_extract_wikilinks_with_anchors`, `get_section_body`,
  `WIKILINK_ANCHOR_RE`-style regex re-export not needed since the helper
  encapsulates it), `_frontmatter` (`split_frontmatter`), `_vault`
  (`_walk_pages`, `SUBDIR_TO_KIND`).

- `reindex.py`: imports `_safety` (`write_text`, `read_text`),
  `_markdown` (`_mask_code_fences`, `_mask_inline_constructs`,
  `_H2_HEADER_RE`, `get_section_body`, `get_all_section_bodies`,
  `replace_section_body`, `_first_sentence`, `_HTML_COMMENT_RE`),
  `_frontmatter` (`split_frontmatter`), `_vault` (`_walk_pages`,
  `INDEX_FILE`, `SUBDIR_TO_KIND`, `SUBDIR_TO_DISPLAY`, `DEFAULT_SUBDIRS`,
  `load_asset`, `ensure_schema`).

## Test Cases

### Unit Tests

1. **TC-UNIT-10-1**: `test_find_body_only_scoring` — fixture with one
   page repeating `crypto×5` in frontmatter, one with two real
   `crypto` mentions in body; assert the body-mention page ranks
   higher. Locks L-M3.

2. **TC-UNIT-10-2**: `test_lint_dangling_includes_anchors` — fixture
   with `[[Foo#API]]` and no `Foo` page; assert dangling report has
   `anchors: ["#API"]`. Locks L-L4.

3. **TC-UNIT-10-3**: `test_lint_concept_freq_case_insensitive` — two
   sources mentioning `"Hermes Agent"` and `"hermes agent"`; assert
   `missing_concept_pages` returns ONE entry with count=2. Locks L-L7.

4. **TC-UNIT-10-4**: `test_lint_redos_guard` — generate a synthetic page
   with 10 000 `## H<i>` headers; call `cmd_lint`; assert wall-clock
   ≤ 1 s. Locks the mask-once invariant (OVERLAP-3 / S-M2).

### End-to-end Tests

1. **TC-E2E-10-1**: `test_lint.test_lint_byte_identity_against_fixture` —
   subprocess-driven; stdout matches `tests/fixtures/expected/lint.json`.
   (Redundant with R11 but kept as a per-command smoke.)

2. **TC-E2E-10-2**: `test_reindex.test_reindex_preserves_custom_section` —
   fixture has a `## Notes` section in `index.md`; reindex; assert
   `## Notes` survives in the rebuilt index.

3. **TC-E2E-10-3**: `test_find.test_find_returns_sanitised_titles` —
   fixture with a control character in `title:` frontmatter; assert the
   JSON output strips it (locks S-M6).

### Regression Tests

- `tests.test_r11_byte_identity` still green — particularly the `lint`
  byte-identity gate.
- `test_architecture` still green.

## Acceptance Criteria

- [ ] Three command files within LoC ceilings.
- [ ] Mask-once perf invariant preserved — `TC-UNIT-10-4` passes
      (10 000-header `lint` wall-clock ≤ 1 s).
- [ ] R11 gate green; `validate_skill.py` exits 0.
