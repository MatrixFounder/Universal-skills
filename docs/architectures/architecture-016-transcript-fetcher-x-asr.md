# Architecture 016 — `transcript-fetcher`: X.com source + pluggable ASR backend

> **Subsystem:** `transcript-fetcher` skill (Apache-2.0).
> **Builds on:** v1.1 source-adapter architecture (`youtube`/`vimeo`/`skool`, shared
> `TranscriptStat` + `_vtt_to_text` + `_description`).
> **Task:** TASK 026 (`docs/tasks/task-026-transcript-fetcher-x-asr.md`) — implemented;
> **+ TASK 029** (`docs/TASK.md`, HLS hardening + `doctor`, §10) — design.
> **Status:** §1–§9 implemented (TASK 026 + follow-ups); §10 design (pre-merge).

---

## 1. Purpose & Scope

Add **X.com (Twitter)** — native status video **and** Broadcasts/Spaces — as a first-class
source, and introduce an **ASR (speech-to-text) fallback** so caption-less media still yields
a transcript. Two design constraints dominate:

1. **Caption-first, ASR-only-when-needed** — reuse pre-existing subtitle text whenever it
   exists (fast, high quality); transcribe audio only as a fallback.
2. **Two clean, orthogonal extension points** — a **source provider** (the X adapter) and a
   **pluggable ASR backend** — neither of which special-cases the core, so that future
   platforms (Vimeo-native-ASR, TikTok, Twitch) and future engines drop in without touching
   the pipeline.

**In scope:** `scripts/sources/x.py`, a new `scripts/asr/` backend package, a shared
`scripts/sources/_ytdlp_media.py` helper extracting reusable yt-dlp plumbing, a debug logger,
`fetch.py` dispatch wiring, stat-schema extension (`transcript_origin`), exit-code 7
(`MissingDependencyError`), tests, docs.

**Out of scope:** browser automation; refactoring the 3 existing adapters' internals;
caption timecode preservation in the `.txt`; making cloud ASR automatic.

---

## 2. Functional Architecture

### 2.1 The two abstractions (the conflation the spec resolves)

The user's prose calls both X and the ASR engines "providers". They are **two different
abstractions** and we keep them separate:

| Abstraction | Question it answers | Interface | Implementations |
|---|---|---|---|
| **Source adapter** | "How do I get a transcript for *this platform's* URL?" | `fetch_<source>_transcript(url, out_path, *, …) -> TranscriptStat` (existing v1.1 contract) | `youtube`, `vimeo`, `skool`, **`x` (new)** |
| **ASR backend** | "How do I turn *this audio file* into text?" | `ASRBackend.available() -> bool` + `.transcribe(audio, *, lang) -> ASRResult` (new) | `macwhisper`, `whisper-cli`, `whisper-cpp`, `openai-api` |

The X adapter is one **source**; it *consumes* the ASR abstraction internally. The ASR
abstraction is platform-agnostic — any future source can call it.

### 2.2 Control flow (X adapter)

```
fetch.py _detect_source(url) == "x"
        │
        ▼
fetch_x_transcript(url, out_path, …)            [scripts/sources/x.py]
        │  log("Detected X media")
        ▼
_ytdlp_media.probe_metadata(url)                [yt-dlp -J, one call]
        │  log("Fetching metadata")
        ├── captions present for a ladder lang? ──── YES ──┐
        │                                                  ▼
        │                                   _ytdlp_media.download_subtitle(...)   (existing VTT path)
        │                                   log("Embedded captions found / Downloading captions")
        │                                   _vtt_to_text.vtt_file_to_plain_meta(...)
        │                                   transcript_origin = "embedded-captions"
        │                                   chosen_track_kind = "manual"|"auto"
        │                                                  │
        └── NO ──────────────────────────────────────────►│
                 │  ASR path                                │
                 ▼                                          │
        _ytdlp_media.download_audio(url, workdir)           │
        log("Downloading audio")                            │
                 │  (bestaudio if ffmpeg else smallest muxed)│
                 ▼                                          │
        asr.transcribe_with_fallback(media, lang)           │
        log("Using MacWhisper" / "Using Whisper CLI" / …)   │
        transcript_origin = backend.name                    │
        chosen_track_kind = "asr"                           │
                 │                                          │
                 └──────────────┬───────────────────────────┘
                                ▼
                 write out_path.txt  +  TranscriptStat
                 finally: shutil.rmtree(tempdir)   log("Cleaning temporary files" / "Finished")
```

### 2.3 ASR registry & fallback (B1/B2)

```
asr.select_backend(allow_cloud) ─► iterate REGISTRY in priority order,
                                    return first backend whose available() is True
REGISTRY = [MacWhisper, WhisperCLI, WhisperCpp, OpenAIAPI]   # OpenAIAPI.available() ⇒ allow_cloud & key

asr.transcribe_with_fallback(audio, *, lang, allow_cloud):
    tried = []
    for backend in REGISTRY where available():
        try: return backend.transcribe(audio, lang=lang)   # ASRResult(text, backend_name, language?)
        except ASRError as e: tried.append((backend.name, e)); continue
    if no backend available at all: raise MissingDependencyError(exit 7, remediation hint)
    else (all available ones failed): raise TranscriptFetchError(exit 3, tried summary)
```

