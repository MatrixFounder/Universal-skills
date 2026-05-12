# Task 008-03: Non-media part copy + rel-target helpers (F13 + R3.5)

## Use Case Connection
- **UC-1 Alt-1b** — chart in MD source (TASK §2.1 Alt-1b).
- **UC-1** — OLE / SmartArt assets when present in MD source.

## Task Goal
Implement F13 `_copy_nonmedia_parts` and the two helper functions `_read_rel_targets` and `_apply_nonmedia_rename_to_rels` in `_relocator.py`. Adds non-media (chart, OLE, SmartArt) part copy with verbatim-default + collision-rename, plus sibling `_rels/<basename>.rels` verbatim copy (D7).

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `_read_rel_targets` (helper):**
```python
def _read_rel_targets(rels_path: Path) -> list[tuple[str, str]]:
    """Return [(Type, Target), ...] from a rels file, in document
    order. Returns [] if file missing/empty/unparseable. Used by F9
    orchestrator to pre-scan insert rels for non-media part copy."""
    if not rels_path.is_file():
        return []
    try:
        root = etree.parse(str(rels_path), _SAFE_PARSER).getroot()
    except etree.XMLSyntaxError:
        return []
    result: list[tuple[str, str]] = []
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        rtype = rel.get("Type") or ""
        target = rel.get("Target") or ""
        if rtype and target:
            result.append((rtype, target))
    return result
```

**Function `_copy_nonmedia_parts` (F13) — R3.5 sub-features:**
Full body from ARCH §12.4 F13 pseudocode (MAJ-3 fix applied). Key invariants:
- For Type ∈ `{chart, oleObject, diagramData, diagramLayout, diagramQuickStyle, diagramColors}` only (skip `image` — handled by F10; skip `hyperlink` — no part to copy).
- `_assert_safe_target(target, base_dir)` called on every Target.
- `final_target = target` default (no rename).
- If `dst.exists()`: rename to `insert_<stem><suffix>` (n=1), then `insert_<n>_<stem><suffix>` (n≥2).
- **Rename map populated ONLY when `final_target != target`** (MAJ-3 contract).
- Copy sibling `_rels/<basename>.rels` verbatim if present (D7).
- Returns `rename_map` (sparse — only collisions).

**Function `_apply_nonmedia_rename_to_rels`:**
```python
def _apply_nonmedia_rename_to_rels(
    base_rels_path: Path,
    nonmedia_rename: dict[str, str],
) -> None:
    """Rewrite Target attrs in base rels file for every entry in
    nonmedia_rename. No-op when the map is empty (the common case —
    verbatim copies are NOT in the map per MAJ-3 contract).

    Called from F9 orchestrator AFTER _merge_relationships (which
    appends rels with the ORIGINAL Target) and AFTER F13 (which may
    rename on collision). Only collision-renamed Targets are rewritten."""
    if not nonmedia_rename:
        return
    if not base_rels_path.is_file():
        return
    tree = etree.parse(str(base_rels_path), _SAFE_PARSER)
    root = tree.getroot()
    changed = False
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        old = rel.get("Target") or ""
        if old in nonmedia_rename:
            rel.set("Target", nonmedia_rename[old])
            changed = True
    if changed:
        tree.write(
            str(base_rels_path), xml_declaration=True,
            encoding="UTF-8", standalone=True,
        )
```

#### File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Class `TestCopyNonmediaParts`** — unskip and implement 5 tests:

1. `test_chart_part_and_sibling_rels_copied`:
   - Fixture: insert tree with `word/charts/chart1.xml` + `word/charts/_rels/chart1.xml.rels`; rels file in `word/_rels/document.xml.rels` has one `<Relationship Type=".../chart" Target="charts/chart1.xml" Id="rId7"/>`.
   - Call `_copy_nonmedia_parts(base_dir, insert_dir, [(chart_type, "charts/chart1.xml")])`.
   - Assert: `base/word/charts/chart1.xml` exists, byte-identical to insert. `base/word/charts/_rels/chart1.xml.rels` exists, byte-identical. Returned map is `{}` (no rename).

2. `test_ole_part_copied`:
   - Fixture: insert has `word/embeddings/oleObject1.bin`.
   - Assert: `base/word/embeddings/oleObject1.bin` exists; returned map `{}`.

3. `test_smartart_diagrams_copied`:
   - Fixture: insert has `word/diagrams/data1.xml` + `word/diagrams/layout1.xml` + `word/diagrams/quickStyle1.xml` + `word/diagrams/colors1.xml`.
   - Pass all four (Type, Target) tuples.
   - Assert: all four copied to base; returned map `{}`.

