# Task Review — TASK 024 (`html2md` authenticated Chrome, server/Hermes-deployable)

- **Date:** 2026-06-23
- **Reviewer:** independent `task-reviewer` subagent.
- **Checklist:** `task-review-checklist`.
- **Status:** APPROVED WITH COMMENTS → **APPROVED** (comments folded into rev 2).
- **has_critical_issues:** false

## General assessment
Strong, security-literate spec that encodes the user's intent (authed render of X-style JS+login
pages, headless on a remote/Hermes server, with a worked-out Jina-key strategy). The standout
correct decision: Chrome SSRF-hardening (R1) as a **hard prerequisite gated before** credential
attachment (D-A, bead 024-02 < 024-03), verified against the real `_fetch_chrome_html` (bare
`launch+goto`, no `_assert_public_http`). RTM granular, every requirement → UC → binary AC,
deferrals justified, fork-free claim accurate. No 🔴.

## 🟡 MAJOR — all resolved in rev 2
- **TR-1 "enforce 0600" overclaim vs the cited pattern** (transcript-fetcher rejects only *world*
  bits; group-readable `0640`/`0660` passes — a real leak on a multi-tenant Hermes box). **Fixed:**
  R7(a)/AC-R7 + ARCH §16.8 now reject `st_mode & 0o077` (group+world), flagged as an intentional
  divergence from the source pattern.
- **TR-2 cookie host-scoping has no enforcement point on the Playwright path** (the urllib
  `_RestrictedRedirectHandler` doesn't carry over). **Fixed:** AC-R7/§16.1/§16.8 now attribute
  cookie scoping to the browser's native cookie-domain matching **+** the new final-origin gate.
- **TR-3 stale-session login-wall heuristic unspecified yet load-bearing for Hermes.** **Fixed:**
  R5(c)/§16.5 name the signal class (redirect-to-/login · marker needle · target-selector absent)
  + best-effort/per-site honest-scope.
- **TR-4 Q4 (Hermes secret transport) open under a ✅-MVP requirement.** **Fixed:** Q4 RESOLVED —
  the skill's contract terminates at "read a 0600 file at an env/flag path"; the secret store is
  Hermes-owned, out of skill scope → does not block MVP.

## 🟢 MINOR — folded
- R2(e): an auth flag now **sets the effective engine to chrome** (bypasses lite/remote) — stated
  in §16.2. · AC-R4 pins concrete defaults (8 passes / 60 s). · Cross-ref to the S-1 mirror
  invariant (creds never propagate to remote/jina on fall-through).

## Verified
Non-contradiction with real code (`_fetch_chrome_html`, `_fetch_kind` 401/407, `_tier_chrome`
carries `opts`), ARCH §16 consistency, fork-free (acquire/cli/new modules ungated), R9 deferrals
sound. Plus the **user's R10 graceful-degradation** requirement added post-review (no keys / no
chrome session → byte-for-byte TASK 023, no crash).

## Recommendation
**PROCEED to /vdd-plan.** Approved with comments folded.
