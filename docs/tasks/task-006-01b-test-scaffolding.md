# Task 006-01b: Test scaffolding — Red state for the docx-6 chain (20 + 30 + 16 stubs + 4 fixtures)

## Use Case Connection
- **UC-1, UC-2, UC-3, UC-4** — every use case has at least one E2E case stub in the scaffolding.
- **R11.a–R11.d** — testing budget (≥ 16 E2E + ≥ 20 anchor unit + ≥ 30 replace unit + fixtures from `md2docx.js`).

## Task Goal

Write the test files and fixture documents that will go RED on the
stubs from 006-01a (and on the not-yet-existing `docx_replace.py`)
and turn GREEN as each Phase-2 task lands.

- `tests/test_docx_anchor.py` — ≥ 20 unit cases in skip-stub form;
  classes: `TestExtractedHelpers`, `TestReplaceInRun`,
  `TestConcatParagraphText`, `TestFindParagraphsContainingAnchor`.
- `tests/test_docx_replace.py` — ≥ 30 unit cases in skip-stub form;
  classes: `TestCrossCutting`, `TestPartWalker`, `TestReplaceAction`,
  `TestInsertAfterAction`, `TestDeleteParagraphAction`, `TestCli`,
  `TestPostValidate`, `TestHonestScopeLocks`.
- `tests/test_e2e.sh` — append a `# --- docx-6: docx_replace ---`
  block with **≥ 16 named cases**, gated by the `DOCX6_STUBS_ENABLED`
  env flag (plan-review MAJ-2 fix): default unset → `echo SKIP
  T-<name>`; `DOCX6_STUBS_ENABLED=1` → run case + expect-fail (rc ≠
  expected ⇒ `nok`). CI stays exit-0 by default; developers exercising
  Stub-First Red state set the flag.
- `examples/docx_replace_body.docx`, `examples/docx_replace_headers.docx`,
  `examples/docx_replace_insert_source.md` — 3 OOXML fixtures generated
  via `md2docx.js` + 1 markdown insert-source.

## Changes Description

### New Files

- **`skills/docx/scripts/tests/test_docx_anchor.py`** — NEW. ≥ 20 unit
  cases as **observably failing stubs** (plan-review MAJ-2 fix). Each
  stub uses `self.fail("docx-6 stub — to be implemented in
  task-006-02")` so the test suite reports a failing test per
  Phase-2 deliverable that downstream tasks turn green. The CI red
  bar SHRINKS monotonically as Phase-2 sub-tasks flip individual
  `self.fail()` lines to real assertions. (NOT `unittest.skip` —
  silent skip = 0 failures = false-green; the Red state must be
  visible to CI.)
  Skeleton:
  ```python
  import unittest
  try:
      from docx_anchor import (
          _is_simple_text_run, _rpr_key, _merge_adjacent_runs,
          _replace_in_run, _concat_paragraph_text,
          _find_paragraphs_containing_anchor,
      )
  except ImportError:
      # Helpers added in 006-02; tests still collectable for Red state.
      pass

  _STUB_002 = "docx-6 stub — to be implemented in task-006-02"

  class TestExtractedHelpers(unittest.TestCase):
      """Regression of the byte-identical extraction (006-01a).

      These 10 tests turn GREEN as part of 006-02 (when the helpers
      are confirmed importable and behavioural assertions are filled
      in). Until then, self.fail() makes the Red state observable.
      """
      def test_is_simple_text_run_accepts_t_only_run(self):
          self.fail(_STUB_002)
      def test_is_simple_text_run_accepts_rPr_t_run(self):
          self.fail(_STUB_002)
      def test_is_simple_text_run_rejects_run_with_drawing(self):
          self.fail(_STUB_002)
      def test_is_simple_text_run_rejects_run_with_fldChar(self):
          self.fail(_STUB_002)
      def test_rpr_key_canonical_serialisation_stable(self):
          self.fail(_STUB_002)
      def test_rpr_key_distinguishes_bold_vs_italic(self):
          self.fail(_STUB_002)
      def test_merge_adjacent_runs_coalesces_identical_rpr(self):
          self.fail(_STUB_002)
      def test_merge_adjacent_runs_skips_non_simple_run(self):
          self.fail(_STUB_002)
      def test_merge_adjacent_runs_idempotent(self):
          self.fail(_STUB_002)
      def test_merge_adjacent_runs_preserves_xml_space_preserve(self):
          self.fail(_STUB_002)

  class TestReplaceInRun(unittest.TestCase):
      def test_first_match_default(self): self.fail(_STUB_002)
      def test_all_flag_replaces_every_occurrence(self): self.fail(_STUB_002)
      def test_empty_replacement_strips_anchor(self): self.fail(_STUB_002)
      def test_anchor_at_run_start_preserves_leading_space(self): self.fail(_STUB_002)
      def test_xml_space_preserve_set_when_needed(self): self.fail(_STUB_002)  # NIT-3
      def test_no_infinite_loop_when_replacement_contains_anchor(self): self.fail(_STUB_002)
      def test_cursor_advances_past_replacement_for_all_flag(self): self.fail(_STUB_002)
      def test_anchor_spanning_runs_returns_zero(self): self.fail(_STUB_002)   # honest-scope D6/B

  class TestConcatParagraphText(unittest.TestCase):
      def test_concat_simple_paragraph(self): self.fail(_STUB_002)
      def test_concat_includes_ins_content(self): self.fail(_STUB_002)   # Q-U1 default
      def test_concat_excludes_del_content(self): self.fail(_STUB_002)   # Q-U1 default
      def test_concat_handles_empty_paragraph(self): self.fail(_STUB_002)

  class TestFindParagraphsContainingAnchor(unittest.TestCase):
      def test_returns_empty_list_when_no_match(self): self.fail(_STUB_002)
      def test_returns_paragraphs_in_document_order(self): self.fail(_STUB_002)
      def test_concat_text_match_crosses_runs(self): self.fail(_STUB_002)
      def test_skips_paragraphs_inside_del_runs(self): self.fail(_STUB_002)
  ```

