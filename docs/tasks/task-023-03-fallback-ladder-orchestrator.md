# Task 023-03 [LOGIC]: fallback-ladder orchestrator (the core resilience)

> **Predecessor:** 023-02 (provider layer).
> **RTM:** [R1] resilient ladder, [R3] failure classification, [R6] observability.
> **ARCH:** §15.2 (state machine), §15.4 (classification), §15.5 (engine enum + tried), §15.8 D-23-A/C.
> **Methodology:** `tdd-strict` (security-critical — write the all-tiers-fail + classification tests FIRST).

## Use Case Connection
- UC-1 (anti-bot page auto-recovers), UC-2 (`--engine jina` survives a Jina outage).

## Task Goal
Rewrite `_acquire_url` as a **tier ladder** with bidirectional fallback so a single
provider/engine failure never kills the run, and classify failures so a genuinely-blocked
target is reported honestly. Surface the real `engine` + a `tried` trace.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py`

**New `_fetch_remote_html(target, opts) -> tuple[str, str]`:**
- Iterate `_remote_providers(opts)`; for each, `_build_reader_request` → `_http_get_bytes`.
- Classify (reuse `_fetch_kind`): transient/5xx/429/402/408/503/DNS/timeout → raise
  `_TierUnavailable(kind, status)` to fall through to the next provider; **empty/too-short
  body** → `_TierUnavailable("empty")`; a reader-mapped **target** 403/401/404 → raise
  `FetchFailed` (terminal target kind) — do NOT try more remote providers.
- On success return `(decoded_html, f"remote:{provider.host}"|"jina")`.
- If all providers raise `_TierUnavailable` → raise `_TierUnavailable("remote_exhausted")`.

**Rewrite `_acquire_url(input_ref, opts)` as a tier loop:**
- Build the tier order from `engine`:
  - `auto` → `[lite, chrome, remote]` (remote last; skipped per 023-04 if target not public / `--no-remote`).
  - `jina` / `remote` → `[remote, lite, chrome]` (remote-first; `jina` pins the jina provider first).
  - `lite` → `[lite]`; `chrome` → `[chrome]` (explicit single tier).
- Keep the existing **lite** internals INTACT: proactive site-variant rewrites
  (`_arxiv_html_variant`/`_mediawiki_rest_variant`/`_nojs_variant`) and the
  `auto` `_looks_substantial` JS-shell check (a thin lite body in `auto` becomes a
  tier-failure → next tier).
- Per tier wrap the call; on `_TierUnavailable` (or, in auto/remote-first, `EngineNotInstalled`
  from chrome, or a **local 403** `FetchFailed kind=bot_blocked`) → append to `tried` and
  continue; on success → build `AcquireResult(engine=<label>, …)`.
- Exhausted → `raise FetchFailed("all engines failed for …", details={"url":_redact,
  "kind":"all_engines_failed", "tried":tried})`. If a terminal **target** error was the
  last cause, surface that kind but still include `tried`.
- `tried` entries: `{"engine":…, "kind":…, "status":…?}`.

**Provenance:** `AcquireResult.engine` = the winning tier label; `source_meta.url` /
frontmatter `source:` stays the **canonical target URL** (never the reader URL).

## Test Cases
### Unit (offline — `_http_get_bytes` / provider seam stubbed per URL)
1. **TC-03-01 `test_auto_lite_success`** — lite substantial → `engine=="lite"`, remote never called.
2. **TC-03-02 `test_auto_403_escalates_to_remote`** — lite 403 (post browser-UA) → remote healthy → `engine` startswith `jina`/`remote`.
3. **TC-03-03 `test_jina_outage_falls_back_to_lite`** — `--engine jina`, reader 503 → lite healthy → exit 0, `engine!="jina"`.
4. **TC-03-04 `test_all_tiers_fail_one_typed_error`** — every tier stubbed to fail → exactly one `FetchFailed(kind="all_engines_failed")` whose `details.tried` lists each tier+kind.
5. **TC-03-05 `test_target_404_terminal_per_provider`** — reader maps target 404 → not retried across providers; `kind=="not_found"`.
6. **TC-03-06 `test_auto_engine_not_installed_falls_through`** — auto, lite=JS-shell, chrome absent (`EngineNotInstalled`) → remote healthy → success (NOT exit 3).
7. **TC-03-07 `test_explicit_chrome_absent_exit3`** — `--engine chrome`, Playwright absent → exit 3 (terminal, unchanged).
8. **TC-03-08 `test_site_variant_preserved`** — arXiv `/abs/` still rewritten to `/html/` in lite (engine `lite+arxiv-html`).
### Regression
- Full `html2md/tests`; the offline I-3 zero-network test still passes (no tier touches the net for file/archive).

## Acceptance Criteria
- [ ] **[R1]** auto=local-first, jina/remote=remote-first, both fall back; one typed error only when exhausted.
- [ ] **[R3]** provider-down/transient → fall-through; local 403 → escalate; reader target-404 → terminal-per-provider; auto `EngineNotInstalled` → fall-through; explicit chrome-absent → exit 3.
- [ ] **[R6]** `engine` = real tier; `FetchFailed.details.tried` populated; `source:` = canonical URL.
- [ ] Existing site-variant rewrites + `_looks_substantial` preserved.
- [ ] No gated master touched.

## Notes
- `tdd-strict`: write TC-03-04 (all-fail) + TC-03-05 (target-terminal) FIRST — they encode
  the two failure-laundering bugs the design must avoid.
- **`tried` entries carry NO URL** — only `{engine, kind, status?}` — so the trace cannot
  leak a configured internal reader base or token (the `_redact`'d `url` stays the sole
  URL-in-envelope field). Add an assertion to TC-03-04 that no entry contains a URL.
- **Split authorization:** this is the heaviest bead. If it balloons during build, split
  classification (`_TierUnavailable` mapping / `_fetch_remote_html`) from the tier-loop
  orchestration into 023-03a/03b — same RTM (R1/R3/R6), same tests.
- Adversarial roast focus: infinite-retry / re-escalation loops; masking a real 404 as
  provider-down (and vice-versa); a tier raising an unexpected exception type escaping the
  ladder (must be caught → tried/terminal, never a traceback).
