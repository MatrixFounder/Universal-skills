# Task 029.04: Docs (SKILL.md / manual / references) + `.env.example` + full regression + `validate_skill`

**RTM IDs:** R6, R8, R9a, R2c, R10 (e/f — final regression + structural gate)
**Priority:** Medium · **Dependencies:** 029.01–029.03 · **Single pass** (documentation/config — no stub split)

## Use Case Connection
- UC-2: readiness + dependency-discoverability docs (Dependencies block, ASR portability, doctor).
- UC-4: X cookie contract documentation (convention path, auth-map, overrides).

## Task Goal
Document everything the code sub-tasks added, wire the two new env vars into `.env.example`, then run the
full regression suite and the structural validator as the merge gate. This is the "убедись, что всё
работает, ничего не сломано" checkpoint.

## Files to touch
### Edit
- `skills/transcript-fetcher/SKILL.md` — Dependencies block (R6), ASR portability note (R8), X cookie contract (R9a), flags list update.
- `skills/transcript-fetcher/scripts/.env.example` — `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` (R2c) + `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC`.
- `docs/Manuals/transcript-fetcher_manual.md` — flags table: add `--concurrent-fragments`, `--media-timeout-sec`, `doctor`; correct the `--timeout-sec` note (media now has its own budget).
- `skills/transcript-fetcher/references/supported_sources.md` (or `asr_backends.md`) — only if they enumerate flags/exit-7 (check first; edit only if stale).

## Changes Description

### `SKILL.md`  (R6 / R8 / R9a + flags)
- **Dependencies block** (prominent, near the top — e.g. after §2 Capabilities or as a new early section):
  - yt-dlp is **vendored in `scripts/.venv`** — do NOT `which yt-dlp`, `pip install yt-dlp`, or
    `brew install yt-dlp` globally (that is the false-negative that caused the 004 detour).
  - The two canonical probes: `scripts/.venv/bin/python -m yt_dlp --version` and
    `scripts/.venv/bin/python scripts/fetch.py doctor`.
  - Shelling callers (e.g. obsidian-llm-wiki) MUST invoke the venv interpreter, never a `$PATH` `python`.
- **ASR portability note:** backend chain `mw → whisper → whisper.cpp → (opt-in) cloud`; caption-less
  Broadcasts/Spaces REQUIRE ffmpeg + one ASR backend; exit-7 remediation
  (`install_components.py --install-whisper` / `--asr-allow-cloud`); `doctor` surfaces which backends
  resolve BEFORE a long fetch.
- **X cookie contract** (under the X sources / Safety Boundaries auth material): the convention path
  `~/.transcript-fetcher/<host>-cookies.txt` → concretely `x.com-cookies.txt` (Netscape format);
  `auth-map.json` required for any custom filename (e.g. `x-cookies.txt`); `--cookies-file` /
  `--cookies-from-browser` overrides; the auth-failure message now names the refresh path.
- **Flags list** (§4 Script Contract, the `Optional flags:` line at ~L106): add
  `--concurrent-fragments N` (X: parallel HLS fragments, default 8, `1` = serial) and
  `--media-timeout-sec N` (X: media-download budget, separate from `--timeout-sec`); mention the
  `doctor` subcommand.
- Bump the `changelog:` front-matter (a v1.3 entry summarising HLS parallelism + media budget + doctor).

### `scripts/.env.example`  (R2c)
- Add, in a new "Media download (X HLS)" section (near the ASR behaviour block):
  ```
  # ── Media download (X HLS) ──────────────────────────────────────────────────
  # Parallel HLS fragment downloads for X Broadcasts/Spaces (yt-dlp -N). Default 8;
  # 1 = serial. CLI --concurrent-fragments overrides. Clamped to [1, 32].
  # TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS=8
  # Per-attempt budget (seconds) for the X media download ONLY (the metadata probe
  # keeps --timeout-sec). Unset → duration-derived max(600, dur*4), else 1800.
  # CLI --media-timeout-sec overrides.
  # TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC=1800
  ```

### `docs/Manuals/transcript-fetcher_manual.md`
- Flags table (~L175–L183): add rows for `--concurrent-fragments N` (default 8) and
  `--media-timeout-sec N` (default: duration-derived / 1800). Add a `doctor` subcommand row/paragraph.
- Correct the existing `--timeout-sec` note: it no longer implies "the audio download counts against it"
  — the media download now has its own `--media-timeout-sec` budget; `--timeout-sec` gates the
  probe + caption path only.

## Test Cases

### Documentation checks (grep-level, no code)
- **TC-01:** `grep -q "concurrent-fragments" SKILL.md scripts/.env.example docs/Manuals/transcript-fetcher_manual.md`.
- **TC-02:** `grep -q "media-timeout-sec" SKILL.md scripts/.env.example docs/Manuals/transcript-fetcher_manual.md`.
- **TC-03:** `grep -q "doctor" SKILL.md docs/Manuals/transcript-fetcher_manual.md`.
- **TC-04:** SKILL.md contains "vendored" + a warning against `which yt-dlp`.
- **TC-05:** SKILL.md contains `x.com-cookies.txt`.

### Regression (R10 e/f — the merge gate)
- Full suite green: `./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts`
  (expected ≥ 274 + the new TCs, `OK`).
- Structural validator exit 0: `validate_skill.py skills/transcript-fetcher`.
- (Manual, opt-in) live: `TRANSCRIPT_FETCHER_E2E=1` — run `doctor` and a short real X fetch end-to-end.

## Verification
```bash
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/transcript-fetcher   # exit 0
cd skills/transcript-fetcher && grep -l "concurrent-fragments" SKILL.md scripts/.env.example ../../docs/Manuals/transcript-fetcher_manual.md
cd skills/transcript-fetcher && ./scripts/.venv/bin/python scripts/fetch.py doctor          # sanity: exit 0
```
Expected: full suite OK; `validate_skill.py` exits 0; all three docs mention the new flags; `doctor` exits 0.

## Acceptance Criteria
- [ ] SKILL.md has a Dependencies block (vendored yt-dlp, no `which yt-dlp`, two canonical probes, venv contract).
- [ ] SKILL.md has an ASR portability note (backend chain + exit-7 remediation + doctor) and the X cookie contract.
- [ ] SKILL.md flags list + manual flags table include `--concurrent-fragments`, `--media-timeout-sec`, `doctor`; `--timeout-sec` note corrected.
- [ ] `.env.example` documents `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` and `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC`.
- [ ] Full `unittest discover` GREEN; `validate_skill.py skills/transcript-fetcher` exits 0.

## Notes
Do not change code behaviour here. If the validator flags a doc/structure issue, fix the doc — not the
tests. Keep the changelog honest: parallelism is the fix, a bigger timeout is only the safety margin.
</content>
