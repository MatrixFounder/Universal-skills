# Task 023-07 [INTEGRATION+DOC]: docs, packaging, fork-free gates, dogfood

> **Predecessor:** 023-01…06 (all logic landed).
> **RTM:** [R7] tests/coverage rollup, [R8] docs / packaging / fork-free integrity.
> **ARCH:** §15.7 (fork-free), §15.9 (023-07); CLAUDE.md §2 (replication).

## Use Case Connection
- All UCs — the user-facing docs + the gate that proves no fork / no new dep.

## Task Goal
Document the new engine ladder, vendor-agnostic providers, privacy posture, and search;
prove the two-master replication gate is untouched; confirm `validate_skill.py` passes and
no new dependency was added; dogfood the real recovery + fallback + search paths.

## Changes Description

### File: `skills/html2md/SKILL.md`
- §2 Capabilities: describe the fallback ladder (`auto` local-first → remote last-resort;
  `--engine jina|remote` remote-first → local fallback; one typed error only when
  exhausted), vendor-agnostic providers (`HTML2MD_READER_URL`/`_PROVIDERS`, self-hosted),
  `--remote-format markdown`, `--target-selector`, and `--search`/`--max-results`.
- §4 Script Contract: add the new flags + env vars + the `all_engines_failed` kind + the
  `details.tried` trace.
- §5 Safety Boundaries: state the auto-escalation **URL-leaves-machine** posture +
  `--no-remote`; the target public-IP gate before remote; injection guard.

### File: `skills/html2md/references/html-to-markdown.md`
- Update the decision tree + engine table for the ladder + remote tier + search; add a
  "Provider configuration" + "Privacy" subsection.

### File: `docs/KNOWN_ISSUES.md`
- **HTML2MD-1** (Cloudflare/anti-bot): now **auto-recovers** via the remote-tier escalation
  (note residual: still needs a reachable reader / chrome; `--no-remote` opts out).
- **HTML2MD-6** (`--engine jina` sends URL externally): broaden to "remote tier"; note
  auto-escalation default for public targets + `--no-remote` + the target public-IP gate.
- Add a short note that the remote tier is vendor-agnostic + has a fallback (the headline fix).

### File: `docs/office-skills-backlog.md` §2 «html2md»
- Record TASK 023 shipped (ladder + vendor-agnostic remote + search) and what stays
  deferred (R10: VLM alt-text, cookie auth, screenshots, links-summary).

### Verification only (no master edits)
- `bash skills/html2md/scripts/tests/test_e2e.sh` → suite + **G-1/G-2 `diff -q` gate** PASS
  (assert `acquire.py`/`cli.py`/`model.py`/`emit.py` are NOT in the gate — only
  `web_clean/*`, `html2md_core.js`, `_errors.py`, `_venv_bootstrap.py` are).
- `diff` docx masters vs HEAD → byte-identical (G-3).
- `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/html2md` → exit 0.
- `git diff --stat skills/html2md/scripts/requirements.txt` → **no change** (no new dep).

## Test Cases
### Integration / Gates
1. **TC-07-01 `test_e2e.sh` PASS** — full html2md suite + G-1/G-2 gate green.
2. **TC-07-02 docx no-drift (G-3)** — docx `test_e2e.sh`/battery byte-identical to HEAD.
3. **TC-07-03 validate_skill exit 0**.
4. **TC-07-04 no-new-dep** — `requirements.txt` unchanged vs HEAD.
### Dogfood (opt-in, network — recorded, not CI-gated)
5. **DF-1** an anti-bot URL (e.g. ssrn/researchgate) on `--engine auto` → recovered via the
   remote tier (`engine` startswith `jina`/`remote`).
6. **DF-2** `--engine jina` with the reader forced-unreachable (e.g. bogus
   `HTML2MD_READER_PROVIDERS`) → falls back to lite, exit 0.
7. **DF-3** `--search "some query" out/ --max-results 3` → 3 notes with `query:` frontmatter.

## Acceptance Criteria
- [ ] **[R8]** `SKILL.md` + `references/` + `KNOWN_ISSUES` + backlog updated for the ladder/providers/privacy/search.
- [ ] **[R8]** G-1/G-2 `diff -q` silent; docx G-3 byte-identical (no master touched).
- [ ] **[R8]** `validate_skill.py skills/html2md` exit 0; `requirements.txt` unchanged (no new dep).
- [ ] **[R7]** full suite green (incl. the new ladder/provider/search/privacy tests + the previously-untested jina path).
- [ ] **[R8]** dogfood DF-1/DF-2/DF-3 demonstrate auto-escalation, Jina-failure fallback, and search.

## Notes
- This bead writes only docs + runs gates — **zero** logic change, so a regression here means
  a prior bead touched a gated file (investigate immediately).
- Final `/vdd-multi` adversarial pass over the whole TASK 023 diff before "done"; **no
  auto-commit**.
