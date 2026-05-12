# Task 008-05: Numbering relocator core (F14 + F15 + R9–R13)

## Use Case Connection
- **UC-2** — `--insert-after` with numbered/bulleted list in MD source (TASK §2.2).
- **UC-3** — image + list integration (E2 half lands here; full integration in 008-06).

## Task Goal
Implement the E2 (docx-6.6) numbering relocator helpers in `_relocator.py`: `_merge_numbering` (F14), `_remap_numid_in_clones` (F15), `_ensure_numbering_part`. Preserve ECMA-376 §17.9.20 abstractNum-before-num element ordering — this is the load-bearing trap from `docx_merge.py:388-433` (iter-2.3). Land ≥ 10 unit tests, including the explicit ECMA ordering regression-lock.

This task does **NOT** wire the numbering relocator into `relocate_assets` — that happens in 008-06. After this task, the E2 helpers are tested in isolation; `relocate_assets` still keeps E2 stubbed.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `_merge_numbering` (F14) — R9 + R10 + R11 + R12 sub-features:**

Direct port of `docx_merge.py:332-466`, with these key adjustments:
- Insert source path: `insert_tree_root / "word/numbering.xml"`.
- Base destination: `base_tree_root / "word/numbering.xml"`.
- If insert has no `numbering.xml` OR insert numbering is empty → return `({}, 0, 0)`.
- If base has no `numbering.xml`:
  - Copy `insert/word/numbering.xml` → `base/word/numbering.xml` verbatim.
  - Call `_ensure_numbering_part(base_tree_root)` to add Content-Types Override + word rels Relationship.
  - Build `num_id_remap` as identity map for every `<w:num>` in installed file.
  - Return `(identity_remap, count_abstractnum, count_num)`.
- Otherwise: compute `anum_offset = _max_int(base_anum_ids) + 1` and `num_offset = _max_int(base_num_ids) + 1`.
- ECMA-376 §17.9.20 ordering insert algorithm:
  - Find `first_num_idx` = index of first `<w:num>` in base.
  - Find `cleanup_idx` = index of `<w:numIdMacAtCleanup>` if any.
  - Find `last_num_idx` = max index of `<w:num>`.
  - `num_insert_idx = cleanup_idx if cleanup_idx is not None else last_num_idx + 1`.
  - Pass 1: insert cloned `<w:abstractNum>` at `first_num_idx`, advance `insert_at` AND `num_insert_idx` after each insertion.
  - Pass 2: insert cloned `<w:num>` at `num_insert_idx`, populate `num_id_remap[old] = str(new)`.
- Return `(num_id_remap, count_abstractnum_inserted, count_num_inserted)`.

Signature:
```python
def _merge_numbering(
    base_tree_root: Path, insert_tree_root: Path,
) -> tuple[dict[str, str], int, int]:
    """F14 — Merge insert/word/numbering.xml into base/word/numbering.xml
    with abstractNumId/numId offset, preserving ECMA-376 §17.9.20
    element order (abstractNum-before-num). If base has no numbering.xml,
    install insert's verbatim. Returns (num_id_remap, abstractnum_count,
    num_count). num_id_remap is identity when base had none, offset-shifted
    otherwise."""
```

**Function `_ensure_numbering_part`:**
Direct port of `docx_merge.py:506-544` (idempotent: adds `[Content_Types].xml` Override AND `word/_rels/document.xml.rels` Relationship for numbering type if missing).

**Function `_remap_numid_in_clones` (F15) — R13 sub-features:**
```python
def _remap_numid_in_clones(
    clones: list[etree._Element], num_id_remap: dict[str, str],
) -> int:
    """F15 — Rewrite <w:numId w:val=N> attrs inside each clone using
    num_id_remap. Returns rewrite count. Unmapped values left alone."""
    if not num_id_remap:
        return 0
    count = 0
    for clone in clones:
        for el in clone.iter(qn("w:numId")):
            old = el.get(qn("w:val"))
            if old in num_id_remap:
                el.set(qn("w:val"), num_id_remap[old])
                count += 1
    return count
```

