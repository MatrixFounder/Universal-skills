---
id: HTML2MD-8
type: known-issue
status: handled
opened_at: 2026-06-23
category: robustness
severity: SEV-2
component: html
slug: html2md-8-empty-extraction-guard
---

# HTML2MD-8 — empty-extraction guard (no more silent empties)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** handled • **Severity:** (was HIGH for Wikipedia) • **Location:** `cli._extraction_is_empty`.
**Was (feedback R-7a):** a substantial source that converted to an empty body still exited 0 with a
frontmatter-only note — the worst failure class (looks like success, silently loses content).
**Now:** if the whole-page Markdown body is < ~16 chars while the source HTML was ≥ ~2 KB, the run
raises typed **`EmptyExtraction` (exit 11)** so callers can retry with another engine/endpoint.
**Do-not:** widen the thresholds without re-running the battery — a genuinely image-only or
one-line page must NOT trip the guard.
