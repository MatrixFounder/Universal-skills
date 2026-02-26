# Tag Taxonomy for Meeting Summaries

All tags in the `tags:` frontmatter MUST be used ONLY from this list.
If a new tag is needed — add it to this file first.

## Rules

1. Use **only** tags from the list below
2. Every summary MUST have the `meeting` tag
3. Add a meeting type tag from the **Meeting Type** section
4. Add 1–3 tags from the **Domain** section based on content
5. Add a project tag from **Project** if applicable
6. Tags are all lowercase, hyphen-separated

## Meeting Type

- `meeting` — base tag (MANDATORY)
- `standup` — daily/weekly standup
- `retrospective` — retrospective
- `discovery` — discovery / brainstorm
- `planning` — planning / grooming
- `review` — code review / design review
- `one-on-one` — 1:1 meeting
- `all-hands` — all-hands / town hall
- `incident` — incident review / postmortem
- `demo` — demo / showcase
- `kickoff` — project kickoff

## Domain

- `product` — product decisions
- `engineering` — technical decisions
- `design` — design / UX
- `data` — data / analytics / ML
- `infrastructure` — infrastructure / DevOps
- `security` — security
- `process` — processes / methodology
- `hiring` — hiring / HR
- `finance` — finance / budget
- `marketing` — marketing
- `sales` — sales
- `support` — support / CX
- `strategy` — strategy
- `legal` — legal matters
- `partnership` — partnerships

## Project

Format: `project/{{project-name}}`

Examples:
- `project/platform-v2`
- `project/mobile-app`
- `project/data-pipeline`

## Priority / Urgency

- `urgent` — requires immediate action
- `blocker` — contains blockers
- `follow-up` — requires follow-up meeting
