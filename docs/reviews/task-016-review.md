# Review: TASK 016 — wiki-ingest cross-course promotion / demotion

**Date**: 2026-05-26
**Reviewer**: task-reviewer (subagent, VDD start-feature pipeline)
**Target**: [`docs/TASK.md`](../TASK.md)
**Source spec**: [`docs/wiki-ingest-promotion-spec.md`](../wiki-ingest-promotion-spec.md)
**Architecture context**: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (post-TASK 015)
**Status**: **APPROVED WITH COMMENTS** — non-blocking, but 4 MAJOR clarifications strongly recommended before Architecture phase. Two findings borderline-critical because they encode a latent contradiction that the Architect will hit immediately.

---

## General Assessment

TASK 016 is high-quality and unusually self-aware for a v1 analyst pass: scope is honest, RTM is granular (every row has ≥3 sub-features), the Open Questions section explicitly mirrors spec §8 with recommended defaults, and §4.5 "Honest scope (locked)" + R13 explicitly enumerate what NOT to build. The architecture-compatibility story (R12.5 import-graph invariant, "no new runtime deps," reuse of `_safety.py` / `_vault.py` / `_markdown.py`) is sound and respects the TASK 015 substrate.

Coverage of the spec is essentially complete:

| Spec section | TASK coverage | Notes |
|---|---|---|
| §2.1 two `WIKI_SCHEMA.md` | R1, R9 | ✅ |
| §2.2 `promoted_from:` | R3.3 | ✅ |
| §2.3 footnote vault-relative form | R3.5, R5.3, R6.4, R8.2 | ✅ |
| §2.4 `## Shared * referenced` | R7.1 | ✅ |
| §2.5 root `index.md` | R3.9, R7.2 | ✅ |
| §3.1 `promote` | R3, R4 | ✅ (+ R3.7 relaxation, see below) |
| §3.2 `demote` | R5 | ✅ |
| §3.3 `merge-into-root` deferred | R3.7 folds into `promote` | ✅ — explicit + documented |
| §4.1 lint extensions | R6 | ✅ |
| §4.2 reindex extensions | R7 | ✅ |
| §4.3 ingest root-aware merge | R8 | ✅ |
| §4.4 query | NOT in RTM | minor (spec §4.4 explicitly says "no changes required"; non-issue) |
| §5 algorithms | encoded via R1, R3.5, R3.6, R6 | ✅ |
| §6 edge cases | R13.1–13.6, §8 risks | ✅ |
| §7 implementation notes | §0 Meta + §9 deliverables | ✅ |
| §8 open questions | §5 Q-1..Q-9 | ✅ all 8 spec items + Q-2b sub-question added |
| §9 testing | R10 | ✅ all 7 spec tests covered |
| §10 migration | §4.5 "Migration: zero-data" + §6 constraints | ✅ |

KNOWN_ISSUES carry-over: all 15 wiki-ingest items are resolved post-TASK-015. The TASK does **not** re-introduce any of them — R12.5 locks the import-graph invariant; R10.7's fixture inherits the static-`log.md` discipline; the new write sites all flow through `_atomic_write_text` (§4.2). Clean.

The TASK is **implementable as written modulo the four MAJOR items below**, which encode latent ambiguity an Architect or Planner will need to resolve. None warrant return-to-analyst; all are decidable in the Architecture phase with explicit notes in PLAN.md §0.

---

## Comments

### 🔴 CRITICAL — none

I considered raising R8 CLI-surface ambiguity (item M-1) to CRITICAL because it actively contradicts the v1 CLI shape, but the TASK does flag R8 as "no CLI change" in §7's bullet "`ingest` workflow (R8 — no CLI change)," so the divergence is recognised even if under-specified. Demoted to MAJOR.

### 🟡 MAJOR (4)

**M-1 — R8 / R8.1 CLI surface is under-specified and silently contradicts v1.**
*Location*: TASK.md §2 R8.1, R8.2; §3 UC-4 step 1; §7 acceptance bullet "ingest workflow (R8 — no CLI change)."

The existing `upsert-page` (and `register-summary`) takes `vault` as a positional argument resolved as the **course wiki root** (`ensure_schema(vault)` refuses anything without a `WIKI_SCHEMA.md` at that level). R8.1 says lookup order is "root `_concepts/` → root `_entities/` → course-local." For this to work, `upsert-page` must somehow know where the *vault* root is — but the only argument it has today is the *course* root. Three undocumented options:
  (a) `upsert-page` autodiscovers the vault root by walking *up* from the passed-in course path via `find_vault_root` (R1) — but R1's signature returns `(course_root, vault_root_or_None)`, so this works only if the caller passes a course path or any path inside it. ✅ feasible.
  (b) Add a new optional `--vault-root` flag. ❌ TASK explicitly says "no CLI change."
  (c) Reinterpret `vault` to mean "any path inside a course"; require commands to call `find_vault_root` internally. ❌ this *is* a behavioural change of v1 CLI (R11 byte-identity test from TASK 015 may break).

