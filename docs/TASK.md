# TASK 009 — xlsx-10.A: `xlsx_read/` common read-only reader library

> **Mode:** VDD (Verification-Driven Development).
> **Source backlog row:** `docs/office-skills-backlog.md` → `xlsx-10.A`.
> **Status:** DRAFT v1 (pre-architecture-review).

---

## 0. Meta Information

- **Task ID:** `009`
- **Slug:** `xlsx-read-library`
- **Backlog row:** `xlsx-10.A` (foundation for xlsx-8 + xlsx-9; gates the future xlsx-10.B refactor of xlsx-7).
- **Target skill:** `skills/xlsx/` (Proprietary — see CLAUDE.md §3, `skills/xlsx/LICENSE`).
- **Cross-skill replication:** **None.** `xlsx_read/` is xlsx-specific (SpreadsheetML only). 5-file silent-`diff -q` gate (`office/`, `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py`) MUST remain silent — none of those files are touched.
- **Mode flag:** Standard (no `[LIGHT]`).

---

## 1. General Description

### 1.1. Goal
Build a **read-only**, **closed-API**, in-skill Python package
`skills/xlsx/scripts/xlsx_read/` that extracts the duplicated reader-
logic shared by the future `xlsx-8` (`xlsx2csv` / `xlsx2json`) and
`xlsx-9` (`xlsx2md`) CLIs into a single source of truth. The package
is the **foundation** that unblocks xlsx-8 and xlsx-9; xlsx-7
(`xlsx_check_rules/`) is **NOT** refactored in this task (deferred to
xlsx-10.B per backlog `R3-M3 split`).

### 1.2. Motivation
- xlsx-8 + xlsx-9 share ≥ 80 % of reader logic (merge resolution,
  multi-row header detection, ListObjects / named-range / gap-
  detection, cell value extraction with number-format heuristic,
  stale-cache detection, encryption + macro pre-checks).
- Without a shared library each new CLI duplicates that surface →
  **2 × maintenance burden** + **drift risk** on edge cases (header-
  merge boundary, hyperlink rendering, multi-row header collapse,
  rich-text spans).
- Mirrors the proven xlsx package pattern (`xlsx_check_rules/`,
  `xlsx_comment/`, `json2xlsx/`, `md_tables2xlsx/`) — package = single-
  responsibility modules, shim is thin.

### 1.3. Connection with the existing system
- **Reuses without modification:** `_errors.py` (cross-5 envelope),
  `_soffice.py` (NOT touched), `office_passwd.py` (encryption probe
  inspiration), `office/validate.py` (NOT touched), `openpyxl`.
- **Reused infrastructure from xlsx-7:** `xl/tables/tableN.xml`
  ListObjects parsing approach (xlsx-7 §4.3) — re-implemented in
  `xlsx_read/_tables.py` (parallel implementation, NOT cross-import,
  per CLAUDE.md §2 spirit: each package self-contained).
- **Future consumers (out of scope for this task):**
  - `xlsx2csv.py` + `xlsx2json.py` shim (xlsx-8) — thin
    `argparse → convert_xlsx_to_csv / convert_xlsx_to_json` dispatch.
  - `xlsx2md.py` shim (xlsx-9) — thin emitter on top of the library.
  - `xlsx-10.B` — refactor `xlsx_check_rules/` internal reader to
    consume `xlsx_read/` (deferred, gated on this task).
- **Toolchain bring-up (verified absent on 2026-05-12):**
  `skills/xlsx/scripts/pyproject.toml` is **created** by this task
  with a `[tool.ruff.lint.flake8-tidy-imports.banned-api]` block;
  `ruff>=0.5.0` is **added** to `requirements.txt`;
  `ruff check scripts/` is **added** to `install.sh` post-hook;
  documented in `skills/xlsx/.AGENTS.md §Toolchain`.

### 1.4. Honest scope (v1 — explicitly out of scope)
- **(a) Read-only.** No write paths. Write surfaces stay in
  `csv2xlsx`, `json2xlsx`, `md_tables2xlsx`.
- **(b) No formula evaluation.** Cached value only (parallel xlsx-7).
- **(c) Pandas deliberately avoided** (`docs/ARCHITECTURE.md §6`
  precedent: xlsx-2, xlsx-3).
- **(d) Named ranges:** scope = `sheet` only; workbook-scope named
  ranges are **ignored** in `detect_tables` (mirror xlsx-7).
