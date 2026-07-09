---
id: HTML2MD-4
type: known-issue
status: open
opened_at: 2026-06-23
category: security
severity: LOW
component: html
slug: html2md-4-ssrf-residuals-lite-path-hardened
---

# HTML2MD-4 — SSRF residuals (lite path hardened)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** open (honest-scope) • **Severity:** LOW • **Location:** `acquire._is_ssrf_blocked`
/ `_host_is_public` + `_fetch_chrome_html`. The lite path blocks private/loopback/link-local/
metadata/reserved on every redirect hop and streams with `--max-bytes`. The gate keeps Python's
maintained `ip.is_private` (a superset of the old behaviour) and only **subtracts an explicit
carve-out** (`HTML_SSRF_ALLOW_NETS`) — there is **no built-in code default**, so an absent var
widens nothing: unset **or** `""` → NO carve-out (strict, fail-safe); a CIDR list → exactly
those ranges. The shipped `<skill>/.env.example` sets `HTML_SSRF_ALLOW_NETS=198.18.0.0/15` (RFC
2544 benchmarking — some local resolvers, e.g. ENS/`.eth.limo` gateways, map real public
hostnames into that range), so the auto-loaded `.env` re-allows it; a host without that value
refuses it. IPv4-mapped (`::ffff:x`) and IPv4-translated (`::ffff:0:x`) IPv6 are unwrapped to
IPv4 before the family-matched check, so `::ffff:169.254.169.254` is still blocked.

**Caveats / NOT covered:**
- **(a) DNS-rebinding (resolve-then-connect TOCTOU) — ✅ CLOSED on the lite path.** Implemented
  fix (1) **IP-pinning**: `_resolve_validated_addrs` resolves + validates the host ONCE, then
  `_pin_host_addrs` forces `socket.getaddrinfo` to return exactly those validated IP(s) for the
  duration of the connect, so httpx connects to the IP that was security-checked (TLS SNI / `Host`
  / cert verification still use the hostname). An attacker who flips the authoritative answer to a
  private IP after validation can no longer be reached — the pinned address holds. *Residual:* the
  pin is process-global (correct for the single-threaded CLI fetch); and the **Chrome engine does
  NOT pin** (Playwright manages its own sockets — its context route-guard re-validates each
  request's host but is itself resolve-then-connect), so chrome retains the TOCTOU. Mitigation for
  chrome: egress-restricted sandbox.
- **(b)** a carve-out you configure is reachable from the host by design — `0.0.0.0/0` disables
  IPv4 protection entirely; trusted-local-config only.
- **(c)** the opt-in Chrome engine is now SSRF-gated (see
  [HTML2MD-10](./html2md-10-authenticated-chrome-honest-scope.md)).

**Strictest local posture:** `--no-remote` + leave `HTML_SSRF_ALLOW_NETS` unset/empty.
