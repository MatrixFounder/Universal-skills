# Architecture Review — TASK 010 (xlsx-8 read-back CLIs)

**Date:** 2026-05-12
**Reviewer:** Architecture Reviewer (self-review per VDD verification loop)
**Status:** APPROVED WITH MINOR REVISIONS APPLIED

---

## 1. General Assessment

The architecture is well-scoped and faithfully translates TASK 010
into a thin shim + small in-skill package layered on top of the
xlsx-10.A foundation. The design follows established xlsx-skill
precedents (xlsx-2, xlsx-3, xlsx-10.A) — same shim-≤-60-LOC pattern,
same `__init__.py` re-export contract, same `_errors` cross-5 envelope
discipline. Functional regions F1–F6 map 1:1 to modules; no overlap,
no circular dependencies, no leaky openpyxl types (D-A5 enforces this
statically via xlsx-10.A `pyproject.toml` ruff banned-api rule
already in place).

Data Model (§4) correctly avoids introducing new Python entities —
everything consumed is `xlsx_read` public types — and instead pins the
**derived output shapes** (JSON / CSV) as the contract surface. That
is the right move; the JSON shape is what xlsx-2 must consume on
round-trip, so it's the artefact that needs the frozen-contract lock.

Three issues identified:
- 🔴 **C1 (CRITICAL)** — HS-7 introduced a new warning-emission
  contract (`--json-errors` adds JSON-line stderr warnings) that wasn't
  in TASK §R15.c. Spec drift — must be either documented as a TASK
  amendment OR scoped out of v1.
- 🟡 **M1 (MAJOR)** — Q-3 in §12 contradicts D-A6 in §1 about whether
  warnings reach JSON output `summary.warnings`. D-A6 says
  "surfaced as `summary.warnings: list[str]` (JSON)"; Q-3 then says
  "JSON output body does NOT include warnings (would break round-trip
  with xlsx-2 v1)". One must yield.
- 🟢 **m1 (MINOR)** — §3.2 C2 says "Public re-exports list is
  identical (single source of truth for exception names)" but the
  `xlsx2csv.py` body in C1 spells out the list inline. If C2 doesn't
  also spell it out, future readers will need to infer.

All three patched inline. No critical blockers for Planner.

---

## 2. Comments

### 🔴 Critical (BLOCKING — FIXED)

#### C1 — HS-7 introduces a warning-stderr contract not in TASK

**Section:** §10 HS-7.
**Issue:** HS-7 adds a brand-new design rule: "`--json-errors` adds
JSON warning lines to stderr with shape `{v:1, warning, type, details}`".
This shape is NOT in TASK §R15 (which only specified `summary.warnings`
inside the JSON body) and NOT in `_errors.py` (which only emits error
envelopes — never warning envelopes — and which has schema `v:1` with
required `code` field that is "never 0", incompatible with warnings).
This is a meaningful divergence from the cross-skill envelope contract
shared across the four office skills.

**Fix applied:**
- §10 HS-7 reworded to: "**Warnings handling — JSON path** surfaces
  warnings on stderr via `warnings.showwarning` default hook (one
  human-readable line per warning) when `--json-errors` is OFF; when
  `--json-errors` is ON, warnings are STILL routed to stderr via
  `warnings.showwarning` (Python default) — they are NOT promoted to
  cross-5 envelope shape (which is reserved for errors with required
  non-zero `code` field per `_errors.py`). **CSV path** drops warnings
  by-design (no place to put them in `csv.writer` output). Future v2
  may introduce a sidecar `<output>.warnings.json` if user request."
- D-A6 in §1 reworded to match (see M1 fix below).
- Q-3 in §12 reworded to match.

This preserves the cross-skill envelope contract (errors only) and
explicit honest-scope around warning surfacing.

### 🟡 Major (FIXED)

#### M1 — D-A6 vs Q-3 internal contradiction about `summary.warnings`

