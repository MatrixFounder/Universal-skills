# Task 002.2: Create `xlsx_comment/` package skeleton

## Use Case Connection
- I1 — Add the `xlsx_comment/` directory with all module stubs.

## Task Goal
Create the empty `xlsx_comment/` package next to
`xlsx_add_comment.py`. Every target module is created as an empty
stub (1-line docstring + `pass`) so the package is importable but
holds no logic yet. Tests still run against the **unchanged**
`xlsx_add_comment.py`.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_comment/__init__.py` — 1-line docstring,
  no symbols (Q4=A from ARCHITECTURE §8 — near-empty).
- `skills/xlsx/scripts/xlsx_comment/constants.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/exceptions.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/cell_parser.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/batch.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/ooxml_editor.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/merge_dup.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/cli_helpers.py` — empty stub.
- `skills/xlsx/scripts/xlsx_comment/cli.py` — empty stub.

Each stub file contains exactly:

```python
"""<one-line description per ARCHITECTURE §3.2 row>."""
```

(Per Stage 1, NO `pass`, NO `__all__` yet — those land per-module
in Tasks 002.3 / 002.4 / etc. as each region migrates in.)

The `__init__.py` is similarly:

```python
"""xlsx_comment — internal package backing skills/xlsx/scripts/xlsx_add_comment.py."""
```

### Changes in Existing Files
*(none in this task — `xlsx_add_comment.py` is untouched)*

## Steps

1. `mkdir skills/xlsx/scripts/xlsx_comment`.
2. Create the 9 stub files listed above. Use the exact 1-line
   docstring per ARCHITECTURE §3.2 row 1's "Public API (selected)"
   column phrasing as the file-level summary (or a tighter version):
   - `constants.py` → `"""XML namespaces, content-types, and editor-wide constants."""`
   - `exceptions.py` → `"""Typed `_AppError` subclasses raised across the xlsx_comment package."""`
   - `cell_parser.py` → `"""Cell-syntax parser and sheet resolver (F2)."""`
   - `batch.py` → `"""--batch input loader: BatchRow + load_batch (F3)."""`
   - `ooxml_editor.py` → `"""OOXML scanners, part-counter, rels/CT, legacy/threaded writers (F4)."""`
   - `merge_dup.py` → `"""Merged-cell resolver and duplicate-cell matrix (F5)."""`
   - `cli_helpers.py` → `"""Pure utilities used by cli.py: validation, date, post-pack guard, etc."""`
   - `cli.py` → `"""argparse + main + single_cell_main + batch_main (F1+F6)."""`
3. **Verify the package imports clean:**
   ```bash
   cd skills/xlsx/scripts && ./.venv/bin/python -c "import xlsx_comment" \
       && ./.venv/bin/python -c "import xlsx_comment.cli" \
       && ./.venv/bin/python -c "import xlsx_comment.ooxml_editor" \
       ; cd ../../..
   ```
   All three should succeed (exit 0, no output).
4. **Run the existing test suite — must remain green** (this is the
   regression guard — adding empty modules must not break anything):
   ```bash
   cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests \
       2>&1 | tail -3; cd ../../..
   bash skills/xlsx/scripts/tests/test_e2e.sh 2>&1 | tail -3
   ```
   Both must end with `OK` / pass count matching baseline.
5. **Run skill validator** (R6.a foreshadow — guard against empty
   `__init__.py` shenanigans):
   ```bash
   python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx
   ```
   Must exit 0.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Run `bash skills/xlsx/scripts/tests/test_e2e.sh`. Must produce
  the same OK count as `pre_e2e_ok_count` from the Task 002.1 baseline.
- **Note:** No new E2E test added in this task; the regression check
  IS the E2E.

### Unit Tests
- **TC-UNIT-01:** `python3 -c "import xlsx_comment"` exits 0.
- **TC-UNIT-02:** `python3 -c "from xlsx_comment import cli, ooxml_editor, exceptions, constants, cell_parser, batch, merge_dup, cli_helpers"` exits 0 (verifies all 8 implementation stubs are valid Python).

### Regression Tests
- All 75 existing unit tests pass (zero edits to test files).
- All 112 E2E checks pass.
- `validate_skill.py skills/xlsx` exits 0.

## Acceptance Criteria
- [ ] Directory `skills/xlsx/scripts/xlsx_comment/` exists.
- [ ] All 9 files exist (1 `__init__.py` + 8 implementation stubs).
- [ ] Each stub file is exactly 1 docstring statement (no `pass`,
      no `__all__`, no other content). Multi-physical-line wrapping of
      the docstring string is acceptable; what matters is that no
      additional Python statements are present. (m5 from plan-review
      clarification.)
- [ ] `python3 -c "import xlsx_comment.<each_module>"` exits 0 for all 8 implementation modules.
- [ ] Pre-refactor unit + E2E + validate_skill all still green.
- [ ] `git status` shows the new directory + 9 new files; nothing else.

## Notes
- This task is intentionally trivial (~10 min). Its purpose is to
  establish the package boundary in one atomic commit before any
  code starts moving in Task 002.3.
- The empty stubs intentionally have NO `pass` statement and NO
  `__all__` — Python accepts a docstring-only module. Adding `pass`
  would force the developer to remove it later when migrating
  symbols in.
- Per `artifact-management` SKILL, this task does NOT update
  `.AGENTS.md` (Task 002.11 is the single point that touches it).
