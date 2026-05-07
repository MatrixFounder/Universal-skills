# Task Review — `docs/TASK.md` (xlsx-6 `xlsx_add_comment.py`)

**Date:** 2026-05-07
**Reviewer:** task-reviewer agent
**Status:** **BLOCKING** (critical OOXML mapping error + missing CLI surface contract) — round 1

## General Assessment

The TASK is unusually thorough for an Analysis-phase artifact: the RTM decomposes 10 requirements into ~50 sub-features all traceable to use cases and E2E fixtures, the cross-3/4/5/7 contracts mirror `docx_add_comment.py` faithfully, and the v1 honest-scope list (R9) reproduces all four backlog non-goals. Where it earns BLOCKING is one substantive technical error (`o:idmap` vs `o:spid` conflation — the exact class of subtle OOXML mistake the gate exists to catch), one analyst-introduced contract that isn't in the backlog and that materially changes the threaded write path (R3.a/I1.4 "always also write the legacy `<comment>`"), and a missing consolidated CLI flag table — at least four flags (`--legacy-only`, `--default-threaded`, `--allow-merged-target`, `--date`) are referenced in prose but never declared, leaving the developer to reverse-engineer the argparse surface. Open Questions Q2 and Q5 are correctly marked as architecture-blockers; the rest are tractable as ARCHITECTURE.md defaults. With C1–C3 fixed, this would be one of the cleaner xlsx TASKs in the project; the bones are right.

---

## Critical Issues (must fix before Architecture phase)

### C1 — `o:idmap` is conflated with `o:spid` / shape-ID throughout RTM and ACs

**Where:** R1.h ("non-colliding `o:idmap` and shape-ID"), I1.3.4 ("`o:idmap` is collision-free"), I1.3 AC ("no o:idmap collision"), I2.3 main-scenario ("Pre-scan existing `o:idmap` and shape-ID values"), I2.3 AC ("no two `<v:shape>` share `o:idmap`").

**Problem:** In OOXML/VML, `o:idmap` lives on the **`<o:shapelayout><o:idmap v:ext="edit" data="1,2,3"/></o:shapelayout>`** element at the root of `xl/drawings/vmlDrawingK.xml`. Its `data` attribute is a **comma-separated list of integer shape-type IDs that this drawing claims**, used by Word/Excel to namespace shape IDs across multiple VML parts in one document. Per-shape uniqueness lives on `<v:shape id="_x0000_s1025" ...>` (the `id` / `o:spid` attribute). The TASK's wording "no two `<v:shape>` share `o:idmap`" is structurally meaningless — shapes don't have `o:idmap`, they have `o:spid`. This is the exact subtlety the user warned about (and historically wrong in real implementations).

**Required fix:** Replace every "`o:idmap`" mention in R1.h, I1.3, I1.3-ACs, I2.3, I2.3-ACs with the precise pair:
- "`<o:idmap data="N">` value at `<o:shapelayout>` root — must be free of any `data` value already used by other `vmlDrawing*.xml` parts in the workbook (workbook-wide scan)";
- "`<v:shape id="_x0000_sNNNN" o:spid=...>` — per-shape integer NNNN must not collide with any existing shape ID across all VML parts in the workbook".

Add a dedicated AC: **"E2E `idmap-conflict` fixture: workbook with pre-existing `vmlDrawing1.xml` having `<o:idmap data="1"/>` → adding a comment to a different sheet allocates `<o:idmap data="2"/>` (or higher) AND uses shape IDs in the `_x0000_s2049+` range so no collision against existing `_x0000_s1025`."**

### C2 — Threaded write contract introduces a backlog deviation that isn't justified

**Where:** I1.4 main-scenario step 1 — *"Always also write the legacy `<comment>` (Excel renders both; legacy is the fallback for older clients)."*

