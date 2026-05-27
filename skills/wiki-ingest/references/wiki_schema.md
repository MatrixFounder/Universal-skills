# Default Wiki Schema (Reference)

This is the *reference* version of the schema the skill scaffolds into a fresh vault. The bundled `assets/WIKI_SCHEMA.template.md` is what gets copied. This file exists so an agent can read the conventions without needing access to the target vault.

## vault_id field (v1.1)

Two-tier vault roots (those with `schema_version: "2.0"` + `kind: vault-root`) MAY carry an additional **`vault_id: <slug>`** field in their root `WIKI_SCHEMA.md` frontmatter. The slug uniquely identifies the vault for downstream consumers — primarily the `obsidian-llm-wiki` index layer's `/wiki-enrich` bridge, which uses it as the SQLite partition key.

```yaml
---
name: WIKI_SCHEMA
schema_version: "2.0"
kind: vault-root
vault_id: my-vault              # ← TASK 017 v1.1 field
---
```

**Pattern**: `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`
- Length 3..32 characters.
- Lowercase ASCII only (no Cyrillic / CJK confusables).
- Kebab-case with internal hyphens; `--` is rejected.
- Leading character must be a letter; trailing must be letter or digit.

**Emit, don't enforce**: wiki-ingest READS the field if present and EMITS it in the v1.1 manifest, but absence is NOT an error in the skill itself. Standalone users without an index-layer consumer see no behavioural change. Strict-mode validation triggers only when a caller passes `--vault-id <slug>` to `wiki-ingest ingest` (or other v1.1 surfaces) — see [`./exit_codes.md`](./exit_codes.md) codes 23/24/25.

**Scaffolding**:
```sh
# fresh vault root with vault_id set:
wiki-ingest init <vault> --root --vault-id my-vault

# existing vault: hand-edit WIKI_SCHEMA.md to add the line (one-line migration).
```

`commands/init.py` validates the slug pattern BEFORE any I/O (`validate_vault_id_pattern` → exit 24 on malformed). Re-running `init --root --vault-id <same>` is idempotent; re-running with a DIFFERENT slug on an already-vault_id'd schema exits 1 (deliberate; hand-edit if intentional).

## When to read this

- The vault's own `WIKI_SCHEMA.md` is missing AND you cannot scaffold it (e.g., dry-run mode).
- You need to remember the default conventions because the vault's schema only shows deltas from default.
- You are deciding how to classify a new page (concept vs entity vs source).

## The conventions

### Directory layout

```
<vault>/
├── WIKI_SCHEMA.md       # conventions (overrides this default)
├── index.md              # catalog
├── log.md                # chronological log
├── _sources/              # per-source summary pages
├── _concepts/             # abstract concepts
├── _entities/             # concrete entities
└── raw/                  # (optional) immutable raw files
```

### Page kinds and their sections

**Source page** (`_sources/<slug>.md`):
- Owned by `summarizing-meetings`; do not write its body directly.
- Frontmatter: `title, date, meeting_type, participants, duration, languages, tags, related, concepts, ...`

**Concept page** (`_concepts/<Name>.md`):
- Frontmatter: `name, kind: concept, created`
- Sections: `## Definition` → `## Facts` → `## Contradictions` (only if any) → `## Sources mentioning this`
- Footnotes at the bottom: `[^src-<slug>]: [[<slug>]] — <Source Title>`

**Entity page** (`_entities/<Name>.md`):
- Same shape as concept page, with `kind: entity`.

### Concept vs Entity — disambiguation rules

| Marker | Concept | Entity |
|--------|---------|--------|
| Generalisable idea | ✅ | ❌ |
| Has a Wikipedia article on the *idea itself* | ✅ | ❌ |
| Proper noun (capitalised name of a thing) | ❌ | ✅ |
| Specific product/person/org/place | ❌ | ✅ |
| Acronym referring to a single product | ❌ | ✅ |
| Acronym referring to a general technique | ✅ | ❌ |

Examples:
- `Sharpe Score` → concept
- `Hermes Agent` → entity (specific product)
- `Reinforcement Learning` → concept
- `Railway` (hosting platform) → entity
- `Bittensor` → entity
- `Bittensor Subnet Trading` → concept (general activity), even though "Bittensor" is an entity
- `Andrej Karpathy` → entity

**Tie-breaker**: when genuinely uncertain, choose `entity`. It's less likely to mis-classify, and entity pages are still valid wiki nodes.

### Slugs

- **Source slug**: kebab-case from the title. `"AI Trading Agent Holy Grail: Self-Improving Agent with Hermes"` → `ai-trading-agent-holy-grail-self-improving-agent-hermes`. Keep it under ~60 chars; truncate at a word boundary if longer.
- **Concept/entity slug**: not used — the page filename is the canonical name verbatim (with spaces). Obsidian resolves `[[Hermes Agent]]` to `_entities/Hermes Agent.md`.

### Citation footnotes

Format: `[^src-<source-slug>]`

Example on a concept page:

