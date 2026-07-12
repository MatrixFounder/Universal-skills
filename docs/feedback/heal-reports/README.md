# heal-reports/

Run reports of the `/heal-issues` workflow (framework: `.agent/workflows/heal-issues.md`),
named `<YYYY-MM-DD-HHMM>-<issue-id>.md`. Each report is committed **on the `fix/<id>-<slug>`
branch it documents** — this directory stays empty on `main` until a fix branch is merged.

Review loop: `git branch --list 'fix/*'` → read the report on the branch → optionally re-run
the gates it lists → merge (the ledger status flip lands with the merge) → delete the branch.

Scheduling is user-level opt-in ONLY (no repo cron/CI/git-hooks — see the honest-scope
precedent in `docs/office-skills-backlog.md` xlsx-10 / `docs/reviews/backlog-xlsx-8-9-10-vdd-adversarial-r2.md` R2-H2):
the documented contract is manual `/heal-issues`; `docs/feedback/heal-config.json` keeps
`scheduling.enabled: false` in git.
