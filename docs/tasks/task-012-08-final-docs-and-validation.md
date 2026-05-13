# Task 012-08 [INTEGRATION]: Final docs + validation gates + KNOWN_ISSUES.md + 34-slug regression cluster

> **Predecessor:** 012-07.
> **RTM:** [R6h] (no-flag shape pin regression), [R20] (number-
> format heuristic regression), [R27] (≥ 14 E2E + unit-per-module
> + validate_skill + existing-suite green + 5-line `diff -q`).
> Locks all 14 honest-scope §1.4 (a)..(m) + R3-H1 items via
> docstrings and/or regressions.
> **UCs:** locks all UCs via the final E2E cluster.

## Use Case Connection

- Locks UC-01..UC-12 via the final E2E gate.
- Locks cross-skill replication boundary (CLAUDE.md §2; TASK §0;
  ARCH §9.1).

## Task Goal

Final release gate for TASK 012:

1. Update `skills/xlsx/SKILL.md` with `xlsx2md.py` registry row +
   §10 honest-scope note.
2. Update `skills/xlsx/.AGENTS.md` with a `## xlsx2md` section
   (Developer-facing; the `.AGENTS.md` notes are READ by agents
   working on the xlsx skill).
3. Add module docstrings for honest-scope §1.4 items to each
   module of `xlsx2md/` (verifying that 012-01..012-06 wrote them
   correctly; this task back-fills any gaps).
