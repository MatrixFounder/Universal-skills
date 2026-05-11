# Architecture Review — Task 004 (xlsx-2 / `json2xlsx.py`)

- **Date:** 2026-05-11
- **Reviewer:** architecture-reviewer subagent
- **Subject:** `docs/ARCHITECTURE.md` (Task 004, xlsx-2)
- **Against:** `docs/TASK.md` (Task 004 v2; task-reviewer APPROVED WITH COMMENTS round-1, orchestrator-fixed).
- **Status:** **APPROVED WITH COMMENTS** → **resolved** after fixes M1/M2/m1/m2/m3/m5/m6 (see §"Resolution").

---

## General Assessment

Well-grounded in xlsx-6 / xlsx-7 precedent and explicitly inherits the shim+package shape from Task 003. Component decomposition (F1–F8) maps 1:1 to modules; LOC budgets are realistic against the csv2xlsx (203 LOC) and xlsx-7 (3791 LOC) baselines. Cross-skill replication boundary (§9) is exhaustively enumerated with eleven `diff -q` invocations matching CLAUDE.md §2 verbatim. Data Model entities (`ParsedInput`, `CellPayload`, `CoerceOptions`) are correctly typed; cross-5 envelope §4 references the frozen schema in `_errors.py:39`. Bool-before-int business rule in `CellPayload` is correctly justified. §7 security threat model is realistic; per-threat mitigations cross-reference TASK §11 honest-scope items. AQ-1 through AQ-5 are genuine architectural unknowns. The COPY style-constants decision (§3.2 writer) is well-argued and consistent with R13.b.

No 🔴 Critical issues. The two 🟡 Major items are a factual error in AQ-1 and an under-sized LOC budget; both correctable without re-architecting.

---

## 🔴 CRITICAL (BLOCKING)

*(none)*

---

## 🟡 MAJOR

### M1 — AQ-1 drift-detection assertion references wrong hex literal

- **Where:** §3.2 writer "Drift detection" + AQ-1.
- **Finding:** Proposes asserting `csv2xlsx.HEADER_FILL.fgColor.rgb == "00F2F2F2"` (8 chars, alpha-prefixed). Verified at `skills/xlsx/scripts/csv2xlsx.py:39`: actual constant is `PatternFill("solid", fgColor="F2F2F2")` (6 chars). openpyxl normalises to `"00F2F2F2"` on attribute access, but agents reading the doc will pattern-match the literal into the test verbatim.
- **Fix proposal:** Change AQ-1 to `csv2xlsx.HEADER_FILL.fgColor.rgb in ("F2F2F2", "00F2F2F2")` and explicitly note "openpyxl normalises 6-char fgColor to 8-char ARGB on attribute access; the test asserts the normalised form".

### M2 — `cli.py ≤ 200 LOC` budget is unrealistic

- **Where:** §3.2 file inventory + §3.3 diagram.
- **Finding:** xlsx-7's analogous `xlsx_check_rules/cli.py` runs 569 LOC for 22 flags. xlsx-2 has 8 flags but the orchestrator still handles: argparse construction, `_AppError` top-of-`_run` catch (AQ-3), cross-5 envelope routing, file-vs-stdin branching, multi-sheet `--sheet` warning, post-validate dispatch, same-path guard pre-check. A more honest estimate is ~280–350 LOC.
- **Fix proposal:** Raise `cli.py` budget to **≤ 320 LOC** and add a guardrail: "If `cli.py` crosses 320 LOC, split `_run` into a separate `orchestrator.py` (≤ 500 LOC architect cap)".

---

## 🟢 MINOR

