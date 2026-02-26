<!--
  TEMPLATE: Retrospective Meeting Summary
  LANGUAGE NOTE: All placeholders and structural headers are in English.
  When generating the actual summary, headers MUST be in the same
  language as the transcription (see generation_prompt.md §7).
-->
---
type: meeting-summary
title: "{{MEETING_TITLE}} — Retrospective"
date: {{YYYY-MM-DD}}
meeting_type: retrospective
participants:
  - "{{Participant 1}}"
  - "{{Participant 2}}"
duration: "{{HH:MM}}"
languages:
  - "{{primary_language}}"
tags:
  - meeting
  - retrospective
  - "{{project-tag}}"
related:
  - "[[{{Related Note}}]]"
---

# {{MEETING_TITLE}} — Retrospective

> **Date**: {{date}} | **Duration**: {{duration}} | **Participants**: {{participants list}}

---

## TL;DR

{{3–5 sentences. Main retrospective takeaways: what critically needs
improvement, what to keep, what is the key action item.}}

---

## 👍 What Went Well

| # | What | Noted by | Why It Matters |
|---|------|---------|---------------|
| 1 | {{Positive item}} | {{Name}} | {{Context}} |

---

## 👎 What Went Wrong

| # | Problem | Raised by | Impact | Root Cause |
|---|---------|----------|--------|------------|
| 1 | {{Problem}} | {{Name}} | {{Impact on team/project}} | {{Why it happened}} |

---

## 🔧 Improvements (Action Items)

| # | Improvement | Owner | Deadline | Priority | Status |
|---|------------|-------|----------|----------|--------|
| 1 | {{Improvement}} | {{Name}} | {{Date}} | 🔴/🟡/🟢 | 🔲 Open |

---

## Detailed Discussion

### {{Topic 1: Name}}

> **Summary**: {{1–2 sentences}}

#### Discussion

{{Detailed description: what was discussed, what opinions were
expressed, what arguments were made.}}

#### Insights

- 💡 {{Insight}}

---

### {{Topic 2: Name}}

> **Summary**: {{1–2 sentences}}

#### Discussion

{{...}}

#### Insights

- 💡 {{...}}

---

*(...repeat for each discussion topic...)*

---

## Retrospective Metrics

- **Team mood**: {{positive / neutral / tense}}
- **Action items count**: {{N}}
- **Recurring issues**: {{Yes: [which] / No}}

---

## Agent Metadata

- **Main topics**: {{topic1}}, {{topic2}}, {{topic3}}
- **Retrospective type**: {{sprint / project / incident}}
- **Emotional tone**: {{constructive / tense / positive}}
- **Consensus level**: {{high / medium / low}}