- **(e) ListObjects header handling** (`R2-M4` + `R3-H2` fixes):
  - `headerRowCount=0` → synthetic headers `col_1..col_N` (uniform
    JSON shape preserved: array-of-objects, **never** array-of-
    arrays). Warning surfaced: `"Table 'X' had no headers; emitted
    synthetic col_1..col_N"`.
  - `headerRowCount>1` → multi-row header handler (` › ` separator,
    U+203A).
  - Gap-detect fallback **only** when ListObject absent.
- **(f) Shared / array formulas** → cached value only.
- **(g) Sparklines, diagonal borders, camera objects** → dropped
  silently.
- **(h) Overlapping `<mergeCells>`** (corrupted workbooks) →
  fail-loud `OverlappingMerges` exception (exit 2 in caller).
- **(i) Thread safety (L2 fix).** `WorkbookReader` is **NOT** thread-
  safe (`openpyxl.Workbook` is not thread-safe). Caller responsible
  for per-thread / per-process instances. No module-level singletons.
- **(j) Refactor of xlsx-7** is **deferred to xlsx-10.B** (separate
  ticket). Temporary duplication window between `xlsx_read/` and
  `xlsx_check_rules/` internal reader is **accepted** per
  ownership-bounded honest scope (R2-H2): xlsx-9 owner opens xlsx-10.B
  within 14 days post-xlsx-9-merge, otherwise duplication is promoted
  to documented technical debt in `skills/xlsx/SKILL.md §10`.
