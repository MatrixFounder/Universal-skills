---
name: log
kind: log
description: Chronological record of ingest/query/lint operations. Append-only.
---

# Wiki Log

Append-only. Each entry starts with `## [YYYY-MM-DD]` so `grep "^## \[" log.md | tail -5` returns the last 5 events.

Maintained by `wiki-ingest`. Do NOT edit past entries — that defeats the audit trail.

---
