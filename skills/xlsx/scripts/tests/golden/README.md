# Goldens — agent-output-only protocol

These files are **agent-output-only** (R9.d / `docs/TASK.md` §5
Assumptions / `docs/tasks/task-001-04-fixtures.md`).

## Why

Excel 365 may silently mutate legacy comments → threaded on save (per
backlog xlsx-6 honest scope, locked in `docs/TASK.md` R9.d). If a
golden is opened and saved in Excel, the next regression run will diff
against the mutated file, producing false positives. The same risk
applies to LibreOffice and Numbers — any consumer that round-trips
OOXML through its own editor pipeline.

## Rules

1. **DO NOT open these files in Excel** (or Numbers, or any consumer
   that might rewrite OOXML on save). LibreOffice has the same risk;
   if you must spot-check, open a COPY.
2. To regenerate **synthetic inputs**, run:
   ```
   cd skills/xlsx/scripts
   ./.venv/bin/python tests/regenerate_synthetic_inputs.py
   ```
3. To regenerate **encrypted.xlsx** (fresh random salt per run):
   ```
   cd skills/xlsx/scripts
   ./.venv/bin/python office_passwd.py \
       tests/golden/inputs/clean.xlsx \
       tests/golden/inputs/encrypted.xlsx \
       --encrypt password123
   ```
4. To regenerate **outputs** (`tests/golden/outputs/`), Stage-2 task
   2.10 will publish a `regenerate_outputs.py` companion that runs
   `xlsx_add_comment.py` against each input with `--date 2026-01-01T00:00:00Z`
   for determinism. Outputs are diffed via canonical XML compare
   (`lxml.etree.tostring(method='c14n')`, with `<threadedComment id>`
   and unpinned `dT` masked) — see `docs/tasks/task-001-15-final-docs.md`.

## Provenance

| File | Source | Notes |
|---|---|---|
| `clean.xlsx` | synthetic via `regenerate_synthetic_inputs.py` | Header + 10 numeric rows on `Sheet1`. |
| `multi_sheet.xlsx` | synthetic | 3 sheets: `Sheet1`, `Sheet2`, `Q1 2026` (last name has whitespace — exercises quoted-cell-syntax `'Q1 2026'!A1`). |
| `hidden_first.xlsx` | synthetic | `Sheet1` `state="hidden"`, `Sheet2` visible (M2 first-VISIBLE rule fixture). |
| `merged.xlsx` | synthetic | `<mergeCell ref="A1:C3"/>`. R6 fixture. |
| `with_legacy.xlsx` | **synthetic — m-E DEVIATION** | See "M-E DEVIATION" section below. |
| `macro.xlsm` | **synthetic — m-E DEVIATION** | See "M-E DEVIATION" section below. |
| `encrypted.xlsx` | `office_passwd.py --encrypt password123` over `clean.xlsx` | Salt-randomised; non-deterministic across regenerations. |

## M-E DEVIATION (Excel-365 fallback per task spec §Notes)

Two fixtures — **`with_legacy.xlsx`** and **`macro.xlsm`** — are
specified by `docs/tasks/task-001-04-fixtures.md` to be authored in
Excel-365 verbatim, "to test against real-world VML and macro
shapes". At fixture-creation time (2026-05-07) Excel-365 access was
unavailable, so the m-E fallback documented in that task's `Notes`
applies:

> If Excel-365 access is unavailable at task pick-up, commit a
> synthetic openpyxl-generated equivalent for `with_legacy.xlsx`
> (use `openpyxl.comments.Comment`) and flag the deviation in
> `tests/golden/README.md`. The corresponding E2E may temporarily
> skip until the real Excel fixture is committed (not a blocker for
> stage progression). Same fallback applies to `macro.xlsm`: a
> hand-crafted `xl/vbaProject.bin` is acceptable as long as
> `office/validate.py` accepts it.

### Implications and replacement procedure

