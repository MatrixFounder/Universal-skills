# VDD Multi-Adversarial Report — TASK 026 (per-domain auth map)

- **Date:** 2026-06-24
- **Target:** `--diff-only` (uncommitted) — `_chrome_auth.py`, `acquire.py`, `cli.py`,
  `tests/test_chrome_auth.py` (+ docs: manual §5b/§3/§8, `.env.example`, `.AGENTS.md`).
- **Critics:** `critic-logic` · `critic-security` · `critic-performance` (parallel, Layer A).
- **Evidence (input):** tests 194→**202** pass (1 skip); `run_audit.py` SECRETS [!!] 2 CRITICAL
  Bearer-Token (acquire.py, test_providers.py) = **confirmed FALSE POSITIVES** (env-sourced
  `Authorization: Bearer {token}` + dummy test fixture); MEDIUM code-patterns in emit.py pre-existing,
  outside diff. e2e + G-1/G-2 gate PASS; `validate_skill` exit 0.
- **Verdict (per --fail-on=none):** **PASS** — all real findings folded + re-verified.

## Convergence
- **critic-performance:** *bikeshedding-only* — no real findings. The map is read twice per
  **process** (validate + resolve, ~50–100µs of stdlib parse) gating a ~1 s browser launch, and the
  second read re-validates `0600` — caching would be a net security loss. No quadratics, unbounded
  caches, leaked handles, or per-request re-parse. TASK 025 `channel="chrome"` probe = synchronous
  binary-resolve, no orphan process.
- **critic-logic + critic-security:** *issues-found* → all resolved. Two findings corroborated across
  both critics (same security domain → merged).

## Findings → resolutions (all folded, re-verified green)
| ID | Sev | Finding | Fix |
|---|---|---|---|
| **F-1** | MED | Map `storage_state` entry NOT hardened (no symlink/0600/existence) unlike the cookies path; loader docstring falsely claimed parity (honest-scope violation) | factored `_assert_secure_credential_file` (symlink/regular-file/0600); applied to the map's `storage_state` at resolve; docstring corrected |
| **F-2** | MED→HIGH | `_registrable` last-2-labels **over-matched** multi-level public suffixes (`s3.amazonaws.com`, `github.io`, `co.uk`) → a credential keyed at a shared apex could route to a **sibling tenant** | replaced eTLD+1 lookup with `_match_host` — **label-boundary domain-suffix** match, most-specific key wins; a key now covers itself + subdomains only, never a sibling. Removed the duplicated `_registrable` from `_chrome_auth` |
| **F-1b** (logic) | MED | Loader accepted an entry with BOTH `cookies_file` + `storage_state` (silent precedence) despite "ONE credential" docstring | reject `len(spec) > 1` |
| **F-2b** (logic) | MED | Duplicate/overlapping keys silently collapsed (last-wins) | reject duplicate normalized host key |
| test gap | — | `HTML2MD_CHROME_AUTH_MAP` not env-cleaned; real env-fallback + map+local-file no-op untested | added to `_ENV`; +8 tests (sibling non-match, own-subdomain match, most-specific wins, both-keys reject, dup-host reject, ss bad-perms reject, real env-fallback, local-file no-op) |

## Confirmed sound (no change)
Engine-forcing scoped correctly (mapped domain ⇒ chrome; unmapped ⇒ normal ladder — a set-and-forget
env map does NOT browser-render every public page); mutual-exclusivity enforced flag-level (argparse
group) AND env-level (`_validate_usage`); map ⊥ `--search` (no session fan-out, TASK 024 S-1/L-1);
SSRF invariants intact after the resolve-signature change + acquire reorder (`_assert_public_http`
before goto, route guard before goto, off-target-redirect refusal); no secrets in logs/errors/trace
(errors sanitized to basename); classic confusables (`evil-x.com`, `x.com.evil.com`, uppercase,
trailing-dot, punycode) all fail closed. Scanner Bearer CRITICALs = false positives.

## Termination
> **VDD Multi-Adversarial complete: Logic ✓ Security ✓ Performance ✓ (iterations: L=1, S=1, P=1; verdict: PASS)**
> Report: docs/reviews/vdd-multi-026.md · 202 tests green, e2e+gate PASS, validate exit 0 · not committed.
