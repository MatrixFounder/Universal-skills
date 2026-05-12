# Task-006 (docx-6 / `docx_replace.py`) — Task Review Round 1

**Reviewer:** `task-reviewer` subagent (read-only).
**Subject:** `docs/TASK.md` (DRAFT v1).
**Date:** 2026-05-11.
**Verdict:** **APPROVED_WITH_COMMENTS**. No CRIT findings; 3 MAJ + 4
MIN/NIT items requested for inline polish before Architecture phase.

---

## Findings (per reviewer)

| Sev | ID | Site | Issue | Fix landed |
|-----|----|------|-------|------------|
| MAJ | M1 | `docs/TASK.md` §2.4 (UC-4) + §5 RTM R8.g | UC-4 `--unpacked-dir` library mode is NOT in the backlog row docx-6 — scope creep. | Added scope note above §2.4.1 marking UC-4 as Architect-discretionary; RTM R8.g flipped to MVP=No. |
| MAJ | M2 | `docs/TASK.md` §3.3 + R9.a | Env-var `XLSX_DOCX_REPLACE_POST_VALIDATE` wrong-skill-prefixed (script lives under docx/). | Renamed to `DOCX_REPLACE_POST_VALIDATE`; review-deferment sentence dropped. |
| MAJ | M3 | `docs/TASK.md` R10.b vs §2.2.4 Alt-6 | R10.b asserted "no `word/media/` parts in output"; Alt-6 said "warn-and-proceed." Test would fail any inserted image even when Alt-6 says we warn-and-proceed. | R10.b reworded to "stderr warning emitted AND inserted `<w:p>` contains no live `r:embed` (refs stripped or text-only fallback)" — consistent with Alt-6. |
| MIN | m1 | `docs/TASK.md` §3.4 / §7 / §11.x | §11.x referenced 4+ times but no §11 existed. | Inserted §9 "Honest-Scope Catalogue" enumerating §11.1–§11.4 as stable aliases; References renumbered to §10. |
| MIN | m2 | `docs/TASK.md` §1.2 vs Q-A2 | §1.2 committed to refactor; Q-A2 left timing open. | §1.2 softened to "candidate refactor … contingent on Q-A2"; mirrors Q-A2 wording. |
| MIN | m3 | `docs/TASK.md` §0 Effort | Effort estimate informal — backlog says "M". | Prefixed "M (per backlog row docx-6)" in §0. |
| MIN | m4 | `docs/TASK.md` R8 | `.docm` output-extension behaviour undocumented. | Added R8.k — output extension preserved verbatim; macro warning covers lossy case. |
| NIT | n1 | `docs/TASK.md` G6 ("eleven diff -q") | Cosmetic — counter to verify in Planning. | Left as-is; planner will reconcile. |
| NIT | n2 | Cross-cutting parity duplication | Listed both in §0 and inside R7. | Left as-is — §0 is a callout, R7 is the gate. |

---

## Resulting TASK.md status

**DRAFT v2** — Architecture phase unblocked. D1–D8 + A1–A5 unchanged.
No second-round task-review needed (all MAJ resolved; MINs polish).

## Trace

- Round-1 review timestamp: 2026-05-11 (during `/vdd-start-feature` workflow).
- Round-1 reviewer agent id (transient): `a8ebc218ea6e9c6dc` (read-only).
- Analyst-side fixes: this file's "Fix landed" column documents the
  exact edits applied to `docs/TASK.md`.
