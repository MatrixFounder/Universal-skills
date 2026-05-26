---
name: wiki-ingest
description: >-
  Use when ingesting a source (transcript, article, summary, meeting note)
  into an Obsidian-style llm-wiki, or maintaining one. Four modes: ingest
  (delegate to `summarizing-meetings`, upsert concept/entity pages
  additively, flag contradictions, update index.md and log.md), lint
  (orphans, dangling links, missing pages, contradictions), reindex (rebuild
  index.md from disk, preserve custom sections), query (keyword-find +
  cite). Triggers: ingest into wiki, register summary, lint, reindex, search
  notes, compound notes, llm-wiki.
tier: 2
version: 1.0
---

# Wiki-Ingest — LLM-Wiki Maintenance Layer

**Purpose**: Turn raw sources into nodes of a *compounding* knowledge base, not isolated summaries. Karpathy's llm-wiki pattern says: each new source must (a) get its own summary page AND (b) touch 10–15 other pages — concept pages, entity pages, the index, the log. `summarizing-meetings` already produces excellent single-file summaries; this skill is the *maintenance layer* that wires those summaries into a living wiki.

The skill enforces three invariants:
1. **Raw layer is immutable** — sources are read, never modified.
2. **Wiki layer is LLM-owned and additive** — pages get richer over time, prior content is never silently overwritten.
3. **Every claim on a concept/entity page traces back to a source** via footnote citation. An auditable wiki at 50 ingests, not a noise pile.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll just create the summary, the user can update concepts themselves" → **WRONG**. That's exactly the maintenance burden llm-wiki is designed to remove. Without page upserts the `[[wiki-links]]` stay dangling and the vault never compounds. Always do the full ingest cycle.
- "The existing concept page is short, I'll rewrite it cleaner" → **WRONG**. Concept pages are *additive*. You append new facts under existing ones with footnote citations. Rewriting destroys the audit trail and silently drops prior sources' contributions.
- "These two facts disagree, I'll pick the newer one" → **WRONG**. Mark with a `⚠️ Contradiction:` block citing both sources. The operator decides — your job is to surface, not silently resolve.
- "I'll skip the log entry, the user can see what changed from git" → **WRONG**. log.md is grep-friendly chronological memory for *the LLM in future sessions*. Git diffs are for humans; the log is for you, next time.
- "WIKI_SCHEMA.md isn't there, I'll improvise conventions" → **WRONG**. Run `wiki_ops.py init` to scaffold it from the bundled template, then read it. Improvised conventions diverge across ingests and break the wiki.
- "The source has no obvious concepts, I'll create a summary and skip upserts" → **WRONG**. Every source has at least 2–3 concepts/entities worth a page. Re-read; if you genuinely find none, ask the operator before proceeding.
- "I'll call summarizing-meetings without telling it what concepts already exist" → **WRONG**. Pass the known-concepts list. Otherwise the summary's `[[wiki-links]]` use new variant names ("Hermes" vs "Hermes Agent") and dangle forever.

## 2. Capabilities

The skill supports four modes. Most uses invoke `ingest` (the default); `query`, `lint`, and `reindex` are maintenance modes.

- **`ingest`** (default) — process one source into the wiki:
  - Scaffold a fresh vault (`WIKI_SCHEMA.md`, `index.md`, `log.md`, `_sources/`, `_concepts/`, `_entities/`) on first run
  - Discover existing concepts/entities by scanning frontmatter
  - Delegate summary generation to `summarizing-meetings` with vault context injected
  - Upsert concept/entity pages additively, with footnote citations
  - Detect and flag (not resolve) contradictions
  - Update `index.md` and append to `log.md`
  - Idempotent: re-running an ingest of the same source does not duplicate rows or footnotes
- **`query`** — answer a question against the wiki:
  - Search pages by keyword to assemble a shortlist
  - Read shortlisted pages, synthesise an answer with `[[wiki-link]]` citations
  - Optionally file the answer back as a new wiki page (compounding pattern)
  - Append a `query` entry to `log.md`
- **`lint`** — health check the vault:
  - Report orphan pages (no inbound `[[wiki-links]]`)
  - Report dangling link targets (referenced but no page)
  - Report open `## Contradictions` blocks pending operator resolution
  - Report concepts mentioned in N+ sources without a dedicated page
