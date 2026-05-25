# Usage Example — Two Ingest Flows

Two end-to-end walkthroughs:
1. **Raw source → wiki** (delegate to `summarizing-meetings`)
2. **Pre-made summary → wiki** (`register-summary`, no LLM call)

Paths use placeholders (`<vault>`, `<source>`, `<summary>`) — substitute your own.

---

## Flow A — Ingest a raw transcript

### Setup

```
Operator: "Ingest the transcript at <source>/lesson.txt into my Obsidian vault at <vault>."
```

### Phase 1 — Scan + scaffold

```bash
python3 scripts/wiki_ops.py scan <vault>
```

Output (abbreviated, fresh vault):
```json
{
  "vault": "<vault>",
  "schema_present": false,
  "index_present": false,
  "log_present": false,
  "subdirs_present": {"_sources": false, "_concepts": false, "_entities": false},
  "concepts": [],
  "entities": [],
  "sources": [],
  "counts": {"concepts": 0, "entities": 0, "sources": 0},
  "last_log_entries": []
}
```

Schema missing → scaffold:

```bash
python3 scripts/wiki_ops.py init <vault>
```

Tell operator: "Scaffolded the vault with default conventions. Edit `WIKI_SCHEMA.md` if you want a different layout."

### Phase 2 — Delegate to summarizing-meetings

Invoke the `summarizing-meetings` skill with:
- the source path
- target path: `<vault>/_sources/<slug>.md`
- known-concepts list from the scan JSON: `[]` (empty on fresh vault — that's fine)

Wait for completion. Read the generated summary end-to-end.

### Phase 3 — Extract upsert targets

From the generated summary's frontmatter:

```yaml
concepts:
  - "Self-Improving AI Agent"
  - "Hermes Agent"
  - "Four Rules for a Good Trading Agent"
  - "Sharpe Score"
  - ...
related:
  - "[[Hermes Agent]]"
  - "[[Claude Code]]"
  - "[[Railway Hosting]]"
  - "[[Bittensor Subnets]]"
```

Classify each as concept or entity per `references/ingest_workflow.md` §B.

### Phase 4 — Upsert each (all new on fresh vault)

For each, extract a one-sentence definition from the summary's glossary and call:

```bash
python3 scripts/wiki_ops.py upsert-page <vault> \
  --kind concept \
  --name "Sharpe Score" \
  --source-slug <slug> \
  --source-title "<Title>" \
  --source-date 2026-05-25 \
  --definition "<one-sentence definition>"
```

Resulting `_concepts/Sharpe Score.md`:

```markdown
---
name: Sharpe Score
kind: concept
created: 2026-05-25
---

# Sharpe Score

## Definition

<one-sentence definition> [^src-<slug>]

## Facts

## Sources mentioning this

- [[<slug>]] — 2026-05-25 — <Title>

## Footnotes

[^src-<slug>]: [[<slug>]] — <Title>
```

Repeat for each concept/entity. Track `created` vs `touched` lists for the log.

### Phase 5 — Update index and log

```bash
python3 scripts/wiki_ops.py update-index <vault> \
  --source-slug <slug> \
  --source-title "<Title>" \
  --source-date 2026-05-25 \
  --summary "<one-line TL;DR>" \
  --new-concepts "Self-Improving AI Agent,Sharpe Score,..." \
  --new-entities "Hermes Agent,Claude Code,Railway Hosting,Bittensor Subnets"

python3 scripts/wiki_ops.py append-log <vault> \
  --title "<Title>" \
  --slug <slug> \
  --source-path "<source>/lesson.txt" \
  --created "<comma list>" \
  --contradictions 0
```

### Phase 6 — Report

Print 5–8 lines: new summary page, pages created/touched, contradictions flagged, suggested next action.

---

## Flow B — Ingest an existing summary

The skill ships a sample summary at `examples/sample_summary.md` you can use to dry-run this flow. Substitute your own summary path in real use.

### Setup

```
Operator: "I already have a summary at <summary>/summary.md — just ingest it
into my vault at <vault>, no re-summarization needed."
```

### Phase 1 — Scan + scaffold (same as Flow A)

```bash
python3 scripts/wiki_ops.py scan <vault>
python3 scripts/wiki_ops.py init <vault>   # if needed
```

### Phase 2-alt — Register the existing summary

```bash
python3 scripts/wiki_ops.py register-summary <vault> \
  --summary-path <summary>/summary.md
```

Output (using bundled `examples/sample_summary.md`):

```json
{
  "summary_source": "<...>/sample_summary.md",
  "target_page": "_sources/sample-lesson-self-improving-trading-agent.md",
  "action": "copied",
  "slug": "sample-lesson-self-improving-trading-agent",
  "title": "Sample Lesson — Self-Improving Trading Agent",
  "date": "2026-05-25",
  "concepts": [
    "Self-Improving AI Agent",
    "Four Rules for a Good Trading Agent",
    "Scientific Method for Strategy Iteration",
    "Sharpe Score",
    "Read-Only Review Cycle"
  ],
  "related": [
    "Hermes Agent",
    "Claude Code",
    "Railway Hosting",
    "Bittensor Subnets"
  ],
  "warnings": []
}
```

**If the target already exists** the script exits non-zero with code 3:

```
wiki_ops: error: _sources/<slug>.md already exists; pass --force to overwrite (or use a different --slug)
```

Decide:
- Re-ingest of same file → `--force` is correct.
- Different content sharing a title → use `--slug <other>` for the new one.

### Phases 3–6 — Same as Flow A

The JSON returned by `register-summary` contains `concepts` and `related` arrays — feed them directly into the Phase 4 upsert loop. Phases 5 and 6 are identical.

---

## Second ingest — what changes (applies to both flows)

When the operator ingests a *second* source mentioning a concept that already has a page (e.g., `Sharpe Score`):

- **Flow A**: Phase 2 passes the known-concepts list to `summarizing-meetings` → the new summary uses `[[Sharpe Score]]` consistently (no variant names).
- **Flow B**: there is no known-concepts hint, so the new summary may have a variant. Fix in the registered `_sources/` page with `Edit` before Phase 3.

Phase 4 for `Sharpe Score` finds the page exists. The new source contributes a new fact:

```bash
python3 scripts/wiki_ops.py upsert-page <vault> \
  --kind concept --name "Sharpe Score" \
  --source-slug <new-slug> \
  --source-title "<New Title>" \
  --source-date 2026-06-01 \
  --fact "Many funds prefer Sortino over Sharpe for asymmetric strategies."
```

The page now has:
- Original definition with `[^src-<first-slug>]`
- New fact under `## Facts` with `[^src-<new-slug>]`
- Two rows under `## Sources mentioning this`
- Two footnotes under `## Footnotes`

If the second source's claim **contradicts** an existing one, add `--contradicts "<short verbatim quote>"`. The page gets a `⚠️ Contradiction` block, the operator decides later.
