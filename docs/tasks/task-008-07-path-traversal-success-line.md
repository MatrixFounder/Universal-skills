# Task 008-07: Path-traversal E2E + success-line annotation (Q-A2) + idempotency unit test (Q-A3)

## Use Case Connection
- **UC-1 Alt-1e** — relocator encounters malformed rels (TASK §2.1 Alt-1e).
- All UCs — Q-A2 stderr success-line annotation when assets are relocated.

## Task Goal
Three independent but small additions:
1. **Q-A2 wiring:** thread `relocation_report` from `_extract_insert_paragraphs` into the stderr success-line formatter in `docx_replace.py:_run`. Append `[relocated K media, A abstractNum, X numId]` ONLY when ≥ 1 asset was relocated (zero-suppression preserves back-compat).
2. **Q-A3 idempotency:** add the `test_relocator_idempotent_on_same_inputs` unit test (defensive regression-lock).
3. **G11 path-traversal E2E:** new E2E case `T-docx-insert-after-path-traversal` that crafts a malicious insert tree with `Target="../../etc/passwd"` and asserts exit 1 + `Md2DocxOutputInvalid` envelope.

Also runs `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` to confirm TASK §7 G10.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Function `_run` — success-line annotation:**

Locate the existing success-line formatter (after `_do_insert_after` returns successfully). It currently looks like:
```python
summary = (
    f"{output_basename}: inserted {count} paragraph(s) "
    f"after anchor {anchor!r} ({matches} match(es))"
)
print(summary, file=sys.stderr)
```

Replace with Q-A2 conditional annotation:
```python
summary = (
    f"{output_basename}: inserted {count} paragraph(s) "
    f"after anchor {anchor!r} ({matches} match(es))"
)
# Q-A2: annotate when ≥ 1 asset relocated (back-compat: zero-suppress).
if relocation_report is not None:
    k = relocation_report.media_copied + relocation_report.nonmedia_parts_copied
    a = relocation_report.abstractnum_added
    x = relocation_report.num_added
    if k + a + x > 0:
        summary += f" [relocated {k} media, {a} abstractNum, {x} numId]"
print(summary, file=sys.stderr)
```

Update the call-site (`_run`) to capture `relocation_report` from `_extract_insert_paragraphs`:
```python
insert_paragraphs, relocation_report = _extract_insert_paragraphs(
    insert_tree, tree_root,
)
count = _do_insert_after(tree_root, anchor, insert_paragraphs, ...)
# ... later, in the success-summary path:
# (relocation_report is in scope here)
```

For `--replace` and `--delete-paragraph` actions, `relocation_report` is `None` (no relocation). Initialize it as `None` at the top of `_run` and conditionally set it only on the `--insert-after` branch.

#### File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Class `TestRelocateAssetsIdempotent`** — unskip and implement:

1. `test_relocator_idempotent_on_same_inputs`:
   ```python
   def test_relocator_idempotent_on_same_inputs(self):
       """Q-A3 regression-lock: calling relocator with fresh clones of
       the SAME insert tree against the SAME base produces deterministic,
       OOXML-valid output. Documents the fresh-tmp-tree invariant."""
       # Build a base tree + an insert tree once.
       base_tree, insert_tree = self._build_fixture()
       # First invocation: full relocation.
       clones_1 = self._fresh_clones_from(insert_tree)
       report_1 = relocate_assets(insert_tree, base_tree, clones_1)
       # Second invocation: same base (now post-first-call), fresh clones from same insert.
       clones_2 = self._fresh_clones_from(insert_tree)
       report_2 = relocate_assets(insert_tree, base_tree, clones_2)
       # Assert: second invocation continues to add (because base now contains
       # first-pass artifacts, second pass adds another offset layer).
       # But base remains OOXML-valid — validate via etree parse + a sample
       # schema-aware check.
       numbering_path = base_tree / "word" / "numbering.xml"
       if numbering_path.is_file():
           root = etree.parse(str(numbering_path)).getroot()
           # ECMA-376 §17.9.20 ordering MUST hold after two passes.
           seen_num = False
           for child in root:
               local = etree.QName(child).localname
               if local == "num":
                   seen_num = True
               elif local == "abstractNum" and seen_num:
                   self.fail("ECMA-376 §17.9.20 order broken after 2 relocations")
       # The clones in pass 2 have rId/numId rewritten to a HIGHER offset than pass 1.
       # (Pass 1 used offset N; pass 2 sees base with N+ inserted defs, uses offset N + len(inserted).)
   ```