- **`skills/docx/scripts/tests/test_docx_replace.py`** — NEW. ≥ 30 unit
  cases as **observably failing stubs** (plan-review MAJ-2 fix —
  same convention as `test_docx_anchor.py`: every method body is
  `self.fail("docx-6 stub — to be implemented in task-006-NN")`,
  where `NN` names the downstream Phase-2 sub-task that turns the
  test green; NOT `unittest.skip`). The CI red bar SHRINKS
  monotonically as Phase-2 tasks flip the `self.fail()` lines.
  Skeleton organisation (with the downstream sub-task per class
  named in the `self.fail()` message):
  - `TestCrossCutting` (≥ 6, **flipped in 006-03**): same-path
    symlink, encrypted, stdin cap, `--json-errors` envelope shape,
    macro stderr warning, library-mode-skips-cross7. `self.fail`
    message ends with `"task-006-03"`.
  - `TestPartWalker` (≥ 4, **flipped in 006-04**): Content_Types
    primary source, glob fallback, deterministic order,
    missing-on-disk silent skip. `self.fail` message ends with
    `"task-006-04"`.
  - `TestReplaceAction` (≥ 5, **flipped in 006-04**): R1.a–R1.g
    coverage. `self.fail` message ends with `"task-006-04"`.
  - `TestInsertAfterAction` (≥ 5, **flipped in 006-05**): subprocess
    discipline, sectPr strip, deep-clone per match, stdin path,
    --all duplication. `self.fail` message ends with `"task-006-05"`.
  - `TestDeleteParagraphAction` (≥ 4, **flipped in 006-06**):
    paragraph removal, empty-cell placeholder (Q-A5),
    last-paragraph refusal, --all multi-match. `self.fail` message
    ends with `"task-006-06"`.
  - `TestCli` (≥ 3, **flipped in 006-07a**): mutex group,
    missing-action UsageError, output extension preserved (R8.k).
    `self.fail` message ends with `"task-006-07a"`.
  - `TestPostValidate` (≥ 3, **flipped in 006-07a**): env-truthy
    parser, validator failure unlinks output + exit 7, env-unset →
    no subprocess. `self.fail` message ends with `"task-006-07a"`.
  - `TestLibraryMode` (≥ 2, **flipped in 006-07b**;
    `unittest.skip("Deferred to docx-6.4 backlog")` if 006-07b is
    deferred): library-mode dispatch first, NotADocxTree, forbids
    positional. `self.fail` message ends with `"task-006-07b"`.
  - `TestHonestScopeLocks` (≥ 5, **flipped in 006-08**): cross-run
    anchor → AnchorNotFound; rel-target warning + no live r:embed;
    last-paragraph guard; --all --delete-paragraph last-paragraph
    guard wins; `<w:numId>` survives. `self.fail` message ends with
    `"task-006-08"`.
  - **PLUS arch-review MIN-2 + MIN-4 + NIT-3:**
    - Q-U1 tracked-change default behaviour lock (`<w:ins>` matched,
      `<w:del>` ignored at E2E level).
    - A4 TOCTOU symlink-race acceptance test (resolve→open same-path
      catches even when source symlink target is rewritten between
      resolve() and open()).
    - R1.g `xml:space="preserve"` set-when-needed E2E.

