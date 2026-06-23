# TASK 024 — `html2md`: authenticated (login-gated) fetch via a hardened Chrome engine, server/Hermes-deployable

**Status:** 🟡 ANALYSIS (VDD start-feature) — TASK + ARCHITECTURE drafted, pending
review-loop gates. NOT yet planned/implemented.
**Skill:** `html2md` (existing, **Proprietary, All Rights Reserved**). Adds only
html2md-**owned** code (`acquire.py`, `cli.py`, a new `_cookies.py`/`_chrome_auth.py`,
tests, docs) — touches **no** `diff -q`-gated master, so G-1/G-2/G-3 stay green.
**Predecessor:** TASK 023 (resilient vendor-agnostic remote-reader + fallback + search) —
SHIPPED & archived (`docs/tasks/task-023-html2md-remote-reader-fallback.md`).
**Mode:** VDD.
**Driver:** dogfooding hit X Articles / reply-threads behind **login + JS** that no engine
can read unauthenticated (lite → "JavaScript is not available" wall; keyless jina →
rate-limited fallback; chrome → login wall). User chose **Chrome-auth** and added two
constraints: **(a)** it must later run on a **remote server (e.g. Hermes)** and **(b)**
the **Jina API-key** story must be worked out (user 2026-06-23).
**Provenance:** design locked over a 6-agent `/vdd-multi`-style design panel (recon ×3 +
approach panel ×3); see `docs/reviews/` + the workflow output.

---

## 0. Meta Information

- **Task ID:** 024
- **Slug:** `html2md-authenticated-chrome`
- **Context:** Login-gated content (X long-form Articles, reply threads, paywalled/members
  articles, private docs) requires a **real, authenticated, JS-rendering browser**. The
  current Chrome tier is a bare `launch + goto` with **no auth and — critically — no SSRF
  gate** (unlike lite/remote). Attaching real session credentials to a redirect-following,
  un-gated browser would be a **credential-exfiltration regression**, so SSRF-hardening the
  Chrome tier is a **hard prerequisite** of this task. The chosen auth primitive is
  Playwright **`storage_state`** (cookies + localStorage/sessionStorage) because it is a
  **portable, read-only-at-runtime file** — ideal for a remote/Hermes server (mint once
  where a browser exists → ship the state file as a secret → render headless; safe under
  concurrency, unlike a mutable persistent profile).
- **Runtime:** unchanged hybrid; Chrome tier stays **soft-optional** (`install.sh
  --with-chrome` / `requirements-chrome.txt`). No new base dependency.

---

## 1. Problem Description

From the dogfood: `html2md` cannot read login-gated pages, and the only working path today
is the **manual** offline `.webarchive` (save-from-browser → convert offline). Gaps:

1. **No authenticated fetch.** `_fetch_chrome_html` (acquire.py) does `pw.chromium.launch()`
   + `browser.new_page(user_agent=…)` + `goto` — **no browser context, no cookies, no
   storage_state**. So JS+login pages return a login wall.
2. **Chrome tier is SSRF-un-gated.** Only lite/remote call `_assert_public_http`; the Chrome
   path follows redirects (incl. to internal/metadata hosts) with no public-IP check. Adding
   credentials here **without** a gate turns a render into an exfil vector → hardening is a
   prerequisite, not an afterthought.
3. **No server/remote story.** A one-time login is inherently interactive (needs a browser);
   a server (Hermes) is headless. There is no defined way to **mint auth once, deploy it as a
   secret, and consume it headless + concurrently** on a server.
4. **Jina key strategy is undocumented.** `JINA_API_KEY` is read but there is no guidance on
   keyless-vs-keyed quotas, where the key lives on a server, or when to prefer local
   chrome-auth over sending content to Jina (and the live-session `x-set-cookie` forwarding
   is unverified + 3rd-party — out of scope here).

