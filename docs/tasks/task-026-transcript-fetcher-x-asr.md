# TASK 026 — `transcript-fetcher`: X.com (Twitter) video/Broadcast support + pluggable ASR backend

**Status:** 🟡 ANALYSIS → ARCHITECTURE (VDD).
**Skill:** `transcript-fetcher` (Apache-2.0; NOT an office/`html` proprietary skill — adding
X support does not change its license scope).
**Mode:** VDD (Verification-Driven, adversarial gates).
**Predecessor task surface:** v1.1 source-adapter architecture (`youtube`, `vimeo`, `skool`),
shared `TranscriptStat` + `_vtt_to_text` + `_description`.

---

## 0. Meta Information

- **Task ID:** 026
- **Slug:** `transcript-fetcher-x-asr`
- **Date:** 2026-06-28
- **Driver (user request, RU):** Extend `transcript-fetcher` so it can produce a transcript
  from **X.com (Twitter) videos and Broadcasts/Spaces**, fully automatically: reuse existing
  **embedded captions** when present, fall back to **ASR** (speech-to-text) only when no
  captions exist. No user mode-switch. Must be implemented as **another source provider**
  (not special-cased conditionals in the core), and the design must be **extensible** to
  Vimeo/TikTok/Twitch/etc. without touching the common pipeline.
- **Canonical live fixture (user-supplied):** `https://x.com/i/broadcasts/1nxnRRZnwbBxO`
  — confirmed via recon to be a **replay broadcast** ("Building AI-Native Startups [003]",
  uploader cyber•Fund), **no `subtitles`, no `automatic_captions`** → exercises the **ASR
  path** end-to-end. Output to be deposited under `tmp10/`.

### Recon facts (verified, not assumed — anti-hallucination)

| Probe | Result |
| --- | --- |
| `mw` (MacWhisper CLI) | **present** at `/usr/local/bin/mw`. Contract: `mw transcribe <file> [--model engine:model-id] [--persist] [--stream]`, prints transcript to **stdout**, accepts **audio _or_ video**. |
| `whisper` / `whisper.cpp` (`whisper-cli`/`main`) | **absent** on this machine. |
| `ffmpeg` / `ffprobe` | **absent** on this machine. |
| venv yt-dlp | present, `2026.03.17` (satisfies `requirements.txt` range). |
| Broadcast `yt-dlp -J` | reachable; 4 muxed HLS formats (`m3u8_native`, smallest `replay-600`, all carry `mp4a.40.2` audio); `live_status=was_live`; `subtitles`/`automatic_captions` both empty. |

> **Consequence (REVISED after the live E2E — see As-built §7):** the original assumption was
> that, because MacWhisper ingests **video**, the ASR path could hand a no-ffmpeg muxed download
> directly to `mw`. The live broadcast test **disproved this for HLS**: yt-dlp's no-ffmpeg HLS
> output is a fragment concatenation that is **not a valid container** — MacWhisper rejects it
> (`cannot open mp4`). X Broadcasts/Spaces are always HLS, so **ffmpeg is required** there (to
> extract a clean `m4a`); the adapter **fails fast (exit 7)** when ffmpeg is absent for an HLS
> source. ffmpeg stays optional only for non-HLS progressive media and the caption path.

---

## 1. Problem Description

`transcript-fetcher` v1.1 only obtains transcripts from **pre-existing caption tracks**
(YouTube/Vimeo via yt-dlp `--write-subs`, Skool author transcript or delegated embed). It has
**no ASR capability**, so any source whose media carries **no captions** (X Broadcasts,
Spaces, most native X video) yields `TranscriptFetchError` (exit 3). X.com is not a recognized
host at all (`_detect_source` → `Unsupported source`).

We must add X.com as a first-class source **and** introduce an ASR fallback so that
caption-less media still produces a transcript — without (a) breaking the three existing
adapters, (b) downloading full video when avoidable, or (c) leaving temp artifacts behind.

---

## 2. Requirements Traceability Matrix (RTM)

Granularity: ≥3 sub-features per requirement. **MVP?** marks what must ship for the live
broadcast test to pass.

