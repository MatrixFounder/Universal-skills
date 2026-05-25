# Wiki Ingest — Manual

## Overview

**Wiki Ingest** is a meta-skill that turns raw sources (transcripts, articles, summaries) into nodes of a **compounding** Obsidian-style knowledge base, following Andrej Karpathy's [llm-wiki pattern](https://github.com/karpathy/llm-wiki). Unlike a one-off summary skill, it maintains a *living wiki* over time — every new source touches 10-15 existing pages: concept pages, entity pages, the index, the chronological log.

It delegates per-source summarisation to **[Summarizing Meetings](summarizing-meetings_manual.md)** and adds the *maintenance layer*: deterministic file operations (upserts, dedup, citation footnotes, contradiction flags) plus LLM judgement for concept-vs-entity classification, fact extraction, and contradiction detection.

### Key Characteristics

| Property | Value |
|----------|-------|
| **Type** | Meta-Skill (Core) |
| **Execution Mode** | `hybrid` (Python script + LLM judgement) |
| **Tier** | 2 |
| **Input** | Path to a raw source OR a pre-made summary; path to the vault |
| **Output** | Mutated Obsidian vault: source page in `_sources/`, concept/entity pages in `_concepts/_entities/`, updated `index.md` + `log.md` |
| **Dependencies** | Pure Python stdlib; optionally invokes Summarizing Meetings skill |

---

## Why a Maintenance Layer

The standard RAG pattern is **stateless**: every query re-derives knowledge from raw documents. Karpathy's insight:

> The LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources.

In practice that means **every new source must touch dozens of files**, not just produce its own summary. The tedious maintenance — updating cross-references, keeping summaries current, flagging contradictions, maintaining citation footnotes — is exactly what humans abandon. This skill is the engine that does it.

The three layers:

```
Raw sources (immutable)   ──┐
                            ├──► concept pages (auditable, additive)
Summary pages (LLM-owned) ──┤
                            ├──► entity pages
                            └──► index.md, log.md
```

---

## Vault Layout

The skill scaffolds (and expects) this structure. Folders use the Obsidian system-folder convention (leading underscore sorts them to the top of the file tree and signals "meta-content, not user notes"):

```
<vault>/
├── WIKI_SCHEMA.md       # conventions for THIS vault (created by `init`)
├── index.md              # catalog (## Sources / ## Concepts / ## Entities)
├── log.md                # chronological append-only journal
├── _sources/             # per-source summary pages (LLM-owned)
├── _concepts/            # abstract concepts (Sharpe Score, Reinforcement Learning, ...)
├── _entities/            # concrete entities (Hermes Agent, Anthropic, ...)
└── raw/                  # (optional) immutable raw source files, never modified
```

**Display vs disk naming**: section headers inside `index.md` stay human-readable (`## Sources`, `## Concepts`, `## Entities`); only the folder names use underscores. Custom sections you add to `index.md` (`## Notes`, `## Pinned`, etc.) are preserved by `reindex`.

---

## Quick Start

### Ingest a raw transcript end-to-end

```
Use the wiki-ingest skill:
Ingest the transcript at /Users/me/notes/lesson-01.txt into my Obsidian
llm-wiki at ~/obsidian-vault. Generate the summary via summarizing-meetings,
then upsert concept and entity pages, update the index, and append to log.
```

The agent will:
1. Run `wiki_ops.py scan <vault>` to discover existing concepts/entities.
2. If `WIKI_SCHEMA.md` is absent → run `wiki_ops.py init <vault>` (scaffolds schema/index/log/subdirs once).
3. Invoke **Summarizing Meetings** with the known-concepts list as context so wiki-links stay consistent.
4. Save the produced summary to `_sources/<slug>.md`.
5. For each entry in the summary's `concepts:` and `related:` frontmatter, classify as concept or entity and `upsert-page` (creates stub OR adds new fact + footnote citation).
6. `update-index` + `append-log`.

### Ingest a pre-made summary (skip the LLM step)

