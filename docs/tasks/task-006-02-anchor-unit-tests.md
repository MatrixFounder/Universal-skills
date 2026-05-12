# Task 006-02: New `docx_anchor.py` helpers + `test_docx_anchor.py` GREEN

## Use Case Connection
- **UC-1** — `_replace_in_run` is the workhorse of the `--replace` action.
- **UC-2, UC-3** — `_concat_paragraph_text` + `_find_paragraphs_containing_anchor` are the locator primitives for `--insert-after` and `--delete-paragraph` (D6 policy B).

## Task Goal

Implement the **three new helper functions** in `docx_anchor.py`
(joining the three extracted in 006-01a) and turn the ≥ 20 unit cases
in `test_docx_anchor.py` GREEN. End state: `docx_anchor.py` ≤ 180 LOC
(full ARCH §3.2 budget reached); helper module complete and frozen
until v2.

New functions (per ARCH §F3):
- `_replace_in_run(paragraph: etree._Element, anchor: str, replacement: str, *, anchor_all: bool) -> int`
- `_concat_paragraph_text(paragraph: etree._Element) -> str`
- `_find_paragraphs_containing_anchor(part_root: etree._Element, anchor: str) -> list[etree._Element]`

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_anchor.py`

**Add new function `_replace_in_run`:**

```python
def _replace_in_run(
    paragraph: etree._Element,
    anchor: str,
    replacement: str,
    *,
    anchor_all: bool,
) -> int:
    """Cursor-loop replace inside simple text runs of `paragraph`.

    Returns the count of replacements performed. Stops after first match
    unless `anchor_all=True`. Caller must have already invoked
    `_merge_adjacent_runs(paragraph)`.

    Honest scope (D6 / B): anchor must fit within ONE <w:t> after the
    merge — cross-run anchors are NOT matched here.
    """
    count = 0
    for run in paragraph.iter(qn("w:r")):
        if not _is_simple_text_run(run):
            continue
        t_elem = run.find(qn("w:t"))
        if t_elem is None or t_elem.text is None:
            continue
        text = t_elem.text
        if anchor not in text:
            continue
        # Cursor-loop: rebuild text by walking and splicing.
        cursor = 0
        parts: list[str] = []
        local_count = 0
        while True:
            idx = text.find(anchor, cursor)
            if idx == -1:
                parts.append(text[cursor:])
                break
            parts.append(text[cursor:idx])
            parts.append(replacement)
            local_count += 1
            cursor = idx + len(anchor)
            if not anchor_all:
                parts.append(text[cursor:])
                break
        new_text = "".join(parts)
        t_elem.text = new_text
        # xml:space="preserve" when result has leading/trailing space or
        # whitespace ≠ stripped form (R1.g).
        if new_text != new_text.strip() or "  " in new_text:
            t_elem.set(
                "{http://www.w3.org/XML/1998/namespace}space", "preserve",
            )
        count += local_count
        if count > 0 and not anchor_all:
            return count
    return count
```

**Add new function `_concat_paragraph_text`:**

```python
def _concat_paragraph_text(paragraph: etree._Element) -> str:
    """Concatenate all <w:t> descendants of `paragraph`, EXCLUDING
    content under <w:del> ancestors (Q-U1 default — `<w:del>` is
    tracked-deletion text and should not match).

    <w:ins> content is INCLUDED (tracked-insertion text is live).
    """
    parts: list[str] = []
    for t_elem in paragraph.iter(qn("w:t")):
        # Walk ancestors; if any is <w:del>, skip this <w:t>.
        skip = False
        anc = t_elem.getparent()
        while anc is not None and anc is not paragraph:
            if etree.QName(anc).localname == "del":
                skip = True
                break
            anc = anc.getparent()
        if skip:
            continue
        if t_elem.text:
            parts.append(t_elem.text)
    return "".join(parts)
```

**Add new function `_find_paragraphs_containing_anchor`:**

```python
def _find_paragraphs_containing_anchor(
    part_root: etree._Element,
    anchor: str,
) -> list[etree._Element]:
    """Return all <w:p> elements whose concat-text contains `anchor`,
    in document order. Used by paragraph-level actions (D6 / B).
    """
    matches: list[etree._Element] = []
    for p in part_root.iter(qn("w:p")):
        if anchor in _concat_paragraph_text(p):
            matches.append(p)
    return matches
```

**Required module-level additions (if not already imported in 006-01a):**

```python
from lxml import etree
from docx.oxml.ns import qn
```

#### File: `skills/docx/scripts/tests/test_docx_anchor.py`

- Remove `unittest.skip` decorators from all ≥ 20 stubs.
- Fill in test bodies per the skeleton in 006-01b. Each test
  constructs a small `<w:p>` via `lxml.etree.fromstring` with the
  `xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"`
  declaration and asserts the function's return / mutation.
