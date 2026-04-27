---
description: Generate a highly detailed summary of educational video content with selective Mermaid infographics
extends: summarizing-meetings
meeting_type_override: discovery
---

# Generate Detailed Educational Video Summary

**Purpose**: This workflow **extends** the standard `summarizing-meetings` skill. It adds educational-specific structure (YAML frontmatter, pyramid sections, RAG metadata, Mermaid infographics) on top of the skill's core engine. The skill handles: input validation, format detection, completeness guarantee, self-verification. This workflow handles: educational content extraction, structural enrichment, agent/RAG optimization.

> **Division of responsibility**:
> - `summarizing-meetings` skill → PRE-FLIGHT, chunking, completeness guarantee, self-check, base template
> - This workflow → YAML frontmatter extension, educational sections, Mermaid diagrams, agent metadata, RAG fields

---

## Execution Steps

### Step 1: Input & Context

1. Identify the input transcription file(s) and the target output directory specified by the user.
2. **Multi-file handling**: If the user provides multiple transcript files for the same lesson/topic, treat them as **parts of one continuous lecture**. Concatenate logically (Part 1 → Part 2 → ...) before processing. Do NOT generate separate summaries.

### Step 2: Load Skill

3. Load the `summarizing-meetings` skill as the core logic engine.
4. Set `meeting_type` to `discovery` (auto or via override).
5. Execute the skill's PRE-FLIGHT checks (Step 1 of skill), format detection (Step 0.5), and completeness guarantee (Step 6) as normal.

### Step 3: Generate — Apply Educational Overlay

6. When generating the summary, apply **all** of the following on top of the skill's base template:
   - Extended YAML frontmatter (§ Frontmatter Extension below)
   - Educational pyramid structure (§ Pyramid Structure below)
   - Content Extraction Prompt (§ Content Extraction Prompt below)
   - Agent & RAG metadata (§ Agent & RAG Metadata below)

### Step 4: Output

7. Save the final summary to the user-specified path.

---

## Frontmatter Extension

The skill's base template provides: `type`, `title`, `date`, `meeting_type`, `participants`, `duration`, `languages`, `tags`, `related`.

This workflow **adds** the following fields to the same YAML frontmatter block. Place them AFTER the skill's base fields:

```yaml
# --- Base fields from skill (OVERRIDDEN for educational content) ---
type: lesson-summary              # overrides skill's default "meeting-summary"
title: "{{LESSON_TITLE}}"
date: {{YYYY-MM-DD}}             # recording date, or ⚠️ UNKNOWN
meeting_type: discovery
participants:                    # for lectures, contains speaker(s) only
  - "{{Speaker Name}}"          # canonical speaker ref is in `speaker` field below
duration: "{{HH:MM}}"            # total across all parts
languages:
  - "{{primary_language}}"
tags:
  - lesson                       # from Educational Type in tag_taxonomy.md
  - "{{educational-type-tag}}"   # e.g. lecture, workshop, course-material
  - "{{domain-tag}}"             # from Domain in tag_taxonomy.md
related:
  - "[[{{Related Note}}]]"

# --- Educational extension fields (THIS WORKFLOW) ---
content_type: lesson-summary      # fixed value for educational content
course: "{{Course Name}}"         # e.g. "Генерация спроса. Мастердата"
module: "{{Module Name}}"         # e.g. "Модуль 1 — Основы методологии"
module_number: {{N}}              # integer, e.g. 1
lesson_number: {{N}}              # integer, e.g. 1
speaker: "{{Speaker Full Name}}"  # primary speaker
speaker_role: "{{Role/Title}}"    # e.g. "Старший тренер-методолог, QED Consulting"
concepts:                         # flat list of KEY concepts for RAG indexing
  - "{{concept_1}}"              # e.g. "Solution Selling"
  - "{{concept_2}}"              # e.g. "PPVVC"
prerequisites:                    # what the learner should know before this lesson
  - "[[{{Prior lesson or concept}}]]"
---
```

