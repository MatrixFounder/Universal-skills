# Task Review — TASK 023 (`html2md` remote-reader fallback + search)

- **Date:** 2026-06-23
- **Reviewer:** Orchestrator-as-Task-Reviewer (sequential role-switch fallback —
  independent `task-reviewer` subagent blocked by a platform 529/classifier outage at
  review time; rerun when infra recovers).
- **Checklist:** `task-review-checklist`.
- **Status (rev 1):** APPROVED WITH COMMENTS → **Status (rev 2, after fixes): APPROVED**.
- **has_critical_issues:** false

## General assessment

The spec delivers the user's two hard requirements — (1) a Jina outage can no longer kill
the run (bidirectional fallback ladder, R1; one typed error only when all tiers exhausted,
AC-R1) and (2) the remote tier is genuinely vendor-agnostic (R2, configurable/self-hosted
providers). Web search (R9) was correctly folded in after the user pulled it into scope,
reusing the same fallback discipline. RTM is granular and traceable (R1–R10 → UC-1…6 →
AC-R1…R9). No 🔴 blocking issues. Five 🟡/🟢 comments were raised and **all addressed in
rev 2**.

## 🔴 CRITICAL
_None._

## 🟡 MAJOR (all resolved in rev 2)

- **T-1 — `EngineNotInstalled` must fall through in `auto`.** The classification (R3) did
  not say what happens when the `auto`/remote-first ladder reaches `chrome` but Playwright
  is absent. If treated as terminal (exit 3) it would defeat the fallback.
  **Fix applied:** R3(f) — `EngineNotInstalled` is a fall-through trigger as an
  auto/remote-first fallback, but stays terminal exit 3 for an **explicit** `--engine
  chrome`. Mirrored in ARCH §15.2/§15.4.
- **T-2 — provider-terminal ≠ tier-terminal.** Original R3(c) said a reader-reported
  target 403/404 was "terminal … not retried across providers" — ambiguous about whether
  the local `chrome` tier may still be tried, and silent on the fact that a **local** lite
  403 must *escalate* (the core recovery case). **Fix applied:** R3(c)+(d) now distinguish
  a local-tier 403 (escalate to remote) from a reader-reported target block (terminal
  across remaining remote *providers*, but `auto` may still try the `chrome` *tier*).
- **T-3 — preserve existing lite logic.** The ladder must wrap, not replace, the existing
  proactive site-variant rewrites (arXiv/Wikipedia/HackerNoon) and the `_looks_substantial`
  JS-shell escalation. **Fix applied:** R1(a) now states the ladder *wraps* and preserves
  them.

## 🟢 MINOR (resolved)

- **T-4 — engine-enum subset.** R6(a) listed a subset of the ARCH §15.5 engine values.
  **Fix applied:** R6(a) now includes `lite+restapi`/`lite+nojs`.
- **T-5 — latency bound.** No non-functional note on ladder latency. **Fix applied:** D-H
  — each tier bounded by the existing per-request timeout; worst-case = Σ tiers (serial v1).

## Verified explicitly

- **Fork-free claim holds** — `acquire.py`/`cli.py` are html2md-owned and absent from the
  G-1/G-2 gate (`scripts/tests/test_e2e.sh` only diffs `web_clean/*.py`, `html2md_core.js`,
  `_errors.py`, `_venv_bootstrap.py`). No master is touched ⇒ AC-R8 holds by construction.
- **No new dependency** — provider layer is plain `httpx` via `_http_get_bytes` (existing
  base dep).
- **Acceptance criteria are testable** via the `acquire._http_get_bytes` monkeypatch seam
  (the existing offline test idiom).

## Final recommendation

**PROCEED to /vdd-plan.** TASK 023 is approved (comments folded in). The architecture
(§15) is consistent with the revised TASK.

---

## Independent rerun (2026-06-23, platform recovered)

The independent `task-reviewer` subagent ran on rev 2: **APPROVED WITH COMMENTS**,
`has_critical_issues: false`. It confirmed both hard requirements verifiably and the
fork-free claim, and independently re-confirmed the five self-review fixes (T-1…T-5)
landed. Four MINOR nits were raised and **folded into rev 3**:
- per-provider auth envs are not interchangeable (jina→`JINA_API_KEY`,
  generic→`HTML2MD_READER_TOKEN`) → R2(e); `--engine remote` no-config = exit 2 → R2(f);
- search empty-result exits 0 + stderr (not 11); `--max-results` ≥ 1 (≤0 → exit 2) → AC-R9;
- R10 intentionally has no AC (cosmetic, no change).
**Net: APPROVED.**
