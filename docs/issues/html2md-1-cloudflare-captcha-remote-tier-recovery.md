---
id: HTML2MD-1
type: known-issue
status: handled
opened_at: 2026-06-23
resolved_by: TASK 023
category: robustness
severity: LOW
component: html
slug: html2md-1-cloudflare-captcha-remote-tier-recovery
---

# HTML2MD-1 — Cloudflare/captcha-hard sites now auto-recover via the remote tier (TASK 023)

> Part of the HTML2MD (TASK 022) honest-scope set. All deferred-by-design;
> the backlog row [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html»
> owns the decisions. Cross-skill replication (G-1/G-3) and security guards are tested,
> not listed here.

**Status:** handled (residual: needs a reachable reader) • **Severity:** LOW • **Location:**
`acquire._acquire_url` ladder + `_fetch_remote_html`.
**Was:** Cloudflare/captcha sites (papers.ssrn, researchgate) 403'd the lite path and required
the user to know to retry with `--engine jina`/`chrome`.
**Now:** `--engine auto` (default) **auto-escalates** a hard-blocked public page to the remote
reader tier (jina default, vendor-agnostic) after lite (+chrome if installed) fail — recovering
ssrn/researchgate without manual intervention. If the reader is also down, the ladder falls
back and finally fails with one `FetchFailed (kind=all_engines_failed, details.tried=[…])`.
**Residual:** still needs a reachable reader OR `install.sh --with-chrome`; `--no-remote`
opts out of any external escalation (then a hard block is a clean exit 10). **Do-not:** treat
`all_engines_failed` as a bug — every tier was tried; see the `tried` trace. Privacy posture:
[HTML2MD-6](./html2md-6-remote-reader-sends-url-external.md).
