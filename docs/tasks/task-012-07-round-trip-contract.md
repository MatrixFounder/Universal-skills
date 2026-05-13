# Task 012-07 [INTEGRATION]: Round-trip contract — `xlsx-md-shapes.md` + xlsx-3 live round-trip flip

> **Predecessor:** 012-06.
> **RTM:** [R25] (round-trip contract document), [R26] (xlsx-3
> live round-trip activation; cell-content byte-identity per D9).
> **UCs:** UC-12 (cell-newline `<br>` round-trip).

## Use Case Connection

- UC-12 — cell newline `\n` → `<br>` in xlsx-9 emit; xlsx-3 R9.c
  consumes `<br>` back to `\n`; cell content byte-identical after
  the full round-trip `xlsx2md → md_tables2xlsx → xlsx2md`.

## Task Goal

Two integration deliverables:

1. **`skills/xlsx/references/xlsx-md-shapes.md`** — new reference
   document defining the frozen xlsx-9 ↔ xlsx-3 round-trip
   contract (mirrors `references/json-shapes.md` for xlsx-2 ↔
   xlsx-8). 8 sections per ARCH §3.2 C6.

2. **`md_tables2xlsx/tests/` test gate flip** — activate
   `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md`. The test
   gate uses `@unittest.skipUnless(xlsx2md_available(), ...)`
   where `xlsx2md_available()` is a tiny helper that tries
   `import xlsx2md` and returns True iff the import succeeds AND
   the package is wired (not just stub). After 012-06, the import
   succeeds and `convert_xlsx_to_md` does real work; the gate
   flips to live.

Note: existing `md_tables2xlsx` test code does NOT yet have a
`TestRoundTripXlsx9` class or the `xlsx2md_available()` helper.
This task ADDS them (test-side activation; no production-code
changes in `md_tables2xlsx/`).

## Changes Description

### New Files

#### `skills/xlsx/references/xlsx-md-shapes.md`

Round-trip contract document. Structure mirrors
`references/json-shapes.md`:

- **§1 Scope** — H2-per-sheet emission shape; H3-per-table
  emission shape; GFM and HTML table emit shapes; hybrid mode
  per-table format selection (cross-link to ARCH §2.1 F3).

- **§2 GFM shape** — pipe-table format with sub-cases:
  - Single-row header (common case): `| h1 | h2 |\n|---|---|\n|
    v1 | v2 |`.
  - Multi-row header degraded with ` › ` flatten + warning.
  - Synthetic header for `headerRowCount=0`: visible `| col_1 |
    col_2 | ... |` row + separator row (per D13 + §1.4 (i)).
  - Pipe `\|` escape (R10).
  - Newline `<br>` (R16).
  - Hyperlink `[text](url)` (R10).

- **§3 HTML shape** — `<table>` block with `<thead>` + `<tbody>`:
  - Multi-row `<thead>` reconstruction by splitting ` › `
    separators (D-A11).
  - `colspan` / `rowspan` on merge anchors; child cells
    suppressed.
  - `data-formula` attribute when `--include-formulas` active.
  - `class="stale-cache"` for formula cells with no cached
    value.
  - `<a href="...">...</a>` hyperlinks; `html.escape(text)` for
    cell content; `html.escape(url, quote=True)` for href.
  - Synthetic `<thead>` for `headerRowCount=0` (D13).

- **§4 Hybrid mode** — per-table promotion rules:
  - Rule 1: body merges → HTML.
  - Rule 2: multi-row header → HTML.
  - Rule 3: `--include-formulas` + formula present → HTML.
  - Rule 4: `headerRowCount=0` → HTML (D13).
  - Otherwise GFM.

- **§5 Inline contract** — applies to BOTH GFM and HTML:
  - Cell newline `\n` → `<br>` (lossless on xlsx-3 round-trip
    per R9.c).
  - Pipe `|` → `\|` (GFM) / `&#124;` (HTML).
  - Empty value `""` → empty cell (`||` in GFM, `<td></td>` in
    HTML).
  - Hyperlink scheme allowlist applied to all hyperlink emissions
    (default `{http, https, mailto}`).

