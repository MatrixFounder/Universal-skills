# Development Plan: Task 005 — `md_tables2xlsx.py` (xlsx-3)

> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 005, draft v2 APPROVED ([`docs/reviews/task-005-review.md`](reviews/task-005-review.md)).
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — F1–F10 / 10-module shim+package layout APPROVED ([`docs/reviews/task-005-architecture-review.md`](reviews/task-005-architecture-review.md)).
> - **Predecessor PLAN.md** (Task 004 / xlsx-2 / json2xlsx) archived at [`docs/plans/plan-003-json2xlsx.md`](plans/plan-003-json2xlsx.md).
> - **Predecessor PLAN.md** (Task 003 / xlsx-7) archived at [`docs/plans/plan-002-xlsx-check-rules.md`](plans/plan-002-xlsx-check-rules.md).
>
> **D5 closure (delivery shape):** **10 sub-tasks** — within the
> 7–10 envelope locked in TASK §0 D5. Order: 3 scaffolding tasks
> (Stage 0, Phase-1 Red→Green over stubs), 6 logic tasks (Stage 1,
> Phase-2 Bead-by-Bead), 1 finalization task (Stage 2 — docs,
> backlog mark, validator gate).
>
> **Total LOC budget (architect-locked, ARCH §3.2):** ≤ 1 540 LOC
> across `md_tables2xlsx.py` shim (≤ 60) + 10 package modules
> (`__init__.py` ≤ 70 + `loaders.py` ≤ 180 + `tables.py` ≤ 220 +
> `inline.py` ≤ 100 + `coerce.py` ≤ 150 + `naming.py` ≤ 130 +
> `writer.py` ≤ 200 + `cli_helpers.py` ≤ 80 + `cli.py` ≤ 280 +
> `exceptions.py` ≤ 90). Tests add ≈ 850 LOC (600 unit + 250 E2E
> append). Total deliverable ≈ 2 390 LOC including tests. ARCH §3.2
> headroom note: budgets are **ceilings**, not targets — Planner
> does NOT pad sub-tasks to reach them; expected actual ~700-1000
> LOC production code.
>
> **Stub-First applies in canonical Red → Green → Refactor form**
> (NEW component, not a refactor):
>
> - **Phase 1 (Tasks 005.01 – 005.03)** — Skeleton + test scaffolding
>   + cross-cutting glue (exceptions, envelope wiring, same-path
>   guard, stdin reader). Stubs `raise NotImplementedError("xlsx-3
>   stub — task-005-NN")`; E2E + unit tests fail uniformly with
>   `NotImplementedError`. CI is **expected red** for the subset of
>   E2E cases that exercise stubs; envelope / argparse / `--help` /
>   same-path-guard tests turn green at the end of Phase 1.
> - **Phase 2 (Tasks 005.04 – 005.09)** — Per-F-region implementation
>   in dependency order: loaders (F1+F2) → inline+coerce (F5+F6) →
>   tables (F3+F4) → naming (F7) → writer (F8) → cli + post-validate
>   (F9+F10 logic). Each task turns its slice of unit + E2E fixtures
>   green.
> - **Phase 3 (Task 005.10)** — SKILL.md update + `.AGENTS.md` final
>   block + backlog row marked ✅ DONE + `validate_skill.py` gate +
>   cross-skill `diff -q` × 11 silent + (optional) perf-test wiring.

## Task Execution Sequence

### Stage 0 — Scaffolding (Phase 1: stubs raise `NotImplementedError`; only cross-cutting tests turn green by end of stage)

- **[R10 R11.a-b R11.c R12.c]** **Task 005.01** — Package skeleton: 10 stub modules + ≤60-LOC shim + placeholder `.AGENTS.md` block + `validate_skill.py` exit 0 (boundary day-1 gate)
  - **RTM coverage:** **R11.a, R11.b, R11.c** (validator gate, byte-identity invariant, importable structure); **R12.c** (`.AGENTS.md` placeholder); **R10.a** (`NoTablesFound` exception stub).
  - **Description:** [`docs/tasks/task-005-01-skeleton.md`](tasks/task-005-01-skeleton.md)
  - **Locks:** public-helper symbol `convert_md_tables_to_xlsx` in `md_tables2xlsx/__init__.py` (mirrors xlsx-2 `convert_json_to_xlsx` per ARCH M4); shim ≤ 60 LOC re-export only.
  - **Priority:** Critical · **Dependencies:** none

