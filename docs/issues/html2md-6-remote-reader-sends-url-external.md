---
id: HTML2MD-6
type: known-issue
status: by-design
opened_at: 2026-06-23
resolved_by: TASK 023
category: security
severity: LOW
component: html
slug: html2md-6-remote-reader-sends-url-external
---

# HTML2MD-6 — the remote-reader tier sends the target URL to an external service (TASK 023)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** open (by design) • **Severity:** LOW • **Location:** `acquire._fetch_remote_html`.
**Symptom:** the remote tier fetches via `r.jina.ai` (or a configured reader), which retrieves
the page **server-side** — the target URL leaves the machine. As of TASK 023 the remote tier is
**reachable from `--engine auto`** as an automatic last-resort escalation for **public** targets
(not just explicit `--engine jina|remote`), so a public URL may leave the machine on escalation.
**Mitigations:** a private/internal/loopback/metadata target is **never** forwarded (a public-IP
gate runs before any remote request); **`--no-remote`** disables the remote tier entirely (fully
local, no external egress); CR/LF/control chars in the target are refused; the local hop is to a
public reader (passes the SSRF gate); the tier is **vendor-agnostic** (`HTML_READER_URL` /
`HTML_READER_PROVIDERS` → self-hosted Jina or another reader). **Do-not:** rely on `auto`
for sensitive/internal conversions without `--no-remote`. Keyless by default (rate-limited);
`JINA_API_KEY` / `HTML_READER_TOKEN` raise/authorize quota. **Residual:** a reader follows its
own server-side redirects beyond our control.
