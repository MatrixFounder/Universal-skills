# TASK 023 — `html2md`: resilient vendor-agnostic remote-reader tier & Jina fallback ladder

**Status:** 🟡 ANALYSIS (VDD start-feature) — TASK + ARCHITECTURE drafted, pending
review-loop gates. NOT yet planned/implemented.
**Skill:** `html2md` (existing, **Proprietary, All Rights Reserved**). This task
adds only html2md-**owned** code (`acquire.py`, `cli.py`, tests, docs) — it touches
**no** `diff -q`-gated master, so the two-master replication gate (G-1/G-2/G-3)
stays green by construction.
**Predecessor:** TASK 022 (`html2md` base build) — SHIPPED & archived
(`docs/tasks/task-022-html2md-web-to-markdown.md`).
**Mode:** VDD (Verification-Driven Development).
**Driver:** user enhancement request + spec `docs/html2md_enh.md` (Jina Reader as a
universal URL→Markdown layer), with the **non-negotiable** requirement: *"if Jina
ever stops working, there must be a fallback"*, plus *"use an LLM/vendor-agnostic
web search/fetch tool"* (user 2026-06-22/23).

---

## 0. Meta Information

- **Task ID:** 023
- **Slug:** `html2md-remote-reader-fallback`
- **Context:** html2md already ships `--engine jina` (opt-in, explicit-only; forces
  `X-Return-Format: html` so the page flows through the local clean→turndown
  pipeline). But Jina is a **single hard-coded external provider with no fallback**:
  if `r.jina.ai` is down / rate-limited / quota-exhausted / changes its API, the run
  just errors (`FetchFailed`, exit 10) and the conversion is lost. Jina is also never
  auto-tried, so the exact pages it solves (Cloudflare / anti-bot / JS-SPA) still fail
  on `--engine auto` unless the user happens to know to retry manually. This task makes
  the remote-reader tier **resilient** (never a single point of failure),
  **vendor-agnostic** (pluggable / self-hostable providers, not locked to jina.ai),
  **auto-integrated** behind a privacy-preserving fallback ladder, and **smarter**
  (article target-selector + opt-in trust-the-reader's-Markdown).
- **Runtime:** unchanged — Python orchestrator (`acquire.py`) + Node converter. All
  network goes through the single seam `acquire._http_get_bytes` (SSRF-safe, streaming,
  retrying), which the new provider layer reuses; no new runtime dependency (`httpx`
  is already a base dep).

---

## 1. Problem Description

The current Jina integration ([acquire.py](skills/html2md/scripts/html2md/acquire.py)
`_fetch_jina_html`) has four gaps the user's request targets:

1. **No fallback (the headline requirement).** `--engine jina` → `_fetch_jina_html`
   → `_http_get_bytes(r.jina.ai/...)`. If that hop fails (service outage, 429
   rate-limit, 402 quota, 5xx, DNS, timeout, API change), the call raises `FetchFailed`
   and the whole conversion dies. There is **no automatic degradation** to the local
   `lite`/`chrome` engines that need no external service.
2. **Single-vendor lock-in.** The reader endpoint `https://r.jina.ai/` is hard-coded.
   Resilience cannot depend on one company's uptime; the user explicitly asked for a
   **vendor-agnostic web fetch tool** so an alternative (e.g. a self-hosted Jina Reader,
   which is open-source, or any compatible `<base>/<url>` reader) can be swapped in.
3. **Jina never escalates automatically.** It is `--engine jina`-only and excluded from
   `auto` for privacy. So an `auto` run against a Cloudflare-protected page returns a
   bare `FetchFailed kind=bot_blocked` even though the remote reader would have recovered
   it (see `docs/KNOWN_ISSUES.md` HTML2MD-1: ssrn / researchgate).
4. **Richer extraction unused.** Jina supports `X-Target-Selector` (grab just the article
   block) and a native clean-Markdown return mode (`X-Return-Format: markdown`) — higher
   fidelity on hard pages than re-cleaning its HTML locally. Today the skill always forces
   `X-Return-Format: html`.
5. **No web search.** Jina also exposes `s.jina.ai/<query>` (search → fetch top results →
   Markdown), turning a converter into a research/grounding step. The skill has no search
   entrypoint at all. *(Pulled into scope by the user 2026-06-23 — see R9.)*

This task closes all five **without forking** (owned files only) and **without a new
dependency**, by introducing a small vendor-agnostic remote-reader/search provider
abstraction and a bidirectional fallback ladder around the existing engines.

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | **Resilient fallback ladder** — no single point of failure | ✅ | (a) `--engine auto` (default) stays **local-first / privacy-first**: `lite` (**preserving** the existing proactive site-variant rewrites — arXiv/Wikipedia/HackerNoon — and the `_looks_substantial` JS-shell check; the ladder *wraps*, does not replace them) → (JS-shell? `chrome` if installed) → **remote-reader as last-resort escalation**; (b) on-demand `--engine jina` / `--engine remote` = **remote-first** with automatic fallback to local `lite`→`chrome`; (c) **bidirectional** — any tier's failure degrades to the next viable tier (Jina-down→local, local-blocked→Jina); (d) a single typed `FetchFailed` is raised **only when every viable tier is exhausted**, never a bare crash; (e) `--no-remote` kill-switch disables the remote tier entirely (auto + on-demand). |
| **R2** | **Vendor-agnostic remote-reader provider layer** | ✅ | (a) a small `RemoteReader` provider abstraction (given a target URL → build reader request URL + headers; classify the response); (b) built-in **`jina`** provider (`r.jina.ai`, current behaviour preserved); (c) a **configurable generic provider** via env (`HTML2MD_READER_URL` for a single `<base>/<url>`-style reader, and/or an ordered `HTML2MD_READER_PROVIDERS` list) — enables a **self-hosted Jina** or any compatible reader; (d) providers tried **in order** with fall-through to the next on "provider-down"; (e) per-provider auth via env, **not interchangeable** — built-in `jina` → `JINA_API_KEY` (retained); generic/configured → `HTML2MD_READER_TOKEN` → `Authorization: Bearer`; (f) **`--engine remote` requires a configured provider** (`HTML2MD_READER_URL`/`_PROVIDERS`) — with none set it is a **usage error (exit 2)**, never a silent fall-back to `jina.ai`. |
| **R3** | **Failure classification** — "provider down" vs "target blocked" vs "tier blocked" | ✅ | (a) treat **DNS/connect/timeout, HTTP 5xx, 429, 402, 408, 503** as *provider/transient unavailable* → fall through to the next provider/tier; (b) reuse the existing retry + exponential backoff + `Retry-After` honouring for the transient classes before falling through; (c) a **local** `lite`/`chrome` block (a 403 that survives the browser-UA retry / Cloudflare) is a **tier**-failure → **escalate to the remote tier** (this is the core ssrn/researchgate recovery case, KNOWN_ISSUES HTML2MD-1); (d) a reader-reported **target** block/absence (reader maps the target's 403/401/404) is **terminal across remaining remote *providers*** (they would hit the same wall) — but in `auto` the ladder MAY still try a different **tier** (`chrome` executes JS and can pass checks `lite`/`jina` cannot) before the final error: **provider-terminal ≠ tier-terminal**; (e) an **empty / too-short reader body** counts as a provider-miss → fall through; (f) **`EngineNotInstalled`** (chrome requested but Playwright absent) is a **fall-through** trigger when chrome is reached as an *auto / remote-first fallback*, but stays **terminal exit 3** for an **explicit** `--engine chrome`; (g) net: no pointless cross-provider retries of a genuine 404, yet survival of any single provider/engine outage. |
| **R4** | **Smarter extraction** (the user-selected Jina capability) | ✅ | (a) pass **`X-Target-Selector`** (default `article, main, [role=main]`, overridable via `--target-selector`) so the reader returns just the article block; (b) opt-in **`--remote-format markdown`** "trust the reader's Markdown" mode → use the reader's own clean Markdown directly (skip the local `web_clean`→turndown pass) for hard pages, still wrapped with **our** YAML frontmatter; (c) **default `--remote-format html`** — the reader returns HTML that flows through the **same** local pipeline (consistent frontmatter / `_attachments` / dual-output) — preserving today's behaviour; (d) trust-markdown still honours `--download-images` (localize image URLs found in the returned Markdown). |
| **R5** | **Privacy / SSRF / honest-scope guards** | ✅ | (a) **NEVER** send a private / loopback / link-local / metadata / unresolvable **TARGET** URL to a remote reader — apply `_host_is_public` to the *target* before any remote escalation (auto **and** on-demand); (b) the auto remote-escalation is documented as "**target URL leaves the machine**" and is suppressible with `--no-remote`; (c) the local hop to the reader endpoint still passes the existing SSRF gate; (d) keyless rate-limit + `*_API_KEY` quota behaviour documented; (e) `SKILL.md` §5, `references/html-to-markdown.md`, and `docs/KNOWN_ISSUES.md` (HTML2MD-1/-6) updated for the new auto-escalation posture. |
| **R6** | **Observability for agent callers** | ✅ | (a) `AcquireResult.engine` reports the **real** tier used (`lite` / `lite+arxiv-html` / `lite+restapi` / `lite+nojs` / `jina` / `remote:<host>` / `chrome`); (b) frontmatter `engine:` / `source:` reflect provenance — `source:` stays the **canonical target URL**, never the reader URL; (c) on total failure the `--json-errors` `FetchFailed.details` carries a **`tried` trace** (each tier/provider attempted + its failure `kind`) so a caller can choose the next action; (d) extend the `details.kind` taxonomy where needed (e.g. `all_engines_failed`). |
| **R7** | **Tests** — close the Jina coverage gap + ladder | ✅ | (a) unit tests for provider request-URL/header construction (jina + a configured generic provider); (b) **fallback-ladder** tests that inject per-URL outcomes via the `_http_get_bytes` / provider seam (jina-down→lite; lite-blocked→jina; all-fail→one typed error with trace); (c) classification tests (provider-down vs reader-reported target-404); (d) **preserve the I-3 offline zero-network guard** (file/archive still make zero calls); (e) trust-markdown emit test; (f) privacy-guard test (an internal/private target is **not** sent to the reader). |
| **R8** | **Docs, packaging, fork-free integrity** | ✅ | (a) `SKILL.md` capabilities + engine table + safety boundaries updated; (b) `references/html-to-markdown.md` decision tree + provider-config + privacy section; (c) `docs/KNOWN_ISSUES.md` HTML2MD-1/-6 revised (auto-escalation + fallback now handled); (d) `validate_skill.py skills/html2md` exits 0; (e) **G-1/G-2/G-3 replication gate UNCHANGED** — assert `acquire.py`/`cli.py` are NOT gated units and no master byte-changes; (f) **no new runtime dependency** (`httpx` reused); (g) `docs/office-skills-backlog.md` §2 updated (record what shipped + what was deferred). |
| **R9** | **Web search (vendor-agnostic)** — query → top-N pages → Markdown | ✅ | (a) `--search "QUERY"` entrypoint (mutually exclusive with a URL/file INPUT); (b) vendor-agnostic **search-provider** layer — **`s.jina.ai`** built-in default + configurable via env (`HTML2MD_SEARCH_URL` / `HTML2MD_SEARCH_PROVIDERS`); (c) **two provider shapes** — *combined* (provider returns merged Markdown of the top results server-side, e.g. `s.jina.ai`) and *links* (provider returns the top result URLs → each is fetched through the **R1 FETCH ladder**, so every result inherits its own fallback); (d) `--max-results N` bound (default 5); (e) **search-provider fallback** — primary search provider down/429/402/5xx → fall through to the next configured provider; one typed `FetchFailed` only when all are exhausted; (f) emit **one note per result** into OUTPUT_DIR sharing `_attachments/`, frontmatter carries the query + the result URL; `--stdout` concatenates results |
| **R10** | **Explicitly deferred** (out of scope) | ⬜ | (a) **`X-With-Generated-Alt`** VLM image captions; (b) **cookie / auth passthrough** (`x-set-cookie`); (c) **screenshot / `pageshot`**; (d) **`X-With-Links-Summary`**. Recorded for a future task; not built (user scope = smarter-extraction + fetch-resilience + search). |

---

## 3. Use Cases

### UC-1 — Anti-bot page on `auto` auto-recovers (primary)
- **Actor:** User / agent clipping a Cloudflare/WAF-protected article.
- **Preconditions:** Network reachable; target host is public.
- **Main scenario:** `auto` tries `lite` → 403 even after the browser-UA retry
  (`kind=bot_blocked`) → **auto-escalates to the remote-reader tier** (default provider
  `jina`) → reader returns the article HTML → normal clean→turndown→emit.
- **Alternatives:** (a) the remote reader is **down/rate-limited/quota** → ladder falls
  through to `chrome` if installed, else raises one typed `FetchFailed` with the `tried`
  trace; (b) `chrome` is not installed and remote is down → typed error (no crash).
- **Postconditions:** A note is produced via whichever tier succeeded;
  `frontmatter.engine` records it; `source:` is the canonical URL.
- **Acceptance:** A simulated `lite`-403 + healthy reader yields a non-empty note with
  `engine: jina`; a simulated `lite`-403 + reader-down + no chrome yields exactly one
  `FetchFailed` whose `details.tried` lists both failed tiers.

### UC-2 — `--engine jina` survives a Jina outage (the headline requirement)
- **Actor:** User who prefers the remote reader for a known-hard page.
- **Preconditions:** Network reachable; target public.
- **Main scenario:** `--engine jina` (remote-first) → reader returns 503 / 429 / times
  out → **automatic fallback to `lite`**, then `chrome` if needed → conversion succeeds.
- **Postconditions:** Note produced via the fallback tier; the failure is invisible to
  the user except in `engine:` provenance.
- **Acceptance:** With the reader stubbed to fail and `lite` stubbed to succeed, the run
  exits 0 and `engine` ≠ `jina`. With **all** tiers stubbed to fail, exactly one typed
  `FetchFailed` (exit 10) is raised — never a traceback.

### UC-3 — Vendor-agnostic / self-hosted reader (no jina.ai dependency)
- **Actor:** Operator who self-hosts a reader or distrusts a single SaaS.
- **Preconditions:** `HTML2MD_READER_URL` (or `HTML2MD_READER_PROVIDERS`) points at a
  compatible reader.
- **Main scenario:** The remote tier uses the **configured** provider(s) in order; a
  jina.ai outage is irrelevant because jina.ai is not in the chain (or is last).
- **Acceptance:** With `HTML2MD_READER_URL=https://reader.internal.example/`, a remote
  escalation builds the request against that base and never contacts `r.jina.ai`.

### UC-4 — Privacy: internal URL is never sent to a remote service
- **Actor:** Agent converting an intranet/CRM URL.
- **Preconditions:** Target resolves to a private/internal/loopback address.
- **Main scenario:** `auto` → `lite` (SSRF gate already refuses private targets) → the
  remote tier is **skipped** because the target is not public; no external egress occurs.
  `--no-remote` additionally forces remote off for any target.
- **Acceptance:** With a private-resolving target, no request to any reader endpoint is
  attempted (verified by stub); `--no-remote` makes the remote tier unreachable.

### UC-5 — Smarter extraction (trust the reader's Markdown)
- **Actor:** User clipping a hard page where local re-clean is noisy.
- **Main scenario:** `--engine jina --remote-format markdown` → reader returns clean
  Markdown (with `X-Target-Selector`) → wrapped with our frontmatter + (optionally)
  localized images → emitted.
- **Acceptance:** The emitted body equals the reader's Markdown (modulo frontmatter +
  image-link rewriting), and `--download-images` still localizes resolvable image URLs.

### UC-6 — Web search → Markdown notes (new capability)
- **Actor:** Agent / user researching a topic (no specific URL yet).
- **Preconditions:** Network reachable; a search provider configured (default `s.jina.ai`).
- **Main scenario:** `html2md.py --search "QUERY" OUTPUT_DIR --max-results 5` → the search
  provider returns the top results → for a *links* provider each result URL is fetched via
  the R1 FETCH ladder (per-result fallback), for a *combined* provider the merged Markdown
  is taken directly → one note per result is emitted, each with frontmatter carrying the
  query + result URL, sharing one `_attachments/`.
- **Alternatives:** (a) the primary search provider is down/rate-limited → fall through to
  the next configured provider; (b) all search providers exhausted → one typed
  `FetchFailed` (exit 10) with the `tried` trace.
- **Postconditions:** Up to N self-contained notes (or concatenated Markdown with
  `--stdout`); no partial-crash if an individual result fails (it is skipped, others
  proceed).
- **Acceptance:** With the search provider stubbed to return 3 result URLs and the FETCH
  tier stubbed healthy, 3 notes are written; with the primary search provider stubbed to
  503 and a secondary healthy, results come from the secondary; with all stubbed to fail,
  exactly one `FetchFailed` is raised.

---

## 4. Acceptance Criteria (binary)

1. **AC-R1 (ladder/never-crash):** For every combination of {tier succeeds / tier fails}
   across the active tiers, the run either produces a note (exit 0) or raises exactly one
   typed `FetchFailed` (exit 10) — never an unhandled exception. `auto` is local-first;
   `--engine jina|remote` is remote-first; both fall back the other way.
2. **AC-R2 (vendor-agnostic):** With `HTML2MD_READER_URL` set, remote escalation targets
   the configured base and not `r.jina.ai`; with multiple providers configured they are
   tried in order until one succeeds or all are exhausted.
3. **AC-R3 (classification):** A reader/transport outcome in {DNS, timeout, 5xx, 429,
   402, 503} triggers fall-through; a reader-reported **target** 404/403 is terminal for
   that target (surfaced with the target `kind`, not retried across providers).
4. **AC-R4 (smarter extraction):** `X-Target-Selector` is sent on remote requests;
   `--remote-format markdown` uses the reader's Markdown directly (frontmatter still
   added; `--download-images` still localizes); default `html` preserves today's pipeline
   output.
