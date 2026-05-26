---
name: wiki-ingest-promotion-spec
description: Implementation specification for extending the `wiki-ingest` skill with a two-tier vault model (per-course + shared root layer) and lazy cross-course promotion/demotion of concept and entity pages.
status: draft
schema_version: 1.0
created: 2026-05-26
---

# wiki-ingest — Cross-Course Promotion / Demotion Specification

This document specifies the changes required in the `wiki-ingest` skill (currently at `/Users/sergey/dev-projects/Universal-skills/skills/wiki-ingest/`) to support a **multi-course Obsidian vault** where each course has its own course-local wiki layer and a **shared root layer** receives concept/entity pages by **lazy, operator-triggered promotion**.

The spec is meant to be portable: it can be implemented in the `wiki-ingest` repo without needing additional context from the `trade-agents` vault.

---

## 1. Background & motivation

### Current behaviour (v1)

The skill assumes a **single vault** rooted at the directory that contains `WIKI_SCHEMA.md` + `index.md` + `log.md` + `_sources/` + `_concepts/` + `_entities/`. Ingest walks up from the input file to find this directory (the "wiki root"), and writes everything there.

When a user has **multiple parallel courses** under a single Obsidian vault — e.g.:

```
my-vault/
└── Lessons/
    ├── Course A/                    # has its own WIKI_SCHEMA, _sources, _concepts, _entities
    └── Course B/                    # same
```

…each course is its own independent wiki. There is no mechanism to **share** a concept or entity that turns out to be common to multiple courses. The current options are bad: either (a) duplicate the concept page in each course (drift, contradictions, fragmented citations), or (b) merge everything into one big course (loses the natural per-course indexing and journaling).

### Target behaviour (v2)

Add a **vault-root shared layer**:

```
my-vault/                            # ← Obsidian vault root
├── WIKI_SCHEMA.md                   # NEW: root schema (cross-course rules)
├── _concepts/                       # NEW: shared concepts (lazy)
├── _entities/                       # NEW: shared entities (lazy)
├── index.md                         # NEW (optional): catalog of the shared layer
└── Lessons/
    ├── Course A/                    # still has its own course-local WIKI_SCHEMA, etc.
    └── Course B/
```

The shared layer is **populated lazily** — only when an operator explicitly promotes a page. Ingest itself never promotes.

The **invariant** that must hold at all times: *a given canonical name lives in exactly one place* — either in a single course's `_concepts/`/`_entities/`, or in the root's. This makes Obsidian's `[[wiki-link]]` resolution unambiguous (filename-based, shortest-path) without any special configuration.

---

## 2. Data model

### 2.1 Two `WIKI_SCHEMA.md` files

- **Root** `<vault>/WIKI_SCHEMA.md` — governs cross-course concerns: layout, link resolution order, promotion/demotion rules, the "one page, one place" invariant. Has `schema_version: 2.0` and a top-level marker the skill can detect.
- **Course-local** `<vault>/Lessons/<Course>/WIKI_SCHEMA.md` — governs naming, frontmatter, citation style, contradiction blocks, optional page kinds. Continues to exist per course. Has `schema_version: 1.x`.

Detection rule: the skill walks **up** from an input path until it finds the first `WIKI_SCHEMA.md` — that is the **course wiki root**. It then walks further up to find a second `WIKI_SCHEMA.md` (or stops at filesystem root) — if found, that is the **vault root** (shared layer). The vault root may equal the course wiki root in single-course vaults; the skill treats that as "no shared layer yet" and behaves as v1.

### 2.2 New frontmatter field on promoted pages

When a concept/entity is promoted to the root, its frontmatter gains:

```yaml
promoted_from:
  - course: "Course A"
    date: 2026-05-26
  - course: "Course B"
    date: 2026-05-26
```

This is provenance metadata; updated on every subsequent promote that merges in another course's version.

### 2.3 Footnote citation format

Course-local pages continue to use the short form:

```markdown
[^src-foo]: [[foo]] — Some Source Title
```

Promoted (root) pages use the **vault-relative** form so the citation survives the move:

```markdown
[^src-foo]: [[Lessons/Course A/_sources/foo]] — Some Source Title
```

Obsidian's filename-based resolution would *also* find `[[foo]]` from the root, but the vault-relative form is explicit and survives a course rename or future re-shuffling.

### 2.4 Course `index.md` — new section

When `reindex` runs on a course whose `_sources/` cite root-promoted pages, the course's `index.md` gains a section:

