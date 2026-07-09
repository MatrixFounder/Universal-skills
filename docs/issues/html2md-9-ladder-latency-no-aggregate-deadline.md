---
id: HTML2MD-9
type: known-issue
status: open
opened_at: 2026-06-23
resolved_by: TASK 023
category: performance
severity: LOW
component: html
slug: html2md-9-ladder-latency-no-aggregate-deadline
---

# HTML2MD-9 — ladder latency has no aggregate deadline; `--max-bytes` is unbounded by default (TASK 023 /vdd-multi)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** open (honest-scope) • **Severity:** LOW (was perf-HIGH in review) • **Location:**
`acquire._acquire_url` ladder + `_http_get_bytes` + `run_search`.
**Symptom:** the fallback ladder runs tiers sequentially and each tier has its OWN retry budget
(`--retries`, default 2) × per-request timeout (~20s). There is no *aggregate* wall-clock cap, so a
target that times out on every tier can take minutes (worst case ≈ Σ tiers; `--search` multiplies it
by `--max-results`). Separately, **`--max-bytes` defaults to unbounded**, so a remote reader / search
response is fully buffered + decoded (peak ≈ 3× body) unless the user sets a cap.
**Workaround:** for untrusted / bulk / flaky targets pass `--retries 0` (or low), `--rate-limit`, and
an explicit `--max-bytes` (e.g. `--max-bytes 52428800`); Ctrl-C is always available. **Fix path
(follow-up, beyond TASK 023 RTM):** add an aggregate `--deadline SECONDS` checked per-tier + a sane
default `--max-bytes`. **Do-not:** treat a slow multi-tier fall-through as a hang — it is bounded,
just uncapped; the `details.tried` trace shows what was attempted.
**Note (handled in this task):** the related SSRF concern — a `--search` result URL escalating to the
un-network-hardened Chrome tier — IS fixed: search-result fetches drop the chrome tier unless the
user explicitly chose `--engine chrome` (`acquire._url_tiers(allow_chrome=…)`). The remaining Chrome
honest-scope (no per-request SSRF gate, follows internal redirects) is unchanged for an *explicit*
`--engine chrome` on a user-supplied URL — see
[HTML2MD-4](./html2md-4-ssrf-residuals-lite-path-hardened.md). **(SUPERSEDED by TASK 024 /
[HTML2MD-10](./html2md-10-authenticated-chrome-honest-scope.md): the Chrome tier is now SSRF-gated
always.)**
