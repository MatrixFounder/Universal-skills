---
name: transcript-fetcher
description: >-
  Use when the user wants a clean plain-text transcript of a video URL
  (YouTube, Vimeo, X.com/Twitter incl. Broadcasts/Spaces) or a Skool
  classroom lesson. X uses embedded captions when present and falls
  back to ASR (MacWhisper/Whisper/whisper.cpp/cloud) automatically.
  Skool cookies are optional (public communities work without; private
  ones accept Netscape cookies.txt). Manual->auto language fallback,
  rolling caption dedup, >> speaker turns preserved, JSON stat sidecar
  plus optional .description.md sidecar.
tier: 2
version: 1.2
status: active
changelog: >-
  v1.2 — Add X.com (Twitter) adapter: native status video + Broadcasts/
  Spaces. Captions-first (subtitles/automatic_captions via yt-dlp) with
  automatic ASR fallback through a pluggable backend chain (MacWhisper
  `mw` -> Whisper CLI -> whisper.cpp -> opt-in OpenAI/compatible cloud).
  ffmpeg is required for the ASR path on HLS sources (Broadcasts/Spaces) —
  used to extract a clean audio-only m4a; the skill fails fast (exit 7)
  when it is absent there. New stat field `transcript_origin`,
  exit code 7 (MissingDependency), `--debug` stage logging, `--asr-*`
  flags. Skill-local `.env` config (secrets-safe, 0600) +
  install_components.py component installer. transcript-fetcher is now a
  universal extraction layer (any future yt-dlp platform reuses the X
  pipeline).
  v1.1 — Add Vimeo + Skool adapters; opt-in --with-description /
  --description-only producing a <out>.description.md (YAML front-
  matter + Markdown body) for YouTube & Skool. Skool delegates
  embedded YouTube/Vimeo to those adapters automatically and uses
  cookies.txt for private/paid communities; public ones work without.
  v1.0 — Initial release — YouTube adapter, ru/ru-orig/en fallback
  ladder, offline tests.
---

# Transcript Fetcher

**Purpose**: Given a video URL, produce a clean plain-text transcript
ready for downstream summarization or analysis. Single responsibility:
fetch + clean. Composes well with `summarizing-meetings` (run this
first, then feed the resulting `.txt` to that skill).

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**

- "I'll just paste the URL into the model and ask it to transcribe" -> **WRONG**. Models do not have audio access and will hallucinate. Always run `fetch.py` and read back the resulting `.txt`.
- "Manual `ru` failed, I'll just use `en` auto-translation, no warning needed" -> **WRONG**. Auto-translated English subtitles destroy idioms, names, and technical terms. The `quality_flag: english_auto_translation` in the stat MUST be surfaced to the user.
- "I'll skip writing the JSON stat sidecar, the .txt is enough" -> **WRONG**. The sidecar records WHICH track was picked. Without it, downstream cannot tell whether the transcript is high-quality manual subs or low-quality auto-translation.
- "The transcript has weird `>>` markers, I'll strip them" -> **WRONG**. Those are speaker-turn boundaries. Removing them collapses multi-speaker meetings into a single voice and ruins downstream attribution.
- "Auto-generated Russian (`ru-orig`) is garbage, I'll prefer `en` instead" -> **WRONG**. `ru-orig` is the actual Russian audio transcribed; `ru` (without `-orig`) is often an English auto-translation back to Russian. `ru-orig` > `ru` > `en`.
- "I'll add `ffmpeg` to the **pip** deps just in case" -> **WRONG**. The caption path (WebVTT parsing) is pure Python and needs nothing extra; `ffmpeg` is a soft-optional **external system tool**, never a pip dependency. It IS genuinely required for the X **ASR** path on HLS sources (Broadcasts/Spaces) — yt-dlp uses it to extract a clean audio-only `m4a`, and the skill fails fast (exit 7) when it is absent there — but it is detected at runtime (`install_components.py`), not bundled. Do not pull heavy packages into `requirements.txt`.

## 2. Capabilities