This task closes 1–4 **without forking** (owned files only) and **without a new base
dependency** (Chrome stays the existing soft-optional extra).

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | **Chrome SSRF hardening** (HARD PREREQUISITE of auth) | ✅ | (a) `_assert_public_http(url)` before `goto` in the chrome tier; (b) refuse navigation/redirect to a non-public host (a `page.on("request"/"response")` or `route` guard re-checking `_host_is_public` on the main-frame navigation chain); (c) best-effort **abort sub-resource requests to non-public hosts** via `page.route`; (d) honest-scope note for residual (full beacon isolation deferred); (e) regression test: a redirect to `169.254.169.254` / `127.0.0.1` is blocked even with auth attached |
| **R2** | **Authenticated Chrome context** | ✅ | (a) `--chrome-storage-state PATH` (**primary**) → `browser.new_context(storage_state=…)` (cookies + localStorage); (b) `--chrome-cookies-file PATH` (Netscape `cookies.txt`) → convert via a hardened loader → `context.add_cookies([...])`; (c) `--chrome-user-data-dir DIR` → `launch_persistent_context` (local convenience; flagged NOT-for-server-concurrency); (d) mutually-exclusive group; env fallbacks `HTML2MD_CHROME_STORAGE_STATE`/`_COOKIES_FILE`/`_USER_DATA_DIR`; (e) **any auth flag implies the chrome tier** (never silently fall back to lite and drop the credential) |
| **R3** | **Session minting helper** (interactive, local) | ✅ | (a) `html2md.py login URL [--save-state out.json]` → **headful** Chromium, user logs in by hand (incl. 2FA), then `context.storage_state(path=out.json)`; (b) output `chmod 0600`; (c) document the alternatives (`playwright codegen --save-storage`, browser `cookies.txt` export); (d) the mint helper is the ONLY interactive/headful path — runtime stays headless |
| **R4** | **Scroll-to-load** (lazy content / replies) | ✅ | (a) opt-in `--chrome-scroll` + `--chrome-scroll-passes N` (default ~8); (b) after `goto`, scroll to bottom N times, awaiting `networkidle`/settle, bounded by a **wall-clock budget**; (c) then snapshot `page.content()`; (d) honest scope: best-effort, deep/infinite threads may truncate (logged) |
| **R5** | **Remote / Hermes deployability** | ✅ | (a) **`storage_state.json` is the portable auth unit** — mint on a workstation, ship to the server as a secret (env path or mounted 0600 file), consume headless; (b) **read-only at runtime → concurrency-safe** (N parallel Hermes runs share one state file); persistent-profile is explicitly **single-concurrency / not server-recommended**; (c) **stale-session detection** (load-bearing for Hermes; X serves a *200* login wall, not a 401, so `_fetch_kind` alone misses it): a **best-effort, per-site login-wall heuristic** — signal class = {redirected to a `/login`-class URL, a known login-wall marker/needle, or the requested `--target-selector` absent} → classify `FetchFailed kind=auth_required` (never return the logged-out wall as content). Honest-scope: best-effort, tuned for X first; a false-negative would emit a wall, so the needles must be conservative and tested; (d) secret-management + rotation guidance (re-mint → redeploy); (e) optional synergy doc: a **self-hosted Jina** (TASK 023 `HTML2MD_READER_URL`) on the Hermes box keeps the remote tier in-network (no 3rd-party egress) |
| **R6** | **Jina API-key strategy** | ✅ | (a) document `JINA_API_KEY` (env/secret) keyless-vs-keyed quota + reliability; (b) **decision matrix:** auth'd content → **local chrome-auth** (never ship a live session to jina by default); anti-bot **non-auth** content / server volume → **keyed jina** (higher quota) or self-hosted reader; (c) ensure the key is read from env/secret only (never argv/logs); (d) explicitly DO NOT enable live-session `x-set-cookie` forwarding (R9) |
| **R7** | **Security** | ✅ | (a) `storage_state.json`/`cookies.txt` are bearer creds → hardened loader (reject symlink, enforce 0600, sanitized errors that never echo file contents) reusing the `transcript-fetcher` pattern; (b) secrets via **file/env only, never argv** (no `ps`/history leak); (c) **redaction**: cookie/state values + auth headers never appear in any error / `--json-errors` / `tried` trace; (d) **host-scope cookies** to the target eTLD+1 (a redirect to `evil.com` cannot replay `example.com`'s session); (e) ToS/honest-scope: this replays the *user's own* human-minted session (no programmatic login/password handling) |
| **R8** | **Tests, docs, fork-free** | ✅ | (a) unit tests via the Playwright seam (monkeypatch `_fetch_chrome_html`/context builder) + offline cookie-loader tests; SSRF-block test (R1e); stale-session→`auth_required` test; (b) `SKILL.md` + `references/` + a server/Hermes deploy section + KNOWN_ISSUES update; (c) `validate_skill.py` exit 0; (d) **G-1/G-2/G-3 unchanged** (assert acquire.py/cli.py/new modules not gated); (e) no new **base** dep (Chrome stays the soft-optional extra) |
| **R10** | **Graceful degradation / non-regression** (auth is strictly additive) | ✅ | (a) **No auth configured** (no `JINA_API_KEY`, no `--chrome-*` flag/env) → behaviour is **byte-for-byte TASK 023**: the resilient `auto` ladder (lite→chrome→remote), keyless-jina fallback, **no crash**; (b) auth/keys are **opt-in only** — never a hard requirement to run; (c) Playwright absent + a `--chrome-*` flag given → graceful `EngineNotInstalled` (exit 3) with remediation, **not a traceback**; (d) an auth flag given but the state/cookies file is **missing/unreadable/malformed** → a clean typed error (`BadInput`/`Usage`), never an unhandled exception; (e) `JINA_API_KEY` absent → keyless tier as today (TASK 023). The **default install + default invocation are unchanged**. |
| **R9** | **Explicitly deferred** | ⬜ | (a) Jina **live-session `x-set-cookie`** forwarding (unverified vs Jina's real API + ships the session to a 3rd party); (b) **programmatic** login / username-password / 2FA automation (we only replay a human-minted session); (c) **auto-refresh** of expired sessions (user re-mints); (d) cookies→lite-tier auth (the panel's clean MVP for *server-rendered* cookie sites) — recordable as a small fast-follow if non-JS login sites become a need |

---

## 3. Use Cases

### UC-1 — Mint locally, clip an authed X Article (primary)
- **Actor:** User on a workstation with a browser.
- **Main scenario:** `html2md.py login https://x.com --save-state ~/.html2md/x.json` →
  headful Chromium, user logs in (2FA ok) → `x.json` (0600) written. Then
  `html2md.py "https://x.com/i/article/<id>" out/ --engine chrome --chrome-storage-state ~/.html2md/x.json`
  → headless render of the **logged-in** page → full article Markdown + images.
- **Acceptance:** the full article body (not a login wall) is emitted; `engine: chrome`;
  the state file is never logged/redacted into output.

### UC-2 — Hermes server, headless, concurrent (the remote requirement)
- **Actor:** Hermes agent on a headless server.
- **Preconditions:** `x.json` minted on a workstation and **deployed as a secret** (env
  `HTML2MD_CHROME_STORAGE_STATE=/secrets/x.json`, mode 0600); `install.sh --with-chrome` on
  the server.
- **Main scenario:** N concurrent Hermes runs each call `--engine chrome` reading the **same
  read-only** state file → each renders headless independently (no profile lock contention).
- **Acceptance:** concurrent runs do not corrupt/lock shared state; no interactive/headful
  step at runtime; a stale state surfaces `auth_required` (exit) rather than logged-out content.

### UC-3 — Pull reply threads / lazy content
- **Main scenario:** `--engine chrome --chrome-storage-state … --chrome-scroll --chrome-scroll-passes 12`
  → after load, scroll to load replies (bounded by passes + wall-clock) → snapshot.
- **Acceptance:** replies present in output up to the scroll budget; never hangs (hard cap).

### UC-4 — Stale / expired session
- **Main scenario:** state file expired → render returns X's login wall → a login-wall
  heuristic classifies it `FetchFailed kind=auth_required` (exit 10).
- **Acceptance:** the logged-out wall is NOT emitted as "content"; the error tells the user
  to re-mint.

### UC-5 — Jina key for anti-bot non-auth content (server volume)
- **Main scenario:** a Cloudflare-protected **public** page on the server → keyed
  `JINA_API_KEY` raises quota/reliability for the remote tier (no session involved).
- **Acceptance:** with `JINA_API_KEY` set, the remote tier uses it (Bearer); without it,
  keyless fallback still works (TASK 023 behaviour); a live session is **never** sent to jina.

---

## 4. Acceptance Criteria (binary)

1. **AC-R1:** with auth attached, a chrome render whose target (or a redirect) resolves to a
   private/loopback/metadata host is **blocked** (`_assert_public_http`); a test proves a
   `169.254.169.254`/`127.0.0.1` redirect is refused **on the first request** (guards installed
   **before** `goto`, at the context level). Additionally, an **off-target *public* redirect**
   (`example.com`→`evil-public.com`) is refused before snapshot — the final landed origin must
   equal the requested target's eTLD+1 (so a session is never carried to a different public
   site). DNS-rebinding TOCTOU remains an inherited residual (§10).
