# Plan Review — Task 004 (xlsx-2 / `json2xlsx.py`)

- **Date:** 2026-05-11
- **Reviewer:** plan-reviewer subagent
- **Subject:** `docs/PLAN.md` + 9 `docs/tasks/task-004-NN-*.md`
- **Against:** `docs/TASK.md` (APPROVED) + `docs/ARCHITECTURE.md` (APPROVED).
- **Status:** **APPROVED WITH COMMENTS** → **resolved** after fixes #1–#6 (Important) + #7/#8/#10/#11 (Minor). See §"Resolution".

---

## General Assessment

**APPROVED WITH COMMENTS.** Mature, traceable, surgical plan. Executes the Task-003 D2 pattern (shim + package up front; F-region-per-task in logic phase) with disciplined per-task atomicity. The 9-task slice fits the 8–12 envelope (D5). Three-stage layering (Scaffolding → Logic → Finalization) is correct. Dependencies linear, no cycles. Every R1–R13 has a closing task; every UC-1..UC-5 has a complete coverage chain; AQ-1..AQ-5 + O1 each anchored to a specific closing task with resolution text spelled out.

**Stub-First / Atomicity / Dependencies — all PASS.** Phase-1 stubs raise `NotImplementedError("xlsx-2 stub — task-004-NN")`; cross-cutting glue (004.03) lands same-path guard + exception hierarchy ahead of any F-region; first F-region (004.04 loaders) brings parse-side E2E cases green.

---

## 🔴 CRITICAL

*(none)*

---

## 🟡 IMPORTANT

1. **R4.g attribution split.** `T-strict-dates-aware-rejected` E2E lands at 004.07 (CLI flag wiring), but R4.g is fully attributed to 004.05 in PLAN.md RTM matrix. Add split-attribution note (mirrors R8 + R10 row pattern).
2. **`_parse_jsonl` signature drift.** ARCH §5 says `_parse_jsonl(raw: bytes) -> list[dict]`; 004.04 implements `_parse_jsonl(raw: bytes, source: str)`. The `source` param is unused. Drop it.
3. **`convert_json_to_xlsx` double-definition.** Defined in `json2xlsx/__init__.py` (004.01 re-export contract) AND in shim `json2xlsx.py` body (004.07). Lock in `__init__.py` only; shim re-exports.
4. **`_size_columns` signature drift.** ARCH §F4 lists `_size_columns(ws, headers, rows)`; 004.06 adds unused `coerce_opts, sheet_name`. Drop.
5. **004.08 E2E count honesty.** "All 12 E2E cases green" actually includes a unit-test substitute for `T-post-validate-on-bad-workbook`. Rename to "11 E2E cases + 1 dedicated post-validate unit test".
6. **004.09 perf inventory.** TASK §4.1 specifies TWO perf budgets (10K × 6 ≤ 3 s AND 100K JSONL ≤ 30 s); 004.09 shows ONE. Explicitly drop 100K-row from v1 (matches honest scope §11.3 / O4) OR add it. Pick one.

---

## 🟢 MINOR

7. 004.09 doesn't mention O1 closure explicitly. Add one-liner.
8. PLAN.md R12.c attribution shows 004.01 only; should show `004.01 (placeholder) + 004.09 (final)`.
9. `sys.path.insert` duplicated in shim and `cli.py`. Nit only — works.
10. Platform-IO errors (`FileNotFoundError`, `OSError`) surfaced via direct `report_error(...)` ad-hoc payloads — intentional per TASK §10 footnote. Could be noted in PLAN.md to pre-empt confusion.
11. 004.02 should note that `T-same-path` is expected RED until 004.03 lands.
12. ≤ 320 LOC `cli.py` guardrail is a Plan-level commitment. ✅ no change.
13. Honest-Scope Carry-Forward mirrors TASK + ARCH cleanly. ✅ no change.

---

## Specific-Risks Checklist

| Risk | Verdict |
| :--- | :--- |
| 004.04 loaders.py (F1+F2) too large? | **No** — ~120 LOC, well under ≤ 200. |
| 004.05 `--strict-dates` flag wired by 004.07? | **Yes** with split-attribution note (Important #1). |
| 004.07 ≤ 320 LOC guardrail Plan-level? | **Yes**. |
| 004.08 reads `office/validators/xlsx.py` — `diff -q` gate? | **Silent** — subprocess invocation, never modifies. |
| 004.09 ✅ DONE depends on 004.08 green? | **Yes** — explicit dependency. |

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Plan is execution-ready. Suggested fix order (lightest first): #2 → #4 → #3 → #1 → #6 → #5, then 🟢 nits #7 / #8 / #10 / #11.

---

## Resolution

Orchestrator (2026-05-11) applied the following edits:

1. **Important #2 fixed.** `_parse_jsonl` signature in 004.04 dropped `source` arg (now matches ARCH §5).
2. **Important #4 fixed.** `_size_columns` in 004.06 dropped `coerce_opts, sheet_name` args.
3. **Important #3 fixed.** `convert_json_to_xlsx` body lives in `json2xlsx/__init__.py` only; shim re-exports. Note in 004.01 + 004.07 reflects single source of truth.
4. **Important #1 fixed.** PLAN.md R4 row + 004.05 task file note R4.g landing point: logic in 004.05, CLI flag + envelope landing in 004.07.
5. **Important #6 fixed.** PLAN.md R11.e + 004.09 perf section explicitly drops 100K-row budget from v1 (matches honest scope §11.3 / O4).
6. **Important #5 fixed.** 004.08 AC + PLAN.md R10 row rephrased to "11 E2E cases + 1 dedicated post-validate unit test (cleanup-path)".
7. **Minor #7 fixed.** 004.09 adds one-liner "Closes O1 — xlsx-2 owns the round-trip contract via `references/json-shapes.md`".
8. **Minor #8 fixed.** PLAN.md R12.c row shows `004.01 (placeholder) + 004.09 (final)`.
9. **Minor #10 fixed.** PLAN.md notes platform-IO errors (`FileNotFound`, `IOError`) are surfaced via ad-hoc envelope payloads (intentional design, NOT typed `_AppError`).
10. **Minor #11 fixed.** 004.02 AC notes `T-same-path` turns green in 004.03, not 004.02.

Status: **APPROVED — ready for Execution (Development) phase**. `has_critical_issues: false`.