UC-4 leaves this entirely implicit ("`register-summary` (or full `ingest`) is invoked for Course C" — no CLI excerpt). The Architect needs an answer because route (a) implies *every* existing command silently gains a `find_vault_root` call, which crosses the v1 byte-identity gate (TASK 015 R11) when a `schema_version: 2.0` root is present.

**Fix**: add an explicit sub-bullet to R8 listing the CLI shape decision, e.g. R8.6 *"`upsert-page` and `register-summary` continue to take the course-root `vault` positional; they internally call `find_vault_root(vault)` to discover an optional vault root. Single-course vaults (no root schema) yield `vault_root=None` and behaviour is byte-identical to v1 (locked by TASK 015 R11 fixtures, extended with a `two_course_vault` fixture variant where root_schema=None)."* Also add a sentence in §4.4 Compatibility clarifying that "byte-identity holds *only* when no root `WIKI_SCHEMA.md` is present" — otherwise R8 demonstrably changes upsert behaviour.

---

**M-2 — R12.5 import-graph invariant contradicts R3 / spec §7 "reuse `upsert_page.merge_into_existing`-style additive merge."**
*Location*: R3 row preamble; R12.5; §8 risk 5.

R3's preamble says: *"Reuses `upsert_page.merge_into_existing`-style additive merge (no rewrite of existing content)."* R12.5 says: *"`promote.py`/`demote.py` import only from `_safety`, `_markdown`, `_frontmatter`, `_vault`, and DO NOT import any other `commands/*` module."*

`upsert_page.merge_into_existing` does not exist in the codebase. The actually-existing helpers are `upsert_source_row`, `append_fact`, `append_contradiction`, `upsert_footnote` — all module-level in `commands/upsert_page.py`. If `promote.py` literally imports them, it violates the import-graph invariant from TASK 015 (`tests/test_architecture.py` will fail), which R12.5 itself locks in.

The Architect's resolution is presumably to **promote** the additive-merge primitives to a F2-tier helper (either `_markdown.py` or a new `_page_merge.py`). This is a real architectural decision the Planner must make, and the TASK is currently inconsistent on it (R3 says reuse; R12.5 forbids the only path to reuse).

**Fix**: rephrase R3 preamble to *"Reuses the additive-merge **primitives** — `upsert_source_row` / `append_fact` / `append_contradiction` / `upsert_footnote` — extracted to a new F2 helper module per the import-graph invariant (R12.5). The extraction is in-scope for this TASK; the existing `commands/upsert_page.py` becomes a thin caller over the helper."* Add this as a new RTM row e.g. R3a or an R12.5 sub-feature. Also remove the `merge_into_existing` placeholder name from §8 risk 5 — it implies a function that doesn't exist.

---

**M-3 — R1 walk-up semantics break when the operator passes the *vault root* (not a path inside a course).**
*Location*: R1.1, R1.2; UC-1 step 2 ("walks up from the vault arg, discovers the vault root + both course roots").

R1.1: *"Walk up from a path inside a course; stop at first `WIKI_SCHEMA.md` → course root."* R1.2: *"Continue walking; second `WIKI_SCHEMA.md` (with `schema_version: 2.0`) → vault root; else None."*

But UC-1 step 1 has the operator running `wiki-ingest promote "Sharpe Score" --vault ~/obsidian/trade-agents` — i.e. the vault root **directly**. Walking up from the vault root means R1.1 immediately matches the **root** schema and treats it as the "course root." Then R1.2 walks further up looking for a *second* schema and finds none → `vault_root=None`. The function returns `(vault_root, None)` mislabelled as `(course_root, None)`. The subsequent "scan `Lessons/*/_concepts/`" step in UC-1 step 3 works only because step 3 ignores the function's return value and hard-codes `Lessons/`.

This is the same Q-8 problem ("the `Lessons/` segment is conventional but not hardcoded — replaced by 'any subdirectory with a course-local schema'") manifesting in the discovery layer. The TASK conflates two operations:
  - **`find_vault_root(start)`**: given a path inside a course, return `(course_root, vault_root_or_None)`. Used by ingest-time commands (UC-4).
  - **`discover_courses(vault_root)`**: given a vault root, return `list[course_root]`. Used by `promote`/`demote`/cross-course `lint`/root-mode `reindex`.

