# Task 008-02: Image / Relationship relocator core (F10 + F11 + F12 + R4 + R5)

## Use Case Connection
- **UC-1** — `--insert-after` with an image in the markdown source (TASK §2.1).
- **UC-3** — image + numbering integration (E1 half lands here).

## Task Goal
Implement the E1 (docx-6.5) image / relationship relocator helpers in `_relocator.py`: `_copy_extra_media` (F10), `_max_existing_rid` (F11), `_merge_relationships` (F12, with `_assert_safe_target` invocation), `_remap_rids_in_clones`, `_merge_content_types_defaults`. Land ≥ 15 unit tests for these (R1–R5 sub-features).

This task does **NOT** wire the relocator into `_actions.py` — that happens in 008-04. After this task, the helpers are tested in isolation but unused.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `_copy_extra_media` (F10) — R1 sub-features:**
Replace stub with ARCH §12.4 F10 algorithm:
```python
def _copy_extra_media(
    base_dir: Path, insert_dir: Path,
) -> dict[str, str]:
    """F10 — Copy insert/word/media/* into base/word/media/ with fixed
    `insert_` prefix. Returns {old_relative_target: new_relative_target}
    map; entries appear ONLY for files that were renamed due to collision
    OR for verbatim copies (every copied file maps its source name to
    its dest name; if dest == src + 'insert_' prefix, the map records
    that mapping)."""
    src_dir = insert_dir / "word" / "media"
    if not src_dir.is_dir():
        return {}
    dst_dir = base_dir / "word" / "media"
    dst_dir.mkdir(parents=True, exist_ok=True)
    rename_map: dict[str, str] = {}
    for src in sorted(src_dir.iterdir()):
        if not src.is_file():
            continue
        new_name = f"insert_{src.name}"
        n = 1
        while (dst_dir / new_name).exists():
            n += 1
            new_name = f"insert_{n}_{src.name}"
        dst = dst_dir / new_name
        dst.write_bytes(src.read_bytes())
        rename_map[f"media/{src.name}"] = f"media/{new_name}"
    return rename_map
```

**Function `_max_existing_rid` (F11) — R2 sub-features:**
```python
def _max_existing_rid(rels_root: etree._Element) -> int:
    """F11 — Return the largest numeric N in any `Id="rId<N>"` in
    rels_root. Returns 0 if no numeric rIds are found."""
    biggest = 0
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        rid = rel.get("Id") or ""
        m = re.match(r"rId(\d+)$", rid)
        if m:
            biggest = max(biggest, int(m.group(1)))
    return biggest
```

**Function `_merge_relationships` (F12) — R3 sub-features (including R3.(g) path guard):**
Full body from ARCH §12.4 F12 pseudocode. Key points:
- Parse insert + base rels with `_SAFE_PARSER`.
- For each insert rel of Type ∈ `_MERGEABLE_REL_TYPES`:
  - Read `TargetMode` first. If `TargetMode != "External"`, call `_assert_safe_target(target, base_tree_root)`.
  - Allocate fresh `rId{next_n}` with collision-skip against `existing_ids` set.
  - **Populate `rid_map[old_id] = new_id`** for EVERY mergeable rel (MAJ-2 fix).
  - Create new `<Relationship>` SubElement on base root; set `Id`, `Type`, `Target` (rewritten via `media_rename` ONLY when Type is image AND target is in map), `TargetMode` if present.
- Write base rels file. Return `rid_map`.

**Function `_remap_rids_in_clones` — R4 sub-features:**
```python
def _remap_rids_in_clones(
    clones: list[etree._Element], rid_map: dict[str, str],
) -> int:
    """R4 — Walk each clone subtree, rewrite r:embed/r:link/r:id/
    r:dm/r:lo/r:qs/r:cs attrs via rid_map. Returns rewrite count.
    Unmapped rIds are left alone (defensive — mirror docx_merge)."""
    if not rid_map:
        return 0
    count = 0
    for clone in clones:
        for el in clone.iter():
            for attr in _RID_ATTRS:
                val = el.get(attr)
                if val and val in rid_map:
                    el.set(attr, rid_map[val])
                    count += 1
    return count
```

**Function `_merge_content_types_defaults` — R5 sub-features:**
```python
def _merge_content_types_defaults(
    base_ct_path: Path, insert_ct_path: Path,
) -> int:
    """R5 — Copy <Default Extension> entries from insert into base
    where the extension (case-fold compared) does not already exist.
    Persist base CT file only if any entries were appended.
    Returns count of appended entries."""
    if not base_ct_path.is_file() or not insert_ct_path.is_file():
        return 0
    base_tree = etree.parse(str(base_ct_path), _SAFE_PARSER)
    insert_tree = etree.parse(str(insert_ct_path), _SAFE_PARSER)
    base_root = base_tree.getroot()
    insert_root = insert_tree.getroot()
    base_exts = {
        d.get("Extension", "").lower()
        for d in base_root.findall(f"{{{CT_NS}}}Default")
    }
    appended = 0
    for d in insert_root.findall(f"{{{CT_NS}}}Default"):
        ext = (d.get("Extension") or "").lower()
        if ext and ext not in base_exts:
            new = etree.SubElement(base_root, f"{{{CT_NS}}}Default")
            new.set("Extension", d.get("Extension") or ext)
            new.set("ContentType", d.get("ContentType") or "")
            base_exts.add(ext)
            appended += 1
    if appended:
        base_tree.write(
            str(base_ct_path), xml_declaration=True,
            encoding="UTF-8", standalone=True,
        )
    return appended
```