**Rules**:
- `content_type: lesson-summary` is a **fixed** value — always use it for educational summaries.
- `concepts` — extract up to 5–15 top-level concepts. These become RAG index terms. Use the speaker's terminology (not synonyms). If the material contains fewer than 5 concepts — extract all that exist, do not fabricate.
- `prerequisites` — infer from the speaker's references to prior knowledge. Use `[[wiki-links]]` to other lessons if identifiable. If none — omit the field.
- `module_number` / `lesson_number` — infer from file path or content. If ambiguous — set to `⚠️ UNKNOWN`. Do NOT halt execution to ask the user.

---

## Pyramid Structure

The skill mandates a two-level pyramid (TL;DR → Detailed Sections). This workflow extends it to **three levels** adapted for educational content:

```
Level 0  │  YAML Frontmatter    → machine-readable metadata (agents, RAG, Obsidian)
─────────┼──────────────────────────────────────────────────────────────────────────
Level 1  │  TL;DR               → 3–5 sentences: what is this lesson about,
         │                         what are the key takeaways (executive summary)
         │  Takeaways            → 5–7 numbered bullets: core ideas to retain
         │  (Что запомнить / Key Takeaways — language-adaptive)
         │                         (placed at the END of the document, before Agent Metadata)
─────────┼──────────────────────────────────────────────────────────────────────────
Level 2  │  Detailed Content     → educational sections (see Content Extraction Prompt):
         │    1. Key Concepts    → terms, definitions, frameworks + mindmaps
         │    2. Logical Structure → narrative arc + flowcharts
         │    3. Techniques      → actionable advice + decision flowcharts
         │    4. Examples/Cases  → every real-world example with context
         │    5. Relationships   → concept maps + graph diagrams
─────────┼──────────────────────────────────────────────────────────────────────────
Level 3  │  Agent Metadata       → machine-readable block for RAG / AI agents
```

### Structural rules

- **Level 1 is self-sufficient**: a reader who reads ONLY TL;DR + Takeaways must understand the lesson's essence and key takeaways.
- **Level 2 sections** are independent: each section can be retrieved and understood in isolation (for RAG chunk retrieval).
- **Takeaways** ("Что запомнить" / "Key Takeaways" — language-adaptive) is the LAST content section (before Agent Metadata). It synthesizes — not repeats — the most important points. Think: "if a student reads only this list before an exam, what should be there?"
- **Key Decisions / Action Items / Open Questions** tables from the base skill template are **omitted** for educational content (they are meeting-specific, not lecture-specific). Replace with the 5 educational sections.
- **Each educational section (1–5) replaces** the skill's `### Section N` structure. Use `> **Summary**:` at the top of each section. Do NOT nest the skill's `#### Discussion / Insights / Section Decisions` sub-headers inside educational sections — the educational content structure is self-contained.

### HTML navigation comments

Add HTML comments as **section anchors** for agent navigation. Place them directly BEFORE each `##` or `###` heading. Anchor IDs are always in English (machine-readable). Heading text follows the **language-adaptive rule** from the base skill (generation_prompt.md §7): use the same language as the transcription.

**Russian transcription example:**

```markdown
<!-- SECTION:tldr -->
## Резюме верхнего уровня

<!-- SECTION:detailed -->
## Детальное содержание

<!-- SECTION:concepts -->
### 1. Ключевые концепции и определения

<!-- SECTION:structure -->
### 2. Логическая структура материала

<!-- SECTION:techniques -->
### 3. Практические техники и рекомендации

<!-- SECTION:examples -->
### 4. Примеры и кейсы

<!-- SECTION:relationships -->
### 5. Связи и зависимости

<!-- SECTION:takeaways -->
## Что запомнить

<!-- SECTION:quotes -->
## Ключевые цитаты спикера

<!-- SECTION:agent-metadata -->
## Agent Metadata
```

**English transcription example:**

```markdown
<!-- SECTION:tldr -->
## Executive Summary

<!-- SECTION:detailed -->
## Detailed Content

<!-- SECTION:concepts -->
### 1. Key Concepts and Definitions

<!-- SECTION:structure -->
### 2. Logical Structure of the Material

<!-- SECTION:techniques -->
### 3. Practical Techniques and Recommendations

<!-- SECTION:examples -->
### 4. Examples and Case Studies

<!-- SECTION:relationships -->
### 5. Relationships and Dependencies

<!-- SECTION:takeaways -->
## Key Takeaways

<!-- SECTION:quotes -->
## Notable Speaker Quotes

<!-- SECTION:agent-metadata -->
## Agent Metadata
```

