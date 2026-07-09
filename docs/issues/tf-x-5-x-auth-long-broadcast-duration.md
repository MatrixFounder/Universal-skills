---
id: TF-X-5
type: known-issue
status: handled
opened_at: 2026-07-09
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-5-x-auth-long-broadcast-duration
---

# TF-X-5 — X auth + long-broadcast cost + duration (largely HANDLED)

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.

**Status:** handled (one residual, one external limit) • **Severity:** LOW •
**Location:** `sources/x.py`, `sources/_auth.py`, `_ytdlp_media.{download_audio,probe_media_duration}`.

- **Large broadcast download → HANDLED.** `--max-duration-min N` clips the download to
  the first N minutes (yt-dlp `--download-sections`, needs ffmpeg — already required for
  HLS), bounding **both** bytes and ASR time. Live-proven: `--max-duration-min 1` on the
  reference broadcast ran end-to-end in ~19 s vs ~20 min for the whole stream. Default is
  the whole media; `--timeout-sec` still time-bounds it (so a runaway can't hang).
- **Auth / login walls → HANDLED.** Cookies resolve from a skill-local
  **`~/.transcript-fetcher/`** folder (mirrors the `html` skill's `~/.html`): an
  `auth-map.json` (host → `{cookies_file}`, hardened 0600/symlink-reject, label-boundary
  host match — `x.com` never leaks to `evil-x.com`) or the convention
  `~/.transcript-fetcher/<host>-cookies.txt`; `--cookies-file` still wins. The resolved
  Netscape file feeds yt-dlp `--cookies` (source-agnostic). `--cookies-from-browser BROWSER`
  loads cookies straight from a local browser (yt-dlp native, X path). Session **minting**
  stays out of scope (that is the `html` skill's Playwright job) → a protected post with no
  cookies is still a clean `SourceAuthError` (exit 5).
- **`duration_sec=None` on Broadcasts → HANDLED.** When the media is downloaded for ASR and
  ffmpeg is present, the duration is derived via **ffprobe** (ships with ffmpeg — no new dep)
  and a `duration: derived via ffprobe` note is added. Live-proven (`duration_sec: 59` on a
  1-min clip).
- **Residual (external limit, NOT fixable here):** MacWhisper's `mw transcribe` has **no
  language flag** (verified) — it auto-detects; the `--lang` hint is forwarded only to
  `whisper`/`whisper.cpp`/cloud. **Do-not:** claim `--lang` reaches MacWhisper.
