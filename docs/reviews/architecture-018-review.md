# Architecture Review — TASK 018 (`pdf-ocr` / pdf-4)

- **Date:** 2026-06-03
- **Reviewer:** Architecture Reviewer Agent (VDD, `05_architecture_reviewer` +
  `architecture-review-checklist`)
- **Target:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (TASK 018 revision)
- **Inputs:** [`docs/TASK.md`](../TASK.md),
  [`docs/reviews/task-018-review.md`](task-018-review.md), existing pdf skill
  (`pdf_extract.py`, `html2pdf_lib/chrome_engine.py`).
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; 1 MAJOR lockstep
  fix, 3 MINOR)

---

## General Assessment

The design is appropriately small and correct for the problem. It mirrors the
established pdf-CLI shape (single file, argparse, `--json-errors`,
deterministic exit matrix), correctly classifies the new script as a
per-skill, non-replicated component (§9 — verified: imports `_errors.py`
read-only, touches no `office/` or shared helpers), and resolves both MAJOR
items the task review delegated here:

- **M-1 (exit codes) → D-A1:** the resolution is *better* than the TASK's
  tentative 11/12. Collapsing dependency failures to exit 1 + envelope
  `error_type` is correctly justified by (a) the in-skill precedent
  (`ChromeEngineUnavailable → exit 1`, confirmed at `html2pdf.py:302`) and (b)
  the principled distinction from `pdf_extract.py`'s `10 DocumentScanned`
  (a *non-failure, output-emitted* condition). YAGNI-sound.
- **M-3 (R5 scope) → D-A2:** deferring password to a dedicated post-MVP bead
  is well-reasoned — the discovery that ocrmypdf has no native input-password
  path (needs a pikepdf decrypt-to-temp pre-stage, D-A3) makes R5 genuinely a
  separate testable unit with its own temp-file security surface (S-3).

Data Model (§4): correctly scoped as a **stateless** CLI — arg record, result
record, error envelope. The checklist's DB items (3NF, indexes, migrations)
are **N/A by design** and the design says so; invariants I-1…I-3 stand in for
"business rules" and are each verifiable. Security (§7): no auth surface is
the right call for a local single-user tool; injection (S-1, Python API not
`shell=True`), secret handling (S-2 argv honest-scope), and temp lifecycle
(S-3) are all addressed. Size: 443 lines, single living doc updated in place,
no `architecture-NNN-*.md` snapshot — compliant.

---

## Comments

### 🔴 CRITICAL (BLOCKING)

None.

### 🟡 MAJOR

- **AM-1 — TASK ↔ ARCHITECTURE drift on exit codes (lockstep).** D-A1
  supersedes the new codes, but `docs/TASK.md` still encodes the old contract
  in three places: R6b ("exit map … `11` OcrEngineUnavailable / `12`
  LanguagePackMissing"), §2.7 acceptance criterion ("a missing language pack
  yields exit 12 … a missing engine yields exit 11"), and OQ-4. The RTM is the
  downstream authority for the `spec-validator`/Planner; leaving it at 11/12
  would propagate the wrong contract into PLAN and tests.
  **Fix (Architect, now):** edit TASK R6b, §2.7, and OQ-4 to the D-A1
  contract — **exit 1 + `error_type` discriminator** (`OcrEngineUnavailable` /
  `LanguagePackMissing`), `10` reserved to `pdf_extract.py`, no 11/12. Keep
  the cross-reference to ARCHITECTURE §5.2 / §12 D-A1.

### 🟢 MINOR

- **AM-2 — Verify ocrmypdf encrypted-input behavior against the pinned
  version (D-A3).** The design assumes ocrmypdf rejects encrypted input,
  motivating the pikepdf decrypt-to-temp pre-stage. This matches current
  ocrmypdf behavior (`EncryptedPdfError`), but the exact exception class and
  whether any ocrmypdf version accepts an input password should be confirmed
  when the `>=` floor is pinned (§6) — fold into bead 04. No design change
  expected; flagged so it is verified, not assumed.

- **AM-3 — `--clean` (R9) needs an `unpaper` system-binary probe, not just
  ocrmypdf import.** FC-3 only probes the `ocrmypdf` import. `--clean`
  additionally requires the `unpaper` binary, and `--rotate-pages` needs `osd`
  traineddata (already noted). Since R9 is deferred to bead 05, this is not an
  MVP gap — but bead 05 must extend the probe/validation (soft-check +
  degrade-with-warn) rather than reuse FC-3 unchanged. Note it in §11 bead-05
  scope.

- **AM-4 — Clarify `PriorOcrFound` reachability in the exit matrix (§5.2).**
  The matrix lists `PriorOcrFound` under exit 1, but the default `--skip-text`
  mode never raises it (that is the whole point of D-3). State explicitly that
  `PriorOcrFound` is reachable **only** in `--redo-ocr`/`--force-ocr` paths
  when ocrmypdf still detects a conflict — so a reader does not expect it on
  the default path. One sentence in §5.2 or FC-6.

---

## Checklist Result (`architecture-review-checklist`)

| Section | Item | Verdict |
|---|---|---|
| 1 TASK Compliance | All UCs mapped to components | ✅ (UC-1→FC-1..6; UC-2→FC-5 sidecar; UC-3→FC-1 mutex/FC-5; UC-4→FC-5 R5) |
| 1 | Non-functional constraints met | ✅ (perf §8, security §7, license/replication §9) |
| 2 Data Model | Entities/attrs/relationships | ✅ (stateless; OcrArgs/OcrResult/envelope) |
| 2 | Types correct | ✅ |
| 2 | Indexes / migrations | N/A (no persistence) — justified |
| 2 | Business rules enforced | ✅ (I-1..I-3 + mode mutex) |
| 3 System Design | Simplicity / YAGNI | ✅ (single file, D-A6) |
| 3 | Style fits problem | ✅ (thin CLI wrapper, sibling parity) |
| 3 | SRP boundaries | ✅ (FC-1..FC-6 single-responsibility) |
| 3 | Doc size ≤1500 / index | ✅ (443 lines) |
| 3 | No per-task drift / NNN snapshots | ✅ (in-place; prior epic archived in tasks/plans + git) |
| 4 Security | Auth/Authz | N/A (local CLI) — justified |
| 4 | OWASP considered | ✅ (injection S-1, secrets S-2, DoS S-4 honest-scope) |
| 4 | No hardcoded secrets | ✅ |
| 5 Scalability | Scaling strategy | ✅ (`--jobs`; honest-scope budget) |
| 5 | Fault handling | ✅ (exit matrix, atomic write I-3, exception mapping FC-6) |
| — | TASK/ARCH consistency | ⚠️ **AM-1** (exit-code drift) |

---

## Final Recommendation

**Proceed to the Planning phase (`/vdd-plan`)** after the Architect applies
**AM-1** (propagate the D-A1 exit-code contract back into `docs/TASK.md` so the
RTM and the architecture are in lockstep for the `spec-validator`). MINOR
items AM-2/AM-3/AM-4 are clarifications to fold into the relevant beads /
one-line edits; none block Planning. The `## 11. Atomic-Chain Skeleton` is a
clean Stub-First handoff for the Planner.
