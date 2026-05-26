---
name: WIKI_SCHEMA
description: Vault-ROOT schema for two-tier (cross-course) wiki-ingest. Governs cross-course concerns; per-course conventions live in each Lessons/<Course>/WIKI_SCHEMA.md.
schema_version: "2.0"
kind: vault-root
---

# Vault-Root Schema — Cross-Course Conventions

This file marks the **vault root** of a two-tier `wiki-ingest` layout.
Course-local conventions live in each `Lessons/<Course>/WIKI_SCHEMA.md`
(schema_version `1.x`); this file governs only the **shared layer**.

## Layout

```
<vault>/                                # ← this file lives at the root
├── WIKI_SCHEMA.md                      # schema_version: 2.0 (this file)
├── _concepts/                          # shared concepts (lazy; populated by `promote`)
├── _entities/                          # shared entities (lazy; populated by `promote`)
├── index.md                            # (optional) catalog of the shared layer
└── Lessons/                            # convention only — NOT hardcoded
    ├── Course A/                       # each course has its own
    │   ├── WIKI_SCHEMA.md              # schema_version: 1.x
    │   ├── _sources/  _concepts/  _entities/
    │   ├── index.md  log.md
    └── Course B/                       # same shape
```

**`Lessons/` is conventional, not hardcoded.** `wiki-ingest`
discovers courses by walking every descendant directory; any folder
with a `WIKI_SCHEMA.md` declaring `schema_version: 1.x` is treated
as a course. Course-of-courses layouts (e.g. `Lessons/2026/Spring/Hermes/`)
are supported.

## Load-bearing invariant — one-page-one-place

A given canonical filename (e.g. `Sharpe Score.md`) lives in
**exactly one** of:

- some course's `_concepts/` or `_entities/`, OR
- the vault root's `_concepts/` or `_entities/` (the shared layer).

Never both. `wiki-ingest lint <vault>` detects violations and refuses
to merge until the operator resolves them.

## Promote / Demote (operator-only, lazy)

The shared layer is populated **on demand** by the operator:

- `wiki-ingest promote "<Name>" --vault <vault>` — merge ≥2 course-local
  copies into a single root page. Dry-run by default; pass `--apply`
  to commit.
- `wiki-ingest demote "<Name>" --to "<Course>" --vault <vault>` — move
  a root page back into one course. Refuses if any other course still
  cites the page.

Lint flags candidates for promotion (`cross_course_duplicate`) and any
invariant violations (`invariant_violation`).

## Footnote convention on root pages

Course-local pages keep the short footnote form:

```markdown
[^src-foo]: [[foo]] — Some Source Title
```

Root pages use the **vault-relative** form so citations resolve from
the shared layer:

```markdown
[^src-foo]: [[Lessons/Course A/_sources/foo]] — Some Source Title
```

The vault-relative prefix is computed as `course_root.relative_to(vault_root)`;
the `Lessons/` substring in the example is illustrative, not literal.

## Source of truth for the skill

This file marks the vault root; the skill's behavioural contract is in
`skills/wiki-ingest/SKILL.md`. Edit this file's prose freely — `wiki-ingest`
checks only `schema_version` and `kind`.
