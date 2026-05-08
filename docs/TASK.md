# Task 003 — xlsx-7 — `xlsx_check_rules.py` (declarative business-rule validator)

> **Source contract:** [`skills/xlsx/references/xlsx-rules-format.md`](../skills/xlsx/references/xlsx-rules-format.md)
> (the design spec, hereafter **SPEC**). This TASK is a derivative of
> SPEC, structured for VDD execution. Where this TASK and SPEC disagree,
> SPEC wins and this TASK is updated. Section numbers in `[SPEC §N]`
> brackets cross-reference SPEC.

## 0. Meta Information
- **Task ID:** `003`
- **Slug:** `xlsx-check-rules`
- **Backlog row:** `xlsx-7` (`docs/office-skills-backlog.md`)
- **Effort estimate:** **L** (M→L per backlog after VDD-adversarial pass).
- **Predecessor:** `xlsx-6` (`xlsx_add_comment.py`) — **MERGED** (Tasks 001, 002).
  xlsx-7 produces the findings envelope that xlsx-6 `--batch` consumes.
- **Status:** ✅ MERGED 2026-05-08 — 20-step atomic chain (003.01–003.17) shipped. All RTM rows R1–R14 closed; D1–D6 + Q1–Q3 / Q5–Q7 architecture decisions reflected in implementation. Per-subtask review trail in `docs/reviews/task-003-*.md`; per-subtask archives in `docs/tasks/task-003-*.md`. Final regression: 311 unit + 113 E2E + canary-meta (Saboteur 04 active, 9 deferred to Stage-2) + 4-skill `validate_skill.py` green + CLAUDE.md §2 byte-identity diffs empty.
- **Decisions locked from `/vdd-start-feature` Q&A (2026-05-08):**
  - **D1 — Delivery shape:** **Atomic chain** of sub-tasks (mirrors
    xlsx-6 Task 001 = 15 sub-tasks; final count for xlsx-7 set in
    Planning phase, target 12–18).
  - **D2 — Code layout:** **Shim + package up front** —
    `scripts/xlsx_check_rules.py` (≤ 200 LOC shim, re-exports test-compat
    surface) + `scripts/xlsx_check_rules/` package (one module per Epic
    region, target ≤ 500 LOC each). Avoids a Task-002-style refactor.
  - **D3 — Fixtures:** **Helper-script generated** —
    `tests/golden/inputs/_generate.py` builds all 39 `.xlsx` + `.json`/
    `.yaml` triples from declarative manifests. CI regenerates;
    `.gitignore` excludes large `.xlsx` outputs from git (manifests are
    committed).
- **Decisions locked from Task-Reviewer round-1 (2026-05-08, see `docs/reviews/task-003-review.md`):**
  - **D4 (was Q4) — Excel error subset.** openpyxl `ERROR_CODES` (cell.py:46) recognises exactly **7 codes**: `#NULL!`, `#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?`, `#NUM!`, `#N/A`. xlsx-7 v1 honours those 7 only — they reach `data_type='e'` and trigger the §5.0 auto-emit. The 3 modern Excel codes (`#SPILL!`, `#CALC!`, `#GETTING_DATA`) are stored by openpyxl as `text` and are **NOT** auto-emitted in v1. Workaround for users whose workbooks rely on the modern codes: hand-author a `regex:^#(SPILL|CALC|GETTING_DATA)` rule on the relevant scope. **Action items downstream:** (a) update SPEC §5.0 to list 7 codes (move the other 3 into SPEC §11 honest-scope as "modern-Excel error codes not auto-detected by openpyxl") — Issue I9.5; (b) add fixture #10b: workbook with `#SPILL!` stored as text → no `cell-error` finding without a user rule.
  - **D5 (was Q1) — `recheck` availability:** **Soft import + hand-coded reject-list fallback.** ReDoS pattern lint at parse uses `recheck` if importable; otherwise falls back to a hand-coded reject-list for the 4 classic shapes (`(a+)+`, `(a*)*`, `(a|a)+`, `(a|aa)*`). Skill install never breaks on a `recheck` PyPI outage (CLAUDE.md "Независимость скиллов"). `recheck` stays OUT of `requirements.txt`; hard dep is only `regex>=2024.0` for the per-cell `timeout=` parameter.
  - **D6 (was Q6) — Perf-test gating:** **`RUN_PERF_TESTS=1` opt-in.** Fixture #31 (100K rows × 5 rules ≤ 30 s ≤ 500 MB RSS) is **skipped in CI by default**, runs locally only when `RUN_PERF_TESTS=1`. Matches the xlsx-6 perf-test convention (no perf gating in CI; reviewer runs locally before merge).

## 1. General Description

### Goal
Ship a CLI under `skills/xlsx/scripts/` that loads a declarative
`rules.json|yaml` file alongside an `.xlsx` workbook and emits
machine-readable findings (`{ok, schema_version, summary, findings}`)
plus optional in-workbook remarks. **No `eval`, no code execution
on hostile input** — rules parse into a closed AST (17 node types,
hand-written recursive-descent parser). CLI is the **find-and-report**
half of the timesheet/budget review pipeline; xlsx-6 is the
**act-on-findings** half.

### Why now
- xlsx-6 (`xlsx_add_comment.py`) is merged; its `--batch` mode already
  auto-detects an xlsx-7 envelope shape (`{ok, summary, findings: […]}`
  → comments per finding). xlsx-7 closes that loop.
