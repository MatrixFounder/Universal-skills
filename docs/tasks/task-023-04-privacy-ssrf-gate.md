# Task 023-04 [LOGIC]: privacy / SSRF gate before remote + injection guard

> **Predecessor:** 023-03 (ladder).
> **RTM:** [R5] privacy / SSRF / injection guards.
> **ARCH:** §15.6 (security), §15.8 D-23-A.
> **Methodology:** `tdd-strict` (security-critical — SSRF/injection tests FIRST).

## Use Case Connection
- UC-4 (internal URL never sent to a remote service); hardens UC-1/UC-2/UC-3.

## Task Goal
Guarantee no private/internal/unresolvable **target** URL is ever forwarded to a remote
reader (auto or on-demand), honour `--no-remote`, and harden request-URL construction
against injection. Closes the current gap where `_fetch_jina_html` checks only the scheme.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py`

**Remote-tier admission guard (applied in `_acquire_url`/`_fetch_remote_html`):**
- Before attempting ANY remote provider, require `_host_is_public(urlparse(target).hostname)`
  to be `True` AND `getattr(opts, "no_remote", False)` to be `False`.
- If the remote tier is the only remaining tier and is inadmissible → it is **skipped**;
  the ladder proceeds to the next/last viable tier or raises the terminal error. A skipped
  remote tier is recorded in `tried` as `{"engine":"remote","kind":"skipped_private"|"disabled"}`.
- `--no-remote` removes the remote tier from EVERY engine's tier list (including
  `--engine jina`/`remote` → they then become local-only, still typed-erroring if local fails).

**Request-URL injection guard (in `_build_reader_request` + the search builder):**
- URL-encode the target/query when concatenating onto a provider base; **reject** a target
  containing CR/LF or other control chars → `FetchFailed(kind="refused")` before any send.
- (The base is operator-set/trusted; the target/query is not.)

## Test Cases
### Unit (offline)
1. **TC-04-01 `test_private_target_not_sent_remote`** — target resolving to `127.0.0.1` /
   `10.x` / `169.254.169.254`: with `--engine jina`, NO request to any reader endpoint is
   made (assert the `_http_get_bytes` spy saw no `r.jina.ai` URL); ladder raises a typed
   error (lite already refuses it too).
2. **TC-04-02 `test_no_remote_disables_tier`** — `--no-remote` + `--engine auto` on a
   blocked public page → remote tier never attempted (`tried` shows `kind="disabled"`).
3. **TC-04-03 `test_no_remote_with_engine_jina_is_local_only`** — `--engine jina --no-remote`
   → behaves local-only; reader never contacted.
4. **TC-04-04 `test_crlf_target_refused`** — a target with `%0d%0a`/raw CRLF → `FetchFailed
   kind="refused"`, no request sent.
5. **TC-04-05 `test_public_target_allowed`** — a normal public target → remote tier IS
   admissible (sanity, no false-positive blocking).
### Regression
- I-3 offline zero-network preserved; existing SSRF tests (`_host_is_public`) green.

## Acceptance Criteria
- [ ] **[R5]** private/internal/unresolvable target never sent to a remote reader (auto + on-demand).
- [ ] **[R5]** `--no-remote` removes the remote tier everywhere; jina/remote become local-only.
- [ ] **[R5]** CRLF/control-char target refused before any network send; target URL-encoded onto the base.
- [ ] Skipped/disabled remote tier recorded in the `tried` trace.
- [ ] No gated master touched.

## Notes
- `tdd-strict`: TC-04-01 + TC-04-04 first.
- Honest scope (unchanged, document, do NOT silently "fix"): DNS-rebinding TOCTOU remains
  (resolve-then-connect) — the guard reduces but cannot fully close it; the Chrome engine
  stays un-hardened. Cross-link KNOWN_ISSUES HTML2MD-4 (updated in 023-07).
- Adversarial roast focus: a redirect from a public target to an internal host on the
  remote hop; IPv6 private ranges; a provider base itself pointing at an internal host
  (operator's risk — note it).