### EPIC A — X.com source provider (`XTranscriptProvider`)

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **A1** | Recognize X.com URLs by hostname allowlist | ✅ | (a) `x.com`, `www.x.com`, `mobile.x.com`; (b) `twitter.com`, `www.twitter.com`, `mobile.twitter.com`; (c) status `…/status/<id>` **and** `…/i/broadcasts/<id>` shapes; (d) reject substring/typosquat hosts (reuse `urlparse` allowlist, not substring) |
| **A2** | Encapsulated caption-first → ASR pipeline inside the provider | ✅ | (a) probe metadata once (`yt-dlp -J` or info-json); (b) if `subtitles`/`automatic_captions` carry a ladder lang → caption path (existing VTT cleaner); (c) else ASR path; (d) NO routing conditionals leak into `fetch.py` core |
| **A3** | Embedded-caption normalization reuse | ✅ | (a) WebVTT via existing `_vtt_to_text`; (b) strip WEBVTT cue/service lines + decode HTML entities (already in cleaner); (c) preserve `>>` speaker turns; (d) SRT/TTML accepted opportunistically (yt-dlp converts to VTT via `--sub-format vtt` when possible — honest-scope note if not) |
| **A4** | Audio-minimal download for ASR | ✅ | (a) never download when captions suffice; (b) prefer `bestaudio`/`-x` **iff** ffmpeg present; (c) else download the **smallest muxed format** (min bytes) and hand the media file to a video-capable backend; (d) `--socket-timeout` + per-attempt `timeout_sec` honored |
| **A5** | `embed_source`/metadata parity with other adapters | ➖ | (a) `--with-description` populates title/uploader/upload_date/duration via info-json; (b) `.description.md` sidecar; (c) `video_id` extracted from status/broadcast id |

