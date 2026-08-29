# Backlog — work-items

Enhancements, polish, and signals with **no broken contract**. Defects go to
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md) instead. A thin index over `docs/backlog/`;
human-ranked, no machine sort. Format: `known-issues-format`, Registry B.

Skill-scoped roadmap items live in
[`docs/office-skills-backlog.md`](office-skills-backlog.md); this ledger is for
cross-cutting work-items that do not belong to one skill's roadmap row.

<!-- feedback:discovered-issues -->
- [WI-032 — Windows support for the office skills](backlog/wi-032-windows-support.md) — **open**; native Windows breaks the first three links of every invocation chain (no `install.ps1`, `.venv/bin/python` in the venv bootstrap, top-level `import fcntl` in `_soffice.py`, `python3` as the documented interpreter). WSL2 works today. 39 of 47 entrypoints need nothing beyond those three links, so Stage 2 (GTK / Poppler / Tesseract) is optional, not a prerequisite. Stage 0 (declare + fail legibly) ships alone.
- [WI-031 — design-md blind-acceptance seams](backlog/wi-031-design-md-blind-acceptance-seams.md) — **resolved 2026-08-29**; all 12 reproduced, none refuted, all closed. A second blind Route 2 run answered yes to all eight targeted questions and found an amber status bar at 2.94:1 that both gates were structurally blind to.

## Closed

- [WI-030 — TASK 030 adversarial carry-over](backlog/wi-030-adversarial-carryover.md) — status `done`, resolved 2026-08-29; both slices worked, 19 tests added (157 → 176), 14 mutations killed; `C5-07` was live at BOTH ends of the fence rule.