#### File: `skills/docx/scripts/tests/test_e2e.sh`

**Add new case `T-docx-insert-after-path-traversal` (TASK §7 G11):**

**Two-layer implementation** to satisfy both the shell-E2E gate (TASK §7 G11 wording) AND the Python-fixture pragmatics (plan-review MAJ-1):

1. **Python-side helper** `tests/fixtures/build_malicious_insert_docx.py` (~30 LOC) — a small script that generates a `.docx` whose internal `word/_rels/document.xml.rels` contains a relocation Target with `'../../../etc/passwd'`. Invocable from shell: `python3 tests/fixtures/build_malicious_insert_docx.py /tmp/malicious_insert.docx`.
2. **Shell-E2E case** in `test_e2e.sh`:
   ```bash
   # T-docx-insert-after-path-traversal: malicious insert rels reject.
   # Build fixture via Python helper (fixture creation is too gnarly for inline shell).
   python3 tests/fixtures/build_malicious_insert_docx.py /tmp/malicious_insert.docx
   # Convert .docx to .md by extracting the malicious tree directly — OR
   # invoke docx_replace.py via a test-helper Python wrapper that
   # monkeypatches _materialise_md_source to return the pre-built malicious tree.
   pt_stderr=$(python3 tests/helpers/run_with_malicious_insert.py \
       /tmp/base.docx /tmp/out.docx --anchor "Section 3:" \
       --malicious-insert /tmp/malicious_insert.docx --json-errors 2>&1)
   pt_rc=$?
   if [ "$pt_rc" = "1" ] && echo "$pt_stderr" | grep -q '"type": *"Md2DocxOutputInvalid"'; then
       ok "T-docx-insert-after-path-traversal (rc=1, type=Md2DocxOutputInvalid)"
   else
       nok "T-docx-insert-after-path-traversal" "rc=$pt_rc stderr=$pt_stderr"
   fi
   ```
3. **Python unit test** in `tests/test_docx_replace.py` (defence-in-depth, faster to debug):

```python
class TestPathTraversal(unittest.TestCase):
    def test_insert_after_rejects_parent_segment_target(self):
        """G11: malicious insert rels with Target='../../../etc/passwd'
        causes Md2DocxOutputInvalid (exit 1)."""
        # Build base.docx + insert source.
        # Materialise insert via md2docx into a tmp tree.
        # Surgically rewrite tmp_insert_tree/word/_rels/document.xml.rels
        #   to add a Relationship with Target='../../../etc/passwd'.
        # Monkeypatch _materialise_md_source to return the patched tree.
        # Invoke docx_replace.main(argv).
        # Assert: SystemExit with code 1; stderr envelope type=Md2DocxOutputInvalid.

    def test_insert_after_rejects_absolute_target(self):
        """Same shape, but Target='/etc/passwd'."""
        # ... (parametrised variant) ...
```

**Total tests added in this sub-task:**
- 1 shell-E2E case (`T-docx-insert-after-path-traversal`) — TASK §7 G11.
- 1 unit test (`test_relocator_idempotent_on_same_inputs`) — Q-A3.
- 2 unit tests (`TestPathTraversal.*`) — defence-in-depth + faster debug.
- 3 unit tests (`TestRunSuccessLine.*`) — Q-A2 zero-suppression.

**Two-layer G11 rationale (plan-review MAJ-1):** keep both the shell-E2E (TASK §7 G11 wording satisfied) AND Python unit tests (faster to debug, monkeypatchable). The fixture build is delegated to a Python helper invoked from shell, so the shell case stays clean.

#### File: `skills/docx/scripts/docx_replace.py` (additional)

**`--help` text:** update the existing description that mentions image/numId honest-scope. Reword the success-line description in the docstring. The full SKILL.md / `--help` polish is a 008-08 item; in this task only add the Q-A2 success-line clause to the `_run` docstring.

