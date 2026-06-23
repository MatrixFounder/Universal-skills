# Task 024-05 [LOGIC]: scroll-to-load + stale-session detection

> **Predecessor:** 024-03 (authenticated context).
> **RTM:** [R4] scroll-to-load, [R5c] stale-session detection. **ARCH:** §16.4, §16.5.

## Use Case Connection
- UC-3 (reply threads / lazy content), UC-4 (stale/expired session).

## Task Goal
Pull lazy-loaded content (X replies/comments) via bounded scroll, and detect a logged-out render
(stale session) → `auth_required` instead of returning the login wall as content.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py` — `_fetch_chrome_html(url, opts)`
- **Scroll (R4):** when `opts.chrome_scroll`, after `goto`: loop up to `opts.chrome_scroll_passes`
  (default 8) — `window.scrollTo(0, document.body.scrollHeight)` (or `page.mouse.wheel`) +
  `page.wait_for_load_state("networkidle", timeout=…)` + small settle — bounded by a **wall-clock
  budget (default 60 s)**; then `page.content()`. Never hangs (hard cap on both passes + clock).

### File: `skills/html2md/scripts/html2md/_chrome_auth.py` — `is_login_wall(html, final_url, opts)`
- **Best-effort, per-site login-wall heuristic** (X serves a *200* wall, not a 401, so
  `_fetch_kind` alone misses it): signal class = {`final_url` redirected to a `/login`-class path ·
  a conservative known login-wall marker/needle in the body · the requested `--target-selector`
  absent from the rendered DOM}. Conservative needles (a false-negative would emit a wall).
- In `_fetch_chrome_html`: if `is_login_wall(...)` → `raise FetchFailed(kind="auth_required")`
  (never return the wall as content). Honest-scope: tuned for X first; documented as best-effort.

## Test Cases
### Unit (Playwright seam mocked)
1. **TC-05-01** `--chrome-scroll --chrome-scroll-passes 3` → 3 scroll calls; content snapshot after.
2. **TC-05-02** scroll never exceeds the wall-clock cap even if `networkidle` never settles (hard stop).
3. **TC-05-03 (R5c)** a fake login-wall render (redirect to `/login` / marker / selector-absent) →
   `FetchFailed kind=auth_required`, NOT returned as content.
4. **TC-05-04** a genuine authed render (target-selector present, no wall marker) → returned normally.
### Regression
- Full suite; no-scroll path unchanged (R10).

## Acceptance Criteria
- [ ] **[R4]** scroll bounded by passes (default 8) + wall-clock (default 60 s); never hangs.
- [ ] **[R5c]** stale-session login wall → `auth_required` (best-effort heuristic; conservative needles).
- [ ] a real authed render is not misclassified as a wall (no false positive).
- [ ] No gated master touched.

## Notes
- Adversarial roast focus: scroll hang on perpetual-beacon pages (must hit the clock cap);
  false-negative wall detection (emitting a logged-out page as content — the R5c regression);
  false-positive (a real short page misread as a wall).