`available()` is cheap and side-effect-free: `shutil.which(<bin>)` (+ env/flag check for
cloud). No heavy import or network at module import time (mirrors the deferred-`yt_dlp`-import
discipline in `youtube.py`).

---

## 3. System Architecture

### 3.1 File layout (new = ✚, edited = ✎, untouched = ·)

```
skills/transcript-fetcher/scripts/
  fetch.py                      ✎  +X hosts in _SOURCE_BY_HOST, +x dispatch branch,
                                    +--debug/--asr-* flags, +MissingDependencyError mapping (exit 7)
  sources/
    __init__.py                 ✎  doc note: x adapter + asr consumption
    x.py                        ✚  XTranscriptProvider: caption-first → ASR
    _ytdlp_media.py             ✚  reusable yt-dlp helpers (probe / captions / audio)
    youtube.py                  ·  (X imports its yt-dlp helpers, like vimeo does — no edits)
    vimeo.py  skool.py          ·
    _stat.py                    ✎  +transcript_origin field; +MissingDependencyError class
    _vtt_to_text.py _description.py _cookies.py _prosemirror.py  ·
    _log.py                     ✚  debug stage logger (stderr, gated)
  asr/                          ✚  NEW package — the ASR backend abstraction
    __init__.py                 ✚  REGISTRY + select_backend + transcribe_with_fallback
    _base.py                    ✚  ASRBackend ABC, ASRResult, ASRError
    macwhisper.py               ✚  mw transcribe <file>
    whisper_cli.py              ✚  whisper <file> --output_format txt …
    whisper_cpp.py              ✚  whisper-cli/main -f <wav> -otxt …  (needs ffmpeg → wav)
    openai_api.py               ✚  opt-in cloud (OPENAI_API_KEY + --asr-allow-cloud)
    tests/                      ✚  backend probe/priority/fallback unit tests (subprocess mocked)
  tests/
    test_x_adapter.py           ✚  URL detection, caption-vs-ASR routing (yt-dlp+asr mocked)
    fixtures/x_broadcast_info.json ✚  sanitized yt-dlp -J snapshot (no captions)
    fixtures/x_status_info_captions.json ✚  status with automatic_captions
  requirements.txt              ·  (NO new pip dep — yt-dlp only; ASR engines are external)
  install.sh                    ✎  print hints for optional ASR tools (mw/whisper/ffmpeg) — does NOT install them
```

### 3.2 Why a shared `_ytdlp_media.py` (C5 extensibility)

Today `vimeo.py` reuses yt-dlp helpers by **importing private functions from `youtube.py`**
(`_yt_dlp_command`, `_classify_failure`, `_find_new_vtt`, …). That works but couples siblings
to youtube's internals. For the X adapter — which needs both the **caption path** *and* a new
**audio-download path** — we lift the genuinely shared, source-neutral primitives into
`_ytdlp_media.py`:

- `yt_dlp_argv(bin)` — base argv (`python -m yt_dlp` from venv).
- `probe_metadata(url, *, timeout, cookies) -> dict|None` — single `-J` call; the one source
  of truth for "does this have captions / what formats / is it private".
- `caption_langs(info) -> {"manual": [...], "auto": [...]}` — read `subtitles` /
  `automatic_captions` keys.
- `download_subtitle(...)` — the existing `_try_download_subtitle` logic, source-neutral.
- `download_audio(url, workdir, *, prefer_audio_only, timeout, cookies) -> Path` — **new**:
  `-f bestaudio/best -x --audio-format m4a` when ffmpeg present, else
  `-f <smallest-with-audio>` muxed download for a video-capable backend. Returns the media file.