**Why**: Anchor IDs (`SECTION:concepts` etc.) are language-agnostic and allow agents/RAG pipelines to jump directly to sections. Heading text adapts to the content language for human readability.

---

## Content Extraction Prompt

When analyzing the transcript, you MUST apply the following instructions to generate the Level 2 (Detailed Content) sections.

***

```text
CRITICAL CONTENT REQUIREMENT FOR EDUCATIONAL VIDEO DOCUMENTATION:

This summary will be used as a comprehensive study reference derived from an educational video transcription. Generate the following as distinct, highly detailed subsections within the "Detailed Content" section:

1. **Key Concepts and Definitions**:
   Extract ALL terms, concepts, frameworks, models, and methodologies introduced by the speaker. Provide a bulleted list with concise definitions in the speaker's own words. Preserve nuances and context — do not reduce to dictionary-style definitions.
   - If a concept has a hierarchical or categorical structure (e.g., a framework with sub-components, a taxonomy, a classification) → add a `mindmap` Mermaid diagram to visualize the hierarchy.

2. **Logical Structure of the Material**:
   Reconstruct the narrative arc of the lecture/video: what topics are covered, in what order, and how they logically connect to each other. Present as a numbered outline with brief annotations for each topic.
   - If the material has a non-linear, multi-branch, or phased structure (e.g., a course roadmap, a methodology with stages, parallel tracks) → add a `flowchart` Mermaid diagram showing topic flow and dependencies.

3. **Practical Techniques and Recommendations**:
   Extract ALL actionable advice, methods, tools, step-by-step instructions, best practices, and anti-patterns mentioned by the speaker. Present each technique with enough context to be applied independently.
   - For multi-step techniques, decision trees, or processes with branching logic → add a `flowchart` Mermaid diagram illustrating the steps and decision points.

4. **Examples and Case Studies**:
   Capture EVERY real-world example, analogy, story, or case study mentioned. For each, describe: the context/setup, the problem or challenge, the approach taken, and the outcome or lesson learned. Do not omit "small" examples — they often carry the most practical value.
   - If a case study involves a process flow, a before/after comparison, or interactions between multiple actors → consider adding a `graph` or `flowchart` Mermaid diagram.

5. **Relationships and Dependencies**:
   Map connections between concepts, roles, tools, systems, or methodologies mentioned in the material. Identify cause-effect links, prerequisites, complementary ideas, and conflicts.
   - When relationships are non-trivial or involve more than 3 interconnected elements → add a `graph LR` Mermaid diagram showing the ecosystem and connections.

---

MERMAID INFOGRAPHIC GUIDELINES:

- Add diagrams ONLY where they sharpen understanding or highlight structure that is hard to grasp from text alone. Plain text is perfectly fine when the material is straightforward.
- Do NOT add a diagram to every section — be selective and purposeful.
- Preferred diagram types:
  - `mindmap` — for hierarchies, taxonomies, concept breakdowns
  - `flowchart` / `flowchart LR` — for processes, sequences, decision trees, course structures
  - `graph LR` — for relationships, ecosystems, integrations between entities
- Use the SAME LANGUAGE as the transcript for all diagram labels and annotations.
- Apply color styling (`style ... fill:#HEX,color:#fff`) and emoji for visual scanning where appropriate.
- Keep diagrams focused: 5–15 nodes is ideal. Split overly complex diagrams into multiple smaller ones.

---

SPEAKER QUOTES:

After the "Relationships and Dependencies" section and before the Takeaways section, add a **Speaker Quotes** section (language-adaptive: "Ключевые цитаты спикера" for Russian, "Notable Speaker Quotes" for English):
- Extract 3–7 direct quotes that capture the speaker's most important or memorable statements.
- Use blockquote formatting (`>`).
- Prefer quotes that convey principles, mental models, or warnings — not factual statements.

---

