# Task 016.01 — Extract `_page_merge.py` from `commands/upsert_page.py`

## Use Case Connection
- Foundation for **UC-1** (promote reuses additive-merge primitives) and
  **UC-4** (root-aware upsert delegates to the same primitives).

## Task Goal

Promote four additive-merge primitives from `commands/upsert_page.py`
(F3) to a new F2 helper module `wiki_ingest/_page_merge.py`. This resolves
the M-2 import-graph conflict (R3 needs to "reuse" the primitives but
R12.5 forbids `promote.py` from importing `commands/upsert_page.py`).
`commands/upsert_page.py` becomes a thin caller; no behavioural change
to the CLI.

## Changes Description

### New Files
- `skills/wiki-ingest/scripts/wiki_ingest/_page_merge.py` — F2 helper
  (≤150 LoC budget per ARCHITECTURE §3.2).
- `skills/wiki-ingest/scripts/tests/test__page_merge.py` — unit tests
  for the four primitives.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/upsert_page.py`

**Symbols to move to `_page_merge.py`:**

| Symbol                  | Notes                                                          |
|-------------------------|----------------------------------------------------------------|
| `upsert_source_row`     | Adds/dedupes a row under `## Sources mentioning this`          |
| `append_fact`           | Appends a fact under `## Facts` with `[^src-<slug>]` citation  |
| `append_contradiction`  | Wraps two claims in a `## Contradictions` block                |
| `upsert_footnote`       | Adds/dedupes a `[^src-<slug>]: [[<slug>]] — <Title>` definition |

Each function preserves its current signature. Module-level constants
(if any feed into these four) move alongside them.

**After extraction:** at the top of `commands/upsert_page.py`, replace
the moved bodies with:

```python
from wiki_ingest._page_merge import (
    upsert_source_row,
    append_fact,
    append_contradiction,
    upsert_footnote,
)
```

Internal call sites within `commands/upsert_page.py` continue to use the
bare names.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_page_merge.py` (new)

- Module docstring documenting F2 tier + the "additive merge primitives"
  charter.
- Imports stdlib only + `wiki_ingest._safety` (for `die` if needed) +
  `wiki_ingest._markdown` (for `find_section` / `replace_section_body` /
  `insert_section_before` — whatever the moved primitives use) +
  `wiki_ingest._frontmatter` (only if any primitive parses frontmatter —
  most likely no).
- The four functions, byte-identical bodies to the originals.
- No new logic.

### Component Integration

- F2 layer gains a new module. `test_architecture.py` already covers
  `_*.py` helpers via `rglob("_*.py")` (lines 49–52) so no test code
  edit is needed (m-A-1).
- Future consumers (Task 016.06 `commands/promote.py` write path; Task
  016.09 `commands/upsert_page.py` root-aware path) will `from
  wiki_ingest._page_merge import ...`.

## Test Cases

### Unit Tests (`tests/test__page_merge.py` — new)

1. **TC-UNIT-016-01-01:** `upsert_source_row` dedupes by slug
   - Input: page content with existing `- [[foo]] — Foo Title` row;
     call `upsert_source_row(content, "foo", "Foo Title")`.
   - Expected: returns content unchanged (no duplicate row).
2. **TC-UNIT-016-01-02:** `upsert_source_row` appends new slug
   - Input: page without `foo` row.
   - Expected: returned content has the row appended under
     `## Sources mentioning this`.
3. **TC-UNIT-016-01-03:** `append_fact` writes `- <fact> [^src-<slug>]`
   - Input: page with `## Facts` section; fact text "X = 42".
   - Expected: returned content has `- X = 42 [^src-foo]` appended under
     `## Facts`.
4. **TC-UNIT-016-01-04:** `append_contradiction` wraps two claims
   - Input: existing claim "X = 42 [^src-foo]"; new fact "X = 43";
     new source slug "bar".
   - Expected: returned content has a `## Contradictions` block with
     both claims cited.
5. **TC-UNIT-016-01-05:** `upsert_footnote` dedupes by slug
   - Input: footnote definitions list already contains `[^src-foo]: …`.
   - Expected: returns content unchanged.
6. **TC-UNIT-016-01-06:** `upsert_footnote` appends new definition
   - Input: page without `[^src-bar]` definition.
   - Expected: footnote definition appended at the end of the file (or
     wherever the existing pattern places it).

### Regression Tests
- All existing `tests/commands/test_upsert_page.py` cases pass after the
  caller becomes a thin shim (byte-identical behaviour).
- `tests/test_r11_byte_identity.py` passes (no CLI change).
- `tests/test_architecture.py` passes (`_page_merge.py` correctly imports
  from F1/F2 only, no `commands/*` imports).

## Acceptance Criteria
- [ ] `_page_merge.py` created with the four primitives.
- [ ] `commands/upsert_page.py` shrinks by the moved LoC and imports from
      `_page_merge`.
- [ ] All 6 new unit tests pass.
- [ ] Existing `tests/commands/test_upsert_page.py` cases still pass.
- [ ] `tests/test_architecture.py` green (no test edits).
- [ ] `tests/test_r11_byte_identity.py` green.
- [ ] `validate_skill.py` exits 0.
- [ ] `_page_merge.py` LoC ≤ 150 (architecture budget §3.2).
- [ ] `commands/upsert_page.py` LoC reduced accordingly (no new code).

## Notes
- This bead is a **Test-First + Move** refactor (per PLAN §2). Confirm
  existing `test_upsert_page.py` green before the move; confirm green
  after the move.
- Any module-level constant only used by the four primitives also moves.
  Any constant shared with other parts of `upsert_page.py` stays in
  `upsert_page.py` and is imported across (forbidden by import-graph
  invariant if it's an F2 helper consuming an F3 constant — fix by
  moving the constant too).
- Honest-scope: NO new functionality is added in this bead. The
  primitives are byte-identical to their pre-refactor versions.
