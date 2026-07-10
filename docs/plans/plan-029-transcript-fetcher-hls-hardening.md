# Development Plan — TASK 029: `transcript-fetcher` HLS hardening + `doctor` (spec S1–S6)

**Task:** 029 · **Slug:** `transcript-fetcher-hls-hardening` · **Mode:** VDD-Enhanced
**Source of truth:** [`docs/TASK.md`](TASK.md) (RTM R1–R10) ·
[`docs/architectures/architecture-016-transcript-fetcher-x-asr.md` §10](architectures/architecture-016-transcript-fetcher-x-asr.md) ·
[`docs/transcript-fetcher-skill-improvement-spec.md`](transcript-fetcher-skill-improvement-spec.md)
**Affected surface:** `skills/transcript-fetcher/scripts/` only —
`sources/_ytdlp_media.py`, `sources/x.py`, `sources/_stat.py`, `fetch.py`, `_config.py`,
`install_components.py`, `tests/`, plus `SKILL.md` / `scripts/.env.example` / manual.
**No office-skills replication units are touched** (no `diff -q` gate applies).

---

## 0. Strategy (Stub-First, 4 atomic sub-tasks)

Every functional sub-task runs in **two stages**: **Stage A** creates signatures,
constants, CLI flags wired to stub values, and RED (failing/skipped) tests; **Stage B**
replaces the stubs with real logic and turns the tests GREEN. Docs/regression (029.04) is a
single pass (config/documentation task — no stub split, per `planning-decision-tree` §1).

Dependency order: **029.01 → 029.02 → 029.03 → 029.04** (029.02 consumes the
`_ytdlp_media`/`_config` core from 029.01; 029.03 is independent of 029.02 but scheduled after
it to keep `fetch.py` edits serialized; 029.04 documents/verifies everything).

---

## 1. RTM Coverage Checklist (one item per RTM ID — literal `[Rn]` tokens)

> Gate: each of `[R1]`…`[R10]` appears below as a checklist item **starting** with its RTM ID,
> mapped 1:1 from [`docs/TASK.md`](TASK.md). "Impl in" = the atomic sub-task(s) that satisfy it.

- [ ] **[R1]** Parallel HLS fragment download — `download_audio(concurrent_fragments=…)` param,
  `DEFAULT_CONCURRENT_FRAGMENTS = 8` module constant, argv always gains `--concurrent-fragments <N>`
  on the media argv, `N` clamped to `[1, 32]`, caption/subtitle argv paths unchanged.
  *Impl in:* **029.01** (Stage A signatures/constant; Stage B argv + clamp).
- [ ] **[R2]** Config knob `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` — `_config.concurrent_fragments()`
  typed accessor (env/`.env`, default 8), malformed/non-positive → default (never crash);
  documented in `scripts/.env.example` (R2c → **029.04**).
  *Impl in:* **029.01** (accessor + tests); **029.04** (`.env.example`).
- [ ] **[R3]** CLI flag `--concurrent-fragments N` on `fetch.py` — argparse flag (default `None` →
  config → 8), `<= 0` → UsageError exit 2, forwarded `_fetch_one` → `fetch_x_transcript` →
  `download_audio`, `--concurrent-fragments 1` reproduces serial argv (literal `1`).
  *Impl in:* **029.02**.
- [ ] **[R4]** Media-aware download timeout — pure helper `media_timeout_for(duration_s)` +
  `_config.media_timeout_sec()` accessor (**029.01**); `--media-timeout-sec N` CLI flag (`<= 0` →
  exit 2) + budget resolution (CLI > env > helper) computed once in `x.py` and passed **only** to
  `download_audio`; probe/caption keep the `--timeout-sec` budget (**029.02**).
  *Impl in:* **029.01** (helper + accessor); **029.02** (CLI flag + x.py wiring).
- [ ] **[R5]** Doctor entrypoint — `fetch.py doctor [--json]` positional subcommand dispatched
  before argparse, reuses `install_components._components()`, reports interpreter/in-venv/yt-dlp
  version (`importlib.metadata`)/ffmpeg/ASR backends/cloud opt-in, exit 0 (yt-dlp present) / 7
  (absent), stable JSON envelope `{v, interpreter, in_venv, ready, components, remediation}`;
  refactor `install_components._have_yt_dlp()` to `importlib.metadata.version("yt-dlp")`.
  *Impl in:* **029.03**.
- [ ] **[R6]** Dependency-discoverability docs — SKILL.md "Dependencies" block (vendored yt-dlp,
  never `which yt-dlp`/global install; the two canonical probes; venv-interpreter contract for
  shelling callers).
  *Impl in:* **029.04**.
