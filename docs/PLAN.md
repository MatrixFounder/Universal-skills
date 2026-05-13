# Development Plan: TASK 011 — `xlsx-8a` Production Hardening (8 atomic fixes)

> **Source TASK:** [`docs/TASK.md`](TASK.md) (TASK 011 v3)
> **Source Architecture:** [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §15 (§15.1–§15.9 security axis; §15.10 perf axis).
> **Predecessor plan archived:** [`docs/plans/plan-010-xlsx-8-readback.md`](plans/plan-010-xlsx-8-readback.md).
> **Mode:** VDD (Verification-Driven Development) — Stub-First two-pass per atomic bead.

---

## 0. Strategy Summary

### 0.1. Chainlink Decomposition Overview

xlsx-8a is decomposed along **two axes** (per TASK §1.1):

- **Security axis (011-01..05)** — 5 atomic fixes for defense-in-depth.
  Closes Sec-HIGH-3, Sec-MED-1/2/3 from `/vdd-multi-3` and ARCH §14.7;
  documents Sec-HIGH-1 (TOCTOU) as known-limitation.
- **Performance axis (011-06..08)** — 3 atomic fixes for large-table
  support (100K × 20-30 cols ≈ 2-3M cells). Closes PERF-HIGH-1
  fully; PERF-HIGH-2 closed for R11.1 single-region (most common
  large-table shape), narrowed for R11.2-4 residual.

Each atomic bead corresponds to **exactly one RTM requirement**
(R1..R10 in TASK §2) and ships as one PR-ready unit with stubs,
E2E tests, and logic in the same atomic delivery (the Stub-First
two-pass is applied **within** each bead — see §0.2 below).

### 0.2. Phasing (Stub-First within each atomic bead)

Per [skill-tdd-stub-first](.agent/skills/tdd-stub-first/SKILL.md),
each of the 8 atomic beads is internally a two-pass:

1. **Pass 1 — Stub + E2E test (Red → Green).**
   Create the file structure (new exception class / new flag
   argparse entry / new helper signature) with stub bodies
   (`raise NotImplementedError` for new logic; passthrough for new
   no-op flags). Write an E2E test that asserts the stub-level
   behaviour. Run test → green.
2. **Pass 2 — Logic implementation (replace stubs).**
   Replace stubs with real logic. Update the E2E test to assert
   real behaviour. Add unit tests for edge cases. Run regression
   suite (every existing test green); run `validate_skill.py`;
   run 12-line cross-skill `diff -q` gate.

For docs-only beads (011-05), the two passes collapse to one
(write the markdown, grep-gate the trust-boundary sentence).

### 0.3. Cross-skill replication gate (mandatory before every commit)

Each bead's acceptance criteria includes the 12-line cross-skill
`diff -q` gate from `docs/ARCHITECTURE.md §9.4`. All 12 must
produce no output. Beads that touch only `xlsx_read/_tables.py`,
`xlsx_read/_merges.py`, `xlsx_read/_exceptions.py`,
`xlsx_read/__init__.py`, `xlsx2csv2json/*.py`, or
`skills/xlsx/references/security.md` automatically satisfy this
gate (none of those files are in the replicated set).

### 0.4. Carve-out boundary (from ARCH §9.1 + §15.10.5)

xlsx-8a re-opens 4 files inside the xlsx-10.A "frozen surface"
(`_merges.py`, `_exceptions.py`, `__init__.py`, `_tables.py`).
The carve-out is bounded by the rule "each re-opened file ships
with a documented `KNOWN_ISSUES.md` entry OR a §15.x decision
record" (per arch-review m5 fix). Beads 011-02 and 011-06
contribute to this carve-out; all changes are additive (no
existing function signature changes; no existing export removed).

---

## 1. Task Execution Sequence

### Stage 1 — Security Axis (011-01..05)

The five security-axis beads are **internally order-independent**
(any internal sequence valid; the order below matches the backlog
row `xlsx-8a` enumeration and the TASK §8 atomic-chain table).

- **Task 011-01** — [R1] Bounded collision-suffix in `_emit_multi_region`.
  - Use Cases: UC-01
  - Description File: [`docs/tasks/task-011-01-collision-suffix-cap.md`](tasks/task-011-01-collision-suffix-cap.md)
  - Priority: Critical (Sec-HIGH-3 DoS closure)
  - Dependencies: none
  - Files touched: `scripts/xlsx2csv2json/emit_csv.py` (lines ~162-172),
    `scripts/xlsx2csv2json/exceptions.py` (new class).

- **Task 011-02** — [R2] Bounded merge-count in `parse_merges(ws)`.
  - Use Cases: UC-02
  - Description File: [`docs/tasks/task-011-02-merges-cap.md`](tasks/task-011-02-merges-cap.md)
  - Priority: Critical (Sec-MED-3 memory exhaustion closure)
  - Dependencies: none (independent of 011-01; touches different files)
  - Files touched: `scripts/xlsx_read/_merges.py` (lines ~36-41),
    `scripts/xlsx_read/_exceptions.py` (new class),
    `scripts/xlsx_read/__init__.py` (`__all__` export),
    `scripts/xlsx2csv2json/cli.py` (`_run_with_envelope` branch).

- **Task 011-03** — [R3] `--hyperlink-scheme-allowlist` flag (both shims).
  - Use Cases: UC-03
  - Description File: [`docs/tasks/task-011-03-hyperlink-scheme-allowlist.md`](tasks/task-011-03-hyperlink-scheme-allowlist.md)
  - Priority: High (Sec-MED-2 javascript:/data: URI closure)
  - Dependencies: none
  - Files touched: `scripts/xlsx2csv2json/cli.py` (argparse),
    `scripts/xlsx2csv2json/dispatch.py` (`_extract_hyperlinks_for_region`).
    Emit branches in `emit_json.py` / `emit_csv.py` are NOT touched —
    blocked entries are dropped from the map upstream and traverse
    the existing no-hyperlink branch (per D7 / D-A11).

- **Task 011-04** — [R4] `--escape-formulas {off,quote,strip}` (CSV-only).
  - Use Cases: UC-04
  - Description File: [`docs/tasks/task-011-04-escape-formulas.md`](tasks/task-011-04-escape-formulas.md)
  - Priority: High (Sec-MED-1 CSV injection closure)
  - Dependencies: none
  - Files touched: `scripts/xlsx2csv2json/cli.py` (argparse + JSON-shim warning),
    `scripts/xlsx2csv2json/emit_csv.py` (`_write_region_csv` transform).

- **Task 011-05** — [R5] Trust-boundary docs (`security.md`).
  - Use Cases: UC-05
  - Description File: [`docs/tasks/task-011-05-security-docs.md`](tasks/task-011-05-security-docs.md)
  - Priority: Medium (documentation only — no code change)
  - Dependencies: none
  - Files touched: `skills/xlsx/references/security.md` (NEW),
    `skills/xlsx/SKILL.md` (cross-link),
    `docs/ARCHITECTURE.md` §14.7 (cross-link).

### Stage 2 — Performance Axis (011-06..08)

The three performance-axis beads are **linearly ordered**:

- **Task 011-06 must precede 011-07 and 011-08** because the
  3M-cell synthesised test fixtures used by R9 / R10 cannot
  complete under the v1 1M-cell cap during fixture setup (per
  TASK §8 reviewer-corrected wording; the bytearray flip does NOT
  change the JSON-path call shape — the dependency is fixture
  timing).
- **011-07 → 011-08** is recommended (simpler `json.dump` refactor
  before larger generator refactor) but not strictly required.

- **Task 011-06** — [R8] `_GAP_DETECT_MAX_CELLS` raise + `bytearray` matrices.
  - Use Cases: UC-06
  - Description File: [`docs/tasks/task-011-06-cap-raise-and-bytearray.md`](tasks/task-011-06-cap-raise-and-bytearray.md)
  - Priority: Critical (large-table support gate; closes PERF-HIGH-1)
  - Dependencies: none (touches only `xlsx_read/_tables.py`)
  - Files touched: `scripts/xlsx_read/_tables.py` (5 functions:
    `_GAP_DETECT_MAX_CELLS` constant, `_gap_detect`,
    `_build_claimed_mask`, `_split_on_gap` / `_tight_bbox`,
    `_whole_sheet_region`); `docs/KNOWN_ISSUES.md` (delete
    PERF-HIGH-1 entry in this commit).

- **Task 011-07** — [R9] `json.dump(fp)` for file output (drop one copy).
  - Use Cases: UC-08
  - Description File: [`docs/tasks/task-011-07-json-dump-file-output.md`](tasks/task-011-07-json-dump-file-output.md)
  - Priority: High (PERF-HIGH-2 R11.2-4 partial closure)
  - Dependencies: 011-06 (fixture-timing prerequisite)
  - Files touched: `scripts/xlsx2csv2json/emit_json.py`
    (lines ~89-98, file-output branch only; stdout unchanged).

- **Task 011-08** — [R10] R11.1 single-region JSON streaming.
  - Use Cases: UC-07
  - Description File: [`docs/tasks/task-011-08-r11-1-streaming.md`](tasks/task-011-08-r11-1-streaming.md)
  - Priority: High (PERF-HIGH-2 closure for most common large-table case)
  - Dependencies: 011-06 (fixture-timing prerequisite); 011-07
    (sequencing recommendation — simpler refactor first)
  - Files touched: `scripts/xlsx2csv2json/emit_json.py`
    (`_rows_to_*` → generators; new `_stream_single_region_json`;
    `_shape_for_payloads` R11.1 dispatch); `docs/KNOWN_ISSUES.md`
    (narrow PERF-HIGH-2 entry: drop `emit_json.py:79` reference,
    narrow `emit_csv.py:59` to region-list-only; add
    `xlsx-8c-multi-sheet-stream` to `Related`);
    `docs/office-skills-backlog.md` (create stub row
    `xlsx-8c-multi-sheet-stream`).
  - **Effort exception (per plan-review M1)**: this bead is sized
    L (~6 h), exceeding the 2-4 h atomicity envelope of
    `06_planner_prompt.md` §1. **Accepted with rationale**: the
    byte-identity invariant (PLAN.md §5 risk row 1) is the
    highest-risk item in the plan; the Stub-First two-pass within
    this single bead already provides a natural in-bead checkpoint
    (Pass 1 lands generators + sentinel + `NotImplementedError`
    stub; Pass 2 lands the streaming-helper body and doc updates).
    Splitting into 011-08a/b would break the byte-identity-test
    continuity (Pass 1's generator refactor must NOT regress
    `test_R10_R11_2_to_4_unchanged`, and the byte-identity gate
    `test_R10_stream_byte_identical_to_v1_*` is best run by the
    same developer in one sitting against the same fixture set).
    Keeping the bead unified preserves the regression-test
    continuity; the L sizing is a deliberate trade-off.

- **Task 011-10** — [R12] Fix `ReadOnlyWorksheet` `AttributeError` on
  workbooks > 10 MiB auto-streaming threshold.
  - Use Cases: UC-10 (new, no separate spec — covered by R12 in
    TASK §2 RTM)
  - Priority: HIGH (blocks the user-reported 15 MB workbook
    conversion path; surfaces as opaque `Internal error: AttributeError`
    via the catch-all in `cli._run_with_envelope`)
  - Dependencies: none (independent of R8/R9/R10/R11)
  - Files touched:
    - `scripts/xlsx_read/_workbook.py` (`_DEFAULT_READ_ONLY_THRESHOLD`
      10 MiB → 100 MiB; docstring + comment update)
    - `scripts/xlsx_read/_merges.py` (`parse_merges` guards
      `hasattr(ws, 'merged_cells')` — returns `{}` on
      `ReadOnlyWorksheet`)
    - `scripts/xlsx_read/_types.py` (`read_table` overlap-check
      block guards the `merged_cells.ranges` access — skip if
      attribute missing)
    - `scripts/xlsx_read/tests/test_workbook.py` or
      `tests/test_tables.py` (3 new tests)
    - `skills/xlsx/SKILL.md` (document `read_only_mode` tradeoffs)
  - **Design summary**:
    - Bumping the threshold to 100 MiB covers typical office
      workbook sizes (5-50 MB) with no behaviour change. Users
      with truly large workbooks (≥ 100 MiB) implicitly opt into
      streaming — for them, merge-aware features degrade to
      no-ops (no overlap detection, no merge policy effect on
      header band). The honest-scope tradeoff is documented in
      SKILL.md.
    - Graceful guard in `parse_merges` + `read_table`
      overlap-check eliminates the crash path for explicit
      `read_only_mode=True` callers.

- **Task 011-11** — [R13] Expose `--memory-mode {auto,streaming,full}`
  CLI flag so callers can opt into openpyxl streaming for large
  workbooks without editing code.
  - Use Cases: UC-11 (new; no separate spec)
  - Priority: HIGH (4.3× RSS reduction available on
    `Моделирование.xlsx` measured 2026-05-13: 1188 MB → 278 MB;
    user can't access this without code change today)
  - Dependencies: R12 (graceful ReadOnlyWorksheet fallback must be
    in place so explicit `streaming` opt-in doesn't crash on
    merge-bearing workbooks)
  - Files touched:
    - `scripts/xlsx2csv2json/cli.py` — new `_MEMORY_MODES =
      ("auto", "streaming", "full")` constant + argparse entry
      `--memory-mode` (default `"auto"`); help-text documents
      RAM trade-off and merge-handling no-op on `streaming`.
    - `scripts/xlsx2csv2json/dispatch.py` (`_dispatch_to_emit`):
      replace the hard-coded
      `read_only_mode = False if args.include_hyperlinks else None`
      with a 3-way switch:
      - `auto` → `None` (preserves existing size-threshold-driven
        behaviour).
      - `streaming` → `True` (force openpyxl streaming).
      - `full` → `False` (force non-streaming, all merge features
        work).
      `--include-hyperlinks` overrides `streaming` → `full` (with
      stderr warning) because ReadOnlyWorksheet doesn't expose
      `cell.hyperlink`.
    - `scripts/xlsx2csv2json/tests/test_e2e.py` or
      `tests/test_cli.py` — 5 new tests.
    - `skills/xlsx/SKILL.md` — document `--memory-mode` in the
      `--header-rows`/`--tables` flag table.
    - `skills/xlsx/scripts/.AGENTS.md` — append 011-11 section.
  - **Design summary**:
    - Default `auto` preserves backward-compat: `open_workbook`
      auto-selects streaming above the
      `_DEFAULT_READ_ONLY_THRESHOLD = 100 MiB` cap (R12 raised
      from 10 MiB).
    - `streaming` is the recommended mode for workbooks where
      memory matters and merges are absent (financial-modeling
      sheets, raw timesheets, gap-detect-friendly layouts).
    - `full` is the recommended mode for merge-heavy workbooks
      regardless of size (forces non-streaming so
      `parse_merges` / `detect_header_band` / overlap-detection
      work correctly).
    - `--include-hyperlinks --memory-mode streaming` is a known
      conflict: hyperlink extraction requires
      `cell.hyperlink.target` which is absent on
      `ReadOnlyWorksheet`. The conflict resolver emits a stderr
      warning and overrides to `full` (matches the existing
      auto-coerce path for `--include-hyperlinks`).
    - **Acceptance**: 5 R13 tests green; existing 445 tests
      stay green (regression gate); `validate_skill.py
      skills/xlsx` exit 0; 12-line cross-skill `diff -q` gate
      silent. Live verification: `xlsx2json.py Моделирование.xlsx
      out.json --memory-mode streaming` should complete with
      peak RSS ≤ 500 MB (was 1188 MB).

- **Task 011-09** — [R11] `--header-rows smart`: type-pattern
  header-row detection for unmerged metadata blocks above data tables.
  - Use Cases: UC-09 (new)
  - Priority: High (real-world workbook pattern — config + data
    stacked, no merges to guide header band; surfaced by user
    workload `tmp4/Моделирование.xlsx` 2026-05-13)
  - Dependencies: none (independent of perf axis 011-06/07/08)
  - Files touched:
    - `scripts/xlsx_read/_tables.py` (new private
      `_detect_data_table_offset(ws, region)` heuristic, ~60 LOC)
    - `scripts/xlsx_read/_types.py` (`read_table` wires
      `header_rows='smart'`: compute offset, shift `region.top_row`,
      treat as 1-row header; ~15 LOC)
    - `scripts/xlsx2csv2json/cli.py` (`_header_rows_type` accepts
      `"smart"`; help text updated)
    - `scripts/xlsx2csv2json/dispatch.py` (`smart_mode` branch
      mirroring existing `leaf_mode` plumbing)
    - `scripts/xlsx_read/tests/test_tables.py` and
      `scripts/xlsx2csv2json/tests/test_emit_json.py` (5 new tests)
    - `skills/xlsx/SKILL.md` (document `smart` mode in
      `--header-rows` help)
  - **Design summary (as-shipped after iter-2 + iter-3 + iter-4)**:
    - Score each top row (up to `PROBE_ROWS=20`) by
      `string_ratio + 1.5×coverage_ratio + 2×stability_ratio
      + 0.5×depth_score` (type stability of `STABILITY_DEPTH=5`
      rows below). Max theoretical score 5.0 after iter-3 H1 clamp.
    - **Score-only** (iter-2 design change): does NOT defer to
      merge-based detection. On merged-banner fixtures, `smart`
      shifts to the sub-header row (leaf-like keys); callers
      needing merge-concatenated multi-level form must use
      `auto` or `leaf` instead. The `--header-rows smart` recipe
      is non-overlapping with `auto`/`leaf` at the **output shape**
      level, not at the scoring-input level.
    - **Adaptive `data_width`** (iter-2): the per-candidate
      `min_non_empty_cols = max(3, data_width // 2)` floor is
      computed from rows BELOW the candidate (max non-empty col
      index across `sample_below`), not from the region width
      `n_cols`. This fixes the masterdata Timesheet pattern
      where a sparse banner inflates `n_cols=25` while the real
      data table is 7 cols wide.
    - **`coverage_ratio` clamp** (iter-3 H1): `min(1.0,
      len(non_empty) / data_width)` so a banner wider than the
      data table can't blow the documented theoretical max score
      via coverage alone.
    - **`len(sample_below) ≥ 2` floor** (iter-3 M1): prevents
      candidates near the bottom of the probe window from
      passing a trivially-satisfied 1-row stability check.
    - **Threshold**: `score ≥ 3.5` to justify a shift; below
      threshold, OR when best candidate is `offset == 0`,
      return 0 (current row-1 fallback).
    - **R12 hasattr probe** (iter-3 L1): the `ws.merged_cells`
      probe used by the no-defer path (and the R12 graceful
      guards in `parse_merges`, `detect_header_band`, overlap-
      check, ambiguous-boundary) uses
      `getattr(merged_cells_attr, "ranges", None)` rather than
      trusting a non-`None` `merged_cells` to expose `.ranges` —
      future-proofs against openpyxl version drift.
    - **Acceptance (as-shipped 2026-05-13)**: 9 R11 tests + 6 R12
      tests + 1 iter-3 hasattr-probe test = 16 new tests green;
      total xlsx_read suite at 224 (+15 from 209 pre-009/010),
      xlsx2csv2json at 221 (+1 E2E from 220) = **445 green**;
      `validate_skill.py skills/xlsx` exit 0; 12-line cross-skill
      `diff -q` gate silent (no replicated files touched).

### Stage 3 — Integration & Final Gates

After all 8 beads land:

- Run full test suite: `cd skills/xlsx/scripts && ./.venv/bin/python
  -m unittest discover -s xlsx_read/tests` + `... -s xlsx2csv2json/tests`.
- Run `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` → exit 0.
- Run 12-line cross-skill `diff -q` gate from ARCH §9.4 → silent.
- Verify `docs/KNOWN_ISSUES.md` reflects post-merge state:
  PERF-HIGH-1 deleted; PERF-HIGH-2 narrowed; `xlsx-8c-multi-sheet-stream`
  appears in backlog.
- Update `docs/office-skills-backlog.md` row `xlsx-8a` to ✅ DONE.

---

## 2. Chainlink — Epic → Issue → Bead breakdown

Eight epics, eight issues, eight beads (1:1:1 across the entire RTM).

### Epic E1 — Sec-HIGH-3 collision-suffix DoS (R1)
- **Issue I1.1** — `_emit_multi_region` collision-suffix loop is unbounded.
  - **Bead 011-01** — Add `_MAX_COLLISION_SUFFIX = 1000` + `CollisionSuffixExhausted(_AppError, CODE=2)`; 2 tests.

### Epic E2 — Sec-MED-3 merge-count unbounded (R2)
- **Issue I2.1** — `parse_merges(ws)` materialises unbounded dict.
  - **Bead 011-02** — Add `_MAX_MERGES = 100_000` + `TooManyMerges(RuntimeError)`; export via `__all__`; map to envelope in shim; 2 tests.

### Epic E3 — Sec-MED-2 hyperlink scheme abuse (R3)
- **Issue I3.1** — Hyperlink targets emitted verbatim (XSS / RCE downstream).
  - **Bead 011-03** — `--hyperlink-scheme-allowlist` (default `http,https,mailto`); `urlparse` scheme-check in `_extract_hyperlinks_for_region`; warn-only on blocked; blocked entries drop from map; 4 tests.

### Epic E4 — Sec-MED-1 CSV formula injection (R4)
- **Issue I4.1** — Cell values starting with `=` / `+` / `-` / `@` / `\t` / `\r` execute as DDE formulas on Excel double-click.
  - **Bead 011-04** — `--escape-formulas {off,quote,strip}` (default `off`); `_write_region_csv` transform; help-text cross-ref `--encoding utf-8-sig`; 15 tests.

### Epic E5 — Sec-HIGH-1 TOCTOU trust-boundary documentation (R5)
- **Issue I5.1** — Parent-symlink + TOCTOU race in `_emit_multi_region` not closed by code; needs documentation.
  - **Bead 011-05** — New `skills/xlsx/references/security.md` (≥ 80 lines, trust-boundary sentence, fix recipe); cross-link from `SKILL.md` + `ARCHITECTURE.md §14.7`.

### Epic E6 — PERF-HIGH-1 `_gap_detect` 8MB matrix (R8)
- **Issue I6.1** — `list[list[bool]]` occupancy matrix + cap blocks 100K × 25-30 workloads.
  - **Bead 011-06** — Cap raise 1M → 50M; bytearray flat buffer; early-exit on empty claimed; delete PERF-HIGH-1 from `KNOWN_ISSUES.md`; 3 tests.

### Epic E7 — PERF-HIGH-2 partial — JSON file-output (R9)
- **Issue I7.1** — `json.dumps(shape) + write_text` materialises serialised string buffer (1 of 3 copies).
  - **Bead 011-07** — `json.dump(shape, fp)` for file output; stdout unchanged; 2 tests.

### Epic E8 — PERF-HIGH-2 full — R11.1 single-region streaming (R10)
- **Issue I8.1** — `_rows_to_dicts` materialises full `list[dict]`; `_shape_for_payloads` builds full `shape` dict.
  - **Bead 011-08** — Refactor `_rows_to_*` to generators; new `_stream_single_region_json`; `_shape_for_payloads` R11.1 dispatch; narrow PERF-HIGH-2 in `KNOWN_ISSUES.md`; create `xlsx-8c-multi-sheet-stream` backlog stub; 6 tests.

---

## 3. Use Case Coverage

| Use Case | Beads | Description |
| --- | --- | --- |
| UC-01 | 011-01 | Collision-suffix cap in multi-region CSV emit |
| UC-02 | 011-02 | Merge-count cap in `parse_merges(ws)` |
| UC-03 | 011-03 | Hyperlink scheme allowlist (R3) |
| UC-04 | 011-04 | CSV formula escape (R4) |
| UC-05 | 011-05 | Trust-boundary documentation |
| UC-06 | 011-06 | Large-table CSV emit (3M cells, `--tables whole`) |
| UC-07 | 011-08 | Large-table JSON emit, R11.1 single-region streaming |
| UC-08 | 011-07 | JSON multi-sheet / multi-region fallback to `json.dump(fp)` |

---

## 4. Stub-First Compliance Matrix

| Bead | Pass 1 (Stub + E2E Red→Green) | Pass 2 (Logic) |
| --- | --- | --- |
| 011-01 | `CollisionSuffixExhausted` class shell + raise-never-triggered stub; `test_collision_suffix_caps_at_1000` Red. | Add `if suffix > _MAX_COLLISION_SUFFIX: raise CollisionSuffixExhausted(...)` inside loop. Test Green. |
| 011-02 | `TooManyMerges` class shell + `_MAX_MERGES` constant; `test_parse_merges_at_100001_raises` Red. | Add `if len(out) > _MAX_MERGES: raise` in iteration loop; `__all__` export; `_run_with_envelope` branch. Test Green. |
| 011-03 | argparse `--hyperlink-scheme-allowlist` accepted but ignored; `test_hyperlink_scheme_javascript_blocked` Red. | `urlparse(href).scheme.lower()` check in `_extract_hyperlinks_for_region`; warn-on-blocked dedup. Test Green. |
| 011-04 | argparse `--escape-formulas {off,quote,strip}` accepted but ignored; `test_escape_quote_prefixes_<char>` Red. | `_write_region_csv` transform on each cell; JSON-shim no-effect warning. Test Green. |
| 011-05 | Empty `security.md` file with header only; grep-gate test asserts trust-boundary sentence — Red. | Write full content (≥ 80 lines); add `SKILL.md` + ARCH §14.7 cross-link. Test Green. |
| 011-06 | `_GAP_DETECT_MAX_CELLS = 50_000_000` constant only (matrix still list-of-list); 3M-cell synthetic fixture test still Red on memory budget but cap-respecting. | Replace `list[list[bool]]` → `bytearray`; add `_build_claimed_mask` early-exit; update `_gap_detect` consumer guard. Test Green. |
| 011-07 | `with output.open("w") as fp: fp.write(json.dumps(shape, ...))` (still buffers string but writes to fp) — half-step stub; test asserts file output exists but no RSS budget yet. | Switch to `json.dump(shape, fp, ...)` proper; remove the string-buffer copy. RSS budget test Green. |
| 011-08 | `_rows_to_dicts` converted to generator but still consumed via `list(rows_gen)` at call site (no streaming yet); `_stream_single_region_json` helper signature only with `NotImplementedError`. E2E Red on streaming peak-RSS test. | Implement helper body (try/except StopIteration + write loop); `_shape_for_payloads` R11.1 early-detect dispatch. Test Green. |

---

## 5. Risk register (planner-layer)

| Risk | Mitigation |
| --- | --- |
| 011-08 streaming output drifts byte-for-byte from v1 (indent/separator/empty-array edge cases) | `test_R10_stream_byte_identical_to_v1_*` runs same fixture through both paths; `diff -q` gates. Arch-review M3 fix locked empty-payload `"[]\n"` form. |
| 011-06 bytearray flip silently breaks `_split_on_gap` / `_tight_bbox` consumers | `test_R8_bytearray_correctness_vs_listoflist` parametric same-output on 100×100 fixture before any behavioural change can land. |
| Carve-out (4th `xlsx_read/` file) erodes the §9.1 frozen-surface contract long-term | §15.10.5 m5-fix locks the rule "per-fix-with-rationale, not fixed count". 011-06 commits a `KNOWN_ISSUES.md` deletion as its rationale anchor. |
| 011-08 forgets to update `docs/office-skills-backlog.md` with `xlsx-8c-multi-sheet-stream` stub row | Q-15-5 m6-fix promoted this to an explicit acceptance criterion of 011-08 (not a "future task"). |
| `tracemalloc`-based RSS budget tests flake on CI runners with different Python builds | Honest scope: budgets are sized at ≥ 2× margin from the v1 baseline. Tests use `current, peak = get_traced_memory()` and assert against budgets that hold across CPython 3.11/3.12/3.13. |
| 011-05 trust-boundary doc lands but cross-links rot if SKILL.md / ARCHITECTURE.md restructure later | Grep-gate in CI: `grep -F "references/security.md" skills/xlsx/SKILL.md docs/ARCHITECTURE.md` returns ≥ 1 hit each. |

---

## 6. Dependencies & Execution Order

```
Stage 1 (Security axis — independent, can ship in parallel):
    011-01 ──┐
    011-02 ──┤
    011-03 ──┼──> Stage 1 complete
    011-04 ──┤
    011-05 ──┘

Stage 2 (Performance axis — linear):
    011-06 ──> 011-07 ──> 011-08 ──> Stage 2 complete

Stage 3 (Integration):
    All beads → full test suite → validate_skill.py → cross-skill diff gate
              → backlog row update → DONE.
```

**Critical path**: 011-06 → 011-07 → 011-08 (performance axis,
fixture-timing dependency chain). Stage 1 beads are independent and
can be shipped concurrently if the developer parallelises. The
backlog row `xlsx-8a` is marked DONE only when Stage 3 completes.
