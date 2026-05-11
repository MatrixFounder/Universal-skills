# Task 004.01: Package skeleton + ≤220-LOC shim + day-1 boundary gate

## Use Case Connection
- **All TASK Use Cases** — foundation task; every subsequent sub-task depends on this skeleton existing.

## Task Goal
Create the `json2xlsx/` package skeleton (7 files = 6 modules + `__init__.py`), the ≤ 220-LOC shim (`json2xlsx.py`), a placeholder `.AGENTS.md` block, and on day one prove the **cross-skill replication boundary is not violated** (`validate_skill.py` + eleven `diff -q` checks green). Every public function must `raise NotImplementedError("xlsx-2 stub — task-004-NN")` so Phase-1 E2E tests fail uniformly with a clear exception type (NOT `ImportError` / `TypeError` / `SyntaxError`).

**Closes AQ-4** — locks the public-helper symbol as `convert_json_to_xlsx` (NOT bare `convert`, to avoid namespace collision with the eventual xlsx-8 `convert_xlsx_to_json`).

## Changes Description

### New Files

- `skills/xlsx/scripts/json2xlsx.py` — ≤ 220-LOC shim. Re-imports the public surface (`main`, `_run`, `convert_json_to_xlsx`, plus exception classes) from the `json2xlsx` package. Includes the `if __name__ == "__main__": sys.exit(main())` entrypoint. **LOC count enforced by test (TC-UNIT-03).**

- `skills/xlsx/scripts/json2xlsx/__init__.py` — ≤ 60 LOC. Re-exports `main`, `_run`, the exception hierarchy (`_AppError`, 9 typed subclasses — stub-imported from `exceptions.py`), **AND owns the body of the public helper** `convert_json_to_xlsx(input_path, output_path, **kwargs) -> int`. The body builds an argv list from kwargs (flag name = `"--" + key.replace("_", "-")`) and calls `main(argv)`. **Single source of truth — plan-reviewer #3 lock.** The shim (`json2xlsx.py`) only re-exports this function; it does NOT contain a function body for `convert_json_to_xlsx`.

- `skills/xlsx/scripts/json2xlsx/exceptions.py` — STUB. Defines `class _AppError(Exception): pass` and 9 placeholder subclasses (`EmptyInput`, `NoRowsToWrite`, `JsonDecodeError`, `UnsupportedJsonShape`, `InvalidSheetName`, `TimezoneNotSupported`, `InvalidDateString`, `SelfOverwriteRefused`, `PostValidateFailed`). All subclass `pass`. Full attribute model (`message`, `code`, `error_type`, `details`) is implemented in 004.03. Module-level TODO header `# TODO(task-004-03): typed-error attribute model + envelope wiring`.

- `skills/xlsx/scripts/json2xlsx/loaders.py` — STUB. Defines `read_input(path, encoding="utf-8")` and `detect_and_parse(raw, source, *, is_jsonl_hint)` both raising `NotImplementedError("xlsx-2 stub — task-004-04")`.

- `skills/xlsx/scripts/json2xlsx/coerce.py` — STUB. Defines `coerce_cell(value, opts, *, ctx)` raising `NotImplementedError("xlsx-2 stub — task-004-05")`. Also stub `@dataclass(frozen=True) class CellPayload` / `CoerceOptions` / `CellContext` with `pass` body (full attribute list landed in 004.05).

- `skills/xlsx/scripts/json2xlsx/writer.py` — STUB. Defines `write_workbook(parsed, output, *, freeze=True, auto_filter=True, sheet_override=None, coerce_opts=None)` raising `NotImplementedError("xlsx-2 stub — task-004-06")`. Also stub `_validate_sheet_name(name)` raising same.

- `skills/xlsx/scripts/json2xlsx/cli_helpers.py` — STUB. Defines `assert_distinct_paths(input_path, output_path)`, `post_validate_enabled()`, `run_post_validate(output)`, `read_stdin_utf8()` all raising `NotImplementedError("xlsx-2 stub — task-004-03")`.

- `skills/xlsx/scripts/json2xlsx/cli.py` — STUB. Defines `build_parser()`, `main(argv=None)`, `_run(args)`. `main` raises `NotImplementedError("xlsx-2 stub — task-004-07")`. `build_parser` returns a minimal argparse parser exposing only positional `input`/`output` and `--help` (so TC-E2E-01 below works); full flag set lands in 004.07.

