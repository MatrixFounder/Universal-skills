# Known Issues

Catalogue of **acknowledged but currently-unfixed** issues in this
repository. Each entry is a deliberate deferral, NOT a bug to
re-discover. Future agents (and humans) MUST read this file before
opening a new task that touches the same surface — see
[CLAUDE.agentic.md](../CLAUDE.agentic.md) §"Pipeline §1 Analysis
Phase" which mandates this read.

**Entry lifecycle**: an issue lives here while it is **documented +
deferred**. When a fix lands, the entry is moved to a section
"Resolved" with a commit-hash pointer, or simply deleted with the
fix commit referenced from the related task/backlog row.

---

## Performance

> **PERF-HIGH-1** (matrix size + cap) was **closed by xlsx-8a-06**
> on 2026-05-13: `_gap_detect` + `_build_claimed_mask` switched to
> `bytearray` flat buffers (8× memory reduction) and
> `_GAP_DETECT_MAX_CELLS` raised 1M → 50M. Entry removed in the
> commit that landed those changes. See `docs/PLAN.md` 011-06
> and `docs/ARCHITECTURE.md` §15.10.

### PERF-HIGH-2 — `payloads_list = list(payloads)` materialises generators (narrowed residual after xlsx-8a-07/08)

- **Status**: **Partially closed (2026-05-13, xlsx-8a-07 / xlsx-8a-08)**.
  - R9 / xlsx-8a-07 drops the `json.dumps`-string-buffer copy for
    JSON file output (one of three full-payload copies removed —
    `emit_json.py:79` reference below no longer holds; the
    `json.dump(fp)` path goes straight to the file).
  - R10 / xlsx-8a-08 **streams the emit-side R11.1 single-region**
    output (the most common large-table case) row-by-row — drops
    the full `shape` dict + `_rows_to_dicts` materialisation from
    the emit path. **Design target**: peak RSS ≤ 200 MB on
    3M-cell payloads vs 1-1.5 GB in v1. **As-shipped honest-scope**:
    upstream `read_table` + `apply_merge_policy` still materialise
    `table_data.rows` (~180 MB on 3M cells), so the realistic peak
    is closer to ~400-600 MB — still a 2-3× win over v1, but not
    the 200 MB design target. The 200 MB budget is **unmeasured
    at the 3M-cell scale** in xlsx-8a's test suite (see
    `docs/ARCHITECTURE.md` §15.10.6 honest-scope note); a future
    task can lift the read-side to a streaming generator or add
    a 3M-cell `tracemalloc` regression to pin the actual budget.
  - **Residual**: R11.2-4 multi-sheet / multi-region shapes still
    build the full `shape` dict in memory (`_shape_for_payloads`
    in `emit_json.py`); and CSV multi-region path's
    `payloads_list = list(payloads)` in
    [`emit_csv.py:59`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py#L59)
    still materialises the **region list** (per-row writes already
    stream via `csv.writer.writerow`).
- **Severity**: MED (lowered from HIGH after the R11.1 closure).
- **Location** (residual after xlsx-8a):
  - [`skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) line ~59:
    `payloads_list = list(payloads)` — **region-list materialisation
    only**; per-row writes already stream via `csv.writer.writerow`.
  - `_shape_for_payloads` R11.2-4 branches in `emit_json.py`
    build a full dict-of-arrays shape before serialisation.
- **Workaround for users**: prefer single-sheet single-region
  outputs (R11.1 path is fully streamed). For multi-sheet
  workbooks at 3M+ cells, split the input or use `--sheet <NAME>`
  to bound the working set.
- **Fix path** (when prioritised): per-sheet streaming for R11.2
  (multi-sheet single-region) — open ``{``, for each sheet write
  ``"name": [<stream rows>]`` + ``,``/``}`` closer. R11.3-4 nested
  dicts cannot be RFC-8259-streamed without inventing a chunked-
  encoding contract. CSV multi-region per-region streaming is
  feasible (each region writes its own file) but needs an
  ``n_regions`` pre-count for dispatch.
- **Related**: future ticket
  **`xlsx-8c-multi-sheet-stream`** (registered in
  [`docs/office-skills-backlog.md`](office-skills-backlog.md) on
  2026-05-13 by 011-08); open when a real R11.2 large-table
  workload is observed.
- **Do not**: claim this as "fixed" by trimming
  `--include-hyperlinks` or `--include-formulas` — those reduce
  per-cell payload size, not the structural materialisation cost.

---

## XLSX-10B-DEFER (xlsx-7 refactor to consume xlsx_read)

**Status:** DEFERRED (14-day timer started 2026-05-14, deadline
2026-05-28).
**Backlog row:** `xlsx-10.B` in
[`docs/office-skills-backlog.md`](office-skills-backlog.md).
**Context:** xlsx-7 (`xlsx_check_rules/`) duplicates a portion of
xlsx-10.A `xlsx_read/` reader logic. The refactor was deferred at
xlsx-10.A merge to bound the v1 surface; xlsx-9 merge starts the
14-day ownership-bounded timer. If unaddressed by 2026-05-28, the
duplication becomes a regression risk for any future
`xlsx_read` API change.
**Owner:** TBD (assigned at xlsx-10.B kickoff).
**Workaround:** None required for xlsx-7's current functionality;
the duplication is correctness-preserving as of 2026-05-14.

---

## XLSX-9-LOWS-DEFER (vdd-multi iter-1+2 LOW-tier findings, deferred to xlsx-9b)

**Status:** DEFERRED to a future `xlsx-9b` follow-up task.
**Backlog row:** none yet (open as `xlsx-9b` if user prioritises).
**Severity:** LOW (paper-cut tier; no HIGH or MEDIUM remain
unaddressed).
**Context:** vdd-multi iterations 1 and 2 (2026-05-14) ran 3 critics
in parallel and surfaced 4 HIGH + 10 MEDIUM + 13 LOW + 13 INFO
findings on the shipped xlsx-9 code. All HIGH + MEDIUM are fixed
with 39 new regression tests. The 13 LOW findings are intentionally
deferred — none are exploitable in the documented trust model, and
none are blockers. Catalogued below for posterity / future xlsx-9b
prioritisation.

### Logic-tier LOWs

- **L1 — `_has_body_merges` ignores vertical-merge col-0.** In
  `emit_hybrid.py:_has_body_merges`, the heuristic looks for `None`
  cells at `col_idx > 0` (horizontal merge detection). A vertical
  merge anchored at column 0 produces `None` at column 0 for
  subsequent rows — which the predicate skips. Hybrid mode would
  emit GFM (lossy) instead of promoting to HTML.
  **Fix path:** widen heuristic to also flag `col_idx==0 and row>0`
  with a column-history check, OR expose `reader.merges_in_region`
  from xlsx-10.B for accurate merge-span detection.
- **L2 — `INPUT=None` → `Internal error: TypeError`.** When the
  positional INPUT is omitted (`python3 xlsx2md.py`), `_resolve_paths`
  hits `Path(None).resolve(strict=True)` → `TypeError` → terminal
  catch-all → InternalError code 7. The error message is unhelpful
  ("Internal error: TypeError"). **Fix path:** add explicit
  `if args.INPUT is None: raise argparse.ArgumentTypeError("INPUT required")`
  at the top of `_resolve_paths`.
- **L7 — `--no-table-autodetect` bypasses R14h gate.** The
  `_validate_flag_combo` gate at `cli.py:296-310` checks
  `not args.no_table_autodetect AND not args.no_split` to permit
  int `--header-rows`. `--no-table-autodetect` filters to gap-detect
  regions only, which can still be multiple → int header-rows N
  applied uniformly is still a hazard. Currently locked by
  `test_cli_envelopes.py:91-96`. **Fix path:** tighten the gate to
  reject `--header-rows N + --no-table-autodetect` OR document the
  exception.
- **L8 — Empty sheet silently omits `## SheetName` H2.**
  `emit_workbook_md` only emits H2 when at least one region yields.
  Multi-sheet workbook with an intentionally-empty "Notes" sheet
  produces output that silently omits the sheet entirely.
  **Fix path:** emit `## SheetName\n\n*(empty sheet)*\n\n` for
  zero-region sheets, OR document in honest-scope §1.4.
- **L9 — `--sheet=all` collides with workbook sheet named `"all"`.**
  The sentinel value `"all"` is reserved; a workbook with a sheet
  literally named `"all"` cannot be targeted individually.
  **Fix path:** add a separate `--all-sheets` flag, OR document.

### Security-tier LOWs (all honest-scope per `references/security.md` §1 trust model)

- **Sec-LOW-1 — D-A9 cell-value markdown pass-through.** GFM mode
  passes `*`, `_`, `` ` ``, `[`, `]`, `(`, `)` through as
  "markdown-in-cell affordance". A workbook cell with value
  `"[click](javascript:alert(1))"` (literal string, no hyperlink
  object) emits as a parseable Markdown link in GFM, bypassing the
  scheme-allowlist (which only filters hyperlinks attached as
  workbook hyperlink objects). Pre-existing limitation, not iter-2
  regression. **Fix path:** add `references/security.md` §2.7 entry
  cataloguing this — or harden with `[`/`]`/`(`/`)` escaping at the
  cost of breaking the markdown-in-cell affordance.
- **Sec-LOW-2 — M5 `<output>.partial` symlink / TOCTOU.** `open(temp_path, "w")`
  follows symlinks. Attacker-controlled output directories where
  adversaries can pre-plant `<output>.md.partial` as a symlink are
  out of scope per `references/security.md` §1 (non-multi-tenant
  output directory). **Fix path:** O_NOFOLLOW per-component (xlsx-8d
  pattern); or document the trust assumption at the M5 code site.
- **Sec-LOW-3 — M3 `reader._read_only` closed-API crossing
  undocumented at architecture layer.** This is the second
  D-A5 exception (first being `reader._wb` in Path C′). A future
  xlsx_read rename would silently disable the streaming-mode
  warning. **Fix path:** promote `WorkbookReader.is_read_only` to
  public API in xlsx_read; consume the public property.
- **Sec-LOW-4 — `_post_validate_output` unbounded `read_text`.**
  Opt-in via `XLSX_XLSX2MD_POST_VALIDATE=1`. A 10 GB output OOMs
  the validator. **Fix path:** bound the read to 1 MiB head
  (`fp.read(1024*1024)`) — substring markers appear early.
- **Sec-LOW-5 — Log injection via CR/LF in sheet name reaching
  warning messages.** `cell_addr_prefix=f"{sheet_info.name}!"`
  feeds workbook sheet names (which can contain `\r\n` via raw XML
  edit) directly into warning text streamed to stderr. Defense in
  depth, not exploitable per trust model §1. **Fix path:**
  `.replace("\r", "\\r").replace("\n", "\\n")` on sheet names before
  log interpolation.
- **Sec-LOW-6 — `str(value or "")` truthiness bug with `value=0`.**
  Three sites in `inline.py` (lines 207, 227, 249): a cell value
  of integer `0` or boolean `False` with a hyperlink renders as
  empty display text. Correctness bug, not security. **Fix path:**
  use `str(value) if value is not None else ""`.

### Performance-tier LOWs

- **Perf-LOW-1 — `_make_cell_addr` closure rebuilt per row in HTML
  emit.** `emit_html._emit_tbody` defines the closure inside the
  `for r_idx, row` loop. ~80ms per 100K-row workbook (closure
  creation overhead). **Fix path:** hoist the function definition
  out of the row loop and pass `abs_row` as a positional argument.
- **Perf-LOW-2 — Defensive `list(table_data.rows)` /
  `list(table_data.headers)` copies in both emit modules.** Not
  mutated downstream; copies are pure waste. **Fix path:** remove
  the `list()` wrapping. ~50ms per 100K-row table; ~800KB peak
  memory delta.
- **Perf-LOW-3 — Hybrid mode 1-2 extra O(cells) scans.**
  `_has_body_merges`, `_is_multi_row_header`, `_has_formula_cells`
  each iterate the full table before emit decides GFM vs HTML.
  Architectural trade-off; documented in module docstring.
  **Fix path:** expose merge-count / formula-presence metadata
  from xlsx_read so the predicates become O(1) (requires
  xlsx-10.B-scope API extension).

**Workaround:** None — all items are LOW severity and the chain is
production-ready as of 2026-05-14. Promoting any item to a
follow-up task is at user discretion.

---

## wiki-ingest — RESOLVED post-TASK-015 (2026-05-26)

> **All 15 wiki-ingest deferred findings have been resolved.** The 12
> cosmetic items from the May-2026 VDD-multi audit + the 3 bugs surfaced
> by Sarcasmotron during TASK 015 (M2-015-01, P-M3-015-02, S-M1b-015-09)
> are fixed. Regression tests live in
> [`skills/wiki-ingest/scripts/tests/test_known_issues_resolved.py`](../skills/wiki-ingest/scripts/tests/test_known_issues_resolved.py).

| ID            | Fix                                                                                                              |
|---------------|------------------------------------------------------------------------------------------------------------------|
| **L-H2**      | `replace_section_body` strips at most one leading `\n` (was: blanket `.lstrip("\n")`).                            |
| **L-L2**      | Determined to be a non-bug — `content or load_asset(...)` fallback ensures content is never truly empty. Test locks "exactly-one-blank-line-between-entries" invariant. |
| **L-L3**      | `_existing_lines` now stitches contiguous `> ` lines into one blockquote entry (Contradiction blocks no longer fragment). |
| **L-L8**      | SKILL.md filesystem-safety paragraph now documents `[`, `]`, `|`, `^` rejection + NFKC normalisation + slug-equivalent collision detection. |
| **L-L9**      | `register-summary --force` now snapshots prior content to `<slug>.md.backup-<UTC-timestamp>` before overwrite; backup path is surfaced in the JSON output. |
| **S-L2**      | `tail_log` regex is ASCII-anchored (`\d{4}-\d{2}-\d{2}` with `re.A`); Unicode-digit decoy dates rejected.            |
| **S-L3**      | `_strip_quotes` mismatched-pair behaviour locked in docstring (pass-through-unchanged, NOT silent corruption).      |
| **P-L1**      | `_check_case_collision` uses `os.scandir()` (~3-5× cheaper at 10k+ files).                                          |
| **P-L2**      | `tail_log` fast path: seek to last 64 KiB on logs >64 KiB; full-file read only on fallback.                         |
| **P-L5**      | `_count_md_structure` decorated with `functools.lru_cache(512)` — `_pick_primary` + `classify-folder` no longer double-read the same candidates. |
| **P-M3**      | `_compile_section_header_re(header_text)` LRU-cached at module level (was: rebuilt per `find_section` call).        |
| **P-M5**      | `cmd_find` uses ONE merged-regex pass (`(?P<t0>...)|(?P<t1>...)`) instead of N `.count()` passes.                    |
| **M2-015-01** | `_atomic_write_text` unlinks the tmp file on `os.write` / `os.fsync` failure (no orphan `.tmp` litter on crash).     |
| **P-M3-015-02** | `replace_section_body` accepts `masked=` and propagates to `find_section` (batch K-section rewrites pay mask cost once). |
| **S-M1b-015-09** | `register-summary` checks `is_symlink()` on the UNRESOLVED path BEFORE `.resolve()` (defence no longer no-op). Sensitive-path blocklist + inbox containment now check both unresolved AND resolved forms. |

The regression-test file enforces all 15 fixes; restoring a regression
requires deleting both the fix AND the test.

---

## WIKI-INGEST-016-VDD-DEFER (TASK 016 VDD-multi residuals)

**Status:** DEFERRED to a future `wiki-ingest-016b` follow-up task.
**Backlog row:** none yet (open as `wiki-ingest-016b` if user prioritises).
**Severity:** LOW (cosmetic / lint-side false-positive tier; no HIGH or
MEDIUM remain unaddressed).
**Context:** VDD-multi over TASK 016 (cross-course promotion / demotion)
ran 3 critics across 2 iterations (2026-05-26). All CRITICAL + HIGH
findings (17 fixes total) are closed with regression tests in
[`skills/wiki-ingest/scripts/tests/`](../skills/wiki-ingest/scripts/tests/).
Two lint-side false-positives + nine cosmetic/micro nits are
intentionally deferred — none are blockers; the chain ships clean.
Catalogued below for posterity / `wiki-ingest-016b` prioritisation.

### Lint-side false positives

- **L-Smoke-1 — Cross-layer dangling-link semantics wider than the
  spec.** `lint` treats a name present ANYWHERE in the vault (root or
  any course) as "resolvable" → cross-course references between two
  courses' `_concepts/`/`_entities/` are NOT flagged dangling. Spec
  §4.1 implied stricter "same-course-only resolution"; the
  implementation chose the LLM-friendly "is this resolvable from any
  layer" semantics. Locked by
  [`tests/commands/test_lint_two_tier.py::TestDanglingRefinement::test_course_to_other_course_link_is_dangling`](../skills/wiki-ingest/scripts/tests/commands/test_lint_two_tier.py).
  **Fix path:** if stricter semantics ever needed, restrict
  `known_global` to `<root_layer> ∪ <current_course>` in `_layer_findings`.

- **L-Smoke-2 — Vault-relative footnote targets register as
  `dangling_link_targets`.** After `promote`, the root page's footnote
  defs use vault-relative form `[[Lessons/A/_sources/foo]]`. The
  existing dangling-link check parses `[[<target>]]` as wikilinks
  expecting bare filename → flags them as dangling. Cosmetic noise; no
  correctness break. **Fix path:** in two-tier mode, exclude wikilink
  targets matching `<course_rel>/_sources/<slug>` for any
  `course_rel ∈ discover_courses(vault_root)` from the dangling check.

### Cosmetic / micro-optimisation (deferred indefinitely)

| ID           | Location                                                   | Description                                                                                                         |
|--------------|------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| **L-016-L1** | `commands/init.py:_execute_root`                           | UX foot-gun: `init --root <new_dir>` dies (target must exist) while `init <new_dir>` (no flag) creates intermediates. Sharper error message wanted: `mkdir -p` hint. |
| **L-016-L2** | `_vault.py:discover_courses`                                | Double symlink filter: `os.walk(..., followlinks=False)` + per-dir `_skip_symlink` filter. Defense-in-depth but wasteful. |
| **L-016-L3** | `_vault.py:_peek_schema_version`                            | Exception filter `(ValueError, UnicodeError, KeyError)` doesn't include `TypeError`/`AttributeError`. `isinstance(fm, dict)` already protects; defensive only. |
| **L-016-L4** | `commands/upsert_page.py:_rewrite_one_footnote`             | Idempotent re-write emits an unnecessary write when target already matches. Trivial early-exit possible.            |
| **L-016-L5** | `commands/promote.py:_serialise` + `commands/demote.py:_serialise` | ~30 LoC scalar-serialise wrapper duplicated. Iter-1 partially de-duplicated (list fields delegate to `_frontmatter._serialize_yaml_list_field`); scalar wrappers still copy each other. |
| **S-016-L1** | `commands/promote.py:_FOOTNOTE_DEF_PATTERN`                 | Regex slug class `[^\]]+` softer than `_safe_name`. Gated at write-time by `_safe_name`; pattern alignment is cosmetic. |
| **S-016-L3** | `commands/init.py:_execute_root`                            | No path-containment enforcement on `--root <path>` (operator-trusted per security trust-model bullet 1). Documented; not exploitable. |
| **P-016-M3** | `commands/promote.py:_slug_to_course_map`                   | Globs every course's `_sources/` per-promote. Acceptable for single CLI invocation; flag if `promote-batch` mode ever lands. |
| **P-016-M4** | `commands/upsert_page.py:find_vault_root`                   | Called unconditionally per upsert. ~3–5 stat calls per invocation. Acceptable for CLI model; flag if bulk-upsert in-process mode lands. |

### Material defects intentionally NOT in this defer (open for `wiki-ingest-016b`)

These two items are **NOT cosmetic** and would warrant a deliberate fix
pass when prioritised — recorded here ONLY to clarify they are NOT in
the "deferred indefinitely" bucket:

- **Logic-016-H3 — `_facts_similar_predicate` heuristic noise.**
  Q-10 PLAN.md locked literal-line-diff; the 2-word-prefix matcher
  produces false positives (`"Risk premium is 5%"` vs `"Risk premium
  accounts for liquidity"`) and false negatives (facts <3 words skipped
  entirely). Threshold tuning + numeric-token-aware divergence check
  recommended.