- **Fetch** YouTube and Vimeo captions via `yt-dlp` (no audio download).
- **Fetch** X.com / Twitter — native status video AND Broadcasts/Spaces.
  The X provider is **captions-first**: it reuses embedded
  `subtitles`/`automatic_captions` when present, and **only** when none
  exist does it download the smallest media and **transcribe via ASR**.
  Fully automatic — no mode switch. ASR runs through a **pluggable
  backend chain**: MacWhisper (`mw`) → Whisper CLI → whisper.cpp →
  opt-in OpenAI/compatible cloud. **`ffmpeg` is required for the X ASR
  path on HLS sources** (Broadcasts/Spaces): with it the smallest media
  is extracted to a clean audio-only `m4a`; without it the skill **fails
  fast (exit 7)** because yt-dlp's no-ffmpeg HLS output is not a valid
  container the ASR engine can open. (For non-HLS progressive media, or
  when embedded captions exist, ffmpeg is not needed.)
- **Fetch** Skool lesson pages via a stdlib HTML scrape — public
  communities work without auth; private/paid ones accept an optional
  Netscape `cookies.txt`. Then **delegate** embedded YouTube/Vimeo
  videos to those adapters; capture author-supplied transcript field
  when present.
- **Fall back** through a configurable ladder (default for ru: manual ru -> auto ru-orig -> auto ru -> auto en).
- **Clean** captions to plain text — WebVTT, and for X also **SRT and TTML/DFXP** (`vtt/srt/ttml/best` preference list, so a non-VTT track is no longer skipped to ASR): strip timestamps, inline timing tags, and rolling-caption overlap; decode HTML entities. TTML is parsed safely (DTD/entity declarations refused — XXE/billion-laughs guard). For X, captions-first is **language-robust**: if the requested `--lang` has no track but the post carries captions in another language, those are used (manual preferred, with a note) rather than dropping to ASR.
- **Preserve** `>>` speaker-turn markers as paragraph breaks.
- **Emit** a JSON stat sidecar (chosen track, char count, speaker-turn count, quality flag, plus optional title/uploader/duration metadata). For X media it also records `transcript_origin` (`embedded-captions` | `macwhisper` | `whisper-cli` | `whisper-cpp` | `openai-api`) so downstream skills know HOW the text was produced.
- **Optionally write** `<out>.description.md` (YAML frontmatter +
  Markdown body) when `--with-description` is passed — gives you a
  ready-to-ingest description for RAG / Obsidian / human review.
- **Batch** mode for processing multiple URLs from a text file.
- **Source-agnostic** architecture: each platform is one file under `scripts/sources/`. The yt-dlp + ASR pipeline is shared (`sources/_ytdlp_media.py` + `asr/`), so a future TikTok/Twitch/Vimeo-ASR provider is one new file + one host entry — no pipeline changes. Zoom and podcast slots remain reserved.
- **Configurable + secrets-safe**: a skill-local `.env` (see `scripts/.env.example`) externalises every endpoint, model, and tool path. The cloud ASR endpoint works with any OpenAI-compatible server (Groq, self-hosted whisper). A `.env` holding an API key is **refused unless `chmod 600`** (and not a symlink); the key is sent only in an HTTP header, never on argv or in logs.

## 3. Execution Mode

- **Mode**: `script-first`
- **Why this mode**: Fetching captions, parsing WebVTT, deduplicating rolling captions, and applying the fallback ladder are deterministic operations with > 5 lines of business logic. The CLI is the contract; SKILL.md is orchestration.

## 4. Script Contract

- **Install** (one-time): creates the venv + yt-dlp, then reports which optional ASR components are present:
  ```bash
  bash skills/transcript-fetcher/scripts/install.sh
  # Optional ASR engines (for caption-less X media) — detect / install:
  ./scripts/.venv/bin/python scripts/install_components.py            # status report
  ./scripts/.venv/bin/python scripts/install_components.py --install-whisper   # pip openai-whisper into the venv
  ./scripts/.venv/bin/python scripts/install_components.py --system --run      # brew/apt ffmpeg + whisper.cpp
  ```