- **§6 Sheet-name asymmetry** (D9 lock):
  - xlsx-9 emits sheet names VERBATIM in `## H2` headings.
  - xlsx-3 `naming.py` may sanitise on write-back
    (`History` → `History_`, >31 UTF-16 chars truncated, etc.).
  - Asymmetric: a workbook with sheet `History` round-tripped
    through xlsx-9 → xlsx-3 yields `## History` on the first
    pass and `## History_` on the second pass (via xlsx-3's
    write-back sanitisation).
  - **This is EXPECTED**, NOT a regression. Round-trip cell
    content byte-equality is asserted; round-trip sheet-name
    byte-equality is NOT.

- **§7 Round-trip limitations (honest scope)** — bullet list
  per TASK §1.4:
  - (a) Rich-text spans collapse to plain-text concat.
  - (b) Cell styles dropped.
  - (c) Comments dropped (v2 sidecar).
  - (d) Charts / images / shapes dropped.
  - (e) Pivot tables → static cached values.
  - (f) Data validation dropdowns dropped.
  - (g) Formula without cached value → empty cell or
    `data-formula` attribute (HTML only).
  - (h) Shared / array formulas → cached value only.
  - (i) `headerRowCount=0` → synthetic `col_1..col_N` headers
    visible in `<thead>`.
  - (j) Diagonal borders / sparklines / camera objects dropped.
  - Merges un-merge on xlsx-3 write-back (xlsx-3 v1 does not
    re-merge HTML colspan/rowspan).

- **§8 Live round-trip test activation** — gate mechanism:
  - `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md` in
    `skills/xlsx/scripts/tests/test_md_tables2xlsx.py` is guarded
    by `@unittest.skipUnless(xlsx2md_available(), ...)`.
  - `xlsx2md_available()` helper tries `import xlsx2md` and
    invokes `convert_xlsx_to_md` on a tiny fixture; returns True
    iff the call succeeds (i.e. package is wired, not just stub).
  - After 012-06 / 012-07 merge, the import succeeds and the
    test flips to live.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_md_tables2xlsx.py`

This task ADDS a new test class `TestRoundTripXlsx9` to the
existing test file. The xlsx-9 round-trip test was not
pre-stubbed in `md_tables2xlsx` (unlike xlsx-2's
`TestRoundTripXlsx8::test_live_roundtrip` in `json2xlsx`).

**Add at end of file (or near existing TestRoundTrip classes):**

```text
def xlsx2md_available() -> bool:
    """Return True iff xlsx-9 (xlsx2md package) is implemented
    (not just stubbed).

    Probe:
        1. `import xlsx2md` must succeed (passes after 012-01).
        2. `convert_xlsx_to_md` on a tiny fixture must return 0
           AND produce non-empty markdown (passes after 012-06).
    """
    try:
        import xlsx2md  # noqa: F401
        from xlsx2md import convert_xlsx_to_md
    except ImportError:
        return False
    # Probe with the round-trip fixture in
    # `xlsx2md/tests/fixtures/single_cell.xlsx` (12-02 deliverable).
    fixture = Path(__file__).resolve().parents[1] / "xlsx2md/tests/fixtures/single_cell.xlsx"
    if not fixture.exists():
        return False
    try:
        out_md = tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w", encoding="utf-8"
        )
        out_md.close()
        exit_code = convert_xlsx_to_md(fixture, out_md.name)
        if exit_code != 0:
            return False
        text = Path(out_md.name).read_text(encoding="utf-8")
        return bool(text.strip())
    except Exception:
        return False
    finally:
        Path(out_md.name).unlink(missing_ok=True)


