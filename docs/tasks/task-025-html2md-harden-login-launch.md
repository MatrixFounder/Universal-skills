# TASK 025 — `html2md`: [LIGHT] harden the `login` mint launch (real Chrome channel + de-automation)

**Status:** 🟢 LIGHT — dev in progress.
**Skill:** `html2md` (Proprietary). Touches only html2md-**owned** `acquire.py` + its tests —
no `diff -q`-gated master, so G-1/G-2/G-3 stay green. **No new dependency** (Playwright already
optional; `channel="chrome"` reuses the user's *system* Chrome when present).
**Mode:** Light (trivial, low-risk; no architecture/API change).
**Predecessor:** TASK 024 (authenticated login-gated Chrome — SHIPPED & archived,
`docs/tasks/task-024-html2md-authenticated-chrome.md`).

---

## 0. Meta Information

- **Task ID:** 025
- **Slug:** `html2md-harden-login-launch`
- **Driver (user, 2026-06-23):** the `login` mint window (and headless render) launches
  **bundled Chromium under CDP automation** (`navigator.webdriver === true`), so a first-party
  login is refused as an "automated browser" — Google OAuth shows *«этот браузер или приложение
  небезопасны»* and X serves *"JavaScript is not available"*. The user reported Google SSO
  blocking the `login` flow on `x.com`.

---

## 1. Problem & Scope

`_login_render` and `_fetch_chrome_html` call `pw.chromium.launch(...)` with **bundled
Chromium** and the default automation fingerprint. Two consequences:

1. **Mint (`login`) UX:** native logins (X email/password, most SSO-free sites) are flagged as
   bot traffic. *(Google OAuth is intentionally hard to satisfy and is out of scope to "beat" —
   see Non-goals.)*
2. **Render:** authed X reads can hit the `"javascript is not available"` wall (`is_login_wall`
   marker) because the webdriver flag is detected.

**Fix (minimal):** launch preferring the **real system Chrome channel** (`channel="chrome"`) with
the automation signal suppressed (`--disable-blink-features=AutomationControlled` +
`navigator.webdriver` mask), and **fall back to bundled Chromium** when system Chrome is absent —
never a hard failure (R10 parity).

## 2. Requirements (RTM)

| ID | Requirement | Verify |
|---|---|---|
| **R1** | Mint + render prefer `channel="chrome"`; fall back to bundled Chromium if unavailable (no crash, no new install requirement) | unit: channel-then-fallback |
| **R2** | Launch passes `--disable-blink-features=AutomationControlled`; context masks `navigator.webdriver` | unit: arg + init-script asserted |
| **R3** | All TASK 024 security invariants intact — pre-`goto` SSRF gate, route guard, off-target-redirect refusal, `--max-bytes`, 0600 mint, stale→`auth_required` | existing 32 chrome tests stay green |
| **R4** | Docs state plainly: Google SSO may still be blocked → use **email/password** or **cookie export** (`--chrome-cookies-file`) | manual §5b + KNOWN_ISSUES HTML2MD-10 |

## 3. Non-goals

- **Not** beating Google's OAuth bot-detection (an arms race; cookie export is the sanctioned
  path). No fingerprint spoofing beyond the standard de-automation flag + webdriver mask.
- No change to the SSRF gate, credential storage (0600/env/argv rules), or the ladder.

## 4. Acceptance

- New unit tests for R1/R2 pass; the existing 32 chrome/auth tests stay green.
- `bash tests/test_e2e.sh` (suite + G-1/G-2 gate) PASS; `validate_skill.py` exit 0.
- **No auto-commit** (user's standing preference — commit is the user's decision).

## 8. As-built (2026-06-23)

Shipped in [acquire.py](../skills/html2md/scripts/html2md/acquire.py) + its tests only (no master
touched; G-1/G-2/G-3 green). **180 tests** (177 + 3 new), e2e + replication gate PASS,
`validate_skill` exit 0. No new dependency.

- **`_launch_chrome_browser(pw, headless)` / `_launch_chrome_persistent(pw, headless, kwargs)`** —
  prefer `channel="chrome"` (real system Chrome) + `_CHROME_LAUNCH_ARGS`
  (`--disable-blink-features=AutomationControlled`); `except → bundled Chromium` fallback (R1/R10).
- **`_WEBDRIVER_MASK_JS`** added to every context via `context.add_init_script(...)` in both
  `_login_render` and `_fetch_chrome_html` (R2).
- **R3 intact:** the pre-`goto` SSRF gate, route guard, off-target-redirect refusal, `--max-bytes`,
  0600 mint, and stale→`auth_required` are untouched — all 32 prior chrome/auth tests stay green.
- **R4 docs:** manual §5b gained a "Google SSO is blocked → email/password or cookie export"
  callout + the de-automation note; KNOWN_ISSUES HTML2MD-10 residual (f) records the Google-OAuth
  limit + the cookie-export sanctioned path; `.AGENTS.md` updated.
- **Tests added:** `TestLoginMint.test_mint_prefers_chrome_channel_and_masks_webdriver`,
  `TestChromeLaunchHardening.{test_render_prefers_chrome_channel_and_masks_webdriver,
  test_render_falls_back_to_bundled_when_channel_missing}`.

**Honest scope:** Google OAuth bot-detection is **not** defeated (by design — non-goal). The de-automation
helps native logins + authed renders; Google-SSO accounts use cookie export.
