# Plan Review — TASK 014 (pdf-7: PDF outline / TOC bookmarks)

**Date:** 2026-05-22
**Reviewer:** Plan Reviewer (subagent)
**Status:** ✅ **APPROVED WITH COMMENTS**
**Plan file:** `docs/PLAN.md` (DRAFT v1)
**TASK file:** `docs/TASK.md` (TASK 014, RTM R1–R9, 3 Epics, UC-1..UC-3)
**Architecture:** `docs/ARCHITECTURE.md` (DRAFT v1, D1–D8)

## General Assessment

A tight, well-decomposed plan for an Effort-S task. It correctly translates the
ARCH §11 architect handoff into 3 strictly-linear, Epic-aligned tasks, each with
a concrete artifact cluster, exact change sites, explicit verification commands,
and an Acceptance Criteria checklist. Every load-bearing codebase claim in the
task files was independently re-verified and is accurate:

- `chrome_engine.py:717–724` `page.pdf()` genuinely lacks `outline=True`.
- `requirements-chrome.txt:16` pins `playwright>=1.40,<2.0`.
- `install.sh:107` is `pip install --quiet -r requirements-chrome.txt` — no
  `--upgrade`.
- `mermaid_renders` soft-skip, `ok`/`nok`/`skip` helpers, `$PY`/`$TMP`,
  inline-heredoc fixtures, `pypdf` `PdfReader` usage, and the `q-2 visual
  regression` anchor block — all real.
- `_acroform_fixture.py` is the cited test-only-helper peer.

RTM coverage is complete and unambiguous (all R1–R9 → exactly one completing
bead, no orphan, no split). Use Case coverage complete (UC-1→014-01,
UC-2→014-02, UC-3→014-01+014-03). Stub-First test-first adaptation is legitimate
and faithfully documented; the 014-02 Red→Green gate is real. Atomicity sound;
dependencies `014-01 → 014-02 → 014-03` correct and stated. Internal consistency
with TASK + ARCHITECTURE holds; §0.4 locked decisions match ARCH D1–D8.

**No CRITICAL issues.**

## 🔴 Critical Issues

None.

## 🟡 Major Comments

**M-1 — `_outline_probe.py` usage exit code contradicts the helper it claims
to mirror.** Task 014-01 instructs `_outline_probe.py` to exit **2** on a wrong
arg count and says this "mirrors `_acroform_fixture.py`" — but
`_acroform_fixture.py` exits **1** (`sys.exit(1)`, line 40). Not a functional
defect (the suite always calls the probe with one argument), but an inaccurate
"mirrors X" claim.
**Fix:** drop the inaccurate cross-reference; keep exit 2 (the conventional
argparse usage-error code) as a free choice.

**M-2 — 014-02 `page.pdf()` snippet silently reorders the call's keyword
arguments.** The real call order is `path, format, print_background, scale,
margin`; the 014-02 (and ARCH §5.2) snippet inserts `outline=True` *between*
`print_background` and `scale`. Behaviourally inert (kwargs), but it muddies the
"add **one** keyword argument" intent and produces a diff that also moves
`scale`/`margin`.
**Fix:** append `outline=True` **after `margin`**, leaving the existing five
arguments in place; add an explicit "do not reorder" instruction.

## 🟢 Minor Comments

- **m-1** — Backlog line offsets (~214/613/689/720) are correctly hedged with a
  "grep, do not trust offsets" instruction. Fine as-is.
- **m-2** — The `test_e2e.sh` section placement in 014-01 ("after html2pdf
  coverage, before q-2") has ~150 lines of latitude; pin it to "immediately
  before the `# --- q-2: visual regression` comment" for precision.
- **m-3** — 014-02's conditional "adjust the install.sh comment if it claims
  plain idempotence" is harmless — the actual comment refers to `playwright
  install chromium`, not the pip line, so nothing needs changing.
- **m-4** — Cosmetic: PLAN §6 could note M-1/M-2 were applied, for traceability.

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to the Development phase.** Complete,
internally consistent, accurately grounded, fully traceable. The two MAJOR
comments are accuracy/honesty refinements, not functional blockers. No
re-review required.

```json
{"review_file": "docs/reviews/plan-014-review.md", "has_critical_issues": false}
```

---

## Revision log

**2026-05-22 — Planner revision pass (post-review):** both MAJOR + the m-2
minor applied:
- **M-1** → 014-01: the `_outline_probe.py` usage-error parenthetical changed
  from "(mirrors `_acroform_fixture.py`)" to "(conventional argparse
  usage-error code)"; exit 2 retained.
- **M-2** → 014-02: the `page.pdf()` snippet now appends `outline=True` **after
  `margin`** (existing five args unchanged in order); an explicit "append last,
  do not reorder" instruction added. `docs/ARCHITECTURE.md` §5.2 snippet synced
  to the same order for PLAN↔ARCH consistency.
- **m-2** → 014-01: `test_e2e.sh` section placement pinned to "immediately
  before the `# --- q-2: visual regression` comment".

No re-review required (no CRITICAL issues; changes are spec refinements).
Status remains APPROVED → Development phase may proceed.