**Problem:** The backlog row does NOT mandate this. The backlog says: "опц. `xl/threadedCommentsM.xml` + `xl/persons/personList.xml` (modern threaded для Excel 365 — без personList Excel не отрендерит thread, **обязательная часть pipeline**)". "Обязательная часть pipeline" refers to **personList** being mandatory *when threaded is used*, not to legacy being mandatory *alongside* threaded. The analyst's "always also write legacy" claim is plausible Excel-365 behaviour (Excel itself does write a legacy stub when it creates a threaded comment), but it changes the surface area of `--threaded`, the meaning of `--legacy-only` (R5.b), and the duplicate-cell semantics of R5.c (which depends on whether *both* parts are present). It needs an explicit decision:

- Option A: `--threaded` writes BOTH legacy + threaded parts (Excel-365 fidelity). Then `--legacy-only` is redundant — rename to `--no-threaded` or drop.
- Option B: `--threaded` writes ONLY threaded + personList. Then R5.c "Mixed legacy+threaded already on the cell" path is a *workbook-state*, not an output mode, and needs a different rule.

**Required fix:** Promote this to a **new Open Question Q7** ("Threaded mode write semantics — both parts or threaded-only?") and mark it as architecture-blocker alongside Q2/Q5. Update I1.4 to be neutral ("write threaded + person; **legacy stub written only if backlog-fidelity flag is enabled** — see Q7") OR remove the "always also write legacy" sentence and re-validate R5.b/c against the chosen branch.

### C3 — No consolidated CLI flag surface; ≥ 4 flags referenced but never declared

**Where:** Throughout §3 (Epics) the prose names CLI flags that have no declaration anywhere:
- `--legacy-only` (R5.b, "Legacy-only mode")
- `--default-threaded` (R4.c, I2.2)
- `--default-author` (R4.c, I2.2 — declared as "REQUIRED with envelope shape" but never listed in a flag table)
- `--allow-merged-target` (R6.b, I1.5.A1.5.b)
- `--date` (Q5 recommendation; nothing in §3)
- `--cell` (everywhere, but mutex with `--batch` is never stated)

**Problem:** The TASK has no §3.0 "CLI surface" / argparse table comparable to docx_add_comment.py's `parser.add_argument` block. Developers will reconstruct the flag set from prose, miss flags, or re-litigate semantics in the implementation phase. The docx reference parity demands a flag list (docx has it implicit in its argparse block, but in a TASK doc it must be explicit).

**Required fix:** Add §2.5 (or §3.0) **"CLI surface (authoritative flag table)"** with rows: flag name, type, default, required-when, mutex group, brief description. Must enumerate at minimum: `INPUT`, `OUTPUT`, `--cell`, `--author`, `--text`, `--initials`, `--threaded`, `--legacy-only`, `--date`, `--batch`, `--default-author`, `--default-threaded`, `--default-initials` (Q1), `--allow-merged-target`, `--json-errors`. Mutex groups: (`--cell` XOR `--batch`), (`--text`+`--author` required when `--cell`, `--default-author` required when `--batch` is envelope-shape), (`--threaded` XOR `--legacy-only`).

---

## Major Issues (should fix before Architecture, otherwise risk re-work)

### M1 — R8.d idempotency claim is internally inconsistent

R8.d states "Re-running the script ... never produces a corrupt file (deterministic where possible — UUIDs derived via UUIDv5 are stable; shape-IDs are picked deterministically by max+1)." But I1.4 step 3 specifies `id="{UUIDv4}"` on `<threadedComment>` — UUIDv4 is non-deterministic. So re-running on identical input produces a workbook with different `<threadedComment id>` values. That's tolerable behaviour, but the wording "deterministic where possible" hides a substantive non-determinism the developer must implement. **Fix:** add to R9 honest-scope: *"(e) `<threadedComment id>` is UUIDv4 — re-running produces non-byte-equivalent output even with `--date` pinned. UUIDv5 is reserved for `<person id>` (stable on `displayName`) where stability matters for Excel-365 thread linkage."*

### M2 — "First sheet" rule incomplete: hidden / `state="veryHidden"` not addressed

