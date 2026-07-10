# ASR backends, configuration & component installer

This skill transcribes audio only when a source has **no embedded captions**
(currently: X.com Broadcasts/Spaces and most native X video). Transcription is
done by a **pluggable ASR backend** — entirely separate from the source
adapters, so any source can use any backend and a new engine drops in without
touching the pipeline.

## 1. The `ASRBackend` interface

`scripts/asr/_base.py` defines the Python equivalent of the spec's
`TranscriptProvider`:

```python
class ASRBackend(abc.ABC):
    name: str
    def available(self) -> bool: ...                       # cheap probe, no network/heavy import
    def transcribe(self, audio_path, *, lang=None) -> ASRResult: ...
```

`ASRResult(text, backend_name, language?, model?)` is the return shape. An
engine-level failure raises `ASRError` (recoverable → the registry falls through
to the next backend). External tools are always invoked via **argv arrays**
(never a shell string).

## 2. The fallback chain (priority order)

`scripts/asr/__init__.py` holds `REGISTRY` and the orchestration:

| # | Backend | `name` | Needs | Notes |
|---|---------|--------|-------|-------|
| 1 | MacWhisper | `macwhisper` | `mw` on PATH | `mw transcribe <file>` → stdout. Reads audio **or** video. Fast on Apple Silicon. |
| 2 | Whisper CLI | `whisper-cli` | `whisper` + `ffmpeg` | `whisper <file> --output_format txt …`. |
| 3 | whisper.cpp | `whisper-cpp` | `whisper-cli`/`main` + `ffmpeg` + `--asr-model <ggml.bin>` | needs a 16 kHz WAV (ffmpeg) and a model path; otherwise `available()=False`. |
| 4 | OpenAI / compatible cloud | `openai-api` | `--asr-allow-cloud` **and** an API key | **opt-in only** — egresses audio. Works with any OpenAI-compatible server. |

- `select_backend(...)` returns the first `available()` backend.
- `transcribe_with_fallback(audio, ...)` tries each available backend in order;
  on `ASRError` it falls through to the next. If **none** is available →
  `MissingDependencyError` (CLI exit 7, with a remediation hint). If all
  available ones fail → `TranscriptFetchError` (exit 3).
- **Check readiness before a long fetch:** `scripts/fetch.py doctor` (import-free,
  no network) reports which of these four backends resolve on the current
  machine — plus ffmpeg and the cloud opt-in state — so a caption-less
  Broadcast/Space's exit-7 risk is visible up front instead of after a large
  download. `--json` emits a machine-readable envelope.

**Add a backend:** drop a `scripts/asr/<engine>.py` implementing `ASRBackend`,
append its class to `REGISTRY`. No change to the X provider or the CLI core.

> **ffmpeg is required for HLS sources (X Broadcasts/Spaces).** Even though
> MacWhisper reads video, yt-dlp's no-ffmpeg HLS download produces a fragment
> concatenation that is *not* a valid container — MacWhisper cannot open it. With
> ffmpeg the smallest media is extracted to a clean `m4a`. When ffmpeg is absent
> for an HLS source the adapter **fails fast (exit 7)** with an install hint,
> before any large download. (ffmpeg stays optional for non-HLS progressive media
> and the caption path.) `whisper`/`whisper.cpp` also need ffmpeg in all cases.

## 3. Configuration & secrets (`.env`)

Everything tunable lives in `scripts/_config.py`, resolved as
**CLI flag → env var → skill-local `.env` → built-in default**. Copy
`scripts/.env.example` → `.env`, then `chmod 600 .env`. Prefix is
`TRANSCRIPT_FETCHER_` (the conventional `OPENAI_API_KEY` is also honoured).

Key knobs (see `.env.example` for the full list):

| Key | Default | Purpose |
|-----|---------|---------|
| `…OPENAI_API_KEY` / `OPENAI_API_KEY` | — | bearer token for the cloud backend |
| `…OPENAI_BASE_URL` | `https://api.openai.com/v1` | point at Groq / self-hosted / a gateway |
| `…OPENAI_TRANSCRIBE_ENDPOINT` | (base+path) | full URL override (verbatim) |
| `…OPENAI_MODEL` | `whisper-1` | cloud model |
| `…ASR_ALLOW_CLOUD` | `0` | enable cloud without the CLI flag |
| `…ASR_TIMEOUT_SEC` | `1800` | per-backend transcription timeout |
| `…ASR_MODEL` | — | default model for all backends |
| `…{MW,WHISPER,WHISPER_CPP,FFMPEG}_BIN` | tool name | point at a non-standard binary path |
| `…NO_DOTENV` | `0` | disable `.env` loading entirely |

**Secret storage (secure by construction):**

- The `.env` is loaded into `os.environ` **only** at the CLI entry point
  (`fetch.py main()`), never on import.
- A `.env` that is a **symlink** or is **group/world-accessible** (not `0600`)
  is **refused** with a stderr warning — a secret never loads from a file other
  users can read.
- **Process env always wins** over `.env` (a caller can override).
- The key is sent **only** in an HTTP `Authorization` header — never on a
  command line (argv), never written to logs. The debug logger prints stage
  names, never config values.
- `.env` is git-ignored (`.gitignore`); only `.env.example` (placeholders) is
  committed.

## 4. Component installer

`scripts/install_components.py` detects and (on request) installs the optional
engines. `bash scripts/install.sh` runs the detector at the end.

```bash
./scripts/.venv/bin/python scripts/install_components.py            # status report (mutates nothing)
./scripts/.venv/bin/python scripts/install_components.py --json     # machine-readable
./scripts/.venv/bin/python scripts/install_components.py --install-whisper   # pip openai-whisper into the venv (in-venv, safe)
./scripts/.venv/bin/python scripts/install_components.py --system           # print brew/apt commands
./scripts/.venv/bin/python scripts/install_components.py --system --run      # execute them (opt-in, double-gated)
```

MacWhisper (`mw`) ships with the MacWhisper app (macOS); the installer points
you to it but cannot install a GUI app. System tools (`ffmpeg`, whisper.cpp) are
installed via `brew`/`apt` only with both `--system` and `--run`.
