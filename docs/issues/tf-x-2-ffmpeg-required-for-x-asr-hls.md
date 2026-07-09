---
id: TF-X-2
type: known-issue
status: handled
opened_at: 2026-07-09
category: robustness
severity: MEDIUM
component: transcript-fetcher
slug: tf-x-2-ffmpeg-required-for-x-asr-hls
---

# TF-X-2 — ffmpeg is required for the X ASR path on HLS sources (Broadcasts/Spaces)

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.

**Status:** handled (fail-fast) • **Severity:** MEDIUM • **Location:**
`sources/x.py` (fail-fast), `_ytdlp_media.{is_hls_only,download_audio}`.
**Live-E2E finding (supersedes the original "ffmpeg-optional" design assumption):**
yt-dlp's native HLS downloader runs without ffmpeg, but the file it produces by
concatenating fragments is **not a valid playable container** — MacWhisper/
AVFoundation rejects it (`Error: cannot open (mp4)`). X Broadcasts/Spaces are
always HLS, so **ffmpeg is required** there (to extract a clean `m4a`). The
adapter probes `is_hls_only(info)` and, when ffmpeg is absent, **fails fast with
`MissingDependencyError` (exit 7)** + a "install ffmpeg" remediation, BEFORE the
~200 MB download — instead of failing cryptically at the ASR step. ffmpeg stays
optional for non-HLS progressive media and the caption path. **Do-not:** re-assert
"MacWhisper reads video so ffmpeg is optional" — true only for a *valid* container,
which the no-ffmpeg HLS output is not.
Separately, **whisper.cpp** needs ffmpeg (to make a 16 kHz WAV) **and**
`--asr-model <ggml.bin>`; without either its `available()` returns False and it is
cleanly skipped — never a mid-run crash.