- The backlog row is the single largest open item in `xlsx/` and
  enables the full "validation + remark + comment" use case advertised
  in `skills/xlsx/SKILL.md`.

### Connection with existing system
- **Trust boundary** = `office/unpack` + `office/pack` (cross-skill
  shared module, **MUST NOT** be modified — CLAUDE.md §2). xlsx-7
  is a **read-mostly** consumer; the only write path is the optional
  `--output OUT.xlsx --remark-column …` workbook copy.
- **Cross-skill envelopes**: cross-3 (encryption fail-fast),
  cross-4 (`.xlsm` macro warning), cross-5 (`--json-errors` shared
  envelope), cross-7 H1 (same-path `Path.resolve()` guard).
- **Pipe-mate**: xlsx-6 `--batch -` consumes xlsx-7 `--json` output
  directly. `findings[i].row == null` (group findings) auto-skipped
  by xlsx-6 [SPEC §9 ↔ xlsx-6 TASK §2 R5/R6].
- **Composes with**: `xlsx_recalc.py` (run before xlsx-7 to populate
  formula caches), `xlsx_validate.py` (post-output sanity check).

### Reference use-case (from SPEC §10 worked example)
A reviewer runs xlsx-7 on `timesheet.xlsx` with `timesheet.rules.json`
(8 rules: required-fields / hours-positive / hours-realistic /
date-in-period / project-code-format / weekly-cap / totals-match /
approved-status). Output:
- `timesheet.reviewed.xlsx` with auto-allocated `Remarks` column
  (red for errors, yellow for warnings).
- Exit code 1 (errors present) + JSON envelope on stdout.
- Stderr: human-readable report.

## 2. Requirements Traceability Matrix (RTM)