- **[R11.a-d]** **Task 005.02** — E2E test scaffolding (≥ 13 named cases per TASK §5) + unit-test scaffolding (≥ 35 cases per TASK §5) + style-constant drift assertion + 5 fixture files in `examples/`
  - **RTM coverage:** **R11.a, R11.b, R11.c, R11.d** (all test-budget rows).
  - **Description:** [`docs/tasks/task-005-02-test-scaffolding.md`](tasks/task-005-02-test-scaffolding.md)
  - **Locks:** the 13 E2E case tags (T-happy-gfm, T-happy-html, T-stdin-dash, T-same-path, T-no-tables, T-no-tables-allow-empty, T-fenced-code-table-only, T-html-comment-table-only, T-coerce-leading-zero, T-coerce-iso-date, T-sheet-name-sanitisation, T-sheet-name-dedup, T-envelope-cross5-shape); 6 unit-test classes; drift-detection via `sys.path` injection of `csv2xlsx.HEADER_FILL` AND `json2xlsx.writer.HEADER_FILL`.
  - **Priority:** Critical · **Dependencies:** 005.01

- **[R8 R10]** **Task 005.03** — Exceptions module (8 typed `_AppError` subclasses, plain `Exception` subclass model per ARCH precedent) + cross-cutting helpers in `cli_helpers.py` (cross-5 envelope wiring, cross-7 H1 same-path guard, stdin-UTF-8 reader, `XLSX_MD_TABLES_POST_VALIDATE` truthy parser)
  - **RTM coverage:** **R8.a, R8.b, R8.c, R8.d, R10.a, R10.b, R10.c** (cross-cutting + empty-input guards).
  - **Description:** [`docs/tasks/task-005-03-exceptions-cross-cutting.md`](tasks/task-005-03-exceptions-cross-cutting.md)
  - **Locks:** all 8 exceptions inherit from `_AppError`; `assert_distinct_paths` follows symlinks via `Path.resolve()`; `read_stdin_utf8()` is the SINGLE source of stdin decode (loaders.read_input delegates).
  - **Priority:** Critical · **Dependencies:** 005.01

### Stage 1 — Logic Implementation (Phase 2: Bead-by-Bead, per F-region)

- **[R1 R2.b R3.e R9.g R9.i]** **Task 005.04** — `loaders.py` (F1+F2): `read_input` (file/stdin), `scrub_fenced_and_comments` (pre-scan strip), `iter_blocks` (heading + table-block detection), helpers. **First fixtures turn green** (UC-1 happy path discovery, UC-2 stdin entry, T-fenced-code-table-only, T-html-comment-table-only, T-no-tables for fixture without any tables).
  - **RTM coverage:** **R1.a, R1.b, R1.c, R1.d, R2.b (separator-row column-count detection at block level), R3.e (skip fenced/comment regions before tables.py sees them), R9.g (blockquoted-table skip lock), R9.i (`<style>`/`<script>` strip lock).**
  - **Description:** [`docs/tasks/task-005-04-loaders.md`](tasks/task-005-04-loaders.md)
  - **Locks:** ARCH §11 Q1 default (indented code blocks also stripped pre-scan; corresponding E2E `T-indented-code-block-skip` added per ARCH m7 review-fix); F2 `_locate_heading` ignores `<hN>` inside `<table>` blocks (ARCH m6).
  - **Priority:** Critical · **Dependencies:** 005.03

- **[R5 R6]** **Task 005.05** — `inline.py` (F5) + `coerce.py` (F6): `strip_inline_markdown`, `_decode_html_entities` (F5); `coerce_column`, `_coerce_cell_numeric`, `_coerce_cell_date`, `_handle_aware_tz`, `_has_leading_zero`, dataclass `CoerceOptions` (F6). **Cell-value fixtures turn green** (T-coerce-leading-zero, T-coerce-iso-date, all inline-strip unit cases).
  - **RTM coverage:** **R5.a-g** (all inline-strip sub-features); **R6.a-e** (numeric/ISO-date/alignment/empty-cell/no-coerce).
  - **Description:** [`docs/tasks/task-005-05-inline-coerce.md`](tasks/task-005-05-inline-coerce.md)
  - **Locks:** `_has_leading_zero` is the gate (ARCH m10): per-cell coercion runs only if the column-level gate is open; `_coerce_cell_date` uses dateutil ONLY after strict regex pre-filter (rejects `"May 11"`-style lenient guesses).
  - **Priority:** Critical · **Dependencies:** 005.04