- The synthetic `with_legacy.xlsx` carries 2 legacy `<comment>`
  elements + a single `xl/drawings/vmlDrawing1.xml` part with
  `<o:idmap data="1"/>` and shape ids in the `_x0000_s1026+` range
  (openpyxl's `shape_writer.enumerate(self.comments, 1026)`) —
  semantically equivalent to Excel's own emission. Excel itself starts
  the per-drawing range at `_x0000_s1025`; the off-by-one is harmless
  because `scan_spid_used` (task 2.03) is workbook-wide max+1.
- The synthetic `macro.xlsm` is structurally a macro-enabled package
  (Content_Types main type swapped to `…macroEnabled.main+xml`,
  `xl/vbaProject.bin` carries a 512-byte CFB-magic-prefixed payload
  that `office._macros.is_macro_enabled_file` accepts as macro-bearing).
  The VBA inside is NOT runnable; this fixture is for round-trip
  preservation tests (R8.c), not macro-execution tests.
- **Replacement procedure (when Excel-365 access becomes available):**
  1. Open a fresh Excel-365 workbook.
  2. For `with_legacy.xlsx`: insert 2 comments via Review → New Comment
     ribbon. Save As `.xlsx`. Record exact build number in this README.
  3. For `macro.xlsm`: write a trivial `Sub Hello() : End Sub` in the
     VBA editor. Save As `.xlsm`. Record exact build number.
  4. Replace the two files in `tests/golden/inputs/` verbatim. Remove
     the corresponding `make_with_legacy()` and `make_macro_xlsm()`
     blocks from `regenerate_synthetic_inputs.py`. Update this README:
     remove the M-E DEVIATION section and update the Provenance table.
  5. Re-run `bash tests/test_e2e.sh` and confirm 53/53 still green.

## Validator exemptions

`docs/tasks/task-001-04-fixtures.md` AC says *"office/validate.py
exits 0 on every committed input fixture"*. Two fixtures are
**architecturally exempted** from this rule:

- **`encrypted.xlsx`** — `office/validate.py` deliberately returns
  exit 3 on encrypted inputs (cross-3 contract, see
  `office/_encryption.py` and `docs/TASK.md` R7.a). Validity here is
  proved instead by `office_passwd.py --check` returning exit 0
  (encrypted) and by a successful `--decrypt password123` round-trip
  to a clean workbook (already covered by existing
  `cross-7 password-protect` block in `tests/test_e2e.sh`).
- **`macro.xlsm`** — `office/validate.py` only accepts `.docx`,
  `.xlsx`, `.pptx` extensions (returns exit 2 `Unknown extension`
  for `.xlsm`). This is an `office/`-shared structural decision and
  cannot be patched without 4-skill replication (CLAUDE.md §2).
  Validity here is proved instead by
  `office._macros.is_macro_enabled_file(path) == True` and by the
  `xl/vbaProject.bin` part being present and non-empty.

The five other inputs (`clean.xlsx`, `multi_sheet.xlsx`,
`hidden_first.xlsx`, `merged.xlsx`, `with_legacy.xlsx`) all pass
`office/validate.py` cleanly.

## Size budget

All committed inputs are ≤ 50 KB each (per task AC). Current sizes:

| File | Bytes |
|---|---|
| clean.xlsx | 5,035 |
| multi_sheet.xlsx | 5,773 |
| hidden_first.xlsx | 5,310 |
| merged.xlsx | 4,885 |
| with_legacy.xlsx | 6,252 |
| macro.xlsm | 5,011 |
| encrypted.xlsx | 10,240 (encryption overhead) |

`regenerate_synthetic_inputs.py` asserts `size <= 50 * 1024` per
fixture so this budget cannot drift silently.

## Test references

| Fixture | E2E test(s) (in `tests/test_e2e.sh`) |
|---|---|
| `clean.xlsx` | `T-clean-no-comments`, `T-threaded`, `T-thread-linkage`, `T-threaded-rel-attachment`, `T-no-threaded-no-threaded-artifacts`, `T-batch-50`, `T-batch-envelope-mode`, `T-batch-skipped-grouped`, `T-apostrophe-sheet`, `T-hidden-first-sheet`, `T-idmap-conflict`, `T-EmptyCommentBody*`, `T-MX-*`, `T-DEP-*`, `T-same-path*`. Default fixture for tests that don't need a special structural property. |
| `multi_sheet.xlsx` | `T-multi-sheet`, `T-golden-multi-sheet` (canonical-XML diff). |
| `hidden_first.xlsx` | `T-hidden-first-sheet` (M2 first-VISIBLE rule). |
| `merged.xlsx` | `T-merged-cell-target` (B2 non-anchor → exit 2), `T-merged-cell-redirect` (--allow-merged-target → A1), `T-merged-cell-anchor-passthrough` (A1 IS anchor). |
| `with_legacy.xlsx` | `T-existing-legacy-preserve` (R8.b c14n byte-equivalence), `T-batch-50-with-existing-vml` (R4.h incremental allocator), `T-duplicate-legacy` (R5.b), `T-golden-existing-legacy-preserve`, `T-golden-idmap-conflict`. |
| `macro.xlsm` | `T-macro-xlsm` (real assertion in tasks 2.01 + 2.08). |
| `encrypted.xlsx` | `T-encrypted` (real assertion in task 2.01: exit 3 envelope). |

## Honest scope

This README and the m-E fallback decisions documented above are
themselves the **R9.d regression lock** — `tests/test_xlsx_add_comment.py::TestHonestScope::test_HonestScope_goldens_README_exists`
(Stage-2 task 2.09) asserts the literal phrase "DO NOT open these
files in Excel" is present in this file. Do not rephrase that line
without updating the test in lockstep.

## xlsx-7 fixtures

`xlsx_check_rules.py` (xlsx-7) ships its own regression battery
(SPEC §13). Fixture authoring uses a different protocol from xlsx-6:

- **Source of truth:** declarative `.yaml` manifests in
  `tests/golden/manifests/` (committed). One per fixture.
- **Generator:** `tests/golden/inputs/_generate.py` reads manifests
  and writes `<name>.xlsx` + `<name>.rules.{json,yaml}` +
  `<name>.expected.json` triples into `tests/golden/inputs/`.
- **Q5 hybrid storage:** small fixtures (≤ 50 KB) regenerated each
  test run; the perf fixture `huge-100k-rows.xlsx` (≈ 10–15 MB) is
  committed once and re-hashed via the `.manifesthash` sidecar so
  `_generate.py --check` short-circuits when manifests are stable.
  See `tests/golden/inputs/.gitignore` for the allow-list.
- **Same agent-output-only rule applies** — DO NOT open these files
  in Excel either; the M2 envelope contract (xlsx-6 batch.py:122
  gate) is fragile to silent OOXML rewrites by editors.

### Manifest schema (frozen contract)

| Field | Type | Notes |
|---|---|---|
| `id` | int | SPEC §13.1 fixture index. |
| `name` | str | Filename stem (`<name>.xlsx`, `.rules.<fmt>`, `.expected.json`). |
| `shape` | str | Builder dispatch key. Today: `simple-grid`, `with-table`, `merged-header` (003.04a). 003.04b adds shapes for adversarial / streaming / output fixtures. |
| `rules_format` | `'json'` \| `'yaml'` | Default `json`. |
| `sheet` | object | `name` + per-shape extra fields (`cells`, `table`, `data`, `merge_ranges`). |
| `rules` | str (block) | Verbatim rules-file body (NOT round-tripped through a YAML serialiser — adversarial fixtures rely on byte-faithful output). |
| `flags` | list[str] | Optional CLI args appended after `--rules`. |
| `expected` | object | `exit_code` + `summary` (subset compare) + `required_rule_ids` + `forbidden_rule_ids` + `requires_envelope` (default `true`; set `false` for exit-2 fixtures that take the cross-5 envelope path). |

### Provenance — 003.04a fixtures (10 of 42; happy path + layout variance)

| # | Manifest | Shape | SPEC anchor | Locks |
|---|---|---|---|---|
| 1 | `clean-pass.yaml` | simple-grid | §13.1 layout #1 | Happy path; ok=true; findings=[] |
| 2 | `timesheet-violations.yaml` | simple-grid | §13.1 layout #2 + §10 worked example | Required `[hours-realistic, totals-match]`, forbidden `[hours-positive]` |
| 3 | `header-row-3.yaml` | simple-grid | §13.1 layout #3 + §4.2 | `defaults.header_row: 3` override |
| 4 | `excel-table-data.yaml` | with-table | §13.1 layout #4 + §4.3 | `table:T1[Hours]` resolves through `xl/tables/tableN.xml` |
| 5 | `multi-row-headers.yaml` | merged-header | §13.1 layout #5 + §4.2 | exit 2 `MergedHeaderUnsupported` |
| 6 | `transposed-layout.yaml` | simple-grid | §13.1 layout #6 + R13.h | Documented honest-scope: silent misfire (no `transposed:` form) |
| 7 | `dup-header.yaml` | simple-grid | §13.1 layout #7 + §4.2 | exit 2 `AmbiguousHeader` |
| 8 | `missing-header.yaml` | simple-grid | §13.1 layout #8 + §4.2 | exit 2 `HeaderNotFound` (with `details.available`) |
| 9 | `apostrophe-sheet.yaml` | simple-grid | §13.1 layout #9 + §4.1 | Sheet-name escaping `'Bob''s Sheet'!` |
| 10b | `modern-error-text.yaml` | simple-grid | §5.0 + D4 (architect-review M-1) | `#SPILL!` stored as text → no `cell-error` auto-emit |
| 31 | `huge-100k-rows.yaml` | perf-fixture | §13.1 #31 + §11.2 perf contract | 100K rows × 10 cols × 5 rules ≤ 30 s wall-clock; `--regenerate-perf-fixture` deterministic seed=42; committed binary (Q5 hybrid). RUN_PERF_TESTS=1 gated. |

The remaining 32 fixtures (adversarial / cross-sheet / aggregates /
output / honest-scope / pipeline) land in 003.04b. The perf fixture
#31 `huge-100k-rows.xlsx` is generated by `_generate.py
--regenerate-perf-fixture` (003.16a) and committed.

### Canary saboteurs (SPEC §13.3)

`tests/canary_check.sh` runs 10 hand-coded saboteurs against the
package source: each saboteur patches a specific module via `sed`,
runs the corresponding battery test, and asserts the test FAILED
(proving the battery actually exercises the patched code path).
Hardened post-Sarcasmotron with two defences:

- **Post-`sed` `cmp -s` assertion** — silently catches pattern-no-
  match (sed exits 0 even when the pattern is absent from the
  file), so refactors that rename a saboteur target line surface as
  `SED MATCHED ZERO LINES` rather than as a vacuous ✓ broke.
- **Textual unittest-output grep** — looks for `FAILED (failures=`
  / `FAILED (errors=` and explicitly REJECTS `unexpected success`,
  so xfail-decorated targets cannot fool the rc-only check.

PRECONDITION for 003.04b authors: every saboteur-targeted manifest
MUST set `xfail: false`; the canary's textual-grep guard rejects
`unexpected success` outcomes as path-mismatches.

Today: 1 saboteur active (Saboteur 04 — multi-row-headers); 9
deferred to 003.04b once their target manifests land.