- **Single URL**:
  ```bash
  cd skills/transcript-fetcher
  ./scripts/.venv/bin/python scripts/fetch.py <URL> --out <path/to/output.txt>
  ```
  Optional flags: `--lang ru` (default), `--prefer manual|auto` (default `manual`), `--with-description`, `--description-only`, `--cookies-file PATH`, `--json-errors`, `--debug` (stage logging to stderr), `--asr-allow-cloud` (opt-in cloud ASR), `--asr-model <id>`, `--asr-timeout-sec N`, `--max-duration-min N` (X: transcribe only the first N minutes — clips the download), `--keep-silence` (X ASR: do NOT strip long silences before transcription — silence removal is ON by default to cut Whisper hallucinated filler on silent lead-in/out), `--auth-map PATH` (per-host cookies), `--cookies-from-browser BROWSER` (X: load cookies from a local browser via yt-dlp).
- **X.com / Twitter** (captions-first, automatic ASR fallback; no mode switch). A Broadcast/Space usually has no captions → ASR via the first available local backend (MacWhisper, etc.):
  ```bash
  cd skills/transcript-fetcher
  ./scripts/.venv/bin/python scripts/fetch.py \
      "https://x.com/i/broadcasts/<id>" \
      --out broadcast.txt --with-description --debug
  # → broadcast.txt + .stat.json (source="x", transcript_origin="macwhisper",
  #   chosen_track_kind="asr"). A status video WITH captions skips ASR
  #   (transcript_origin="embedded-captions"). Use --cookies-file for
  #   protected/age-gated media.
  ```
- **Skool lesson** (cookies needed ONLY for private / paid communities — public ones work without):
  ```bash
  ./scripts/.venv/bin/python scripts/fetch.py \
      "https://www.skool.com/<community>/classroom/<id>?md=<lesson-id>" \
      --out lesson.txt --with-description \
      --cookies-file ~/.config/skool-cookies.txt
  ```
- **Batch**:
  ```bash
  ./scripts/.venv/bin/python scripts/fetch.py --batch urls.txt --out-dir transcripts/
  ```
- **Inputs**: A YouTube / Vimeo / Skool-lesson URL (or a file with one URL per line). Empty lines and `#` comments in the batch file are ignored.
- **Outputs**:
  - `<out>.txt` — clean plain text, UTF-8.
  - `<out>.txt.stat.json` — sidecar with the chosen track, quality flag, plus optional title / uploader / upload_date / duration_sec / embed_source / embed_url metadata.
  - `<out>.description.md` — only when `--with-description` is passed; YAML frontmatter + Markdown body.
  - One JSON stat record per URL on stdout.
- **Failure semantics**: Non-zero exit. With `--json-errors`, stderr carries a single JSON line `{v, error, code, type, details?}`. Exit codes: `2` usage error (incl. malformed Skool URL, cookies file path missing on disk), `3` no transcript producible (no caption track in the ladder AND — for X — ASR produced nothing / every available backend failed), `4` partial batch failure, `5` source-auth error (HTTP 401/403 — private Skool community needs cookies, X protected/suspended/age-gated media, or supplied cookies expired), `6` source rate-limit (HTTP 429), `7` missing dependency (yt-dlp absent, ffmpeg required-but-absent, or **no ASR backend available** for caption-less media — `details.remediation` carries the hint), `1` unexpected.
- **Idempotency**: Re-running overwrites the output file and sidecar. yt-dlp itself caches nothing the skill depends on; behaviour is reproducible given network availability.
- **Dry-run support**: Not currently exposed as a flag. Inspect the fallback ladder via `_build_ladder` if needed.

## 5. Safety Boundaries

- **Allowed scope**: Reads from the network (yt-dlp HTTPS to YouTube/Vimeo; stdlib HTTPS to Skool). Writes ONLY to the user-specified `--out` / `--out-dir` path plus a `.stat.json` sidecar (and optionally a `.description.md` sidecar) next to it.
- **Default exclusions**: Never downloads the video itself (only `--skip-download` + subtitle tracks / `--write-info-json` for metadata). Never writes to any path the user did not explicitly pass via `--out` / `--out-dir`.
- **Destructive actions**: None. The script does not delete or modify any pre-existing files outside the chosen output paths. In batch mode, output path collisions are handled per `--on-collision={error,skip,suffix}` (default: `error`).
- **Optional artifacts**: The JSON stat sidecar is mandatory in single-URL mode (it is the audit trail for which track was used). The `.description.md` sidecar is written only when `--with-description` is passed.
- **URL allowlist**: Source dispatch is hostname-based against an explicit allowlist:
  - YouTube — `youtu.be`, `youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtube-nocookie.com` (plus `www.` variants).
  - Vimeo — `vimeo.com`, `www.vimeo.com`, `player.vimeo.com`.
  - X / Twitter — `x.com`, `www.x.com`, `mobile.x.com`, `twitter.com`, `www.twitter.com`, `mobile.twitter.com` (status `…/status/<id>` and `…/i/broadcasts/<id>`).
  - Skool — `skool.com`, `www.skool.com`, `app.skool.com`; additionally URLs must match `/<community>/classroom/<id>?md=<lesson-id>`. Landing / `/about` / `/calendar` pages are rejected.
  URLs that merely contain a supported host as a substring elsewhere are rejected.
