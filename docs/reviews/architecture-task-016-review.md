# Architecture Review — TASK 016 (wiki-ingest cross-course promotion / demotion)

**Date**: 2026-05-26
**Reviewer**: architecture-reviewer (subagent, VDD start-feature pipeline)
**Target**: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (1051 LoC, single file mixing TASK 015 MERGED + TASK 016 IN DESIGN)
**Inputs reviewed**:
- [`docs/TASK.md`](../TASK.md)
- [`docs/reviews/task-016-review.md`](task-016-review.md) (4 MAJOR items M-1..M-4)
- [`docs/wiki-ingest-promotion-spec.md`](../wiki-ingest-promotion-spec.md)
- [`skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`](../../skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md)
- [`skills/wiki-ingest/scripts/tests/test_architecture.py`](../../skills/wiki-ingest/scripts/tests/test_architecture.py)
- [`skills/wiki-ingest/scripts/wiki_ingest/_vault.py`](../../skills/wiki-ingest/scripts/wiki_ingest/_vault.py) (current — `find_vault_root` does NOT yet exist; ✓)
- [`skills/wiki-ingest/scripts/wiki_ingest/commands/upsert_page.py`](../../skills/wiki-ingest/scripts/wiki_ingest/commands/upsert_page.py) (current — confirms the four merge primitives are module-level)

**Status**: **APPROVED WITH COMMENTS** — non-blocking. One MAJOR item is genuinely load-bearing (bead ordering vs invariant net); the other comments are tightening / wording nits.

---

## General Assessment

The architect's pass is high quality and resolves all four task-review MAJOR items concretely, not aspirationally:

| Item | Resolution location | Concrete? |
|---|---|---|
| M-1 (upsert-page byte-identity caveat) | §2.1.bis "F3 helpers" final paragraph + §5.1 "Existing subcommand changes" + §13 decision row | ✓ Concrete — fixture variant `two_course_vault` with `root_schema=None` named; caveat scoped to "no root schema present" |
| M-2 (`_page_merge.py` extraction) | §2.1.bis "F2 — new module" + §3.2 table + §5.3 "Internal helper boundary" + §13 decision row | ✓ Concrete — 4 functions named, F2 tier locked, import budget specified, `commands/upsert_page.py` becomes thin caller |
| M-3 (`find_vault_root` vs `discover_courses` split) | §2.1.bis "F3 helpers" + §2.3 "Discovery algorithm" + §13 decision row | ✓ Concrete — both signatures and callers spelled out; Q-8 "Lessons/" hardcoding explicitly killed |
| M-4 (reindex root-mode auto-detection) | §2.3 "Schema-version detection (M-4 resolution)" + §5.1 "Existing subcommand changes" + §13 decision row | ✓ Concrete — schema-peek of `schema_version` field, 2.0 → root, 1.x → course, mismatched → die |

Import-graph invariant is mechanically intact:
- `_page_merge.py` is F2: imports `_markdown` + `_safety` only — matches the `rglob("_*.py")` helper-scan in `test_architecture.py` lines 49–52. The "F1/F2/F3-helper modules MUST NOT import commands" assertion will pass.
- `promote.py` / `demote.py` import `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_page_merge` — i.e., no other `commands/*.py`. The "no command imports another command" assertion at lines 63–80 will pass.
- §3.2 footnote correctly states no new lines of test code are strictly required; existing `rglob("_*.py")` already covers `_page_merge.py` automatically.

Living-document discipline is respected: TASK 015 content is preserved verbatim; TASK 016 additions are layered as §2.1.bis, §2.3, §3.2-additions-table, §4.5, §5.1-additions, §5.3, §7-T16-additions, §8-016-perf-table, §11 016-NN beads, §12 016 OQ, §13 016 decisions. Status banner correctly multi-task ("015 MERGED · 016 IN DESIGN"). Cross-skill replication §9 still "Not triggered."

Data-model entities are well-typed: `PromotedPageFrontmatter` (§4.5.1), `PromotionPlan` (§4.5.2), `DemotionPlan` (§4.5.3), lint findings `cross_course_duplicate` / `invariant_violation` (§4.5.4) each have concrete field shapes with example JSON. `promoted_from:` is correctly a `list[dict]`, not a flat `list[str]`.

Honest-scope items from R13 are uniformly absent from the design — no auto-promotion, no semantic identity, no root log, no custom kinds, no file-watch, no full-path link normalisation, no configurable threshold appears anywhere in §2.x / §3.x / §5.x / §11.

---

## Comments

### 🔴 CRITICAL — none

### 🟡 MAJOR (4)

**A-M-1 — Atomic-bead chain ordering contradicts the architect's own stated invariant-net rationale and TASK §8 risk 6.**