- **(k) No `eval` / no shell**, no network, no subprocess (the
  underlying `openpyxl` is pure-Python + lxml).

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R1** | Public API surface (closed, openpyxl-types **never** leak) | ✅ | (a) `open_workbook(path, **opts) -> WorkbookReader`; (b) `WorkbookReader.sheets() -> list[SheetInfo]`; (c) `WorkbookReader.detect_tables(sheet, mode, gap_rows=2, gap_cols=1) -> list[TableRegion]`; (d) `WorkbookReader.read_table(region, header_rows="auto", merge_policy=ANCHOR_ONLY, include_hyperlinks=False, include_formulas=False, datetime_format=ISO) -> TableData`; (e) `__all__` lock; (f) regression test asserting `isinstance(returned, openpyxl_type)` is **False** across the public surface. |
| **R2** | Package layout: private modules `_workbook.py` / `_sheets.py` / `_merges.py` / `_tables.py` / `_headers.py` / `_values.py`; public surface only via `__init__.py` re-exports (L1 fix). | ✅ | (a) Underscore prefix for all internals; (b) `__init__.py` defines `__all__`; (c) `ruff` `[tool.ruff.lint.flake8-tidy-imports.banned-api]` pattern `xlsx_read._*` → fail (R2-M2 + R3-M1 fix); (d) `pyproject.toml` created at `skills/xlsx/scripts/pyproject.toml`; (e) `ruff>=0.5.0` added to `requirements.txt`; (f) `ruff check scripts/` added to `install.sh` post-hook; (g) `.AGENTS.md §Toolchain` updated. |
| **R3** | `open_workbook` — workbook opener with cross-cutting pre-flight | ✅ | (a) Path → `_workbook.py:open_workbook`; (b) cross-3 encryption probe (raise `EncryptedWorkbookError`, exit 3 in caller); (c) cross-4 macro detection (raise `MacroEnabledWarning` as **warning**, not error — caller decides); (d) openpyxl `read_only=True` mode for large files (`>10 MiB` heuristic; verbatim caller-overridable via `read_only_mode: bool \| None`); (e) typed exceptions only — no string-matching by caller. |
| **R4** | `sheets()` — sheet enumeration | ✅ | (a) Read order from `xl/workbook.xml/<sheets>` (preserved verbatim); (b) `SheetInfo` dataclass fields: `name: str`, `index: int`, `state: Literal["visible","hidden","veryHidden"]`; (c) `--include-hidden` filter resolved at caller; (d) sheet resolver `name \| "all" \| missing-name` — missing name raises `SheetNotFound`; (e) sheet-name case-sensitive match. |
| **R5** | `detect_tables()` — 3-tier table detector | ✅ | (a) Tier-1: `xl/tables/tableN.xml` ListObjects (re-implement xlsx-7 §4.3 logic in `_tables.py`); (b) Tier-2: `<definedName>` named ranges, sheet-scope only; (c) Tier-3: gap-detection (≥ `gap_rows` empty rows AND/OR ≥ `gap_cols` empty cols); (d) defaults `gap_rows=2` / `gap_cols=1` (M4 fix — single-empty-row would over-split totals/section rows); (e) modes: `auto` (1→2→3 fallthrough), `tables-only` (1+2 only), `whole` (no split). |
| **R6** | `read_table()` — extract a region into `TableData` | ✅ | (a) `header_rows: int \| Literal["auto"] = "auto"` default (R2-L3 fix — was `1`, changed because backward-compat is circular under H3 fix forcing `auto` for multi-table sheets); (b) `merge_policy: anchor-only \| fill \| blank` (default `anchor-only`); (c) `include_hyperlinks: bool = False` → on-true: extract `cell.hyperlink.target`; (d) `include_formulas: bool = False` → on-true: emit formula string instead of cached value; (e) `datetime_format: ISO \| excel-serial \| raw` (default ISO-8601). |
| **R7** | Multi-row header detection (`_headers.py`) | ✅ | (a) `header_rows="auto"` → detect rows with column-spanning merges from top; (b) Flatten top→sub via ` › ` (U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK) — does not collide with `/` headers `"Q1 / Q2 split"`; (c) JSON-side `header_flatten_style: string \| array` option (caller can request keys-array — solves any residual collision); (d) Ambiguous-boundary warning `AmbiguousHeaderBoundary` when a merge straddles the detected header/body cut; (e) `header_rows=int` is **allowed**, but caller must enforce `mode != "auto"` consistency (the multi-table conflict is handled by the **caller** xlsx-8 — `HeaderRowsConflict` envelope is a caller concern, **not** library concern). |
| **R8** | Cell value extraction (`_values.py`) | ✅ | (a) Formula vs cached toggle; (b) `cell.number_format` heuristic — `#,##0.00` → formatted; `0%` / `0.0%` → percent (correct decimals); date formats → ISO-8601; raw float fallback; (c) datetime → ISO / excel-serial / raw; (d) hyperlink → `cell.hyperlink.target`; (e) rich-text spans → plain-text concat; (f) stale-cache detector — formula present + `cell.value=None` → surface in `TableData.warnings`. |
| **R9** | Merge resolution (`_merges.py`) | ✅ | (a) Parse `<mergeCells>` → `anchor → spans` map; (b) Policy `anchor-only` (only top-left cell carries value); (c) Policy `fill` (anchor value broadcast to all cells in span); (d) Policy `blank` (anchor value, rest = `None`); (e) Overlapping-merge detector → `OverlappingMerges` typed exception, fail-loud (M8 fix — explicit `_overlapping_merges_check(ws.merged_cells.ranges)`); (f) verified empirically against openpyxl behavior during implementation (M8 design-question resolution). |
| **R10** | Typed exception contract | ✅ | (a) `EncryptedWorkbookError`; (b) `MacroEnabledWarning` (subclass of `UserWarning`); (c) `OverlappingMerges`; (d) `AmbiguousHeaderBoundary`; (e) `SheetNotFound`; (f) all listed in `__init__.py` `__all__`; (g) caller maps to cross-5 envelope, library NEVER prints to stdout/stderr. |
| **R11** | Dataclass returns (`frozen=True` outer; M3 honest scope) | ✅ | (a) `TableData(rows: list, headers: list, warnings: list, region: TableRegion)` — outer frozen; (b) `TableRegion(sheet, top_row, left_col, bottom_row, right_col, source: Literal["listobject","named_range","gap_detect"], name: str \| None)` — outer frozen; (c) `SheetInfo` — outer frozen; (d) Inner sequences MUTABLE `list` (R2-M6 fix — `tuple()` constructor is O(n), same as `list()`, and deep-freeze forces caller into build-list-then-rebuild pattern; the cost is ergonomic, not perf); (e) docstring in `__init__.py` documents: *"outer struct immutable, inner sequences mutable — caller-responsibility not to mutate; library does not deepcopy on read"*. |
| **R12** | Honest-scope + thread-safety documentation locks | ✅ | (a) `WorkbookReader.__doc__` states "**NOT** thread-safe; caller responsible for per-thread instances; no module-level singletons" (L2 fix); (b) `skills/xlsx/.AGENTS.md` adds `xlsx_read/` section with thread-safety note; (c) `skills/xlsx/SKILL.md §10` adds known-duplication marker pointing to xlsx-10.B; (d) `xlsx_read/__init__.py` module docstring lists every honest-scope item from §1.4. |
| **R13** | Test suite (≥ 20 E2E + full unit per module) | ✅ | See §3 (Use Cases) and §5 (Acceptance Criteria) — 20+ E2E scenarios enumerated; full unit suite per private module; `validate_skill.py` exit 0; existing xlsx-* E2E suites must remain green (no-behavior-change gate for shared infra). |

