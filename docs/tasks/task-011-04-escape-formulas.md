# Task 011.04 — [R4] `--escape-formulas {off,quote,strip}` (CSV-only)

## Use Case Connection
- UC-04: `--escape-formulas` defangs CSV injection (`xlsx-8a-04`)

## Task Goal
Add `--escape-formulas {off,quote,strip}` CLI flag (default `off`
for backward compatibility) that defangs the Excel "CSV Injection"
attack vector (ARCH §14.7.2). Cell values whose stringified form
begins with one of the OWASP-canonical six sentinels (`=`/`+`/`-`/
`@`/`\t`/`\r`) currently flow verbatim into CSV output and execute
as DDE formulas on Excel double-click.

- `off` (default) — passthrough, byte-identical to xlsx-8 output.
- `quote` — prepend `'` to defang (Excel renders as literal text).
- `strip` — replace cell with empty string `""`.

The flag is **CSV-only**; passing it to `xlsx2json.py` emits a
stderr warning (mirrors the `--delimiter` / `--encoding utf-8-sig`
on-JSON warnings already in `cli.py`).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Module-level constants (top of file):**
- `_ESCAPE_FORMULAS_MODES = ("off", "quote", "strip")`
- `_FORMULA_SENTINELS = ("=", "+", "-", "@", "\t", "\r")` —
  OWASP-canonical six (per D-A13 / TASK §6.3 assumption).

**Function `build_parser`:**
- Add new argparse argument:
  ```python
  parser.add_argument(
      "--escape-formulas",
      dest="escape_formulas",
      choices=_ESCAPE_FORMULAS_MODES,
      default="off",
      help=(
          "Defang CSV cells starting with =/+/-/@/<TAB>/<CR> "
          "(OWASP CSV Injection). 'off' (default) passes through "
          "verbatim — backward-compatible. 'quote' prepends `'` "
          "so Excel renders as literal text. 'strip' replaces "
          "with empty string. CSV-only: passing to xlsx2json.py "
          "emits a stderr warning. See also --encoding utf-8-sig "
          "(both flags address 'what happens when Excel "
          "double-clicks the CSV')."
      ),
  )
  ```

**Function `_validate_flag_combo`:**
- Add new branch: if `effective_format == "json"` AND
  `args.escape_formulas != "off"`, emit a stderr warning (mirrors
  the existing `--delimiter`-on-JSON pattern at line ~396):
  ```python
  if effective_format == "json" and args.escape_formulas != "off":
      print(
          "warning: --escape-formulas has no effect on JSON output "
          "(CSV-only flag — JSON has its own escape contract).",
          file=sys.stderr,
      )
  ```

**Function `_dispatch_to_emit`:**
- Pass `escape_formulas=args.escape_formulas` to `emit_csv.emit_csv`
  call (extends the existing call site at line ~698).

**Update `--encoding utf-8-sig` help text:**
- Append to the existing help string in `_validate_flag_combo`
  description: " See also `--escape-formulas` for the related
  Excel-double-click CSV-injection mitigation."

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`

**Function `emit_csv` signature:**
- Add new keyword parameter `escape_formulas: str = "off"` (extends
  the existing signature at line ~34).
- Thread through to `_emit_single_region` and `_emit_multi_region`.

**Function `_write_region_csv`:**
- Add new keyword parameter `escape_formulas: str = "off"`.
- Inside the row-emit loop (after the hyperlink wrap at line
  ~212), apply the transform:
  ```python
  if escape_formulas != "off":
      out_row = [
          _apply_formula_escape(v, escape_formulas)
          for v in out_row
      ]
  ```