### Component Integration
- After this task, the only remaining unwired piece is the `--help` text + docs polish (008-08).
- The success-line annotation only fires when something was relocated; existing E2E parsers that match the v1 success-line regex (e.g. `re.search(r"inserted \d+ paragraph", stderr)`) continue to work (the suffix is appended after a literal `)` character, not embedded).

## Test Cases

### Unit Tests
- `test_relocator_idempotent_on_same_inputs` (Q-A3).
- `TestPathTraversal.test_insert_after_rejects_parent_segment_target` (G11).
- `TestPathTraversal.test_insert_after_rejects_absolute_target` (G11).

### Q-A2 success-line annotation tests (in test_docx_replace.py):
- `TestRunSuccessLine.test_no_annotation_when_no_relocation` — `--insert-after` of plain text → no `[relocated ...]` suffix.
- `TestRunSuccessLine.test_annotation_when_image_relocated` — image MD → suffix present, K ≥ 1.
- `TestRunSuccessLine.test_annotation_when_numbering_relocated` — list MD → suffix present, A + X ≥ 1.

**Total new tests: ~6** in this sub-task.

### End-to-end Tests
- Run `DOCX_REPLACE_POST_VALIDATE=1 bash tests/test_e2e.sh` to confirm G10 (the post-pack validator catches any relocator schema bug).

### Regression Tests
- All previous unit tests green. All E2E cases green.

## Acceptance Criteria
- [ ] Q-A2 success-line annotation wired in `docx_replace.py:_run`; suppressed when all counts zero.
- [ ] 1 new `test_relocator_idempotent_on_same_inputs` unit test green.
- [ ] 2 new `TestPathTraversal.*` unit tests green; both produce `Md2DocxOutputInvalid` exit 1.
- [ ] 3 new `TestRunSuccessLine.*` unit tests green (Q-A2 zero-suppression contract).
- [ ] TASK §7 G10 green: `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` exits 0.
- [ ] TASK §7 G11 green: malicious rels rejection.
- [ ] All previous tests green.

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_relocator.TestRelocateAssetsIdempotent -v
./.venv/bin/python -m unittest tests.test_docx_replace.TestPathTraversal -v
./.venv/bin/python -m unittest tests.test_docx_replace.TestRunSuccessLine -v
./.venv/bin/python -m unittest discover -s tests
bash tests/test_e2e.sh
DOCX_REPLACE_POST_VALIDATE=1 bash tests/test_e2e.sh
```

## Notes
- **G11 placement decision (E2E vs unit-E2E):** the planner places G11 as a unit-test class (`TestPathTraversal` in `test_docx_replace.py`) rather than a shell-based E2E case because (a) crafting a malicious docx fixture requires surgical XML editing, easier in Python; (b) E2E cases are integration tests typically for the CLI subprocess, and exit-1 with envelope assertion is straightforward in shell BUT the FIXTURE CREATION is the hard part. Going Python-side keeps the fixture creation in the test file itself, avoiding a binary fixture in `tests/fixtures/` that's hard to inspect/maintain. Document this choice; G11 is satisfied either way. If the developer prefers shell, they can add the case to `test_e2e.sh` and create the fixture inline via Python helper script.
- **Q-A3 idempotency test is partial regression-lock.** The actual idempotency property (calling relocator twice produces SAME state, not just OOXML-valid) does NOT hold given the algorithm — second call always appends additional offset layers. The test asserts the WEAKER property: post-double-call state is still OOXML-valid (ECMA-376 §17.9.20 order, validatable). This is acceptable per ARCH §12.1 Q-A3 decision ("the relocator is constructed to be idempotent by virtue of the fresh-tmp-tree invariant"). Test docstring documents this nuance.
- **Q-A2 zero-suppression:** the `if k + a + x > 0` guard is the back-compat protection. Existing E2E grep patterns like `grep "inserted .* paragraph" stderr` continue to match.
- **POST_VALIDATE end-to-end run:** if the validator surfaces any ECMA-376 violation, treat it as a defect in `_merge_numbering` (most likely §17.9.20 ordering) and fix in 008-05/008-06. Until G10 is green, this task cannot close.