- **ASR backends (external, optional)**: For caption-less X media the skill shells out (argv arrays, never a shell string) to whichever local engine is present — MacWhisper `mw`, Whisper CLI, or whisper.cpp. None is a pip dependency; all are probed at runtime. **ffmpeg** (also external) is required to turn an X Broadcast's HLS stream into a valid audio file; the skill **fails fast with exit 7** (clear remediation, before any large download) when ffmpeg is absent for an HLS source. `bash scripts/install.sh` reports which engines are available; `scripts/install_components.py` guides/installs them (incl. ffmpeg). If no ASR backend is available (and cloud is not opted in), the run also fails cleanly with exit 7, never a traceback.
- **Cloud ASR egress (opt-in only)**: The OpenAI/compatible cloud backend is used **only** with `--asr-allow-cloud` (or `TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD=1`) AND an API key present. When used, the **audio leaves the machine** to the configured endpoint — disclosed here and in the stat notes. Local backends are always tried first; cloud is the last resort.
- **Silence removal before ASR (X)**: before transcribing, the X path runs ffmpeg `silenceremove` to trim leading silence and collapse long interior/trailing gaps — this cuts Whisper-family hallucinated filler (e.g. `"Продолжение следует..."`) on silent lead-in/out. **ON by default**; `--keep-silence` (or `TRANSCRIPT_FETCHER_SILENCE_REMOVAL=0`) opts out; `_THRESHOLD`/`_MIN_GAP_SEC`/`_KEEP_SEC` tune it. Only **true silence** is removed (music/speech survive — a music-only intro can still trigger filler, see KNOWN_ISSUES TF-X-6). Never fatal: ffmpeg absent or a filter failure transparently falls back to the original audio. The stat `notes` record what was stripped (`silence-removal: stripped ~Ns ...`); the original media is kept for the ffprobe duration fill.
- **Secrets**: The API key is read from `OPENAI_API_KEY` / `TRANSCRIPT_FETCHER_OPENAI_API_KEY` or a skill-local `.env`. A `.env` is loaded **only** at the CLI entry point and is **refused** if it is a symlink or not `chmod 600` (group/world-readable). The key is sent **only** in an HTTP `Authorization` header — never on a command line, never logged. `.env` is git-ignored; only `scripts/.env.example` (placeholders) is committed.
- **Per-host cookies (`~/.transcript-fetcher/`)**: cookies for auth-walled media resolve (after an explicit `--cookies-file`) from a skill-local home folder — mirrors the `html` skill's `~/.html`. An `auth-map.json` (`--auth-map` / `TRANSCRIPT_FETCHER_AUTH_MAP` / `~/.transcript-fetcher/auth-map.json`) maps a host to its `{cookies_file}`, or the convention `~/.transcript-fetcher/<host>-cookies.txt` is used. Host match is **label-boundary** (a key `x.com` matches `x.com`/`*.x.com`, never `evil-x.com`); auth-map and convention files are **hardened** (symlink-reject + `0600`). The resolved Netscape cookies.txt feeds yt-dlp's `--cookies` (and Skool's opener). `--cookies-from-browser BROWSER` loads cookies straight from a local browser via yt-dlp (opt-in — reads the browser's cookie store).
- **Temp-file hygiene**: For X media, all intermediates (audio, VTT, info.json, `.part`, `.m3u8`, fragments) live under one tempdir removed in a `finally` block even on error — nothing is left behind.
- **Auth credentials**: `--cookies-file <path>` accepts a Netscape `cookies.txt` and is **ALWAYS OPTIONAL** for every source. The file is read once at startup, never copied or re-emitted. For Skool, public communities (e.g. `zero-one`) serve lessons without auth; private / paid communities respond with HTTP 401/403 and the user then needs to supply cookies. YouTube/Vimeo optionally forward the file to yt-dlp's `--cookies` for age-gated or unlisted videos. The skill **never blocks on missing cookies up-front** — it tries the fetch and surfaces a `SourceAuthError` (exit 5) only if the source returns 401/403.

