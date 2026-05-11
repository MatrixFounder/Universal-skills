# Task 004 Review — `xlsx-2 / json2xlsx.py`

- **Date:** 2026-05-11
- **Reviewer:** task-reviewer subagent
- **Target:** `docs/TASK.md` (Task 004, slug `json2xlsx`)
- **Status:** **APPROVED WITH COMMENTS** (round 1) → **resolved** after fixes M1/M2/M3 + minor promotions (see §"Resolution" below).

---

## General Assessment

Strong v1 draft. RTM is granular (R1–R13, every row 3–7 sub-features, MVP-flagged). D1–D5 are properly locked with provenance (`/vdd-start-feature` Q&A 2026-05-11). All 5 UCs carry Actors / Preconditions / Main / Alt / Post / AC. Cross-cutting boundary is correctly observed — no new shared `office/` / `_errors.py` / `preview.py` edits (C2/C3). Effort S→M is honestly disclosed with provenance. The xlsx-8 coupling (D4/O1/UC-5) is split cleanly between synthetic-now and live-later.

One material defect (M1 — cross-5 envelope shape mismatch), one technically-incorrect claim (M2 — `OrderedDict.fromkeys()` defence), and one missing section (M3 — Honest Scope §11) need correcting before Architecture phase. Minor items are cheap tightenings.

---

## 🔴 CRITICAL (BLOCKING)

*(none)*

---

## 🟡 MAJOR

### M1 — Envelope shape in UC-4 and §8 example contradicts the frozen `_errors.py` contract

- **Where:** §3 UC-4 Main/Alt + §8 Exit-codes worked example.
- **Finding:** TASK uses `{ok, code, type, message, details}` but `skills/xlsx/scripts/_errors.py:39,126-138` emits `{v: 1, error, code, type?, details?}`. Fields differ: `v: 1` (schema version, always present, missing from TASK), `error` (NOT `message`), and there is no `ok` key. The xlsx-6 findings envelope (`{ok, summary, findings}`) is a different payload — it is xlsx-6's batch input/output, not the cross-5 error envelope. Conflating the two is the same trap M2 caught in Task-003 (`docs/reviews/task-003-review.md`).
- **Why it matters:** Developer would code `envelope["message"] = msg` against `_errors.py`'s `error` field; xlsx-2's E2E (R11.b) would pass against a hand-rolled envelope but agent wrappers reading `head -1 stderr | jq '.error'` would break. UC-4 AC ✅ *"Envelope contains `ok, code, type, message, details`"* would never be true with the real helper.
- **Fix:** Replace UC-4 AC + §8 example with the actual cross-5 shape `{v: 1, error, code, type, details}`. Update UC-4 AC bullets to: `v: 1`, `error`, `code`, `type`, `details` (drop `ok`, `message`). Add R8.a sub-bullet pinning the schema.

### M2 — R7.c claim about Python `OrderedDict.fromkeys()` defence is technically incorrect

- **Where:** R7.c sub-feature.
- **Finding:** R7.c says *"defence-in-depth: explicit guard via `collections.OrderedDict.fromkeys()` on the JSON parse path"*. But `json.loads()` returns a normal `dict` whose keys are already deduplicated by the JSON parser (last-wins per RFC 8259 §4); by the time `OrderedDict.fromkeys()` runs there is nothing to detect. Duplicate-key detection in JSON requires `object_pairs_hook=lambda pairs: …` to inspect the raw `(key, value)` tuples **before** dict construction. UC-2 Alt-A2 even acknowledges this honestly, which contradicts R7.c.
- **Fix:** Drop the "defence-in-depth" claim (matches UC-2 Alt-A2 stance, simplest). Document the limitation in §11 Honest Scope. Promote `object_pairs_hook` to v2 follow-up.

### M3 — TASK references "Honest Scope §11" four times but no §11 section exists

- **Where:** R4.e, §4.2 (twice), C7, O4 — all cite §11.
- **Finding:** Document stops at §8. Without §11 the Architect cannot lock the honest-scope contract; this is the same locking convention used by xlsx-6 m4 / xlsx-7 R13.l.
- **Fix:** Add §11 "Honest Scope" with seven bullets: aware datetime → naive UTC; leading `=` passthrough; 100K-row write-only deferred; sheet-name auto-sanitization NOT in v1; duplicate top-level keys collapsed (M2); TOCTOU symlink race out of scope (parity with xlsx-7 m6); cell-value `=cmd|…` not auto-escaped.