```markdown
## Shared concepts referenced

- [[Sharpe Score]] — (shared)

## Shared entities referenced

- [[Hermes Agent]] — (shared)
```

These sections list root pages that this specific course's `_sources/` actually footnote-cite. Purpose: a reader who only opens `Lessons/Course A/` should still see a complete map of what is referenced from this course, even if some pages live "above" it. The skill computes this section by scanning all `[^src-…]` footnote *references* across `_concepts/`/`_entities/` of the course… actually scanning incoming `[[wiki-link]]` from the course's `_sources/` and `_concepts/`/`_entities/` against root pages is simpler. See §6 algorithms.

### 2.5 Root `index.md`

Optional. Created the first time any page is promoted to the root. Structure mirrors a course index but only has `## Concepts` and `## Entities` sections (no `## Sources` — sources never live at root).

---

## 3. New commands

### 3.1 `promote <Name>`

```text
wiki-ingest promote "Sharpe Score" [--kind concept|entity]
```

**Pre-conditions:**

- The same canonical filename (`<Name>.md`) exists in `_concepts/` (or `_entities/`) of **≥ 2 different courses**.
- (If `--kind` not provided) auto-infer from where duplicates live; error if mixed (some courses have it as concept, others as entity — operator must reconcile first).
- The operator has confirmed the duplicates describe the same thing. The skill does not verify semantic identity; it trusts the operator.

**Steps:**