**New helper `_apply_formula_escape`:**
- Module-level helper:
  ```python
  def _apply_formula_escape(value: Any, mode: str) -> Any:
      """Defang CSV-injection-prone cell values per OWASP recipe.

      mode='off': passthrough (caller filters via the outer
                  branch, this is defence-in-depth).
      mode='quote': prepend `'` if value's str form begins with
                    one of the 6 sentinels.
      mode='strip': replace with "" if sentinel-prefixed.

      Non-string and numeric values are untouched (numeric cells
      never start with a sentinel char).
      """
      if mode == "off" or value is None:
          return value
      s = str(value) if not isinstance(value, str) else value
      if not s or s[0] not in _FORMULA_SENTINELS:
          return value
      if mode == "quote":
          return "'" + s
      # mode == "strip"
      return ""
  ```
- Import `_FORMULA_SENTINELS` from `cli.py` OR (preferred) define
  it locally in `emit_csv.py` to keep the dependency direction
  clean (cli.py imports emit_csv, not the other way round).

### Component Integration

- `emit_csv` → `_write_region_csv` is the only emit path that
  touches cell values for CSV output. The transform runs once per
  cell, after the hyperlink-wrap step (so a hyperlink cell with
  text `"=cmd"` and url `"https://..."` becomes
  `'[' + escape_formulas('=cmd', 'quote') + '](https://...)'` =
  `[=cmd](https://...)` — the `[` prefix means the cell no longer
  begins with `=`, so the markdown-link wrapper naturally defangs
  the embedded `=`. Locked behaviour, asserted by a regression
  test in TC-E2E-07).

## Test Cases

Hosted in `xlsx2csv2json/tests/test_hardening.py` (extends the file
created in 011-03).

### End-to-end Tests (15 total per TASK R4 sub-feature (g))

1. **TC-E2E-01:** `test_escape_off_no_transform`
   - Fixture: 6 cells, one per sentinel, with `=cmd`, `+1`, `-1`,
     `@SUM(A1)`, `\tHTML`, `\rOK`.
   - Invocation: `--escape-formulas off` (default).
   - Expected: CSV output byte-identical to xlsx-8 baseline (all
     6 sentinels present verbatim).

2-7. **TC-E2E-02..07:** `test_escape_quote_prefixes_<char>` for
   each sentinel.
   - Fixture: one cell with `<sentinel> + payload`.
   - Invocation: `--escape-formulas quote`.
   - Expected: cell value becomes `' + <sentinel> + payload` (e.g.
     `=cmd` → `'=cmd`).

8-13. **TC-E2E-08..13:** `test_escape_strip_drops_<char>` for each
   sentinel.
   - Fixture: same per-sentinel cells.
   - Invocation: `--escape-formulas strip`.
   - Expected: each cell becomes empty string `""`.

14. **TC-E2E-14:** `test_escape_json_warning_only`
   - Invocation: `python3 xlsx2json.py book.xlsx --escape-formulas
     quote --output -`.
   - Expected: stderr contains the no-effect warning; JSON output
     identical to no-flag invocation.

15. **TC-E2E-15:** `test_dde_payload_e2e`
   - Fixture: a single cell with literal `=cmd|'/C calc'!A1`.
   - Invocation: `--escape-formulas quote`.
   - Expected: CSV row contains `'=cmd|'/C calc'!A1` (defanged).
     Re-opening the CSV in LibreOffice Calc would render the cell
     as text, not a formula (manual verification documented in
     the test docstring).

### Unit Tests

1. **TC-UNIT-01:** `test_apply_formula_escape_off`
   - For each sentinel and a few non-sentinel values, mode='off'
     returns the value unchanged.

2. **TC-UNIT-02:** `test_apply_formula_escape_quote_each_sentinel`
   - 6 parametrised cases.

3. **TC-UNIT-03:** `test_apply_formula_escape_quote_non_sentinel`
   - Values like `"42"`, `"hello"`, `42` (int), `None` are
     unchanged under `quote`.

### Regression Tests
- All existing `emit_csv` tests in
  `xlsx2csv2json/tests/test_emit_csv.py` continue to pass
  (default `off` mode is byte-identical to xlsx-8).
- The existing `xlsx-2 round-trip` test
  (`xlsx2csv2json/tests/test_e2e.py::test_roundtrip_xlsx_2`) MUST
  pass under `--escape-formulas off` (default) — `quote`/`strip`
  modes are NOT round-trip-safe and that's documented.
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `python3 xlsx2csv.py --help | grep -F "escape-formulas"` shows
  the new flag with all 3 modes.
- [ ] All 15 E2E + 3 unit tests green.
- [ ] Existing `test_emit_csv.py` 100% green.
- [ ] Existing round-trip test green under default `off` mode.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `validate_skill.py skills/xlsx` exit 0.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Add `--escape-formulas` argparse + JSON-shim warning + help-text
   cross-ref to `--encoding utf-8-sig`.
2. Add `_FORMULA_SENTINELS` constant + `_apply_formula_escape`
   helper with **stub body** `return value` (passthrough — does
   nothing).
3. Wire `_write_region_csv` to call the stub.
4. Write all 15 E2E + 3 unit tests — TC-E2E-02..13 + TC-E2E-15
   FAIL Red; TC-E2E-01 and TC-E2E-14 pass already.

### Pass 2 — Logic + Green E2E
1. Replace `_apply_formula_escape` stub body with real
   transform logic.
2. Re-run all tests — Green.

## Notes
- Sentinel set is OWASP-canonical six (D-A13). Unicode lookalikes
  (`＝` U+FF1D, `＋` U+FF0B) are explicitly out of scope per TASK
  §1.4 (h) and ARCH §15.4 §14.7.1 row.
- Hyperlink + escape-formulas interaction (TC-E2E-07-style edge
  case): hyperlinks emit as `[text](url)` — the leading `[` is not
  a sentinel, so the markdown wrapper "naturally defangs" any
  sentinel-prefixed text inside. Test documents this behaviour.
- Effort: M (~3 hours). Diff size: ~70 LOC across 2 files + ~250
  LOC test file.
