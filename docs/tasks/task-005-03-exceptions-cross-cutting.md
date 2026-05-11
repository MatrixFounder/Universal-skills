# Task 005.03: Exceptions + cross-cutting helpers (cross-5 + cross-7 + stdin)

## Use Case Connection
- UC-4 (same-path collision) — `assert_distinct_paths` exits 6.
- UC-2 (stdin pipe) — `read_stdin_utf8` is the single source of stdin decode.
- Cross-cutting parity for all UCs.

## Task Goal

Fill in `exceptions.py` with the 8 `_AppError` subclasses (full
bodies) and `cli_helpers.py` with cross-cutting helpers
(`assert_distinct_paths`, `post_validate_enabled`,
`run_post_validate` stub, `read_stdin_utf8`). After this task,
the **envelope-only** E2E cases (T-same-path → exit 6 envelope;
T-envelope-cross5-shape — argparse error → cross-5 envelope) turn
green. Logic-bearing tasks 005.04+ depend on the exception classes
already being callable.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/exceptions.py`

- Replace the 8 stub class bodies with full implementations. Each inherits from `_AppError(Exception)` (NOT a frozen dataclass; mirrors xlsx-2 `m1 fix` precedent).

```python
class _AppError(Exception):
    def __init__(self, message: str, *, code: int, error_type: str,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        self.details = details or {}
```

- 8 subclasses (each calls `super().__init__(...)` with locked `code` + `error_type`):
  - `EmptyInput` (code 2, type `EmptyInput`)
  - `NoTablesFound` (code 2, type `NoTablesFound`)
  - `MalformedTable` (code 2, type `MalformedTable`) — internal use, orchestrator usually maps to stderr warning
  - `InputEncodingError` (code 2, type `InputEncodingError`) — `details: {offset, source}`
  - `InvalidSheetName` (code 2, type `InvalidSheetName`) — `details: {original, reason}` or `{original, retry_cap, first_collisions}`
  - `SelfOverwriteRefused` (code 6, type `SelfOverwriteRefused`)
  - `PostValidateFailed` (code 7, type `PostValidateFailed`)
  - `NoSubstantialRowsAfterParse` (code 2, type `NoSubstantialRowsAfterParse`) — internal: emerges if every table parses to zero rows after coercion (very rare; honest-scope edge)

#### File: `skills/xlsx/scripts/md_tables2xlsx/cli_helpers.py`

- Fill 4 function bodies:

```python
def assert_distinct_paths(input_path: str, output_path: Path) -> None:
    """Cross-7 H1 same-path guard. Stdin sentinel bypasses."""
    if input_path == "-":
        return
    in_resolved = Path(input_path).resolve(strict=False)
    out_resolved = output_path.resolve(strict=False)
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(
            f"Input and output resolve to the same path: {in_resolved}",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": str(in_resolved), "output": str(out_resolved)},
        )

def post_validate_enabled() -> bool:
    """Truthy allowlist mirrors xlsx-2/xlsx-6."""
    raw = os.environ.get("XLSX_MD_TABLES_POST_VALIDATE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}

def run_post_validate(output: Path) -> tuple[bool, str]:
    """STUB until 005.09. Returns (True, '') in stub mode."""
    raise NotImplementedError("xlsx-3 stub — task-005-09")

def read_stdin_utf8() -> str:
    """Single source of stdin decode. Strict UTF-8 — raises UnicodeDecodeError on bad bytes."""
    return sys.stdin.buffer.read().decode("utf-8")
```

#### File: `skills/xlsx/scripts/md_tables2xlsx/__init__.py`

- Add re-exports for all 8 exception classes (so `from md_tables2xlsx import NoTablesFound` works).

### Component Integration

`cli.py` (still STUB) imports `assert_distinct_paths` AND
`read_stdin_utf8` (via `loaders.read_input`'s `-` dispatch — but
`loaders` is still STUB at this point; the wiring lands in 005.04).
For now, the `_run` STUB can directly call `assert_distinct_paths`
+ `report_error` to satisfy the T-same-path envelope test.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-same-path):** `python3 md_tables2xlsx.py /tmp/x.md /tmp/x.md --json-errors` exits 6 with stderr containing a single JSON envelope `{"v":1, "error": "Input and output resolve to the same path: ...", "code": 6, "type": "SelfOverwriteRefused", "details": {...}}`. (Test fixture creates `/tmp/x.md` first.)
2. **TC-E2E-02 (T-envelope-cross5-shape):** `python3 md_tables2xlsx.py --invalid-flag-that-does-not-exist --json-errors` (argparse usage error) exits 2 with stderr containing the envelope (`type: "UsageError"`).
3. **TC-E2E-03 (T-same-path-symlink):** Create `a.md`, `ln -s a.md b.md`, then `md_tables2xlsx.py a.md b.md --json-errors` → exit 6 (symlink follow via `Path.resolve()`).

### Unit Tests

1. **TC-UNIT-01 (TestExceptions::test_each_AppError_has_code_and_type):** For each of the 8 subclasses, instantiate with minimal args and assert `.code` and `.error_type` match the locked values.
2. **TC-UNIT-02 (TestExceptions::test_AppError_details_default_empty_dict):** `EmptyInput("msg", code=2, error_type="EmptyInput").details == {}`.
3. **TC-UNIT-03 (TestPublicSurface::test_post_validate_truthy_allowlist):** For each of `"1", "true", "TRUE", "yes", "on"` in env → `post_validate_enabled() is True`; for `"0", "false", "no", "off", ""` → `False`.
4. **TC-UNIT-04 (TestPublicSurface::test_assert_distinct_paths_stdin_bypasses):** `assert_distinct_paths("-", Path("/tmp/out.xlsx"))` returns None (no raise).
5. **TC-UNIT-05 (TestPublicSurface::test_assert_distinct_paths_same_path_raises):** `assert_distinct_paths("/tmp/x.md", Path("/tmp/x.md"))` raises `SelfOverwriteRefused` with `code=6`.
6. **TC-UNIT-06 (TestPublicSurface::test_read_stdin_utf8_strict):** Monkeypatch `sys.stdin.buffer` with bad UTF-8 bytes → `read_stdin_utf8()` raises `UnicodeDecodeError`.

### Regression Tests

- Existing skill tests still pass.

## Acceptance Criteria

- [ ] All 8 `_AppError` subclasses callable with locked `(code, error_type)` per the exit-code matrix (TASK §7).
- [ ] `assert_distinct_paths` follows symlinks via `Path.resolve()`.
- [ ] `read_stdin_utf8` is strict UTF-8 (raises on bad bytes).
- [ ] `post_validate_enabled` truthy allowlist exactly `{"1","true","yes","on"}` (case-insensitive after `.strip().lower()`).
- [ ] All 3 E2E + 6 unit tests above pass.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

`run_post_validate` is a STUB here on purpose — the subprocess-call
logic lands in 005.09 alongside the orchestrator wiring. The
`post_validate_enabled` truthy parser, however, IS fully
implemented here because it has zero dependencies and is trivial
to unit-test. Locking it day-one prevents 005.09 from re-litigating
the allowlist surface (a known xlsx-6/xlsx-2 round-2 NIT pattern).
