---
description: Generate a highly detailed summary from a meeting/lecture transcript in one of two profiles — business-discovery (5 process-extraction registries as a Business Process Passport dataset) or educational (3-level pyramid, selective Mermaid infographics, speaker quotes, RAG/agent metadata). Extends the summarizing-meetings skill.
extends: summarizing-meetings
meeting_type_override: discovery
---

# Generate Detailed Meeting Summary (Process Discovery + Educational)

**Purpose**: This workflow **extends** the standard `summarizing-meetings` skill. It turns a raw transcript into a highly detailed summary in **one of two profiles**:

- **`business-discovery`** — extracts structured business-process information (Roles, IT Systems, Process Steps, KPIs, Risks) as an ideal, rich **single source of truth** dataset for subsequently generating a formal **Business Process Passport**.
- **`educational`** — produces a lesson/study reference with a 3-level pyramid, selective Mermaid infographics, speaker quotes, and RAG/agent metadata.

Both profiles ride the SAME engine path: content class **`transcript`** → output format **pyramid Markdown** → `meeting_type: discovery`. The profile only selects which overlay (Detailed-Content shape, frontmatter, self-check, metadata) is layered on top — it does NOT change how the skill is invoked.

> **Division of responsibility**:
> - `summarizing-meetings` skill → PRE-FLIGHT, chunking, content-class/format detection, completeness guarantee, self-verification, base template.
> - This workflow → profile selection, profile-specific Detailed-Content extraction, frontmatter shaping, structural enrichment, agent/RAG optimization.

---

## Profiles

This workflow is parameterized by a single selector that the base skill never reads:

| Selector | Values | How chosen |
|----------|--------|-----------|
| **`--profile`** | `business-discovery` · `educational` | **Auto-detected** (see below); override with `--profile business-discovery\|educational`. **Default: `business-discovery`.** |

> **Why a new flag?** `--profile` is deliberately distinct from every flag the `summarizing-meetings` skill already consumes (`--content`, `--type`, `--mode`, `--emit`, `--contract`, `--translate`) and from its reserved enum values / injected keys — so it never collides with the engine. `--profile` selects an *overlay*, not a skill parameter.

**Auto-detection** (applies only when `--profile` is absent):

- → **`business-discovery`** when the input is a **multi-party** transcript (≥ 2 distinct speakers/roles) exhibiting job titles/roles, decisions/approvals, hand-offs of responsibility, IT-system mentions, KPIs, or pain-points/risks — i.e. an operational / process discovery meeting.
- → **`educational`** when the input shows a **single-speaker teaching cadence** (one dominant voice, explanatory/lecture prose, "this is important" markers) **or** references a course/module/lesson structure (e.g. `Модуль N`, lesson numbering, a course name in the path or content).
- **Tie or ambiguity → `business-discovery`** (the default).

An explicit `--profile` **always wins** over auto-detection.

---

## Execution Steps

### Step 1: Input & Context

1. Identify the input transcript file(s) and the target output directory specified by the user.
2. **Multi-file handling**: If the user provides multiple transcript files for the same lesson/topic/meeting, treat them as **parts of one continuous session**. Concatenate logically (Part 1 → Part 2 → ...) before processing. Do NOT generate separate summaries.

### Step 2: Select Profile

3. Determine the profile: honor an explicit `--profile business-discovery|educational` if given; otherwise auto-detect per the **Profiles** section above (multi-party process meeting → `business-discovery`; single-speaker teaching / course-module cadence → `educational`). Default = `business-discovery`.

### Step 3: Load Skill

4. Load the `summarizing-meetings` skill as the core logic engine.
5. Set `meeting_type` to `discovery` (auto or via override).
6. Execute the skill's PRE-FLIGHT checks (skill Step 1), content-class detection (skill Step 0 — auto-detects `transcript`, the path this workflow extends), input-format detection (skill Step 0.5), and completeness guarantee (skill Step 8) as normal. Output stays **pyramid Markdown** — do NOT pass `--emit note-json`, and do NOT translate (no `--translate`) unless the user explicitly asks.

### Step 4: Generate — Apply the Selected Profile Overlay

7. Apply the overlay for the selected profile **on top of** the skill's base template:
   - **`business-discovery`** → apply the **Process Extraction Prompt** (§ Profile A) and **KEEP** the base meeting template blocks (Key Decisions / Action Items / Open Questions).
   - **`educational`** → apply the Extended YAML frontmatter, 3-level Pyramid Structure, Content Extraction Prompt, Speaker Quotes, and Agent & RAG Metadata (§ Profile B).

### Step 5: Output

8. Save the final summary to the user-specified path.

---

# Profile A — Business Discovery

> Active when `--profile business-discovery` (the default). Produces a `meeting-summary` whose "Detailed Content" section is enriched with five process registries, forming the single source of truth for a Business Process Passport.

