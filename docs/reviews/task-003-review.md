# Task 003 Review — `xlsx-7 / xlsx_check_rules.py`

**Date:** 2026-05-08
**Reviewer:** Task Reviewer (subagent)
**Target:** `/Users/sergey/dev-projects/Universal-skills/docs/TASK.md`
**Status:** **APPROVED WITH COMMENTS** (no blockers; 2 MAJOR items fixable in-place by Analyst before Architect picks up).

## General Assessment

The TASK is unusually strong for a v1 draft of a feature this size:

- **RTM granularity is real, not theatrical** — 14 requirements, every row has 3+ named sub-features (most have 5–8), every row carries a `[SPEC §N]` anchor.
- **Decisions D1/D2/D3 are properly locked** at the top with provenance (`/vdd-start-feature` Q&A 2026-05-08), and the Open Questions Q1–Q7 are correctly scoped to architectural questions, not user-product questions — they belong with the Architect.
- **xlsx-6 envelope contract is recognised as frozen** (Assumption §5; R11.e; I8.2). This is the right framing.
- **Honest scope is locked by tests** (R13.l), mirroring the xlsx-6 m4/R9.d convention.
- **CLAUDE.md §2 boundary respected** — explicit "xlsx-7 does NOT activate 4-skill replication; office/, _soffice.py, _errors.py, preview.py, office_passwd.py NOT modified" call-out in §4 / §5.
- **License hygiene** — implicit but correct (xlsx is proprietary, no third-party license touched; new PyPI deps would need a `THIRD_PARTY_NOTICES.md` update, but that's a Planning-phase task, not a TASK-phase gap).

The two material issues are scoped narrowly: (1) Q4 is answerable now and shouldn't be deferred to the Architect (data is in the repo), and (2) the I8.2 envelope-shape description is one sentence too loose vs. the actual xlsx-6 implementation.

---

## 🔴 CRITICAL

*(none — no blocking issues)*

---

## 🟡 MAJOR

### M1 — Q4 (Excel error subset) is answerable from openpyxl source; should be resolved in TASK, not punted

**Where:** §6 Open Questions, Q4. Also propagates to R2.e, I2.1 Alt-1, fixture #10, canary saboteur 8, SPEC §5.0 cross-reference.

**Finding:** The TASK asks the Architect to verify "openpyxl reports all 10? `#GETTING_DATA` is rare (Power Query-only); Architect may scope down to the canonical 7." This is **directly answerable from the installed openpyxl in the repo's `.venv`** without spiking — verified:

`skills/xlsx/scripts/.venv/lib/python3.14/site-packages/openpyxl/cell/cell.py:46`:

```python
ERROR_CODES = ('#NULL!', '#DIV/0!', '#VALUE!', '#REF!', '#NAME?', '#NUM!',
               '#N/A')
```

That is **exactly 7 codes**. `#GETTING_DATA`, `#SPILL!`, `#CALC!` are **not** in openpyxl's recognised set; they will be returned as `data_type='s'` (text) when stored in cells via shared-strings — a cell containing the string `"#SPILL!"` would silently bypass the §5.0 auto-emit path.

**Why this matters now (not later):**
- The SPEC §5.0 currently lists 10 codes. Either SPEC is wrong (should list 7) or the implementation must do extra work (string-prefix detection on `text` cells to also catch `#SPILL!`/`#CALC!`/`#GETTING_DATA`). That decision affects R2.e, the AST `is_error` predicate semantics, fixture #10's expected `cell-error` count, and saboteur #8's failure surface.
- The Architect would have to spike to find out exactly what is confirmed in 30 seconds. That makes Q4 a TASK-phase deficiency, not an architectural unknown.

**Fix (suggested resolution to bake into TASK):**
Replace Q4 with a closed decision **D4** in §0 with the following content (and update SPEC §5.0 + fixture #10 in the same edit):

> **D4 (was Q4) — Excel error subset.** openpyxl `ERROR_CODES` (cell.py:46) recognises exactly 7 codes: `#NULL!`, `#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?`, `#NUM!`, `#N/A`. xlsx-7 v1 honours those 7 only — they reach `data_type='e'` and trigger the §5.0 auto-emit. The 3 modern Excel codes (`#SPILL!`, `#CALC!`, `#GETTING_DATA`) are stored by openpyxl as `text` and are **NOT** auto-emitted in v1; if a workbook uses them, a user-authored `regex:^#(SPILL|CALC|GETTING_DATA)` rule on the relevant scope is the v1 workaround. **Action items downstream:** (a) update SPEC §5.0 to list 7 codes (move the other 3 into §11 honest scope as "modern-Excel error codes not auto-detected by openpyxl"); (b) lock with fixture #10b: a workbook with `#SPILL!` stored as text → no `cell-error` finding without a user rule.

This unblocks the Architect (one fewer Q to resolve), tightens the SPEC's honest-scope contract, and prevents a Developer from hand-rolling a parallel string-detection path that would silently diverge from openpyxl's behaviour.

### M2 — I8.2 envelope-shape description is looser than the xlsx-6 implementation it must contract against

**Where:** §3 Epic E8 Issue I8.2 Main Scenario step 2. Also implicit in R11.e and Assumption "shape of the xlsx-7 findings envelope is already promised by xlsx-6".

**Finding:** The TASK says: *"xlsx-6 auto-detects envelope shape (object with `findings` key); maps `cell ← findings[i].cell`, `text ← findings[i].message`."*

The actual xlsx-6 implementation (`skills/xlsx/scripts/xlsx_comment/batch.py:122`) is stricter:

```python
if isinstance(root, dict) and {"ok", "summary", "findings"} <= set(root.keys()):
```

xlsx-6 requires **all three** keys `{ok, summary, findings}` to be present. A dict with only `findings` (or missing `ok` / `summary`) falls through to `InvalidBatchInput` (exit 2). This is the **actual** envelope contract.

**Why this matters:** The TASK's loose phrasing could lead the Developer to (a) emit an envelope with optional `summary` (e.g. when `--max-findings 0`), thinking xlsx-6 would still auto-detect — it won't, the pipe will exit 2; (b) regress xlsx-6 inadvertently when fixture #39 is run, because the test driver might not exercise the all-three-keys requirement.

**Fix (suggested):** Tighten I8.2 step 2 to mirror xlsx-6's actual gate, and add fixtures #39a/#39b for partial-flush and `--max-findings 0` paths. Tightened I8.2 step 2:

> 2. xlsx-6 auto-detects envelope shape — root must be a JSON object containing **all three** keys `{ok, summary, findings}` (xlsx-6 batch.py:122; this is the frozen contract). xlsx-7's `--json` output therefore MUST always emit all three top-level keys, even on `--max-findings 0` / `--severity-filter` / `--require-data` / timeout-with-partial-flush paths. Maps `cell ← findings[i].cell`, `text ← findings[i].message`.

Add to I8.2 Acceptance Criteria:

> ✅ Fixture #39a: xlsx-7 timeout-partial-flush output (exit 7 + partial JSON) still has all three top-level keys; piping to xlsx-6 succeeds (no `InvalidBatchInput`).
> ✅ Fixture #39b: xlsx-7 `--max-findings 0` (cap disabled, stderr warning per §8.1) still emits `summary` and `ok`; xlsx-6 round-trip clean.

---

## 🟢 MINOR

### m1 — Epics E3 and E4 use "delegate to SPEC §5.x" shortcut; sub-issues I3.1–I3.8 / I4.2–I4.4 lack inline Use-Case structure

For comparison, I1.1 / I1.2 / I2.1 / I2.2 / I8.2 carry the full Actors / Preconditions / Main Scenario / Alternatives / Postconditions / AC structure. The asymmetry is defensible — §5.1–§5.7 of the SPEC are exhaustive on each predicate's semantics, so duplicating them in the TASK would be cargo-cult ceremony.

**Verdict: ACCEPTABLE as-is** for D1 atomic chain (the Planner will produce one task per I3.x and that task will carry the AC inline). Optional fix: add one line to each I3.x stub naming the **negative** fixture by number (costs 8 lines).

### m2 — Fixture #19 vs #19a coverage mentioned but issue mapping is generic (I7.2)

I7.2's one-liner names "replay semantics" but doesn't separately call out #19a's strict-mode invariant. R10.d covers it correctly, but I7.2's AC line is silent. Optional fix: expand I7.2 AC to spell out #19, #19a, and saboteur #9.

### m3 — `--treat-text-as-date` and `--treat-numeric-as-date` share R4d but have very different parse-risk profiles

`--treat-numeric-as-date` is deterministic (zero-risk window check). `--treat-text-as-date` invokes `dateutil.parser.parse(s, fuzzy=False, dayfirst=...)` which **does not have a true strict mode** — even with `fuzzy=False` it accepts `"42"` as `2042-01-01` (SPEC §5.4.1 path 4 explicit). I2.1 Alt-3 captures the dateutil quirk but doesn't lock a negative test for the `--treat-text-as-date NumericCol` typo case. Optional fix: split R4d into R4d / R4d2 + add Alt-3a.

### m4 — `--require-data` synthetic finding bypass-of-`--severity-filter` undocumented in TASK

SPEC §8.1 says `--require-data` produces a `no-data-checked` finding that *"bypasses `--severity-filter` (always visible)"*. Add to I4.2 AC.

### m5 — `--treat-numeric-as-date ''` (empty list disables per-rule overrides) is in SPEC §8.1 but not explicit in TASK DEP-6

Append to DEP-6: *"Empty string value (`--treat-numeric-as-date ''`) explicitly disables per-rule `treat_numeric_as_date: true` overrides — distinct from omitting the flag entirely."*

### m6 — Q1 recommendation already converges on graceful fallback; could be promoted to D5

Q1 text already states "Recommendation: B (graceful fallback)". This is the right answer for skill-package independence (CLAUDE.md "Независимость скиллов" — `recheck` PyPI outage shouldn't break install). Could be locked as D5 right now.

### m7 — TASK §0 "Status: Draft v1 — pending Architecture-phase decisions on Q1–Q5" undercounts (should be Q1–Q7)

s/Q1–Q5/Q1–Q7/.

### m8 — `examples/check-rules-timesheet.json` referenced in R14.d and I9.5 but no `.xlsx` companion is named consistently

R14.d says "`examples/check-rules-timesheet.json`"; I9.5 says "`examples/check-rules-timesheet.{json,xlsx}`". Standardise on `{json,xlsx}` everywhere — the SPEC §10 worked example needs both files to be runnable.

---

## Open Questions Audit (Q1–Q7)

| Q | Right audience | Verdict |
|---|---|---|
| Q1 (`recheck` availability) | Architect | ✓ Correct — implementation/dep choice. Could lock as D5 (m6). |
| Q2 (module split inside `xlsx_check_rules/`) | Architect | ✓ Correct — internal architecture, user already gave D2. |
| Q3 (streaming-output remark-column-mode `replace`) | Architect | ✓ Correct — SPEC §8.2.1 left it open. |
| **Q4** (Excel error subset) | **Architect → should be Analyst NOW** | ✗ **M1 above** — answerable from openpyxl source. |
| Q5 (fixture-set storage) | Architect | ✓ Correct — CI strategy choice. |
| Q6 (perf-test gating) | Architect | ✓ Correct — matches xlsx-6 convention. |
| Q7 (`version: 1` strictness) | Architect | ✓ Correct — implementation policy choice. |

**None are user-blocking.** Q1–Q7 are all implementation-level and safely Architect-scoped — except Q4, which is **technically resolved by the codebase already**.

---

## Cross-checks summary

- ✅ **No contradiction with SPEC** found other than M1 (SPEC §5.0 lists 10 error codes; openpyxl recognises 7 — needs SPEC update too).
- ✅ **No contradiction with xlsx-6** envelope contract found other than M2 wording.
- ✅ **CLAUDE.md §2 4-skill replication boundary** correctly observed.
- ✅ **CLAUDE.md §3 license hygiene** — new PyPI deps correctly flagged for Planning-phase `THIRD_PARTY_NOTICES.md` update.
- ✅ **xlsx-6 honest-scope test convention** mirrored (R13.l).

---

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Architecture phase after addressing M1 and M2 in-place.**

- **M1 (Q4 → D4):** convert Q4 into D4 in §0 with the openpyxl-7-codes finding; update SPEC §5.0 / R2.e / I2.1 Alt-1 / fixture #10 cross-refs in the same edit.
- **M2 (I8.2 envelope tightening):** update I8.2 step 2 + AC; add fixtures #39a/#39b.
- **🟢 minor items:** at Analyst's discretion — none are gating. m6/m7/m8 are cheap and worth doing.

After M1/M2 land, Architect can pick up the TASK and resolve Q1–Q3 / Q5–Q7 (Q4 will already be D4).

---

## Files relevant to this review

- TASK under review: `docs/TASK.md`
- SPEC contract: `skills/xlsx/references/xlsx-rules-format.md` (12 sections + §13 battery)
- xlsx-6 envelope gate (M2 evidence): `skills/xlsx/scripts/xlsx_comment/batch.py:122`
- openpyxl error-code set (M1 evidence): `skills/xlsx/scripts/.venv/lib/python3.14/site-packages/openpyxl/cell/cell.py:46`
- Backlog row for xlsx-7: `docs/office-skills-backlog.md` (line 192)

```json
{"has_critical_issues": false}
```