---

## 3. Use Cases

> **Convention:** UC actors include `Caller` (a future xlsx-8 /
> xlsx-9 / xlsx-10.B consumer — Python code, NOT end-user CLI), the
> `xlsx_read library` (System), and the underlying `openpyxl` parser
> (External system). End-user CLI behavior (exit codes, envelopes) is
> a **caller** concern; library use cases focus on **library
> behavior**.

### UC-01 — Open an unencrypted workbook (happy path)

**Actors:** Caller, xlsx_read library, openpyxl.

**Preconditions:**
- Input file is a valid `.xlsx` (or `.xlsm`).
- File is not encrypted.
- File is readable to the current process.

**Main Scenario:**
1. Caller invokes `open_workbook(path)`.
2. Library probes file for encryption (cross-3) — none detected.
3. Library probes for macros (cross-4) — emits
   `MacroEnabledWarning` if `.xlsm`, otherwise silent.
4. Library decides `read_only` mode: size > 10 MiB ⇒ `True`, else
   `False`. Caller can override via `read_only_mode` kwarg.
5. Library returns a `WorkbookReader` instance bound to the open
   workbook.

**Alternative Scenarios:**
- **A1: File missing.** `FileNotFoundError` propagated unchanged.
- **A2: Encrypted file.** Library raises `EncryptedWorkbookError`
  (caller maps to exit 3).
- **A3: Macro-enabled file.** Library emits `MacroEnabledWarning`
  via `warnings.warn(...)`; **does not raise**. Caller decides
  policy.
- **A4: Corrupted ZIP / not OOXML.** `openpyxl` raises
  `zipfile.BadZipFile` or `InvalidFileException` — propagated
  unchanged (these are **structural** failures, not library
  concerns).

**Postconditions:**
- `WorkbookReader` is bound to the file; subsequent `sheets()` /
  `detect_tables()` / `read_table()` calls succeed.

**Acceptance Criteria:**
- ✅ Returns a `WorkbookReader` for unencrypted `.xlsx` and `.xlsm`.
- ✅ Raises `EncryptedWorkbookError` for encrypted file.
- ✅ Emits exactly one `MacroEnabledWarning` for `.xlsm`.
- ✅ `read_only=True` chosen automatically when file size > 10 MiB.
- ✅ No `openpyxl` types in raised exceptions (regression test).

---

### UC-02 — Enumerate sheets (visible + hidden filter)

**Actors:** Caller, xlsx_read library.

**Preconditions:**
- `WorkbookReader` from UC-01.

**Main Scenario:**
1. Caller invokes `reader.sheets()`.
2. Library reads `xl/workbook.xml/<sheets>` and emits a list of
   `SheetInfo` in document order, including hidden sheets.
3. Caller filters on `info.state == "visible"` if needed.

**Alternative Scenarios:**
- **A1: Empty workbook.** Returns `[]`.
- **A2: Sheet name with special chars.** Preserved verbatim
  (Excel allows e.g. `"Q1 / Q2 split"`).

**Postconditions:**
- Caller has the ordered sheet list.

**Acceptance Criteria:**
- ✅ Document order preserved (matches `<sheets>` element order).
- ✅ Hidden + veryHidden sheets included; `state` field correct.
- ✅ Special-character sheet names preserved byte-for-byte.

---

### UC-03 — Detect tables (3-tier fallthrough)

**Actors:** Caller, xlsx_read library.

**Preconditions:**
- `WorkbookReader` from UC-01.
- Target sheet exists.

**Main Scenario:**
1. Caller invokes
   `reader.detect_tables(sheet, mode="auto", gap_rows=2, gap_cols=1)`.
2. **Tier-1:** Library reads `xl/tables/tableN.xml` ListObjects
   bound to the sheet; for each, emits `TableRegion(source="listobject", name=...)`.
3. **Tier-2:** Library reads `<definedName>` named ranges with
   `localSheetId` matching the target sheet; emits
   `TableRegion(source="named_range", name=...)` for ranges not
   covered by Tier-1.
4. **Tier-3:** For the remaining sheet area, run gap-detection
   (≥ 2 empty rows OR ≥ 1 empty col); emit
   `TableRegion(source="gap_detect", name="Table-1"...)` in
   document order.
5. Returns the union of regions.

**Alternative Scenarios:**
- **A1: `mode="tables-only"`.** Skip Tier-3.
- **A2: `mode="whole"`.** Skip Tier-1 + Tier-2; emit a single
  `TableRegion` spanning the sheet's used range.
