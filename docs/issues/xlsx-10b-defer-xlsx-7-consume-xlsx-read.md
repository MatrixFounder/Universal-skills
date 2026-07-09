---
id: XLSX-10B-DEFER
type: known-issue
status: open
opened_at: 2026-05-14
category: tech-debt
component: xlsx
slug: xlsx-10b-defer-xlsx-7-consume-xlsx-read
---

# XLSX-10B-DEFER — xlsx-7 refactor to consume `xlsx_read`

**Status:** DEFERRED (14-day timer started 2026-05-14, deadline
2026-05-28).
**Backlog row:** `xlsx-10.B` in
[`docs/office-skills-backlog.md`](../office-skills-backlog.md).
**Context:** xlsx-7 (`xlsx_check_rules/`) duplicates a portion of
xlsx-10.A `xlsx_read/` reader logic. The refactor was deferred at
xlsx-10.A merge to bound the v1 surface; xlsx-9 merge starts the
14-day ownership-bounded timer. If unaddressed by 2026-05-28, the
duplication becomes a regression risk for any future
`xlsx_read` API change.
**Owner:** TBD (assigned at xlsx-10.B kickoff).
**Workaround:** None required for xlsx-7's current functionality;
the duplication is correctness-preserving as of 2026-05-14.
