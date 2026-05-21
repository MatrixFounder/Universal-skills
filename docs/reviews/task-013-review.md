# Task Review Report — TASK 013 (pdf-to-markdown)

**Date:** 2026-05-21
**Reviewer:** Task Reviewer Agent (VDD pipeline)
**Target:** `docs/TASK.md` (TASK 013 — pdf-12)
**Status:** ✅ **APPROVED WITH COMMENTS** — no blocking issues. Analysis→Architecture gate is OPEN.

## General Assessment

TASK 013 is a high-quality, well-scoped specification. Strengths:

- **RTM is real and complete** — 13 numbered requirements across 3 Epics, every one with ≥3 sub-features, every one MVP-✅, no orphans.
- **Non-goals are first-class** (§1.2, §1.4) — actively defends against the "magic converter" anti-pattern, including the `.docx`-has-a-semantic-model contrast explaining *why* PDF gets no converter.
- **Honest scope** (§1.4 (a)–(g)) aligns with root CLAUDE.md §3 "Honest scope, not aspirational".
- **CLAUDE.md-vs-SKILL.md ambiguity correctly resolved** — verified: the pdf skill has no `CLAUDE.md`; SKILL.md §3/§7.1/§12 exist and match the TASK's quotations. Assumption A-1 is sound.
- **Factual claims verified against the repo** — `pdf_fill_form.py --check` exit codes 0/11/12 (custom-codes-≥10 precedent real); `_errors.py`/`preview.py` exist; `test_e2e.sh` is a bash harness invoking CLIs directly (R12.6 wording correct); `library-selection.md` extraction rows exist; `pdfplumber` is a declared dependency. No contradictions.
- **Use cases properly structured** and cover the common path, the silent-scan fix, and maintainer validation.

## 🔴 CRITICAL (BLOCKING)

None.

## 🟡 MAJOR

- **M-1 — Scan-detection threshold (A-4 / R8.1) left fully unpinned.** The whole feature's correctness depends on this constant; "TBD in a later phase" risks an arbitrary number with fixtures built to match it. *Fix:* require the threshold value, unit, and rationale to be documented in the helper docstring + reference, and the scan-like fixture to sit clearly (not borderline) on the scanned side.
- **M-2 — `doc_scanned` boundary case for blank pages unhandled.** A blank page is `scanned:false` (R8.1); an all-blank or blank+1-scanned document would trip `doc_scanned:true` and wrongly point the agent at OCR. *Fix:* pin the rule for blank-page documents and add an alternative scenario / test note.
- **M-3 — Encrypted-but-readable PDF (correct `--password`) untested.** R6.4/R9.3 cover the fail path; §1.4(f) says the success path is "supported" but no UC/criterion/test exercises it. *Fix:* add an R12 sub-feature + fixture/criterion for "encrypted + correct password → exit 0", or explicitly defer the `--password` success path.
- **M-4 — R12.5 exit-code matrix omits explicit exit-2 (`UsageError`) envelope assertion.** R9.3 defines codes {0,1,2,10}; the matrix should pin all four, and the exit-2 path with `--json-errors` should be asserted to yield a `type:"UsageError"` envelope. *Fix:* make R12.5 list {0,1,2,10} and add the UsageError envelope assertion.

## 🟢 MINOR

- **m-1** — Drop the self-graded "no requirement without ≥3 sub-features" sentence in §2 (adds no value, could go stale).
- **m-2** — Consider making `scanned_pages` (the list) a contract field, since the UC-2/A2 stderr warning already depends on it.
- **m-3** — Standardise on "scan-like fixture" (TASK alternates "scan-like" / "scanned").
- **m-4** — Table output dialect (GFM) appears only in a UC step; state it once in R3 if the reference recommends a dialect.

## Compatibility Check

- ✅ Honors the prompt-first stance — R13.3 correctly reconciles with SKILL.md §3 (helper is a *dump*, not a converter).
- ✅ No cross-skill replication triggered — helper imports `_errors.py` read-only; CLAUDE.md §2 protocol not triggered.
- ✅ License/dependency hygiene — no new dependency, no `THIRD_PARTY_NOTICES.md` change, proprietary `LICENSE`/`NOTICE` untouched.
- ✅ ARCHITECTURE.md xlsx-centric / thin pdf section — expected; TASK defers a small pdf section to the Architecture phase.

## Final Recommendation

**APPROVED WITH COMMENTS.** No 🔴 issues — the Analysis→Architecture gate is OPEN. The four 🟡 items are "tighten before code", not "rewrite the TASK"; they must be resolved before reaching the Developer.

```json
{"review_file": "docs/reviews/task-013-review.md", "has_critical_issues": false}
```

---

## Resolution (Analyst v2 — 2026-05-21)

All four 🟡 and the actionable 🟢 items were applied to `docs/TASK.md` immediately
after this review (before the Architecture phase), so no contract surface reaches
the Developer under-defined:

- **M-1** → R8.1 extended (sub-feature 8.1a): threshold value/unit/rationale must
  be documented in the helper docstring + reference; new acceptance criterion in
  UC-2 §3.2.6 and R11.2 require the scan-like fixture to sit clearly on the
  scanned side. New Open Question Q-3 (resolved-with-default) records the unit
  decision.
- **M-2** → R8.2 extended (sub-feature 8.2a): explicit blank-page rule —
  `doc_scanned` is true only when ≥1 page is `scanned` AND no page yields
  meaningful text; an all-blank document (0 scanned pages) is `doc_scanned:false`,
  exit 0. New UC-2 Alternative Scenario A3 (all-blank document) added.
- **M-3** → R12 sub-feature R12.7 added (encrypted fixture + correct
  `--password` → exit 0, correct dump); R11 sub-feature R11.4 added (encrypted
  fixture); UC acceptance criterion added.
- **M-4** → R12.5 reworded to assert the full {0,1,2,10} matrix; R12.3 extended
  to assert the exit-2 `type:"UsageError"` envelope under `--json-errors`.
- **m-1** → self-graded sentence removed from §2.
- **m-2** → `scanned_pages` (list) promoted to a contract field in R7.1/R7.5.
- **m-3** → standardised on "scan-like fixture" throughout.
- **m-4** → R3 sub-feature 3.7 added: the reference recommends GFM as the default
  table dialect (composition still agent judgement).

Status after resolution: **APPROVED, all comments resolved** — proceed to
Architecture phase.
