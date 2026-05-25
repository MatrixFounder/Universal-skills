# Query / Lint / Reindex — Workflow Details

The judgement-heavy steps for the three maintenance modes. The script handles the file mechanics (`find`, `lint`, `reindex`); this doc covers the *decisions* you make as the LLM driving them.

## Query mode

### When to use
- Operator asks a substantive question about already-ingested material.
- A previous query touched the wiki and you want to extend the chain ("now compare those two sources on metric X").
- Operator asks "what does the wiki say about Y" — even casually.

### Term extraction

The `find` subcommand uses substring matching on the lowercased text. To get good hits:

- Use **content words only**. Drop articles, pronouns, "say", "do", "is", "tell me".
- Use **multiple specific terms** rather than one generic one. `sharpe crypto` is better than `metric`.
- Include **proper-noun spellings** the user used — they probably match how the wiki has them.
- 2–4 terms is the sweet spot. More terms doesn't hurt scoring (sum-of-counts), but pollutes when terms are rare.

### Filtering hits

`find` returns up to `--limit` hits sorted by total term-count. Decide what to read:

- **Read top hit unconditionally.**
- **Read additional hits while** their score ≥ 20% of top hit's score.
- **Stop** when score drops below that or you have 5 pages. Reading more rarely helps and dilutes the answer.
- **Kind filter** (`--kinds source` or `--kinds concept,entity`): use when the operator asks "which sources discuss X" (force source) or "what does the wiki define X as" (force concept/entity).

### Synthesis rules

- **Every claim cites a page** as `[[<slug>]]` inline. The wiki is auditable; the answer should be too.
- **If two pages disagree, surface it** explicitly. Don't pick a winner without operator input.
- **Distinguish source claims from concept-page synthesis**. A concept page is itself derived from sources; quoting it is fine but mention which sources back it if relevant.
- **Length**: 4–10 sentences for most questions. Longer only if the question is structured ("compare A and B and C in detail").

### When to file the answer back

Karpathy's principle: "good answers can be filed back into the wiki." A filed answer becomes findable by the next query, which is the compounding pattern.

File the answer back when:
- The question is **analytical or comparative** (compares two sources, traces evolution, summarises a thread)
- The operator **explicitly asks** to save it
- You can name a **specific reusable insight** as the title ("Sharpe vs Sortino tradeoffs", "Hermes architecture overview")

Don't file when:
- The question is a **one-shot lookup** ("what's the Sharpe formula?") — the concept page already covers it
- The answer is **mostly verbatim from one source** — just point to that source

When filing: write to `<vault>/_sources/query-<slug>.md` with frontmatter `kind: source` and a `query:` field instead of `participants:` or similar. Treat the synthesis as if it were a new ingestable source for future queries.

## Lint mode

### When to use
- Operator says "lint", "health check", "what's missing", "find orphans"
- After every ~10 ingests as a periodic hygiene check (suggest this in the ingest report)
- Before a query session, if the wiki feels stale — fix dangling links first so the query has cleaner data

### Reading the report

```json
{
  "totals": { "orphans": N, "dangling_link_targets": N, "pages_with_open_contradictions": N, "missing_concept_pages": N },
  "orphans": [{ "page": "...", "kind": "..." }, ...],
  "dangling_links": [{ "target": "...", "referenced_by": [...] }, ...],
  "open_contradictions": [{ "page": "...", "count": N }, ...],
  "missing_concept_pages": [{ "name": "...", "mentioned_in": [...], "count": N }, ...]
}
```

### Action playbook per category

**Orphans** (concept/entity pages with no inbound `[[wiki-links]]`):
- *Often benign*: the page was created by an ingest but the source frontmatter used the bare name (no `[[brackets]]`), so the link counter missed it. Fix by adding `[[<name>]]` to the source's `related:` field — or accept that frontmatter mentions count too if you want.
- *Truly orphan*: a concept was upserted but no source actually references it semantically. Either link it from a related concept page (under `## See also`) or delete it.
- *Don't auto-delete*. Surface the candidates; operator decides.

**Dangling links** (`[[X]]` references where X has no page):
- **Highest priority** — these are the wiki's promises to the reader that something exists, broken.
- For each, propose one of:
  - **Ingest a source** that would create the page (if you know one)
  - **Rename the link** to an existing page (e.g., `[[Hermes]]` → `[[Hermes Agent]]` via Edit)
  - **Delete the link** if it's truly out of scope
- For high-mention targets (referenced by ≥3 pages), suggest creating a stub concept page now from a one-line synthesis of the referring sources.

**Open contradictions** (pages with `## Contradictions` blocks):
- These are pending operator decisions. Present each with: the page, the two claims, and the sources backing each.
- Offer to apply the resolution: "Which claim should win, A or B? I'll Edit the page to fold the chosen claim into Facts and archive the loser under `## Resolved contradictions`."
- Never auto-resolve.

**Missing concept pages** (concepts mentioned in N+ sources, no page):
- These are easy wins. Propose creating a stub page now using a one-sentence synthesis of how the N sources describe the concept.
- Use the same `upsert-page` mechanism with a synthetic source slug like `lint-bootstrap-2026-05-25` or, better, pick the most authoritative source's slug.

### Cadence

- Lint takes seconds; run it freely.
- Reporting and discussing the diagnostics takes 5–15 minutes per session at moderate vault size.
- Don't try to fix everything in one pass. Prioritise: dangling-links → contradictions → missing-pages → orphans.

## Reindex mode

### When to use

- `index.md` got manually edited and is now broken
- Many pages were renamed/moved and index slugs point to the wrong places
- Lint reports the index disagrees with on-disk pages (rare; the script keeps them in sync during ingest)
- The vault was imported from another tool and `index.md` was hand-written or missing structure

### What `reindex` does

- Walks `_sources/`, `_concepts/`, `_entities/` in that order
- For each page, extracts:
  - `title` from frontmatter (fall back to `name` or filename stem)
  - `date` from frontmatter (Sources only)
  - One-line description from `summary:`/`tldr:`/`description:` field, or the page's `## TL;DR` section, or the first sentence of `## Definition`
- Rewrites `index.md` from the bundled template with fresh rows under `## Sources`, `## Concepts`, `## Entities`
- **Preserves `## Notes`** verbatim from the existing index (operator's free-form notes)
- Does NOT preserve other custom sections — if you've added unusual sections to `index.md`, copy them to `## Notes` first

### Safety pattern

Reindex overwrites `index.md`. Before running:

1. If the vault is a git repo, suggest: `git diff --stat` first; commit current state if dirty.
2. Otherwise suggest the operator save a copy: `cp index.md index.md.bak`.
3. Then run `reindex`.
4. Show the diff and let the operator confirm. If they want to revert: restore from the backup or `git checkout index.md`.

### What to do after reindex

- If you used reindex to fix drift, run `lint` to verify orphans/dangling-links counts dropped.
- If reindex changed many rows, log a `reindex` event with `--detail "reason=<text>"` so the rebuild is auditable.
