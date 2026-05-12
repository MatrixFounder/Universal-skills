# Task 008-01a: `_relocator.py` skeleton + `RelocationReport` dataclass + Stub-First scaffolding

## Use Case Connection
- Preparatory (no UC directly). Sets up the call-sites for UC-1, UC-2, UC-3, UC-4.

## Task Goal
Create the new `_relocator.py` sibling module with ALL 13 function signatures from ARCH §12.6 implemented as stubs (returning zero/empty defaults). Create `test_docx_relocator.py` with ≥ 25 explicitly-skipped tests covering future Green paths. **Stub-First Red phase:** existing docx-6 tests must remain green; new tests are explicitly skipped, not failing.

## Changes Description

### New Files
- `skills/docx/scripts/_relocator.py` — docx-only sibling module owning all asset-relocation logic (image + numbering + content-types) for `--insert-after`. Pattern source: `docx_merge.py` (re-used by copy per Decision D3). Target LOC after Phase 1 stubs: ~150; final cap ≤ 500 LOC.
- `skills/docx/scripts/tests/test_docx_relocator.py` — Unit-test module for `_relocator.py`. Initial state: ≥ 25 explicitly-skipped tests with `@unittest.skip("stub-first; logic lands in 008-0X")` annotations covering all 13 functions and the four `RelocationReport` invariant classes.

### New File: `skills/docx/scripts/_relocator.py`

**Module docstring (top of file):**
```
"""Asset relocation for `docx_replace.py --insert-after`.

Scope:
- Image / Relationship relocator (docx-6.5): media file copy, rels
  append with rId offset, r:embed/r:link/r:id remap, content-types
  merge, chart/OLE/SmartArt part copy.
- Numbering relocator (docx-6.6): abstractNum/num offset shift,
  w:numId remap, install verbatim if base has no numbering.xml.

Pattern source: docx_merge.py (re-used BY COPY per Decision D3 —
single-insert context vs N-extras context of docx_merge).
"""
```

**Imports (Stage 0 stubs):**
```python
from __future__ import annotations
import copy
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree  # type: ignore
from docx.oxml.ns import qn  # type: ignore

from _app_errors import Md2DocxOutputInvalid

# Hardened XML parser (defense vs XXE / external entity / DTD).
_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False,
)
```

**Namespace constants (top-level):**
```python
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

_MERGEABLE_REL_TYPES = frozenset({
    f"{R_NS}/image",
    f"{R_NS}/hyperlink",
    f"{R_NS}/diagramData",
    f"{R_NS}/diagramLayout",
    f"{R_NS}/diagramQuickStyle",
    f"{R_NS}/diagramColors",
    f"{R_NS}/chart",
    f"{R_NS}/oleObject",
})

_RID_ATTRS = (
    f"{{{R_NS}}}embed",
    f"{{{R_NS}}}link",
    f"{{{R_NS}}}id",
    f"{{{R_NS}}}dm",
    f"{{{R_NS}}}lo",
    f"{{{R_NS}}}qs",
    f"{{{R_NS}}}cs",
)
```

**Dataclass:**
```python
@dataclass(frozen=True)
class RelocationReport:
    media_copied: int
    rels_appended: int
    rid_rewrites: int
    content_types_added: int
    abstractnum_added: int
    num_added: int
    numid_rewrites: int
    nonmedia_parts_copied: int
```

**13 function stubs** — copy each signature verbatim from ARCH §12.6, body = `raise NotImplementedError("stub-first; logic lands in 008-0X (see PLAN.md)")` OR `return RelocationReport(0, 0, 0, 0, 0, 0, 0, 0)` / `return {}` / `return 0` as appropriate so stubs are importable without raising on collection. Use the latter approach for unit-test collection to succeed:
1. `relocate_assets(...) -> RelocationReport` → return zero-report.
2. `_copy_extra_media(...) -> dict[str, str]` → return `{}`.
3. `_max_existing_rid(...) -> int` → return `0`.
4. `_merge_relationships(...) -> dict[str, str]` → return `{}`.
5. `_copy_nonmedia_parts(...) -> dict[str, str]` → return `{}`.
6. `_read_rel_targets(...) -> list[tuple[str, str]]` → return `[]`.
7. `_apply_nonmedia_rename_to_rels(...) -> None` → return `None`.
8. `_remap_rids_in_clones(...) -> int` → return `0`.
9. `_merge_content_types_defaults(...) -> int` → return `0`.
10. `_merge_numbering(...) -> tuple[dict[str, str], int, int]` → return `({}, 0, 0)`.
11. `_ensure_numbering_part(...) -> None` → return `None`.
12. `_remap_numid_in_clones(...) -> int` → return `0`.
13. `_assert_safe_target(...) -> None` → return `None` (NO raise yet — logic lands in 008-01b).

