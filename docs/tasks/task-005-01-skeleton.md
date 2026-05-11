# Task 005.01: Skeleton — package scaffolding + shim + validator gate

## Use Case Connection
- UC-1 (HAPPY PATH) — skeleton must allow `import md_tables2xlsx` and `python3 md_tables2xlsx.py --help` to succeed.
- UC-2 (stdin) — argparse `INPUT` positional accepts `-` from day 1.
- UC-4 (same-path) — argparse parses two positionals; same-path-guard logic lands in 005.03.

## Task Goal

Create the on-disk skeleton for the xlsx-3 deliverable: a ≤ 60 LOC
shim `skills/xlsx/scripts/md_tables2xlsx.py` and a 10-module package
`skills/xlsx/scripts/md_tables2xlsx/` where every module exists but
every public function raises `NotImplementedError("xlsx-3 stub —
task-005-NN")`. The shim re-exports the public surface from
`md_tables2xlsx.__init__`. After this task, `python3 -c "import
md_tables2xlsx"` succeeds, `python3 md_tables2xlsx.py --help` prints
a help message (or raises `NotImplementedError` at the
`build_parser` stub), `validate_skill.py skills/xlsx` exits 0, and
the eleven `diff -q` cross-skill replication checks remain silent.

## Changes Description

### New Files

- `skills/xlsx/scripts/md_tables2xlsx.py` — ≤ 60 LOC shim, re-exports `main`, `_run`, `convert_md_tables_to_xlsx`, all `_AppError` subclasses from `md_tables2xlsx` package; `sys.path.insert(0, str(Path(__file__).resolve().parent))` so the package can resolve `_errors` (4-skill replicated sibling).
- `skills/xlsx/scripts/md_tables2xlsx/__init__.py` — ≤ 70 LOC; re-exports the symbols listed above; `convert_md_tables_to_xlsx` is a STUB at this point (raises `NotImplementedError`) but its signature is locked: `def convert_md_tables_to_xlsx(input_path: str | Path, output_path: str | Path, **kwargs: object) -> int` per ARCH M4.
- `skills/xlsx/scripts/md_tables2xlsx/loaders.py` — ≤ 180 LOC budget; module skeleton with function signatures and docstrings, all bodies `raise NotImplementedError("xlsx-3 stub — task-005-04")`.
- `skills/xlsx/scripts/md_tables2xlsx/tables.py` — ≤ 220 LOC budget; signatures locked; `_HTML_PARSER` module-level singleton constructed at import (so M1 lock is testable from day 1).
- `skills/xlsx/scripts/md_tables2xlsx/inline.py` — ≤ 100 LOC budget; stubs.
- `skills/xlsx/scripts/md_tables2xlsx/coerce.py` — ≤ 150 LOC budget; stubs + `@dataclass(frozen=True) class CoerceOptions: coerce: bool = True; encoding: str = "utf-8"`.
- `skills/xlsx/scripts/md_tables2xlsx/naming.py` — ≤ 130 LOC budget; `class SheetNameResolver` skeleton with `__init__` + `resolve` stub.
- `skills/xlsx/scripts/md_tables2xlsx/writer.py` — ≤ 200 LOC budget; stubs + 4 style constants COPIED from `csv2xlsx.py` with `# Mirrors csv2xlsx.py — keep visually identical.` comment.
- `skills/xlsx/scripts/md_tables2xlsx/cli_helpers.py` — ≤ 80 LOC budget; stubs.
- `skills/xlsx/scripts/md_tables2xlsx/cli.py` — ≤ 280 LOC budget; argparse parser construction can land here in stub form (sufficient to run `--help`); `_run` and `main` are STUBS.
- `skills/xlsx/scripts/md_tables2xlsx/exceptions.py` — ≤ 90 LOC budget; 8 `_AppError` subclass STUBS (full bodies in 005.03 — but the class definitions exist now so `from md_tables2xlsx import NoTablesFound` succeeds).
- `skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md` — placeholder block per `skill-update-memory` convention; first paragraph names the package and its 10 modules; subsequent blocks populated in 005.10.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/.AGENTS.md` (top-level scripts dir)

- Add a placeholder entry pointing to `md_tables2xlsx/.AGENTS.md` (one line, mirrors how `json2xlsx/` was added in Task-004.01).

#### File: `skills/xlsx/SKILL.md`

- **No changes in this task.** Full SKILL.md update lands in 005.10.

### Component Integration

The shim is the only Python entry point external code touches. It
sits at the same directory level as `csv2xlsx.py`, `json2xlsx.py`,
`xlsx_add_chart.py`, etc. Internal modules are isolated under
`md_tables2xlsx/` and cannot collide with any other CLI's modules.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-skeleton-importable):** `python3 -c "import md_tables2xlsx; print(md_tables2xlsx.convert_md_tables_to_xlsx)"` exits 0 and prints `<function convert_md_tables_to_xlsx at ...>`. The function body raises `NotImplementedError` when called — but importing must succeed.
2. **TC-E2E-02 (T-skeleton-help):** `python3 skills/xlsx/scripts/md_tables2xlsx.py --help` exits 0 and prints usage including `INPUT`, `OUTPUT`, `--json-errors`, `--no-coerce`, `--no-freeze`, `--no-filter`, `--allow-empty`, `--sheet-prefix`, `--encoding`. (argparse `--help` works even when `_run` is a stub.)

### Unit Tests

1. **TC-UNIT-01 (TestPublicSurface):** `from md_tables2xlsx import main, _run, convert_md_tables_to_xlsx` + all 8 `_AppError` subclasses succeeds. Each is callable / type-importable.
2. **TC-UNIT-02 (TestPublicSurface):** `inspect.signature(convert_md_tables_to_xlsx)` matches `(input_path: str | Path, output_path: str | Path, **kwargs: object) -> int` (ARCH M4 lock — pin signature day 1).
3. **TC-UNIT-03 (TestPublicSurface):** Module-level `tables._HTML_PARSER` is an `lxml.etree.HTMLParser` instance with `no_network is True`, `huge_tree is False`. (ARCH M1 lock — pin parser construction day 1.)

### Regression Tests

- Run existing tests from `skills/xlsx/scripts/tests/`. Existing csv2xlsx / json2xlsx / xlsx-6 / xlsx-7 tests must continue to pass (no shared code edited).
- Drift-detection scaffold: `import csv2xlsx` and `from json2xlsx.writer import HEADER_FILL` succeed (they will be the drift-detection counterparties in 005.02).

## Acceptance Criteria

- [ ] All 11 new files created (shim + 10 package files + `.AGENTS.md` placeholder).
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks from ARCH §9 silent.
- [ ] TC-E2E-01, TC-E2E-02, TC-UNIT-01, TC-UNIT-02, TC-UNIT-03 pass.
- [ ] No unrelated tests fail (regression gate).
- [ ] `wc -l skills/xlsx/scripts/md_tables2xlsx.py` ≤ 60.
- [ ] `wc -l skills/xlsx/scripts/md_tables2xlsx/__init__.py` ≤ 70.

## Notes

This is the **day-1 boundary gate** task. The validator must be
green and the eleven `diff -q` checks must be silent BEFORE the
test scaffolding in 005.02 lands — otherwise any cross-skill
replication drift will be misattributed to a later task. Time-box
this task to ~2 hours; if `validate_skill.py` complains about
anything beyond the expected (file presence / per-skill structural
checks), STOP and escalate rather than working around the
complaint.