2. **AC-R2:** `--chrome-storage-state` produces an authenticated context (cookies+localStorage);
   `--chrome-cookies-file` converts Netscape cookies → context cookies; the three auth sources
   are mutually exclusive; any auth flag forces the chrome tier (never silently lite).
3. **AC-R3:** `html2md.py login URL --save-state f.json` writes a 0600 `storage_state` JSON via
   a headful browser; runtime consumption is headless.
4. **AC-R4:** `--chrome-scroll` loads additional lazy content bounded by `--chrome-scroll-passes`
   (default 8) + a wall-clock cap (default 60 s) — never hangs.
5. **AC-R5:** the same read-only `storage_state.json` is consumed headless by concurrent runs
   without corruption/lock; a stale session yields `auth_required`, not logged-out content;
   docs describe the mint→deploy→rotate flow + the self-hosted-Jina synergy.
6. **AC-R6:** `JINA_API_KEY` (env only) is used when present (keyed) and absent→keyless; a live
   session is never forwarded to jina; the decision matrix is documented.
7. **AC-R7:** state/cookie files reject **both group- and world-accessible** modes (`st_mode &
   0o077` → error; tighter than the transcript-fetcher world-only check — an intentional
   server-threat-model divergence), symlink-rejected, sanitized-on-error; secrets never appear
   on argv or in any error/`--json-errors`/`tried` output. Cookie host-scoping is enforced by
   the browser's native cookie-domain matching **plus** the AC-R1 final-origin gate (the
   Playwright path does not use a urllib redirect handler).
