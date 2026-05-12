# TASK 010 — xlsx-8: `xlsx2csv.py` / `xlsx2json.py` read-back CLIs

> **Mode:** VDD (Verification-Driven Development).
> **Source backlog row:** [`docs/office-skills-backlog.md`](office-skills-backlog.md) → `xlsx-8`.
> **Status:** DRAFT v1 — pending Task-Reviewer approval.
> **Predecessor:** TASK 009 (`xlsx-10.A` — `xlsx_read/`) — ✅ MERGED
> 2026-05-12. Archive: [`docs/tasks/task-009-xlsx-read-library-master.md`](tasks/task-009-xlsx-read-library-master.md).

---

## 0. Meta Information

- **Task ID:** `010`
- **Slug:** `xlsx-read-back`
- **Backlog row:** `xlsx-8` (depends-on `xlsx-10.A`, ✅ shipped).
- **Target skill:** `skills/xlsx/` (Proprietary — see CLAUDE.md §3, `skills/xlsx/LICENSE`).
- **Cross-skill replication:** **None.** xlsx-8 is xlsx-specific. The
  12-line `diff -q` gate (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`) MUST remain silent — none of those
  files are touched.
- **Mode flag:** Standard (no `[LIGHT]`).
- **Reference docs:**
  - `xlsx_read/` public surface: [`skills/xlsx/scripts/xlsx_read/__init__.py`](../skills/xlsx/scripts/xlsx_read/__init__.py).
  - Round-trip contract (xlsx-2 ↔ xlsx-8): [`skills/xlsx/references/json-shapes.md`](../skills/xlsx/references/json-shapes.md) — to be **updated** by this task with nested-multi-table shape.
  - Sibling write-side shim (pattern source): [`skills/xlsx/scripts/json2xlsx.py`](../skills/xlsx/scripts/json2xlsx.py) (53 LOC).
  - Cross-cutting envelope helper: [`skills/xlsx/scripts/_errors.py`](../skills/xlsx/scripts/_errors.py) (4-skill replicated).

---

## 1. General Description

### 1.1. Goal
Ship **two CLI shims** — `skills/xlsx/scripts/xlsx2csv.py` and
`skills/xlsx/scripts/xlsx2json.py` — plus an in-skill package
`skills/xlsx/scripts/xlsx2csv2json/` (single package serving both
shims) that converts an `.xlsx` workbook into CSV (per-sheet /
per-table) or JSON (array-of-objects / nested dict per sheet per
table). All reader logic (merge resolution, ListObjects, gap-detect,
multi-row headers, hyperlinks, stale-cache) is **delegated** to the
shipped `xlsx_read/` library — the shims own only emit-side concerns
(CLI parsing, JSON/CSV serialisation, cross-cutting envelopes, file
I/O).

### 1.2. Motivation
- Closes the **read-back gap**: `csv2xlsx.py` / `json2xlsx.py` are
  one-way; consuming a user's `.xlsx` requires either manual OOXML
  unpack or invoking `xlsx_check_rules.py` with empty rules — both
  footguns for the "analyse my spreadsheet" use case.
- Provides the **symmetric round-trip pair** to xlsx-2
  (`json2xlsx.py`): `xlsx2json → edit JSON → json2xlsx` pipeline.
  Live round-trip test in xlsx-2 is gated with
  `@unittest.skipUnless(...)` and **activates** at xlsx-8 merge.
- Reuses **the foundation**: `xlsx_read/` was shipped specifically to
  unblock xlsx-8 + xlsx-9. Effort stays **S** because the heavy
  reader-logic is already done; xlsx-8 is emit-only.

### 1.3. Connection with the existing system

**Imports (consumed without modification):**
- `xlsx_read.open_workbook`, `xlsx_read.WorkbookReader`,
  `xlsx_read.SheetInfo`, `xlsx_read.TableRegion`, `xlsx_read.TableData`,
  `xlsx_read.MergePolicy`, `xlsx_read.TableDetectMode`,
  `xlsx_read.DateFmt`, plus typed exceptions
  (`EncryptedWorkbookError`, `MacroEnabledWarning`,
  `OverlappingMerges`, `AmbiguousHeaderBoundary`, `SheetNotFound`).
- `_errors.report_error`, `_errors.add_json_errors_argument`
  (cross-5 envelope).
- `office_passwd.py` is **NOT** imported (encryption detection
  already inside `xlsx_read._workbook`).

**Activates round-trip contract** at merge:
- xlsx-2 (`json2xlsx/tests/test_json2xlsx.py::TestRoundTripXlsx8`)
  — `@unittest.skipUnless(...)` gate flipped to live after this task
  lands (mirror the xlsx-9 ↔ xlsx-3 pattern).
- `skills/xlsx/references/json-shapes.md` — updated with the
  **nested multi-table** shape introduced by `--tables != whole` (new
  `tables: {NAME: [...]}` field under each sheet key).

**Out of scope (separate tickets):**
- xlsx-9 (`xlsx2md.py`) — own task; shares `xlsx_read/` but is
  emit-only into markdown, owns its own `xlsx2md/` package.
- xlsx-10.B (xlsx-7 refactor) — gated on xlsx-9 merge + 14-day
  ownership clock; not unblocked by this task.
- xlsx-2 v2 `--write-listobjects` flag — required for full
  round-trip with `--tables listobjects`; deferred to xlsx-2 v2 per
  honest scope (see §1.4 below).

### 1.4. Honest scope (v1 — explicitly out of scope)

These items are **deliberately deferred**. Each is documented in the
relevant module docstring AND locked by a regression test where
applicable.

- **(a) Cached value only.** Formulas resolve to cached values by
  default. If cached value is missing (`cell.value is None` + formula
  present), a `stale-cache` warning is surfaced. Caller is expected
  to run `xlsx_recalc.py` upstream when cached values are needed.
- **(b) Rich-text spans → plain-text concat.** Bold/italic runs
  inside a cell are flattened (delegated to `xlsx_read._values`).
- **(c) Cell styles dropped.** Color / font / fill / border /
  alignment / conditional formatting are NOT emitted (parallel
  xlsx-9).
- **(d) Comments dropped.** Excel comments are NOT emitted in v1.
  Deferred to v2 sidecar pattern à la docx-4 (`xlsx2json.comments.json`).
- **(e) Charts / images / shapes / pivot-source / data-validation
  dropped.** Markdown/CSV/JSON cannot represent these. `preview.py`
  remains the canonical visual path.
- **(f) ListObject `headerRowCount ≠ 1` per-region fallback.** When
  a ListObject's `headerRowCount` is neither `1` nor consistent with
  the requested `--header-rows`, that region falls back to gap-detect
  for header determination (already implemented in `xlsx_read`).
- **(g) Workbook-scope named ranges ignored.** Only sheet-scope
  named ranges feed Tier-2 of `detect_tables`.
- **(h) Shared / array formulas → cached value only.**
- **(i) `AmbiguousHeader` warning, never raise.** When `--header-rows
  auto` AND a merge straddles header/body boundary, library emits
  warning via `xlsx_read.AmbiguousHeaderBoundary` (subclass of
  `UserWarning`); shim surfaces as soft warning in `summary.warnings`.
- **(j) `--write-listobjects` round-trip dependency.** Restoring
  ListObjects via xlsx-2 consumer (the reverse direction) requires a
  future xlsx-2 v2 flag. xlsx-8 emits the nested-multi-table shape
  but xlsx-2 v1 will collapse it to flat sheets; full round-trip is a
  v2 concern.
- **(k) No `eval` / no shell / no subprocess / no network.**
  Pure-Python read path inherited from `xlsx_read/`.
- **(l) `--tables listobjects` includes Tier-2 named ranges silently.**
  The library `xlsx_read.WorkbookReader.detect_tables(mode="tables-only")`
  returns Tier-1 ListObjects **+** Tier-2 sheet-scope named ranges
  (`<definedName>` entries with `localSheetId`). The shim does NOT
  filter Tier-2 out — sheet-scope named ranges are functionally
  equivalent to Excel-explicit tables (both are user-declared
  rectangular regions). Behaviour is documented in the shim
  `--help` epilogue and in `xlsx2csv2json/__init__.py` module
  docstring. `--tables gap` is the inverse: shim calls library
  `mode="auto"` then filters out regions where
  `region.source != "gap_detect"` (no library API extension in v1;
  see Q-A6).
- **(m) `--include-hyperlinks` forces `read_only_mode=False`** at
  workbook open (vdd-multi C1 fix). openpyxl's `ReadOnlyCell` does
  NOT expose `cell.hyperlink` — the data lives in
  `xl/worksheets/_rels/sheetN.xml.rels` and is only joined to cells
  by the in-memory `Worksheet` (non-streaming). The library
  auto-selects `read_only=True` for files > 10 MiB; to make the flag
  actually work, the shim overrides to `read_only=False` when
  hyperlinks are requested. Trade-off: increased memory cost for
  large workbooks (caller-controlled, opt-in).
- **(n) `--datetime-format raw` (JSON) emits ISO-8601** strings
  (vdd-multi H1 fix). The library returns native Python `datetime`
  objects; stdlib `json` cannot encode them, so the shim coerces
  via `.isoformat()`. Net: `raw` and `ISO` produce **identical** JSON
  output today. The flag distinction is meaningful for Python
  callers using the library directly, NOT for CLI JSON output.
  CSV path is unaffected (it str()-coerces via `csv.writer`).
- **(o) Multi-region CSV same-name regions get a `__N` suffix**
  (vdd-multi M2 fix). Two regions sharing `(sheet, region_name)` —
  most commonly a ListObject named `Table-1` colliding with a
  gap-detect fallback `Table-1` — previously silently overwrote.
  The shim now appends `__2`, `__3`, ... to the second-and-later
  collisions during a single emit pass. Region names that already
  contain literal `__` are unaffected; the suffix is applied only
  on file-path collision.
- **(p) Internal errors surface as redacted envelopes**
  (vdd-multi H3 fix). Exceptions outside the documented dispatch
  table (`PermissionError`, `OSError`, generic `RuntimeError`, etc.)
  are caught by a terminal envelope branch and rendered as
  `Internal error: <ClassName>` with empty `details` — the raw
  message is dropped to prevent absolute-path leaks from openpyxl /
  xlsx_read internals. For local debugging, run without
  `--json-errors` to see the Python traceback.

---

## 2. Requirements Traceability Matrix (RTM)

**Convention:** Epics (`E*`) group cohesive feature areas; Issues
(`R*`) are atomic, testable requirements within an Epic. Sub-features
are granularity ≥ 3 per Issue (per `skill-task-model`). MVP column
marks ship-blocking work for v1.

### Epic E1 — Package + Shim Skeleton

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R1** | Two CLI shims with single package backend | ✅ | (a) `skills/xlsx/scripts/xlsx2csv.py` ≤ 60 LOC re-export shim; (b) `skills/xlsx/scripts/xlsx2json.py` ≤ 60 LOC re-export shim; (c) `skills/xlsx/scripts/xlsx2csv2json/` package — modules per single-responsibility (cli, dispatch, emit_csv, emit_json, cli_helpers, exceptions, `__init__.py`); (d) public helpers `convert_xlsx_to_csv(input_path, output_path, **kwargs) -> int` and `convert_xlsx_to_json(input_path, output_path, **kwargs) -> int` in `__init__.py` (single source of truth — shim only dispatches). |
| **R2** | Shim dispatch via `--format csv\|json` | ✅ | (a) `xlsx2csv.py` hard-binds `--format csv` (rejects override at parse time); (b) `xlsx2json.py` hard-binds `--format json`; (c) one shared `cli.py:main(argv)` orchestrator dispatches by format; (d) regression test: `xlsx2csv.py --format json` exits 2 with envelope `FormatLockedByShim`. |
| **R3** | Package import hygiene | ✅ | (a) `sys.path.insert(0, parent)` once in each shim so package can resolve `_errors`; (b) `from xlsx2csv2json import main, convert_xlsx_to_csv, convert_xlsx_to_json, _AppError, …` re-export list mirrors `json2xlsx.py` pattern; (c) ruff check clean (`pyproject.toml` from xlsx-10.A is reused — no new banned-api rule needed). |

### Epic E2 — Core CLI Surface (backward-compat defaults)

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R4** | Input + output args | ✅ | (a) Positional `INPUT` (path to `.xlsx`/`.xlsm`); (b) optional `--output OUT` (stdout if omitted, dash `-` for stdout-explicit); (c) `--output` supports paths whose parent does NOT yet exist (auto-create parent dir, csv2xlsx parity); (d) cross-7 H1 same-path canonical-resolve guard: `--output INPUT.xlsx` after `Path.resolve()` symlink-follow → exit 6 `SelfOverwriteRefused` (mirror json2xlsx). |
| **R5** | Sheet selector | ✅ | (a) `--sheet NAME` returns single-sheet output; (b) `--sheet all` (default) returns multi-sheet output — JSON dict-of-arrays / CSV multi-file via `--output-dir`; (c) missing sheet name → exit 2 envelope `SheetNotFound` (typed exception from `xlsx_read` re-mapped); (d) `--include-hidden` opt-in (default skip hidden + veryHidden). |
| **R6** | Format defaults (backward-compat lock) | ✅ | (a) `--header-rows 1` default (single-row header); (b) `--merge-policy anchor-only` default; (c) `--tables whole` default (entire sheet = one region); (d) `--include-hyperlinks` off by default; (e) `--include-formulas` off by default (cached value only); (f) `--datetime-format ISO` default; (g) regression test pins the all-flags-omitted output shape against a synthetic 5-cell fixture: flat JSON array-of-objects for single sheet; dict-of-arrays per sheet for `--sheet all`; single-row header from row 1; merged cells use `anchor-only` policy; no hyperlinks / formulas; ISO-8601 datetime. NOT a comparison against a prior implementation. |

### Epic E3 — Complex Table Support (opt-in, parity with xlsx-9)

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R7** | Multi-row headers (`--header-rows`) | ✅ | (a) `--header-rows N` (int) flattens top `N` rows with `xlsx_read.detect_header_band` short-circuit; (b) `--header-rows auto` activates `xlsx_read` `detect_header_band` autodetection; (c) **flatten separator** ` › ` (U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK) — banned in spreadsheet headers, mirror `/` separator NOT used (collides with `"Q1 / Q2 split"`); (d) optional `--header-flatten-style string\|array` (JSON output only): `string` → flat `"2026 plan › Q1"` keys; `array` → keys-array `["2026 plan", "Q1"]` (resolves residual collision); (e) **H3 lock**: `--header-rows N` (int) + `--tables != whole` → exit 2 `HeaderRowsConflict` envelope (per-table header counts differ); force `auto` when multi-table. |
| **R8** | Body merge policy (`--merge-policy`) | ✅ | (a) `anchor-only` (default): only top-left of merge carries value (rest `None`/empty cell); (b) `fill`: anchor value duplicated to ALL child cells in span (denormalisation for grouping); (c) `blank`: anchor carries value, children blank (row width preserved); (d) delegated to `xlsx_read.WorkbookReader.read_table(..., merge_policy=...)` — no shim re-implementation. |
| **R9** | Multi-table-per-sheet (`--tables`) | ✅ | (a) `whole` (default, backward-compat): single region spanning sheet used range; (b) `listobjects`: read `xl/tables/tableN.xml` only (Tier-1); (c) `gap`: gap-detection only (Tier-3); (d) `auto`: 1→3 fallthrough — try listobjects first, fall back to gap; (e) `--gap-rows N` (default **2**) — M4 VDD-adversarial fix vs naive default 1; (f) `--gap-cols N` (default **1**); (g) all delegated to `xlsx_read.WorkbookReader.detect_tables(..., mode=..., gap_rows=..., gap_cols=...)`. |
| **R10** | Hyperlinks (`--include-hyperlinks`) | ✅ | (a) Default off (backward-compat); (b) JSON cells emit `{"value": "click here", "href": "https://..."}` for cells with `cell.hyperlink` (R3-L1 fix locks the dict-shape); (c) CSV cells emit `[text](url)` markdown-link-as-text for symmetry with xlsx-9 markdown emission; (d) NEVER emit `=HYPERLINK("url","text")` formula syntax (R4-L2 lock — Excel-reopen attack surface + literal `=`-prefix confuses humans); (e) NEVER emit `<header>` + `<header>_href` two-column form (column-count lossy). |

### Epic E4 — Output Shapes

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R11** | JSON shape | ✅ | (a) Single sheet, single-region: flat `[{header1: val1, ...}, ...]`; (b) `--sheet all`, single-region per sheet: `{"Sheet1": [{...}], "Sheet2": [{...}]}`; (c) `--sheet all` AND `--tables != whole` AND >1 region/sheet: nested `{"Sheet1": {"tables": {"TableA": [...], "TableB": [...]}}}` (R3-L1 lock — `tables` is the round-trip-frozen key); (d) single-sheet `--tables != whole` with multiple regions: `{"TableA": [...], "TableB": [...]}` (no enclosing sheet key); (e) single-sheet single-region falls through to flat (backward-compat). |
| **R12** | CSV shape | ✅ | (a) Single-region: write to `--output` or stdout (RFC-4180-ish quoting via `csv.writer(quoting=QUOTE_MINIMAL)`); (b) multi-region requires `--output-dir DIR`; (c) **subdirectory schema** `DIR/<sheet>/<table>.csv` (L4 VDD-adversarial fix — NOT `DIR/<sheet>__<table>.csv`, because sheet names may legally contain `__`); (d) **fail-loud envelope** exit 2 `MultiTableRequiresOutputDir` when `--tables != whole` AND CSV output is single-file/stdout AND > 1 region detected; (e) parent dirs auto-created (csv2xlsx parity); (f) **`--sheet all` AND CSV output to single-file/stdout AND > 1 visible sheet** → exit 2 `MultiSheetRequiresOutputDir` envelope (CSV cannot multiplex multiple sheets into a single stream — distinct from R12.d which concerns multi-region within a single sheet). |
| **R13** | Round-trip contract update | ✅ | (a) Append to `skills/xlsx/references/json-shapes.md` — nested multi-table shape (`{Sheet: {tables: {Name: [...]}}}`); (b) document explicit honest-scope: xlsx-2 v1 **drops** the `tables` key on consume (flat-sheet shape only); xlsx-2 v2 `--write-listobjects` flag will reverse-restore (deferred); (c) live round-trip test in xlsx-2's `TestRoundTripXlsx8` flips from `@unittest.skipUnless(xlsx8_exists)` to **always-run** at xlsx-8 merge. |

### Epic E5 — Cross-Cutting Parity

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R14** | Cross-3 — encrypted input | ✅ | (a) Library raises `EncryptedWorkbookError` (typed); (b) shim catches → emit cross-5 envelope `{v:1, error, code:3, type:"EncryptedWorkbookError", details:{filename:basename}}`; (c) exit 3; (d) regression test with encrypted fixture. |
| **R15** | Cross-4 — macro-bearing input | ✅ | (a) Library emits `MacroEnabledWarning` via `warnings.warn`; (b) shim captures via `warnings.catch_warnings(record=True)` and surfaces in `summary.warnings`; (c) **does NOT raise** — `.xlsm` files are read; warning is informational; (d) regression test with `.xlsm` fixture. |
| **R16** | Cross-5 — `--json-errors` envelope | ✅ | (a) `add_json_errors_argument(parser)` adds the standard flag; (b) ALL fail paths route through `report_error()` (no ad-hoc `sys.exit`); (c) envelope shape `{v:1, error, code, type, details}` byte-identical to xlsx-2/-3 (regression via 3-way drift test if practical, otherwise type assertion against `_errors._SCHEMA_VERSION == 1`); (d) `code` is **never** 0 (guarded by `_errors.report_error`). |
| **R17** | Cross-7 — H1 same-path guard | ✅ | (a) Canonical-resolve via `Path.resolve()` follows symlinks (csv2xlsx parity); (b) same-path → exit 6 `SelfOverwriteRefused`; (c) cross-checks `--output-dir` ROOT against input dir (mismatch is fine; collision detected by file-level check, not dir prefix); (d) regression test: symlink `out.xlsx -> input.xlsx` → exit 6. |

### Epic E6 — Honest-Scope Locks + Tests

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R18** | Honest-scope documentation | ✅ | (a) Module docstring in `xlsx2csv2json/__init__.py` enumerates §1.4 honest scope verbatim; (b) `skills/xlsx/.AGENTS.md` gains `## xlsx2csv2json` section pointing to TASK §1.4; (c) `skills/xlsx/SKILL.md` registry gains xlsx2csv.py + xlsx2json.py rows. |
| **R19** | Test suite (≥ 25 E2E + full unit per module) | ✅ | (a) Unit tests per module (cli, emit_csv, emit_json, dispatch, helpers, exceptions) — ≥ 60 unit tests total; (b) 25 E2E scenarios fixed list in §5.5 (acceptance criteria); (c) `validate_skill.py skills/xlsx` exit 0; (d) all existing xlsx-* E2E suites green (no-behaviour-change for shared infra). |
| **R20** | Post-validate hook (env-flag opt-in) | 🟡 | (a) `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1` env-flag invokes downstream validator on JSON-shape only (CSV has no schema); (b) JSON validator: `json.loads()` round-trip — ensures the shim emitted valid JSON before exit (defends against truncation); (c) on failure: exit 7 `PostValidateFailed` envelope; (d) default OFF (parallel xlsx-2 / xlsx-3 D8 pattern). |

---

## 3. Use Cases

> **Convention:** Actors: `User` (CLI invoker / orchestrating agent),
> `xlsx2csv2json shim` (System), `xlsx_read library` (System), `OS / FS`
> (External system).

### UC-01 — Convert single sheet to JSON (happy path, default flags)

**Actors:** User, xlsx2csv2json shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` is unencrypted, readable, ≥ 1 visible sheet.
- Each sheet has a single-row header in row 1.

**Main Scenario:**
1. User runs `python3 xlsx2json.py report.xlsx out.json`.
2. Shim parses argv; binds `--format json`; sets defaults
   (`--sheet all`, `--header-rows 1`, `--merge-policy anchor-only`,
   `--tables whole`, no hyperlinks/formulas, ISO datetime).
3. Shim invokes `xlsx_read.open_workbook(Path("report.xlsx"))`.
4. Shim calls `reader.sheets()`, filters out hidden sheets.
5. For each visible sheet: `reader.detect_tables(sheet, mode="whole")`
   → one region; `reader.read_table(region, header_rows=1,
   merge_policy="anchor-only")` → `TableData`.
6. Shim collects `{sheet_name: [{header: val, ...}, ...]}` mapping.
7. Shim writes JSON to `out.json` (UTF-8, no BOM, `ensure_ascii=False`).
8. Exit 0.

**Alternative Scenarios:**
- **A1: Output to stdout.** No `--output` → JSON written to stdout
  (`sys.stdout.buffer`).
- **A2: Single sheet without `--sheet all`.** `--sheet "Sheet1"` →
  flat array-of-objects without enclosing sheet key.
- **A3: Hidden sheet.** Skipped silently; `--include-hidden` opts in.
- **A4: Sheet name with special chars (`"Q1 / Q2 split"`).**
  Preserved verbatim in JSON keys modulo standard JSON escaping
  (`\\`, `\"`); `json.dumps(..., ensure_ascii=False)` emits non-ASCII
  characters as UTF-8 byte sequences.

**Postconditions:**
- `out.json` exists and is valid JSON (re-parseable by `json.loads`).

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ JSON shape matches §R11.
- ✅ No `openpyxl.*` type ever leaks (regression via `type()` audit).
- ✅ Datetimes formatted ISO-8601.

---

### UC-02 — Convert single sheet to CSV (single region, stdout)

**Actors:** User, xlsx2csv2json shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` valid, single sheet "Data" with single-row header.

**Main Scenario:**
1. User runs `python3 xlsx2csv.py report.xlsx --sheet Data > out.csv`.
2. Shim binds `--format csv`; resolves single sheet.
3. Shim calls `xlsx_read` reader chain (per UC-01.5).
4. Shim writes CSV to stdout using `csv.writer(sys.stdout,
   quoting=QUOTE_MINIMAL, lineterminator="\n")`.
5. Exit 0.

**Alternative Scenarios:**
- **A1: `--sheet all`.** Multi-sheet output requires `--output-dir`;
  without it, exit 2 `MultiSheetRequiresOutputDir` (CSV cannot
  multiplex sheets into a single stream).
- **A2: Encoding.** UTF-8 with BOM optional flag (deferred to v2 if
  user request; v1 = UTF-8 no BOM).
- **A3: Empty sheet.** Header-only output (zero data rows); exit 0.

**Postconditions:**
- stdout contains valid CSV.

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ CSV passes `csv.reader` round-trip parse.
- ✅ Comma / newline / quote characters in values are properly quoted.

---

### UC-03 — Convert multi-table sheet to JSON (nested shape)

**Actors:** User, xlsx2csv2json shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` has a sheet with **two ListObjects** (`xl/tables/
  table1.xml`, `xl/tables/table2.xml`) named `RevenueTable` and
  `CostsTable`.

**Main Scenario:**
1. User runs `python3 xlsx2json.py budget.xlsx out.json
   --tables listobjects --header-rows auto`.
2. Shim opens workbook; resolves `--sheet all` (default).
3. For each sheet, shim calls
   `reader.detect_tables(sheet, mode="tables-only")` — this maps
   `--tables listobjects` to the library mode that returns Tier-1
   ListObjects **plus** Tier-2 sheet-scope named ranges (no Tier-3
   gap-detect fallback). Honest-scope: sheet-scope named ranges are
   silently treated as explicit tables (§1.4 (l); Q-A6 records the
   alternative — library API extension deferred to v2).
4. For each region, shim calls `reader.read_table(region,
   header_rows="auto", ...)`.
5. Shim assembles nested shape:
   `{"Summary": {"tables": {"RevenueTable": [...], "CostsTable": [...]}}}`.
6. Writes JSON to `out.json`. Exit 0.

**Alternative Scenarios:**
- **A1: `--tables gap`.** Switches to gap-detect-only; useful for
  workbooks without ListObjects. Shim invokes library `mode="auto"`
  and filters `[r for r in regions if r.source == "gap_detect"]`
  before emit (no library-API extension in v1; §1.4 (l)).
- **A2: `--tables auto`.** Try listobjects, fall back to gap-detect
  per sheet (delegated to `xlsx_read.mode="auto"`).
- **A3: Single-table-per-sheet despite `--tables != whole`.** Shape
  falls through to flat per-sheet array; the nested `tables` key only
  appears when > 1 region detected.
- **A4: `--header-rows N` (int) explicit AND `--tables != whole`.**
  Exit 2 `HeaderRowsConflict` envelope; user must use `--header-rows auto`.

**Postconditions:**
- JSON is parseable; `tables` key present iff > 1 region per sheet.

**Acceptance Criteria:**
- ✅ Nested shape matches §R11.c–d.
- ✅ Region order is document-order (deterministic across re-reads).
- ✅ ListObject names preserved verbatim as dict keys.

---

### UC-04 — Convert multi-table sheet to CSV (subdirectory layout)

**Actors:** User, xlsx2csv2json shim, xlsx_read library, OS.

**Preconditions:**
- Same fixture as UC-03 (two ListObjects).

**Main Scenario:**
1. User runs `python3 xlsx2csv.py budget.xlsx --tables listobjects
   --output-dir /tmp/budget-out`.
2. Shim creates `/tmp/budget-out/` (and parents) if missing.
3. For each region, shim creates `/tmp/budget-out/<sheet>/<table>.csv`
   (auto-create per-sheet subdir).
4. Writes one CSV file per region.
5. Exit 0.

**Alternative Scenarios:**
- **A1: `--tables listobjects` + no `--output-dir`.** Exit 2
  `MultiTableRequiresOutputDir` (envelope per §R12.d).
- **A2: Sheet name contains a forbidden filesystem character.**
  Disallowed (cross-platform reject list — see §4.2: `/`, `\\`, `..`,
  NUL, `:`, `*`, `?`, `<`, `>`, `|`, `"`) → exit 2
  `InvalidSheetNameForFsPath` envelope. User can rename in Excel or
  pre-flight with `--sheet NAME` to extract individually.
- **A3: Existing files in `--output-dir`.** Overwritten silently;
  user is presumed to own the directory (parallel csv2xlsx).
- **A4: Single region per sheet.** Each sheet still gets its own
  subdir + one CSV file (not flattened to root — predictable layout).

**Postconditions:**
- One CSV per region exists at `<output-dir>/<sheet>/<table>.csv`.

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ File layout matches the L4 lock (subdirectory, not `__` separator).
- ✅ Sheet names with `_` or `__` produce no collisions.

---

### UC-05 — Multi-row headers with auto-detection

**Actors:** User, xlsx2csv2json shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` with a sheet whose top **two** rows form a header
  group: row 1 is a banner (`"2026 plan"` merged across cols A–C);
  row 2 has column-specific labels (`"Q1"`, `"Q2"`, `"Q3"`).

**Main Scenario:**
1. User runs `python3 xlsx2json.py plan.xlsx out.json
   --header-rows auto`.
2. Shim invokes `reader.read_table(region, header_rows="auto", ...)`.
3. Library detects 2-row header via column-spanning merge heuristic.
4. Library flattens: `"2026 plan › Q1"`, `"2026 plan › Q2"`,
   `"2026 plan › Q3"` (U+203A separator).
5. JSON dict keys use flattened strings.
6. Exit 0.

**Alternative Scenarios:**
- **A1: `--header-flatten-style array` (JSON only).** Keys become
  arrays `["2026 plan", "Q1"]` instead of joined strings. (CSV ignores
  the flag — it has no notion of multi-row JSON keys.)
- **A2: Merge straddles header/body boundary.** Library emits
  `AmbiguousHeaderBoundary` warning → shim surfaces in
  `summary.warnings`; processing continues with best-effort cut.
- **A3: ListObject with `headerRowCount=0`.** Library emits synthetic
  `col_1..col_N` headers + warning; shim relays warning to caller.

**Postconditions:**
- JSON keys are deterministic across re-reads.

**Acceptance Criteria:**
- ✅ Separator is U+203A (` › `).
- ✅ `--header-flatten-style array` only affects JSON, ignored by CSV.
- ✅ Warnings surfaced (not silently swallowed).

---

### UC-06 — Hyperlinks emission

**Actors:** User, xlsx2csv2json shim, xlsx_read library.

**Preconditions:**
- Input sheet has cells with `cell.hyperlink.target` set.

**Main Scenario (JSON):**
1. User runs `xlsx2json.py page.xlsx out.json --include-hyperlinks`.
2. Library returns `TableData` with hyperlink targets attached.
3. Shim emits each hyperlink cell as `{"value": "<text>", "href": "<url>"}`.
4. Exit 0.

**Main Scenario (CSV):**
1. User runs `xlsx2csv.py page.xlsx --include-hyperlinks > out.csv`.
2. Shim emits each hyperlink cell as `[<text>](<url>)` (markdown).
3. Exit 0.

**Alternative Scenarios:**
- **A1: `--include-hyperlinks` off (default).** Plain cell text only;
  hyperlink target dropped silently.
- **A2: Hyperlink with empty text.** JSON: `{"value": "", "href": "..."}`;
  CSV: `[](url)` (empty link-text — still a valid markdown link).
- **A3: External vs internal hyperlinks.** Both emitted; library does
  not distinguish.

**Postconditions:**
- Hyperlink data is reachable downstream.

**Acceptance Criteria:**
- ✅ JSON shape is the dict-form `{"value", "href"}` (R3-L1 lock).
- ✅ CSV shape is `[text](url)` (R3-L1 lock; never `=HYPERLINK()`).
- ✅ Round-trip xlsx-2 ↔ xlsx-8 preserves hyperlinks in JSON path
  (deferred for CSV — lossy by design).

---

### UC-07 — Encrypted workbook (cross-3)

**Actors:** User, xlsx2csv2json shim, xlsx_read library, OS.

**Preconditions:**
- Input is encrypted (OPC `EncryptedPackage` stream present).

**Main Scenario:**
1. User runs `python3 xlsx2json.py encrypted.xlsx out.json`.
2. Library probes encryption → raises `EncryptedWorkbookError`.
3. Shim catches; emits cross-5 envelope
   `{v:1, error: "Workbook is encrypted: encrypted.xlsx", code: 3, type: "EncryptedWorkbookError", details: {filename: "encrypted.xlsx"}}` to stderr.
4. Exit 3.

**Acceptance Criteria:**
- ✅ Exit code 3.
- ✅ `details.filename` is basename only (no full path leak — security
  parity with xlsx_read §13.2 fix).

---

### UC-08 — Same-path overwrite refusal (cross-7 H1)

**Actors:** User, xlsx2csv2json shim, OS.

**Preconditions:**
- A symlink `out.json -> input.xlsx` exists (or user passes
  `--output input.xlsx`).

**Main Scenario:**
1. Shim resolves `--output` via `Path.resolve()` (follows symlinks).
2. Shim resolves INPUT via `Path.resolve()`.
3. Equal? → emit cross-5 envelope `SelfOverwriteRefused`; exit 6.

**Alternative Scenarios:**
- **A1: Different extensions on the same inode** (`a.xlsx` →
  `b.json` symlink to the same inode). Still refused — inode equality
  via `Path.resolve()` catches this.

**Acceptance Criteria:**
- ✅ Exit code 6.
- ✅ Mirror json2xlsx behaviour (regression test via fixture symlink).

---

### UC-09 — `--json-errors` envelope (cross-5)

**Actors:** User (CI / agent), xlsx2csv2json shim.

**Preconditions:** Any failure path.

**Main Scenario:**
1. User runs `xlsx2json.py missing.xlsx out.json --json-errors`.
2. Shim catches `FileNotFoundError`; calls
   `report_error("Input not found", code=1, json_mode=True)`.
3. stderr receives single line of JSON; exit 1.

**Acceptance Criteria:**
- ✅ Envelope shape `{v:1, error, code, type, details}` (schema v1).
- ✅ `code` never 0 (guarded by `_errors.report_error`).
- ✅ Exactly one line on stderr (no trailing newline blobs).

---

### UC-10 — Round-trip with xlsx-2 (`json2xlsx`)

**Actors:** User, xlsx2csv2json shim, xlsx-2 shim.

**Preconditions:**
- A reference `.xlsx` (single sheet, simple data).

**Main Scenario:**
1. User runs `xlsx2json.py ref.xlsx ref.json`.
2. User runs `json2xlsx.py ref.json roundtrip.xlsx`.
3. User runs `xlsx2json.py roundtrip.xlsx roundtrip.json`.
4. `diff -q ref.json roundtrip.json` → empty (byte-identical).

**Alternative Scenarios:**
- **A1: Multi-table source (`--tables listobjects`).** xlsx-2 v1
  drops the `tables` nesting; round-trip is lossy by design (deferred
  to xlsx-2 v2). Honest-scope documented.
- **A2: Hyperlinks present.** JSON round-trip is lossless (the dict
  form survives both directions); CSV round-trip is lossy (markdown
  link string passes through xlsx-2 as plain text in v1).

**Acceptance Criteria:**
- ✅ Simple-shape round-trip is byte-identical.
- ✅ `TestRoundTripXlsx8` in xlsx-2 flips from skip to live at merge.
- ✅ `references/json-shapes.md` updated to reflect §R11 shapes.

---

## 4. Non-functional Requirements

### 4.1. Performance (S-tier — emit-only on top of xlsx-10.A envelope)

- **Open + convert single 10K × 20 sheet to JSON:** ≤ 5 s wall-clock,
  ≤ 250 MiB RSS. (xlsx-10.A `read_table` envelope is ≤ 3 s + ≤ 200
  MiB; emit overhead is ~500 ms / ~50 MiB JSON serialisation.)
- **`--tables auto` on 100-sheet workbook with 2 ListObjects/sheet:**
  ≤ 8 s wall-clock (xlsx-10.A `detect_tables` envelope ≤ 5 s + per-table
  read).
- **CSV stream-mode** (`--output-dir`, > 100 regions): O(regions) file
  opens; uses `csv.writer` per region (no in-memory accumulation
  across regions).
- **Stretch (NOT enforced in v1):** > 100 000-row sheets — document as
  "use `--sheet NAME` to isolate" in `--help` footer.

### 4.2. Security

- Pure-Python read path. No `eval`, no shell, no subprocess, no
  network. Trust boundary inherited from `xlsx_read/` (XXE,
  billion-laughs, zip-slip, macro execution all mitigated upstream).
- **Path allowlisting** — shim follows `Path.resolve(strict=True)`;
  caller responsible for allowlisting untrusted inputs (parallel
  xlsx_read §13.14.1).
- **`--output-dir` path traversal** — shim refuses to write outside
  `--output-dir` root: each computed `<output-dir>/<sheet>/<table>.csv`
  passes through `Path.resolve()` AND `is_relative_to(output_dir.resolve())`
  check; mismatch → exit 2 `OutputPathTraversal` envelope.
- **Sheet/table names as path components** — characters `/`, `\\`,
  `..`, NUL → exit 2 `InvalidSheetNameForFsPath` (UC-04 A2). Other
  forbidden chars on Windows (`:`, `*`, `?`, `<`, `>`, `|`, `"`) are
  also rejected because cross-platform consumers may run on Windows.
- **Stale-cache leak** — formula present + `cell.value is None`:
  emit warning, NEVER fabricate a value.

### 4.3. Compatibility

- Python ≥ 3.10 (xlsx skill baseline).
- `openpyxl >= 3.1.0`, `lxml >= 4.9` (already pinned).
- `ruff >= 0.5.0` (already pinned by xlsx-10.A; reused, no new deps).
- macOS + Linux. (No Windows-specific paths in v1.)

### 4.4. Scalability

- Library is stateless per CLI invocation. Each invocation opens
  ONE `WorkbookReader`, fully drains it, closes it.
- No global state in the package (regression test scans for
  module-level mutable globals).

### 4.5. Maintainability

- ≤ 700 LOC per module (xlsx skill precedent: xlsx-7, xlsx-2, xlsx-3,
  xlsx-10.A all enforce this).
- ≤ 1500 LOC total package (vs xlsx-2 1307 and xlsx-3 1903 baselines;
  emit-only shim should land at the low end since reader-logic is
  delegated).
- Shims ≤ 60 LOC each (xlsx-2 shim is 53 LOC; xlsx-8 shims will mirror).
- 100 % `__all__` coverage of public symbols (`convert_xlsx_to_csv`,
  `convert_xlsx_to_json`, `main`, exception types).

---

## 5. Acceptance Criteria (binary, library-level)

### 5.1. Module + shim layout

- ✅ Files exist: `skills/xlsx/scripts/xlsx2csv.py`,
  `skills/xlsx/scripts/xlsx2json.py`,
  `skills/xlsx/scripts/xlsx2csv2json/__init__.py` (+ siblings per
  ARCH).
- ✅ Both shims ≤ 60 LOC; pure re-export pattern.
- ✅ Public helpers `convert_xlsx_to_csv` + `convert_xlsx_to_json`
  exported from `xlsx2csv2json/__init__.py`.
- ✅ `ruff check scripts/` is green (xlsx-10.A toolchain reused).

### 5.2. CLI surface

- ✅ Args per §R4–§R10 (input, --output, --sheet, --include-hidden,
  --tables, --gap-rows, --gap-cols, --header-rows, --header-flatten-style,
  --merge-policy, --include-hyperlinks, --include-formulas,
  --datetime-format, --output-dir, --json-errors).
- ✅ Defaults exactly per §R6 backward-compat lock.
- ✅ `xlsx2csv.py --format json` rejected at parse time (§R2.d).

### 5.3. Output shapes

- ✅ JSON shapes per §R11 (a–e).
- ✅ CSV shapes per §R12 (a–e).
- ✅ Hyperlink emission per §R10 (b–c) — dict-form for JSON,
  markdown-link for CSV.
- ✅ Multi-row header flatten per §R7 (c) using U+203A separator.

### 5.4. Cross-cutting parity

- ✅ Cross-3 / cross-4 / cross-5 / cross-7 envelopes (§R14–§R17).
- ✅ `code` never 0; envelope shape v1.
- ✅ Basename-only in error messages (no full-path leak parallel xlsx_read §13.2).

### 5.5. Test suite (≥ 25 E2E scenarios — fixed list)

| # | Scenario | Maps to |
| --- | --- | --- |
| 1 | `json_single_sheet_default_flags` | UC-01 |
| 2 | `json_stdout_when_output_omitted` | UC-01 A1 |
| 3 | `json_sheet_named_filter` | UC-01 A2 |
| 4 | `json_hidden_sheet_skipped_default` | UC-01 A3 |
| 5 | `json_hidden_sheet_included_with_flag` | UC-01 A3 |
| 6 | `json_special_char_sheet_name_preserved` | UC-01 A4 |
| 7 | `csv_single_sheet_stdout` | UC-02 |
| 8 | `csv_sheet_all_without_output_dir_exits_2` | UC-02 A1 |
| 9 | `csv_quoting_minimal_correct` | UC-02 |
| 10 | `json_multi_table_listobjects_nested_shape` | UC-03 |
| 11 | `json_multi_table_gap_detect_default_2_1` | UC-03 A1 |
| 12 | `json_multi_table_auto_falls_back_to_gap` | UC-03 A2 |
| 13 | `json_single_table_falls_through_flat` | UC-03 A3 |
| 14 | `header_rows_int_with_multi_table_exits_2_HeaderRowsConflict` | UC-03 A4 |
| 15 | `csv_multi_table_subdirectory_schema` | UC-04 |
| 16 | `csv_multi_table_without_output_dir_exits_2` | UC-04 A1 |
| 17 | `csv_sheet_name_with_slash_exits_2_InvalidSheetNameForFsPath` | UC-04 A2 |
| 18 | `header_rows_auto_detects_multi_row_header_with_U203A` | UC-05 |
| 19 | `header_flatten_style_array_only_for_json` | UC-05 A1 |
| 20 | `ambiguous_header_boundary_surfaced_as_warning` | UC-05 A2 |
| 21 | `synthetic_headers_when_listobject_header_row_count_zero` | UC-05 A3 |
| 22 | `hyperlinks_json_dict_shape_value_href` | UC-06 |
| 23 | `hyperlinks_csv_markdown_link_text_url` | UC-06 |
| 24 | `encrypted_workbook_exits_3_with_basename_only` | UC-07 |
| 25 | `same_path_via_symlink_exits_6_SelfOverwriteRefused` | UC-08 |
| 26 | `json_errors_envelope_shape_v1` | UC-09 |
| 27 | `roundtrip_xlsx2_simple_shape_byte_identical` | UC-10 |
| 28 | `merge_policy_anchor_only_fill_blank_three_fixtures` | §R8 |
| 29 | `include_formulas_emits_formula_strings_not_cached` | §R6.e |
| 30 | `output_dir_path_traversal_rejected_OutputPathTraversal` | §4.2 |

**Count:** 30 ≥ 25 required (§R19.b).

### 5.6. Regression gates

- ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` exits 0.
- ✅ Existing xlsx-2 / xlsx-3 / xlsx-6 / xlsx-7 / xlsx-10.A E2E suites
  green (no-behaviour-change gate; this task does NOT modify their
  source).
- ✅ 12-line cross-skill `diff -q` silent gate (CLAUDE.md §2):
  `office/`, `_soffice.py`, `_errors.py`, `preview.py`,
  `office_passwd.py` unchanged across all four office skills.
- ✅ xlsx-2's `TestRoundTripXlsx8` flips from skip to live and passes.
- ✅ `skills/xlsx/references/json-shapes.md` updated with §R11 shapes.

---

## 6. Constraints and Assumptions

### 6.1. Technical constraints

- **No new system tools.** All reading via `xlsx_read/` (which uses
  `openpyxl` + `lxml`). No `pandas`, no `subprocess`, no shell.
- **Single source of truth for reader logic.** Shims and package
  modules MUST NOT re-implement merge resolution, ListObjects,
  gap-detect, multi-row headers, hyperlink extraction, stale-cache
  detection, encryption probe, or macro probe. Those live in
  `xlsx_read/`. Drift between this package and xlsx_read = bug.
- **5-file silent diff gate** (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`) must remain unchanged.
- **xlsx-10.A toolchain reuse.** `pyproject.toml` /
  `requirements.txt` / `install.sh` ruff post-hook are kept as-is.
  No new ruff banned-api rule needed (this package is allowed to
  import from `xlsx_read.__init__` public surface; banned-api rule
  already targets `xlsx_read._*` external imports — unchanged).

