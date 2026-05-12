# Task 006-06: `--delete-paragraph` action (F6) — UC-3 GREEN

## Use Case Connection
- **UC-3** — Delete the paragraph containing the anchor (main scenario + Alt-1..Alt-5).
- **R3.a–R3.f** — remove from parent, concat-text match, `--all`, last-paragraph refusal, empty-cell placeholder, `<w:sectPr>` preservation.
- **R10.c, R10.d** — last-paragraph regression lock; `--all --delete-paragraph` last-paragraph guard wins.

## Task Goal

Implement F6 in `docx_replace.py`:
- `_do_delete_paragraph(tree_root, anchor, *, anchor_all) -> int` —
  walks parts; for each matched `<w:p>`, calls `_safe_remove_paragraph`.
  Without `--all`, stops after first successful deletion.
- `_safe_remove_paragraph(p, part_root) -> None` — refuses
  last-body-paragraph deletion (raises
  `LastParagraphCannotBeDeleted`); removes `p` from parent; if parent
  is `<w:tc>` and no `<w:p>` remains, inserts `etree.Element(qn("w:p"))`
  placeholder (Q-A5 short form).

Wire `_run` to dispatch when `args.delete_paragraph` is set.

At end of task: UC-3 E2E cases turn GREEN.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Add F6 `_safe_remove_paragraph`:**

```python
def _safe_remove_paragraph(
    p: etree._Element,
    part_root: etree._Element,
    *,
    anchor: str,
) -> None:
    """Remove `p` from its parent. Guards:

    1. If `p` is the last <w:p> in <w:body> of word/document.xml
       (ignoring <w:sectPr>), refuse: raise LastParagraphCannotBeDeleted.
    2. If parent is <w:tc> and removing `p` would leave the cell with
       zero <w:p> children, insert <w:p/> placeholder (Q-A5 short form,
       ECMA-376 §17.4.66).
    """
    parent = p.getparent()
    if parent is None:
        # Defensive: orphan element. Should not happen for matches from
        # _find_paragraphs_containing_anchor (which walks the tree).
        return
    # Last-paragraph guard (only applies to word/document.xml body).
    # Detect by checking if the part_root is the <w:document>'s
    # descendant pointing at <w:body>.
    body = part_root.find(qn("w:body"))
    if body is not None and parent is body:
        body_p_count = sum(
            1 for c in body
            if etree.QName(c).localname == "p"
        )
        if body_p_count <= 1:
            raise LastParagraphCannotBeDeleted(
                f"Refusing to delete the only <w:p> in <w:body> "
                f"(anchor={anchor!r}).",
                code=2, error_type="LastParagraphCannotBeDeleted",
                details={"anchor": anchor},
            )
    parent.remove(p)
    # Empty-cell placeholder (Q-A5).
    if etree.QName(parent).localname == "tc":
        remaining_p = [
            c for c in parent
            if etree.QName(c).localname == "p"
        ]
        if not remaining_p:
            parent.append(etree.Element(qn("w:p")))
```

**Add F6 `_do_delete_paragraph`:**

```python
def _do_delete_paragraph(
    tree_root: Path,
    anchor: str,
    *,
    anchor_all: bool,
) -> int:
    """Walk parts; remove every (or first) <w:p> whose concat-text
    contains `anchor`. Returns the count of paragraphs deleted.

    Iterates a snapshot of matches BEFORE mutating to avoid iterator
    invalidation when --all is set."""
    deleted = 0
    for part_path, part_root in _iter_searchable_parts(tree_root):
        matches = _find_paragraphs_containing_anchor(part_root, anchor)
        if not matches:
            continue
        # Iterate snapshot; first-match wins without --all.
        for matched_p in matches:
            try:
                _safe_remove_paragraph(matched_p, part_root, anchor=anchor)
            except LastParagraphCannotBeDeleted:
                # Re-raise to surface to _run; do NOT silently swallow.
                raise
            deleted += 1
            if not anchor_all:
                # Write this part and return.
                with part_path.open("wb") as f:
                    f.write(etree.tostring(
                        part_root, xml_declaration=True,
                        encoding="UTF-8", standalone=True,
                    ))
                return deleted
        # All matches in this part deleted; write back.
        with part_path.open("wb") as f:
            f.write(etree.tostring(
                part_root, xml_declaration=True,
                encoding="UTF-8", standalone=True,
            ))
    return deleted
```

**Wire into `_run` (delete-paragraph branch):**

```python
elif args.delete_paragraph:
    count = _do_delete_paragraph(
        tree_root, args.anchor, anchor_all=args.all,
    )
    action_summary = (
        f"deleted {count} paragraph(s) (anchor={args.anchor!r})"
    )
```