- **Logic-016-M1 — Cross-course duplicate scan NOT case-folded.**
  Inconsistent with v1 L-L7 `concept_freq` (which uses `.lower()`).
  On case-sensitive filesystems, `Sharpe Score.md` and `sharpe score.md`
  across two courses are NOT detected as duplicates. Apply same
  `.lower()` discipline in `_collect_layer_filenames` /
  cross-course-duplicate aggregation.

**Workaround:** None — all items are LOW severity (cosmetic) or
diagnostic-only (lint false-positives). Promoting any item to a
follow-up task is at user discretion.

---

## PDF-4 (`pdf_ocr.py`) — vdd-multi deferred LOWs (2026-06-03)

**Status:** DEFERRED (LOW; documented-scope, not regressions).
**Backlog row:** `pdf-4` in
[`docs/office-skills-backlog.md`](office-skills-backlog.md).
**Context:** `/vdd-multi` over TASK 018 ran 3 parallel critics across 3
iterations. All CRITICAL/HIGH/MED findings are fixed with regression tests
(non-zero ocrmypdf `ExitCode` no longer promoted to success; raw `OSError` on
an unwritable OUTPUT dir now maps to `OutputWriteFailed`; decrypted-scratch
leak + `KeyError` window closed; `.partial` hardened to `mkstemp` O_EXCL 0600;
`_installed_languages`/exception-mapping test gaps closed; fixture rebuild +
double `--list-langs` perf items closed). Two LOW items are intentionally
deferred:

- **PDF4-L1 — `--sidecar` is not written atomically.** `run_ocr`
  ([`skills/pdf/scripts/pdf_ocr.py`](../skills/pdf/scripts/pdf_ocr.py)) passes
  `--sidecar` to ocrmypdf as the final path, while the searchable PDF goes
  through an mkstemp `.partial` + `os.replace`. On a mid-OCR failure a
  stale/partial `sidecar.txt` can remain (the I-3 atomicity invariant + the
  `finally` cleanup cover only the PDF and the decrypted scratch). **Severity:**
  LOW (best-effort side output; the PDF — the primary deliverable — is atomic).
  **Fix path:** route the sidecar through a temp + `os.replace` and add it to
  the `finally` cleanup; update the fake-engine test to write a sidecar.
  **Do-not:** claim sidecar atomicity in docs until this lands.
- **PDF4-L2 — `_installed_languages` ignores `tesseract --list-langs` non-zero
  exit.** `subprocess.run(..., check=False)`; a tesseract that errors for a
  reason other than "not found" yields an empty language set, so the requested
  langs are reported as `LanguagePackMissing` rather than the true tesseract
  error. **Severity:** LOW (still fails loud with a remediation hint; never
  silent). **Fix path:** surface a non-zero rc + stderr as a distinct
  diagnostic. **Do-not:** change this without checking the
  `test_installed_languages_*` expectations.

