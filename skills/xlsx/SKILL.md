---
name: xlsx
description: Use when the user asks to create, transform, validate, chart, preview, or password-protect Microsoft Excel .xlsx workbooks. Triggers include "csv to xlsx", "recalculate this workbook", "scan formula errors", "add a chart to xlsx", "bar / line / pie chart over a range", "financial model in xlsx", "fix #REF errors", "preview xlsx as image", "encrypt / decrypt / password-protect an xlsx", and related spreadsheet generation, recalculation, or OOXML round-trip tasks.
tier: 2
version: 1.0
license: LicenseRef-Proprietary
---
# xlsx skill

**Purpose**: Give the agent a deterministic, script-first path for
creating and sanity-checking `.xlsx` workbooks. The core operations
(CSV → styled .xlsx, force formula recalculation, scan for formula
errors, structural OOXML validation) are wrapped in small CLIs so the
agent does not have to rewrite openpyxl boilerplate on every task and
is never surprised by "formulas are stored but not calculated" (the
single most common xlsx bug).

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll just call `DataFrame.to_excel` and ship it." → **WRONG**. `to_excel` writes no styles, no frozen header, and no auto-filter. The result looks amateur. Use `csv2xlsx.py`.
- "I'll just call `pd.DataFrame.from_records(rows).to_excel(out)` on my LLM JSON output." → **WRONG**. Same `to_excel` styling gap, plus pandas' `infer_objects` heuristics silently promote mixed-type columns to `object`/`float64` (an `int` column with one `null` becomes `float64`). Use `json2xlsx.py` — preserves native JSON types, ISO-date auto-coercion, csv2xlsx-style header.
- "I wrote formulas with openpyxl, so the numbers are there." → **WRONG**. `openpyxl` stores formulas as strings with no cached value. Every downstream consumer (pandas, charts, external apps) sees `None`. Run `xlsx_recalc.py` before shipping.
- "Validation says OK, the formulas must be fine." → **WRONG**. `xlsx_validate.py` scans for cached error values. If there are no cached values at all (fresh openpyxl output), the scan is meaningless. Use `--fail-empty` or recalc first.
- "Leading zeros in my phone-number column vanished; it's fine." → **WRONG**. It is almost never fine. Excel and pandas both coerce `"007"` to `7` by default. `csv2xlsx.py` detects leading-zero columns and keeps them as text; inline code should either pass `dtype=str` to pandas or set `cell.number_format = "@"` in openpyxl.

