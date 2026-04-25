---
name: xlsx
description: Use when the user asks to create, transform, or validate Microsoft Excel .xlsx workbooks. Triggers include "csv to xlsx", "JSON to xlsx", "recalculate this workbook", "scan formula errors", "financial model in xlsx", "fix #REF errors", and related spreadsheet generation, recalculation, or OOXML round-trip tasks.
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
- "I wrote formulas with openpyxl, so the numbers are there." → **WRONG**. `openpyxl` stores formulas as strings with no cached value. Every downstream consumer (pandas, charts, external apps) sees `None`. Run `xlsx_recalc.py` before shipping.
- "Validation says OK, the formulas must be fine." → **WRONG**. `xlsx_validate.py` scans for cached error values. If there are no cached values at all (fresh openpyxl output), the scan is meaningless. Use `--fail-empty` or recalc first.
- "Leading zeros in my phone-number column vanished; it's fine." → **WRONG**. It is almost never fine. Excel and pandas both coerce `"007"` to `7` by default. `csv2xlsx.py` detects leading-zero columns and keeps them as text; inline code should either pass `dtype=str` to pandas or set `cell.number_format = "@"` in openpyxl.

## 2. Capabilities
- Convert a CSV / TSV to a styled `.xlsx` with bold header, freeze-first-row, auto-filter, auto column widths, and leading-zero preservation.
- Force formula recalculation in an `.xlsx` via headless LibreOffice, then optionally scan for error cells.
- Scan an `.xlsx` for formula errors (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!`, `#NULL!`) without recomputing.
- Add a bar / line / pie chart on a value range with optional categories, title, anchor; stays editable in Excel / LibreOffice.
- Unpack and repack `.xlsx` archives for raw OOXML editing (shared `office/` module with the docx skill).
- Structurally validate an `.xlsx` (relationships, content types, required parts).
- Reject password-protected and legacy `.xls` (CFB-container) inputs early with a clear remediation message (exit 3) instead of a `BadZipFile` traceback.

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: Spreadsheet tasks have well-defined inputs and outputs and benefit heavily from deterministic CLIs. Writing the styling code inline produces ugly workbooks every time; delegating to scripts frees the agent to focus on the user's intent.

## 4. Script Contract

- **Commands**:
  - `python3 scripts/csv2xlsx.py INPUT.csv OUTPUT.xlsx [--delimiter auto|,|;|\t] [--encoding utf-8] [--no-freeze] [--no-filter]`
  - `python3 scripts/xlsx_recalc.py INPUT.xlsx [--output OUT.xlsx] [--timeout 120] [--scan-errors] [--json]`
  - `python3 scripts/xlsx_validate.py INPUT.xlsx [--json] [--fail-empty]`
  - `python3 scripts/xlsx_add_chart.py INPUT.xlsx --type bar|line|pie --data RANGE [--categories RANGE] [--title TEXT] [--sheet NAME] [--anchor CELL] [--titles-from-data | --no-titles-from-data] [--output OUT.xlsx]`
  - `python3 scripts/office/unpack.py INPUT.xlsx OUTDIR/`
  - `python3 scripts/office/pack.py INDIR/ OUTPUT.xlsx`
  - `python3 scripts/office/validate.py INPUT.xlsx [--strict] [--json]`
- **Inputs**: positional paths; optional flags per command.
- **Outputs**: a single file at the named output path; `office/unpack.py` produces a directory tree; validators print a report (or JSON).
- **Failure semantics**: non-zero exit on missing input, invalid encoding, soffice errors, or formula errors (`xlsx_validate.py` returns 1 when errors are present). Error detail goes to stderr.
- **Idempotency**: `csv2xlsx.py` produces the same workbook for the same input every time. `xlsx_recalc.py` is idempotent on an already-recalculated workbook.
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
| Unpack for XML editing | `python3 scripts/office/unpack.py file.xlsx unpacked/` |
| Repack | `python3 scripts/office/pack.py unpacked/ file.xlsx` |
| Structural validation | `python3 scripts/office/validate.py file.xlsx` |

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

## 12. Resources

- [references/financial-modeling-conventions.md](references/financial-modeling-conventions.md) — colour coding, number formats, formula hygiene, drivers layout.
- [references/openpyxl-vs-pandas.md](references/openpyxl-vs-pandas.md) — which library for which job, read-mode pitfalls.
- [references/formula-recalc-gotchas.md](references/formula-recalc-gotchas.md) — why cached values matter, engines that recalc, engines that don't.
- [scripts/csv2xlsx.py](scripts/csv2xlsx.py) — CSV/TSV → styled workbook.
- [scripts/xlsx_recalc.py](scripts/xlsx_recalc.py) — LibreOffice-backed formula recalculation + error scan.
- [scripts/xlsx_validate.py](scripts/xlsx_validate.py) — fast formula-error scan without recalc.
- [scripts/office/](scripts/office/) — OOXML unpack/pack/validate, identical copy from the docx skill.
