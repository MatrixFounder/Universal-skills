# Task 008-04: `_extract_insert_paragraphs` signature change + E1 wiring + R6

## Use Case Connection
- **UC-1** — `--insert-after` with image in MD source (TASK §2.1). First end-to-end Green path for image relocation lands here.

## Task Goal
Wire the E1 image relocator into the `--insert-after` call-path. Change `_extract_insert_paragraphs` signature per ARCH §12.5 to thread `base_tree_root` and return `(clones, RelocationReport)`. Implement (partial) `relocate_assets` orchestrator covering only E1 — E2 (numbering) stays at stub until 008-05/008-06. Delete the R10.b WARNING stderr line. Rewrite the existing `T-docx-insert-after-image-warns` E2E to assert GREEN-path relocation. Add new E2E `T-docx-insert-after-image-relocated`.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `relocate_assets` — partial implementation (E1 only):**
Replace zero-report stub with E1 portion of ARCH §12.4 F9 pseudocode. Skip E2 (numbering) — leave `num_id_remap = {}`, `abstractnum_added = 0`, `num_added = 0`, `numid_rewrites = 0` until 008-05/008-06.

```python
def relocate_assets(
    insert_tree_root: Path,
    base_tree_root: Path,
    clones: list[etree._Element],
) -> RelocationReport:
    """F9 — orchestrator. As of 008-04: E1 (image/rel/chart/OLE/SmartArt)
    only; E2 (numbering) lands in 008-05/008-06."""
    base_rels_path = base_tree_root / "word" / "_rels" / "document.xml.rels"
    insert_rels_path = insert_tree_root / "word" / "_rels" / "document.xml.rels"

    # --- E1: Image / Relationship relocator ---
    media_rename = _copy_extra_media(base_tree_root, insert_tree_root)
    rid_offset = (
        _max_existing_rid(etree.parse(str(base_rels_path), _SAFE_PARSER).getroot()) + 1
        if base_rels_path.is_file() else 1
    )
    insert_rel_targets = _read_rel_targets(insert_rels_path)
    rid_map = _merge_relationships(
        base_rels_path, insert_rels_path,
        media_rename, rid_offset, base_tree_root,
    )
    nonmedia_rename = _copy_nonmedia_parts(
        base_tree_root, insert_tree_root, insert_rel_targets,
    )
    _apply_nonmedia_rename_to_rels(base_rels_path, nonmedia_rename)
    rid_rewrites = _remap_rids_in_clones(clones, rid_map)
    ct_added = _merge_content_types_defaults(
        base_tree_root / "[Content_Types].xml",
        insert_tree_root / "[Content_Types].xml",
    )
    media_copied_count = sum(
        1 for (rtype, tgt) in insert_rel_targets
        if rtype == f"{R_NS}/image"
        and (insert_tree_root / "word" / tgt).is_file()
    )
    nonmedia_count = sum(
        1 for (rtype, tgt) in insert_rel_targets
        if rtype not in (f"{R_NS}/image", f"{R_NS}/hyperlink")
        and (insert_tree_root / "word" / tgt).is_file()
    )

    # --- E2: Numbering relocator (stub — lands in 008-05/008-06) ---
    num_id_remap: dict[str, str] = {}
    abstractnum_added = 0
    num_added = 0
    numid_rewrites = 0

    return RelocationReport(
        media_copied=media_copied_count,
        rels_appended=len(rid_map),
        rid_rewrites=rid_rewrites,
        content_types_added=ct_added,
        abstractnum_added=abstractnum_added,
        num_added=num_added,
        numid_rewrites=numid_rewrites,
        nonmedia_parts_copied=nonmedia_count,
    )
```

#### File: `skills/docx/scripts/_actions.py`

**Function `_extract_insert_paragraphs` — signature change + WARNING deletion:**

Lines to replace: `_actions.py:255-312` (current body).

**OLD signature:**
```python
def _extract_insert_paragraphs(
    insert_tree_root: Path,
    *,
    base_has_numbering: bool,
) -> "list[etree._Element]":
```

**NEW signature:**
```python
def _extract_insert_paragraphs(
    insert_tree_root: Path,
    base_tree_root: Path,
) -> "tuple[list[etree._Element], RelocationReport]":
```

