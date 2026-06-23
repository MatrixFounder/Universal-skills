# Task 024-04 [LOGIC]: `login` mint helper + hardened cookie loader

> **Predecessor:** 024-03 (context builder consumes what this mints/loads).
> **RTM:** [R3] session minting, [R7] credential file security. **Methodology:** `tdd-strict`.
> **ARCH:** §16.3 (mint), §16.8 (security).

## Use Case Connection
- UC-1 (mint locally → use), UC-2 (mint → deploy to Hermes).

## Task Goal
Provide the ONE interactive step to produce a `storage_state.json` (headful, local), and a
hardened Netscape-`cookies.txt` loader → Playwright cookie dicts, with strict credential-file
handling.

## Changes Description

### File: `skills/html2md/scripts/html2md/cli.py` (+ `acquire._login_render`)
- `login URL [--save-state out.json]` (dispatch shape frozen in 024-01): **headful** Chromium
  (`launch(headless=False)`), `goto(URL)`, **block on stdin** ("press Enter when logged in"),
  then `context.storage_state(path=out.json)`; **`os.chmod(out.json, 0o600)`**.
- Default `out.json` under `./` (documented); never echo cookie/state contents.
- The mint helper is the ONLY headful path; runtime stays headless.

### File: `skills/html2md/scripts/html2md/_cookies.py`
- `load_cookie_jar(path) -> MozillaCookieJar` — **lift the file-hardening half** of
  `transcript-fetcher/scripts/sources/_cookies.py`: reject symlink (`Path.is_symlink`); **reject
  group- AND world-accessible** (`st_mode & 0o077` → error "tighten to 0600" — *tighter* than the
  source's world-only check, an **intentional server-threat-model divergence**; add a tracking
  note vs the source, do not silently fork); `jar.load(ignore_discard=True, ignore_expires=True)`;
  sanitize parse errors so no file-content/line snippets leak.
- `to_playwright_cookies(jar) -> list[dict]` — **new html2md code**: convert each cookie to
  `{name, value, domain, path, expires, secure, httpOnly:False, sameSite:"Lax"}`.

## Test Cases
### Unit (offline)
1. **TC-04-01 (`tdd-strict`, write first)** a `0o640`/`0o644`/`0o660` cookies file → rejected
   (`0o077` mask); a symlink → rejected; a `0o600` file → loads.
2. **TC-04-02 (`tdd-strict`, write first)** a malformed cookies file → sanitized error with NO
   file-content/line snippet in the message.
3. **TC-04-03** `to_playwright_cookies` maps Netscape rows → correct dicts (domain/path/secure/expires).
4. **TC-04-04** `login` mint (Playwright seam mocked) writes a `storage_state` JSON and chmods 0600;
   no cookie/state value appears on stdout/stderr.
5. **TC-04-05 (R10)** `--chrome-cookies-file /missing` → typed `BadInput` (not traceback).
### Regression
- Full suite; offline I-3 (no network for file ops) preserved.

## Acceptance Criteria
- [ ] **[R3]** `login` writes a 0600 `storage_state.json` via a headful browser; runtime headless.
- [ ] **[R7]** loader rejects `0o077` (group+world) + symlink; sanitized errors; secrets never on argv/stdout/logs.
- [ ] **[R7]** `to_playwright_cookies` is correct (domain/path/secure scoping preserved for the browser).
- [ ] tracking note recorded: `_cookies.py` lifted (file-hardening only) from transcript-fetcher, NOT gated, do-not-fork.
- [ ] No gated master touched.

## Notes
- `tdd-strict`: TC-04-01 + TC-04-02 FIRST (perm rejection + no-leak) — credential-file handling
  is the security boundary here.
- Adversarial roast focus: TOCTOU on the perm check; symlink to a 0600 target; stdlib LoadError
  echoing file lines; chmod race on mint output; cookie value leaking via an exception repr.