*Location*: ARCHITECTURE.md §11 "TASK 016 atomic-bead chain" preamble + table rows 016-03 through 016-08.

The preamble states:
> "The chain is ordered to land the invariant-enforcement net (016-06) early so later development is covered."

But 016-06 (`lint.py` cross-course-duplicate + `invariant_violation` extensions) is the **7th of 10 beads**. The chain executes 016-04 (`promote --apply` write path — first state-mutating bead) and 016-05 (`commands/demote.py` — second state-mutating bead) BEFORE 016-06 (lint invariant-violation finding) lands. This contradicts TASK §8 risk 6:

> "Hidden invariant break during incremental development. Until the `commands/lint.py` invariant check (R6.2) lands, the codebase can easily be left in a state where a page exists at root AND in a course simultaneously. Land R6 EARLY in the plan so the regression net is active throughout the rest of execution."

Recommended ordering:

- 016-00 (pre-flight helpers) — unchanged
- 016-01 (`_page_merge.py` extraction) — unchanged
- 016-02 (root schema scaffold + `init --root`) — unchanged
- 016-03 (NEW): **`lint.py` extensions (cross_course_duplicate + invariant_violation + dangling-link refinement)** — invariant net live BEFORE any write path
- 016-04 (was 016-03): `promote.py` skeleton + dry-run
- 016-05 (was 016-04): `promote --apply` — invariant net catches any regression immediately
- 016-06 (was 016-05): `commands/demote.py`
- 016-07: `reindex.py` extensions
- 016-08: `upsert_page.py` root-aware lookup
- 016-09: E2E + docs

*Severity rationale*: this is the only finding that materially affects implementation safety. Everything else is wording / completeness.

---

**A-M-2 — `Lessons/<Course>` is hardcoded in the footnote-rewrite contract while Q-8 explicitly killed the `Lessons/` hardcoding for discovery.**

*Location*: §2.1.bis (`lint.py` "Root-page footnote-format check" + `promote.py` row + `demote.py` row); §5.1 promote/demote grammars; §7 T16-S3; §13 016 Q-8 decision.

The architecture preserves the spec's literal `[[Lessons/<Course>/_sources/<slug>]]` form in three places (the lint check R6.4, the promote rewrite R3.5, the demote rewrite R5.3) — but Q-8 / §13 explicitly resolve that course directories are NOT under a hardcoded `Lessons/` segment ("`discover_courses` walks ALL descendants, not just `Lessons/`").

If a vault has its course at `<vault>/Hermes/` directly, the literal `Lessons/Hermes/_sources/<slug>` won't resolve in Obsidian.

*Fix*: replace every literal `Lessons/<Course>/_sources/<slug>` with "the vault-relative path of the source's directory" — i.e., the form is `<course_dir_relative_to_vault_root>/_sources/<slug>`. The R6.4 lint check should validate that the path prefix is the relative path of some `discover_courses(vault_root)` entry, not literally `Lessons/`. Add one sentence to §2.3 "Lazy promotion" or §5.1 stating: "The footnote prefix is `course_root.relative_to(vault_root)`; `Lessons/` is conventional but not hardcoded."

---

**A-M-3 — `_splice_frontmatter_fields` list-of-dicts extension is named but not scheduled as its own bead.**

*Location*: §2.1.bis "F2 — new module" final paragraph; §3.2 "TASK 016 module additions" row `_frontmatter.py (extended)`; §11 atomic-bead chain (no bead owns this work).

The architecture states `_frontmatter.py` gains a list-of-dicts code path inside `_splice_frontmatter_fields` (public signature unchanged). This is needed by `promote.py` writing `promoted_from:` and by `demote.py` removing it. Yet no bead in §11 owns it — it's implicit inside 016-04 (`promote --apply` write path). TASK §8 risk 2 flags this as a planning-phase decision needing care.

*Fix*: insert a new bead between 016-01 and 016-02 titled "Extend `_splice_frontmatter_fields` for list-of-dicts" with its own unit test (`test__frontmatter.py` extension) and a clear "verifies" gate. Then 016-04 can assume the helper is shipped.

---

**A-M-4 — `discover_courses` ambiguity: nested course schemas + symlink behaviour.**

*Location*: §2.1.bis "F3 helpers (M-3 resolution)" `discover_courses` definition; §2.3 "Discovery algorithm".

Two gaps:

1. **Nested course schemas**: what if a course has a sub-directory that itself contains a `WIKI_SCHEMA.md`? Is the result list flat? Probably yes (every descendant qualifies independently), but state it.
2. **Symlink discipline**: the existing `_walk_pages` skips symlinks (OVERLAP-5). `discover_courses` walks course directories via `os.walk` — does it inherit the same symlink-skip? Currently silent.

