# Task 024-02 [LOGIC]: Chrome SSRF hardening (prerequisite for auth)

> **Predecessor:** 024-01 (surface + stubs + RED).
> **RTM:** [R1] Chrome SSRF hardening, [R7] security. **Methodology:** `tdd-strict` (write the
> refusal tests FIRST — this gate is what makes attaching credentials safe).
> **ARCH:** §16.1 (the gate), §10 (inherited residuals).

## Use Case Connection
- Hardens UC-1/UC-2 (authed render must not exfiltrate the session). MUST land before 024-03.

## Task Goal
Make the Chrome tier SSRF-safe so credentials can be attached in 024-03 without turning a render
into a cred-exfil vector. All guards installed **before `page.goto`**, at the **context** level.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py` — `_fetch_chrome_html(url, opts)`
- **Pre-goto:** `_assert_public_http(url)` (reuse the existing lite-path gate).
- **Context-level guards installed BEFORE `goto`** (so popups/workers + the first request are
  covered — no TOCTOU): build a `browser.new_context(...)` (or `launch_persistent_context`) and
  register on the **context**:
  - `context.route("**/*", handler)` — abort any request (sub-resource, JS `fetch`,
    `sendBeacon`, navigation) whose host fails `_host_is_public` → `route.abort()`.
  - a main-frame navigation host-gate (via the route handler on `request.is_navigation_request()`
    or `page.on("framenavigated")`) refusing a redirect to a non-public host.
- **Off-target public-redirect refusal:** after load, assert the **final landed origin**
  (`page.url` eTLD+1) **== the requested target's eTLD+1**; otherwise raise
  `FetchFailed(kind="offsite_redirect")` and do NOT snapshot — a session must never be carried to
  a different public site.
- Keep `page.goto(url, wait_until="load", timeout=30000)` + `page.content()`.
- **Honest-scope (docstring):** DNS-rebind TOCTOU inherited from §10 (resolve-then-connect);
  `storage_state` localStorage is origin-restored; not full beacon isolation — egress-sandbox
  advice stands.
- **R10:** when `opts` carries no auth, behaviour is the prior bare render **plus** these gates
  (the gates are a pure safety add; a normal public page still renders unchanged).

## Test Cases
### Unit (Playwright seam mocked — fake page/context recording routes + nav)
1. **TC-02-01 (`tdd-strict`, write first)** target/redirect → `127.0.0.1` / `169.254.169.254`
   refused **on the first request** (guard active pre-goto) → `FetchFailed` (not a render).
2. **TC-02-02 (`tdd-strict`, write first)** off-target **public** redirect
   (`example.com`→`evil-public.com`) → `FetchFailed kind=offsite_redirect`, no snapshot.
3. **TC-02-03** a non-public **sub-resource**/`fetch` request is `route.abort()`ed while the
   main public page still renders.
4. **TC-02-04 (R10)** a normal public page with no auth renders identically (gates are inert).
### Regression
- Full suite; the existing auto-ladder chrome-tier tests still pass (gate is additive).

## Acceptance Criteria
- [ ] **[R1]** private + off-target-public redirects refused on the first request (guards before goto, context-level).
- [ ] **[R1]** non-public sub-resource/beacon requests aborted; main public page renders.
- [ ] **[R7]** honest-scope residuals (DNS-rebind, localStorage) documented in the docstring.
- [ ] **[R10]** no-auth public render unchanged.
- [ ] No gated master touched.

## Notes
- `tdd-strict`: TC-02-01 + TC-02-02 FIRST — they encode the exact exfil edges (private host AND
  off-target public host) that auth attachment must not reopen.
- Adversarial roast focus: a guard registered AFTER goto (first-request TOCTOU); a redirect chain
  that lands off-target but same final scheme; `route` on page vs context (popups bypass).