#### File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Class `TestMergeNumbering` — unskip and implement 4 tests + add 4 more for thorough coverage = 8 tests:**

1. `test_no_insert_numbering_returns_empty`:
   - Fixture: insert tree without `word/numbering.xml`.
   - Assert: `_merge_numbering` returns `({}, 0, 0)`; base unchanged.

2. `test_insert_empty_numbering_returns_empty`:
   - Fixture: insert tree has `word/numbering.xml` but with no `<w:abstractNum>` or `<w:num>` children.
   - Assert: returns `({}, 0, 0)`.

3. `test_install_verbatim_when_base_has_none`:
   - Fixture: base has NO `numbering.xml`; insert has 1 abstractNum + 1 num.
   - Assert: `base/word/numbering.xml` is created (byte-identical to insert's file).
   - Assert: `base/[Content_Types].xml` has new Override for `numbering.xml`.
   - Assert: `base/word/_rels/document.xml.rels` has new Relationship Type=".../numbering".
   - Assert: returned `num_id_remap` is identity for the single numId (e.g. `{"1": "1"}`).

4. `test_offset_shift_collision_avoided`:
   - Fixture: base has abstractNumIds [0, 1, 2] and numIds [1, 2]; insert has abstractNumIds [0, 1] and numIds [1, 2].
   - Assert: returned `num_id_remap == {"1": "3", "2": "4"}` (num_offset = 3).
   - Assert: base numbering.xml now has abstractNumIds [0, 1, 2, 3, 4] (the two new ones offset by anum_offset=3).
   - Assert: ECMA-376 §17.9.20 order — all `<w:abstractNum>` precede all `<w:num>`.

5. `test_ecma_376_17_9_20_abstractnum_before_num_preserved` (the REGRESSION-LOCK for the docx_merge iter-2.3 trap):
   - Fixture: base numbering has order `[abstractNum(0), abstractNum(1), num(1), num(2), numIdMacAtCleanup]`; insert has `[abstractNum(0), num(1)]`.
   - Call `_merge_numbering`.
   - Assert: base numbering.xml children in order: `[abstractNum(0), abstractNum(1), abstractNum(2 — new), num(1), num(2), num(3 — new), numIdMacAtCleanup]`.
   - Explicitly: every `<w:abstractNum>` precedes every `<w:num>`; `<w:numIdMacAtCleanup>` is the tail.

6. `test_abstractnum_with_malformed_id_skipped`:
   - Fixture: insert has one abstractNum with `w:abstractNumId="ABC"` (non-integer) + one valid abstractNum.
   - Assert: only the valid one is inserted; malformed skipped.

7. `test_num_with_missing_abstractnum_child_skipped`:
   - Fixture: insert has `<w:num w:numId="1"/>` (no `<w:abstractNumId>` child).
   - Assert: skipped; not included in `num_id_remap`.

8. `test_idempotent_when_called_twice_with_same_state`:
   - Q-A3 idempotency check (one regression-lock test):
   - Setup base + insert; call once; capture `num_id_remap`.
   - Call again with the SAME base (now post-first-call) + a FRESH clone of the original insert.
   - Assert: result is `({}, 0, 0)` because base now contains insert's abstractNums (collision-skip pass-through OR detection that all incoming abstractNum elements are duplicates — note: in practice this assertion does NOT hold because the algorithm does NOT detect duplicates; it always offset-shifts. So this test asserts the WEAKER invariant: calling the algorithm twice produces a state that still validates as OOXML — i.e. no schema corruption). Document this nuance in test docstring.

**Class `TestRemapNumidInClones` — unskip 2 tests:**

9. `test_rewrite_w_numId`:
   - Clone with `<w:p><w:pPr><w:numPr><w:numId w:val="3"/></w:numPr></w:pPr></w:p>`.
   - Map `{"3": "7"}`. Call → 1 rewrite. Assert `w:val == "7"`.

10. `test_unmapped_numid_left_alone`:
   - Clone with `<w:numId w:val="99"/>`. Map empty. → 0 rewrites; attr unchanged.

**Class `TestEnsureNumberingPart` — add 2 new tests:**

11. `test_adds_content_type_override_when_missing`:
   - Fixture: base with `[Content_Types].xml` lacking numbering Override.
   - Call `_ensure_numbering_part(base_dir)`.
   - Assert: Override added.

12. `test_idempotent`:
   - Call `_ensure_numbering_part` twice in a row.
   - Assert: only one Override + one Relationship, no duplicates.

**Total new tests in this sub-task: 8 (TestMergeNumbering) + 2 (TestRemapNumidInClones) + 2 (TestEnsureNumberingPart) = 12 tests.** Exceeds task spec floor of 10; satisfies G6.

### Component Integration
- `_actions.py` UNCHANGED. `docx_replace.py` UNCHANGED.
- `relocate_assets` still does NOT call `_merge_numbering` (wiring lands in 008-06).

## Test Cases

### Unit Tests
≥ 12 unskipped (8 numbering + 2 numid-clone + 2 ensure-part).

### End-to-end Tests
- **None** in this sub-task. E2 E2E lands in 008-06.

### Regression Tests
- All previous (39 docx-008 + 108 docx-6) unit tests still green.
- All 24 existing E2E cases plus the 2 new/rewritten from 008-04 still green.

## Acceptance Criteria
- [ ] F14 body matches ARCH §12.4 (ECMA-376 §17.9.20 ordering trap honored).
- [ ] F15 body trivial (~10 LOC).
- [ ] `_ensure_numbering_part` byte-ported from `docx_merge.py:506-544`.
- [ ] All 12 new unit tests green, including the explicit ECMA ordering regression-lock.
- [ ] All previous tests green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_relocator.TestMergeNumbering -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestRemapNumidInClones -v
./.venv/bin/python -m unittest tests.test_docx_relocator.TestEnsureNumberingPart -v
./.venv/bin/python -m unittest discover -s tests
bash tests/test_e2e.sh
```

## Notes
- **LOC budget for this task:** ~150 LOC of production code (F14 ~125 + F15 ~12 + `_ensure_numbering_part` ~40 — partly overlapping due to shared parsing setup) + ~250 LOC of tests. Running total in `_relocator.py`: ~510 LOC — slightly over the 500 LOC cap (Q-A1 guardrail). **Contingency:** if over by ≤ 30 LOC, the developer EITHER extracts `_merge_numbering_install_verbatim_branch` as a sibling helper (saves ~25 LOC inside `_merge_numbering` by hoisting the no-base-numbering branch) OR raises the cap to 550 LOC with a one-line update in PLAN.md §Estimated Effort + Q-A1 architect-ratification note in 008-08. **Do not silently exceed the cap** — flag in the 008-05 commit message.
- **ECMA-376 §17.9.20 trap:** the test `test_ecma_376_17_9_20_abstractnum_before_num_preserved` is the REGRESSION-LOCK. If a future contributor naively `.append()`s new abstractNum elements to `base_root`, this test fails immediately. The trap is documented in `docx_merge.py:388-433` — copy that explanatory comment block verbatim into `_merge_numbering` for the next reader.
- **DO NOT** import from `docx_merge`. The AST-walk regression-lock (`test_relocator_does_not_import_docx_merge`) catches this. The pattern is re-used by COPY per D3.
- **DO NOT** wire `_merge_numbering` into `relocate_assets` in this sub-task. That wiring lands in 008-06. Until then, the function is tested in isolation.
- **Q-A3 idempotency test placement:** the `test_idempotent_when_called_twice_with_same_state` test in `TestMergeNumbering` is a partial fulfillment of Q-A3. The relocator-level idempotency test (`test_relocator_idempotent_on_same_inputs` in `TestRelocateAssetsIdempotent`) lands in 008-07 once E2 is wired.
