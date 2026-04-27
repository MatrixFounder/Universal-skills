# Transcript Fetcher Manual

Practical reference for the [`transcript-fetcher`](../../skills/transcript-fetcher/)
skill: pull a clean plain-text transcript from a video URL and emit a
JSON stat sidecar alongside.

This manual is for **users** of the skill. For the design rationale
and adversarial review notes, see
[`SKILL.md`](../../skills/transcript-fetcher/SKILL.md).

---

## 1. What it does

| Capability | Detail |
|---|---|
| **Source** | **YouTube only** today (via `yt-dlp`). URLs from Vimeo, Zoom, or any other host are rejected by the hostname allowlist with `ValueError: Unsupported source for URL: ...`. Adapter slots for Vimeo / Zoom / podcast are documented in [`references/supported_sources.md`](../../skills/transcript-fetcher/references/supported_sources.md) but **not implemented** in v1.0. |
| **Caption tracks** | Manual (user-uploaded) and auto-generated. The fallback ladder picks the highest-quality track that exists for a given language. |
| **Output** | Two files per URL: `<out>.txt` (cleaned plain text, UTF-8) and `<out>.txt.stat.json` (audit trail of which track was used). |
| **Modes** | Single-URL and batch (one URL per line). |
| **No video download** | `--skip-download` always passed to yt-dlp; only subtitle tracks travel the network. |