```
Use the wiki-ingest skill:
I already have a summary at notes/2026-04-12-summary.md — just register it
into my vault at ~/obsidian-vault. Upsert its concepts/entities, update the
index, append to log. Do NOT re-summarize.
```

The agent runs `wiki_ops.py register-summary <vault> --summary-path <path>` — copies the file into `_sources/`, auto-normalises filesystem-unsafe characters in `concepts:`/`related:` (e.g., `Railway 24/7 Deployment` → `Railway 24-7 Deployment`), and returns the upsert targets for Phase 3.

### Maintenance modes

```
# 1) Health-check
"Lint my Obsidian wiki at ~/obsidian-vault — find orphans, dangling links,
contradictions, and concepts mentioned in 2+ sources without a page."

# 2) Rebuild the index from disk
"Reindex my wiki at ~/obsidian-vault. Preserve my custom ## Notes section."

# 3) Answer a question with citations
"What does my wiki say about Sharpe Score in crypto? Any disagreements?"
```

---

## The Four Modes

### Ingest (default)

Pipeline (7 phases — see [`SKILL.md`](../../skills/wiki-ingest/SKILL.md) §7):

1. **Resolve inputs**: source path / summary path + vault path
2. **Scan + scaffold**: discover existing pages, init schema if needed
3. **Generate or register summary**: delegate to `summarizing-meetings`, OR `register-summary` if pre-made
4. **Extract upsert targets**: classify each entry in `concepts:` / `related:` as concept or entity
5. **Upsert each**: additive — never overwrites existing pages, flags contradictions, attaches `[^src-<slug>]` footnotes
6. **Update index + log**: `update-index` adds rows, `append-log` records the event
7. **Report to operator**

### Lint

`wiki_ops.py lint <vault>` returns a JSON health report with four categories:

| Finding | Means |
|---|---|
| **Orphans** | Concept/entity pages with no inbound `[[wiki-links]]` — possibly stale |
| **Dangling links** | `[[X]]` references where X has no page |
| **Open contradictions** | Pages containing `## Contradictions` sections (pending operator review) |
| **Missing concept pages** | Names appearing in `concepts:` of N+ sources without a dedicated page |

Action priority: **dangling → contradictions → missing → orphans** (per [`references/query_lint_workflow.md`](../../skills/wiki-ingest/references/query_lint_workflow.md)).

### Reindex

`wiki_ops.py reindex <vault>` rebuilds `## Sources`, `## Concepts`, `## Entities` sections of `index.md` from on-disk pages. All other sections (`## Notes`, `## Pinned`, `## Reading Queue`, etc.) are preserved verbatim. Duplicate header bodies are **merged** (with a `---` separator) and a warning is emitted so the operator can rename if unintended.

**Safety**: backup `index.md` first (`cp index.md index.md.bak` or commit to git) — reindex is the only destructive default-path operation.

### Query

`wiki_ops.py find <vault> --terms "<words>"` returns a ranked JSON shortlist of pages matching keywords. The agent then reads the top 3-5 hits and synthesises an answer with `[[<slug>]]` inline citations. Following Karpathy's "good answers can be filed back into the wiki", analytical/comparative answers can be saved as new `_sources/query-*.md` pages for future queries to find.

Every query event is logged via `log-event --event query --title "<question>"` for audit.

---

## Citation Pattern (the auditability invariant)

Every fact on a concept or entity page traces back to its source via a Markdown footnote:

```markdown
## Definition

Risk-adjusted return: `(R_p − R_f) / σ_p`. [^src-hermes-trading-agent]

## Facts

- Min Sharpe of 1 recommended as a baseline. [^src-hermes-trading-agent]
- Many funds prefer Sortino over Sharpe for asymmetric strategies. [^src-quant-crypto-handbook]

## Sources mentioning this

- [[hermes-trading-agent]] — 2026-05-25 — AI Trading Agent Holy Grail
- [[quant-crypto-handbook]] — 2026-03-12 — Quant Crypto Handbook ch.4

## Footnotes

[^src-hermes-trading-agent]: [[hermes-trading-agent]] — AI Trading Agent Holy Grail
[^src-quant-crypto-handbook]: [[quant-crypto-handbook]] — Quant Crypto Handbook ch.4
```

