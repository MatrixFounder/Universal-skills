# VDD Multi-Adversarial Report — TASK 024 (authenticated login-gated Chrome)

- **Date:** 2026-06-23
- **Critics:** `critic-logic` · `critic-security` · `critic-performance` (parallel, Layer A).
- **Evidence (input):** 177 unit tests pass, **proven hermetic** (full suite green with external
  DNS + TCP blocked); `test_e2e.sh` PASS (G-1/G-2 gate); `validate_skill.py` exit 0; no new base
  dep; no `NotImplementedError` stubs remain.
- **Verdict (per --fail-on=none):** **PASS** — no 🔴/🔥; all actionable findings folded in.

## Convergence
- **critic-security:** *bikeshedding-only* — **(a)** the credentialed-render SSRF model is
  **sufficient** (pre-goto `_assert_public_http`; context-level `route` abort of non-public
  navigation/sub-resource/`fetch`/`beacon`, installed before `goto`, covers popups/workers;
  off-target-public-redirect refusal); **(b)** the scanner's 2 "Bearer Token (CWE-798)" CRITICALs
  are **confirmed FALSE POSITIVES** (env-sourced `Authorization: Bearer {JINA_API_KEY/…}` header
  + a dummy `"SEKRET"` test fixture — no hardcoded secret); **(c)** **no real secret leak**
  (files via path/env only, never argv; cookie/state values + Authorization never logged / in
  `--json-errors` / in the `tried` trace; 0600 enforced on load).
- **critic-logic:** *issues-found* → all resolved. Confirmed **fully implemented** (R1–R10 each
  realized) and **no regression** (the `_fetch_chrome_html(url)`→`(url, opts)` change + 5 updated
  fakes are consistent; 023 ladder/search/privacy intact). R10 graceful-degradation traced sound.
- **critic-performance:** *issues-found* → resolved. Route-guard per-host DNS cache correct;
  scroll double-bounded (passes + 60 s wall-clock, never hangs); `input()` isolated to the `login`
  verb; lite/auto path zero added cost.

## Findings → resolutions (all folded, re-verified green + hermetic)
| ID | Sev | Finding | Fix |
|---|---|---|---|
| **L-1** | MED | auth + `--search` set `engine=chrome`, fanning the session over attacker-influenceable search URLs (defeats S-1) | `_validate_usage` now **rejects `--chrome-* + --search`** (Usage/exit 2) + test |
| **P-1** | LOW-MED | chrome `page.content()` had no `--max-bytes` parity (downstream-memory lever) | enforce `--max-bytes` on the rendered body → `FetchFailed kind=max_bytes` + test |
| **INFO-1** | LOW(sec) | `_login_render` chmod was post-write (brief 0644 window) | write `storage_state` under `umask(0o077)` (0600 from creation) |
| **L-2** | LOW | `is_login_wall(opts)` dead param; R5c 3rd signal (selector-absent) unimplemented | dropped `opts`; honest-scope note that the selector-absent signal is **deferred** (needs a DOM parse; weak heuristic risks false positives) |
| **L-3 / INFO-3** | LOW | stale "until 024-02 … no gate" docstring + references SSRF text (now false) | corrected `_fetch_chrome_html` docstring + `references/html-to-markdown.md` to the hardened reality |
| **L-4** | LOW | `_install_chrome_guards(target_reg)` param unused | dropped the param + call site |

## Confirmed sound (no change)
Login flow isolation (`input()` only via the `login` verb); same-site `www`↔apex allowed while
off-target refused; `_registrable` last-2-labels (`co.uk` over-match) documented honest-scope;
DNS-rebind TOCTOU inherited (documented); `_login_render` intentionally skips the off-target
guard (manual SSO to a different eTLD+1 is legitimate). Injection paths clean (CRLF/control
rejected). No ReDoS.

## Termination
> **VDD Multi-Adversarial complete: Logic ✓ Security ✓ Performance ✓ (iterations: L=1, S=1, P=1; verdict: PASS)**
