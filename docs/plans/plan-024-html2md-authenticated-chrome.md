# PLAN 024 — `html2md` authenticated Chrome (server/Hermes-deployable) — Stub-First

Maps **TASK 024** R1–R10 onto an atomic Stub-First bead chain. Architecture:
`docs/ARCHITECTURE.md` §16. **License:** Proprietary (html2md). **Scope guard:** every bead
edits only html2md-**owned** files (`acquire.py`, `cli.py`, new `_chrome_auth.py`/`_cookies.py`,
tests, docs) — **no `diff -q`-gated master** is touched (G-1/G-2/G-3 green by construction,
asserted in 024-06). Chrome stays **soft-optional** → no new base dependency.

**Load-bearing ordering:** **R1 (Chrome SSRF hardening, 024-02) lands BEFORE R2 (auth context,
024-03)** — attaching credentials to an un-gated, redirect-following browser is a cred-exfil
regression. Security beads **024-02** and **024-04** run under **`tdd-strict`** (failing
SSRF/exfil + file-hardening tests first). **Cookies sub-path forward-ref (no inversion):** the
`storage_state` (primary) + persistent-profile paths land green in **024-03**; only the
`cookies.txt` sub-path needs `to_playwright_cookies` from **024-04**, so its one test (TC-03-02)
is written **RED in 024-03 and greened in 024-04** — the chain stays linear. **`login` dispatch:
DECIDED = verb-intercept in `main`** (the flat `nargs="?"` parser would mis-parse `login URL`).

**Phasing (`tdd-stub-first`):**
- **Phase 1 (Stub + RED):** **024-01** freezes the CLI/`login`-subcommand surface + records +
  RED tests (incl. the **R10 non-regression** test).
- **Phase 2 (Logic, Green):** **024-02…05** fill each concern behind the frozen surface.
- **Integration + Docs:** **024-06** ships docs + Hermes-deploy + gates + dogfood.

**No auto-commit** (per `/vdd-*`); each Phase-2 bead gets an adversarial `/vdd-multi` roast.

## R10 — graceful degradation is a CROSS-CUTTING invariant (not one bead)

Auth/keys are strictly additive. **Every** bead must preserve: no `--chrome-*`/no `JINA_API_KEY`
→ byte-for-byte TASK 023, no crash. 024-01 lays the non-regression test; 024-06 asserts the full
no-auth suite stays green.

## Stub-First ordering (beads)

- **024-01 — [STUB] Surface + records + RED tests.** `cli.py`: add `--chrome-storage-state` /
  `--chrome-cookies-file` / `--chrome-user-data-dir` (mutually-exclusive), `--chrome-scroll` /
  `--chrome-scroll-passes`, and the `login` subcommand surface (dispatch shape: a `login` verb in
  `main` before the flat parser, **or** `add_subparsers` — decide here). New `_chrome_auth.py` /
  `_cookies.py` skeletons + `_fetch_chrome_html(url)`→`(url, opts)` signature stub. **RED** tests:
  SSRF private-redirect-block (first request), off-target public-redirect block, auth-context,
  stale-session→`auth_required`, cookie host-scope, **R10 non-regression** (no-auth=TASK-023 +
  missing-file→typed-error). → [task-024-01](docs/tasks/task-024-01-surface-stubs-red-tests.md)
- **024-02 — [R1] Chrome SSRF hardening (`tdd-strict`).** In `_fetch_chrome_html`: install
  guards **before `page.goto`** at the **context** level — `_assert_public_http(url)`; main-frame
  redirect host-gate; **off-target public-redirect refusal** (final landed origin == target
  eTLD+1); `context.route("**/*")` abort of non-public sub-resource/`fetch`/`sendBeacon`.
  Honest-scope: DNS-rebind TOCTOU inherited, localStorage origin-restored. →
  [task-024-02](docs/tasks/task-024-02-chrome-ssrf-hardening.md)
- **024-03 — [R2] Authenticated context.** `_chrome_auth.resolve_context_kwargs(opts)` →
  `new_context(storage_state=…)` / `new_context()+add_cookies(…)` / `launch_persistent_context(…)`;
  mutually-exclusive; **any auth flag sets effective engine=chrome** (never silently drops the
  credential to lite). → [task-024-03](docs/tasks/task-024-03-authenticated-context.md)
- **024-04 — [R3/R7] `login` mint helper + hardened cookie loader (`tdd-strict`).** `login`
  subcommand → headful Chromium → `context.storage_state(path=…)` → `chmod 0600`. `_cookies.py`:
  lift `load_cookie_jar` (symlink-reject, **reject `st_mode & 0o077`** group+world, sanitized
  errors) + new Netscape→Playwright-cookie-dict conversion. Secrets file/env-only; redaction. →
  [task-024-04](docs/tasks/task-024-04-login-mint-cookie-loader.md)
