<!--
  TEMPLATE: Document / Article Summary (content class = document)
  LANGUAGE NOTE: All placeholders and structural headers are in English.
  When generating, headers MUST be in the SAME language as the source
  (source language by default; target language only if --translate is set).
  See references/article_generation_prompt.md §5–6.
  DEPTH: chosen by --mode (full / summary / thread) — see content_type_detection.md Part B.
-->
---
type: article-summary
title: "{{DOCUMENT_TITLE}}"
title_orig: "{{ORIGINAL_TITLE if translated, else omit}}"
author: "{{Author or null}}"
date: {{YYYY-MM-DD or ⚠️ UNKNOWN}}
source: "{{canonical URL or origin, if known}}"
mode: {{full | summary | thread}}
languages:
  - "{{source_language}}"
tags:
  - article
  - "{{document-type-tag}}"   # paper / blog / news / thread / report / reference-doc
  - "{{domain-tag}}"
related:
  - "[[{{Related Concept 1}}]]"
  - "[[{{Related Concept 2}}]]"
---

# {{DOCUMENT_TITLE}}

> **Author**: {{author}} | **Date**: {{date}} | **Source**: {{source}} | **Mode**: {{mode}}

---

## TL;DR

{{3–5 sentences: the document's thesis, its method/approach, and its main conclusion.
This block is the ONLY thing a busy reader will read — make it self-sufficient.}}

---

## Key Points

<!-- full: 4–7 bullets · summary/dense: 8–14 detailed bullets -->

- 🔑 {{Problem / goal the document addresses}}
- 🔑 {{Approach / method / framework used}}
- 🔑 {{Key finding (with numbers where given)}}
- 🔑 {{Conclusion / recommendation / implication}}

---

## Detailed Content

<!-- One section per logical part of the source. Follow the source's own structure. -->

### {{Section 1: Topic / Source Section Name}}

> **Summary**: {{1–2 sentences — section essence for quick scanning}}

{{Detailed prose: the argument, evidence, examples, and numbers in this part of the document.
For mode=full reproduce the whole argument; for mode=summary digest it faithfully (preserve
named findings and numbers); for mode=thread distil and attribute to the author.}}

#### Insights

- 💡 {{Non-obvious takeaway worth remembering}}

---

### {{Section 2: Topic / Source Section Name}}

> **Summary**: {{1–2 sentences}}

{{...}}

---

*(...repeat for each logical section of the source — every section MUST be represented...)*

---

## Open Questions / Limitations

<!-- Capture the document's own stated limitations, caveats, and unresolved questions. -->

- {{Limitation or open question the author raised}}

---

## Agent Metadata

> [!NOTE]
> This block is intended for AI agents and RAG systems.

- **Main topics**: {{topic1}}, {{topic2}}, {{topic3}}
- **Key concepts / frameworks**: {{concept1}}, {{concept2}}
- **Named entities (people / orgs / products)**: {{entity1}}, {{entity2}}
- **Key metrics / numbers**: {{metric1: value}}, {{metric2: value}}
- **Document genre**: {{paper / blog / news / thread / report / reference}}
- **Stance / tone**: {{neutral / argumentative / promotional / critical}}