8. **AC-R8:** `diff -q` (G-1/G-2) silent + docx G-3 byte-identical; `validate_skill.py` exit 0;
   no new line in base `requirements.txt`; new tests cover R1/R2/R4/R5/R7.
9. **AC-R10 (non-regression):** with NO auth/keys configured, the full existing test suite stays
   green and `--engine auto` behaves identically to TASK 023 (a test asserts no `--chrome-*`/key
   path is taken by default); a `--chrome-*` flag with a missing/malformed file → a typed error
   (not a traceback); Playwright-absent + `--chrome-*` → exit 3 `EngineNotInstalled`.

---

## 5. Design Decisions (locked) & Constraints

- **D-A (chrome SSRF gate is a prerequisite):** R1 lands with/before R2 — never attach
  credentials to an un-gated, redirect-following browser.
- **D-B (`storage_state` primary, server-first):** portable, read-only-at-runtime,
  concurrency-safe → the unit of remote/Hermes auth deployment. `cookies.txt` is the
  cookie-only alternative; persistent-profile is local-convenience only (not server-concurrent).
- **D-C (replay-only, never programmatic login):** the skill replays a *human-minted* session;
  it never handles passwords or automates 2FA — narrower attack surface + cleaner ToS posture.
- **D-D (auth only on the chrome tier; never to jina by default):** live sessions stay local;
  the remote/jina tier is for non-auth content (keyed for quota). `x-set-cookie` forwarding is
  deferred (R9) — unverified + 3rd-party exfil.
- **D-E (secrets discipline):** file/env only (never argv), 0600 + symlink-reject + sanitized
  errors (reuse `transcript-fetcher` `_cookies.py` pattern), full redaction, host-scoped cookies.
- **D-F (fork-free, owned files; no new base dep):** all changes in `acquire.py`, `cli.py`, new
  html2md-owned `_cookies.py`/`_chrome_auth.py`, tests, docs; Chrome stays soft-optional.
- **D-G (graceful degradation — auth is strictly additive; user-required):** with NO keys and
  NO chrome session configured, html2md runs **exactly as TASK 023** (resilient ladder, no
  crash) — auth/keys are opt-in, never a precondition. A `--chrome-*` flag with a missing/broken
  file, or Playwright absent, degrades to a **typed error** (exit 1 / exit 3), never a traceback.
  The default install and default invocation are unchanged. (R10.)