- **[R2 R3]** **Task 005.06** — `tables.py` (F3+F4): `parse_table` dispatcher (ARCH m2), `parse_pipe_table` (GFM), `parse_html_table` (HTML with M1 `_HTML_PARSER` lock — `no_network=True`, `huge_tree=False`, `recover=True`), `_split_row`, `_parse_alignment_marker`, `_walk_rows`, `_expand_spans`. **Table-parsing fixtures turn green** (T-happy-gfm 3-sheet, T-happy-html with merged cells, R9.h overlapping-colspan stderr warning).
  - **RTM coverage:** **R2.a-e** (GFM pipe parser); **R3.a-e** (HTML parser incl. colspan/rowspan, thead/tbody, entity decode, fenced/comment skip).
  - **Description:** [`docs/tasks/task-005-06-tables.md`](tasks/task-005-06-tables.md)
  - **Locks:** module-level singleton `_HTML_PARSER` (ARCH M1) NOT re-constructed per call; `test_html_billion_laughs_neutered` asserts `_HTML_PARSER.no_network is True` AND wall-clock ≤ 100 ms.
  - **Priority:** Critical · **Dependencies:** 005.05

- **[R4]** **Task 005.07** — `naming.py` (F7): `class SheetNameResolver`, `_truncate_utf16` (m1 review-fix; UTF-16 code-unit-aware), `_sanitise_step2/3/4`, `_dedup_step8` (M3 review-fix: prefix-truncation via `_truncate_utf16`, NOT Python code-point slicing). **Sheet-naming fixtures turn green** (T-sheet-name-sanitisation, T-sheet-name-dedup, all TestSheetNaming unit cases).
  - **RTM coverage:** **R4.a, R4.b, R4.c, R4.d, R4.e** (the locked 9-step algorithm + `--sheet-prefix` override).
  - **Description:** [`docs/tasks/task-005-07-naming.md`](tasks/task-005-07-naming.md)
  - **Locks:** unit test `test_dedup_emoji_prefix_utf16_safe` (the M3 regression — 16-emoji collision) asserts resulting name `len(name.encode("utf-16-le")) // 2 <= 31`; `--sheet-prefix` mode short-circuits the heading-walk per ARCH m12.
  - **Priority:** Critical · **Dependencies:** 005.05 (F5 inline strip consumed for heading text)

- **[R6.c R7]** **Task 005.08** — `writer.py` (F8): `write_workbook`, `_build_sheet`, `_style_header_row`, `_apply_merges` (with overlap try/except per §11.8), `_apply_alignment` (per-column GFM-marker → openpyxl `cell.alignment.horizontal`), `_size_columns`. Style constants `HEADER_FILL`/`HEADER_FONT`/`HEADER_ALIGN`/`MAX_COL_WIDTH` copied from csv2xlsx with mirror-comment. **Workbook-output fixtures turn green** (all happy paths now produce real `.xlsx` files; UC-3 merged-cells passing; R10.c zero-row-table edge case).
  - **RTM coverage:** **R6.c** (GFM alignment carryover); **R7.a-e** (all output-styling sub-features); also closes ARCH m11 (zero-row-table contract).
  - **Description:** [`docs/tasks/task-005-08-writer.md`](tasks/task-005-08-writer.md)
  - **Locks:** drift-detection assertion (ARCH m8): `csv2xlsx.HEADER_FILL.fgColor.rgb in ("F2F2F2", "00F2F2F2")` AND `json2xlsx.writer.HEADER_FILL.fgColor.rgb` matches; A8 parent-dir auto-create (`output.parent.mkdir(parents=True, exist_ok=True)`).
  - **Priority:** Critical · **Dependencies:** 005.06, 005.07

- **[R8 R9 R10]** **Task 005.09** — `cli.py` (F9) + post-validate logic (F10): `build_parser` (8 flags per TASK §9), `main`, `_run` linear pipeline F1→F8 + post-validate hook. `convert_md_tables_to_xlsx` public helper in `__init__.py` (M4 lock: `**kwargs -> int` via argparse with `--flag=value` atomic-token form). Top-of-`_run` `_AppError` → cross-5 envelope catch. **All remaining E2E cases turn green** (T-stdin-dash, T-same-path, T-no-tables-allow-empty, T-envelope-cross5-shape, the full happy path with post-validate hook).
  - **RTM coverage:** **R8.a (orchestration), R9 (all 8 CLI flag sub-features), R10.b, R10.d (orchestrator-level checks)**, **R11.c (post-validate hook logic on top of 005-03 stub)**.
  - **Description:** [`docs/tasks/task-005-09-cli-and-post-validate.md`](tasks/task-005-09-cli-and-post-validate.md)
  - **Locks:** `cli.py` LOC ≤ 280 (M2 lock; guardrail at 280, NOT 320); env-truthy parser allowlist `{"1","true","yes","on"}` (xlsx-2 parity); post-validate failure unlinks output (xlsx-2 parity).
  - **Priority:** Critical · **Dependencies:** 005.08