> Granularity: each Epic row decomposes to ≥ 3 sub-features; sub-features
> map to Issues in §3.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| R1 | **Rule-file parser & AST** [SPEC §2, §6] | yes | (a) JSON/YAML detection by ext; (b) 1 MiB pre-parse size cap → exit 2 `RulesFileTooLarge`; (c) ruamel.yaml typ='safe', YAML 1.2, no anchors/aliases (`AliasEvent` reject), no custom tags, no dup-keys, no YAML-1.1 bool coercion; (d) hand-written recursive-descent parser — NOT `ast.parse`; (e) closed 17-node AST whitelist; (f) composite depth cap 16 → exit 2 `CompositeDepth`; (g) builtin whitelist (`sum/avg/mean/min/max/median/stdev/count/count_nonempty/count_distinct/count_errors/len`) → exit 2 `UnknownBuiltin`; (h) `version: 1` enforcement. |
| R2 | **Cell-value type model** [SPEC §3.5] | yes | (a) 6 logical types `number/date/bool/text/error/empty`; (b) "numbers stored as text" stays `text` (no auto-coerce); (c) `Decimal` → `float` for arithmetic; (d) whitespace strip default-on (per-rule and `--no-strip-whitespace` opt-out); (e) `cell-error` auto-emit on `error` type, suppresses other rules unless `is_error: info` declared. |
| R3 | **Scope vocabulary** [SPEC §4] | yes | (a) forms: `cell:` / `RANGE` / `col:HEADER` / `col:LETTER` / `cols:LIST` / `row:N` / `sheet:NAME` / `named:NAME` / `table:NAME` / `table:NAME[COL]`; (b) sheet qualifier (plain / quoted / apostrophe-escaped `''`); (c) header semantics (case-sensitive, whitespace-stripped, `defaults.header_row` default `1`, `0` to disable); (d) duplicate header → `AmbiguousHeader`; missing → `HeaderNotFound`+available; merged → `MergedHeaderUnsupported`; (e) Excel-Tables auto-detect (`xl/tables/tableN.xml` fallback, `--no-table-autodetect` opt-out); (f) merged-cell anchor resolution + `merged-cell-resolution` info; (g) hidden rows/cols included by default, `--visible-only` opts out. |
| R4 | **Check vocabulary** [SPEC §5] | yes | (a) §5.1 comparisons (`==`/`!=`/`<`/`<=`/`>`/`>=` + `between`/`between_excl` + `in`/`not in`); (b) §5.2 type guards (`is_number`/`is_date`/`is_text`/`is_bool`/`is_error`/`required`); (c) §5.3 text (`regex:` + `len OP N` + `not_empty` + `starts_with:`/`ends_with:`); (d) §5.4 dates (`date_in_month/range/before/after/weekday`) + `--treat-numeric-as-date` + `--treat-text-as-date` opt-in flags; (e) §5.5 cross-cell aggregates (sum/avg/min/max/median/stdev/count/count_nonempty/count_distinct/count_errors) — cross-sheet OK; (f) §5.6 group-by (`sum_by/count_by/avg_by:KEY OP X`); (g) §5.7 composite (`and/or/not`, depth ≤ 16); (h) §3 fields (`severity`, `message`, `when`, `skip_empty`, `tolerance`). |
| R5 | **Output JSON envelope** [SPEC §7] | yes | (a) `{ok, schema_version: 1, summary, findings}`; (b) summary keys: `errors/warnings/info/checked_cells/rules_evaluated/cell_errors/skipped_in_aggregates/regex_timeouts/eval_errors/aggregate_cache_hits/elapsed_seconds/truncated`; (c) finding fields per §7.1.1; (d) deterministic sort by 5-tuple `(sheet,row,column,rule_id,group)` with type-homogeneous sentinels per §7.1.2; (e) grouped findings shape per §7.1.3 (`row=null`, `column=null`, `cell="<sheetName>"`); (f) `--max-findings N` cap (default `1000`) → `summary.truncated` + synthetic `max-findings-reached`; (g) `--summarize-after N` (default `100` per `rule_id`) → collapsed entries with `count`, `sample_cells`. |
| R6 | **Exit codes** [SPEC §7.3] | yes | (a) 0 pass; (b) 1 ≥ 1 error; (c) 2 RulesParseError; (d) 3 unreadable / encrypted (cross-3); (e) 4 `--strict` ∧ ≥ 1 warning; (f) 5 IO error; (g) 6 same-path (cross-7 H1); (h) 7 wall-clock timeout. `--json-errors` (cross-5) wraps fatal codes 2/3/5/6/7 in shared envelope; finding-level codes 0/1/4 ALWAYS use the §7.1 schema. |
| R7 | **CLI surface** [SPEC §8] | yes | (a) ≥ 22 flags (full list in §2.5 below); (b) mutex pairs: `--include-hidden` × `--visible-only`, `--json` × `--no-json`; (c) deps: `--remark-column` ⇒ `--output`; `--remark-column-mode` ⇒ `--remark-column`; `--streaming-output` ⇒ `--output`; (d) `--remark-column-mode` default `new` (preserves user data via `_2` suffix); (e) §8.2.1 streaming-incompatible combos rejected at arg-parse (`IncompatibleFlags` exit 2). |
| R8 | **Workbook output** [SPEC §8.1, §11.2] | yes | (a) `--output` writes a copy + remark column; (b) `--remark-column auto` picks first free letter; (c) `replace`/`append`/`new` modes; (d) PatternFill red/yellow/blue per severity; (e) `--streaming-output` (openpyxl `WriteOnlyWorkbook`) for ≥ 100K-cell perf; (f) cross-7 H1 same-path → exit 6; (g) round-trip preservation: comments / drawings / charts / defined names on cells **NOT** modified by xlsx-7. |
| R9 | **Performance & adversarial hardening** [SPEC §5.3.1, §11.2] | yes | (a) `regex` PyPI lib (NOT stdlib `re`) + per-cell `timeout=100ms`; (b) ReDoS pattern lint at parse via `recheck` (or hand-coded reject-list fallback for the 4 classic shapes); (c) compilation cache (one `re.compile` per unique pattern per run); (d) per-cell budget overflow → finding `rule-eval-timeout`; (e) wall-clock cap `--timeout 300` default → exit 7; (f) **Perf contract** — `huge-100k-rows.xlsx × 5-rule.rules.json` ≤ 30 s wall-clock & ≤ 500 MB RSS on a 4-core machine (assertion in fixture #31). |
| R10 | **Aggregate cache & determinism** [SPEC §5.5.3] | yes | (a) canonical key = SHA-1 of `(sheet, scope, fn)` after whitespace/quote normalisation, sheet-qualifier resolution, header→letter resolution, Table-fallback equivalence; (b) cache entry stores `(value, skipped_cells, error_cells, cache_hits)`; (c) replay re-emits per-cell skip/error events into each consuming rule (under `--strict-aggregates`); (d) intra-rule replay dedup on `(rule_id, cell)`; inter-rule no-dedup; (e) `summary.aggregate_cache_hits` counter (fixture #19 anchor). |
| R11 | **Cross-skill integration** | yes | (a) cross-3 fail-fast on encrypted input (exit 3); (b) cross-4 `.xlsm` warning to stderr; (c) cross-5 `--json-errors` envelope on fatal exit codes; (d) cross-7 H1 `Path.resolve()` same-path → exit 6; (e) **xlsx-6 envelope contract**: `xlsx_check_rules.py … --json | xlsx_add_comment.py … --batch -` produces output `.xlsx` with one comment per non-grouped finding (fixture #39). |
| R12 | **Regression battery** [SPEC §13] | yes | (a) ≥ 21 xlsx-7 fixtures (manifest in §3 E9); (b) 10 canary saboteurs in `tests/canary_check.sh` — each must fail the battery; (c) all adversarial fixtures (#22–#30) reject ≤ 100 ms wall-clock; (d) deterministic golden output (sort order locked by §7.1.2 sentinels). |
| R13 | **Honest scope (v1)** [SPEC §11] | yes | (a) no JOIN-style lookups (`vlookup` semantics); (b) no datetime arithmetic; (c) no auto-fix (find/report only); (d) no Python plugins/lambdas; (e) no native Excel-`<dataValidations>` ingestion; (f) no message localisation; (g) no multi-row / merged headers; (h) no transposed layout; (i) no multi-area `definedName`; (j) Decimal precision loss documented; (k) cached-value dependency (run `xlsx_recalc.py` first); (l) regression tests **lock each limitation** (negative tests in §3 E9). |
| R14 | **Documentation** | yes | (a) `skills/xlsx/SKILL.md` §2/§4/§10/§12 entries for `xlsx_check_rules.py`; (b) `skills/xlsx/scripts/.AGENTS.md` updated with new module map; (c) `skills/xlsx/references/xlsx-rules-format.md` SPEC moves from "design spec" to "implementation reference" (§Status header updated post-merge) AND §5.0 error-code list reduced from 10 to 7 per D4 (§11 picks up the 3 modern codes as honest-scope); (d) `examples/check-rules-timesheet.{json,xlsx}` (the §10 worked example) committed as runnable reference (BOTH files needed); (e) `tests/golden/README.md` documents fixture provenance ("agent-output-only — DO NOT open in Excel" mirroring xlsx-6 m4/R9.d). |

## 2.5 CLI surface (authoritative flag table)

> The Architect MAY tighten defaults during Architecture review;
> additions/removals require user gating.

```
xlsx_check_rules.py INPUT.xlsx --rules RULES.{json,yaml}
                    [--json | --no-json]
                    [--strict] [--require-data]
                    [--severity-filter LIST]
                    [--max-findings N] [--summarize-after N]
                    [--timeout SECONDS]
                    [--sheet NAME] [--header-row N]
                    [--include-hidden | --visible-only]
                    [--no-strip-whitespace] [--no-table-autodetect]
                    [--no-merge-info] [--ignore-stale-cache]
                    [--strict-aggregates]
                    [--treat-numeric-as-date COLS]
                    [--treat-text-as-date COLS]
                    [--output OUT.xlsx
                     [--remark-column auto|LETTER|HEADER]
                     [--remark-column-mode replace|append|new]
                     [--streaming-output]]
                    [--json-errors]
```

### Mutex / dependency rules (must be enforced in argparse)
- **MX-A:** `--json` ⊕ `--no-json` (default `--no-json`).
- **MX-B:** `--include-hidden` ⊕ `--visible-only` (default include).
- **DEP-1:** `--remark-column` ⇒ `--output`.
- **DEP-2:** `--remark-column-mode` ⇒ `--remark-column`.
- **DEP-3:** `--streaming-output` ⇒ `--output`.
- **DEP-4:** `--streaming-output` ∧ `--remark-column auto` → exit 2 `IncompatibleFlags`.
- **DEP-5:** `--streaming-output` ∧ `--remark-column-mode append` → exit 2 `IncompatibleFlags`.
- **DEP-6:** `--treat-numeric-as-date` and `--treat-text-as-date` accept `,`-separated headers/letters; if any token contains `,`, switch to `;` separator (auto-detected by presence of `;`).
- **DEP-7:** All argparse usage errors route through `_errors.report_error` when `--json-errors` is set.

### Exit codes
| Code | Type | Trigger |
|---|---|---|
| 0 | OK | All rules pass; warnings/info allowed unless `--strict`. |
| 1 | RuleErrors | ≥ 1 error finding (or `--require-data` ∧ `checked_cells == 0`). |
| 2 | RulesParseError / IncompatibleFlags / UnknownBuiltin / CompositeDepth / RulesFileTooLarge / AmbiguousHeader / HeaderNotFound / MergedHeaderUnsupported | Bad rules or bad flag combo. |
| 3 | EncryptedInput / CorruptInput | Cross-3 fail-fast; not an .xlsx. |
| 4 | StrictWarnings | `--strict` ∧ ≥ 1 warning finding. |
| 5 | IOError | Path read/write failure. |
| 6 | SelfOverwriteRefused | Cross-7 H1 (resolved input==output). |
| 7 | TimeoutExceeded | `--timeout` exceeded; partial findings flushed if `--json`. |

## 3. Epics & Use Cases

> One Epic ≈ one orthogonal capability cluster. Each Issue is a
> Use Case with Actors / Preconditions / Main Scenario / Alternative
> Scenarios / Postconditions / Acceptance Criteria. Issues are sized
> to ≤ 1 atomic task per chain-link rule (D1).

### Epic E1 — Rules-file parsing & AST safety [maps R1, R9 lint]

#### Issue I1.1 — Rules file loader (JSON / YAML) with hardening
- **Actors:** Reviewer (CLI invoker), System (parser).
- **Preconditions:** `--rules PATH` resolves; file ≤ 1 MiB.
- **Main Scenario:**
  1. Reviewer invokes `xlsx_check_rules.py W.xlsx --rules R.yaml`.
  2. System checks `Path(R).stat().st_size ≤ 1 MiB` → otherwise exit 2 `RulesFileTooLarge`.
  3. System detects format by extension (`.json` → stdlib `json`; `.yaml`/`.yml` → ruamel.yaml).
  4. **YAML path:** install ruamel.yaml `YAML(typ='safe', pure=True, version=(1,2))` with `allow_duplicate_keys=False`. Hook the parser event stream and abort on any `AliasEvent` or non-empty `anchor` field on `ScalarEvent`/`SequenceStartEvent`/`MappingStartEvent` BEFORE composition.
  5. System rejects any custom tag not in canonical YAML 1.2 schema (str/int/float/bool/null/seq/map/timestamp).
  6. System validates `version: 1` and presence of `rules: [...]` (≥ 1 element).
  7. System hands the dict to the AST builder (I1.2).
- **Alternative Scenarios:**
  - **Alt-1:** YAML with anchors → exit 2; **must complete ≤ 100 ms** (alias rejected pre-composition, no expansion).
  - **Alt-2:** YAML with `!!python/object` → exit 2 (custom-tag reject).
  - **Alt-3:** YAML with `value in [yes, no]` → strings stay strings (YAML 1.1 bool trap disabled); legal rule, no error.
  - **Alt-4:** YAML with duplicate keys → exit 2 (`allow_duplicate_keys=False`).
  - **Alt-5:** YAML scalar containing literal `&` (e.g. `description: 'see Q1 & Q2'`) → **MUST NOT** be rejected (negative regression).
  - **Alt-6:** rules file 1.5 MiB → exit 2 `RulesFileTooLarge`.
- **Postconditions:** parsed dict in memory, ready for AST build.
- **Acceptance Criteria:**
  - ✅ Fixture `billion-laughs.rules.yaml` exits 2 in ≤ 100 ms (no memory blow-up).
  - ✅ Fixture `yaml-string-with-ampersand.rules.yaml` exits 0 (no false positive).
  - ✅ Stdlib `yaml.safe_load` is **NOT** imported (grep test).

#### Issue I1.2 — Hand-written DSL parser (recursive descent, closed AST)
- **Actors:** System (parser).
- **Preconditions:** I1.1 produced a `dict` with `rules: [...]`.
- **Main Scenario:**
  1. For each rule, parse `check` field. If `str`, run recursive-descent over the DSL grammar (§5 SPEC). If `dict`, route to composite handler (`and`/`or`/`not`).
  2. Build AST nodes from the closed 17-type whitelist (`Literal`, `CellRef`, `RangeRef`, `ColRef`, `RowRef`, `SheetRef`, `NamedRef`, `TableRef`, `BuiltinCall`, `BinaryOp`, `UnaryOp`, `In`, `Between`, `Logical`, `TypePredicate`, `RegexPredicate`, `LenPredicate`, `StringPredicate`, `DatePredicate`, `GroupByCheck`).
  3. Track composite depth; exit 2 `CompositeDepth` if > 16.
  4. Validate `BuiltinCall.name` against whitelist (`sum/avg/mean/min/max/median/stdev/count/count_nonempty/count_distinct/count_errors/len`); exit 2 `UnknownBuiltin` otherwise.
  5. **Pattern-lint** (R9): for each `RegexPredicate`, run `recheck` (or hand-coded fallback) for the 4 classic ReDoS shapes (`(a+)+`, `(a*)*`, `(a|a)+`, `(a|aa)*`). Reject at parse unless rule carries `"unsafe_regex": true`.
  6. **Forbidden Python constructs** — no attribute access (`.`), no `**`, no `%`, no bitwise, no lambda. Tested by hostile fixtures.
- **Acceptance Criteria:**
  - ✅ `ast.parse` is **NOT** in the import graph of the parser module (grep test).
  - ✅ Fixture `deep-composite.rules.json` (1000-level `and`) exits 2 `CompositeDepth`.
  - ✅ Fixture `unknown-builtin.rules.json` (`foo(col:X)`) exits 2 `UnknownBuiltin`.
  - ✅ Fixture `regex-dos.rules.json` (`^(a+)+$`) is rejected at parse (or per-cell timeout if `unsafe_regex: true`) within 100 ms.

### Epic E2 — Cell-value type model & scope resolution [maps R2, R3]

#### Issue I2.1 — Cell-value canonicalisation (six logical types)
- **Actors:** System (cell reader).
- **Preconditions:** workbook unpacked via `office/unpack`; cell read via openpyxl.
- **Main Scenario:**
  1. Read cell via openpyxl `data_only=False` (we want the formula presence signal for §5.0.1 stale-cache).
  2. Map openpyxl type → logical type per SPEC §3.5: `<c t="n">` non-date → `number`; `<c t="n">` date-format or `<c t="d">` → `date`; `<c t="b">` → `bool`; `<c t="s">`/`<c t="inlineStr">` → `text` (whitespace stripped per `--no-strip-whitespace`); `<c t="e">` → `error` (synthetic `CellError(code)` token); empty/`None` → `empty`.
  3. **DO NOT** auto-coerce `text` "42" to `number` (§3.5.1).
  4. **Decimal**: `<c t="d">` → coerce to `float` for arithmetic; equality uses rule's `tolerance`.
  5. Cells with `<f>` (formula) but no `<v>` (cached value) → emit one-time stderr stale-cache warning (suppressed by `--ignore-stale-cache`) and treat value as `empty` for that cell.
- **Alternative Scenarios:**
  - **Alt-1:** `error` cell → auto-emit `cell-error` finding (SEV `error`, `value="<error code>"`); skip ALL other rules on this cell. Counted in `summary.cell_errors`. Suppress by user-rule `is_error: info`.
  - **Alt-2:** `--treat-numeric-as-date COLS`: serial in `[25569, 73050]` is logical-type `date` for those cols.
  - **Alt-3:** `--treat-text-as-date COLS`: pass through `dateutil.parser.parse(s, fuzzy=False, dayfirst=...)`; on parse failure, stays `text`.
- **Acceptance Criteria:**
  - ✅ Fixture `errors-as-values.xlsx` auto-emits `cell-error` for every `#REF!`/`#N/A` cell; other rules suppressed.
  - ✅ Fixture `formulas-no-cache.xlsx` triggers ONE stale-cache stderr warning (not one per cell), and rule findings see `value=None`.
  - ✅ Fixture `localized-dates-ru-text.xlsx` (Russian text dates) WITHOUT `--treat-text-as-date` → `date_in_period` MISFIRES per honest scope (negative test).

#### Issue I2.2 — Scope resolver (10 forms)
- **Actors:** System (scope resolver).
- **Main Scenario:**
  1. Parse scope string (or use AST node from I1.2).
  2. Resolve sheet qualifier (plain / quoted / apostrophe-escaped). Default = first non-hidden sheet in `xl/workbook.xml` element order (deterministic across openpyxl versions).
  3. Resolve form: `cell:` / `RANGE` / `col:HEADER` / `col:LETTER` / `cols:LIST` / `row:N` / `sheet:NAME` / `named:NAME` / `table:NAME` / `table:NAME[COL]`.
  4. **Header lookup** uses `defaults.header_row` (default `1`); case-sensitive; whitespace-stripped.
  5. **Excel-Tables fallback**: if cell range lies inside an Excel Table (read `xl/tables/tableN.xml`), Table header takes precedence over `header_row` (default-on; `--no-table-autodetect` opts out).
  6. **Merged cells**: anchor (top-left) carries the value; non-anchor cells in merge return `None` (= `empty`); emit one info `merged-cell-resolution` per merge encountered (suppress with `--no-merge-info`).
  7. **Hidden rows/cols**: included by default; `--visible-only` filters out `<row hidden="1">` / `<col hidden="1">`.
- **Alternative Scenarios:**
  - **Alt-1:** Duplicate header on same sheet → exit 2 `AmbiguousHeader` listing offending column letters.
  - **Alt-2:** Missing header → exit 2 `HeaderNotFound` with available-header list (truncated to 50).
  - **Alt-3:** Merged cell IN header row → exit 2 `MergedHeaderUnsupported`.
  - **Alt-4:** Multi-area `definedName` (`Sheet1!A1:A10,Sheet1!B1:B10`) → exit 2 `RulesParseError`.
  - **Alt-5:** Quoted sheet name with apostrophe (`'Bob''s Sheet'!A1`) → resolve correctly (case-sensitive, apostrophe doubled).
  - **Alt-6:** `header_row: 0` → header forms (`col:HEADER`, `cols:NAME,...`) become parse errors; only `cell:`/range/`col:LETTER`/`row:N`/`sheet:`/`named:` allowed.
- **Acceptance Criteria:** fixtures #3, #4, #5, #7, #8, #9, #13 all locked.

### Epic E3 — Check vocabulary [maps R4]

> Each Issue locks one §5 sub-section. AC = relevant battery rows
> + at least one negative case (`is_number` against text-stored
> "42" returns `false`).

- **I3.1 — Comparison & membership** [§5.1]
- **I3.2 — Type guards** [§5.2]
- **I3.3 — Text rules + regex hardening** [§5.3, §5.3.1]
- **I3.4 — Date rules + localisation fallback** [§5.4, §5.4.1, §5.4.2]
- **I3.5 — Cross-cell aggregates + arithmetic + tolerance** [§5.5]
- **I3.6 — Group-by aggregates** [§5.6]
- **I3.7 — Composite (object form) + depth cap** [§5.7]
- **I3.8 — Pre-rule cell triage (§5.0) + cached-value preflight (§5.0.1)**

Acceptance criteria for each Issue: SPEC §5.x text + ≥ 2 fixtures
from §13 (one positive, one negative).

### Epic E4 — Output JSON envelope [maps R5, R6]

#### Issue I4.1 — Findings envelope schema + sort order
- **Main Scenario:** emit `{ok, schema_version: 1, summary: {...}, findings: [...]}` to stdout when `--json`; suppress with `--no-json` (default).
- **Sort key:** 5-tuple `(sheet_name, row, column_letter, rule_id, group)` with type-homogeneous sentinels per §7.1.2 (group findings: `row=2**31-1`, `column="￿"`, `group=str`).
- **Acceptance Criteria:** fixture `clean-pass.xlsx` → byte-identical output across runs (deterministic).

#### Issue I4.2 — Finding caps (`--max-findings`, `--summarize-after`)
- **Main Scenario:** stop emitting after N; keep walking workbook for `summary.*` totals; append synthetic `max-findings-reached`. `--summarize-after N` collapses runs of same `rule_id` once N emitted with `count` + `sample_cells[10]`.

#### Issue I4.3 — Exit codes (full matrix from §2.5)

#### Issue I4.4 — Stderr human report (when `--no-json`) / stdout pure JSON (when `--json`)

### Epic E5 — CLI surface & flag interactions [maps R7]

#### Issue I5.1 — argparse setup (≥ 22 flags, mutex MX-A/B, deps DEP-1..7)
#### Issue I5.2 — `--treat-numeric-as-date` / `--treat-text-as-date` `,`/`;` auto-switch
#### Issue I5.3 — Streaming-incompatible combos (DEP-4, DEP-5) → exit 2 `IncompatibleFlags` at arg-parse

### Epic E6 — Workbook output (remark column) [maps R8]

#### Issue I6.1 — Output-copy + remark column allocation
- **Main Scenario:**
  1. Without `--output`: do not write any workbook.
  2. With `--output OUT.xlsx`: copy input → out, apply remark column.
  3. `--remark-column auto`: pick first free letter to the right of data region.
  4. `--remark-column LETTER|HEADER`: explicit placement.
  5. PatternFill: red (errors), yellow (warnings), blue (info).
  6. Round-trip: comments / drawings / charts / defined names on un-modified cells preserved.

#### Issue I6.2 — Remark-column-mode (`replace`/`append`/`new` default)

#### Issue I6.3 — `--streaming-output` (openpyxl `WriteOnlyWorkbook`) for ≥ 100K cells
- **Acceptance Criteria:** fixtures #32, #32a, #32b, #32c locked.

### Epic E7 — Performance & adversarial hardening [maps R9, R10]

#### Issue I7.1 — Regex hardening (`regex` lib, per-cell timeout, lint, compile cache)
#### Issue I7.2 — Aggregate cache with replay semantics (R10) + `summary.aggregate_cache_hits`
#### Issue I7.3 — Wall-clock `--timeout` + exit 7 + partial-flush
#### Issue I7.4 — Perf contract: 100K rows × 5 rules ≤ 30 s & ≤ 500 MB RSS (fixture #31)

### Epic E8 — Cross-skill integration [maps R11]

#### Issue I8.1 — cross-3 (encrypted), cross-4 (.xlsm), cross-5 (--json-errors), cross-7 H1 (same-path)
#### Issue I8.2 — xlsx-6 envelope contract (full pipeline fixture #39 / #39a / #39b)
- **Main Scenario:**
  1. `xlsx_check_rules.py timesheet.xlsx --rules timesheet.rules.json --json | xlsx_add_comment.py timesheet.xlsx --batch - --default-author "Reviewer Bot" --output reviewed.xlsx`.
  2. xlsx-6 auto-detects envelope shape — root must be a JSON **object containing all three keys** `{ok, summary, findings}` (xlsx-6 [`batch.py:122`](../skills/xlsx/scripts/xlsx_comment/batch.py#L122); this is the **frozen contract**). xlsx-7's `--json` output therefore MUST always emit all three top-level keys, even on `--max-findings 0` / `--severity-filter` / `--require-data` / timeout-with-partial-flush paths. Maps `cell ← findings[i].cell`, `text ← findings[i].message`.
  3. xlsx-6 skips findings with `row=null` (group-aggregate); counts in `summary.skipped_grouped`.
- **Acceptance Criteria:**
  - ✅ Fixture #39 (happy path): `reviewed.xlsx` has exactly `len(non-grouped findings)` comments; xlsx-6 exit 0; xlsx-7 exit code preserved as `$PIPESTATUS[0]`.
  - ✅ Fixture #39a: xlsx-7 timeout-partial-flush output (exit 7 + partial JSON) still has all three top-level keys `{ok, summary, findings}`; piping to xlsx-6 succeeds (no `InvalidBatchInput`).
  - ✅ Fixture #39b: xlsx-7 `--max-findings 0` (cap disabled, stderr warning per §8.1) still emits `summary` and `ok`; xlsx-6 round-trip clean.

### Epic E9 — Regression battery + Honest scope locks + Docs [maps R12, R13, R14]

#### Issue I9.1 — Fixture generator (`tests/golden/inputs/_generate.py`)
Builds all 39 `.xlsx` (+ `.json`/`.yaml` rule files + `expected.json`)
triples from declarative manifests in `tests/golden/manifests/`. CI
regenerates each run; `tests/golden/inputs/*.xlsx` is `.gitignore`d.

#### Issue I9.2 — `test_battery.py` driver
Walks `tests/golden/manifests/`, regenerates fixtures, runs `xlsx_check_rules.py`, asserts:
- exit code matches `expected.exit_code`.
- `summary` keys match exactly (subset compare for elastic counts allowed).
- `findings[]` `rule_id` set ⊇ `expected.required_rule_ids` and ∩ `expected.forbidden_rule_ids = ∅`.

#### Issue I9.3 — Canary saboteur runner (`tests/canary_check.sh`, ≥ 10 saboteurs)
Reverts each saboteur via `trap`. Battery MUST fail for each saboteur; missing failure → CI red.

#### Issue I9.4 — Honest-scope regression locks
For each item in §11 SPEC: a fixture + test that asserts the v1 limitation. Negative-test naming convention `Test*HonestScope*`.

#### Issue I9.5 — Docs
- `skills/xlsx/SKILL.md` §2/§4/§10/§12 entries for `xlsx_check_rules.py`.
- `skills/xlsx/scripts/.AGENTS.md` updated.
- `examples/check-rules-timesheet.{json,xlsx}` runnable demo (= SPEC §10 worked example).
- `tests/golden/README.md` provenance + "DO NOT open in Excel".
- `references/xlsx-rules-format.md` §Status header → "implementation reference (v1 merged)".

## 4. Non-functional Requirements

### Performance
- **Committed bound:** `huge-100k-rows.xlsx × 5-rule.rules.json` ≤ 30 s wall-clock & ≤ 500 MB peak RSS on a 4-core machine. Fixture #31 enforces.
- **Adversarial-input rejection:** all §13 hostile fixtures (#22–#30) reject at parse in ≤ 100 ms wall-clock.
- **Aggregate cache:** N rules referencing the same canonical scope walk the column **once**; `summary.aggregate_cache_hits ≥ N − 1`.
- **Streaming mode** (`--streaming-output`): ≥ 100K-cell workbooks fit in a single openpyxl `WriteOnlyWorkbook` pass (some flag combos rejected — DEP-4, DEP-5).

### Correctness / Compatibility
- **No `eval`** in the import graph (grep test in CI).
- **`ast.parse` not used** for DSL parsing (hand-written recursive-descent).
- **`yaml.safe_load` not imported** (ruamel.yaml only — grep test).
- **Deterministic output:** byte-identical findings JSON across re-runs on the same workbook+rules (sort sentinels per §7.1.2).

### Security
- **Trust boundary:** `office/unpack` (defusedxml against XML-bombs / XXE / billion-laughs in workbook XML).
- **Rules-file YAML hardening:** anchors / aliases / custom tags / dup-keys / YAML-1.1 bool coercion all rejected. 1 MiB hard cap.
- **Regex DoS:** `regex` lib + per-cell 100 ms timeout + parse-time ReDoS lint via `recheck` (or hand-coded reject-list fallback).
- **Format-string injection:** `string.Template` for `message` interpolation, NOT `str.format`.
- **No shell exec:** `subprocess` not imported in xlsx-7 module graph.
- **No network I/O:** xlsx-7 does not fetch URLs.
- **OWASP A03/A04/A06/A08** mapped (mirror `docs/ARCHITECTURE.md` §5 xlsx-6 mapping).

### Cross-skill compatibility
- `office/`, `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py` — **NOT** modified by xlsx-7 (CLAUDE.md §2 4-skill replication does NOT activate).
- xlsx-7 is **xlsx-private**; no propagation to docx/pptx/pdf.

## 5. Constraints and Assumptions

### Technical constraints
- **Python 3.10+** (matches `xlsx_add_comment.py` and `office/`).
- **No new system tools** beyond what's already in `install.sh`.
- **New PyPI deps** (subject to Architect review):
  - `regex>=2024.0` — required for `timeout=` parameter (R9).
  - `python-dateutil>=2.8.0` — required for `--treat-text-as-date` (R4d). May already be a transitive dep of pandas; verify.
  - `ruamel.yaml>=0.18.0` — required for YAML 1.2 parsing + alias rejection (R1c).
  - `recheck` — optional (graceful fallback to hand-coded reject-list per R9b); add to `requirements.txt` only if available cross-platform.
- **Existing deps reused:** `openpyxl>=3.1.5` (R2 / §5.4.2 — bump from `>=3.1.0` to `>=3.1.5`), `lxml>=5.0.0`, `defusedxml>=0.7.1`, `pandas>=2.0.0`.

### Business constraints
- **VDD strict mode:** atomic chain (D1) with per-task review (Sarcasmotron / VDD-adversarial pass at chain-end recommended, mirroring xlsx-6 Task 002).
- **Backwards compat:** `xlsx_check_rules.py` is a **new** script; no existing public API to preserve.

### Assumptions
- The shape of the xlsx-7 findings envelope (object with `findings: [...]`) is **already promised** by xlsx-6 — changing it would be a cross-task regression. Architect MUST treat §7.1 as frozen.
- Helper script `_generate.py` (D3) will use openpyxl + the same fixtures-per-row pattern that xlsx-6's `tests/golden/inputs/` README describes. Hand-craft NOT required.
- `xlsx_recalc.py` is run by the user before xlsx-7 if their workbook has formulas without cached values. xlsx-7 emits a one-time stale-cache warning but does **NOT** auto-invoke recalc (that would be a side-effect violating "find and report").
- Excel 365 round-trip mutation is **out of scope** (§11.2): goldens are agent-output-only; we never assert post-Excel-touch byte equality.

## 6. Open Questions

> Decisions D1–D6 (Delivery / Layout / Fixtures / openpyxl-error-set / `recheck` / perf-gating) are LOCKED at the top of this TASK (§0). The Open Questions below are RESERVED for the Architect; Planning may not proceed until each is closed (or deferred with explicit user gating). Original Q1, Q4, Q6 were closed by D5, D4, D6 respectively after Task-Reviewer round-1.

- **Q2 — Module split inside `xlsx_check_rules/` package (D2 confirmed layout, but not internals).** Candidate modules: `__init__.py`, `constants.py`, `exceptions.py`, `rules_parser.py` (E1), `ast_nodes.py` (E1 + E3), `cell_types.py` (E2), `scope_resolver.py` (E2), `evaluator.py` (E3), `aggregates.py` (E3 + R10 cache), `output.py` (E4 emit), `cli_helpers.py`, `cli.py` (E5 + E6 main). Architect to lock module boundaries + LOC budget per module (target ≤ 500 LOC each; total ≤ 3000 LOC).

- **Q3 — Streaming-output remark-column-mode `replace` semantics.** SPEC §8.2.1 says streaming + `replace` is supported but does not specify what happens when the destination column is OUT of the streaming write order (column letters past the last data column written). Architect to decide:
  - **A** — Allocate the remark column letter ahead of time; stream all data including remark column in single pass.
  - **B** — Reject explicit-letter `--remark-column` placements that would require a second pass.

- **Q5 — Fixture-set storage.** D3 says `_generate.py` builds fixtures on the fly. Architect to clarify CI strategy:
  - **A** — Generate every test run; no `.xlsx` in git.
  - **B** — Generate once, commit `.xlsx` outputs into `tests/golden/inputs/`; CI re-runs only on manifest change (cached binary).
  Recommendation: **A** for small fixtures, **B** for `huge-100k-rows.xlsx` (10–20 MB; expensive to generate on every run).

- **Q7 — `version: 1` strictness.** SPEC §2 says rules file MUST carry `version: 1`. Architect to decide if missing/wrong version is exit 2 `RulesParseError: VersionMismatch` or implicit-default to v1 with a stderr warning. Recommendation: hard exit 2 (CI determinism).

---

**Next step:** Architecture phase — Architect reads this TASK,
closes Q1–Q7, and produces an updated `docs/ARCHITECTURE.md` with
F1–F11 functional decomposition aligned with the §3 Epic boundaries.
