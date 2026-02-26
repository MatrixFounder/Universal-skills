<!--
  TEMPLATE: Default Meeting Summary
  LANGUAGE NOTE: All placeholders and structural headers are in English.
  When generating the actual summary, headers MUST be in the same
  language as the transcription (see generation_prompt.md §7).
-->
---
type: meeting-summary
title: "{{MEETING_TITLE}}"
date: {{YYYY-MM-DD}}
meeting_type: default
participants:
  - "{{Participant 1}}"
  - "{{Participant 2}}"
duration: "{{HH:MM}}"
languages:
  - "{{primary_language}}"
tags:
  - meeting
  - "{{domain-tag}}"
  - "{{project-tag}}"
related:
  - "[[{{Related Note 1}}]]"
  - "[[{{Related Note 2}}]]"
---

# {{MEETING_TITLE}}

> **Date**: {{date}} | **Duration**: {{duration}} | **Participants**: {{participants list}}

---

## TL;DR

{{3–5 sentences. What was discussed, what key decisions were made,
what is the main outcome of the meeting. This block is the ONLY thing
a busy executive will read.}}

---

## Key Decisions

| # | Decision | Decided by | Context |
|---|----------|-----------|---------|
| 1 | {{Decision}} | {{Name}} | {{Why this approach}} |

## Action Items

| # | Task | Owner | Deadline | Status |
|---|------|-------|----------|--------|
| 1 | {{Task}} | {{Name}} | {{Date}} | 🔲 Open |

## Open Questions

- {{Question that remained unanswered and requires follow-up}}

---

## Detailed Content

### {{Section 1: Topic Name}}

> **Summary**: {{1–2 sentences — section essence for quick scanning}}

#### Discussion

{{Detailed description of what was discussed in this logical part
of the meeting. Who said what, which arguments were made, which
options were considered.}}

#### Insights

- 💡 {{Insight 1 — non-obvious thought worth remembering}}
- 💡 {{Insight 2}}

#### Section Decisions

- ✅ {{Decision made within this section}}

---

### {{Section 2: Topic Name}}

> **Summary**: {{1–2 sentences — section essence}}

#### Discussion

{{...}}

#### Insights

- 💡 {{...}}

#### Section Decisions

- ✅ {{...}}

---

*(...repeat for each logical section...)*

---

## Agent Metadata

> [!NOTE]
> This block is intended for AI agents and RAG systems.

- **Main topics**: {{topic1}}, {{topic2}}, {{topic3}}
- **Mentioned systems/tools**: {{tool1}}, {{tool2}}
- **Mentioned metrics/numbers**: {{metric1: value}}, {{metric2: value}}
- **Emotional tone**: {{neutral / constructive / tense}}
- **Consensus level**: {{high / medium / low}}