## 2. Capabilities
- Convert a CSV / TSV to a styled `.xlsx` with bold header, freeze-first-row, auto-filter, auto column widths, and leading-zero preservation.
- Convert a JSON / JSONL document (file or stdin `-`) to a styled `.xlsx` with the SAME visual contract as csv2xlsx (`json2xlsx.py`). Three input shapes auto-detected: array-of-objects (single sheet), dict-of-arrays-of-objects (multi-sheet), JSONL (one JSON object per line — `.jsonl` extension). Preserves native JSON types (int / float / bool / null / str); ISO-8601 date strings auto-coerced to Excel datetime cells; `--strict-dates` makes timezone-aware datetimes a hard fail. Cross-cutting parity: cross-5 `--json-errors` envelope, cross-7 H1 same-path guard (exit 6 `SelfOverwriteRefused`), stdin pipe `-`. Round-trip contract with the future `xlsx2json.py` (xlsx-8) is frozen at [`skills/xlsx/references/json-shapes.md`](references/json-shapes.md).
- Force formula recalculation in an `.xlsx` via headless LibreOffice, then optionally scan for error cells.
- Scan an `.xlsx` for formula errors (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!`, `#NULL!`) without recomputing.
- Add a bar / line / pie chart on a value range with optional categories, title, anchor; stays editable in Excel / LibreOffice.
- Insert an Excel comment (legacy `<comment>`, optionally with the threaded-comment + personList Excel-365 modern layer) into a target cell, with cross-sheet `--cell` syntax and a batch mode that auto-detects the xlsx-7 findings envelope. Closes the "validation-агент расставляет замечания" pipeline together with `xlsx_check_rules.py` (xlsx-7).
- **Declarative business-rule validation** — `xlsx_check_rules.py` reads a YAML/JSON rules file alongside an `.xlsx` and emits a machine-readable findings envelope (`{ok, summary, findings}`) on stdout; pipes directly into `xlsx_add_comment.py --batch -` for cell-comment placement. Optional `--output` writes a workbook copy with a `Remarks` column + per-severity PatternFill. Hardened DSL (closed AST, no `eval`/`exec`), ReDoS-lint reject-list, billion-laughs YAML alias rejection, and a 100K-row × 10-rule perf contract (≤ 30 s wall-clock).
- Unpack and repack `.xlsx` archives for raw OOXML editing (shared `office/` module with the docx skill).
- Structurally validate an `.xlsx` (relationships, content types, required parts).
- Reject password-protected and legacy `.xls` (CFB-container) inputs early in the **reader scripts** (`xlsx_recalc.py`, `xlsx_validate.py`, `xlsx_add_chart.py`, `office/validate.py`, `office/unpack.py`, `preview.py`) with a clear remediation message (exit 3) instead of a `BadZipFile` traceback. `csv2xlsx.py` and `office_passwd.py` are not gated — the former takes CSV/TSV input (no encryption to detect), the latter is the encryption tool itself.
- Detect macro-enabled inputs (`.xlsm`, with `xl/vbaProject.bin`) and warn when the chosen output extension would silently drop the macros (`xlsm` → `xlsx`).
- Render any `.xlsx`/`.xlsm`/`.pdf` (or peer-skill `.docx`/`.pptx`) into a single PNG-grid preview via `preview.py` (LibreOffice + Poppler).
- Emit failures as machine-readable JSON to stderr with `--json-errors` (uniform across all four office skills).
- Set or remove a password on a `.xlsx`/`.docx`/`.pptx` (MS-OFB Agile, Office 2010+) via `office_passwd.py` — three modes: `--encrypt PASSWORD`, `--decrypt PASSWORD`, `--check` (exit 0 encrypted / 10 clean / 11 missing).

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: Spreadsheet tasks have well-defined inputs and outputs and benefit heavily from deterministic CLIs. Writing the styling code inline produces ugly workbooks every time; delegating to scripts frees the agent to focus on the user's intent.

## 4. Script Contract

- **Commands**:
  - `python3 scripts/csv2xlsx.py INPUT.csv OUTPUT.xlsx [--delimiter auto|,|;|\t] [--encoding utf-8] [--no-freeze] [--no-filter]`
  - `python3 scripts/xlsx_recalc.py INPUT.xlsx [--output OUT.xlsx] [--timeout 120] [--scan-errors] [--json]`
  - `python3 scripts/xlsx_validate.py INPUT.xlsx [--json] [--fail-empty]`
  - `python3 scripts/xlsx_add_chart.py INPUT.xlsx --type bar|line|pie --data RANGE [--categories RANGE] [--title TEXT] [--sheet NAME] [--anchor CELL] [--titles-from-data | --no-titles-from-data] [--output OUT.xlsx]`
  - `python3 scripts/xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx (--cell REF --author NAME --text MSG | --batch FILE [--default-author NAME] [--default-threaded]) [--threaded | --no-threaded] [--initials INI] [--date ISO] [--allow-merged-target] [--json-errors]`
  - `python3 scripts/xlsx_check_rules.py INPUT.xlsx --rules RULES.{json,yaml} [--sheet NAME | --all-sheets] [--visible-only] [--json | --human] [--max-findings N] [--summarize-after N] [--require-data] [--ignore-stale-cache] [--strict-aggregates] [--treat-numeric-as-date COL] [--treat-text-as-date COL] [--timeout SECONDS] [--no-strip-whitespace] [--no-table-autodetect] [--no-merge-info] [--output OUT.xlsx [--remark-column auto|LETTER|HEADER] [--remark-column-mode replace|append|new] [--streaming-output]] [--json-errors]`
  - `python3 scripts/office/unpack.py INPUT.xlsx OUTDIR/`
  - `python3 scripts/office/pack.py INDIR/ OUTPUT.xlsx`
  - `python3 scripts/office/validate.py INPUT.xlsx [--strict] [--json]`
  - `python3 scripts/preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110] [--gap 12] [--padding 24] [--label-font-size 14] [--soffice-timeout 240] [--pdftoppm-timeout 60]`
  - `python3 scripts/office_passwd.py INPUT [OUTPUT] (--encrypt PASSWORD | --decrypt PASSWORD | --check)` — pass `-` as PASSWORD to read it from stdin.
  - All scripts above accept `--json-errors` to emit failures as a single line of JSON on stderr (`{v, error, code, type?, details?}`). The schema version `v` is currently `1`; argparse usage errors are routed through the same envelope (`type:"UsageError"`).
- **Inputs**: positional paths; optional flags per command.
- **Outputs**: a single file at the named output path; `office/unpack.py` produces a directory tree; validators print a report (or JSON).
- **Failure semantics**: non-zero exit on missing input, invalid encoding, soffice errors, or formula errors (`xlsx_validate.py` returns 1 when errors are present). Error detail goes to stderr.
- **Idempotency**: `csv2xlsx.py` produces the same workbook for the same input every time. `xlsx_recalc.py` is idempotent on an already-recalculated workbook. **Exception**: `office_passwd.py --encrypt` is intentionally non-deterministic — Office encryption uses a fresh random salt per run.
- **Dry-run support**: not applicable.

## 5. Safety Boundaries
- **Allowed scope**: only the paths named on the command line; never write outside the requested output path.
- **Default exclusions**: do not fetch data from remote URLs; only read from the provided local file.
- **Destructive actions**: `xlsx_recalc.py` rewrites its input in place when `--output` is omitted — the convention matches how users expect "recalculate this file" to behave, but make it explicit to the user if the file is important.
- **Optional artifacts**: `office/schemas/` is optional; validators fall back to structural checks.

## 6. Validation Evidence
- **Local verification**:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scripts/requirements.txt` — installs openpyxl, pandas, lxml, defusedxml.
  - `python3 scripts/csv2xlsx.py examples/fixture.csv /tmp/out.xlsx && python3 scripts/office/validate.py /tmp/out.xlsx` — exit 0, validator reports `OK`.
  - `python3 scripts/xlsx_validate.py /tmp/out.xlsx --fail-empty` — exit 0 (no formula errors, values are concrete).
  - `python3 scripts/xlsx_recalc.py /tmp/out.xlsx --scan-errors --json | jq .ok` — prints `true` if LibreOffice is installed.
- **Expected evidence**: `/tmp/out.xlsx`, validator reports, non-empty `xlsx_validate.py --json`.
- **CI signal**: `python3 ../../.claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` — exit 0.

## 7. Instructions

### 7.1 Pick the script before writing inline code

1. **Check §10 Quick Reference first.** Most common tasks (CSV→xlsx, recalc, error scan) already exist.
2. Drop to inline `openpyxl`/`pandas` only when you need something the scripts don't cover (charts, conditional formatting, pivot sources).

### 7.2 Setup

1. **MUST** run `bash scripts/install.sh` once. It creates `scripts/.venv/` locally (nothing global), prints a warning for any missing system tool, and is idempotent.
2. **External system tools** (checked by `install.sh`, installed manually per project plan §3.3 "внешние инструменты — не бандлятся"):
   - **LibreOffice** (`soffice`) — required by `xlsx_recalc.py` to populate cached formula values that openpyxl cannot compute. macOS: `brew install --cask libreoffice`. Debian: `sudo apt install libreoffice --no-install-recommends`. Fedora: `sudo dnf install libreoffice`.
   Commands that need it fail with a clear error until it's installed.

### 7.3 Creating `.xlsx` from CSV

1. `python3 scripts/csv2xlsx.py input.csv output.xlsx` covers 80% of cases.
2. Use `--delimiter ';'` for European exports; `--delimiter '\t'` for TSV.
3. Preserve leading zeros automatically — the script detects them and keeps the column as text. If you need to force that behaviour for a specific column, pre-process the CSV or write a custom openpyxl pass with `cell.number_format = "@"`.

### 7.4 Producing a workbook with formulas

1. Write the workbook with openpyxl: `cell.value = "=SUM(B2:B100)"`. Remember the formula is just a string.
2. **MUST** run `python3 scripts/xlsx_recalc.py file.xlsx` before shipping. Otherwise consumers that read with `data_only=True` see `None` for every formula cell.
3. After recalc, run `python3 scripts/xlsx_validate.py file.xlsx`. Any `#REF!` / `#DIV/0!` is a bug to fix, not a cosmetic issue.

### 7.5 Validating someone else's workbook

1. Structural: `python3 scripts/office/validate.py file.xlsx`.
2. Formula errors: `python3 scripts/xlsx_validate.py file.xlsx --fail-empty`. The `--fail-empty` flag catches the "formulas never recalculated" case.

### 7.6 Raw XML editing

Use the shared `office/` module (same as docx). Typical reason to drop into XML: tweaking a specific cell style, patching a corrupted `sharedStrings.xml`, or adding a relationship the user's downstream tool expects.

## 8. Workflows (Optional)

CSV to a styled, ready-to-ship workbook:

```markdown
- [ ] Inspect the CSV — check delimiter, encoding, leading zeros
- [ ] `python3 scripts/csv2xlsx.py data.csv out.xlsx`
- [ ] `python3 scripts/office/validate.py out.xlsx`
- [ ] Open in Excel/LibreOffice for a spot-check
```

Build a formula-driven model:

```markdown
- [ ] Write workbook with openpyxl (cells + formulas)
- [ ] `python3 scripts/xlsx_recalc.py out.xlsx --scan-errors`
- [ ] Surface any error cells to the user
- [ ] `python3 scripts/xlsx_validate.py out.xlsx`
```

Audit an incoming `.xlsx`:

```markdown
- [ ] `python3 scripts/office/validate.py in.xlsx`
- [ ] `python3 scripts/xlsx_validate.py in.xlsx --fail-empty`
- [ ] If --fail-empty fails, run `xlsx_recalc.py` first then revalidate
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Use `csv2xlsx.py` — styled header, frozen row, auto-filter, leading zeros preserved. | `DataFrame.to_excel("out.xlsx")` — unstyled, coerces leading zeros, no filter. |
| Run `xlsx_recalc.py` after any openpyxl write that touches formulas. | Ship the openpyxl output directly — cached values are `None`. |
| Combine pandas (fast ETL) with openpyxl (rich styling) in that order. | Mix `xlsxwriter` and `openpyxl` on the same file; styles diverge. |
| Use `@`-format or `dtype=str` for code-like columns. | Let pandas coerce "007" to `7`. |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The user didn't ask for styling." | A freeze-first-row and bold header are table stakes. Unstyled `to_excel` output looks amateur. |
| "Formulas will recalculate when the user opens the file." | Yes, but consumers like pandas, charts, and schedulers do not open the file — they read cached values. Always recalc for shared files. |
| "I need a chart, the scripts don't cover it." | Correct — drop to inline openpyxl for charts. The scripts cover the 80%. |
| "Just loading in pandas is fine — it handles everything." | pandas reads cached values (`data_only` semantics), so stale caches become NaN. Recalc first. |

## 10. Quick Reference

| Task | Command |
|---|---|
| CSV → styled .xlsx | `python3 scripts/csv2xlsx.py data.csv out.xlsx` |
| Force formula recalc | `python3 scripts/xlsx_recalc.py file.xlsx [--scan-errors]` |
| Scan for `#REF!`/`#DIV/0!`/... | `python3 scripts/xlsx_validate.py file.xlsx --fail-empty` |
| Add bar/line/pie chart | `python3 scripts/xlsx_add_chart.py file.xlsx --type bar --data B2:B10 [--categories A2:A10] [--title "..."]` |
| Insert single comment | `python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --cell A5 --author "..." --text "..." [--threaded]` |
| Batch comments from xlsx-7 findings | `python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --batch findings.json --default-author "..."` |
| Validate against declarative rules | `python3 scripts/xlsx_check_rules.py file.xlsx --rules rules.json --json` |
| Pipe findings into batch comments | `python3 scripts/xlsx_check_rules.py file.xlsx --rules rules.json --json \| python3 scripts/xlsx_add_comment.py file.xlsx annotated.xlsx --batch - --default-author "Reviewer"` |
| Workbook copy with Remarks column | `python3 scripts/xlsx_check_rules.py file.xlsx --rules rules.json --output reviewed.xlsx --remark-column auto` |
| Unpack for XML editing | `python3 scripts/office/unpack.py file.xlsx unpacked/` |
| Repack | `python3 scripts/office/pack.py unpacked/ file.xlsx` |
| Structural validation (deep) | `python3 scripts/office/validate.py file.xlsx [--json] [--strict]` |
| Preview as PNG-grid | `python3 scripts/preview.py file.xlsx preview.jpg [--cols 3] [--dpi 110]` |
| Set password | `python3 scripts/office_passwd.py clean.xlsx encrypted.xlsx --encrypt PASSWORD` (use `-` to read from stdin) |
| Remove password | `python3 scripts/office_passwd.py encrypted.xlsx clean.xlsx --decrypt PASSWORD` |
| Detect password | `python3 scripts/office_passwd.py file.xlsx --check` (exit 0 encrypted / 10 clean / 11 missing) |
| Machine-readable failures | append `--json-errors` to any of the above |

## 11. Examples (Few-Shot)

Fixture: [examples/fixture.csv](examples/fixture.csv).

**Input** — user request:
> Convert `sales.csv` into a presentable `.xlsx` and make sure the
> numbers are usable as a pivot source.

**Output** — agent action:
```bash
python3 scripts/csv2xlsx.py sales.csv sales.xlsx
python3 scripts/office/validate.py sales.xlsx
python3 scripts/xlsx_validate.py sales.xlsx --fail-empty
```

The output has no formulas, so `xlsx_validate.py --fail-empty` is the
right check; all cells carry concrete values.

**Input** — user request:
> The forecast workbook shows `#REF!` in a bunch of cells. Find them
> all.

**Output** — agent action:
```bash
python3 scripts/xlsx_recalc.py forecast.xlsx        # ensure cache is fresh
python3 scripts/xlsx_validate.py forecast.xlsx --json
```

Paste the JSON or the human report back to the user, grouped by error
type and sheet.

**Input** — user request:
> Run the validator on `timesheet.xlsx` and drop a comment on every
> problematic cell so my team can triage in Excel.

**Output** — agent action (xlsx-7 → xlsx-6 pipeline; piped envelope):
```bash
# xlsx_check_rules.py emits a JSON envelope of findings; xlsx_add_comment.py
# auto-detects the {ok, summary, findings} shape and writes one comment
# per finding (skipping group-findings with row=null).
python3 scripts/xlsx_check_rules.py timesheet.xlsx --rules rules.json --json \
    | python3 scripts/xlsx_add_comment.py timesheet.xlsx timesheet-annotated.xlsx \
        --batch - --default-author "Validator Bot"
```

The `--default-author` flag is required for envelope shape (DEP-2);
without it the script exits with `MissingDefaultAuthor`. To attach the
comments as Excel-365 threaded comments instead of legacy bubbles, add
`--default-threaded`.

## 12. Resources

- [references/financial-modeling-conventions.md](references/financial-modeling-conventions.md) — colour coding, number formats, formula hygiene, drivers layout.
- [references/openpyxl-vs-pandas.md](references/openpyxl-vs-pandas.md) — which library for which job, read-mode pitfalls.
- [references/formula-recalc-gotchas.md](references/formula-recalc-gotchas.md) — why cached values matter, engines that recalc, engines that don't.
- [scripts/csv2xlsx.py](scripts/csv2xlsx.py) — CSV/TSV → styled workbook.
- [scripts/xlsx_recalc.py](scripts/xlsx_recalc.py) — LibreOffice-backed formula recalculation + error scan.
- [scripts/xlsx_validate.py](scripts/xlsx_validate.py) — fast formula-error scan without recalc.
- [scripts/xlsx_add_chart.py](scripts/xlsx_add_chart.py) — bar / line / pie chart attachment over a cell range; chart stays editable in Excel / LibreOffice.
- [scripts/xlsx_add_comment.py](scripts/xlsx_add_comment.py) — insert an Excel comment (legacy + optional Excel-365 threaded) into a target cell; single-cell mode (`--cell`) or batch mode (`--batch`, auto-detects xlsx-7 findings envelope).
- [references/comments-and-threads.md](references/comments-and-threads.md) — OOXML data model behind `xlsx_add_comment.py`: part graph, cell-syntax forms, the C1/M-1/M6 pitfalls list (read these before editing the scanner code), v1 honest-scope.
- [scripts/xlsx_check_rules.py](scripts/xlsx_check_rules.py) — declarative business-rule validator. Reads YAML/JSON rules, emits `{ok, summary, findings}` envelope; pipes into `xlsx_add_comment.py --batch -`. Closed AST + ReDoS lint + billion-laughs alias rejection. Backed by [scripts/xlsx_check_rules/](scripts/xlsx_check_rules/) package.
- [references/xlsx-rules-format.md](references/xlsx-rules-format.md) — full SPEC for `xlsx_check_rules.py`: rule shape, scope vocabulary, check vocabulary, AST safety, output envelope, exit codes, honest-scope catalogue, regression battery anchors.
- [examples/check-rules-timesheet.json](examples/check-rules-timesheet.json) + [examples/check-rules-timesheet.xlsx](examples/check-rules-timesheet.xlsx) — worked SPEC §10 example, ready to run end-to-end (validate → pipe → annotate).
- [scripts/preview.py](scripts/preview.py) — universal `INPUT → PNG-grid` renderer for `.xlsx`/`.xlsm`/`.docx`/`.pptx`/`.pdf`. Byte-identical across all four office skills.
- [scripts/office_passwd.py](scripts/office_passwd.py) — set / remove / detect password protection on `.xlsx`/`.docx`/`.pptx` via msoffcrypto-tool (MS-OFB Agile, Office 2010+). Byte-identical across the three OOXML skills (not pdf — pdf has its own AcroForm encryption). Pass `-` as the password to read it from stdin.
- [scripts/_errors.py](scripts/_errors.py) — `--json-errors` envelope helper (schema `v=1`).
- [scripts/_soffice.py](scripts/_soffice.py) — LibreOffice subprocess wrapper.
- [scripts/office/](scripts/office/) — OOXML unpack/pack/validate, byte-identical copy from the docx skill (master — see CLAUDE.md §2). Includes deep `XlsxValidator` (sheet chain, sst+styles index bounds, sheet-name uniqueness, orphan parts).