### Stage 2 — Finalization (Phase 3: docs, gates, ✅ DONE)

- **[R11 R12]** **Task 005.10** — SKILL.md update (§1 Red Flags + §2 Capabilities + §4 Script Contract) + `scripts/.AGENTS.md` final block + backlog row `xlsx-3` marked ✅ DONE with status line + perf-test wiring under `RUN_PERF_TESTS=1` (no CI gate) + cross-skill `diff -q` × 11 invocations silent + `validate_skill.py skills/xlsx` exit 0
  - **RTM coverage:** **R11.e (perf opt-in), R12.a, R12.b, R12.c, R12.d** — all docs/integration sub-features.
  - **Description:** [`docs/tasks/task-005-10-final-docs.md`](tasks/task-005-10-final-docs.md)
  - **Locks:** SKILL.md §1 adds new Red Flag for "I'll just regex-replace `\|` to extract markdown tables"; backlog row update mirrors xlsx-2's pattern (LOC + test counts + sarcasmotron status); cross-skill `diff -q` × 11 from ARCH §9 silent.
  - **Priority:** High · **Dependencies:** 005.09

## RTM Coverage Matrix

| RTM Row | Sub-feature scope | Closing task(s) |
| :---: | :--- | :---: |
| **R1** | Read markdown from file / stdin / encoding flag / empty-input | 005.04 |
| **R2** | GFM pipe parser (header + separator + trailing-pipe + escaped-pipe + alignment) | 005.04 (block detection) + 005.06 (full parse) |
| **R3** | HTML `<table>` parser (thead/tbody, th/td, colspan/rowspan, entity decode, fenced/comment skip) | 005.04 (skip) + 005.06 (parse) |
| **R4** | Sheet-name resolution + 9-step sanitisation algorithm + `--sheet-prefix` | 005.07 |
| **R5** | Inline-markdown strip helper (bold/italic/code/link/strike/br/entities) | 005.05 (F5 portion) |
| **R6** | Cell coercion (numeric leading-zero-aware + ISO-date + alignment + empty→None + `--no-coerce`) | 005.05 (numeric/date/empty/--no-coerce) + 005.08 (alignment carryover) |
| **R7** | Output styling (bold header, freeze, auto-filter, column widths, opt-outs) | 005.08 |
| **R8** | Cross-cutting parity (cross-5 envelope, cross-7 H1 same-path, stdin `-`) | 005.03 (helpers + exceptions) + 005.09 (CLI wiring + orchestrator catch) |
| **R9** | Honest-scope regression locks (a)–(j) — 9 active tests + 1 doc-only | 005.04 (R9.g/i — pre-scan: blockquoted + `<style>`/`<script>`) + 005.05 (R9.b — §11.2 MultiMarkdown literal text [plan-review M1 fix]; R9.c — §11.3 `<br>` literal-newline + no wrap_text; R9.d — §11.4 no rich-text Runs) + 005.06 (R9.c-html — colspan/rowspan-only-in-HTML; M1 billion-laughs neuter) + 005.07 (UTF-16 dedup M3 lock) + 005.08 (R9.e — §11.5 no formula evaluation; R9.h — §11.8 overlap-colspan stderr warning [plan-review m1 fix]) + 005.09 (R9.a — §11.1 RST grid `NoTablesFound`; R9.f — §11.6 `--strict-dates` argparse-rejected); R9.j (§11.10 TOCTOU) doc-only per §11 preamble |
| **R10** | Empty-input guards (`NoTablesFound`, `--allow-empty`, zero-row-table contract) | 005.03 (exception class stubs) + 005.04 (zero-tables detection) + 005.08 (zero-row contract) + 005.09 (`--allow-empty` + Empty placeholder) |
| **R11** | Tests (unit ≥ 35, E2E ≥ 13, drift-detection, validator, replication diff) | 005.02 (scaffolding) + 005.04..09 (logic green) + 005.10 (final gate) |
| **R12** | Docs (SKILL.md, `.AGENTS.md`, examples/, backlog row, references if any) | 005.01 (R12.c `.AGENTS.md` placeholder) + 005.10 (R12.a/b/c/d full) |

## Use Case Coverage

