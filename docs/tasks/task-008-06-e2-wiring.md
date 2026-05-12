# Task 008-06: E2 wiring + R14

## Use Case Connection
- **UC-2** — `--insert-after` with numbered/bulleted list (TASK §2.2). First Green E2E path for numbering relocation.
- **UC-3** — image + list integration (TASK §2.3). E1 + E2 in one call.

## Task Goal
Wire E2 (numbering relocator) into `relocate_assets` orchestrator. Delete the R10.e WARNING stderr line in `_actions.py`. Rewrite `T-docx-numid-survives-warning` E2E case to assert GREEN-path relocation. Add new E2E cases `T-docx-insert-after-numbering-relocated` and `T-docx-insert-after-image-and-numbering`.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `relocate_assets` — extend E2 branch:**

Replace the E2 stub block from 008-04:
```python
# --- E2: Numbering relocator (stub — lands in 008-05/008-06) ---
num_id_remap: dict[str, str] = {}
abstractnum_added = 0
num_added = 0
numid_rewrites = 0
```

With the live E2 branch:
```python
# --- E2: Numbering relocator ---
num_id_remap, abstractnum_added, num_added = _merge_numbering(
    base_tree_root, insert_tree_root,
)
numid_rewrites = _remap_numid_in_clones(clones, num_id_remap)
```

Other fields of `RelocationReport` already correctly populated from 008-04.

#### File: `skills/docx/scripts/_actions.py`

**Delete R10.e WARNING block in `_extract_insert_paragraphs`:**

After 008-04 deleted the R10.b WARNING block (lines 296–303), the function still contains the R10.e WARNING block (lines 304–311 in original numbering — `if saw_numid and not base_has_numbering: print(...)`). Delete this block entirely. Also delete the `saw_numid` local flag, the `numId` detection loop, and the `base_has_numbering` parameter dependency (the `base_has_numbering` kwarg was already removed in 008-04; if any trace remains, clean it up here).

After this delete, `_extract_insert_paragraphs` body is a clean deep-clone-with-sectPr-strip → `relocator.relocate_assets()` → return.

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

**Test `test_extract_insert_paragraphs_emits_numid_warning`** — **REWRITE** as `test_extract_relocates_numbering`:
```python
def test_extract_relocates_numbering(self):
    """008-06 R10.e → GREEN. Insert tree with numbered list; assert
    abstractNum + num defs copied with offset, numId rewritten in clone,
    no WARNING."""
    # ... fixture setup with insert/word/numbering.xml ...
    captured_stderr = io.StringIO()
    with contextlib.redirect_stderr(captured_stderr):
        clones, report = _extract_insert_paragraphs(
            insert_tree_root, base_tree_root,
        )
    self.assertGreaterEqual(report.abstractnum_added, 1)
    self.assertGreaterEqual(report.num_added, 1)
    self.assertGreaterEqual(report.numid_rewrites, 1)
    self.assertNotIn("[docx_replace] WARNING", captured_stderr.getvalue())
    # The clone's <w:numId w:val> points at the base-side numId.
    numid_el = clones[0].find(".//{*}numId")
    self.assertIsNotNone(numid_el)
    new_val = numid_el.get(qn("w:val"))
    # Verify it was actually rebound (different from insert-side original).
    self.assertNotEqual(new_val, "1")  # Insert's original was numId=1; base offset → ≥ 2.
```

#### File: `skills/docx/scripts/tests/test_e2e.sh`

**Rewrite case `T-docx-numid-survives-warning` (currently around line 2239):**
- Currently asserts `[docx_replace] WARNING: ... <w:numId>` line on stderr. Rewrite to:
  - Assert NO `[docx_replace] WARNING` line on stderr.
  - Assert `<w:numId w:val="N">` inside inserted `<w:p>` resolves to a `<w:num w:numId="N">` in base `word/numbering.xml`.
  - The case name can stay or be renamed to `T-docx-insert-after-numbering-relocated-warn-replacement`.

**Add new case `T-docx-insert-after-numbering-relocated`:**
- Build fixture: `insert.md` with `1. Step one\n2. Step two\n` (or `- bullet1\n- bullet2\n`).
- Run: `python3 docx_replace.py base.docx out.docx --anchor "Section 3:" --insert-after insert.md`.
- Assert exit 0.
- Unpack `out.docx`; assert:
  - `word/numbering.xml` exists in output (either was already there OR installed verbatim).
  - `<w:abstractNum w:abstractNumId="N">` and `<w:num w:numId="M">` for the inserted list defs exist with offsets relative to any existing base lists.
  - Inserted `<w:p>` references `<w:numId w:val="M">` matching the new num def.
  - No `[docx_replace] WARNING` line on stderr.

