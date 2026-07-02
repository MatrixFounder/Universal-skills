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
| LibreOffice (this skill) | `python3 scripts/xlsx_recalc.py file.xlsx` | Headless `soffice --convert-to` round-trip with `OOXMLRecalcMode=0` seeded into a throw-away profile ("recalculate always on load"), then a self-verification pass. |
| Microsoft Excel | Opening and saving the file in the desktop app | Not scriptable without COM/AppleScript. |
| Gnumeric (`ssconvert`) | `ssconvert file.xlsx file.xlsx` | Another GPL CLI option; not as feature-complete as LibreOffice. |
| `xlwings` (Python+Excel) | `xlwings.Book(path).save()` | Requires Excel installed; macOS + Windows only. |

`xlsx_recalc.py` is the recommended path on any machine where
LibreOffice is available.

### Why not a StarBasic macro (LibreOffice 26.2 gotcha)

Until 2026-07 `xlsx_recalc.py` drove a one-shot StarBasic macro
(`macro:///Standard.Module1.RecalcAndSave`) installed into a second
user profile passed via `-env:UserInstallation=`. LibreOffice 26.2
broke that silently, twice over:

1. Only the FIRST `-env:UserInstallation=` on the command line is
   honoured — the macro was installed into a profile LibreOffice
   never read.
2. Even with the macro in the right profile, cold (fresh) profiles
   drop the CLI `macro:///` dispatch during first-run initialisation.

In both cases `soffice` exits 0, so the script reported success while
every formula cell stayed `None`. The `--convert-to` path has neither
failure mode, and the script now verifies its output at the XML level
(at least one formula cell must carry a cached `<v>`) and exits
non-zero otherwise — the total silent no-op that shipped on 26.2
cannot pass unnoticed again. Do not reintroduce `macro:///`-based
flows for xlsx work.

Note for plain `--convert-to` users: LibreOffice's DEFAULT load mode
keeps whatever cached values are already in the file, so a stale
(wrong) cache survives an un-seeded conversion. The `OOXMLRecalcMode=0`
profile seed is what forces a true recalculation.

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

## Cross-sheet reference syntax

Excel/OOXML uses `!` (not `.`) as the sheet-to-cell separator. A
formula pointing at another sheet reads `=Sheet1!A1`, not `Sheet1.A1`
or `'Sheet 1'.A1` (the latter two are LibreOffice Calc's native syntax
and *only* render correctly inside `.ods`; writing them into an
`.xlsx` yields `#NAME?` after recalc). When the sheet name contains a
space, punctuation, or begins with a digit, wrap it in single quotes:
`='Sheet With Space'!A1` or `='Q1 2024'!B2`. `openpyxl` does not
rewrite this for you — emit the quoted form from the start.

## Interaction with tracked changes and merged cells

LibreOffice's recalc does not disturb tracked changes or merged
ranges; `xlsx_recalc.py` performs a plain load-recalculate-save
round-trip with no extra flags. Still, validate the file before and
after with `office/validate.py` if the workbook is important — the
structural checks are fast and catch accidental corruption.
