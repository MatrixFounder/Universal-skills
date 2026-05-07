# Architecture Review — `docs/ARCHITECTURE.md` (xlsx-6)

**Date:** 2026-05-07
**Reviewer:** architecture-reviewer agent (subagent)
**Status:** **APPROVED WITH COMMENTS** — proceed to Planning phase, fold the Major comments below into PLAN.md (or a quick ARCHITECTURE.md cleanup) before development.

---

## General Assessment

The architecture cleanly closes the three Open Questions handed off from the Analyst (Q2 reject-empty, Q5 dual default+override, Q7 Option-A Excel-365 fidelity) with rationale tied to the docx parity precedent and the backlog's "personList obligatory" wording. The component decomposition F1–F6 maps 1:1 to the TASK use cases, the single-file vs sub-package decision is correctly grounded in the CLAUDE.md §2 byte-identical-replication burden (helpers stay in `xlsx_add_comment.py`, NOT promoted to `office/`), and §4.2's invariants list correctly preserves the C1 distinction (idmap workbook-wide vs spid per-shape) and the M6 workbook-scoped vs sheet-scoped split. Where the document leaves work to do is one Major OOXML-correctness gap (`<o:idmap data>` is a *list*, not a scalar — see M-1; same family as round-1 C1), one Major Q7-closure ambiguity (`--no-threaded` × thread-already-exists matrix is under-specified — M-2), and three Minor open-question housekeeping issues. The data model and ER diagram are correct; the security section is adequate for a non-network single-file CLI; YAGNI is respected throughout.

---

## Critical Issues

*(none)*

M-1 is on the boundary of Critical because it can produce silently corrupt output, but it can be locked in PLAN.md as an explicit parsing rule without touching the architecture itself.

---

## Major Issues (fix before Planning, otherwise risk re-work in Developer phase)

### M-1 — `<o:idmap data>` is a comma-separated LIST per ECMA-376, not a scalar integer

**Where:** §2.1 F4 (`scan_idmap_used(tree) -> set[int]`), §3.2 S2 reference doc, §4.1 VmlDrawing entity, §4.2 invariant 3.

**Problem:** The round-1 task-review C1 explicitly states the `data` attribute is *"a comma-separated list of integer shape-type IDs that this drawing claims, used by Word/Excel to namespace shape IDs across multiple VML parts in one document."* The architecture treats `data` as a scalar `data="N"`. In practice Excel-emitted VML for a single comments-bearing sheet often has `data="1"` (one block), so a naive scalar implementation will *appear* to work on synthetic fixtures and silently corrupt workbooks where Excel itself wrote `data="1,2"` (two blocks claimed by one drawing — heavily-edited workbooks).

**Required fix:**
1. `scan_idmap_used` parses `<o:idmap data>` as `[int(x) for x in attr.split(",")]`, unioning into the workbook-wide set. Architecture §2.1 F4 should change `set[int]` semantics to "all integers claimed across all `<o:idmap data>` lists in the workbook".
2. On write, emitting a single integer per part is acceptable (xlsx-6 only ever creates one block per part); document the read-vs-write asymmetry in §4.1 VmlDrawing business rules.
3. `comments-and-threads.md` (§3.2 S2) MUST document the list-vs-scalar asymmetry.
4. PLAN.md AC: unit test for `scan_idmap_used` on synthetic VML with `<o:idmap data="1,5,9"/>` → `{1, 5, 9}`; E2E fixture where input has multi-claim `data` list and xlsx-6 allocates a fresh integer disjoint from the entire list.

### M-2 — Q7 closure is incomplete: `--no-threaded` × thread-already-exists matrix is under-specified

**Where:** §6 Q7 row, second-to-last sentence: *"R5.c 'thread already exists on cell' → append to threaded; if `--threaded` and cell has only legacy → write both parts (creating a new thread on that cell)."*

**Problem:** Three sub-cases need to be enumerated; only two are clear.

| Cell state on input | `--threaded` | `--no-threaded` |
|---|---|---|
| Empty | Write legacy + threaded ✓ | Write legacy only ✓ |
| Legacy only | Write both — but does existing legacy `<comment>` body get a matching threaded entry? Or fresh thread? | exit 2 `DuplicateLegacyComment` (R5.b) ✓ |
| Threaded thread exists | Append to thread ✓ | **UNDEFINED** |
| Threaded only (no legacy stub) | Append to thread ✓ | **UNDEFINED** |

The two `--no-threaded` UNDEFINED cells are precisely where R5.c was deferred in the TASK ("once Q7 is closed in ARCHITECTURE.md it becomes a corollary, not a free-standing rule"). Q7 closes but does NOT spell out the corollary.