**Workaround:** none required — both are LOW and the chain is production-ready
(modulo the documented sandbox composition-verification caveat on the `pdf-4`
backlog row). Promoting either to a follow-up is at user discretion.

---

## DOCX-MERMAID-EXECSYNC (pre-existing; surfaced by TASK 019 vdd-multi)

**Status:** DEFERRED (LOW; pre-existing, out of TASK 019 scope).
**Severity:** LOW (not exploitable under the single-tenant local-CLI trust model).
**Location:** [`skills/docx/scripts/md2docx.js`](../skills/docx/scripts/md2docx.js) Mermaid
branch (`execSync(\`npx -y @mermaid-js/mermaid-cli -i ${mmdFile} -o ${pngFile} ...\`)`).
**Symptom:** Mermaid temp files use predictable sequential names (`temp_1.mmd`,
`temp_1.png`, …) created in the **current working directory**, and the render command is
built as a shell string passed to `execSync`.
**Why LOW / not fixed in TASK 019:** the interpolated values (`mmdFile`/`pngFile`) are
derived from an integer counter — **no user input flows into the shell line**, so there is
no command-injection vector. The predictable-name-in-CWD angle is a symlink-pre-plant
concern only in a shared/multi-tenant CWD, which the office-skills trust model excludes.
The TASK 019 spec (§6) explicitly says **"do not touch the Mermaid rendering logic"**, so
hardening it was out of scope. Flagged by the TASK 019 `/vdd-multi` adversarial pass.
**Fix path (when prioritised):** (1) render into a `mkstemp`/`fs.mkdtemp` scratch dir
instead of CWD; (2) switch the `execSync` string to the argv-array form
(`execFileSync('npx', [...])`) to remove the shell entirely. Both are mechanical and
behaviour-preserving.
**Do-not:** claim Mermaid temp-file hardening until this lands.

