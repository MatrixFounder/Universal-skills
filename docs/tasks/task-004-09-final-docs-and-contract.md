# Task 004.09: `references/json-shapes.md` contract freeze + SKILL.md + .AGENTS.md + backlog ✅ DONE + perf wiring + validator gate

## Use Case Connection
- **All UCs** (docs reflect the final shipped behaviour).
- **UC-5** specifically (`references/json-shapes.md` is the contract spec xlsx-8 must implement against — DoD §7 m1 + ARCH §3.2 m4 lock).

## Task Goal
Finalise the deliverable: author `skills/xlsx/references/json-shapes.md` as the canonical round-trip contract spec; update `SKILL.md` §1 Red Flags + §2 Capabilities to reflect xlsx-2; update `scripts/.AGENTS.md` with the post-merge module map; mark `docs/office-skills-backlog.md` xlsx-2 row ✅ DONE with status block (date + LOC + test counts); wire the 10K-row perf opt-in test under `RUN_PERF_TESTS=1` (no CI gate); confirm CLAUDE.md §2 byte-identity diffs + `validate_skill.py` final pass.

**Closes DoD §7 m1** — `references/json-shapes.md` is the contract artefact mentioned at end-of-chain.
**Closes ARCH §3.2 m4** — pins xlsx-8's future obligation to consume the spec unchanged.
**Closes O1** — xlsx-2 owns the round-trip contract via `references/json-shapes.md`; xlsx-8's future task consumes the spec and adds the live test wiring in `tests/test_json2xlsx.py`, NOT in this chain. (Plan-reviewer #7 nit.)

## Perf Inventory (plan-reviewer #6 honesty fix)

TASK §4.1 specifies TWO perf budgets:

- **10K-row × 6-col ≤ 3 s** — **shipped in v1** (test class below).
- **100K-row JSONL ≤ 30 s** — **EXPLICITLY DEFERRED to v2** per honest scope §11.3 / O4 (deferred to `openpyxl write_only=True` mode). xlsx-2 v1 does NOT include a 100K-row perf test. The budget number stays documented in TASK §4.1 as a forward-looking target; the test does not exist in v1.

R11.e in PLAN.md RTM matrix matches this honest single-perf-test inventory.

## Changes Description

### New Files