- **m1** — §5 lists `_AppError(Exception)` with four attributes but other sections imply "frozen dataclass" idiom. State explicitly whether `_AppError` is a plain `Exception` subclass (xlsx-6 pattern) or a `@dataclass(frozen=True)` Exception (xlsx-7 `RulesParseError` pattern). The Developer needs to know.
- **m2** — F1 → F8 ordering mismatch between §2.2 component diagram and §F7 sequence (F7 has `F1 → F8 → F2`; §2.2 doesn't show F8 receiving the input path before F1). Reorder §2.2 or amend to show F8 receiving the path string before F1 reads bytes.
- **m3** — F2 `detect_and_parse(..., is_jsonl_hint: bool)` only takes a boolean hint, losing the JSON root-token signal. Clarify whether root-token branch is part of `detect_and_parse` (preferred) or part of F1 (currently silent). Mirror UC-3 A1 (blank-line tolerance) into the function contract.
- **m4** — `references/json-shapes.md` placement at end-of-chain (DoD §7) is acceptable, but the front-loading alternative is more defensible engineering order. Not blocking; note in §3.2 that **xlsx-8's task (when it lands) MUST consume `references/json-shapes.md` unchanged**, so xlsx-2 doesn't ship the spec then immediately revise it.
- **m5** — A1 ("no `write_only=True`") restates TASK §11.3. Either tag A1 "mirrors TASK §11.3" or drop it and keep A2/A3/A4/A5.
- **m6** — §6 Tech Stack says "no new dependency" and lists `python-dateutil` as already pinned. Accurate. But `pandas>=2.0.0` is also in `requirements.txt` and xlsx-2 deliberately avoids it. Worth a one-line explicit statement in §6 to lock the decision against a future Developer "simplifying" with `pd.DataFrame.from_records`.

---

## Trace against user-supplied focus list

| # | Topic | Verdict |
|---|---|---|
| 1 | Data Model correctness | OK; bool-before-int correctly motivated. |
| 2 | F1–F8 decomposition, LOC budgets | OK except `cli.py` (M2). F1+F2 → `loaders.py` and F6+F8 → `cli_helpers.py` are right consolidations. |
| 3 | Style-constant COPY policy | **Right call.** Importing csv2xlsx would create a cross-CLI dep with no precedent. Drift assertion is appropriate (M1 fixes the literal). |
| 4 | Cross-skill replication §9 | All eleven `diff -q` verified. Exact match to CLAUDE.md §2. No file in the boundary is touched. |
| 5 | Security §7 | Complete. "No eval / no shell" is verifiable. |
| 6 | AQ-1 through AQ-5 | AQ-1: real unknown (M1). AQ-2 / AQ-3 / AQ-5 could be locked NOW (Planner). AQ-4: real naming decision, keep open. |
| 7 | Honest scope §10 (A1–A5) | A1 overlaps TASK §11.3 (m5). A2–A5 genuinely new. |
| 8 | YAGNI | F1+F2 / F6+F8 collapses are right. `cli.py` vs `cli_helpers.py` split is justified. |
| 9 | §5 signatures vs TASK R9 flags | Matches. 8 flags exactly cover R9 (a)–(f). |
| 10 | `json-shapes.md` placement | End-of-chain is acceptable; m4 flags alternative. |

---

## Final Recommendation

**APPROVED WITH COMMENTS** — proceed to Planning after orchestrator inlines M1 + M2. Minor items m1–m6 can be absorbed into the same pass or into the first planning sub-task.

---

## Resolution

Orchestrator (2026-05-11) applied the following edits to `docs/ARCHITECTURE.md`:

1. **M1 fixed.** AQ-1 + §3.2 writer "Drift detection" rewritten to `csv2xlsx.HEADER_FILL.fgColor.rgb in ("F2F2F2", "00F2F2F2")` with an explicit note on openpyxl's 6→8-char ARGB normalisation.
2. **M2 fixed.** `cli.py` LOC budget raised to ≤ 320 in §3.2 + §3.3 diagram + table. Added a guardrail: "If `cli.py` crosses 320 LOC, split `_run` into `orchestrator.py` (≤ 500 LOC architect cap)".
3. **m1 fixed.** §3.2 exceptions.py + §5 Internal interfaces clarified — `_AppError` is a plain `Exception` subclass with attributes set in `__init__`, NOT a `@dataclass(frozen=True)` Exception. Mirrors xlsx-6 `xlsx_comment/exceptions.py` precedent.
4. **m2 fixed.** §2.2 diagram updated so F8 receives the **path string** from F5 BEFORE F1 reads bytes; matches the §F7 linear-pipeline mermaid.
5. **m3 fixed.** F2 signature updated to `detect_and_parse(raw: bytes, source: str, *, is_jsonl_hint: bool) -> ParsedInput` with a sub-bullet "Root-token branch is part of this function; F1 only knows about the extension hint. Blank lines in JSONL are stripped before parse (mirrors UC-3 A1)".
6. **m5 fixed.** A1 in §10 tagged "(mirrors TASK §11.3)" to signal it's a re-statement.
7. **m6 fixed.** §6 Tech Stack table gains a "pandas dep deliberately avoided" row with the 3-bullet rationale.
8. **m4 captured.** §3.2 "References" sub-section gains a note: "xlsx-8's task (when it lands) MUST consume `references/json-shapes.md` unchanged; if xlsx-8 requirements force a revision, the live round-trip test breaks until both skills update synchronously".

Status: **APPROVED — ready for Planning phase**. `has_critical_issues: false`.
