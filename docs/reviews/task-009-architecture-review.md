# Architecture Review — Task 009 (`xlsx-10.A` `xlsx_read/` library)

- **Date:** 2026-05-12
- **Reviewer:** Architecture Reviewer (self-review pass)
- **Target:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — DRAFT v1
- **Checklist:** `architecture-review-checklist` (v1.0)
- **Status:** ✅ **APPROVED — NO BLOCKING ISSUES**

## General Assessment

Architecture is **a new in-skill Python package** (7 modules + 1
toolchain config + 4 modified support files). Follows the same
pattern proven by `xlsx_check_rules/` (xlsx-7), `json2xlsx/`
(xlsx-2), `md_tables2xlsx/` (xlsx-3) and `xlsx_comment/` (xlsx-4).
Closed-API surface enforced via `ruff` banned-api (D5) is the
distinguishing architectural feature — it is the **single
guarantee** that allows future refactor (xlsx-10.B) without
breaking callers.

All 8 architect-locked decisions (D-A1 – D-A8) close the
non-blocking Open Questions from TASK §7.2 with rationale. Honest-
scope items HS-1 – HS-6 prevent scope-creep (no runtime
enforcement, no telemetry, no wheel distribution).

## Comments

### 🔴 Critical — none
### 🟡 Major — none
### 🟢 Minor — none

## Item-by-item checklist

| § | Item | Status |
| --- | --- | --- |
| 1 | **TASK Coverage:** all UCs → components | ✅ UC-01→F1, UC-02→F2, UC-03→F4 (+F3/F5), UC-04→F3/F5/F6, UC-05→D7+§3.1 doc, UC-06→C2 (pyproject.toml banned-api) |
| 1 | **NFR coverage:** perf, security, thread-safety, maintainability | ✅ §8 perf budget, §7 threat model, D7 thread-safety, HS-1..HS-6 |
| 2 | **Data Model completeness** | ✅ SheetInfo, TableRegion, TableData + 3 enums (MergePolicy, TableDetectMode, DateFmt) + 5 typed exceptions |
| 2 | **Data types valid** | ✅ Literals for enums, Path for filesystem, Python primitives only at public surface |
| 2 | **Indexes** | N/A — no persistent storage (read-only library) |
| 2 | **Migrations** | N/A — no schema |
| 2 | **Business rules** | ✅ Tier-1 wins on overlap (UC-03 A4); workbook-scope ranges dropped (D8); rectangular invariant on TableData; frozen-outer/mutable-inner contract documented (D3) |
| 3 | **Simplicity / YAGNI** | ✅ 7 modules × ~one responsibility each; no premature caching (LRU explicitly deferred §8); no `__getattr__` magic (HS-1); no runtime enforcement (HS-5) |
| 3 | **Style matches problem** | ✅ Layered in-skill package; mirrors xlsx-7 proven precedent |
| 3 | **SRP boundaries** | ✅ Each F1–F7 region == one module; closed-API at F7; library-boundary at D-A7 |
| 4 | **Authentication / Authorization** | N/A — no network, no users; trust boundary is the input `.xlsx` file (§7.1) |
| 4 | **OWASP Top-10 considered** | ✅ §7.3 maps A03 (XML injection — `resolve_entities=False`), A05 (lxml misconfig — explicitly configured), A08 (data integrity — stale-cache detection) |
| 4 | **No hardcoded secrets** | ✅ No credentials in design |
| 5 | **Scaling strategy** | ✅ Per-thread `WorkbookReader` instances (L2 fix); `read_only=True` auto-mode for > 10 MiB (D-A6) |
| 5 | **Fault handling** | ✅ Typed exceptions §5.3; soft-warnings via `warnings.warn`; `OverlappingMerges` fail-loud; stale-cache always surfaced |
| 9 | **CLAUDE.md §2 boundary** | ✅ §9 enumerates 12 files MUST-NOT-modify + 12-line `diff -q` gate must remain silent |

## Cross-Document Coherence

- **TASK ↔ ARCH:** Every TASK RTM row (R1–R13) maps to an ARCH
  component or section:
  - R1 → §2.1 F7 + §5.1
  - R2 → §3.2 C1 + C2 + §10 HS-1
  - R3 → §2.1 F1 + §3.2 C2/C3/C4
  - R4 → §2.1 F2
  - R5 → §2.1 F4
  - R6 → §2.1 F3/F5/F6 + §5.1
  - R7 → §2.1 F5
  - R8 → §2.1 F6
  - R9 → §2.1 F3
  - R10 → §5.3
  - R11 → §4.1 (Entities) + D3
  - R12 → §3.2 C5/C6 + §1.4(i)/(j)
  - R13 → §11 (atomic chain) + TASK §5.5 (30 E2E)
- **D-A1 – D-A8:** Each architect decision either closes a TASK
  Open Question (Q-A1→D-A1, Q-A2→D-A2, Q-A3→D-A3, Q-A4→D-A4,
  Q-A5→D-A5) or adds an unprompted but necessary design lock
  (D-A6 read_only threshold, D-A7 IO contract, D-A8 M8 spike
  scheduling).

## Final Recommendation

**Proceed to Planning phase.** No critical, major, or minor issues
block the handoff. The atomic-chain skeleton (§11) provides 8
clean sub-tasks for the Planner; Stub-First gate is defined per
sub-task.