4. Add the regression test cluster — the 34 test slugs from TASK
   §5.1 are all bound to bead-specific tests in 012-02..012-07;
   this task ensures the cluster lives in `test_e2e.py` as a
   consolidated entry point and adds the inherited-hardening
   regressions (#26..#34) plus pinned-no-flag-shape (R6.h) and
   number-format heuristic (R20).
5. `docs/KNOWN_ISSUES.md` gets the `XLSX-10B-DEFER` entry with
   `xlsx-10.B` backlog cross-link + 14-day deadline marker
   (TASK AC #15).
6. Update `docs/office-skills-backlog.md` xlsx-9 row → ✅ DONE.
7. Run all release gates:
   - `python3 .claude/skills/skill-creator/scripts/validate_skill.py
     skills/xlsx` exit 0.
   - `ruff check scripts/` green.
   - 5-line `diff -q` silent.
   - Full xlsx skill test suite green (no-behaviour-change for
     existing xlsx-* paths).

This task introduces **no Python source code changes** in
`xlsx2md/` itself — only documentation, regression tests,
KNOWN_ISSUES update, backlog update, and validation. If a gate
fails, the failure mode is to return to the responsible upstream
task (012-04, 012-05, etc.), not to patch here.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

**Locate** the script registry table (search by `xlsx2csv.py`
row to find it). **Add** a new row:

```markdown
| `xlsx2md.py` | Convert `.xlsx` to Markdown (GFM, HTML, or per-table hybrid). |
```

**Locate** `§10` honest-scope catalogue. **Append**:

```markdown
- **xlsx2md (v1):** comments / charts / images / shapes /
  pivots / data-validation / cell styles / diagonal borders /
  sparklines / camera objects dropped; rich-text spans →
  plain-text concat; formulas without cached value emit empty
  (or `data-formula` attr in HTML when `--include-formulas`);
  hyperlinks always extracted (D5; `read_only_mode=False`
  default; `--memory-mode=streaming` override available);
  hyperlink scheme allowlist defaults `{http, https, mailto}`
  (Sec-MED-2 default-enabled in v1); sheet names emitted
  verbatim from `xl/workbook.xml/<sheets>` (xlsx-3 round-trip
  may sanitise on write-back — documented in
  `references/xlsx-md-shapes.md` §6, NOT a regression). See
  [docs/tasks/task-012-*.md](../../docs/tasks/) for details.
```

#### File: `skills/xlsx/.AGENTS.md`

**Append** a new section:

```markdown
## xlsx2md (xlsx-9 read-back to Markdown)

**Package:** `scripts/xlsx2md/`
**Shim:** `scripts/xlsx2md.py` (≤ 60 LOC).

### Closed-API consumption pattern

The package is the **second consumer** (after xlsx-8 / xlsx2csv2json)
of the xlsx-10.A `xlsx_read/` closed-API contract (ARCH D-A5).
Imports come exclusively from `xlsx_read.<public>`; the ruff
banned-api rule in `scripts/pyproject.toml` blocks any
`xlsx_read._*` import.

### Format selector (hybrid) decision rules

Per-table format selection in hybrid mode (default) — first match wins:

| Rule | Condition | Format |
| --- | --- | --- |
| 1 | Body merges present | HTML |
| 2 | Multi-row header (` › ` in any header) | HTML |
| 3 | `--include-formulas` AND ≥ 1 formula cell | HTML |
| 4 | `headerRowCount=0` (synthetic headers, D13) | HTML |
| — | None of the above | GFM |

`--format gfm` / `--format html` short-circuit the promotion
rules.

### Multi-row `<thead>` reconstruction (D-A11)

`xlsx_read` returns flat ` › `-joined headers. xlsx-9
reconstructs the multi-row HTML `<thead>` emit-side:
`headers.split_headers_to_rows` splits each header into a
row-major matrix; `headers.compute_colspan_spans` groups
consecutive identical prefix paths into colspan values;
`headers.validate_header_depth_uniformity` raises
`InconsistentHeaderDepth` on non-uniform depth.

### `--no-table-autodetect` (D-A2 post-call filter)

The shim's `--no-table-autodetect` flag does NOT use a library
enum value (no `gap-only` mode in `xlsx_read.TableDetectMode`).
Instead, the dispatch calls `detect_tables(mode="auto")` then
filters with `r.source == "gap_detect"`. Mirror of xlsx-8 D-A2
pattern.

### `--memory-mode` (D-A14 inherited from xlsx-8a-11)

| `--memory-mode` | `read_only_mode` | Behaviour |
| --- | --- | --- |
| `auto` (default) | `None` | Library size-threshold (≥ 100 MiB → streaming) |
| `streaming` | `True` | Force read-only streaming; hyperlinks unreliable |
| `full` | `False` | Force in-memory; correct hyperlinks; ~5-10× workbook size heap |

### `--hyperlink-scheme-allowlist` (D-A15 inherited from xlsx-8a-03)

Default `http,https,mailto`. Scheme filter applied to both GFM
`[text](url)` and HTML `<a href>` emissions. Blocked schemes
emit text-only + stderr `UserWarning`. Special values:
- `'*'` allows all schemes.
- `""` (empty) blocks all hyperlinks.

### Honest scope (v1)

See [docs/tasks/task-012-07-round-trip-contract.md](../../docs/tasks/task-012-07-round-trip-contract.md)
and the `xlsx2md/__init__.py` module docstring for the full TASK
§1.4 catalogue.

### Round-trip with md_tables2xlsx (xlsx-3)

Cell content is byte-identical after `xlsx2md → md_tables2xlsx →
xlsx2md` for non-merged, non-formulated tables with plain text /
integers / ISO dates. Sheet names may differ on the second pass
because xlsx-3 sanitises (`History` → `History_`); this is
documented in `references/xlsx-md-shapes.md` §6 as EXPECTED.

Live round-trip test:
`scripts/tests/test_md_tables2xlsx.py::TestRoundTripXlsx9`.

### Cross-skill replication

**None.** This package is xlsx-specific. The 5-line `diff -q`
gate (CLAUDE.md §2) MUST remain silent.
```

#### File: `docs/office-skills-backlog.md`

**Locate** the `xlsx-9` row. **Update** its status / notes
column:

```markdown
| xlsx-9 | `xlsx2md.py` (read-back to Markdown) ✅ DONE 2026-MM-DD (Task 012 atomic chain 012-01..012-08) | ... [existing description unchanged] ... |
```

> **NOTE:** The developer running this task makes the merge — the
> exact date is the merge-commit date.

#### File: `docs/KNOWN_ISSUES.md`

**Append** a new entry:

```markdown
## XLSX-10B-DEFER (xlsx-7 refactor to consume xlsx_read)

**Status:** DEFERRED (14-day timer started 2026-05-13, deadline
2026-05-27).
**Backlog row:** `xlsx-10.B` in
[`docs/office-skills-backlog.md`](office-skills-backlog.md).
**Context:** xlsx-7 (`xlsx_check_rules/`) duplicates a portion of
xlsx-10.A `xlsx_read/` reader logic. The refactor was deferred at
xlsx-10.A merge to bound the v1 surface; xlsx-9 merge starts the
14-day ownership-bounded timer. If unaddressed by 2026-05-27, the
duplication becomes a regression risk for any future
`xlsx_read` API change.
**Owner:** TBD (assigned at xlsx-10.B kickoff).
**Workaround:** None required for xlsx-7's current functionality;
the duplication is correctness-preserving as of 2026-05-13.
```

#### File: `skills/xlsx/scripts/xlsx2md/__init__.py`

**No source code change.** Verify the module docstring written
in 012-01 already covers honest-scope items (a)..(m) + R3-H1 +
the inherited (k), (l), (m) items from xlsx-8a-09 / xlsx-8a-03 /
xlsx-8a-11. If any item is missing, this task BACK-FILLS the
docstring (still no behaviour change; pure documentation).

#### File: `skills/xlsx/scripts/xlsx2md/inline.py`

**No source code change.** Verify module docstring covers §1.4
(l) hyperlink scheme allowlist default + special values; back-fill
if missing.

#### File: `skills/xlsx/scripts/xlsx2md/dispatch.py`

**No source code change.** Verify module docstring covers §1.4
(k) `--header-rows smart` semantics + §1.4 (m) hyperlinks-always-on
+ memory-mode trade-off; back-fill if missing.

#### File: `skills/xlsx/scripts/xlsx2md/emit_html.py`

**No source code change.** Verify module docstring covers §1.4
(g) stale-cache emit + D13 synthetic `<thead>` decision; back-fill
if missing.

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_e2e.py`

Consolidated 34-slug E2E cluster. Each test method is a thin
wrapper that invokes `python3 xlsx2md.py [args]` via subprocess
and asserts exit code + a key substring in stdout/stderr/output
file.

The 25 slugs #1..#25 are defined in 012-02..012-06; the 9 new
slugs #26..#34 are FIRST-time-asserted here (as inherited-hardening
regressions). Test cluster organisation:

1. `test_T01_single_sheet_gfm_default`
2. `test_T02_stdout_when_output_omitted`
3. `test_T03_sheet_named_filter`
4. `test_T04_multi_sheet_h2_ordering`
5. `test_T05_hidden_sheet_skipped_default`
6. `test_T06_hidden_sheet_included_with_flag`
7. `test_T07_multi_table_listobjects_h3`
8. `test_T08_merged_body_cells_html_colspan`
9. `test_T09_gfm_merges_require_policy_exit2`
10. `test_T10_multi_row_header_html_thead`
11. `test_T11_multi_row_header_gfm_u203a_flatten`
12. `test_T12_hyperlink_gfm_url_form`
13. `test_T13_hyperlink_html_anchor_tag`
14. `test_T14_include_formulas_gfm_exits2`
15. `test_T15_include_formulas_html_data_attr`
16. `test_T16_same_path_via_symlink_exit6`
17. `test_T17_encrypted_workbook_exit3`
18. `test_T18_xlsm_macro_warning`
19. `test_T19_gap_detect_default_no_split_on_1_row`
20. `test_T20_gap_detect_splits_on_2_empty_rows`
21. `test_T21_cell_newline_br_roundtrip` (uses 012-07
    `roundtrip_basic.xlsx` + `md_tables2xlsx`)
22. `test_T22_json_errors_envelope_shape_v1`
23. `test_T23_gfm_merge_policy_duplicate`
24. `test_T24_synthetic_headers_listobject_zero`
25. `test_T25_no_autodetect_empty_fallback_whole_sheet`
26. `test_T26_header_rows_smart_skips_metadata_block`
27. `test_T27_header_rows_int_with_multi_table_exits_2_conflict`
28. `test_T28_memory_mode_streaming_bounds_peak_rss` (slow,
    `@unittest.skipUnless(os.environ.get("RUN_SLOW_TESTS"))`)
29. `test_T29_memory_mode_auto_respects_library_default_100mib_threshold`
30. `test_T30_hyperlink_allowlist_blocks_javascript_html`
31. `test_T31_hyperlink_allowlist_blocks_javascript_gfm`
32. `test_T32_hyperlink_allowlist_default_passes_https_mailto`
33. `test_T33_hyperlink_allowlist_custom_extends`
34. `test_T34_internal_error_envelope_redacts_raw_message`

#### `skills/xlsx/scripts/xlsx2md/tests/test_regressions.py`

R6.h, R20, R3-H1, A-A3 regressions:

1. `test_no_flag_omitted_shape_pin` (R6.h) — single-sheet
   single-row-header fixture; no flags; output shape EXACTLY
   matches the locked baseline string.
2. `test_number_format_heuristic_thousand_separator` (R20) —
   cell with `number_format = "#,##0.00"` and value `1234.5`;
   output markdown cell contains literal `"1,234.50"`.
3. `test_number_format_heuristic_percent` (R20) — cell with
   `0%` format and value `0.42`; output cell contains `"42%"`.
4. `test_sheet_name_verbatim_no_sanitisation` (R3-H1) — sheet
   named `History`; output H2 is `## History` (NOT
   `## History_`).
5. `test_literal_u203a_in_header_consistent_across_runs` (A-A3) —
   sheet with single-row header cell value containing literal
   `" › "` (U+203A with surrounding spaces); run xlsx-9 twice;
   results byte-identical (deterministic misinterpretation).

### Component Integration

- All gates from 012-01..012-07 are exercised end-to-end.
- The 5 release gates (`validate_skill.py`, `ruff`, `diff -q`,
  full test suite, LOC budget) are explicitly enumerated below.

## Test Cases

### E2E Tests

34 slugs in `test_e2e.py` (consolidates per-bead E2Es into one
file as required by R27).

### Unit Tests

5 regressions in `test_regressions.py` (per ARCH §11 row 012-08
regression list).

### Regression Tests

#### Gate 1: `validate_skill.py`

```bash
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx
```

Must exit 0.

#### Gate 2: 5-line `diff -q` silent (CLAUDE.md §2; TASK §0; ARCH §9.1)

```bash
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -q  skills/docx/scripts/_soffice.py      skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_errors.py       skills/xlsx/scripts/_errors.py
diff -q  skills/docx/scripts/preview.py       skills/xlsx/scripts/preview.py
diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
```

ALL must produce no output.

#### Gate 3: LOC budget

```bash
wc -l skills/xlsx/scripts/xlsx2md.py
# Expected: ≤ 60 LOC (TASK AC #1; R1.d).

find skills/xlsx/scripts/xlsx2md -name '*.py' -not -path '*/tests/*' \
    -exec wc -l {} +
# Expected: total ≤ 4500 LOC (9 modules × ≤ 700 LOC/module TASK R2.g);
# typical actual: ~1500-2500 LOC for v1.
```

#### Gate 4: Full xlsx test suite green

```bash
cd skills/xlsx/scripts
./.venv/bin/python -m unittest discover -s xlsx2md/tests
./.venv/bin/python -m unittest discover -s xlsx2csv2json/tests
./.venv/bin/python -m unittest discover -s json2xlsx/tests
./.venv/bin/python -m unittest discover -s tests   # md_tables2xlsx tests including TestRoundTripXlsx9
./.venv/bin/python -m unittest discover -s xlsx_check_rules/tests
./.venv/bin/python -m unittest discover -s xlsx_comment/tests
./.venv/bin/python -m unittest discover -s xlsx_read/tests
```

ALL must exit 0. Specifically:
- `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md` is NOT
  skipped (R-2 risk mitigation).
- All 34 E2E slugs pass.
- No existing test starts failing.

#### Gate 5: ruff banned-api

```bash
cd skills/xlsx/scripts
ruff check scripts/
```

Must exit 0. Specifically: no `from xlsx_read._workbook import
...` etc. from `xlsx2md/*.py`.

## Acceptance Criteria

- [ ] `skills/xlsx/SKILL.md` updated: 1 registry row +
      §10 honest-scope note.
- [ ] `skills/xlsx/.AGENTS.md` updated: `## xlsx2md` section
      added.
- [ ] `docs/office-skills-backlog.md` xlsx-9 row marked ✅ DONE
      with merge date.
- [ ] `docs/KNOWN_ISSUES.md` has `XLSX-10B-DEFER` entry with
      backlog cross-link + 14-day deadline marker (TASK AC #15).
- [ ] All 14 honest-scope §1.4 (a)..(m) + R3-H1 items locked by
      docstring AND/OR regression test (verify by grepping
      module docstrings for each item identifier).
- [ ] `xlsx2md/tests/test_e2e.py` exists with 34 test methods
      (one per TASK §5.1 slug).
- [ ] `xlsx2md/tests/test_regressions.py` exists with the 5
      regressions listed above.
- [ ] **Gate 1** (`validate_skill.py skills/xlsx`) exits 0.
- [ ] **Gate 2** (5-line `diff -q`) silent:
      ```bash
      diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
      diff -q  skills/docx/scripts/_soffice.py      skills/xlsx/scripts/_soffice.py
      diff -q  skills/docx/scripts/_errors.py       skills/xlsx/scripts/_errors.py
      diff -q  skills/docx/scripts/preview.py       skills/xlsx/scripts/preview.py
      diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
      ```
- [ ] **Gate 3** (LOC budget) — shim ≤ 60 LOC; each module
      ≤ 700 LOC.
- [ ] **Gate 4** (full xlsx suite) — green; specifically
      `TestRoundTripXlsx9` not skipped.
- [ ] **Gate 5** (`ruff check scripts/`) — green.
- [ ] No source code changes to `xlsx2md/*.py` modules in this
      task (only documentation, tests, KNOWN_ISSUES, backlog).
- [ ] No changes to `office/`, `_errors.py`, `_soffice.py`,
      `preview.py`, `office_passwd.py`, `xlsx_read/`,
      `xlsx2csv2json/`, `json2xlsx/`, `md_tables2xlsx/` source.

## Notes

- This task introduces **no Python source code changes** in
  `xlsx2md/` modules — only documentation, regression tests,
  KNOWN_ISSUES.md, backlog row update, and validation.
- If a gate fails, the failure mode is to **return to the
  responsible upstream task** (ruff failure → 012-04 / 012-05 /
  012-06; validate_skill failure → fix the structural issue;
  test failure → return to the bead that owns the test) rather
  than patching here.
- The `XLSX-10B-DEFER` entry in `KNOWN_ISSUES.md` is the
  TASK AC #15 deliverable. The 14-day deadline is computed from
  the xlsx-9 merge commit date — if the merge happens 2026-05-13,
  deadline 2026-05-27. The developer must update the deadline
  date at merge time.
- The backlog row update is **strictly documentation** — the
  developer must use the actual merge-commit date.
- The `validate_skill.py` gate is **not optional** — it verifies
  the Gold Standard structure of `skills/xlsx/`. If it fails,
  fix the structural issue, not the gate.
- Slow tests (#28 `T-memory-mode-streaming-bounds-peak-rss`) are
  gated by `RUN_SLOW_TESTS=1` env var (mirror xlsx-2 D8 pattern).
  CI may run them in nightly mode; local dev may skip.
- The `_extract_table_bodies` normaliser from 012-07 is used by
  the round-trip live test (`TestRoundTripXlsx9`). This task
  does NOT modify it.

## Done-Definition (project-level — final gate)

A merge of TASK 012 is acceptable iff:

1. All 5 release gates above pass on the merge commit.
2. Every R-Issue R1..R27 + R10a + R20a has at least one
   passing test bound to it.
3. Every TASK §5.1 slug T-#1..T-#34 has at least one passing
   E2E in `test_e2e.py`.
4. Every honest-scope §1.4 (a)..(m) + R3-H1 has at least one
   docstring lock OR regression test.
5. `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md` is not
   skipped AND passes.
6. The 5-line `diff -q` silent gate stays silent.
7. The xlsx-9 backlog row reads ✅ DONE in
   `docs/office-skills-backlog.md`.
8. `docs/KNOWN_ISSUES.md` has the `XLSX-10B-DEFER` entry.
