---
name: summarizing-meetings
description: >-
  Use when generating meeting summaries from transcriptions.
  Meta-skill: auto-detects meeting type, selects appropriate template,
  and produces a two-level pyramid Markdown document
  optimized for people, AI agents, RAG, and Obsidian.
tier: 2
version: 1.0
status: active
changelog: Initial release — meta-skill with 4 meeting types, PRE-FLIGHT, self-verification, and tag taxonomy.
---

# Summarizing Meetings — Meta-Skill

**Purpose**: Transform raw meeting transcriptions into highly-detailed, structured summaries with two-level pyramid documentation. Adapts to meeting type automatically.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll skip the PRE-FLIGHT checks, the input looks fine" → **WRONG**. ALWAYS run PRE-FLIGHT. Bad input = garbage output.
- "I'll merge all topics into one section" → **WRONG**. EVERY distinct topic MUST be a separate section.
- "This detail is too minor to include" → **WRONG**. If it was discussed, it MUST appear in the summary.
- "I'll invent a participant name" → **WRONG**. Use "Participant N" if unknown. NEVER fabricate names.
- "I'll skip self-verification, the summary looks complete" → **WRONG**. ALWAYS run the Self-Check checklist.
- "The template is just a suggestion" → **WRONG**. The template is a CONTRACT. Every section MUST be filled.
- "The transcription is too long, I'll summarize the key parts" → **WRONG**. You MUST process the ENTIRE transcription. EVERY topic discussed MUST appear.
- "This part is just casual talk / off-topic" → **WRONG**. If participants discussed it, it matters. Include at minimum a brief mention.
- "I already covered the main points" → **WRONG**. Re-read the transcription end-to-end and verify NOTHING was skipped.

## 2. Capabilities

- **Auto-detect** meeting type (default / standup / retrospective / discovery)
- **Parameterize** output via `--type` override
- **Generate** two-level pyramid summaries (TL;DR → Detailed Sections)
- **Extract** structured data: decisions, action items, open questions
- **Produce** Obsidian-compatible output with YAML frontmatter, tags, and `[[wiki-links]]`
- **Handle** long transcriptions via chunking strategy
- **Self-verify** completeness after generation

## 3. Execution Mode

- **Mode**: `prompt-first`
- **Rationale**: Core task is text-to-text transformation (transcription → structured summary). No algorithmic logic > 5 lines required.

## 4. Safety Boundaries

- **Scope**: Operates ONLY on the provided transcription text.
- **Output**: Creates ONE markdown file as output.
- **No Mutations**: NEVER modifies files outside the target output path.
- **No Fabrication**: NEVER invents facts, names, dates, or numbers not present in the transcription.

## 5. Validation Evidence

- **Self-Check**: The 8-point checklist at the end of the generation prompt (see `references/generation_prompt.md`).
- **Verification Loop**: After self-check, re-scan the transcription for missed decisions/actions/insights.
- **Quality Signal**: If > 3 fields marked `⚠️ UNKNOWN`, WARN the user about transcription quality.

## 6. Instructions

### Step 0.5: DETECT INPUT FORMAT

The skill handles **two input formats**:

| Format | Markers | Example |
|--------|---------|--------|
| **Timestamped** | Lines like `00:12:34 Name:` or `[12:34]` | Zoom/Teams auto-transcription |
| **Plain text** | `Speaker N` labels or continuous paragraphs, NO timestamps | Whisper, manual, or raw ASR output |

**Detection rule**: Scan first 10 lines. If ≥ 2 lines match pattern `\d{1,2}:\d{2}` → timestamped. Otherwise → plain text.

**For plain text**: Topic boundaries are detected by CONTENT shifts, not by timestamps. Pay extra attention to speaker changes and topic transitions.

### Step 1: PRE-FLIGHT CHECKS

Before generating, you **MUST** validate the input:

| # | Check | Action on Failure |
|---|-------|-------------------|
| 1 | Input is not empty | ❌ STOP: "Transcription is empty." |
| 2 | Length < context window | ⚠️ If > 100K chars → chunk into ~50K blocks with 2K overlap, process each, then merge. **For plain text: split on speaker boundaries, NOT mid-sentence.** |
| 3 | Detect language | Set `languages` in frontmatter. If mixed → note both |
| 4 | ASR quality | If > 30% garbage tokens → WARN user: "Low transcription quality, results may be incomplete." |
| 5 | Participants extractable | If no names found → use "Participant 1", "Participant 2" etc. NEVER fabricate |
| 6 | Input format | Set internal flag: `timestamped` or `plain_text`. Affects section splitting logic. |

### Step 2: DETECT MEETING TYPE

Read `references/meeting_type_detection.md` and classify the meeting.

- If user provided `--type`, use that (override).
- Otherwise, auto-detect from content signals.
- Default to `default` if uncertain.

### Step 3: SELECT TEMPLATE

Based on detected type, load the corresponding template:

| Type | Template |
|------|----------|
| `default` | `assets/template_default.md` |
| `standup` | `assets/template_standup.md` |
| `retrospective` | `assets/template_retrospective.md` |
| `discovery` | `assets/template_default.md` (with emphasis on alternatives and trade-offs) |

### Step 4: GENERATE SUMMARY

Follow the system prompt in `references/generation_prompt.md` using the selected template.

**MANDATORY**: Use tags from `references/tag_taxonomy.md` for consistency.

### Step 5: SELF-VERIFICATION

After generation, execute the Self-Check checklist from `references/generation_prompt.md` §Self-Check.

Then re-scan the transcription to verify no decisions, actions, or insights were missed. If gaps found → supplement and re-check.

### Step 6: COMPLETENESS GUARANTEE (CRITICAL)

**This step is NON-NEGOTIABLE.** After self-verification, perform a final completeness scan:

1. **Count topics in the transcription** — list ALL distinct topics discussed.
2. **Count sections in your summary** — every topic MUST have a corresponding section.
3. **If topics > sections** → you MISSED content. Go back and add the missing sections.
4. **For long transcriptions (> 50K chars)**: Read the ENTIRE text in sequential passes. Do NOT stop after processing "enough" content. The user WILL notice omissions.

**Explicit prohibition**: You MUST NOT:
- Truncate processing midway through the transcription
- Generate a summary based only on the first N% of the text
- Use phrases like "and other topics were discussed" without detailing them
- Collapse multiple distinct topics into a single section

> **Why this matters**: Long meeting transcriptions (1-2 hours, 100K+ chars) contain critical insights scattered throughout. The most valuable action items and decisions often occur in the LAST 30% of the meeting. Skipping the tail is the #1 failure mode.

### Step 7: OUTPUT

Save the final summary to the user-specified path.

## 7. Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The transcription is too messy to parse" | Use PRE-FLIGHT check #4. Warn user, but still extract what you can. |
| "This meeting type doesn't fit any template" | Use `default`. It covers all cases. |
| "The self-check is redundant" | Studies show LLMs miss 10-20% of extractable items on first pass. Verify. |
| "I'll add wiki-links later" | You won't. Add them NOW based on mentioned documents/meetings. |
| "Tags taxonomy is too restrictive" | Consistency > creativity for graph navigation. Follow the taxonomy. |