The TASK has only the first; the second is implied but unnamed.

**Fix**: split R1 into R1 (`find_vault_root` — caller passes a path *inside* a course) and a new R1b (`discover_courses(vault_root)` — returns every direct-or-nested subdirectory containing a `WIKI_SCHEMA.md` with `schema_version: 1.x`; the recommended Lessons-segment convention from Q-8 is honoured but not hardcoded). Update UC-1 step 2 to use both functions explicitly. Bonus: this also makes Q-8 a closable question — the answer is "two helpers, not one."

---

**M-4 — R7.2 root-mode reindex CLI surface is ambiguous; conflicts with `ensure_schema(vault)` v1 contract.**
*Location*: R7.2; UC-5 A1.

R7.2: *"When reindex runs on the vault root (new), rebuild root `index.md`…"* Current `reindex` calls `ensure_schema(vault)` (TASK 015 §3.2). If the operator runs `wiki-ingest reindex <vault-root>`, the root has a `WIKI_SCHEMA.md` with `schema_version: 2.0` — `ensure_schema` succeeds. But existing `reindex` then walks `vault/_sources/_concepts/_entities/` (`_walk_pages`) and expects v1 layout. Root has `_concepts/` and `_entities/` but **no `_sources/`** by R7.2 design (sources never live at root, per spec §2.5). Existing code does `if not d.is_dir(): continue` — so missing `_sources/` is a non-error — ✅ but only by luck.

More importantly, the `Lessons/` subtree is NOT scanned by `_walk_pages`. So a naive `reindex <vault-root>` invocation would only rebuild the root layer's `index.md` from root pages, **never crossing into courses**. R7.2 implicitly relies on this (the description does say "Optionally cascade-reindex every course (gated by `--cascade` flag — default off)"), but the trigger condition — "how does the CLI know it's running in root mode vs course mode?" — is not specified.

Three implied options:
  - Auto-detect: peek `WIKI_SCHEMA.md`'s `schema_version`. `2.0` → root mode.
  - Explicit `--root` flag mirroring `init --root` (Q-1).
  - Path-based: `find_vault_root(vault)` returns `(self, None)` → root mode.

