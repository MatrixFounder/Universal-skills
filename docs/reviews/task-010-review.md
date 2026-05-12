# Task Review — TASK 010 (xlsx-8 `xlsx2csv` / `xlsx2json` read-back)

**Date:** 2026-05-12
**Reviewer:** Task Reviewer (self-review per VDD verification loop)
**Status:** APPROVED WITH MINOR REVISIONS APPLIED

---

## 1. General Assessment

The TASK draft is well-structured and inherits the discipline of TASK
009 (xlsx-10.A): explicit RTM with Epics→Issues→Sub-features,
detailed UC structure (Actors / Preconditions / Main / Alternatives /
Postconditions / Acceptance), honest-scope catalogue, locked decisions
table, atomic-chain hint for Planner. Backlog row `xlsx-8` is faithfully
expanded into machine-checkable acceptance criteria with no scope creep
beyond what the backlog (and dependency on xlsx-10.A) authorises.

Five issues identified — three Minor (typo / phrasing), two Major
(ambiguity in `--tables` mode mapping + R6.g vague regression
description). All have been **patched inline in TASK.md**; no critical
issues blocking architecture.

---

## 2. Comments

### 🔴 Critical (BLOCKING)

— None.

### 🟡 Major

#### M1 — `--tables` mode mapping to library `TableDetectMode` is ambiguous

**Section:** UC-03 step 3 (and §R9).
**Issue:** The backlog row defines four `--tables` values
(`whole|listobjects|gap|auto`); the `xlsx_read` library exposes three
`TableDetectMode` values (`auto|tables-only|whole`). There is no 1:1
mapping:

- `--tables listobjects` ≠ library `tables-only` — library mode includes
  Tier-2 sheet-scope named ranges; backlog implies Tier-1 only.
- `--tables gap` has no library mode (no "Tier-3 only" exists).

Without a resolution, the implementer has to invent semantics during
coding, breaking VDD discipline.

**Fix applied:** UC-03 step 3 now reads "translates `--tables
listobjects` to library `tables-only` mode (which includes Tier-1
ListObjects + Tier-2 sheet-scope named ranges); honest-scope addition
to §1.4 (l) documents that named ranges are silently included alongside
ListObjects when `--tables listobjects`." For `--tables gap`, shim
calls library `mode="auto"` and filters `region.source == "gap_detect"`.
Added §1.4 (l) item. Added Q-A6 to §7.2 documenting the alternative
(filter-out vs library-API addition) and recommending the filter
approach for v1 (deferred library API extension to v2).

#### M2 — R6.g regression description is meaningless

**Section:** §R6.g.
**Issue:** "Output byte-identical to originally-described xlsx-8 v1
behaviour" — there is no prior xlsx-8 to compare against; this is a
self-referential acceptance criterion.

**Fix applied:** R6.g reworded to "with all flags omitted, output is
the simplest documented shape (flat JSON array-of-objects for single
sheet; flat array-of-objects per sheet for `--sheet all`; single-row
header from row 1; merged cells use `anchor-only` policy; no
hyperlinks / formulas; ISO-8601 datetime). Regression test pins this
shape via a synthetic 5-cell fixture, NOT via comparison with a prior
implementation."

### 🟢 Minor

#### m1 — UC-04 A2 disallowed-character list inconsistent with §4.2

**Section:** UC-04 A2 vs §4.2.
**Issue:** UC-04 A2 listed `/`, `\\`, `..`, NUL but §4.2 added
`:`, `*`, `?`, `<`, `>`, `|`, `"` (Windows-forbidden). Doc should be
consistent.

**Fix applied:** UC-04 A2 now references §4.2 for the full list:
"Disallowed characters in sheet/table names when used as filesystem
path components — see §4.2 for the cross-platform reject list."

#### m2 — UC-02 A1 envelope name needs to be explicit in R*

**Section:** UC-02 A1.
**Issue:** Mentions `MultiSheetRequiresOutputDir` envelope but it isn't
defined in any R* explicitly (only `MultiTableRequiresOutputDir` is in
R12.d).

**Fix applied:** Added §R12.f: "`--sheet all` AND CSV output to
single-file/stdout AND > 1 visible sheet detected → exit 2
`MultiSheetRequiresOutputDir` envelope (multi-sheet CSV cannot
multiplex into one stream)."

#### m3 — UC-01 A4 "byte-verbatim" needs JSON-escape caveat

**Section:** UC-01 A4.
**Issue:** Sheet name like `"Q1 / Q2 split"` preserved "byte-verbatim
in JSON keys" — but JSON serialisers always escape `\` and `"`. Caveat
needed.

**Fix applied:** UC-01 A4 now reads "Preserved verbatim in JSON keys
modulo standard JSON escaping (`\\`, `\"`) — `json.dumps` is invoked
with `ensure_ascii=False` so non-ASCII chars are emitted as UTF-8."

---

## 3. Checklist Compliance

| Item | Status | Notes |
| --- | --- | --- |
| **1.1 Requirements** | ✅ | All xlsx-8 features from backlog mapped to R*. |
| **1.2 Scope** | ✅ | No unrequested features. Honest scope §1.4 explicit. |
| **1.3 Goal** | ✅ | Closes read-back gap + activates xlsx-2 round-trip. |
| **2.1 Use Case structure** | ✅ | All 10 UCs have full structure. |
| **2.2 Main Scenario clarity** | ✅ | Step-by-step actor/system actions. |
| **2.3 Alternative coverage** | ✅ | Error handling + edge cases enumerated. |
| **2.4 Acceptance Criteria binary** | ✅ | Pass/fail per UC. |
| **3.1 Terminology** | ✅ | Uses project terms (xlsx_read, cross-3/4/5/7, ListObjects). |
| **3.2 Architecture respect** | ✅ | Shim ≤ 60 LOC pattern; ARCH §9 diff-q gate respected. |
| **3.3 Integrations** | ✅ | `_errors`, `xlsx_read`, `references/json-shapes.md` correctly described. |
| **4.1 Internal consistency** | 🟡→✅ | M1/M2 fixed. |
| **4.2 Naming consistency** | ✅ | `xlsx2csv2json/` package, `--tables` modes consistent post-fix. |
| **5.1 Performance metrics** | ✅ | §4.1 has wall-clock + RSS bounds. |
| **5.2 Security** | ✅ | §4.2 path traversal, allowlisting, basename-only. |

---

## 4. Final Recommendation

**APPROVED.** All Major / Minor issues have been patched inline in
`docs/TASK.md`. No re-review needed. **Proceed to Architecture phase.**

---

**Return payload:**
```json
{
  "review_file": "docs/reviews/task-010-review.md",
  "has_critical_issues": false
}
```