- **A3: ListObject with `headerRowCount=0`.** Region recorded;
  caller will see synthetic headers in `read_table()`.
- **A4: ListObject overlaps a named range.** Tier-1 wins
  (ListObjects are explicit). Named range is dropped silently.
- **A5: No tables detectable.** Returns `[]` (caller handles).
- **A6: Workbook-scope named range.** Ignored (Tier-2 sheet-scope
  only, per honest scope (d)).

**Postconditions:**
- Caller has a list of `TableRegion`s; each carries its
  provenance (`source` field) for downstream emit decisions.

**Acceptance Criteria:**
- ✅ ListObjects detected exactly once each, attributed `"listobject"`.
- ✅ Sheet-scope named ranges detected; workbook-scope ignored.
- ✅ Gap-detect respects `gap_rows` / `gap_cols` thresholds.
- ✅ Default `gap_rows=2`, `gap_cols=1`.
- ✅ `mode="whole"` returns exactly one region.

---

### UC-04 — Read a table region (with merges, multi-row headers, value extraction)

**Actors:** Caller, xlsx_read library.

**Preconditions:**
- `TableRegion` from UC-03.

**Main Scenario:**
1. Caller invokes
   `reader.read_table(region, header_rows="auto",
   merge_policy="anchor-only", datetime_format="ISO")`.
2. Library reads cell values from the region.
3. Library detects header rows (top rows with column-spanning
   merges); flattens via ` › ` separator.
4. Library applies merge policy.
5. Library applies number-format heuristic per cell.
6. Library converts datetimes per `datetime_format`.
7. Library returns `TableData(rows, headers, warnings, region)`.

**Alternative Scenarios:**
- **A1: ListObject with `headerRowCount=0`.** Library emits
  synthetic headers `col_1..col_N`; appends warning `"Table 'X'
  had no headers; emitted synthetic col_1..col_N"`. Output shape
  is **still** array-of-objects (R2-M4 fix).
- **A2: Merge straddles header/body cut.** Library appends
  `AmbiguousHeaderBoundary` warning; does **not** raise.
- **A3: Formula present + `cell.value=None`.** Stale-cache
  detected; warning appended; raw `None` returned for that cell
  (do not invent a value).
- **A4: Rich-text cell.** Spans concatenated as plain text.
- **A5: Hyperlink + `include_hyperlinks=True`.** Cell value
  replaced with the hyperlink target URL.
- **A6: `include_formulas=True`.** Cell value replaced with the
  formula string (leading `=` preserved).
- **A7: Overlapping merges.** `OverlappingMerges` raised
  immediately on first detection.
- **A8: `header_rows=0`** (explicit). No header row; synthetic
  `col_1..col_N` emitted; same warning as A1.

**Postconditions:**
- Caller holds a `TableData` ready to serialise to JSON / CSV /
  Markdown / other downstream.

**Acceptance Criteria:**
- ✅ Multi-row header auto-detection flattens correctly.
- ✅ ` › ` separator (U+203A) used in flattened keys.
- ✅ All three merge policies behave per spec.
- ✅ Number-format heuristic emits formatted values (decimal,
  percent, currency, leading-zero text, date).
- ✅ Hyperlinks extracted when requested.
- ✅ Stale-cache warning emitted, never silently swallowed.
- ✅ `OverlappingMerges` raised on corrupted input.

---

### UC-05 — Caller-facing thread-safety contract

**Actors:** Caller (long-running Claude Code session, multi-threaded
caller).

**Preconditions:**
- Multiple user requests arrive concurrently.

**Main Scenario:**
1. Each request creates its own `WorkbookReader` instance.
2. No reader is shared across threads.

**Alternative Scenarios:**
- **A1: Caller violates contract.** Behavior is undefined
  (openpyxl `Workbook` is not thread-safe). Library does **not**
  attempt to lock; documentation makes this explicit.

**Postconditions:**
- Concurrent reads succeed when each thread owns its own reader.

**Acceptance Criteria:**
- ✅ `WorkbookReader.__doc__` contains the thread-safety note.
- ✅ `skills/xlsx/.AGENTS.md §xlsx_read` contains the note.
- ✅ No module-level singleton state in `xlsx_read/*.py` (regression
  test grepping for module-level mutable globals).

---

### UC-06 — Closed-API enforcement (`ruff` banned-api gate)

**Actors:** Developer / CI.

