# Architecture Review — TASK 014 (pdf-7: PDF outline / TOC bookmarks)

**Date:** 2026-05-22
**Reviewer:** Architecture Reviewer (subagent)
**Status:** ✅ **APPROVED**
**Architecture file:** `docs/ARCHITECTURE.md` (DRAFT v1)
**TASK file:** `docs/TASK.md` (TASK 014, RTM R1–R9, 3 Epics)

## General Assessment

High-quality, correctly-scoped architecture for an Effort-S task. It resists
inventing structure: no new module, no data persistence, no auth model, no
process boundary — and the document says so and justifies it (§3.1, §10, D2).
Core template selection is correct; living-document discipline is honored
(~426 lines, under the 1500-line Index-Mode threshold, updated in place, not
per-task snapshotted).

Every load-bearing codebase claim was independently verified and is accurate:

- `chrome_engine.py:717–724` `page.pdf(...)` genuinely lacks `outline=True`;
  the §5.2 "after" snippet matches the real call site argument-for-argument.
- `render_chrome()` (line 547) already has 8 params — the design correctly
  declines to add a 9th (D2).
- `install.sh:107` genuinely lacks `--upgrade` (line 64 does use it for pip
  itself — D4 is a real surgical gap, not a blanket claim).
- `requirements-chrome.txt:16` pins `playwright>=1.40,<2.0` — floor bump
  accurately described; a rationale comment matches house style.
- `pypdf` is already in `requirements.txt` and already used in
  `test_e2e.sh:47–48` — "no new test dependency" is correct.
- The `mermaid_renders` soft-skip pattern and `ok`/`nok`/`skip` helpers are
  real; §5.5's soft-skip mapping is faithful.
- `emulate_media("screen")` (line 682) and `_DOM_NORMALIZE_SCRIPT` (689/705)
  are real — the §10(g)/A-6 and §10(b)/(f) caveats are grounded in code.

The Task-Reviewer's four MAJOR comments (M-1..M-4) are all correctly absorbed
into the architecture (§5.3+D4, §5.5 R6.4 probe, §10(g)+A-6, §5.5 plain-content
fixture+D8, §5.5 md2pdf no-`--no-default-css` asymmetry).

**No CRITICAL issues. No MAJOR issues.**

## Weighted findings

- **Data Model (§4) — sound.** Honestly framed: no persisted model;
  `PdfOutline`/`OutlineItem` are modelled only as the F5 test contract
  (engine-produced, not skill-constructed). §4.3 well-formedness rule is
  concrete and verifiable; assertion granularity correctly scoped to
  non-empty+nested+titled, not byte-identical cross-engine trees.
- **Security (§7) — verified, no gaps.** `outline=True` is a static boolean
  literal; offline guarantees (`_block_remote_routes`, `_strip_base_href`,
  `_strip_script_tags`) structurally untouched; weasyprint paths unedited;
  `_outline_probe.py` reads only test-produced PDFs in a private tempdir.
- **Scalability (§8) — sane.** weasyprint zero change; chrome `outline=True`
  reuses the tree Chromium already computes — negligible. No invented
  throughput target.
- **YAGNI — proportionate.** D2 (hardcode `outline=True`) is the
  YAGNI-conformant choice (Q-2: no opt-out flag). `_outline_probe.py` mirrors
  the existing `_acroform_fixture.py` peer — established pattern, not invention.
  No over-engineering.
- **Traceability — complete.** All 9 RTM requirements (R1–R9) and all 3 Use
  Cases (UC-1..UC-3) covered; sub-requirements (R6.4, R5.4, R9.3, UC-1/A2-A3,
  UC-3/A1) land. No orphan, no uncovered Use Case.
- **Internal consistency — sound.** F1–F7 consistent across §2.1/§2.2/§3.2/§3.3;
  D1–D8 coherent and each traces to a TASK Q/A; §11 bead→Epic partition clean.

## 🔴 Critical Issues

None.

## 🟡 Major Comments

None.

## 🟢 Minor Comments (non-blocking — no architecture revision required)

- **m-1** — `_outline_probe.py` exit-3 should be documented (in its docstring)
  as a private test-harness sentinel, not an `_errors.py`-style code.
  **→ Applied:** §5.4 now states this explicitly.
- **m-2** — §5.5 "skip rule: none — always runs" for the weasyprint blocks is
  true only where weasyprint's native libs (pango/cairo) are present; this
  matches the existing `md2pdf:` block's posture, so it is not a defect — flag
  for the Developer that the new blocks inherit the same environmental
  precondition. No change needed.
- **m-3** — The R6.4 `inspect.signature` capability probe should run *before*
  the chrome render so an under-floor Playwright fails on the cheap check.
  **→ Applied:** §11 bead 014-02 description now makes the ordering explicit.
- **m-4** — §2.2 ASCII dataflow diagram is slightly cramped. Pure presentation;
  no semantic ambiguity. No change.

## Final Recommendation

**APPROVED — proceed to the Planning phase.** The architecture is correct,
internally consistent, accurately grounded in the verified codebase,
proportionate to an Effort-S task, and fully traceable to all 9 RTM
requirements and all 3 Use Cases with no orphans. The four minor comments are
non-blocking; m-1 and m-3 were applied as cheap handoff polish, m-2 and m-4
need no change. No revision routing back to the architect is required. The §11
atomic-chain skeleton is a clean handoff: 3 strictly-linear beads, Epic-aligned.

```json
{"review_file": "docs/reviews/architecture-014-review.md", "has_critical_issues": false}
```
