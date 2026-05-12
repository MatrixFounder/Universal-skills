# Task 006-09: Final docs + backlog ✅ DONE + validator/replication gates

## Use Case Connection
- All UCs — final documentation lands.
- **G5, G6, G7, G8 gates** — validator exit 0; cross-skill `diff -q` silent; backlog row ✅ DONE; SKILL.md + `.AGENTS.md` updated.

## Task Goal

Close the docx-6 chain. Update documentation, mark the backlog row
✅ DONE with full status line, re-run the validator and cross-skill
`diff -q` checks. The DoD checklist below **explicitly enumerates
all 12 `diff -q` invocations** to close the "eleven vs twelve"
reconciliation flagged by NIT n1 (task-006-review) and ARCH §9.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/SKILL.md`

- **§1 Red Flags** — Add a new row if v1 ships behaviour that
  diverges from the docx-1 cookbook. Candidate rows:
  - "I'll just regex-replace `\|` in OOXML to extract text" — NO,
    use `docx_replace.py` (anchor-and-action surgical edit).
  - "I need to edit a `.docx` and a `docx2md → md2docx` round-trip
    loses styling" — use `docx_replace.py --replace` (run-level
    formatting preserved).
- **§2 Capabilities** — Add capability bullet:
  - `docx_replace.py` — surgical anchor-and-action edit of a `.docx`
    (replace / insert-after / delete-paragraph) without lossy
    `docx2md → md2docx` round-trip. Honest scope: single-run anchor
    for `--replace`; cross-run anchor for paragraph-level actions.
- **§4 Script Contract** — Add row to the script-contract table:
  - `docx_replace.py` — Tier B (script-first); positional INPUT
    OUTPUT; `--anchor TEXT`; one of `--replace`/`--insert-after`/
    `--delete-paragraph`; flags `--all`, `--unpacked-dir` (if
    landed), `--json-errors`; exit codes 0/1/2/3/6/7; stdin via
    `--insert-after -`.
- **Honest-scope notes** — Add 4 bullet points mirroring TASK §9
  §11.1–§11.4 if these are surfaced in SKILL.md's honest-scope
  section.

#### File: `skills/docx/scripts/.AGENTS.md`

- Add a new row for `docx_replace.py` AND `docx_anchor.py`. Mirror
  the existing format for `docx_add_comment.py` (each script gets a
  one-paragraph description + LOC + test count + last-modified
  timestamp).
- If a `.AGENTS.md` subsection exists for the docx-6 chain, add the
  11 sub-task IDs (006-01a, 006-01b, 006-02, 006-03, 006-04, 006-05,
  006-06, 006-07a, 006-07b, 006-08, 006-09) for traceability.

#### File: `docs/office-skills-backlog.md`

- Locate the `docx-6` row in §docx. Update its status column from
  "PENDING" / "DRAFT" to **✅ DONE**.
- Append a **status line** mirroring xlsx-3's cadence in the row:
  ```
  ✅ DONE 2026-05-NN: 11-task chain (006-01a..006-09 with
  006-07a + 006-07b split per plan-review MIN-1; mark 006-07b as
  "shipped" or "deferred to docx-6.4");
  docx_replace.py <LOC>/600 LOC; docx_anchor.py <LOC>/180 LOC;
  test_docx_replace.py <N> unit tests; test_docx_anchor.py <N> unit
  tests; tests/test_e2e.sh +<N> E2E cases.
  ```
- If UC-4 (`--unpacked-dir` library mode) was deferred (006-07a left
  < 40 LOC headroom; see 006-07b deferral path), add a NEW backlog
  row `docx-6.4 — library mode for docx_replace.py` and reference
  the deferral here. Otherwise mark 006-07b as shipped within the
  main docx-6 status line.

### Changes in NO files

- `office/` — UNTOUCHED throughout the chain.
- `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py` —
  UNTOUCHED throughout the chain.
- xlsx, pptx, pdf skill directories — UNTOUCHED.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (full E2E suite):** `bash skills/docx/scripts/tests/test_e2e.sh` exits 0. ALL docx-1, docx-2, …, docx-5 cases plus the ≥ 20 docx-6 cases pass.
2. **TC-E2E-02 (validator gate):** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx` exits 0.

### Unit Tests

1. **TC-UNIT-01 (full unit suite):** `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0. All docx-1..docx-5 tests + ≥ 20 + ≥ 30 docx-6 tests pass.

### Regression Tests

- All G4 (docx-1) tests pass unchanged.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria — DoD Checklist

### Documentation gates (G8)

- [ ] `skills/docx/SKILL.md` §1 Red Flags has at least one new row for the docx-6 use case.
- [ ] `skills/docx/SKILL.md` §2 Capabilities has the `docx_replace.py` bullet.
- [ ] `skills/docx/SKILL.md` §4 Script Contract has the `docx_replace.py` row.
- [ ] `skills/docx/scripts/.AGENTS.md` has rows for `docx_replace.py` AND `docx_anchor.py`.
- [ ] `--help` text (verified by running `python3 docx_replace.py --help`) documents the four honest-scope notes (R8.j).

### Backlog gate (G7)

- [ ] `docs/office-skills-backlog.md` row `docx-6` is ✅ DONE with status line including LOC and test counts.
- [ ] If UC-4 was deferred, NEW row `docx-6.4` added with rationale.

### Validator gate (G5)

- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx` exits 0.

