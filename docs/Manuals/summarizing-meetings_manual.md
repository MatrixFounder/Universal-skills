# Summarizing Meetings — Manual

## Overview

**Summarizing Meetings** is a meta-skill for generating structured meeting summaries from text transcriptions. Unlike a simple prompt, it is a **parameterizable constructor** — it auto-detects the meeting type, selects the appropriate template, and generates a document with two levels of detail (pyramid documentation).

### Key Characteristics

| Property | Value |
|----------|-------|
| **Type** | Meta-Skill (Core) |
| **Execution Mode** | `prompt-first` |
| **Tier** | 2 |
| **Input** | Transcription text |
| **Output** | Markdown document with YAML frontmatter |

---

## Quick Start

### Basic Usage

Pass the transcription text and invoke the skill:

```
Use skill summarizing-meetings:
Generate a meeting summary from the following transcription:

[transcription text]
```

### With Explicit Meeting Type

```
Use skill summarizing-meetings --type standup:
Generate a standup summary:

[transcription text]
```

### With Output Path

```
Use skill summarizing-meetings:
Generate a summary to docs/meetings/2026-02-26-planning.md:

[transcription text]
```

---

## Processing Pipeline

The skill operates in 6 steps:

```
1. PRE-FLIGHT ──► 2. DETECT ──► 3. SELECT ──► 4. GENERATE ──► 5. VERIFY ──► 6. OUTPUT
   Input          Meeting       Template       Summary        Self-Check     Save
   validation     type          from assets/   via prompt     (8 points)     to file
                                               from refs/
```

### Step 1: PRE-FLIGHT CHECKS

Before generation, the agent validates:

| Check | Action on Failure |
|-------|-------------------|
| Non-empty input | ❌ STOP: error |
| Length < context window | ⚠️ Chunking (50K blocks with 2K overlap; for plain text: split on speaker boundaries) |
| Language detection | Set in frontmatter |
| ASR quality | ⚠️ WARN if > 30% garbage tokens |
| Participant names | Use "Participant N" if not extractable |
| Input format | Auto-detect: `timestamped` or `plain_text` |

### Step 2: Meeting Type Auto-Detection

The agent scans the first 20% of the transcription for signal words:

| Type | Example Signals |
|------|----------------|
| **standup** | "yesterday", "today", "blockers", short utterances |
| **retrospective** | "retro", "what went well", "what to improve" |
| **discovery** | "brainstorm", "idea", "what if", "options" |
| **default** | No clear signals or low confidence |

> Full rules: `references/meeting_type_detection.md`

### Step 3: Template Selection

| Type | Template | Key Feature |
|------|----------|-------------|
| `default` | `assets/template_default.md` | Full pyramid + all sections |
| `standup` | `assets/template_standup.md` | Done / Doing / Blocked per participant |
| `retrospective` | `assets/template_retrospective.md` | 👍 / 👎 / 🔧 + action items |
| `discovery` | Extended `default` | Emphasis on alternatives and trade-offs |

---

## Input Formats

The skill handles two transcription formats:

| Format | Markers | Source |
|--------|---------|--------|
| **Timestamped** | Lines like `00:12:34 Name:` | Zoom, Teams auto-transcription |
| **Plain text** | `Speaker N` labels, continuous paragraphs | Whisper, manual transcription, raw ASR |

**Auto-detection**: The agent scans the first 10 lines. If ≥ 2 lines match a timestamp pattern → timestamped. Otherwise → plain text.

For plain text:
- Duration is marked `⚠️ UNKNOWN`
- Sections are split by **content topic shifts**, not timestamps
- Speaker names are extracted from context if possible
- Lower ASR quality is expected (run-on sentences, missing punctuation)

See `examples/example_input_plain_text.md` for a plain text example.

---

## Templates

### Default (General)

Two-level pyramid:

- **Level 1**: TL;DR (3–5 sentences) + decision and action item tables
- **Level 2**: Logical sections, each containing:
  - `> Summary:` — mini-summary for scanning
  - `#### Discussion` — who said what, arguments
  - `#### Insights` — non-obvious thoughts (💡)
  - `#### Section Decisions` — decisions made (✅)

### Standup

Optimized for short daily/weekly meetings:
- **Done / Doing / Blocked** table per participant
- Blockers summary
- Minimal text, maximum structure

### Retrospective

