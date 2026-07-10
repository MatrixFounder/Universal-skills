# TASK 029 — transcript-fetcher: HLS parallel download + media-aware timeout + `doctor` (spec S1–S6)

**Status:** ✅ COMPLETE (VDD-Enhanced converged 2026-07-10; 3 adversarial cycles: 18→9→3 findings, all fixed or deferred as TF-X-7; 351 offline tests + live E2E green).
**Skill:** `transcript-fetcher` (Apache-2.0). **Mode:** VDD-Enhanced (`/vdd`).
**Origin spec:** [`docs/transcript-fetcher-skill-improvement-spec.md`](transcript-fetcher-skill-improvement-spec.md)
— born from the 2026-07-09 import of the cyber•Fund *"Building AI-Native Startups [004]"* X Broadcast
(~70 min, 2089 HLS fragments), where the serial media download timed out and forced a manual
out-of-skill workaround (`yt-dlp -N 16` + `mw transcribe`).

---

## 0. Meta Information

- **Task ID:** 029 · **Slug:** `transcript-fetcher-hls-hardening` · **Date:** 2026-07-10
- **Driver (RU):** «реализуй спецификацию docs/transcript-fetcher-skill-improvement-spec.md.
  Убедись в конце, что все работает корректно и ничего не сломано.»
- **Affected surface:** `skills/transcript-fetcher/` only —
  `scripts/sources/_ytdlp_media.py`, `scripts/sources/x.py`, `scripts/fetch.py`,
  `scripts/_config.py`, `scripts/install_components.py` (reused, minor), `SKILL.md`,
  `scripts/tests/`. **No** office-skills replication units are touched (no `diff -q` gates apply).
- **Known-issues context (read):** TF-X-1 (youtube/vimeo NOT on `_ytdlp_media.py` — by design,
  do not retrofit), TF-X-2 (ffmpeg required for X HLS ASR — handled), TF-X-3 (cloud ASR
  egress — by-design opt-in), TF-X-5 (X auth + long-broadcast cost — handled; this task
  extends its documentation), TF-X-6 (silence removal — handled).

## 1. Problem Description

An X Broadcast is an HLS stream of thousands of small fragments. The skill's
`download_audio()` ([_ytdlp_media.py:344](../skills/transcript-fetcher/scripts/sources/_ytdlp_media.py))
builds a yt-dlp argv with **no `--concurrent-fragments`**, so fragments download serially
(~120 KB/s measured) and long media hits the **flat per-attempt `timeout_sec`** — the same
180 s default (`DEFAULT_TIMEOUT_SEC`, [youtube.py:55](../skills/transcript-fetcher/scripts/sources/youtube.py))
that gates the fast metadata probe. The failure surfaces as an opaque
`TranscriptFetchError` («timeout downloading audio (>600s)») with no remediation. Separately,
`yt-dlp` is **vendored in `scripts/.venv`** (invoked as `python -m yt_dlp`), so a naïve
`which yt-dlp` yields a false "missing" verdict — there is no one-command readiness probe,
and SKILL.md does not warn against the global-install trap. ASR portability (backend chain,
exit-7) and the X cookie contract are under-documented.

Measured on the 004 import: serial ≈ 120 KB/s (26 MB in ~4 min, timed out at 600 s);
`yt-dlp -N 16` ≈ 2.2 MB/s (130 MB in ~2 min) — ≈18× speedup. **Parallelism is the fix;
a bigger timeout is only the safety margin.**

## Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| R1 | **Parallel HLS fragment download** (spec S1, P0): `download_audio()` adds `--concurrent-fragments N` to the media argv | YES | (a) new `download_audio(concurrent_fragments=…)` param; (b) `DEFAULT_CONCURRENT_FRAGMENTS = 8` module constant; (c) argv gains `--concurrent-fragments <N>` for every media download (safe no-op on progressive files); (d) `N` clamped to `[1, 32]` (bounded — rate-limit safety); (e) caption/subtitle argv paths **unchanged** (single files today) |
| R2 | **Config knob** for concurrency (spec S1): `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` | YES | (a) `_config.concurrent_fragments()` typed accessor (env / `.env`, default 8); (b) malformed / non-positive values fall back to default (never crash — config contract); (c) documented in `scripts/.env.example` |
| R3 | **CLI flag** `--concurrent-fragments N` on `fetch.py` (spec S1), forwarded end-to-end to `download_audio` | YES | (a) argparse flag, default `None` → config → 8; (b) `<= 0` rejected as UsageError exit 2 (matches `--timeout-sec` convention); (c) forwarded through `_fetch_one` → `fetch_x_transcript` → `download_audio`; (d) `--concurrent-fragments 1` reproduces serial behaviour (argv carries the literal `1`) |
| R4 | **Media-aware download timeout** (spec S2, P1): the media download gets its own budget, separate from the probe | YES | (a) new `--media-timeout-sec N` CLI flag (`<= 0` → UsageError 2) + `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC` accessor; (b) resolution: CLI flag > env > **duration-derived floor** `max(600, duration_s × 4)` when the probe reported a duration, else generous default **1800 s** (X often probes `NA`); (c) helper `media_timeout_for(duration_s)` in `_ytdlp_media.py` (pure, unit-testable); (d) the metadata probe and caption download keep the small `--timeout-sec` budget (≤60 s socket / 180 s attempt) — **probe behaviour unchanged** |
| R5 | **Doctor entrypoint** (spec S3, P0): `fetch.py doctor` answers "is this skill ready?" without `$PATH` guessing | YES | (a) `fetch.py doctor [--json]` subcommand (positional dispatch before normal arg parsing; normal fetch CLI contract untouched); (b) reports resolved interpreter (`sys.executable`), in-venv flag, yt-dlp presence **+ version via `importlib.metadata`** (no yt_dlp module import — cheap probe), ffmpeg, each ASR backend (mw / whisper / whisper.cpp / cloud opt-in state); (c) exact remediation line for every gap; (d) exit **0** when required deps (yt-dlp) present, exit **7** when missing; (e) JSON shape `{v, interpreter, in_venv, ready, components:{…}, remediation:[…]}` stable for machine callers; (f) reuses `install_components._components()` for the ffmpeg/ASR-backend presence probes (no logic fork); the yt-dlp **version** specifically comes from `importlib.metadata.version("yt-dlp")` (not `install_components._have_yt_dlp()`'s `import yt_dlp`), keeping the probe import-free per spec §Risks |
| R6 | **Dependency-discoverability docs** (spec S3): SKILL.md gets a prominent "Dependencies" block | YES | (a) block near the top of SKILL.md: yt-dlp is **vendored in `scripts/.venv`**, do NOT `which yt-dlp` / `pip install` / `brew install` globally; (b) names the two canonical probes: `scripts/.venv/bin/python -m yt_dlp --version` and `scripts/.venv/bin/python scripts/fetch.py doctor`; (c) states that shelling callers MUST use the venv interpreter (downstream-integrator contract, e.g. obsidian-llm-wiki) |
| R7 | **Retryable + actionable timeout error** (spec S4, P2): a media-download timeout tells the operator the remedy | YES | (a) `classify_failure()` gains a `"transient"` category scoped to the **audio-download** timeout message only (`"timeout downloading audio"`); a metadata-**probe** timeout (`"timeout probing metadata"`) is NOT classified transient and does NOT get the concurrency remediation (fragment concurrency / media budget cannot fix a probe timeout); (b) `_raise_for_failure` maps `"transient"` → `TranscriptFetchError` whose message names **`--concurrent-fragments` and `--media-timeout-sec`** («long HLS broadcasts need parallel fragment download»); (c) the JSON error envelope carries the remediation in `details` (`TranscriptFetchError` gains an optional `remediation` attr, mirrored from `MissingDependencyError`) in **both** single-URL and batch modes — batch mode gains an explicit `except TranscriptFetchError` handler carrying `remediation` (mirrors the existing batch `MissingDependencyError` handling); (d) exit code stays **3** single-URL / **4** batch-aggregate (no contract break) |
| R8 | **ASR portability + exit-7 docs** (spec S5, P2) | YES | (a) SKILL.md "ASR portability" note: backend chain `mw → whisper → whisper.cpp → (opt-in) cloud`; (b) caption-less Broadcasts/Spaces **require** ffmpeg + one ASR backend; (c) exit-7 remediation named (`install_components.py --install-whisper` / `--asr-allow-cloud`); (d) `doctor` (R5) surfaces which backends resolve **before** a long fetch |
| R9 | **Explicit X cookie contract** (spec S6, P2) | YES | (a) SKILL.md documents the zero-config **convention path** `~/.transcript-fetcher/<host>-cookies.txt` (concretely `x.com-cookies.txt` for X; Netscape format), the `auth-map.json` (required for any custom filename such as `x-cookies.txt`), and the `--cookies-file` / `--cookies-from-browser` overrides under X sources; (b) the X auth-failure message names the cookie **refresh** path: the resolved file when one was used, else the convention path to create (`~/.transcript-fetcher/x.com-cookies.txt`) — not just "supply --cookies-file"; (c) cookie files remain hardened (0600, symlink-reject — unchanged, regression-locked) |
| R10 | **Tests + regression safety**: offline unit coverage for R1–R9; the full existing suite stays green | YES | (a) argv builder asserts `--concurrent-fragments` presence/value/clamp (R1–R3); (b) media-vs-probe timeout split + `media_timeout_for` table test (R4); (c) doctor exit codes + JSON shape (R5); (d) remediation strings (R7, R9b); (e) **regression:** YouTube/Vimeo/Skool caption paths untouched — full `unittest discover` green; (f) `validate_skill.py skills/transcript-fetcher` exits 0 |

## 3. Use Cases

### UC-1 — Long X Broadcast transcribes with default flags (R1–R4)

- **Actors:** Operator (human or agent skill-runner); System (fetch.py CLI).
- **Preconditions:** venv bootstrapped; ffmpeg + ≥1 ASR backend present; broadcast ≥60 min, no captions.
- **Main scenario:**
  1. Operator runs `fetch.py "https://x.com/i/broadcasts/<id>" --out b.txt` (no manual `-N`, no manual timeout).
  2. System probes metadata under `--timeout-sec` (180 s default) — unchanged fast path.
  3. No captions → System downloads audio with `--concurrent-fragments 8` under the **media** budget (duration-derived, or 1800 s when duration is `NA`).
  4. ASR transcribes; transcript + stat sidecar written; exit 0.
- **Alternative A (slow link, still too slow):** download exceeds the media budget → exit 3 with a message naming `--concurrent-fragments` / `--media-timeout-sec` (UC-3).
- **Alternative B (operator override):** `--concurrent-fragments 16 --media-timeout-sec 3600` → argv/budget reflect the overrides verbatim.
- **Postconditions:** transcript non-empty; stat records `transcript_origin`; no residual temp files.
- **Acceptance criteria:** offline: argv contains `--concurrent-fragments 8` by default and the literal override value when given; media call gets the media budget, probe keeps the probe budget. Network (opt-in, `TRANSCRIPT_FETCHER_E2E=1`): a ≥60-min Broadcast completes end-to-end with default flags.

### UC-2 — Readiness check without $PATH guessing (R5, R6, R8)

- **Actors:** Caller (agent/human/integrator); System (`fetch.py doctor`).
- **Preconditions:** none beyond a bootstrapped venv (that is exactly what it verifies).
- **Main scenario:**
  1. Caller runs `scripts/.venv/bin/python scripts/fetch.py doctor`.
  2. System prints interpreter path, in-venv flag, yt-dlp version, ffmpeg, ASR backends, cloud opt-in state; exit 0.
- **Alternative A (`--json`):** machine-readable envelope on stdout, same exit semantics.
- **Alternative B (yt-dlp absent, e.g. venv not bootstrapped):** report shows the gap + `bash scripts/install.sh` remediation; exit 7.
- **Alternative C (no ASR backend):** exit stays 0 (ASR is optional) but the report flags «caption-less X media will exit 7» with install remediation — the gap is visible **before** a long fetch.
- **Postconditions:** no side effects (read-only probes, no heavy imports, no network).
- **Acceptance criteria:** exit 0 + `"yt-dlp": {"present": true}` in a bootstrapped venv **without** consulting `$PATH` for yt-dlp; exit 7 + remediation when yt-dlp is unimportable; ASR backends listed.

### UC-3 — Timeout failure is actionable (R7)

- **Actors:** Operator; System.
- **Preconditions:** media download exceeds the media budget (simulated in tests via a stubbed `subprocess.run` raising `TimeoutExpired`).
- **Main scenario:**
  1. `download_audio` returns `(None, "timeout downloading audio (>Ns)")`.
  2. `_raise_for_failure` classifies it `"transient"` and raises `TranscriptFetchError` whose message + `details.remediation` name `--concurrent-fragments` and `--media-timeout-sec`.
  3. CLI exits 3; with `--json-errors` the envelope carries the remediation.
- **Postconditions:** no partial `_raw`/output committed; temp dir cleaned.
- **Acceptance criteria:** simulated timeout produces an error whose remediation names concurrency **and** media timeout; exit code remains 3.

### UC-4 — Expired X cookies point at the refresh path (R9)

- **Actors:** Operator; System.
- **Preconditions:** auth-gated Broadcast; the convention cookie file `~/.transcript-fetcher/x.com-cookies.txt` (or an auth-map-configured one) expired.
- **Main scenario:** probe/download fails with an auth-class yt-dlp error → `SourceAuthError` (exit 5) whose message names the cookie refresh path — the resolved cookie file when one was used, else the convention path to create (`~/.transcript-fetcher/x.com-cookies.txt`) — and the refresh options (`--cookies-file`, `--cookies-from-browser`).
- **Alternative A (cookies present but still rejected):** a fresh 401/403 with valid-looking cookies still maps to `SourceAuthError` (protected/suspended media); rate-limit phrases keep mapping to `SourceRateLimitError` (exit 6) — classification precedence unchanged.
- **Postconditions:** no output/sidecar written; temp dir cleaned; cookie file untouched (read-only).
- **Acceptance criteria:** offline: the auth-branch message contains the cookie-refresh remediation (convention path when no file was resolved); SKILL.md documents the `<host>-cookies.txt` convention + Netscape format + auth-map for custom names under X sources.

## 4. Non-Goals (Honest Scope)

- **No YouTube/Vimeo retrofit** onto `_ytdlp_media.py` (TF-X-1 is by-design; caption paths there are single-file downloads and gain nothing from fragment concurrency).
- **No automatic retry-with-larger-budget** after a timeout (spec S4 marks it optional). One long download already costs minutes; silently doubling it hides the knob the operator should learn. The remediation message is the retry contract. Documented here, not an open question.
- **No caption-path concurrency** — caption files are single files today (spec S1 explicitly defers).
- **No new external dependencies**; `requirements.txt` unchanged (yt-dlp already supports `--concurrent-fragments` and `importlib.metadata` is stdlib).
- **CLI contract preserved**: existing flags/exit codes unchanged; `doctor` is additive.

## 5. Open Questions

*(none blocking — spec decisions taken: S2 implemented as CLI/env override over a duration-derived floor with 1800 s NA-default, per spec preference order; S4 auto-retry deferred as a non-goal.)*

## 6. Verification Plan (summary)

1. **Offline unit** (`scripts/tests/`, no network): new `test_doctor.py`; extensions to `test_ytdlp_media.py`, `test_config.py`, `test_x_adapter.py`, `test_fetch_cli.py` per RTM R10.
2. **Full regression:** `./scripts/.venv/bin/python -m unittest discover -s scripts/tests` — green.
3. **Structural:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/transcript-fetcher` — exit 0.
4. **Live E2E (opt-in, network + cookies + ASR):** gated behind `TRANSCRIPT_FETCHER_E2E=1`; not required for merge (CI-safe), but the doctor + a real short X fetch will be exercised manually at the end («убедись, что всё работает»).