## 6. Validation Evidence

- **Local verification**:
  ```bash
  cd skills/transcript-fetcher
  ./scripts/.venv/bin/python -m unittest discover -s scripts/tests
  ```
  All offline tests must pass without network. The end-to-end network test is gated behind `TRANSCRIPT_FETCHER_E2E=1`.
- **Skill-validator (structural)**:
  ```bash
  python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/transcript-fetcher
  ```
- **Skill-validator (security)**:
  ```bash
  python3 .claude/skills/skill-validator/scripts/validate.py skills/transcript-fetcher
  ```
- **Expected evidence**: Both validators exit 0; unittest reports `OK`.

## 7. Instructions

### Step 1: Verify environment

If `scripts/.venv/` does not exist, run `bash scripts/install.sh` first.
The install script is idempotent — safe to re-run.

### Step 2: Choose mode

| Input | Mode | Command form |
| --- | --- | --- |
| Single URL | `single` | `fetch.py <URL> --out path.txt` |
| List of URLs in a file | `batch` | `fetch.py --batch urls.txt --out-dir dir/` |

### Step 3: Pick a fallback strategy

Default is `--lang ru --prefer manual`. This tries:

1. `manual:ru` — user-uploaded Russian subtitles (highest quality).
2. `auto:ru-orig` — YouTube auto-captions of the original Russian audio (good).
3. `auto:ru` — YouTube auto-translation TO Russian (often noisy if speech was in another language).
4. `auto:en` — English auto-captions as last resort (will set `quality_flag = english_auto_translation`).

For non-Russian content, pass `--lang en` (or another ISO code). For
non-Russian languages the `lang-orig` step is skipped — it is a YouTube
quirk that mainly matters for non-English speech.

### Step 4: Run the CLI

Capture stdout (it carries the JSON stat). Read the stat to confirm
which track was used:

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://youtu.be/NSVTpCfBMK8" \
    --out /tmp/talk.txt
# stdout: {"source":"youtube","url":"...","chosen_track_kind":"auto","chosen_track_lang":"ru-orig", ...}
```

### Step 5: Inspect quality

Open the generated `<out>.txt.stat.json`. If `quality_flag` is set
(currently only `"english_auto_translation"`), surface a warning to
the user before passing the transcript to a downstream summarizer:

> ⚠️ TRANSCRIPT QUALITY: only English auto-translation was available
> for this URL. Idioms, proper names, and technical terms may be
> distorted. Consider asking the user for a manual transcription.

### Step 6: Hand off

The clean `.txt` is now ready for `summarizing-meetings` or any other
downstream consumer. Pass the path; do not paste the contents inline
(transcripts are often large).

## 8. Workflows

```text
- [ ] Verify scripts/.venv/ exists (run install.sh otherwise)
- [ ] Decide single vs batch mode
- [ ] Run fetch.py with the chosen language and preference
- [ ] Read the JSON stat sidecar
- [ ] Surface quality_flag warning if set
- [ ] Hand .txt path to downstream skill
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Always read the stat sidecar after fetching | Trust the .txt without checking which track was used |
| Prefer `ru-orig` over `ru` for Russian content | Pick the first track that returns text |
| Pass batch URLs through a file | Loop the CLI shell-side with arbitrary URLs |
| Surface `quality_flag` in any user-visible output | Silently downgrade to English auto-translation |
| Use `--json-errors` in CI/automation pipelines | Parse free-form stderr |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "yt-dlp is on `$PATH` so I can just call it" | The skill invokes `python -m yt_dlp` from the per-skill venv. The system `yt-dlp` may be a different version with different output. |
| "The `>>` markers are clutter" | They are paragraph breaks for speaker turns. Downstream summarizers attribute statements by them. |
| "Rolling-caption dedup is overkill, just keep the longest cue" | The dedup IS keeping the longest cue. Without it, the same sentence would appear 3-4 times. |
| "I'll add a Vimeo adapter inline in fetch.py" | Add it as `scripts/sources/vimeo.py`. Each source is its own file. |