`<slug>` matches the source page filename without extension. Click the footnote → jump to the source. This is what makes the wiki **auditable at 50 ingests**, not a noise pile.

---

## Contradiction Handling (the don't-pick-a-winner invariant)

When a new source contributes a fact that disagrees with an existing claim, the skill does **not** resolve it. Instead, it inserts a `## Contradictions` block:

```markdown
## Contradictions

> ⚠️ **Contradiction flagged** — operator review needed.
> - Existing claim: min Sharpe of 1 recommended
> - New claim from [[conservative-crypto-guide]]: For crypto, a minimum Sharpe
>   of 0.5 is sufficient. [^src-conservative-crypto-guide]
```

The `--contradicts <quote>` argument is **substring-verified** against the existing page text — if the agent hallucinates a non-existent existing claim, the script refuses (exit code 5) unless `--force` is passed. Operator resolves contradictions manually by editing the page.

---

## Filesystem Safety Guarantees

The script enforces multiple invariants you can rely on:

| Threat | Defence |
|---|---|
| Path traversal in `--name` or `--slug` (`../../etc/passwd`) | `_safe_name()` rejects `..`, `/`, `\`, leading `.`, control chars, template placeholders `{{}}`, names > 200 chars |
| Case collision on macOS APFS / NTFS (`Sharpe Score` vs `sharpe score`) | Pre-write canonicalisation check, refuses without `--force` |
| Non-ASCII titles producing empty slugs (Russian/Chinese/Japanese) | Unicode-aware `slugify` using `\w` regex; titles like "Анализ торговых стратегий" → `анализ-торговых-стратегий` |
| Code-fence headers in concept pages corrupting section parsing | `_mask_code_fences()` strips fenced content before regex matching |
| Duplicate ingest of the same source | `upsert-page` dedupes by slug; `append-log` dedupes by `(date, event, source-slug)`; pass `--force-log` to override |
| Newlines in log details breaking grep-friendly format | `log-event` rejects newlines and log-header prefixes in `--detail` values |

---

## `wiki_ops.py` Subcommand Reference

```
scan          dump vault state as JSON (concepts, entities, sources, schema/index/log presence)
init          scaffold WIKI_SCHEMA.md, index.md, log.md, _sources/_concepts/_entities/ (idempotent)
register-summary  copy a pre-made summary into _sources/, auto-normalise unsafe names, return upsert targets
upsert-page   create OR additively update a concept/entity page (deduplicated, footnoted)
update-index  add rows under ## Sources / ## Concepts / ## Entities (deduplicated by slug)
append-log    append an ingest entry (idempotent by date+event+slug; --force-log to override)
log-event     append a generic event (query, lint, reindex); rejects multiline / log-header injection
find          keyword search; returns ranked JSON hits with optional --kinds filter
lint          health report (orphans, dangling, contradictions, missing concept pages)
reindex       rebuild Sources/Concepts/Entities sections; preserve custom sections; merge duplicates with warning
```

All mutating subcommands support `--dry-run`. Most return JSON to stdout.

Full contract: [`SKILL.md`](../../skills/wiki-ingest/SKILL.md) §4.

---

## Composition with Other Skills

The canonical pipeline:

```
       transcript-fetcher          summarizing-meetings              wiki-ingest
           │                              │                              │
URL ───────┤                              │                              │
           ▼                              │                              │
       lesson.txt ─────────────────────► .md summary ──────────────────► _sources/<slug>.md
                                                                          + concept/entity upserts
                                                                          + index.md + log.md
