<!--
  TEMPLATE: Standup Meeting Summary
  LANGUAGE NOTE: All placeholders and structural headers are in English.
  When generating the actual summary, headers MUST be in the same
  language as the transcription (see generation_prompt.md §7).
-->
---
type: meeting-summary
title: "{{MEETING_TITLE}} — Daily Standup"
date: {{YYYY-MM-DD}}
meeting_type: standup
participants:
  - "{{Participant 1}}"
  - "{{Participant 2}}"
duration: "{{HH:MM}}"
languages:
  - "{{primary_language}}"
tags:
  - meeting
  - standup
  - "{{project-tag}}"
related:
  - "[[{{Related Note}}]]"
---

# {{MEETING_TITLE}} — Daily Standup

> **Date**: {{date}} | **Duration**: {{duration}} | **Participants**: {{participants list}}

---

## TL;DR

{{1–2 sentences. Brief summary: main blockers and key updates.}}

---

## Status by Participant

### {{Participant 1}}

| ✅ Done Yesterday | 🔄 Plans for Today | 🚧 Blockers |
|-------------------|-------------------|-------------|
| {{Task 1}} | {{Task 1}} | {{Blocker or "None"}} |
| {{Task 2}} | {{Task 2}} | |

---

### {{Participant 2}}

| ✅ Done Yesterday | 🔄 Plans for Today | 🚧 Blockers |
|-------------------|-------------------|-------------|
| {{Task 1}} | {{Task 1}} | {{Blocker or "None"}} |

---

*(...repeat for each participant...)*

---

## Blockers Summary

| # | Blocker | Who is Blocked | Required Action |
|---|---------|---------------|-----------------|
| 1 | {{Blocker}} | {{Name}} | {{What needs to happen}} |

## Action Items

| # | Task | Owner | Deadline | Status |
|---|------|-------|----------|--------|
| 1 | {{Task}} | {{Name}} | {{Date}} | 🔲 Open |

---

## Agent Metadata

- **Main topics**: {{topic1}}, {{topic2}}
- **Critical blockers**: {{yes / no}}
- **Overall progress**: {{on track / behind / ahead}}
