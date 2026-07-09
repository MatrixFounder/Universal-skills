---
id: WIKI-INGEST-016-VDD-DEFER
type: known-issue
status: open
opened_at: 2026-05-26
category: tech-debt
severity: LOW
component: wiki-ingest
slug: wiki-ingest-016-vdd-defer
---

# WIKI-INGEST-016-VDD-DEFER — TASK 016 VDD-multi residuals

**Status:** DEFERRED to a future `wiki-ingest-016b` follow-up task.
**Backlog row:** none yet (open as `wiki-ingest-016b` if user prioritises).
**Severity:** LOW (cosmetic / lint-side false-positive tier; no HIGH or
MEDIUM remain unaddressed).
**Context:** VDD-multi over TASK 016 (cross-course promotion / demotion)
ran 3 critics across 2 iterations (2026-05-26). All CRITICAL + HIGH
findings (17 fixes total) are closed with regression tests in
[`skills/wiki-ingest/scripts/tests/`](../../skills/wiki-ingest/scripts/tests/).
Two lint-side false-positives + nine cosmetic/micro nits are
intentionally deferred — none are blockers; the chain ships clean.
Catalogued below for posterity / `wiki-ingest-016b` prioritisation.

## Lint-side false positives

- **L-Smoke-1 — Cross-layer dangling-link semantics wider than the
  spec.** `lint` treats a name present ANYWHERE in the vault (root or
  any course) as "resolvable" → cross-course references between two
  courses' `_concepts/`/`_entities/` are NOT flagged dangling. Spec
  §4.1 implied stricter "same-course-only resolution"; the
  implementation chose the LLM-friendly "is this resolvable from any
  layer" semantics. Locked by
  [`tests/commands/test_lint_two_tier.py::TestDanglingRefinement::test_course_to_other_course_link_is_dangling`](../../skills/wiki-ingest/scripts/tests/commands/test_lint_two_tier.py).
  **Fix path:** if stricter semantics ever needed, restrict
  `known_global` to `<root_layer> ∪ <current_course>` in `_layer_findings`.

- **L-Smoke-2 — Vault-relative footnote targets register as
  `dangling_link_targets`.** After `promote`, the root page's footnote
  defs use vault-relative form `[[Lessons/A/_sources/foo]]`. The
  existing dangling-link check parses `[[<target>]]` as wikilinks
  expecting bare filename → flags them as dangling. Cosmetic noise; no
  correctness break. **Fix path:** in two-tier mode, exclude wikilink
  targets matching `<course_rel>/_sources/<slug>` for any
  `course_rel ∈ discover_courses(vault_root)` from the dangling check.

## Cosmetic / micro-optimisation (deferred indefinitely)

| ID           | Location                                                   | Description                                                                                                         |
|--------------|------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| **L-016-L1** | `commands/init.py:_execute_root`                           | UX foot-gun: `init --root <new_dir>` dies (target must exist) while `init <new_dir>` (no flag) creates intermediates. Sharper error message wanted: `mkdir -p` hint. |
| **L-016-L2** | `_vault.py:discover_courses`                                | Double symlink filter: `os.walk(..., followlinks=False)` + per-dir `_skip_symlink` filter. Defense-in-depth but wasteful. |
| **L-016-L3** | `_vault.py:_peek_schema_version`                            | Exception filter `(ValueError, UnicodeError, KeyError)` doesn't include `TypeError`/`AttributeError`. `isinstance(fm, dict)` already protects; defensive only. |
| **L-016-L4** | `commands/upsert_page.py:_rewrite_one_footnote`             | Idempotent re-write emits an unnecessary write when target already matches. Trivial early-exit possible.            |
| **L-016-L5** | `commands/promote.py:_serialise` + `commands/demote.py:_serialise` | ~30 LoC scalar-serialise wrapper duplicated. Iter-1 partially de-duplicated (list fields delegate to `_frontmatter._serialize_yaml_list_field`); scalar wrappers still copy each other. |
| **S-016-L1** | `commands/promote.py:_FOOTNOTE_DEF_PATTERN`                 | Regex slug class `[^\]]+` softer than `_safe_name`. Gated at write-time by `_safe_name`; pattern alignment is cosmetic. |
| **S-016-L3** | `commands/init.py:_execute_root`                            | No path-containment enforcement on `--root <path>` (operator-trusted per security trust-model bullet 1). Documented; not exploitable. |
| **P-016-M3** | `commands/promote.py:_slug_to_course_map`                   | Globs every course's `_sources/` per-promote. Acceptable for single CLI invocation; flag if `promote-batch` mode ever lands. |
| **P-016-M4** | `commands/upsert_page.py:find_vault_root`                   | Called unconditionally per upsert. ~3–5 stat calls per invocation. Acceptable for CLI model; flag if bulk-upsert in-process mode lands. |

## Material defects intentionally NOT in this defer (open for `wiki-ingest-016b`)

These two items are **NOT cosmetic** and would warrant a deliberate fix
pass when prioritised — recorded here ONLY to clarify they are NOT in
the "deferred indefinitely" bucket:

- **Logic-016-H3 — `_facts_similar_predicate` heuristic noise.**
  Q-10 PLAN.md locked literal-line-diff; the 2-word-prefix matcher
  produces false positives (`"Risk premium is 5%"` vs `"Risk premium
  accounts for liquidity"`) and false negatives (facts <3 words skipped
  entirely). Threshold tuning + numeric-token-aware divergence check
  recommended.
- **Logic-016-M1 — Cross-course duplicate scan NOT case-folded.**
  Inconsistent with v1 L-L7 `concept_freq` (which uses `.lower()`).
  On case-sensitive filesystems, `Sharpe Score.md` and `sharpe score.md`
  across two courses are NOT detected as duplicates. Apply same
  `.lower()` discipline in `_collect_layer_filenames` /
  cross-course-duplicate aggregation.

**Workaround:** None — all items are LOW severity (cosmetic) or
diagnostic-only (lint false-positives). Promoting any item to a
follow-up task is at user discretion.