Each function MUST have a docstring referencing its ARCH §12.4 / §12.6 anchor (e.g. "F10 — see ARCH §12.4 F10").

### New File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Skeleton (Stage 0):**
```python
"""Unit tests for _relocator.py — see docs/PLAN.md Task 008 chain.

Initial state (008-01a): all tests are explicitly skipped. As each
sub-task lands logic for a function, the corresponding tests are
unskipped (decorator removed).
"""
import unittest
from pathlib import Path

import _relocator
from _relocator import (
    RelocationReport, relocate_assets,
    _copy_extra_media, _max_existing_rid, _merge_relationships,
    _copy_nonmedia_parts, _read_rel_targets,
    _apply_nonmedia_rename_to_rels,
    _remap_rids_in_clones, _merge_content_types_defaults,
    _merge_numbering, _ensure_numbering_part,
    _remap_numid_in_clones, _assert_safe_target,
)
```

**Required test stubs (≥ 25):**

| Class | Test methods (skipped) | Lands in |
|---|---|---|
| `TestAssertSafeTarget` | `test_relative_target_ok`, `test_absolute_path_rejected`, `test_parent_segment_rejected`, `test_drive_letter_rejected`, `test_outside_base_rejected` (5 tests) | 008-01b |
| `TestCopyExtraMedia` | `test_no_media_dir_returns_empty_map`, `test_single_file_copied_with_prefix`, `test_collision_renamed_to_counter`, `test_returns_relative_target_map` (4 tests) | 008-02 |
| `TestMaxExistingRid` | `test_empty_rels_returns_zero`, `test_single_rid_returned`, `test_gap_filled_returns_max`, `test_non_numeric_id_skipped` (4 tests) | 008-02 |
| `TestMergeRelationships` | `test_mergeable_only_appended`, `test_rid_offset_avoids_collision`, `test_image_target_rewritten_via_rename_map`, `test_external_hyperlink_skips_path_guard`, `test_returns_complete_rid_map` (5 tests) | 008-02 |
| `TestRemapRidsInClones` | `test_rewrite_embed`, `test_rewrite_link_and_id`, `test_unmapped_rid_left_alone` (3 tests) | 008-02 |
| `TestMergeContentTypesDefaults` | `test_no_op_when_no_new_extensions`, `test_appends_missing_default`, `test_case_fold_extension_check` (3 tests) | 008-02 |
| `TestCopyNonmediaParts` | `test_chart_part_and_sibling_rels_copied`, `test_ole_part_copied`, `test_smartart_diagrams_copied`, `test_verbatim_when_no_collision`, `test_collision_renamed_with_insert_prefix` (5 tests) | 008-03 |
| `TestMergeNumbering` | `test_no_insert_numbering_returns_empty`, `test_install_verbatim_when_base_has_none`, `test_offset_shift_collision_avoided`, `test_ecma_376_17_9_20_abstractnum_before_num_preserved` (4 tests) | 008-05 |
| `TestRemapNumidInClones` | `test_rewrite_w_numId`, `test_unmapped_numid_left_alone` (2 tests) | 008-05 |
| `TestRelocateAssetsIdempotent` | `test_relocator_idempotent_on_same_inputs` (1 test) | 008-07 |
| `TestRelocationReportInvariants` | `test_zero_report_no_op_invocation`, `test_rels_appended_equals_len_rid_map` (2 tests) | 008-02 + 008-07 |
| `TestRunSuccessLine` (forward-ref; lives in `test_docx_replace.py` NOT `test_docx_relocator.py`) | `test_no_annotation_when_no_relocation`, `test_annotation_when_image_relocated`, `test_annotation_when_numbering_relocated` (3 tests) | 008-07 (created there; mentioned here for traceability) |
| `TestPathTraversal` (forward-ref; lives in `test_docx_replace.py`) | `test_insert_after_rejects_parent_segment_target`, `test_insert_after_rejects_absolute_target` (2 tests) | 008-07 |
| `TestImportBoundary` | `test_relocator_does_not_import_docx_merge` (AST-walk; 1 test) | 008-01a (immediate Green) |

