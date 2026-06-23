# Plan Review — PLAN 023 (`html2md` remote-reader fallback + search)

- **Date:** 2026-06-23
- **Reviewer:** Orchestrator-as-Plan-Reviewer (sequential role-switch fallback —
  independent `plan-reviewer` subagent blocked by a persistent platform 529 at review time;
  rerun when subagent capacity returns).
- **Checklist:** `plan-review-checklist`.
- **Status (rev 1):** APPROVED WITH COMMENTS → **Status (rev 2, after fix): APPROVED**.
- **has_critical_issues:** false

## General assessment

PLAN 023 decomposes TASK 023 into a sound Stub-First chain (023-01 STUB → 023-02…06 LOGIC
→ 023-07 INTEGRATION) with correct dependency ordering (provider → ladder → privacy →
extraction → search → docs), a complete RTM→bead map and a UC→bead coverage table, and
concrete per-bead task files (paths, signatures, RTM-tagged acceptance). `tdd-strict` is
called out for the security-critical beads (023-03/04). One integration gap (P-1) was
found and fixed; otherwise the plan is buildable on the real `acquire.py`/`cli.py`.

## 🔴 CRITICAL
_None._

## 🟡 MAJOR (resolved in rev 2)

- **P-1 — search emit must reuse a full per-input convert, not bare `emit()`.** 023-06
  originally said "loop `emit` per result", but `emit()` expects a `cleaned` result and a
  *links*-shape search result is `content_kind=="html"` (needs the full clean→turndown→emit)
  while a *combined* result is `content_kind=="markdown"` (023-05 bypass). **Fix applied:**
  023-06 now refactors `convert()` to extract `_convert_one(acq, args, output_dir, …,
  query=None)` shared by the single-input path and the search loop; added 023-05 to 023-06's
  predecessors.

## 🟢 MINOR (noted, no change required)

- **P-2 — 023-03 is the heaviest bead** (tier-order + fall-through + classification +
  terminal-error + `tried` trace + `_fetch_remote_html`, 8 TCs). It is cohesive ("the
  ladder") and mirrors the multi-TC granularity of the shipped 022 beads, so it stays one
  bead — but if it balloons during implementation, split classification (`_TierUnavailable`
  mapping) from orchestration.
- **P-3 — interim `--engine jina` integrity.** Verified the ordering keeps `--engine jina`
  working between 023-02 (refactor `_fetch_jina_html` into a provider, old `_acquire_url`
  still calls it) and 023-03 (rewrites `_acquire_url`). No transient breakage. TC-02-05 guards it.

## Verified explicitly

- **Coverage:** UC-1…6 each → ≥1 bead (table present); RTM R1–R9 → beads; R10 justified as
  no-bead (deferred). ✓
- **Fork-free:** every bead edits only owned files (`acquire.py`/`cli.py`/`model.py`/
  `emit.py`/html2md tests/`SKILL.md`/`references/`); none are in the G-1/G-2 gate
  (`scripts/tests/test_e2e.sh` diffs only `web_clean/*`, `html2md_core.js`, `_errors.py`,
  `_venv_bootstrap.py`). 023-07 asserts it. ✓
- **No new dependency:** provider/search layers are plain `httpx` via `_http_get_bytes`;
  023-07 asserts `requirements.txt` unchanged. ✓
- **Naming/structure:** all seven files are `task-023-0N-slug.md` with Goal/Changes/Test
  Cases/Acceptance(RTM-tagged). ✓

## Final recommendation

**PROCEED to /vdd-develop (023-01 first).** Plan approved (P-1 folded in). Recommend
running 023-03 and 023-04 under `tdd-strict` (failing security/all-fail tests first).

---

## Independent rerun (2026-06-23, platform recovered)

The independent `plan-reviewer` subagent ran: **APPROVED WITH COMMENTS**,
`has_critical_issues: false`. It confirmed the P-1 fix landed (023-06 `_convert_one` +
023-05 predecessor), Stub-First ordering, full UC/RTM coverage, and the fork-free claim
against `test_e2e.sh`. Two 🟡 + minors raised, **folded into rev 2**:
- **M-1** `--rate-limit` bypassed on the search path (`run_search`→`_acquire_url` never
  hits `acquire()` where `_RATE_LIMITER` is set) → 023-06 now sets the limiter in
  `run_search` (TC-06-09);
- **M-2** `--search` OUTPUT_DIR/stdout resolution unspecified (`_resolve_paths` raises when
  INPUT is None) → 023-01 adds a `--search`-aware path resolution (TC-01-09);
- minors: 023-03 split pre-authorized in Notes; `tried` entries carry no URL (023-03);
  parser-surface tests extend `test_surface.py` (023-01).
**Net: APPROVED.**
