# Task 024-06 [INTEGRATION]: docs + Hermes deploy + Jina-key matrix + gates + dogfood

> **Predecessor:** 024-01…05 (all logic landed).
> **RTM:** [R5] remote/Hermes docs, [R6] Jina-key strategy, [R8] tests/docs/fork-free, [R10] no-auth suite green.
> **ARCH:** §16.5, §16.6, §16.9; CLAUDE.md §2.

## Use Case Connection
- UC-2 (Hermes deploy), UC-5 (jina key) — the user-facing docs + the gates that prove no fork /
  no new dep / no regression.

## Task Goal
Document the authenticated-Chrome flow + the **server/Hermes deployment model** + the
**Jina-key matrix**, prove the replication gate + no-new-dep + the **R10 non-regression**, and
dogfood mint→render on a real authed X Article.

## Changes Description

### File: `skills/html2md/SKILL.md`
- §2 Capabilities: authenticated Chrome (`--chrome-storage-state`/`--chrome-cookies-file`/
  `--chrome-user-data-dir`), `login` subcommand, `--chrome-scroll`; note **auth is opt-in /
  additive (R10)**.
- §4 Script Contract: new flags + env (`HTML2MD_CHROME_*`) + the `login` verb + `auth_required`
  classification + `offsite_redirect` kind.
- §5 Safety: the chrome SSRF gate, host-scoping, secret handling (0600, file/env-only), honest
  scope (DNS-rebind, localStorage).

### File: `skills/html2md/references/html-to-markdown.md`
- A **server / Hermes deploy** section: `login` (mint, headful, local) → deploy `storage_state`
  as a 0600 secret (`HTML2MD_CHROME_STORAGE_STATE`) → headless consume; **concurrency-safe**
  (read-only state; persistent-profile is single-concurrency/local-only); rotation = re-mint +
  redeploy; **self-hosted-Jina synergy** (`HTML2MD_READER_URL` in-network → no 3rd-party egress).
- A **Jina-key matrix** (R6): `JINA_API_KEY` env-only, keyless-vs-keyed quota; auth'd content →
  local chrome-auth (never ship a live session to jina); anti-bot non-auth / server volume →
  keyed jina or self-hosted reader; `x-set-cookie` deferred.

### File: `docs/KNOWN_ISSUES.md`
- New HTML2MD entry: authenticated Chrome honest-scope (DNS-rebind TOCTOU inherited; localStorage
  origin-restored; login-wall heuristic best-effort/per-site; persistent-profile single-concurrency;
  2FA/expiry → re-mint). Note the chrome tier is now SSRF-gated (supersedes the old HTML2MD-4 note
  for the auth path).

### File: `docs/office-skills-backlog.md` §2 «html2md»
- Record TASK 024 shipped (authed chrome + Hermes-deploy + jina-key matrix) + R9 deferrals.

### Verification only (no master edits)
- `bash skills/html2md/scripts/tests/test_e2e.sh` → suite + **G-1/G-2 `diff -q` gate** PASS
  (assert `acquire.py`/`cli.py`/`_chrome_auth.py`/`_cookies.py` NOT in the gate).
- docx masters vs HEAD byte-identical (G-3).
- `validate_skill.py skills/html2md` exit 0.
- `git diff --stat -- skills/html2md/scripts/requirements.txt` → **no change** (Chrome is the
  existing soft-optional extra).

## Test Cases
### Integration / Gates
1. **TC-06-01** `test_e2e.sh` PASS (suite + G-1/G-2).
2. **TC-06-02** docx no-drift (G-3) byte-identical.
3. **TC-06-03** `validate_skill.py` exit 0.
4. **TC-06-04 (R10)** full suite green with NO auth/keys configured; `--engine auto` identical to TASK 023.
5. **TC-06-05** no new base-`requirements.txt` line.
### Dogfood (opt-in, network — recorded, not CI-gated)
6. **DF-1** `html2md.py login https://x.com --save-state ~/.html2md/x.json` (headful) →
   `html2md.py "https://x.com/i/article/<id>" out/ --engine chrome --chrome-storage-state ~/.html2md/x.json`
   → full article (not a login wall); `engine: chrome`.
7. **DF-2** the same with `--chrome-scroll` on a reply-heavy status → replies present.
8. **DF-3** stale state → `auth_required` (not logged-out content).

## Acceptance Criteria
- [ ] **[R5/R6]** SKILL.md + references updated: Hermes deploy model + Jina-key matrix.
- [ ] **[R8]** G-1/G-2 silent; docx G-3 byte-identical; `validate_skill.py` exit 0; no new base dep.
- [ ] **[R10]** full no-auth suite green; `auto` identical to TASK 023.
- [ ] KNOWN_ISSUES + backlog updated; dogfood DF-1/2/3 demonstrate mint→render, scroll, staleness.

## Notes
- Docs + gates only — zero logic change; a gate regression here means a prior bead touched a
  gated file (investigate immediately).
- Final `/vdd-multi` adversarial pass over the whole TASK 024 diff before "done"; **no auto-commit**.
