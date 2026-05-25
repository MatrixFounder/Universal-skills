# Ingest Workflow — Judgement-Heavy Steps

This file is for the steps that aren't deterministic and need LLM judgement. The script handles the file mechanics; this doc handles the *decisions* you make as the LLM driving the script.

## Step A — Build the known-concepts hint for summarizing-meetings

The `wiki_ops.py scan` JSON has `concepts: [...]` and `entities: [...]`. Concatenate them into one list and pass it to `summarizing-meetings` like this:

> "Known wiki entries — when the source mentions any of these, use the EXACT name in `concepts:` frontmatter and `[[wiki-links]]`. Do not invent variants. List: `Sharpe Score`, `Hermes Agent`, `Railway`, ..."

This prevents the most common ingest failure mode: variant naming that creates dangling `[[Hermes]]` next to existing `[[Hermes Agent]]`.

## Step B — Classify each upsert target as concept or entity

For each name in the new summary's `concepts:` and `related:` frontmatter:

1. Look up the name in the scan JSON. If it already exists → use its existing kind (don't re-classify).
2. If new → apply the heuristic from `wiki_schema.md` §Concept vs Entity.
3. If genuinely ambiguous → default to `entity` (less harmful when wrong).

**Batch ambiguity check**: if you have ≥3 ambiguous names in one ingest, ask the operator once at the start of Phase 4 with a single multi-choice question. Don't ask per-name — that destroys flow.

## Step C — Extract the one-sentence definition for new pages

When creating a stub concept/entity page, the script needs a one-sentence definition (passed via `--definition`). Source it from, in this order:

1. The summary's `### Key Concepts and Definitions` section (or its translated header) — the bullet for that exact name. Lift the definition verbatim, lightly trimmed.
2. The summary's `### Technical Glossary` "What it is" line.
3. The first sentence of the summary's TL;DR that mentions the term.
4. If none of the above → omit `--definition`; the stub gets a placeholder. (Better than fabricating.)

## Step D — Decide whether to add a fact to an existing page

When the page already exists, the question is: does the new summary contain a fact the page lacks?

**Add a fact if** any of these are true:
- The page's `## Facts` section does not contain a claim about the same sub-aspect (e.g., page has the formula but not the "min Sharpe 1" recommendation → add).
- The new fact specifies a numeric threshold, a formula, a procedure, or a counter-example absent from the page.
- The new fact relates the concept to a different concept the page does not yet link to (cross-reference enrichment).

**Skip the fact (but still upsert source row) if**:
- The new summary just re-states an existing claim in different words. The source-row update alone signals "another source agrees."
- The new fact is meta ("the speaker called this a holy grail") rather than substantive.

**Default when uncertain**: add the fact. Redundancy is fixable later by `lint`; missing knowledge is not.

## Step E — Detect contradictions

A contradiction needs the new fact and a *specific existing claim* to point at. Look for:

1. **Numeric contradiction**: "min Sharpe 1" vs "min Sharpe 1.5" — same parameter, different number.
2. **Definition contradiction**: page says "X is a Y" → new source says "X is a Z" (and Y ≠ Z).
3. **Mechanism contradiction**: page says "X works by Y" → new source says "X works by not-Y".
4. **Causal contradiction**: page says "X causes Y" → new source says "X does not cause Y" or "X causes anti-Y".

**False positives to avoid**:
- Two sources giving *different examples* of the same concept → not a contradiction; both belong as separate facts.
- A more precise version of an older claim → not a contradiction; the new fact subsumes; add it and let the operator deprecate the old one manually.
- Different time windows ("Sharpe was 1.2 in 2024 vs 1.4 in 2025") → not a contradiction; add as a time-stamped fact.

When you do flag a contradiction, pass *both* `--fact "<new claim>"` and `--contradicts "<short verbatim quote of existing claim>"`. The script wraps both into a `⚠️ Contradiction` block.

## Step F — Build touched/created lists for the log

As you call `upsert-page` in a loop, track:
- `touched`: pages that already existed before this ingest (use the scan JSON's `concepts` + `entities` lists to know which).
- `created`: pages that did not exist before this ingest.

These get passed to `append-log --touched <list> --created <list>`. They drive the grep-friendly log entry.

## Step G — When NOT to update the index

`wiki_ops.py update-index` is idempotent (dedupes by slug), so you can always call it. But: if no new concepts/entities were created and the source slug already exists in `index.md`, the call becomes a no-op. That's fine — call it anyway to keep the workflow consistent.

## Common failure modes (and how to avoid them)

| Failure | Symptom | Avoidance |
|---|---|---|
| Variant naming | `[[Hermes]]`, `[[Hermes Agent]]`, `[[Hermes agent]]` all in vault | Always pass known-concepts list to summarizing-meetings |
| Silent overwrite | Concept page lost prior facts after second ingest | Never use `Write` on existing pages — always upsert via the script |
| Missing footnote | Page has fact but no `[^src-X]` | The script handles this; only fails if you bypassed the script |
| Auto-resolved contradiction | Operator finds new fact replacing old, no warning | Detect contradictions in Step E, never overwrite |
| Empty log entry | `log.md` shows the ingest but no touched/created lists | Pass the lists explicitly; tracking them across the loop is on you |
