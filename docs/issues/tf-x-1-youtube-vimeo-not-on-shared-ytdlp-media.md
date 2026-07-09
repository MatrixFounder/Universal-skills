---
id: TF-X-1
type: known-issue
status: by-design
opened_at: 2026-07-09
category: tech-debt
severity: LOW
component: transcript-fetcher
slug: tf-x-1-youtube-vimeo-not-on-shared-ytdlp-media
---

# TF-X-1 — youtube/vimeo not retrofitted onto the shared `_ytdlp_media.py`

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.
> None is a blocker; the chain ships with 268 offline tests green + `validate_skill` exit 0.

**Status:** open (by design) • **Severity:** LOW • **Location:**
`sources/youtube.py`, `sources/vimeo.py`.
The shared media core (`_ytdlp_media.py`) is the **forward** extension surface
(X uses it; future TikTok/Twitch will). The two pre-existing adapters keep their
own copies of the yt-dlp helpers to avoid regressing three tested adapters in one
task. `classify_failure` in the shared module **imports** youtube's base pattern
tuples (no fork). **Fix path:** a future `transcript-fetcher-Nb` can converge
youtube/vimeo onto the shared core. **Do-not:** treat the duplication as a fork —
the base failure patterns have one source of truth.