The `if count == 0: raise AnchorNotFound(...)` guard from 006-04
catches the "no matches" case. `LastParagraphCannotBeDeleted` is
caught by the top-level `except _AppError` in `main()` and surfaced as
exit 2 (already wired in 006-03).

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Un-skip and live** `TestDeleteParagraphAction` (≥ 4 cases):
  - `test_delete_body_paragraph` — fixture body has 5 paragraphs;
    anchor matches paragraph 3; after delete, body has 4 paragraphs
    (paragraph 3 removed; paragraph 4 shifts to position 3).
  - `test_delete_all_matches` — 3 paragraphs match; with `--all`, all
    3 removed; counter == 3.
  - `test_delete_last_body_paragraph_refused` — single-paragraph body;
    anchor matches that paragraph; `_do_delete_paragraph` raises
    `LastParagraphCannotBeDeleted` (R10.c lock).
  - `test_delete_table_cell_paragraph_inserts_placeholder` — fixture
    with `<w:tbl><w:tr><w:tc><w:p>DEPRECATED CLAUSE</w:p></w:tc></w:tr></w:tbl>`;
    after delete, the `<w:tc>` contains a single empty `<w:p/>`
    placeholder.
  - `test_delete_with_sectPr_at_body_tail_does_not_count_sectPr` —
    body has `<w:p>foo</w:p><w:p>bar</w:p><w:sectPr/>`; anchor "foo"
    matches; delete succeeds (body has 2 `<w:p>` children, not 1 —
    sectPr ignored in the count); body still has 1 `<w:p>` after delete
    (which is allowed); attempting to delete that last `<w:p>` raises.

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Un-SKIP UC-3 cases:
  - `T-docx-delete-paragraph` — UC-3 main scenario; anchor "DEPRECATED
    CLAUSE" in `docx_replace_body.docx` → exit 0; paragraph count -1.
  - `T-docx-delete-paragraph-table-cell-placeholder` — fixture with
    table cell containing the anchor → exit 0; cell has `<w:p/>`
    placeholder.
  - `T-docx-delete-paragraph-last-body-refused` — single-paragraph
    body → exit 2 `LastParagraphCannotBeDeleted` (R10.c).
  - `T-docx-delete-paragraph-all-common-word` — fixture where anchor
    "the" matches every paragraph; with `--all --delete-paragraph` →
    exit 2 `LastParagraphCannotBeDeleted` triggered at some point in
    the loop (last-paragraph guard wins, R10.d). Output file is NOT
    written (since pack() is never reached).

### Component Integration

`_do_delete_paragraph` is independent of `_do_insert_after` (they
share `_iter_searchable_parts` and `_find_paragraphs_containing_anchor`
but operate on different action paths). No 006-05 dependency.

The `LastParagraphCannotBeDeleted` exception propagates from
`_safe_remove_paragraph` up through `_do_delete_paragraph` up to
`_run`, where the top-level `except _AppError` catch (from 006-03)
calls `report_error` with exit code 2.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-delete-paragraph):** UC-3 main. Exit 0; paragraph count -1.
2. **TC-E2E-02 (T-docx-delete-paragraph-table-cell-placeholder):** Cell paragraph removed; `<w:p/>` placeholder present.
3. **TC-E2E-03 (T-docx-delete-paragraph-last-body-refused):** Single-paragraph body → exit 2 (R10.c).
4. **TC-E2E-04 (T-docx-delete-paragraph-all-common-word):** `--all` on common word → exit 2 last-paragraph guard (R10.d).

### Unit Tests

1. **TC-UNIT-01..05 (TestDeleteParagraphAction):** 5 cases above pass.

### Regression Tests

- All G4 (docx-1) + previous docx-6 (006-02..05) tests still green.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria

- [ ] `_safe_remove_paragraph` ignores `<w:sectPr>` when counting body paragraphs (R3.f).
- [ ] Empty-cell placeholder uses `etree.Element(qn("w:p"))` (short form, Q-A5).
- [ ] Last-paragraph refusal raises `LastParagraphCannotBeDeleted` with `details["anchor"]` (R3.d, R10.c).
- [ ] `--all --delete-paragraph` on common word trips the guard mid-loop (R10.d).
- [ ] UC-3 E2E cases (4 listed above) pass.
- [ ] `TestDeleteParagraphAction` (≥ 5 cases) pass.
- [ ] `wc -l skills/docx/scripts/docx_replace.py` ≤ 570 (F6 ~ 70 LOC; total ~ 560 of 600 budget — still within ceiling).
- [ ] G4 regression: docx-1 E2E block still passes.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

The "match snapshot" pattern is important for `--all`:
`_find_paragraphs_containing_anchor` returns a list of `<w:p>` elements
captured BEFORE any mutation. Iterating this list and calling
`parent.remove(p)` is safe; iterating `part_root.iter(qn("w:p"))` and
mutating in the loop would invalidate the iterator. The unit test
`test_delete_all_matches` indirectly verifies this — if iterator
invalidation occurred, the third match would be missed.

For T-docx-delete-paragraph-all-common-word, the fixture is the same
`docx_replace_body.docx` (every paragraph contains "the" as a word).
The expected behaviour: the first match (paragraph 1) is removed
without writing to disk yet; the second match (paragraph 2) is
removed; ... at some iteration, the body has 1 paragraph left, the
next deletion triggers `LastParagraphCannotBeDeleted`. The output
file is NOT written. R10.d locks this behaviour.

For T-docx-delete-paragraph-table-cell-placeholder, the fixture body
needs a real `<w:tbl>` with a `<w:tc>` containing only one `<w:p>`
with the anchor. Generate via markdown:
```
| only column |
|-------------|
| DEPRECATED CLAUSE: this is the only paragraph in the cell |
```
The resulting cell has a single `<w:p>`. After delete, verify
`<w:tc>` has exactly one `<w:p>` child (the placeholder) and that the
serialised XML matches `<w:p/>` (no children).

RTM coverage: **R3.a, R3.b, R3.c, R3.d, R3.e, R3.f, R10.c (lock
test here; regression suite in 006-08), R10.d (lock test here;
regression suite in 006-08)**.