**Required fix:** Add an explicit table to §6 (or new §6.1) enumerating all four `(cell-state, --threaded/--no-threaded)` combinations with chosen behaviour. **Recommendation, consistent with Option A's "fidelity" framing:** `--no-threaded` × thread-exists → exit 2 `DuplicateThreadedComment` (NEW envelope; TASK §2.5 exit-code 2 list will need updating in the cleanup). Silently writing legacy-only alongside an existing thread is the worst of both worlds.

### M-3 — A-Q1 (fixture provenance) and A-Q2 (`--no-threaded` default) should be locked, not deferred to user

**Where:** §7 Open Questions, A-Q1 and A-Q2.

**Problem:** A-Q2 in particular is not really open — backlog says threaded is "опц." (optional), docx parity precedent has non-threaded default, and §6 Q7 rationale already cites this. "Confirm or override" creates a gate the user has no useful additional information to resolve. A-Q1 is similar: "generate fixtures by opening Excel-365" is the only sensible answer.

**Required fix:** Demote A-Q1 and A-Q2 to "Architect-locked decision; user may override before development if desired." A-Q3 is already correctly marked as PLAN-internal.

**Optional:** §11 currently duplicates §7. Either delete §7 (keep §11) or add `> See §11` cross-reference in §7. Template-clutter, not correctness.

---

## Minor Issues (do not block Planning)

### m-1 — `<v:shape id="_x0000_s2049+">` lower-bound from round-1 AC missing

**Where:** §4.1 VmlDrawing, §4.2 invariant 4. TASK round-1 AC said "shape IDs in `_x0000_s2049+` range" (Excel's per-drawing 1024-stride convention). Architecture says "max+1 workbook-wide". Both valid. PLAN.md picks one.

### m-2 — F2 `details.suggestion` case-insensitivity scope

**Where:** §2.1 F2 `resolve_sheet`. Add docstring clarification: "Case-insensitive scan is performed *only* to populate `details.suggestion`; resolution remains case-sensitive."

### m-3 — `Default Extension="vml"` vs per-part `<Override>` idempotency

**Where:** §4.1 ContentTypes business rule. PLAN.md AC: "fixture with pre-existing `Default Extension="vml"`: xlsx-6 does not add a redundant per-part `<Override>`."

### m-4 — 8 MiB stdin cap exact-boundary behaviour

**Where:** §5. PLAN.md picks one (recommend `read(8 * MiB + 1)` then `if len > 8 * MiB`). Trivial.

### m-5 — A-Q3 goldens diff: `c14n` vs `c14n2`

**Where:** §7 A-Q3. `c14n2` does NOT canonicalise attribute order; `c14n` (1.0) does. Recommend `method='c14n'` for golden comparison. PLAN.md detail.

---

## Verification of gate criteria

| Question | Verdict |
|---|---|
| §4.2 invariants consistent with C1? | ✅ except idmap-as-scalar — see M-1 |
| `personList` workbook-scoped vs `threadedComment` sheet-scoped (M6)? | ✅ |
| Dedup case-sensitive on `displayName` everywhere? | ✅ |
| ER relationships (1:N, 0..1) correct? | ✅ |
| Q2/Q5/Q7 closed with rationale? | ✅ |
| A-Q1..A-Q3 genuinely user-facing? | ❌ A-Q1, A-Q2 over-cautious (M-3); A-Q3 correctly internal |
| F1..F6 coherent, no double-handling? | ✅ |
| Single-file justification holds? | ✅ — CLAUDE.md §2 grounding is correct |
| Helpers correctly NOT promoted to `office/`? | ✅ |
| Input-validation boundary clear? | ✅ — `office/unpack` + `defusedxml` |
| 8 MiB cap pre-parse (m2)? | ✅ (boundary in m-4) |
| OWASP coverage adequate? | ✅ — A03/A04/A06/A08 mapped; A02/A05/A07/A09/A10 N/A |
| Over/under-engineering? | ✅ — clean, no abstractions |
| TASK Use Cases mapped to components? | ✅ |

---

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Planning phase.**

The Architect should fold M-1, M-2, M-3 into a quick ARCHITECTURE.md cleanup before Planning starts (data-model semantics + §6 closure table + open-question demotion). M-1 in particular MUST be picked up somewhere — it's the same OOXML-pitfall family as round-1 C1 and is exactly what this gate exists to catch. Minor m-1..m-5 are PLAN.md details.

```json
{ "review_file": "docs/reviews/architecture-001-review.md", "has_critical_issues": false }
```
