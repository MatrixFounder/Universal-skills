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

All deferred-by-design; the backlog row `docs/office-skills-backlog.md` §2 «html»
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
public reader (passes the SSRF gate); the tier is **vendor-agnostic** (`HTML_READER_URL` /
`HTML_READER_PROVIDERS` → self-hosted Jina or another reader). **Do-not:** rely on `auto`
for sensitive/internal conversions without `--no-remote`. Keyless by default (rate-limited);
`JINA_API_KEY` / `HTML_READER_TOKEN` raise/authorize quota. **Residual:** a reader follows its
own server-side redirects beyond our control.

### HTML2MD-2 — PDFs / binary URLs are not converted
**Status:** open (by design) • **Severity:** LOW • **Location:** `acquire._fetch_lite_html`.
**Symptom:** a `*.pdf` (or binary) URL → `FetchFailed kind=pdf/binary` with a pointer to the
pdf skill. html is HTML→Markdown only. **Fix path:** use `skills/pdf/scripts/pdf_extract.py`.
**Do-not:** feed PDF bytes to turndown (it overflowed the Node stack before the guard).

### HTML2MD-3 — data-grid SPAs degrade
**Status:** open (honest-scope) • **Severity:** LOW.
**Symptom:** market-data dashboards / virtualized registries (e.g. a TradingView ideas
listing) have no table semantics (no `<table>`/`role=table`) — ticker widgets flatten to
loose lines. **Workaround:** none for Markdown; this is the wrong *kind* of page. Mirrors
the pdf-10 "data-heavy SPA" note.

### HTML2MD-4 — SSRF residuals (lite path hardened)
**Status:** open (honest-scope) • **Severity:** LOW • **Location:** `acquire._is_ssrf_blocked`
/ `_host_is_public` + `_fetch_chrome_html`. The lite path blocks private/loopback/link-local/
metadata/reserved on every redirect hop and streams with `--max-bytes`. The gate keeps Python's
maintained `ip.is_private` (a superset of the old behaviour) and only **subtracts an explicit
carve-out** (`HTML_SSRF_ALLOW_NETS`) — there is **no built-in code default**, so an absent var
widens nothing: unset **or** `""` → NO carve-out (strict, fail-safe); a CIDR list → exactly
those ranges. The shipped `<skill>/.env.example` sets `HTML_SSRF_ALLOW_NETS=198.18.0.0/15` (RFC
2544 benchmarking — some local resolvers, e.g. ENS/`.eth.limo` gateways, map real public
hostnames into that range), so the auto-loaded `.env` re-allows it; a host without that value
refuses it. IPv4-mapped (`::ffff:x`) and IPv4-translated (`::ffff:0:x`) IPv6 are unwrapped to
IPv4 before the family-matched check, so `::ffff:169.254.169.254` is still blocked.