### 6.2. Business / process constraints

- **Activates round-trip contract.** xlsx-2's
  `TestRoundTripXlsx8::test_live_roundtrip` is gated
  `@unittest.skipUnless(...)`; this task removes the skip on the
  merge commit.
- **Triggers xlsx-9 unblock.** xlsx-9 (`xlsx2md.py`) is parallel work
  on `xlsx_read/` foundation; no scheduling dependency, but xlsx-9's
  merge starts the 14-day ownership clock for xlsx-10.B.

### 6.3. Assumptions

- **A1:** `xlsx_read.WorkbookReader` public surface is stable post
  xlsx-10.A merge (frozen by `__all__` lock); no API drift expected.
- **A2:** `_errors.py` envelope schema `v=1` is stable across xlsx
  skill (already used by xlsx-2 / xlsx-3 / xlsx-7).
- **A3:** xlsx-2's `convert_json_to_xlsx` public helper accepts
  dict-of-arrays input (verified in `json2xlsx/__init__.py`); the
  nested `tables` shape from §R11 will be **dropped** by xlsx-2 v1
  but caller-flat shapes preserved.
- **A4:** `cell.hyperlink.target` is reachable in openpyxl ≥ 3.1.0
  for both internal (sheet-anchor) and external (URL) links — already
  smoke-tested by xlsx-10.A `test_values.py`.