class TestRoundTripXlsx9(unittest.TestCase):
    """Live round-trip xlsx-9 ↔ xlsx-3 — content byte-identity."""

    @unittest.skipUnless(
        xlsx2md_available(),
        "xlsx2md not yet implemented (xlsx-9 / TASK 012)",
    )
    def test_live_roundtrip_xlsx_md(self) -> None:
        """xlsx → md → xlsx → md → assert cell content unchanged."""
        # Setup: a multi-cell fixture with cell content that
        # round-trips losslessly.
        from xlsx2md import convert_xlsx_to_md
        from md_tables2xlsx import convert_md_tables_to_xlsx
        fixture = Path(__file__).resolve().parents[1] / "xlsx2md/tests/fixtures/roundtrip_basic.xlsx"
        # Stage 1: xlsx → md
        with tempfile.TemporaryDirectory() as tmpdir:
            md1 = Path(tmpdir) / "first.md"
            self.assertEqual(convert_xlsx_to_md(fixture, md1), 0)
            # Stage 2: md → xlsx (via md_tables2xlsx)
            xlsx2 = Path(tmpdir) / "roundtrip.xlsx"
            self.assertEqual(
                convert_md_tables_to_xlsx(md1, xlsx2),
                0,
            )
            # Stage 3: xlsx → md (second pass)
            md2 = Path(tmpdir) / "second.md"
            self.assertEqual(convert_xlsx_to_md(xlsx2, md2), 0)
            # Assert cell-content byte-equality between stages
            # 1 and 3 (sheet-name asymmetry is documented in
            # xlsx-md-shapes.md §6 — NOT asserted).
            text1 = md1.read_text(encoding="utf-8")
            text2 = md2.read_text(encoding="utf-8")
            # Normalise sheet-name H2 lines (D9 lock — drop them
            # entirely from the comparison; only assert table body).
            table1 = _extract_table_bodies(text1)
            table2 = _extract_table_bodies(text2)
            self.assertEqual(
                table1, table2,
                "cell content drift after xlsx-9 ↔ xlsx-3 round-trip",
            )

    @unittest.skipUnless(
        xlsx2md_available(),
        "xlsx2md not yet implemented (xlsx-9 / TASK 012)",
    )
    def test_live_roundtrip_cell_newline_br(self) -> None:
        """T-cell-newline-br-roundtrip (TASK §5.1 #21)."""
        from xlsx2md import convert_xlsx_to_md
        from md_tables2xlsx import convert_md_tables_to_xlsx
        fixture = Path(__file__).resolve().parents[1] / "xlsx2md/tests/fixtures/cell_with_newline.xlsx"
        with tempfile.TemporaryDirectory() as tmpdir:
            md1 = Path(tmpdir) / "first.md"
            self.assertEqual(convert_xlsx_to_md(fixture, md1), 0)
            text = md1.read_text(encoding="utf-8")
            self.assertIn("<br>", text, "newline not converted to <br>")
            xlsx2 = Path(tmpdir) / "roundtrip.xlsx"
            self.assertEqual(
                convert_md_tables_to_xlsx(md1, xlsx2), 0,
            )
            # Open xlsx2 and assert cell A2 contains the original
            # "first line\nsecond line" content (xlsx-3 R9.c
            # converts <br> back to \n).
            import openpyxl
            wb = openpyxl.load_workbook(xlsx2)
            ws = wb[wb.sheetnames[0]]
            cell_value = ws.cell(row=2, column=1).value
            self.assertEqual(
                cell_value, "first line\nsecond line",
                "cell newline not preserved through round-trip",
            )
```

Helper function `_extract_table_bodies(text: str) -> list[str]`:

- Splits `text` into chunks per `## H2` heading; for each chunk,
  drops the H2 line; for the H3 lines, drops them too; returns
  the list of remaining table-body lines.