## A.1 Output frontmatter (business profile)

Use the skill's base meeting frontmatter. Keep `type: meeting-summary` (the skill default) and pin `meeting_type: discovery`:

```yaml
type: meeting-summary            # business-discovery keeps the skill's meeting type
meeting_type: discovery
# title / date / participants / duration / languages / tags / related — from the skill base template
```

Do **NOT** set `content_type`, `course`, `module`, `speaker`, `concepts`, etc. — those are **educational-only** (Profile B).

## A.2 Kept base template blocks

`business-discovery` **KEEPS** the base skill's meeting template blocks — **Key Decisions**, **Action Items**, and **Open Questions** tables — exactly as `generation_prompt.md` / `template_default.md` produce them. The five registries below are **ADDED** as distinct subsections **within** the "Detailed Content" section; they do not replace the meeting blocks.

## A.3 Process Extraction Prompt

When analyzing the transcript, you MUST inject the following exact instructions into your generation context.

***

```text
CRITICAL CONTENT REQUIREMENT FOR PROCESS DOCUMENTATION:

This meeting protocol will be used as the single source of truth for generating a formal Business Process Passport. In addition to the standard summary template blocks, you MUST extract and structure the following elements from the transcript. Add them as distinct, highly detailed subsections within the "Detailed Content" section:

1. **Role and Actor Registry**: 
   Extract all mentioned job titles, roles, or organizational units (e.g., Key Account Manager, Operator, Supervisor, External Client, Financial Controller). Provide a bulleted list describing the specific responsibilities and actions of each role within the discussed process.

2. **IT Landscape and Artifacts**: 
   Compile a comprehensive list of all technical systems and documents mentioned in the flow.
   - *Systems*: List any software, platforms, or tools mentioned (e.g., ERP, CRM, B2B portals, mobile applications, reporting cubes).
   - *Artifacts*: List any input/output documents, forms, or data entities (e.g., specifications, contracts, invoices, Excel planning files, KPI matrices).

3. **Draft Process Steps (Scenarios)**: 
   Extract the step-by-step flow of the discussed processes. Present this as a structured list or table containing the following fields for each step:
   - [Actor] -> [Action performed] -> [IT System used] -> [Input Artifact] -> [Output/Result]
   *Do not omit details.* Pay special attention to conditions, approvals, manual workarounds, and points where responsibility is handed over between actors.

4. **KPIs and Metrics Matrix**: 
   Explicitly identify any metrics, targets, or performance indicators discussed (e.g., sales volume targets, profit margins, SLA compliance, defect rates, out-of-stock limits). Note how these metrics are calculated or tracked, if mentioned.

5. **Risk and Bottleneck Registry**: 
   Extract all operational pain points, delays, or inefficiencies discussed by the participants. Formulate these as specific business risks. 
   Examples: 
   - Operations risk: Manual data transfer between two legacy systems leading to errors.
   - Financial risk: Delayed notifications about price changes leading to margin loss.
   - Compliance risk: Lack of formal SLA for document approvals.

Do not generalize the narrative. Ensure maximum granularity. Every detail regarding the transfer of responsibility, state changes, and software system usage MUST be preserved and structured.
```

***

---

# Profile B — Educational

> Active when `--profile educational`. Produces a `lesson-summary` with a 3-level pyramid, selective Mermaid infographics, speaker quotes, and extended RAG/agent metadata. Everything in this profile is **scoped to Profile B** and must NOT leak into Profile A (in particular `type: lesson-summary` / `content_type: lesson-summary`).

## B.1 Frontmatter Extension

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
sources:                         # provenance — THIS WORKFLOW; one entry per source recording/transcript
  - file: "{{transcript_vault_rel_path}}"  # REQUIRED — the local transcript actually summarized, as a path RELATIVE TO THE VAULT ROOT (e.g. "<folder>/_transcripts/<id>.ru.txt"), not a bare filename, so the reference stays unambiguous when the same filename exists in other folders
    url: "{{source_url}}"            # optional — canonical web origin if any (YouTube/Vimeo/Skool/article/podcast/…)
    id: "{{platform_id}}"            # optional — platform-native id when the source has one (e.g. YouTube video slug)
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
- `sources` — provenance of the lesson. One list entry **per source recording/transcript** (multi-part lectures get multiple entries, in Part order). `file` is the **only required** key and works for **any** source: set it to the transcript's path **relative to the vault root** (e.g. `<folder>/_transcripts/<id>.ru.txt`) — **not** a bare filename — so the reference stays unambiguous when the same basename exists in more than one folder. `url` (canonical web origin) and `id` (platform-native id) are **optional** — include them only when the source actually has them. Conventions by source type:
  - **YouTube** → `id` = the 11-char video slug (preserve a leading `-`), `url` = `https://youtu.be/<id>`; for `<id>.ru.txt`-style transcript filenames both are derivable from the filename (the part before the first `.`).
  - **Other web sources** (Vimeo, Skool, article, podcast, …) → use that platform's native `url`, and `id` only if it exposes a stable one.
  - **No web origin** (local recording, uploaded file) → keep only `file`; omit `id`/`url`.

  This is the structured, frontmatter-level mirror of the `Source files` line in the Content Fingerprint block (§ Agent & RAG Metadata): both list the SAME source set, but `sources[].file` carries the machine-readable **vault-relative path** while the body line stays the human-readable basename.
