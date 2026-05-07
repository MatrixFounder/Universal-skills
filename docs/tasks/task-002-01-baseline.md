# Task 002.1: Capture pre-refactor baseline (regression anchor)

## Use Case Connection
- I9 — Test-suite full-pass evidence (baseline half — see also Task 002.10 for delta verification).

## Task Goal
Establish the **regression anchor** for Task 002. Capture the green
test state, the canonical re-export grep, the `--help` byte form, and
golden-file hashes **before** any code is moved. Every subsequent
migration task verifies "delta vs this baseline = 0".

## Changes Description

### New Files
- `docs/reviews/task-002-baseline.txt` — single text file with the
  baseline artefacts. Format: a sequence of section headers (`==
  <name> ==`) followed by raw command output. Created by the
  developer agent during Task 002.1 execution; consumed by Task
  002.10's delta verification.

### Changes in Existing Files
*(none in this task — read-only evidence capture)*

## Steps

> **Working directory:** `skills/xlsx/scripts/` (use `cd` once at the
> top of the shell session). All commands below assume that CWD.

1. **Activate the venv** (per CLAUDE.md §1 package management):
   `source .venv/bin/activate` (or use `./.venv/bin/python` directly).

2. **Capture pre-refactor file size** (so Task 002.9 can verify
   `wc -l xlsx_add_comment.py` after the shim reduction):
   ```bash
   echo "== pre_xlsx_add_comment_loc ==" > docs/reviews/task-002-baseline.txt
   wc -l skills/xlsx/scripts/xlsx_add_comment.py >> docs/reviews/task-002-baseline.txt
   ```
   *(Run from repo root — adjust paths if running from `skills/xlsx/scripts/`.)*

3. **Capture canonical 35-symbol re-export grep** (the source of
   truth for TASK §2.5 R3.a):
   ```bash
   echo "== pre_test_imports_canonical ==" >> docs/reviews/task-002-baseline.txt
   grep -hE "from xlsx_add_comment import" \
       skills/xlsx/scripts/tests/test_xlsx_add_comment.py | \
       sed 's/^[[:space:]]*//' | sort -u \
       >> docs/reviews/task-002-baseline.txt
   echo "== pre_test_imports_symbols ==" >> docs/reviews/task-002-baseline.txt
   awk '/from xlsx_add_comment import \(/, /\)/ {print} /^[[:space:]]*from xlsx_add_comment import / {print}' \
       skills/xlsx/scripts/tests/test_xlsx_add_comment.py | \
       grep -oE '\b[A-Za-z_][A-Za-z0-9_]+\b' | \
       grep -vE '^(from|import|xlsx_add_comment)$' | sort -u \
       >> docs/reviews/task-002-baseline.txt
   ```
   Expected: 35-name set matching TASK §2.5 (constants 9 + exceptions
   10 + cell_parser 2 + batch 1 + ooxml_editor 9 + merge_dup 2 +
   cli_helpers 1 + cli 1 — note the constants count is 9 if R_NS is
   excluded; if R_NS is included it is 10). The exact list IS the
   contract.

4. **Capture `--help` output** (verbatim, byte-anchored for R2-style
   verification in 002.10):
   ```bash
   echo "== pre_help_output ==" >> docs/reviews/task-002-baseline.txt
   cd skills/xlsx/scripts && \
       ./.venv/bin/python xlsx_add_comment.py --help 2>&1 \
           >> ../../../docs/reviews/task-002-baseline.txt; \
       cd ../../..
   ```
   *Note: capture stderr too via `2>&1` so any deprecation warnings
   are also frozen — this is the byte-anchor.*

5. **Run the unit test suite, capture summary**:
   ```bash
   echo "== pre_unit_tests ==" >> docs/reviews/task-002-baseline.txt
   cd skills/xlsx/scripts && \
       ./.venv/bin/python -m unittest discover -s tests -v 2>&1 | \
       tail -20 >> ../../../docs/reviews/task-002-baseline.txt; \
       cd ../../..
   ```
   Expected tail: `Ran NN tests in X.YYZs` followed by `OK` (NN is
   ~75 per session-state). Record the full count.

6. **Run the E2E suite, capture OK count**:
   ```bash
   echo "== pre_e2e_tests ==" >> docs/reviews/task-002-baseline.txt
   bash skills/xlsx/scripts/tests/test_e2e.sh 2>&1 | tee /tmp/e2e_pre.log | \
       tail -20 >> docs/reviews/task-002-baseline.txt
   echo "== pre_e2e_ok_count ==" >> docs/reviews/task-002-baseline.txt
   grep -cE "^OK |^✓ |PASS" /tmp/e2e_pre.log >> docs/reviews/task-002-baseline.txt
   ```
   *Note: the OK-line pattern depends on the E2E script's output
   format. The developer adjusts `grep -E` to match the actual prefix
   (e.g. `[E2E] OK`, `PASS:`, `✓`). The captured count is the figure
   002.10 must reproduce exactly.*

