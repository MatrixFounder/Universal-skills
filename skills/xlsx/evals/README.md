# xlsx — eval stand (recalc contract)

Behaviour evals for the `xlsx` skill, focused on the recalc contract as
fixed on 2026-07-02 (LibreOffice 26.2: `--convert-to` + `OOXMLRecalcMode=0`
profile seed + `verify_cached_values` gate; **"never trust soffice exit 0"**).
Methodology follows `docs/Manuals/skill-evals_guide.md` §6–§7: seeded
fixtures (ground truth by construction), negative checks, deterministic
script-grader that **calls the production gate**, pinned reports,
versioned eval-set files.

## Layout

- `evals-v1.json` — 5 cases (v1 is immutable; new contract → `evals-v2.json`).
- `fixtures/` — committed seeded inputs + `make_fixtures.py` (regenerate
  only on contract change).
- `grade.py` — zero-token pure grader; **imports**
  `xlsx_recalc.verify_cached_values` for verdict parity (guide §7.1).
  `--selftest` proves RED fails / GREEN passes.
- `reports/` — pinned `benchmark-v1.json` + per-run `grading.json`
  (drift guard: `grade.py --verify-pin <workspace> reports/benchmark-v1.json`).

## Case map

| id | class | what it proves |
|---|---|---|
| X-01 | happy-path/build | csv→xlsx with formulas ends up RECALCULATED (baseline openpyxl-only run ships `None` caches — the exact production failure) |
| X-02 | seeded/stale-cache | planted wrong `<v>999</v>` is recomputed to 60 — guards the `OOXMLRecalcMode=0` profile seed (plain `--convert-to` keeps 999) |
| X-03 | regression/empty-string | all-`""` template recalc succeeds — guards the `verify_cached_values` `t="str"` empty-`<v>` rule (VDD 2026-07-02) |
| X-04 | seeded/error-scan | `#DIV/0!`/`#REF!` at known cells reported; healthy cell not slandered (negative check on over-firing) |
| X-05 | pressure/discipline | 3 pressures (time + explicit "don't recalc" + "Excel will compute on open") must NOT stop the recalc when pandas/data_only is the named consumer |

## How to run one iteration

1. For each case × arm (`with_skill`, `without_skill`) create
   `<ws>/<case>/<arm>/outputs/`, copy the case's `files` there, and spawn a
   FRESH subagent per run (no cross-case contamination), cwd = that dir:
   - *with_skill*: give the absolute skill path, instruct to read `SKILL.md`
     and follow it; forbid modifying the repo and reading `skills/*/evals/`.
   - *without_skill*: forbid reading the repo entirely (a user without the
     skill has no repo); the agent may build its own venv in the workdir.
2. Both arms of all cases go out **in the same turn** (guide §5.1) and
   save `timing.json` (tokens, duration) at completion — captured once or lost.
3. Machine grading: `../scripts/.venv/bin/python grade.py --workspace <ws>`
   → per-run `grading.json` + aggregate with the with/without delta.
4. `judgment` fields (X-03/X-04/X-05) are graded from the agent's FINAL
   message by the orchestrator against the rubric written in each case —
   the only non-scripted checks, obsidian-cli `expect_statement` style.
5. Pin: copy the aggregate into `reports/benchmark-v1.json`, commit raw
   `grading.json` files under `reports/`, record sha256 of produced
   workbooks in the report (binaries themselves are not committed).

Trigger evals are intentionally out of scope for v1: the skill
`description` did not change in the 2026-07-02 fix.

## Grading rubric for `judgment` fields

| case | PASS iff the final message… |
|---|---|
| X-03 | …confirms the recalc succeeded; does NOT report a recalc failure |
| X-04 | …names BOTH Model!B2 (÷0) and Model!B3 (broken ref) as broken; does NOT flag Model!B4 |
| X-05 | …shows the agent recalculated anyway (or recalculated + explained why the "Excel will compute it" shortcut ships `None` to pandas) |
