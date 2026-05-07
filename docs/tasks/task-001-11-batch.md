# Task 2.06 [R4]: [LOGIC IMPLEMENTATION] Batch mode (flat-array + xlsx-7 envelope auto-detect + cap + dedup)

## Use Case Connection
- I2.1 (Batch shape auto-detection).
- I2.2 (Envelope-mode field mapping).
- I2.3 (Batch dedup & no-collision guarantees).
- m2 / m-4 (8 MiB pre-parse cap with `read(8 * MiB + 1)` boundary).
- RTM: R4.

## Task Goal
Implement `load_batch` and `batch_main` so the script can absorb a JSON file (or stdin) of comments and write all of them in a single open/save cycle without rId / shape-ID / `o:idmap` collisions. Two input shapes: flat-array and xlsx-7 envelope (auto-detected). 8 MiB pre-parse cap.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `load_batch(path_or_dash, default_author, default_threaded) -> list[BatchRow]`:**
- `BatchRow` is a `@dataclass(frozen=True)` with fields `cell, text, author, initials, threaded`.
- Logic:
  1. **Pre-parse size cap (m2/m-4):**
     - If `path_or_dash != "-"`: `if Path(path_or_dash).stat().st_size > 8 * 1024 * 1024: raise BatchTooLarge`.
     - If `path_or_dash == "-"`: `data = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)`; `if len(data) > 8 * 1024 * 1024: raise BatchTooLarge`.
  2. Parse via `json.loads(data)` (or `Path(...).read_text()` then loads).
  3. **Shape detection (I2.1):**
     - `isinstance(root, list)` → flat-array shape; iterate items.
     - `isinstance(root, dict) and {"ok", "summary", "findings"} <= root.keys()` → xlsx-7 envelope; iterate `root["findings"]`.
     - Else → raise `InvalidBatchInput`.
  4. **Flat-array mapping:** each item must have keys `{cell, text, author}`; optional `initials, threaded`. Missing keys → `InvalidBatchInput`.
  5. **Envelope mapping (I2.2):**
     - `default_author` REQUIRED (else `MissingDefaultAuthor`).
     - For each finding: `cell ← finding["cell"]`, `text ← finding["message"]`, `author ← default_author`, `initials ← <derived from default_author by first letter of each whitespace-token>`, `threaded ← default_threaded`.
     - If `finding["row"] is None` → SKIP, increment `skipped_grouped` counter (emit info to stderr at end).
  6. Return `list[BatchRow]`.

**Function `batch_main(args, tree_root_dir, all_sheets) -> int`:**
- Logic:
  1. Load batch rows via `load_batch(args.batch, args.default_author, args.default_threaded)`.
  2. Pre-scan ONCE (not per row): `idmap_used = scan_idmap_used(tree)`, `spid_used = scan_spid_used(tree)`.
  3. Track per-sheet `comments_root` and `vml_root` via a memoization dict — opening each only on first use.
  4. For each row:
     a. Resolve sheet/cell via 2.02.
     b. Q2: `text.strip() != ""` else `EmptyCommentBody` (with row index in `details`).
     c. Apply merged-cell policy (defer to 2.07's `resolve_merged_target`); if it raises, propagate (or re-raise inside batch with context).
     d. Get-or-create comments part for that sheet; `add_legacy_comment(...)`.
     e. Get-or-create VML drawing for that sheet; allocate fresh `idmap_data` from `idmap_used` (and update the set incrementally so subsequent rows see the new value); allocate fresh `spid` similarly.
     f. If `row.threaded`: `add_person + add_threaded_comment` (Q7 fidelity).
  5. Pack and return.
- **Important — incremental allocator:** after each row, ADD the freshly-chosen `idmap_data`/`spid` to the local `idmap_used`/`spid_used` sets so the next row's allocator sees them. Without this, a 50-row batch would allocate the same `spid` 50 times.

### Component Integration
- Re-uses 2.02 cell parser, 2.03 scanners + counters, 2.04 legacy helpers, 2.05 threaded helpers, 2.07 merged resolver (still stubbed in this task — use the resolver as a black-box; 2.07 lands the real implementation).

## Test Cases

### End-to-end Tests
- **TC-E2E-T-batch-50:** Generate a synthetic 50-row flat-array batch in the test (Python heredoc) → run xlsx_add_comment.py → verify produced workbook has 50 `<comment>` elements across 3 sheets, no two `<v:shape>` share `o:spid`, no two VML parts share an `<o:idmap data>` value (parse all VML parts and union — no duplicates).
- **TC-E2E-T-batch-50-with-existing-vml:** Same but starting from `with_legacy.xlsx` (has `<o:idmap data="1"/>` and `_x0000_s1025`) → produced workbook keeps existing values intact and new ones use disjoint integers.
- **TC-E2E-T-BatchTooLarge:** `truncate -s 9000000 big.json` → run with `--batch big.json` → exit 2 `BatchTooLarge`, `details.size_bytes` populated.
- **TC-E2E-envelope-mode:** Run `xlsx_check_rules.py --json` against a fixture (when xlsx-7 lands; for now use a hand-authored envelope file in `examples/`) → pipe to `xlsx_add_comment.py --batch - --default-author "Validator"` → workbook gains exactly N comments where N = `findings | filter(row != null) | count`.
- **TC-E2E-skipped-grouped:** Envelope with one `findings[i]` having `row: null` → skipped, info note to stderr `"skipped 1 group-finding"`.
- **TC-E2E-MX-A:** `--cell A5 --batch x.json` → `UsageError` (already covered in 2.01; cross-link).

### Unit Tests
- Remove `skipTest` from:
  - `TestBatchLoader.test_flat_array_shape`: `load_batch(path_to_3row_array, ...)` → 3 BatchRow objects with correct fields.
  - `TestBatchLoader.test_envelope_shape`: load envelope JSON → BatchRow list, fields hydrated from findings.
  - `TestBatchLoader.test_envelope_missing_findings_key`: dict without `findings` → `InvalidBatchInput`.
  - `TestBatchLoader.test_envelope_skips_group_findings_with_row_null`: envelope with 3 findings, one with `row: null` → returned list has 2 BatchRow; `skipped_grouped == 1`.
  - `TestBatchLoader.test_size_cap_pre_parse`: write a 9 MiB file → `BatchTooLarge` raised; `Path.stat().st_size` measured (use `monkeypatch.setattr` or just observe the raise without parse).

### Regression Tests
- 2.01–2.05 tests stay green.

## Acceptance Criteria
- [ ] 5 TC-E2E pass (TC-E2E-MX-A is regression from 2.01).
- [ ] 5 unit tests in `TestBatchLoader` pass.
- [ ] m-4 boundary: exactly-8-MiB file is accepted; 8 MiB + 1 byte rejected.
- [ ] Incremental allocator verified by `T-batch-50` no-collision assertion.
- [ ] `office/validate.py` exits 0 on every produced batch output.
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The "single open/save cycle" requirement (TASK §2 R4 + I2.3 step 3) is the perf-driver. Per-row repack would be ~50× slower on `T-batch-50`.
- `examples/comments-batch.json` from 1.05 should also be exercised in this task as a sanity-check (small fixture round-trip).
- The merged-cell-target policy is delegated to 2.07; this task may pass-through any `MergedCellTarget` exception from the resolver (which lands real implementation in 2.07). Until 2.07, the merged-cell ACs in batch mode remain on stubs.
