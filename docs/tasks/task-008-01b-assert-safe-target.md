# Task 008-01b: `_assert_safe_target` + path-traversal unit tests (F16)

## Use Case Connection
- Security primitive supporting **UC-1** + **UC-2** + **UC-3** (called from F12 + F13 starting in 008-02 / 008-03).

## Task Goal
Implement the F16 security primitive `_assert_safe_target` in `_relocator.py`. Reject malicious `Target` values from `insert/word/_rels/document.xml.rels` — absolute paths, drive letters, `..` segments, or paths that resolve outside `base/word/`. Each reject branch populates `details.reason` with a fixed token (`absolute_or_empty` / `drive_letter` / `parent_segment` / `outside_base`).

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/_relocator.py`

**Function `_assert_safe_target`:**
Replace stub body with full F16 implementation per ARCH §12.4 / §12.6:
```python
def _assert_safe_target(target: str, base_tree_root: Path) -> None:
    """F16 — Raise Md2DocxOutputInvalid if Target is unsafe.

    Rejects:
    - Empty / absolute (starts with '/') / backslash-bearing paths
      → details.reason = 'absolute_or_empty'
    - Paths with a drive letter (Windows-style)
      → details.reason = 'drive_letter'
    - Paths containing '..' segments
      → details.reason = 'parent_segment'
    - Paths resolving outside base_tree_root/word/
      → details.reason = 'outside_base'
    """
    if not target or target.startswith("/") or "\\" in target:
        raise Md2DocxOutputInvalid(
            f"insert rels Target is invalid or absolute: {target!r}",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"target": target, "reason": "absolute_or_empty"},
        )
    if re.match(r"^[A-Za-z]:", target):
        raise Md2DocxOutputInvalid(
            f"insert rels Target has a drive letter: {target!r}",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"target": target, "reason": "drive_letter"},
        )
    if any(p == ".." for p in Path(target).parts):
        raise Md2DocxOutputInvalid(
            f"insert rels Target contains '..' segments: {target!r}",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"target": target, "reason": "parent_segment"},
        )
    candidate = (base_tree_root / "word" / target).resolve()
    base_word = (base_tree_root / "word").resolve()
    if not candidate.is_relative_to(base_word):
        raise Md2DocxOutputInvalid(
            f"insert rels Target resolves outside base/word/: {target!r}",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"target": target, "reason": "outside_base"},
        )
```

#### File: `skills/docx/scripts/tests/test_docx_relocator.py`

**Class `TestAssertSafeTarget`:** UNSKIP the 5 stub tests (remove `@unittest.skip(...)` decorator) and implement bodies:

1. `test_relative_target_ok`:
   ```python
   tmpdir = Path(self.mkdtemp())
   (tmpdir / "word").mkdir()
   # Should not raise.
   _assert_safe_target("media/img.png", tmpdir)
   _assert_safe_target("charts/chart1.xml", tmpdir)
   ```

2. `test_absolute_path_rejected`:
   ```python
   with self.assertRaises(Md2DocxOutputInvalid) as ctx:
       _assert_safe_target("/etc/passwd", tmpdir)
   self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")
   ```
   Also test empty string `""` → same reason. Also test `\\server\share\f.png` → same reason.

3. `test_parent_segment_rejected`:
   ```python
   with self.assertRaises(Md2DocxOutputInvalid) as ctx:
       _assert_safe_target("../../etc/passwd", tmpdir)
   self.assertEqual(ctx.exception.details["reason"], "parent_segment")
   ```
   Also test `media/../../../etc/passwd` → same reason. Also test `../foo` → same reason.

4. `test_drive_letter_rejected`:
   ```python
   with self.assertRaises(Md2DocxOutputInvalid) as ctx:
       _assert_safe_target("C:/Windows/system32/cmd.exe", tmpdir)
   self.assertEqual(ctx.exception.details["reason"], "drive_letter")
   ```
   Also test `D:nofile.txt` (drive letter no slash) → same reason.

5. `test_outside_base_rejected`:
   ```python
   # Symlink trick: word/ has a symlink that escapes base.
   tmpdir = Path(self.mkdtemp())
   (tmpdir / "word").mkdir()
   escape = tmpdir.parent / "escape_target"
   escape.mkdir(exist_ok=True)
   (tmpdir / "word" / "linked").symlink_to(escape, target_is_directory=True)
   with self.assertRaises(Md2DocxOutputInvalid) as ctx:
       _assert_safe_target("linked/escape.png", tmpdir)
   self.assertEqual(ctx.exception.details["reason"], "outside_base")
   ```

### Component Integration
- `_assert_safe_target` is invoked from `_merge_relationships` (F12) starting in 008-02 and `_copy_nonmedia_parts` (F13) starting in 008-03. NO wiring change in this sub-task — only the primitive lands.

## Test Cases

### Unit Tests
1. **TC-UNIT-01..05:** 5 `TestAssertSafeTarget.*` tests (see above).

### End-to-end Tests
- **None** in this sub-task. `T-docx-insert-after-path-traversal` lands in 008-07 (after F12 + F13 wire `_assert_safe_target` into the call path).

### Regression Tests
- All 109 unit tests (108 existing docx-6 + 1 import-boundary from 008-01a) must remain green.
- All 24 existing T-docx-* E2E cases must remain green.

## Acceptance Criteria
- [ ] `_assert_safe_target` body matches ARCH §12.4 F16 + §12.8 contract.
- [ ] Four `details.reason` tokens populated correctly: `absolute_or_empty`, `drive_letter`, `parent_segment`, `outside_base`.
- [ ] 5 `TestAssertSafeTarget.*` tests unskipped and green.
- [ ] All previous tests still green (no regression).

## Verification Commands
```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest tests.test_docx_relocator.TestAssertSafeTarget -v
./.venv/bin/python -m unittest discover -s tests
bash tests/test_e2e.sh
```

## Notes
- This task is **deliberately small (~30 LOC + 50 LOC of tests)** to land the security primitive before any caller wires it. The path-traversal E2E (`T-docx-insert-after-path-traversal`) is gated to 008-07 because it requires F12+F13 wiring.
- `Path.is_relative_to` requires Python ≥ 3.9. Existing docx-6 scripts already assume this; no version bump needed.
- Use `tempfile.TemporaryDirectory` (mixed in via `unittest.TestCase` + `self.mkdtemp()` helper) for test isolation — symlinks must clean up.
- **DO NOT** add the test helper `self.mkdtemp()` to a shared base class in this sub-task. Inline `tempfile.mkdtemp()` calls + manual cleanup in `tearDown` is acceptable for 5 tests; the refactor to a base class can be a 008-08 polish item if needed.
