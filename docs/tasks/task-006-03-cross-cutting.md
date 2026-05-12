# Task 006-03: Cross-cutting pre-flight (F1) + CLI skeleton

## Use Case Connection
- **UC-1, UC-2, UC-3, UC-4** — every UC depends on the cross-cutting pre-flight (same-path, encryption, macro, stdin cap).
- **G1 gate** — cross-3/4/5/7 all green for `docx_replace.py` at end of this task.

## Task Goal

Land `docx_replace.py` with:
- F1 pre-flight helpers: `_assert_distinct_paths`,
  `_read_stdin_capped`, `_tempdir`.
- CLI skeleton: `build_parser` (all 7 flags registered, mutex group
  present), `main` entrypoint, `_run` with **pre-flight only** —
  action dispatch raises `NotImplementedError("docx-6 stub —
  task-006-04/05/06")`.
- Cross-cutting wiring: `assert_not_encrypted` (cross-3),
  `warn_if_macros_will_be_dropped` (cross-4), cross-5 envelope via
  `add_json_errors_argument` + `report_error`, cross-7 same-path
  guard (symlink-aware via `Path.resolve(strict=False)`).

At end of task: the **cross-cutting E2E cases** (T-docx-replace-same-path,
T-docx-replace-encrypted, T-docx-replace-macro-warning,
T-docx-replace-envelope-shape, T-docx-replace-action-mutex,
T-docx-insert-after-empty-stdin part 1 — stdin cap, T-docx-replace-help-honest-scope partial) turn GREEN.

## Changes Description

### New Files

- **`skills/docx/scripts/docx_replace.py`** — NEW. Initial body:
  - Module docstring + `from __future__ import annotations`.
  - Imports:
    ```python
    import argparse
    import contextlib
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    from typing import Iterator

    from lxml import etree
    from docx.oxml.ns import qn

    from _errors import add_json_errors_argument, report_error
    from docx_anchor import (
        _is_simple_text_run, _rpr_key, _merge_adjacent_runs,
        _replace_in_run, _concat_paragraph_text,
        _find_paragraphs_containing_anchor,
    )
    from office import unpack, pack
    from office._encryption import assert_not_encrypted, EncryptedFileError
    from office._macros import warn_if_macros_will_be_dropped
    ```
  - **F1 functions:**
    - `_assert_distinct_paths(input_path: Path, output_path: Path) -> None`
      — resolve both with `strict=False`; raise
      `SelfOverwriteRefused` (exit 6) if equal.
    - `_read_stdin_capped(max_bytes: int = 16 * 1024 * 1024) -> bytes`
      — read `sys.stdin.buffer.read(max_bytes + 1)`; raise
      `InsertSourceTooLarge` (exit 2) if length > `max_bytes`.
    - `_tempdir(prefix: str = "docx_replace-")` — `@contextlib.contextmanager`
      wrapper around `tempfile.TemporaryDirectory(prefix=prefix)`;
      yields `Path(tmp)`; cleanup on exception.
  - **Typed `_AppError` subclasses** (mirrors docx-1 / xlsx-2 pattern;
    each carries `message`, `code`, `error_type`, `details`):
    ```python
    class _AppError(Exception):
        def __init__(self, message, *, code, error_type, details=None):
            super().__init__(message)
            self.message = message
            self.code = code
            self.error_type = error_type
            self.details = details or {}

    class AnchorNotFound(_AppError): pass
    class SelfOverwriteRefused(_AppError): pass
    class InsertSourceTooLarge(_AppError): pass
    class EmptyInsertSource(_AppError): pass
    class Md2DocxFailed(_AppError): pass
    class Md2DocxOutputInvalid(_AppError): pass
    class Md2DocxNotAvailable(_AppError): pass
    class LastParagraphCannotBeDeleted(_AppError): pass
    class NotADocxTree(_AppError): pass
    class PostValidateFailed(_AppError): pass
    ```
  - **F7 skeleton:**
    - `build_parser() -> argparse.ArgumentParser` — register positional
      INPUT/OUTPUT, mutex group `{--replace, --insert-after,
      --delete-paragraph}` (required=True at this stage), `--anchor`,
      `--all`, `--unpacked-dir`, `--json-errors` (via
      `add_json_errors_argument`). `--help` text includes the four
      honest-scope notes from TASK §3.4 (R8.j).
    - `main(argv: list[str] | None = None) -> int` — parses argv; on
      `SystemExit` from argparse, surface as exit code 2; else call
      `_run`; catch `_AppError` → `report_error(...)`; catch
      `FileNotFoundError` / `OSError` → direct `report_error(code=1,
      error_type="FileNotFound" | "IOError", ...)` per "platform-IO
      errors" PLAN note.
    - `_run(args) -> int` — at this task's scope, do ONLY:
      1. Library mode dispatch placeholder: if `args.unpacked_dir`,
         raise `NotImplementedError("library mode (UC-4) —
         task-006-07b")`. (Full library-mode logic — ARCH §F7 step 1
         MAJ-1 dispatch-FIRST + UsageError + NotADocxTree — lands in
         006-07b; 006-07a leaves this placeholder in place.)
      2. Cross-7: `_assert_distinct_paths(args.input, args.output)`.
      3. Cross-3: `assert_not_encrypted(args.input)`.
      4. Cross-4: `warn_if_macros_will_be_dropped(args.input)`.
      5. Raise `NotImplementedError("docx-6 stub — action dispatch
         lands in task-006-04/05/06")` — happy-path E2E cases will
         continue to SKIP until those tasks land.

