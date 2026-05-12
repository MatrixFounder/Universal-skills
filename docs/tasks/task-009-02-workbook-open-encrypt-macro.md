# Task 009-02: F1 `_workbook.py` — open + encrypt + macro + M8 spike [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-01** (open unencrypted workbook + alternative scenarios A1–A4).

## RTM Coverage
- **[R3]** `open_workbook` with cross-3 encryption probe, cross-4
  macro probe, openpyxl `read_only` heuristic, typed exceptions
  only — full implementation.

## Task Goal

Replace the `NotImplementedError` stub in
`skills/xlsx/scripts/xlsx_read/_workbook.py` with real logic that:
1. Probes the OPC archive for encryption **before** invoking
   openpyxl; raises `EncryptedWorkbookError` on detection (cross-3).
2. Probes for `vbaProject.bin` and emits `MacroEnabledWarning` via
   `warnings.warn` for `.xlsm`/`.xltm` (cross-4) — does **not**
   raise.
3. Decides `read_only` mode automatically when the input file size
   exceeds `size_threshold_bytes` (default 10 MiB); honors a
   caller-supplied `read_only_mode: bool | None` override (D-A6).
4. Returns a fully initialised `WorkbookReader` whose `close()`,
   `__enter__`, `__exit__` are correctly wired to the underlying
   openpyxl `Workbook`.
5. Lands the **M8 spike** (D-A8): one empirical test that opens a
   fixture with overlapping `<mergeCells>` and documents openpyxl's
   actual behaviour in the test docstring. Regardless of outcome,
   the library still raises `OverlappingMerges` (the detector is
   implemented in 009-04 — this task only commits the fixture +
   spike test for future use).

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/encrypted.xlsx` —
  password-protected workbook (any password; just needs the
  `EncryptedPackage` OPC part).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/macros.xlsm` —
  workbook with a trivial empty `vbaProject.bin`.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/large_5mib.xlsx` —
  ≥ 5 MiB workbook to test the size threshold boundary.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/overlapping_merges.xlsx`
  — hand-edited workbook with two intersecting `<mergeCells>` ranges
  (M8 spike fixture).
- `skills/xlsx/scripts/xlsx_read/tests/test_workbook.py` — unit +
  E2E tests for F1.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_workbook.py`
**Replace** the stubs with:
- `def open_workbook(path: Path, *, read_only_mode: bool | None =
  None, size_threshold_bytes: int = 10 * 1024 * 1024) ->
  WorkbookReader`:
  - Steps:
    1. `path = Path(path).resolve(strict=True)` — propagates
       `FileNotFoundError`.
    2. `_probe_encryption(path)` — raises `EncryptedWorkbookError`
       if `EncryptedPackage` stream present in OPC archive.
    3. `if _probe_macros(path): warnings.warn(...,
       MacroEnabledWarning)`.
    4. `ro = _decide_read_only(path, read_only_mode,
       size_threshold_bytes)`.
    5. `wb = openpyxl.load_workbook(path, read_only=ro, data_only=
       False, keep_links=False)`.
    6. `return WorkbookReader(path=path, _wb=wb, _read_only=ro)`.
- `def _probe_encryption(path: Path) -> None`:
  - Open with `zipfile.ZipFile(path, "r")`; if the namelist contains
    `"EncryptedPackage"` OR `"\\x06DataSpaces/DataSpaceMap"`, raise
    `EncryptedWorkbookError(f"Workbook is encrypted: {path}")`.
- `def _probe_macros(path: Path) -> bool`:
  - Return `True` iff `"xl/vbaProject.bin"` appears in
    `zipfile.ZipFile(path, "r").namelist()`.
- `def _decide_read_only(path: Path, override: bool | None,
  threshold: int) -> bool`:
  - If `override is not None`: return `override`.
  - Else: `return path.stat().st_size > threshold`.

#### File: `skills/xlsx/scripts/xlsx_read/_types.py` (UPDATE — append, not redefine)
- Update `WorkbookReader` to accept `_wb: openpyxl.Workbook` and
  `_read_only: bool` slots in `__init__`. Implement `close()` to
  call `self._wb.close()` exactly once (idempotent). Wire
  `__enter__` to `return self`; `__exit__` to `self.close()`.

#### File: `skills/xlsx/scripts/xlsx_read/tests/test_smoke_stub.py`
**Update** TC-UNIT-04: the line asserting `open_workbook` raises
`NotImplementedError` is **removed** (it now succeeds on the empty
fixture). Add a positive assertion: `open_workbook(FIXTURES_DIR /
"empty.xlsx")` returns a `WorkbookReader` instance whose `close()`
is callable.

### Component Integration

`_workbook.py` is the **only** entry point exposed by `__init__.py`
to construct a `WorkbookReader`. Subsequent modules (`_sheets`,
`_merges`, ...) operate on the `wb` attribute internally but
**never** import `_workbook.py` itself (banned-api remains green).

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_workbook.py`)