---

## 7. Open Questions

> **Convention:** Questions split into **BLOCKING** (cannot proceed
> without answer) and **NON-BLOCKING** (deferred to architecture phase
> or implementation-time judgement).

### 7.1. Blocking — none.

All required decisions are either locked by the backlog row or
recorded as deliberate honest-scope items in §1.4 / §R*.

### 7.2. Non-blocking (deferred to architect)

- **Q-A1.** Should `xlsx2csv` and `xlsx2json` share **one package**
  (`xlsx2csv2json/`) or be **two packages** (`xlsx2csv/`, `xlsx2json/`)?
  **Recommendation:** one package — emit-format dispatch in
  `cli.py:main()` is ~20 LOC; two packages would duplicate the entire
  CLI surface and force a third shared helper module anyway.
- **Q-A2.** Should the shared package live at
  `skills/xlsx/scripts/xlsx2csv2json/` or at
  `skills/xlsx/scripts/xlsx_readback/`? **Recommendation:**
  `xlsx2csv2json/` — explicit about the two output formats and matches
  the shim file names; `xlsx_readback` is too generic and conflicts
  with the foundation name `xlsx_read`.
- **Q-A3.** Should `--output-dir` default to a directory derived from
  the input filename (e.g. `<INPUT>_out/`) when not specified? **No,
  fail loud.** Auto-derived paths are footguns when running in CI /
  one-shot scripts.