- **`reindex`** — rebuild `index.md` from disk, recovering from drift; preserves the `## Notes` section

## 3. Execution Mode

- **Mode**: `hybrid`
- **Why this mode**: File-format operations (upsert without duplicates, append to log, dedupe footnotes, rewrite index sections) are deterministic and MUST be scripted — text-based logic at this density fails 30% of the time. Judgement steps (which facts from the new summary belong on which concept page, whether two claims contradict, whether two concept names refer to the same thing) MUST stay with the LLM. The split keeps both halves reliable.

## 4. Script Contract

- **Command(s)**:
  - `python3 scripts/wiki_ops.py scan <vault>` → JSON dump of vault state (existing concepts, entities, sources, schema presence)
  - `python3 scripts/wiki_ops.py init <vault>` → scaffold missing `WIKI_SCHEMA.md`, `index.md`, `log.md`, and standard subdirs (idempotent)
  - `python3 scripts/wiki_ops.py upsert-page <vault> --kind {concept|entity} --name <name> --source-slug <slug> --source-title <title> --source-date <YYYY-MM-DD> [--definition <text>] [--fact <text>] [--contradicts <existing-claim-id>]`
  - `python3 scripts/wiki_ops.py register-summary <vault> --summary-path <path> [--slug <override>] [--title <override>] [--force]` → ingest a pre-made summary file directly into `_sources/` (skip delegating to `summarizing-meetings`). Returns JSON with slug/title/date/concepts/related for Phase 3+.
  - `python3 scripts/wiki_ops.py update-index <vault> --source-slug <slug> --source-title <title> --source-date <YYYY-MM-DD> --summary <one-line> [--new-concepts <name1,name2>] [--new-entities <name1,name2>]`
  - `python3 scripts/wiki_ops.py append-log <vault> --title <title> --slug <slug> --source-path <path> --touched <slug1,slug2,...> --created <slug1,slug2,...> --contradictions <count>` — ingest-specific shortcut
  - `python3 scripts/wiki_ops.py log-event <vault> --event <type> --title <text> [--detail key=value ...]` — generic log append (query, lint, reindex events)
  - `python3 scripts/wiki_ops.py find <vault> --terms "<space-separated>" [--limit N] [--kinds source,concept,entity]` → ranked JSON hits for the keyword search backing `query` mode
  - `python3 scripts/wiki_ops.py lint <vault> [--threshold N]` → JSON health report (orphans, dangling links, open contradictions, missing concept pages)
  - `python3 scripts/wiki_ops.py reindex <vault>` → rebuild `index.md` from on-disk pages (preserves `## Notes`)
  - `python3 scripts/wiki_ops.py classify-folder <folder> [--group-by <regex>]` → Phase 0 of folder-ingest: detect grouping pattern + classify each file into primary/metadata/merge/link/derived-output; emit a plan JSON. Pure read-only; no vault required.
- **Inputs**: vault root path; for upserts, the source's slug/title/date and the concept name and either a definition (stub-creation) or a fact (additive update).
- **Outputs**: stdout JSON for `scan`; mutated markdown files for the rest; non-zero exit on missing required args or invalid vault.
- **Failure semantics**: exits 1 with stderr message on invalid args / missing vault; exits 2 if `WIKI_SCHEMA.md` is absent and `init` was not run first (prevents improvised conventions).
- **Idempotency**: `init` is fully idempotent — never overwrites existing files. `upsert-page` deduplicates source rows and footnotes by slug, and refuses case-colliding names (`--force` to override). `update-index` deduplicates rows by slug. `append-log` deduplicates by (date, event, source-slug) — re-running an identical ingest is a no-op; pass `--force-log` to append anyway.
- **Dry-run support**: `--dry-run` on all mutating subcommands prints the diff to stdout without writing.

## 5. Safety Boundaries

