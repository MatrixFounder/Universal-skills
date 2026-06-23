# Task 023-06 [LOGIC]: web search — vendor-agnostic --search → Markdown notes

> **Predecessor:** 023-02 (provider pattern), 023-03 (FETCH ladder), 023-04 (injection guard), 023-05 (trust-markdown emit path, reused for combined-shape results).
> **RTM:** [R9] web search (vendor-agnostic).
> **ARCH:** §15.3a (search provider), §15.5 (multi-result IR + CLI), §15.8 D-23 (R9).

## Use Case Connection
- UC-6 (web search → Markdown notes).

## Task Goal
Add the `--search "QUERY"` entrypoint: a vendor-agnostic search-provider layer
(`s.jina.ai` default + configurable), with per-result routing through the existing FETCH
ladder so each result inherits the fallback discipline, emitting one note per result.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py`
**`_search_providers(opts) -> list[_SearchProvider]`:**
- Order: `HTML2MD_SEARCH_PROVIDERS` else `HTML2MD_SEARCH_URL` (shape `links`) then
  built-in `s.jina.ai` (shape `combined`). Token via `HTML2MD_READER_TOKEN`/`JINA_API_KEY`.
**`run_search(query, opts) -> list[AcquireResult]`:**
- Try providers in order (fall through on provider-down, like 023-03):
  - **combined** (`s.jina.ai`): `GET <base><url-encoded query>` (X-Return-Format markdown)
    → merged Markdown → split into ≤ `--max-results` `AcquireResult(content_kind="markdown",
    markdown=…, source_meta.url=<result url if parseable>)`.
  - **links**: provider returns top result URLs/JSON → take ≤ `--max-results` → fetch EACH
    via `_acquire_url(result_url, opts)` (the full FETCH ladder → per-result Jina/local
    fallback). A result that fails its own ladder is **skipped** (appended to a run-level
    `skipped` list), not fatal.
- All search providers exhausted → raise `FetchFailed(kind="all_engines_failed",
  details={"tried":…,"query":query})`.
- **Empty (healthy) result set** → return `[]`; `cli.convert` exits **0 with a stderr note**
  (zero-results is not content-loss → NOT `EmptyExtraction`/11).
- Query is URL-encoded + CRLF-rejected (023-04 guard) before any send.
- **Rate limiter (fix):** `run_search` MUST configure/reset `_RATE_LIMITER` at its top
  (mirroring `acquire.acquire()` lines ~759-764) — otherwise the search + per-result ladder
  fetches bypass `--rate-limit` (they never go through `acquire()`). Set it once for the
  whole search run (covers all result fetches + their image bursts).

### File: `skills/html2md/scripts/html2md/cli.py`
**Refactor `convert(args)` → extract `_convert_one(acq, args, output_dir, *, stdout_mode,
input_ref, query=None) -> int`:** the existing single-input body (clean → core_bridge →
tidy → empty-guard → emit, AND the 023-05 `content_kind=="markdown"` bypass) becomes this
helper, so BOTH the single path and the search loop share one code path. (A *links*-shape
result is `content_kind=="html"` → full clean→turndown; a *combined* result is
`content_kind=="markdown"` → 023-05 bypass.)
**`convert(args)` (search branch, stubbed in 023-01):**
- `results = acquire_mod.run_search(args.search, args)`; if empty → typed `FetchFailed`
  (not exit 0); else loop `_convert_one(r, args, output_dir, query=args.search, …)` per
  result into the one `OUTPUT_DIR` (shared `_attachments/`); each note's frontmatter
  carries `query: "<args.search>"` + `source: <result url>`. `--stdout` concatenates
  results (with a `---`/heading separator). A `_convert_one` that raises on one result is
  caught → that result skipped (logged), others proceed.

### File: `skills/html2md/scripts/html2md/emit.py`
- Extend `_frontmatter(...)` (currently a hardcoded `source/title/date/author/tags` set) to
  accept an optional `query` → emit a `query:` field when present (YAML-escaped like the
  other string fields). `_convert_one` passes `query` through to `emit`.

## Test Cases
### Unit (offline — providers + ladder stubbed)
1. **TC-06-01 `test_search_provider_order`** — default `[s.jina.ai]`; `HTML2MD_SEARCH_URL`
   prepends a links provider.
2. **TC-06-02 `test_search_links_routes_each_through_ladder`** — links provider returns 3
   URLs → `_acquire_url` called per URL → 3 results.
3. **TC-06-03 `test_search_per_result_skip_on_fail`** — 1 of 3 result URLs fails its
   ladder → 2 notes emitted, the failure recorded, run still exit 0.
4. **TC-06-04 `test_search_provider_fallback`** — primary search provider 503 → secondary
   healthy → results from secondary.
5. **TC-06-05 `test_search_all_fail_one_error`** — all search providers fail → one
   `FetchFailed(kind="all_engines_failed")` with `details.query`.
6. **TC-06-06 `test_search_max_results_bound`** — provider returns 10, `--max-results 3` → 3.
7. **TC-06-07 `test_search_input_exclusion`** — `--search` + positional INPUT → exit 2 (from 023-01).
8. **TC-06-08 `test_search_empty_results_exit0`** — healthy provider returns 0 results →
   exit 0, stderr note, no notes written (NOT exit 11).
9. **TC-06-09 `test_search_respects_rate_limit`** — `--rate-limit` set + a multi-result
   links search → `_RATE_LIMITER` is configured on the search path (the limiter spy fires).
### E2E (mocked)
10. **TC-E2E-06** `--search "q" OUTPUT_DIR --max-results 2` → 2 `<slug>.md` notes, each with
    `query:` + `source:` frontmatter, shared `_attachments/`.
### Regression
- Full suite; non-search paths unaffected.

## Acceptance Criteria
- [ ] **[R9]** `--search` emits ≤ `--max-results` notes (one per result), `query:`+`source:` frontmatter.
- [ ] **[R9]** links-shape routes each result through the FETCH ladder (per-result fallback).
- [ ] **[R9]** per-result failure skipped (not fatal); search-provider fallback; all-fail → one typed error.
- [ ] **[R9]** query URL-encoded + CRLF-rejected; vendor-agnostic via env.
- [ ] No gated master touched.

## Notes
- Adversarial roast focus: a combined provider returning one giant blob that can't be split
  per result (fall back to a single note + note the limitation); query injection into the
  search base; unbounded results ignoring `--max-results`; partial-failure leaving an empty
  OUTPUT_DIR (should still write the successful ones).
