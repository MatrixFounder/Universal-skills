# Task 004 — xlsx-2 — `json2xlsx.py` (JSON → styled .xlsx converter)

> **Backlog row:** `xlsx-2` (`docs/office-skills-backlog.md`).
> **Predecessor / sibling:** `csv2xlsx.py` (`skills/xlsx/scripts/csv2xlsx.py`,
> 203 LOC, MERGED) — xlsx-2 is the **JSON-shaped parallel** to that CLI.
> **Symmetric companion:** `xlsx2json.py` from xlsx-8 (open, scheduled
> day-1 after xlsx-2). xlsx-2 MUST accept the canonical xlsx-8 output
> shape so the agent loop `xlsx2json → edit-JSON → json2xlsx`
> round-trips without manual XML.
> **Status:** **DRAFT** — pre-Architecture / Planning.

## 0. Meta Information

- **Task ID:** `004`
- **Slug:** `json2xlsx`
- **Backlog row:** `xlsx-2` (`docs/office-skills-backlog.md` §xlsx).
- **Effort estimate:** **S → M** (backlog says S "несколько строк на
  pandas", but VDD-mode kick-off Q&A (2026-05-11) widened scope:
  3 input shapes + ISO-date coercion + cross-cutting parity (cross-5
  envelope, cross-7 H1 same-path, stdin `-`) + xlsx-8 round-trip
  integration test + atomic-chain plan shape. Final LOC estimate: shim
  ≤ 220 + `json2xlsx/` package ~600 + tests ~800.
- **Decisions locked from `/vdd-start-feature` Q&A (2026-05-11):**
  - **D1 — JSON shapes:** v1 accepts **three** input shapes (auto-
    detected by file extension and first-non-whitespace JSON token):
    1. **Array-of-objects** (single-sheet, mirrors `csv2xlsx`):
       `[{col: val, …}, {col: val, …}, …]`.
    2. **Multi-sheet dict** (mirrors xlsx-8 `--sheet all`):
       `{"Sheet1": [{…}, …], "Sheet2": [{…}, …]}`.
    3. **JSONL** (one JSON object per line — single-sheet, streaming
       LLM-output friendly): `{"col": "v1"}\n{"col": "v2"}\n`.
    Detection rule (deterministic): `.jsonl` extension → JSONL; else
    parse JSON document and dispatch on root type (`list` → shape 1,
    `dict-of-lists-of-objects` → shape 2; anything else → exit 2
    `UnsupportedJsonShape`).
  - **D2 — Type strategy:** Native JSON types preserved (int / float /
    bool / null / str). **ISO-date string coercion** is opt-in-default:
    strings matching `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS[.fff][±HH:MM|Z]`
    → Excel datetime cell with `number_format = "YYYY-MM-DD"` /
    `"YYYY-MM-DD HH:MM:SS"`. Opt-out: `--no-date-coerce`. Custom format
    via `--date-format STRFTIME`. **Heterogeneous schema** (array of
    objects with different keys) → union all keys, missing → empty
    cell. Order: insertion order of first row + insertion order of
    new keys as they appear.
  - **D3 — Cross-cutting parity:** Full surface — `--json-errors`
    envelope (cross-5); same-path guard exit 6 `SelfOverwriteRefused`
    via `Path.resolve()` (cross-7 H1, follows symlinks); stdin `-`
    as INPUT (LLM-pipe). **N/A:** cross-3 (encryption) and cross-4
    (macro) — input is JSON, not OOXML, so those guards are
    inapplicable on input. **Output** is a fresh `.xlsx` workbook
    (no macros, never password-protected).
  - **D4 — Round-trip integration test:** Dedicated E2E
    `T-roundtrip-xlsx8` locks the symmetry contract with xlsx-8.
    Because xlsx-8 ships **after** xlsx-2 (backlog day-1 sequence),
    v1 implementation uses **synthetic golden JSON** that exactly
    matches the xlsx-8 output shape declared in the backlog
    (`[{header1: value1, ...}, ...]` per sheet,
    `{"Sheet1": [...], "Sheet2": [...]}` for multi-sheet). When
    xlsx-8 lands, a follow-up `T-roundtrip-xlsx8-live` wires the
    actual `xlsx2json | json2xlsx` pipe and asserts structural
    equivalence. **Open Question O1** tracks this coupling.
  - **D5 — Plan shape:** Atomic chain of **8–12 sub-tasks**
    (mirrors Task 003 pattern). Shim + package up front (Task-003 D2
    pattern, **NOT** Task-001 → 002 refactor pattern). Per-subtask
    review files in `docs/reviews/`, archive in `docs/tasks/`.
- **Decisions locked from task-reviewer round-1 (2026-05-11, see `docs/reviews/task-004-review.md`):**
  - **D6 (was O2) — No explicit `--input-format` flag in v1.** The
    detection rule of R1+R2 (`.jsonl` extension → JSONL; else dispatch
    on JSON root token) is deterministic and documented. A user-
    override flag is **deferred to v2**. Rationale: agents almost
    always know what shape they're producing; the override flag adds
    surface area without a real-world use-case in the corpus.
  - **D7 (was O5) — `--strict-dates` rejects aware datetimes.**
    Under `--strict-dates`, a timezone-aware datetime string → exit 2
    `TimezoneNotSupported` envelope. Without `--strict-dates`, R4.e
    applies (aware → UTC naive). Locks the timezone contract before
    Architecture so the Architect doesn't have to re-litigate.

---

## 1. General Description

### Goal

Ship a CLI **`skills/xlsx/scripts/json2xlsx.py`** that converts a
JSON input (file or stdin) into a styled `.xlsx` workbook. Three
canonical input shapes are auto-detected: (1) array-of-objects
(single sheet, parallel to `csv2xlsx`); (2) multi-sheet dict
(`{sheet_name: [rows]}`); (3) JSONL (one JSON object per line).
Output styling matches `csv2xlsx` 1:1 (bold header, light-grey fill,
center alignment, freeze first row, auto-filter, auto column widths).
Native JSON types are preserved; ISO-8601 date strings are auto-
coerced to Excel datetime cells by default.

### Why now

- **Closes the agent's natural output path.** LLMs produce JSON
  natively. Today the agent has to (a) emit CSV (lossy for strings
  containing commas, no native types, leading-zero footgun) and pipe
  through `csv2xlsx`, or (b) call openpyxl directly (no styling, easy
  to break leading zeros). `json2xlsx` removes that footgun.
- **Closes the xlsx-8 round-trip.** xlsx-8 will emit
  `[{col: val, …}]` per sheet / `{sheet: [...]}` for all-sheets.
  Without xlsx-2, the agent can read a workbook → edit JSON → cannot
  write it back without unsafe openpyxl scratch code.
- **Parity gap.** docx has md2docx + html2docx; pdf has md2pdf +
  html2pdf; pptx has md2pptx + outline2pptx; xlsx has only csv2xlsx.
  Adding json2xlsx normalises the input-format coverage matrix.

### Connection with existing system

| Existing component | Role |
| :--- | :--- |
| `csv2xlsx.py` | **Reference implementation** for output styling, type-coercion guards, header formatting. xlsx-2 reuses the visual contract 1:1 — same `HEADER_FILL`/`HEADER_FONT`/`HEADER_ALIGN`/`MAX_COL_WIDTH` constants either by import or by copy-with-comment. |
| `_errors.py` (`add_json_errors_argument`, `report_error`) | Cross-5 envelope provider. xlsx-2 uses it for every CLI exit ≠ 0. |
| `office/` validators | After write, output passes through `office/validators/xlsx.py` in the post-validate hook (parity with xlsx-6 `XLSX_ADD_COMMENT_POST_VALIDATE`). Activated by `XLSX_JSON2XLSX_POST_VALIDATE=1`. |
| xlsx-8 `xlsx2json.py` (open) | Symmetric companion — its output shape is xlsx-2's input contract (D4). |
| `cross-7 H1` (same-path guard) | Inherited convention: input path = output path → exit 6. |

### Use-case context (concrete)

1. **LLM → spreadsheet.** Agent computes a 50-row table of
   "Vendor / Item / Cost / Date" as JSON and ships
   `agent_output.xlsx` to the user.
   ```bash
   json2xlsx.py agent_out.json report.xlsx
   ```
2. **Pipe from another tool.** A query tool emits JSON on stdout;
   xlsx-2 catches it.
   ```bash
   curl … | jq '.results' | json2xlsx.py - report.xlsx --json-errors
   ```
3. **Multi-sheet dashboard.** Agent emits
   `{"Employees": […], "Departments": […]}`; xlsx-2 writes a 2-sheet
   workbook.
4. **xlsx-8 edit loop (post xlsx-8 landing).** Read existing workbook
   to JSON, edit, write back:
   ```bash
   xlsx2json.py original.xlsx --sheet all > edit.json
   $EDITOR edit.json
   json2xlsx.py edit.json roundtrip.xlsx
   ```

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
| :--- | :--- | :--- | :--- |
| **R1** | **Read JSON from file path or stdin.** | ✅ | (a) `INPUT.json` resolved via `Path`. (b) Sentinel `-` reads from `sys.stdin` (UTF-8 strict; replace-on-error rejected to fail-loud on truncated pipes). (c) `--encoding utf-8` flag for file mode (default utf-8). (d) Empty input → exit 2 `EmptyInput`. (e) Invalid JSON / JSONL line → exit 2 `JsonDecodeError` with line/column details. |
| **R2** | **Detect & dispatch on JSON shape.** | ✅ | (a) `.jsonl` extension → JSONL parser. (b) Else parse single JSON document. (c) `root is list of dicts` → shape-1 array-of-objects, single sheet. (d) `root is dict where every value is a list of dicts` → shape-2 multi-sheet. (e) Anything else (scalar root, list-of-lists, list-of-scalars, dict-of-scalars, mixed-value dict) → exit 2 `UnsupportedJsonShape` with details `{root_type, hint}`. (f) Empty array `[]` and empty multi-sheet `{}` → exit 2 `NoRowsToWrite` (writing zero-row workbooks is almost always a bug). |
| **R3** | **Preserve JSON native types.** | ✅ | (a) `int` → numeric cell. (b) `float` → numeric cell. (c) `bool` → bool cell (Excel boolean). (d) `null` → empty cell (no value set). (e) `str` (non-date) → string cell. (f) Mixed-type column (e.g., `Age: 30` in row 1, `Age: "n/a"` in row 2) → each cell typed individually; no column-wide coercion. |
| **R4** | **Coerce ISO-8601 date strings.** | ✅ | (a) Date-only `YYYY-MM-DD` → `datetime.date` → `number_format = "YYYY-MM-DD"`. (b) Datetime `YYYY-MM-DDTHH:MM:SS` (+ optional `.fff`, `±HH:MM`/`Z` timezone) → `datetime.datetime` → `number_format = "YYYY-MM-DD HH:MM:SS"`. (c) `--no-date-coerce` → strings preserved as text. (d) `--date-format STRFTIME` → custom output `number_format`. (e) Naive vs aware datetimes (default): aware datetimes are converted to UTC and stored naive (Excel has no native tz); a `--keep-timezone` toggle is **out of scope v1**, documented in §11 Honest Scope. (f) Invalid candidate (`"2026-13-99"`, `"2024-01-15ish"`) → string cell, NO coercion, NO warning (silent fall-through; users who need strict parsing add `--strict-dates`). (g) **Under `--strict-dates` (locked via D7):** aware datetime → exit 2 `TimezoneNotSupported` envelope with `details: {value, sheet, row, column, tz_offset}`; invalid candidate (R4.f) → exit 2 `InvalidDateString`. |
| **R5** | **Schema heterogeneity → union keys.** | ✅ | (a) Headers = ordered set of all keys across all rows in a sheet. (b) Order = first-seen wins (row 1 keys first, then keys new to row 2 appended, etc.). (c) Missing key in a row → empty cell (no value, NOT `null` text). (d) Extra key — same as case (a); the new column is appended. (e) No fail-fast mode in v1; `--strict-schema` deferred to v2 per Open Question O3. |
| **R6** | **Style output workbook (csv2xlsx parity).** | ✅ | (a) Bold header (`HEADER_FONT`). (b) Light-grey fill `F2F2F2` (`HEADER_FILL`). (c) Centre alignment (`HEADER_ALIGN`). (d) Freeze first row `ws.freeze_panes = "A2"`. (e) Auto-filter over data range when rows ≥ 1. (f) Column widths = `min(max(header_len, max_value_len) + 2, MAX_COL_WIDTH=50)`. (g) Flags `--no-freeze` and `--no-filter` mirror csv2xlsx. |
| **R7** | **Multi-sheet write (D1 shape-2).** | ✅ | (a) Each top-level dict key → one sheet, name preserved verbatim (Excel sheet-name rules enforced: ≤ 31 chars, no `[]:*?/\\`, not `History`). (b) Sheet-name violation → exit 2 `InvalidSheetName` with details `{name, reason}`. Auto-sanitization (truncate/replace) is **out of scope v1** — fail-loud per §11 Honest Scope. (c) Duplicate top-level sheet keys are silently collapsed by `json.loads()` (last-wins per RFC 8259 §4); xlsx-2 v1 does NOT detect this and documents the gap in §11 Honest Scope. Proper detection requires `json.JSONDecoder(object_pairs_hook=…)` and is deferred to v2. (d) Single-sheet input writes to `--sheet NAME` (default `Sheet1`); multi-sheet input **ignores** `--sheet` with a stderr warning (avoid silent override). |
| **R8** | **Cross-cutting (cross-5 envelope, cross-7 same-path, stdin).** | ✅ | (a) `--json-errors` accepted; on every non-zero exit emit the **frozen cross-5 schema** `{v: 1, error, code, type, details?}` via `_errors.report_error(...)` (see `skills/xlsx/scripts/_errors.py:39,126-138`). **Do NOT** introduce `ok` / `message` keys — those belong to xlsx-6's findings envelope, a different payload. `details` always merged into the helper, never written directly. (b) `Path(input).resolve() == Path(output).resolve()` → exit 6 `SelfOverwriteRefused` (skip when input is stdin `-`). (c) Stdin `-` reads JSON from `sys.stdin.buffer` (binary then UTF-8 decode) to avoid Windows newline translation breaking JSONL. (d) Cross-3 / cross-4 not applicable (no OOXML input). |
| **R9** | **CLI surface (argparse).** | ✅ | (a) Positional `input` and `output`. (b) `--sheet NAME` (single-sheet default override). (c) `--no-freeze`, `--no-filter`. (d) `--no-date-coerce`, `--date-format STR`, `--strict-dates`. (e) `--encoding utf-8` (file mode only). (f) `--json-errors`. (g) `--help` echoes the module docstring's first line (csv2xlsx pattern). (h) Unknown flag → argparse default exit 2. |
| **R10** | **Post-validate hook (opt-in).** | ✅ | (a) `XLSX_JSON2XLSX_POST_VALIDATE=1` env-var triggers `office/validators/xlsx.py` after `wb.save()`. (b) Validate failure → exit 7 `PostValidateFailed` envelope with `details.validator_output[:8192]`. (c) Output file is unlinked on failure (mirrors xlsx-6 `--post-validate` cleanup). (d) Truthy allowlist `1/true/yes/on` (case-insensitive); anything else → off (parity with xlsx-6 `_post_validate_enabled()`). |
| **R11** | **Tests: unit + E2E + round-trip.** | ✅ | (a) `tests/test_json2xlsx.py` ≥ 25 unit tests covering parse/coerce/style/schema-drift/sheet-validation/encoding. (b) `tests/test_e2e.sh` adds ≥ 10 named E2E cases. (c) `T-roundtrip-xlsx8` (synthetic JSON → workbook → assert structure). (d) `T-roundtrip-xlsx8-live` (skip-with-reason, activates when xlsx-8 lands). (e) Performance budget: 10 000-row × 6-column array-of-objects → `.xlsx` ≤ 3 s on the same fixture-runner as csv2xlsx 10K-row benchmark (gated by `RUN_PERF_TESTS=1`, no CI gate). |
| **R12** | **Docs: SKILL.md + .AGENTS.md + examples.** | ✅ | (a) `skills/xlsx/SKILL.md` §2 Capabilities adds JSON bullet. (b) `skills/xlsx/SKILL.md` §1 Red Flags adds "I'll just `df.to_excel`" rebuttal cross-ref. (c) `skills/xlsx/scripts/.AGENTS.md` (if present) updates section on script inventory. (d) `examples/` gains `json2xlsx_simple.json` + `json2xlsx_multisheet.json` + their golden `.xlsx` outputs (referenced from SKILL.md). (e) docs/office-skills-backlog.md xlsx-2 row marked ✅ DONE in the merge commit. |
| **R13** | **Skill-validator + repo-level invariants green.** | ✅ | (a) `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0 after change. (b) CLAUDE.md §2 byte-identity diffs unchanged (json2xlsx adds NEW file; doesn't touch `office/` or `_soffice.py` or `_errors.py` or `preview.py` or `office_passwd.py`). (c) `python3 -m unittest discover` exits 0 inside `skills/xlsx/scripts/`. (d) E2E `tests/test_e2e.sh` exits 0. |

---

## 3. Use Cases

### UC-1 — Agent emits LLM-computed table

#### Actors
- **Agent** (LLM-driven script that produces JSON-array output).
- **System** (json2xlsx CLI).

#### Preconditions
- Agent produces a JSON-array file (or stdout pipe) where rows are
  uniform objects with string-named keys.

#### Main Scenario
1. Agent writes `agent_out.json`:
   ```json
   [
     {"Vendor": "Acme", "Item": "Widget", "Cost": 12.5, "Date": "2026-05-11"},
     {"Vendor": "Beta", "Item": "Sprocket", "Cost": 7.0, "Date": "2026-05-10"}
   ]
   ```
2. Agent runs `python3 json2xlsx.py agent_out.json report.xlsx`.
3. System parses JSON; detects shape-1 (array-of-objects).
4. System builds DataFrame; coerces "2026-05-11"/"2026-05-10" to dates.
5. System writes workbook: 1 sheet "Sheet1", bold header row, freeze pane "A2", auto-filter, column widths sized.
6. System exits 0; no stdout output.

#### Alternative Scenarios
- **A1 (Pipe from stdin):** Agent runs `tool | json2xlsx.py - report.xlsx`. Step 1 replaced with `sys.stdin.buffer` read; rest identical.
- **A2 (Same-path collision):** Agent runs `json2xlsx.py file.xlsx file.xlsx` (typo). System resolves both paths, detects equality, exits 6 with envelope `{type: "SelfOverwriteRefused", details: {input, output}}`. Mirrors cross-7 H1.
- **A3 (Empty input):** `agent_out.json = "[]"`. System exits 2 `NoRowsToWrite`. Rationale: writing zero-row workbooks is virtually always a bug; if intentional, user uses csv2xlsx with `--allow-empty` (out of scope v1).
- **A4 (Schema drift):** Row 1 has `{Vendor, Item}`; row 2 has `{Vendor, Item, Note}`. System unions keys → 3 columns; row 1 `Note` cell is empty. No warning.
- **A5 (Invalid JSON):** Truncated file `[{"Vendor":` → exit 2 `JsonDecodeError` with `details: {line, column, msg}`.

#### Postconditions
- Output `.xlsx` is a valid OOXML workbook openable by Excel / LO.
- Native JSON types preserved; ISO-date strings written as Excel dates.

#### Acceptance Criteria
- ✅ Exit 0 on valid array-of-objects.
- ✅ Output workbook opens in LibreOffice without errors.
- ✅ Header row has bold + light-grey + centre styling.
- ✅ Date cell `data_type == "n"` and `number_format` matches `YYYY-MM-DD`.
- ✅ Cost cell stored as float `12.5`, not string `"12.5"`.
- ✅ stderr is silent on the happy path (matches csv2xlsx).

---

### UC-2 — Multi-sheet workbook from `{sheet: [rows]}` dict

#### Actors
- **Agent** (or human emitting structured JSON).
- **System**.

#### Preconditions
- JSON input is a dict whose values are all `list[dict]`.

#### Main Scenario
1. Input `multi.json`:
   ```json
   {
     "Employees": [{"Name": "Alice", "Salary": 100000}, {"Name": "Bob", "Salary": 95000}],
     "Departments": [{"Dept": "Eng", "Head": "Alice"}]
   }
   ```
2. Run `json2xlsx.py multi.json multi.xlsx`.
3. System detects shape-2 (multi-sheet dict).
4. System creates two worksheets in insertion order: "Employees", "Departments".
5. Each sheet receives independent styling (bold header, freeze, auto-filter).
6. Exit 0.

#### Alternative Scenarios
- **A1 (Invalid sheet name):** Key `"Q1/Q2"` → exit 2 `InvalidSheetName` (contains `/`).
- **A2 (Duplicate sheet name in input JSON):** Python's `json.loads()` accepts duplicate top-level keys and silently keeps the last value (RFC 8259 §4 is permissive). xlsx-2 v1 does NOT detect this — only one survives, no error raised. Locking detection requires `json.JSONDecoder(object_pairs_hook=…)`, deferred to v2. Documented in §11 Honest Scope item 5; not a v1 bug.
- **A3 (`--sheet` flag with multi-sheet input):** Flag ignored, stderr warning `--sheet ignored when JSON root is multi-sheet dict`. Exit 0.
- **A4 (One sheet empty):** `{"Sheet1": [...], "Sheet2": []}` → exit 2 `NoRowsToWrite` with `details: {empty_sheet: "Sheet2"}`. v1 is fail-loud; partial-write is deferred.

#### Postconditions
- Workbook has the same number of sheets as top-level dict keys, in order.

#### Acceptance Criteria
- ✅ `len(wb.sheetnames) == len(input_dict)`.
- ✅ `wb.sheetnames` matches input key order exactly.
- ✅ Each sheet is independently styled per R6.

---

### UC-3 — JSONL streaming input

#### Actors
- **Agent** producing one-JSON-per-line output (common for log-style
  LLM emissions).

#### Preconditions
- Input file has `.jsonl` extension OR stdin pipe with `--input-format jsonl` (open question, see O2).

#### Main Scenario
1. Input `events.jsonl`:
   ```
   {"event": "login", "user": "alice", "ts": "2026-05-11T09:00:00Z"}
   {"event": "logout", "user": "alice", "ts": "2026-05-11T09:30:00Z"}
   ```
2. Run `json2xlsx.py events.jsonl events.xlsx`.
3. System detects `.jsonl` extension → JSONL parser.
4. Each line parsed independently; one row per line.
5. Output single-sheet `.xlsx` with 3 columns (`event`, `user`, `ts`).

#### Alternative Scenarios
- **A1 (Blank line in middle):** Skipped silently (whitespace-only lines are stripped before parse).
- **A2 (Malformed line N):** Exit 2 `JsonDecodeError` with `details: {line: N, msg}`.
- **A3 (Mixed JSONL — line 5 is an array):** Exit 2 `UnsupportedJsonShape` with `details: {line: 5, expected: "object"}`.

#### Postconditions
- One sheet, N data rows, headers = union of keys.

#### Acceptance Criteria
- ✅ Auto-detection via extension alone, no flag required.
- ✅ Malformed-line error message points to source line number.

---

### UC-4 — Stdin pipe with envelope error

#### Actors
- **Agent** in a multi-stage shell pipeline.

#### Preconditions
- Caller passes `-` as input and `--json-errors` to capture errors
  programmatically.

#### Main Scenario
1. Caller: `cat valid.json | python3 json2xlsx.py - out.xlsx --json-errors`.
2. System reads `sys.stdin.buffer`, decodes UTF-8 strict, parses JSON.
3. Writes workbook, exits 0.

#### Alternative Scenarios
- **A1 (Truncated pipe):** stdin closes mid-JSON → exit 2 envelope `{ok: false, code: 2, type: "JsonDecodeError", message: "...", details: {...}}`.
- **A2 (No `-`, just empty input file):** Treat as A3 in UC-1 → `EmptyInput` envelope.

#### Postconditions
- Envelope on stderr (cross-5 convention; frozen schema per R8.a).
- Stdout untouched (reserved for future `--output -` mode, **not v1**).

#### Acceptance Criteria
- ✅ Envelope JSON parses on caller side (`head -1 stderr | jq` works).
- ✅ Envelope contains `v: 1`, `error` (the human-readable message), `code` (int), `type` (the ErrorClass string), and `details` (object, may be empty).
- ✅ Envelope does NOT contain `ok` or `message` keys (those are xlsx-6 findings-envelope vocabulary, not cross-5).
- ✅ Exit code matches envelope `code` field exactly.

---

### UC-5 — xlsx-8 round-trip (deferred live wiring)

#### Actors
- **Agent** reading then editing then re-writing a workbook.

#### Preconditions
- xlsx-8 (`xlsx2json.py`) is **eventually** available. v1 of xlsx-2 uses synthetic JSON matching xlsx-8's declared output shape.

#### Main Scenario (post xlsx-8 landing — v1 includes scaffolding only)
1. `python3 xlsx2json.py original.xlsx --sheet all > intermediate.json`.
2. Agent edits `intermediate.json` (adds rows, fixes typos).
3. `python3 json2xlsx.py intermediate.json roundtrip.xlsx`.
4. Compare `roundtrip.xlsx` to `original.xlsx`: sheet names, headers, cell values match. **Formatting/styles NOT compared** (xlsx-2 produces fresh styling; original may have user-authored styles).

#### Alternative Scenarios
- **A1 (v1, xlsx-8 not yet built):** Test scaffolded as `T-roundtrip-xlsx8` using synthetic JSON (hard-coded fixture mirroring xlsx-8 spec). Live wiring deferred to `T-roundtrip-xlsx8-live`, marked `@unittest.skipUnless(_xlsx2json_available())`.

#### Postconditions
- Structural equivalence preserved across the round-trip.

#### Acceptance Criteria
- ✅ Synthetic `T-roundtrip-xlsx8` passes in v1 CI.
- ✅ Live `T-roundtrip-xlsx8-live` test is wired but skipped with explicit reason mentioning xlsx-8 dependency.
- ✅ When xlsx-8 lands, live test passes without xlsx-2 code change.

---

## 4. Non-Functional Requirements

### 4.1. Performance

- 10 000-row × 6-column array-of-objects → `.xlsx` ≤ **3 s** on
  the same fixture-runner machine used for the xlsx-7 100K-row
  benchmark (csv2xlsx has no committed perf test; this is an
  informal target, not a regression gate).
- 100 000-row JSONL (single-stream) → `.xlsx` ≤ **30 s** (loose
  budget; openpyxl normal mode, NOT write-only). If this budget is
  exceeded, fall back to openpyxl `write_only=True` is deferred to
  v2 per Open Question O4.
- Memory budget: 500 MB RSS for 100K-row case (matches xlsx-7 budget).
- Performance tests gated by `RUN_PERF_TESTS=1` env-var; no CI gate
  (xlsx-6 / xlsx-7 convention; reviewer runs locally).

### 4.2. Security

- **No `eval`, no `exec`.** JSON is parsed with `json.loads` /
  `json.JSONDecoder.raw_decode`. No user-supplied format strings
  reach `str.format` or `%`-formatting (use `string.Template` if
  templated output ever lands — not v1).
- **JSON-bomb defense.** Python's `json` module is not natively
  vulnerable to billion-laughs (no entity expansion in JSON spec),
  but extremely deep nesting can blow the C stack. Add explicit
  recursion guard: input parsed with default limit (1000 levels);
  document the limit in `--help`. Out-of-scope for v1: per-key
  size cap.
- **Sheet-name injection.** Excel sheet-name rules enforced
  (R7.b); a key like `"=cmd|'/c calc'!A1"` would NOT trigger Excel
  formula evaluation when used as a *sheet name* (only as a cell
  value with leading `=`). Cell-value leading `=` interpretation
  is **out of scope v1**; document in Honest Scope §11. csv2xlsx
  has the same behaviour (does not auto-escape leading `=`).
- **Path safety.** `Path.resolve()` for input/output / same-path
  check; follows symlinks. TOCTOU honest scope: symlink mutated
  between `resolve()` and `open()` is out of scope (parity with
  xlsx-7 architect-review m6).

### 4.3. Compatibility

- Python ≥ 3.10 (matches xlsx skill baseline).
- Dependencies: `openpyxl`, `pandas`, `python-dateutil` (already in
  xlsx `requirements.txt` from xlsx-7) — **no new dependency**.
- No platform-specific code; same Win/Mac/Linux contract as
  csv2xlsx.
- Excel 2016+ / LibreOffice 7.0+ for date number-format rendering.

### 4.4. Maintainability

- Shim file `json2xlsx.py` ≤ 220 LOC (CLI argparse + dispatch).
- Package `json2xlsx/` modules ≤ 500 LOC each (Task-003 D2
  pattern): `loaders.py`, `coerce.py`, `writer.py`, `cli_helpers.py`,
  `exceptions.py`.
- Unit-test coverage ≥ 85 % of `json2xlsx/` module LOC (excluded:
  argparse plumbing).

---

## 5. Constraints and Assumptions

### Technical constraints

- C1. **No new top-level dependency.** Reuse `openpyxl`, `pandas`,
  `python-dateutil` already present from xlsx-7.
- C2. **No edit of shared `office/` / `_soffice.py` / `_errors.py` /
  `preview.py` / `office_passwd.py`** unless absolutely necessary.
  Any such edit triggers the 3-skill or 4-skill replication protocol
  (CLAUDE.md §2). Default: leave shared modules untouched.
- C3. **No new shared modules.** New code lives entirely inside
  `skills/xlsx/scripts/json2xlsx.py` (shim) and
  `skills/xlsx/scripts/json2xlsx/` (package).
- C4. **License preserved.** xlsx skill is Proprietary; new files
  inherit `LicenseRef-Proprietary` and contribute to `LICENSE` /
  `NOTICE` per office-skill convention.

### Business / scope constraints

- C5. **No write-back to existing workbooks.** json2xlsx ALWAYS
  produces a fresh `.xlsx`. Editing an existing workbook
  (preserving formulas, charts, styles) is out of scope — that is
  the `xlsx-4` (charts/data-validation preservation) and `docx-6`-
  parallel territory.
- C6. **No mixed input forms in v1.** Picking JSON or JSONL is by
  extension/root-token; user can't force the parser via flag.
  Documented as Open Question O2 (low-risk; agents typically know
  what they're producing).
- C7. **No formula injection escape on cell values.** Leading `=`
  in a JSON string value goes through to Excel as a formula (or as
  text — depends on Excel's leading-`=` heuristic). Mirrors
  csv2xlsx; documented in Honest Scope §11.

### Assumptions

- A1. xlsx-8 (`xlsx2json.py`) is a separate task that ships AFTER
  xlsx-2. Synthetic round-trip test is therefore the lock; live
  test activates post xlsx-8 merge.
- A2. The xlsx skill's `requirements.txt` already pins all needed
  Python deps. No `requirements.txt` edit required for xlsx-2.
- A3. The agent supplying JSON is responsible for the JSON's
  structural correctness; xlsx-2 reports clearly but does NOT
  recover (no "best-effort" parsing).

---

## 6. Open Questions

> The following are **non-blocking** for Architecture / Planning
> phase start, but MUST be resolved before the corresponding
> sub-task in the atomic chain begins. Each links to the sub-task
> that closes it.

- **O1 — xlsx-8 coupling.** Round-trip test design is synthetic
  in v1 (D4). When xlsx-8 lands, does the integration test live
  in xlsx-2's test file (preferred — owns the contract) or in
  xlsx-8's test file (alternative — owns the producer)?
  **Proposal:** owner of the contract = xlsx-2; live test is added
  to `tests/test_json2xlsx.py` in the xlsx-8 merge commit.
  **Sub-task that resolves:** Planning phase decision; tracked in
  xlsx-8 task notes.

- **O3 — `--strict-schema`.** R5 unions keys silently. Should v1
  add a fail-fast mode for production pipelines that reject
  schema drift?
  **Proposal:** Defer to v2. xlsx-7 already handles structural
  validation on the workbook side; xlsx-2's job is to write
  whatever JSON it gets.
  **Sub-task that resolves:** Sub-task 004.04 (type-coercion +
  schema rules).

- **O4 — Write-only mode for ≥ 100K rows.** Performance budget
  4.1 says 30 s loose. If real-world JSONL files blow past this,
  do we switch to openpyxl `write_only=True`?
  **Proposal:** Defer to v2. Mention in §11 Honest Scope.
  **Sub-task that resolves:** Sub-task 004.05 (writer); decision
  reflected in `writer.py` module-level docstring.

- **O6 — Leading `=` in cell values.** C7 documents the gap. Add
  a `--escape-formulas` flag (prepends `'` to leading-`=` values
  to force text) in v1?
  **Proposal:** Defer to v2 unless reviewer disagrees. csv2xlsx
  has the same gap; fixing both at once in a follow-up is more
  coherent.
  **Sub-task that resolves:** Sub-task 004.07 (cross-cutting).

> O2 (`--input-format` flag) and O5 (`--strict-dates` rejects aware
> datetimes) were **promoted to D6 and D7** in §0 Meta Information
> during round-1 task-reviewer resolution. See
> `docs/reviews/task-004-review.md` §Resolution.

---

## 7. Definition of Done

- [x] `docs/TASK.md` exists with this content; Task ID 004.
- [ ] `docs/ARCHITECTURE.md` §2 (Functional Architecture) and §3 (System Architecture) updated to include json2xlsx layer.
- [ ] `docs/PLAN.md` and `docs/tasks/task-004-*.md` (8–12 sub-tasks) authored under Stub-First.
- [ ] Each sub-task has a `docs/reviews/task-004-XX-review.md` companion (post-implementation).
- [ ] All R1–R13 acceptance criteria met.
- [ ] CLAUDE.md §2 byte-identity diffs unchanged (`docx ↔ xlsx ↔ pptx ↔ pdf` cross-skill scripts).
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] backlog row xlsx-2 marked ✅ DONE with Status block (date + LOC + test counts).
- [ ] No regression on existing xlsx tests (`csv2xlsx`, `xlsx_add_chart`, `xlsx_add_comment`, `xlsx_recalc`, `xlsx_validate`, `xlsx_check_rules`).
- [ ] **xlsx-8 input-contract freeze sub-task** (closes review m1): `skills/xlsx/references/json-shapes.md` authored at end of atomic chain, exhaustively specifying (a) sheet-name key under `--sheet all` (verbatim Excel sheet name), (b) null-cell JSON representation (`null` value vs omitted key), (c) datetime serialization (ISO-8601 with offset, never Excel-serial), (d) `--header-row N>1` behaviour, (e) formula resolution (cached value vs `=…` string). Both xlsx-2 R2 and the future xlsx-8 task reference this file; xlsx-8 implementation MUST conform on landing, removing the risk of `T-roundtrip-xlsx8-live` breaking xlsx-2 (UC-5 AC).

---

## 8. Exit codes (CLI contract)

| Exit | Type (envelope `type`) | When |
| :---: | :--- | :--- |
| 0 | `Ok` | Success. |
| 1 | `IOError` | Output path unwritable, disk full, parent dir not created (and `--mkdirs` not in v1 — output's parent MUST exist). |
| 2 | `EmptyInput` / `NoRowsToWrite` / `JsonDecodeError` / `UnsupportedJsonShape` / `InvalidSheetName` / `DuplicateSheetName` / `TimezoneNotSupported` (under `--strict-dates`) | User-input errors. |
| 6 | `SelfOverwriteRefused` | Cross-7 H1: resolved input path == resolved output path. |
| 7 | `PostValidateFailed` | Optional post-validate hook (R10) returned non-zero. |

All non-zero exits emit a **cross-5 envelope** when `--json-errors`
is set. The schema is the one frozen in `_errors.py:39` (one JSON
line on stderr, single-call `report_error(...)`):

```json
{
  "v": 1,
  "error": "JSON root must be array-of-objects or dict-of-arrays-of-objects",
  "code": 2,
  "type": "UnsupportedJsonShape",
  "details": {
    "root_type": "list",
    "first_element_type": "int",
    "hint": "Did you mean to wrap each row in an object?"
  }
}
```

> Field-by-field semantics: `v` is the envelope schema version
> (`SCHEMA_VERSION = 1` in `_errors.py`). `error` is the human-
> readable message. `code` matches the process exit status. `type` is
> the symbolic error class. `details` is a free-form object (may be
> omitted by the helper when empty). **Do NOT** use `ok` / `message` —
> those are vocabulary from the xlsx-6 findings-envelope (a different
> payload) and conflating them is a known pitfall (Task-003 M2).

---

## 9. Cross-skill Replication Audit (CLAUDE.md §2)

xlsx-2 does **NOT** edit any cross-skill replicated module. R13.b is the gate. For belt-and-braces, the Developer MUST run before any commit:

```bash
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
for s in xlsx pptx pdf; do
    diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
    diff -q skills/docx/scripts/preview.py  skills/$s/scripts/preview.py
done
diff -q skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
diff -q skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
```

All eleven `diff` invocations MUST be silent. **If any output appears, the change is wrong** — xlsx-2's job is to add new files under `skills/xlsx/scripts/` only.

---

## 10. New file inventory (planned)

| Path | Purpose | Approx. LOC |
| :--- | :--- | ---: |
| `skills/xlsx/scripts/json2xlsx.py` | CLI shim (argparse + dispatch into the package) | ≤ 220 |
| `skills/xlsx/scripts/json2xlsx/__init__.py` | Package marker + public surface re-export | ≤ 30 |
| `skills/xlsx/scripts/json2xlsx/loaders.py` | JSON / JSONL parsing + shape detection | ~ 180 |
| `skills/xlsx/scripts/json2xlsx/coerce.py` | Type / ISO-date coercion logic | ~ 200 |
| `skills/xlsx/scripts/json2xlsx/writer.py` | openpyxl write loop + styling | ~ 200 |
| `skills/xlsx/scripts/json2xlsx/exceptions.py` | `_AppError` + typed errors (`EmptyInput`, `NoRowsToWrite`, `JsonDecodeError`, `UnsupportedJsonShape`, `InvalidSheetName`, `TimezoneNotSupported`, `InvalidDateString`, `PostValidateFailed`, `SelfOverwriteRefused`) | ~ 90 |
| `skills/xlsx/scripts/json2xlsx/cli_helpers.py` | `_post_validate_enabled()` clone, stdin reader, path resolver | ~ 60 |
| `skills/xlsx/scripts/tests/test_json2xlsx.py` | Unit tests (≥ 25 cases) | ~ 600 |
| `skills/xlsx/scripts/tests/test_e2e.sh` | Append ≥ 10 named E2E cases | + ~ 200 |
| `skills/xlsx/examples/json2xlsx_simple.json` | Fixture (array-of-objects) | small |
| `skills/xlsx/examples/json2xlsx_multisheet.json` | Fixture (multi-sheet dict) | small |
| `skills/xlsx/examples/json2xlsx_events.jsonl` | Fixture (JSONL) | small |
| `skills/xlsx/references/json-shapes.md` | Round-trip contract spec (R12 + DoD §7 m1 sub-task) | ~ 250 |

Total new code: ~ 1 580 LOC (close to the §0 estimate of ~ 1 620 — confirms M-tier).

---

## 11. Honest Scope (v1 limitations)

These are the limitations xlsx-2 v1 **deliberately accepts**. Each is
referenced from one or more sections above. The Architect / Planner
must NOT silently widen scope to close them; instead, file a v2 backlog
row (xlsx-2a, xlsx-2b, …) if the limitation becomes pressing.

1. **Aware datetime → naive UTC (R4.e).** Default behaviour. A
   `--keep-timezone` flag that would store the timezone offset as a
   sibling column is **out of scope v1**. Under `--strict-dates`
   (D7 / R4.g) aware datetimes hard-fail with `TimezoneNotSupported`
   instead of silently being shifted. Excel itself has no native
   timezone type; any cross-tool fidelity is best-effort.
2. **Leading `=` in JSON string values (C7).** A string like
   `"=A1+1"` passes through to Excel as-is. Excel's own leading-`=`
   heuristic then decides whether to interpret it as a formula
   (usually yes) or text (rarely). xlsx-2 does **not** auto-prepend
   `'` to defuse formula injection (csv2xlsx parity). The
   `--escape-formulas` flag is deferred to v2 per O6 and will land
   simultaneously in csv2xlsx + json2xlsx.
3. **100 000-row write-only mode (O4).** xlsx-2 v1 uses openpyxl's
   normal-write mode. Real-world inputs that blow past the 30 s
   loose budget warrant openpyxl `write_only=True`, but the
   trade-off (no late style edits, slightly different cell-typing
   path) needs its own design pass. Deferred to v2 per O4.
4. **Sheet-name auto-sanitization (R7.b).** Invalid keys fail-loud
   with `InvalidSheetName`. Truncating `"Q1/Q2 results 2026 review"`
   to `"Q1Q2 results 2026 revi"` would silently mutate data;
   fail-loud is the safer default for an agent-targeted CLI. A
   `--sanitize-sheet-names` flag is a v2 candidate.
5. **Duplicate top-level JSON keys collapsed by `json.loads()`
   (R7.c / UC-2 Alt-A2).** Python's stdlib `json` module accepts
   duplicate keys and silently keeps the last value (RFC 8259 §4 is
   permissive on this). Detecting duplicates requires custom
   `json.JSONDecoder(object_pairs_hook=…)`. xlsx-2 v1 does NOT do
   this. Practical impact is low (humans rarely hand-author duplicate
   sheet keys; tools that emit JSON deduplicate upstream). Deferred
   to v2.
6. **TOCTOU on the same-path guard (R8.b).** `Path.resolve()`
   compares paths at one moment; a symlink racing between
   `resolve()` and `open(output, "wb")` is **out of scope v1**.
   Mirrors xlsx-7 architect-review m6 (locked precedent).
7. **Cell-value `=cmd|'/c calc'!A1` injection (R7 §4.2).** The
   same leading-`=` story as honest-scope item 2, but specifically
   for the WIN32-CSV-injection class. xlsx-2 does NOT escape; the
   downstream consumer (Excel, LO, Numbers) is responsible. csv2xlsx
   has the same gap; honest-scope item 2 covers the v2 fix.

> If you arrive at one of these limitations during implementation and
> believe it is now blocking, **stop and escalate** — do not silently
> widen v1. Open a Question in `docs/TASK.md` or a follow-up backlog
> row.
