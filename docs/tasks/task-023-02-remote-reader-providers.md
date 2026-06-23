# Task 023-02 [LOGIC]: vendor-agnostic RemoteReader provider layer

> **Predecessor:** 023-01 (frozen surface + `_RemoteReader`/stubs).
> **RTM:** [R2] vendor-agnostic remote-reader provider layer. (Feeds [R1]/[R3] in 023-03.)
> **ARCH:** §15.3 (provider abstraction), §15.5 (env), §15.8 D-23-B.

## Use Case Connection
- UC-3 (vendor-agnostic / self-hosted reader); enables UC-1/UC-2 (the remote tier).

## Task Goal
Implement the pluggable remote-reader provider layer: build the ordered provider list
from env (with `jina` as the default), and construct each provider's request URL +
headers. Resilience must not depend on a single vendor.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py`

**Function `_remote_providers(opts) -> list[_RemoteReader]`:**
- Order: if `HTML2MD_READER_PROVIDERS` set (comma/space list of base URLs) → that order;
  else `HTML2MD_READER_URL` (single base, if set) **then** the built-in
  `jina` (`https://r.jina.ai/`). De-dup by base.
- Token per provider: `HTML2MD_READER_TOKEN` for the generic base; `JINA_API_KEY` for jina.
- Name = host of the base (`remote:<host>`), except the built-in is `jina`.

**Function `_build_reader_request(provider, target, opts) -> tuple[str, dict]`:**
- URL = `provider.base + target` (literal concat — Jina's `r.jina.ai/https://…`
  convention), with the **target URL-encoded enough to be safe** (defer the full CRLF/
  injection guard to 023-04, but already `quote` the target's unsafe chars here).
- Headers: `X-Return-Format: <opts.remote_format or "html">`; `Authorization: Bearer
  <token>` when `provider.token`. (`X-Target-Selector` is added in 023-05.)
- Returns `(reader_url, headers)`.

**Refactor `_fetch_jina_html`:** re-express as the `jina` provider going through
`_build_reader_request` + `_http_get_bytes` (preserve current behaviour: keyless +
`JINA_API_KEY`, `X-Return-Format: html`). Keep the public name as a thin wrapper if any
test imports it.

## Test Cases
### Unit (offline)
1. **TC-02-01 `test_provider_order_default`** — no env → `[jina]`.
2. **TC-02-02 `test_provider_order_env`** — `HTML2MD_READER_URL=https://r.internal/` →
   `[remote:r.internal, jina]`; `HTML2MD_READER_PROVIDERS="https://a/ https://b/"` →
   `[a, b]` (jina NOT appended when an explicit list is given).
3. **TC-02-03 `test_build_reader_request_jina`** — `_build_reader_request(jina,
   "https://x.com/p", opts)` → url `https://r.jina.ai/https://x.com/p`,
   header `X-Return-Format: html`; with `JINA_API_KEY` set → `Authorization` present.
4. **TC-02-04 `test_build_reader_request_generic_token`** — generic base + `HTML2MD_READER_TOKEN`
   → `Authorization: Bearer …`.
5. **TC-02-05 `test_jina_wrapper_unchanged`** — the old `_fetch_jina_html` path (mocked
   `_http_get_bytes`) still returns decoded HTML (no behaviour regression).
### Regression
- Full `html2md/tests` suite; `--engine jina` still works end-to-end (mocked).

## Acceptance Criteria
- [ ] **[R2]** providers built from env with `jina` default; ordering rules honoured.
- [ ] **[R2]** `_build_reader_request` produces correct URL+headers per provider.
- [ ] Existing `--engine jina` behaviour preserved (TC-02-05).
- [ ] No gated master touched.

## Notes
- This bead is provider **construction** only — the ladder/fall-through is 023-03, the
  hard injection guard is 023-04. Keep the two concerns separate (SRP).
- Adversarial roast focus: env parsing edge cases (empty list, trailing comma, base
  without trailing slash), token leakage in any error message (reuse `_redact`).