1. **Read** every course-local version of `<Name>.md`. Parse frontmatter + body.
2. **Merge frontmatter** — union of fields. `created:` takes the earliest. Add `promoted_from:` listing all source courses with today's date.
3. **Merge body** — use the existing additive-merge logic from `upsert_page.py` (the same one used when a new source's facts are merged into an existing page). Sections handled: `## Definition`, `## Facts`, `## Sources mentioning this`, `## Contradictions`, plus any custom sections defined in the course schemas.
4. **Rewrite footnote definitions** at the bottom of the merged page to vault-relative form: `[^src-<slug>]: [[Lessons/<Course>/_sources/<slug>]] — <Title>`. The `<Course>` is whichever course originally cited that source (preserved from the source course's version).
5. **Conflict detection** — if two course-local versions have a fact-level disagreement (same predicate, different value), emit a `## Contradictions` block as usual. Do not auto-resolve.
6. **Write** `<vault>/_concepts/<Name>.md` (or `_entities/`).
7. **Delete** every course-local copy of `<Name>.md`. Critical for invariant.
8. **Update each affected course's `index.md`** — remove `<Name>` from `## Concepts` (or `## Entities`); add it to `## Shared concepts referenced` (or `## Shared entities referenced`) if that course's `_sources/` still cite it (likely yes; the spec assumes yes — verify by scanning footnotes in the course's `_sources/` for `[^src-<slug>]` whose slug matches a source from this course).
9. **Update root `index.md`** — create if missing; add page to `## Concepts` / `## Entities`.
10. **Append `## [YYYY-MM-DD] promote | <Name>`** to each affected course's `log.md`, listing the pages that were merged and any contradictions raised. Body example:

    ```markdown
    ## [2026-05-26] promote | Sharpe Score
    - Merged from: Lessons/Course A/_concepts/Sharpe Score.md, Lessons/Course B/_concepts/Sharpe Score.md
    - Destination: _concepts/Sharpe Score.md (vault root)
    - Contradictions raised: 1
    ```

11. **Dry-run mode** (`--dry-run`): print the plan (what will be merged, what will be deleted, what `## Contradictions` will be added) without writing. Default to dry-run on first invocation; require `--apply` to actually execute. (Open question — see §8.)

**Error / abort conditions:**

- Page exists only in one course (no duplicate) → error: "no duplicates found; nothing to promote."
- Page already exists at the root → error: "already promoted; use `merge-into-root` if you want to fold an additional course-local copy in." (See §3.3.)
- Two courses disagree on `kind` (concept vs entity) → error: operator must align kinds first.
- Page has same name but obviously different content (e.g., `## Definition` differs by more than a threshold) → **warn** but do not abort; the operator confirmed.

### 3.2 `demote <Name> --to <Course>`

```text
wiki-ingest demote "Sharpe Score" --to "Course A"
```

**Pre-conditions:**

- Page exists at root.
- No course **other than** the target course has `_sources/` that cite this page. The skill scans all `_sources/` in all courses for `[^src-<slug>]` footnotes whose definitions reference `<Name>` — if any such citation lives outside the target course, the skill aborts with a clear message listing the conflicting citations.

**Steps:**

1. **Move** `<vault>/_concepts/<Name>.md` → `<vault>/Lessons/<Course>/_concepts/<Name>.md`. (Or `_entities/`.)
2. **Filter facts**: drop facts whose `[^src-<slug>]` cites a source from a course other than `<Course>`. (Should be none after the precondition check, but enforce.)
3. **Rewrite footnote definitions** back to course-relative form: `[^src-<slug>]: [[<slug>]] — <Title>`.
4. **Remove `promoted_from:`** from frontmatter.
5. **Update root `index.md`** — remove the page; if `## Concepts` / `## Entities` becomes empty, leave the heading (file can be GC'd manually later).
6. **Update target course's `index.md`** — remove from `## Shared concepts referenced`; add back to `## Concepts` / `## Entities`.
7. **Append `## [YYYY-MM-DD] demote | <Name>`** to the target course's `log.md`.

**Demote is not a deletion.** Use `rm` for that, outside the skill.

### 3.3 `merge-into-root <Name> --from <Course>` (optional, deferred)

Cleaner name for the case "page already at root, and now `<Course>` has independently created a course-local version with new facts to merge in." Could be implemented as a special case of `promote` (which already handles N-way merge) — only difference is the "must be ≥ 2 duplicates" precondition. Recommendation: just relax `promote` to also accept "≥ 1 course-local version when a root version already exists."

---

## 4. Extensions to existing commands

### 4.1 `lint`

Currently lints a single wiki root. Extensions:

- **Cross-course duplicate detection**: walk all `Lessons/<Course>/_concepts/` and `_entities/`. For any filename that appears in ≥ 2 courses, emit:

  ```
  ⚠️ Cross-course duplicate (promotion candidate):
    <Name>.md found in:
      - Lessons/Course A/_concepts/
      - Lessons/Course B/_concepts/
    Suggest: wiki-ingest promote "<Name>"
  ```

- **Invariant check**: a filename that exists at the root **and** in any course's `_concepts/`/`_entities/` is an error (violates "one page, one place"). Emit a hard failure suggesting `promote` (to merge the course-local back into root) or `demote` (to pull the root copy down).
- **Dangling links across layers**: a course-local page links `[[Foo]]`, no `Foo.md` exists in this course but exists at root — this is NOT dangling (resolution order: course → root). A course-local page links `[[Bar]]`, `Bar.md` exists in a *different* course and not in this one and not at root — this IS dangling and should be flagged. (Possible suggestion: prompt operator to promote `Bar` if it makes sense.)
- **Footnote-format check on root pages**: every `[^src-<slug>]` definition on a root page must use the vault-relative form (`[[Lessons/<Course>/_sources/<slug>]]`). Short form on a root page is a lint warning.

### 4.2 `reindex`

When run on a course:

- After rebuilding course-local `## Concepts` / `## Entities` from disk, scan the course's `_sources/` for footnote references. For every cited source that exists in this course and is also footnoted on a **root** concept/entity page, add that root page to `## Shared concepts referenced` / `## Shared entities referenced` in the course index.
- Custom sections in `index.md` are still preserved.

When run on the vault root (new):

- Build root `index.md` from disk (`_concepts/`, `_entities/`).
- Run reindex on every course as a follow-up (so course indexes pick up any newly-promoted pages they cite).

### 4.3 `ingest`

Minimal changes — ingest still writes only to a single course. But:

- When upserting a concept/entity page, check both the **course-local** layer and the **root** layer (in that order). If a page with the canonical name already exists at the root, **merge into the root page** (additive, same footnote format, contradictions handled the same). Do not create a course-local duplicate.
- Append to the course's `log.md` as today, but if the merge target was a root page, note that explicitly: `Pages touched: ../../\_concepts/Sharpe Score (shared)`.

### 4.4 `query`

No changes required. Querying is read-only; resolution order (course → root) is already what the LLM should follow when reading. Update prompts/instructions to reflect the two-tier model.

---

## 5. Algorithms

### 5.1 Finding the vault root

```
def find_vault_root(start: Path) -> tuple[Path, Path | None]:
    """
    Returns (course_wiki_root, vault_root). vault_root is None if there is
    no separate root schema (single-course vault, v1 behaviour).
    """
    course_root = walk_up_until(start, has_file="WIKI_SCHEMA.md")
    if course_root is None:
        raise NotInAVault(start)
    vault_root = walk_up_until(course_root.parent, has_file="WIKI_SCHEMA.md")
    return course_root, vault_root
```

The root schema can be distinguished from the course schema by `schema_version: 2.0` + a known marker in the frontmatter description, or simply by being the outer one when both are present.

### 5.2 Link resolution (for the LLM, not the skill)

The skill itself does not resolve `[[wiki-links]]` at read time — Obsidian does. But for the LLM's *reading* algorithm (in query mode), the documented order is:

1. Look in `<current course>/_concepts/<Name>.md`, then `<current course>/_entities/<Name>.md`.
2. Else look in `<vault root>/_concepts/<Name>.md`, then `<vault root>/_entities/<Name>.md`.
3. Else: dangling.

This order is enforced by the "one page, one place" invariant — there cannot be both a course-local and a root version simultaneously.

### 5.3 Cross-course duplicate scan

```
def find_cross_course_duplicates(vault_root: Path) -> dict[str, list[Path]]:
    seen: dict[str, list[Path]] = defaultdict(list)
    for course_dir in (vault_root / "Lessons").iterdir():
        for sub in ("_concepts", "_entities"):
            d = course_dir / sub
            if not d.is_dir(): continue
            for f in d.glob("*.md"):
                seen[f.name].append(f)
    return {name: paths for name, paths in seen.items() if len(paths) >= 2}
```

### 5.4 Citation rewrite (promote)

```
def rewrite_footnotes_for_root(body: str, course: str) -> str:
    # Find every line of the form: [^src-<slug>]: [[<slug>]] — <Title>
    # Rewrite to:                   [^src-<slug>]: [[Lessons/<course>/_sources/<slug>]] — <Title>
    return FOOTNOTE_DEF_PATTERN.sub(
        lambda m: f"[^src-{m['slug']}]: [[Lessons/{course}/_sources/{m['slug']}]] — {m['title']}",
        body,
    )
```

When merging multiple courses, each course's footnotes are rewritten with their own `<course>` value.

---

## 6. Edge cases & gotchas

1. **Same name, different concepts.** `Pipeline` in an ML course and `Pipeline` in a DevOps course are unrelated. The skill must never auto-promote on ingest. Promotion is operator-triggered, and the operator is responsible for the same-meaning check. The dry-run mode of `promote` exists specifically so the operator can review the merged output before committing.

2. **Footnote slug collisions across courses.** Source slugs are intended to be globally unique (they are derived from titles, kebab-cased). If two courses happen to ingest sources that produce the same slug, ingest itself should already fail; if it doesn't, promotion will silently keep one of them. **Mitigation**: ingest must check for slug collision across all courses, not just the current course. (Possibly a separate v1 bug; document here.)

3. **Page references that span layers.** If `Course A/_concepts/Foo.md` cites `[[Bar]]` and `Bar.md` lives at the root, Obsidian will resolve it fine. But if the operator later demotes `Bar` to `Course B`, `Foo`'s link silently goes dangling — `demote` must detect this and refuse to proceed (or warn).

4. **Custom page kinds.** Each course's `WIKI_SCHEMA.md` may declare additional page kinds (e.g., `Methods/`, `Decisions/`). Promotion logic should default to **not** promoting these — only `_concepts/` and `_entities/` are in scope. If a course wants shared `Methods/` at root, that's a v3 feature.

5. **Empty root `index.md`.** Before the first promotion, the root has no `_concepts/` or `_entities/` and no `index.md`. The skill should treat this as "shared layer not yet bootstrapped" and behave exactly like v1 (single-course mode) until the first `promote` creates the root layer.

6. **`log.md` per course only.** There is no root-level `log.md`. Cross-course operations write to every affected course's log. Open question: do we *also* want a root-level audit log? Probably yes for v2.1; defer for now.

7. **Concurrency.** The skill is single-process; no locking needed. If a future version runs against a vault that's also being edited live in Obsidian, file-watch / mtime checks may be useful.

8. **Filename special characters.** Obsidian allows characters in `[[wiki-links]]` that some filesystems trip on (e.g., `×`, `/`, `:`). Existing v1 already handles this; promotion just moves files, no new escaping needed.

9. **Schema versioning.** Root schema introduces `schema_version: 2.0`. Course schemas stay at `1.x`. The skill should refuse to run `promote` if the root schema is absent or wrong version, with a clear message.

---

## 7. Implementation notes (mapping to existing wiki-ingest code)

Existing layout:

```
wiki-ingest/scripts/
├── wiki_ops.py               # top-level CLI dispatcher
└── wiki_ingest/
    ├── _vault.py             # find_wiki_root logic — EXTEND
    ├── _frontmatter.py
    ├── _markdown.py
    ├── _safety.py
    ├── _classify.py
    └── commands/
        ├── upsert_page.py    # additive merge — REUSE for promote
        ├── reindex.py        # EXTEND for two-tier
        ├── lint.py           # EXTEND with cross-course checks
        ├── scan.py
        ├── append_log.py
        ├── log_event.py
        ├── find.py
        ├── classify_folder.py
        ├── init.py
        ├── register_summary.py
        └── update_index.py
```

Suggested additions:

- `wiki_ingest/_vault.py` — add `find_vault_root()` returning the `(course_root, vault_root)` tuple. The existing `find_wiki_root()` becomes a thin wrapper that returns the course root.
- `wiki_ingest/commands/promote.py` — new module. Reuses `upsert_page.merge_into_existing()` for the additive merge logic.
- `wiki_ingest/commands/demote.py` — new module.
- `wiki_ingest/commands/lint.py` — extend with `find_cross_course_duplicates()` and the invariant check.
- `wiki_ingest/commands/reindex.py` — extend to handle root-level reindex and the `## Shared concepts referenced` section in course indexes.
- `wiki_ingest/commands/upsert_page.py` — extend to check the root layer when looking for an existing page to merge into.
- `wiki_ops.py` — add `promote` / `demote` subcommands.

`SKILL.md` of `wiki-ingest` needs to be updated to document the new commands and the two-tier model, but the bulk of the conceptual documentation should live in the *vault's* `WIKI_SCHEMA.md` (skill is generic, vault is specific).

---

## 8. Open questions / decisions to make during implementation

1. **`--dry-run` default for `promote`.** I have suggested making dry-run the default and requiring `--apply` to commit. Alternative: require an explicit confirmation prompt instead. Decide based on UX preferences.
2. **Promotion threshold.** Currently specified as "≥ 2 courses." Is it worth making this configurable in the root `WIKI_SCHEMA.md`? Probably not at v2; the operator always reviews. Hardcode 2.
3. **Root-level `log.md`.** Deferred. Add when there's demand.
4. **Auto-promotion as a separate opt-in flag.** Decided: no. Operator-only.
5. **Merging frontmatter `description:` fields when two courses disagree.** Current proposal: keep both, separated by ` / `, or pick the longer one. Pick whichever is simpler to implement.
6. **What happens to a course's `_sources/<slug>.md` when its corresponding lesson folder is deleted?** Out of scope for this spec; existing v1 behaviour stands.
7. **Bidirectional `[[Course A/Foo]]` links.** If the operator manually writes such a link (full-path), should the skill normalize it on the next reindex? Probably leave alone — operator wrote it for a reason.

---

## 9. Testing strategy

1. **Fixture vault** with two courses, each having an overlapping concept and a unique concept.
2. **Round-trip test**: ingest a source into each course that mentions the overlapping concept → `lint` detects the duplicate → `promote` merges → `lint` is clean → `demote` reverses → state matches initial.
3. **Invariant test**: after every operation, no concept/entity filename exists in more than one location.
4. **Footnote-survival test**: after `promote`, every footnote on the root page resolves to an existing `Lessons/<Course>/_sources/<slug>.md` file via vault-relative path.
5. **Contradiction-on-promote test**: two courses define conflicting facts about the same concept → `promote` raises `## Contradictions` block, does not pick a winner.
6. **Refuse-demote test**: a root page is cited by sources from two courses → `demote --to <one course>` refuses with a clear message.
7. **Ingest-into-existing-root test**: a root page exists; ingest into a course that mentions it → fact lands on the root page, not on a new course-local copy.

---

## 10. Migration from v1

For an existing single-course vault (the current state of `trade-agents`):

1. Create root `WIKI_SCHEMA.md` and update root `CLAUDE.md` (manual, one-off — done in `trade-agents`).
2. No data migration is needed: the existing course-local layer continues to work; the root layer is empty and stays empty until the first `promote`.
3. The skill's `find_vault_root()` will detect the new root schema; behaviour for ingest/query/lint on existing pages is unchanged until promotion happens.

For a vault that was originally single-course and grows to multi-course: the second course is created as a new `Lessons/<Course>/` folder with its own `WIKI_SCHEMA.md` / `index.md` / `log.md` / `_sources/` / `_concepts/` / `_entities/`. The first ingest into the second course works exactly like v1. The two-tier behaviour only kicks in when `lint` flags the first cross-course duplicate.
