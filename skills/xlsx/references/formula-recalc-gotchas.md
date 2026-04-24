# Formula recalculation gotchas

Every Excel/LibreOffice feature that makes spreadsheets *useful*
depends on cached formula values: chart data sources, conditional
formatting, pivot inputs, external consumers reading the file with
`openpyxl(data_only=True)`. When cached values go stale (or never
existed), everything downstream silently breaks.

## The failure mode in one sentence

`openpyxl` writes `.xlsx` files with formulas stored as text strings
and *no cached values*. Anything that consumes the file without
opening and saving it in an actual spreadsheet application sees
`None` where numbers should be.

## How to tell if a file has stale values

1. Open with openpyxl in `data_only=True`.
2. For any cell with a formula, `cell.value` is the cached value if
   one was stored, or `None` if not.

```python
from openpyxl import load_workbook
wb = load_workbook("file.xlsx", data_only=True)
ws = wb.active
print(ws["B2"].value)  # 42.0 if fresh, None if stale
```

## Engines that *do* recalculate

| Tool | Command | Notes |
|---|---|---|
| LibreOffice (this skill) | `python3 scripts/xlsx_recalc.py file.xlsx` | Uses headless `soffice` + a throw-away StarBasic macro. |
| Microsoft Excel | Opening and saving the file in the desktop app | Not scriptable without COM/AppleScript. |
| Gnumeric (`ssconvert`) | `ssconvert file.xlsx file.xlsx` | Another GPL CLI option; not as feature-complete as LibreOffice. |
| `xlwings` (Python+Excel) | `xlwings.Book(path).save()` | Requires Excel installed; macOS + Windows only. |

`xlsx_recalc.py` is the recommended path on any machine where
LibreOffice is available.

## Engines that do *not* recalculate

- `pandas.read_excel` — just reads the cached value. If none exists,
  `NaN`.
- `openpyxl` on its own — never computes formulas.
- `xlsxwriter` — write-only, no recalc.

## Common symptoms

| Symptom | Root cause |
|---|---|
| "My pivot table shows no data." | Cached values are None; pivot source is formulas. Run `xlsx_recalc.py`. |
| "My chart looks empty." | Same. |
| "`pandas.read_excel` returns NaN for formula columns." | Same. |
| "Two consecutive runs of openpyxl code keep the old cached values." | openpyxl preserves whatever cache was in the file on read; it doesn't update it on save. Run `xlsx_recalc.py` after any write. |

## Performance of `xlsx_recalc.py`

Rule of thumb: 1–3 seconds of overhead for launching LibreOffice plus
~20ms per thousand cells of actual recalc. For files up to ~50k cells
the script finishes in under five seconds. For larger sheets consider
increasing `--timeout` and running it as a single pass over a batch
of files rather than per-file.

## Error cells after recalc

`xlsx_recalc.py --scan-errors` reports cells containing `#REF!`,
`#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!`, or `#NULL!`. Any of
these in a model you are about to ship is usually a red flag —
investigate before delivering.

## Interaction with tracked changes and merged cells

LibreOffice's recalc does not disturb tracked changes or merged
ranges; the macro used by `xlsx_recalc.py` calls `calculateAll()` and
`store()` with no extra flags. Still, validate the file before and
after with `office/validate.py` if the workbook is important — the
structural checks are fast and catch accidental corruption.