**Caveats / NOT covered:**
- **(a) DNS-rebinding (resolve-then-connect TOCTOU) — ✅ CLOSED on the lite path.** Implemented
  fix (1) **IP-pinning**: `_resolve_validated_addrs` resolves + validates the host ONCE, then
  `_pin_host_addrs` forces `socket.getaddrinfo` to return exactly those validated IP(s) for the
  duration of the connect, so httpx connects to the IP that was security-checked (TLS SNI / `Host`
  / cert verification still use the hostname). An attacker who flips the authoritative answer to a
  private IP after validation can no longer be reached — the pinned address holds. *Residual:* the
  pin is process-global (correct for the single-threaded CLI fetch); and the **Chrome engine does
  NOT pin** (Playwright manages its own sockets — its context route-guard re-validates each
  request's host but is itself resolve-then-connect), so chrome retains the TOCTOU. Mitigation for
  chrome: egress-restricted sandbox.
- **(b)** a carve-out you configure is reachable from the host by design — `0.0.0.0/0` disables
  IPv4 protection entirely; trusted-local-config only.
- **(c)** the opt-in Chrome engine is now SSRF-gated (see HTML2MD-10).

**Strictest local posture:** `--no-remote` + leave `HTML_SSRF_ALLOW_NETS` unset/empty.

### HTML2MD-5 — cosmetic conversion quirks
**Status:** open (low-priority) • **Severity:** LOW.
(a) **Slug collision** — distinct inputs with the same filename/URL stem write
`<slug>-2.md`, `<slug>-3.md` (idempotent via a hidden source-id marker), so the output name
is not always the bare stem. (b) **Empty-heading merge** (`md_clean`) re-levels the line
after an empty heading into that heading — for the targeted GitBook/Mintlify pattern this is
correct, but a body paragraph directly after an empty heading would be mis-leveled (never
deleted). (c) **Math-signal heuristic** (`md_clean._normalize_math`) — bracket forms `\[…\]`
convert to `$$…$$` only when the body looks mathy (LaTeX command / sub-superscript / operator
between operands), so turndown-escaped plain `[word]`/`[1]` are NOT mangled into math; the
trade-off is a bare single-variable display like `\[x\]` from the remote-reader path is left
as-is. Real `class="math"` spans (the lite path) are unaffected — they convert via the DOM rule.
(d) **Inline `data:` images** — content-sized blobs are localized to `_attachments/` (decoded
to files); the icon-vs-content cut is a **dual floor**: ≥1024-char encoded URI *and* ≥512
decoded bytes, so a percent-encoded icon that clears the encoded floor but is tiny decoded is
still dropped (the decoded floor is the load-bearing one). An SVG `data:` image is written
verbatim — Obsidian/weasyprint render it without executing embedded JS, so a `<script>` in it is
inert, but it is not sanitized. In `--no-download-images` file mode a `data:` image stays inline
(self-contained note); `--stdout` strips it (no localization there → would be base64 bloat).
**Related:** `docs/office-skills-backlog.md` §2 «html».

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
`--engine chrome` on a user-supplied URL — see HTML2MD-4. **(SUPERSEDED by TASK 024 / HTML2MD-10:
the Chrome tier is now SSRF-gated always.)**

### HTML2MD-10 — authenticated Chrome (login-gated) honest-scope (TASK 024)
**Status:** handled (with documented residuals) • **Severity:** LOW • **Location:**
`acquire._fetch_chrome_html` / `_chrome_auth` / `_cookies` / `acquire._login_render`.
**What shipped:** read login-gated pages (X Articles/threads, paywalled, private) by replaying a
**human-minted** session — `html login URL --save-state s.json` (headful) then
`--chrome-storage-state s.json` (also `--chrome-cookies-file` / `--chrome-user-data-dir`);
`--chrome-scroll` for lazy replies. The Chrome tier is now **SSRF-gated** (supersedes the old
HTML2MD-4 "chrome not hardened"): `_assert_public_http` before navigation, context-level route
guard aborts non-public sub-resources/`fetch`/`beacon`, and an **off-target public-redirect** is
refused (final origin must equal the target's eTLD+1). Auth is **opt-in / additive** — with none
configured, behaviour is byte-for-byte TASK 023 (no crash). `storage_state` is **server-deployable**
(read-only → concurrency-safe; e.g. an *example* Hermes deploy). **Residuals (do-not treat as bugs):**
(a) **DNS-rebinding TOCTOU** inherited (resolve-then-connect) — run untrusted input in an
egress-restricted sandbox; (b) `storage_state` **localStorage is origin-restored** (readable by a
same-origin script the page loads); (c) the **login-wall heuristic** (stale session → `auth_required`)
is best-effort/per-site (X-tuned first); (d) **`_registrable` = last-2-labels** (no public-suffix
list → multi-level suffixes like `co.uk` over-match the off-target check); (e) **no 2FA/auto-refresh**
— re-mint when the session expires; (f) **Google "Continue with Google" SSO cannot be completed in
the mint window** — Google's OAuth bot-detection refuses automation-controlled browsers (*"this
browser or app may not be secure"*). **TASK 025 mitigation:** mint/render now prefer the **real
system Chrome channel** (`channel="chrome"`, bundled-Chromium fallback) + suppress the automation
signal (`--disable-blink-features=AutomationControlled` + `navigator.webdriver` mask), which makes
**native** logins (X email/password) and authed renders reliable — but Google OAuth specifically may
**still** block (intentional, not a bug). For Google-SSO accounts use **email/password** in the mint
window, or **export cookies** from your everyday browser → `--chrome-cookies-file` (sanctioned path;
manual §5b). **Do-not:** put secrets on argv (file/env only); cookies/state
files must be `0600` (group+world rejected) or they're refused; **do-not** add fingerprint-spoofing
beyond the standard de-automation flag to chase Google's check (arms race — cookie export wins).

### HTML2MD-11 — rewritten-fetch relative `<img>` srcs resolved against the wrong base → broken images — RESOLVED (TASK 027, 2026-07-09)
**Status:** ✅ RESOLVED (TASK 027; delete this entry when the fix commits). **Was:** SEV-2 silent
figure loss — fetching arXiv `/abs/<id>` (rewritten to `/html/<id>`) absolutized the page's
relative `<img>` against `input_ref` (`/abs/`), so `x1.png` → `/abs/…x1.png` → a 404 HTML body
that was then saved verbatim as `_attachments/<hash>.png`; all figures collapsed to one
HTML-as-png and the run looked successful. **Fix (universal, no per-site logic):** absolutize
`<img>`/`<a>` against the URL the page was actually **fetched** from — the post-redirect final
URL, propagated out of every tier via a `final_url_out` out-param (`_http_get_bytes`,
`_fetch_chrome_html`) and returned as the third element of each tier's `(html, label, base)`
tuple; `_acquire_url` uses it at the absolutization seam while `AcquireResult.base_url` stays the
canonical `input_ref` for provenance. NB the bug-doc's proposed arXiv trailing-slash/version hack
was **not** applied — it was wrong (the real served HTML at `/html/<id>` is a 200 with figure
srcs `<id>vN/xK.png` already relative to `/html/`, so a trailing slash would double the path).
Defense-in-depth: `_resolve_url_image` now magic-byte-validates the download (`_looks_like_image`:
PNG/JPEG/GIF/BMP/TIFF/ICO/WEBP/AVIF/HEIC/JXL/SVG) and **drops** a non-image body with a
control-char-sanitised stderr warning instead of writing it as `.png` (no more silent
`images: 1`). `_arxiv_html_variant` (the separate full-text acquisition feature) is unchanged.
**Verification:** 10 new regression tests (`test_url.py::TestArxivImageResolution`) + full suite
(282) + e2e diff-gate + `validate_skill` green; live dogfood on `arxiv.org/abs/2510.08369` now
localises all 17 figures as real PNGs (was 1 HTML-as-png). Root-cause write-up:
[`docs/html-arxiv-image-resolution-bug.md`](html-arxiv-image-resolution-bug.md); RTM in
[`docs/tasks/task-027-html-arxiv-image-resolution.md`](tasks/task-027-html-arxiv-image-resolution.md).

### HTML2MD-12 — arXiv/LaTeXML MathML (`<math alttext>`) came out as garbled glyphs — RESOLVED (TASK 028, 2026-07-09)
**Status:** ✅ RESOLVED (TASK 028; delete this entry when the fix commits). **Was:** every formula
on an arXiv `/html/` (LaTeXML/ar5iv) page — 328 in the reference paper — rendered as interleaved
presentation-MathML Unicode glyphs + the markdown-escaped `<annotation>` TeX, undelimited and
unrenderable (`wt′∑i=1L…\\sum\_{i=1}^{L}…`). Root cause (found by a 5-agent cross-skill math audit):
the html skill's only math rule (`htmlMath`) matches Pandoc `<span class="math inline|display">`,
never a MathML `<math>` node, so turndown dumped the subtree's `textContent`; `_normalize_math`
then no-op'd (no `\(`/`\[`), and `summarizing-meetings` R-7 couldn't help (it presumes an intact,
delimited TeX body html had already destroyed). **Fix (one html-owned file,
`skills/html/scripts/html_convert.js`, NOT a replication unit):** a new `htmlMathml` turndown rule
(filter `nodeName==="math"`, lowercase — MathML foreign elements aren't uppercased) lifts the clean
LaTeX that already ships in `alttext` (fallback: the `<annotation encoding="application/x-tex">`
child, exact-match) and emits `$…$` / single-line `$$…$$` (display keyed on `display="block"`)
**directly** — bypassing `_normalize_math`'s `_looks_like_math` display gate and its escaping, since
turndown does not re-escape a rule's raw return. Reuses the existing normalizers (unchanged) and a
shared `_mathTex` helper; the pre-existing `htmlLatexmlListing` rule (arXiv Algorithm blocks) routes
through the same helper so math inside code listings is clean too. Two adversarial-review hardenings:
(a) `|`/`\|` in math are pre-mapped to pipe-free `\vert`/`\Vert` so the GFM table-cell escaper
(display equations live in `<table>` cells) cannot corrupt norm/abs/conditional bars into `\|`
(KaTeX line-break); (b) presentation-only MathML with no recoverable TeX (hand-authored
Wikipedia/MDN) keeps the default glyph rendering rather than vanishing silently. **Do-not:** put the
rule in `web_clean/preprocess.py` (pdf-mastered gate; pdf may want MathML retained) or
`html2md_core.js` (docx-mastered); expand R-7 (can't reach the direct `.md`, works on destroyed
input); build a presentation-MathML→LaTeX glyph parser (lift `alttext`). **Also (R6):** arXiv **Algorithm/pseudocode** blocks (`ltx_listing` carrying inline `<math>`) used to
be fenced as ``` code, where `$…$` shows as literal LaTeX; the `htmlLatexmlListing` rule now branches
on inline-`<math>` presence and renders pseudocode as text (`$…$` math + `**bold**` keywords + hard
line breaks, no fence), while math-free real-code listings stay fenced. **vdd-multi hardening
round (2026-07-09, 3 parallel critics: logic/security/performance):** (a) the pipe remap in (a)
above turned out to be over-broad — it corrupted `\begin{array}{c|c}` column specs (KaTeX's
column parser accepts only `l c r | :`; `\vert` throws) — it is now **cell-gated**
(`_texPipesForCell` runs only in table-cell context, detected via a `_cellDepth` re-entrancy flag
around every cell innerHTML re-conversion + a `<td>/<th>` ancestor walk) and **exempts**
`\begin{array|darray|tabular}{…}` preambles; outside cells pipes pass through verbatim; (b)
display math OUTSIDE a cell is now blank-line-wrapped `$$\n…\n$$` (same shape as `htmlMath`),
single-line only inside cells; (c) **`$`-breakout injection closed** (shared `_dollarSafe`,
hardened across BOTH vdd-multi review iterations): every `$` in lifted TeX is made escaped, on
BOTH the MathML rule AND the sibling Pandoc `htmlMath` rule (identical channel). The neutralizer
is **parity-aware** (`(\\*)\$` — a naive `/\\?\$/g` was a no-op on an EVEN backslash run like
`\\$`, leaving the `$` live) and guards a **trailing odd-backslash** run (which would escape the
rule's own abutting closing delimiter, leaving the span unterminated) with a TeX-insignificant
space; NEL (U+0085, not matched by JS `\s`) is folded into the whitespace collapse. So a crafted
`alttext="x$ ![](evil) $y"` — or any backslash-parity variant — can no longer terminate the
`$…$`/`$$…$$` wrapper and inject a live Markdown exfil beacon. Two further adversarial
iterations closed a boundary regression (the cell pipe-map's trailing `.trim()` stripped the
guard space → re-applied via `_boundaryGuard`) and gave `htmlMath` the same interior-whitespace
collapse as `_mathTex` (an interior blank line would otherwise split the inline span into a new
paragraph, orphaning the opening `$`). Verified by a whole-document escaped-aware oracle over
15+ attack vectors — all beacons stay inside a math span; (d) `acquire.py` `_CTRL_CHAR_STRIP`
extended to C1 controls (U+0080–9F, 8-bit CSI), `_looks_like_image` accepts JP2 + extra HEIC
brands + SVG-with-`<foreignObject>` (rejects only when `<html` precedes `<svg`). Residual
honest-scope (documented, accepted): array-with-rules inside a GFM cell is unrepresentable
(no pipe-free column-rule spelling exists); presentation-only MathML (MathJax v3 assistive MML,
hand-authored MDN) has no TeX to lift → glyph fallback (rebuilding TeX from presentation MathML
is an explicit non-goal); LaTeXML algorithm indentation is pt-width-encoded → flush-left.
**Verification:** 13 regression tests (`test_convert.py::test_mathml_*`,
`test_pseudocode_*`, `test_ltx_listing_*`) + full suite (293) + e2e diff-gate + `validate_skill`
green; live dogfood on the reference paper → **all 328 formulas strict-KaTeX-valid** (validated
with the pdf skill's bundled KaTeX; zero `\|` inside any math span), including the 2 Algorithm
blocks; a non-arXiv universal fixture (W3C alttext / MediaWiki annotation-only / display-block /
presentation-only / pipes-in-cell / Pandoc span / MathJax-v3 container / zero-width garbage)
converts 8/8 with byte-identical re-runs. RTM:
[`docs/tasks/task-028-html-mathml-to-latex.md`](tasks/task-028-html-mathml-to-latex.md).

---

## TRANSCRIPT-FETCHER-X (TASK 026) — honest-scope limitations

All deferred-by-design for the X.com + ASR feature. Architecture:
[`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](architectures/architecture-016-transcript-fetcher-x-asr.md) §7.
None is a blocker; the chain ships with 268 offline tests green +
`validate_skill` exit 0.

### TF-X-1 — youtube/vimeo not retrofitted onto the shared `_ytdlp_media.py`
**Status:** open (by design) • **Severity:** LOW • **Location:**
`sources/youtube.py`, `sources/vimeo.py`.
The shared media core (`_ytdlp_media.py`) is the **forward** extension surface
(X uses it; future TikTok/Twitch will). The two pre-existing adapters keep their
own copies of the yt-dlp helpers to avoid regressing three tested adapters in one
task. `classify_failure` in the shared module **imports** youtube's base pattern
tuples (no fork). **Fix path:** a future `transcript-fetcher-Nb` can converge
youtube/vimeo onto the shared core. **Do-not:** treat the duplication as a fork —
the base failure patterns have one source of truth.

### TF-X-2 — ffmpeg is required for the X ASR path on HLS sources (Broadcasts/Spaces)
**Status:** handled (fail-fast) • **Severity:** MEDIUM • **Location:**
`sources/x.py` (fail-fast), `_ytdlp_media.{is_hls_only,download_audio}`.
**Live-E2E finding (supersedes the original "ffmpeg-optional" design assumption):**
yt-dlp's native HLS downloader runs without ffmpeg, but the file it produces by
concatenating fragments is **not a valid playable container** — MacWhisper/
AVFoundation rejects it (`Error: cannot open (mp4)`). X Broadcasts/Spaces are
always HLS, so **ffmpeg is required** there (to extract a clean `m4a`). The
adapter probes `is_hls_only(info)` and, when ffmpeg is absent, **fails fast with
`MissingDependencyError` (exit 7)** + a "install ffmpeg" remediation, BEFORE the
~200 MB download — instead of failing cryptically at the ASR step. ffmpeg stays
optional for non-HLS progressive media and the caption path. **Do-not:** re-assert
"MacWhisper reads video so ffmpeg is optional" — true only for a *valid* container,
which the no-ffmpeg HLS output is not.
Separately, **whisper.cpp** needs ffmpeg (to make a 16 kHz WAV) **and**
`--asr-model <ggml.bin>`; without either its `available()` returns False and it is
cleanly skipped — never a mid-run crash.

### TF-X-6 — ASR filler on silence → silence-removal preprocessing (HANDLED for silence; music residual)
**Status:** handled (silence) / open (music, engine-level) • **Severity:** LOW •
**Location:** `_ytdlp_media.remove_silence` (ffmpeg `silenceremove`), wired into the
`sources/x.py` ASR path; `_config.silence_*`.
**Was:** Whisper-family models (incl. MacWhisper) emit repeated training-data filler —
e.g. `"Продолжение следует..."`, `"Thanks for watching"` — over **silent or
music-only** lead-in/out. The live broadcast opened with ~14 such lines before the
real speech; the skill recorded whatever the engine returned.
**Now (the user's "analyse the audio and remove large silences" approach):** before
ASR the X path runs ffmpeg `silenceremove` to trim leading silence and collapse every
interior/trailing gap longer than `min_gap` (default 1.0s) to `keep` (0.3s), gated at
`threshold` (-45dB) — removing the dead air where the hallucination originates. **ON by
default**; `--keep-silence` (or `TRANSCRIPT_FETCHER_SILENCE_REMOVAL=0`) opts out, and
`TRANSCRIPT_FETCHER_SILENCE_{THRESHOLD,MIN_GAP_SEC,KEEP_SEC}` tune it. Never fatal —
ffmpeg absent or a filter failure transparently falls back to the original media. The
timeline shifts, but the ASR path emits no timecodes (so the text is faithful) and the
**original** media is kept for the ffprobe duration fill.
**Residual (music, NOT silence — engine-level):** the threshold treats only *true
silence* as removable, so **music/applause carry energy above it and survive** — a
*music-only* intro can still trigger filler. For that, use a model/engine config with
VAD / `condition_on_previous_text=false`, or trim downstream. **Do-not:** lower the
threshold far enough to eat music — it would clip quiet speech (a worse failure).
**Do-not:** add a blanket text dedup that could strip legitimately-repeated speech.

### TF-X-3 — cloud ASR egresses audio (opt-in)
**Status:** open (by design) • **Severity:** LOW • **Location:**
`asr/openai_api.py`. The cloud backend is used **only** with `--asr-allow-cloud`
(or `TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD=1`) AND a key present; the audio leaves
the machine to the configured endpoint. Disclosed in SKILL.md §5 + `.env.example`.
Local backends are always tried first. **Do-not:** use `--asr-allow-cloud` for
sensitive audio without accepting the egress.

### TF-X-4 — captions: VTT + SRT + TTML/DFXP (HANDLED)
**Status:** handled • **Severity:** LOW (residual) • **Location:**
`_ytdlp_media.download_captions` + `sources/_captions.py`.
**Was:** the X caption path asked yt-dlp for `--sub-format vtt` only; a track served
only as SRT or TTML was treated as absent → ASR.
**Now:** yt-dlp is handed a format *preference list* `vtt/srt/ttml/best` and the
downloaded file is parsed **format-aware** — SRT is normalised into the VTT machinery
(comma→dot timestamps; all rolling-caption dedup + `>>`-turn handling reused), and
TTML/DFXP is parsed via stdlib `ElementTree` (`<p>` → line, `<br/>` → space). A
malformed or DTD-bearing TTML is **refused before parse** (XXE / billion-laughs guard:
a `<!DOCTYPE`/`<!ENTITY` declaration is rejected; the file is size-capped) and the run
falls through to ASR rather than crashing or silently emptying.
**Also (language-robust captions-first):** the X path used to drop to ASR when the requested
`--lang` (default `ru`) had no track even though the post carried captions in *another*
language. It now falls back to **any available caption** (`_ytdlp_media.pick_any_caption`,
manual preferred over auto) before ASR, with a note (`using the available <kind>:<lang> track`)
— so e.g. a post whose only track is `manual en` is transcribed from captions, not ASR.
Live-proven on `x.com/Av1dlive/status/2070507527213871594` (manual `en` VTT → 1345 chars,
`embedded-captions`, no ASR) under the default `--lang ru`.
**Residual:** YouTube-only `srv1/2/3` XML and other exotic sub formats are NOT parsed —
`best` may still fetch one, in which case the finder declines it → ASR (same outcome as
before). **Do-not:** pull in a heavyweight XML dep (`defusedxml`) — the
declaration-refusal guard covers the threat model cheaply.

### TF-X-5 — X auth + long-broadcast cost + duration (largely HANDLED)
**Status:** handled (one residual, one external limit) • **Severity:** LOW •
**Location:** `sources/x.py`, `sources/_auth.py`, `_ytdlp_media.{download_audio,probe_media_duration}`.

- **Large broadcast download → HANDLED.** `--max-duration-min N` clips the download to
  the first N minutes (yt-dlp `--download-sections`, needs ffmpeg — already required for
  HLS), bounding **both** bytes and ASR time. Live-proven: `--max-duration-min 1` on the
  reference broadcast ran end-to-end in ~19 s vs ~20 min for the whole stream. Default is
  the whole media; `--timeout-sec` still time-bounds it (so a runaway can't hang).
- **Auth / login walls → HANDLED.** Cookies resolve from a skill-local
  **`~/.transcript-fetcher/`** folder (mirrors the `html` skill's `~/.html`): an
  `auth-map.json` (host → `{cookies_file}`, hardened 0600/symlink-reject, label-boundary
  host match — `x.com` never leaks to `evil-x.com`) or the convention
  `~/.transcript-fetcher/<host>-cookies.txt`; `--cookies-file` still wins. The resolved
  Netscape file feeds yt-dlp `--cookies` (source-agnostic). `--cookies-from-browser BROWSER`
  loads cookies straight from a local browser (yt-dlp native, X path). Session **minting**
  stays out of scope (that is the `html` skill's Playwright job) → a protected post with no
  cookies is still a clean `SourceAuthError` (exit 5).
- **`duration_sec=None` on Broadcasts → HANDLED.** When the media is downloaded for ASR and
  ffmpeg is present, the duration is derived via **ffprobe** (ships with ffmpeg — no new dep)
  and a `duration: derived via ffprobe` note is added. Live-proven (`duration_sec: 59` on a
  1-min clip).
- **Residual (external limit, NOT fixable here):** MacWhisper's `mw transcribe` has **no
  language flag** (verified) — it auto-detects; the `--lang` hint is forwarded only to
  `whisper`/`whisper.cpp`/cloud. **Do-not:** claim `--lang` reaches MacWhisper.

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