§5 Assumptions says "First sheet = `<sheet>` order in `xl/workbook.xml`, not alphabetical". But `<sheet>` elements carry `state="hidden"` / `state="veryHidden"`. Adding a comment to a hidden sheet is legal but probably not what the user wants when they pass `--cell A5` (no sheet qualifier). **Fix:** clarify in I1.1 main-scenario step 3 — either "first visible sheet" (mirrors xlsx-7's `--include-hidden` flag pattern) or "first sheet regardless of `state`, with a stderr info-level note when target is hidden". Add an E2E fixture for hidden first sheet.

### M3 — Sheet-name resolution case-sensitivity unspecified

§I1.1 alternatives don't say whether `--cell sheet2!B5` (lowercase) matches `<sheet name="Sheet2">`. Excel's UI is case-insensitive on sheet names but case-preserving on storage; tooling typically does case-sensitive lookup. **Fix:** add A1.1.f ("`--cell sheet2!A1` against `<sheet name="Sheet2">` → exit 2 `SheetNotFound`, with `details.suggestion: "Sheet2"`") and document choice in §5.

### M4 — Duplicate-cell semantics R5.c not in backlog

R5.c ("Mixed legacy+threaded already on the cell: append to threaded by default") is an analyst inference — backlog only specifies the two clean cases (threaded → append thread; legacy-only → fail). Once C2 is resolved, R5.c needs to re-derive its rule from the chosen threaded-mode contract. **Fix:** strike R5.c until C2 is decided; then write it as a corollary, not a new rule.

### M5 — `--default-initials` Q1 should not be Open Question

Q1 says "Recommendation: YES, but optional and not MVP." If it's not MVP, it should be in §R9 (honest scope, v2 follow-up) — not in §6. Open Questions are architecture-blockers; non-MVP items are scope-locks. **Fix:** move Q1 to R9.f as "Per-row `initials` override is taken from `BatchRow.initials`; envelope-mode uses `--default-author`-derived initials only — separate `--default-initials` deferred to v2."

### M6 — `personList.xml` rel attachment point inconsistent with workbook structure

I1.4 step 6 says "`personList` is a workbook-level rel in `xl/_rels/workbook.xml.rels`". Need to double-check: per ECMA-376 / MS-XLSX threaded-comments extension, `personList` is referenced from the **workbook part** via the `personList` relationship (workbook-level), AND the Override is `[Content_Types].xml`. This is correct in the TASK but worth flagging an explicit AC: **"E2E `threaded-rel-attachment`: confirm `xl/_rels/workbook.xml.rels` (NOT a sheet rels file) gains the `personList` Relationship; sheet rels gain only the `threadedComment` rel."** Currently this is implicit and easy to miss in implementation.

### M7 — Library mode (`--unpacked-dir`) not addressed

`docx_add_comment.py` exposes `--unpacked-dir DIR` for chained pipelines. xlsx-6's TASK is silent on this. Backlog doesn't require it but parity-with-docx is a stated goal (§1 "feature parity with `docx_add_comment.py`"). **Fix:** either add a use case (parity-extension) or explicitly document in R9 honest scope: *"`--unpacked-dir` library mode deferred to v2 — pipeline integration in v1 is via `--batch path.json`."*

### M8 — `--cell` and `--batch` mutex never stated

Implied throughout but not formalized. Should be in C3's CLI surface table; flagging here as a separate concern because the error envelope it produces (`UsageError: --cell mutually exclusive with --batch`) needs an AC.

---

## Minor Issues (nice-to-fix, don't block architecture)

### m1 — Q6 `casefold()` for non-ASCII userId

Backlog says "lowercase"; TASK Q6 introduces `str.casefold()` for Cyrillic. This is an improvement but `casefold` and `lower` differ on German ß and a few other glyphs. **Fix:** in the resolution of Q6, write the chosen function literally and lock with a unit test (`displayName="STRAẞE"` → expected userId).

### m2 — `BatchTooLarge` envelope cap (Q4) — confirm helper location

Q4 caps batch JSON at 8 MiB. The check belongs in the same place that loads the JSON, with a typed envelope. Not a blocker, but an AC line in I2.1 saying "AC: 9 MiB JSON file → exit 2 `BatchTooLarge` envelope; size measured pre-parse via `Path.stat().st_size`" would be tighter than the §4 prose.

### m3 — `xlsx_validate.py --fail-empty` is correct, but cite it

I3.2 AC says "runs `xlsx_validate.py --fail-empty`". Confirmed flag exists (line 66 of `xlsx_validate.py`). Minor: link to it from §1 "Connection with existing system" so the reader knows that's a real flag.

### m4 — R9.d "goldens are agent-output-only" needs a test-mechanism

R9.d says Excel may convert legacy → threaded silently. The honest-scope lock in I4.1 says "Goldens are agent-output-only — never round-tripped through Excel (R9.d). README in test dir documents this." A `tests/golden/README.md` is good; consider also adding a CI guard that fails if a golden file's `xl/_rels/workbook.xml.rels` mtime differs from the sibling `xlsx_add_comment.py` mtime by more than X (i.e. golden was hand-touched). Optional.

### m5 — `<authors>` dedup key

I1.3 step 2 says "Insert author into `<authors>` if absent; reuse index if present (`authorId` is the position)". The dedup key isn't specified — by exact string? case-folded? The threaded path uses lowercased `userId` for personList dedup (I1.4.A1.4.a). Legacy and threaded should use the **same** dedup key for consistency. **Fix:** add unit-test AC: "`<authors>` dedup uses identity-comparison on the displayName string (case-sensitive), matching `<person>` dedup on `displayName`."

### m6 — §10 SKILL.md Quick Reference column for `xlsx_add_comment.py` not specified

I4.2 AC says "§10 Quick Reference table adds a row" but doesn't specify columns. Quick Reference rows in SKILL.md follow a fixed schema (script, purpose, key flags). Minor — analyst can copy the existing pattern.

### m7 — Backlog "validation-агент (xlsx-7 pipe) расставляет замечания" — TASK should mention this in §1

§1 "Why now" says "Pipeline enabler for xlsx-7" but doesn't quote the backlog's specific use case. Adding a one-line example from §11 of SKILL.md would help (cross-reference to §11 examples).

---

## Final Recommendation

**Status: BLOCKING. Do NOT proceed to Architecture phase.**

**Next step:** Analyst MUST address **C1 (o:idmap/o:spid OOXML mapping)**, **C2 (threaded write contract — promote to Q7)**, and **C3 (consolidated CLI flag table)** before architecture sign-off. Major issues M1–M8 should be addressed in the same revision pass — they're cheap fixes individually but compound into re-work if deferred to architecture (especially M2, M3, M6, M7 which all reshape E2E fixtures). Minor issues m1–m7 may be picked up during architecture without blocking the gate, but the analyst should batch them with the C/M revision rather than punt to development.

Recommended path: revise TASK.md → re-submit for analysis-gate review → on APPROVED-WITH-COMMENTS proceed to Architecture phase with Q2/Q5/Q7 as the three open questions ARCHITECTURE.md must close.

```json
{ "review_file": "docs/reviews/task-001-review.md", "has_critical_issues": true }
```

---

## Round 2 (Date 2026-05-07)

**Status:** **APPROVED WITH COMMENTS** — proceed to Architecture phase.

### General assessment

The revision lands the three round-1 BLOCKERS cleanly: C1 (`o:idmap`/`o:spid` distinction) is now correct everywhere it matters; C2's "always also write legacy" claim has been demoted from a stated fact to a properly-flagged ARCHITECTURE-blocker (Q7) with neutral wording in I1.4 step 1; C3 produces a substantial §2.5 CLI surface table with mutex rules MX-A/MX-B and dependency rules DEP-1..DEP-4 plus an exit-code matrix. All eight major issues are addressed in concrete, testable form with named ACs. The remaining nits (m1, m2, m4, m5, m6, m7) are all closed; m3 is unchanged but was non-blocking.

### Per-item closure table

| ID | Status | Justification |
|---|---|---|
| C1 | CLOSED | R1.h, I1.3 step 4, I1.3 ACs, I2.3 pre-scan, I2.3 ACs all correctly distinguish `<o:idmap data="N">` (workbook-wide) from `<v:shape o:spid>` (per-shape). New `idmap-conflict` E2E with `_x0000_s2049+` allocation. |
| C2 | CLOSED | I1.4 step 1 is now Q7-dependent preamble. Q7 added to §6 as ARCHITECTURE-BLOCKER. R5.b uses `--no-threaded` (renamed); R5.c marked deferred / corollary-of-Q7. |
| C3 | CLOSED | New §2.5 CLI surface table enumerates all 14 flags + 2 positionals; mutex MX-A/MX-B explicit; dependency DEP-1..DEP-4 explicit; exit-code matrix maps every envelope. |
| M1 | CLOSED | R8.d scopes determinism explicitly; R9.e flags UUIDv4 non-determinism on `<threadedComment id>`. |
| M2 | CLOSED | I1.1 step 3 = "first VISIBLE sheet"; `NoVisibleSheet` envelope added; A1.1.g covers explicit qualifier bypass. |
| M3 | CLOSED | I1.1 step 3 declares case-sensitive lookup; A1.1.f locks `details.suggestion`. |
| M4 | CLOSED | R5 marks R5.c deferred / corollary-of-Q7. |
| M5 | CLOSED | Q1 moved out of §6 to R9.f as v2-deferred. |
| M6 | CLOSED | I1.4 step 6 splits `personList` → `xl/_rels/workbook.xml.rels` vs `threadedComment` → sheet rels; dedicated `threaded-rel-attachment` AC. |
| M7 | CLOSED | R9.g marks `--unpacked-dir` deferred to v2; I4.1 step 5 locks it with a regression test. |
| M8 | CLOSED | MX-A in §2.5; I2.3 AC asserts `--cell --batch` together → `UsageError`. |
| m1 | CLOSED | I1.4 step 4 names `str.casefold()`; AC unit-tests `STRAẞE` → `strasse`. |
| m2 | CLOSED | I2.1 step 2 places 8 MiB cap pre-parse via `Path.stat().st_size`; AC covers 9 MiB exit-2 case. |
| m4 | CLOSED | I4.1 step 4 names `tests/golden/README.md` and quotes the protocol. |
| m5 | CLOSED | I1.3 step 2 specifies case-sensitive identity-comparison dedup matching I1.4. |
| m6 | CLOSED | I4.2 step 3 names two-column schema; AC on line 371 supplies template (cosmetic glitch — see N1). |
| m7 | CLOSED | §1 Reference use-case block quotes the backlog Russian text. |
| m3 | UNCHANGED (non-blocking) | `xlsx_validate.py --fail-empty` cited at §1; was a nice-to-have. |

### New (cosmetic-only) issues

- **N1** — I4.2 AC line 371 has unbalanced pipes in the §10 Quick Reference row template (`[--threaded] | --batch <file>]`). Cosmetic; intent clear; suggested fix to `[--threaded]` or `--batch file.json --default-author "..."`. Folded into Architecture pass.
- **N2** — R3.b still says `userId="<lower>"` while I1.4 step 4 + Q6 lock `casefold()`. Internally inconsistent in the RTM-row prose vs Use Case body; Use Case wins by convention. One-token edit.

No new critical or major issues found.

### Final Recommendation

**APPROVED WITH COMMENTS — proceed to Architecture phase.** The Architect must close Q2, Q5, Q7 in `docs/ARCHITECTURE.md` before development starts. N1 and N2 are cosmetic and may be folded into the Architecture cleanup without re-review.

```json
{ "review_file": "docs/reviews/task-001-review.md", "round": 2, "has_critical_issues": false, "approved_for_architecture": true }
```