Do not generalize the narrative. Ensure maximum granularity. Every concept, technique, example, and relationship discussed in the video MUST be preserved and structured. Pay special attention to the speaker's emphasis, repeated points, and explicit "this is important" markers.
```

***

---

## Self-Check Override

The base skill's self-check (`generation_prompt.md` §Self-Check) references meeting-specific tables (Key Decisions, Action Items) that are **omitted** in educational summaries. Replace the skill's 8-point checklist with the following **educational self-check**:

```
□ Every concept from the transcription is in the "Key Concepts" section
□ Every technique/recommendation has enough context to apply independently
□ Every example/case study has context + problem + outcome described
□ Every section contains > **Summary**: block at the top
□ TL;DR is self-sufficient (understandable without reading details)
□ Takeaways section synthesizes (not repeats) the most important points
□ All specific numbers/names/dates/formulas are preserved verbatim
□ Tags conform to references/tag_taxonomy.md (Educational Type section)
□ No more than 3 fields marked ⚠️ UNKNOWN (otherwise → WARN user)
□ [[wiki-links]] are correct (if vault is accessible)
□ Mermaid diagrams render correctly (valid syntax, 5–15 nodes each)
□ HTML section anchors are present before every ## and ### heading
```

After this checklist, perform the skill's standard **Verification Loop**: re-read the transcription end-to-end and verify no concepts, techniques, or examples were missed.

---

## Agent & RAG Metadata

The skill's base template includes a generic `Agent Metadata` block. This workflow **replaces** it with an extended version optimized for educational content retrieval.

Place this block at the very end of the document, after the Takeaways section:

```markdown
<!-- SECTION:agent-metadata -->
## Agent Metadata

> [!NOTE]
> This block is intended for AI agents, RAG systems, and automated pipelines.
> It is not part of the study material.

### Semantic Index

- **Main topics**: {{topic1}}, {{topic2}}, {{topic3}}
- **Mentioned frameworks/models**: {{framework1}}, {{framework2}}
- **Mentioned companies/products**: {{company1}}, {{company2}}
- **Mentioned persons/roles**: {{person1 (role)}}, {{person2 (role)}}
- **Mentioned metrics/numbers**: {{metric1: value}}, {{metric2: value}}

### Concept Definitions (machine-readable)

| Concept | Definition (1 sentence) | Related concepts |
|---------|------------------------|-----------------|
| {{concept}} | {{definition}} | {{related1}}, {{related2}} |

### Chunk Boundaries

> Use these anchors to split the document into semantic chunks for embedding.
> Each chunk is self-contained and retrievable independently.

| Chunk ID | Section | Anchor | Token estimate |
|----------|---------|--------|---------------|
| {{lesson}}-concepts | {{Concepts section title}} | `<!-- SECTION:concepts -->` | ~{{N}} |
| {{lesson}}-structure | {{Structure section title}} | `<!-- SECTION:structure -->` | ~{{N}} |
| {{lesson}}-techniques | {{Techniques section title}} | `<!-- SECTION:techniques -->` | ~{{N}} |
| {{lesson}}-examples | {{Examples section title}} | `<!-- SECTION:examples -->` | ~{{N}} |
| {{lesson}}-relationships | {{Relationships section title}} | `<!-- SECTION:relationships -->` | ~{{N}} |
| {{lesson}}-takeaways | {{Takeaways section title}} | `<!-- SECTION:takeaways -->` | ~{{N}} |

### Content Fingerprint

- **Total concepts extracted**: {{N}}
- **Total examples/cases**: {{N}}
- **Total Mermaid diagrams**: {{N}}
- **Transcript coverage**: 100%
- **Source files**: {{file1.txt}}, {{file2.txt}}
```

**Rules for Agent Metadata**:
- `Concept Definitions` table — one row per concept from the `concepts` frontmatter field. Definition must be a single sentence (for embedding). Related concepts create a graph.
- `Chunk Boundaries` — estimate token count per section (~3 chars/token for Russian/Cyrillic, ~4 chars/token for English/Latin). This helps RAG pipelines decide chunking strategy.
- `Content Fingerprint` — quantitative summary for pipeline validation (e.g., "did the agent actually extract enough?").
- `Source files` — list all input transcript filenames (not full paths).

---

## Usage Example

```
/generate-detailed-meeting-summary on transcript [path/to/transcript.txt] output to [path/to/output_folder/]
```

For multiple files (same lesson):

```
/generate-detailed-meeting-summary
Module 1/Transcripts/01-1 - Topic Name.txt
Module 1/Transcripts/01-2 - Topic Name.txt

Combine all files into a single lesson summary and save to Module 1/Summary
```