- `skills/xlsx/references/json-shapes.md` — **Round-trip contract spec.** ≈ 250 LOC. Mandatory sections (the spec freezes these unambiguously):

  ### §1 Scope
  Defines the JSON shape contract for the **xlsx-2 ↔ xlsx-8** producer/consumer pair. Any future xlsx-8 implementation MUST conform.

  ### §2 Three accepted input shapes (mirrors xlsx-2 R2 / D1)
  - **2.1 array-of-objects** `[{col: val, …}, …]`
  - **2.2 multi-sheet dict** `{"<sheet_name>": [{col: val, …}, …], …}`
  - **2.3 JSONL** `{"col": "v1"}\n{"col": "v2"}\n` (single sheet)

  Detection rule: `.jsonl` extension → JSONL; else dispatch on JSON root token.

  ### §3 Sheet-name key naming (locked)
  - Multi-sheet root keys are **verbatim Excel sheet names**. No normalisation, no case-folding, no truncation. If a key violates Excel's sheet-name rules (≤ 31 chars, no `[]:*?/\\`, not case-insensitive `History`), the implementation MUST fail with `InvalidSheetName` (exit 2).
  - For single-sheet input (shapes 2.1 / 2.3), the output sheet name defaults to `Sheet1` and is overridable via `--sheet NAME`.

  ### §4 Cell-value typing (locked)
  - JSON `int` → Excel numeric cell (`data_type='n'`).
  - JSON `float` → Excel numeric cell (`data_type='n'`).
  - JSON `bool` → Excel boolean cell (`data_type='b'`).
  - JSON `null` → empty cell (no value set; no `data_type`).
  - JSON `str` (non-date) → Excel string cell (`data_type='s'`).
  - JSON `str` matching ISO-8601 `YYYY-MM-DD` → Excel datetime cell (`data_type='n'`, `number_format='YYYY-MM-DD'`) **when `--no-date-coerce` is off (default)**.
  - JSON `str` matching ISO-8601 datetime (with optional fractional seconds + optional `Z`/`±HH:MM`) → Excel datetime cell (`number_format='YYYY-MM-DD HH:MM:SS'`).
  - Mixed-type columns: each cell typed individually; no column-wide coercion.

  ### §5 Null-cell representation in xlsx-8 OUTPUT (the read-back direction)
  - xlsx-8 MUST emit `null` for empty cells (not omit the key). This means `json2xlsx(xlsx2json(workbook))` produces a workbook with the same set of empty cells as the original.
  - Rationale: omitting the key would lose information for downstream callers that rely on column-presence (e.g., `df.columns` after round-trip).

  ### §6 Datetime serialisation in xlsx-8 OUTPUT
  - Date cells → `"YYYY-MM-DD"` (ISO-8601 date).
  - Datetime cells → `"YYYY-MM-DD HH:MM:SS"` or `"YYYY-MM-DDTHH:MM:SS"` (either form valid; xlsx-2 accepts both).
  - **Excel does NOT store timezone**, so xlsx-8 NEVER emits a timezone offset in the JSON output. Datetimes are treated as naive.

  ### §7 `--header-row N>1` (xlsx-8 future feature)
  - Out of scope for v1. xlsx-2 receives JSON; it doesn't care what row was the header in the source workbook. xlsx-8's `--header-row N` flag is its own concern.

  ### §8 Formula resolution in xlsx-8 OUTPUT
  - xlsx-8 MUST emit **cached values** by default (`cell.value` of an openpyxl-loaded workbook resolves to the cached value when present, or `None` if no cached value). `--include-formulas` flag is xlsx-8's own opt-in.
  - **Cross-reference:** xlsx-7 (`xlsx_check_rules.py`) and xlsx-6 (`xlsx_add_comment.py`) operate the same way.

  ### §9 Honest scope (round-trip limitations)
  - Cell-level formatting (fonts, colors, alignment, borders) is NOT round-trippable. xlsx-2 always produces a fresh styled workbook with csv2xlsx-style headers; user-authored styling in an original workbook is lost on round-trip.
  - Charts, data-validation, named ranges, conditional formatting are NOT round-trippable. xlsx-4 covers some of this for a different code path.
  - Merged cells: xlsx-8 emits the anchor cell value and `null` for the merged tail; xlsx-2 writes the values back into individual cells with no re-merge. Round-trip un-merges the range.
  - Comments: xlsx-8 does NOT emit comments to JSON; xlsx-6 owns the comment surface separately.

  ### §10 Test contract
  Both xlsx-2 and xlsx-8 MUST keep `tests/golden/json2xlsx_xlsx8_shape.json` in sync. The synthetic round-trip test (`T-roundtrip-xlsx8-synthetic`) is owned by xlsx-2 v1; the live test (`T-roundtrip-xlsx8-live`) is wired in the xlsx-8 merge commit.

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

**§1 Red Flags** — Add bullet:
- `"I'll just `pd.DataFrame.from_records(rows).to_excel(out)` and ship it."` → **WRONG**. `to_excel` writes no styles, no frozen header, no auto-filter, and pandas' `infer_objects` heuristics silently promote mixed-type columns to `object`/`float64` in ways that break R3 native-type preservation. Use `json2xlsx.py`. (Echoes the existing `df.to_excel` rebuttal for csv2xlsx context.)

**§2 Capabilities** — Add bullet:
- Convert a JSON / JSONL document to a styled `.xlsx` with the same visual contract as csv2xlsx (bold header, freeze, auto-filter, column widths), native JSON types preserved, ISO-8601 dates auto-coerced.

#### File: `skills/xlsx/scripts/.AGENTS.md`

Expand the placeholder section from 004.01 to the final 7-module post-merge map:

```
## json2xlsx/ — JSON → styled .xlsx (xlsx-2)

| Module | LOC | Responsibility |
| :--- | ---: | :--- |
| `__init__.py` | ≤ 30 | Package-level public surface (convert_json_to_xlsx, main, _run, exceptions). |
| `exceptions.py` | ≤ 100 | `_AppError` + 9 typed subclasses (cross-5 envelope payload model). |
| `loaders.py` | ≤ 200 | F1+F2 — read input from file/stdin, detect shape, parse JSON / JSONL. |
| `coerce.py` | ≤ 220 | F3 — per-cell type coercion + ISO-date heuristic + --strict-dates rejection. |
| `writer.py` | ≤ 220 | F4 — workbook construction, styling (mirrors csv2xlsx), multi-sheet, sheet-name validation. |
| `cli_helpers.py` | ≤ 80 | F6+F8 — same-path guard, stdin reader, post-validate enable-check + invocation. |
| `cli.py` | ≤ 320 | F5+F7 — argparse + orchestrator + envelope routing. |

Shim: `skills/xlsx/scripts/json2xlsx.py` (≤ 220 LOC).

Cross-skill replication: **NONE.** json2xlsx is xlsx-only. No edits to `office/` / `_soffice.py` / `_errors.py` / `preview.py` / `office_passwd.py`.
```

