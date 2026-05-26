---
name: WIKI_SCHEMA
description: Conventions for this LLM-wiki. Read this before any ingest/query/lint operation.
schema_version: 1.0
---

# Wiki Schema — Conventions for This Vault

This file describes the conventions for the vault. It was scaffolded by `wiki-ingest`. Edit it to fit your domain — the skill will follow whatever this file says.

## Layout

```
<vault>/
├── WIKI_SCHEMA.md       # this file — conventions
├── index.md              # content catalog (always up-to-date)
├── log.md                # chronological ingest/query/lint record
├── _sources/              # per-source summary pages (output of summarizing-meetings)
├── _concepts/             # one page per abstract concept (Sharpe Score, Reward Function, ...)
├── _entities/             # one page per concrete entity (Hermes Agent, Railway, person, org)
└── raw/                  # (optional) immutable raw source files; never modified by the skill
```

## Page kinds

- **Source page** (`_sources/<slug>.md`) — owned by `summarizing-meetings`. Full structured summary. Frontmatter includes `concepts:` and `related:`.
- **Concept page** (`_concepts/<Name>.md`) — abstract concept. Has `## Definition`, `## Facts`, `## Sources mentioning this`, and `[^src-<slug>]` footnotes.
- **Entity page** (`_entities/<Name>.md`) — concrete thing/person/org. Same sections as concept pages.

## Concept vs Entity heuristic

- **Concept** = generalisable idea, would have a Wikipedia article on the *concept* itself (e.g., Sharpe Ratio, Reinforcement Learning, Scientific Method).
- **Entity** = proper noun, specific product/person/org (e.g., Hermes Agent, Railway, Andrej Karpathy).
- When uncertain → treat as entity (lower bar, less likely to be wrong).

## Naming

- Page filenames use the **canonical name** verbatim (with spaces), e.g., `Hermes Agent.md`, `Sharpe Score.md`. This is what Obsidian's `[[wiki-links]]` expect.
- Source page slugs are kebab-case, derived from the title: e.g., `self-improving-trading-agent-hermes`.

## Frontmatter

All pages have YAML frontmatter. Minimum fields:

```yaml
---
name: <name or slug>
kind: <source|concept|entity>
created: YYYY-MM-DD
---
```

Source pages inherit the richer frontmatter that `summarizing-meetings` produces (title, date, participants, concepts, related, ...).

## Citation style

Every fact added to a concept/entity page from a specific source is followed by a footnote of the form `[^src-<slug>]` where `<slug>` matches the source page filename without extension. The footnote definition at the bottom of the page resolves it: `[^src-<slug>]: [[<slug>]] — <Source Title>`.

Example:

```markdown
- A risk-adjusted return measure; formula `(R_p − R_f) / σ_p`. [^src-hermes-trading-agent]
- Min Sharpe 1 recommended as a baseline for self-improving trading agents. [^src-hermes-trading-agent]

[^src-hermes-trading-agent]: [[hermes-trading-agent]] — AI Trading Agent Holy Grail
```

This is what makes the wiki **auditable**: every claim can be traced back to its raw source in O(1).

## Contradiction handling

When a new source contributes a fact that disagrees with an existing claim on the same concept page, the skill does NOT pick a winner. It inserts a block under `## Contradictions`:

```markdown
> ⚠️ **Contradiction flagged** — operator review needed.
> - Existing claim: <quoted text from prior source>
> - New claim from [[<new-source-slug>]]: <new claim> [^src-<new-source-slug>]
```

The operator resolves these manually. Run `wiki_ops.py scan <vault>` and grep for `Contradictions` headers to find open ones.

## index.md

Three top-level sections — `## Sources`, `## Concepts`, `## Entities` — each a bullet list of `[[wiki-links]]` with one-line descriptions. Updated on every ingest. Use as the LLM's primary index at small/medium scale (~100 sources); switch to BM25/vector search (e.g., `qmd`) when bigger.

## log.md

Append-only. Each entry starts with `## [YYYY-MM-DD] ingest|query|lint | <title>` so `grep "^## \[" log.md | tail -5` gives the last 5 events. Body of each entry lists which pages were touched/created and how many contradictions were flagged. Never edit past entries.

## Optional sections

If your domain needs more page kinds (e.g., `Methods/`, `Decisions/`, `People/`), add them here and the skill will respect them. You'll need to extend `wiki_ops.py` to know the new kinds, or use a generic upsert.
