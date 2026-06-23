# Plan Review — PLAN 024 (`html2md` authenticated Chrome, server/Hermes)

- **Date:** 2026-06-23
- **Reviewer:** independent `plan-reviewer` subagent.
- **Checklist:** `plan-review-checklist`.
- **Status:** APPROVED WITH COMMENTS → **APPROVED** (comments folded into rev 2).
- **has_critical_issues:** false

## General assessment
Sound, well-traced Stub-First decomposition that maps cleanly onto the real code (every spot-check
accurate: `_fetch_chrome_html` bare un-gated launch+goto at acquire.py:510; `_tier_chrome` carries
`opts` but calls without it → the signature change is real; transcript-fetcher loader is world-only
→ the `0o077` tightening is a genuine divergence; G-1/G-2 excludes all four 024 target files). The
load-bearing **R1-before-R2** prerequisite (024-02 before 024-03) is correctly + redundantly
encoded. No 🔴.

## 🟡 MAJOR — resolved in rev 2
- **PR-1 024-03 cookies-path depended on 024-04 (ordering inversion).** TC-03-02
  (`--chrome-cookies-file`→`add_cookies`) needs `to_playwright_cookies` from 024-04, but 024-03 is
  ordered first. **Fixed:** 024-03 + PLAN now state the `storage_state` (primary) + persistent-profile
  paths land green in 024-03; only TC-03-02 is **written RED in 024-03, greened in 024-04**
  (forward-ref) — chain stays linear.
- **PR-2 scroll wall-clock cap (60s) not frozen in the 024-01 surface bead** (only `--chrome-scroll-passes`
  was). **Fixed:** 024-01 now freezes `_CHROME_SCROLL_BUDGET_S = 60` as an internal module constant
  (deliberately not a flag) so 024-05 fills behaviour behind a frozen number.

## 🟢 MINOR — folded / noted
- `login` dispatch **hard-committed to verb-intercept** in 024-01 + PLAN (the flat `nargs="?"`
  parser would mis-parse `login URL` as `INPUT="login"`) — reviewer-confirmed the right call.
- `kind="offsite_redirect"`/`auth_required` are additive `FetchFailed.details` values (free-form) —
  documented in 024-06 SKILL.md update. · R9 no-bead + AC rollup (AC-R1…R8 + AC-R10, no AC-R9) are
  correct/cosmetic.

## Checklist verdicts (all PASS)
Use-case coverage (UC-1…5 → beads; R1–R10 mapped; R9 no-bead justified; R10 cross-cutting +
024-01 test + 024-06 assert) · Stub-First + ordering (STUB/LOGIC/INTEGRATION; R1-before-R2
load-bearing) · Task files (6, correct naming, Goal/Changes/Tests/RTM-tagged Acceptance) ·
Atomicity/buildability (each buildable on real code; verb-intercept sound; 024-02 SSRF design
testable via the Playwright seam) · `tdd-strict` on 024-02 + 024-04 with write-first tests ·
Consistency (PLAN↔tasks↔ARCH §16.10; AC↔TASK §4 incl. AC-R10; fork-free verified vs test_e2e.sh).

## Recommendation
**PROCEED to /vdd-develop (024-01 first).** Approved; comments folded. Run 024-02 (SSRF gate) and
024-04 (credential file) under `tdd-strict`.
