# Architecture Review — TASK 024 (`docs/ARCHITECTURE.md` §16)

- **Date:** 2026-06-23
- **Reviewer:** independent `architecture-reviewer` subagent.
- **Checklist:** `architecture-review-checklist` (Data Model, Security/OWASP, Scalability, YAGNI).
- **Status:** APPROVED WITH COMMENTS → **APPROVED** (comments folded into rev 2).
- **has_critical_issues:** false

## General assessment
§16 is sound, internally consistent, and buildable on the real `acquire.py` (`_tier_chrome`
already carries `opts` → the `_fetch_chrome_html(url)`→`(url, opts)` change is localized, not a
rewrite). The core security thesis — SSRF-harden the Chrome tier as a hard prerequisite (R1,
bead 024-02) before attaching any credential (R2, 024-03) — is the correct sequencing and is
right. `storage_state` (read-only-at-runtime → concurrency-safe) is the correct foundation for
the Hermes requirement; replay-only sharply narrows the attack surface. No 🔴; the SSRF model is
sufficient **as a documented best-effort boundary** once the two MAJORs are folded in.

## 🟡 MAJOR — resolved in rev 2
- **M-1 host-scoping partly aspirational with `storage_state`; the real exfil edge is an
  off-target *public* redirect + origin-restored localStorage.** **Fixed:** §16.1 adds an
  **off-target public-redirect guard** (final landed origin must == target eTLD+1 before
  snapshot), attributes cookie scoping to the browser, and adds an honest-scope line that
  `storage_state` localStorage is origin-restored (not further filtered). AC-R1 updated.
- **M-2 install-before-goto / TOCTOU not stated.** **Fixed:** §16.1 now requires all guards
  installed **before `page.goto`** at the **context level** (popups/workers; no first-request
  TOCTOU), uses `context.route` (catches JS `fetch`/`sendBeacon`), and names **DNS-rebinding
  TOCTOU as inherited from §10**. AC-R1 asserts the guard is active on the first request.

## 🟢 MINOR — folded
- m-1 `login` dispatch shape named in §16.10 (verb-in-`main` vs `add_subparsers`, pick at
  planning). · m-2 §16.8 clarifies only the file-hardening half of transcript-fetcher's
  `_cookies.py` is lifted; cookie→dict conversion is new code. · m-3 bead 024-01 RED-test list now
  includes the off-target-redirect case (+ R10 non-regression).

## Explicit confirmations
- **Fork-free: CONFIRMED** — `acquire.py`/`cli.py`/new `_cookies.py`/`_chrome_auth.py` are
  html2md-owned and absent from the G-1/G-2 gate (`test_e2e.sh`); no master touched → gate silent,
  docx G-3 byte-identical. Residual *fork-risk* (file-hardening drift vs transcript-fetcher)
  mitigated by the tracking-note requirement.
- **SSRF model: sufficient as an honestly-bounded best-effort** for attaching a human-minted
  replay session once M-1/M-2 are in (private+off-target-public redirects refused, sub-resource/
  beacon routes aborted; residuals = DNS-rebind TOCTOU + same-origin localStorage, both
  documented, egress-sandbox advice stands). Safe to attach credentials under this design.

Doc size: `ARCHITECTURE.md` ~820 lines (< 1500 → no Index-Mode split).

## Recommendation
**PROCEED to /vdd-plan.** Approved; M-1/M-2/minors folded. Plus the user's **R10
graceful-degradation** invariant (§16.2) added post-review.