**Preconditions:**
- `pyproject.toml` configured with
  `[tool.ruff.lint.flake8-tidy-imports.banned-api]` rule banning
  `xlsx_read._*` imports.

**Main Scenario:**
1. Developer attempts to add `from xlsx_read._values import ...`
   in a sibling module.
2. `ruff check scripts/` fails with a banned-api error.
3. Developer changes the import to public surface (or extends
   `__init__.py` re-exports if intentional).

**Alternative Scenarios:**
- **A1: Internal sibling import** (`from ._values import ...` inside
  the package itself). Allowed — banned-api targets external imports
  only (`xlsx_read._*`, not `._*`).
- **A2: `install.sh`** runs `ruff check scripts/` post-install;
  fails loud if any leaky imports exist in tracked code.

**Postconditions:**
- No external module ever imports `xlsx_read._*`.

**Acceptance Criteria:**
- ✅ `pyproject.toml` created at `skills/xlsx/scripts/pyproject.toml`
  with the banned-api rule.
- ✅ `ruff>=0.5.0` in `requirements.txt`.
- ✅ `install.sh` runs `ruff check scripts/` and fails on violations.
- ✅ Regression unit test asserts `__all__` membership.

---

## 4. Non-functional Requirements

### 4.1. Performance (M-tier — within xlsx-2/-3/-7 envelope)
- **Open + sheet enumeration:** ≤ 200 ms for typical (≤ 1 MiB)
  workbooks on `read_only=True` path.
- **`detect_tables` (3-tier) on a 100-sheet workbook with 1
  ListObject + 1 gap-detected region per sheet:** ≤ 5 s wall-clock.
- **`read_table` on a 10 000-row × 20-col region:** ≤ 3 s, ≤ 200 MiB
  RSS (parallel xlsx-7 performance envelope).
- **Stretch (NOT enforced):** 100 000-row × 20-col → no upper bound
  in v1; document as "use `read_only=True` for large workbooks".

### 4.2. Security
- Pure-Python + lxml. No `eval`, no shell, no subprocess, no
  network. Trust boundary: input `.xlsx` file. Threats mitigated:
  - **XXE / billion-laughs.** `openpyxl` uses lxml; xlsx files are
    ZIP-archived XML parts. `xlsx_read` does **NOT** parse raw XML
    outside of `openpyxl`'s already-hardened code path.
  - **Path traversal / zip-slip.** `openpyxl` reads via `zipfile`
    standard library; library does **NOT** extract to disk.
  - **DoS via huge merge ranges / sparse regions.** `read_only=True`
    streaming + bounded region reads cap memory.
  - **Macro execution.** `MacroEnabledWarning` surfaces but library
    does **NOT** execute VBA / OLE objects.

### 4.3. Compatibility
- Python ≥ 3.10 (matches existing xlsx skill baseline).
- `openpyxl >= 3.1.0` (already in `requirements.txt`).
- `ruff >= 0.5.0` (new dependency, added by this task).
- macOS + Linux (xlsx skill platforms; no Windows-specific paths).

### 4.4. Scalability
- Library is **stateless per call** beyond the bound `Workbook`
  reference. No caching across reader instances. Caller may keep a
  reader instance alive for the lifetime of one request; closing is
  via `WorkbookReader.close()` (releases the underlying `openpyxl`
  Workbook).

### 4.5. Maintainability
- ≤ 700 LOC per module (xlsx-7 precedent); over-target → review
  before splitting further.
- 100 % `__all__` coverage of public symbols.
- Mandatory unit-test colocation under `xlsx_read/tests/`.

---

## 5. Acceptance Criteria (binary, library-level)

### 5.1. Module + toolchain layout
- ✅ Package exists at `skills/xlsx/scripts/xlsx_read/`.
- ✅ Modules: `__init__.py`, `_workbook.py`, `_sheets.py`,
  `_merges.py`, `_tables.py`, `_headers.py`, `_values.py`.
- ✅ All non-`__init__` modules start with `_` (closed-API
  prefix convention).
- ✅ `__init__.py` declares `__all__` listing exactly the public
  surface from R1–R10.
- ✅ `skills/xlsx/scripts/pyproject.toml` created with banned-api
  rule for `xlsx_read._*`.
- ✅ `requirements.txt` contains `ruff>=0.5.0`.
- ✅ `install.sh` runs `ruff check scripts/` and fails loud.

### 5.2. Public API behavior
- ✅ `open_workbook(path)` returns `WorkbookReader`.
- ✅ `WorkbookReader.sheets()` returns ordered `list[SheetInfo]`.
- ✅ `WorkbookReader.detect_tables(sheet, mode, gap_rows, gap_cols)`
  returns `list[TableRegion]`.