- **`skills/docx/examples/docx_replace_body.docx`** — NEW. Generated
  fixture (NOT manually crafted OOXML — R11.d). Use a small
  markdown source like:
  ```markdown
  # Test contract

  Effective Date: May 2024.

  ## Article 5.

  The agreement begins on the effective date.

  DEPRECATED CLAUSE: this section is no longer in force.

  | Item | Value |
  |------|-------|
  | A    | 1     |
  | B    | 2     |

  Final paragraph.
  ```
  Save the generated `.docx` to `skills/docx/examples/docx_replace_body.docx`. This single fixture serves UC-1 (anchor "May 2024"), UC-2 (anchor "Article 5."), UC-3 (anchor "DEPRECATED CLAUSE"), and the table-cell deletion edge case.

- **`skills/docx/examples/docx_replace_headers.docx`** — NEW. Generated
  fixture with the same anchor text appearing in both the body and a
  header. Used by R5 part-walker E2E cases. Source markdown is minimal
  — anchor "Company X" appears in `## Heading` (renders to body) and
  the post-generation step injects a `word/header1.xml` part with the
  same anchor text. (Acceptable to manually splice the header part
  AFTER md2docx generation; the body itself remains md2docx-generated
  per R11.d.)

- **`skills/docx/examples/docx_replace_insert_source.md`** — NEW.
  Markdown source for `--insert-after` E2E tests:
  ```markdown
  # Inserted heading

  Inserted body paragraph **bold** and *italic*.
  ```
  Used by `T-insert-after-file` and `T-insert-after-stdin` cases. ALSO the source for `T-insert-after-image` (R10.b) is a sibling file `docx_replace_insert_with_image.md` containing `![alt](nonexistent.png)`.

### Changes in Existing Files

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Append a new section header:
  ```bash
  # ---------- docx-6 / docx_replace ----------
  # Plan-review MAJ-2 fix: stub cases gated by DOCX6_STUBS_ENABLED.
  # Default (unset/0) → echo SKIP; suite stays exit-0 in CI.
  # DOCX6_STUBS_ENABLED=1 → run case, expect-fail (nok if rc != expected).
  # Each Phase-2 sub-task removes its gate as the region lands GREEN.
  : "${DOCX6_STUBS_ENABLED:=0}"
  ```