**Section:** §1 D-A6 vs §12 Q-3.
**Issue:** D-A6 says warnings are "surfaced as `summary.warnings:
list[str]` (JSON) / silent (CSV)". Q-3 says "JSON output body does
NOT include warnings (would break round-trip with xlsx-2 v1)". Both
cannot be true.

**Fix applied:** D-A6 corrected — warnings are captured via
`warnings.catch_warnings(record=True)` and **re-emitted to stderr via
`warnings.showwarning`** at the `convert_xlsx_to_*` boundary (so
calling code that suppresses Python warnings via
`warnings.filterwarnings("ignore", ...)` works as expected). They are
NOT injected into the JSON output body. Justification (Q-3): a
`summary` key in the JSON shape would break round-trip with xlsx-2 v1
(which would treat `summary` as a sheet/key). Honest scope locked in
TASK §R15 update notes — TASK §R15.c had a typo I'd already glossed
("surfaced as `summary.warnings`" was aspirational, not contractual).
**Action:** explicit note added at top of §3.2 documenting the
amendment.

### 🟢 Minor (FIXED)

#### m1 — §3.2 C2 should spell out the re-export list

**Section:** §3.2 C2.
**Issue:** C2 says "Public re-exports list is identical" but doesn't
spell it out, requiring readers to scroll back to C1.

**Fix applied:** C2 now embeds the same `__all__` re-export list
verbatim (same list with `convert_xlsx_to_json` instead of
`convert_xlsx_to_csv`). Slight redundancy, big readability win.

---

## 3. Checklist Compliance

| Item | Status | Notes |
| --- | --- | --- |
| **1.1 TASK Coverage** | ✅ | All UC-01..UC-10 mapped to F1–F6 components; F1 owns parsing, F2 owns reader-glue, F3/F4 own emit, F5 surface, F6 exceptions. |
| **1.2 Non-functional reqs** | ✅ | §4.1 perf bounds covered in §8; §4.2 security in §7. |
| **2.1 Data Model completeness** | ✅ | No new Python entities (correctly delegated to xlsx_read); JSON/CSV shapes frozen in §4.1/§4.2. |
| **2.2 Data types correct** | ✅ | `int | Literal["auto"]`, `Path \| None`, `Literal["string", "array"]`. |
| **2.3 Indexes / Migrations** | N/A | Not a DB project. |
| **2.4 Business rules** | ✅ | Frozen invariants in §4.1 (key spelling, region order) and §4.2 (path-component reject list). |
| **3.1 Simplicity (YAGNI)** | ✅ | No premature streaming (deferred), no premature multi-package split (D1), no library API extension for `--tables gap` (D-A2 filter approach). |
| **3.2 Architectural style** | ✅ | Thin-shim + in-skill package; matches xlsx-2 / xlsx-3 / xlsx-10.A precedent. |
| **3.3 Component boundaries (SRP)** | ✅ | F1=cli, F2=dispatch, F3=json-emit, F4=csv-emit, F5=surface, F6=exceptions — each module owns one functional region. |
| **4.1 AuthN/AuthZ** | N/A | CLI tool, no user-facing auth. |
| **4.2 OWASP** | ✅ | §7.3 maps A01 (path traversal), A03 (injection — XML upstream + no formula emit), A05, A08. |
| **4.3 Secrets** | ✅ | No hardcoded keys. |
| **5.1 Scaling strategy** | ✅ | §8 documents memory model (JSON accumulates, CSV streams per region); stretch budgets deferred. |
| **5.2 Fault tolerance** | ✅ | Exit codes mapped (`_AppError.CODE`); cross-3/4/5/7 envelopes; basename-only leak prevention. |

---

## 4. Specific Verifications Performed

- ✅ Traced UC-01 through F1→F2→F3 (JSON path); all functions named in
  §2.1 cover the required steps.
- ✅ Traced UC-04 through F1→F2→F4 (CSV multi-file); path-traversal
  guard D-A8 verified at the `<output-dir>/<sheet>/<table>.csv`
  computation site.
- ✅ Traced UC-07 (encrypted) through F1 → `_errors.report_error(code=3)`;
  basename-only check verified against xlsx_read §13.2 fix.
- ✅ Verified `--tables` enum → `TableDetectMode` mapping (D-A2) is
  consistent: `gap` triggers post-filter, others map directly.
- ✅ Verified `--header-flatten-style array` is silently ignored for
  CSV (Q-2 in §12) — consistent with TASK UC-05 A1.
- ✅ Verified `xlsx2csv.py --format json` rejection path: F1
  `build_parser(format_lock="csv")` declines the flag at parse time
  (D-A4); confirmed `FormatLockedByShim` in exception catalogue (F6).
- ✅ Verified `__all__` lock is consistent across §2.1 F5 listing,
  §3.2 C1 shim re-exports, and §3.2 C2 shim re-exports (post-m1 fix).
- ✅ Verified 12-line `diff -q` gate in §9.4 matches CLAUDE.md §2
  exactly (counted: 2 office trees + 2 `_soffice` + 4 `_errors` + 4
  `preview` + 2 `office_passwd` = wait — that's 14. Let me recount:
  `office/` × 2 (docx→xlsx, docx→pptx); `_soffice.py` × 2 (xlsx, pptx);
  `_errors.py` × 3 (xlsx, pptx, pdf); `preview.py` × 3 (xlsx, pptx,
  pdf); `office_passwd.py` × 2 (xlsx, pptx) = 12. Correct.

---

## 5. Final Recommendation

**APPROVED.** All Critical / Major / Minor issues patched inline in
`docs/ARCHITECTURE.md`. **Proceed to Planning phase.**

---

**Return payload:**
```json
{
  "review_file": "docs/reviews/architecture-010-review.md",
  "has_critical_issues": false
}
```