#### File: `docs/office-skills-backlog.md`

Mark xlsx-2 row:

```
| xlsx-2 | `json2xlsx.py` ✅ DONE | JSON-array → лист с авто-detection типов колонок. Параллель к csv2xlsx. Поддерживает 3 формы (array-of-objects / multi-sheet dict / JSONL), ISO-date coercion, --strict-dates, stdin -. **Status (2026-05-NN):** 9-step atomic chain (004.01–004.09). Shim 220 LOC + json2xlsx/ package — 7 modules. Tests: NN unit + 12 E2E + 1 perf (RUN_PERF_TESTS=1). Contract spec: `skills/xlsx/references/json-shapes.md`. Полная задача-история: `docs/tasks/task-004-*.md` + `docs/reviews/task-004-*.md`. | S→M | M | — | Несколько строк на pandas. ❌ Pandas deliberately avoided — see ARCH §6. |
```

#### File: `skills/xlsx/scripts/tests/test_json2xlsx.py`

Add the perf-test class:

```python
@unittest.skipUnless(os.environ.get("RUN_PERF_TESTS") == "1",
                     "Set RUN_PERF_TESTS=1 to run perf budget tests.")
class TestPerfBudget(unittest.TestCase):
    """Informal perf targets (NOT CI-gated). Mirrors xlsx-7 RUN_PERF_TESTS
    convention. Reviewer runs locally before merge.
    """
    def test_10k_rows_6_cols_under_3s(self):
        rows = [{"a": i, "b": i*2, "c": "x"*20, "d": True, "e": 3.14, "f": "2024-01-15"}
                for i in range(10_000)]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as inp, \
             tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as out:
            inp.write(json.dumps(rows).encode())
            inp.close()
            t0 = time.perf_counter()
            rc = convert_json_to_xlsx(inp.name, out.name)
            t1 = time.perf_counter()
        self.assertEqual(rc, 0)
        self.assertLess(t1 - t0, 3.0, f"10K-row write took {t1-t0:.2f}s, budget 3.0s")
```

### Component Integration

- This task is **finalisation only** — no behaviour changes in code. Touches only docs, AGENTS.md, backlog row, and the perf-test addition.

## Test Cases

### Unit Tests
1. `test_perf_10k_rows_skipped_without_env` — without `RUN_PERF_TESTS=1`, the perf test is reported as skipped (decoration check).
2. **(Opt-in)** `test_10k_rows_6_cols_under_3s` — runs only with `RUN_PERF_TESTS=1`.

### E2E Tests
- Existing E2E green; no new cases added in this task.

### Regression Tests
- All xlsx existing tests pass.
- **CLAUDE.md §2 boundary final check** — eleven `diff -q` invocations silent.
- `validate_skill.py skills/xlsx` exit 0.

## Acceptance Criteria

- [ ] `skills/xlsx/references/json-shapes.md` authored with all 10 sections.
- [ ] `skills/xlsx/SKILL.md` §1 + §2 updated with xlsx-2 entries.
- [ ] `skills/xlsx/scripts/.AGENTS.md` json2xlsx section expanded to the 7-module map.
- [ ] `docs/office-skills-backlog.md` xlsx-2 row marked ✅ DONE with status block.
- [ ] Perf test class scaffolded under `RUN_PERF_TESTS=1` gate (no CI gate).
- [ ] **Final gates:** `validate_skill.py` green; eleven `diff -q` silent; full unit + E2E suites green.
- [ ] LOC count of `json-shapes.md` ~ 250 LOC; no aspirational claims (every section maps to actual xlsx-2 behaviour).
- [ ] **Task-004 chain CLOSED.**

## Notes

- `references/json-shapes.md` is the **contract**, not the docs. SKILL.md is for human users; json-shapes.md is for the future xlsx-8 implementer who needs unambiguous spec.
- The §9 honest-scope subsection of json-shapes.md duplicates some content from TASK §11. That's intentional — the contract file must be self-contained; readers shouldn't have to chase cross-refs.
- xlsx-8's eventual merge commit will:
  1. Implement `xlsx2json.py` against `json-shapes.md`.
  2. Add `T-roundtrip-xlsx8-live` test in `tests/test_json2xlsx.py` (the helper `_xlsx2json_available()` from 004.08 starts returning True).
  3. NOT modify any xlsx-2 code.
  If xlsx-8's discovery work surfaces a requirement that forces a `json-shapes.md` revision, both xlsx-2 and xlsx-8 must update synchronously. The orchestrator opens an issue in the xlsx-8 task to track this risk.
- The backlog ✅ DONE marker uses date `2026-05-NN` as placeholder — the developer fills in the actual merge date on the final commit.