- [ ] **[R7]** Retryable + actionable timeout error — `classify_failure()` `"transient"` category
  scoped ONLY to `"timeout downloading audio"` (probe timeout NOT transient); `_raise_for_failure`
  maps transient → `TranscriptFetchError` with `remediation` attr naming `--concurrent-fragments`
  and `--media-timeout-sec`; `TranscriptFetchError` gains optional `remediation` (mirrors
  `MissingDependencyError`); `fetch.py` surfaces `details.remediation` in single-URL AND batch
  (explicit `except TranscriptFetchError` before the generic handler); exit codes unchanged (3/4).
  *Impl in:* **029.02**.
- [ ] **[R8]** ASR portability + exit-7 docs — SKILL.md "ASR portability" note (backend chain
  `mw → whisper → whisper.cpp → (opt-in) cloud`; caption-less Broadcasts/Spaces require ffmpeg +
  one backend; exit-7 remediation; `doctor` surfaces which backends resolve before a long fetch).
  *Impl in:* **029.04** (doctor mechanism from **029.03**).
- [ ] **[R9]** Explicit X cookie contract — SKILL.md documents the convention path
  `~/.transcript-fetcher/<host>-cookies.txt` (`x.com-cookies.txt`, Netscape), `auth-map.json` for
  custom names, `--cookies-file`/`--cookies-from-browser` overrides (R9a → **029.04**); the X
  auth-failure message names the cookie **refresh** path — the resolved file when one was used,
  else the convention path to create (R9b → **029.02**).
  *Impl in:* **029.02** (R9b message); **029.04** (R9a docs).
- [ ] **[R10]** Tests + regression safety — offline unit coverage per R1–R9 (argv/clamp in 029.01;
  media-vs-probe split + `media_timeout_for` table in 029.01/029.02; doctor exit codes + JSON shape
  + no-heavy-imports in 029.03; remediation strings in 029.02); full `unittest discover` green +
  `validate_skill.py skills/transcript-fetcher` exit 0 (final gate in **029.04**).
  *Impl in:* all sub-tasks; final regression gate in **029.04**.

---

## 2. Task Execution Sequence

### Stage 1 — Core (config + shared yt-dlp plumbing)

- **Task 029.01** — Config knobs + `_ytdlp_media` parallel-download & media-timeout core
  - RTM: **R1**, **R2** (accessor), **R4** (pure helper + accessor), **R10** (a/b unit tests)
  - Description File: [`docs/tasks/task-029-01-config-ytdlp-core.md`](tasks/task-029-01-config-ytdlp-core.md)
  - Priority: Critical · Dependencies: none
  - Stage A: `DEFAULT_CONCURRENT_FRAGMENTS`, `download_audio(concurrent_fragments=None)` param,
    `media_timeout_for()` + `_config.concurrent_fragments()` / `media_timeout_sec()` stubs + RED tests.
  - Stage B: argv `--concurrent-fragments <clamp>`, `media_timeout_for` formula, accessor fallbacks; GREEN.

### Stage 2 — Wiring (x.py + fetch.py + _stat.py)

- **Task 029.02** — X media-budget wiring + transient/auth remediation + CLI flags & validation
  - RTM: **R3**, **R4** (CLI + x.py resolution), **R7**, **R9b**, **R10** (d remediation tests)
  - Description File: [`docs/tasks/task-029-02-x-fetch-wiring-remediation.md`](tasks/task-029-02-x-fetch-wiring-remediation.md)
  - Priority: High · Dependencies: **029.01**
  - Stage A: CLI flags `--concurrent-fragments`/`--media-timeout-sec` (validation), `fetch_x_transcript`
    + `_raise_for_failure` signatures, `classify_failure` `"transient"` branch, `TranscriptFetchError.remediation`;
    RED tests.
  - Stage B: budget resolution in `x.py`, forwarding to `download_audio`, transient/auth remediation
    messages, `fetch.py` single+batch remediation surfacing; GREEN.

### Stage 3 — Doctor

- **Task 029.03** — `fetch.py doctor` subcommand + `install_components` refactor
  - RTM: **R5**, **R10** (c doctor tests)
  - Description File: [`docs/tasks/task-029-03-doctor-subcommand.md`](tasks/task-029-03-doctor-subcommand.md)
  - Priority: High · Dependencies: **029.02** (serializes `fetch.py` edits)
  - Stage A: `_run_doctor(argv)` + positional dispatch stub, `_have_yt_dlp()` refactor stub, NEW
    `tests/test_doctor.py` RED (exit codes, JSON shape, import-free assertion).
  - Stage B: full doctor logic (interpreter/in-venv/version/remediation/cloud key_present); GREEN.