#### File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Unskip and implement ≥ 15 tests across these classes:**

1. **`TestCopyExtraMedia`** (4 tests):
   - `test_no_media_dir_returns_empty_map` — `insert/word/media/` doesn't exist → `{}` returned, no error.
   - `test_single_file_copied_with_prefix` — `insert/word/media/img.png` → copied to `base/word/media/insert_img.png`; map = `{"media/img.png": "media/insert_img.png"}`; byte-identical content.
   - `test_collision_renamed_to_counter` — pre-create `base/word/media/insert_img.png`; copy → `insert_2_img.png`; map = `{"media/img.png": "media/insert_2_img.png"}`. Test triple-collision → `insert_3_img.png`.
   - `test_returns_relative_target_map` — keys / values have `media/` prefix (no full path).

2. **`TestMaxExistingRid`** (4 tests):
   - `test_empty_rels_returns_zero` — empty Relationships root → 0.
   - `test_single_rid_returned` — one `rId5` → 5.
   - `test_gap_filled_returns_max` — `rId1, rId7, rId3` → 7.
   - `test_non_numeric_id_skipped` — `rIdABC` ignored; numeric ones counted.

3. **`TestMergeRelationships`** (5 tests):
   - `test_mergeable_only_appended` — insert has 1 image + 1 styles rel; base gains image rel only.
   - `test_rid_offset_avoids_collision` — base has `rId1..rId5`; insert image gets `rId6`.
   - `test_image_target_rewritten_via_rename_map` — `media_rename = {"media/img.png": "media/insert_img.png"}`; appended rel has Target=`media/insert_img.png`.
   - `test_external_hyperlink_skips_path_guard` — `TargetMode="External"` URL `http://evil.com` does NOT raise from `_assert_safe_target`.
   - `test_returns_complete_rid_map` — every mergeable rel from insert appears in `rid_map` (assert keys match insert's mergeable-rel Id set).

4. **`TestRemapRidsInClones`** (3 tests):
   - `test_rewrite_embed` — clone with `<a:blip r:embed="rId7"/>`; `rid_map={"rId7": "rId12"}` → attr rewritten to `rId12`; return count = 1.
   - `test_rewrite_link_and_id` — clone with both `r:link` and `r:id`; mapped values rewritten.
   - `test_unmapped_rid_left_alone` — clone with `r:embed="rId99"`; map empty → no rewrite; count = 0.

5. **`TestMergeContentTypesDefaults`** (3 tests):
   - `test_no_op_when_no_new_extensions` — base + insert both have `<Default Extension="png">` → 0 appended; mtime unchanged.
   - `test_appends_missing_default` — base has png only; insert has png + jpeg → 1 appended (jpeg).
   - `test_case_fold_extension_check` — base has `PNG`; insert has `png` → 0 appended (case-fold match).

6. **`TestRelocationReportInvariants`** (1 test for this sub-task):
   - `test_zero_report_no_op_invocation` — call `relocate_assets` with empty insert tree → returns `RelocationReport(0,0,0,0,0,0,0,0)` (NOTE: still requires `relocate_assets` stub to be present; not yet using F10-F12 because orchestrator wiring is part of 008-04. This test asserts the **stub** continues to return zeros — gating that the orchestrator stub is unchanged here).

**Test fixtures:** create helper `_make_rels_tree(rels: list[tuple[str, str, str]]) -> Path` that writes a temporary `word/_rels/document.xml.rels` with the given `(Id, Type, Target)` tuples — reusable across tests.

### Component Integration
- `_actions.py` is UNCHANGED.
- `docx_replace.py` is UNCHANGED.
- `relocate_assets` orchestrator stays at stub (returns zero report).

## Test Cases

### Unit Tests (≥ 15 unskipped in this task)
See above section.

### End-to-end Tests
- **None** in this sub-task. E1 E2E lands in 008-04 after wiring.

### Regression Tests
- All previous unit tests green.
- All 24 existing E2E cases green.

## Acceptance Criteria
- [ ] F10–F12 + `_remap_rids_in_clones` + `_merge_content_types_defaults` bodies match ARCH §12.4 / §12.6.
- [ ] `_merge_relationships` calls `_assert_safe_target` for every non-External rel Target before append.
- [ ] `_merge_relationships` populates `rid_map[old_id] = new_id` for EVERY mergeable rel (MAJ-2 contract).
- [ ] ≥ 15 unit tests unskipped and green across the 5 test classes.
- [ ] `test_relocator_does_not_import_docx_merge` AST-walk test still green (D3 lock).
- [ ] All previous tests still green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_relocator.TestCopyExtraMedia -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestMaxExistingRid -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestMergeRelationships -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestRemapRidsInClones -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestMergeContentTypesDefaults -v
./.venv/bin/python -m unittest discover -s tests
bash tests/test_e2e.sh
```

## Notes
- **LOC budget for this task:** ~140 LOC of production code + ~250 LOC of tests. Running total in `_relocator.py` after this task: ~290 LOC (well within the 500 LOC cap).
- The `_assert_safe_target` invocation in `_merge_relationships` is the FIRST live caller. Until this task, the function exists with logic (from 008-01b) but is unused.
- The 5 `TestAssertSafeTarget` tests from 008-01b remain green here (regression). Together with the 15 new tests + 1 import-boundary + 5 already-green = **21 tests green for `_relocator.py`** at end of this task.
- **DO NOT** modify `_actions.py` or `docx_replace.py`. The wiring lands in 008-04.