Three classic sections:
- 👍 **What Went Well** (table)
- 👎 **What Went Wrong** (table with root causes)
- 🔧 **Improvements** (action items with priorities)
- Plus detailed discussion by topic

---

## Language-Adaptive Headers

Templates use English placeholders. When generating the actual summary:

- **Headers follow the transcription language**
- Russian meeting → Russian headers (e.g., "Ключевые решения", "Действия")
- English meeting → English headers (e.g., "Key Decisions", "Action Items")
- Structural markers (💡, ✅, 🔲, ⚠️) remain language-agnostic

---

## Obsidian Integration

### YAML Frontmatter

Every summary contains YAML metadata compatible with Obsidian and Dataview:

```yaml
type: meeting-summary
title: "..."
date: 2026-02-26
meeting_type: default
participants: [...]
duration: "01:00"
languages: [ru]
tags: [meeting, planning, engineering]
related: ["[[Sprint 42 Retro]]", "[[Q2 OKR]]"]
```

### Tag Taxonomy

All tags come from a fixed taxonomy (`references/tag_taxonomy.md`) for consistent graph navigation:

- **Meeting type**: `meeting`, `standup`, `retrospective`, `discovery`, `planning`, etc.
- **Domains**: `product`, `engineering`, `design`, `data`, `infrastructure`, etc.
- **Projects**: `project/{{name}}`
- **Urgency**: `urgent`, `blocker`, `follow-up`

### Wiki-links

The agent automatically adds `[[wiki-links]]` to `related:` when the transcription mentions:
- Other meetings
- Documents
- Projects
- Systems

---

## Markers and Conventions

| Marker | Meaning |
|--------|---------|
| 💡 | Insight — non-obvious thought |
| ✅ | Decision made |
| 🔲 | Action item — open |
| ⚠️ UNKNOWN | Data could not be extracted from transcription |
| [INAUDIBLE] | ASR could not recognize a fragment |
| 🔴 / 🟡 / 🟢 | Priority levels |

---

## Handling Long Transcriptions

For meetings > 1 hour (100K+ characters), the skill uses a **chunking strategy**:

1. Split text into ~50K character blocks with 2K overlap
2. Process each block independently
3. Merge results: combine sections, deduplicate decisions and action items
4. Generate a unified TL;DR across all blocks

---

## Quality Verification

After generation, the agent runs a **Self-Check**:

```
□ Every decision is in the "Key Decisions" table
□ Every action item has an owner
□ Every section has > Summary: + Discussion + Insights
□ TL;DR is self-sufficient
□ All numbers/names/dates preserved
□ Tags from tag_taxonomy.md
□ No more than 3 ⚠️ UNKNOWN fields
□ [[wiki-links]] are correct
```

Then — **Verification Loop**: re-scan the transcription for missed decisions/insights.

### Completeness Guarantee

**The agent MUST process 100% of the transcription.** This is enforced by:

1. Counting topics in the transcription vs sections in the summary
2. If any topic is missing → agent adds the missing section
3. For long transcriptions: sequential pass through ENTIRE text
4. Explicit prohibition against:
   - Truncating processing midway
   - Generating summary from only the first portion
   - Using vague "other topics were discussed" language
   - Collapsing multiple topics into one section

> The last 30% of meetings often contains the most actionable content (wrap-up, decisions, deadlines). Skipping the tail is the #1 failure mode.

---

## Examples

### Input

See `examples/example_input_transcript.md` — a realistic Q2 planning meeting transcription with 4 participants, ~12 minutes.

### Expected Output

See `examples/example_output_summary.md` — full summary using the default template with 4 sections, decision tables, action items, insights, and agent metadata.

---

## Skill File Structure

```
summarizing-meetings/
├── SKILL.md                              # Meta-skill instructions
├── assets/
│   ├── template_default.md               # Full default template
│   ├── template_standup.md               # Standup template
│   └── template_retrospective.md         # Retro template
├── references/
│   ├── generation_prompt.md              # System prompt
│   ├── tag_taxonomy.md                   # Tag taxonomy
│   └── meeting_type_detection.md         # Auto-detect rules
└── examples/
    ├── example_input_transcript.md       # Timestamped input
    ├── example_input_plain_text.md       # Plain text input (Whisper/ASR)
    └── example_output_summary.md         # Sample output
```

---

> **Russian version**: See [summarizing-meetings_manual_ru.md](summarizing-meetings_manual_ru.md)