- `skills/xlsx/scripts/json2xlsx/__init__.py` re-export contract (locked here so 004.07 doesn't churn):
  - `convert_json_to_xlsx` (public helper — AQ-4 lock).
  - `main`, `_run` (CLI surface).
  - `_AppError` + 9 typed exception classes.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/.AGENTS.md`

- Append a new section `## json2xlsx/ — JSON → styled .xlsx (xlsx-2)` with a placeholder body that lists the 7 module names + one-line responsibilities. Body expanded in 004.09 with the final post-merge module map.

### Component Integration

The shim serves as the user-visible CLI entrypoint and as the test-import gateway (E2E `test_e2e.sh` invokes `python3 json2xlsx.py …`; unit tests `import json2xlsx`). Internal package modules use sibling-relative imports (`from .exceptions import _AppError`); the shim does NOT import from the package directly during stub phase — it just exposes `main` for argparse routing. Day-1 validator gate ensures no accidental `office/` / `_soffice.py` / `_errors.py` / `preview.py` / `office_passwd.py` imports slip in.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01:** `python3 skills/xlsx/scripts/json2xlsx.py --help` returns exit 0; stdout contains "usage:" and "input" and "output".
   - Note: `--help` short-circuits argparse before `main()` is called, so `NotImplementedError` does not fire.
2. **TC-E2E-02:** `python3 skills/xlsx/scripts/json2xlsx.py any.json out.xlsx` exits 1 (or 2 for argparse type errors); stderr contains the substring `NotImplementedError`. **Stub-First red state confirmation.**

### Unit Tests
1. **TC-UNIT-01:** Import smoke — `python -c "import json2xlsx; from json2xlsx import cli, exceptions, loaders, coerce, writer, cli_helpers; from json2xlsx.cli import main"` exits 0.
2. **TC-UNIT-02:** Public surface present — `from json2xlsx import convert_json_to_xlsx, main, _run, _AppError, EmptyInput, NoRowsToWrite, JsonDecodeError, UnsupportedJsonShape, InvalidSheetName, TimezoneNotSupported, InvalidDateString, SelfOverwriteRefused, PostValidateFailed` exits 0.
3. **TC-UNIT-03:** Shim LOC count ≤ 220 (excluding blank lines + comments). Use `awk '!/^\s*$/ && !/^\s*#/' skills/xlsx/scripts/json2xlsx.py | wc -l` and assert.
4. **TC-UNIT-04:** All 9 exception classes inherit from `_AppError`: `for c in (EmptyInput, NoRowsToWrite, …): assert issubclass(c, _AppError)`.

### Regression Tests
- Run all xlsx unit tests: `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests`. **MUST pass** — xlsx-6 / xlsx-7 / csv2xlsx tests unchanged by this task.
- Run `bash skills/xlsx/scripts/tests/test_e2e.sh` — existing blocks green; new xlsx-2 block does not exist yet (added in 004.02).

## Acceptance Criteria

- [ ] All 8 new files created (1 shim + 7 package files including `__init__.py`).
- [ ] Every public stub raises `NotImplementedError("xlsx-2 stub — task-004-NN")` with the exact phrasing.
- [ ] Shim LOC count ≤ 220 (verified by TC-UNIT-03).
- [ ] `.AGENTS.md` placeholder section added.
- [ ] No `requirements.txt` change (zero new deps per TASK C1 / ARCH §6).
- [ ] xlsx-6 / xlsx-7 / csv2xlsx tests pass unchanged (regression gate).
- [ ] **CLAUDE.md §2 boundary day-1 gate:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0 — catches accidental shared-module imports on day one, not only at chain's end.
- [ ] **Cross-skill `diff -q` × 11** (ARCH §9 + TASK §9) all silent.

## Notes

- Do NOT implement any logic in this task — that is what later tasks are for. The point is that **the structure exists and tests fail in a uniform, expected way**.
- This task is the precondition for 004.02 (test scaffolding), 004.03 (cross-cutting), and all subsequent tasks.
- Symbol-naming convention (`convert_json_to_xlsx` rather than `convert`) is **non-negotiable** in this chain — it closes AQ-4 explicitly. Future xlsx-8 task will use `convert_xlsx_to_json`. csv2xlsx's existing `convert()` is unchanged.