5. **AC-R5 (privacy/SSRF):** A private/internal/unresolvable target is **never** sent to
   a remote reader (auto or on-demand); `--no-remote` disables the remote tier; docs state
   the URL-leaves-machine posture.
6. **AC-R6 (observability):** `frontmatter.engine` and `AcquireResult.engine` report the
   real tier; `source:` is the canonical target URL; on total failure
   `FetchFailed.details.tried` lists every attempted tier + its failure kind.
7. **AC-R7 (offline + coverage):** `I-3` holds (file/archive = zero network); new unit
   tests cover provider construction, the ladder, classification, trust-markdown, and the
   privacy guard; the previously-untested Jina path now has coverage.
8. **AC-R8 (fork-free + validate):** `diff -q` (G-1/G-2) stays silent and docx G-3 stays
   byte-identical (no master touched); `validate_skill.py skills/html2md` exits 0; no new
   line in `requirements.txt`.
9. **AC-R9 (search):** `--search "QUERY"` emits ≤ `--max-results` notes (one per result),
   each with the query + result URL in frontmatter; a *links* provider routes each result
   through the FETCH ladder (so a result's Jina-failure still falls back); search-provider
   failure falls through to the next provider, and only an all-providers-exhausted state
   raises one typed `FetchFailed`; an individual failed result is skipped, not fatal. A
   **healthy** search returning **zero** results exits **0 with a stderr note** (zero-results
   is not content-loss → not `EmptyExtraction`/11). `--max-results` must be **≥ 1** (≤ 0 →
   usage error, exit 2).

---

## 5. Design Decisions (locked) & Constraints

- **D-A (engine ladder — "best option", user-confirmed):** `auto` = local-first
  (`lite`→`chrome`→remote last-resort, privacy-preserving), opt-out `--no-remote`;
  `--engine jina|remote` = remote-first with local fallback. Combines the recommended
  "local-first, Jina auto-escalates + falls back" with on-demand remote-first.
- **D-B (vendor-agnostic remote tier — user-requested):** providers are pluggable and
  configurable (env), with `jina` as the built-in default; resilience never depends on a
  single vendor's uptime. Self-hosted Jina Reader is a first-class configuration.
- **D-C (provider-down vs target-blocked):** the fallback only fires for provider/transient
  failures; a genuinely blocked/absent *target* is reported honestly, not laundered into
  an infinite provider retry.
- **D-D (smarter extraction):** `X-Target-Selector` + opt-in `--remote-format markdown`;
  default stays HTML-through-local-pipeline for output consistency.
- **D-E (fork-free, owned files only):** all changes in `acquire.py`, `cli.py`, html2md
  tests, `SKILL.md`, `references/`, `KNOWN_ISSUES.md`. **No** `diff -q`-gated master
  (`web_clean/*`, `html2md_core.js`, `_errors.py`, `_venv_bootstrap.py`) is edited — the
  replication gate stays green by construction (CLAUDE.md §2). `acquire.py`/`cli.py` are
  confirmed html2md-owned and absent from the G-1/G-2 gate.
- **D-F (no new dependency):** the provider layer is plain `httpx` (already a base dep)
  through the existing `_http_get_bytes` seam — keeping the skill installable in isolation.
- **D-G (web search in scope — user-pulled-in 2026-06-23):** `--search "QUERY"` via a
  vendor-agnostic search-provider layer (`s.jina.ai` default + fallback). *Links*-shape
  providers route each result through the **same** R1 FETCH ladder, so search inherits the
  full fallback discipline; *combined*-shape providers (s.jina.ai) take merged Markdown
  directly. One note per result. Search providers fall through on provider-down; an
  individual failed result is skipped, not fatal.
- **D-H (latency bound — non-functional):** each tier is bounded by the existing
  per-request timeout; worst-case ladder latency = Σ attempted tiers. Acceptable for the
  serial v1; a slow provider cannot stall unboundedly (bounded timeout per hop). Revisit
  if/when batch is added.
- **Honest-scope inheritance:** all TASK 022 residuals (DNS-rebinding TOCTOU, un-hardened
  Chrome engine, data-grid SPAs, PDFs→pdf skill) remain; this task does not regress them.

---

## 6. Open Questions

- **Q1 (non-blocking, decided default):** Should the remote tier auto-escalate in `auto`
  by **default** (privacy trade-off: the target URL leaves the machine on escalation)?
  **Decision:** YES by default for **public** targets only, suppressible via `--no-remote`
  — this is exactly the "Jina becomes an automatic safety net" option the user chose. The
  architecture-reviewer should confirm the default is acceptable vs. requiring an explicit
  `--allow-remote` opt-in. *(Recorded for the review gate; default = auto-escalate-on.)*
- **Q2 (non-blocking):** Provider-config surface — a single `HTML2MD_READER_URL`, an
  ordered `HTML2MD_READER_PROVIDERS` list, or both? **Proposed:** support both (single var
  is the simple case; list is the power case), `jina` appended as the final default unless
  the user sets an explicit order.
- **Q3 (RESOLVED):** Web **search** is **IN SCOPE** — the user pulled it in (2026-06-23).
  Delivered by **R9** (vendor-agnostic search provider, `s.jina.ai` default + fallback,
  `--search`/`--max-results`, per-result FETCH-ladder routing). The vendor-agnostic
  **fetch** part remains R2; search reuses the same fallback discipline.
- **Q4 (non-blocking):** `--remote-format markdown` image localization — localize only
  `http(s)` image URLs found in the returned Markdown (skip `data:`), bounded by
  `--max-images`/`--max-bytes`. Proposed: yes, reuse the existing url-mode image path.

---

## 7. Verification plan (rolls into PLAN at /vdd-plan)

- Unit + ladder tests via the `_http_get_bytes` monkeypatch seam (offline, deterministic).
- `bash skills/html2md/scripts/tests/test_e2e.sh` — full suite + G-1/G-2 `diff -q` gate
  (must stay PASS).
- `validate_skill.py skills/html2md` exit 0.
- A real dogfood run on a known anti-bot URL (ssrn/researchgate) demonstrating
  auto-escalation, and a forced-Jina-failure run demonstrating fallback.
- **No auto-commit** (per `/vdd-*`); each logic bead gets an adversarial logic+security
  roast before being declared done.

---

## 8. As-built (post-implementation, 2026-06-23)

**Status:** ✅ SHIPPED — all 7 beads (023-01…07) merged via `/vdd-develop-all`, then a
3-critic `/vdd-multi` adversarial pass. **NOT committed** (per `/vdd-*`). **145 unit tests**
green; `test_e2e.sh` PASS incl. the G-1/G-2 `diff -q` replication gate; docx G-3
byte-identical; `validate_skill.py skills/html2md` exit 0; `requirements.txt` unchanged
(no new dependency). All changes in html2md-**owned** files (`acquire.py`, `cli.py`,
`model.py`, `emit.py`, `exceptions.py`).

Beyond the §2 RTM, the as-built adds:

- **`engine:` frontmatter (AC-R6 completion).** `emit._frontmatter` records the real fetch
  tier (caught by live dogfood — the spec required it but the first cut omitted it).
- **Search = one note per result.** `--search` results suppress the reader variant (R9 intent
  "N results → N notes"), via `_convert_one(query=…)`.
- **`/vdd-multi` hardening (7 findings fixed, +7 regression tests):**
  - *L-2* broadened the trust-markdown HTML sniff (`_LOOKS_HTML`) — a reader returning HTML
    despite `--remote-format markdown` (no doctype, `<?xml>`, comment, `<div>`/`<article>`)
    now falls back to the pipeline instead of emitting raw HTML.
  - *S-1* a `--search` result URL no longer escalates to the un-network-hardened Chrome tier
    in non-explicit-chrome modes (`_url_tiers(allow_chrome=…)`).
  - *P-3/L-4* `_search_result_urls` is bounded + deduped (no unbounded junk list).
  - *S-3* a `?url=`-style reader base fully encodes the target (query-injection guard).
  - *L-3* `--target-selector` CR/LF refused; *L-6* `run_search` per-result catch narrowed.
  - *L-5* `--search --stdout` emits a document separator.
- **Deferred (documented, `docs/KNOWN_ISSUES.md` HTML2MD-9):** *P-1/P-2* no aggregate
  `--deadline` (bounded but uncapped serial latency) and *P-4* `--max-bytes` unbounded default
  — both flagged as follow-ups beyond this task's RTM.
- **Verification artifacts:** `docs/tasks/task-023-0N-*.md` (beads),
  `docs/reviews/{task,arch,plan}-023-review.md` (gates), `docs/ARCHITECTURE.md` §15.
  New tests: `tests/test_{providers,ladder,privacy,extraction,search}.py` + `test_surface`
  additions. The critics confirmed sound: ladder always terminates with one typed error;
  `tried` trace is URL-free; private-target-never-sent-to-a-reader holds; YAML escaping;
  `_host_is_public` IPv6/encoded-host posture; no ReDoS; lazy heavy-dep imports.