- ✅ `WorkbookReader.read_table(region, **opts)` returns `TableData`.
- ✅ `WorkbookReader.close()` releases the underlying Workbook.
- ✅ Public dataclasses (`SheetInfo`, `TableRegion`, `TableData`)
  are `frozen=True` at the outer level.

### 5.3. Honest-scope locks
- ✅ Read-only (no write methods in public API).
- ✅ No formula evaluation (cached value only; opt-in formula string
  via `include_formulas=True`).
- ✅ No pandas import.
- ✅ Workbook-scope named ranges ignored in `detect_tables`.
- ✅ ListObject `headerRowCount=0` emits synthetic `col_1..col_N` +
  warning.
- ✅ Overlapping merges raise `OverlappingMerges` (fail-loud).
- ✅ `WorkbookReader` documented NOT thread-safe.
- ✅ No module-level mutable singletons (regression test).
- ✅ `skills/xlsx/SKILL.md §10` updated with known-duplication
  marker pointing to xlsx-10.B.

### 5.4. Closed-API enforcement
- ✅ `ruff check scripts/` is green at task close.
- ✅ Unit test asserts `__all__` matches public surface; fails if
  a new symbol leaks.
- ✅ Regression unit test scans public API return values; fails if
  any `openpyxl.*` type is reachable via `type(...)` inspection.

### 5.5. Test suite (≥ 20 E2E scenarios — fixed list)
1. `open_encrypted_raises_EncryptedWorkbookError` (cross-3).
2. `open_xlsm_emits_MacroEnabledWarning_only` (cross-4).
3. `open_corrupted_zip_propagates_openpyxl_error_unchanged`.
4. `sheets_enumerate_visible_plus_hidden_state_field`.
5. `sheets_enumerate_include_hidden_skipped_by_caller_filter`.
6. `sheets_resolver_NAME_returns_one_entry`.
7. `sheets_resolver_all_returns_all`.
8. `sheets_resolver_missing_NAME_raises_SheetNotFound`.
9. `merges_anchor_only_three_fixtures` (row-merge / col-merge /
   rect-merge).
10. `merges_fill_three_fixtures`.
11. `merges_blank_three_fixtures`.
12. `tables_listobject_detect_with_xl_tables_fixture`.
13. `tables_listobject_headerRowCount_zero_synthetic_headers`.
14. `tables_named_range_detect_sheet_scope`.
15. `tables_named_range_workbook_scope_ignored`.
16. `tables_gap_detect_default_thresholds_2_rows_1_col`.
17. `tables_auto_fallback_no_listobjects_uses_gap_detect`.
18. `headers_single_row_default_behavior`.
19. `headers_multi_row_auto_detect_flatten_with_U203A`.
20. `headers_ambiguous_boundary_emits_warning`.
21. `values_formula_cached_default`.
22. `values_formula_stale_cache_emits_warning`.
23. `values_number_format_heuristic_decimal_percent_currency_text`.
24. `values_datetime_iso_excel_serial_raw`.
25. `values_hyperlink_extracted_when_opted_in`.
26. `values_rich_text_flatten_spans`.
27. `public_api_closed_no_openpyxl_leak` (regression).
28. `overlapping_merges_raises_OverlappingMerges` (M8 fix).
29. `dataclasses_outer_frozen_inner_mutable` (M3 honest scope).
30. `module_level_singletons_absent` (L2 fix regression).

> **Count:** 30 scenarios > 20 required (R13). Each scenario maps
> to one or more `pytest`/`unittest` test methods in
> `xlsx_read/tests/test_*.py`.

### 5.6. Regression gates
- ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` exits 0.
- ✅ Existing xlsx-2 / xlsx-3 / xlsx-6 / xlsx-7 E2E suites are green
  (no-behavior-change gate; this task does **not** modify their
  source).
- ✅ 5-file `diff -q` silent gate (CLAUDE.md §2): `office/`,
  `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py`
  unchanged across all four office skills.

---

## 6. Constraints and Assumptions

### 6.1. Technical constraints
- **No new system tools.** `openpyxl`, `lxml`, and the new `ruff`
  Python dep cover everything. No `pandas`. No `subprocess`. No
  `eval`. No network.
- **Closed API surface enforced statically** via `ruff` banned-api
  (not at runtime — runtime checks would add overhead and still be
  bypassable; static linting is the right boundary).
- **No cross-skill replication.** Library lives in
  `skills/xlsx/scripts/xlsx_read/` only.
- **5-file silent diff gate** (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`) must remain unchanged.

