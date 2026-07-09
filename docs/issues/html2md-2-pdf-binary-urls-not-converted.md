---
id: HTML2MD-2
type: known-issue
status: by-design
opened_at: 2026-06-23
category: honest-scope
severity: LOW
component: html
slug: html2md-2-pdf-binary-urls-not-converted
---

# HTML2MD-2 — PDFs / binary URLs are not converted

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** open (by design) • **Severity:** LOW • **Location:** `acquire._fetch_lite_html`.
**Symptom:** a `*.pdf` (or binary) URL → `FetchFailed kind=pdf/binary` with a pointer to the
pdf skill. html is HTML→Markdown only. **Fix path:** use `skills/pdf/scripts/pdf_extract.py`.
**Do-not:** feed PDF bytes to turndown (it overflowed the Node stack before the guard).
