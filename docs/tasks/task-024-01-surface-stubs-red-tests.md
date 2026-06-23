# Task 024-01 [STUB]: CLI/login surface + `_chrome_auth`/`_cookies` skeletons + RED tests

> **Predecessor:** none (first bead of TASK 024; builds on shipped TASK 023).
> **RTM:** [R1] SSRF surface, [R2] auth surface, [R3] login surface, [R10] non-regression test.
> **ARCH:** §16.2 (flags), §16.7 (interfaces + dispatch), §16.10 (024-01).

## Use Case Connection
- UC-1…UC-5 — freezes the CLI/IR contract every later bead fills. No behaviour yet.

## Task Goal
Freeze the **public surface** (new `--chrome-*` flags + the `login` subcommand + the
`_fetch_chrome_html(url)`→`(url, opts)` signature + `_chrome_auth`/`_cookies` skeletons) and lay
**RED** tests (skipped/`expectedFailure` until their logic bead). Stubs raise `NotImplementedError`.

## Changes Description

### Changes in Existing Files

#### File: `skills/html2md/scripts/html2md/cli.py`
**`build_parser`:** add (a mutually-exclusive group for the three auth sources):
- `--chrome-storage-state PATH` (dest `chrome_storage_state`, default `None`)
- `--chrome-cookies-file PATH` (dest `chrome_cookies_file`)
- `--chrome-user-data-dir DIR` (dest `chrome_user_data_dir`)
- `--chrome-scroll` (store_true) + `--chrome-scroll-passes N` (int, default 8). Also **freeze the
  wall-clock budget as a module constant** `_CHROME_SCROLL_BUDGET_S = 60` in `acquire.py` now
  (internal, deliberately NOT a flag) so 024-05 fills the scroll behaviour behind a frozen number.
Env fallbacks read in `_validate_usage`/resolution: `HTML2MD_CHROME_STORAGE_STATE` /
`_COOKIES_FILE` / `_USER_DATA_DIR`.
**`login` subcommand dispatch — DECIDED: verb-intercept** (NOT `add_subparsers`). The flat parser
has `INPUT`/`OUTPUT_DIR` as `nargs="?"`, so `login URL` would mis-parse as `INPUT="login"`;
therefore `main` checks `argv and argv[0] == "login"` → routes to `_login_main(argv[1:])` (stub
now) **before** building the flat parser, preserving the existing positional contract.
**`_validate_usage`/resolution:** an auth flag (or env) **sets the effective engine to `chrome`**
(so the credential is never silently dropped to lite); missing/unreadable file → `BadInput`
(typed, R10).

#### File: `skills/html2md/scripts/html2md/acquire.py`
- `_fetch_chrome_html(url)` → **`_fetch_chrome_html(url, opts)`** (stub keeps current behaviour
  when `opts` carries no auth — R10); `_tier_chrome` call site updated to pass `opts`.
- Stub `def _login_render(url, save_state_path, opts) -> None: raise NotImplementedError("024-04")`.

### New Files
- `skills/html2md/scripts/html2md/_chrome_auth.py` — `def resolve_context_kwargs(opts) -> dict |
  None` (stub `NotImplementedError("024-03")`); `def is_login_wall(html, final_url, opts) -> bool`
  (stub `024-05`).
- `skills/html2md/scripts/html2md/_cookies.py` — `def load_cookie_jar(path) -> MozillaCookieJar`
  + `def to_playwright_cookies(jar) -> list[dict]` (stub `NotImplementedError("024-04")`).
- `skills/html2md/scripts/html2md/tests/test_chrome_auth.py` — RED tests (skipped per bead).

## Test Cases
### Unit (surface — GREEN now)
1. **TC-01-01** parser accepts all new flags; the three auth sources are mutually exclusive (exit 2).
2. **TC-01-02** an auth flag sets effective engine to `chrome` (resolution result).
3. **TC-01-03 (R10 non-regression)** with NO auth flag + no env, `_resolve_paths`/engine pick is
   identical to TASK 023; a normal local-file convert still works (existing suite stays green).
4. **TC-01-04 (R10)** `--chrome-storage-state /no/such/file` → exit 1 `BadInput` (typed, not traceback).
### Unit (contract — RED, skip→green per bead)
5. **TC-01-05** (→024-02) `_fetch_chrome_html` with a private/off-target redirect is refused.
6. **TC-01-06** (→024-03) `resolve_context_kwargs` builds storage_state/cookies/profile kwargs.
7. **TC-01-07** (→024-04) `load_cookie_jar` rejects `0o077`/symlink; `_login_render` mints state.
8. **TC-01-08** (→024-05) `is_login_wall` detects a stale-session wall → `auth_required`.
### Regression
- Full `html2md/tests` suite green (new flags/fields additive; default path unchanged).

## Acceptance Criteria
- [ ] **[R1/R2/R3]** all new flags + `login` verb parse; auth sources mutually exclusive.
- [ ] **[R10]** no-auth default path byte-identical to TASK 023; missing file → typed `BadInput`.
- [ ] Stubs exist with the exact signatures above (raise `NotImplementedError`).
- [ ] RED tests written (skipped with their greening bead); existing suite green.
- [ ] No gated master touched; `bash scripts/tests/test_e2e.sh` (suite + G-1/G-2) PASS.

## Notes
- Keep `_fetch_chrome_html` behaviour identical when `opts` has no auth — R10 is the contract.
- Decide & document the `login`-dispatch shape now so 024-04 doesn't re-derive it.