**Add new case `T-docx-insert-after-image-and-numbering` (TASK §7 G4 — integration):**
- Fixture: `insert.md` containing BOTH `![demo](demo.png)` and `1. step\n2. step\n`.
- Run: `--insert-after insert.md`.
- Assert exit 0.
- Assert: BOTH image relocated (UC-1 assertions) AND numbering relocated (UC-2 assertions).
- This is the smoke test that E1 + E2 cooperate without interference.

**Total new/rewritten E2E cases in this task: 1 rewrite + 2 new = 3.**

Cumulative E2E delta after 008-06: 2 new from 008-04 + 3 new from 008-06 + 2 rewrites = 5 new cases + 2 rewrites = **7 changes to test_e2e.sh** total across 008-04+008-06.

### Component Integration
- `relocate_assets` is now FULLY live (both E1 and E2 branches).
- `_actions.py:_extract_insert_paragraphs` body is now minimal (no WARNING noise, no precursor-scan loops).
- `docx_replace.py:_run` continues to capture `relocation_report` but does NOT yet use it for stderr annotation (Q-A2 lands in 008-07).

## Test Cases

### Unit Tests
- `test_extract_relocates_numbering` (rewritten).

### End-to-end Tests
1. **T-docx-insert-after-numbering-relocated** (NEW): TASK §7 G3.
2. **T-docx-insert-after-image-and-numbering** (NEW): TASK §7 G4.
3. **T-docx-numid-survives-warning** (REWRITTEN to GREEN-path): TASK §7 G5 (second half).

### Regression Tests
- All other Task 006 E2E cases continue to pass unchanged (TASK §7 G1 — full).
- After 008-04 + 008-06: total E2E count = 22 unchanged + 4 new + 2 rewritten = 28 cases all green.
- All unit tests (108 existing + 51 docx-008 by end of this sub-task: 39 + 12 in 008-05) green.

## Acceptance Criteria
- [ ] `relocate_assets` E2 branch is live (calls `_merge_numbering` + `_remap_numid_in_clones`).
- [ ] R10.e WARNING stderr line is **deleted** from `_actions.py`.
- [ ] `_extract_insert_paragraphs` body is clean: deep-clone + sectPr-strip + `relocator.relocate_assets()` + return.
- [ ] TASK §7 G3 green (T-docx-insert-after-numbering-relocated).
- [ ] TASK §7 G4 green (T-docx-insert-after-image-and-numbering).
- [ ] TASK §7 G5 fully green (both rewritten warn cases are GREEN-path).
- [ ] TASK §7 G1 fully green (all 22 unchanged cases + 2 rewritten from 008-04 + 2 from this task pass).
- [ ] All previous unit tests still green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_replace -v
bash tests/test_e2e.sh
# Confirm G1: count all-green
grep -c "^ok " /tmp/docx-e2e.log  # or whatever the test logger writes
```

## Notes
- **R10.e WARNING deletion:** find and remove the `if saw_numid and not base_has_numbering: print("[docx_replace] WARNING: inserted body contains <w:numId> references; base document has no numbering.xml ...", file=sys.stderr)` block in `_actions.py`. Also delete the `saw_numid` local flag and its inline check at the top of the `for el in clone.iter():` loop.
- **R10.e regression-lock E2E rewrite:** the rewritten case asserts the OPPOSITE: no WARNING, numbering correctly relocated. The case name `T-docx-numid-survives-warning` can stay (git-blame traceability) — the implementation behind the case changes, the name's semantic shifts from "WARNING surfaces but doesn't fail" to "WARNING is gone because actually relocated".
- **G4 integration test fixture:** the insert MD with both image and list should be deterministic. Suggest:
  ```markdown
  # Inserted heading
  ![demo](demo.png)
  1. Step one
  2. Step two
  ```
  md2docx will produce a single `.docx` with the image's `<w:drawing>` referencing `media/image1.png` AND the list's `<w:p>` referencing `<w:numId w:val="1">`. Both relocate together.
- **Idempotency check:** after this task, calling `relocate_assets` twice on the same fresh insert tree produces two valid relocations (the second adds another offset layer — semantically duplicates, but OOXML-valid). The full relocator-level idempotency test (`test_relocator_idempotent_on_same_inputs`) lands in 008-07.
- **POST_VALIDATE hook:** if `DOCX_REPLACE_POST_VALIDATE=1` env-var is set, the post-pack validator catches any ECMA-376 §17.9.20 ordering violations introduced by buggy `_merge_numbering`. This validator already exists from docx-6; no new wiring needed. Manual test: `DOCX_REPLACE_POST_VALIDATE=1 bash tests/test_e2e.sh` (full TASK §7 G10 lands in 008-07).