4. `test_verbatim_when_no_collision`:
   - Fixture: insert has `word/charts/chart1.xml`; base has NO chart files.
   - Assert: returned rename_map is `{}` (NOT `{"charts/chart1.xml": "charts/chart1.xml"}` — MAJ-3 contract: only collisions populate the map).

5. `test_collision_renamed_with_insert_prefix`:
   - Fixture: insert has `word/charts/chart1.xml`; base PRE-EXISTS `word/charts/chart1.xml` (a base-authored chart).
   - Assert: returned `rename_map == {"charts/chart1.xml": "charts/insert_chart1.xml"}`. `base/word/charts/insert_chart1.xml` exists and is byte-identical to insert. `base/word/charts/chart1.xml` is unchanged.
   - Add a third sub-case: base pre-exists BOTH `chart1.xml` AND `insert_chart1.xml` → rename to `insert_2_chart1.xml`.

**Class `TestApplyNonmediaRenameToRels`** — add 2 new tests (this class can be added alongside `TestCopyNonmediaParts`):

6. `test_empty_map_is_noop`:
   - Fixture: base rels with `Type=".../chart" Target="charts/chart1.xml"`.
   - Call with empty map.
   - Assert: rels file not rewritten (mtime check OR string equality).

7. `test_renames_only_listed_targets`:
   - Fixture: base rels with 3 rels (chart, image, hyperlink); map = `{"charts/chart1.xml": "charts/insert_chart1.xml"}`.
   - Call.
   - Assert: only the chart rel's Target is rewritten; image and hyperlink untouched.

**Class `TestReadRelTargets`** — add 2 new tests:

8. `test_returns_pairs_in_doc_order`:
   - Fixture: rels file with 3 entries.
   - Assert: `[(t1, T1), (t2, T2), (t3, T3)]` order matches document.

9. `test_missing_file_returns_empty`:
   - Pass nonexistent path → `[]`.

**Total new tests in this sub-task: 5 (TestCopyNonmediaParts) + 2 (TestApplyNonmediaRenameToRels) + 2 (TestReadRelTargets) = 9 tests.** Exceeds task spec floor of 5; satisfies G6.

### Component Integration
- `_actions.py` UNCHANGED. `docx_replace.py` UNCHANGED.
- `relocate_assets` orchestrator stays at stub (returns zero report). Wiring lands in 008-04.

## Test Cases

### Unit Tests
≥ 9 unskipped (5 R3.5 + 2 rels-apply + 2 read-rel-targets).

### End-to-end Tests
- **None**. The single chart E2E case (mentioned in TASK §4.3 Assumption "Acceptance: a chart inserted via --insert-after renders correctly in the output") is bundled with 008-04 image E2E.

### Regression Tests
- All 30 docx-6.5/.6 tests from 008-01a..008-02 still green.
- All 108 docx-6 existing unit tests still green.
- All 24 existing E2E cases still green.

## Acceptance Criteria
- [ ] F13 body matches ARCH §12.4 (MAJ-3 contract: rename_map populated only on `final_target != target`).
- [ ] `_read_rel_targets` returns list of (Type, Target) tuples; handles missing file gracefully.
- [ ] `_apply_nonmedia_rename_to_rels` is no-op on empty map; rewrites only listed Targets.
- [ ] Sibling `_rels/<basename>.rels` files copied verbatim (D7 / Q-A4 ratification).
- [ ] All 9 new unit tests green.
- [ ] All previous tests green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_relocator.TestCopyNonmediaParts -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestApplyNonmediaRenameToRels -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestReadRelTargets -v
./.venv/bin/python -m unittest discover -s tests
bash tests/test_e2e.sh
```

## Notes
- **LOC budget for this task:** ~70 LOC of production code (F13 ~50 + `_read_rel_targets` ~12 + `_apply_nonmedia_rename_to_rels` ~20) + ~180 LOC of tests. Running total in `_relocator.py`: ~360 LOC.
- The "verbatim then rename" pattern of F13 is identical in spirit to F10 `_copy_extra_media` but operates on chart/OLE/diagram subdirectories. The sibling-rels verbatim copy is **only** done for non-media (charts can have their own rels; images cannot).
- **DO NOT** recursively scan chart sibling `_rels/<chartN>.xml.rels` — verbatim copy is the v2 contract (D7, Q-A4 ratified).
- **DO NOT** modify `_merge_relationships` to also copy non-media parts; that's an architectural mistake (`_merge_relationships` is the rels-only writer; `_copy_nonmedia_parts` is the part-file writer; they cooperate via `nonmedia_rename` → `_apply_nonmedia_rename_to_rels`).
