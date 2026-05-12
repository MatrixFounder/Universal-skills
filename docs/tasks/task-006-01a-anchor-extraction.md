# Task 006-01a: `docx_anchor.py` extraction + import refactor (byte-identical, all-green)

## Use Case Connection
- **Indirect** — UC-1, UC-2, UC-3 all depend on anchor helpers that this task extracts to a shared module. UC-4 also depends transitively.
- **G4 regression gate** — `docx_add_comment.py` E2E suite passes unchanged after refactor.

## Task Goal

Extract the three anchor-finding helpers (`_is_simple_text_run`,
`_rpr_key`, `_merge_adjacent_runs`) **byte-identically** from
`skills/docx/scripts/docx_add_comment.py` into a new docx-only sibling
module `skills/docx/scripts/docx_anchor.py`. Refactor
`docx_add_comment.py` to `from docx_anchor import ...`. **No behaviour
change.** No new test stubs in this sub-task (architecture-reviewer
MAJ-2 fix: G4 gate is evaluated on green helpers only).

End-state:
- `docx_anchor.py` exists with the 3 extracted functions (≤ 90 LOC at
  this point; additional helpers added in 006-02).
- `docx_add_comment.py` imports them from `docx_anchor` (-45 LOC net).
- Existing docx-1 E2E suite (`tests/test_e2e.sh` docx-1 block) passes
  unchanged.
- `validate_skill.py skills/docx` exits 0.
- All 12 `diff -q` cross-skill replication checks silent.

## Changes Description

### New Files

- `skills/docx/scripts/docx_anchor.py` — NEW. Module docstring + module-
  level `lxml.etree` + `docx.oxml.ns.qn` imports + the 3 extracted
  functions verbatim (BYTE-IDENTICAL bodies; only the imports preamble
  is new). ≤ 90 LOC after extraction; ≤ 180 LOC budget after 006-02.

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_add_comment.py`

**Remove:**
- `def _rpr_key(run: etree._Element) -> bytes: ...` (existing line ~155).
- `def _is_simple_text_run(run: etree._Element) -> bool: ...` (existing line ~160).
- `def _merge_adjacent_runs(paragraph: etree._Element) -> None: ...` (existing line ~177).

**Add (single import line):**
```python
from docx_anchor import _is_simple_text_run, _rpr_key, _merge_adjacent_runs
```

Place the import near other intra-package imports (between `from _errors import ...` and the first internal helper block). Net LOC delta: -45.

### Component Integration

`docx_anchor.py` lives in `skills/docx/scripts/` (sibling to `docx_add_comment.py`, NOT under `office/`). This preserves the cross-skill replication boundary from `CLAUDE.md §2`: the new module is docx-only and out-of-scope of the `office/` 3-skill replication and the 4-skill `_errors.py`/`preview.py`/`_soffice.py` replication.

`docx_add_comment.py` continues to call `_is_simple_text_run`, `_rpr_key`, `_merge_adjacent_runs` exactly as before — only the import path changes.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (G4 regression):** `bash skills/docx/scripts/tests/test_e2e.sh` — the docx-1 block must pass with **zero changes**. Capture exit code; must be 0. (Run AFTER refactor; if any case that previously passed now fails, revert immediately.)

### Unit Tests

1. **TC-UNIT-01 (extraction byte-identity):** `python3 -c "from docx_anchor import _is_simple_text_run, _rpr_key, _merge_adjacent_runs; print(_is_simple_text_run, _rpr_key, _merge_adjacent_runs)"` exits 0 and prints 3 function objects.
2. **TC-UNIT-02 (`docx_add_comment.py` still works):** `python3 skills/docx/scripts/docx_add_comment.py --help` exits 0 and prints the unchanged help text.
3. **TC-UNIT-03 (no behavioural drift):** Re-run the existing `tests/test_battery.py` (docx-1 unit-level battery if present). Must report unchanged pass count.

### Regression Tests

- **All existing docx skill tests** — `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0 with unchanged pass count.
- **Cross-skill `diff -q`** — all 12 invocations from CLAUDE.md §2 silent (this task touches neither `office/` nor 4-skill replicated files).

## Acceptance Criteria

- [ ] `skills/docx/scripts/docx_anchor.py` exists with 3 functions extracted byte-identically (verify with `diff` of function bodies).
- [ ] `skills/docx/scripts/docx_add_comment.py` no longer defines these 3 functions; imports them from `docx_anchor` instead.
- [ ] `wc -l skills/docx/scripts/docx_anchor.py` ≤ 90 (full ≤ 180 cap reserved for 006-02 additions).
- [ ] `wc -l skills/docx/scripts/docx_add_comment.py` ↓ by ~45 LOC vs. pre-refactor.
- [ ] `bash skills/docx/scripts/tests/test_e2e.sh` exits 0 with the docx-1 block passing unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

This is the **G4 gating refactor** — its sole purpose is to ship the
shared module so 006-02 can add new helpers and 006-04..06 can consume
them without each having to declare its own copy.

The byte-identity invariant is checked manually: pre-refactor, grab
the exact source bytes of the 3 function bodies with `sed -n`; post-
refactor, run the same `sed -n` against `docx_anchor.py` and compare.
A 1-line whitespace drift (e.g. trailing blank line removed) is OK
provided the function bodies themselves are unchanged.

If the existing `docx_add_comment.py` test suite goes red, **STOP**
and revert. Do NOT debug the helpers — the only reason this should
fail is if the import path is broken (e.g. `_errors.py`-style
`sys.path` insertion is needed). Mirror the pattern from
`docx_add_comment.py`'s own `from _errors import ...` line.

RTM coverage: **R6.a, R6.b, R6.c**.