**NEW body:**
```python
"""Deep-clone body block children from insert tree's word/document.xml.
Strip ALL <w:sectPr> body-direct children (Q-A3 lock).

As of docx-008: runs the asset relocator BEFORE returning, so the
returned clones have rIds + numIds already remapped to base-side
values. Returns (clones, RelocationReport)."""
doc_xml = insert_tree_root / "word" / "document.xml"
if not doc_xml.is_file():
    raise Md2DocxOutputInvalid(
        "insert docx has no word/document.xml",
        code=1, error_type="Md2DocxOutputInvalid",
        details={"path": str(doc_xml)},
    )
tree = etree.parse(str(doc_xml), _SAFE_PARSER)
body = tree.find(qn("w:body"))
if body is None:
    raise Md2DocxOutputInvalid(
        "insert docx body element missing",
        code=1, error_type="Md2DocxOutputInvalid",
        details={"path": str(doc_xml)},
    )
clones: "list[etree._Element]" = []
for child in body:
    local = etree.QName(child).localname
    if local == "sectPr":
        continue  # Q-A3 strip.
    clones.append(_deep_clone(child))

# Run the asset relocator. Side-effects on base tree files; rewrites
# rid/numid attrs inside clones.
report = _relocator.relocate_assets(
    insert_tree_root, base_tree_root, clones,
)
return clones, report
```

**Imports:** add `import _relocator` at the top of `_actions.py` (alongside existing imports).

**Function `_do_insert_after` caller (in `docx_replace.py`):**

The `_extract_insert_paragraphs` + `_do_insert_after` invocations live in `docx_replace.py:_run` (NOT inside `_actions.py`). Concrete locations (verify via `grep -n "_extract_insert_paragraphs\|_do_insert_after" docx_replace.py`):
- `docx_replace.py:46-47` — imports (already in place; no edit needed).
- `docx_replace.py:~239` — `base_has_numbering = (...)` precursor computation. **DELETE** — no longer needed; relocator detects internally.
- `docx_replace.py:~264-267` — `insert_paragraphs = _extract_insert_paragraphs(insert_tree_root, base_has_numbering=...)` followed by `count = _do_insert_after(tree_root, anchor, insert_paragraphs, anchor_all=args.all, scope=scope)`.

Replace with:
  ```python
  insert_paragraphs, relocation_report = _extract_insert_paragraphs(
      insert_tree, tree_root,
  )
  count = _do_insert_after(tree_root, anchor, insert_paragraphs, ...)
  ```

  The `relocation_report` is threaded up to `_run` for stderr-line annotation (Q-A2 wiring lands in 008-07).

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

**Test `test_extract_insert_paragraphs_emits_image_warning`** — **REWRITE** as `test_extract_relocates_image`:
```python
def test_extract_relocates_image(self):
    """008-04 R10.b → GREEN. Insert tree with an image; assert
    image relocated to base, rId rewritten in clone, no WARNING."""
    # ... fixture setup ...
    captured_stderr = io.StringIO()
    with contextlib.redirect_stderr(captured_stderr):
        clones, report = _extract_insert_paragraphs(
            insert_tree_root, base_tree_root,
        )
    self.assertEqual(report.media_copied, 1)
    self.assertEqual(report.rid_rewrites, 1)
    self.assertGreaterEqual(report.rels_appended, 1)
    # No WARNING line on stderr.
    self.assertNotIn("[docx_replace] WARNING", captured_stderr.getvalue())
    # The clone's r:embed attribute points at the new base-side rId.
    blip = clones[0].find(".//{*}blip")
    embed = blip.get(f"{{{R_NS}}}embed") if blip is not None else None
    self.assertIsNotNone(embed)
    self.assertNotIn("rIdNonExistent", embed)
```

#### File: `skills/docx/scripts/tests/test_e2e.sh`

**Rewrite case `T-docx-insert-after-image-warns` (currently around line 1969):**
- Currently asserts `[docx_replace] WARNING` line on stderr + image NOT in output media. Rewrite to:
  - Assert NO `[docx_replace] WARNING` line on stderr.
  - Assert `word/media/insert_*` file exists in output.
  - Assert inserted `<w:p>` has `<a:blip r:embed=...>` pointing at a rId that exists in `word/_rels/document.xml.rels`.
  - Rename case to `T-docx-insert-after-image-relocated-warn-replacement` for traceability (keeps the lineage visible).

