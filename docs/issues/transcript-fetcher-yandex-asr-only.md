---
id: TF-YANDEX-1
type: known-issue
status: by-design
opened_at: 2026-07-31
category: honest-scope
severity: LOW
component: transcript-fetcher
slug: transcript-fetcher-yandex-asr-only
---

# transcript-fetcher — Yandex VH/Strm is ASR-only: that player carries no caption track

- **Reported**: 2026-07-31 (real dogfood: transcribing the 9-talk
  [Yandex AI Studio Series Summer Edition 2026](https://aistudio.yandex.ru/ru/ai-series) programme)
- **Severity**: LOW (honest-scope limitation, not a defect — the adapter behaves correctly)
- **Affected component**: `skills/transcript-fetcher/scripts/sources/yandex.py`
- **Status**: **BY DESIGN** — documented here so nobody "fixes" it by adding a caption ladder.

## Symptom

The Yandex adapter never returns `chosen_track_kind: "manual"` or `"auto"`. Every
successful run reports `"asr"`, costs an audio download plus a full ASR pass, and
requires `ffmpeg` (exit 7 without it). Compared with the YouTube adapter — which
returns captions in seconds and needs no ffmpeg — this looks like a missing feature.

It is not. The player has no caption track to fetch.

## Root cause

`runtime.strm.yandex.ru` / `frontend.vh.yandex.ru` serve no subtitles at all.
Verified five independent ways across five distinct episode ids
(`vple7dqmd5w2awbjijmo`, `vplegzpe463wsyw4qk7j`, `vpleqcviustj6oddnar5`,
`vplet6w5ai4tqb2lbav4`, `vplefi4lxqhmuvgzujwm`):

| Probe | Result |
|---|---|
| Player config JSON (`?format=json`) | no `subtitle` / `caption` / `track` key on any episode |
| HLS master playlist | **zero** `#EXT-X-MEDIA` tags (histogram: 79x `EXT-X-STREAM-INF`, 1x `EXT-X-VERSION`) |
| DASH `.mpd` | exactly two AdaptationSets — `contentType="video"` and `contentType="audio" lang="rus"`. No text set |
| `yt-dlp --list-subs` | `manifest has no subtitles` |
| Live player in headless Chromium | `video.textTracks: []`; zero caption-shaped URLs across 114 captured network records |

A caption ladder in this adapter would therefore be dead code that costs a
round-trip on every run and can never succeed.

## Workaround — check for a YouTube mirror FIRST

Conference and webinar recordings embedded in a proprietary player are routinely
re-published by the same organiser on YouTube **with** auto-captions. In the
dogfood case all five underlying streams were on the official Yandex Cloud
YouTube channel with full-coverage `ru-orig` captions (99.7–100 % of duration),
so the whole ~7.6 h ASR job collapsed into five caption fetches.

Spot-checked afterwards: the local MacWhisper output on the Yandex stream and the
YouTube captions for the same talk agree word-for-word on content, and MacWhisper's
is actually *cleaner* (no rolling-caption duplication). So the mirror is preferred
for **cost**, not because ASR is worse.

This is now a Red Flag in `SKILL.md` §1.

## Do-not

- **Do NOT add a caption ladder to `sources/yandex.py`.** Locked in by
  `TestNoCaptionLadder` in `scripts/tests/test_yandex_adapter.py`.
- **Do NOT trust the config JSON's `duration` field.** It overstates every
  observed episode — 4365 vs a real 3800 s, and 43970 vs a real 8825 s (~5x).
  Real duration is the `#EXTINF` sum from the media playlist; the download and
  ASR timeout budgets derive from it, so this is load-bearing. Regression:
  `TestRealDurationBeatsJsonField`.
- **Do NOT cache signed stream URLs.** `ysign1` is minted per request and expires
  in ~48 h.
- **Do NOT point ffmpeg at the HLS master playlist** (79 variants — it opens all
  of them and hangs past any sane timeout), and **do NOT expect ffmpeg to open the
  DASH manifest at all** (`Invalid data found when processing input` — it does not
  follow the 302 + `BaseURL` indirection). This is why a clipped download
  (`--max-duration-min`, which routes through ffmpeg) prefers HLS while an
  unclipped one prefers DASH's audio-only rendition. Regression:
  `TestManifestOrdering`.
- **Do NOT treat a non-None return from `download_audio` as success.** It returns
  a path whenever ANY `media.*` artefact survives, *even when yt-dlp exited
  non-zero* — so a postprocessor failure leaves a complete-but-unconverted
  container that looks like a win, silently defeating the DASH→HLS fallback and
  discarding the real stderr. A candidate counts as successful only with an empty
  stderr, and `media.*` must be purged between attempts or candidate 2 inherits
  candidate 1's leftovers. Regression: `TestDownloadFailureIsNotMistakenForSuccess`.
- **Do NOT widen the stream allowlist to a `*.yandexcloud.net` suffix.** That is
  object storage — anyone can create a bucket, so the suffix rule made the
  allowlist an open redirect (`mybucket.storage.yandexcloud.net` passed). Exact
  hosts only. And the pre-flight check is not enough on its own: fetch through the
  shared restricted opener so cross-host **redirects** are refused too.
  Regression: `TestStreamUrlAllowlist`, `TestHttpHardening`.

## Related

- `skills/transcript-fetcher/SKILL.md` §1 Red Flags ("check for a mirror first"), §2 Capabilities.
- Module docstring of `skills/transcript-fetcher/scripts/sources/yandex.py`.
