---
id: TF-X-6
type: known-issue
status: handled
opened_at: 2026-07-09
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-6-asr-filler-on-silence-removal
---

# TF-X-6 — ASR filler on silence → silence-removal preprocessing (HANDLED for silence; music residual)

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.

**Status:** handled (silence) / open (music, engine-level) • **Severity:** LOW •
**Location:** `_ytdlp_media.remove_silence` (ffmpeg `silenceremove`), wired into the
`sources/x.py` ASR path; `_config.silence_*`.
**Was:** Whisper-family models (incl. MacWhisper) emit repeated training-data filler —
e.g. `"Продолжение следует..."`, `"Thanks for watching"` — over **silent or
music-only** lead-in/out. The live broadcast opened with ~14 such lines before the
real speech; the skill recorded whatever the engine returned.
**Now (the user's "analyse the audio and remove large silences" approach):** before
ASR the X path runs ffmpeg `silenceremove` to trim leading silence and collapse every
interior/trailing gap longer than `min_gap` (default 1.0s) to `keep` (0.3s), gated at
`threshold` (-45dB) — removing the dead air where the hallucination originates. **ON by
default**; `--keep-silence` (or `TRANSCRIPT_FETCHER_SILENCE_REMOVAL=0`) opts out, and
`TRANSCRIPT_FETCHER_SILENCE_{THRESHOLD,MIN_GAP_SEC,KEEP_SEC}` tune it. Never fatal —
ffmpeg absent or a filter failure transparently falls back to the original media. The
timeline shifts, but the ASR path emits no timecodes (so the text is faithful) and the
**original** media is kept for the ffprobe duration fill.
**Residual (music, NOT silence — engine-level):** the threshold treats only *true
silence* as removable, so **music/applause carry energy above it and survive** — a
*music-only* intro can still trigger filler. For that, use a model/engine config with
VAD / `condition_on_previous_text=false`, or trim downstream. **Do-not:** lower the
threshold far enough to eat music — it would clip quiet speech (a worse failure).
**Do-not:** add a blanket text dedup that could strip legitimately-repeated speech.