1. **TC-E2E-01 (open_unencrypted):** `open_workbook
   (FIXTURES_DIR / "empty.xlsx")` returns a `WorkbookReader`;
   `reader.close()` succeeds; second `close()` is a no-op.
2. **TC-E2E-02 (open_encrypted):** `open_workbook(FIXTURES_DIR /
   "encrypted.xlsx")` raises `EncryptedWorkbookError` containing
   the path string.
3. **TC-E2E-03 (open_macro_warns):** With
   `warnings.catch_warnings(record=True) as w`, calling
   `open_workbook(FIXTURES_DIR / "macros.xlsm")` records **exactly
   one** `MacroEnabledWarning` and still returns a valid
   `WorkbookReader`.
4. **TC-E2E-04 (open_missing):** `open_workbook(FIXTURES_DIR /
   "nonexistent.xlsx")` raises `FileNotFoundError` (propagated
   unchanged).
5. **TC-E2E-05 (corrupted_zip):** Pass a non-zip text file —
   `zipfile.BadZipFile` propagates unchanged.
6. **TC-E2E-06 (read_only_auto_threshold):** Open
   `large_5mib.xlsx` with default threshold (10 MiB) →
   `reader._read_only == False`. Re-open with `size_threshold_bytes=
   1024` → `reader._read_only == True`.
7. **TC-E2E-07 (read_only_override):** Open `empty.xlsx` with
   explicit `read_only_mode=True` → `reader._read_only == True`
   regardless of size.
8. **TC-E2E-08 (context_manager):** `with open_workbook(...) as
   r:` succeeds; `r._wb` is closed after the block.

### Unit Tests

1. **TC-UNIT-01 (`_probe_encryption` positive):** Returns
   `None` for unencrypted workbook; raises for encrypted fixture.
2. **TC-UNIT-02 (`_probe_macros`):** Returns `True` for
   `macros.xlsm`, `False` for `empty.xlsx`.
3. **TC-UNIT-03 (`_decide_read_only`):** Truth-table coverage of
   `(override ∈ {None,True,False}) × (size ⋛ threshold)`.
4. **TC-UNIT-04 (no openpyxl in exceptions):** Capture the
   exception object from TC-E2E-02 and assert
   `not any('openpyxl' in repr(type(arg)) for arg in
   exc.args + (exc,))` — no leaky openpyxl types in the public
   exception surface.

### M8 Spike (TC-SPIKE-01 in `test_workbook.py`)

1. **TC-SPIKE-01 (openpyxl_overlapping_merges_behaviour):**
   - Open `overlapping_merges.xlsx` with `read_only=False`.
   - In the test docstring, record whether openpyxl: (a) raises on
     `load_workbook`, (b) silently accepts and exposes both ranges,
     or (c) silently coalesces. Whichever it is — capture in a
     docstring sentence: *"openpyxl 3.1.x behaviour on overlapping
     merges: {a|b|c} — verified 2026-MM-DD."*
   - The test itself **passes unconditionally** at this stage (the
     `OverlappingMerges` detector is implemented in 009-04). This
     test exists to inform that subsequent implementation.

### Regression Tests

- `test_smoke_stub.py` updated (TC-UNIT-04 only) — all other cases
  unchanged, still green.
- 12-line cross-skill `diff -q` — silent.

## Acceptance Criteria

- [ ] `_workbook.py` no longer raises `NotImplementedError` for any
  documented entry point.
- [ ] All 8 TC-E2E and 4 TC-UNIT cases pass.
- [ ] M8 spike test recorded openpyxl's actual behaviour in the
  test docstring.
- [ ] `WorkbookReader.close()` is idempotent (second call is no-op).
- [ ] `with open_workbook(...) as r:` works correctly.
- [ ] `ruff check skills/xlsx/scripts` green; `validate_skill.py
  skills/xlsx` exit 0; 12-line `diff -q` silent.

## Notes

- The "exception object contains no openpyxl types" regression
  test in TC-UNIT-04 is also part of the broader [R1] closed-API
  guarantee — it lives here because this task is the first one to
  raise a non-stub typed exception.
- `_probe_encryption` heuristic is **deliberately the same shape**
  as `office_passwd.py`'s detection but is **NOT imported from it**
  (CLAUDE.md §2 boundary — `office_passwd.py` is the OOXML 3-skill
  replicated file we MUST NOT touch from this task).
