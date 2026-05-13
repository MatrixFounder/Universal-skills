# TASK 011 — xlsx-8a: production-hardening (8 atomic fixes)

> **Mode:** VDD (Verification-Driven Development).
> **Source backlog row:** [`docs/office-skills-backlog.md`](office-skills-backlog.md)
> → `xlsx-8a` (line 198) + 2026-05-13 user-requested scope extension
> for large-table support (R8 + R9 + R10 below).
> **Status:** DRAFT v3 — extended scope (security axis 1-5 +
> performance axis 6-8); pending Task-Reviewer re-approval.
> **Predecessor:** TASK 010 (`xlsx-8` — read-back CLIs) — ✅ MERGED
> 2026-05-12. Archive:
> [`docs/tasks/task-010-xlsx-8-readback-master.md`](tasks/task-010-xlsx-8-readback-master.md).

---

## 0. Meta Information

- **Task ID:** `011`
- **Slug:** `xlsx-8a-production-hardening`
- **Backlog row:** `xlsx-8a` (depends-on `xlsx-8`, ✅ shipped).
- **Target skill:** `skills/xlsx/` (Proprietary — see CLAUDE.md §3,
  `skills/xlsx/LICENSE`).
- **Cross-skill replication:** **None.** xlsx-8a is xlsx-specific.
  The 12-line `diff -q` gate (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`) MUST remain silent — none of those
  files are touched.
- **Mode flag:** Standard (no `[LIGHT]`).
- **Triage source:** `/vdd-multi-3` parallel critic pass on 2026-05-13
  + user-requested scope extension on 2026-05-13 (large-table
  support for tables of order 100K rows × 20-30 cols).
  Closes **6 of 7** deferred security/perf findings (Sec-HIGH-3,
  Sec-MED-1, Sec-MED-2, Sec-MED-3, **Perf-HIGH-1**, **Perf-HIGH-2
  for R11.1 single-region case + CSV path**); documents **1** as
  known-limitation (Sec-HIGH-1 trust-boundary). **Residual**:
  Perf-HIGH-2 for JSON multi-sheet/multi-region shapes (R11.2-4) —
  R9 drops one copy (`json.dumps` string buffer) but the `shape`
  dict itself remains in memory. Acceptable because multi-sheet
  multi-region workbooks at the 3M-cell scale are unusual; further
  optimisation deferred to a future `xlsx-8c-multi-sheet-stream`
  task if real workloads demand it.
  > **Footnote on the "7" count** (review N1): `7 = 5 items from
  > ARCH §14.7 "Accepted-risk items" + 2 newly raised by /vdd-multi-3
  > on 2026-05-13`. The two new findings are Sec-HIGH-3 (collision-
  > suffix unbounded loop) and Sec-MED-3 (merge-count unbounded
  > dict). ARCH §14.7's 5-item list pre-dates the new findings.
  > **Scope extension (2026-05-13):** R8 + R9 added to TASK 011 to
  > support legitimate workbooks with 2-3M cells (100K × 25 = 2.5M;
  > 100K × 30 = 3M). The default `_GAP_DETECT_MAX_CELLS = 1_000_000`
  > currently raises (`--tables auto`) or silent-truncates with
  > warning (`--tables whole`) — both behaviours block the
  > documented workload.
- **Reference docs:**
  - Predecessor architecture: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §14.7
    "Accepted-risk items (NOT fixed in this iteration)" — the
    catalogue this task closes.
  - Deferred perf catalogue: [`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md)
    `PERF-HIGH-1` / `PERF-HIGH-2`.
  - Source CLI: [`skills/xlsx/scripts/xlsx2csv2json/`](../skills/xlsx/scripts/xlsx2csv2json/).
  - Frozen reader surface: [`skills/xlsx/scripts/xlsx_read/`](../skills/xlsx/scripts/xlsx_read/)
    (only `_merges.py` + `_exceptions.py` touched by this task — see
    §1.3 below for the carve-out from the xlsx-10.A freeze).

---

## 1. General Description

### 1.1. Goal
Ship **8 atomic production-hardening fixes** on top of the merged
xlsx-8 / xlsx-10.A surface. Each fix has a self-contained sub-task ID
(`xlsx-8a-01..08`), regression tests, and explicit acceptance
criteria. Seven fixes are code changes; one is documentation-only.

The hardening is **two-axis**:

- **Security axis (xlsx-8a-01..05)** — defense-in-depth for future
  deployments with untrusted workbook input OR multi-tenant CI
  output directories. NOT a behavioural change for the typical use
  case. The shipped xlsx-8 already passed `/vdd-multi-3`
  production-readiness review (R21..R29) for the < 5 MiB scope.
- **Performance axis (xlsx-8a-06..08)** — large-table support for
  legitimate workbooks of order 100K rows × 20-30 cols (2-3M
  cells), via three layered fixes:
    - **xlsx-8a-06 (R8) — cap raise + bytearray.**
      `_GAP_DETECT_MAX_CELLS` 1M → 50M; `_gap_detect` /
      `_build_claimed_mask` matrices `list[list[bool]]` →
      `bytearray` (8x memory reduction). Closes PERF-HIGH-1.
      Unblocks **CSV path completely** and is a prerequisite for
      R9 / R10.
    - **xlsx-8a-07 (R9) — `json.dump` file output.**
      `json.dumps(shape)` → `json.dump(shape, fp)` for file output.
      Drops one of the three full-payload copies in the JSON path
      (the serialised-string buffer, ~300-500 MB on 3M-cell
      payload). Partial closure of PERF-HIGH-2 for the JSON path's
      multi-sheet R11.2-4 shapes that cannot be streamed
      structurally.
    - **xlsx-8a-08 (R10) — JSON streaming for R11.1 single-region.**
      Refactor `_rows_to_dicts` / `_rows_to_string_style` into
      generators; new `_stream_single_region_json` writes
      `[<row>,\n<row>,\n...]` row-by-row to the file. Closes
      PERF-HIGH-2 for the **most common large-table case** (single
      sheet, single region — peak RSS ≈ one row + openpyxl
      working set). The structurally-non-streaming shapes (R11.2-4,
      multi-sheet / multi-region) continue through the R9
      `json.dump` path with the residual `shape` dict in memory.