**Total: 38 stubbed/skip-annotated tests + 1 immediate-Green import-boundary test = 39 tests.** Exceeds TASK §7 G6 floor of 25.

### Component Integration
- `_relocator.py` is **import-only-by** `_actions.py` starting in 008-04. Until then, the module is imported by nothing except `test_docx_relocator.py`. No edits to `_actions.py`, `docx_replace.py`, `docx_anchor.py`, or `_app_errors.py` in this sub-task.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `TestImportBoundary.test_relocator_does_not_import_docx_merge` — Use `ast.parse(open("skills/docx/scripts/_relocator.py").read())` to walk the AST; assert no `ImportFrom` or `Import` node names `docx_merge`. NIT-1 regression-lock for D3.

### End-to-end Tests
- **None.** E2E tests for Task 008 are added starting in 008-04 (E1 E2E) / 008-06 (E2 E2E) / 008-07 (path-traversal E2E).

### Regression Tests
- Run `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests` — all 108 existing docx-6 unit tests MUST remain green.
- Run `cd skills/docx/scripts && bash tests/test_e2e.sh` — all 24 existing T-docx-* E2E cases MUST remain green.

## Acceptance Criteria
- [ ] `skills/docx/scripts/_relocator.py` exists, importable (`python3 -c "import _relocator"` exits 0).
- [ ] All 13 functions are present with correct signatures matching ARCH §12.6.
- [ ] `RelocationReport` dataclass exists with 8 fields (frozen).
- [ ] `_MERGEABLE_REL_TYPES` is a frozenset of 8 entries; `_RID_ATTRS` is a tuple of 7 entries.
- [ ] `_SAFE_PARSER` defined with `resolve_entities=False, no_network=True, load_dtd=False`.
- [ ] `skills/docx/scripts/tests/test_docx_relocator.py` exists with ≥ 25 stubbed tests + 1 import-boundary test.
- [ ] `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests -v` reports 1 new test green (TestImportBoundary), ≥ 25 new tests skipped.
- [ ] All 108 existing docx-6 unit tests still pass (no regression).
- [ ] All 24 existing T-docx-* E2E cases still pass (no regression).

## Verification Commands
```bash
cd skills/docx/scripts
# Stub importable + module sanity
./.venv/bin/python -c "
import _relocator
assert hasattr(_relocator, 'RelocationReport')
assert hasattr(_relocator, 'relocate_assets')
for fn in ('_copy_extra_media', '_max_existing_rid', '_merge_relationships',
          '_copy_nonmedia_parts', '_read_rel_targets',
          '_apply_nonmedia_rename_to_rels', '_remap_rids_in_clones',
          '_merge_content_types_defaults', '_merge_numbering',
          '_ensure_numbering_part', '_remap_numid_in_clones',
          '_assert_safe_target'):
    assert hasattr(_relocator, fn), fn
print('PASS')
"
# Test suite
./.venv/bin/python -m unittest discover -s tests -v
# E2E suite
bash tests/test_e2e.sh
```

## Notes
- **DO NOT** implement `_assert_safe_target` logic here. It is a security primitive that lands in 008-01b with its 5 dedicated tests. Today the stub returns `None` (no raise); the 5 path-traversal tests are skipped until 008-01b unskips them.
- **DO NOT** import `docx_merge`. The `TestImportBoundary.test_relocator_does_not_import_docx_merge` test (AST-walk) is the regression-lock for Decision D3 (re-use by copy, not by import). NIT-1.
- The 12 `diff -q` cross-skill replication checks (CLAUDE.md §2) are UNCHANGED by this task — `_relocator.py` is docx-only, not in any replicated set.