- **Allowed scope**: a single vault directory provided as `<vault>`. All writes stay inside it.
- **Default exclusions**: raw source files (operator's transcripts, articles); the script reads them only when invoked by the agent for inspection, never mutates them.
- **Destructive actions**: the only operations that can remove operator content are `reindex` (rewrites `index.md`) and `--force` overrides. `reindex` preserves every non-default section (anything outside `_sources/_concepts/Entities` — including `Notes` and any custom sections the operator added) — but its output is reported as a list under `preserved_sections`; review the diff before accepting. The agent never passes `--force` or `--force-log` without explicit operator approval.
- **Contradiction handling is non-destructive**: contradictions are *marked* with a `⚠️ Contradiction:` block linking both sources. The skill never auto-resolves. The `--contradicts` text MUST match a substring on the existing page (script verifies); operator must pass `--force` to record an unverified citation.
- **Filesystem safety**: `--name`/`--slug`/`--source-slug` reject path traversal (`..`, `/`, `\`, leading `.`), control characters, markdown link metacharacters (`[`, `]`, `|`, `^`), template placeholders (`{{`, `}}`), and overlong (>200 char) values. Case-insensitive collisions (e.g., `sharpe score.md` vs `Sharpe Score.md` on macOS APFS) AND slug-equivalent collisions (e.g., `_Foo_.md` vs `foo.md`) are detected and refused without `--force`. Names are NFKC-normalised so visually-identical Unicode variants (composed vs decomposed, fullwidth vs ASCII) collapse onto the same on-disk filename.
- **No network calls**: the script is local-only. Transcript fetching is a separate skill (`transcript-fetcher`); plumb that upstream if needed.

## 6. Validation Evidence

- **Local verification**:
  - `python3 scripts/wiki_ops.py scan <vault>` after ingest → confirm `last_ingest` slug and counts match expectations
  - `grep "^## \[" <vault>/log.md | tail -5` → last 5 log entries readable
  - Open the new summary page in Obsidian → all `[[wiki-links]]` resolve (no dangling)
- **Expected evidence per ingest**:
  - 1 new file under `_sources/<slug>.md`
  - 0+ new files under `_concepts/` and `_entities/`
  - `index.md` and `log.md` modified
  - Every concept/entity touched contains a footnote `[^src-<slug>]` and an entry under "Sources mentioning this"
- **CI signal**: none (skill operates on user-local files).

## 7. Instructions

### Phase 0 — Resolve inputs

1. **Required from user / inferred from context**:
   - One of:
     - `<source-folder>` — path to a **folder** containing one or more related source files (transcript + slides + notes + binaries). Triggers Phase 0-folder (classify-folder), then per-group Phases 2-6.
     - `<source>` — path to a **single raw source file** (transcript, article markdown, paper text). Triggers Phase 2 (delegate to `summarizing-meetings`).
     - `<summary>` — path to a **pre-made summary file** (e.g., already produced by an earlier `summarizing-meetings` run). Triggers Phase 2-alt (`register-summary`).
   - `<vault>` — path to the Obsidian vault root.
2. **Distinguishing the three input shapes**:
   - **Folder** → Phase 0-folder (see below).
   - **File with summary-style frontmatter** (`type: lesson-summary` / `type: meeting-summary` / `kind: source`, OR both `concepts:` AND `related:` arrays) → Phase 2-alt.
   - **Any other file** → Phase 2.
   - When uncertain, ask the operator once.
3. **If `<vault>` not provided**: ask the user. Do NOT guess. Common defaults to *propose* (not assume): the parent directory of the source/summary file, `~/obsidian-vault`, or a vault the user mentioned earlier in the conversation.
4. **If `<source>` is a URL**, refuse and instruct: "Fetch first with `transcript-fetcher`, then re-invoke `wiki-ingest` with the local path." This skill operates on local files only.

### Phase 0-folder — Classify-folder (when input is a directory)

When `<source-folder>` is a directory containing multiple files (e.g., a transcript + slides + notes bundle, or a numbered course like `01 - intro.md` + `01 - intro - slides.pptx`):

1. **Run `python3 scripts/wiki_ops.py classify-folder <folder>`** — outputs JSON plan with:
   - Detected grouping pattern (`prefix` / `sibling` / `flat`)
   - Per-group classification: `primary` / `metadata` / `merge` / `link` / `derived_outputs` / `skipped`
   - Per-file rationale + warnings
2. **Present the plan to the operator** in human-readable form. Surface warnings (e.g., groups with no text-readable primary).
3. **Apply LLM judgement** on ambiguous classifications:
   - If rationale shows "close runner-up — review" → ask operator to pick primary
   - If a file's role seems wrong (e.g., a substantial recipe got `merge` instead of `link`) → propose override
   - Operator can re-run with `--group-by '<regex>'` to force a custom grouping
4. **For each group** with a confirmed `primary`:
   - Run Phases 2-6 below (treating the group's `primary` file as `<source>` and `merge` files as supplementary context for the `summarizing-meetings` call)
   - After Phase 5 (`update-index` + `append-log`), **post-process** the generated summary to inject:
     - `companion_links:` frontmatter list — one entry per `link` file with `path`, `kind`, one-line `description`
     - `metadata:` frontmatter fields — flatten the `metadata` files' contents (e.g., `url`, `duration_sec`, `embed_url` from a `*.stat.json`)
     - For prefix-grouped courses: `course:`, `lesson_number:`, `previous:`, `next:` cross-references
     - `## Companion Material` body section — one bullet per `link` file with a Markdown link to its raw location
5. **NEVER copy `link` files into the wiki.** They live in the raw layer. Wiki only references them by path. (Karpathy invariant: raw is immutable.)
6. **`derived_outputs`** (previously-generated summary files like `summary.md`) are **skipped** entirely — they're outputs of a prior ingest, not sources.

Detailed algorithm, examples, edge cases: [`references/folder_ingest_workflow.md`](references/folder_ingest_workflow.md).

### Phase 1 — Scan + scaffold

1. Run `python3 scripts/wiki_ops.py scan <vault>` → capture the JSON.
2. **If the JSON reports `schema_present: false`**: run `python3 scripts/wiki_ops.py init <vault>`. Then immediately read `<vault>/WIKI_SCHEMA.md` and tell the operator one sentence: "Scaffolded the vault with default conventions — edit WIKI_SCHEMA.md if you want a different layout." This is the *only* time the skill creates structural files.
3. **Always read `<vault>/WIKI_SCHEMA.md`** before proceeding — it defines paths, naming, frontmatter conventions. The default schema is good; bespoke schemas override it.

### Phase 2 — Delegate summary generation (when input is a raw source)

1. Build a **known-concepts list** from the scan JSON: `["Hermes Agent", "Claude Code", ...]`. Include both concepts and entities. This is the disambiguation hint.
2. Invoke `summarizing-meetings` via the Skill tool. In the args, include:
   - the source file path
   - the target output path: `<vault>/_sources/<slug>.md` (slug from the title; the scan JSON's helper `proposed_slug` is fine if available, otherwise kebab-case the title)
   - the known-concepts list and an instruction: "When the source mentions any of these, use the EXACT name in `[[wiki-links]]` and `concepts:` frontmatter. Do not invent variant names."
3. **Wait for the sub-skill to finish.** Read the generated file end-to-end before proceeding. If the file is short or fields are mostly `⚠️ UNKNOWN`, warn the operator and ask before continuing — a low-quality summary will pollute concept pages.

### Phase 2-alt — Register an existing summary (when input is a pre-made summary)

When the operator provides a path to a summary file that already exists (typically produced by an earlier run of `summarizing-meetings`), skip Phase 2 entirely. Use `register-summary` instead:

1. **Run `python3 scripts/wiki_ops.py register-summary <vault> --summary-path <summary>`** — this copies the summary into `<vault>/_sources/<slug>.md` and returns JSON with `slug`, `title`, `date`, `concepts`, `related`, and any `warnings`.
2. **Heed warnings**: if the JSON contains warnings (e.g., empty `concepts:` and `related:`), surface them to the operator before continuing. A summary without upsert targets means Phase 3 will be a no-op.
3. **If `_sources/<slug>.md` already exists** the script exits with code 3. Decide:
   - Same content (e.g., the operator re-ran the same file) → re-invoke with `--force` (it's just an overwrite-with-same).
   - Different content → ask the operator: rename the new slug (`--slug <other>`) or `--force` to replace.
4. **Skip Phase 2's known-concepts-list hint** — it doesn't apply, since the summary was generated without that context. Be aware: the existing summary may use variant names ("Hermes" instead of "Hermes Agent"). If you detect a variant, fix it in the registered _sources/ page with `Edit` before Phase 3 to keep `[[wiki-links]]` consistent.
5. The returned `concepts` and `related` arrays are exactly what Phase 3 needs — proceed directly.

### Phase 3 — Extract upsert targets

From the generated summary's frontmatter:
- `concepts:` → list of concept names that need concept-page upserts
- `related:` → list of `[[wiki-links]]` — split into concepts vs entities by checking the scan JSON; new ones default to `entities` (people, organizations, products) unless clearly conceptual (rule of thumb: capital-letter abstractions like "Sharpe Score" are concepts; proper nouns like "Railway" are entities). When uncertain, ask the operator once at the start of the ingest and remember the answer for the rest of the run.
- Sections under `### Technical Glossary` → additional concepts the operator clearly cares about

### Phase 4 — Upsert pages (the maintenance work)

For each concept/entity in the upsert list:

1. **Check existence** via the scan JSON.
2. **If page does NOT exist**:
   - Pull a one-sentence definition from the summary (from `### Key Concepts` or the glossary). Cite it as `[^src-<slug>]`.
   - Run `python3 scripts/wiki_ops.py upsert-page <vault> --kind <k> --name <name> --source-slug <slug> --source-title <title> --source-date <date> --definition "<one sentence>"` — the script creates a stub page with the definition, a "Sources mentioning this" section, and the footnote.
3. **If page EXISTS**:
   - Read it with the Read tool.
   - **Decide**: does the new summary contribute a new fact this page lacks?
     - If no → run `upsert-page` with no `--fact` (still records the source under "Sources mentioning this" and adds the footnote — that alone is valuable).
     - If yes → extract the *new* fact as one paragraph and run `upsert-page --fact "<text>"`. The script appends under a "Facts" section with the citation.
   - **Check for contradictions**: if the new fact disagrees with an existing claim on the page (different number, different definition, opposite assertion), do NOT pick a winner. Run `upsert-page --contradicts "<short quote of existing claim>"` — the script wraps both claims in a `⚠️ Contradiction:` block.
4. **Track for the log**: maintain two lists — `touched` (existed before) and `created` (created this ingest), plus a contradiction counter.

### Phase 5 — Update index and log

1. **Index**: `python3 scripts/wiki_ops.py update-index <vault> --source-slug <slug> --source-title <title> --source-date <YYYY-MM-DD> --summary "<one-line TL;DR>" --new-concepts <names> --new-entities <names>` — adds rows under the right sections, deduplicated by slug.
2. **Log**: `python3 scripts/wiki_ops.py append-log <vault> --title <title> --slug <slug> --source-path <path> --touched <slugs> --created <slugs> --contradictions <n>` — appends the grep-friendly entry.

### Phase 6 — Report to operator

Print a short report (5–8 lines) listing:
- the new summary page
- pages created (with full paths)
- pages touched (count + names)
- contradictions flagged (count + 1-line preview of each, with file paths)
- one suggestion for the next ingest or a lint check the operator might want to run

DO NOT print the summary itself again — the operator will open it in Obsidian. Keep the report scannable.

### Phase Q — Query mode

Use this when the operator asks a question about already-ingested material ("What does the wiki say about Sharpe Score?", "Compare Hermes and OpenClaw based on what we have."). Steps:

1. **Extract search terms** from the question — content words only, drop stop-words. For "What does the wiki say about Sharpe Score in crypto?" → terms `sharpe score crypto`.
2. **Run `wiki_ops.py find <vault> --terms "..." --limit 10`** — JSON returns ranked pages.
3. **Read the top 3–5 hits** with the Read tool. Skip pages whose score is < 20% of the top hit (likely noise).
4. **Synthesise** an answer in 4–10 sentences. Every claim MUST cite the source page as `[[<slug>]]` inline. If two pages disagree, surface it explicitly ("`[[source-a]]` says X; `[[source-b]]` says Y").
5. **Decide whether to file the answer back**:
   - If the question is a one-shot lookup → don't file; just answer in chat.
   - If the question is analytical ("compare X vs Y", "trace the evolution of Z across sources") → propose filing the answer at `<vault>/_sources/query-<slug>.md` so the next query benefits. Ask the operator once before writing.
6. **Log the event**: `python3 scripts/wiki_ops.py log-event <vault> --event query --title "<question short>" --detail "pages_read=<comma list>" --detail "saved_as=<path or none>"`.

### Phase L — Lint mode

Use this when the operator says "lint the wiki", "what's missing", or after ~10 ingests as a periodic health check. Steps:

1. **Run `wiki_ops.py lint <vault>`** — JSON returns four categories.
2. **Present a summary table** to the operator with counts and 1-line examples per category. Do NOT auto-fix — lint is diagnostic only.
3. **Suggest concrete actions** keyed to each category (see `references/query_lint_workflow.md` §Lint for the playbook):
   - Orphans → maybe link from a related concept, or delete if obsolete
   - Dangling links → ingest the missing source, or rename the link to an existing page, or delete the link
   - Open contradictions → operator decides which claim wins; you can offer to apply the resolution via `Edit`
   - Missing concept pages → propose an ingest of the most-mentioned ones first
4. **Log the event**: `python3 scripts/wiki_ops.py log-event <vault> --event lint --title "Lint pass" --detail "orphans=<n>" --detail "dangling=<n>" --detail "open_contradictions=<n>" --detail "missing_pages=<n>"`.

### Phase R — Reindex mode

Use this when:
- The operator manually edited `index.md` and broke it
- Many pages were renamed and the index now points to wrong slugs
- `lint` shows the index disagrees with disk (rare; the script keeps index in sync during ingest)

Steps:

1. **`wiki_ops.py reindex <vault>`** — rebuilds `_sources`, `_concepts`, `_entities` sections from on-disk pages. ALL other sections the operator added (`## Notes`, `## Pinned`, `## Reading Queue`, etc.) are preserved verbatim. The JSON output lists them under `preserved_sections` — confirm nothing was unexpectedly dropped.
2. **Show the operator a diff** (compare with the pre-reindex copy if you saved one). For safety, suggest `git diff index.md` if the vault is a git repo, or `cp index.md index.md.bak` before invoking.
3. **Log the event**: `python3 scripts/wiki_ops.py log-event <vault> --event reindex --title "Index rebuild" --detail "sources=<n>" --detail "concepts=<n>" --detail "entities=<n>"`.

## 8. Workflows

**Ingest** (the default):
```markdown
- [ ] Phase 0: Resolve input path (raw source OR pre-made summary) and vault path
- [ ] Phase 1: Scan vault; init schema if missing
- [ ] Phase 2: Delegate to summarizing-meetings with known-concepts context
       — OR Phase 2-alt: register-summary if input is a pre-made summary
- [ ] Phase 3: Extract concept/entity upsert targets from summary frontmatter
- [ ] Phase 4: Upsert each (additive; flag contradictions)
- [ ] Phase 5: Update index.md and append to log.md
- [ ] Phase 6: Report to operator
```

**Query**:
```markdown
- [ ] Extract content-word search terms from the question
- [ ] wiki_ops.py find — get ranked hits
- [ ] Read top 3–5 hits
- [ ] Synthesise answer with [[<slug>]] citations
- [ ] Decide whether to file the answer back; ask operator if so
- [ ] log-event --event query
```

**Lint**:
```markdown
- [ ] wiki_ops.py lint
- [ ] Present summary table per category
- [ ] Suggest actions: dangling → contradictions → missing-pages → orphans
- [ ] Apply approved fixes (Edit / upsert-page / Edit again)
- [ ] log-event --event lint
```

**Reindex**:
```markdown
- [ ] Suggest backup (git or cp)
- [ ] wiki_ops.py reindex
- [ ] Show diff; operator confirms
- [ ] log-event --event reindex
```

For details on judgement-heavy steps:
- Ingest (concept vs entity classification, contradiction detection, "new fact" extraction): `references/ingest_workflow.md`
- Query/Lint/Reindex (term extraction, hit filtering, lint action playbook, reindex safety): `references/query_lint_workflow.md`

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Pass known-concepts list to `summarizing-meetings` so wiki-links resolve | Let the summarizer invent variant names ("Hermes" vs "Hermes Agent") |
| Append new facts under existing ones with footnote citations | Rewrite a concept page "cleaner" — you erase the audit trail |
| Mark contradictions, let the operator resolve | Auto-pick one source over another |
| Run `scan` first, every time | Assume vault state from memory of last ingest |
| One source per `wiki-ingest` invocation | Batch many sources into one run (errors cascade silently) |
| Read `WIKI_SCHEMA.md` before writing | Improvise paths and naming on the fly |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The concept exists, but the new fact is so close to an existing one, I'll skip" | Add the source to "Sources mentioning this" anyway. The cross-reference itself is the value — it's what tells future-you that *three* sources back the claim. |
| "Two concept names look like the same thing, I'll merge" | Don't merge silently. Add both with a `> See also: [[OtherName]]` note and ask the operator. Merges are destructive and need approval. |
| "The summary's `related:` list is huge, I'll upsert just the most important" | Upsert all of them. The cost of an extra stub page is one row in index.md. The cost of a missing one is a forever-dangling link. |
| "I'll add the contradiction note later" | You won't. Add it inside the same `upsert-page` call — the script keeps the markup consistent. |
| "log.md is verbose, I'll skip it for small ingests" | log.md is the *only* place future-you can grep to reconstruct what happened on a given day. Skipping kills future debuggability. |

## 10. Examples (Few-Shot)

See `examples/usage_example.md` for a full walkthrough on a real source.

**Minimal invocation:**
```
User: ingest the transcript at Lessons/ZeroOne/Hermes/transcript.txt into my obsidian-llm-wiki vault
```

**Expected agent flow:**
1. Confirm vault path (`<vault>`).
2. `wiki_ops.py scan <vault>` → vault has 0 concepts, no schema yet.
3. `wiki_ops.py init <vault>` → scaffolds schema/index/log/subdirs. Tells operator one sentence.
4. Invoke `summarizing-meetings` with source + target path + (empty) known-concepts list.
5. Read the generated `_sources/<slug>.md`.
6. Frontmatter has 11 concepts + 4 related entities. Upsert each (all new → all get stub pages with definitions).
7. `wiki_ops.py update-index` + `append-log`.
8. Report: "Created `_sources/<slug>.md`, 15 concept/entity stubs under `_concepts/` and `_entities/`. Index and log updated. 0 contradictions."

**Alternative invocation — pre-made summary:**
```
User: ingest the existing summary at <summary>/summary.md into my vault at <vault>
```

The agent uses Phase 2-alt instead of Phase 2: `wiki_ops.py register-summary <vault> --summary-path <summary>/summary.md` returns the slug, title, and the same `concepts`/`related` lists Phase 3 needs. No call to `summarizing-meetings`. See `examples/usage_example.md` Flow B for a full walkthrough; `examples/sample_summary.md` is bundled so this flow can be exercised end-to-end without an external file.

## 11. Resources

- `scripts/wiki_ops.py` — deterministic vault operations across all four modes: `scan`, `init`, `upsert-page`, `update-index`, `append-log`, `log-event`, `find`, `lint`, `reindex`. Mutating subcommands support `--dry-run`.
- `references/karpathy-llm-wiki.md` — foundational methodology by Andrej Karpathy (imported verbatim from [github.com/karpathy/llm-wiki](https://github.com/karpathy/llm-wiki)). Read this when you need to remember WHY the skill is structured the way it is — raw vs wiki vs schema layers, the ingest/query/lint operations, the "compounding artifact" thesis. This skill is an implementation of that pattern.
- `references/wiki_schema.md` — full default vault conventions (paths, frontmatter, footnote style, page sections). Read when interpreting an existing vault's `WIKI_SCHEMA.md` or deciding how to upsert.
- `references/ingest_workflow.md` — judgement-heavy steps for ingest: concept-vs-entity classification rules, contradiction detection patterns, new-fact extraction heuristics.
- `references/query_lint_workflow.md` — judgement-heavy steps for query, lint, reindex: term extraction, hit filtering, lint action playbook (orphans → dangling → contradictions → missing-pages), reindex safety pattern.
- `references/folder_ingest_workflow.md` — Phase 0-folder algorithm: grouping pattern detection (prefix / sibling / flat), per-file role classification (primary / metadata / merge / link / derived-output), primary selection within a group with segment-aware filename hints + pool filter. Read when ingesting multi-file folders.
- `assets/WIKI_SCHEMA.template.md` — bundled default schema; copied into the vault by `wiki_ops.py init`.
- `assets/index.template.md` — bundled empty index; copied by `init`.
- `assets/log.template.md` — bundled empty log; copied by `init`.
- `assets/concept_page.template.md` / `assets/entity_page.template.md` — stub-page templates used by `upsert-page`.
- `examples/usage_example.md` — annotated example ingest.

## 12. Evals (Optional but Recommended)

See `evals/evals.json` for test cases (initial set covers: fresh-vault ingest, second ingest with shared concept, contradiction detection, idempotent re-ingest).