- `content_type: lesson-summary` is a **fixed** value — always use it for educational summaries.
- `concepts` — extract up to 5–15 top-level concepts. These become RAG index terms. Use the speaker's terminology (not synonyms). If the material contains fewer than 5 concepts — extract all that exist, do not fabricate.
- `prerequisites` — infer from the speaker's references to prior knowledge. Use `[[wiki-links]]` to other lessons if identifiable. If none — omit the field.
- `module_number` / `lesson_number` — infer from file path or content. If ambiguous — set to `⚠️ UNKNOWN`. Do NOT halt execution to ask the user.

## B.2 Pyramid Structure

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
- **Key Decisions / Action Items / Open Questions** tables from the base skill template are **omitted** for educational content (they are meeting-specific, not lecture-specific). Replace with the 5 educational sections. *(This OMIT applies to Profile B only — Profile A KEEPS those tables.)*
- **Each educational section (1–5) replaces** the skill's `### Section N` structure. Use `> **Summary**:` at the top of each section. Do NOT nest the skill's `#### Discussion / Insights / Section Decisions` sub-headers inside educational sections — the educational content structure is self-contained.

## B.3 HTML navigation comments

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

## B.4 Content Extraction Prompt

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

## B.5 Agent & RAG Metadata

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
- `Source files` — list all input transcript **basenames** (human-readable, no paths). These refer to the SAME sources as the frontmatter `sources[].file` values (§ B.1 Frontmatter Extension), which instead carry the **vault-relative path** — the body line is the human-readable view, `sources` is the machine-readable one. Keep the set consistent (same recordings, same order).

---

## Self-Check (Unified)

Run the shared checks, then the checklist for the **active profile**, then the skill's standard Verification Loop.

### Shared checks (both profiles)

```
□ Entire transcript processed end-to-end — no truncation, no "first N%", no collapsed topics (skill Step 8 completeness guarantee)
□ Every distinct source topic maps to a section/registry (topic count == coverage)
□ All specific numbers / names / dates / formulas preserved verbatim
□ No fabricated participants / roles / dates (use "Participant N" or ⚠️ UNKNOWN where unknown)
□ Tags conform to references/tag_taxonomy.md
□ No more than 3 fields marked ⚠️ UNKNOWN (otherwise → WARN the user; never halt to ask)
□ Output is pyramid Markdown (not note-json); meeting_type = discovery
```

### If profile = business-discovery

```
□ All 5 registries present as subsections inside "Detailed Content": Role & Actor Registry; IT Landscape & Artifacts (Systems + Artifacts sublists); Draft Process Steps using [Actor] -> [Action performed] -> [IT System used] -> [Input Artifact] -> [Output/Result]; KPIs & Metrics Matrix; Risk & Bottleneck Registry
□ Base meeting blocks retained: Key Decisions, Action Items, Open Questions
□ type: meeting-summary (no lesson-summary / content_type / course / speaker / concepts fields)
□ Responsibility hand-offs, state changes, and software usage NOT generalized away
```

### If profile = educational (replaces the skill's 8-point meeting self-check)

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
□ type: lesson-summary; content_type: lesson-summary present
□ sources[].file (vault-relative paths) and Content Fingerprint "Source files" (basenames) describe the SAME recordings in the SAME order
```

### Then (both profiles)

Perform the skill's standard **Verification Loop**: re-read the transcription end-to-end and verify no topics / decisions / concepts / techniques / examples / registry items were missed. If gaps are found → supplement and re-check.

---

## Usage Examples

**Business discovery (default profile):**

```
/generate-detailed-meeting-summary on transcript [path/to/transcript.txt] output to [path/to/output_folder/]
```

(Add `--profile business-discovery` to force it; it is also the default.)

**Educational:**

```
/generate-detailed-meeting-summary --profile educational on transcript [path/to/lesson.txt] output to [path/to/output_folder/]
```

**Educational, multiple files (same lesson):**

```
/generate-detailed-meeting-summary --profile educational
Module 1/Transcripts/01-1 - Topic Name.txt
Module 1/Transcripts/01-2 - Topic Name.txt

Combine all files into a single lesson summary and save to Module 1/Summary
```

You may also ask the agent directly instead of using the slash command.