- **Required test classes & key assertions** (R6.d, R6.e, R11.b):
  - `TestReplaceInRun::test_no_infinite_loop_when_replacement_contains_anchor`
    — `_replace_in_run(p, "a", "aaa", anchor_all=True)` on `text="ababa"` must terminate and return 3 (replacements at positions 0/2/4); test asserts cursor advanced past replacement, not into it.
  - `TestReplaceInRun::test_xml_space_preserve_set_when_needed` — replacement that produces leading-space text sets `xml:space="preserve"`; replacement without leading/trailing space does NOT.
  - `TestReplaceInRun::test_anchor_spanning_runs_returns_zero` — paragraph with anchor split across two simple runs with identical rPr (post-merge collapses; THIS test asserts BEFORE merge: anchor split across rPr-differing runs, merge keeps them separate, count=0).
  - `TestConcatParagraphText::test_concat_includes_ins_content` — `<w:p>` with `<w:ins><w:r><w:t>foo</w:t></w:r></w:ins>bar` → `"foobar"`.
  - `TestConcatParagraphText::test_concat_excludes_del_content` — `<w:p>` with `<w:del><w:r><w:t>foo</w:t></w:r></w:del>bar` → `"bar"`.
  - `TestFindParagraphsContainingAnchor::test_concat_text_match_crosses_runs` — fixture paragraph with anchor "Article 5" split across 3 runs; function returns the paragraph.

### Component Integration

`docx_anchor.py` is now the complete shared helper module. From 006-03
onwards, `docx_replace.py` imports all six functions (3 extracted +
3 new). `docx_add_comment.py` continues to import only the original
3 extracted functions; no functional change there.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `bash skills/docx/scripts/tests/test_e2e.sh` exits 0 — the docx-1 block still passes (G4 regression) and the docx-6 block continues to SKIP (logic actions land in 006-03..07).

### Unit Tests

1. **TC-UNIT-01 (TestExtractedHelpers full green):** All 10 unit cases from `TestExtractedHelpers` pass (regression of 006-01a).
2. **TC-UNIT-02 (TestReplaceInRun green):** ≥ 7 cases pass including infinite-loop guard, xml:space:preserve set-when-needed, anchor-spanning-runs returns 0.
3. **TC-UNIT-03 (TestConcatParagraphText green):** ≥ 4 cases pass including the Q-U1 default (include `<w:ins>`, exclude `<w:del>`).
4. **TC-UNIT-04 (TestFindParagraphsContainingAnchor green):** ≥ 4 cases pass including cross-run anchor match (paragraph-level concat-text policy D6 / B).
5. **TC-UNIT-05 (LOC ceiling):** `wc -l skills/docx/scripts/docx_anchor.py` ≤ 180 (full budget reached).

### Regression Tests

- All existing docx skill tests still pass (`docx_add_comment.py` E2E suite, all other unit tests).
- All 12 `diff -q` cross-skill replication checks silent.
- `test_docx_replace.py` still entirely SKIPs (docx_replace.py module not yet present).

## Acceptance Criteria

- [ ] `docx_anchor.py` has all 6 functions (3 extracted + 3 new).
- [ ] `wc -l skills/docx/scripts/docx_anchor.py` ≤ 180.
- [ ] `test_docx_anchor.py`: ≥ 20 unit cases PASS (no SKIPs).
- [ ] `_replace_in_run` infinite-loop guard test passes.
- [ ] `_concat_paragraph_text` includes `<w:ins>`, excludes `<w:del>` (Q-U1 default lock).
- [ ] `_find_paragraphs_containing_anchor` returns matches in document order.
- [ ] G4 regression: docx-1 E2E block still passes.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

The cursor-loop pattern in `_replace_in_run` mirrors
`_wrap_anchors_in_paragraph` (docx_add_comment.py:523). The critical
invariant is `cursor = idx + len(anchor)` — using
`cursor = idx + len(replacement)` would create an infinite loop when
`replacement` contains `anchor` (TC-UNIT-02 covers this).

The R1.g `xml:space="preserve"` heuristic uses two predicates:
1. `new_text != new_text.strip()` — has leading or trailing whitespace.
2. `"  " in new_text` — consecutive spaces (Word collapses these
   without `preserve`).

If a future test reveals a case where `preserve` should be set but
isn't (e.g. `\t` or `\n` in the text), widen the predicate but keep
the test coverage.

For Q-U1 default (`<w:ins>` matched, `<w:del>` ignored), the rationale
is: tracked insertions are LIVE text (Word renders them); tracked
deletions are NOT live (Word strikes them through). An agent looking
for "the actual text" wants to match the rendered output.

RTM coverage: **R6.d, R6.e, R11.b**.
