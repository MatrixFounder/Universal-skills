# Subtitle Fallback Policy

Each supported source has a fallback **ladder** — an ordered list of
`(kind, lang)` pairs the adapter walks until one succeeds. The goal is
to maximise transcript fidelity while still completing the request when
the user's first-choice track does not exist.

## 1. Default ladder for Russian content (`--lang ru`)

```
1. manual : ru        # user-uploaded human captions          (best)
2. auto   : ru-orig   # ASR of the original Russian audio     (good)
3. auto   : ru        # auto-translation TO Russian           (noisy)
4. auto   : en        # auto-translation to English           (last resort)
```

If the only successful track is step 4, the adapter sets
`quality_flag = "english_auto_translation"` in the JSON stat sidecar.
Callers MUST surface this to the end user.

## 2. Default ladder for other languages (`--lang <lang>`)

```
1. manual : <lang>
2. auto   : <lang>
3. auto   : en        # last resort
```

The `<lang>-orig` step is skipped — it is a YouTube quirk that mainly
matters for non-English speech being mis-translated through English.

## 3. Auto-first override (`--prefer auto`)

When the user is fairly sure manual captions on the source are
machine-uploaded garbage (or non-existent), they can flip the order so
ASR is tried first:

```
1. auto   : ru-orig
2. auto   : ru
3. manual : ru
4. auto   : en
```

The `manual` step still appears (it might be a real human transcription
for some videos and we should not categorically skip it).

## 4. What counts as "success"

A track is considered successfully fetched if, after running yt-dlp:

- yt-dlp exited cleanly OR returned a non-zero code that does NOT match
  a hard-failure pattern like `video unavailable` / `private video`;
- AND a file matching `*.<lang>.vtt` exists in the working directory.

This is intentionally loose because yt-dlp sometimes returns 0 with no
file (no track in that language) and sometimes returns non-zero
warnings while still producing the file. We trust the file system as
the source of truth.

## 5. What the `quality_flag` field means

The stat sidecar (`<out>.txt.stat.json`) carries a `quality_flag`
field. Possible values:

| Value | Meaning | Action for caller |
| --- | --- | --- |
| `null` | Track came from steps 1-3 of the ladder | None — proceed |
| `english_auto_translation` | Only step 4 succeeded | Warn the user before downstream consumption |

Future flags may include `low_confidence_asr` (when ASR confidence is
exposed by yt-dlp) and `partial_track` (when the VTT is suspiciously
short). They are not implemented yet — out of scope for v1.0.

## 6. Why this is a policy, not a hardcoded constant

The ladder is exposed as an iterable parameter on
`fetch_youtube_transcript(fallback_ladder=...)`. Callers that need a
different policy (e.g. always-English-only for a translation pipeline)
can pass their own. The CLI exposes the two most common policies via
`--prefer manual|auto`; the underlying API is more flexible.
