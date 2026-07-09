---
id: TF-X-4
type: known-issue
status: handled
opened_at: 2026-07-09
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-4-captions-vtt-srt-ttml
---

# TF-X-4 — captions: VTT + SRT + TTML/DFXP (HANDLED)

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.

**Status:** handled • **Severity:** LOW (residual) • **Location:**
`_ytdlp_media.download_captions` + `sources/_captions.py`.
**Was:** the X caption path asked yt-dlp for `--sub-format vtt` only; a track served
only as SRT or TTML was treated as absent → ASR.
**Now:** yt-dlp is handed a format *preference list* `vtt/srt/ttml/best` and the
downloaded file is parsed **format-aware** — SRT is normalised into the VTT machinery
(comma→dot timestamps; all rolling-caption dedup + `>>`-turn handling reused), and
TTML/DFXP is parsed via stdlib `ElementTree` (`<p>` → line, `<br/>` → space). A
malformed or DTD-bearing TTML is **refused before parse** (XXE / billion-laughs guard:
a `<!DOCTYPE`/`<!ENTITY` declaration is rejected; the file is size-capped) and the run
falls through to ASR rather than crashing or silently emptying.
**Also (language-robust captions-first):** the X path used to drop to ASR when the requested
`--lang` (default `ru`) had no track even though the post carried captions in *another*
language. It now falls back to **any available caption** (`_ytdlp_media.pick_any_caption`,
manual preferred over auto) before ASR, with a note (`using the available <kind>:<lang> track`)
— so e.g. a post whose only track is `manual en` is transcribed from captions, not ASR.
Live-proven on `x.com/Av1dlive/status/2070507527213871594` (manual `en` VTT → 1345 chars,
`embedded-captions`, no ASR) under the default `--lang ru`.
**Residual:** YouTube-only `srv1/2/3` XML and other exotic sub formats are NOT parsed —
`best` may still fetch one, in which case the finder declines it → ASR (same outcome as
before). **Do-not:** pull in a heavyweight XML dep (`defusedxml`) — the
declaration-refusal guard covers the threat model cheaply.