- Append **≥ 16** named cases. Each case is wrapped in the pattern:
  ```bash
  # T-docx-replace-happy (UC-1; flipped in 006-04)
  if [ "$DOCX6_STUBS_ENABLED" = "1" ]; then
      # Expect-fail: stub returns NotImplementedError → rc=1; expected rc once
      # green = 0. Today: rc=1 ⇒ ok (stub Red); when 006-04 lands, expected
      # becomes 0 and the case flips to a real assertion.
      run_expect_fail T-docx-replace-happy 1 \
          python3 docx_replace.py ... --anchor "May 2024" --replace "April 2025"
  else
      echo "SKIP T-docx-replace-happy (DOCX6_STUBS_ENABLED unset; flipped in 006-04)"
  fi
  ```
  The 20 stable cases (≥ 16 minimum per R11.a):
  1. `T-docx-replace-happy` — UC-1 happy path (anchor "May 2024" → "April 2025"); preserve bold.
  2. `T-docx-replace-empty-replacement` — `--replace ""` strips anchor; exit 0.
  3. `T-docx-replace-all-multiple` — `--all` on paragraph with 3 occurrences; counter == 3.
  4. `T-docx-replace-anchor-not-found` — bogus anchor; exit 2 `AnchorNotFound` envelope.
  5. `T-docx-replace-cross-run-anchor-fails` — anchor spans formatting boundary; exit 2 `AnchorNotFound` (R10.a honest-scope lock).
  6. `T-docx-insert-after-file` — UC-2 happy path (markdown file → 2 paragraphs inserted after "Article 5.").
  7. `T-docx-insert-after-stdin` — UC-2 stdin (`-`); same output as file path.
  8. `T-docx-insert-after-empty-stdin` — empty stdin → exit 2 `EmptyInsertSource`.
  9. `T-docx-insert-after-all-duplicates` — `--all` produces N×duplication.
  10. `T-docx-insert-after-image-warns` — MD source with `![](image.png)` → stderr warning + no live r:embed (R10.b).
  11. `T-docx-delete-paragraph` — UC-3 happy path; paragraph count -1.
  12. `T-docx-delete-paragraph-table-cell-placeholder` — paragraph in `<w:tc>` removed; `<w:p/>` placeholder inserted (Q-A5).
  13. `T-docx-delete-paragraph-last-body-refused` — refuse to empty `<w:body>`; exit 2 `LastParagraphCannotBeDeleted` (R10.c).
  14. `T-docx-delete-paragraph-all-common-word` — `--all --delete-paragraph` with common word still trips last-paragraph guard (R10.d).
  15. `T-docx-replace-same-path` — INPUT == OUTPUT (incl. symlink); exit 6 (cross-7).
  16. `T-docx-replace-encrypted` — encrypted input; exit 3 (cross-3).
  17. `T-docx-replace-macro-warning` — `.docm` input; stderr warning then proceed (cross-4).
  18. `T-docx-replace-envelope-shape` — any failure with `--json-errors` → cross-5 envelope on stderr.
  19. `T-docx-replace-action-mutex` — two of `{--replace, --insert-after, --delete-paragraph}` → exit 2 `UsageError` (R4.a).
  20. `T-docx-replace-help-honest-scope` — `--help` text mentions single-run honest scope, blast-radius warning, last-paragraph refusal, image-not-copied note (R8.j).

  (20 ≥ 16 minimum.) Each case is wrapped in the `if [
  "$DOCX6_STUBS_ENABLED" = "1" ]` gate shown above. Default unset →
  all 20 echo SKIP; script exit-0 in CI. With
  `DOCX6_STUBS_ENABLED=1` set, developers can exercise the Stub-First
  Red state (each case expect-fails on the stub's `NotImplementedError`
  or argparse-rejection).

### Component Integration

`test_docx_anchor.py` adds `from docx_anchor import (...)` — the
import succeeds for `_is_simple_text_run`, `_rpr_key`,
`_merge_adjacent_runs` (006-01a output); imports for
`_replace_in_run`, `_concat_paragraph_text`,
`_find_paragraphs_containing_anchor` will fail with `ImportError`
until 006-02 lands — wrap those imports in a try/except so
`test_docx_anchor.py` is collectable today.

