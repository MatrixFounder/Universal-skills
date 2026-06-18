# Content-Class & Document-Mode Detection

This file defines how the skill decides **what** it was given (`transcript` vs `document`) and,
for documents, **how deep** to go (`full` / `summary` / `thread`). The agent MUST use these rules
when the user has not explicitly passed `--content` / `--mode`.

> Both classifications are content-driven and model-agnostic — they rely only on observable
> surface features of the text, not on a model "just knowing" what the input is.

## Part A — Content class: `transcript` vs `document`

### Algorithm
1. Scan the first ~20% of the input (and skim the rest if borderline).
2. Tally `transcript` signals and `document` signals.
3. Higher tally wins. On a tie or low confidence → default to `transcript` (the skill's
   historical core; the meeting path is the safe fallback).
4. `--content transcript|document` OVERRIDES detection with absolute priority.

### `transcript` signals
- Timestamps: lines like `00:12:34`, `[12:34]`, `12:34 —`.
- Speaker labels: `Name:`, `Speaker 1`, `>>`, repeated `Имя:` turns.
- Dialogue cadence: many short turns, second-person address, interjections ("да", "ага",
  "okay so", "right"), back-and-forth question/answer.
- Standup/retro phrasing: "yesterday / today / blocker", "what went well", "let's go around".
- ASR artifacts: missing punctuation, run-on sentences, `[INAUDIBLE]`, filler words.

### `document` signals
- A byline / author line, a publication date, an `## Abstract`, a DOI / arXiv id.
- Section headings (`## 1 Introduction`, numbered sections), figures/tables, a `## References`
  or citation markers (`[12]`, `(Smith 2021)`).
- Continuous authored prose in third person; no speaker turns.
- Frontmatter with `source:` / `title:` / `author:` (a fetched/clipped page).
- Thread markers: numbered tweets (`1/`, `2/`), `@handles`, "🧵", retweet/like counts.

### Borderline cases
- **Interview transcript published as an article** → it has speaker turns → `transcript`
  (use the meeting path; it handles Q&A well).
- **A meeting's AI-generated minutes (already prose)** → if it reads as authored prose with no
  turns, treat as `document` (mode `summary`); if turns remain, `transcript`.
- **A lecture/webinar transcript** → `transcript` (this is what
  `workflows/generate-detailed-meeting-summary.md` consumes; meeting_type `discovery`).

## Part B — Document mode: `full` / `summary` / `thread`

Used only when content class = `document`. `--mode` OVERRIDES.

| Mode | Pick when the document is… | Body depth |
|------|----------------------------|-----------|
| `full` | a digestible web article, blog post, news piece, or encyclopedia entry — something a reader would want in full | reproduce the **whole** body (`body` = full), preserve structure |
| `summary` | a dense academic paper, preprint (arXiv), long PDF report, spec, or multi-section technical doc — too long/dense to reproduce in full | **digest** — `body = null`, 8–14 detailed bullets |
| `thread` | an X/Twitter thread or a short single-author opinion post | tight конспект, attribute claims to the author as opinion |

### Heuristics
- Length: > ~6–8K words of dense technical prose, or an abstract + numbered sections +
  references → lean `summary`. A few screens of approachable prose → `full`.
- Genre markers: "Abstract", "we propose", "Section 3", citation lists, equations → `summary`.
- Social markers: `@handle`, numbered tweets, "🧵" → `thread`.
- If `prepare` (wiki) already passed a `--mode` and it clearly mismatches the content, surface
  that to the operator **before** handoff and re-run `prepare --mode <better>` — the note JSON
  has no rationale field.

### Examples
- `examples/example_input_article.md` (the Bitcoin-DAO arXiv paper) → `document`, mode `summary`
  (dense academic preprint with abstract, numbered sections, tables, and a reference list).
- A Vitalik blog post on coin-voting → `document`, mode `full`.
- A 12-tweet thread on rollup economics → `document`, mode `thread`.