### Stage 4 — Docs + regression gate

- **Task 029.04** — Docs (SKILL.md/manual/references), `.env.example`, full regression + `validate_skill`
  - RTM: **R6**, **R8**, **R9a**, **R2c**, **R10** (e/f final gate)
  - Description File: [`docs/tasks/task-029-04-docs-env-regression.md`](tasks/task-029-04-docs-env-regression.md)
  - Priority: Medium · Dependencies: **029.01–029.03**
  - Single pass (documentation/config): SKILL.md Dependencies/ASR-portability/X-cookie blocks +
    flags list (`--concurrent-fragments`/`--media-timeout-sec`/`doctor`); manual flags table;
    `.env.example` new env vars; final full-suite green + validator exit 0.

---

## 3. Verification Commands (exact, working)

Run from the skill root `skills/transcript-fetcher/`:

```bash
# Full offline regression suite (baseline: 274 tests OK, skipped=1):
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts

# Single module (fast iteration), e.g.:
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_ytdlp_media.py

# Structural / Gold-Standard validation (must exit 0):
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/transcript-fetcher
```

Live E2E (opt-in, NOT required for merge): gated behind `TRANSCRIPT_FETCHER_E2E=1`; exercised
manually at the end per the driver ("убедись, что всё работает") — a real short X fetch + `doctor`.

---

## 4. Use Case Coverage

| Use Case | Tasks |
|----------|-------|
| UC-1 (long X Broadcast, default flags — R1–R4) | 029.01, 029.02 |
| UC-2 (readiness check — R5, R6, R8) | 029.03, 029.04 |
| UC-3 (actionable timeout — R7) | 029.02 |
| UC-4 (expired cookies refresh path — R9) | 029.02 (R9b), 029.04 (R9a) |

---

## 5. Locked Design Constraints (copy into every sub-task; do NOT re-litigate)

1. `DEFAULT_CONCURRENT_FRAGMENTS = 8` in `_ytdlp_media.py`; argv ALWAYS gains
   `--concurrent-fragments N` on the **media** download; clamp `min(32, max(1, n))` inside
   `download_audio`; caption/subtitle paths untouched.
2. **3-layer validation:** CLI `--concurrent-fragments <= 0` → UsageError exit 2; env
   `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` malformed/non-positive → default 8
   (`_config.concurrent_fragments()`); the `download_audio` clamp is defensive (upper bound in
   practice).
3. **Media budget:** `--media-timeout-sec` (`<= 0` → exit 2) > env
   `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC` (malformed → ignored; `_config.media_timeout_sec()`
   returns `Optional[int]`) > `media_timeout_for(duration_s)` = `max(600, int(duration_s*4))` if
   duration known else `1800`. `x.py` computes the budget ONCE (it owns `info`;
   `duration = info.get("duration")`) and passes it ONLY to `download_audio` —
   probe/captions/silence-removal/ASR keep their existing budgets. `fetch_x_transcript` gains
   `media_timeout_sec: Optional[int] = None`.
4. **doctor:** positional subcommand dispatched BEFORE argparse (`argv[0] == "doctor"`); own
   mini-parser with `--json`; reuse `install_components._components()`; REFACTOR
   `install_components._have_yt_dlp()` to `importlib.metadata.version("yt-dlp")` (no `import yt_dlp`);
   report `interpreter=sys.executable`, `in_venv=(sys.prefix != sys.base_prefix)`, yt-dlp version via
   `importlib.metadata`, cloud row = boolean `key_present` + `allow_cloud` state ONLY (never the key
   value); exit 0 if yt-dlp present else 7; envelope `{v:1, interpreter, in_venv, ready,
   components:{…}, remediation:[…]}`. Doctor stays import-free (a test asserts `"yt_dlp" not in
   sys.modules` after a run).
5. **Transient classification:** `classify_failure()` `"transient"` matched ONLY on
   `"timeout downloading audio"` (NOT `"timeout probing metadata"`); `_raise_for_failure` maps
   transient → `TranscriptFetchError(remediation=…)` naming `--concurrent-fragments` and
   `--media-timeout-sec`; `TranscriptFetchError` gains optional `remediation` param in `_stat.py`;
   `fetch.py` single-URL handler adds `details.remediation`; batch mode gains explicit
   `except TranscriptFetchError` (before the generic `Exception`) carrying `remediation`.
6. **Auth remediation (R9b):** `x.py._raise_for_failure` auth branch names the resolved cookies
   file when one was used, else the convention path `~/.transcript-fetcher/x.com-cookies.txt`
   (reuse `_auth.DEFAULT_AUTH_DIR`); pass `cookies_file` into `_raise_for_failure`.
</content>
</invoke>
