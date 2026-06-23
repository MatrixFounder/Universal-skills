# PLAN 023 — `html2md` resilient vendor-agnostic remote-reader + fallback + search — Stub-First

Maps **TASK 023** R1–R10 onto an atomic Stub-First bead chain. Architecture:
`docs/ARCHITECTURE.md` §15 (TASK 023 delta). **License:** Proprietary (html2md;
ARCH §9 / CLAUDE.md §3). **Scope guard:** every bead edits only html2md-**owned**
files (`acquire.py`, `cli.py`, `model.py`, `emit.py`, html2md tests, `SKILL.md`,
`references/`) — **no `diff -q`-gated master** is touched, so the two-master gate
(G-1/G-2/G-3) stays green by construction (asserted in 023-07).

**Phasing (`tdd-stub-first`):**
- **Phase 1 (Stub + RED tests):** bead **023-01** freezes the new public surface
  (CLI flags, `RemoteReader`/`SearchProvider` records, ladder skeleton) and lays
  RED tests via the `acquire._http_get_bytes` monkeypatch seam.
- **Phase 2 (Logic, Green):** beads **023-02…06** fill each concern behind the
  frozen surface, turning RED tests green and adding unit tests.
- **Integration + Docs:** bead **023-07** ships docs + gates + dogfood.

**No new dependency:** the provider layer is plain `httpx` (existing base dep) via
the single network seam `_http_get_bytes`. **No auto-commit** (per `/vdd-*`); each
Phase-2 bead gets an adversarial logic+security roast (`/vdd-multi`) before "done".

## Stub-First ordering (beads)

- **023-01 — [STUB] Public surface + records + ladder skeleton + RED tests.**
  Freeze `cli.py` flags (`--engine …|remote`, `--no-remote`, `--remote-format
  html|markdown`, `--target-selector`, `--search`, `--max-results`; `--search` ⊥
  positional INPUT → exit 2); add `RemoteReader`/`SearchProvider` records +
  `_TierUnavailable` internal signal (stubs); extend `model.AcquireResult`
  (`content_kind`, `markdown`); ladder/provider/search functions as stubs
  (`NotImplementedError`/sentinel); **RED** unit tests (ladder matrix, classification,
  privacy guard, provider construction, search) wired to the `_http_get_bytes` seam.
  → [task-023-01](docs/tasks/task-023-01-surface-stubs-red-tests.md)
- **023-02 — [R2] RemoteReader provider layer.** `_remote_providers(opts)` from env
  (`HTML2MD_READER_URL`/`HTML2MD_READER_PROVIDERS`) + `jina` default + ordering;
  `_build_reader_request(provider, target, opts) -> (url, headers)` (URL-encoded
  target, `X-Return-Format`, `Authorization`); keep `_fetch_jina_html` behaviour as
  the `jina` provider. → [task-023-02](docs/tasks/task-023-02-remote-reader-providers.md)
- **023-03 — [R1/R3/R6] Fallback-ladder orchestrator.** Rewrite `_acquire_url` as a
  tier loop: `auto`=local-first (`lite`→`chrome`→remote), `jina`/`remote`=remote-first
  (→`lite`→`chrome`), `lite`/`chrome`=single tier; fall-through on provider/transient
  (incl. auto `EngineNotInstalled`); one terminal `FetchFailed(kind=all_engines_failed,
  details.tried=[…])`; `engine`/`tried` provenance. Preserve existing site-variant
  rewrites + `_looks_substantial`. → [task-023-03](docs/tasks/task-023-03-fallback-ladder-orchestrator.md)
- **023-04 — [R5] Privacy / SSRF gate.** Apply `_host_is_public(target)` BEFORE any
  remote escalation (auto + on-demand); enforce `--no-remote`; request-URL injection
  guard (URL-encode target/query, reject CRLF/control chars). →
  [task-023-04](docs/tasks/task-023-04-privacy-ssrf-gate.md)
- **023-05 — [R4] Smarter extraction.** `X-Target-Selector` (default `article, main,
  [role=main]`, `--target-selector`) on remote requests; `--remote-format markdown`
  trust-mode (`content_kind=markdown` bypasses `clean`+`core_bridge`; frontmatter +
  image localization only; no reader variant). →
  [task-023-05](docs/tasks/task-023-05-smarter-extraction.md)
