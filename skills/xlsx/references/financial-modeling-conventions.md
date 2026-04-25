# Financial modeling conventions

Investment banks, corporate finance teams, and auditors have built a
shared visual language for spreadsheet models. It is not mandated by
any ISO standard, but near-universally followed in firms like
McKinsey, Goldman, Morgan Stanley, and the Big Four. Reference works
such as Rosenbaum & Pearl's *Investment Banking* and Pignataro's
*Financial Modeling and Valuation* all describe essentially the same
rules. This note summarises the operational ones that matter when a
script is producing or checking an `.xlsx`.

## Cell colour coding

| Colour | Meaning |
|---|---|
| Blue font | Hardcoded input (driver, assumption, raw data). |
| Black font | Formula that references inputs or other formulas within the same sheet. |
| Green font | Cross-sheet link (`=Inputs!B5`). |
| Red font | Link to an external workbook (`='[Assumptions.xlsx]Sheet1'!A1`). |
| Yellow fill | Highlight of a key driver the reviewer should look at first. |
| Grey fill | Headers, totals, section separators (non-editable per convention). |

`openpyxl` exposes these via `Font(color="0000FF")` and
`PatternFill(fill_type="solid", fgColor="FFFF00")`. Hard-coded values
that *look* like formulas (e.g. an analyst typed 0.15 for 15% growth)
still count as blue — the colour follows what the cell *is*, not what
it looks like.

## Number formats

| Kind | Recommended format string |
|---|---|
| Currency with sign | `$#,##0;($#,##0);-` |
| Currency with two decimals | `$#,##0.00;($#,##0.00);-` |
| Percentage | `0.0%` |
| Multiple (multipliers, ratios) | `0.0x` |
| Count | `#,##0` |
| Year | `0000` |
| Date | `yyyy-mm-dd` (ISO) or `dd-mmm-yy` (banking) |

The use of parentheses for negatives (`($1,234)` instead of `-$1,234`)
is standard; scripts that emit financial numbers as bare Python floats
produce `-1234.0` and look wrong in context.

The canonical three-part pattern for audit templates is
`"$#,##0;($#,##0);-"` — positives render normally, negatives in
parentheses, and zero collapses to a dash so empty rows read cleanly.
Assign it with `cell.number_format = "$#,##0;($#,##0);-"`.

## Year values must be plain text

Store year labels as strings (`cell.value = "2024"`), not integers. A
numeric `2024` under any `#,##0`-style format renders as `2,024` and
misleads every reader. Either keep the cell as plain text (value is
`"2024"`, format `"@"`) or pin it to the `0000` year format from the
table above. Mixing a thousand-separator format with a numeric year is
the single most common cosmetic bug in auto-generated FY headers.

## Column-letter arithmetic past column 26

Column letters extend past `Z` by gaining a second character:
`AA`–`AZ` cover columns 27–52, `BA`–`BZ` cover 53–78, so column 52 is
`AZ` and column 64 is `BL` (not `BK`). Financial models with many FY
columns regularly compute cell addresses arithmetically; use
`openpyxl.utils.get_column_letter(n)` instead of hand-rolling
`chr(64+n)`, which breaks the moment `n` crosses 26.

## Formula hygiene

1. **One assumption per cell.** If a growth rate appears in a formula
   four times, extract it to a single input cell and reference it.
2. **Absolute vs relative references** — use `$B$6` when the reference
   should stay put when the formula is copied; leave it relative when
   it should slide. Mixed (`$B6`, `B$6`) is common in price/volume
   tables.
3. **Comment the source of every input.** A short comment like
   "Source: FY2024 10-K, page 45" saves hours when an audit asks why
   a number is what it is. `openpyxl` supports this via
   `Comment("Source: …", "AuthorName")`. Every numeric hardcode
   should carry an adjacent cell comment or sibling cell in the
   standard form `Source: <System/Document>, <Date>,
   <Reference/Ticker>, <URL>` so audit trails remain intact across
   handoffs.
4. **No hidden magic numbers inside formulas.** If `=A1*1.2` means "add
   20%", move the 1.2 (or the 0.2) to its own input cell.

## Drivers layout

Larger models put all assumptions on a dedicated "Inputs" (or
"Drivers") sheet, referenced from every downstream sheet via green
formulas. This allows a reviewer to flex a single driver and watch
every dependent figure update. Scripts that programmatically build
models should respect the convention by keeping drivers on a sheet
named `Inputs` (or `Assumptions`) even when there's only one or two
of them.

## Recalc is mandatory before delivery

`openpyxl` stores formulas as strings; the cached values remain
`None` until some engine opens and resaves the workbook. If you plan
to share the file (as opposed to feeding it back into another Python
script) run `xlsx_recalc.py` so consumers see populated cells rather
than blank cells with formulas that only render on their machine.

## Protect key cells

For models that will be handed to non-technical users, consider
protecting the drivers with `ws.protection.sheet = True` and marking
input cells explicitly unprotected (`cell.protection = Protection(
locked=False)`). This prevents accidental edits to the calc layer.

## Further reading

- Rosenbaum & Pearl, *Investment Banking: Valuation, Leveraged
  Buyouts, and Mergers & Acquisitions*.
- Pignataro, *Financial Modeling and Valuation*.
- ICAEW's *Spreadsheet competency framework*: <https://www.icaew.com/technical/technology/excel/spreadsheet-competency-framework>
