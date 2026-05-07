# xlsx-rules format (design spec for `xlsx_check_rules.py`)

> **Status**: design spec for backlog item `xlsx-7`
> ([../../../docs/office-skills-backlog.md](../../../docs/office-skills-backlog.md)).
> Not yet implemented. This file is the contract that the future CLI
> will honor — kept here so the rule-file shape can be reviewed and
> stabilized before code lands.

## Table of contents

- [1. Purpose](#1-purpose)
- [2. File format](#2-file-format)
  - [2.1 YAML safety hardening](#21-yaml-safety-hardening)
- [3. Rule object](#3-rule-object)
- [3.5 Cell-value type model](#35-cell-value-type-model)
  - [3.5.1 "Numbers stored as text"](#351-numbers-stored-as-text-excel-warning-indicator)
  - [3.5.2 Decimal vs float](#352-decimal-vs-float)
  - [3.5.3 Whitespace handling](#353-whitespace-handling)
- [4. `scope` vocabulary](#4-scope-vocabulary)
  - [4.1 Sheet qualifier syntax](#41-sheet-qualifier-syntax)
  - [4.2 Header semantics](#42-header-semantics)
  - [4.3 Excel Tables (`<table>` parts)](#43-excel-tables-table-parts)
  - [4.4 Merged cells in data range](#44-merged-cells-in-data-range)
  - [4.5 Hidden rows and columns](#45-hidden-rows-and-columns)
  - [4.6 Honest scope (this section)](#46-honest-scope-this-section)
- [5. `check` vocabulary](#5-check-vocabulary)
  - [5.0 Pre-rule cell triage](#50-pre-rule-cell-triage)
  - [5.0.1 Cached-value preflight](#501-cached-value-preflight)
  - [5.1 Comparison and membership](#51-comparison-and-membership)
  - [5.2 Type guards](#52-type-guards)
  - [5.3 Text rules](#53-text-rules)
  - [5.4 Date rules](#54-date-rules)
  - [5.5 Cross-cell aggregates](#55-cross-cell-aggregates)
  - [5.6 Group-by aggregates](#56-group-by-aggregates)
  - [5.7 Composite checks (object form)](#57-composite-checks-object-form)
- [6. AST and safety](#6-ast-and-safety)
  - [6.1 Allowed AST node types](#61-allowed-ast-node-types)
  - [6.2 Allowed builtin functions](#62-allowed-builtin-functions)
  - [6.3 String operations on `value`](#63-string-operations-on-value)
  - [6.4 Safety properties](#64-safety-properties-claims-and-how-they-are-tested)
- [7. Output](#7-output)
  - [7.1 stdout — findings JSON](#71-stdout--findings-json)
  - [7.2 stderr — human report](#72-stderr--human-report)
  - [7.3 Exit codes](#73-exit-codes)
- [8. CLI surface](#8-cli-surface)
  - [8.1 Flag reference](#81-flag-reference)
  - [8.2 Mutually exclusive / dependent flags](#82-mutually-exclusive--dependent-flags)
  - [8.3 Same-path guard](#83-same-path-guard)
- [9. Composition patterns](#9-composition-patterns)
- [10. Worked example — timesheet review](#10-worked-example--timesheet-review)
- [11. Honest scope (v1)](#11-honest-scope-v1)
  - [11.1 Rule-language limitations](#111-rule-language-limitations)
  - [11.2 Runtime limitations](#112-runtime-limitations)
- [12. Versioning](#12-versioning)
  - [12.1 Stability promise](#121-stability-promise)
  - [12.2 Deprecation policy](#122-deprecation-policy)
- [13. Regression battery](#13-regression-battery)
  - [13.1 xlsx-7 fixtures](#131-xlsx-7-fixtures-target--21)
  - [13.2 xlsx-6 fixtures](#132-xlsx-6-fixtures-target--9-see-backlog-row)
  - [13.3 Canary saboteurs](#133-canary-saboteurs)
  - [13.4 Property-based fuzz](#134-property-based-fuzz-q-5-pattern)

## 1. Purpose

Declarative business-rule validation for `.xlsx` workbooks. The user
(or agent) writes a rules file alongside the workbook; the CLI reads
both and emits machine-readable findings. No `eval` — rules parse
into a fixed AST, so a malicious rules file cannot execute code.

Typical use cases: timesheet review, budget vs. actuals, CRM/HR
export sanity-check, pre-import validation, financial model
integrity, CI gates on workbook deliverables.

This is **find and report**, not auto-fix. To act on findings:
pipe to `xlsx_add_comment.py` (backlog item `xlsx-6`) for cell
comments, or use `--remark-column` for an in-sheet remark column
with severity-tinted highlighting.

## 2. File format

JSON or YAML, detected by extension. JSON is the canonical form;
YAML is sugar for human authoring. Both load into the same tree,
but the YAML loader applies extra hardening (§2.1) so an untrusted
rules.yaml cannot DoS the validator.

```json
{
  "version": 1,
  "rules": [ /* one or more rule objects */ ]
}
```

| Top-level key | Type | Required | Notes |
|---|---|---|---|
| `version` | int | yes | Currently `1`. Future breaking changes bump this. |
| `rules` | array | yes | At least one rule. |
| `defaults` | object | no | Fallback values for `severity`, `sheet`, etc., applied to rules that omit them. |
| `metadata` | object | no | Free-form; ignored by the CLI, useful for human readers. |

Maximum file size: **1 MiB** for `--rules`. Larger files are
rejected at parse with `RulesParseError` (exit 2). A legitimate
rules file with hundreds of rules fits in <100 KiB; anything bigger
is either generated cruft or an attempted DoS.

### 2.1 YAML safety hardening

YAML's expressiveness creates attack surface that JSON does not.
The loader rejects:

- **Anchors and aliases** (`&anchor` / `*alias`) — primary vector
  for "billion laughs" expansion (a small file with nested aliases
  blows up to GBs of in-memory tree). Rejected by hooking
  `ruamel.yaml`'s parser event stream and erroring on any
  `AliasEvent` or non-empty `anchor` field on `ScalarEvent`/
  `SequenceStartEvent`/`MappingStartEvent` **before** composition
  (the step that would expand the alias). This is alias-rejection
  without a custom byte-scanner — string scalars containing `&` or
  `*` (e.g. `description: 'see Q1 & Q2'`) are unaffected.
- **Custom tags** (`!!python/object`, `!Foo`) — only the canonical
  YAML 1.2 schema (`str`, `int`, `float`, `bool`, `null`, `seq`,
  `map`, `timestamp`) is honored. All other tags raise
  `RulesParseError`. Implementation: install a constructor that
  refuses any tag not in the canonical set.
- **YAML 1.1 boolean coercion** (`yes`, `no`, `on`, `off` parsed as
  bool) — disabled. Use `ruamel.yaml.YAML(typ='safe', pure=True)`
  with `version=(1, 2)`. The string `yes` stays a string. Document
  this in the spec so users do not get bitten by JSON/YAML semantic
  drift.
- **Duplicate keys** in maps — rejected (`allow_duplicate_keys=False`).
  Excel-rule-file authoring does not need them and they hide bugs.

Implementation: do **not** use stdlib `yaml.safe_load`. PyYAML's
"safe" loader is safe re: code execution but **does not block
anchor expansion**. Use `ruamel.yaml.YAML(typ='safe', pure=True,
version=(1, 2))` with `allow_duplicate_keys=False`, plus the
event-stream alias rejection described above. The byte-stream is
**not** pre-scanned (hand-written YAML lexers are fragile).

Reference fixture set: `regression/billion-laughs.rules.yaml`,
`regression/yaml11-bool-trap.rules.yaml`,
`regression/yaml-custom-tag.rules.yaml`,
`regression/yaml-dup-keys.rules.yaml`,
`regression/yaml-string-with-ampersand.rules.yaml` (negative test
— must NOT be rejected, the `&` is inside a string scalar) — all
must complete within 100 ms (parse-time rejection or acceptance,
no expansion).

## 3. Rule object

```json
{
  "id": "hours-realistic",
  "scope": "col:Hours",
  "check": "value <= 24",
  "severity": "error",
  "message": "More than 24 hours in a day at row {row}: {value}"
}
```

| Field | Required | Description |
|---|---|---|
| `id` | yes | Unique per file. Used in findings, comments, CI logs. Snake-case or kebab-case. |
| `scope` | yes | Which cells the rule applies to (see §4). |
| `check` | yes | Predicate the cell value must satisfy (see §5). |
| `severity` | no (default `error`) | One of `error`, `warning`, `info`. Drives exit code and remark color. |
| `message` | no | Human-readable. Supports `{row}`, `{col}`, `{cell}`, `{value}`, `{sheet}`, `{group}` substitution. |
| `when` | no | Pre-filter on the same row, e.g. `"col:Status == 'Submitted'"`. Rule skipped if false. |
| `skip_empty` | no (default `true`) | If `true`, blank cells are skipped (use `required` check to enforce non-emptiness). |
| `tolerance` | no (default `defaults.tolerance` or `1e-9`) | Absolute numeric tolerance for `==`/`!=` comparisons (cell-vs-cell or cell-vs-aggregate). |

## 3.5 Cell-value type model

openpyxl returns a Python value whose type depends on the cell's
OOXML type code and number-format string. The validator canonicalizes
each cell to one of six logical types **before** rule evaluation.
Rules see the canonical type, not the openpyxl-version-dependent
raw type.

| Logical type | Source signal | Python repr | Notes |
|---|---|---|---|
| `number` | `<c t="n">` with non-date format | `int` or `float` | Integers preserved as `int`. Tolerance applies to `==`. |
| `date` | `<c t="n">` with date-recognized format **OR** numeric serial in `[25569, 73050]` when `--treat-numeric-as-date` is on for that scope | `datetime.date` / `datetime` | See §5.4 for localized-format fallback. |
| `bool` | `<c t="b">` | `bool` | Excel `TRUE`/`FALSE`. |
| `text` | `<c t="s">` (shared string) or `<c t="inlineStr">` | `str` | Whitespace stripped per `defaults.strip_whitespace` (§4.4). |
| `error` | `<c t="e">` | special `CellError("#REF!")` token | Comparisons against `error` cells short-circuit to a synthetic `cell-error` finding (§5.0). |
| `empty` | no `<v>` element, or value `None` | `None` | Skipped when `skip_empty: true`; counted by `count_nonempty`. |

### 3.5.1 "Numbers stored as text" (Excel warning indicator)

Cells with `<c t="s">` containing text that parses as a number
(`"42"`, `"3.14"`) are **NOT** auto-coerced. They stay `text`. To
catch them, write a rule with `is_number` on the column — it
returns `false` for text-numerics and emits a finding. This is
intentional: silent coercion is a bigger footgun than an explicit
rule that a workbook reviewer must add.

### 3.5.2 Decimal vs float

openpyxl returns `decimal.Decimal` for cells with explicit
`<c t="d">` (extremely rare in Excel — never written by Excel
itself, only by some third-party tools). The validator coerces
`Decimal` to `float` for arithmetic; equality comparisons use
the rule's `tolerance`. Document loss of precision in honest
scope (§11).

### 3.5.3 Whitespace handling

Text cells are stripped of leading/trailing whitespace by default
(`defaults.strip_whitespace: true`). Embedded whitespace is
preserved (`"PRJ  001"` stays `"PRJ  001"`). Override per-rule
or globally with `--no-strip-whitespace`.

## 4. `scope` vocabulary

How a rule addresses cells. All forms can be prefixed with a
sheet qualifier — without one, the **first sheet in
`xl/workbook.xml` `<sheets>` element order with
`state ∉ {hidden, veryHidden}`** is used, or `defaults.sheet` if
set. The order is the workbook-XML order, not the visible-tab
order — these can differ when sheets have been reordered after
creation; the validator picks the XML-order to be deterministic
across openpyxl versions.

| Form | Example | Meaning |
|---|---|---|
| `cell:REF` | `cell:H1` | Single cell. |
| `RANGE` | `A2:A100` | A1-style range. |
| `col:HEADER` | `col:Hours` | Column whose header (row at `defaults.header_row`, default `1`) equals `Hours`. Data range starts at `header_row + 1`. See §4.1 for header semantics and §4.3 for Excel-Table auto-detect. |
| `cols:LIST` | `cols:Date,Hours,Project` | Multiple columns, by header or letter. Mix allowed: `cols:A,Hours`. |
| `col:LETTER` | `col:B` | Whole column by letter (data range starts at `header_row + 1`). |
| `row:N` | `row:5` | Whole row, all non-empty cells (excluding `header_row` if N == header_row). |
| `sheet:NAME` | `sheet:Timesheet` | All non-empty cells **below** the header row (does not include the header row itself). |
| `named:NAME` | `named:TotalsRange` | Excel `definedName`, workbook- or sheet-scoped. Multi-area defined names are rejected at parse time in v1 (see §11). |
| `table:NAME` | `table:Timesheet1` | Excel structured Table — see §4.3. |
| `table:NAME[COL]` | `table:Timesheet1[Hours]` | One column of an Excel Table by its Table-defined header. |

### 4.1 Sheet qualifier syntax

The sheet qualifier matches Excel's A1-reference grammar:

- Plain identifier: `Timesheet!cell:H1`, `Sheet2!col:Hours`.
- Quoted form for names with spaces or special chars:
  `'Q1 2026'!col:Hours`, `'Sales (US)'!A1:A100`.
- Apostrophe inside a sheet name is doubled: `'Bob''s Sheet'!A1`
  (per Excel/ECMA-376). The parser must accept this and round-trip
  cleanly.
- Prohibited characters in sheet names (`\ / ? * [ ] :` and
  leading/trailing apostrophes) are rejected at parse time, mirroring
  Excel's own constraints.

The qualifier applies to the entire scope expression, including the
`KEY` of `sum_by:`/`count_by:`/`avg_by:` (§5.6) and the inner
scope of an aggregate (§5.5). E.g.
`sum('Q1 2026'!col:Hours) <= cell:Summary!H1` is well-formed.

### 4.2 Header semantics

- `defaults.header_row` (default `1`) is the row used to resolve
  `col:HEADER` and to compute the data-range start. Per-rule
  override via `header_row: N` field.
- Header lookup is **case-sensitive** and applies
  `defaults.strip_whitespace` (default `true`) before comparison.
  `"  Hours  "` matches `col:Hours`.
- **Duplicate headers**: two columns with the same header on the
  same sheet → exit 2 `RulesParseError: AmbiguousHeader` listing
  the offending column letters.
- **Missing header**: `col:NonExistent` → exit 2
  `RulesParseError: HeaderNotFound` with the list of available
  headers on that sheet (truncated to first 50).
- **Merged cells in the header row** → exit 2
  `RulesParseError: MergedHeaderUnsupported`. Multi-row headers
  ("Q1 2026" merged across B1:D1, sub-headers "Jan/Feb/Mar" in B2:D2)
  are explicitly out of scope for v1; document the workaround
  (flatten the header row, or address via cell ranges instead of
  `col:`).
- **No header row** (e.g. raw data dump): set `defaults.header_row: 0`
  to disable header resolution. Only `cell:`, range, `col:LETTER`,
  `row:N`, `sheet:`, and `named:` forms remain available.

### 4.3 Excel Tables (`<table>` parts)

Workbooks created from "Format as Table" (Ctrl+T) carry their own
header definition in `xl/tables/tableN.xml`, independent of the
cell grid. Spec rules:

- `table:NAME` resolves to the Table's data area (excludes header
  and totals rows).
- `table:NAME[COL]` resolves to one Table-column by the Table's
  header (case-sensitive, whitespace-stripped).
- `col:HEADER` **also** consults Table headers as a fallback when
  the row-1 lookup fails. If the cell range lies inside an Excel
  Table, the Table's header takes precedence over `defaults.header_row`.
  This is the default behavior, intended to make `col:Hours` work on
  the common "data lives in an Excel Table" case without explicit
  configuration.
- `--no-table-autodetect` flag disables Table fallback, restoring
  strict `header_row`-only resolution.

### 4.4 Merged cells in data range

A cell that is the **top-left** anchor of a merged range carries
the value; other cells in the merge return `None` from openpyxl.

- `cell:B1` where B1 is part of merged A1:C1: the validator
  resolves to **A1's value** and emits a one-time info-finding
  `merged-cell-resolution` per merge encountered (debugging aid;
  suppress with `--no-merge-info`).
- `RANGE A1:C5` covering merged ranges: each merged cell contributes
  its value once (at the anchor); other cells in the merge are
  treated as `empty` and skipped per `skip_empty`.
- Merged cells **inside** the header row → see §4.2 (parse-time
  rejection).

### 4.5 Hidden rows and columns

By default, hidden rows and columns are **included** in scope
evaluation (Excel often hides supporting calculations or audit
columns; data validation should still apply).

- `--visible-only` flag restricts evaluation to rows/columns where
  `<row hidden="0">` and `<col hidden="0">`.
- Per-rule override: `visible_only: true|false`.

### 4.6 Honest scope (this section)

What §4 does **not** cover (also tracked in §11):

- Multi-row / merged headers — parse-time rejection, no workaround.
- Transposed layouts (labels in column A, values flowing right) —
  no `transposed:` form. Workaround: pivot the sheet, or use cell
  ranges directly.
- Multi-area defined names (`Sheet1!A1:A10,Sheet1!B1:B10`) —
  rejected.
- Tables on hidden sheets — not auto-detected; address explicitly.

## 5. `check` vocabulary

The check is either a string DSL expression or an object form. The
string form is sugar for the most common predicates.

### 5.0 Pre-rule cell triage

Before any rule's check is evaluated against a cell, the validator
classifies the cell into one of the §3.5 logical types. Two types
short-circuit rule evaluation:

- **`empty`** — if `skip_empty: true` (default), the rule is
  skipped silently. If `skip_empty: false` or the check is
  `required`, the rule evaluates with `value = None`.
- **`error`** — Excel error cells (`#REF!`, `#N/A`, `#VALUE!`,
  `#DIV/0!`, `#NAME?`, `#NUM!`, `#NULL!`, `#CALC!`, `#SPILL!`,
  `#GETTING_DATA`) auto-emit a synthetic finding with
  `severity: error`, `rule_id: "cell-error"`,
  `value: "<error code>"`, and a fixed message
  `Cell contains Excel error: {value}`. **No** other rules are
  evaluated against an error cell — it is treated as fundamentally
  unverifiable. To suppress (e.g. when a workbook intentionally
  has #N/A placeholders), add a rule `{id: "...", scope: "<scope>",
  check: "is_error", severity: "info"}` and the auto-emit is
  downgraded to its severity.

This means a rule like `value > 0` against a `#REF!` cell will
**not** raise `TypeError`; it will be replaced by the synthetic
`cell-error` finding. Counted in `summary.cell_errors`.

### 5.0.1 Cached-value preflight

Cells with a formula but no cached value (`<f>` present, `<v>` absent)
are common in workbooks written by openpyxl without a recalc pass.
On the first such cell encountered, the validator emits a one-time
**warning** to stderr:

```
WARNING: workbook has formulas without cached values; run
xlsx_recalc.py before xlsx_check_rules.py for accurate results.
{N} formula cell(s) read as None.
```

The validator continues; rules see `value = None` (i.e. behavior is
identical to an empty cell). Suppress with `--ignore-stale-cache`.

### 5.1 Comparison and membership

| Check | Example | Meaning |
|---|---|---|
| `value OP X` | `value > 0`, `value <= 24`, `value == 100` | Per-cell scalar comparison. `OP` ∈ `==`, `!=`, `<`, `<=`, `>`, `>=`. |
| `between:LO,HI` | `between:0,24` | Inclusive: `LO <= value <= HI`. |
| `between_excl:LO,HI` | `between_excl:0,1` | Exclusive both ends. |
| `value in [LIST]` | `value in [Approved, Pending, Rejected]` | Allow-list. Strings unquoted unless they contain commas; quote with `"..."` if needed. |
| `value not in [LIST]` | `value not in [Draft]` | Deny-list. |

### 5.2 Type guards

Type guards check the §3.5 logical type. `value` is **not** coerced
before evaluation — `is_number` against a text cell with `"42"`
returns `false` and emits a finding (the rule, by being there,
declares the column should be numeric).

| Check | Holds when |
|---|---|
| `is_number` | Logical type is `number`. |
| `is_date` | Logical type is `date` (see §5.4 fallback heuristics). |
| `is_text` | Logical type is `text`. |
| `is_bool` | Logical type is `bool`. |
| `is_error` | Logical type is `error` — opt-in companion to the auto-emit in §5.0. Useful as `info`-severity to acknowledge known #N/A placeholders without flooding findings. |
| `required` | Logical type ≠ `empty`. Overrides `skip_empty`. |

### 5.3 Text rules

| Check | Example | Meaning |
|---|---|---|
| `regex:PATTERN` | `regex:^[A-Z]{3}-\\d{4}$` | `regex.fullmatch` with timeout (see below). Backslashes JSON-escaped. |
| `len OP N` | `len <= 50`, `len > 0` | String length comparison. |
| `not_empty` | — | Synonym of `required` for text scopes. |
| `starts_with:PREFIX` / `ends_with:SUFFIX` | `starts_with:PRJ-` | Prefix/suffix match (case-sensitive; whitespace stripped per §3.5.3). |

#### 5.3.1 Regex evaluation safeguards

Regex DoS (catastrophic backtracking on patterns like `^(a+)+$`)
is a real attack vector when rules.json originates outside the
agent's trust boundary. v1 hardening:

- **Library**: use the `regex` PyPI package (`regex>=2024.0`),
  **not** stdlib `re`. It supports a `timeout=` parameter on
  `match`/`fullmatch`/`search` calls that raises `TimeoutError`
  (Python builtin) when the matcher exceeds wall-clock budget.
- **Per-cell budget**: 100 ms (`defaults.regex_timeout`,
  configurable). On `TimeoutError`, emit a finding with
  `severity: error`, `rule_id: <rule.id>`,
  `message: regex evaluation timed out`,
  and increment `summary.regex_timeouts`.
- **Pattern linter at parse time**: reject patterns containing the
  classic ReDoS shapes (`(a+)+`, `(a*)*`, `(a|a)+`, `(a|aa)*`)
  detected by `recheck` (Python port of recheck-vm; fastest pure-
  Python ReDoS analyzer on PyPI) — **note**: `redos-detector` is an
  npm package, not a Python one, so it cannot be used here. If
  `recheck` is unavailable in the deployment environment, fall back
  to a hand-coded reject-list for the four shapes above. Operators
  of trusted rules.json files can override with
  `"unsafe_regex": true` per-rule (still subject to the per-cell
  timeout — defense in depth).
- **Compilation cache**: each unique pattern compiles once per run.

### 5.4 Date rules

All date predicates ignore the time component (Excel datetimes are
tz-naive; comparisons use date-only arithmetic).

| Check | Example | Meaning |
|---|---|---|
| `date_in_month:YYYY-MM` | `date_in_month:2026-05` | Date falls within calendar month. |
| `date_in_range:FROM,TO` | `date_in_range:2026-01-01,2026-12-31` | Inclusive date window. |
| `date_before:DATE` | `date_before:2026-06-01` | Strictly before. |
| `date_after:DATE` | `date_after:2026-01-01` | Strictly after. |
| `date_weekday:LIST` | `date_weekday:Mon,Tue,Wed,Thu,Fri` | Weekday filter (e.g. exclude weekends). |

#### 5.4.1 `is_date` recognition and the localization fallback

A cell is recognized as `date` (logical type) when **any** of:

1. `cell.is_date` is `True` per openpyxl (number-format string
   matches a date heuristic, e.g. `dd.mm.yyyy`, `mm/dd/yyyy`,
   `yyyy-mm-dd`, ISO/8601, etc.).
2. The cell is `<c t="d">` (rare; ISO 8601 string in `<v>`).
3. The cell is a `number` with value in the Excel-serial date range
   `[25569, 73050]` (1970-01-01 to 2099-12-31) **and** the column
   is annotated via `--treat-numeric-as-date COL,COL` flag (or
   per-rule `treat_numeric_as_date: true`). Rationale: Russian/JP
   locales often store dates with a number-format string that
   openpyxl's heuristic does not recognize as a date; the heuristic
   above lets a reviewer mark the column explicitly.
4. The cell is `text` and parses via `dateutil.parser.parse(s,
   fuzzy=False, dayfirst=...)`, **only** when
   `--treat-text-as-date COL,COL` is set. `dayfirst` is
   configurable per scope. Off by default because `dateutil` does
   not have a true strict mode — even with `fuzzy=False` it accepts
   `"42"` as `2042-01-01`. Opt-in only, for workbooks where the
   reviewer has confirmed the column contains only date-shaped
   strings.

If none match, `is_date` returns `false` and the date predicates
emit findings on the cell (since the rule asserted "this should be
a date and isn't").

#### 5.4.2 Localization caveats (honest scope)

- Excel locale-string number formats (e.g. `[$-419]dd.mm.yyyy` for
  Russian) are recognized by openpyxl's heuristic in modern
  versions; older versions miss them. Pin `openpyxl>=3.1.5` in the
  skill's `requirements.txt`.
- Year-only cells (`2026` as a number with format `0`) are **not**
  treated as dates even with the fallback — too ambiguous.

Arbitrary datetime arithmetic (`date - prev_row_date < 7d`) is
**not supported** in v1. Add a derived helper column in the
workbook if you need it.

### 5.5 Cross-cell aggregates

The right-hand side (or either side) of a comparison can be an
aggregate over another scope. Both sides may carry a sheet
qualifier per §4.1, including across sheets:

| Check | Meaning |
|---|---|
| `value == sum(col:X)` | Cell equals sum of column X (current sheet). |
| `value == avg(A2:A100)` | Cell equals average of range. |
| `sum(col:X) <= cell:H1` | Aggregate vs scalar in either direction. |
| `sum(Sheet1!col:Actual) <= cell:Summary!BudgetCap * 1.05` | Cross-sheet aggregate vs cross-sheet cell with arithmetic. |
| `sum('Q1 2026'!col:Hours) == cell:'Q1 2026'!H1` | Quoted sheet name inside aggregate. |

**Aggregate functions** (all take exactly one scope argument):
`sum`, `avg` (alias `mean`), `min`, `max`, `count`,
`count_nonempty`, `count_distinct`, `count_errors`, `stdev`
(sample standard deviation), `median`.

#### 5.5.1 Type policy in aggregates

Cells that are not `number` (per §3.5) are skipped silently by
numeric aggregates (`sum`/`avg`/`min`/`max`/`stdev`/`median`).
Counted in `summary.skipped_in_aggregates` per scope. Promote to
errors with `--strict-aggregates` (skipped cells become findings
with `rule_id: aggregate-type-mismatch`).

`count` counts every cell in scope (including empty/error).
`count_nonempty` excludes `empty`. `count_errors` counts only
`error`-type cells (handy for "no #N/A in this column" rules).

#### 5.5.2 Arithmetic operators

The DSL supports `+`, `-`, `*`, `/` between numeric operands
(literals, cell refs, aggregates). Precedence and associativity
follow Python (`*`/`/` bind tighter than `+`/`-`).

- **Integer operands** stay `int` for `+`/`-`/`*`; `/` always
  produces `float`.
- **Date operands**: arithmetic on dates is **not allowed** in v1.
  `cell:D1 - cell:D2` where both are dates raises `RulesParseError`
  at parse time (the parser knows the type via the §3.5 model only
  at evaluation, so this check is dynamic — finding emitted with
  `rule_id: rule-eval-error`, not a crash).
- **Division by zero**: `cell:Cap * 1.05` where Cap is `0` is fine;
  `value / cell:Cap` where Cap is `0` produces a finding with
  `severity: error`, `rule_id: rule-eval-error`,
  `message: division by zero in rule expression`. Counted in
  `summary.eval_errors`. The rule does **not** crash the run.
- **Overflow**: Python ints are arbitrary precision; floats follow
  IEEE 754 (`inf`/`nan`). Aggregates that produce `nan` (e.g.
  `avg` of an all-empty scope) emit one finding per affected
  scalar comparison with `rule_id: rule-eval-nan`.

#### 5.5.3 Aggregate caching

Identical aggregate expressions across rules are evaluated **once**
per run. Canonicalization (the cache key) folds:

- Whitespace and quote normalization.
- Sheet-qualifier resolution (default sheet → explicit name).
- Header lookup → column letter (including Table-fallback resolution
  per §4.3 — `col:Hours` resolved through Table T1's column shares
  a key with `table:T1[Hours]` if they refer to the same cell range).

Implication: 20 rules referencing `sum(col:Hours)` walk the column
once. Hash function: SHA-1 of canonical form (collision-free for
realistic rule counts).

Cache is process-local; not persisted across runs.

**Cache entry payload**: each entry stores **both** the computed
value AND the per-cell skip-or-error events:

```python
CacheEntry = (
    value,               # the aggregate result
    skipped_cells,       # list[CellRef] — non-numeric cells excluded
    error_cells,         # list[CellRef] — Excel-error cells encountered
    cache_hits,          # int — incremented each replay
)
```

When a second rule references the same scope, the cache returns
the value AND **replays** the skip/error events into that rule's
context. Under `--strict-aggregates`, each rule independently emits
`aggregate-type-mismatch` findings for `skipped_cells`.

Dedup semantics:

- **Intra-rule** (defensive): if a cache entry is replayed twice
  for the same `rule_id` (e.g. when a recursive aggregate triggers
  re-evaluation), the second replay is suppressed for that
  `(rule_id, cell)` pair. Findings are NOT double-emitted.
- **Inter-rule** (no dedup): the same cell skipped under N
  distinct rules counts N times — one finding per rule, one
  contribution to `summary.skipped_in_aggregates` per rule.

`summary.skipped_in_aggregates` therefore equals the number of
unique `(rule_id, cell)` pairs across the entire run. This makes
the cache semantically transparent: outputs are identical with or
without the cache, only timing differs.

`summary.aggregate_cache_hits` exposes the number of cache replays
for observability (used by regression fixture #19).

#### 5.5.4 Numeric tolerance

Equality on aggregates and on cell-vs-cell comparisons uses
`defaults.tolerance` (default `1e-9` absolute). Override per-rule
with `"tolerance": 0.01`. Inequalities (`<=`, `<`, `>=`, `>`) do
**not** apply tolerance — strict floating-point comparison.

### 5.6 Group-by aggregates

`sum_by:KEY OP X` partitions the scope by the values of column
`KEY` in the same row, applies the aggregate per group, and checks
each group's value.

| Check | Example | Meaning |
|---|---|---|
| `sum_by:KEY OP X` | `sum_by:WeekNum <= 40` | For each `WeekNum` group, the sum of the scope must satisfy the predicate. |
| `count_by:KEY OP X` | `count_by:Project >= 1` | Each distinct `Project` must appear at least once. |
| `avg_by:KEY OP X` | `avg_by:Department <= 8` | Each department's average ≤ 8. |

Findings for grouped rules carry `{group}` in the message and
`group` in the JSON.

**Empty / error group keys**:

- Cells where the group-key column is `empty` form a single
  synthetic group named `<empty>`. Their aggregate is computed
  normally and a finding (if produced) carries `group: null` in
  JSON / `<empty>` in human output.
- Cells where the group-key column is `error` are skipped from
  group-by aggregates (counted in `summary.skipped_in_aggregates`).

### 5.7 Composite checks (object form)

Boolean composition requires the object form:

```json
{
  "id": "submitted-and-realistic",
  "scope": "col:Hours",
  "check": {
    "and": [
      "value > 0",
      "value <= 24",
      { "or": ["value <= 8", "col:Status == 'Approved'"] }
    ]
  }
}
```

Operators: `and`, `or`, `not`. Each leaf is a string DSL
expression (any from §5.1–5.6).

**Depth limit**: composite trees are bounded to **16 levels** of
nesting. Deeper trees are rejected at parse time with exit 2
`RulesParseError: composite depth > 16`. This caps both authoring
mistakes and adversarial recursion. The limit is intentionally
generous — real rule files rarely exceed 4 levels.

## 6. AST and safety

The DSL parses into a **closed** set of node types listed below.
No attribute access (`.`), no function definition, no import, no
lambda, no `getattr`/`setattr`-equivalents. Implementation must use
a hand-written recursive-descent parser, **not** Python's `ast.parse`
(which would expose Python-syntax surface).

### 6.1 Allowed AST node types

| Node | Forms | Notes |
|---|---|---|
| `Literal` | int, float, str, bool, null, ISO date string | Strings JSON-quoted or unquoted in lists per §5.1. |
| `CellRef` | `cell:H1`, `H1` (in arithmetic context) | Always resolves through §3.5 type model. |
| `RangeRef` | `A2:A100` | |
| `ColRef` | `col:Hours`, `col:B`, `cols:A,B,C` | |
| `RowRef` | `row:5` | |
| `SheetRef` | `sheet:Timesheet` | |
| `NamedRef` | `named:TotalsRange` | |
| `TableRef` | `table:T1`, `table:T1[Hours]` | |
| `BuiltinCall` | `sum(...)`, `avg(...)`, `len(...)`, `count(...)`, etc. | Whitelist below. |
| `BinaryOp` | `==`, `!=`, `<`, `<=`, `>`, `>=`, `+`, `-`, `*`, `/` | No bitwise, no `%`, no `**`. |
| `UnaryOp` | unary `-`, unary `not` | |
| `In` | `value in [...]`, `value not in [...]` | |
| `Between` | `between:LO,HI`, `between_excl:LO,HI` | |
| `Logical` | `and: [...]`, `or: [...]`, `not: ...` | Object form (§5.7). Depth ≤ 16. |
| `TypePredicate` | `is_number`, `is_date`, `is_text`, `is_bool`, `is_error`, `required` | |
| `RegexPredicate` | `regex:PATTERN` | Compiled with `regex` library + timeout. |
| `LenPredicate` | `len OP N` | |
| `StringPredicate` | `starts_with:`, `ends_with:`, `not_empty` | |
| `DatePredicate` | `date_in_month:`, `date_in_range:`, `date_before:`, `date_after:`, `date_weekday:` | |
| `GroupByCheck` | `sum_by:KEY OP X`, `count_by:KEY OP X`, `avg_by:KEY OP X` | |

### 6.2 Allowed builtin functions

Whitelist (case-sensitive, no aliases beyond those listed):

```
sum  avg  mean  min  max  median  stdev
count  count_nonempty  count_distinct  count_errors
len
```

Any other identifier in a function-call position raises
`RulesParseError: UnknownBuiltin` at parse time.

### 6.3 String operations on `value`

`value` substitution for string interpolation in `message` uses
`string.Template` (`$value`, `${value}`), **not** Python's
`str.format`. This forecloses format-spec injection
(`{0.__class__.__mro__}`-style attribute access via `.format`).

The DSL itself does **not** interpolate cell values into
expressions; comparisons consume them via the AST evaluator.

### 6.4 Safety properties (claims and how they are tested)

1. **No code execution** — exhaustively tested by 30+ hostile
   rules-file fixtures (regression battery §13).
2. **Bounded memory** — file size cap (§2), composite depth cap
   (§5.7), regex-pattern lint (§5.3.1), aggregate cache reuse (§5.5.3).
3. **Bounded time** — per-rule regex timeout, per-run wall-clock
   limit (`--timeout`, default 300s), early exit on
   `--max-findings`.
4. **Deterministic output** — for the same workbook + rules, the
   findings array is byte-identical across runs. Sort key is the
   normalized 5-tuple `(sheet, row, column, rule_id, group)` with
   type-homogeneous sentinels for grouped findings (see §7.1.2).
   Code-point ordering for strings; locale-independent.

## 7. Output

### 7.1 stdout — findings JSON

```json
{
  "ok": false,
  "schema_version": 1,
  "summary": {
    "errors": 3,
    "warnings": 1,
    "info": 0,
    "checked_cells": 1240,
    "rules_evaluated": 7,
    "cell_errors": 2,
    "skipped_in_aggregates": 1,
    "regex_timeouts": 0,
    "eval_errors": 0,
    "aggregate_cache_hits": 4,
    "elapsed_seconds": 0.42,
    "truncated": false
  },
  "findings": [
    {
      "cell": "Timesheet!B17",
      "sheet": "Timesheet",
      "row": 17,
      "column": "B",
      "rule_id": "hours-realistic",
      "severity": "error",
      "value": 28,
      "message": "More than 24 hours in a day at row 17: 28"
    },
    {
      "cell": "Timesheet!H1",
      "sheet": "Timesheet",
      "row": 1,
      "column": "H",
      "rule_id": "totals-match",
      "severity": "error",
      "value": 156.5,
      "expected": 160.0,
      "tolerance": 0.01,
      "message": "Total in H1 does not match sum of Hours"
    }
  ]
}
```

#### 7.1.1 Field semantics

| Field | Always present | Notes |
|---|---|---|
| `ok` | yes | `true` iff zero `error`-severity findings (warnings/info do not flip it). |
| `schema_version` | yes | Currently `1`. Increments on breaking output-schema changes. |
| `summary.errors` / `warnings` / `info` | yes | **Unfiltered** total findings produced by the scan, regardless of `--severity-filter` or `--max-findings`. Reflects the workbook's actual state, not what is shown in `findings[]`. Consumers wanting the visible count should compute `len([f for f in findings if f.severity == "error"])`. |
| `summary.checked_cells` | yes | Cells touched by at least one rule (post-`skip_empty`). Cells that auto-emit `cell-error` (§5.0) are NOT counted here — they short-circuit before any rule's check. |
| `summary.rules_evaluated` | yes | Rules that ran at least once. |
| `summary.cell_errors` | yes | Cells with Excel error type (auto-emit per §5.0). |
| `summary.skipped_in_aggregates` | yes | Unique `(rule_id, cell)` pairs where a cell was excluded from a numeric aggregate (§5.5.1). De-duplicated across cache replays — same cell skipped under two rules counts as 2; same cell replayed twice for the same rule counts as 1. |
| `summary.aggregate_cache_hits` | yes | Number of times an aggregate value was served from the cache instead of recomputed (§5.5.3). 0 on a fresh run with no shared scopes; ≥ N − 1 when N rules reference the same canonical scope. |
| `summary.regex_timeouts` | yes | Per-cell regex evaluations that hit the budget. |
| `summary.eval_errors` | yes | Division-by-zero / NaN / type-mismatch in arithmetic. |
| `summary.elapsed_seconds` | yes | Wall-clock evaluation time (rounded to ms). |
| `summary.truncated` | yes | `true` if `--max-findings` cut the array short. |
| `findings[].cell` | yes | `Sheet!Ref` for per-cell findings; bare `Sheet` (no `!Ref`) for grouped findings. Sheet name un-quoted unless ambiguous. |
| `findings[].sheet` | yes | Plain sheet name. |
| `findings[].row` | yes | Cell row (`int`) for per-cell findings; `null` for grouped findings. |
| `findings[].column` | yes | Column letter (`str`) for per-cell findings; `null` for grouped findings. |
| `findings[].value` | yes | Cell value at evaluation time. For `error`-cells: the error string (`"#REF!"`). For aggregates: the computed aggregate. |
| `findings[].expected` | conditional | Present when the check has a computable RHS: aggregate equality, `between`, cell-vs-cell. **Not** present for `regex`/`is_*`/`required`/`len`/composite. |
| `findings[].tolerance` | conditional | Present iff the check used a tolerance (default or override). |
| `findings[].group` | conditional | Present iff the rule was a `*_by:KEY` aggregate. `null` for the synthetic empty-key group. |
| `findings[].rule_id` | yes | The rule's `id`, **or** synthetic `cell-error`/`rule-eval-error`/`rule-eval-timeout`/`rule-eval-nan`/`aggregate-type-mismatch`/`merged-cell-resolution`/`stale-cache-warning`/`max-findings-reached`/`no-data-checked`/`aggregate-cache-replay`. |
| `findings[].count` | conditional | Present iff this entry is a `--summarize-after` summary. Number of original findings collapsed. |
| `findings[].sample_cells` | conditional | Present iff this entry is a `--summarize-after` summary. First 10 collapsed cells (cell refs as strings). |

#### 7.1.2 Sort order

`findings` is sorted by a single normalized 5-tuple:
`(sheet_name, row, column_letter, rule_id, group)`.

To keep all elements **type-homogeneous** (Python 3 forbids
`int < str` in comparisons), the validator substitutes deterministic
sentinels for missing fields:

| Field | Per-cell finding | Group-aggregate finding | `cell-error` / `stale-cache-warning` |
|---|---|---|---|
| `row` | the cell's row (`int`) | `2**31 - 1` | the cell's row |
| `column_letter` | the cell's column (`str`) | `"￿"` | the cell's column |
| `rule_id` | rule's id | rule's id | synthetic id |
| `group` | `""` | the group label as `str` (or `""` for the synthetic empty group) | `""` |

Result: per-cell findings sort first by sheet/row/column; group
findings appear at the end of each sheet, ordered by rule_id then
group label. The 5-tuple is fully comparable: `int < int`,
`str < str`, deterministic across locales (Python sort is stable
and uses code-point ordering for `str`). Golden-file tests rely on
this contract.

The JSON `findings[]` entries always carry `row`/`column` as the
**actual** values (never sentinels) — sentinels exist only inside
the sort key. For group findings, `row` and `column` are emitted as
`null` in JSON (see §7.1.3).

#### 7.1.3 Grouped finding JSON shape

```json
{
  "cell": "Timesheet",
  "sheet": "Timesheet",
  "row": null,
  "column": null,
  "rule_id": "weekly-cap",
  "severity": "warning",
  "group": "W18",
  "value": 47.5,
  "expected": 40.0,
  "message": "Week W18: total exceeds 40h"
}
```

Fields:

- `cell` — bare sheet name (no `!Ref`) for grouped findings; consumers can use this as a stable identifier.
- `row`, `column` — `null` (group findings have no single anchor cell).
- `group` — the group key value as a string. `null` for the synthetic `<empty>` group (cells where the group-key column was empty).
- `value` / `expected` — the aggregate result and the predicate's RHS, when computable.
- `tolerance` — **omitted** in this example because the rule uses `<=` (an inequality, which per §5.5.4 does not apply tolerance). The field is present only when the check actually consumed a tolerance (equality / `between` / cell-vs-cell).

#### 7.1.4 Finding caps

`--max-findings N` (default `1000`) bounds the array length. When
hit:

- The validator stops emitting new findings but keeps walking the
  workbook to compute `summary` totals correctly.
- `summary.truncated` is `true`.
- The last entry of `findings` is a synthetic
  `{rule_id: "max-findings-reached", severity: "info",
  message: "Output truncated; N findings shown of M total"}`.

`--summarize-after N` (default `100` per `rule_id`) collapses runs
of the same `rule_id` into one summary entry once N have been
emitted, with `count` and a `sample_cells` array (first 10 cells).

### 7.2 stderr — human report

When `--json` is omitted, stdout is human-readable (rule id, cell,
severity, message) and the JSON envelope is suppressed. With
`--json`, the human report goes to stderr (still useful for
operators) and stdout is pure JSON for piping.

### 7.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | All rules pass (or only warnings/info, with no `--strict`). |
| 1 | At least one `error`-severity finding. |
| 2 | `RulesParseError`: rules file invalid (unknown check, bad scope, version mismatch, depth/size cap, YAML hardening rejection, unknown builtin, ambiguous/missing/merged header). |
| 3 | Workbook unreadable (encrypted — see cross-3 — or corrupt). |
| 4 | `--strict` and at least one `warning` finding. |
| 5 | I/O error on input/output paths. |
| 6 | `SelfOverwriteRefused`: `--output` resolves to the same path as the input (cross-7 H1 parity, follows symlinks via `Path.resolve()`). |
| 7 | Wall-clock timeout (`--timeout` exceeded). Partial findings flushed to stdout if `--json` is set. |

`--json-errors` (cross-5) wraps fatal errors (codes 2/3/5/6/7) in
the shared envelope; finding-level output (codes 0/1/4) always uses
the schema in §7.1.

## 8. CLI surface

```
xlsx_check_rules.py INPUT.xlsx --rules RULES.{json,yaml}
                    [--json | --no-json]
                    [--strict] [--require-data]
                    [--severity-filter error,warning,info]
                    [--max-findings N] [--summarize-after N]
                    [--timeout SECONDS]
                    [--sheet NAME] [--header-row N]
                    [--include-hidden | --visible-only]
                    [--no-strip-whitespace] [--no-table-autodetect]
                    [--no-merge-info] [--ignore-stale-cache]
                    [--strict-aggregates]
                    [--treat-numeric-as-date COLS] [--treat-text-as-date COLS]
                    [--output OUT.xlsx
                     [--remark-column auto|LETTER|HEADER]
                     [--remark-column-mode replace|append|new]
                     [--streaming-output]]
                    [--json-errors]
```

### 8.1 Flag reference

**Output mode**:
| Flag | Effect |
|---|---|
| `--json` | Stdout = findings JSON; stderr = human report. |
| `--no-json` | (default) Stdout = human report; no JSON envelope. |
| `--json-errors` | Wrap fatal errors (codes 2/3/5/6/7) in cross-5 envelope. |

**Severity & gating**:
| Flag | Effect |
|---|---|
| `--strict` | Promote any warning to non-zero exit (code 4). |
| `--require-data` | If `summary.checked_cells == 0`, exit code 1 with a synthetic finding `{rule_id: "no-data-checked", severity: "error"}` that bypasses `--severity-filter` (always visible). For CI use where an empty workbook is itself a regression. |
| `--severity-filter LIST` | Drop findings at unlisted severities from `findings[]` only; `summary.*` counts remain unfiltered totals. `--strict` reads `summary.warnings` (unfiltered) — so `--severity-filter error --strict` still trips on warnings. Comma-separated subset of `error,warning,info`. |

**Findings volume**:
| Flag | Default | Effect |
|---|---|---|
| `--max-findings N` | `1000` | Hard cap on `findings` array length. See §7.1.4. `0` disables cap (use with care; emits a stderr warning). |
| `--summarize-after N` | `100` | Per-`rule_id` summarization once N findings emitted. `0` disables. |

**Performance**:
| Flag | Default | Effect |
|---|---|---|
| `--timeout SECONDS` | `300` | Wall-clock cap; on timeout, exit 7 with partial findings if `--json`. |

**Sheet & header config**:
| Flag | Effect |
|---|---|
| `--sheet NAME` | Override `defaults.sheet`. |
| `--header-row N` | Override `defaults.header_row`. `0` disables header resolution. |
| `--include-hidden` | (default) Hidden rows/cols evaluated. |
| `--visible-only` | Skip hidden rows/cols. |
| `--no-table-autodetect` | Disable Excel-Table fallback for `col:HEADER` (§4.3). |
| `--no-strip-whitespace` | Disable default whitespace stripping on text cells (§3.5.3). |
| `--no-merge-info` | Suppress `merged-cell-resolution` info findings (§4.4). |

**Cache & error handling**:
| Flag | Effect |
|---|---|
| `--ignore-stale-cache` | Suppress the §5.0.1 stale-cache warning. |
| `--strict-aggregates` | Promote `aggregate-type-mismatch` skips to error findings (§5.5.1). |

**Date interpretation**:
| Flag | Effect |
|---|---|
| `--treat-numeric-as-date COLS` | Comma-separated list of column letters or headers; treat numeric serial in `[25569, 73050]` as dates (§5.4.1). Headers containing literal commas must use the alternate `;` separator (`--treat-numeric-as-date "Q1, 2026;Q2, 2026"`); the parser auto-detects which separator was used by checking whether the string contains `;` and switching mode. Pass an empty list (`--treat-numeric-as-date ''`) to disable per-rule overrides. |
| `--treat-text-as-date COLS` | Same separator semantics as above. Parses text via `dateutil` (off-default, permissive — opt-in only). |

**Workbook output**:
| Flag | Effect |
|---|---|
| `--output OUT.xlsx` | Write a copy of INPUT with remarks attached. Without `--remark-column`, this is just a copy with no modifications. |
| `--remark-column auto` | Add a `Remarks` column to the right of the data region (`auto` picks the next free column letter). |
| `--remark-column LETTER \| HEADER` | Place at specific letter (e.g. `Z`) or column with given header (e.g. `Notes`). |
| `--remark-column-mode replace\|append\|new` | When the remark column already exists: `replace` overwrites, `append` adds messages to existing content (newline-separated), `new` creates a sibling column with `_2` suffix (default `new` to preserve user data). |
| `--streaming-output` | Use openpyxl streaming-write path for large workbooks (≥ 100K cells); some fidelity trade-offs documented in §11. |

### 8.2 Mutually exclusive / dependent flags

- `--include-hidden` and `--visible-only` — mutex.
- `--remark-column` requires `--output`.
- `--remark-column-mode` requires `--remark-column`.
- `--streaming-output` requires `--output`.
- `--json` and `--no-json` — mutex.

#### 8.2.1 Streaming-output limitations

`openpyxl`'s `WriteOnlyWorkbook` is a one-pass writer with no read
API, which forecloses two combinations that look natural but
require reading existing cells:

- `--streaming-output` with `--remark-column auto` — auto-pick
  needs to know which column letters are already occupied.
  **Rejected** at arg-parse with exit 2 `IncompatibleFlags`.
  Workaround: pass an explicit letter (`--remark-column Z`).
- `--streaming-output` with `--remark-column-mode append` — append
  needs to read the existing cell value to concatenate. **Rejected**
  at arg-parse with exit 2 `IncompatibleFlags`. Workaround: use
  `--remark-column-mode replace` or `new`.

`--streaming-output` is compatible with:

- `--remark-column LETTER` (explicit column) — no auto-detection
  needed.
- `--remark-column-mode replace` — write-only.
- `--remark-column-mode new` — write-only (the new column gets a
  `_2` suffix unconditionally; collision detection is replaced by
  always-allocating-new).

This is documented honest scope: streaming mode trades some flag
combinations for the ability to handle ≥ 100K-cell workbooks.

### 8.3 Same-path guard

`--output OUT.xlsx` where `OUT.xlsx` resolves (via `Path.resolve()`,
following symlinks) to the same inode as `INPUT.xlsx` → exit 6
`SelfOverwriteRefused`. Mirrors the cross-7 H1 parity used by all
4 office skills.

## 9. Composition patterns

**Recalculate first** when the workbook has formulas (avoids the
§5.0.1 stale-cache warning and false `None == sum(...)` findings):

```bash
python3 scripts/xlsx_recalc.py timesheet.xlsx
python3 scripts/xlsx_check_rules.py timesheet.xlsx --rules rules.json
```

**Add a comment per finding** (requires `xlsx_add_comment.py`,
backlog `xlsx-6`).

`xlsx_add_comment.py --batch -` accepts stdin in **two shapes**
(auto-detected by JSON root type):

1. **Flat array** of explicit comment specs:
   `[{cell, author, text, [initials], [threaded]}, ...]`.
   Hand-authored or produced by other tooling.
2. **Findings envelope** as emitted by `xlsx_check_rules.py --json`:
   `{ok, summary, findings: [...]}`. xlsx-6 unpacks `.findings[]`
   and maps fields:
   - `cell` ← `findings[i].cell` (already in `Sheet!Ref` form).
   - `text` ← `findings[i].message`.
   - `author` ← `--default-author` flag (required when piping the
     envelope; xlsx-7 findings carry no `author` field).
   - `initials` ← derived from `--default-author` (first letter of
     each whitespace-separated token).
   - `threaded` ← `--default-threaded` flag (default `false`).
   - Findings with `row: null` (group-aggregate findings) are
     skipped — there is no single anchor cell to attach a comment
     to. Counted in xlsx-6's `summary.skipped_grouped` envelope.

The two shapes are distinguished by JSON root type: array → shape
1, object with `findings` key → shape 2. Anything else → exit 2
`InvalidBatchInput`.

```bash
# Direct pipe — xlsx-6 unpacks envelope, requires --default-author
xlsx_check_rules.py timesheet.xlsx --rules rules.json --json \
  | xlsx_add_comment.py timesheet.xlsx --batch - \
      --default-author "Reviewer Bot" \
      --output timesheet.reviewed.xlsx

# Equivalent explicit form via jq
xlsx_check_rules.py timesheet.xlsx --rules rules.json --json \
  | jq '[.findings[] | select(.row != null) |
         {cell, author: "Reviewer Bot", text: .message}]' \
  | xlsx_add_comment.py timesheet.xlsx --batch - \
      --output timesheet.reviewed.xlsx
```

The envelope-shape path is the documented happy path; the
flat-array form is the lower-level interface for bespoke scripts.

**Remark column without comments** (idempotent — second run goes
to `Remarks_2` by default, see `--remark-column-mode`):

```bash
xlsx_check_rules.py timesheet.xlsx --rules rules.json \
  --remark-column auto --output timesheet.reviewed.xlsx
```

**CI gate** (no output file, fail on warnings, require non-empty
data):

```bash
xlsx_check_rules.py timesheet.xlsx --rules rules.json \
  --strict --require-data
```

**Filter to errors only, for a clean PR comment**:

```bash
xlsx_check_rules.py timesheet.xlsx --rules rules.json --json \
  --severity-filter error
```

**Catastrophic-input mode** (workbook where most cells violate —
keep findings bounded so the downstream toolchain doesn't choke):

```bash
xlsx_check_rules.py noisy.xlsx --rules rules.json --json \
  --max-findings 200 --summarize-after 20
```

**Large-workbook streaming** (≥ 100K cells with output):

```bash
xlsx_check_rules.py big.xlsx --rules rules.json \
  --streaming-output --output reviewed.xlsx --remark-column auto
```

## 10. Worked example — timesheet review

`timesheet.rules.json`:

```json
{
  "version": 1,
  "defaults": { "sheet": "Timesheet", "severity": "error" },
  "rules": [
    {
      "id": "required-fields",
      "scope": "cols:Date,Hours,Project",
      "check": "required",
      "message": "Required field empty"
    },
    {
      "id": "hours-positive",
      "scope": "col:Hours",
      "check": "value > 0",
      "message": "Hours must be positive (got {value})"
    },
    {
      "id": "hours-realistic",
      "scope": "col:Hours",
      "check": "value <= 24",
      "message": "More than 24 hours at row {row}: {value}"
    },
    {
      "id": "date-in-period",
      "scope": "col:Date",
      "check": "date_in_month:2026-05",
      "message": "Date outside reporting period (May 2026)"
    },
    {
      "id": "project-code-format",
      "scope": "col:Project",
      "check": "regex:^[A-Z]{3}-\\d{4}$",
      "severity": "warning",
      "message": "Project code should match XXX-NNNN"
    },
    {
      "id": "weekly-cap",
      "scope": "col:Hours",
      "check": "sum_by:WeekNum <= 40",
      "severity": "warning",
      "message": "Week {group}: total exceeds 40h"
    },
    {
      "id": "totals-match",
      "scope": "cell:H1",
      "check": "value == sum(col:Hours)",
      "tolerance": 0.01,
      "message": "Total in H1 disagrees with sum of Hours column"
    },
    {
      "id": "approved-status",
      "scope": "col:Status",
      "check": "value in [Approved, Pending, Rejected]",
      "message": "Status must be Approved/Pending/Rejected"
    }
  ]
}
```

Run:

```bash
xlsx_check_rules.py timesheet.xlsx --rules timesheet.rules.json \
  --remark-column auto --output timesheet.reviewed.xlsx
```

Output: `timesheet.reviewed.xlsx` with a `Remarks` column (red for
error rows, yellow for warning rows) and `xlsx_check_rules.py`
exits 1 because of the error-severity findings.

## 11. Honest scope (v1)

What the v1 spec deliberately does **not** cover. Split into
"limitations of the rule language" and "limitations of the runtime."

### 11.1 Rule-language limitations

- **Cross-sheet JOIN-style lookups** — aggregates across sheets are
  fine (`sum(Sheet1!X)`), but `lookup`/`vlookup` semantics (find row
  in sheet B matching column from sheet A, then validate) are out
  of scope. Workaround: add a helper column in the workbook with
  the resolved value; validate that.
- **Arbitrary datetime arithmetic** — only the calendar predicates
  in §5.4. No `date - other_date < 7d`. Workaround: derived helper
  column.
- **Date arithmetic on cells** — `cell:D1 - cell:D2` between dates
  produces a `rule-eval-error` finding (§5.5.2), not a usable diff.
- **Auto-fix** — find/report only. Acting on findings is a separate
  step (xlsx-6 comments, `--remark-column`, or inline openpyxl).
- **Custom Python plugins / lambdas** — closed AST by design. A
  whitelisted entry-point mechanism may land as `xlsx-7a` if real
  use cases demand it.
- **Reading Excel-native `<dataValidations>` rules** — our rules
  live in the JSON/YAML file, not in the workbook. Mirroring native
  data-validation could land as `xlsx-7b`.
- **Localization of `message` strings** — `message` is a single
  string. If you need multi-language output, run the CLI twice
  with two rules files or post-process the JSON.
- **Multi-row / merged headers** — explicitly rejected at parse
  time (§4.2). Workaround: flatten the header row before validation.
- **Transposed layouts** (labels in column A, values flowing right)
  — no `transposed:` scope form. Workaround: pivot the sheet.
- **Multi-area defined names** (`Sheet1!A1:A10,Sheet1!B1:B10`) —
  rejected at parse time.
- **Bitwise / modulo / power operators** — not in §6.1. The DSL is
  for predicates, not number-crunching.

### 11.2 Runtime limitations

- **Excel Tables** — auto-detect via §4.3 covers the common case
  (data lives inside one Table on the active sheet). Cross-sheet
  Table address (`Sheet2!table:T1`) is supported; multi-sheet
  Tables-with-relations is not (Power Query model parts ignored).
- **Numeric serial date heuristic** is opt-in per column
  (`--treat-numeric-as-date`). v1 will not auto-detect Russian/JP
  locale dates that openpyxl misclassifies as numbers.
- **`Decimal` precision loss** — cells with `<c t="d">` decimal
  representation are coerced to `float` for arithmetic (§3.5.2);
  high-precision financial workbooks may see `1e-9` tolerance
  exhaustion.
- **Streaming output** (`--streaming-output`) — bypasses the
  full-fidelity write path; loses these on the output workbook:
  conditional formatting on the remark column (uses `PatternFill`
  via inline style instead), comments **on cells the validator did
  not modify** (preserved), drawings/charts (preserved), defined
  names (preserved). For deliveries that must round-trip every
  feature, do not use `--streaming-output`.
- **Read-only vs writable trade-off** — without `--output` and
  `--streaming-output`, the validator can stream-read up to ~1M
  cells. With `--output` and full-fidelity write, the practical
  limit is ~100K cells (read-write mode loads the full tree).
  Use `--streaming-output` to get back to ~1M.
- **Cached-value dependency** — formulas without cached values
  (xlsx that has not been recalc'd) read as `None`. v1 emits a
  one-time stale-cache warning (§5.0.1). Spurious findings are the
  user's responsibility — run `xlsx_recalc.py` first.
- **`is_date` localization** — see §5.4.2; ancient openpyxl missed
  some locale formats. Pin `openpyxl>=3.1.5`.
- **Excel error cells** — auto-emit `cell-error` finding (§5.0).
  Other rules on the same cell are skipped. To validate a cell
  whose formula intentionally returns `#N/A`, add an `is_error`
  rule with `severity: info`.
- **Hidden / very-hidden sheets** — `state="hidden"` and
  `state="veryHidden"` (the latter only settable via VBA, invisible
  in Excel's Show-Sheet dialog) are treated identically: included
  in `--sheet NAME` resolution (so a reviewer can target them
  explicitly), excluded from default-sheet auto-pick (§4). Rules
  run unless `--visible-only`. There is no `--visible-sheets-only`
  switch in v1.
- **`--remark-column` collision** — default mode `new` appends a
  `Remarks_2` column to preserve existing user data (§8.1
  workbook-output flags). `replace` and `append` are opt-in.
- **Excel 365 round-trip mutation** — if a user opens a validator-
  output `.xlsx` in Excel 365 and saves, Excel may reorder
  comments / promote legacy comments to threaded / re-encode
  shared strings. Goldens must be agent-output only, never
  Excel-touched.
- **Performance contract** — committed bound: 100K rows × 10
  rules ≤ 30 s wall-clock and ≤ 500 MB peak RSS on a 4-core
  machine, validated by regression-battery fixture
  `huge-100k-rows.xlsx`. Beyond that, no guarantees in v1.
- **Empty workbook** — `summary.checked_cells == 0` returns
  `ok: true` by default. Use `--require-data` if "no data" is
  itself a regression for your CI.
- **rules-file size cap** — 1 MiB hard limit (§2). Exceeds → exit
  2. v1 has no streaming rules-file loader; rules are resident.
- **In-process global state** — the validator is single-threaded
  by design. Concurrent runs against the same workbook with the
  same `--output` path produce a race; use distinct outputs or
  serialize.

## 12. Versioning

`version: 1` is the current rules-file schema. Backward-incompatible
changes (removing a check, changing scope semantics) bump to
`version: 2` and the CLI keeps a v1 compatibility path for at least
one minor release. Adding new checks within v1 is **not** a breaking
change.

The output JSON also has `schema_version` (§7.1) which evolves
independently of the rules-file `version`.

### 12.1 Stability promise

Within v1:

- **Field names** in `findings[]` are stable. New fields may be
  added (e.g. `group` was added for group-by aggregates); existing
  ones are not renamed.
- **Exit codes** are stable. New codes only at the high end (8+).
- **Sort order** of findings is stable (§7.1.2). Tooling can rely
  on byte-identical output across versions when no new checks are
  introduced.
- **Severity counts** in `summary` are **unfiltered totals** —
  they reflect the actual state of the workbook regardless of
  `--severity-filter` or `--max-findings`. The `findings[]` array
  is the **filtered/capped projection**; the `summary.*` numbers
  are the ground truth. Consumers should not assume
  `len(findings) == summary.errors + summary.warnings`. Use
  `summary.truncated` to detect when `findings[]` is incomplete.

### 12.2 Deprecation policy

A check can be deprecated within v1 (warning at parse time,
`--deny-deprecated` to harden) and removed in v2. Minimum two
minor releases of warning before removal.

## 13. Regression battery

Following the `q-7` (html2docx) pattern: per-fixture exact-equality
on counts, with required/forbidden `rule_id` needles. Tolerance
bands only on perf metrics. Three layers:

1. **Unit tests** — parser, AST evaluator, type coercion, scope
   resolver — small in-memory inputs.
2. **Battery** — `(workbook.xlsx, rules.json|yaml, expected.json)`
   triples exercised by `test_battery.py`.
3. **Canary meta-test** — `tests/canary_check.sh` saboteurs that
   confirm the battery actually catches regressions.

### 13.1 xlsx-7 fixtures (target: ≥ 21)

**Layout & schema variance**:

| # | Fixture pair | Locks |
|---|---|---|
| 1 | `clean-pass.xlsx` + `simple.rules.json` | happy path; ok=true; findings=[] |
| 2 | `timesheet-violations.xlsx` + `timesheet.rules.json` | needles `[hours-realistic, totals-match]`, forbidden `[hours-positive]` |
| 3 | `header-row-3.xlsx` + rules with `defaults.header_row: 3` | header-row override |
| 4 | `excel-table-data.xlsx` + `table-aware.rules.json` | `table:NAME` and `table:NAME[COL]` (§4.3) |
| 5 | `multi-row-headers.xlsx` + rules | exit 2 `MergedHeaderUnsupported` (§4.2) |
| 6 | `transposed-layout.xlsx` + rules | documented honest-scope error |
| 7 | `dup-header.xlsx` + rules | exit 2 `AmbiguousHeader` |
| 8 | `missing-header.xlsx` + rules | exit 2 `HeaderNotFound` with available-headers hint |
| 9 | `apostrophe-sheet.xlsx` + rules with `'Bob''s Sheet'!cell:A1` | sheet-name escaping (§4.1) |

**Type & error edges**:

| # | Fixture pair | Locks |
|---|---|---|
| 10 | `errors-as-values.xlsx` (`#REF!`, `#N/A`) + rules | auto-emit `cell-error`; other rules suppressed (§5.0) |
| 11 | `mixed-types-aggregate.xlsx` + `sum(col:Hours)` | `summary.skipped_in_aggregates: 1` (§5.5.1) |
| 12 | `mixed-types-aggregate.xlsx` + `--strict-aggregates` | finding `aggregate-type-mismatch` (§5.5.1) |
| 13 | `merged-data-cells.xlsx` + `cell:B1` (B1 in merge A1:C1) | resolves to A1 + emits one `merged-cell-resolution` info (§4.4) |
| 14 | `formulas-no-cache.xlsx` + cell-references | one stale-cache warning to stderr (§5.0.1); no spurious findings |
| 15 | `localized-dates-ru-text.xlsx` (Russian dates stored as `<c t="s">"01.05.2026"` text, NOT numeric serials with locale format — openpyxl cannot recognize text-stored dates regardless of version) + `date_in_month` rule (no override) | misfires per honest scope; needles forbid `[date-in-period]`. Distinct from numeric-serial path which `openpyxl>=3.1.5` does handle (§5.4.2). |
| 16 | same fixture + `--treat-text-as-date Date` | `date-in-period` fires correctly (§5.4.1 path 4) |
| 17 | `whitespace-values.xlsx` (`" PRJ-001 "`) + `value == 'PRJ-001'` | passes (default strip); same fixture with `--no-strip-whitespace` → fails |

**Cross-sheet & aggregates**:

| # | Fixture pair | Locks |
|---|---|---|
| 18 | `multi-sheet-aggregates.xlsx` + rule `sum(Sheet1!col:Actual) <= cell:Summary!Cap` | cross-sheet syntax (§5.5) |
| 19 | `aggregate-cache.xlsx` (10K rows, single Hours column with numeric data) + 5 rules each containing `sum(col:Hours)` as the RHS | `summary.aggregate_cache_hits == 4` (5 references − 1 fresh compute = 4 replays); `summary.elapsed_seconds < 2.0` absolute (generous CI bound for 10K-row scan; relax proportionally if the fixture is regenerated at a different size). The counter — not the timing — is the primary assertion; timing is a sanity bound. |
| 19a | `aggregate-cache-strict.xlsx` (Hours has 1 stray text) + 2 rules sharing `sum(col:Hours)` + `--strict-aggregates` | `summary.aggregate_cache_hits == 1`; `summary.skipped_in_aggregates == 2` (1 cell × 2 rules — replayed per rule); 2 findings with `rule_id: aggregate-type-mismatch` (one per rule). Locks §5.5.3 cache-replay determinism. |
| 20 | `divide-by-zero.xlsx` + rule `value / cell:Cap` (Cap=0) | finding `rule-eval-error`; no crash |
| 21 | `nan-aggregate.xlsx` (empty column) + `value == avg(col:X)` | finding `rule-eval-nan` |

**Adversarial / DoS** (must reject quickly, ≤ 100 ms):

| # | Fixture pair | Locks |
|---|---|---|
| 22 | any.xlsx + `regex-dos.rules.json` (`^(a+)+$`) | `recheck` reject at parse; OR per-cell timeout → `rule-eval-timeout` |
| 23 | any.xlsx + `billion-laughs.rules.yaml` | exit 2; anchor reject pre-composition (§2.1) |
| 23a | any.xlsx + `yaml-string-with-ampersand.rules.yaml` (`description: 'see Q1 & Q2'`) | **negative regression**: must NOT exit 2 — `&` in string scalar is legitimate, byte-scanner false-positive guard |
| 24 | any.xlsx + `yaml-custom-tag.rules.yaml` (`!!python/object`) | exit 2 |
| 25 | any.xlsx + `yaml11-bool-trap.rules.yaml` (`value in [yes, no]`) | strings stay strings (§2.1) |
| 26 | any.xlsx + `yaml-dup-keys.rules.yaml` | exit 2 |
| 27 | any.xlsx + `deep-composite.rules.json` (1000-level `and`) | exit 2 `CompositeDepth` (§5.7) |
| 28 | any.xlsx + `huge-rules.json` (1.5 MB) | exit 2 `RulesFileTooLarge` (§2) |
| 29 | `format-string-injection.xlsx` (cell value `${value}` literal) + rule with `message: "got: $value"` | message renders as `got: ${value}` literally (Template-style, §6.3) |
| 30 | any.xlsx + `unknown-builtin.rules.json` (`foo(col:X)`) | exit 2 `UnknownBuiltin` (§6.2) |

**Scale & perf**:

| # | Fixture pair | Locks |
|---|---|---|
| 31 | `huge-100k-rows.xlsx` + `5-rule.rules.json` | wall ≤ 30 s, RSS ≤ 500 MB (§11.2 perf contract) |
| 32 | `huge-100k-rows.xlsx` + `--max-findings 200 --output OUT.xlsx --streaming-output` | `summary.truncated: true`; output written |
| 32a | `huge-100k-rows.xlsx` + `--streaming-output --remark-column auto --output OUT.xlsx` | exit 2 `IncompatibleFlags` (§8.2.1) |
| 32b | `huge-100k-rows.xlsx` + `--streaming-output --remark-column Z --remark-column-mode append --output OUT.xlsx` | exit 2 `IncompatibleFlags` (§8.2.1) |
| 32c | `huge-100k-rows.xlsx` + `--streaming-output --remark-column Z --remark-column-mode replace --output OUT.xlsx` | exit 1 with findings; output has remarks in column Z |
| 33 | `noisy-all-violate.xlsx` (every cell breaks) + `--summarize-after 20` | `findings` length ≤ 21 per rule; sample_cells populated |

**Output mode**:

| # | Fixture pair | Locks |
|---|---|---|
| 34 | reviewed.xlsx round-trip — `--output reviewed.xlsx --remark-column auto` (no existing Remarks col) | new column at first free letter; PatternFill applied |
| 35 | re-run on reviewed.xlsx (Remarks already exists) | default `--remark-column-mode new` → `Remarks_2` created; original preserved |
| 36 | empty.xlsx + `--require-data` | exit 1 with `no-data-checked` finding |
| 37 | input == output path | exit 6 `SelfOverwriteRefused` |
| 38 | encrypted.xlsx | exit 3 `EncryptedInput` (cross-3) |
| 39 | full pipeline: `--json | xlsx_add_comment.py --batch -` | output xlsx has matching comments per finding (xlsx-6 integration) |

### 13.2 xlsx-6 fixtures (target: ≥ 9, see backlog row)

Listed in the xlsx-6 backlog entry; cross-referenced here for the
canary meta-test (a sabotage in xlsx-6 should not cause xlsx-7
fixtures 39 to silently pass).

### 13.3 Canary saboteurs

`tests/canary_check.sh` reverts each saboteur via `trap`. The
battery must FAIL for each:

1. Make `regex` matcher always return `True` → fixtures 2, 22 fail.
2. Make `sum_by` ignore the group key → fixtures 2 (weekly-cap), 11 fail.
3. Make text-stored dates always parse as dates (bypass §5.4.1 path-4 opt-in gate) → fixtures 15, 16 fail (15 expects misfire without flag; 16 expects fire with flag — auto-parse breaks both invariants).
4. Skip merged-cell detection in headers → fixture 5 fails (silent misfire).
5. Disable ruamel.yaml AliasEvent rejection (skip event-stream filter) → fixture 23 fails (no exit 2; alias expands and consumes memory).
6. Disable `recheck` ReDoS pattern lint → fixture 22 fails OR per-cell timeout > 100 ms.
7. Disable composite-depth cap → fixture 27 fails.
8. Skip `cell-error` auto-emit → fixture 10 fails (no `cell-error` needle).
9. Disable aggregate cache → fixture 19 fails (`summary.aggregate_cache_hits` becomes 0, not 4 — counter assertion trips reliably regardless of CI box speed).
10. Use `str.format` instead of `string.Template` → fixture 29 fails (Python attribute access in message).

Without canary, a green battery is indistinguishable from a battery
permanently broken by an evaluator that emits no findings.

### 13.4 Property-based fuzz (q-5 pattern)

Hypothesis strategies for v2 (post-implementation):

- **Random rule generator** that produces only well-formed AST
  trees from §6.1 — invariant: parse → emit → re-parse round-trips
  byte-identically.
- **Random workbook generator** with mixed cell types — invariant:
  `summary.errors + summary.warnings + summary.info ≤ summary.checked_cells × N_rules`.
- **No-crash invariant** for arbitrary JSON input under 1 MiB —
  exit code is one of {0, 1, 2, 3, 4, 5, 6, 7}; never an
  unhandled traceback.