7. **Capture golden-file hashes** for structural-diff regression
   reference:
   ```bash
   echo "== pre_golden_hashes ==" >> docs/reviews/task-002-baseline.txt
   find skills/xlsx/scripts/tests/golden -type f \( -name "*.xlsx" -o -name "*.xlsm" \) \
       -exec shasum -a 256 {} \; | sort \
       >> docs/reviews/task-002-baseline.txt
   ```
   These hashes are **expected to drift** if the refactor reformats
   any code that affects output bytes (it shouldn't — Q1=A locks
   `_xml_serialize` byte-equivalent). Task 002.10 distinguishes
   "golden bit-equal" (preferred) from "structural-diff zero" (ok if
   re-formatting is unavoidable).

8. **Capture cold-import latency baseline** (TASK NFR perf):
   ```bash
   echo "== pre_import_time ==" >> docs/reviews/task-002-baseline.txt
   cd skills/xlsx/scripts && \
       ./.venv/bin/python -X importtime -c "import xlsx_add_comment" 2>&1 | \
       tail -5 >> ../../../docs/reviews/task-002-baseline.txt; \
       cd ../../..
   ```
   The "self" column total of the last lines is the measurement; Task
   002.10 must be within ±20 % of this number.

9. **Capture `office/` byte-identity baseline** (TASK R6.e gate). **Spec correction (caught during 002.1 execution):** the office/ replication scope is **3 skills (docx → xlsx + pptx)**, NOT 4 — `skills/pdf/scripts/office/` does not exist (pdf does not use OOXML/LibreOffice and is not in CLAUDE.md §2's office-replication scope). The 4-skill scope applies to `_errors.py` + `preview.py` only; `office_passwd.py` is 3-skill (docx + xlsx + pptx).
   ```bash
   # Pre-clean __pycache__ so the diff is true byte-identity, not
   # build-artefact noise.
   find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
   echo "== pre_office_diff ==" >> docs/reviews/task-002-baseline.txt
   # 3-skill scope: docx (master) -> xlsx + pptx (mirrors). NOT pdf.
   for s in xlsx pptx; do
       diff -qr skills/docx/scripts/office skills/$s/scripts/office \
           >> docs/reviews/task-002-baseline.txt 2>&1 || true
   done
   echo "== pre_cross_skill_helpers ==" >> docs/reviews/task-002-baseline.txt
   # 4-skill scope: _errors.py + preview.py (incl. pdf).
   for s in xlsx pptx pdf; do
       diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py \
           >> docs/reviews/task-002-baseline.txt 2>&1 || true
       diff -q skills/docx/scripts/preview.py skills/$s/scripts/preview.py \
           >> docs/reviews/task-002-baseline.txt 2>&1 || true
   done
   # 3-skill scope: office_passwd.py (NOT pdf — pdf has its own
   # encryption via pypdf PdfWriter.encrypt; see CLAUDE.md §2 "3-skill replication").
   for s in xlsx pptx; do
       diff -q skills/docx/scripts/office_passwd.py skills/$s/scripts/office_passwd.py \
           >> docs/reviews/task-002-baseline.txt 2>&1 || true
   done
   ```
   Expected: every diff produces empty output (no differences). 002.10
   re-runs the same command and asserts identical empty result.

## Test Cases

### End-to-end Tests
*(none new — this task captures evidence from the existing suite)*

### Unit Tests
*(none new — this task is read-only)*

### Regression Tests
- The baseline file MUST contain non-empty output for every section
  header. An empty section indicates a captured-too-early failure
  (e.g. venv not activated, file paths wrong) and the task is NOT
  done until the section is populated.

## Acceptance Criteria
- [ ] `docs/reviews/task-002-baseline.txt` exists, ≥ 50 LOC, with all
      **11** section headers (m6 from plan-review fix):
      `pre_xlsx_add_comment_loc`, `pre_test_imports_canonical`,
      `pre_test_imports_symbols`, `pre_help_output`, `pre_unit_tests`,
      `pre_e2e_tests`, `pre_e2e_ok_count`, `pre_golden_hashes`,
      `pre_import_time`, `pre_office_diff`, `pre_cross_skill_helpers`.
- [ ] `pre_unit_tests` section ends with `OK`.
- [ ] `pre_e2e_ok_count` section is a positive integer ≥ 100 (per
      session-state "112 E2E").
- [ ] `pre_office_diff` and `pre_cross_skill_helpers` sections have
      no `differ` lines (i.e. office/ and the 3 cross-skill helpers
      are byte-identical across the four office skills).
- [ ] `pre_test_imports_symbols` lists exactly the symbol set
      documented in TASK §2.5 (developer should manually confirm 35
      names match).
- [ ] No code changes anywhere; `git status` shows only the new
      `docs/reviews/task-002-baseline.txt`.

## Notes
- This task does NOT count toward the LOC budget of any module — it
  produces a single evidence file outside the package.
- The baseline file is committed (R7.a "single self-contained PR")
  so reviewers can replay the comparison without re-running the suite.
- Estimated effort: 30 min (the slowest step is the E2E run, ~5 min).
