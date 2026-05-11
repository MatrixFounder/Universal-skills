# JSON ↔ XLSX Round-Trip Contract (xlsx-2 ↔ xlsx-8)

> **Status:** **FROZEN** as of xlsx-2 v1 merge (Task 004).
> **Owners:** xlsx-2 (`json2xlsx.py`) — producer of `.xlsx` from JSON.
> xlsx-8 (`xlsx2json.py`, future) — producer of JSON from `.xlsx`.
> **Goal:** unambiguous, lossless-as-defined round-trip between
> JSON shape and `.xlsx` workbook structure for the agent-style
> "read my spreadsheet → edit JSON → write it back" loop.
>
> xlsx-8's future implementation **MUST** consume this spec
> unchanged. If xlsx-8 discovery work surfaces a requirement that
> forces a revision, both skills update synchronously in the same
> commit (see ARCH §3.2 m4 lock).

---

## §1 Scope

This document is the **single source of truth** for the JSON shape
contract shared between xlsx-2 and xlsx-8. Both implementations
parse / emit JSON according to the same rules so a clean round-
trip is possible.

In scope:
- Three accepted input shapes (single-sheet array, multi-sheet
  dict, JSONL stream).
- Sheet-name key handling (no normalisation).
- Cell-value typing (native JSON types + ISO-8601 date strings).
- Null-cell representation in xlsx-8 output (the read-back path).
- Datetime serialisation in xlsx-8 output.
- Formula resolution in xlsx-8 output.

Out of scope (xlsx-8 v1; tracked separately):
- `--header-row N>1` for non-standard layouts.
- Cell-level formatting round-trip (fonts, colors, alignment, borders).
- Charts, data-validation, named ranges, conditional formatting.
- Comment round-trip (owned by xlsx-6).

---

## §2 Three accepted input shapes

xlsx-2 auto-detects via two deterministic signals:

1. **`.jsonl` file extension** → JSONL parser (line-by-line).
2. **Otherwise, JSON root token after parse:**
   - `list` → single-sheet "array-of-objects" (§2.1).
   - `dict` where every value is a list → "multi-sheet dict" (§2.2).
   - Anything else → `UnsupportedJsonShape` exit 2.

### §2.1 Array-of-objects (single sheet)

```json
[
  {"Name": "Alice", "Age": 30},
  {"Name": "Bob",   "Age": 25}
]
```

- Each `dict` is one data row.
- Headers = ordered union of all dict keys (first-seen wins; see §4).
- Default sheet name: `"Sheet1"`. Overridable via `--sheet NAME`.

### §2.2 Multi-sheet dict

```json
{
  "Employees": [
    {"Name": "Alice", "Salary": 100000}
  ],
  "Departments": [
    {"Dept": "Eng", "Head": "Alice"}
  ]
}
```

- Each top-level key is a sheet name (see §3 for rules).
- Each top-level value is a list of row dicts.
- Multi-sheet input **ignores `--sheet`** with a stderr warning.
- xlsx-8's `--sheet all` output **MUST** emit this shape.

### §2.3 JSONL (one JSON object per line)

```
{"event":"login","user":"alice"}
{"event":"logout","user":"alice"}
```

- Each non-empty line is one row dict.
- Blank lines are tolerated and skipped.
- Single sheet only (use `--sheet NAME` to override default `Sheet1`).
- A line that parses to anything other than `dict` → exit 2
  `UnsupportedJsonShape` with the offending line number.

---

## §3 Sheet-name key naming (locked)

Multi-sheet root keys are **verbatim Excel sheet names** — no
normalisation, no case-folding, no truncation.

If a key violates Excel's sheet-name rules, the producer (xlsx-2)
**MUST** hard-fail with `InvalidSheetName` (exit 2). Rules:

| Rule | Reject when |
| :--- | :--- |
| Length | `len(name) > 31` |
| Forbidden chars | any of `[ ] : * ? / \` |
| Reserved | case-insensitive match `"history"` |
| Empty | `name == ""` |

Auto-sanitization (truncate / replace bad chars) is **out of scope
v1** — silently mutating user-supplied sheet keys is more dangerous
than a clear error. A `--sanitize-sheet-names` flag is a v2
candidate.

xlsx-8 **MUST** preserve sheet names verbatim when emitting JSON
output; if the workbook contains a sheet whose name doesn't satisfy
xlsx-2's input rules, that's a contract violation on the workbook
side (Excel will have accepted it, but the round-trip cannot
proceed without sanitization).

---

## §4 Cell-value typing (locked)

### §4.1 Native JSON types

| JSON value | xlsx-2 output cell | xlsx-8 output JSON value |
| :--- | :--- | :--- |
| `int`        | numeric cell (`data_type='n'`)              | `int` (same value) |
| `float`      | numeric cell (`data_type='n'`)              | `float` (same value) |
| `bool`       | boolean cell (`data_type='b'`)              | `bool` (same value) |
| `null`       | empty cell (no value set)                   | `null` (see §5) |
| `str` (non-date) | string cell (`data_type='s'`)           | `str` (same value) |

**Critical:** Python `bool` is a subclass of `int`. xlsx-2 classifies
`bool` BEFORE `int` (locked in `coerce.py:coerce_cell`); xlsx-8 MUST
do the same on the read-back path (emit `true`/`false`, not `1`/`0`).

### §4.2 ISO-8601 date strings

xlsx-2 auto-coerces strings matching these forms to date / datetime
cells when `--no-date-coerce` is **not** set (default):

| Form | Example | xlsx-2 output | Excel `number_format` |
| :--- | :--- | :--- | :--- |
| Date-only          | `"2024-01-15"`                      | `date(2024,1,15)`     | `"YYYY-MM-DD"` |
| Naive datetime     | `"2024-01-15T09:00:00"`             | `datetime(...)`        | `"YYYY-MM-DD HH:MM:SS"` |
| Naive datetime (space) | `"2024-01-15 09:00:00"`         | `datetime(...)`        | `"YYYY-MM-DD HH:MM:SS"` |
| Aware datetime     | `"2024-01-15T09:00:00Z"`            | UTC-naive `datetime` (offset dropped)  | `"YYYY-MM-DD HH:MM:SS"` |
| Aware w/ offset    | `"2024-01-15T09:00:00+02:00"`       | UTC-naive (07:00 stored)               | `"YYYY-MM-DD HH:MM:SS"` |

Under `--strict-dates`:
- Aware datetime → exit 2 `TimezoneNotSupported`.
- String matching `YYYY-` prefix but not the regexes above → exit 2
  `InvalidDateString` (the conservative "looks like a date attempt"
  heuristic; arbitrary plain strings still pass through silently).

### §4.3 Mixed-type columns

Each cell is typed individually. No column-wide coercion. A column
with `Age: 30` in row 1 and `Age: "n/a"` in row 2 produces a numeric
cell and a string cell respectively — Excel handles the mix natively.

---

## §5 Null-cell representation in xlsx-8 OUTPUT

xlsx-8 **MUST** emit `null` for empty cells (not omit the key).

Rationale: omitting the key would lose column-presence information.
A downstream consumer that does `df.columns` after round-trip
would see different columns from row to row, breaking schema-aware
pipelines.

Example:

| Workbook |   | xlsx-8 emits | xlsx-8 must NOT emit |
| :--- | :--- | :--- | :--- |
| A2="Alice", B2=(empty) | | `{"Name":"Alice","Age":null}` | `{"Name":"Alice"}` |

xlsx-2's read-back path (when it consumes xlsx-8 output) treats
both `null` and missing-key as empty cells (`R3.d`), so the round-
trip from `null` → empty cell → `null` is preserved.

---

## §6 Datetime serialisation in xlsx-8 OUTPUT

xlsx-8 **MUST** emit datetime cells as ISO-8601 strings:

| Cell type | xlsx-8 output |
| :--- | :--- |
| Date cell  | `"YYYY-MM-DD"`             (10 chars) |
| Datetime cell | `"YYYY-MM-DDTHH:MM:SS"` (preferred) OR `"YYYY-MM-DD HH:MM:SS"` (both accepted by xlsx-2) |

**Excel does not store timezone.** xlsx-8 **MUST NOT** emit a
timezone offset in JSON output. All datetimes are treated as naive
on the JSON side.

If the original workbook stored a datetime via xlsx-2's UTC-naive
coercion (R4.e default), the round-trip silently drops the
original offset. This is documented honest scope (§11.1 in
xlsx-2's TASK).

Excel-serial-number form (`44935.375`) is **NOT** emitted by
xlsx-8. Always ISO-8601 strings.

---

## §7 `--header-row N>1` (xlsx-8 future feature)

Out of scope for xlsx-8 v1. The current contract assumes the
**first row** of each sheet is the header.

If xlsx-8 later adds `--header-row N` to handle workbooks where the
header is not on row 1, this section will be revised in lockstep
with the implementation.

---

## §8 Formula resolution in xlsx-8 OUTPUT

xlsx-8 **MUST** emit **cached values** by default — i.e., the
result openpyxl reads as `cell.value` when the workbook was last
saved with calculated values (the `<v>` element in the OOXML cell).

| Cell content | xlsx-8 emits | Notes |
| :--- | :--- | :--- |
| Static value           | the value                       | — |
| Formula with cached `v`| the cached `v` value            | — |
| Formula without cached `v` | `null`                       | (stale workbook; warn the user) |

Opt-in: `--include-formulas` flag (xlsx-8's own surface) would
emit `{"value": <cached>, "formula": "=A1+B1"}`-shaped objects.
NOT part of xlsx-2's input contract — xlsx-2 ignores such
extensions if encountered. This is a forward-compatibility hook
only.

Cross-reference: xlsx-6 (`xlsx_add_comment`) and xlsx-7
(`xlsx_check_rules`) operate the same way — cached values are the
default; formula-recompute is owned by `xlsx_recalc.py`.

---

## §9 Honest scope (round-trip limitations)

These limitations are **deliberately accepted v1**. Future revisions
of this spec must list any new limitation here in the same commit.

- **Cell-level formatting is NOT round-trippable.** xlsx-2 always
  produces a fresh styled workbook with csv2xlsx-style headers
  (bold + light-grey fill + centre alignment + auto-filter + freeze
  pane). User-authored styling in an original workbook is lost on
  round-trip. If preservation is required, use xlsx-6 / xlsx-7
  surfaces which do not modify cell values.
- **Charts / data-validation / named ranges / conditional
  formatting are NOT round-trippable** by this pair. xlsx-4 covers
  some preservation for a different code path.
- **Merged cells**: xlsx-8 emits the anchor cell's value and `null`
  for the merged tail; xlsx-2 writes the values back into
  individual cells with no re-merge. Round-trip un-merges the range.
- **Comments**: xlsx-8 does NOT emit cell comments to JSON. The
  comment surface belongs to xlsx-6.
- **Duplicate top-level JSON keys**: Python's stdlib `json.loads()`
  silently keeps the last value per RFC 8259 §4. xlsx-2 v1 does
  NOT detect this; if you author `{"Sheet1": [...], "Sheet1": [...]}`
  by hand, the second wins. Locked in TASK §11.5.
- **Aware datetimes under default mode**: silently converted to
  UTC-naive (R4.e). The offset is lost. Under `--strict-dates`,
  aware datetimes are a hard fail (`TimezoneNotSupported`).
- **Leading `=` in JSON string values**: passes through to Excel
  as-is. Excel may render as a formula or as text per its own
  heuristic. xlsx-2 does NOT defuse with `'` (csv2xlsx parity;
  v2 joint fix tracked as `xlsx-2a / csv2xlsx-1`).

---

## §10 Test contract

Both xlsx-2 and xlsx-8 **MUST** keep this fixture in sync:

`skills/xlsx/scripts/tests/golden/json2xlsx_xlsx8_shape.json`

The synthetic round-trip test (`T-roundtrip-xlsx8-synthetic`) is
owned by xlsx-2 v1. The live round-trip test
(`test_live_roundtrip` in `tests/test_json2xlsx.py`) is gated by
`@unittest.skipUnless(_xlsx2json_available(), …)` and activates
automatically when `import xlsx2json` succeeds — i.e., in the
xlsx-8 merge commit. The xlsx-8 merge commit MUST:

1. Implement `xlsx2json.py` against this spec.
2. Fill in the `test_live_roundtrip` body to invoke
   `xlsx2json(original) → JSON → json2xlsx → assert structural
   equivalence`.
3. NOT modify any xlsx-2 source code.

If xlsx-8 discovery work requires a revision to this spec, BOTH
files must update synchronously in the same commit; otherwise
`test_live_roundtrip` breaks until parity is restored.