```markdown
## Facts

- Risk-adjusted return: `Sharpe = (R_p − R_f) / σ_p`. [^src-hermes-trading-agent]
- A min Sharpe of 1 is a sensible floor for self-improving trading agents. [^src-hermes-trading-agent]
- For crypto strategies, R_f is often treated as 0 due to absence of clear baseline. [^src-quant-crypto-handbook]

## Sources mentioning this

- [[hermes-trading-agent]] — 2026-05-25 — AI Trading Agent Holy Grail
- [[quant-crypto-handbook]] — 2026-03-12 — Quant Crypto Handbook chapter 4

---

[^src-hermes-trading-agent]: [[hermes-trading-agent]] — AI Trading Agent Holy Grail
[^src-quant-crypto-handbook]: [[quant-crypto-handbook]] — Quant Crypto Handbook chapter 4
```

This is the canonical shape — `wiki_ops.py upsert-page` produces exactly this layout.

### Contradiction markup

```markdown
## Contradictions

> ⚠️ **Contradiction flagged** — operator review needed.
> - Existing claim: <quoted text>
> - New claim from [[<new-source-slug>]]: <new claim> [^src-<new-source-slug>]
```

When the same page accumulates multiple contradictions, they stack as separate `> ⚠️` blocks under the same `## Contradictions` header.

### log.md entry format

```markdown
## [2026-05-25] ingest | AI Trading Agent Holy Grail
- Source path: `transcripts/01-systems-hermes.txt`
- Summary page: [[ai-trading-agent-holy-grail]]
- Pages touched: [[Sharpe Score]], [[Reinforcement Learning]]
- Pages created: [[Hermes Agent]], [[Railway]], [[Bittensor Subnets]], [[Scientific Method for Strategy Iteration]]
- Contradictions flagged: 0
```

Grep-friendly prefix `## [YYYY-MM-DD] ingest|query|lint` is non-negotiable.

### index.md layout

```markdown
## Sources
- [[ai-trading-agent-holy-grail]] — 2026-05-25 — AI Trading Agent Holy Grail — one-line TL;DR

## Concepts
- [[Sharpe Score]] — introduced by [[ai-trading-agent-holy-grail]]
- [[Reinforcement Learning]] — introduced by [[ai-trading-agent-holy-grail]]

## Entities
- [[Hermes Agent]] — introduced by [[ai-trading-agent-holy-grail]]
- [[Railway]] — introduced by [[ai-trading-agent-holy-grail]]
```

The agent can extend each row with extra metadata over time, but the first column (`[[slug]]`) is the dedupe key.

---

## Root schema (v2.0) — Two-tier vaults (TASK 016)

When a vault holds **multiple parallel courses**, an OUTER
`WIKI_SCHEMA.md` lives at the vault root and governs cross-course
concerns. The OUTER schema has `schema_version: 2.0` and `kind:
vault-root`. Each course keeps its own `WIKI_SCHEMA.md` with
`schema_version: 1.x`.

### Root frontmatter

```yaml
---
name: WIKI_SCHEMA
description: Vault-root schema for two-tier wiki-ingest.
schema_version: "2.0"
kind: vault-root
---
```

`wiki-ingest` checks `schema_version` and `kind`; the rest is freeform.
The bundled template
[`assets/WIKI_SCHEMA.root.template.md`](../assets/WIKI_SCHEMA.root.template.md)
is copied verbatim by `init <vault> --root`.

### Root layout

```
<vault>/
├── WIKI_SCHEMA.md            # v2.0 (this section)
├── _concepts/                # shared concepts (lazy; populated by promote)
├── _entities/                # shared entities (lazy)
├── index.md                  # optional; created on first promote
└── Lessons/                  # convention, NOT hardcoded
    ├── <Course A>/           # v1.x schema, full v1 layout
    └── <Course B>/           # same
```

NO `_sources/` and NO `log.md` at the root — sources live only in
courses (R13.2), and per-course logs serve as the audit trail.

### One-page-one-place invariant

A canonical filename lives in **exactly one** of (a) some course's
`_concepts/`/`_entities/`, or (b) the root's. `lint` detects violations
and exits non-zero.

### Footnote-convention difference

Course-local pages use the v1 short form: `[^src-foo]: [[foo]] — Title`.

Root pages use the **vault-relative** form so citations resolve from
the shared layer regardless of which course owns the source:

```markdown
[^src-foo]: [[Lessons/Hermes/_sources/foo]] — Title
```

The vault-relative prefix is computed as
`course_root.relative_to(vault_root)`; `Lessons/` is conventional, not
hardcoded.

### Course-`index.md` additions

When a course's `_sources/` cite a root-promoted concept, `reindex`
emits a `## Shared concepts referenced` / `## Shared entities
referenced` section to that course's `index.md`:

```markdown
## Shared concepts referenced

- [[Sharpe Score]] — (shared)
```

### Operator workflow (promote / demote / lint)

See [`cross_course_promotion.md`](cross_course_promotion.md) for the
full playbook.
