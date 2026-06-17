# Task 022-06 [LOGIC]: `acquire.py` URL path — httpx+trafilatura lite + Chrome fallback + SSRF caps

> **Predecessor:** 022-02 (`acquire` offline + dispatch), 022-05 (emit pipeline).
> **RTM:** [R1a] lite URL fetch + metadata, [R1b] Chrome fallback. Implements §7 fetch security.
> **ARCH:** §2.1 (FC-1 url), §6 (stack), §7 (SSRF/DoS), §8 (perf), §13 OQ-2 (auto heuristic), §11 (022-06).

## Use Case Connection
- UC-1 (clip a live URL), UC-4 (JS/SPA via Chrome). Completes the only
  network-touching component.

## Task Goal
Fill the `mode="url"` branch of `acquire`: fetch via `httpx`+`trafilatura`
(lite, default), auto-fallback to Playwright/Chrome for JS/SPA shells, with
SSRF/DoS bounds. Supply the live-image resolver hook that 022-05's emit uses.

## Changes Description
### `html2md/acquire.py` (url branch)
- **lite path** (`--engine lite|auto`): `httpx.get(url, timeout, follow_redirects,
  headers={UA})` with `--max-bytes` cap (stream + abort over limit); `trafilatura`
  extracts main article + `metadata` (`title/date/author`) → `source_meta`;
  `acq.html` = extracted article HTML (or raw HTML if extraction empty);
  `images` left empty (resolved lazily at download time).
- **auto-fallback** (`--engine auto`): if the lite body is empty / near-empty /
  JS-shell (heuristic OQ-2: extracted text < threshold OR `<script>`-bundle ≥
  threshold with no article) → invoke chrome path.
- **chrome path** (`--engine chrome` or auto-fallback): lazy-import Playwright;
  absent → `EngineNotInstalled` (exit 3) with remediation
  (`install.sh --with-chrome`). Reuse the **html2md-owned** fetch hardening
  adapted from pdf's `chrome_engine.py` (D-7, owned fork — NOT a gated replica):
  block beacons, render, return hydrated DOM HTML.
- **SSRF guards (§7):** refuse non-`http(s)` top-level fetch schemes; `--max-bytes`
  enforced; request timeout; no credential forwarding; unreachable/blocked →
  `FetchFailed` (exit 10).
- **`acquire._resolve_url_image(url, opts) -> bytes|None`** — the live-fetch
  resolver hook 022-05's emit calls when `mode=url` and `--download-images`:
  bounded `httpx.get` per image (`--max-images`, `--max-bytes`), sha1 returned.

### `skills/html2md/scripts/requirements.txt` — add `httpx`, `trafilatura`.
### `skills/html2md/scripts/requirements-chrome.txt` — `playwright` (soft-optional).

## Test Cases
### Unit (network mocked — no real egress in CI)
1. **TC-06-01 `test_lite_fetch_and_metadata`** — mocked `httpx` returns a fixture
   article; `trafilatura` yields body + `title/date/author` → `source_meta` set.
2. **TC-06-02 `test_auto_fallback_on_empty_body`** — mocked lite returns JS-shell
   (empty extracted text) → chrome path invoked (chrome itself mocked).
3. **TC-06-03 `test_chrome_absent_envelope`** — `--engine chrome`, Playwright not
   importable → exit 3 `EngineNotInstalled` with remediation text.
4. **TC-06-04 (§7) `test_ssrf_scheme_and_maxbytes`** — `file://`/`gopher://` top-
   level URL refused; oversized mocked response aborted at `--max-bytes` →
   `FetchFailed` (10).
5. **TC-06-05 `test_fetch_failure_exit10`** — mocked connection error → exit 10.
### E2E (offline/mocked + 1 opt-in live, engine-gated)
6. **TC-E2E-06** mocked URL → `out/<slug>.md` + `.reader.md` + downloaded
   `_attachments/*`; `--no-download-images` keeps URLs. (A real-network dogfood
   is engine/host-gated, recorded in 022-07.)

## Acceptance Criteria
- [ ] **[R1a]** lite `httpx`+`trafilatura` fetch + `title/date/author` metadata.
- [ ] **[R1b]** `auto` fallback to Chrome on JS-shell; `--engine chrome` explicit.
- [ ] Chrome absent → exit 3 `EngineNotInstalled` (graceful, no traceback).
- [ ] **§7**: non-http(s) refused; `--max-bytes`/`--max-images` enforced;
      fetch failure → exit 10.
- [ ] url-image resolver supplies bytes to 022-05's emit (download path works).
- [ ] `httpx`/`trafilatura` in base reqs; `playwright` in `requirements-chrome.txt`.

## Notes
- The Chrome fetch code is **html2md-owned** (D-7) — fetch semantics differ from
  pdf's render-only `goto`; it is NOT under the `diff -q` gate.
- Adversarial roast focus: SSRF (redirect to internal IP, DNS rebinding caveat —
  document as honest scope if unmitigated), unbounded download, secret leakage in
  envelopes.
