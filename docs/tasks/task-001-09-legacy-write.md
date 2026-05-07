# Task 2.04 [R1]: [LOGIC IMPLEMENTATION] Legacy comment write path

## Use Case Connection
- I1.3 (Legacy comment XML write path).
- m-3 (Default Extension="vml" idempotency refinement).
- m5 (case-sensitive `<authors>` dedup).
- Q2 (Empty-text rejection — `EmptyCommentBody` exit 2).
- RTM: R1 main path.

## Task Goal
Replace stubs `ensure_legacy_comments_part`, `add_legacy_comment`, `ensure_vml_drawing`, `add_vml_shape` with real lxml implementations. Wire them into a single-cell `single_cell_main(args, tree)` flow that, when `--no-threaded` (or default) is selected, writes one legacy comment + one VML shape and patches all rels + Content_Types overrides idempotently.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `ensure_legacy_comments_part(tree_root, sheet_name) -> tuple[Path, etree._Element]`:**
- Returns `(path, root_element)` for the comments part bound to `sheet_name`.
- Logic:
  1. Inspect `xl/_rels/sheet<S>.xml.rels` (where S is sheet's 1-based index from `xl/workbook.xml`) for a `Relationship` of type `http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments`. If present → load and return that part path.
  2. Else, allocate `N = next_part_counter(tree_root, "xl/comments?.xml")`; create `xl/commentsN.xml` with empty `<comments xmlns="..."><authors/><commentList/></comments>`; add the rel; add `<Override>` to `[Content_Types].xml`.
- Returns the parsed root element of the comments part.

**Function `add_legacy_comment(comments_root, ref, author, text) -> None`:**
- Logic:
  1. Locate `<authors>`. Iterate children; if any `<author>` text equals `author` (CASE-SENSITIVE — m5), reuse its position as `authorId`. Else append new `<author>{author}</author>` and use the new position.
  2. Append `<comment ref="A5" authorId="N"><text><r><t xml:space="preserve">{text}</t></r></text></comment>` to `<commentList>`.
- **Q2 enforcement:** caller `single_cell_main` checks `text.strip() == ""` → raise `EmptyCommentBody` (exit 2). The helper itself trusts pre-validation.

**Function `ensure_vml_drawing(tree_root, sheet_name, idmap_used: set[int]) -> tuple[Path, etree._Element, int]`:**
- Returns `(path, root_element, idmap_data_value)`.
- Logic:
  1. Inspect sheet rels for an existing `vmlDrawing` rel (type `...vmlDrawing`). If present → load existing part, return its existing `<o:idmap data>` value.
  2. Else allocate `K = next_part_counter(tree_root, "xl/drawings/vmlDrawing?.xml")`; choose `idmap_data = max(idmap_used) + 1` if `idmap_used` non-empty else `1`. Create `xl/drawings/vmlDrawingK.xml` with the standard root (xmlns:v, xmlns:o, xmlns:x; `<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="{idmap_data}"/></o:shapelayout>`; standard `<v:shapetype id="_x0000_t202">`).
  3. Add rel to sheet rels; add Override to `[Content_Types].xml`.
  4. **m-3 idempotency:** if `[Content_Types].xml` already has `<Default Extension="vml">`, do NOT add a per-part Override (would be redundant); just register the rel.

**Function `add_vml_shape(vml_root, ref, spid, sheet_name, sheet_index) -> None`:**
- Logic:
  1. Append `<v:shape id="_x0000_s{spid}" o:spid="_x0000_s{spid}" type="#_x0000_t202" style="..."><v:fill .../><v:shadow .../><v:path .../><v:textbox .../><x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/><x:Anchor>...</x:Anchor><x:Row>{row-1}</x:Row><x:Column>{col-1}</x:Column></x:ClientData></v:shape>`.
  2. Default anchor (R9.c — honest scope): use `<x:Anchor>3, 15, 0, 5, 5, 31, 4, 8</x:Anchor>` (Excel's default offsets for a comment one column to the right and slightly below the target cell).
  3. `<x:Row>` and `<x:Column>` are 0-based; converted from `ref` via the cell-parser regex.

**Function `_patch_content_types(content_types_root, override_path, override_content_type) -> None`:**
- Idempotent: skip if Override for `override_path` already present.

**Function `_patch_sheet_rels(sheet_rels_root, target_part_path, rel_type) -> str`:**
- Idempotent: returns existing rId if a rel already targets the same path; else allocates new `rIdN+1`.

**Function `single_cell_main(args, tree_root_dir, all_sheets) -> int`:**
- The orchestrator for `--cell` mode (legacy-only path, since this task is `--no-threaded` default; threaded path lands in 2.05).
- Logic:
  1. Pre-validate `args.text.strip() != ""` else `EmptyCommentBody`.
  2. Resolve sheet/cell via 2.02 helpers.
  3. Pre-scan: `idmap_used = scan_idmap_used(tree)`, `spid_used = scan_spid_used(tree)`.
  4. `comments_root = ensure_legacy_comments_part(tree, sheet_name)`.
  5. `add_legacy_comment(comments_root, ref, args.author, args.text)`.
  6. `vml_path, vml_root, idmap_value = ensure_vml_drawing(tree, sheet_name, idmap_used)`.
  7. `spid = max(spid_used) + 1 if spid_used else 1025` (matches Excel baseline of 1025).
  8. `add_vml_shape(vml_root, ref, spid, sheet_name, sheet_index)`.
  9. Serialise modified parts back to disk (lxml `tree.write` with `xml_declaration=True, encoding="UTF-8", standalone=True`).
  10. Pack via `office.pack(tree_root_dir, args.output)`.
  11. Return 0.

### Component Integration
- This task FINISHES the `--no-threaded` (default) single-cell happy path. Threaded mode is layered on top in 2.05.
- Pack/unpack via existing `office/` module — NO edits there.

## Test Cases

### End-to-end Tests
- **TC-E2E-T-clean-no-comments:** `clean.xlsx` + `--cell A5 --author "Q" --text "msg"` → produced file has `xl/comments1.xml` with author "Q" + comment ref="A5"; `xl/drawings/vmlDrawing1.xml` with `<o:idmap data="1"/>` and `<v:shape o:spid="_x0000_s1025">`; `[Content_Types].xml` has both Overrides; `xl/_rels/sheet1.xml.rels` has both rels.
- **TC-E2E-T-existing-legacy-preserve:** `with_legacy.xlsx` (2 pre-existing comments) + add 3rd → `<commentList>` has exactly 3 `<comment>` children; original 2 byte-equivalent (XML diff via c14n).
- **TC-E2E-T-multi-sheet:** `multi_sheet.xlsx` + `--cell Sheet2!B5` → `xl/_rels/sheet2.xml.rels` has the comments rel; `xl/comments1.xml` has the new comment (NOT `comments2.xml` — N is part-counter, not sheet-index).
- **TC-E2E-T-EmptyCommentBody:** `... --cell A5 --author Q --text ""` → exit 2 `EmptyCommentBody` envelope.

### Unit Tests
- Remove `skipTest` from:
  - `TestAuthorsDedup.test_case_sensitive_identity`: insert author "Alice" twice → only one `<author>` element; insert "alice" (lowercase) → second `<author>` (case-sensitive).
  - One new test (add to module): `TestVmlAnchor.test_default_anchor_offsets` asserts the produced `<x:Anchor>` matches `"3, 15, 0, 5, 5, 31, 4, 8"` (R9.c lock).
  - `TestContentTypesOverride.test_idempotent_skip`: call `_patch_content_types` twice with same args → only one Override emitted.
  - `TestContentTypesOverride.test_default_extension_skips_per_part_override` (m-3): when Default `Extension="vml"` is present, per-part Override for VML is NOT added.

### Regression Tests
- Cross-cutting tests from 2.01 stay green.
- All Stage-1 stub assertions still pass.

## Acceptance Criteria
- [ ] 4 TC-E2E above pass.
- [ ] 4 unit tests above pass.
- [ ] `office/validate.py` exits 0 on every produced file.
- [ ] m-3 idempotency rule honoured: no duplicate Override or Default-vs-Override conflict.
- [ ] m5 case-sensitive author dedup verified.
- [ ] Q2 `EmptyCommentBody` envelope on `--text ""` and `--text "   "`.
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The default `<x:Anchor>` value `"3, 15, 0, 5, 5, 31, 4, 8"` is the standard Excel-generated offset (column +3 right, row +15 below — verified by inspecting Excel-365 output). Matches R9.c "default VML anchor only — no custom offsets".
- The author-dedup test's `Alice` vs `alice` case is the canonical edge case from the m5 review note.
