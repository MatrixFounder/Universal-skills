# Task 024-03 [LOGIC]: authenticated Chrome context (storage_state / cookies / profile)

> **Predecessor:** 024-02 (SSRF-hardened chrome tier — REQUIRED before attaching creds).
> **RTM:** [R2] authenticated context. **ARCH:** §16.2, §16.9.

## Use Case Connection
- UC-1 (clip an authed page), UC-2 (Hermes headless storage_state).

## Task Goal
Attach a human-minted session to the (now SSRF-gated) Chrome tier via one of three sources, and
ensure an auth flag forces the chrome tier so the credential is never dropped.

## Changes Description

### File: `skills/html2md/scripts/html2md/_chrome_auth.py`
- `resolve_context_kwargs(opts) -> dict | None` — exactly ONE of (mutually-exclusive, enforced in
  cli):
  - `chrome_storage_state` → `{"storage_state": <path>}` for `new_context(...)` (cookies +
    localStorage + sessionStorage).
  - `chrome_cookies_file` → load via `_cookies.load_cookie_jar` + `to_playwright_cookies` (024-04)
    → returned as `("add_cookies", [dicts])` (applied after `new_context()`).
  - `chrome_user_data_dir` → signal to use `launch_persistent_context(user_data_dir=…,
    headless=True)` (no separate browser; close the context).
  - none → `None` (anonymous render — R10).
- Missing/unreadable/malformed source → `BadInput` (typed, R10), never a traceback.

### File: `skills/html2md/scripts/html2md/acquire.py` — `_fetch_chrome_html(url, opts)`
- Build the context from `resolve_context_kwargs(opts)`: `new_context(**kwargs)` (+ `add_cookies`
  if the cookies path), or `launch_persistent_context(...)` for the profile path — **then apply
  the 024-02 guards on that context BEFORE `goto`**.
- `engine` label stays `"chrome"`; the `tried`/trace records auth as a **boolean only** (never the
  secret).

### File: `skills/html2md/scripts/html2md/cli.py`
- An auth flag/env **sets the effective engine to `chrome`** (bypass lite/remote) so the ladder
  never silently drops the credential. (Surface frozen in 024-01; wire the engine override here.)

## Test Cases
### Unit (Playwright seam mocked)
1. **TC-03-01** `--chrome-storage-state f.json` → `new_context(storage_state="f.json")` called.
2. **TC-03-02** `--chrome-cookies-file c.txt` → `add_cookies([...])` called with converted dicts.
3. **TC-03-03** `--chrome-user-data-dir d` → `launch_persistent_context(user_data_dir="d", headless=True)`.
4. **TC-03-04** two auth flags together → exit 2 (mutually exclusive).
5. **TC-03-05** an auth flag forces engine=chrome even under `--engine auto` (lite not tried).
6. **TC-03-06** the 024-02 guards are installed on the authenticated context (private redirect still refused WITH auth attached).
### Regression
- Full suite; no-auth render unchanged (R10).

## Acceptance Criteria
- [ ] **[R2]** all three auth sources build the right context; mutually exclusive.
- [ ] **[R2]** auth flag ⇒ effective engine chrome (credential never dropped to lite).
- [ ] **[R7]** auth recorded only as a boolean in the trace; secret never logged.
- [ ] **[R1]** SSRF guards apply to the authenticated context too (TC-03-06).
- [ ] No gated master touched.

## Notes
- **Ordering (no inversion):** the **storage_state** path (primary) + persistent-profile have NO
  dependency on 024-04 and land green here. The **cookies** path needs `to_playwright_cookies`
  (024-04): **TC-03-02 is written RED in this bead and greened in 024-04** (forward-reference,
  like the 024-01 RED tests) — do NOT block 024-03 on it. Requires 024-02 (gates) done.
- Adversarial roast focus: a context built WITHOUT the 024-02 guards (auth + un-gated = exfil);
  persistent-profile path leaving a browser/context unclosed; secret leaking into `engine`/trace.
