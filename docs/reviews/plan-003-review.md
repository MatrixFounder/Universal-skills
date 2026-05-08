# Plan Review — Task 003 (xlsx-7 / `xlsx_check_rules.py`)

**Date:** 2026-05-08
**Reviewer:** Plan Reviewer (subagent)
**Target:** `docs/PLAN.md` + 17 task files at `docs/tasks/task-003-{01..17}-*.md`
**Status:** **APPROVED WITH COMMENTS** — no blockers. 0 CRITICAL, 4 MAJOR, 6 MINOR.

## General Assessment

The plan is unusually well-built for a 17-task greenfield chain. Stub-First phasing (003.01–04 red / 003.05–15 implementation / 003.16–17 cross-skill+docs) is canonically correct: a NEW system done in TDD form, not retrofit. RTM coverage is exhaustive and explicit (every R-letter sub-feature is mapped to exactly one PLAN row, with the few legitimately split items annotated with both task IDs). Architect-locked invariants (M-1 dual-stream, M-2 main-thread `_partial_flush`, M2 envelope all-three-keys) all have named tests in named tasks with assertion structures that would catch real regressions. CLAUDE.md §2 4-skill replication boundary is honoured. D1–D6 traceability is consistent. The execution discipline section is the right kind of paranoid.

Real items below are atomicity outliers and one xfail-discipline gap. Nothing blocks the Developer.

## Use Case → Task Mapping (Spot-Check)

PLAN §"Use Case Coverage" verified: I1.1→003.09, I1.2→003.10, I2.1→003.07, I2.2→003.08, I3.1–I3.7→003.10/11/12, I4.1→003.13, I4.3→003.14, I6.3→003.15, I8.2→003.16, I9.4→003.17 all match the task bodies. RTM spot-checks: R3.f → 003.08 has `test_merged_data_cell_anchor_resolution` ✓; R4.e → 003.12 has cache+text-skip tests ✓; R5.f → 003.13 `apply_max_findings` impl + `test_max_findings_appends_synthetic` ✓.

## Findings

### 🟡 MAJOR

**M-1. Task 003.04 is overweight (42 manifests + generator + 3 sub-manifests + README + xlsx-6 regression check).** Realistic effort 6–8 h, not 2–4. **Proposed split:** 003.04a (manifest schema + generator plumbing + 10 happy-path manifests #1–#9 + #10b); 003.04b (adversarial + cross-sheet + output manifests #11–#21, #22–#28, #29–#30, #32a/b/c, #34–#37, #39/#39a/#39b — same raw-bytes write pattern). 003.04b can run parallel to 003.05.

**M-2. Task 003.14 (`cli.py`) is at the LOC ceiling and mixes 22 flags + watchdog + cross-3/4/5/7 + 16 unit tests in one task.** Acceptance Criteria already says "if you exceed, factor out…". Architect M-3 already flagged the 500-LOC overrun. **Proposed split:** 003.14a (argparse builder + mutex/dep validation; LOC ≈ 200); 003.14b (watchdog + `_partial_flush` + `_run` orchestrator + cross-3/4/5/7 envelopes; LOC ≈ 300). M-2 architect-lock test becomes 003.14b's headline.

**M-3. Task 003.16 mixes perf-fixture generation + 10 saboteurs + 3 cross-skill tests + battery xfail removal.** Realistic effort 5–7 h. **Proposed split:** 003.16a (perf fixture + xlsx-6 envelope tests + battery xfail removal); 003.16b (10 canary saboteurs functional + meta-test exit 0).

**M-4. Task 003.08 (`scope_resolver.py`) crowds 10 scope forms + Excel-Tables + merged-cell + hidden filter + 16 tests into ≤ 400 LOC.** Realistic effort 5–6 h. **Proposed split (optional, lower priority than M-1/M-2/M-3):** 003.08a (scope forms + sheet-qualifier + header lookup); 003.08b (Excel-Tables fallback + merged-cell anchor + hidden filter). Developer can keep 003.08 unified if they hit 4 h cleanly.

### 🟢 MINOR

- **m1 — xfail discipline is implicit, not enforced.** Add to each Phase-2 task's AC: "`@unittest.expectedFailure` removed from `test_battery.<owned-fixture>` entries; battery shows xpass on the slice." 003.16 sweep is a safety net but explicit per-task is cleaner.
- **m2 — Architecture review M-3 LOC contradiction not echoed in PLAN.** Add a sentence naming 3560 LOC as the official total budget so the Developer doesn't get confused mid-stream.
- **m3 — D1 (atomic-chain delivery shape) never explicitly named.** Add one-line "**D1 closure:** 17 sub-tasks per Q&A 2026-05-08" to PLAN.
- **m4 — 003.13 `apply_max_findings` is implemented inline but `apply_summarize_after` is stub.** Asymmetry hints at hidden complexity; flag during implementation.
- **m5 — 003.10 mixes implemented and stub functions in same code block.** Mark unimplemented functions with `# IMPL: <hint>` comments for clarity.
- **m6 — 003.17 runs `validate_skill.py` on docx/pptx/pdf as sanity check.** Recommend adding the same gate to 003.01 so accidental `office/` imports get caught on day one.

## xlsx-6 envelope contract integrity (M2)

VERIFIED. 003.13 has `test_envelope_always_three_keys` + `test_envelope_xlsx6_round_trip` (explicitly checks xlsx-6 batch.py:122 keyset). 003.14 has `test_partial_flush_main_thread_not_signal_handler` (M-2 architect lock) + #39a/#39b tests. 003.16 has the three subprocess-piped end-to-end tests. Strong.

## CLAUDE.md §2 4-skill replication boundary

VERIFIED. No task body modifies `office/`, `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py`. 003.14 imports `from _errors import report_error` (USING, not modifying — fine). 003.17 has `diff -qr` byte-identity gate as final regression sanity check. Sufficient.

## Final Recommendation

**APPROVED WITH COMMENTS.** Developer can proceed once at least M-1, M-2, M-3 are addressed; M-4 is the Developer's call. The 6 MINOR are polish.

```json
{"has_critical_issues": false}
```