The skill is **Apache-2.0** (matches the repo root); runtime deps are
attributed in [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

---

## 2. One-time setup

```bash
cd skills/transcript-fetcher
bash scripts/install.sh
# Creates scripts/.venv with yt-dlp installed.
# Re-running is idempotent — safe.
```

The script pins `yt-dlp>=2026.3.17,<2027` (see
[`requirements.txt`](../../skills/transcript-fetcher/scripts/requirements.txt)).
Upper bound is intentional: yt-dlp ships breaking changes ~quarterly,
and silent breakage is the worst failure mode for a captions fetcher.

Verify:

```bash
./scripts/.venv/bin/python -m yt_dlp --version
# 2026.03.17  (or newer in the same major)
```

---

## 3. CLI quick reference

### Single URL

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://youtu.be/NSVTpCfBMK8" \
    --out /tmp/talk.txt
```

Stdout: one JSON line with the stat record. Two files written:
`/tmp/talk.txt` and `/tmp/talk.txt.stat.json`.

### Batch

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    --batch urls.txt \
    --out-dir /tmp/transcripts/
```

`urls.txt` format: one URL per line. Blank lines and lines starting
with `#` are ignored. Output naming: `<video_id>.txt` (and sibling
`.stat.json`). Exit code `4` if any URL failed.

### Common flags

| Flag | Default | Purpose |
|---|---|---|
| `--lang` | `ru` | Preferred caption language. `--lang en` for English content. |
| `--prefer manual\|auto` | `manual` | Try human-uploaded subs first, or auto-captions first. |
| `--timeout-sec` | `180` | Per-attempt yt-dlp timeout. Increase for very long videos. |
| `--on-collision error\|skip\|suffix` | `error` | Batch mode behaviour when two URLs share a `video_id` (the same talk via different URL forms, or duplicate entries). |
| `--json-errors` | off | Emit failure messages as a single JSON line on stderr (machine-readable). |

---

## 4. The fallback ladder

Default for `--lang ru --prefer manual`:

```
1. manual : ru        # user-uploaded human captions       (highest quality)
2. auto   : ru-orig   # ASR of the original Russian audio  (good)
3. auto   : ru        # auto-translation TO Russian        (often noisy)
4. auto   : en        # English auto-captions              (last resort)
```

Step 4 raises a `quality_flag = "english_auto_translation"` in the
stat sidecar — surface this to the user before passing the transcript
to a downstream summarizer. Idioms, names, and jargon are usually
mangled by the translation.

For non-Russian content (`--lang <other>`), the `<lang>-orig` step is
skipped. It is a YouTube quirk meaningful mainly for non-English
speech going through their auto-translation.

Override the order with `--prefer auto` (try auto-generated first).
For arbitrary policies, call `fetch_youtube_transcript()` directly with
your own `fallback_ladder=` tuple — the API is more flexible than the
two CLI presets.

Full policy reference:
[`references/fallback_policy.md`](../../skills/transcript-fetcher/references/fallback_policy.md).

---

## 5. The JSON stat sidecar

```json
{
  "source": "youtube",
  "url": "https://youtu.be/NSVTpCfBMK8",
  "video_id": "NSVTpCfBMK8",
  "output_path": "/tmp/talk.txt",
  "chosen_track_kind": "auto",
  "chosen_track_lang": "ru-orig",
  "char_count": 62223,
  "speaker_turn_count": 2,
  "quality_flag": null,
  "notes": [
    "no subtitle returned for manual:ru",
    "got auto:ru-orig -> NSVTpCfBMK8.ru-orig.vtt"
  ]
}
```

| Field | Meaning |
|---|---|
| `chosen_track_kind` / `chosen_track_lang` | Which step of the ladder won. `null` only when the fetch failed. |
| `char_count` | Length of the cleaned plain text, in characters. Useful for chunking decisions downstream. |
| `speaker_turn_count` | How many `>>` speaker-turn boundaries the parser detected. Q&A and panels typically have 30–100; solo lectures have 1–20 (host intro + outro). |
| `quality_flag` | One of `null`, `"english_auto_translation"`, `"encoding_recovered"`. Always inspect before consuming the transcript. |
| `notes` | Human-readable trace of every ladder step attempted, including yt-dlp stderr tail when a step failed for non-trivial reasons (rate-limit, hard failure). |

---

## 6. Composition: fetch → summarize

The skill pairs naturally with
[`summarizing-meetings`](../../skills/summarizing-meetings/). Two-step
chain:

```bash
# Step 1: fetch the transcript.
./scripts/.venv/bin/python skills/transcript-fetcher/scripts/fetch.py \
    "https://youtu.be/<id>" \
    --out /tmp/talk.txt

# Step 2: read the JSON stat. If quality_flag is set, surface the warning.
python3 -c "
import json
stat = json.load(open('/tmp/talk.txt.stat.json'))
if stat['quality_flag']:
    print(f'WARNING: {stat[\"quality_flag\"]}')
"

# Step 3: pass the .txt to summarizing-meetings (or its educational
#         workflow extension /generate-detailed-meeting-summary).
```

Why two skills, not one: fetching is a deterministic file operation
(network call + VTT cleanup); summarizing is a prompt-first reasoning
task. Coupling them would muddy the contracts and make either side
harder to test in isolation.

---

## 7. Troubleshooting

### "No caption track available for ..."

Means every step of the fallback ladder failed. The `notes` field
of the (would-be) stat record carries per-step diagnostics — they
are also re-included in the exception message. Common causes:

| Note fragment | Cause | Fix |
|---|---|---|
| `rate-limit (http error 429)` | yt-dlp hit YouTube's anti-bot rate limit. | Wait 5–10 min, re-run. For batch, reduce concurrency. |
| `rate-limit (sign in to confirm you're not a bot)` | YouTube wants a logged-in cookie jar. | Pass cookies via yt-dlp config (out of scope for v1; see [`youtube_caption_format.md`](../../skills/transcript-fetcher/references/youtube_caption_format.md)). |
| `hard-failure (video unavailable)` | Video deleted, geoblocked, or region-restricted. | Confirm in a browser; no remedy from this skill. |
| `hard-failure (private video)` | Private upload. | Owner must make it public or unlisted. |
| `no subtitle returned for X:Y` | The track simply doesn't exist for that language. | Try `--lang en` or `--prefer auto`. |

### `quality_flag: "english_auto_translation"`

Only English auto-captions were available. The transcript is technically
complete but is YouTube's auto-translation of speech that may have been
in another language. Idioms, names, and technical terms will be mangled.

Surface a warning to the human/agent reading the result. If a manual
transcription is available offline (Whisper, paid service), prefer it.

### `quality_flag: "encoding_recovered"`

The VTT file was not valid UTF-8; the parser fell back to CP1251 or
UTF-16. The text is correct as far as the codec ladder could tell, but
re-encode the source if you can — silent codec drift is hard to debug.

### Output looks repetitive (`"и я думаю что и я думаю что"`)

The dedup heuristic only collapses suffix-prefix overlaps of **3 word
tokens or longer** (a deliberately conservative threshold to avoid
false-positive merging on common 2-word phrases like "это нужно" / "и
вот"). Two-word overlaps slip through. If this hurts, post-process
with a more aggressive dedup downstream — or open an issue with a
real fixture and we will tighten the heuristic.

### `>>` markers in places that aren't speaker turns

The parser anchors `>>` to the **start of a cue's text** only. A
talk about C++ stream operators or shell redirection that emits
`cout >> x` mid-cue is preserved verbatim. If you see a stray `\n\n>>`
in the output that doesn't correspond to a speaker change, the source
VTT had a leading `>>` on that cue — that's the broadcast-caption
convention, and the parser is doing the right thing. Inspect the
raw `.vtt` if uncertain.

---

## 8. Limitations and roadmap

- **One source today**. Adapter slots for Vimeo, Zoom, and podcast
  RSS are reserved in
  [`references/supported_sources.md`](../../skills/transcript-fetcher/references/supported_sources.md)
  but not implemented.
- **No Whisper fallback**. Videos with no captions cannot be transcribed
  by this skill. Pair with a separate Whisper invocation if you need
  ASR for caption-less content.
- **No cookie auth**. Age-restricted / members-only content needs a
  cookie jar; out of scope for v1.
- **Multi-source batch**. Batch mode currently dispatches everything
  through the YouTube adapter. When new adapters land, batch will
  route per-URL via the same `_detect_source` allowlist.

---

## 9. Anti-patterns

| DO NOT | WHY |
|---|---|
| Strip `>>` markers from the output before summarization | They are speaker-turn boundaries. Removing them collapses a panel into a single voice. |
| Trust the `.txt` without reading the `.stat.json` | The flag tells you whether the captions are high-quality manual subs or low-quality English auto-translation. |
| Loop the CLI shell-side over arbitrary URLs | Use `--batch <file>`. The batch path handles collisions, partial failures, and JSON-stat aggregation correctly. |
| `pip install -g yt-dlp` and bypass the venv | The skill invokes `python -m yt_dlp` from its per-skill `.venv`. A globally-installed yt-dlp may be a different version with different output formats. |
| Pass `--prefer auto` by default | Manual subs (when they exist) are higher fidelity than ASR. Default `--prefer manual` is correct for almost all use cases. |

---

## 10. References

- [SKILL.md](../../skills/transcript-fetcher/SKILL.md) — orchestration contract, anti-rationalization rules.
- [scripts/fetch.py](../../skills/transcript-fetcher/scripts/fetch.py) — CLI entry point.
- [scripts/sources/youtube.py](../../skills/transcript-fetcher/scripts/sources/youtube.py) — yt-dlp adapter, fallback ladder, snapshot-aware VTT discovery.
- [scripts/sources/_vtt_to_text.py](../../skills/transcript-fetcher/scripts/sources/_vtt_to_text.py) — pure-Python WebVTT cleaner with cue grouping, suffix-prefix dedup, anchored `>>` markers, encoding fallback ladder.
- [references/youtube_caption_format.md](../../skills/transcript-fetcher/references/youtube_caption_format.md) — what `>>`, `&gt;`, rolling captions, and `ru-orig` actually mean.
- [references/fallback_policy.md](../../skills/transcript-fetcher/references/fallback_policy.md) — language ladder rationale.
- [references/supported_sources.md](../../skills/transcript-fetcher/references/supported_sources.md) — current and planned source slots.