---

## XLSX-PREVIEW-PNG-ASSERT (pre-existing; surfaced by TASK 019 vdd-multi verification)

**Status:** DEFERRED (LOW; pre-existing, **not** a TASK 019 regression — proven below).
**Severity:** LOW (test-only; the rendering itself works, the assertion is wrong).
**Location:** [`skills/xlsx/scripts/tests/test_xlsx_add_comment.py`](../skills/xlsx/scripts/tests/test_xlsx_add_comment.py)
`TestRenderSmoke.test_single_cell_renders_via_libreoffice` (+ `_render_to_png` helper).
**Symptom:** the test renders an `.xlsx` via `preview.py` to a `*.preview.png` path and
asserts a PNG magic header (`\x89PNG\r\n\x1a\n`), but `preview.py` **always emits JPEG**
(`canvas.save(output, "JPEG", …)` — JPEG is its documented output format, regardless of
the output path's extension). So `f.read(8)` sees `\xff\xd8\xff\xe0` and the assertion
fails. Only fires where LibreOffice is installed (otherwise the render path is unavailable).
**Proven pre-existing (not TASK 019):** `git diff HEAD -- skills/xlsx/scripts/preview.py`
shows TASK 019 added **only** the 3-line self-bootstrap prelude; the `save(…, "JPEG", …)`
line is unchanged from HEAD (`git show HEAD:…/preview.py` → same JPEG save). The test
asserts PNG identically before and after TASK 019.
**Fix path (xlsx-skill, separate from TASK 019):** either (a) assert JPEG magic
(`\xff\xd8\xff`) — `preview.py`'s contract is JPEG; or (b) render to a `.jpg` path and
rename the helper. One-line test change; no `preview.py` change (its JPEG output is by
design, and it is a 4-skill replicated file).
**Do-not:** attribute this failure to TASK 019 — the bootstrap prelude does not touch
`preview.py`'s image-format logic.

---

## HTML2MD (TASK 022) — honest-scope limitations

All deferred-by-design; the backlog row `docs/office-skills-backlog.md` §2 «html2md»
owns the decisions. Cross-skill replication (G-1/G-3) and security guards are tested,
not listed here.

### HTML2MD-1 — Cloudflare/captcha-hard sites now auto-recover via the remote tier (TASK 023)
**Status:** handled (residual: needs a reachable reader) • **Severity:** LOW • **Location:**
`acquire._acquire_url` ladder + `_fetch_remote_html`.
**Was:** Cloudflare/captcha sites (papers.ssrn, researchgate) 403'd the lite path and required
the user to know to retry with `--engine jina`/`chrome`.
**Now:** `--engine auto` (default) **auto-escalates** a hard-blocked public page to the remote
reader tier (jina default, vendor-agnostic) after lite (+chrome if installed) fail — recovering
ssrn/researchgate without manual intervention. If the reader is also down, the ladder falls
back and finally fails with one `FetchFailed (kind=all_engines_failed, details.tried=[…])`.
**Residual:** still needs a reachable reader OR `install.sh --with-chrome`; `--no-remote`
opts out of any external escalation (then a hard block is a clean exit 10). **Do-not:** treat
`all_engines_failed` as a bug — every tier was tried; see the `tried` trace. Privacy posture: HTML2MD-6.

### HTML2MD-6 — the remote-reader tier sends the target URL to an external service (TASK 023)
**Status:** open (by design) • **Severity:** LOW • **Location:** `acquire._fetch_remote_html`.
**Symptom:** the remote tier fetches via `r.jina.ai` (or a configured reader), which retrieves
the page **server-side** — the target URL leaves the machine. As of TASK 023 the remote tier is
**reachable from `--engine auto`** as an automatic last-resort escalation for **public** targets
(not just explicit `--engine jina|remote`), so a public URL may leave the machine on escalation.
**Mitigations:** a private/internal/loopback/metadata target is **never** forwarded (a public-IP
gate runs before any remote request); **`--no-remote`** disables the remote tier entirely (fully
local, no external egress); CR/LF/control chars in the target are refused; the local hop is to a
public reader (passes the SSRF gate); the tier is **vendor-agnostic** (`HTML2MD_READER_URL` /
`HTML2MD_READER_PROVIDERS` → self-hosted Jina or another reader). **Do-not:** rely on `auto`
for sensitive/internal conversions without `--no-remote`. Keyless by default (rate-limited);
`JINA_API_KEY` / `HTML2MD_READER_TOKEN` raise/authorize quota. **Residual:** a reader follows its
own server-side redirects beyond our control.

### HTML2MD-2 — PDFs / binary URLs are not converted
**Status:** open (by design) • **Severity:** LOW • **Location:** `acquire._fetch_lite_html`.
**Symptom:** a `*.pdf` (or binary) URL → `FetchFailed kind=pdf/binary` with a pointer to the
pdf skill. html2md is HTML→Markdown only. **Fix path:** use `skills/pdf/scripts/pdf_extract.py`.
**Do-not:** feed PDF bytes to turndown (it overflowed the Node stack before the guard).

### HTML2MD-3 — data-grid SPAs degrade
**Status:** open (honest-scope) • **Severity:** LOW.
**Symptom:** market-data dashboards / virtualized registries (e.g. a TradingView ideas
listing) have no table semantics (no `<table>`/`role=table`) — ticker widgets flatten to
loose lines. **Workaround:** none for Markdown; this is the wrong *kind* of page. Mirrors
the pdf-10 "data-heavy SPA" note.

### HTML2MD-4 — SSRF residuals (lite path hardened)
**Status:** open (honest-scope) • **Severity:** LOW • **Location:** `acquire._host_is_public`
+ `_fetch_chrome_html`. The lite path blocks private/loopback/link-local/metadata on every
redirect hop and streams with `--max-bytes`. **NOT covered:** (a) DNS-rebinding (resolve-
then-connect TOCTOU); (b) the opt-in Chrome engine does NO network hardening. **Workaround:**
run untrusted conversions in an egress-restricted sandbox.

### HTML2MD-5 — cosmetic conversion quirks
**Status:** open (low-priority) • **Severity:** LOW.
(a) **Slug collision** — distinct inputs with the same filename/URL stem write
`<slug>-2.md`, `<slug>-3.md` (idempotent via a hidden source-id marker), so the output name
is not always the bare stem. (b) **Empty-heading merge** (`md_clean`) re-levels the line
after an empty heading into that heading — for the targeted GitBook/Mintlify pattern this is
correct, but a body paragraph directly after an empty heading would be mis-leveled (never
deleted). **Related:** `docs/office-skills-backlog.md` §2 «html2md».

### HTML2MD-7 — clean-source host variants (Wikipedia REST, arXiv /html)
**Status:** handled • **Severity:** LOW (residual) • **Location:** `acquire._mediawiki_rest_variant`
/ `_arxiv_html_variant` / `_acquire_url`.
**Was (feedback R-7/R-9):** canonical `…/wiki/<Title>` is chrome-heavy and `preprocess` stripped
its body to nothing (silent empty); arXiv `/abs/` gave only the abstract and `/pdf/` a binary PDF.
**Now:** `auto`/`lite` proactively fetch Wikipedia's Parsoid REST `page/html` endpoint
(engine `lite+restapi`) and arXiv's `/html/<id>` full text (engine `lite+arxiv-html`); relative
links/images resolve against the endpoint's `<base href>`. Provenance (`source:`) stays the
canonical URL. **Residuals:** (a) PDF-only arXiv papers 404 on `/html/` → typed
`FetchFailed kind=arxiv_no_html` with a "use the pdf skill" hint (correct, not a bug);
(b) the **reader variant** on Wikipedia REST HTML is thin (Parsoid is landmark-free → the
`spa-largest-contentful-subtree` reader heuristic under-extracts) — the **whole-page `.md` is
the faithful, substantial output**, so prefer it for Wikipedia. **Do-not:** treat `arxiv_no_html`
as a failure to retry — fetch the PDF instead.

### HTML2MD-8 — empty-extraction guard (no more silent empties)
**Status:** handled • **Severity:** (was HIGH for Wikipedia) • **Location:** `cli._extraction_is_empty`.
**Was (feedback R-7a):** a substantial source that converted to an empty body still exited 0 with a
frontmatter-only note — the worst failure class (looks like success, silently loses content).
**Now:** if the whole-page Markdown body is < ~16 chars while the source HTML was ≥ ~2 KB, the run
raises typed **`EmptyExtraction` (exit 11)** so callers can retry with another engine/endpoint.
**Do-not:** widen the thresholds without re-running the battery — a genuinely image-only or
one-line page must NOT trip the guard.

### HTML2MD-9 — ladder latency has no aggregate deadline; `--max-bytes` is unbounded by default (TASK 023 /vdd-multi)
**Status:** open (honest-scope) • **Severity:** LOW (was perf-HIGH in review) • **Location:**
`acquire._acquire_url` ladder + `_http_get_bytes` + `run_search`.
**Symptom:** the fallback ladder runs tiers sequentially and each tier has its OWN retry budget
(`--retries`, default 2) × per-request timeout (~20s). There is no *aggregate* wall-clock cap, so a
target that times out on every tier can take minutes (worst case ≈ Σ tiers; `--search` multiplies it
by `--max-results`). Separately, **`--max-bytes` defaults to unbounded**, so a remote reader / search
response is fully buffered + decoded (peak ≈ 3× body) unless the user sets a cap.
**Workaround:** for untrusted / bulk / flaky targets pass `--retries 0` (or low), `--rate-limit`, and
an explicit `--max-bytes` (e.g. `--max-bytes 52428800`); Ctrl-C is always available. **Fix path
(follow-up, beyond TASK 023 RTM):** add an aggregate `--deadline SECONDS` checked per-tier + a sane
default `--max-bytes`. **Do-not:** treat a slow multi-tier fall-through as a hang — it is bounded,
just uncapped; the `details.tried` trace shows what was attempted.
**Note (handled in this task):** the related SSRF concern — a `--search` result URL escalating to the
un-network-hardened Chrome tier — IS fixed: search-result fetches drop the chrome tier unless the
user explicitly chose `--engine chrome` (`acquire._url_tiers(allow_chrome=…)`). The remaining Chrome
honest-scope (no per-request SSRF gate, follows internal redirects) is unchanged for an *explicit*
`--engine chrome` on a user-supplied URL — see HTML2MD-4.

---

## How to add a new entry

1. Append below the relevant category (or create a new top-level
   `##` if necessary — `## Security`, `## Logic`, `## UX`, etc.).
2. Use the schema: ID • Status • Severity • Location • Symptom •
   Reproduction • Workaround • Fix path • Related • Do-not.
3. Cross-link to the backlog row that owns the deferral decision.
4. If a fix lands, **delete the entry** in the same commit that
   ships the fix; reference the KNOWN_ISSUES entry text in the
   commit body for posterity.
