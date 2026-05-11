# Task 005.10: Final docs — SKILL.md + `.AGENTS.md` + backlog ✅ DONE + gates

## Use Case Connection
- All UCs covered indirectly through documentation linking back to them.
- R11.e (perf-test wiring opt-in `RUN_PERF_TESTS=1`).
- R12 (all docs sub-features: SKILL.md, `.AGENTS.md`, examples/, backlog row).

## Task Goal

Close the chain: update `skills/xlsx/SKILL.md` (Red Flag + Capability +
Script Contract), populate `skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md`
with the final module map, mark the backlog row `xlsx-3` as ✅ DONE with
LOC / test counts / status line, optionally wire a perf-test under
`RUN_PERF_TESTS=1` env-gate (no CI gate), and verify all phase-boundary
gates one last time.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

- **§1 Red Flags — add new Red Flag:**
  > "I'll just regex-replace `\|` to extract markdown tables." → **WRONG**. GFM pipe parsing has 5 edge cases (escaped pipes, trailing-pipe variations, separator-row alignment markers, column-count validation, blockquoted-skip) that regex hand-rolls always fail. Use `md_tables2xlsx.py`. For HTML `<table>` blocks, use the same tool — `lxml.html` is already locked with `no_network=True, huge_tree=False`.

- **§2 Capabilities — add new bullet:**
  > Extract all markdown tables from a `.md` document (file or stdin `-`) and emit a styled multi-sheet `.xlsx` (`md_tables2xlsx.py`). Two table flavors auto-detected: GFM pipe tables (with column-alignment carried to Excel cell alignment) and HTML `<table>` blocks (with `colspan` / `rowspan` honoured as Excel merged cells). Sheet names derive from the nearest preceding heading; fallback `Table-N`. Default-on numeric / ISO-date coercion with leading-zero preservation (csv2xlsx + json2xlsx parity). Tables inside fenced code blocks, HTML comments, indented code blocks, `<style>` / `<script>` blocks, and blockquotes are skipped pre-scan. Cross-cutting parity: `--json-errors` envelope (cross-5), `Path.resolve()` same-path guard (cross-7 H1), stdin pipe `-`.

- **§4 Script Contract — add new command:**
  > `python3 scripts/md_tables2xlsx.py INPUT OUTPUT.xlsx [--no-coerce] [--no-freeze] [--no-filter] [--allow-empty] [--sheet-prefix STR] [--encoding utf-8] [--json-errors]` — markdown tables → multi-sheet xlsx. `INPUT` is a path or `-` for stdin.

#### File: `skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md`

- Replace 005.01 placeholder with the final module map:

```markdown
# md_tables2xlsx package

CLI: `skills/xlsx/scripts/md_tables2xlsx.py` (≤60 LOC shim).

## Module map

| Module | F-region | LOC budget | Purpose |
|---|---|---|---|
| `__init__.py` | — | ≤70 | Public re-exports + `convert_md_tables_to_xlsx` (mirrors xlsx-2 `convert_json_to_xlsx`). |
| `loaders.py` | F1 + F2 | ≤180 | Input reader, pre-scan strip (fenced code / HTML comments / indented code / `<style>` / `<script>`), block iteration (headings + table blocks). |
| `tables.py` | F3 + F4 | ≤220 | GFM pipe parser + HTML `<table>` parser. Module-level `_HTML_PARSER = HTMLParser(no_network=True, huge_tree=False, recover=True)` singleton. |
| `inline.py` | F5 | ≤100 | Inline-markdown strip (bold/italic/code/link/strike/br/entities). |
| `coerce.py` | F6 | ≤150 | Numeric + ISO-date cell coercion with leading-zero gate (csv2xlsx parity). |
| `naming.py` | F7 | ≤130 | Sheet-name resolution via 9-step algorithm with UTF-16-aware truncate + dedup. |
| `writer.py` | F8 | ≤200 | openpyxl Workbook assembly + styling (HEADER_FILL/FONT/ALIGN copied from csv2xlsx). |
| `cli.py` | F9 | ≤280 | argparse + `main` + `_run` linear pipeline. |
| `cli_helpers.py` | F10 | ≤80 | Cross-cutting helpers: same-path guard, stdin reader, post-validate. |
| `exceptions.py` | — | ≤90 | 8 `_AppError` subclasses for cross-5 envelope. |

## Cross-references

- **TASK:** [`docs/tasks/task-005-md-tables2xlsx.md`](../../../../docs/tasks/task-005-md-tables2xlsx.md) (after archiving)
- **ARCHITECTURE:** [`docs/architectures/architecture-004-md-tables2xlsx.md`](../../../../docs/architectures/architecture-004-md-tables2xlsx.md) (after archiving)
- **PLAN:** [`docs/plans/plan-004-md-tables2xlsx.md`](../../../../docs/plans/plan-004-md-tables2xlsx.md) (after archiving)
- **Sibling references:** `csv2xlsx.py` (style constant source); `json2xlsx.py` + `json2xlsx/` (shim+package pattern + drift-detection counterparty).

## Cross-skill replication boundary (CLAUDE.md §2)

`md_tables2xlsx` touches NO shared file. The eleven `diff -q` gating
checks from ARCH §9 remain silent — verified pre-merge.
```

#### File: `skills/xlsx/scripts/.AGENTS.md` (top-level scripts dir)

- Add a permanent entry pointing to `md_tables2xlsx/` package (one line, mirrors how `json2xlsx/` was added in Task-004).

