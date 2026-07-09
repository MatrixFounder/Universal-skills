---
id: HTML2MD-10
type: known-issue
status: handled
opened_at: 2026-06-23
resolved_by: TASK 024
category: security
severity: LOW
component: html
slug: html2md-10-authenticated-chrome-honest-scope
---

# HTML2MD-10 — authenticated Chrome (login-gated) honest-scope (TASK 024)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** handled (with documented residuals) • **Severity:** LOW • **Location:**
`acquire._fetch_chrome_html` / `_chrome_auth` / `_cookies` / `acquire._login_render`.
**What shipped:** read login-gated pages (X Articles/threads, paywalled, private) by replaying a
**human-minted** session — `html login URL --save-state s.json` (headful) then
`--chrome-storage-state s.json` (also `--chrome-cookies-file` / `--chrome-user-data-dir`);
`--chrome-scroll` for lazy replies. The Chrome tier is now **SSRF-gated** (supersedes the old
[HTML2MD-4](./html2md-4-ssrf-residuals-lite-path-hardened.md) "chrome not hardened"):
`_assert_public_http` before navigation, context-level route
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