- `classify_failure(stderr)` — hard/rate-limit/auth phrase classifier. **Imports** the base
  pattern tuples (`_HARD_FAILURE_PATTERNS`, `_RATE_LIMIT_PATTERNS`) from `youtube.py` and extends
  them with X-specific phrases (suspended/protected/unavailable broadcast) — so the base set has
  one source of truth and cannot silently fork (arch-review #4). Adds an **auth** bucket
  (protected/suspended/age-gated → `SourceAuthError`).
- `extract_x_id(url)` — pull the status id (`…/status/<id>`) or broadcast id
  (`…/i/broadcasts/<id>`). The batch-mode filename resolver in `fetch.py` becomes source-aware
  (tries youtube→vimeo→x id extractors) so X URLs in batch mode get id-named outputs instead of a
  slugified URL (task-review #1 / arch-review #2).

`youtube.py`/`vimeo.py` stay byte-stable for v1 (they keep their local copies; we do **not**
force-refactor working, tested adapters — honest, low-blast-radius). The new module is the
**forward** path every *future* source (and X today) builds on. This is the documented
extension surface.

> **Decision (recorded):** v1 does not retrofit youtube/vimeo onto `_ytdlp_media.py` to avoid
> regressing three tested adapters. A future `transcript-fetcher-Nb` may converge them; tracked
> as honest-scope §7.

### 3.3 ffmpeg audio strategy (A4 — REQUIRED for HLS; see correction below)

The format is always selected deterministically with yt-dlp's built-in `worst*` selectors
(`-f "worstaudio/worst[acodec!=none]/worst"`) — the smallest variant that still carries audio,
never a literal instance-specific id like `replay-600`, and **never** combined with a
`-S +size/+br` sort (a `+` sort inverts `worst` into picking the *largest* — caught by the live
probe).

| ffmpeg present? | Source kind | Strategy |
|---|---|---|
| yes | any | smallest variant + `-x --audio-format m4a` → clean audio-only `media.m4a` (valid for any backend) |
| no | **HLS-only** (X Broadcasts/Spaces) | **fail fast → `MissingDependencyError` (exit 7)** with a "install ffmpeg" remediation, BEFORE the large download |
| no | progressive (direct mp4) | smallest muxed file as-is → hand to a video-capable backend (MacWhisper) |
| (any) | wav-only backend (whisper.cpp) | `available()` → **False** without ffmpeg + a model; never selected |

> **CORRECTION (live-E2E finding, supersedes the original "ffmpeg-optional" assumption):**
> yt-dlp's native HLS downloader *does* run without ffmpeg, but the file it produces by
> concatenating fragments is **not a valid playable container** — MacWhisper/AVFoundation
> rejects it (`Error: cannot open (mp4)`). So for an **HLS source** (which X Broadcasts/Spaces
> always are), **ffmpeg is required** to remux/extract a valid audio file. The adapter therefore
> probes `is_hls_only(info)` and, when ffmpeg is absent, **fails fast with exit 7** instead of
> downloading ~200 MB only to fail at the ASR step. ffmpeg stays *optional* only for non-HLS
> progressive media and the caption path.

**Output-path discipline (security, arch-review #3):** the audio download uses a **fixed**
output template `--output <workdir>/media.%(ext)s` (NOT `%(id)s.%(ext)s`, whose stem derives
from untrusted `info["id"]`). After download we glob `media.*` in the tempdir, `resolve()` the
result, and **assert `media.resolve().parent == workdir.resolve()`** before handing the path to
any ASR backend — closing the path-escape / TOCTOU gap on the yt-dlp-authored filename.

---

## 4. Data Model

### 4.1 `TranscriptStat` extension (C1, backward-compatible)

```python
@dataclass
class TranscriptStat:
    source: str                       # platform — now also "x"
    ...
    chosen_track_kind: Optional[str]  # "manual" | "auto" | "skool_manual" | "asr"  (+"asr")
    ...
    transcript_origin: Optional[str] = None   # NEW: "embedded-captions" | "macwhisper"
                                              #      | "whisper-cli" | "whisper-cpp" | "openai-api"
    asr_backend: Optional[str] = None         # NEW: redundant convenience == backend.name (None for caption path)
    asr_model: Optional[str] = None           # NEW: backend-reported model id, if any
```

All new fields are `Optional` with `None` defaults → pre-existing consumers and the 3 adapters
are unaffected (they never set them). `source` stays the **platform**; `transcript_origin`
carries the spec's requested provenance (`source: macwhisper` in the user's words maps here).

### 4.2 `ASRResult` (new)

```python
@dataclass
class ASRResult:
    text: str
    backend_name: str          # "macwhisper" | ...
    language: Optional[str] = None
    model: Optional[str] = None
```

### 4.3 Error taxonomy & exit codes

| Condition | Exception | Exit | Origin |
|---|---|---|---|
| usage / bad flag / bad X URL shape | `UsageError`/`ValueError` | 2 | existing |
| no transcript producible (no captions AND ASR empty/failed) | `TranscriptFetchError` | 3 | existing (reused) |
| partial batch failure | `BatchPartialFailure` | 4 | existing |
| private/protected/suspended X media | `SourceAuthError` | 5 | existing (reused) |
| HTTP 429 | `SourceRateLimitError` | 6 | existing (reused) |
| **missing required tool** (yt-dlp absent · ffmpeg required but absent · NO ASR backend available) | **`MissingDependencyError`** | **7** | **NEW** |
| unexpected | catch-all | 1 | existing |

`MissingDependencyError` carries a `remediation` string (e.g. "Install MacWhisper (`mw`), or
run with `--asr-allow-cloud` and set `OPENAI_API_KEY`.").

> **Binding (arch-review #1):** `MissingDependencyError(RuntimeError)` is **NOT** a subclass of
> `TranscriptFetchError`. `fetch.py` must add an explicit `except MissingDependencyError → exit 7`
> clause **before** the generic `except Exception` in **both** the single-URL and batch paths,
> or it is silently swallowed as exit 1.

---

## 5. Interfaces

### 5.1 `ASRBackend` (Python ABC — the spec's `TranscriptProvider`)

```python
class ASRBackend(abc.ABC):
    name: str                          # class attribute, stable id
    @abc.abstractmethod
    def available(self) -> bool: ...   # cheap probe; no network/heavy import
    @abc.abstractmethod
    def transcribe(self, audio_path: Path, *, lang: Optional[str] = None) -> ASRResult: ...
```

`__init__(self, *, allow_cloud=False, model=None)` lets the registry pass policy without the
backends reaching into globals.

### 5.2 X adapter (source contract — unchanged shape)

```python
def fetch_x_transcript(
    url: str, out_path: Path, *,
    fallback_ladder: Iterable[tuple[str,str]] = DEFAULT_FALLBACK_X,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    with_description: bool = False,
    description_only: bool = False,
    # ASR policy (threaded from CLI; defaults keep non-X callers oblivious)
    asr_allow_cloud: bool = False,
    asr_model: Optional[str] = None,
    debug: bool = False,
) -> TranscriptStat: ...
```

### 5.3 CLI additions (`fetch.py`)

- `--debug` (also `TRANSCRIPT_FETCHER_DEBUG=1`) — stage logging to stderr.
- `--asr-allow-cloud` — permit the opt-in cloud backend (needs `OPENAI_API_KEY`).
- `--asr-model <engine:model-id>` — forwarded to the chosen backend (e.g. MacWhisper `--model`).
- Dispatch: `for h in ("x.com","www.x.com","mobile.x.com","twitter.com","www.twitter.com",
  "mobile.twitter.com"): _SOURCE_BY_HOST[h] = "x"`; one `elif source == "x":` branch.

### 5.4 Debug logger (`_log.py`)

```python
def debug_log(msg: str, *, enabled: bool) -> None:
    if enabled: sys.stderr.write(f"[transcript-fetcher] {msg}\n"); sys.stderr.flush()
```

Stage strings exactly as the spec lists them. Pure stderr — stdout JSON contract is preserved.

---

## 6. Cross-cutting concerns

- **Temp cleanup (C2):** one `tempfile.mkdtemp(prefix="transcript-fetcher-x-")` per call;
  audio, VTT, info.json, `.part`, `.m3u8`, fragments all live under it; `finally:
  shutil.rmtree(workdir, ignore_errors=True)`. A regression test asserts the dir is gone and
  no stray files were created in CWD. Caller-supplied `workdir` is *not* auto-removed (matches
  youtube/vimeo convention).
- **Security:** `--` terminates yt-dlp flag parsing (reuse existing pattern) so a `-`-leading
  URL can't smuggle flags; ASR backends invoke external bins via **argv arrays** (never a
  shell string); the audio path passed to `mw`/`whisper` is an mkstemp path inside our
  tempdir (no user-controlled filename injection). Cloud backend egress is opt-in + disclosed.
  **Adversarial-review hardening (post-implementation):** the cloud multipart encoder
  **rejects CRLF** in any field value (`--asr-model`/`--lang`/filename) — closing a header/part
  injection vector; the audio upload is **size-capped** (`openai_max_upload_bytes`, default
  25 MiB, configurable) so an over-limit file fails fast instead of buffering; the HTTP
  response read is **bounded** (64 MiB) so a hostile/misconfigured endpoint can't OOM the
  client; and `MissingDependencyError` is handled in **both** the single-URL and batch paths
  (batch surfaces the `remediation` hint per-URL while still aggregating to exit 4).
- **No new pip dep (C6 / AC-6):** ASR engines are optional **external** tools, probed at
  runtime — consistent with the skill's "don't add ffmpeg/heavy deps" red flag. `requirements.txt`
  stays `yt-dlp` only. `install.sh` only *prints hints* for `mw`/`whisper`/`ffmpeg`.
- **Logging discipline:** without `--debug`, success path writes nothing to stderr; stdout is
  exactly one JSON stat line (batch: one per URL).
- **License:** transcript-fetcher is Apache-2.0; nothing here changes that (no proprietary
  code embedded). No `THIRD_PARTY_NOTICES.md` change for pip deps; if cloud backend is used it
  hits the OpenAI API (a service, not a bundled dep).

---

## 7. Honest Scope & Open Questions

- **HS-1 — youtube/vimeo not retrofitted onto `_ytdlp_media.py`.** To avoid regressing three
  tested adapters, v1 leaves them importing helpers from `youtube.py`. The shared module is the
  forward extension surface; convergence is a future `-b` follow-up. Not a bug — a bounded blast
  radius decision.
- **HS-2 — whisper.cpp needs ffmpeg.** Without ffmpeg it cannot make the 16 kHz WAV it requires,
  so its `available()` returns False on a no-ffmpeg host. Documented, not silently skipped.
- **HS-3 — cloud ASR is opt-in & egresses audio.** `--asr-allow-cloud` + `OPENAI_API_KEY`
  required; the target audio leaves the machine. Disclosed in SKILL.md + a stat note; never
  auto-selected. (Mirrors the html skill's remote-tier privacy posture.)
- **HS-4 — `mw` model is the user's MacWhisper-selected default** unless `--asr-model` is
  passed. We do not enumerate or validate models (MacWhisper owns that).
- **HS-5 — caption SRT/TTML → HANDLED (TF-X-4).** The X path now asks yt-dlp for a *preference
  list* `vtt/srt/ttml/best` and parses the result format-aware (`sources/_captions.py`): SRT is
  normalised into the VTT machinery (comma→dot; all dedup/`>>` handling reused), TTML/DFXP via
  stdlib `ElementTree` with a DTD/entity-declaration refusal (XXE / billion-laughs guard) and a
  size cap. Exotic YouTube `srv*` XML is still unparsed → ASR (residual).
- **HS-6 — X login walls.** Protected/age-gated/some-Broadcast media needs `--cookies-file`
  (existing mechanism); without it → `SourceAuthError` (exit 5). We do not mint sessions
  (that's the html skill's job).
- **OQ-1 — duration on Broadcasts.** yt-dlp may report `duration: None` for replays; the stat's
  `duration_sec` is then `None` (acceptable; not derived from the media to avoid an ffprobe dep).

## 8. Follow-up additions (TF-X-5 handled)

Three additions closed most of honest-scope TF-X-5 (see `docs/KNOWN_ISSUES.md`):

- **`--max-duration-min N`** — clips the ASR download to the first N minutes via yt-dlp
  `--download-sections "*0-<N*60>"` (inside the ffmpeg branch of `download_audio`). Bounds a
  long Broadcast/Space in both bytes and ASR time. Live-proven: a 1-min clip ran in ~19 s.
- **`~/.transcript-fetcher/` per-host cookies** (`sources/_auth.py`) — mirrors the `html`
  skill's `~/.html` auth-map: a hardened (0600 / symlink-reject) `auth-map.json`
  (host → `{cookies_file}`, label-boundary match) or the `~/.transcript-fetcher/<host>-cookies.txt`
  convention; resolved in `_fetch_one` (source-agnostic) → feeds yt-dlp `--cookies`. Plus
  `--cookies-from-browser BROWSER` (yt-dlp native, X path).
- **ffprobe duration fill** (`_ytdlp_media.probe_media_duration`) — when the media is downloaded
  for ASR and ffmpeg is present, `stat.duration_sec` is derived via ffprobe (ships with ffmpeg —
  no new dep). Live-proven (`duration_sec: 59` on a 1-min clip).

Residual (not fixable here): MacWhisper's `mw transcribe` has no language flag — `--lang` is
forwarded only to whisper/whisper.cpp/cloud.

## 9. Follow-up additions (TF-X-4 + TF-X-6 handled)

- **Multi-format captions (TF-X-4)** — `_ytdlp_media.download_captions` requests the format
  preference list `vtt/srt/ttml/best` (vs VTT-only) and `sources/_captions.py` converts whichever
  text track arrived: SRT is normalised into the VTT cleaner (comma→dot timestamps; all
  rolling-caption dedup + `>>`-turn handling reused), TTML/DFXP via stdlib `ElementTree`. The TTML
  path **refuses a `<!DOCTYPE`/`<!ENTITY` declaration before parse** (XXE / billion-laughs guard,
  no `defusedxml` dep) and is size-capped; a refusal/parse error is a note + fall-through to ASR,
  never a crash or silent empty. The new caption path runs in the shared forward-surface module
  (youtube/vimeo untouched — preserves HS-1). **Language-robust:** when the `--lang`-derived
  ladder matches no track but the post carries captions in another language, the X adapter falls
  back to `pick_any_caption` (manual preferred over auto) before ASR, with a note — so a post
  whose only track is `manual en` is used under the default `--lang ru` (live-proven on
  `x.com/Av1dlive/status/2070507527213871594`).
- **Silence-removal preprocessing (TF-X-6)** — `_ytdlp_media.remove_silence` runs ffmpeg
  `silenceremove` on the downloaded media before ASR (trim leading silence; collapse interior/
  trailing gaps > `min_gap` to `keep`, gated at `threshold`). This removes the dead air where
  Whisper-family filler hallucination originates. ON by default (`--keep-silence` /
  `TRANSCRIPT_FETCHER_SILENCE_REMOVAL=0` opts out; `_THRESHOLD`/`_MIN_GAP_SEC`/`_KEEP_SEC` tune).
  Never fatal: ffmpeg-absent / filter failure / "no silence found" all fall back to the original
  media; the original is also what feeds the ffprobe duration fill. **Residual:** only true
  silence is removed — a *music-only* intro survives and can still trigger filler (engine-level).
  Verified by a gated real-ffmpeg test (`test_real_ffmpeg_strips_silence`: 10 s synthetic
  silence+tone+silence collapses to ≤ 5 s).

## 10. TASK 029 — HLS download hardening + `doctor` (spec S1–S6)

> **Amended after adversarial cycle 1 (2026-07-10):** four deltas layered onto
> the design below without changing its shape — (1) the media-timeout floor
> (§10.2) is now capped at 21600 s (6h) and derived from the
> `--max-duration-min`-clipped duration, not the full probed one; (2)
> `doctor`'s `remediation` (§10.3) now covers EVERY missing component (ffmpeg
> included) and is cloud-backend-aware for the no-local-ASR hint; (3) the
> transient-timeout remediation (§10.4) is also printed to stderr in non-JSON
> mode, and a media-download rate-limit additionally names
> `--concurrent-fragments`; (4) the auth cookie hint (§10.4) is derived from
> the failing URL's own host instead of a hardcoded `x.com`. All four config
> accessors also close a Unicode-digit crash class (`str.isdigit()`-true /
> `int()`-invalid characters like `'²'`) that could raise uncaught out of a
> plain fetch run.
>
> **Amended after adversarial cycle 3 (2026-07-10) — three residuals from the
> cycle-1 amendment above:** (1) §10.2's `--max-duration-min` budget clip now
> only applies when ffmpeg is present — cycle-1's fix clipped the budget
> whenever the flag was set, even on an ffmpeg-less box where the download
> itself is never actually clipped (`download_audio` only emits
> `--download-sections` inside its ffmpeg branch), which sized a premature
> timeout for a download that was really pulling the full media; (2) §10.3's
> "EVERY missing component" `remediation` contract is narrowed to ONLY
> flow-blocking gaps (yt-dlp / ffmpeg / no-ASR-capability-at-all) — it made
> `remediation == []` / `✓ Ready.` unattainable on any correctly-provisioned
> box short of all three local ASR engines installed simultaneously
> (impossible on Linux); non-blocking gaps (an alternative local ASR engine,
> or the no-local-ASR note on a cloud-configured box) now surface only as
> informational lines in the human report, never in `remediation`; (3) §10.4's
> host-derived auth cookie hint strips a `www.`/`mobile.` label before
> printing the convention path, but `_auth.resolve_cookies_file`'s convention
> lookup was unchanged — a dead end for 4 of the 6 documented X hosts. The
> resolver now carries the matching `www`/`mobile`/`m` label-stripped
> fallback (exact-host file still wins when both exist), so the hinted path
> always round-trips.

Origin: the 004-broadcast import (2026-07-09) — a ~70-min X Broadcast (2089 HLS fragments)
timed out on the **serial** media download (~120 KB/s) while `yt-dlp -N 16` pulled the same
media at ~2.2 MB/s (≈18×). Four design changes, all confined to the existing forward surface
(`_ytdlp_media.py` / `x.py` / `fetch.py` / `_config.py` / `install_components.py`);
youtube/vimeo/skool byte-stable (HS-1 preserved).

### 10.1 Parallel fragment download (S1)

`download_audio()` gains `concurrent_fragments: Optional[int]` and always emits
`--concurrent-fragments <N>` on the **media** argv (yt-dlp ignores it for single-file
progressive downloads — safe no-op). Resolution: CLI `--concurrent-fragments` >
`TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` (env/.env) > `DEFAULT_CONCURRENT_FRAGMENTS = 8`
(module constant, `_ytdlp_media.py`).

**Layered validation contract** (three distinct layers, per RTM R2b/R3b — do NOT collapse):

1. **CLI** `--concurrent-fragments <= 0` → **UsageError exit 2** (mirrors the existing
   `--timeout-sec` / `--asr-timeout-sec` / `--max-duration-min` validators in `fetch.py`).
2. **env/config** non-positive or malformed → silently fall back to the default **8**
   (config never crashes a run — the `_config` contract).
3. The resolved value is then **capped at 32** in `download_audio` (upper bound only in
   practice — neither upstream layer yields `< 1`; the `max(1, …)` guard is defensive).
   Bounded to avoid rate-limit trips (spec §Risks); `1` reproduces serial behaviour for
   A/B debugging.

The caption/subtitle argv paths are **unchanged** (single files today, per spec).

### 10.2 Split probe/media budgets (S2)

`--timeout-sec` (180 s default) stays the **probe + caption** per-attempt budget (≤60 s
socket). The media download gets its own budget resolved as: CLI `--media-timeout-sec`
(`<= 0` → UsageError exit 2) > `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC` (malformed → ignored) >
`media_timeout_for(duration_s)` — a pure helper in `_ytdlp_media.py` returning
`min(21600, max(600, duration_s × 4))` when the probe reported a positive, finite duration,
else **1800 s** (X Broadcasts commonly probe `duration: None`, closing OQ-1's practical gap).
`x.py` computes the effective budget once (it owns `info`) and passes it only to
`download_audio`; silence-removal and ASR keep their existing `asr_timeout_sec` budgets.

**Amended (adversarial cycle 1):** the derived floor is now bounded on BOTH ends:

1. **Upper cap — 21600 s (6h).** An uncapped `duration_s × 4` on a pathological/un-clipped
   probed duration (e.g. a 10-hour broadcast → 144000 s / 40h) turned the per-attempt budget
   into a multi-day hang ceiling that only yt-dlp's own (much shorter) socket-timeout would
   ever actually bound in practice. A per-attempt timeout exists to cap a HANG, not to model
   the expected wait — 6h is generous headroom over any realistic single-attempt media pull.
2. **Clip-awareness.** `--max-duration-min` clips the ACTUAL download (`download_audio`'s
   `--download-sections`), but the pre-amendment budget derived from the FULL probed
   duration regardless — a `--max-duration-min 10` run against a 6-hour broadcast got a
   budget sized for the whole 6 hours instead of the ~10 minutes actually being pulled. `x.py`
   now computes `effective_duration = min(probed_duration, max_duration_min × 60)` (when the
   clip is active and the probed duration is a positive number) BEFORE calling
   `media_timeout_for`. An explicit CLI/env `--media-timeout-sec` still wins unchanged over
   both the cap and the clip — it is the operator's deliberate override.

`media_timeout_for` also now coerces `duration_s` defensively (`float()` in a try/except) —
`Infinity`/`NaN` round-trip through yt-dlp's `-J` JSON on a pathological extractor value, and
a caller may hand in a numeric string; unparseable/non-finite/non-positive/`None` all fall
back to 1800 s rather than raising `OverflowError`/`TypeError`. A FINITE but astronomical
`duration_s` (e.g. `1e308`) is also handled (cycle-3 INFO fix): once `d >= 5400` the 21600 s
cap is returned directly, before ever computing `d * 4` — for `d` near the float max that
product overflows to `inf`, and `int(inf)` raises `OverflowError`.

**Amended (adversarial cycle 3) — clip conditioned on ffmpeg.** Step 2 above clipped the
budget whenever `--max-duration-min` was set and the probed duration was positive — but
`download_audio`'s `--download-sections` (the clip that ACTUALLY bounds the download) is only
emitted inside its `ffmpeg_available()` branch (§10.1/x.py). Without ffmpeg, a progressive
(non-HLS) X video is downloaded in full regardless of `--max-duration-min`, so a budget sized
for the clip was premature — `x.py` now gates the clip on `ytm.ffmpeg_available()` too: no
ffmpeg → `effective_duration` stays the FULL probed duration, matching what is actually
downloaded.

### 10.3 `fetch.py doctor` (S3) — readiness without $PATH guessing

Positional subcommand dispatched **before** the normal argparse contract (additive; `doctor`
is not a valid URL, so no collision). Reports: resolved interpreter (`sys.executable`),
in-venv flag, yt-dlp presence + version, ffmpeg + each ASR backend, cloud opt-in state.

**Import-free by construction (resolves the `_components()` contradiction):**
`install_components._have_yt_dlp()` is **refactored** to probe via
`importlib.metadata.version("yt-dlp")` (distribution metadata, no module import) instead of
`import yt_dlp` — so `_components()` itself becomes import-free and the doctor **reuses the
whole `_components()` list** (one source of truth, no logic fork). The doctor deliberately
never uses `shutil.which("yt-dlp")` (vendored in the venv — the false-negative that caused
the 004 detour). Exit **0** when yt-dlp (the only hard dep) is present, **7** otherwise;
`--json` emits a stable envelope `{v, interpreter, in_venv, ready, components:{…},
remediation:[…]}`. No network, no heavy imports — the probe stays cheap (spec §Risks).
**Secrets discipline:** the cloud row reports only a **boolean** key-presence
(`key_present: true|false`) — never the key value, in either human or `--json` output
(preserves `_config`'s never-log-secrets invariant).

**Amended (adversarial cycle 1) — remediation contract widened.** The original design built
`remediation` only from `required: True` components (yt-dlp alone) plus a single no-local-ASR
hint. This let a missing **ffmpeg** — labelled "REQUIRED for X Broadcast/Space ASR" in its own
row, and a hard `exit 7` for any HLS-only X source — produce `remediation: []` and a bare
`✓ Ready.` human line, a false all-clear for the exact pre-flight scenario `doctor` exists to
catch. The contract now:

1. Iterates EVERY component in `_components()` (not just `required: True`) and, for each
   `present: False`, appends `"<key> — <install_hint>"` to `remediation` — ffmpeg gets bespoke
   wording ("needed for X Broadcast/Space (HLS) ASR and by whisper/whisper.cpp at runtime")
   since it back-stops BOTH the HLS path and the whisper-family backends despite being an
   optional (`required: False`) component itself.
2. The no-local-ASR hint is **cloud-aware**: when the synthetic `cloud` row already resolves
   (`key_present AND allow_cloud`), the hint is replaced with an informational note
   ("caption-less media will use the cloud backend") instead of demanding a redundant local
   install; otherwise it states the consequence explicitly ("caption-less X media
   (Broadcasts/Spaces) will exit 7").
3. Human mode now distinguishes three states: `✓ Ready.` (remediation empty — nothing to
   report), `✓ Core ready (yt-dlp present) — gaps above may block specific flows.`
   (yt-dlp present, `remediation` non-empty — the CLI itself works but a listed gap may bite a
   specific flow), or the bare `Remediation:` block with no extra summary line (yt-dlp absent
   — the block itself IS the failure output).

Exit semantics are UNCHANGED (`0` iff yt-dlp present, R5d) — a non-empty `remediation` with
`ready: true` means "usable, but gaps remain", not failure. The JSON envelope's KEYS are
unchanged (`{v, interpreter, in_venv, ready, components, remediation}`); only the population
of `remediation` widened.

**Amended (adversarial cycle 3) — narrowed to flow-blocking gaps.** The cycle-1 widening above
("EVERY missing component") over-corrected: on the flagship recommended box (yt-dlp + one
local ASR engine + ffmpeg — sufficient for every documented flow) it still emitted install
hints for the OTHER, unneeded local ASR engines, making `remediation == []` / `✓ Ready.`
unattainable except with all three local engines installed simultaneously (impossible on
Linux, where MacWhisper does not exist). `remediation` now contains ONLY the three
flow-blocking gap kinds — yt-dlp missing, ffmpeg missing, or NO ASR capability at all (no
local backend present AND NOT (cloud `key_present` AND `allow_cloud`)) — never an individual
missing ALTERNATIVE local ASR engine while ASR capability resolves elsewhere. Those
non-blocking gaps (including the no-local-ASR note on an already cloud-configured box) are
demoted to informational-only: an indented `→ <install_hint>` line under each missing
component's row in the human report (mirroring `install_components._print_report`), plus one
extra informational note line for the cloud-configured case — never JSON `remediation`. The
envelope's KEYS and exit semantics are unchanged; only the population of `remediation`
narrowed back down to genuinely flow-blocking gaps.

### 10.4 Transient-failure classification (S4) + cookie contract surfacing (S6)

`classify_failure()` gains a `"transient"` category scoped to the skill-authored
**audio-download** timeout message (`"timeout downloading audio"`); the probe timeout
(`"timeout probing metadata"`) is deliberately NOT transient (concurrency/media budget cannot
fix it). `_raise_for_failure` maps `"transient"` → `TranscriptFetchError` with a
`remediation` attr (mirrors `MissingDependencyError`) naming `--concurrent-fragments` /
`--media-timeout-sec`; `fetch.py` surfaces `details.remediation` in the JSON envelope for
single-URL and a top-level `remediation` field for batch records (mirroring the existing batch
`MissingDependencyError` record shape — the two modes intentionally use DIFFERENT envelope
shapes, not a shared `details.remediation`). Exit codes unchanged (3 / 4).
The auth branch names the cookie **refresh** path: the resolved cookies file when one fed
the request, else the convention path to create.

**Amended (adversarial cycle 1) — three deltas:**

1. **Ordering + match rule hardened.** `classify_failure` originally checked the transient
   substring FIRST (before auth/rate/hard) and matched anywhere in the string. Because the
   function is also fed raw yt-dlp stderr from the metadata probe / caption download / non-
   timeout download failures (a channel that can echo server-supplied free text), a
   server-influenced message that happened to CONTAIN the phrase mid-string could spoof
   `"transient"` over a correct (and more actionable) auth/rate/hard classification. The check
   now runs LAST and matches via `str.startswith` — an exact match for the internally-authored
   sentinel (which replaces stderr wholesale on `TimeoutExpired`), and no longer matchable
   mid-string by third-party text.
2. **Remediation is now message-visible, not just attribute-visible.** The transient hint
   originally lived ONLY in the `remediation` attribute / `details.remediation` JSON field —
   `str(e)` (and hence the default non-`--json-errors` stderr line) never named
   `--concurrent-fragments`/`--media-timeout-sec`. `fetch.py`'s `_emit_error` now prints a
   second stderr line (`remediation: <text>`) whenever `details` carries a `remediation` key,
   in BOTH the transient-timeout and `MissingDependencyError` cases, so the fix is visible
   without `--json-errors`.
3. **Rate-limit hint gains a concurrency note; auth hint's cookie filename is host-derived.**
   A 429 caused by the new 8-way parallel fragment default previously said only "retry
   later" with no link back to `--concurrent-fragments` — `_raise_for_failure` gains a
   `media_download: bool` parameter (`True` ONLY from the audio-download failure call site,
   not the metadata-probe one) that appends a `--concurrent-fragments` hint to the rate-limit
   message when set. Separately, the auth hint's convention cookie filename was hardcoded to
   `x.com-cookies.txt` regardless of the failing URL's actual host — a dead end for the other
   5 documented X hosts (`twitter.com`, `www.x.com`, `mobile.x.com`, `www.twitter.com`,
   `mobile.twitter.com`), since `_auth.resolve_cookies_file`'s convention lookup keys on the
   EXACT hostname with no aliasing. The hint now derives the host from the failing URL
   (`www.`/`mobile.` labels stripped) — e.g. `~/.transcript-fetcher/twitter.com-cookies.txt`
   for a `twitter.com` URL, `~/.transcript-fetcher/x.com-cookies.txt` for an `x.com` one.

**Amended (adversarial cycle 3) — the hint/resolver mismatch from delta 3 above, closed.**
Delta 3 stripped `www.`/`mobile.` from the printed hint but left
`_auth.resolve_cookies_file`'s convention lookup untouched — it still keyed on the EXACT URL
hostname, so the hinted file was a dead end for 4 of the 6 documented X hosts (`www.x.com`,
`mobile.x.com`, `www.twitter.com`, `mobile.twitter.com`): creating the file the hint named did
NOT make the next attempt find it. `resolve_cookies_file` now carries the matching fallback —
if the exact-host convention file is absent AND the host's first label is one of the three
well-known mirror prefixes (`www`, `mobile`, `m`), it also tries the same file with that label
stripped (exact-host file still wins when both exist). This is deliberately narrow — only a
single well-known label strip, never a generic parent-domain walk (which would widen the
cookie-leak surface) — so the printed hint now round-trips for all 6 allowlisted X hosts.

SKILL.md §Dependencies (vendored yt-dlp warning + doctor), §ASR portability (backend chain +
exit-7 remediation) and §X cookies (convention `<host>-cookies.txt`, auth-map for custom
names) document S3/S5/S6.