#### File: `docs/office-skills-backlog.md`

- Update the `xlsx-3` row (line 189) to mark ✅ DONE with status line. Pattern mirrors xlsx-2 row (line 188):

```markdown
| xlsx-3 | `md_tables2xlsx.py` ✅ DONE | Извлечь все markdown-таблицы из .md и положить каждую на отдельный лист. **Two flavors:** GFM pipe tables (with column alignment carried to Excel) + HTML `<table>` blocks (with colspan/rowspan as merged cells). Inline markdown (`**bold**`, `*italic*`, `` `code` ``, `[link](url)`, `~~strike~~`, `<br>`, HTML entities) stripped to plain text per cell. Sheet names derive from nearest preceding heading; fallback `Table-N`; UTF-16-aware truncate to 31 chars; case-insensitive dedup `-2..-99`. Default-on numeric + ISO-date coercion (csv2xlsx + json2xlsx parity; leading-zero preservation; aware-datetime → UTC-naive). Cross-cutting parity (cross-5 `--json-errors`, cross-7 H1 `SelfOverwriteRefused` exit 6, stdin `-`). Pre-scan strips fenced code blocks, HTML comments, indented code blocks, `<style>` / `<script>` blocks, and blockquoted tables — so tables inside these regions never reach the parser. **Security:** module-level `lxml.html.HTMLParser(no_network=True, huge_tree=False, recover=True)` singleton — XXE + billion-laughs neutralised. Public helper `convert_md_tables_to_xlsx(input_path, output_path, **kwargs) -> int` in `md_tables2xlsx/__init__.py` mirrors xlsx-2 `convert_json_to_xlsx` 1:1 (VDD-multi M4 atomic-token argparse-routing inherited). **Status (2026-05-NN):** 10-step atomic chain (005.01–005.10) shipped. Shim ~60 LOC + `md_tables2xlsx/` package — 10 modules. Tests: NN unit + NN E2E + drift-detection × 2 (csv2xlsx + json2xlsx). `validate_skill.py skills/xlsx` ✅ + eleven `diff -q` ARCH §9 silent. Полная задача-история: `docs/PLAN.md` + `docs/tasks/task-005-NN-*.md` + `docs/reviews/task-005-*.md`. | S→M | L | — | Use-case: вытащить таблицы из тех. документации в excel. |
```

(LOC/test counts filled in at the end of execution.)

### New Files (optional)

- `skills/xlsx/scripts/tests/test_md_tables2xlsx_perf.py` — opt-in perf test gated by `RUN_PERF_TESTS=1`:
  - Test 100-tables × 50-rows × 6-cols fixture renders in ≤ 2s wall (TASK §8 informal target).
  - Test 10-tables × 10K-rows × 6-cols fixture renders in ≤ 10s wall, ≤ 200MB RSS.
  - Both tests `@unittest.skipUnless(os.environ.get("RUN_PERF_TESTS") == "1", ...)`.
  - **Note (plan-review m7 fix):** the large 10K-row fixture is generated in-test via a `setUp` helper (~600 KB synthetic markdown); it is NOT committed to git. The 100-tables × 50-rows fixture may live in `examples/` if small enough (~50 KB), otherwise also generated.

### Changes in Existing Files (continued)

#### File: `docs/TASK.md`

- After this task completes, the orchestrator archives `docs/TASK.md` → `docs/tasks/task-005-md-tables2xlsx.md` per `skill-archive-task` (next task initiation; NOT this task).

#### File: `docs/ARCHITECTURE.md` + `docs/PLAN.md`

- Same archive convention — done at NEXT task initiation, not this task.

## Test Cases

### End-to-end Tests

- All 13 E2E cases from 005.02 remain green (regression gate).
- Optional perf test runs in `RUN_PERF_TESTS=1` mode but does NOT block CI.

### Unit Tests

- All previous unit tests remain green.
- Drift-detection tests (005.08 TC-UNIT-16, -17) green.
- M3 regression test (005.07 TC-UNIT-09) green.
- M1 billion-laughs test (005.06 TC-UNIT-14) green.

### Regression Tests

- Run full skill test-suite: `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests`.
- Run E2E: `bash skills/xlsx/scripts/tests/test_e2e.sh`.
- Run validator: `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx`.
- Run eleven `diff -q` cross-skill replication checks.

## Acceptance Criteria

- [ ] `skills/xlsx/SKILL.md` updated with the new Red Flag + Capability bullet + Script Contract line.
- [ ] `skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md` has the final module map.
- [ ] `skills/xlsx/scripts/.AGENTS.md` (top-level) lists the new package.
- [ ] `docs/office-skills-backlog.md` `xlsx-3` row marked ✅ DONE with full status line (LOC + test counts + sarcasmotron status if a multi-agent adversarial pass was run).
- [ ] All 13 E2E cases + ≥ 35 unit cases pass.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.
- [ ] Optional perf test scaffolded (NOT gating CI).

## Notes

This is the FINALIZATION task. Do NOT add new logic here — every
production code path landed in 005.01–005.09. This task is purely
documentation + boundary gates + backlog mark.

If the Developer finds a missing requirement at this point, STOP
and escalate — opening a new sub-task is cheaper than retrofitting
into 005.10. Examples of "found late" issues that justify a new
sub-task: (a) `--strict-dates` accidentally landed in `cli.py`
flags (regression of R9.f); (b) a forbidden char wasn't sanitised
in sheet names; (c) a `<style>` block wasn't stripped in
pre-scan.