- **Q-A4.** Should the package expose `convert_xlsx_to_csv(...,
  output_path: Path)` and `convert_xlsx_to_json(...)` as **separate**
  helpers, OR a single `convert_xlsx_readback(..., format=...)`
  helper? **Recommendation:** two separate helpers — clearer call sites,
  static typing of the format param avoided.
- **Q-A5.** Should we recover Excel's `--include-formulas` for users
  who genuinely want `=A1+B1` strings? Library supports it via
  `xlsx_read.WorkbookReader.read_table(include_formulas=True)`, but
  it requires `keep_formulas=True` at workbook open. **Decision (locks
  here):** YES, surface `--include-formulas` at shim level; shim passes
  `keep_formulas=True` to `open_workbook` AND `include_formulas=True`
  to `read_table` in lockstep (per xlsx-10.A §13.1).
- **Q-A6.** `--tables` enum is 4-valued (`whole|listobjects|gap|auto`)
  but library `TableDetectMode` is 3-valued (`auto|tables-only|whole`).
  Should the shim filter region-`source` post-call, OR should
  xlsx-10.A be extended with `listobjects-only` and `gap-only` modes?
  **Recommendation:** filter-out for v1. Library API extension would
  break the `__all__` frozen surface and require an xlsx-10.A v2.
  Filter-out is ≤ 4 LOC in the shim. Honest-scope locked in §1.4 (l).
  **Architect to confirm.**

