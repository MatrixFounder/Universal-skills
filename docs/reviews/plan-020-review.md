# Plan Review — TASK 020 (`pptx2md`, pptx → Markdown converter)

- **Date:** 2026-06-08
- **Reviewer:** plan-reviewer (independent VDD gate, Planning→Execution boundary)
- **Target:** `docs/PLAN.md` (TASK 020, 6 beads) + `docs/tasks/task-020-0{1..6}-*.md`
- **Against:** `docs/TASK.md` (RTM + UC-1..UC-5), `docs/ARCHITECTURE.md`
- **Status:** **APPROVED WITH COMMENTS** (no BLOCKING; 2 MAJOR; 4 MINOR)

> Persisted by the orchestrator on behalf of the read-only `plan-reviewer` subagent.
> All 2 MAJOR + 4 MINOR were folded into the beads after this review.

## General Assessment

Mature, well-traced plan. The Stub-First split is real (020-01 freezes the surface +
RED tests on stubs; 020-04 removes `_STUB_SENTINEL` and tightens assertions);
dependency order is correct; every RTM id and Use Case is covered; the architecture's
resolved findings (AR-1, AR-3, AR-9, MAJOR-1/3/4, the §9 `diff -q` gate) are genuinely
carried into the beads — verified against the live codebase. No blocking issues.

## Use-Case Coverage
| UC | Beads | Verdict |
|----|-------|---------|
| UC-1 | 020-01/02/03/04/06 | COVERED |
| UC-2 | 020-01/05/06 | COVERED |
| UC-3 | 020-01/02 | COVERED |
| UC-4 | 020-05 | COVERED |
| UC-5 | 020-02/04 | COVERED |

## RTM Coverage
All 21 ids (R-A1..A5, R-B1..B3, R-C1..C5, R-D1..D4, R-E1..E4) present in the PLAN
RTM→Task table and traced into bead checklists with `[ID]` prefixes. No gap.

## Stub-First Verification
Real, not cosmetic. 020-01 STUB (NotImplementedError + sentinel + real guards/`--help`)
precedes the LOGIC beads; 020-02/03/04 tighten the 020-01 assertions per §2.4; the
frozen surface is internally consistent with ARCH §4/§5.1 and the live `xlsx2md`
precedent; the `_venv_bootstrap.reexec_into_venv(requires=("pptx",))` prelude is grounded.

## Atomicity / Dependencies
All beads 2–4h, single-test-verifiable. 020-04 (emit+cli, MVP gate) bundling is
justified (emit has no observable behaviour without the CLI; MVP needs both). Order
`01→02→03→04→05→06` is logical; 020-06 depends on 020-04 (MVP) + 020-05 (OCR dogfood).

## 🔴 CRITICAL (BLOCKING)
None.

## 🟡 MAJOR

- **MAJOR-A — Missing `scripts/tests/__init__.py`.** `skills/pptx/scripts/tests/`
  holds only `test_e2e.sh` (bash) and is **not** a Python package (no `__init__.py`),
  unlike `skills/xlsx/scripts/tests/`. The PLAN global gate
  `python -m unittest discover -s tests` will not reliably collect the new
  `test_pptx2md_e2e.py`. **Fix:** add `scripts/tests/__init__.py` to 020-01 New Files.
  *(Folded into 020-01.)*
- **MAJOR-B — `safe_image_meta` cross-bead ownership ambiguity.** 020-02 hedges
  ("keep in a shared helper if cleaner — coordinate with 020-03") while 020-03 owns it
  REAL — an ordering inversion (020-02 precedes 020-03). **Fix:** promote
  `images.safe_image_meta(shape)` to a **REAL** helper created in **020-01** (it is
  pure, ~6 lines); 020-02 and 020-03 both consume it; drop the hedge.
  *(Folded: helper moved to 020-01; 020-02/03 consume it.)*

## 🟢 MINOR
- **MINOR-1 — PLAN RTM table R-C5 cell** should read `020-05/06` (matches the prose).
  *(Folded.)*
- **MINOR-2 — `--ocr-timeout` type drift** (int/float vs float). Pick `float`.
  *(Folded: 020-01 says `type=float, default 120`.)*
- **MINOR-3 — `convert` vs xlsx's `convert_xlsx_to_md`** — add a one-line note that
  pptx intentionally names its API `convert`. *(Folded into 020-01.)*
- **MINOR-4 — guard the `slodes-3` [sic] path** in the 020-06 dogfood loop
  (`test -f tmp8/slodes-3.pptx`) so an autocorrect to `slides-3` fails loudly.
  *(Folded into 020-06.)*

## Final Decision
**APPROVED WITH COMMENTS.** Full RTM/UC coverage, real Stub-First, AR/MAJOR fixes
carried. The 2 MAJOR + 4 MINOR are small/mechanical, do not change bead boundaries,
and were folded back by the planner. Proceed to Development (`/vdd-develop`).

```json
{"review_file":"docs/reviews/plan-020-review.md","has_critical_issues":false,"major_count":2,"minor_count":4,"summary":"APPROVED WITH COMMENTS — full coverage, real Stub-First, AR/MAJOR fixes carried; 2 MAJOR (tests/__init__.py; safe_image_meta ownership) + 4 MINOR folded into beads."}
```