### Changes in Existing Files

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Un-skip** the `TestCrossCutting` class (≥ 6 cases) and write live
  test bodies:
  - `test_assert_distinct_paths_raises_on_collision` —
    `_assert_distinct_paths("a.docx", "a.docx")` raises
    `SelfOverwriteRefused`.
  - `test_assert_distinct_paths_follows_symlinks` — `tmp_path` setup
    with `b.docx` symlinked to `a.docx`; `_assert_distinct_paths
    ("a.docx", "b.docx")` raises `SelfOverwriteRefused`.
  - `test_read_stdin_capped_raises_on_overflow` — patch
    `sys.stdin.buffer` to a `BytesIO` of `16 * 1024 * 1024 + 1`
    bytes; `_read_stdin_capped()` raises `InsertSourceTooLarge` with
    `details["max_bytes"]==16*1024*1024`,
    `details["actual_bytes"]>=16*1024*1024+1`.
  - `test_read_stdin_capped_accepts_at_limit` — exactly `16 MiB`
    succeeds.
  - `test_tempdir_cleans_up_on_exception` — `with _tempdir() as p:
    raise RuntimeError("x")` raises but `p.exists()` is False afterwards.
  - `test_main_argparse_usage_error_returns_envelope` — `main(["--invalid"])`
    with `--json-errors` in argv → exit 2 + cross-5 envelope on stderr.
- **Un-skip and live** `TestCli::test_build_parser_7_flags` —
  `build_parser()` has positional INPUT/OUTPUT, `--anchor`, mutex
  group with 3 actions, `--all`, `--unpacked-dir`, `--json-errors`
  (7 user-facing flags + 2 positionals).
- **Note:** `TestCli::test_unpacked_dir_forbids_positional` stays
  `self.fail("docx-6 stub — to be implemented in task-006-07b")` in
  this task — the full library-mode logic (including the positional
  mutex check) lands in 006-07b per plan-review MIN-1 split.
  Argparse currently accepts both forms; the `_run` placeholder
  raises `NotImplementedError("library mode (UC-4) — task-006-07b")`
  early.

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Un-SKIP cross-cutting cases (T-docx-replace-same-path,
  T-docx-replace-encrypted, T-docx-replace-macro-warning,
  T-docx-replace-envelope-shape, T-docx-replace-action-mutex,
  T-docx-replace-help-honest-scope partial). Each invocation now
  runs `python3 docx_replace.py ...` and asserts exit code / stderr
  match.

### Component Integration