### 7.3. Locked decisions (recorded for traceability)

- **D1.** Single package `xlsx2csv2json/` (Q-A1).
- **D2.** Default `--header-rows 1` for backward-compat (R6).
- **D3.** Default `--tables whole` for backward-compat (R6).
- **D4.** U+203A separator for flattened multi-row headers (R7.c).
- **D5.** Subdirectory schema `<sheet>/<table>.csv`, NOT `<sheet>__<table>.csv`
  (R12.c, L4 VDD-adversarial fix).
- **D6.** Default `--gap-rows 2`, `--gap-cols 1` (R9.e–f, M4 fix).
- **D7.** Hyperlink JSON shape `{"value", "href"}` (R10.b, R3-L1 fix);
  CSV `[text](url)` (R10.c).
- **D8.** Same-path canonical-resolve guard via `Path.resolve()`
  (R17.a, cross-7 H1).
- **D9.** `--include-formulas` at shim level passes through to
  `keep_formulas=True` at `open_workbook` (Q-A5).
- **D10.** Round-trip contract: nested `tables` shape documented as
  lossy on xlsx-2 v1 consume; full restoration deferred to xlsx-2 v2
  `--write-listobjects` flag (R13.b, honest-scope).

---

## 8. Atomic-Chain Skeleton (Planner handoff hint)

