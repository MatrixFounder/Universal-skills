# Task 003.01: Package skeleton + ≤200-LOC shim + dependencies

## Use Case Connection
- **All TASK Use Cases** (this is the foundation — every subsequent task depends on this skeleton existing).

## Task Goal
Create the `xlsx_check_rules/` package skeleton (12 files = 11 modules + `__init__.py`), the ≤200-LOC shim (`xlsx_check_rules.py`), updated `requirements.txt`, and a placeholder `.AGENTS.md` block. **Every public function must `raise NotImplementedError("xlsx-7 stub — task-003-NN")`** so Phase-1 E2E tests fail uniformly with a clear exception type (NOT `ImportError` / `TypeError` / `SyntaxError`).

## Changes Description

### New Files

- `skills/xlsx/scripts/xlsx_check_rules.py` — ≤ 200-LOC shim. Re-imports a planned ~25-symbol test-compat surface from the package (target list locked here; minor adjustments allowed in 003.13–003.15 as final modules ship). Includes the `if __name__ == "__main__": sys.exit(main())` entrypoint.

- `skills/xlsx/scripts/xlsx_check_rules/__init__.py` — near-empty (≤ 10 LOC). Re-exports `main` for the shim.

- `skills/xlsx/scripts/xlsx_check_rules/constants.py` — STUB. Empty module with TODO header `# TODO(task-003-05): F-Constants impl`. Holds the single placeholder `__all__ = []`.

- `skills/xlsx/scripts/xlsx_check_rules/exceptions.py` — STUB. Empty module with TODO header `# TODO(task-003-05): F-Errors impl`. Holds `__all__ = []`.

- `skills/xlsx/scripts/xlsx_check_rules/ast_nodes.py` — STUB. `__all__ = []` + TODO `# TODO(task-003-06)`.

- `skills/xlsx/scripts/xlsx_check_rules/rules_loader.py` — STUB. Defines `load_rules_file(path) -> dict: raise NotImplementedError("xlsx-7 stub — task-003-09")`.

- `skills/xlsx/scripts/xlsx_check_rules/dsl_parser.py` — STUB. Defines `parse_check(text, depth=0)` and `parse_scope(text)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/cell_types.py` — STUB. Defines `classify(cell, opts)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/scope_resolver.py` — STUB. Defines `resolve_scope(scope_node, workbook, defaults)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/evaluator.py` — STUB. Defines `eval_rule(rule_spec, scope_result, ctx)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/aggregates.py` — STUB. Defines `eval_aggregate(call_node, scope_node, ctx)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/output.py` — STUB. Defines `emit_findings(findings, summary, opts, fp)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/remarks_writer.py` — STUB. Defines `write_remarks(...)` and `write_remarks_streaming(...)` raising `NotImplementedError`.

- `skills/xlsx/scripts/xlsx_check_rules/cli_helpers.py` — STUB. Empty module reserved for helpers extracted during 003.14.

- `skills/xlsx/scripts/xlsx_check_rules/cli.py` — STUB. Defines `build_parser()`, `parse_args(argv)`, `main(argv=None)` (which calls `_run`); `main` raises `NotImplementedError("xlsx-7 stub — task-003-14")`.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/requirements.txt`

- Bump `openpyxl>=3.1.0` → `openpyxl>=3.1.5` (R2 / SPEC §5.4.2 locale-format date detection).
- Add `regex>=2024.0` (per-cell timeout for §5.3.1).
- Add `python-dateutil>=2.8.0` (`--treat-text-as-date` fallback parser).
- Add `ruamel.yaml>=0.18.0` (YAML 1.2 hardening).
- **Do NOT add** `recheck` (D5 closure — JVM CLI, hand-coded fallback only).

#### File: `skills/xlsx/scripts/.AGENTS.md`

- Append a new section "## xlsx_check_rules/ — declarative rules-based validation (xlsx-7)" with a placeholder body that lists the 12 module names + one-line responsibilities. The body will be expanded in 003.17 with the final post-merge module map.

#### File: `THIRD_PARTY_NOTICES.md` (root)

- Add attribution stubs for `regex`, `python-dateutil`, `ruamel.yaml`. Body fleshed out with license texts in 003.17.

### Component Integration
The shim serves as the user-visible CLI entrypoint and as the test-import gateway. Internal package modules use sibling-relative imports (`from .exceptions import _AppError`); imports through the shim are forbidden inside the package.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01:** `python3 skills/xlsx/scripts/xlsx_check_rules.py --help` returns exit 0 with the full TASK §2.5 flag list.
   - Note: `--help` short-circuits before `main()` is called, so `NotImplementedError` does not fire.

2. **TC-E2E-02:** `python3 skills/xlsx/scripts/xlsx_check_rules.py any.xlsx --rules x.json` exits 1 (non-zero) because `main()` raises `NotImplementedError`. Stderr contains `NotImplementedError`. Stub-First red state.

### Unit Tests
1. **TC-UNIT-01:** Import smoke — `python -c "import xlsx_check_rules; from xlsx_check_rules import cli; from xlsx_check_rules.cli import main"` exits 0.
2. **TC-UNIT-02:** `from xlsx_check_rules.constants import *` works (empty `__all__`); same for exceptions / ast_nodes.
3. **TC-UNIT-03:** Shim LOC count ≤ 200 (excluding blank lines + comments). Use `awk '!/^\s*$/ && !/^\s*#/' skills/xlsx/scripts/xlsx_check_rules.py | wc -l`.

### Regression Tests
- Run all xlsx unit tests: `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests`. **MUST pass** — xlsx-6 tests are unchanged by this task.
- Run `bash skills/xlsx/scripts/tests/test_e2e.sh` — existing xlsx_add_comment block green; new xlsx_check_rules block does not exist yet (added in 003.02).

## Acceptance Criteria
- [ ] All 13 new files created (1 shim + 12 package files including `__init__.py`).
- [ ] Every public stub raises `NotImplementedError("xlsx-7 stub — task-003-NN")` with the exact phrasing.
- [ ] Shim LOC count ≤ 200 (verified by TC-UNIT-03).
- [ ] `requirements.txt` updated (4 dep deltas).
- [ ] `.AGENTS.md` placeholder section added.
- [ ] `THIRD_PARTY_NOTICES.md` stubs added.
- [ ] xlsx-6 tests pass unchanged (regression gate).
- [ ] `pip install -r requirements.txt` succeeds in `.venv/`.
- [ ] **CLAUDE.md §2 boundary sanity check (plan-review m6):** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0 — catches accidental `office/` / `_soffice.py` / `_errors.py` / `preview.py` / `office_passwd.py` imports on day one, not only at the chain's end.

## Notes
- Use `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` to verify dep resolution. If `regex>=2024.0` cannot be installed in the target Python (3.10+), document the resolved version and pin it.
- Do NOT implement any logic in this task; that is what the chain's later tasks are for. The point is that **the structure exists and tests fail in a uniform, expected way**.
- This task is the precondition for 003.02–003.04 (test scaffolding) which finalize the red-state baseline.
