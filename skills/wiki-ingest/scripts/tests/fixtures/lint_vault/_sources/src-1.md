---
title: Lint Source 1
kind: source
type: lesson-summary
date: 2024-03-01
concepts:
  - Foo Bar
  - MissingConcept
related:
  - "[[Linked]]"
---

# Lint Source 1

## TL;DR

Discusses [[Linked]] and [[HasContradiction]]. Also references a specific
section: [[Missing#API]].

## Notes

Inline `[[ShouldBeIgnored]]` and <!-- [[AlsoIgnored]] --> must not surface
as wiki-links. A fenced code block with a fake link:

```md
[[FakeInsideFence]] should be skipped.
```
