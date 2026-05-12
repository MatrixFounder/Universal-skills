# Task-006 (docx-6 / `docx_replace.py`) — Architecture Review Round 1

**Reviewer:** `architecture-reviewer` subagent (read-only).
**Subject:** `docs/ARCHITECTURE.md` (DRAFT v1, written by `architect` subagent).
**Date:** 2026-05-11.
**Verdict:** **APPROVED**. No CRIT findings; 2 MAJ + 4 MIN + 3 NIT items
applied as inline polish (reviewer explicitly stated the MAJ items are
clarifications, not blockers).

---

## Findings & fixes applied

| Sev | ID | Issue | Fix landed |
|-----|----|-------|------------|
| MAJ | M1 | Pipeline order in §7 listed `--unpacked-dir` skip AFTER cross-3/cross-7, but UC-4 §2.4.3 declares them skipped in library mode. | F7 `_run` pipeline rewritten in `docs/ARCHITECTURE.md` (the 10-step block) to dispatch library mode FIRST, then cross-7, then cross-3+cross-4, then unpack. Steps 7–8 (pack + post-validate) explicitly marked "zip-mode only — library mode skips". |
| MAJ | M2 | Sub-task 006-01 "Skeleton + extraction" conflated byte-identical refactor with new failing test stubs — would muddy the G4 gate. | Atomic-chain table split: **006-01a** = `docx_anchor.py` extraction + import refactor (all-green, no test stubs); **006-01b** = test scaffolding (Stub-First Red state, explicit `unittest.skip()`); old 006-02 renumbered to "Test scaffolding green". Chain now has 10 sub-tasks instead of 9. |
| MIN | m1 | "Eleven `diff -q` checks silent" label vs the actual count of 12 in `CLAUDE.md` §2 not reconciled into Planner handoff. | 006-09 row updated to "**11 (actual count 12, see §9 NIT n1 reconciliation handoff)** `diff -q` checks silent — Planner reconciles the label in DoD checklist before merge." |
| MIN | m2 | A4 TOCTOU honest-scope item had no regression-lock test cell. | `test_docx_replace.py` description gained an A4 TOCTOU symlink-race acceptance test (catches resolve→open same-path even with target rewrite). |
| MIN | m3 | F2 part-walker enumeration source ambiguous (Content_Types vs glob). | F2 description rewritten: authoritative source = `[Content_Types].xml` `<Override PartName="...">` entries with WordprocessingML content-types; filesystem glob is fallback only when Content_Types missing/malformed. Matches TASK R5.f. |
| MIN | m4 | `_concat_paragraph_text` Q-U1 default behaviour (match through `<w:ins>`, ignore `<w:del>`) not pinned to a regression-lock test. | `test_docx_replace.py` test list gained Q-U1 default behaviour lock entry. |
| NIT | n1 | F1+F2+F8 LOC budget tight after `_actions.py` extraction. | Cosmetic; left as-is — the conservatism is intentional. |
| NIT | n2 | `docx_anchor.py` per-function LOC breakdown not given. | Cosmetic; left as-is — module is ≤ 180 LOC and the function list in §3.2 + §3.3 already enumerates each function. |
| NIT | n3 | R1.g `xml:space="preserve"` set-when-needed lacks an explicit test cell. | `test_docx_replace.py` test list gained an explicit R1.g entry. |

---

## Resulting ARCHITECTURE.md status

**DRAFT v2** — Planning phase unblocked. All Q-A1–Q-A5 closed; all
TASK §8 A1–A5 handoff constraints respected; cross-skill replication
boundary preserved; no new external dependencies; atomic-chain skeleton
now has 10 sub-tasks (split of 006-01 → 006-01a + 006-01b + 006-02
green).

## Trace

- Round-1 review timestamp: 2026-05-11 (during `/vdd-start-feature` workflow).
- Round-1 reviewer agent id (transient): `ac10da9b71a04932a` (read-only).
- Architect (round-1 author) agent id (transient): `ac4d2992e961fa091`.
- Architect-side fixes: this file's "Fix landed" column documents the
  exact edits applied to `docs/ARCHITECTURE.md`.
