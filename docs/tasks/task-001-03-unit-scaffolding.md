# Task 1.03: [STUB CREATION] Unit-test scaffolding (`tests/test_xlsx_add_comment.py`)

## Use Case Connection
- I1.1, I1.2, I1.3, I1.4, I1.5, I2.1, I2.3, I4.1.
- RTM: prepares R1, R2, R3, R4, R6, R8, R9 verification.

## Task Goal
Create `skills/xlsx/scripts/tests/test_xlsx_add_comment.py` — Python `unittest` module with all unit-test names declared as `class TestX(unittest.TestCase): def test_Y(...): ...`. Each test body begins with `self.skipTest("Implemented in task 2.NN")`. After this task `python3 -m unittest discover -s tests` reports skips, NOT failures, so the regression suite stays green throughout Stage 1.

## Changes Description

### New Files
- `skills/xlsx/scripts/tests/test_xlsx_add_comment.py` — ≥ 30 test names, organised by component (F2 cell parser, F3 batch loader, F4 OOXML editor, F5 merged resolver, plus honest-scope locks).

### Concrete test class layout

```python
import unittest
class TestCellSyntaxParser(unittest.TestCase):
    def test_simple_a1(self): self.skipTest("2.02")
    def test_qualified_sheet(self): self.skipTest("2.02")
    def test_quoted_sheet_with_space(self): self.skipTest("2.02")
    def test_apostrophe_escape(self): self.skipTest("2.02")
    def test_invalid_cell_ref(self): self.skipTest("2.02")
    def test_unknown_sheet_includes_available(self): self.skipTest("2.02")
    def test_case_mismatch_includes_suggestion(self): self.skipTest("2.02")  # M3
    def test_first_visible_skips_hidden(self): self.skipTest("2.02")  # M2
    def test_no_visible_sheet_envelope(self): self.skipTest("2.02")  # M2

class TestPartCounter(unittest.TestCase):
    def test_counter_starts_at_1_when_empty(self): self.skipTest("2.03")
    def test_counter_independent_for_comments_and_vml(self): self.skipTest("2.03")
    def test_counter_uses_max_plus_1(self): self.skipTest("2.03")

class TestIdmapScanner(unittest.TestCase):  # M-1
    def test_scalar_data_attr(self): self.skipTest("2.03")
    def test_list_data_attr_returns_all_integers(self): self.skipTest("2.03")  # M-1 fix
    def test_workbook_wide_union(self): self.skipTest("2.03")

class TestSpidScanner(unittest.TestCase):  # C1
    def test_scans_all_vml_parts(self): self.skipTest("2.03")
    def test_returns_max_plus_1_baseline(self): self.skipTest("2.03")

class TestPersonRecord(unittest.TestCase):
    def test_uuidv5_stable_on_displayName(self): self.skipTest("2.05")
    def test_providerId_literal_None_string(self): self.skipTest("2.05")
    def test_userId_casefold_strasse(self): self.skipTest("2.05")  # m-1
    def test_dedup_case_sensitive_displayName(self): self.skipTest("2.05")  # m5

class TestAuthorsDedup(unittest.TestCase):
    def test_case_sensitive_identity(self): self.skipTest("2.04")  # m5

class TestBatchLoader(unittest.TestCase):
    def test_flat_array_shape(self): self.skipTest("2.06")
    def test_envelope_shape(self): self.skipTest("2.06")
    def test_envelope_missing_findings_key(self): self.skipTest("2.06")
    def test_envelope_skips_group_findings_with_row_null(self): self.skipTest("2.06")
    def test_size_cap_pre_parse(self): self.skipTest("2.06")  # m2/m-4

class TestMergedResolver(unittest.TestCase):
    def test_anchor_passes_through(self): self.skipTest("2.07")
    def test_non_anchor_raises_default(self): self.skipTest("2.07")
    def test_non_anchor_redirects_with_flag(self): self.skipTest("2.07")

class TestSamePathGuard(unittest.TestCase):
    def test_identical_path_exits_6(self): self.skipTest("2.01")
    def test_symlink_resolves_to_same_path(self): self.skipTest("2.01")

class TestHonestScope(unittest.TestCase):
    def test_HonestScope_no_parentId(self): self.skipTest("2.09")  # R9.a
    def test_HonestScope_plain_text_body(self): self.skipTest("2.09")  # R9.b
    def test_HonestScope_default_vml_anchor(self): self.skipTest("2.09")  # R9.c
    def test_HonestScope_threadedComment_id_is_uuidv4(self): self.skipTest("2.09")  # R9.e
    def test_HonestScope_no_unpacked_dir_flag(self): self.skipTest("2.09")  # R9.g
    def test_HonestScope_no_default_initials_flag(self): self.skipTest("2.09")  # R9.f

if __name__ == "__main__":
    unittest.main()
```

### Component Integration
- Tests live in `skills/xlsx/scripts/tests/` next to existing `test_e2e.sh`. Run via `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests`.
- The Python `tests/` directory needs `__init__.py` if it doesn't exist (check; existing `office/tests/` has one).

## Test Cases

### End-to-end Tests
*(not in this task — see 1.02)*

### Unit Tests
- See class layout above. Total ≥ 30 names; all skipped during Stage 1.

### Regression Tests
- `office/tests/` (existing) MUST stay green: `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s office/tests`.

## Acceptance Criteria
- [ ] `tests/test_xlsx_add_comment.py` exists with ≥ 30 named test methods organised in classes per component.
- [ ] Every test body begins with `self.skipTest("<task ID>")`.
- [ ] `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` reports `OK (skipped=N)` (where N matches the test count) — NO failures.
- [ ] No imports of unfinished helpers fail at import time (use `from xlsx_add_comment import ...` only inside `setUp` or test methods).
- [ ] Existing `office/tests/` regression stays green.
- [ ] No edits to `skills/docx/scripts/office/` (CLAUDE.md §2).

## Notes
- Test names embed RTM/M/m references in comments so the developer can grep for an issue when implementing.
- Skipping (not red) keeps the harness green during Stage 1 — Stage 2 tasks remove the `skipTest` line and add the assertion body.