**Fix**: add R7.2.1 "Mode detection: `reindex <path>` peeks `<path>/WIKI_SCHEMA.md`'s `schema_version`. `2.0` → root mode (rebuild root `index.md`); `1.x` → course mode (existing v1 behaviour); mismatched/absent → die with the existing v1 message." Add an explicit alternative scenario to UC-5 covering "operator runs `reindex` on a vault root with `--cascade=off`: only root index rebuilt, no course touched." Also clarify whether `--cascade` is meaningful in *course* mode (it isn't — cascade always means "and every course").

---

### 🟢 MINOR (6)

**m-1 — `commands/init.py` vs `init-root` decision pushed to Q-1.** Q-1 has a recommended default (`init --root`), but R2 oscillates between the two phrasings throughout the row ("Extend `commands/init.py` (or add a sibling subcommand `init-root`)" ... "`init <vault> --root` (or `init-root <vault>`)"). Once the Architect closes Q-1, R2's text should be tightened to whichever decision lands; current wording is fine for the TASK level but should not survive into PLAN.md verbatim.

**m-2 — R3.7 wording ambiguous about whether re-promote requires `≥1` or exactly 1 course-local copy.** *"if the root version already exists and an additional course has a course-local copy"* — singular ("an additional course"). If two more courses both have course-local copies of an already-promoted page, does `promote` merge all of them in one shot? Spec §3.3 implies yes ("relax `promote` to also accept '≥ 1 course-local version when a root version already exists'"). Fix: rephrase R3.7 as "≥1 course-local copies (singular or plural)."

**m-3 — UC-1 A4 (contradiction at merge time) does not exercise R3.6's "fact-level disagreement (same predicate, different value)" mechanic.** The fact-level disagreement requires a predicate-extraction step the existing `append_contradiction` does NOT do (it works on operator-supplied `--contradicts <existing-claim>` strings). R3.6's "same predicate, different value" implies new logic. UC-1 A4 narrates the outcome but skips the algorithm. The Architect / Planner needs to know whether "predicate" is extracted heuristically or whether the operator is expected to flag it manually. Recommend: open a Q-10 "Promote-time contradiction detection: literal-line-diff or predicate-extraction?" with recommended default *literal-line-diff (cheap; matches v1 contradiction surfacing where operator supplies the existing claim)*.

**m-4 — R5.2's cross-course citation scan defines "page being demoted" but doesn't say what counts as a citation.** R5.2: *"scan every `Lessons/<Course>/_sources/<slug>.md` for footnote definitions whose `<slug>` is referenced by `[^src-<slug>]` *on the page being demoted*."* The semantics is: "if any source-slug appearing in the root page's footnote definitions belongs to a non-target course's `_sources/`, refuse." That's clear after re-reading, but the sentence chains three nested conditions. Suggest splitting into two sentences. Also: clarify whether "belongs to" means "filename `<slug>.md` lives in that course's `_sources/`" — yes, but say so.

**m-5 — UC-3 main scenario step 3 emits two new finding categories but does not specify ordering or sort discipline.** Existing lint output is sorted (TASK 015 §10 / 015-00 determinism gate). The two new categories should declare sort key (alphabetical by `name`?) to keep `diff -q` byte-identity. Easy fix in R6 / R10.3.

**m-6 — §8 risk 3 ("findings count blow-up") proposes `--limit N`, but R6 does not list a `--limit` sub-feature.** Either add it as R6.6 or remove from §8 risks. The current state is "we noticed the risk but didn't plan a mitigation."

---

## Compatibility & Architecture Compliance

- ✅ **Import-graph invariant** (TASK 015 R7.4 / `tests/test_architecture.py`): R12.5 explicitly preserves it. (Pending M-2 resolution — see above.)
- ✅ **Layered DAG F3 → F2 → F1**: `promote.py` / `demote.py` are F3 commands; they import F1 + F2 + F3-helper only.
- ✅ **No new runtime deps**: §0 Meta explicitly confirms.
- ✅ **R11 byte-identity gate (TASK 015)**: §4.4 Compatibility states the v1 byte-identity must hold on single-course fixtures. (Pending M-1 resolution — see above for the conditional caveat.)
- ✅ **`_atomic_write_text` / `flock` discipline** preserved: §4.2 Security explicitly enumerates all new write sites.
- ✅ **Pure stdlib**: §6 Constraints lists the exact stdlib subset.
- ✅ **KNOWN_ISSUES**: no re-introduction of any of the 15 resolved items; the `_atomic_write_text`, `_check_case_collision` scandir path, `_compile_section_header_re` LRU, `tail_log` ASCII anchor, `_splice_frontmatter_fields` structural rewrite are all reused.

---

## Honest Scope Check

The TASK §4.5 + R13 + §5 Q-1..Q-9 faithfully mirror spec §6 + §8. Items locked OUT-of-scope:

- ❌ Auto-promotion at ingest time (R8.5, R13, Q-5)
- ❌ Semantic identity detection (R13.1)
- ❌ Root-level `log.md` (R13.2, Q-4)
- ❌ Source-slug cross-vault collision detection (R13.3)
- ❌ Custom page kinds beyond `_concepts/_entities` (R13.4)
- ❌ Concurrency / file-watch (R13.5)
- ❌ Bidirectional `[[Course A/Foo]]` link normalisation (R13.6, Q-7)
- ❌ Configurable promotion threshold (Q-3)
- ❌ Migration script (§4.5 "Migration: zero-data")

No scope creep detected. The TASK does **not** silently add multi-tenant isolation, namespace conflict resolution, schema-migration tooling, or auto-promotion.

---

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Architecture phase.**

The four 🟡 MAJOR items (M-1..M-4) are all decisions the **Architect** is the right person to resolve (they encode "which helper module hosts what" and "what does the CLI look like in root mode") — they do not require returning to the analyst. The Architect should:

1. Resolve M-2 by promoting `upsert_page` additive-merge primitives to F2-tier (likely a new `_page_merge.py` between `_markdown.py` and `commands/upsert_page.py`), update §3.2 module table accordingly, and re-state R3 / §8 risk 5 in the architecture record.
2. Resolve M-1 + M-4 + M-3 by adding three explicit CLI-shape sub-decisions to ARCHITECTURE.md (one each for upsert-aware-of-root, reindex root-mode autodetection, and `find_vault_root` vs `discover_courses` split). Carry the resolutions back into TASK.md if drift is large; otherwise note in PLAN.md §0 "Open Questions Resolved."
3. Refresh `references/architecture.md` (in `skills/wiki-ingest/references/`) — the existing maintainer-facing module map needs the two new commands.

The 🟢 MINOR items can be folded into the Planner phase or addressed during atomic-bead execution.

```json
{
  "review_file": "docs/reviews/task-016-review.md",
  "has_critical_issues": false
}
```