> Final chain is the Planner's responsibility; this is the recommended
> decomposition (8 atomic sub-tasks, mirroring xlsx-10.A cadence).

| # | Slug | Scope | Stub-First gate |
| --- | --- | --- | --- |
| 010-01 | `pkg-skeleton` | Create empty `xlsx2csv2json/` package + both shims (53 + 53 LOC). All modules `pass` stubs. `--help` works for both shims. | `python3 xlsx2csv.py --help` exits 0; package importable. |
| 010-02 | `cli-argparse` | Full argparse surface per §R4–§R10. Validation only (no business logic). `HeaderRowsConflict`, `MultiTableRequiresOutputDir`, `MultiSheetRequiresOutputDir`, `InvalidSheetNameForFsPath` all raised at parse time where determinable. | Test all bad-flag combos exit 2 with envelopes. |
| 010-03 | `cross-cutting` | `_errors.py` integration, cross-3/4/5/7 envelopes, basename-only error messages, same-path guard. | UC-07, UC-08, UC-09 green. |
| 010-04 | `dispatch-and-reader-glue` | `cli.py:main()` orchestrator opens workbook, resolves sheets/regions via `xlsx_read`, dispatches to emit_csv / emit_json. No emit body yet — just integration. | UC-01 minimal smoke (single sheet → empty JSON skeleton). |
| 010-05 | `emit-json` | `emit_json.py` — flat, nested-by-sheet, nested-multi-table shapes per §R11. `--header-flatten-style` handling. Hyperlink dict emission. | UC-01, UC-03, UC-05, UC-06 (JSON path) all green. |
| 010-06 | `emit-csv` | `emit_csv.py` — single-region stdout, multi-region subdirectory schema, hyperlink markdown emission, path-traversal guard, OutputPathTraversal envelope. | UC-02, UC-04, UC-06 (CSV path) all green. |
| 010-07 | `roundtrip-and-references` | Update `references/json-shapes.md` with §R11 shapes; flip xlsx-2's `TestRoundTripXlsx8` from skip to live; add 30 E2E test list per §5.5. | UC-10 + all 30 E2E green. |
| 010-08 | `final-docs-and-validation` | `SKILL.md` + `.AGENTS.md` updates; `validate_skill.py` exit 0; 12-line `diff -q` silent gate; package LOC budget verified (≤ 1500 total). | All gates green. |
