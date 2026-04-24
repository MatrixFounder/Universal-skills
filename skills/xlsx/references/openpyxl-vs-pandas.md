# openpyxl vs pandas: when to reach for which

Both libraries read and write `.xlsx`. They have different sweet
spots, and mixing them correctly is what most "why doesn't my number
show up" problems come down to.

## `pandas.read_excel` / `DataFrame.to_excel`

Strengths:
- Fast, vectorised, handles large tabular data with a one-liner.
- Great for ETL: pivot, filter, join, export.
- Preserves numeric types out of the box.

Weaknesses:
- `to_excel` discards most formatting. Fonts, colours, borders, number
  formats, and column widths are lost.
- Formulas can only be written as strings (identical to openpyxl), but
  with `to_excel` you don't get structured access to `cell.value =
  "=SUM(A1:A10)"`.
- Merged cells and multi-level headers are fragile; reading a file
  that Word-style-merges the first two rows often yields `NaN` in
  places you don't expect.

Rule of thumb: use pandas for "ingest a CSV, reshape, write a simple
tabular .xlsx". The moment someone asks for colour coding, a frozen
header, or a chart, switch to openpyxl.

## `openpyxl` (writing)

Strengths:
- Full control over styling: fonts, fills, borders, number formats.
- Named styles, merged cells, freeze panes, auto-filter, conditional
  formatting, data validation, charts, images.
- You can write formulas as plain strings (`cell.value = "=A1+B1"`) —
  LibreOffice or Excel will recalculate them on next open. For
  headless recalc use `xlsx_recalc.py`.

Weaknesses:
- Verbose for large tabular loads. A 10k-row spreadsheet takes tens of
  seconds with `ws.append(row)`.
- Writes formulas as strings only; the cached numeric value is always
  None until a spreadsheet engine opens and saves the file.

## `openpyxl` (reading)

Two modes:

- Default: reads formulas as strings. `cell.value` for a formula cell
  returns `"=SUM(A1:A10)"`.
- `data_only=True`: reads the *last cached value*. If the file was
  last saved by Excel or LibreOffice, you get numbers. If the file was
  last saved by openpyxl itself, you get `None`.

`xlsx_validate.py` uses `data_only=True` on purpose — a file saved by
openpyxl without a recalc pass will show as "no errors" because every
cell is `None`. The `--fail-empty` flag catches that situation.

## Common mixed-use pattern

```python
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

df = pd.read_csv("input.csv", dtype=str, keep_default_na=False)
df.to_excel("tmp.xlsx", index=False, engine="openpyxl")

wb = load_workbook("tmp.xlsx")
ws = wb.active
for cell in ws[1]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="F2F2F2")
ws.freeze_panes = "A2"
wb.save("styled.xlsx")
```

`csv2xlsx.py` does essentially this in a single pass. Use the script
when it covers the case; inline code when you need something more
specific (multi-sheet, conditional formatting, charts).

## Never use `xlsxwriter` and `openpyxl` on the same file

`xlsxwriter` is another popular library — it creates `.xlsx` but
cannot read or modify them. If you accidentally open an
`xlsxwriter`-created file with `openpyxl`, and save it, you'll lose
some formatting because the two libraries track styles slightly
differently. Pick one library for the lifetime of the file.

## Preserving text vs number semantics

Leading zeros and long numeric IDs (credit card numbers, phone
numbers, account numbers) must stay as strings, or Excel silently
turns them into scientific notation. `csv2xlsx.py` detects this by
checking whether the first non-empty value in a column starts with a
zero and keeps the whole column as text if so. If you write your own
converter, either pass `dtype=str` to `pandas.read_csv` for the
affected columns, or set `cell.number_format = "@"` (text format) in
openpyxl.
