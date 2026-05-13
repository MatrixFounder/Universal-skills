# Architecture Review — §15 xlsx-8a Production Hardening (TASK 011)

- **Date:** 2026-05-13
- **Reviewer:** Architecture Reviewer (subagent invocation, VDD
  start-feature workflow)
- **ARCHITECTURE file:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
  §15 only (lines ~1231–1468). §1–§14 are out of scope.
- **TASK file:** [`docs/TASK.md`](../TASK.md) (TASK 011)
- **Backlog row:** `xlsx-8a` (line 198 of
  `docs/office-skills-backlog.md`)
- **Status:** **APPROVED WITH COMMENTS** (2 MAJOR + 3 MINOR; no
  blocking issues)

---

## 1. General Assessment

§15 is a tight, well-bounded additive specification. The five fixes
are atomic, the carve-out from the §9.1 xlsx-10.A frozen surface is
genuinely narrow (3 files, additive only, no public-API mutation),
backward compatibility is preserved by defaults, and the
decision-record extension (D-A11..D-A14) is consistent with the
existing D-A1..D-A10 style. Cross-references back to §14.7 and into
TASK.md / `KNOWN_ISSUES.md` are present and mostly correct.

The data model deltas are minimal and orthogonal: two typed
exceptions inheriting the correct bases (`RuntimeError` for the
library-internal `TooManyMerges`, `_AppError` with `CODE = 2` for
the shim-layer `CollisionSuffixExhausted`). The exception hierarchy
aligns with the existing `OverlappingMerges` (library,
`RuntimeError`) and `OutputPathTraversal` (shim, `_AppError,
CODE = 2`) precedents — no envelope-contract violation.

Security coverage is correct in substance: OWASP-canonical
sentinels, RFC-3986-aligned case-insensitive scheme matching,
fail-loud caps, explicit-allowlist-only policy with no `*`
shorthand. Two cross-link / consistency defects warrant correction
before Planning starts, but none are load-bearing — no entity
invariants, no public surface mutations, no security regressions.
The carve-out into the "frozen" xlsx_read surface is justified,
bounded, and consistent with the backlog row's explicit re-opening
of those three files for this defect class.

No 🔴 CRITICAL / BLOCKING issues. Two 🟡 MAJOR comments and three
🟢 MINOR comments below. One **cross-cutting note** on a stale TASK
UC-03 acceptance reference (architect's responsibility to fix while
in the same pass).

---

## 2. Comments

### 🔴 CRITICAL (BLOCKING) — none.

### 🟡 MAJOR

#### M1 — §15.4 mis-cites D-A13 for the path-validator Unicode-norm row

**Section affected:** `docs/ARCHITECTURE.md` §15.4, "Unicode-norm
bypass in path-validator" row (line ~1340).

The §14.7 "Unicode normalization in path validator" item is about
sheet-name reject-list bypass via U+2024 (`․`, one-dot-leader) and
U+FF0E (`．`, fullwidth full stop) NFKC-folding to `..`. §15.4
attributes it to "D-A13 caveat: out of scope here". But D-A13
(lines 1318–1324) is about **formula-escape Unicode lookalikes**
(e.g. `＝` U+FF1D fullwidth equals) — a completely different class
of Unicode bypass. The path-validator Unicode case has no decision
number attached to it in §15. A future reader will follow D-A13
expecting path-validator context and bounce.

**Recommended fix:** either (a) tag the §14.7 item "Still accepted
— not addressed by xlsx-8a; defense-in-depth via
`is_relative_to(output_dir)` continues to catch the resulting path.
**No decision number** — out of scope for this iteration", or (b)
add a fifth decision `D-A15` explicitly accepting this. Without
one of these, the citation is misleading.

#### M2 — §14.7 items lack stable numeric IDs for §15.4 cross-reference

**Sections affected:** `docs/ARCHITECTURE.md` §14.7 (5 bullets) and
§15.4 status table (column 1).

The two "Closed" rows (CSV-injection, javascript-URI) cite the
relevant decisions (R4/D-A13, R3/D-A11/12), but the table presents
the §14.7 ↔ §15.4 mapping as text rather than as a strict 1:1
cross-link with `§14.7-Nth` anchors. Not strictly wrong — the
table headers do match (§14.7 "Accepted-risk items NOT fixed in
this iteration" ↔ §15.4 "Status after xlsx-8a") — but Planner /
Developer downstream will benefit if each row carries a stable
identifier (e.g. `§14.7.1`..`§14.7.5`) so the regression checklist
in §15.6 can grep-cite which §14.7 item every R-* requirement
closes.

**Recommended fix:** add per-item numeric IDs in §14.7
(`14.7.1` Unicode-path-validator, `14.7.2` CSV-injection,
`14.7.3` javascript:/data: URIs, `14.7.4` JSON-full-payload-
materialisation, `14.7.5` TOCTOU race) and reference them in §15.4
column 1. Low effort, high traceability payoff.

### 🟢 MINOR

#### m1 — §15.5 cross-skill-replication claim could be paired with an explicit dev-time checklist line

§15.5 says "Cross-skill replication: NONE." Implicit — explicit is
better. Suggest adding to §15.6 Regression gate: "12-line cross-
skill `diff -q` gate from §9.4 silent — none of `office/`,
`_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py` is
touched." Paper-cut hygiene.

#### m2 — D-A12 (OWASP URL-schemes rationale) could name a concrete reference link or version

D-A12 (lines 1307–1316) asserts the `http,https,mailto` default
matches OWASP guidance but doesn't link to a specific OWASP Cheat
Sheet. Not a blocker — but a single URL or section number would
prevent the next reviewer from re-litigating which OWASP doc the
default comes from.

#### m3 — Open Question Q-15-1 (env-var tuning) precedent citation could be tightened

Q-15-1 cites `_GAP_DETECT_MAX_CELLS = 1_000_000` as the precedent.
The parallel is correct, but readers may want a one-line citation
`(xlsx-10.A §honest-scope (e)?)` so the reasoning is verifiable.
Minor — not blocking.

### Cross-cutting note — TASK UC-03 acceptance test reference is stale

**Section affected:** `docs/TASK.md` UC-03 acceptance criterion
`test_hyperlink_scheme_javascript_blocked`. Wording flagged during
arch-review cross-check.

The TASK now locks **D7** (blocked-scheme cells emit bare scalar,
NOT `{value, href: null}`), and §15.6 R3 reflects this correctly
("asserts JSON output is bare scalar, not `{value, href: null}`").
But UC-03 acceptance criteria list (in TASK §3) earlier described
the blocked test in terms of the rejected shape. Architect should
sweep TASK.md UC-03 acceptance bullets to ensure the bare-scalar
assertion is the canonical wording — flag for Planning hand-off.

---

## 3. Final Recommendation

**APPROVED WITH COMMENTS.** The Architect should: (1) **fix M1** by
either dropping the spurious "D-A13" reference on the §15.4
Unicode-path row or adding a new `D-A15` that explicitly accepts
the path-validator Unicode-norm risk; (2) **address M2** by tagging
each §14.7 item with a stable numeric ID so §15.4 and §15.6 can
reference them precisely. The three 🟢 minors are
quality-of-life and may be picked up alongside M1/M2 or left for
the next iteration. No blocking issues; Planner may proceed once
M1 + M2 land. The carve-out from §9.1 frozen surface is acceptable
and properly scoped to the three named files.

```json
{"has_critical_issues": false}
```
