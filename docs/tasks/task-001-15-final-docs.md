# Task 2.10 [R10]: [LOGIC IMPLEMENTATION] Final docs polish + skill-validator + golden-diff strategy

## Use Case Connection
- I4.2 (Skill docs + reference).
- m-5 (golden-diff via `lxml.etree.tostring(method='c14n')`).
- A-Q3 (PLAN-internal canonicalisation).
- RTM: R10.

## Task Goal
Replace the 1.05 doc-stubs with finalised content now that the implementation has converged: SKILL.md is updated with the real CLI signature; `references/comments-and-threads.md` documents the OOXML data model + the C1/M-1 pitfalls in detail; `examples/comments-batch.json` is exercised by an example invocation in SKILL.md §11; goldens exist in `tests/golden/outputs/` with a `c14n`-based diff harness.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

- **§2 Capabilities:** Final phrasing for the comment-insertion bullet (replace 1.05 stub).
- **§4 Script Contract:** Final CLI signature with all flags from §2.5.
- **§10 Quick Reference:** Two rows added (one for single-cell, one for batch):
  - `| Insert single comment | python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --cell A5 --author "..." --text "..." [--threaded] |`
  - `| Batch comments from xlsx-7 findings | python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --batch findings.json --default-author "..." |`
- **§11 Examples (Few-Shot):** Add a new example showing the xlsx-7 → xlsx-6 pipeline (echo a tiny envelope JSON, pipe through xlsx-6, mention `--default-author`).
- **§12 Resources:** Final hyperlinks to `[scripts/xlsx_add_comment.py]` and `[references/comments-and-threads.md]`.

#### File: `skills/xlsx/references/comments-and-threads.md`

Replace 1.05's stub sections with full content:

**§1 Part graph** — reproduce ARCHITECTURE.md §4's ER diagram (or a simplified version) and explain part-naming (`commentsN`, `threadedComments<M>`, `vmlDrawingK` are independent counters; `personList.xml` is workbook-scoped).

**§2 Cell-syntax reference** — `A5`, `Sheet2!B5`, `'Q1 2026'!A1`, `'Bob''s Sheet'!A1`. Note that lookup is case-sensitive and unqualified resolves to first-VISIBLE sheet (M2/M3 documented).

**§3 Pitfalls** — already complete from 1.05; minor polish (cross-link to ARCHITECTURE §4.2 invariants).

**§4 Honest scope (v1)** — final phrasing of R9.a–R9.g; cross-link to `tests/test_xlsx_add_comment.py::TestHonestScope` for the regression locks.

**§5 (NEW) Goldens diff strategy** — document the canonicalisation:
> Goldens are compared via `lxml.etree.tostring(method='c14n')` (NOT `c14n2` — c14n2 does not canonicalise attribute order, see m-5 architecture-review note). Volatile attributes — `<threadedComment id>` (UUIDv4 per R9.e) and `<threadedComment dT>` when not pinned via `--date` — are masked via XPath replace before comparison. Re-generation procedure: run xlsx_add_comment.py with `--date 2026-01-01T00:00:00Z` for determinism on the timestamp axis; `<threadedComment id>` always differs across runs and is masked, not regenerated.

#### File: `skills/xlsx/examples/comments-batch.json`

- Final version (already shipped in 1.05; no change unless the file format evolved during implementation).

#### File: `skills/xlsx/scripts/tests/golden/outputs/`

Generate the regression golden outputs by running the now-finished xlsx_add_comment.py against each input fixture with deterministic flags (`--date 2026-01-01T00:00:00Z`). Golden files:
- `clean-no-comments.golden.xlsx`
- `existing-legacy-preserve.golden.xlsx`
- `threaded.golden.xlsx`
- `multi-sheet.golden.xlsx`
- `idmap-conflict.golden.xlsx`

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Add a final `golden-diff` block that runs each test, then compares the produced output against the corresponding `.golden.xlsx` using a Python helper:

```python
# tests/_golden_diff.py
import sys, zipfile, re
from lxml import etree

VOLATILE_XPATH = ".//{http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments}threadedComment"

def canon_part(xml_bytes):
    """Mask volatile attrs, then c14n-serialise."""
    root = etree.fromstring(xml_bytes)
    for tc in root.iterfind(VOLATILE_XPATH):
        if "id" in tc.attrib: tc.attrib["id"] = "{MASKED}"
        # dT is masked only if it doesn't match the deterministic date marker
        if "dT" in tc.attrib and "2026-01-01" not in tc.attrib["dT"]:
            tc.attrib["dT"] = "MASKED"
    return etree.tostring(root, method="c14n")

def diff_xlsx(actual_path, golden_path):
    with zipfile.ZipFile(actual_path) as a, zipfile.ZipFile(golden_path) as g:
        # Compare matching part lists
        a_parts = set(a.namelist())
        g_parts = set(g.namelist())
        if a_parts != g_parts:
            return f"Part list differs: {a_parts ^ g_parts}"
        for part in sorted(a_parts):
            if not part.endswith(".xml") and not part.endswith(".rels"):
                continue  # skip binary parts (e.g. vbaProject.bin — checked separately)
            a_canon = canon_part(a.read(part))
            g_canon = canon_part(g.read(part))
            if a_canon != g_canon:
                return f"Part {part} differs"
    return None  # OK
```

### Component Integration
- `validate_skill.py` is the final external check. Must exit 0.
- The golden-diff helper is xlsx-6-local; not promoted to `office/` because it's xlsx-comment-specific (volatile-attribute mask is xlsx-6's contract).

## Test Cases

### End-to-end Tests
- **TC-E2E-T-golden-clean:** produced output for `T-clean-no-comments` matches `clean-no-comments.golden.xlsx` under canonical diff.
- Same for the other 4 goldens.
- **TC-E2E-validate-skill:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
- **TC-E2E-no-office-edits:** `diff -qr skills/xlsx/scripts/office skills/docx/scripts/office` produces no output (CLAUDE.md §2 cross-skill compliance).

### Unit Tests
- All previous tests stay green.
- New: `TestGoldenDiff.test_canon_part_masks_threaded_id`: load fixture XML with `<threadedComment id="{ABC...}">`; canon → id="{MASKED}".
- New: `TestGoldenDiff.test_canon_part_masks_unpinned_dT`: `<threadedComment dT="2099-12-31...">` (random year) → `dT="MASKED"`; `<threadedComment dT="2026-01-01T00:00:00Z">` → unchanged.

### Regression Tests
- Full suite: `bash tests/test_e2e.sh` exits 0.
- `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0.
- `office/tests` discover green.
- Cross-skill diff green.
- `validate_skill.py skills/xlsx` exits 0.

## Acceptance Criteria
- [ ] SKILL.md final updates land.
- [ ] `references/comments-and-threads.md` complete (5 sections).
- [ ] 5 golden output files generated and committed.
- [ ] Golden-diff helper passes 2 unit tests.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] No `office/` edits.
- [ ] All TASK §3 ACs (Acceptance Criteria) checked off — full traceability.
- [ ] **Update TASK §2.5 Exit codes table with both `DuplicateThreadedComment` (M-2 / ARCHITECTURE §6.2 — exit 2 envelope) AND `OutputIntegrityFailure` (2.08 paranoid post-validate — exit 1 IOError class)** so the user-facing reference matches the implemented surface (J-4 plan-review fix).
- [ ] Golden-diff block runs for exactly the 5 named goldens listed above; other E2E tests rely on exit-code + lxml-assertion only — canonical diff is for stable-shape outputs, not exit-code-error tests (m-C plan-review clarification).

## Notes
- After this task, the feature is **done**. The next step is the Code-Review gate (post-development) per `vdd-03-develop.md`.
- The 5 goldens are the minimum lock — adding more later is fine; the canonical diff makes them robust to harmless re-runs.
- m-5 c14n choice is the load-bearing decision in this task — wrong canonicalisation method would produce flaky goldens.
