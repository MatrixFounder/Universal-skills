# Task 2.03 [R1.h + M-1]: [LOGIC IMPLEMENTATION] `<o:idmap>` + `o:spid` workbook-wide scanners

## Use Case Connection
- I1.2 (Part-counter resolution).
- C1 round-1 review (idmap workbook-wide LIST vs spid per-shape).
- M-1 architecture review (`<o:idmap data>` is comma-separated list, NOT scalar).
- m-1 architecture review (spid allocator = workbook-wide max+1, NOT 1024-stride).
- RTM: R1.h.

## Task Goal
Implement the three workbook-wide scanners that drive part-counter and shape-ID allocation: `scan_idmap_used`, `scan_spid_used`, `next_part_counter`. These are pure-lxml functions (no zip I/O, no rels editing) — their inputs are `WorkbookTree` (a thin lxml-tree wrapper) and their outputs are `set[int]` or `int`. They are the foundation for tasks 2.04 (legacy write) and 2.06 (batch dedup).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `scan_idmap_used(tree_root_dir: Path) -> set[int]`:**
- Parameters: `tree_root_dir` — the unpacked tree root (i.e. the dir containing `xl/`, `[Content_Types].xml`, etc.).
- Returns: union of all integers claimed by `<o:idmap data>` across every `xl/drawings/vmlDrawing*.xml` file.
- Logic (M-1 fix — list-aware):
  1. Glob `tree_root_dir / "xl" / "drawings" / "vmlDrawing*.xml"`.
  2. For each file, parse with lxml; find `<o:idmap data="...">` (namespace `o = "urn:schemas-microsoft-com:office:office"`).
  3. Parse `data` attribute via `[int(x) for x in data_attr.split(",") if x.strip()]`.
  4. Union all into a single `set[int]`.
- Edge cases:
  - File has `<o:shapelayout>` but NO `<o:idmap>` → contributes nothing.
  - Empty `data=""` → contributes nothing (vacuous list).
  - Malformed integer → raise `MalformedVml` (exit 1) — should not happen on Excel-emitted input but guards against tampering.

**Function `scan_spid_used(tree_root_dir: Path) -> set[int]`:**
- Parameters: same.
- Returns: workbook-wide set of NNNN integers from every `<v:shape id="_x0000_sNNNN" o:spid="...">` across all VML parts.
- Logic:
  1. Glob VML drawings as above.
  2. For each `<v:shape>`, parse `id` attribute via regex `^_x0000_s(\d+)$`. If the regex fails, skip (Excel sometimes emits non-conforming shape IDs which we treat as "not in our managed range").
  3. Union into `set[int]`.

**Function `next_part_counter(tree_root_dir: Path, glob_pattern: str) -> int`:**
- Parameters:
  - `tree_root_dir`: same.
  - `glob_pattern`: e.g. `"xl/comments?.xml"`, `"xl/threadedComments?.xml"`, `"xl/drawings/vmlDrawing?.xml"`.
- Returns: next free integer counter — `max(N) + 1` where N is parsed from filenames matching the glob; `1` if no matches.
- Logic:
  1. Use `glob.glob(str(tree_root_dir / glob_pattern))` (string-glob; lxml not needed).
  2. Parse `N` from each match via regex, taking max.
  3. Return `max + 1` or `1` if empty.
- Important: The three counters (`commentsN`, `threadedComments<M>`, `vmlDrawing<K>`) are INDEPENDENT — each is its own glob.

### Component Integration
- All three scanners are called from `_allocate_new_parts(args, tree)` (a new helper that lives in the F4 region) — that helper bundles the four allocations needed before any write happens, so the workbook-wide pre-scan happens ONCE per invocation, not per-row in batch mode.

## Test Cases

### End-to-end Tests
- **TC-E2E-T-idmap-conflict:** `golden/inputs/with_legacy.xlsx` already has `<o:idmap data="1"/>` and `_x0000_s1025` in `xl/drawings/vmlDrawing1.xml`. Add a comment to a different sheet → produced workbook has a NEW `xl/drawings/vmlDrawing2.xml` with `<o:idmap data="2"/>` (or higher) and a `<v:shape id="_x0000_s1026">` (workbook-wide max+1; m-1 chosen rule). Asserted via `lxml.etree.parse` on the produced file.

### Unit Tests
Remove `skipTest` from:
- `TestPartCounter.test_counter_starts_at_1_when_empty`: `next_part_counter(empty_dir, "xl/comments?.xml") == 1`.
- `TestPartCounter.test_counter_independent_for_comments_and_vml`: dir with `xl/comments1.xml` and `xl/drawings/vmlDrawing1.xml` → next comments = 2, next vml = 2 (independent counters; both happen to equal 2 because both have one).
- `TestPartCounter.test_counter_uses_max_plus_1`: dir with `xl/comments1.xml`, `xl/comments3.xml` (gap) → next = 4 (max+1, not gap-fill).
- `TestIdmapScanner.test_scalar_data_attr`: synthetic VML with `<o:idmap data="5"/>` → `{5}`.
- `TestIdmapScanner.test_list_data_attr_returns_all_integers`: synthetic VML with `<o:idmap data="1,5,9"/>` → `{1, 5, 9}`. **(M-1 critical test.)**
- `TestIdmapScanner.test_workbook_wide_union`: dir with two VML parts, one has `data="1,3"`, other has `data="2"` → `{1, 2, 3}`.
- `TestSpidScanner.test_scans_all_vml_parts`: dir with two VML parts, shapes `_x0000_s1025` and `_x0000_s1026` → `{1025, 1026}`.
- `TestSpidScanner.test_returns_max_plus_1_baseline`: scanner returns the set; `max(scan_spid_used(d)) + 1` is what the allocator will use; assert `1027` for the above.

### Regression Tests
- All Stage-1 stub-stage tests still pass; cross-cutting tests from 2.01 stay green.

## Acceptance Criteria
- [ ] All 8 unit tests above pass.
- [ ] `T-idmap-conflict` E2E passes (with the produced-file assertions implemented inline using lxml).
- [ ] `<o:idmap data="1,5,9"/>` test is the explicit M-1 lock — must be present and named `test_list_data_attr_returns_all_integers`.
- [ ] Scanner functions are pure (no zip I/O, no rels mutation) — testable on synthetic dir trees.
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The `MalformedVml` envelope path is defensive — Excel-emitted VML always has well-formed integers in `<o:idmap data>`, but the production code needs to fail loudly rather than silently mis-allocate.
- m-1 chose "workbook-wide max+1" over Excel's 1024-stride convention (`_x0000_s1025`, `_x0000_s2049`, ...). Document this choice in `comments-and-threads.md` §3.5 (or wherever final polish lands in 2.10).