### 6.2. Business / process constraints
- **xlsx-10.B is deferred.** This task **explicitly does not**
  refactor `xlsx_check_rules/`. Temporary duplication is accepted
  per backlog R2-H2 ownership-bounded scope.
- **Ownership clock starts at xlsx-9 merge** (not this task's
  merge): xlsx-9 owner opens xlsx-10.B ≤ 14 calendar days after
  xlsx-9 lands.

### 6.3. Assumptions
- A1: openpyxl `>=3.1.0` exposes `ws.merged_cells.ranges` as an
  iterable of `MergedCellRange` (verified in existing xlsx-7 code at
  `scope_resolver.py:148`).
- A2: openpyxl `>=3.1.0` exposes `cell.hyperlink.target` (verified
  in openpyxl docs; will be smoke-tested early in implementation).
- A3: ListObjects XML schema (`xl/tables/tableN.xml`) is identical
  to that used by xlsx-7 (verified in
  `skills/xlsx/scripts/xlsx_check_rules/scope_resolver.py`).
- A4: ECMA-376 forbids overlapping merges, but real-world corrupted
  workbooks contain them; openpyxl's behavior on such input is
  **unverified at planning time** (M8 design-question — resolved
  in the architecture spike: explicit detect-and-raise regardless
  of openpyxl's behavior).
- A5: `read_only=True` mode of openpyxl preserves
  `<mergeCells>` data sufficiently for `_merges.py` to function
  (will be empirically smoke-tested in spike).

---

## 7. Open Questions

> **Convention:** Questions are split into **BLOCKING** (cannot
> proceed without answer) and **NON-BLOCKING** (decision deferred to
> architecture phase or implementation-time judgement).

### 7.1. Blocking — none.

All required decisions are either locked by the backlog row or
recorded as deliberate honest-scope items.

### 7.2. Non-blocking (deferred to architect)

- **Q-A1.** Should `WorkbookReader.close()` be auto-invoked via a
  context-manager protocol (`__enter__` / `__exit__`)? Backlog row
  does not specify. **Architect to decide** — recommendation: yes
  (Pythonic; cheap to add).
- **Q-A2.** Should `MacroEnabledWarning` be a `UserWarning` subclass
  (caller can `warnings.filterwarnings` it away) or a plain
  `Warning`? **Recommendation:** `UserWarning` subclass — standard
  Python practice; callers can opt out trivially.
- **Q-A3.** Should `SheetInfo` carry the openpyxl `Worksheet`
  reference (caller convenience) or a sheet-name handle only
  (closed-API purity)? **Recommendation:** name-handle only;
  callers re-resolve via `reader._resolve_sheet(name)` internally.
  (Leaning toward closed-API purity per R1.)
- **Q-A4.** Should `_headers.py` use the existing xlsx-7
  `scope_resolver._header_row_has_merged_cells` heuristic verbatim
  or a fresh implementation? **Recommendation:** fresh
  implementation in `xlsx_read/` (duplication is the **whole point**
  of the 10.A → 10.B split; later 10.B refactors xlsx-7 to consume
  `xlsx_read/`, not the other way around).
- **Q-A5.** Should `_values.py` number-format heuristic match
  xlsx-7's exactly, or be a fresh implementation with documented
  divergence? **Recommendation:** fresh + documented divergence
  (same rationale as Q-A4); divergence list captured in
  `_values.py` module docstring.

### 7.3. Locked decisions (recorded for traceability)

- **D1.** `header_rows="auto"` is the **default** (R2-L3 fix).
- **D2.** `gap_rows=2`, `gap_cols=1` default (M4 fix).
- **D3.** Outer dataclasses `frozen=True`; inner sequences mutable
  (M3 + R2-M6 fixes).
- **D4.** Overlapping merges → fail-loud `OverlappingMerges`
  (M8 fix; pinning openpyxl version is **not** an acceptable
  alternative — R2-M5 fix).
- **D5.** Closed-API enforcement via `ruff` banned-api in
  `pyproject.toml`, **not** via `validate_skill.py` extension
  (R2-M2 + R3-M1 separation-of-concerns fix).
- **D6.** xlsx-7 refactor explicitly deferred to xlsx-10.B
  (R3-M3 split).
- **D7.** No thread-safety locking — library documents the
  constraint; caller responsible (L2 fix).
- **D8.** Workbook-scope named ranges ignored in `detect_tables`
  (mirror xlsx-7; honest-scope item d).