`test_docx_replace.py` imports nothing from `docx_replace` yet
(module doesn't exist); wrap the import in `try/except ImportError`
so the test module is collectable today. **Do NOT use
`unittest.skip` on the ImportError path** — the methods must still
`self.fail()` to surface the Red state. The import-time guard only
prevents an unrecoverable collection error.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (default CI cadence):** `bash skills/docx/scripts/tests/test_e2e.sh` (no env) exits 0 with all 20 new T-tagged cases reporting `SKIP`. (The existing docx-1 block continues to PASS — 006-01a guaranteed this.)
2. **TC-E2E-02 (Stub-First Red verification):** `DOCX6_STUBS_ENABLED=1 bash skills/docx/scripts/tests/test_e2e.sh` — script exits **NON-ZERO** (Stub-First Red state visible) because each of the 20 cases is expect-fail and the stubs raise `NotImplementedError`. This non-zero exit is the **expected** behaviour of the Red state and proves the gate works.

### Unit Tests

1. **TC-UNIT-01 (Red bar visible):** `python3 -m unittest discover -s skills/docx/scripts/tests` reports ≥ 50 FAILED tests (20 from `test_docx_anchor` + 30 from `test_docx_replace`), each with a `self.fail("docx-6 stub — to be implemented in task-006-NN")` message that names a downstream task. No SKIPs and no ERRORs (collection errors).
2. **TC-UNIT-02 (collectability):** `test_docx_anchor.py` AND `test_docx_replace.py` are collectable without `ImportError` even when `docx_replace.py` doesn't exist yet (use guarded imports — see Component Integration above).

### Regression Tests

- All existing docx skill tests pass (006-01a refactor regression should already be green).
- All 12 `diff -q` cross-skill replication checks silent (this task touches only docx-only files).

## Acceptance Criteria

- [ ] `tests/test_docx_anchor.py` exists with 4 test classes, ≥ 20 method stubs, each `self.fail("docx-6 stub — to be implemented in task-006-02")` (NOT `unittest.skip`).
- [ ] `tests/test_docx_replace.py` exists with 8 test classes, ≥ 30 method stubs, each `self.fail("docx-6 stub — to be implemented in task-006-NN")` naming the downstream sub-task.
- [ ] `tests/test_e2e.sh` has the 20 new T-tagged cases gated by `DOCX6_STUBS_ENABLED`: default unset → echo SKIP (script exit 0); `DOCX6_STUBS_ENABLED=1` → expect-fail (script exit non-zero on the Red state).
- [ ] `examples/docx_replace_body.docx` generated via `md2docx.js` (NOT manually crafted).
- [ ] `examples/docx_replace_headers.docx` generated via `md2docx.js` + manual header-part splice; document the splice steps in a comment block inside the test file that consumes it.
- [ ] `examples/docx_replace_insert_source.md` exists with the documented body.
- [ ] `examples/docx_replace_insert_with_image.md` exists (used by R10.b case 10).
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.
- [ ] **Default CI cadence:** `bash skills/docx/scripts/tests/test_e2e.sh` exits 0 (all 20 stubs echo SKIP).
- [ ] **Red-state verification:** `python3 -m unittest discover -s skills/docx/scripts/tests` reports ≥ 50 FAILED tests (the Stub-First Red bar; SHRINKS monotonically as Phase-2 sub-tasks land).

## Notes

The 16-case minimum is from TASK §5 / RTM R11.a. We commit to **20 cases**
to leave headroom for honest-scope lock tests in 006-08 without
retro-adding entries.

The "no manually-crafted OOXML" rule (R11.d) is **load-bearing**:
agents must NOT inline raw OOXML byte sequences in fixtures. Generate
via `md2docx.js`; if a specific feature (e.g. header part) cannot be
expressed via markdown, document the post-generation splice in a code
comment so the fixture is reproducible.

If the `docx_replace_headers.docx` fixture proves hard to assemble in
this task, defer the header-scope E2E case (T-docx-replace-happy may
suffice for R5 in early development) and re-add it in 006-04. The
20-case count gives 4 cases of slack.

**Plan-review MAJ-1 closure — R11.e N/A:** TASK §5 RTM row R11
enumerates R11.a–R11.e with R11.e = "canary saboteur tests if
applicable (docx-1 had none)". docx-6 inherits the docx-1 testing
conventions verbatim and likewise ships **no canary saboteur tests**.
R11.e is therefore declared **N/A** for the docx-6 chain; no test
artifact corresponds to it. Documented here so PLAN.md RTM Coverage
Matrix's "R11.e — N/A" entry has its source of truth.

**Plan-review MAJ-2 closure — Stub-First Red state observable:**
`self.fail()` (NOT `unittest.skip`) makes the Red bar visible to CI;
`DOCX6_STUBS_ENABLED` env flag for the E2E gate lets the default CI
run stay exit-0 while developers and PR reviewers can opt into the
expect-fail cadence. As Phase-2 sub-tasks land, individual
`self.fail()` lines flip to real assertions and the Red bar shrinks
monotonically. Convention: each `self.fail()` message names the
downstream sub-task that turns it green.

RTM coverage: **R11.a, R11.b, R11.c, R11.d, R11.e (declared N/A here)**.
