# Task 016.02 — Extend `_splice_frontmatter_fields` for list-of-dicts

## Use Case Connection
- Foundation for **UC-1** (`promote` writes `promoted_from:` as
  `list[{course, date}]`) and **UC-2** (`demote` removes the same field
  cleanly).

## Task Goal

Extend the existing `_splice_frontmatter_fields` helper in
`wiki_ingest/_frontmatter.py` to handle `list[dict]` field values
(specifically `promoted_from: [{course: str, date: str}, ...]`). The
public signature does NOT change — internal code path branches on the
value shape. Single bead (A-M-3 resolution) so 016.06 can assume the
helper is shipped.

## Changes Description

### New Files
- None.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/_frontmatter.py`

**Function `_splice_frontmatter_fields(text: str, fields: dict, fm: dict) -> str`:**
- Extend the existing implementation. Pre-bead behaviour: handles `str`
  and `list[str]` field values.
- Add a third value shape: `list[dict]`. For each dict-list field name in
  `fields`:
  - Serialise as a YAML block:
    ```yaml
    promoted_from:
      - course: "Course A"
        date: 2026-05-26
      - course: "Course B"
        date: 2026-05-26
    ```
  - Keys within each dict are written in INSERTION ORDER (Python 3.7+
    `dict` guarantee). For determinism on cross-platform runs, the keys
    within a dict are written in a sorted order when the upstream caller
    has not explicitly ordered them — document this in the function
    docstring.
- Removal semantics: if `fields` has `promoted_from: None` (or the key
  is absent), the existing remove-field path handles it (no new code).

**Function `_serialize_yaml_list_field` (helper used by splice):**
- Add a sibling helper or extend in place to emit the list-of-dicts
  form. Keep the existing list-of-strings form. Branch on
  `isinstance(item, dict)`.

**Helpers introduced (private)**:
- `_serialize_yaml_dict_inline(d: dict) -> str` — serialise a single dict
  as the `- key: value` indented block.
  - Each key is `_safe_inline`-validated; each value is rendered as a
    bare scalar if it matches `[A-Za-z0-9_.:-]+`, else quoted with double
    quotes.

### Component Integration

- F2 module gains internal complexity; F1 dependency unchanged (still
  imports only `_safety`).
- Consumers (none yet) will pass `{"promoted_from": [{"course": "...",
  "date": "..."}, ...]}` to `_splice_frontmatter_fields`. The
  function returns the rewritten frontmatter text.

## Test Cases

### Unit Tests (`tests/test__frontmatter.py` — extended)

1. **TC-UNIT-016-02-01:** Write a new list-of-dicts field
   - Input: frontmatter with no `promoted_from` field; splice with
     `{"promoted_from": [{"course": "A", "date": "2026-05-26"}]}`.
   - Expected output: YAML block with one entry.
2. **TC-UNIT-016-02-02:** Update an existing list-of-dicts field
   - Input: frontmatter already has `promoted_from: [{course: A, date: 2026-05-26}]`;
     splice with `{"promoted_from": [{"course": "A", "date": "2026-05-26"}, {"course": "B", "date": "2026-05-26"}]}`.
   - Expected: the field is replaced with the new two-entry list.
3. **TC-UNIT-016-02-03:** Remove a list-of-dicts field
   - Input: frontmatter has `promoted_from: [{course: A, date: ...}]`;
     splice with `{"promoted_from": None}`.
   - Expected: the field is removed; other fields preserved.
4. **TC-UNIT-016-02-04:** Round-trip parse → splice → parse
   - Input: write `promoted_from: [{c1,d1},{c2,d2}]`; re-parse via
     `split_frontmatter`; the resulting `fm["promoted_from"]` is a
     `list[dict]` with the expected keys/values.
5. **TC-UNIT-016-02-05:** Course names with quoting (NFKC + spaces)
   - Input: `{"promoted_from": [{"course": "Course A", "date": "2026-05-26"}]}`.
   - Expected: the YAML output quotes the course value (`"Course A"`) so
     it round-trips cleanly.
6. **TC-UNIT-016-02-06:** Existing list-of-strings field path unchanged
   - Input: splice with `{"concepts": ["a", "b", "c"]}`.
   - Expected: byte-identical output to the pre-bead behaviour.
7. **TC-UNIT-016-02-07:** Existing single-string field path unchanged
   - Input: splice with `{"title": "Foo Bar"}`.
   - Expected: byte-identical output to the pre-bead behaviour.

### Regression Tests
- All existing `tests/test__frontmatter.py` tests pass.
- `tests/test_architecture.py` passes (no new imports).
- `tests/test_r11_byte_identity.py` passes (no CLI consumer yet).
- `tests/commands/test_upsert_page.py` passes (no consumer in this bead).

## Acceptance Criteria
- [ ] `_splice_frontmatter_fields` handles `list[dict]` field values.
- [ ] All 7 new unit tests pass.
- [ ] Existing `_frontmatter.py` test suite still green.
- [ ] `tests/test_architecture.py` green.
- [ ] `tests/test_r11_byte_identity.py` green.
- [ ] `validate_skill.py` exits 0.
- [ ] `_frontmatter.py` LoC ≤ 350 (architecture budget; current ~333).
- [ ] Function docstring updated to document the new shape.

## Notes
- Public signature MUST NOT change. The architect explicitly noted that
  the splice helper's "public signature unchanged" is a contract.
- The serialisation format MUST match what `split_frontmatter` can
  re-parse. Round-trip test (TC-UNIT-016-02-04) locks this in.
- Honest-scope: ONLY list-of-dicts shape is added. No support for
  nested dicts beyond one level (out of scope; not needed for
  `promoted_from`). Document in docstring.