- This is the comparison normaliser per D9 lock — sheet names and
  table-name H3s vary across xlsx-3 sanitisation; cell content
  inside the table body MUST match.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/roundtrip_basic.xlsx`

Hand-built: 2 sheets, each with 1 header row + 3 data rows.
Mixed content: strings, integers, ISO dates, one hyperlink, no
merges, no formulas (so xlsx-3 round-trip preserves everything
losslessly).

### Component Integration

- `md_tables2xlsx/` package itself is NOT modified — only the
  test file `tests/test_md_tables2xlsx.py` (gate flip) and a new
  fixture file.
- `xlsx2md/` package is NOT modified — this is integration only.

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 21 | `T-cell-newline-br-roundtrip` | `cell_with_newline.xlsx` (012-04) | `xlsx2md(cell_with_newline.xlsx)` → md contains `<br>`; `md_tables2xlsx(md)` → xlsx; cell A2 reads `"first line\nsecond line"` byte-identical. | 0 |

### Unit Tests

In `tests/test_md_tables2xlsx.py`:

1. **TC-UNIT-01** `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md`
   — full xlsx → md → xlsx → md round-trip; cell content equal
   stages 1 and 3.
2. **TC-UNIT-02** `TestRoundTripXlsx9::test_live_roundtrip_cell_newline_br`
   — UC-12 round-trip assertion.
3. **TC-UNIT-03** `test_xlsx2md_available_returns_true_after_xlsx9_lands`
   — meta-test asserting the gate helper returns True (sanity).

### Regression Tests

- 5-line `diff -q` silent gate.
- 012-01..012-06 tests still green.
- `xlsx-md-shapes.md` exists and has ≥ 8 sections (verified by
  a shell test or by reading file structure).
- `ruff check skills/xlsx/scripts/` green (no Python code change
  in this task).
- **Critical risk check (R-2):** assert
  `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md` is NOT
  skipped. Run `python3 -m unittest skills.xlsx.scripts.tests.test_md_tables2xlsx
  -v 2>&1 | grep -c "test_live_roundtrip_xlsx_md ... ok"` — must
  print `1`, NOT `0`.

## Acceptance Criteria

- [ ] `skills/xlsx/references/xlsx-md-shapes.md` exists and has
      8 sections per ARCH §3.2 C6.
- [ ] `TestRoundTripXlsx9` class added to
      `skills/xlsx/scripts/tests/test_md_tables2xlsx.py`.
- [ ] `xlsx2md_available()` helper function added to the same
      file.
- [ ] `test_live_roundtrip_xlsx_md` passes (not skipped) when
      `xlsx2md` is implemented.
- [ ] `test_live_roundtrip_cell_newline_br` passes (T-21).
- [ ] `roundtrip_basic.xlsx` fixture added.
- [ ] No source code changes in `md_tables2xlsx/` (test-side
      activation only).
- [ ] No changes to `xlsx2md/` source modules (this is integration).
- [ ] All 012-01..012-06 tests still green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green:
      ```bash
      diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
      diff -q  skills/docx/scripts/_soffice.py      skills/xlsx/scripts/_soffice.py
      diff -q  skills/docx/scripts/_errors.py       skills/xlsx/scripts/_errors.py
      diff -q  skills/docx/scripts/preview.py       skills/xlsx/scripts/preview.py
      diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
      ```

## Notes

- **Risk R-2 (planner-layer):** The xlsx-9 round-trip test was
  NOT pre-stubbed in `md_tables2xlsx/tests/` (unlike xlsx-2's
  `TestRoundTripXlsx8` which lives in `json2xlsx`). This task
  ADDS both the helper and the test class. Explicitly asserting
  the test is NOT skipped after flip (TC-UNIT-03 meta-test).
- **D9 lock comparison normaliser:** `_extract_table_bodies`
  drops H2 / H3 lines from both sides of the comparison because
  sheet name `History` becomes `History_` after xlsx-3 write-back
  sanitisation. Only the TABLE BODIES are byte-equal. The
  contract doc §6 documents this explicitly.
- **Cross-reference:** every section in `xlsx-md-shapes.md`
  cross-links to ARCH or TASK for the deeper rationale. The
  contract doc itself is a developer-facing reference, not a
  user-facing manual.
- **No new dependencies.** `openpyxl` import in the round-trip
  test is for ASSERTING cell content post-roundtrip, not for
  production code. The package itself does not import openpyxl
  directly (D-A5 banned-api).
- **Fixture `roundtrip_basic.xlsx`** should NOT contain anything
  that xlsx-3 cannot round-trip: avoid merges (xlsx-3 v1 doesn't
  recreate them), avoid formulas (xlsx-3 emits values), avoid
  styles (xlsx-3 drops them). Use plain strings, integers, ISO
  dates, and one hyperlink.
- This task does NOT bind test slugs from §5.1 #19-#20 or
  #22-#25 — those are 012-03 / 012-04 / 012-05 / 012-06 / 012-08
  responsibilities. T-#21 (newline `<br>` round-trip) is the
  unique binding for this task.