| Use Case | Closing task(s) |
| :--- | :--- |
| UC-1 — Convert tech-spec markdown to multi-sheet workbook (HAPPY PATH) | 005.04 (block discovery) + 005.05 (cell coerce) + 005.06 (parse) + 005.07 (sheet name) + 005.08 (write) + 005.09 (CLI) |
| UC-2 — Stream markdown from stdin | 005.03 (stdin reader) + 005.04 (delegation) + 005.09 (CLI `-` handling) |
| UC-3 — HTML `<table>` with colspan/rowspan | 005.06 (parse + merge ranges) + 005.08 (`_apply_merges` with overlap try/except) |
| UC-4 — Same-path collision (input == output) | 005.03 (`assert_distinct_paths` helper) + 005.09 (CLI wiring + `--json-errors` envelope) |

## Open-Question Closure Trail

| Question (source) | Closing task | Resolution lock |
| :--- | :---: | :--- |
| ARCH Q1 — pre-scan strips indented code blocks? | 005.04 | Default YES; E2E `T-indented-code-block-skip` added per ARCH m7 |
| ARCH Q2 — `--sheet-prefix` × heading interaction | 005.07 | Prefix mode ignores `heading`; counter increments per-call; dedup step 8 is a no-op |
| ARCH Q3 — Diagnostics for M3 retry overflow | 005.07 | `InvalidSheetName` envelope `details: {original, retry_cap: 99, first_collisions: ...[:10]}` |
| TASK m4 — UC-3 A2 lxml leniency test | 005.06 | `TestHtmlParser::test_malformed_html_lxml_lenient_recovery` unit case |
| TASK m5 — `--sheet-prefix` + `--allow-empty` interaction | 005.09 | Placeholder sheet = `Empty` (NOT `<prefix>-1`); locked in ARCH §10 A6 |
| TASK m8 promotions D6/D7/D8 | (already locked in TASK) | D6 indented-code default YES; D7 no Source-cell metadata; D8 env-var OFF default |

## Platform-IO Errors (envelope-only, NOT typed `_AppError`)

The 8 typed `_AppError` subclasses cover xlsx-3's logical error
taxonomy (empty input, no tables found, malformed-table-skip,
encoding error, invalid sheet name, same-path collision,
post-validate failure). Platform-IO failures (`FileNotFoundError`,
generic `OSError` on read/write) are **deliberately NOT** added to
the taxonomy — they're caught at the CLI layer in `_run` and surfaced
via direct `report_error(message, code=1, error_type="FileNotFound"
| "IOError", details={"path": …})` calls. This is intentional design
mirroring xlsx-2 PLAN platform-IO note — platform errors are best
surfaced via free-form message rather than a synthetic typed-error
class that would just wrap `str(exc)`.

## Phase-Boundary Gates

Between each task, the orchestrator MUST verify:

1. **Validator gate:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
2. **Byte-identity gate (after every commit):** eleven `diff -q` invocations from ARCH §9 silent.
3. **Test gate:** `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0; `bash skills/xlsx/scripts/tests/test_e2e.sh` exits 0.
4. **Session-state persistence:** `update_state.py` invoked at each task boundary (mode `VDD-Develop`, task `Task-005-md-tables2xlsx`, status `Task-NN-Done`).

## Honest-Scope Carry-Forward (TASK §11 + ARCH §10)

The following limitations are **deliberately accepted in v1**. The
chain MUST NOT silently widen scope. If implementation work surfaces
a limitation as blocking, **stop and escalate** — open a new TASK
Open Question or a v2 backlog row (`xlsx-3a`, `xlsx-3b`, …):

- **§11.1** No RST grid tables (R9.a lock).
- **§11.2** No MultiMarkdown / PHP-Markdown-Extra extensions (R9.b lock).
- **§11.3** No `wrap_text=True` on `<br>` cells (R9.c lock).
- **§11.4** No rich-text Runs (R9.d lock).
- **§11.5** No formula resolution (R9.e lock).
- **§11.6** No `--strict-dates` flag (R9.f lock).
- **§11.7** Blockquoted tables skipped (R9.g lock).
- **§11.8** Overlapping HTML merge → stderr warning, first wins (R9.h lock).
- **§11.9** `<style>` / `<script>` blocks skipped (R9.i lock).
- **§11.10** Symlink TOCTOU acceptance — documentation-only lock.
- **ARCH A1** No openpyxl `write_only=True` mode.
- **ARCH A2** No `--output -` stdout streaming.
- **ARCH A3** No automatic Excel string truncation.
- **ARCH A4** No CSS-driven formatting from HTML.
- **ARCH A5** No empty-cell `None` vs `""` distinction.
- **ARCH A6** `--sheet-prefix` × `--allow-empty` → placeholder `Empty` (NOT `<prefix>-1`).
- **ARCH A7** `lxml.html.HTMLParser(no_network=True, huge_tree=False, recover=True)` enforced.
- **ARCH A8** Output parent-directory auto-create (csv2xlsx parity, divergence from xlsx-2).