### EPIC B — Pluggable ASR backend abstraction

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **B1** | `ASRBackend` interface (Python equivalent of the spec's TS `TranscriptProvider`) | ✅ | (a) `name: str`; (b) `available() -> bool` (probe, no network/heavy import at module load); (c) `transcribe(audio_path, *, lang) -> ASRResult`; (d) adding a backend requires **zero** edits to X-provider/core |
| **B2** | Fallback chain in fixed priority | ✅ | (a) MacWhisper (`mw`) → (b) Whisper CLI (`whisper`) → (c) whisper.cpp (`whisper-cli`/`main`) → (d) cloud API (OpenAI Whisper) **opt-in only**; (e) select first `available()`; (f) on engine error, fall through to next available |
| **B3** | MacWhisper backend (primary, present on this host) | ✅ | (a) probe `command -v mw`; (b) `mw transcribe <file>` capture stdout; (c) optional `--model`; (d) map non-zero exit / empty output → `ASRError` with stderr tail |
| **B4** | Whisper CLI backend | ➖ | (a) probe `whisper`; (b) `whisper <file> --model … --output_format txt --output_dir <tmp> --language <lang>`; (c) read produced `.txt`; (d) error mapping |
| **B5** | whisper.cpp backend | ➖ | (a) probe `whisper-cli`/`main`; (b) requires 16 kHz WAV → needs ffmpeg, else `available()` returns False / raises clear MissingDependency; (c) `-otxt -of <out>`; (d) error mapping |
| **B6** | Cloud (OpenAI Whisper API) backend — opt-in | ➖ | (a) `available()` True only if `--asr-allow-cloud` AND `OPENAI_API_KEY` set; (b) POST audio to transcription endpoint; (c) **egress disclosure** in docs + stat note; (d) never auto-selected without explicit opt-in |

### EPIC C — Transcript provenance, cleanup, errors, logging

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **C1** | Transcript provenance in stat | ✅ | (a) NEW `transcript_origin` field = `embedded-captions`/`macwhisper`/`whisper-cli`/`whisper-cpp`/`openai-api`; (b) keep `source` = platform (`x`); (c) `chosen_track_kind="asr"` for ASR; (d) backward-compatible Optional field |
| **C2** | Guaranteed temp cleanup (`try/finally`) | ✅ | (a) all audio/VTT/info.json/`.part`/`.m3u8`/dirs under one tempdir; (b) `shutil.rmtree` in `finally` even on error; (c) zero residual artifacts post-run (assert in test); (d) honors caller-supplied `workdir` (only auto-tempdir is auto-removed, per existing convention) |
| **C3** | Graceful error mapping (clear messages, no raw tracebacks) | ✅ | (a) private/protected/suspended → `SourceAuthError` (exit 5); (b) deleted/unavailable broadcast → `TranscriptFetchError` (exit 3); (c) rate-limit 429 → `SourceRateLimitError` (exit 6); (d) missing yt-dlp/ffmpeg-when-required/no-ASR-backend → `MissingDependencyError` (exit **7**); (e) ASR ran-but-empty/failed across all backends → `TranscriptFetchError` (exit 3) |
| **C4** | Debug-only stage logging | ✅ | (a) `--debug` / `TRANSCRIPT_FETCHER_DEBUG=1` → stage lines on **stderr** ("Detected X media", "Fetching metadata", "Embedded captions found", "Downloading captions", "Downloading audio", "Using MacWhisper", "Cleaning temporary files", "Finished"); (b) silent without debug; (c) stdout stays pure JSON stat |
| **C5** | Extensibility proof | ✅ | (a) shared yt-dlp media core reused (no copy-paste of download logic into X); (b) a documented "add a platform in N edits" recipe; (c) ASR path reusable by any future yt-dlp source; (d) existing 3 adapters + their tests untouched & green |

---

## 3. Use Cases

### UC-1 (MVP, the live test) — caption-less Broadcast → MacWhisper ASR
1. User runs `fetch.py "https://x.com/i/broadcasts/1nxnRRZnwbBxO" --out tmp10/broadcast.txt --debug`.
2. `_detect_source` → `x`. Provider probes metadata: no captions.
3. Provider downloads smallest muxed format → `media.mp4` in a tempdir.
4. ASR registry selects MacWhisper (`mw` available) → `mw transcribe media.mp4` → text.
5. Plain text → `tmp10/broadcast.txt`; stat sidecar with `source=x`,
   `transcript_origin=macwhisper`, `chosen_track_kind=asr`.
6. Tempdir removed in `finally`. Exit 0, JSON stat on stdout.

### UC-2 — native X status video WITH captions
1. `…/status/<id>` whose media carries `automatic_captions[en]`.
2. Provider takes the **caption path** (no audio download), `transcript_origin=embedded-captions`.

### UC-3 (alt) — no ASR backend available
1. Caption-less media on a host with no `mw`/`whisper`/`whisper.cpp` and cloud not opted in.
2. → `MissingDependencyError` exit 7 with a remediation hint (install MacWhisper, or
   `--asr-allow-cloud` + `OPENAI_API_KEY`). No traceback.

### UC-4 (alt) — private/deleted/rate-limited
1. Protected/suspended post → exit 5; deleted broadcast → exit 3; HTTP 429 → exit 6.

---

## 4. Acceptance Criteria (verifiable pass/fail)

- **AC-1 (live):** `fetch.py` on `…/broadcasts/1nxnRRZnwbBxO` writes a non-empty
  `tmp10/broadcast.txt` (> 200 chars) + `tmp10/broadcast.txt.stat.json` with
  `source="x"`, `transcript_origin="macwhisper"`, `chosen_track_kind="asr"`; exit 0;
  **no temp artifacts remain** anywhere after the run.
- **AC-2:** All existing offline tests stay green; new offline tests cover X URL detection
  (incl. mobile + twitter.com + broadcasts + reject typosquats), ASR backend
  probe/priority/fallback (subprocess mocked), and caption-vs-ASR routing.
- **AC-3:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/transcript-fetcher` exits 0; security validator exits 0.
- **AC-4:** Adding a hypothetical new platform requires only: append hosts to
  `_SOURCE_BY_HOST`, one dispatch branch, one new `sources/<p>.py` reusing the shared
  yt-dlp+ASR core — demonstrated by the X adapter being ≤ the size of `vimeo.py` + a thin
  ASR call. No ASR/core edits.
- **AC-5:** `--debug` emits the documented stage lines on stderr; without it, stderr is
  empty on success and stdout is exactly one JSON stat line.
- **AC-6:** No new **pip** dependency beyond yt-dlp (ASR engines are optional external
  tools, probed at runtime — consistent with the skill's "no heavy deps" red flag).

## 5. Open Questions

- **OQ-1 (resolved by default, documented):** Cloud OpenAI Whisper backend is **opt-in**
  (`--asr-allow-cloud` + `OPENAI_API_KEY`), never auto-selected — privacy/egress posture
  matches the skill's local-first ethos. Revisit only if the user wants it in the automatic
  chain.
- **OQ-2 (REVISED by live E2E):** ffmpeg is **required for HLS sources** (X Broadcasts/Spaces):
  the no-ffmpeg HLS download is not a valid container the ASR engine can open, so the adapter
  fails fast (exit 7) when ffmpeg is absent for an HLS source. With ffmpeg, the smallest media is
  extracted to a clean `m4a`. ffmpeg stays optional only for non-HLS progressive media and the
  caption path. whisper.cpp additionally needs ffmpeg + a model (`available()=False` otherwise).
- **OQ-3 (resolved):** `tmp10/` interpreted as a repo-root working directory for the live
  test artifacts (untracked).
- **OQ-4 (honest-scope):** exact `mw --model` default is "currently selected model" in
  MacWhisper; we pass no `--model` (use the user's selected model) unless a future flag
  is added.

## 6. Non-goals

- No browser automation (Playwright/Puppeteer) — yt-dlp only (per user).
- Not beating X login walls beyond an optional `--cookies-file` (existing mechanism) for
  protected/age-gated media.
- Not preserving caption timecodes in the `.txt` (the format is plain text by design — the
  user's "if the format supports them" clause resolves to "it does not").
- No refactor of the 3 existing adapters' internals (only additive shared-core extraction).

## 7. As-built (2026-06-28)

Shipped (all additive; the 3 existing adapters untouched):

- **X source** `sources/x.py` (`XTranscriptProvider`) — captions-first → ASR, fully
  encapsulated; `sources/_ytdlp_media.py` shared yt-dlp core (the extension surface);
  `sources/_log.py` debug logger.
- **Pluggable ASR** `asr/` package — `ASRBackend` ABC + priority chain MacWhisper → Whisper CLI
  → whisper.cpp → opt-in OpenAI/compatible cloud; `MissingDependencyError` (exit 7) vs
  all-failed (exit 3).
- **Config/secrets** `_config.py` + `.env.example` + `.gitignore` — every endpoint/model/tool
  path externalised (any OpenAI-compatible server); `.env` is secrets-safe (0600-or-refuse,
  symlink-reject, process-env-wins, header-only, never argv/logged). `install_components.py`
  component installer (wired into `install.sh`).
- **Stat** `_stat.py` — `transcript_origin` provenance + `asr_backend`/`asr_model`
  (backward-compatible Optionals).
- **CLI** `fetch.py` — X dispatch, `--debug`/`--asr-*` flags, exit-7 (single + batch),
  source-aware batch ids.

**Verification:** 219 offline tests green, `validate_skill` exit 0, security validator
0 critical / 0 errors. Two reviewer gates (task + architecture) + a 3-critic adversarial review
(5 findings fixed: batch exit-7, CRLF-injection guard, cloud upload size-cap, response-cap,
type annotation).

**Live E2E** on `https://x.com/i/broadcasts/1nxnRRZnwbBxO` → `tmp10/`: **75 827-char transcript**
(`source=x`, `transcript_origin=macwhisper`, `chosen_track_kind=asr`), description sidecar,
verified-clean teardown, exit 0.

**Key as-built correction (live-E2E finding):** the analysis assumption "ffmpeg-optional —
MacWhisper reads video" was **wrong for HLS**. yt-dlp's no-ffmpeg HLS download is not a valid
container (`mw` → `cannot open mp4`). **ffmpeg is required** for the X Broadcast/Space ASR path;
the adapter now **fails fast (exit 7)** via `is_hls_only()` when ffmpeg is absent for an HLS
source, and extracts a clean audio-only `m4a` when present. Docs corrected across SKILL.md,
arch-016, KNOWN_ISSUES (TF-X-2/6), the manual, and THIRD_PARTY_NOTICES (ffmpeg + ASR engines +
cloud service added).

**Not committed** (user's standing preference).