## 10. Examples

See `examples/`:

- `example_input_url.txt` — batch input format.
- `example_output_plain.txt` — what a cleaned transcript looks like (excerpt).
- `example_output_stat.json` — what the stat sidecar contains.

## 11. Resources

- `scripts/fetch.py` — CLI entry point.
- `scripts/sources/youtube.py` — YouTube adapter (yt-dlp orchestration + fallback ladder + description path).
- `scripts/sources/vimeo.py` — minimal Vimeo adapter (yt-dlp).
- `scripts/sources/x.py` — X.com / Twitter adapter (captions-first → ASR; the `XTranscriptProvider`).
- `scripts/sources/_ytdlp_media.py` — shared yt-dlp plumbing (metadata probe, caption inspection, audio-minimal download, failure classifier) reused by X and any future yt-dlp source.
- `scripts/sources/_log.py` — debug-only stage logger (stderr, gated on `--debug`).
- `scripts/sources/_auth.py` — `~/.transcript-fetcher/` per-host cookie resolution (auth-map + convention, hardened; mirrors the `html` skill's `~/.html`).
- `scripts/asr/` — pluggable ASR backend package: `_base.py` (the `ASRBackend` interface), `macwhisper.py`, `whisper_cli.py`, `whisper_cpp.py`, `openai_api.py` (opt-in cloud), `__init__.py` (priority registry + fallback chain).
- `scripts/_config.py` — skill-local `.env` loader (secrets-safe) + typed config accessors (endpoints/models/tool paths).
- `scripts/.env.example` — config/secret template (copy to `.env`, `chmod 600`).
- `scripts/install_components.py` — detect / guide / install the optional ASR components.
- `scripts/sources/skool.py` — Skool lesson adapter (cookies.txt + Next.js scrape + embed delegation).
- `scripts/sources/_vtt_to_text.py` — pure-Python WebVTT cleaner.
- `scripts/sources/_captions.py` — multi-format caption → text dispatch (SRT/TTML/DFXP build on the VTT cleaner; TTML XXE/billion-laughs guard).
- `scripts/sources/_stat.py` — shared `TranscriptStat` + sidecar writer + error classes.
- `scripts/sources/_description.py` — `.description.md` writer (YAML frontmatter + Markdown body).
- `scripts/sources/_cookies.py` — Netscape cookies.txt loader + authenticated opener.
- `scripts/sources/_prosemirror.py` — ProseMirror/TipTap v2 JSON → Markdown for Skool lesson bodies.
- `scripts/install.sh` — venv bootstrap.
- `scripts/requirements.txt` — pinned deps (single source of truth for the yt-dlp version range).
- `scripts/tests/` — offline unit tests + opt-in E2E network test.
- `scripts/tests/_sanitize_fixture.py` — utility for scrubbing PII from Skool HTML snapshots before they become fixtures.
- `references/youtube_caption_format.md` — what `>>`, `&gt;`, rolling captions, and `ru-orig` actually mean.
- `references/fallback_policy.md` — the language ladder and why it is in this order.
- `references/supported_sources.md` — current and planned source slots.
- `references/skool_adapter.md` — Skool auth flow, schema notes, embed delegation rules.
- `references/description_metadata.md` — `.description.md` format for YouTube and Skool.
- [`docs/Manuals/transcript-fetcher_manual.md`](../../docs/Manuals/transcript-fetcher_manual.md) — user-facing manual with quick reference, troubleshooting, and composition recipes.

## 12. Composition

- **Composes well with `summarizing-meetings`**: run `transcript-fetcher` first to get a clean `.txt`, then pass that file to `summarizing-meetings` for a structured Markdown summary. The two skills are intentionally separate — fetching is a deterministic file operation; summarizing is a prompt-first reasoning task.
