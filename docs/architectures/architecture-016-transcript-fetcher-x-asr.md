# Architecture 016 — `transcript-fetcher`: X.com source + pluggable ASR backend

> **Subsystem:** `transcript-fetcher` skill (Apache-2.0).
> **Builds on:** v1.1 source-adapter architecture (`youtube`/`vimeo`/`skool`, shared
> `TranscriptStat` + `_vtt_to_text` + `_description`).
> **Task:** TASK 026 (`docs/tasks/task-026-transcript-fetcher-x-asr.md`).
> **Status:** design (pre-merge).

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
- **HS-5 — caption SRT/TTML.** yt-dlp is asked for `--sub-format vtt`; when a source only
  offers TTML/SRT, yt-dlp converts to VTT where it can. If conversion is unavailable the track
  is treated as absent → ASR path. No bespoke TTML parser.
- **HS-6 — X login walls.** Protected/age-gated/some-Broadcast media needs `--cookies-file`
  (existing mechanism); without it → `SourceAuthError` (exit 5). We do not mint sessions
  (that's the html skill's job).
- **OQ-1 — duration on Broadcasts.** yt-dlp may report `duration: None` for replays; the stat's
  `duration_sec` is then `None` (acceptable; not derived from the media to avoid an ffprobe dep).
```