*Fix*: append a sentence to `discover_courses`'s algorithm in §2.3 stating: "Skips symlinked directories during the walk (same defence as `_walk_pages`, OVERLAP-5). Descends into matched course directories (a course may legitimately contain nested course schemas, e.g. `Lessons/2026/Spring/Hermes/`)." Also state same-device behaviour explicitly.

---

### 🟢 MINOR (6)

**m-A-1 — Bead 016-01 "extends `test_architecture.py`" — extension is unnecessary.** The existing `rglob("_*.py")` (line 50) and `commands/*.py` scan (line 68) auto-pick up the new modules. No code edit required; soften wording from "extended" to "passes against new modules" to avoid scheduling phantom work.

**m-A-2 — Task-review's m-4 ("what counts as a citation in R5.2") not directly addressed in §2.x / §5.x.** Add one sentence to the `demote.py` row: "a citation = a `[^src-<slug>]` reference on the root page whose `<slug>.md` file lives in any course's `_sources/` directory other than the `--to` target."

**m-A-3 — `init --root` mkdir semantics for `_concepts/` / `_entities/` not pinned.** §2.1.bis row `init.py` says "writes `_concepts/`, `_entities/`" — pin to `os.makedirs(..., exist_ok=True)` and explicitly state "no sentinel files."

**m-A-4 — Performance table for `lint` cross-course doesn't include per-course-pages breakdown.** §8 compresses to one number (5×100 ≤0.5 s). Adding a 50×200 row would lock the asymptotic contract.

**m-A-5 — Mermaid diagram in §3.3 uses `& `-chained targets for 13 commands.** Cosmetic only; §2.2 diagram uses per-line edges and is cleaner. Match styles for consistency.

**m-A-6 — `find` command silence on root-awareness.** The architecture does NOT extend `find`. Consistent with TASK (no R-row mentions `find`), but worth a one-sentence non-goal in §10 "Honest Scope" so future maintainers know the silence is intentional.

---

## Compatibility & architecture compliance

- **Import-graph invariant**: ✓ verified against `test_architecture.py` lines 49–80; `_page_merge.py`, `promote.py`, `demote.py` are all compliant by design.
- **Layered DAG F3 → F2 → F1**: ✓ `_page_merge.py` correctly placed at F2 (imports `_markdown` + `_safety` only); `find_vault_root` / `discover_courses` correctly stay in `_vault.py` (F3-helper).
- **R11 byte-identity caveat**: ✓ explicitly stated and scoped to "no root schema present"; new `two_course_vault` fixture variant `root_schema=None` extends the existing R11 fixtures.
- **No new runtime deps**: ✓ §6 still lists pure stdlib; no new imports added.
- **`_atomic_write_text` / `flock` discipline**: ✓ §7 T16-S5 enumerates root `index.md`, root concept/entity page, course `index.md`, course `log.md`.
- **Cross-skill replication**: ✓ §9 "Not triggered" still correct.

---

## Honest-scope check

R13 items absent from the design: auto-promotion (R13.0), semantic identity (R13.1), root `log.md` (R13.2), source-slug cross-vault collision detection (R13.3), custom page kinds (R13.4), concurrency / file-watch (R13.5), full-path link normalisation (R13.6) — all silently absent, no prophylactic abstractions added. ✓

No speculative future-proofing detected. Only one new helper module (`_page_merge.py`); no parallel `_promotion.py` / `_demotion.py` / `_root_layer.py` modules. ✓

---

## Final recommendation

**APPROVED WITH COMMENTS — proceed to Planning phase.**

A-M-1 (bead ordering) is the only finding the Planner needs to act on materially: the lint invariant-net bead should land BEFORE the first state-mutating bead (`promote --apply`), per TASK §8 risk 6 and the architect's own stated rationale. The Planner can either renumber the chain in `docs/PLAN.md` and surface the change in §0 "Open Questions Resolved," or route back to the Architect via the orchestrator.

A-M-2 (Lessons/ hardcoding) and A-M-3 (`_splice_frontmatter_fields` bead) are tighten-ups; A-M-4 (`discover_courses` symlink behaviour) is a one-sentence completeness fix. The MINOR items can be folded into PLAN.md §0 or addressed during atomic-bead execution.

The four task-review MAJOR items (M-1..M-4 from `docs/reviews/task-016-review.md`) are all resolved concretely, not aspirationally — each has a named module / function / contract in the architecture text.

```json
{
  "review_file": "docs/reviews/architecture-task-016-review.md",
  "has_critical_issues": false
}
```
