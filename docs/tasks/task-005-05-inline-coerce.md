# Task 005.05: `inline.py` (F5) + `coerce.py` (F6) — strip + numeric/ISO-date

## Use Case Connection
- UC-1 (HAPPY PATH) — cell-value preparation (strip inline markdown → coerce types).
- R5 (all sub-features of inline strip).
- R6 (numeric + ISO-date coercion).
- R9.b (§11.2 MultiMarkdown / PHP-Markdown-Extra `[Caption]` rendered as literal text).
- R9.c (§11.3 `<br>` produces literal `\n`, no `wrap_text=True`).
- R9.d (§11.4 no rich-text Runs).

## Task Goal

Land two small modules together (TASK §6 / PLAN combined-task rationale):
F5 inline-strip (≤ 100 LOC) is consumed by F6 coerce (per-cell strip-then-coerce
flow), and they share a single test-class boundary (`TestInlineStrip` + `TestCoerce`
in `test_md_tables2xlsx.py`).

After this task, the following E2E cases turn GREEN:

- `T-coerce-leading-zero` — column with `"007"`/`"042"` values stays text (number_format=`"@"`).
- `T-coerce-iso-date` — column with ISO-date strings → Excel date cells.

…assuming 005.06 (parser) and 005.08 (writer) land later — the unit tests for
F5/F6 are exercisable today.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/inline.py`

- Fill `strip_inline_markdown(text: str) -> str`:
  - Decode HTML entities first (`html.unescape`).
  - Replace `<br>` / `<br/>` / `<br />` → `\n` (case-insensitive regex).
  - Strip `**X**`, `__X__` → `X` (non-greedy regex; matches across word boundaries).
  - Strip `*X*`, `_X_` → `X` (with care to NOT match inside identifiers like `var_name`).
  - Strip `` `X` `` → `X`.
  - Strip `[text](url)` → `text` (link target dropped; no Excel hyperlink in v1).
  - Strip `~~X~~` → `X`.
  - Strip remaining inline HTML tags (`<span class="…">X</span>` → `X`, `<em>X</em>` → `X`, etc.) via `re.sub(r"<[^>]+>", "", text)` LAST so already-handled `<br>` and entities are gone.
- Helper: `_decode_html_entities(text: str) -> str` — thin wrapper for `html.unescape` (the wrapping makes the test surface stable if future v2 needs custom entity handling).

#### File: `skills/xlsx/scripts/md_tables2xlsx/coerce.py`

- Fill `coerce_column(values: list[str], opts: CoerceOptions) -> list[object]`:
  - If `not opts.coerce` → return `[v if v else None for v in values]` (text-only; cell formatting locked to `"@"` in writer.py).
  - Strip whitespace per value first (`v = v.strip()`).
  - If `_has_leading_zero(values)` → column stays text (mirror csv2xlsx); return `[v if v else None for v in values]`. **Gate (ARCH m10): leading-zero gate is checked FIRST; per-cell coercion runs only if the column-level gate is open.**
  - Otherwise per-cell:
    - Try `_coerce_cell_numeric(v)` (regex pre-filter `^-?\d+(?:[.,]\d+)?$`, comma→dot normalise).
    - Else try `_coerce_cell_date(v)` (strict regex pre-filter `^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?)?$` BEFORE dateutil; dateutil only resolves the pre-filtered match).
    - Else `v` (string).
    - Empty string `""` → `None`.

**Helpers:**

- `_coerce_cell_numeric(v: str) -> int | float | None`: re-match, replace `,` → `.`, `int(v)` if no `.` else `float(v)`. Return `None` on no match.
- `_coerce_cell_date(v: str) -> datetime.date | datetime.datetime | None`:
  - Strict regex pre-filter (above).
  - `python_dateutil.parser.isoparse(v)` (strict ISO-8601; raises if not ISO).
  - If parsed result has `tzinfo is not None` → call `_handle_aware_tz` → return UTC-naive datetime.
  - If the original string had no `T` (pure date `YYYY-MM-DD`) → return `datetime.date` not datetime.
- `_handle_aware_tz(dt: datetime.datetime) -> datetime.datetime`: `dt.astimezone(timezone.utc).replace(tzinfo=None)`.
- `_has_leading_zero(values: list[str]) -> bool`: csv2xlsx parity — `non_empty[0].startswith("0") and len(non_empty[0]) > 1 and non_empty[0][1] not in ".,"`. (Single-value check on the first non-empty value, NOT all-values check — matches csv2xlsx:61 logic.)

**Dataclass:**

```python
@dataclass(frozen=True)
class CoerceOptions:
    coerce: bool = True
    encoding: str = "utf-8"