- **024-05 — [R4/R5c] Scroll-to-load + stale-session detection.** `--chrome-scroll` (passes
  default 8, wall-clock cap 60 s); login-wall heuristic (redirect-to-/login · marker needle ·
  target-selector absent) → `FetchFailed kind=auth_required`. →
  [task-024-05](docs/tasks/task-024-05-scroll-and-stale-session.md)
- **024-06 — [R5/R6/R8] Docs + Hermes deploy + Jina-key matrix + gates + dogfood.** `SKILL.md`,
  `references/`, a **server/Hermes deploy** section (mint→deploy→consume→rotate; storage_state as
  secret; concurrency; self-hosted-Jina synergy), the **Jina-key matrix** (R6), KNOWN_ISSUES;
  `validate_skill.py` exit 0; **assert G-1/G-2/G-3 unchanged + no new base dep + full no-auth
  suite green (R10)**; dogfood: `login` → render an authed X Article. →
  [task-024-06](docs/tasks/task-024-06-docs-hermes-gates.md)

## RTM → Bead checklist (one RTM item per line)

- [ ] **[R1]** Chrome SSRF hardening (prerequisite) — **024-01** (RED) + **024-02** (logic)
- [ ] **[R2]** Authenticated Chrome context — **024-01** (surface) + **024-03**
- [ ] **[R3]** Session minting helper (`login`) — **024-04**
- [ ] **[R4]** Scroll-to-load — **024-05**
- [ ] **[R5]** Remote / Hermes deployability — **024-05** (stale-session) + **024-06** (deploy/synergy)
- [ ] **[R6]** Jina API-key strategy — **024-06**
- [ ] **[R7]** Security (file hardening / redaction / host-scope) — **024-02** (SSRF) + **024-04** (creds) + cross-cutting
- [ ] **[R8]** Tests, docs, fork-free — all beads (tests) + **024-06** (gates/validate)
- [ ] **[R9]** Explicitly deferred (x-set-cookie / programmatic-login / auto-refresh / cookies→lite) — *no bead*
- [ ] **[R10]** Graceful degradation / non-regression — **024-01** (test) + **ALL beads preserve** + **024-06** (no-auth suite green)

## Use-Case → Bead coverage

| Use Case | Beads |
|---|---|
| UC-1 mint locally + clip authed X Article | 024-04 (mint) + 024-03 (context) + 024-02 (gate) |
| UC-2 Hermes server, headless, concurrent | 024-03 (storage_state) + 024-06 (deploy docs) |
| UC-3 reply threads / lazy content | 024-05 (scroll) |
| UC-4 stale/expired session | 024-05 (auth_required heuristic) |
| UC-5 jina key for anti-bot non-auth | 024-06 (key matrix) |

## MVP gate

**024-01…04** = the hardened authenticated render (SSRF gate + auth context + mint/loader).
**024-05** (scroll/staleness) and **024-06** (docs/server/gates) complete TASK 024.

## Acceptance (rolls up TASK 024 §4)

- [ ] **AC-R1** private + off-target-public redirects blocked on first request (guards before goto) — 024-02
- [ ] **AC-R2** storage_state/cookies context; mutually-exclusive; auth⇒chrome — 024-03
- [ ] **AC-R3** `login` writes 0600 storage_state via headful; runtime headless — 024-04
- [ ] **AC-R4** scroll bounded by passes(8)+wall-clock(60s); never hangs — 024-05
- [ ] **AC-R5** read-only state concurrency-safe; stale→auth_required; deploy/rotate docs — 024-05/06
- [ ] **AC-R6** `JINA_API_KEY` env-only keyed/keyless; live session never to jina; matrix doc — 024-06
- [ ] **AC-R7** reject `0o077` perms + symlink + sanitized; secrets never argv/logs; host-scope — 024-02/04
- [ ] **AC-R8** `diff -q` (G-1/G-2) silent + docx G-3; `validate_skill.py` exit 0; no new base dep — 024-06
- [ ] **AC-R10** no-auth = TASK-023 (suite green); missing-file→typed-error; Playwright-absent→exit 3 — 024-01/06

## Strict-mode note

**024-02** (SSRF/exfil gate) and **024-04** (credential file handling) MUST follow `tdd-strict` —
write the failing security tests first (private + off-target-public redirect refusal on the first
request; group/world-perm rejection; secret-never-in-logs). These are where a regression silently
exfiltrates a session or leaks a credential.