---

## 🟢 MINOR

- **m1** — D4 references xlsx-8 backlog as source of truth for round-trip JSON shape, but backlog row is narrative-loose: doesn't freeze `--sheet all` key naming, null-cell representation, or header-row handling. Without freezing the contract before xlsx-8 lands, `T-roundtrip-xlsx8-live` will require xlsx-2 code change — contradicting UC-5 AC. **Fix:** add explicit contract-freeze sub-task at end of atomic chain (or `skills/xlsx/references/json-shapes.md`).
- **m2** — R11.e cites "csv2xlsx 10K-row benchmark" but csv2xlsx has no committed perf test. Rephrase as informal target on the same fixture-runner machine as xlsx-7 100K-row benchmark.
- **m3** — O2 (`--input-format` flag) Proposal *"defer to v2"* is essentially already a decision. Promote to D6 in §0, remove from §6.
- **m4** — O5 (`--strict-dates` rejects aware datetimes) Proposal converges; promote to D7. Reconcile with R4.e by adding R4.g.
- **m5** — LOC estimate (~1620) is plausible for "M" effort but high; 8–12 sub-tasks × ~150 LOC = 1800. Internally consistent. Worth confirming with the Planner.
- **m6** — R12.b assumes `skills/xlsx/SKILL.md` has §1 "Red Flags" section. **Verified present** (`skills/xlsx/SKILL.md:18`).

---

## Open Questions Audit (O1–O6)

| Q | Verdict |
|---|---|
| O1 (xlsx-8 test ownership) | Could lock now (cheap). |
| O2 (`--input-format` flag) | Already resolved (m3) — promote to D6. |
| O3 (`--strict-schema`) | Correct — defer to v2. |
| O4 (write-only mode) | Correct — perf-dependent. |
| O5 (timezone rejection under `--strict-dates`) | Converges — promote to D7 (m4). |
| O6 (leading `=` escape) | Correct — csv2xlsx parity argument sound. |

None are user-blocking; O1/O2/O5 could be pre-locked to reduce Architect's lift.

---

## Cross-checks Summary

- ✅ CLAUDE.md §2 4-skill replication boundary (R13.b, C2/C3 explicit; no shared module edits).
- ❌ cross-5 envelope shape (M1).
- ✅ cross-7 H1 same-path guard (R8.b mirrors `office_passwd.py:130`).
- ✅ Post-validate hook truthy allowlist (R10 mirrors `xlsx_comment/cli_helpers.py:121-133`).
- ✅ Dependencies (`openpyxl`, `pandas`, `python-dateutil` in `skills/xlsx/scripts/requirements.txt:1-9`; no new deps).
- ✅ License hygiene (xlsx proprietary; no third-party additions).
- ◔ xlsx-8 input contract (m1).
- ❌ §11 Honest Scope (M3).
- ❌ R7.c duplicate-sheet defence claim (M2).

---

## Final Recommendation

**APPROVED WITH COMMENTS** — proceed to Architecture phase after addressing M1 / M2 / M3 in-place, and promoting m3 / m4 to D6 / D7. After fixes, Architect picks up O1, O3, O4, O6 (m1 sub-task added during Architecture).

---

## Resolution

Orchestrator (2026-05-11) applied the following edits to `docs/TASK.md`:

1. **M1 fixed.** UC-4 AC + §8 example rewritten to `{v: 1, error, code, type, details}`. New R8.a sub-bullet pins cross-5 schema with explicit "do NOT introduce `ok` / `message`" guard.
2. **M2 fixed.** R7.c rewritten to drop the `OrderedDict.fromkeys()` claim; reality (json.loads last-wins) documented in §11.
3. **M3 fixed.** §11 "Honest Scope" added with the 7 enumerated bullets.
4. **m3 promoted to D6.** O2 removed from Open Questions; `--input-format` flag formally deferred to v2.
5. **m4 promoted to D7.** O5 removed from Open Questions; R4.g added pinning the `--strict-dates` → `TimezoneNotSupported` contract.
6. **m1 captured as Planning-phase action.** New entry in §7 Definition of Done tracks the `skills/xlsx/references/json-shapes.md` contract-freeze sub-task at end of atomic chain.
7. **m2 rephrased** ("csv2xlsx 10K-row benchmark" → "same fixture-runner machine as xlsx-7 100K-row benchmark").
8. **m6** verified — no edit needed.

Status: **APPROVED — ready for Architecture phase**. `has_critical_issues: false`.