`docx_replace.py` is now an importable Python module. `--help` works
end-to-end (argparse). The cross-cutting layer is callable from
external code; action dispatch is the only remaining stub.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-replace-same-path):** `python3 docx_replace.py a.docx a.docx --anchor x --delete-paragraph` exits 6 with cross-5 envelope `{type: "SelfOverwriteRefused"}` when `--json-errors`.
2. **TC-E2E-02 (T-docx-replace-encrypted):** Encrypted fixture (use an existing one from `tests/fixtures/` if present, else generate via `office_passwd.py`) → exit 3 `EncryptedFileError`.
3. **TC-E2E-03 (T-docx-replace-macro-warning):** `.docm` fixture → stderr warning (cross-4); then `NotImplementedError` (since action body not yet implemented); exit code is whatever the stub raises (typically 1 with envelope). The test asserts the WARNING is emitted before the stub failure.
4. **TC-E2E-04 (T-docx-replace-envelope-shape):** Any failure with `--json-errors` → single-line JSON on stderr with keys `{v, error, code, type, details}`.
5. **TC-E2E-05 (T-docx-replace-action-mutex):** Two of `{--replace, --insert-after, --delete-paragraph}` → argparse rejects → exit 2 `UsageError`.
6. **TC-E2E-06 (T-docx-replace-help-honest-scope):** `python3 docx_replace.py --help` exits 0 AND output contains substrings: "single-run", "image", "last paragraph", "blast-radius" (per TASK §3.4 R8.j).

### Unit Tests

1. **TC-UNIT-01 (TestCrossCutting, 6 cases):** All listed in "Changes" section above pass.
2. **TC-UNIT-02 (TestCli::test_build_parser_7_flags):** Argparse surface pinned.
3. **(deferred to 006-07b)** `TestCli::test_unpacked_dir_forbids_positional` stays `self.fail("...task-006-07b")`.

### Regression Tests

- G4: docx-1 E2E suite passes unchanged.
- All 12 `diff -q` cross-skill replication checks silent.
- `test_docx_anchor.py` ≥ 20 cases still green.

## Acceptance Criteria

- [ ] `docx_replace.py` exists; `--help` runs and prints honest-scope notes.
- [ ] All 6 cross-cutting E2E cases listed in TC-E2E-01..06 pass.
- [ ] `TestCrossCutting` ≥ 6 unit cases pass.
- [ ] `TestCli::test_build_parser_7_flags` passes; `TestCli::test_unpacked_dir_forbids_positional` stays Red (`self.fail`) until 006-07b.
- [ ] G4 regression: docx-1 E2E block passes unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.
- [ ] `wc -l skills/docx/scripts/docx_replace.py` ≤ 250 (≈ F1 + F7-skeleton allotment per ARCH §3.2).

## Notes

The `--unpacked-dir` mutex with positional INPUT/OUTPUT is enforced
in `_run` step 1 (NOT via argparse), because argparse cannot express
"either both positionals OR --unpacked-dir but not both". The check is
explicit: `if args.unpacked_dir is not None and (args.input is not
None or args.output is not None): raise UsageError(...)`.

The mutex group on the three action flags uses
`parser.add_mutually_exclusive_group(required=True)` — argparse handles
the "exactly one" enforcement. The "required=True" means EVERY
invocation must specify an action; `docx_replace.py file.docx out.docx`
without an action exits 2 via argparse usage error (T-docx-replace-action-mutex
covers two-actions-set; this case covers zero-actions-set — both
return exit 2).

For T-docx-replace-help-honest-scope, the literal strings checked are
the substrings, not full sentences, so help text wording can evolve
without test fragility. The R8.j requirement is that `--help`
*mentions* the four honest-scope items; we don't gate on exact phrasing.

If the stdin cap test (`test_read_stdin_capped_raises_on_overflow`)
proves flaky due to memory pressure during test setup (allocating
16 MiB of test bytes), use `b"\0" * (16 * 1024 * 1024 + 1)` or
`io.BytesIO` with a custom `.read()` that returns the byte count
without materializing the payload.

RTM coverage: **R7.a, R7.b, R7.c, R7.d, R7.e, R7.f, R2.h, R8.h** (cross-cutting + stdin-cap + json-errors flag).