- **023-06 — [R9] Web search.** `SearchProvider` layer (`s.jina.ai` combined +
  generic links-shape via `HTML2MD_SEARCH_URL`/`HTML2MD_SEARCH_PROVIDERS`);
  `--search "QUERY"`/`--max-results`; links-shape routes each result URL through the
  R1 FETCH ladder; per-result skip-on-fail; one-note-per-result emit loop (shared
  `_attachments/`, `query:` frontmatter); search-provider fallback. →
  [task-023-06](docs/tasks/task-023-06-web-search.md)
- **023-07 — [R7/R8] Integration + docs + gates.** `SKILL.md`,
  `references/html-to-markdown.md`, `docs/KNOWN_ISSUES.md` HTML2MD-1/-6, backlog §2;
  `validate_skill.py skills/html2md` exit 0; **assert G-1/G-2/G-3 unchanged** + no new
  `requirements.txt` line; dogfood an anti-bot URL (auto-escalation) + a
  forced-Jina-failure (fallback) + a `--search` run. →
  [task-023-07](docs/tasks/task-023-07-docs-integration-gates.md)

## RTM → Bead checklist (mandatory RTM linking — one RTM item per line)

- [ ] **[R1]** Resilient fallback ladder (no single point of failure) — **023-01** (surface/stub) + **023-03** (logic)
- [ ] **[R2]** Vendor-agnostic remote-reader provider layer — **023-02**
- [ ] **[R3]** Failure classification (provider-down / target-blocked / tier-block) — **023-03**
- [ ] **[R4]** Smarter extraction (X-Target-Selector + trust-markdown) — **023-05**
- [ ] **[R5]** Privacy / SSRF / injection guards — **023-04**
- [ ] **[R6]** Observability (`engine` + `tried` trace) — **023-03**
- [ ] **[R7]** Tests (jina-gap + ladder + classification + privacy + search) — **023-01** (RED) + **023-02…06** (Green) + **023-07** (suite/validate)
- [ ] **[R8]** Docs, packaging, fork-free integrity (gate unchanged, no new dep) — **023-07**
- [ ] **[R9]** Web search (vendor-agnostic) — **023-06**
- [ ] **[R10]** Explicitly deferred (VLM alt-text / cookie / screenshot / links-summary) — *no bead; recorded in TASK §2 + backlog*

## Use-Case → Bead coverage table

| Use Case | Beads |
|---|---|
| UC-1 anti-bot page auto-recovers | 023-03 (ladder) + 023-02 (provider) + 023-04 (public-target guard) |
| UC-2 `--engine jina` survives a Jina outage | 023-03 (remote-first + local fallback) |
| UC-3 vendor-agnostic / self-hosted reader | 023-02 (env providers) |
| UC-4 privacy: internal URL never sent remote | 023-04 |
| UC-5 smarter extraction (trust-markdown) | 023-05 |
| UC-6 web search → Markdown notes | 023-06 (+ 023-03 ladder for links-shape results) |

## MVP gate

**023-01…04** = the resilient vendor-agnostic ladder + privacy gate (the user's two
hard requirements). **023-05** (smarter extraction), **023-06** (web search, R9) and
**023-07** (docs/gates) complete TASK 023.

## Acceptance (rolls up TASK 023 §4 + ARCH §15 guards)

- [ ] **AC-R1** ladder never crashes; one typed error only when all tiers exhausted — 023-03
- [ ] **AC-R2** `HTML2MD_READER_URL` → configured base, not r.jina.ai; ordered providers — 023-02
- [ ] **AC-R3** provider-down → fall-through; reader-reported target-404 → terminal-per-provider — 023-03
- [ ] **AC-R4** `X-Target-Selector` sent; `--remote-format markdown` trust-mode; default html unchanged — 023-05
- [ ] **AC-R5** private/internal target never sent remote; `--no-remote` disables tier — 023-04
- [ ] **AC-R6** `engine`/`tried` reflect the real tier; `source:` = canonical URL — 023-03
- [ ] **AC-R7** I-3 offline zero-network preserved; new coverage incl. previously-untested jina — 023-01…06
- [ ] **AC-R8** `diff -q` (G-1/G-2) silent + docx G-3 byte-identical; `validate_skill.py` exit 0; no new dep — 023-07
- [ ] **AC-R9** `--search` ≤ N notes; per-result FETCH-ladder fallback; per-result skip; search-provider fallback — 023-06

## Strict-mode note

The **security-critical** beads (**023-03** ladder + **023-04** SSRF/injection gate)
SHOULD follow `tdd-strict` (write the failing test first, incl. the SSRF/injection and
all-tiers-fail cases) — they are the parts where a regression silently leaks a URL or
masks a failure.
