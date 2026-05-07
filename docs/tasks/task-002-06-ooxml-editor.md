# Task 002.6: Migrate `ooxml_editor.py` (F4 — largest move)

## Use Case Connection
- I5 — Relocate the OOXML editing core (single-file per Q1=A from ARCHITECTURE §8).

## Task Goal
Move the F4 region (lines 647–1423, ~776 LOC of OOXML scanners,
part-counter, cell-ref helpers, target/path resolution, rels/CT,
legacy comment writers, threaded comment writers) from
`xlsx_add_comment.py` to `xlsx_comment/ooxml_editor.py` as a
**single file** per ARCHITECTURE §8 Q1=A. Update the shim to
re-import the public names.

## Changes Description

### New Files
*(none — `ooxml_editor.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/ooxml_editor.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """OOXML scanners, part-counter, rels/CT, legacy/threaded writers (F4).

  Migrated from `xlsx_add_comment.py` F4 region during Task 002.

  Owns the workbook-wide invariants:
    - <o:idmap data> integers are workbook-wide unique (C1 + M-1):
        the attribute is a comma-separated LIST per ECMA-376; the
        scanner unions every integer from every <o:idmap> element
        across every xl/drawings/vmlDrawing*.xml part.
    - <v:shape o:spid> integers are workbook-wide unique (C1).
        DIFFERENT collision domain from idmap — they are TWO
        domains, conflating them is the round-1 bug C1.
    - personList rel attaches to xl/_rels/workbook.xml.rels (M6).
    - <author>/<person> dedup is case-sensitive on displayName (m5).

  Security boundary:
      _VML_PARSER is an lxml XMLParser hardened against billion-laughs
      / XXE on tampered VML (resolve_entities=False, no_network=True,
      load_dtd=False, huge_tree=False). DO NOT mutate this constructor
      — the security argument from Task 2.04 is locked verbatim here.

  Public API (re-exported from xlsx_add_comment.py shim per TASK §2.5):
      next_part_counter, scan_idmap_used, scan_spid_used,
      add_person, add_legacy_comment, add_vml_shape,
      _make_relative_target, _allocate_rid, _patch_content_types
  Private (NOT on shim, but in __all__ for sibling-module import):
      _vml_part_paths, _parse_vml, _allocate_new_parts, _Allocation,
      _column_letters_to_index, _cell_ref_to_zero_based,
      _resolve_target, _resolve_workbook_rels, _sheet_part_path,
      _sheet_rels_path, _open_or_create_rels, _find_rel_of_type,
      _patch_sheet_rels, ensure_legacy_comments_part,
      ensure_vml_drawing, _xml_serialize,
      ensure_threaded_comments_part, ensure_person_list,
      add_threaded_comment
  """
  ```
- `__all__` lists the symbols that other package modules (and the
  shim re-export contract) must reach:
  ```python
  __all__ = [
      # Scanners + part-counter
      "scan_idmap_used", "scan_spid_used", "next_part_counter",
      "_vml_part_paths", "_parse_vml",
      "_Allocation", "_allocate_new_parts",
      # Cell-ref helpers
      "_column_letters_to_index", "_cell_ref_to_zero_based",
      # Target/path resolution
      "_resolve_target", "_make_relative_target",
      "_resolve_workbook_rels", "_sheet_part_path", "_sheet_rels_path",
      # Rels + content-types
      "_open_or_create_rels", "_allocate_rid", "_find_rel_of_type",
      "_patch_sheet_rels", "_patch_content_types",
      # Legacy comments
      "ensure_legacy_comments_part", "add_legacy_comment",
      "ensure_vml_drawing", "add_vml_shape", "_xml_serialize",
      # Threaded comments
      "ensure_threaded_comments_part", "ensure_person_list",
      "add_person", "add_threaded_comment",
      # Security boundary — preserved verbatim from Task 001 (m4 from
      # plan-review). NOT a function but a module-level constant; in
      # __all__ so 002.10's smoke test + lint tools see it.
      "_VML_PARSER",
  ]
  ```
- Imports (sibling-relative + stdlib + lxml + office):
  ```python
  from __future__ import annotations
  import re
  import uuid
  from dataclasses import dataclass
  from datetime import datetime, timezone
  from pathlib import Path
  from lxml import etree  # type: ignore
  from .constants import (
      SS_NS, R_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS, THREADED_NS,
      COMMENTS_REL_TYPE, COMMENTS_CT,
      VML_REL_TYPE, VML_CT,
      THREADED_REL_TYPE, THREADED_CT,
      PERSON_REL_TYPE, PERSON_CT,
      DEFAULT_VML_ANCHOR,
  )
  from .exceptions import _AppError, MalformedVml
  ```
  *(The exact import set must reconcile with what the F4 body actually
  uses — the developer trims unused imports during the move. NOT all
  18 constants are needed here; the developer pares down based on
  what F4 actually references.)*
- Body: byte-equivalent move of the F4 region (lines 651–1422). The
  `_VML_PARSER = etree.XMLParser(...)` module-level constant moves
  verbatim — DO NOT change any kwarg.

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F4 region (lines 647–1423).
- **Insert** the re-import block (the 9 symbols on the test-compat
  surface):
  ```python
  from xlsx_comment.ooxml_editor import (  # noqa: F401
      next_part_counter, scan_idmap_used, scan_spid_used,
      add_person, add_legacy_comment, add_vml_shape,
      _make_relative_target, _allocate_rid, _patch_content_types,
  )
  ```
  Plus the **internal-only** imports needed by the remaining
  F5 + F6 regions in the shim (these are file-internal references,
  not re-exports — they need to resolve names that the post-F4-deletion
  shim still uses for orchestration):
  ```python
  # Internal-only imports — needed by F5/F6 regions still in this
  # file. NOT on the public re-export contract; will be removed when
  # F5 + F6 migrate in Tasks 002.7 / 002.9.
  from xlsx_comment.ooxml_editor import (  # noqa: F401
      _vml_part_paths, _parse_vml,
      _Allocation, _allocate_new_parts,
      _column_letters_to_index, _cell_ref_to_zero_based,
      _resolve_target, _resolve_workbook_rels,
      _sheet_part_path, _sheet_rels_path,
      _open_or_create_rels, _find_rel_of_type,
      _patch_sheet_rels,
      ensure_legacy_comments_part,
      ensure_vml_drawing,
      _xml_serialize,
      ensure_threaded_comments_part, ensure_person_list,
      add_threaded_comment,
  )
  ```
  *(This second block is **temporary** — Tasks 002.7 / 002.9 will
  remove the names that become unreferenced as F5 / F6 migrate out.
  The final state in 002.9 has only the 9-name first block.)*

### Component Integration
- `ooxml_editor.py` depends on `constants.py` + `exceptions.py`.
- F5 / F6 in the shim (still pre-migration) call into `ooxml_editor`
  symbols via the temp re-imports above.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run E2E. All 112 checks green.
- **TC-E2E-02:** Specifically: `T-idmap-conflict`, `T-batch-50`,
  `T-batch-50-with-existing-vml`, `T-thread-linkage`,
  `T-threaded-rel-attachment`, `T-merged-cell-anchor-passthrough`
  pass — these are the F4-heavy E2Es most likely to fail on a botched
  move.

### Unit Tests
- **TC-UNIT-01:** `Test*Scanner*` (`scan_idmap_used`,
  `scan_spid_used` incl. `MalformedVml` token-error path,
  `_x0000_s` regex), `Test*PartCounter*`,
  `Test*PersonId*` (`add_person` UUIDv5 stability,
  `casefold()` on `STRAẞE`) pass unchanged.

### Regression Tests
- Per per-task micro-cycle: unit + E2E green.

## Acceptance Criteria
- [ ] `xlsx_comment/ooxml_editor.py` ≤ 850 LOC (Q1=A budget).
- [ ] `_VML_PARSER` is in `ooxml_editor.py` with constructor kwargs
      byte-equivalent to the original.
- [ ] `xlsx_add_comment.py` F4 region is replaced by two re-import
      blocks (9 public + ~18 internal-temp).
- [ ] R4.b lock: `grep -nE 'from xlsx_add_comment' xlsx_comment/*.py`
      empty.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- This is the largest single move. Estimated effort: 2.5 h. Plan
  for an extended verification pass — it's wise to run unit tests
  after every ~200 LOC of moved code, not all at once.
- The F4 in-line comments include important explanations of the
  C1 + M-1 invariants and the security rationale for `_VML_PARSER`.
  Move ALL of them — they ARE the documentation.
- The session-state recent-decisions log records:
  *"_load_sheets_from_workbook silently skips <sheet> elements
  missing name attr"* — that was already moved to `cell_parser.py`
  in Task 002.4 and is unrelated to F4. Mentioned only to disambiguate.