- **Honest-scope inheritance:** TASK 022/023 residuals stand; the chrome network hardening here
  is **best-effort** (main-frame + sub-resource host gating), not full beacon isolation — the
  egress-restricted-sandbox advice remains for fully-untrusted input.

---

## 6. Open Questions

- **Q1 (non-blocking):** include the persistent-profile path (`--chrome-user-data-dir`) in the
  MVP, or defer it? **Proposed:** include but document as local-only / single-concurrency
  (it's the only path that self-refreshes + survives 2FA without re-mint).
- **Q2 (non-blocking):** scroll defaults — passes (8?) + wall-clock cap (e.g. 60s)? confirm at
  planning.
- **Q3 (non-blocking, recorded):** also wire **cookies→lite** (the panel's S-effort MVP for
  *server-rendered* cookie sites)? Deferred to R9(d) — html2md's login cases are JS-walled
  (X), which lite can't render; pull in only if a non-JS login site becomes a need.
- **Q4 (Hermes secret transport) — RESOLVED (scoping):** the **skill's contract terminates at
  "read a 0600 file at a path given by `--chrome-storage-state` / `HTML2MD_CHROME_STORAGE_STATE`"**.
  HOW the secret is delivered (mounted volume / env / secret manager) is **Hermes-owned, out of
  this skill's scope** — so Q4's open status does NOT block R5/MVP. Recommend env-path to a 0600
  file; confirm the transport with the Hermes integration owner at deploy time.

---

## 7. Verification plan (rolls into PLAN at /vdd-plan)

- Playwright-seam unit tests (monkeypatch the context builder + a fake page) — no real browser
  in CI; an opt-in live mint+render dogfood (the X Article) recorded, not CI-gated.
- SSRF-block test (R1e), stale-session→`auth_required` (R5c), cookie host-scope + file-hardening
  (R7), concurrency note (read-only state).
- `bash scripts/tests/test_e2e.sh` (suite + G-1/G-2 gate) PASS; `validate_skill.py` exit 0.
- **No auto-commit** (per `/vdd-*`); security beads (R1 gate, R7) under `tdd-strict`.

## 8. As-built (2026-06-23, post-`/vdd-multi`)

Delivered across 6 beads; all 10 RTM rows realized. Gates: **177 tests green & proven hermetic**
(suite passes with external DNS+TCP blocked), G-1/G-2/G-3 replication gate PASS, `validate_skill`
exit 0, **no new base dependency** (Playwright already optional/lazy from TASK 023).

**New files (all html2md-OWNED, NOT `diff -q`-gated):**
- `html2md/_chrome_auth.py` — `resolve_context_kwargs(opts)` (one auth source → Playwright context
  spec: storage_state / cookies / persistent profile) + `is_login_wall(html, final_url)`
  (conservative stale-session heuristic).
- `html2md/_cookies.py` — `load_cookie_jar` (symlink + `0o077` reject + sanitized errors) +
  `to_playwright_cookies` (lifted+tightened from transcript-fetcher; do-not-fork note in code).
- `skills/html2md/.env.example` — documents every optional env var (read from process env; **not**
  auto-loaded).

**Changed:** `acquire._fetch_chrome_html(url, opts)` is SSRF-gated (pre-`goto`
`_assert_public_http`, context `route` guard, off-target public-redirect refusal, `--max-bytes`
parity, stale→`auth_required`); `cli.py` chrome flags + `login` verb-intercept + `_validate_usage`
(env fallback, auth⇒engine chrome, missing-file→`BadInput`, `--chrome-* ⊥ --search`).

**`/vdd-multi` (PASS, no 🔴/🔥):** folded L-1 (auth+search reject), P-1 (chrome `--max-bytes`),
INFO-1 (umask-0600 mint), L-2 (dead `is_login_wall` param dropped; R5c 3rd signal deferred),
L-3/INFO-3 (stale docstrings/refs), L-4 (unused guard param). Scanner's 2 "Bearer Token CWE-798"
CRITICALs confirmed **false positives** (env-sourced header + dummy test fixture).

**Honest-scope (KNOWN_ISSUES HTML2MD-10):** auth replays a **human-minted** session (no
password/2FA automation); `--max-bytes` cap is post-render (Chromium in-render DOM uncapped);
login-wall heuristic is best-effort/per-site; R5c selector-absent signal deferred. R5 (Hermes
deploy) documented & headless-ready but **not live-tested** per the user's instruction.