```

### Component Integration

`tables.py` (005.06) will call `strip_inline_markdown` on header
strings and per-cell raw text. `naming.py` (005.07) will call
`strip_inline_markdown` on heading text. `writer.py` (005.08) will
call `coerce_column` on each column AFTER parsing. No circular deps.

## Test Cases

### End-to-end Tests

- (None turn green this task — writer + orchestrator are still stubs.)

### Unit Tests

**TestInlineStrip:**

1. **TC-UNIT-01 (test_strip_bold):** `strip_inline_markdown("**hello**")` == `"hello"`.
2. **TC-UNIT-02 (test_strip_italic_underscore):** `strip_inline_markdown("_world_")` == `"world"`. Edge: `var_name` stays `var_name` (underscore inside identifier NOT stripped).
3. **TC-UNIT-03 (test_strip_code_span):** `strip_inline_markdown("` `code` `")` == `"code"`.
4. **TC-UNIT-04 (test_strip_link):** `strip_inline_markdown("[text](http://x)")` == `"text"`.
5. **TC-UNIT-05 (test_strip_strikethrough):** `strip_inline_markdown("~~gone~~")` == `"gone"`.
6. **TC-UNIT-06 (test_br_to_newline):** `strip_inline_markdown("line1<br>line2")` == `"line1\nline2"` (**R9.c lock** [plan-review M1 fix] — literal `\n`, not `wrap_text=True`).
7. **TC-UNIT-07 (test_html_entity_decode):** `strip_inline_markdown("a &amp; b &lt; c")` == `"a & b < c"`.
8. **TC-UNIT-08 (test_strip_mixed_inline):** `strip_inline_markdown("**bold** _italic_ `code` [link](url)")` == `"bold italic code link"`.
9. **TC-UNIT-09 (test_strip_html_span):** `strip_inline_markdown('<span class="hl">X</span>')` == `"X"`.
10. **TC-UNIT-10 (test_strip_idempotent):** `strip(strip(text)) == strip(text)` for fixture strings.

**TestCoerce:**

1. **TC-UNIT-11 (test_coerce_int):** `coerce_column(["1", "2", "3"], CoerceOptions())` == `[1, 2, 3]`.
2. **TC-UNIT-12 (test_coerce_float_comma):** `coerce_column(["1,5", "2,7"], CoerceOptions())` == `[1.5, 2.7]`.
3. **TC-UNIT-13 (test_coerce_leading_zero_keeps_text):** `coerce_column(["007", "042", "0123"], CoerceOptions())` == `["007", "042", "0123"]`. (csv2xlsx parity.)
4. **TC-UNIT-14 (test_coerce_iso_date):** `coerce_column(["2026-05-11"], CoerceOptions())[0]` == `datetime.date(2026, 5, 11)`.
5. **TC-UNIT-15 (test_coerce_iso_datetime):** `coerce_column(["2026-05-11T14:30:00"], CoerceOptions())[0]` == `datetime.datetime(2026, 5, 11, 14, 30, 0)` (tz-naive).
6. **TC-UNIT-16 (test_coerce_iso_datetime_aware_to_utc_naive):** `coerce_column(["2026-05-11T14:30:00+02:00"], CoerceOptions())[0]` == `datetime.datetime(2026, 5, 11, 12, 30, 0)` (converted UTC, tz-stripped). D7 default-mode (no `--strict-dates` in v1).
7. **TC-UNIT-17 (test_coerce_no_coerce_flag_keeps_text):** `coerce_column(["1", "2026-05-11"], CoerceOptions(coerce=False))` == `["1", "2026-05-11"]`.
8. **TC-UNIT-18 (test_coerce_empty_string_to_None):** `coerce_column(["", "1"], CoerceOptions())` == `[None, 1]`.
9. **TC-UNIT-19 (test_coerce_lenient_date_string_rejected):** `coerce_column(["May 11"], CoerceOptions())` == `["May 11"]` (strict regex pre-filter rejects; dateutil's lenient parse NOT applied).
10. **TC-UNIT-20 (test_coerce_mixed_numeric_with_string_keeps_text):** `coerce_column(["1", "abc", "3"], CoerceOptions())` — first column-level numeric-only check fails (one value isn't numeric) → whole column stays text → `["1", "abc", "3"]`.
11. **TC-UNIT-21 (TestHonestScopeLocks::test_no_rich_text_runs):** `strip_inline_markdown("**bold**")` returns plain `str`, NOT an openpyxl `Run` instance — assert `type(...) is str` (R9.d lock).
12. **TC-UNIT-22 (TestHonestScopeLocks::test_multimarkdown_caption_literal):** A cell value `"[Caption: Q1 Results]"` (MultiMarkdown / PHP-Markdown-Extra table-caption syntax) passes through `strip_inline_markdown` AND `coerce_column` unchanged as plain text `"[Caption: Q1 Results]"` — no caption-metadata side channel (no separate column, no `Worksheet.title` mutation invoked from coerce). **R9.b lock** (plan-review M1 fix — §11.2 MultiMarkdown extensions rendered as literal text in cells).

### Regression Tests

- Existing tests pass.

## Acceptance Criteria

- [ ] All 22 unit tests above pass.
- [ ] `strip_inline_markdown` is idempotent.
- [ ] `coerce_column` `_has_leading_zero` gate runs BEFORE per-cell coercion (ARCH m10).
- [ ] `_coerce_cell_date` strict-regex pre-filter rejects `"May 11"`-class lenient strings.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

The combined-task structure is justified because (a) F5 is consumed
by F6 in the same per-cell pipeline, (b) both modules are small
(F5 ≤ 100, F6 ≤ 150), and (c) splitting them creates an artificial
test-coverage boundary that slows the chain. If `inline.py` lands at
< 50 LOC, the Developer MAY collapse it into a private section of
**`tables.py`** per ARCH m3 (plan-review m2 fix — ARCH m3 specifies
`tables.py` as the collapse destination, NOT `coerce.py`; the
F5/F6/F7 import paths get updated accordingly) — but unit tests stay
as `TestInlineStrip` + `TestCoerce` separate classes either way.