```

- **Transcript Fetcher** pulls a clean plaintext transcript from a YouTube/Vimeo/Skool URL.
- **Summarizing Meetings** generates the structured summary document.
- **Wiki Ingest** registers the summary into the wiki and maintains the cross-reference graph.

You can use any of the three independently, but the composition is where the value compounds.

---

## Examples

### Sample summary fixture

[`skills/wiki-ingest/examples/sample_summary.md`](../../skills/wiki-ingest/examples/sample_summary.md) — a trimmed example summary with the rich frontmatter the skill expects (`type: lesson-summary`, `concepts:`, `related:`). Drop it into `register-summary` to exercise Flow B end-to-end without an external file.

### Annotated walkthrough

[`skills/wiki-ingest/examples/usage_example.md`](../../skills/wiki-ingest/examples/usage_example.md) — two full flows side by side: raw transcript → wiki (Flow A) and pre-made summary → wiki (Flow B), with command-line examples and expected output JSON.

### Evals

[`skills/wiki-ingest/evals/evals.json`](../../skills/wiki-ingest/evals/evals.json) — 10 test cases covering all four modes plus adversarial inputs (path-traversal, unicode titles, idempotency). Fixtures in [`evals/fixtures/`](../../skills/wiki-ingest/evals/fixtures/). Run via `skill-creator/scripts/run_eval.py`.

---

## Skill File Structure

```
wiki-ingest/
├── SKILL.md                            # 12-section spec (red flags, contract, instructions for 4 modes)
├── scripts/
│   └── wiki_ops.py                     # 9 subcommands (pure stdlib, ~1350 lines)
├── assets/                             # bundled templates (copied by `init` + `upsert-page`)
│   ├── WIKI_SCHEMA.template.md         # default vault conventions
│   ├── index.template.md               # empty index skeleton (3 reserved sections)
│   ├── log.template.md                 # empty log skeleton
│   ├── concept_page.template.md        # stub for new concept page
│   └── entity_page.template.md         # stub for new entity page
├── references/                         # judgement-heavy guidance for the agent
│   ├── karpathy-llm-wiki.md            # foundational methodology by Andrej Karpathy (imported verbatim)
│   ├── wiki_schema.md                  # full vault conventions (layout, naming, citation, contradiction)
│   ├── ingest_workflow.md              # concept vs entity classification, fact extraction, contradiction detection
│   └── query_lint_workflow.md          # term extraction, hit filtering, lint action playbook, reindex safety
├── examples/
│   ├── sample_summary.md               # self-contained example summary for register-summary
│   └── usage_example.md                # annotated Flow A + Flow B walkthrough
└── evals/
    ├── evals.json                      # 10 test cases (4 modes + adversarial + idempotency + unicode)
    ├── trigger_evals.json              # 20 trigger-eval queries (12 should-trigger + 8 should-not)
    └── fixtures/                       # 4 self-contained fixture files
        ├── summary-pre-made.md         # rich frontmatter; basic register-summary fixture
        ├── summary-contradicting.md    # contradicts pre-made.md on Sharpe threshold
        ├── summary-unicode-title.md    # Russian (Cyrillic) title for slug-edge-case
        └── transcript-trading-bot.txt  # short raw transcript for full ingest pipeline
```

---

## Anti-Patterns (Do NOT)

| Anti-pattern | Why wrong |
|---|---|
| Manually edit concept pages instead of `upsert-page` | Bypasses the footnote-citation invariant; the wiki loses auditability |
| Resolve contradictions silently | The whole `## Contradictions` mechanism exists *because* the skill refuses to pick a winner — operator decides |
| Skip the `log.md` entry | The log is grep-friendly chronological memory for future LLM sessions; git diff is for humans |
| Ingest the same source twice without `--force-log` | The script dedupes by default — re-running is a safe no-op; only `--force` if you intentionally want a second entry |
| Use bare `[[wiki-links]]` in `prerequisites:` field of summaries | Prerequisites are *meta-info for the reader*, not wiki pages — they pollute the link graph. Use plain strings |
| Run `reindex` without a backup | `reindex` is the only operation that overwrites `index.md` — commit to git or `cp index.md index.md.bak` first |

Full anti-rationalisation table: [`SKILL.md`](../../skills/wiki-ingest/SKILL.md) §9.

---

> **Related**: [Summarizing Meetings Manual](summarizing-meetings_manual.md) · [Transcript Fetcher Manual](transcript-fetcher_manual.md)