### Cross-skill drift gate (G6) — eleven (actual 12) `diff -q` invocations all silent

Run all twelve manually (or via the script below) and verify ZERO output:

```bash
# Twelve invocations per CLAUDE.md §2 reconciliation (NIT n1 closure).

# (1) office/ tree — 3-skill OOXML (docx is master)
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
# (2) office/ tree — pptx replica
diff -qr skills/docx/scripts/office skills/pptx/scripts/office

# (3) _soffice.py — 4-skill (xlsx replica)
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
# (4) _soffice.py — pptx replica
diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py

# (5) _errors.py — xlsx replica (part of 4-skill)
diff -q skills/docx/scripts/_errors.py skills/xlsx/scripts/_errors.py
# (6) _errors.py — pptx replica
diff -q skills/docx/scripts/_errors.py skills/pptx/scripts/_errors.py
# (7) _errors.py — pdf replica (4-skill includes pdf even without office/)
diff -q skills/docx/scripts/_errors.py skills/pdf/scripts/_errors.py

# (8) preview.py — xlsx replica
diff -q skills/docx/scripts/preview.py skills/xlsx/scripts/preview.py
# (9) preview.py — pptx replica
diff -q skills/docx/scripts/preview.py skills/pptx/scripts/preview.py
# (10) preview.py — pdf replica
diff -q skills/docx/scripts/preview.py skills/pdf/scripts/preview.py

# (11) office_passwd.py — xlsx replica (3-skill OOXML; pdf has its own encryption)
diff -q skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
# (12) office_passwd.py — pptx replica
diff -q skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
```

- [ ] All **12** invocations produce no output (silent = identical).

> **Reconciliation note (NIT n1 closure):** the "eleven" label is
> inherited from arch-003 / arch-005 (xlsx-2, xlsx-3) and was kept in
> ARCH §9 and TASK G6 for narrative continuity. The actual invocation
> count is **12** as enumerated above. The semantics of the gate (all
> invocations silent) are unambiguous regardless of the count.

### Test gates

- [ ] `bash skills/docx/scripts/tests/test_e2e.sh` exits 0.
- [ ] `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0.
- [ ] G4 regression: docx-1 E2E block passes unchanged (count assertion: same number of PASS lines as pre-chain).
- [ ] G1 cross-cutting: all cross-3/4/5/7 cases green.
- [ ] G2 RTM coverage: every R1–R12 sub-feature has ≥ 1 test (verify by tagging tests with the RTM ID in a docstring; cross-reference via PLAN.md RTM Coverage Matrix).
- [ ] G3 honest-scope locks: R10.a–R10.e + Q-U1 + A4 TOCTOU all live (not skipped).

### LOC budget compliance

- [ ] `wc -l skills/docx/scripts/docx_replace.py` ≤ 600 (or ≤ 350 if `_actions.py` extracted).
- [ ] `wc -l skills/docx/scripts/docx_anchor.py` ≤ 180.

## Notes

This task is **documentation-only** in terms of production code —
no `.py` files outside of test scaffolding are modified here (the
test suite was already complete in 006-08).

The DoD checklist above is the **single source of truth** for the
merge decision. Every box must be checked before the chain can be
declared complete. If any check fails, escalate:

1. **G4 regression failure** — revert 006-01a immediately.
2. **G5 validator failure** — investigate; common causes are missing
   `__init__.py`, missing `SKILL.md` heading levels, or a
   newly-introduced file with disallowed permissions.
3. **G6 `diff -q` non-silent** — IMMEDIATELY revert the file that
   diverged. The chain MUST NOT modify `office/`, `_soffice.py`,
   `_errors.py`, `preview.py`, or `office_passwd.py`. If a developer
   accidentally edited one, restore byte-identity from the
   `skills/docx/scripts/...` master copy via:
   ```bash
   for s in xlsx pptx pdf; do
       cp skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
       cp skills/docx/scripts/preview.py skills/$s/scripts/preview.py
   done
   # plus office/, _soffice.py, office_passwd.py per CLAUDE.md §2
   ```
4. **G7 backlog miss** — `office-skills-backlog.md` row not updated.
5. **G8 docs miss** — `SKILL.md` or `.AGENTS.md` row missing.

The reconciliation note in DoD G6 closes NIT n1 (task-006-review)
and the architecture-reviewer's MIN-1 (planner handoff).

After this task is closed, the docx-6 chain is **MERGEABLE**. The
chain can ship as a single PR (11-task atomic chain, or 10-task if
006-07b is deferred to `docx-6.4`) or as a
sub-tree of 10 commits — the choice is the developer's, but the merge
is gated on ALL DoD boxes being checked.

RTM coverage: **R12.a, R12.b, R12.c, R12.d, R12.e, R12.f**.