**Add new case `T-docx-insert-after-image-relocated`:**
- Build fixture: `insert.md` with `![demo](path/to/demo.png)` (PNG fixture from existing test fixtures or a freshly-generated 1×1 PNG).
- Run: `python3 docx_replace.py base.docx out.docx --anchor "Section 3:" --insert-after insert.md`.
- Assert exit 0.
- Unpack `out.docx`; assert:
  - `word/media/insert_demo.png` exists with byte-content identical to source.
  - `word/_rels/document.xml.rels` has a new `<Relationship Type=".../image" Target="media/insert_demo.png">`.
  - `word/document.xml` body has an inserted `<w:drawing>` whose `<a:blip r:embed="rIdN">` resolves to the new Relationship.
  - No `[docx_replace] WARNING` line on stderr.

**Total new E2E cases in this task: 1 (rewrite of T-docx-insert-after-image-warns) + 1 (new T-docx-insert-after-image-relocated) = 2.**

### Component Integration
- `docx_replace.py:_run` now threads `relocation_report` from `_extract_insert_paragraphs` return into the stderr success-line annotation site (the wiring lands in 008-07 for Q-A2 final formatting; in this sub-task the variable is captured but unused beyond the report).
- TASK §7 G1 partially landed (T-docx-insert-after-* cases continue to pass except for the rewritten one).

## Test Cases

### Unit Tests
- `test_extract_relocates_image` (rewritten from `test_extract_insert_paragraphs_emits_image_warning`).

### End-to-end Tests
1. **T-docx-insert-after-image-relocated** (NEW): asserts GREEN-path image relocation (TASK §7 G2).
2. **T-docx-insert-after-image-warns** (REWRITTEN to GREEN-path): asserts no WARNING + image relocated (TASK §7 G5).

### Regression Tests
- All other 22 T-docx-* E2E cases continue to pass unchanged (G1 partial — G3/G4 lands in 008-06).
- All existing 108 docx-6 unit tests + 39 docx-008 unit tests continue to pass.

## Acceptance Criteria
- [ ] `_extract_insert_paragraphs` signature is `(insert_tree_root, base_tree_root) -> tuple[clones, RelocationReport]`.
- [ ] R10.b WARNING stderr line is **deleted** from `_actions.py`.
- [ ] `_do_insert_after` caller threads `base_tree_root` correctly.
- [ ] `_relocator.relocate_assets` E1 branch is live; E2 branch stays at stub.
- [ ] TASK §7 G2 green (T-docx-insert-after-image-relocated).
- [ ] TASK §7 G5 partial green (T-docx-insert-after-image-warns rewritten + green).
- [ ] All 22 unchanged T-docx-* cases still green (G1 partial).
- [ ] All previous unit tests still green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_replace.TestExtractInsertParagraphs -v
bash tests/test_e2e.sh  # T-docx-insert-after-image-relocated should pass; rewritten -warns case green
```

## Notes
- **R10.b WARNING deletion:** find and remove the `print("[docx_replace] WARNING: inserted body references relationships ...", file=sys.stderr)` block in `_actions.py:296-303`. Also delete the `saw_relationship_ref` local flag and its computation loop (lines 280, 288-292) — they are dead code after the WARNING is gone.
- **R10.e WARNING:** do NOT delete in this sub-task. It belongs to 008-06.
- **R10.b regression-lock E2E rewrite:** the goal is the rewritten case asserts the OPPOSITE of what it asserted before (no WARNING, image present). Keep the case name `T-docx-insert-after-image-warns` for git-blame traceability OR rename to `T-docx-insert-after-image-warns-replacement-test` for clarity. Either is acceptable; planner has no strong preference. Whichever the developer picks, the rewritten case must be in the same git commit as the new `T-docx-insert-after-image-relocated`.
- **PNG fixture:** generate or reuse a small fixture PNG. Existing fixtures live in `skills/docx/examples/`. If a PNG isn't there, generate a 1×1 transparent PNG inline via Python (`base64.b64decode(...)`) in a `tests/fixtures/` helper — keeps fixtures hermetic and small.
- **DO NOT** wire Q-A2 success-line annotation in this sub-task — it lands in 008-07. The `relocation_report` captured from `_extract_insert_paragraphs` is currently used ONLY for the unit-test assertions.