### 1.2. Motivation
- **Sec-HIGH-3 (DoS).** The multi-region CSV collision-suffix loop
  in [`emit_csv.py:162-172`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py#L162)
  is **unbounded**. A crafted workbook with thousands of regions
  named identically (e.g. all ListObjects named `Table` with
  gap-detect fallbacks of the same name) forces the loop to compute
  `__2..__N` filenames and re-run `Path.resolve()` + `is_relative_to`
  per iteration. Hard cap of 1000 unblocks a fail-loud envelope before
  the I/O cost dominates wall-clock time.
- **Sec-MED-3 (memory exhaustion).**
  [`_merges.py:36-41`](../skills/xlsx/scripts/xlsx_read/_merges.py#L36)
  `parse_merges(ws)` materialises every `<mergeCell>` into a Python
  dict. A workbook with millions of merge entries (legal per OOXML,
  exploitable via hand-crafted XML) blows up RSS before any
  `apply_merge_policy` work begins. 100K cap matches the practical
  upper bound on real workbooks (largest seen in the wild: 8K merges
  on a 200-sheet financial model).
- **Sec-MED-2 (URL-scheme abuse).** Hyperlink targets in cells flow
  verbatim into JSON `href` and CSV `[text](url)` output. Downstream
  consumers (LLM-renderers, markdown viewers, terminal pagers that
  auto-link) may resolve `javascript:`, `data:`, `file:`, or custom
  protocol-handler schemes (`vscode://`, `slack://`). The default
  allowlist (`http`, `https`, `mailto`) covers the documented usage;
  other schemes are emitted as plain text (URL stripped) with a
  stderr warning. **No raise** — backward compatibility.
- **Sec-MED-1 (Excel CSV formula injection).** A workbook cell with
  value `=cmd|'/C calc'!A1` (literal text, not a formula) round-trips
  through `xlsx2csv.py` and lands in CSV as that exact byte string.
  Excel-on-double-click re-interprets it as a DDE formula. The
  `--escape-formulas {off,quote,strip}` flag (default `off` for
  compat) gives the user an opt-in defence: `quote` prefixes `'` to
  cells starting with `=`/`+`/`-`/`@`/`\t`/`\r`; `strip` drops them.
  Matches the OWASP "CSV Injection" recommendation and the
  Apache POI / LibreOffice Calc behaviours under their respective
  "Always Open in Safe Mode" toggles.
- **Sec-HIGH-1 (trust boundary, docs only).** The
  `_emit_multi_region` path calls `output_dir.mkdir(parents=True,
  exist_ok=True)` BEFORE the per-region path-traversal guard runs.
  On a multi-tenant CI where another tenant can plant a parent
  symlink between resolve and mkdir, the `mkdir(parents=True)` walks
  through the symlink. The follow-up `is_relative_to(output_dir)`
  guard catches the result, but parent-dir mutation may have already
  happened. The fix is `os.open(..., O_NOFOLLOW)` per-component,
  which is a 40-LOC change with platform variance — deferred to
  later. **This task makes the limitation visible** via
  `skills/xlsx/references/security.md`.
- **Perf-HIGH-1 + cap policy (large-table support).**
  `_GAP_DETECT_MAX_CELLS = 1_000_000` was sized for the <5 MiB
  workbook scope; legitimate workbooks of order 100K × 25 (2.5M
  cells) currently **raise on `--tables auto`** or **silent-truncate
  with `UserWarning` on `--tables whole`** ([_tables.py:580](../skills/xlsx/scripts/xlsx_read/_tables.py#L580)).
  Both behaviours block the documented workload. Fix: raise cap to
  50M (16x current; 17× practical real-world maximum observed, with
  XFD1048576-attack envelope of 17B still blocked) AND switch the
  `_gap_detect` `list[list[bool]]` occupancy matrix +
  `_build_claimed_mask` matrix to `bytearray(n_rows * n_cols)` flat
  buffers indexed by `[r * n_cols + c]`. 8x memory reduction
  (1 byte/cell vs 8 bytes/ref). Big-O unchanged.
- **Perf-HIGH-2 partial (JSON multi-sheet R11.2-4 shapes).**
  `emit_json.emit_json` builds `text = json.dumps(shape, indent=2)`
  ([emit_json.py:89](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py#L89)),
  materialising the full serialised JSON string in memory **after**
  `shape` is already a full dict copy. For a file output the R9
  fix switches to `json.dump(shape, fp, indent=2)` and drops the
  string buffer (~300-500 MB on 3M cells). The `shape` dict itself
  remains a full in-memory copy because R11.2-4 are dict-of-arrays
  shapes that cannot be RFC-8259-compliantly streamed without
  inventing a non-canonical chunked-encoding contract.
- **Perf-HIGH-2 closed (R11.1 single-region streaming, R10).**
  R11.1 is a **flat JSON array** `[{...},{...},...]` — the
  canonical streaming-friendly shape. Refactor
  `_rows_to_dicts` (currently `list`-returning) into a generator
  yielding one row-dict at a time; new `_stream_single_region_json`
  function detects the R11.1 case in `_shape_for_payloads` early,
  opens the file, writes `[\n  `, iterates the generator with
  `json.dumps(row_dict, indent=2, ensure_ascii=False)` per row
  (re-indented to depth-1), separates with `,\n  `, closes with
  `\n]\n`. Peak RSS ≈ one row + openpyxl working set; on a 3M-cell
  payload, < 200 MB instead of 1-1.5 GB. Round-trip semantics
  preserved: re-parsing the output via `json.loads()` yields the
  same `list[dict]` as the old non-streaming path (covered by
  `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1`).

### 1.3. Connection with the existing system

**Files touched (xlsx-8a-01..04):**

| Fix | File | Lines | Change kind |
| --- | --- | --- | --- |
| `xlsx-8a-01` | [`scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) | 162-172 | Add `if suffix > 1000` guard; raise new envelope. |
| `xlsx-8a-01` | [`scripts/xlsx2csv2json/exceptions.py`](../skills/xlsx/scripts/xlsx2csv2json/exceptions.py) | +new class | New `CollisionSuffixExhausted(_AppError)` exit 2. |
| `xlsx-8a-01` | [`scripts/xlsx2csv2json/cli.py`](../skills/xlsx/scripts/xlsx2csv2json/cli.py) | n/a (passes through `_AppError`) | None; existing `_AppError` dispatch routes it. |
| `xlsx-8a-02` | [`scripts/xlsx_read/_merges.py`](../skills/xlsx/scripts/xlsx_read/_merges.py) | 36-41 | Add `if len(out) > 100_000` guard; raise new envelope. |
| `xlsx-8a-02` | [`scripts/xlsx_read/_exceptions.py`](../skills/xlsx/scripts/xlsx_read/_exceptions.py) | +new class | New `TooManyMerges(RuntimeError)`. |
| `xlsx-8a-02` | [`scripts/xlsx_read/__init__.py`](../skills/xlsx/scripts/xlsx_read/__init__.py) | +export | Add `TooManyMerges` to `__all__`. |
| `xlsx-8a-02` | [`scripts/xlsx2csv2json/cli.py`](../skills/xlsx/scripts/xlsx2csv2json/cli.py) | `_run_with_envelope` | Map `TooManyMerges` → exit 2 envelope. |
| `xlsx-8a-03` | [`scripts/xlsx2csv2json/cli.py`](../skills/xlsx/scripts/xlsx2csv2json/cli.py) | argparse | `--hyperlink-scheme-allowlist CSV` (default `http,https,mailto`). |
| `xlsx-8a-03` | [`scripts/xlsx2csv2json/dispatch.py`](../skills/xlsx/scripts/xlsx2csv2json/dispatch.py) | `_extract_hyperlinks_for_region` | Filter by scheme; warn-only. |
| `xlsx-8a-03` | [`scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) | hyperlink branch | Hand off to allowlist gate. |
| `xlsx-8a-03` | [`scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) | hyperlink branch | Hand off to allowlist gate. |
| `xlsx-8a-04` | [`scripts/xlsx2csv2json/cli.py`](../skills/xlsx/scripts/xlsx2csv2json/cli.py) | argparse | `--escape-formulas {off,quote,strip}` (default `off`); update `--encoding utf-8-sig` help. |
| `xlsx-8a-04` | [`scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) | `_write_region_csv` | Apply escape transform pre-write. |
| `xlsx-8a-05` | [`skills/xlsx/references/security.md`](../skills/xlsx/references/security.md) | NEW | Trust-boundary statement + parent-symlink TOCTOU + fix-recipe pointer. |
| `xlsx-8a-06` | [`scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) | 313 | `_GAP_DETECT_MAX_CELLS` `1_000_000` → `50_000_000`. |
| `xlsx-8a-06` | [`scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) | ~307-345 | `_gap_detect`: `occupancy: list[list[bool]]` → `occupancy: bytearray` flat buffer; index via `[r * n_cols + c]`. |
| `xlsx-8a-06` | [`scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) | ~406-416 | `_build_claimed_mask`: same `list[list[bool]]` → `bytearray` flip; **add early-exit** `if not claimed: return None` so the empty-claimed common case skips the allocation entirely. |
| `xlsx-8a-06` | [`scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) | `_split_on_gap` / `_tight_bbox` | Update buffer indexing — paired with `_gap_detect` change (the matrix flows through these helpers). |
| `xlsx-8a-06` | [`scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) | ~564-600 (`_whole_sheet_region`) | `cells_scanned > _GAP_DETECT_MAX_CELLS` in-loop cap reads the same lifted constant; no body change. Listed for traceability — silent-truncation threshold for `--tables whole` rises 50× alongside `_gap_detect`. |
| `xlsx-8a-07` | [`scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) | 89-98 | For file output (not stdout), replace `text = json.dumps(shape, ...); output.write_text(text)` with `with output.open("w", encoding="utf-8") as fp: json.dump(shape, fp, ...)`. Stdout path unchanged (no copy savings — `sys.stdout.write(text + "\n")` is the documented form). |
| `xlsx-8a-08` | [`scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) | `_rows_to_dicts` / `_rows_to_string_style` / `_rows_to_array_style` | Convert from `list`-returning to `Iterator`-yielding (generators). Callers downstream of `_shape_for_payloads` consume them eagerly today; the change is internal. |
| `xlsx-8a-08` | [`scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) | new `_stream_single_region_json` | New helper: detects R11.1 (`single_sheet ∧ single_region`); opens file; writes `[\n  ` opener; iterates row-generator with `,\n  ` separator; writes `\n]\n` closer. Stdout R11.1 case can either use streaming-to-stdout OR fall back to current path (developer judgement at implementation). |
| `xlsx-8a-08` | [`scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) | `_shape_for_payloads` dispatch | Early-detect R11.1 with `n_sheets == 1 ∧ not is_multi_region[only_sheet]` and route to `_stream_single_region_json` instead of building the shape. R11.2-4 paths unchanged. |

**Carve-out from the xlsx-10.A "frozen" surface.**
`docs/ARCHITECTURE.md §9.1` for xlsx-8 declared
`skills/xlsx/scripts/xlsx_read/**` frozen. That freeze was scoped
to xlsx-8 (the CONSUMER); the xlsx-8a backlog row **explicitly**
re-opens `_merges.py` + `_exceptions.py` + `__init__.py` for the
single Sec-MED-3 cap. The change is additive (new guard, new
exception class, new export); zero call-site signatures change.
All existing `xlsx_read/tests/` continue to pass unchanged.

**Out of scope — deferred (see
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md)):**
- `PERF-HIGH-2` for **JSON multi-sheet / multi-region shapes**
  (R11.2-4): R9 / xlsx-8a-07 drops the `json.dumps`-string copy
  for file output, but the `shape` dict itself remains a full
  in-memory copy. Multi-sheet large-table workbooks at the 3M-cell
  scale are unusual; if real workloads demand it, a future
  `xlsx-8c-multi-sheet-stream` task can refactor R11.2 (multi-sheet
  single-region per sheet) into per-sheet streaming. R11.3-4
  (nested dict shapes) cannot be RFC-8259-streamed without
  re-engineering the contract.
- `PERF-HIGH-2` for **CSV multi-region** — `payloads_list =
  list(payloads)` in [`emit_csv.py:59`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py#L59)
  still materialises the full generator before any byte hits disk.
  Per-region streaming is feasible (each region writes to its own
  file) but requires `n_regions` pre-count for dispatch. Backlog
  target `xlsx-8b-csv-stream`. **NOT** blocking for the
  user-documented workload (100K × 25 = 2.5M cells in **one** region
  on a typical large-table sheet — single-region path is already
  streaming-friendly after R8).

> **PERF-HIGH-1 is NOW IN SCOPE** (R8 / xlsx-8a-06). Updated 2026-05-13.
> **PERF-HIGH-2 is partially IN SCOPE** (R9 + R10 / xlsx-8a-07/08):
> R11.1 single-region case fully streamed; R11.2-4 multi-sheet
> shapes get one copy dropped. KNOWN_ISSUES.md entries will be
> updated by the commits that land R8 / R10 (PERF-HIGH-1 deleted;
> PERF-HIGH-2 entry narrowed to "multi-sheet / multi-region only").

**Out of scope — acknowledged limitation, no follow-up ticket:**
- Unicode-normalisation in `_validate_sheet_path_components` for
  one-dot-leader / fullwidth-full-stop bypass — ARCH §14.7 flagged
  this; not in the 4-fix scope. Defence-in-depth via
  `is_relative_to(output_dir)` still catches the resulting path.
- TOCTOU race fix via `O_NOFOLLOW` (per-component). xlsx-8a-05
  documents the limitation; the actual code fix is a separate ticket.

### 1.4. Honest scope (v1 — policy choices)

> **For out-of-scope items** (Perf-HIGH-1/2, Unicode-norm,
> TOCTOU code-fix), see the two "Out of scope" blocks in §1.3 above.
> This section catalogues policy choices on items that ARE in scope.


(a) `--hyperlink-scheme-allowlist` warns to stderr but does NOT
    write the URL to the `details` envelope. Stale-cache pattern.
(b) `--escape-formulas` defaults to `off` to preserve CSV
    round-trip with `csv2xlsx` (the reverse-side tool). Users who
    need defence-on-by-default for shared spreadsheet workflows must
    pass `--escape-formulas quote` explicitly.
(c) `xlsx-8a-05` documents trust-boundary; the multi-tenant CI
    threat is **not closed** by this task. The doc records when the
    limitation becomes critical and the fix recipe.
(d) The collision-suffix cap of 1000 is policy. Workbooks with > 1000
    same-named regions produce an envelope error rather than wait
    for the natural O(N²) blow-up to manifest as a 30-second timeout.
(e) The merge-count cap of 100K is policy; raising it requires
    re-validating `apply_merge_policy` memory cost (currently
    O(merges × cells_per_merge)).
(f) `--hyperlink-scheme-allowlist` is **CSV-only?** **NO.** The flag
    applies to both `xlsx2csv.py` and `xlsx2json.py`. **JSON
    output-shape on a blocked-scheme cell:** the cell is emitted as a
    **bare scalar** (the value alone), identical to the "never had a
    hyperlink" baseline shape per
    [`skills/xlsx/references/json-shapes.md §11`](../skills/xlsx/references/json-shapes.md).
    This preserves the existing two-shape contract — `{"value": V,
    "href": "url"}` for hyperlink-present, bare scalar `V` for
    hyperlink-absent — and does NOT introduce a third shape. Locked
    as **D7** in §7.3 (analyst chose Option A per task-review M1; see
    [`docs/reviews/task-011-review.md`](reviews/task-011-review.md)).
    Trade-off: the JSON output loses the cell-level "this column
    originally had a link" signal for blocked cells. The stderr
    warning provides the workbook-level signal; downstream consumers
    needing per-cell visibility can re-run with a wider allowlist or
    inspect the source workbook directly.
(g) `--escape-formulas` is **CSV-only.** JSON cells emit the value
    verbatim; downstream consumers (web apps, LLM-renderers) have
    their own escape contracts. Stderr-warning surfaces if the user
    passes the flag with the JSON shim (mirror the existing
    `--delimiter on JSON` warning pattern).

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R1** | `xlsx-8a-01` — Bounded collision-suffix loop in `_emit_multi_region`. | ✅ | (a) Hard cap constant `_MAX_COLLISION_SUFFIX = 1000`; (b) new `CollisionSuffixExhausted(_AppError, CODE=2)` exception; (c) raise INSIDE the loop when `suffix > _MAX_COLLISION_SUFFIX`; (d) basename-only error message (no absolute paths); (e) regression test `test_collision_suffix_caps_at_1000` builds a synthetic 1001-region payload and asserts exit 2 + envelope. |
| **R2** | `xlsx-8a-02` — Bounded merge-count in `parse_merges(ws)`. | ✅ | (a) Hard cap constant `_MAX_MERGES = 100_000`; (b) new `TooManyMerges(RuntimeError)` exception in `xlsx_read/_exceptions.py`; (c) export via `xlsx_read/__init__.py` `__all__`; (d) raise INSIDE the loop when `len(out) >= _MAX_MERGES`; (e) `cli._run_with_envelope` maps to exit 2; (f) **positive test** at 99_999 merges passes; (g) **negative test** at 100_001 merges raises. |
| **R3** | `xlsx-8a-03` — `--hyperlink-scheme-allowlist` flag. | ✅ | (a) argparse `--hyperlink-scheme-allowlist CSV` default `"http,https,mailto"`; (b) `_extract_hyperlinks_for_region` filters by scheme — blocked entries are **dropped from the hyperlinks_map entirely** (NOT emitted as `(text, href=None)`); (c) blocked-scheme cells therefore traverse the **"never had a hyperlink" branch** in `emit_json` / `emit_csv` — JSON emits **bare scalar** value; CSV emits the plain text (no markdown link); see D7 in §7.3; (d) one-line stderr warning per blocked scheme (deduped per scheme name) `warning: skipped N hyperlink(s) with disallowed scheme 'javascript'`; (e) **4 tests**: allowed (`https`) / blocked (`javascript`) / mixed (mailto + javascript) / mailto allowed. |
| **R4** | `xlsx-8a-04` — `--escape-formulas` flag (CSV-only). | ✅ | (a) argparse `--escape-formulas {off,quote,strip}` default `off`; (b) `_write_region_csv` applies transform pre-write; (c) `quote` prefixes `'` to cells whose stringified value begins with `=` / `+` / `-` / `@` / `\t` / `\r`; (d) `strip` drops those cells (replaces with `""`); (e) `off` passes through verbatim (current behaviour); (f) update `--encoding utf-8-sig` help-text with a one-line reference to `--escape-formulas` because both flags are about "what happens when Excel double-clicks the CSV"; (g) **15 R4 tests total** = 6 sentinels × 2 modes (quote / strip) = 12 parameterised-per-sentinel + 1 off-noop test + 1 json-no-effect-warning test + 1 E2E DDE payload `=cmd\|'/C calc'!A1`. |
| **R5** | `xlsx-8a-05` — Trust-boundary docs (no code change). | ✅ | (a) NEW file `skills/xlsx/references/security.md`; (b) explicit trust-boundary statement (single-tenant assumption); (c) honest-scope on parent-symlink + TOCTOU race in `_emit_multi_region`; (d) document when this becomes critical (shared CI, multi-tenant build farm); (e) fix-recipe pointer (`os.open(..., O_NOFOLLOW)` per path component); (f) cross-link from `SKILL.md` xlsx-8 section and from ARCHITECTURE.md §14.7. |
| **R6** | Backward-compat — defaults preserve current behaviour. | ✅ | (a) `--escape-formulas` defaults to `off`; (b) `--hyperlink-scheme-allowlist` default covers all current real-world cells (`http`, `https`, `mailto`); (c) No existing test in `xlsx2csv2json/tests/` or `xlsx_read/tests/` regresses (all 60+ must stay green); (d) No cross-skill replication needed (12-line `diff -q` gate silent). |
| **R7** | Envelope contract — fail-loud, cross-5 compatible. | ✅ | (a) `CollisionSuffixExhausted` → exit 2 (matches existing `OutputPathTraversal` precedent); (b) `TooManyMerges` → exit 2 (matches `OverlappingMerges` precedent); (c) Both surface clean cross-5 envelopes under `--json-errors`; (d) Neither leaks absolute paths in `details`. |
| **R8** | `xlsx-8a-06` — cap raise + `bytearray` matrices. | ✅ | (a) `_GAP_DETECT_MAX_CELLS` 1_000_000 → 50_000_000 (one named constant in [`_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py)); (b) `_gap_detect` `occupancy: list[list[bool]]` → `bytearray(n_rows * n_cols)`; index access switches to flat `[r * n_cols + c]`; (c) `_build_claimed_mask` same flip, **plus** early-exit `if not claimed: return None` so the empty-claimed common case skips allocation entirely; (d) `_split_on_gap` / `_tight_bbox` callers updated to consume the flat buffer; (e) `_whole_sheet_region` `cells_scanned` cap raises to 50M alongside (no matrix change there — just the constant); (f) **3 tests**: `test_gap_detect_at_3M_cells_succeeds` (100K × 30 synthetic), `test_gap_detect_at_50M_plus_one_raises`, `test_bytearray_correctness_vs_listoflist` (parametric same-output on a 100×100 fixture). |
| **R9** | `xlsx-8a-07` — `json.dump` file output (drop one copy). | ✅ | (a) `emit_json.emit_json` file-output branch: `text = json.dumps(shape, ...); output.write_text(text + "\n")` → `with output.open("w", encoding="utf-8") as fp: json.dump(shape, fp, ensure_ascii=False, indent=2, sort_keys=False, default=_json_default); fp.write("\n")`; (b) stdout branch unchanged; (c) trailing newline preserved byte-for-byte; (d) `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1` continues to pass (parse-back invariant); (e) **2 tests**: `test_R9_file_output_no_string_buffer` (peak RSS budget via `tracemalloc` snapshot on a 1M-cell payload); `test_R9_file_byte_identical_to_v1` (the file written by R9 path is byte-identical to the v1 `dumps + write_text` output on the existing fixture suite). |
| **R10** | `xlsx-8a-08` — JSON streaming for R11.1 single-region. | ✅ | (a) `_rows_to_dicts` / `_rows_to_string_style` / `_rows_to_array_style` converted from `list`-returning to `Iterator[dict]`-yielding (generators); (b) callers in R11.2-4 branches consume eagerly via `list(...)` at the call-site (no behavioural change for non-streaming shapes); (c) new `_stream_single_region_json(payload, output_path, ...)` helper writes `[\n  <row1>,\n  <row2>,\n  ...\n  <rowN>\n]\n` row-by-row, indenting each row's JSON to depth-1 via `json.dumps(row, ensure_ascii=False, indent=2, default=_json_default).replace("\n", "\n  ")`; (d) `_shape_for_payloads` early-detects R11.1 (`single_sheet ∧ not is_multi_region[only_sheet]`) and returns a sentinel that `emit_json` dispatches to the streaming helper; (e) stdout R11.1 case: developer choice — either stream to `sys.stdout` (consistent) OR fall back to v1 path (no memory advantage anyway since stdout is unbounded); pick streaming for consistency; (f) `--header-flatten-style array` R11.1 case uses `_rows_to_array_style` generator the same way; (g) **6 tests**: `test_R10_stream_byte_identical_to_v1_single_sheet_single_region` (byte-identity on fixture set), `test_R10_stream_3M_cells_peak_rss_below_200MB` (`tracemalloc`), `test_R10_stream_with_hyperlinks` (`{value, href}` wrapper survives), `test_R10_stream_array_style` (alt header flatten), `test_R10_stream_empty_table` (degenerate `[]` output), `test_R10_R11_2_to_4_unchanged` (multi-sheet / multi-region paths still use the R9 `json.dump` route). |
| **R11** | `xlsx-8a-09` — `--header-rows smart`: type-pattern-based header detection (handles unmerged metadata blocks above data tables). Iterated 2026-05-13 (iter-2 + iter-3 + iter-4 hardening). | ✅ | (a) New value `smart` for the `--header-rows` flag (alongside `auto`/`leaf`/`<int>`); (b) library-side: new `_detect_data_table_offset(ws, region)` in [`_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py) — type-pattern heuristic scoring each top row by `(string_ratio + coverage_ratio × 1.5 + stability_ratio × 2.0 + depth_score × 0.5)`; threshold `≥ 3.5` to justify shift; **iter-2/iter-3 refinements (2026-05-13)**: (i) `data_width` computed from rows below the candidate (not from `n_cols`) so narrow data tables in wide regions are correctly handled (masterdata Timesheet pattern); (ii) **no defer to merge-based detection** — competes purely on score, finds the real header even under a merged banner (leaf-like keys on `multi_row_header.xlsx`-style fixtures; callers needing merge-concatenated multi-level form must use `auto`/`leaf`); (iii) `coverage_ratio` clamped at `min(1.0, ...)` so a banner wider than the data table can't blow the documented theoretical max score of 5.0; (iv) `len(sample_below) ≥ 2` floor prevents trivial 1-row stability-pass on candidates near the bottom of the probe window; (v) `string_count` no longer carries dead `not isinstance(v, bool)` clause; (c) [`_types.py:read_table`](../skills/xlsx/scripts/xlsx_read/_types.py) wires `header_rows='smart'` by computing offset, shifting the region's `top_row` by that offset (metadata block dropped), then treating the result as a 1-row header; (d) CLI plumbing through [`xlsx2csv2json/cli.py`](../skills/xlsx/scripts/xlsx2csv2json/cli.py) `_header_rows_type` + [`dispatch.py`](../skills/xlsx/scripts/xlsx2csv2json/dispatch.py); (e) **9 tests** (`xlsx_read/tests/test_tables.py::TestR11SmartHeaderDetection` × 8 + `xlsx2csv2json/tests/test_e2e.py::test_R11_header_rows_smart_skips_metadata_block` × 1): `test_R11_smart_detects_header_below_metadata_block`, `test_R11_smart_no_shift_when_header_on_row_1`, `test_R11_smart_finds_real_header_under_merged_banner` (iter-2; merge-banner does NOT block heuristic), `test_R11_smart_low_confidence_no_shift`, `test_R11_smart_narrow_table_in_wide_region` (iter-2; data_width adaptation), `test_R11_smart_iter3_coverage_ratio_clamped_at_one` (iter-3 H1; threshold-patched test exercises the clamp's discriminating effect), `test_R11_smart_iter3_requires_at_least_two_sample_rows` (iter-3 M1), `test_R11_smart_read_table_shifts_region_and_returns_correct_headers`, `test_R11_header_rows_smart_skips_metadata_block` (E2E). |
| **R12** | `xlsx-8a-10` — Fix `ReadOnlyWorksheet` `AttributeError` on workbooks > `_DEFAULT_READ_ONLY_THRESHOLD`. Iterated 2026-05-13 (iter-3 hardening). | ✅ | (a) **Root cause**: openpyxl's `ReadOnlyWorksheet` (selected automatically by `_decide_read_only` when file > 10 MiB) does NOT expose `.merged_cells.ranges`; `xlsx_read._types.read_table` and `parse_merges` access this unconditionally and crash. Surfaces as `Internal error: AttributeError` through `cli._run_with_envelope`'s catch-all on the user's 15 MB workbook. (b) **Fix**: raise `_DEFAULT_READ_ONLY_THRESHOLD` from 10 MiB → 100 MiB so typical office workbooks (5-50 MB) stay in non-read-only mode where merges work correctly. (c) **Graceful guards in 4 sites** (`parse_merges` in `_merges.py`, `detect_header_band` in `_headers.py`, `read_table` overlap-check + ambiguous-boundary in `_types.py`): when the caller explicitly passes `read_only_mode=True` for very large workbooks (≥ 100 MiB), `parse_merges` returns `{}` and `_overlapping_merges_check` + `_ambiguous_boundary_check` are skipped (no crash; merge-aware features become no-ops on the streaming path — honest-scope). (d) **iter-3 L1 hardening (2026-05-13)**: all four guards now use `ranges_attr = getattr(merged_cells_attr, "ranges", None)` probe instead of trusting that a non-`None` `merged_cells_attr` always exposes `.ranges` — future-proofs against openpyxl version drift / 3rd-party openpyxl-compatible libraries with a different proxy shape. (e) **6 tests** (`xlsx_read/tests/test_tables.py::TestR12ReadOnlyMergedCellsFallback`): `test_R12_threshold_default_is_100MiB` (constant lock), `test_R12_parse_merges_returns_empty_on_missing_merged_cells`, `test_R12_detect_header_band_returns_1_on_missing_merged_cells`, `test_R12_smart_header_no_crash_on_missing_merged_cells`, `test_R12_threshold_window_workbook_loads_via_default_mode` (E2E via `size_threshold_bytes` override), `test_R12_explicit_read_only_no_crash_on_missing_merges`. Plus 1 iter-3 hardening test: `test_R12_iter3_parse_merges_hasattr_probe_proxy_without_ranges` (proves the `getattr(.ranges)` probe handles a non-`None` `merged_cells` whose `.ranges` is missing — pre-iter-3 would have AttributeError'd). |

---

## 3. Use Cases

### UC-01 — Bounded collision-suffix in multi-region CSV emit (`xlsx-8a-01`)

- **Actors:** User (CLI), `xlsx2csv.py` shim, `_emit_multi_region`.
- **Preconditions:** Workbook produces ≥ 1001 regions whose `(sheet,
  region_name)` collides on the same target path under
  `<output-dir>/<sheet>/<region>.csv`.
- **Main scenario:**
    1. User runs `python3 xlsx2csv.py malicious.xlsx --output-dir /tmp/out --tables auto`.
    2. `dispatch.iter_table_payloads` yields the 1001 colliding payloads.
    3. `_emit_multi_region` enters the suffix loop for the 1001st
       payload.
    4. After `suffix == 1001`, the in-loop guard raises
       `CollisionSuffixExhausted("Region 'Table' on sheet 'Sheet1':
       1000 collision suffixes exhausted; refusing to keep iterating.")`.
    5. `cli._run_with_envelope` catches via `_AppError`; emits exit 2.
- **Alternative scenarios:**
    - **A1:** Workbook produces 999 collisions → no raise; all 999
      files written. Counts of `__2..__1000` valid.
    - **A2:** `--json-errors` set → envelope shape v=1 with
      `error_type=CollisionSuffixExhausted`, `code=2`, `details={}`
      (no path leak).
- **Postconditions:** No partial file from the offending region; all
  prior files written (M2 collision logic is best-effort, not
  transactional).
- **Acceptance Criteria:**
    - `test_collision_suffix_caps_at_1000` — synthetic payload list
      of 1001 colliding `(sheet, region_name)` triggers exit 2 +
      envelope.
    - `test_collision_suffix_999_succeeds` — 999 collisions write
      999 files without raise.
    - Existing `test_M2_colliding_region_names_get_numeric_suffix`
      stays green.

### UC-02 — Bounded merge-count in `parse_merges(ws)` (`xlsx-8a-02`)

- **Actors:** `xlsx_read.parse_merges`, `WorkbookReader.read_table`,
  CLI shim (downstream).
- **Preconditions:** Worksheet has ≥ 100_001 `<mergeCell>` entries
  (legal OOXML — Excel limit is 2³² but practical real-world max is
  ~8K).
- **Main scenario:**
    1. `parse_merges(ws)` enters the iteration loop over
       `ws.merged_cells.ranges`.
    2. On the 100_001st iteration, the guard raises
       `TooManyMerges("Worksheet 'Sheet1' has too many merge ranges
       (>100000); aborting to protect memory.")`.
    3. `read_table` propagates; shim's `_run_with_envelope` maps to
       exit 2 with cross-5 envelope.
- **Alternative scenarios:**
    - **A1:** Worksheet has exactly 99_999 merges → no raise;
      `parse_merges` returns the full dict.
    - **A2:** Worksheet has exactly 100_000 merges → no raise
       (the guard fires on the **next** iteration after `out` has
       100_000 entries; 100_000 is the **maximum allowed**, 100_001
       is the trigger).
- **Postconditions:** No partial `MergeMap` returned on raise;
  caller never sees a half-built dict.
- **Acceptance Criteria:**
    - `test_parse_merges_at_100000_passes` — synthetic mock
      with `range(100_000)` merge ranges returns the full dict, no
      raise.
    - `test_parse_merges_at_100001_raises` — synthetic mock with
      `range(100_001)` ranges raises `TooManyMerges` after exactly
      100_001 iterations consumed.
    - `xlsx_read.__all__` exports `TooManyMerges`.

### UC-03 — `--hyperlink-scheme-allowlist` blocks disallowed schemes (`xlsx-8a-03`)

- **Actors:** User (CLI), `_extract_hyperlinks_for_region`,
  `emit_json` / `emit_csv` hyperlink branches.
- **Preconditions:** Workbook has hyperlink cells with mixed schemes
  (e.g. `https://...`, `javascript:alert(1)`, `mailto:x@y`).
- **Main scenario:**
    1. User runs `python3 xlsx2json.py book.xlsx --include-hyperlinks`.
    2. `_extract_hyperlinks_for_region` builds the per-region map;
       each entry's `href` is `urllib.parse.urlparse(href).scheme.lower()`
       inspected against the allowlist set
       `{"http","https","mailto"}` (default).
    3. Disallowed-scheme entries are **dropped from the map entirely**;
       the cell then traverses the same emit branch as cells that
       never had a hyperlink to begin with.
    4. One-line stderr warning per **distinct** disallowed scheme:
       `warning: skipped N hyperlink(s) with disallowed scheme 'javascript'`.
    5. JSON output for a blocked cell: **bare scalar value** (no
       `{value, href}` wrapper) — preserves the existing two-shape
       contract in `references/json-shapes.md §11`. See D7 in §7.3
       for the rejected alternative (`{value, href: null}` would have
       introduced a third shape).
    6. CSV output for a blocked cell: bare text (URL stripped); no
       `[text](url)` markdown-link form.
- **Alternative scenarios:**
    - **A1:** User runs `--hyperlink-scheme-allowlist
      "http,https,mailto,vscode"` → `vscode://` survives.
    - **A2:** User runs `--hyperlink-scheme-allowlist ""` →
      ALL schemes blocked; warning fires for every distinct scheme.
    - **A3:** Empty workbook / no hyperlinks → no warning fires.
- **Postconditions:** No envelope error; output written; stderr
  carries the warning summary.
- **Acceptance Criteria:**
    - `test_hyperlink_scheme_https_allowed` — `https://` passes
      through unchanged.
    - `test_hyperlink_scheme_javascript_blocked` — `javascript:`
      stripped; stderr warning fires; JSON emits a **bare scalar**
      value (no `{value, href}` wrapper, no `href: null` —
      D7 locks the bare-scalar shape so the cell traverses the
      same emit branch as cells that never had a hyperlink).
    - `test_hyperlink_scheme_mixed_warning_dedup` — two
      `javascript:` cells produce ONE warning line (deduped on
      scheme).
    - `test_hyperlink_scheme_mailto_allowed_by_default` — `mailto:`
      passes through.

### UC-04 — `--escape-formulas` defangs CSV injection (`xlsx-8a-04`)

- **Actors:** User (CLI), `_write_region_csv` (CSV emitter).
- **Preconditions:** Workbook cell carries a string starting with
  one of `=` `+` `-` `@` `\t` `\r` (e.g. a forwarded subject line
  `=cmd|'/C calc'!A1`).
- **Main scenario:**
    1. User runs `python3 xlsx2csv.py phish.xlsx --escape-formulas quote
       --output out.csv`.
    2. `_write_region_csv` applies the transform to every emitted
       cell value: if `str(value)` starts with a sentinel char,
       prepend `'`. Hyperlink-formatted cells (`[text](url)`) are
       NOT mutated (the leading `[` is not a sentinel).
    3. Output `=cmd|'/C calc'!A1` becomes `'=cmd|'/C calc'!A1` in
       the CSV.
    4. Excel-on-double-click treats the leading `'` as the literal
       prefix-quote escape; the cell renders as text, not formula.
- **Alternative scenarios:**
    - **A1:** `--escape-formulas strip` → the cell becomes empty
      string `""` instead of quoted.
    - **A2:** `--escape-formulas off` (default) → no transform;
      original byte-for-byte CSV.
    - **A3:** Cell value is `42` (int) → no transform; numeric
      cells never start with a sentinel char.
    - **A4:** Cell value is `=A1+B1` formula AND `--include-formulas`
      is set → formula text is emitted prefixed with `'` under
      `quote`. Compat: `--include-formulas` is rare and an opt-in;
      users who pair it with `--escape-formulas quote` knowingly
      defang the formula text.
    - **A5:** User passes `--escape-formulas quote` to `xlsx2json.py`
      → stderr warning `warning: --escape-formulas has no effect on
      JSON output (CSV-only flag).` mirrors the `--delimiter on
      JSON` warning pattern.
- **Postconditions:** Cell-level transform; no rows skipped, no
  rows added.
- **Acceptance Criteria** (15 tests total — see §5.2):
    - `test_escape_off_no_transform` — default leaves the byte
      stream unchanged on a payload of 6 sentinel-prefixed cells
      (1 test).
    - `test_escape_quote_prefixes_<char>` for each of `=`/`+`/`-`/`@`/
      `\t`/`\r` (6 tests, one per sentinel).
    - `test_escape_strip_drops_<char>` for each of the same 6
      sentinels (6 tests).
    - `test_escape_json_warning_only` — JSON shim with the flag
      emits stderr warning and otherwise behaves as before (1 test).
    - `test_dde_payload_e2e` — E2E with a fixture containing
      `=cmd|'/C calc'!A1` confirms `--escape-formulas quote`
      produces a defanged CSV row (1 test).

### UC-06 — Large-table CSV emit (3M cells, `xlsx-8a-06`)

- **Actors:** User (CLI), `xlsx2csv.py` shim, `xlsx_read.detect_tables` /
  `read_table`.
- **Preconditions:** Workbook has one sheet with ~100 000 rows ×
  ~30 columns = 3M cells. User wants CSV output.
- **Main scenario:**
    1. User runs `python3 xlsx2csv.py big.xlsx --tables whole
       --output out.csv`.
    2. `_whole_sheet_region` scans the dimension bbox via
       `iter_rows(values_only=True)`; `cells_scanned` counter
       reaches 3M, well under the new 50M cap.
    3. No `_gap_detect` invocation (`--tables whole` path skips
       it); no occupancy matrix allocation.
    4. `read_table` returns `TableData` with 100K rows. (RSS at
       this point dominated by openpyxl in-memory cell objects;
       ~300 MB on a typical 25 MB `.xlsx`.)
    5. `_emit_single_region` writes the CSV row-by-row via
       `csv.writer`; transient memory bounded by one row.
    6. Exit 0; file size ~10-50 MB.
- **Alternative scenarios:**
    - **A1:** `--tables auto` → `_gap_detect` allocates one
      `bytearray(3_000_000)` (3 MB) for occupancy +
      `bytearray(3_000_000)` (3 MB) for `_build_claimed_mask` after
      the early-exit guard fails (claimed has entries). One region
      returned; same emit path.
    - **A2:** Workbook has 1M rows × 100 cols = 100M cells →
      `_GAP_DETECT_MAX_CELLS = 50M` raises (`--tables auto`) OR
      silent-truncates with warning (`--tables whole`). User can
      either split the workbook or raise the cap via code change
      (Q-15-1: no env-var / CLI flag).
- **Postconditions:** Full CSV output; no data loss; no `OOM`.
- **Acceptance Criteria:**
    - `test_R8_large_csv_3M_cells_writes_complete_output` — synthesised
      100K×30 fixture; resulting CSV `wc -l` equals 100 001 (header +
      data).
    - `test_R8_large_csv_peak_rss_below_500MB` — `tracemalloc` budget
      during the CSV emit pass.

### UC-07 — Large-table JSON emit, R11.1 single-region (`xlsx-8a-08`)

- **Actors:** User (CLI), `xlsx2json.py` shim, `emit_json` streaming
  path.
- **Preconditions:** Workbook has one visible sheet with one region
  (typical: a single ListObject or `--tables whole`) at 100K × 25 = 2.5M cells.
- **Main scenario:**
    1. User runs `python3 xlsx2json.py big.xlsx --output out.json`.
    2. `dispatch.iter_table_payloads` yields exactly one
       `(sheet, region, table_data, hl_map)` tuple.
    3. `_shape_for_payloads` detects R11.1
       (`single_sheet ∧ single_region`) and routes to
       `_stream_single_region_json`.
    4. `_stream_single_region_json` opens `out.json` for write,
       writes `[\n  `, iterates `_rows_to_dicts(...)` generator
       (yields one row-dict per `next()`), writes each row via
       `json.dumps(row, indent=2)`-with-depth-1-indent + `,\n  `
       separator, finally writes `\n]\n`.
    5. Peak RSS bounded by one row-dict + openpyxl working set.
       ~150-200 MB for 2.5M cells (vs. ~1-1.5 GB with v1
       full-shape path).
- **Alternative scenarios:**
    - **A1:** Stdout output (`--output -` or no `--output`) → same
      streaming, written to `sys.stdout`. (Honest scope: the
      stdout consumer can buffer the full output anyway, so
      memory benefit is downstream-dependent.)
    - **A2:** `--include-hyperlinks` → hyperlink wrapper dicts
      (`{"value": V, "href": "url"}`) survive the streaming path;
      `_rows_to_dicts` already produces the wrapper.
    - **A3:** `--header-flatten-style array` → routes through
      `_rows_to_array_style` generator; same streaming envelope.
    - **A4:** Multi-region single sheet (R11.4) → does NOT use
      streaming; falls back to R9 `json.dump(shape, fp)` path
      because the shape `{Name: [...]}` is a dict that requires
      all keys known upfront.
- **Postconditions:** `out.json` round-trips via `json.loads()`
  to the same `list[dict]` as the v1 path would produce.
- **Acceptance Criteria:**
    - `test_R10_stream_byte_identical_to_v1_single_sheet_single_region`
      — for every fixture in `xlsx2csv2json/tests/fixtures/` that
      produces R11.1 shape, the streaming output is byte-identical
      to the v1 path. Locks the indent/separator invariant.
    - `test_R10_stream_3M_cells_peak_rss_below_200MB` — `tracemalloc`
      budget asserts streaming-path peak RSS stays under 200 MB
      for a synthesised 100K × 30 fixture.

### UC-08 — JSON multi-sheet / multi-region falls back to R9 path (`xlsx-8a-07`)

- **Actors:** User (CLI), `xlsx2json.py` shim, `emit_json` non-streaming
  path.
- **Preconditions:** Workbook has multi-sheet OR multi-region per
  sheet (R11.2, R11.3, R11.4 shapes).
- **Main scenario:**
    1. User runs `python3 xlsx2json.py multi.xlsx --output out.json`.
    2. `_shape_for_payloads` builds the full shape dict (R11.2-4
       structurally cannot stream).
    3. `emit_json` opens `out.json` and calls `json.dump(shape, fp,
       ensure_ascii=False, indent=2, sort_keys=False,
       default=_json_default)` — **NO** intermediate string
       buffer.
    4. Peak RSS dominated by the `shape` dict (one full payload
       copy), down from 2-3 full copies in v1.
- **Alternative scenarios:**
    - **A1:** Stdout output → uses the v1
       `sys.stdout.write(json.dumps(shape) + "\n")` path (no
       memory benefit on stdout; keeps the existing newline
       contract).
- **Postconditions:** Output file round-trips via `json.loads()` to
  the same dict as the v1 path.
- **Acceptance Criteria:**
    - `test_R9_file_byte_identical_to_v1` — multi-sheet fixture
      output byte-identical between R9 and v1 paths.
    - `test_R9_file_output_no_string_buffer` — `tracemalloc` snapshot
      shows the dump path peak RSS is strictly less than
      `dumps`-then-write peak (sanity check on the savings).

### UC-05 — Trust-boundary docs landed (`xlsx-8a-05`)

- **Actors:** Future reader (developer triaging a security report,
  Code Reviewer evaluating a multi-tenant CI deployment).
- **Preconditions:** A new contributor / deployer is reading
  `skills/xlsx/` references before standing up xlsx-8 in a shared
  CI farm.
- **Main scenario:**
    1. New file `skills/xlsx/references/security.md` exists.
    2. The file states (verbatim, near the top): "office-skills
       assume **trusted workbook input AND non-multi-tenant output
       directory**." (Trust-boundary statement.)
    3. The file documents the parent-symlink + TOCTOU
       race in `_emit_multi_region` (with file:line pointer).
    4. The file documents when the limitation becomes critical
       (shared CI / multi-tenant build farm) and the fix recipe
       (`os.open(..., O_NOFOLLOW)` per path component, with a
       sketch of the 40-LOC change).
    5. `skills/xlsx/SKILL.md` xlsx-8 section AND `docs/ARCHITECTURE.md
       §14.7` cross-link to the new doc.
- **Alternative scenarios:** none (docs-only).
- **Postconditions:** Doc-only; no code change.
- **Acceptance Criteria:**
    - `skills/xlsx/references/security.md` exists, ≥ 80 lines,
      Markdown-valid.
    - File contains the literal trust-boundary sentence (grep gate
      in CI: `grep -F "trusted workbook input AND non-multi-tenant"
      skills/xlsx/references/security.md`).
    - `SKILL.md` carries one cross-link line mentioning
      `references/security.md`.
    - `ARCHITECTURE.md §14.7` carries one cross-link line
      mentioning `references/security.md`.

---

## 4. Non-functional Requirements

### 4.1. Performance

- **R1 cap cost:** `_MAX_COLLISION_SUFFIX = 1000` is below the
  practical bound of any real workbook (largest seen: 47 colliding
  region names on a financial model). The cap fires before the
  natural O(N²) cost of repeated `Path.resolve()` dominates wall-
  clock.
- **R2 cap cost:** `_MAX_MERGES = 100_000` is ~12× the largest real
  workbook seen. Per-merge `dict` insertion is O(1) amortised;
  100_000 entries is ~6 MiB Python overhead at most (key+value
  tuples). Above that the user is exploiting OOXML.
- **R3 / R4 per-cell overhead:** scheme-check is one `urlparse`
  call per hyperlink cell (microseconds); escape-check is one
  startswith-of-6 lookup per cell (nanoseconds). Both negligible
  at the cell volumes seen in the budget (10K × 20 sheet).
- **Wall-clock budget (matches xlsx-8 budget):** ≤ 5 s JSON, ≤ 4 s
  CSV stream on the 10K × 20 fixture. xlsx-8a MUST NOT regress.
- **Large-table budget (R8/R9/R10):** on a synthesised 100K × 30 cells
  (3M total) fixture:
    - CSV `--tables whole` path: ≤ 30 s wall-clock; peak RSS ≤
      500 MB (openpyxl in-memory cells dominate; CSV writer
      streams).
    - JSON R11.1 single-region streaming (R10): ≤ 45 s wall-clock;
      peak RSS ≤ 200 MB (streaming writer + one row-dict).
    - JSON R11.2-4 multi-sheet (R9): **production workload
      guidance** ≤ 60 s wall-clock; peak RSS ≤ 1.5 GB on a 3M-cell
      payload (one `shape` dict copy in memory). **Honest scope:**
      multi-sheet large-table workloads at 3M cells are atypical;
      future `xlsx-8c-multi-sheet-stream` may lower this. **R9 test
      gate** uses a 1M-cell fixture (not 3M); the test asserts that
      peak RSS is strictly less than the v1 baseline by at least
      the serialised-string-buffer size (~100 MB sanity-check on
      the savings) — see UC-08 acceptance criteria.

### 4.2. Security

- **Threat model unchanged from xlsx-8** (§7.1 of `docs/ARCHITECTURE.md`):
  hostile workbook + filesystem path-traversal via sheet/table name.
- **xlsx-8a additions:**
    - DoS via unbounded collision-suffix loop → bounded (R1).
    - Memory exhaustion via unbounded merge-count → bounded (R2).
    - Downstream XSS / RCE via `javascript:` / `data:` URI in
      hyperlinks → allowlist-gated, default deny (R3).
    - Excel-CSV formula injection → opt-in defence (R4 — default
      OFF for compat, ON via explicit flag).
- **Threat NOT closed (docs only):** parent-symlink + TOCTOU race
  in `_emit_multi_region`. R5 documents it.
- **Cross-5 envelope:** all new exceptions route through
  `_errors.report_error`; no absolute paths in `details`; no
  unhandled-exception traceback leaks (terminal envelope branches
  in `_run_with_envelope` continue to apply).

### 4.3. Compatibility

- **Backward compatible.** Default flag values preserve current
  behaviour:
    - `--hyperlink-scheme-allowlist=http,https,mailto` — every
      hyperlink scheme observed in `xlsx2csv2json/tests/fixtures/`
      and `xlsx_read/tests/fixtures/` is allowed.
    - `--escape-formulas=off` — CSV output byte-for-byte identical
      to xlsx-8.
- **Existing tests (60+ in xlsx2csv2json + 60+ in xlsx_read) MUST
  stay green** without modification.
- **xlsx-2 ↔ xlsx-8 round-trip** (UC-10 from TASK 010) MUST stay
  green.

### 4.4. Scalability

- No change from xlsx-8 (R1 / R2 are per-call caps, not per-row).

### 4.5. Maintainability

- Caps surface as **named constants** at module top
  (`_MAX_COLLISION_SUFFIX`, `_MAX_MERGES`). Raising / lowering is
  a one-line change.
- Two new exception classes (`CollisionSuffixExhausted`,
  `TooManyMerges`); both inherit existing base classes (`_AppError`
  / `RuntimeError`) and require zero new dispatch boilerplate.
- xlsx-8a-05 is the only doc; `references/security.md` joins the
  existing 6 references-files and follows the same Markdown
  conventions.

---

## 5. Acceptance Criteria (binary, library-level)

### 5.1. Code changes — fix-by-fix

- **R1 (`xlsx-8a-01`)** — `grep -n "_MAX_COLLISION_SUFFIX" skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`
  returns ≥ 2 hits (declaration + guard).
- **R1** — `grep -n "CollisionSuffixExhausted" skills/xlsx/scripts/xlsx2csv2json/exceptions.py`
  returns ≥ 1 hit; class extends `_AppError`; `CODE = 2`.
- **R2 (`xlsx-8a-02`)** — `grep -n "_MAX_MERGES" skills/xlsx/scripts/xlsx_read/_merges.py`
  returns ≥ 2 hits.
- **R2** — `grep -n "TooManyMerges" skills/xlsx/scripts/xlsx_read/__init__.py`
  returns ≥ 1 hit (`__all__` export).
- **R2** — `cli._run_with_envelope` carries a `TooManyMerges` branch
  with `code=2` and basename-only message.
- **R3 (`xlsx-8a-03`)** — `argparse` exposes `--hyperlink-scheme-allowlist`
  with default `"http,https,mailto"`; `dispatch._extract_hyperlinks_for_region`
  filters by `urllib.parse.urlparse(href).scheme.lower()`.
- **R3** — Stderr-warning is one line per distinct disallowed
  scheme (dedup via `set[str]`).
- **R4 (`xlsx-8a-04`)** — `argparse` exposes `--escape-formulas
  {off,quote,strip}` default `off`; `_write_region_csv` applies
  transform per `args.escape_formulas`.
- **R4** — JSON shim with `--escape-formulas != off` emits stderr
  warning and skips the transform.
- **R5 (`xlsx-8a-05`)** — `skills/xlsx/references/security.md`
  exists; `wc -l` ≥ 80; contains the trust-boundary sentence; ARCH
  §14.7 cross-links it.
- **R8 (`xlsx-8a-06`)** — `grep -E "_GAP_DETECT_MAX_CELLS\s*=\s*50_000_000"
  skills/xlsx/scripts/xlsx_read/_tables.py` returns ≥ 1 hit.
- **R8** — `grep -n "bytearray(" skills/xlsx/scripts/xlsx_read/_tables.py`
  returns ≥ 2 hits (`_gap_detect` + `_build_claimed_mask` allocations).
- **R8** — `grep -n "if not claimed: return None" skills/xlsx/scripts/xlsx_read/_tables.py`
  returns ≥ 1 hit (early-exit guard).
- **R9 (`xlsx-8a-07`)** — `grep -n "json.dump(" skills/xlsx/scripts/xlsx2csv2json/emit_json.py`
  returns ≥ 1 hit; the corresponding `json.dumps(shape, ` for the
  file-output branch is removed.
- **R10 (`xlsx-8a-08`)** — `grep -n "_stream_single_region_json"
  skills/xlsx/scripts/xlsx2csv2json/emit_json.py` returns ≥ 2 hits
  (definition + caller); `_rows_to_dicts` is a generator (returns
  `Iterator[dict]`, not `list[dict]`).
- **R10** — `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1` env-flag opt-in
  round-trip passes on every R11.1 fixture.

### 5.2. Test suite

- **8 new test groups** under `skills/xlsx/scripts/xlsx2csv2json/tests/`
  and `skills/xlsx/scripts/xlsx_read/tests/`. Minimum count:
    - R1: 2 tests (cap, just-under-cap). Hosted in
      `xlsx2csv2json/tests/test_emit_csv.py` (or new
      `test_hardening.py` at developer judgement).
    - R2: 2 tests (cap, just-under-cap). Hosted in
      `xlsx_read/tests/test_merges.py`.
    - R3: 4 tests (allowed, blocked, mixed-dedup, mailto-default).
    - R4: 15 tests = (6 sentinels × 2 modes quote/strip = 12) + 1
      off-noop + 1 json-no-effect-warning + 1 E2E DDE payload.
    - R8: 3 tests (3M cells succeeds, 50M+1 raises, bytearray
      correctness vs list-of-list). Hosted in
      `xlsx_read/tests/test_tables.py`.
    - R9: 2 tests (file output byte-identical to v1; peak RSS
      shows the saved string-buffer copy).
    - R10: 6 tests (byte-identical R11.1 vs v1; 3M-cell peak RSS
      under 200 MB; hyperlinks survive; array-style works; empty
      table; R11.2-4 unchanged regression).
- **Total**: ≥ 34 new tests across both test packages.

> **Test pattern note** (review N2): R8 / R9 / R10 introduce
> `tracemalloc` (Python stdlib, no `requirements.txt` change) as a
> peak-RSS budget pattern. Canonical form:
>
> ```python
> import tracemalloc
> tracemalloc.start()
> # ... run code under test ...
> current, peak = tracemalloc.get_traced_memory()
> tracemalloc.stop()
> self.assertLess(peak, BUDGET_BYTES)
> ```
>
> This is the first task to introduce the pattern in
> `skills/xlsx/scripts/*/tests/`; future tasks can grep for
> `tracemalloc` to find the precedent.
- All run through `./.venv/bin/python -m unittest discover -s
  xlsx2csv2json/tests` and `./.venv/bin/python -m unittest discover
  -s xlsx_read/tests`.
- Existing tests in both suites stay green (regression gate).

### 5.3. Regression gates

- `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` → exit 0.
- All four office-skill validators (`docx`, `xlsx`, `pptx`, `pdf`)
  → exit 0.
- 12-line cross-skill `diff -q` gate from `docs/ARCHITECTURE.md
  §9.4` → all silent.
- `ruff check skills/xlsx/scripts/` → green.

---

## 6. Constraints and Assumptions

### 6.1. Technical constraints

- **`xlsx_read/` carve-out is bounded** — this task touches exactly
  three files (`_merges.py` + `_exceptions.py` + `__init__.py`)
  and the changes are purely additive. No existing function
  signature mutates.
- **`exceptions.py` carve-out is bounded** — one new class
  (`CollisionSuffixExhausted`); registered in `__all__`.
- **No new dependencies.** `urllib.parse` is stdlib; everything
  else is current.
- **No new env-flags.** Behaviour change is opt-in via CLI flag
  only (R3 default permissive; R4 default off).
- **Path-handling helpers** (`Path.resolve`, `is_relative_to`)
  reused from xlsx-8 — no new path-traversal logic.

### 6.2. Business / process constraints

- Effort budget: **S→M** (per backlog row). Each atomic fix is S;
  cumulative is M.
- Value: **M** — defense-in-depth for future deployments; not user-
  visible for typical use.
- **Atomic chain shippable.** Each `xlsx-8a-0N` sub-task is a
  separate PR-ready unit. Order: 01 → 02 → 03 → 04 → 05. Each
  closes one acceptance criterion.

### 6.3. Assumptions

- The 1000 / 100_000 caps are policy choices, not derived from a
  workload model. If a real workbook breaches them in production,
  raise via a regression bug rather than silently widening.
- `--hyperlink-scheme-allowlist` parses the comma list itself
  (no `csv` module needed); whitespace stripped; case folded to
  lower; empty entries dropped.
- `--escape-formulas` sentinel chars are the OWASP-canonical six:
  `=` `+` `-` `@` `\t` `\r`. Unicode characters that LibreOffice
  also treats as formula triggers (e.g. `＝` U+FF1D fullwidth
  equals sign) are out of scope; if a future report shows
  exploitation, add a follow-up task.

---

## 7. Open Questions

### 7.1. Blocking — none.

All design decisions are locked in §1.4 honest-scope items.

### 7.2. Non-blocking (deferred to architect)

- **Q-1.** Should the `TooManyMerges` cap be a CLI flag
  (`--max-merges 100000`)? **Decision:** No. Cap is policy; making
  it a CLI flag invites operators to silently widen it on
  misconfigured workbooks. Constant-only; raise via code change if
  evidence demands.
- **Q-2.** Should `CollisionSuffixExhausted` carry the offending
  `(sheet, region_name)` in the cross-5 envelope `details`?
  **Decision:** Yes — `details = {"sheet": "<basename-safe>",
  "region": "<basename-safe>"}`. Both are originally workbook-
  attacker-controlled but already validated by
  `_validate_sheet_path_components`; safe to surface.
- **Q-3.** Should `--hyperlink-scheme-allowlist` accept a `*` /
  `all` shorthand for "permit everything"? **Decision:** No.
  Defense-in-depth means "explicit allow only"; a global escape
  hatch defeats the purpose. Users who need a scheme not in the
  default pass it explicitly (`--hyperlink-scheme-allowlist
  "http,https,mailto,custom"`).

### 7.3. Locked decisions (recorded for traceability)

- **D1.** `_MAX_COLLISION_SUFFIX = 1000` — fires on the 1001st
  attempted suffix.
- **D2.** `_MAX_MERGES = 100_000` — fires on the 100_001st merge
  (insertion of the 100_001st entry triggers raise).
- **D3.** `--hyperlink-scheme-allowlist` default
  `http,https,mailto`. Comma-separated; case-insensitive; empty
  entries dropped.
- **D4.** `--escape-formulas` default `off` for backward compat;
  sentinels `=` `+` `-` `@` `\t` `\r` (OWASP-canonical six).
- **D5.** xlsx-8a-05 is **docs only** — no code change.
- **D6.** Carve-out from xlsx-10.A frozen surface is bounded to
  `_merges.py` + `_exceptions.py` + `__init__.py`; xlsx_read tests
  in `tests/test_merges.py` extended (positive + negative).
- **D7.** **JSON output shape for blocked-scheme hyperlink cells:
  bare scalar** (Option A from task-review M1). Blocked cells
  traverse the same emit branch as cells that never had a hyperlink;
  the existing two-shape contract (`{value, href: url}` /
  bare-scalar) is preserved. A third shape `{value, href: null}`
  was considered and rejected to avoid breaking the round-trip with
  xlsx-2 and the documented `references/json-shapes.md §11`
  shapes. Trade-off: per-cell "originally had a link" signal is
  lost on blocked schemes (the workbook-level stderr warning
  remains). See [`docs/reviews/task-011-review.md`](reviews/task-011-review.md) §M1.
- **D8.** **`_GAP_DETECT_MAX_CELLS` raised to 50 000 000** (16x prior
  value; ~17x the largest legitimate workload observed). Rationale:
  100K × 30 = 3M cells (documented user workload) needs ≥ 3M
  headroom; 50M gives 16x safety margin while keeping the XFD1048576
  attack envelope (17B cells) blocked. Constant; no CLI / env-var.
  Policy precedent: TASK §7.2 Q-1 (`TooManyMerges` cap is also
  constant-only) and ARCHITECTURE.md §15.8 Q-15-1
  (`_MAX_COLLISION_SUFFIX` / `_MAX_MERGES` are constants, not
  flags).
- **D9.** **`bytearray` flat buffer indexed `[r * n_cols + c]`** for
  `_gap_detect` and `_build_claimed_mask`. Drop-in replacement for
  `list[list[bool]]`; 8x memory reduction (1 byte vs 8 bytes per
  ref); Big-O unchanged. `_build_claimed_mask` adds early-exit
  `if not claimed: return None` so the empty-claimed common case
  (Tier-1 + Tier-2 empty) skips the allocation entirely. Test:
  parametric same-output on a 100×100 fixture vs the v1 list-of-list
  implementation (held as `_v1_reference` in the test file).
- **D10.** **`_stream_single_region_json` is the only streaming
  path** (R11.1 shape only). R11.2-4 multi-sheet / multi-region
  shapes fall back to `json.dump(shape, fp, ...)` (R9 fix). Full
  R11.2 streaming (per-sheet append) is feasible but deferred to
  `xlsx-8c-multi-sheet-stream` because R11.2 large-table workloads
  are atypical; R11.3/R11.4 cannot be RFC-8259-streamed without
  inventing chunked-encoding.

---

## 8. Atomic-Chain Skeleton (Planner handoff hint)

8 atomic sub-tasks, one per fix. Order is **linear, not parallel**.
Sub-tasks 011-01..011-05 are the security axis (any internal order
valid; locked to match backlog row); 011-06..011-08 are the
performance axis, ordered:

- **011-06 must precede 011-07 and 011-08** because R8 raises
  `_GAP_DETECT_MAX_CELLS` to 50M, which is a **fixture-side
  prerequisite** for the 3M-cell synthesised fixtures used by
  R9 and R10 tests (`test_R9_file_output_no_string_buffer`,
  `test_R10_stream_3M_cells_peak_rss_below_200MB`,
  `test_R10_stream_byte_identical_to_v1_single_sheet_single_region`).
  Without R8's raise, the v1 1M-cell cap fires during
  `detect_tables` while the test fixture is being built, before
  any JSON emit code runs. (Reviewer-corrected from v2 wording:
  the bytearray flip does NOT change `_gap_detect`'s call-shape
  for the JSON paths — those paths consume `TableData`, not the
  occupancy matrix. R8 is a fixture-timing prerequisite, not a
  runtime-call-shape prerequisite.)
- **011-07 and 011-08 may ship in either order**, but the
  recommended order is 07 → 08 so the simpler `json.dump(fp)`
  refactor stabilises before the larger generator refactor lands.
  011-08 supersedes 011-07 for the R11.1 single-region path; 011-07
  remains live for R11.2-4 shapes that 011-08 does not touch.

| # | Slug | Scope | Stub-First gate |
| --- | --- | --- | --- |
| 011-01 | `collision-suffix-cap` | Add `CollisionSuffixExhausted` exception; cap loop at 1000; 2 tests. | `test_collision_suffix_caps_at_1000` + `test_collision_suffix_999_succeeds` green; existing `test_M2_*` green. |
| 011-02 | `merges-cap` | Add `TooManyMerges` exception + `_MAX_MERGES`; export via `xlsx_read.__all__`; map to envelope in shim; 2 tests. | `test_parse_merges_at_100000_passes` + `test_parse_merges_at_100001_raises` green; existing `xlsx_read/tests/test_merges.py` green; shim envelope test green. |
| 011-03 | `hyperlink-scheme-allowlist` | Add CLI flag; `urlparse` scheme-check; warn-only on blocked; 4 tests. | All 4 R3 tests green; `--include-hyperlinks` existing tests green. |
| 011-04 | `escape-formulas` | Add CLI flag; `_write_region_csv` transform; help-text update on `--encoding utf-8-sig`; 6 + 1 tests. | All 7 R4 tests green; existing CSV emit tests green. |
| 011-05 | `security-docs` | New `references/security.md`; cross-link from SKILL.md + ARCHITECTURE.md §14.7. | grep-gate for trust-boundary sentence; cross-link presence verified. |
| 011-06 | `cap-raise-and-bytearray` | `_GAP_DETECT_MAX_CELLS` 1M → 50M; `_gap_detect` + `_build_claimed_mask` matrices to `bytearray`; early-exit for empty-claimed; 3 tests; delete `PERF-HIGH-1` entry from `docs/KNOWN_ISSUES.md`. | `test_R8_gap_detect_at_3M_cells_succeeds` + `test_R8_gap_detect_at_50M_plus_one_raises` + `test_R8_bytearray_correctness_vs_listoflist` green; existing `xlsx_read/tests/test_tables.py` 100% green; CSV path on 100K×30 fixture writes 100 001 lines. |
| 011-07 | `json-dump-file-output` | `emit_json` file-output branch: `json.dumps`→`json.dump(fp)`; stdout unchanged; 2 tests. | `test_R9_file_output_no_string_buffer` + `test_R9_file_byte_identical_to_v1` green; multi-sheet fixtures byte-identical. |
| 011-08 | `r11-1-streaming` | `_rows_to_dicts` / `_rows_to_string_style` / `_rows_to_array_style` → generators; new `_stream_single_region_json` helper; `_shape_for_payloads` dispatch updated for R11.1 early-detect; 6 tests; narrow `PERF-HIGH-2` entry in `docs/KNOWN_ISSUES.md` to "multi-sheet / multi-region only" — update BOTH `Status` line AND `Location` subsection (drop `emit_json.py:79` reference, R10 closes that path; narrow `emit_csv.py:59` reference to "region-list materialisation only — per-row writes already stream via `csv.writer.writerow`"). Reference the `xlsx-8c-multi-sheet-stream` follow-up by slug in the narrowed entry's `Related` line; if no backlog row exists yet, also create a stub row in [`docs/office-skills-backlog.md`](office-skills-backlog.md). | All 6 R10 tests green; R11.2-4 fixtures unchanged; `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1` passes on R11.1 fixtures. |

---

## 9. Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| Carve-out into "frozen" xlsx_read surface erodes the freeze long-term. | Bounded to 3 files; additive only; documented in §1.3; reviewed by `architecture-reviewer` before code lands. |
| `--escape-formulas quote` breaks downstream pipelines expecting raw `=`-prefix to round-trip. | Default `off` preserves current behaviour; user must opt-in. Documented in §1.4 (b). |
| `--hyperlink-scheme-allowlist` default omits a real-world scheme (e.g. `tel:`). | Test fixtures in `xlsx2csv2json/tests/fixtures/` audited for scheme coverage. If a fixture has a non-default scheme, add it to default OR add `--hyperlink-scheme-allowlist` to that fixture's test. |
| Caps too tight for a legitimate real workbook. | Caps are 10×–100× current real-world max; raise via code change with rationale in commit body. |
| TOCTOU race in `_emit_multi_region` is NOT closed by this task. | xlsx-8a-05 documents the limitation + fix recipe; user can decide whether to deploy in multi-tenant CI today. |
| `bytearray` flip in `_gap_detect` accidentally breaks `_split_on_gap` / `_tight_bbox` callers (matrix shape changes). | Internal-only refactor; existing `xlsx_read/tests/test_tables.py` exercises the call graph end-to-end. The `test_R8_bytearray_correctness_vs_listoflist` test pins same-output before behavioural changes can sneak in. Stub-First gate (011-06) requires the existing test suite green at 100%. |
| R10 `_stream_single_region_json` produces JSON that differs byte-for-byte from v1 (e.g. trailing-newline drift, indent depth-1 vs depth-2). | `test_R10_stream_byte_identical_to_v1_single_sheet_single_region` runs the same fixture through both paths and `diff -q`'s the outputs. The streaming path's indent strategy (depth-1 per row, depth-0 at the wrapper) is locked by this test. If the test fails, the streaming indent helper is the only place to fix. |
| R8 cap raise to 50M masks a real DoS attack surface. | Cap is policy; 50M is 1/340 of XFD1048576 hard-limit. Any "this workbook has 50M legitimate cells but you blocked it" report triggers a code-change PR with rationale (no env-var widening per D8). The threat model continues to assume "trusted workbook input" (Sec-HIGH-1 honest scope). |
| R10 generator-based shape refactor introduces a regression on R11.2-4 paths. | `test_R10_R11_2_to_4_unchanged` exercises every existing multi-sheet / multi-region fixture and asserts byte-identical output. The `_rows_to_*` generator change is internal — callers in R11.2-4 branches consume eagerly via `list(...)` at the call-site, preserving the v1 semantics. |

---
