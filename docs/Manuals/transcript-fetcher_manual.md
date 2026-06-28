# Transcript Fetcher Manual

Practical reference for the [`transcript-fetcher`](../../skills/transcript-fetcher/)
skill (v1.1): pull a clean plain-text transcript from a video URL or
Skool classroom lesson, optionally save its description / metadata
sidecar, emit a JSON stat record alongside.

This manual is for **users** of the skill. For the design rationale
and adversarial-review notes, see
[`SKILL.md`](../../skills/transcript-fetcher/SKILL.md).

---

## 1. What it does

| Capability | Detail |
|---|---|
| **Sources (v1.1)** | **YouTube** + **Vimeo** (both via `yt-dlp`) + **Skool** classroom lessons (`/<community>/classroom/<id>?md=<lesson-id>` via stdlib HTML scrape). Any other host is rejected by the hostname allowlist with `ValueError: Unsupported source for URL: ...`. Zoom / podcast adapter slots remain reserved — see [`references/supported_sources.md`](../../skills/transcript-fetcher/references/supported_sources.md). |
| **Skool delegation** | When a Skool lesson embeds a YouTube / Vimeo video, the adapter delegates the transcript fetch to that source's adapter; description metadata always comes from the Skool lesson itself. Loom / Wistia / native Skool MP4 are flagged `embed_source_unsupported` (description still written). When an author has filled the lesson's `transcript` field, that text wins outright. |
| **Auth** | `--cookies-file <Netscape cookies.txt>` is **ALWAYS OPTIONAL**. Skool public communities (e.g. `zero-one`) serve lessons without auth; private / paid ones answer HTTP 401/403 → `SourceAuthError` (exit code 5). Cookies are also forwarded to yt-dlp's `--cookies` when supplied (age-gated YouTube, private Vimeo, etc.). |
| **Caption tracks** | Manual (user-uploaded) and auto-generated. The fallback ladder picks the highest-quality track for a given language. |
| **Outputs** | `<out>.txt` (cleaned plain text, UTF-8) + `<out>.txt.stat.json` (audit trail) + optional `<out>.description.md` (YAML frontmatter + Markdown body) under `--with-description`. |
| **Modes** | Single-URL and batch (one URL per line); `--description-only` skips the transcript and writes only the description sidecar. |
| **No video download** | `--skip-download` is always passed to yt-dlp; only subtitle tracks and an optional `--write-info-json` (when `--with-description` is set) travel the network. |

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
Skool / cookies / ProseMirror handling are pure stdlib — zero new
dependencies beyond yt-dlp.

Verify:

```bash
./scripts/.venv/bin/python -m yt_dlp --version
# 2026.03.17  (or newer in the same major)
```

---

## 3. CLI quick reference

### Single URL (YouTube)

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://youtu.be/NSVTpCfBMK8" \
    --out /tmp/talk.txt
```

Stdout: one JSON line with the stat record. Two files written:
`/tmp/talk.txt` and `/tmp/talk.txt.stat.json`.

### Single URL with description sidecar

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://youtu.be/NSVTpCfBMK8" \
    --out /tmp/talk.txt \
    --with-description
```

Adds `/tmp/talk.description.md` (YAML frontmatter — `title`, `uploader`,
`upload_date`, `duration_sec` — + the original description body).
yt-dlp piggy-backs `--write-info-json` onto the same subtitle subprocess
so no extra network round-trip is paid on the happy path.

### Skool lesson (public community — no cookies needed)

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://www.skool.com/zero-one/classroom/a60f0bd2?md=5dbd5cacecc34686890e838ef10f7312" \
    --out /tmp/lesson.txt \
    --with-description
```

For public Skool communities the adapter fetches lesson HTML directly
(no auth). It parses `__NEXT_DATA__`, picks the lesson by `?md=...`,
delegates the embedded YouTube/Vimeo to the matching adapter, and
renders the lesson description (TipTap/ProseMirror JSON) to Markdown.

### Skool lesson (private community — pass cookies.txt)

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://www.skool.com/private-foo/classroom/AAA?md=BBB" \
    --out /tmp/lesson.txt \
    --with-description \
    --cookies-file ~/.config/skool-cookies.txt
```

Export the cookie jar with a browser extension such as *Get cookies.txt
LOCALLY* (any tool producing Netscape format works). Permissions must
be `0600` and the file must not be a symlink — the loader refuses both
with a clear error.

### Single URL (X.com / Twitter — incl. Broadcast/Space)

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://x.com/i/broadcasts/<id>" \
    --out /tmp/broadcast.txt \
    --with-description --debug
```

Fully automatic and captions-first: if the X media carries
`subtitles`/`automatic_captions` they are used (fast, high quality,
`transcript_origin: embedded-captions`). A Broadcast/Space normally has
**no** captions, so the skill downloads the smallest media and
transcribes it with the first available **ASR backend** — MacWhisper
(`mw`), Whisper CLI, whisper.cpp, or (opt-in) a cloud API — recording
which one in `transcript_origin` (e.g. `macwhisper`). `--debug` prints
the pipeline stages to stderr; without it stderr is silent.

Opt-in cloud ASR (audio leaves the machine — see §8):

```bash
./scripts/.venv/bin/python scripts/fetch.py "https://x.com/i/broadcasts/<id>" \
    --out /tmp/b.txt --asr-allow-cloud --asr-model whisper-1
# needs OPENAI_API_KEY (or a skill-local .env); works with any
# OpenAI-compatible server via TRANSCRIPT_FETCHER_OPENAI_BASE_URL.
```

### Description-only (skip the transcript)

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://www.skool.com/zero-one/classroom/.../?md=..." \
    --out /tmp/lesson.txt \
    --with-description --description-only
```

Useful for batch-enriching a corpus you already transcribed elsewhere:
emits only `<out>.description.md` + `<out>.txt.stat.json` (with
`char_count: 0`). The `.txt` itself is NOT written.

### Batch

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    --batch urls.txt \
    --out-dir /tmp/transcripts/
```

`urls.txt` format: one URL per line. Blank lines and lines starting
with `#` are ignored. URLs may mix sources — each is dispatched via
`_detect_source` to the correct adapter (YouTube / Vimeo / X / Skool).
Output naming: `<video_id>.txt` for YouTube/Vimeo, `<status-or-broadcast-id>.txt`
for X, `<lesson-id>.txt` for Skool. Exit code `4` if any URL failed;
`5` for auth errors; `6` for rate-limit; `7` for a missing dependency.

### Common flags

| Flag | Default | Purpose |
|---|---|---|
| `--lang` | `ru` | Preferred caption language. `--lang en` for English content. |
| `--prefer manual\|auto` | `manual` | Try human-uploaded subs first, or auto-captions first. |
| `--with-description` | off | Also write `<out>.description.md` (YAML frontmatter + Markdown body) and populate metadata fields in the stat sidecar. |
| `--description-only` | off | Skip the transcript download entirely; produce only the description sidecar. Implies `--with-description`. |
| `--cookies-file PATH` | none | Netscape `cookies.txt`. Optional for every source; Skool needs it only for private communities, yt-dlp uses it for age-gated content. |
| `--timeout-sec` | `180` | Per-attempt yt-dlp / HTTP timeout. Worst-case wall-clock = `(ladder_steps + 1) × timeout_sec` if every attempt times out. For long X Broadcasts raise it (the audio download counts against it). |
| `--on-collision error\|skip\|suffix` | `error` | Batch mode behaviour when two URLs share an output filename. |
| `--json-errors` | off | Emit failure messages as a single JSON line on stderr (machine-readable). |
| `--debug` | off | (X) Print pipeline stages to stderr (also `TRANSCRIPT_FETCHER_DEBUG=1`). Stdout stays pure JSON. |
| `--asr-allow-cloud` | off | (X) Permit the opt-in cloud ASR backend (needs an API key). Audio leaves the machine. |
| `--asr-model ID` | none | (X) Model forwarded to the chosen ASR backend (MacWhisper `engine:model-id`, whisper name, whisper.cpp ggml path, cloud model). |
| `--asr-timeout-sec N` | `1800` | (X) Per-backend transcription timeout (also `TRANSCRIPT_FETCHER_ASR_TIMEOUT_SEC`). |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Unexpected error (uncategorized exception). |
| `2` | Usage error (bad flag combo, malformed URL, cookies file missing on disk, Skool URL not a lesson). |
| `3` | `TranscriptFetchError` — no caption track in the fallback ladder (transcript path). |
| `4` | Batch mode: at least one URL failed (partial success). |
| `5` | `SourceAuthError` — source returned HTTP 401/403 (private Skool needs cookies; X protected/suspended/age-gated; cookies expired). |
| `6` | `SourceRateLimitError` — source returned HTTP 429. |
| `7` | `MissingDependencyError` — a required tool is absent: yt-dlp, ffmpeg (when required), or **no ASR backend** for caption-less X media. `details.remediation` carries the fix. |

---

## 4. The fallback ladder

### YouTube (default `--lang ru --prefer manual`)

```
1. manual : ru        # user-uploaded human captions       (highest quality)
2. auto   : ru-orig   # ASR of the original Russian audio  (good)
3. auto   : ru        # auto-translation TO Russian        (often noisy)
4. auto   : en        # English auto-captions              (last resort)
```

Step 4 raises `quality_flag = "english_auto_translation"` in the stat
sidecar — surface this to the user before passing the transcript to a
downstream summarizer. Idioms, names, and jargon are usually mangled.

For non-Russian content (`--lang <other>`), the `<lang>-orig` step is
skipped (YouTube quirk meaningful mainly for non-English speech going
through their auto-translation).

### Vimeo

Vimeo has no `<lang>-orig` quirk; the ladder is the user's `--lang` /
`--prefer` choice with `("auto", "en")` always appended as the
last-ditch fallback. Vimeo auto-captions are far rarer than on
YouTube — expect `TranscriptFetchError` for many videos and use
`--with-description` to at least save the metadata.

### X / Twitter (captions-first → ASR)

X has a two-stage strategy rather than a pure caption ladder:

```
1. embedded captions?  (subtitles / automatic_captions, manual:en then auto:en)
        ├─ yes → download VTT → clean        (transcript_origin: embedded-captions)
        └─ no  → download smallest media → ASR
                 MacWhisper → Whisper CLI → whisper.cpp → cloud (opt-in)
                 (transcript_origin: macwhisper | whisper-cli | whisper-cpp | openai-api)
```

Most native X video and all Broadcasts/Spaces have no captions, so they
take the ASR branch. **ffmpeg is required** for the ASR branch on these
HLS sources — without it the downloaded fragment-stream is not a valid
container any ASR engine can open, so the run **fails fast with exit 7**
(install ffmpeg) BEFORE the large download, rather than failing cryptically
later. The ASR backend chain then stops at the first engine that is
**available** and **succeeds**; if none is available the run also exits `7`
(install MacWhisper or another engine, or use `--asr-allow-cloud`). See
[`references/asr_backends.md`](../../skills/transcript-fetcher/references/asr_backends.md)
for the backend interface, the `.env` config, and the component installer.

### Skool

Skool itself has no caption ladder — it either:

1. **Uses the author-supplied `metadata.transcript` field** verbatim
   (chosen_track_kind: `skool_manual`, chosen_track_lang: `unknown`),
   if present and non-empty.
2. **Delegates to YouTube/Vimeo** for the embedded video (using the
   ladder above).
3. **Flags `embed_source_unsupported`** (Loom/Wistia/native MP4) or
   `no_transcript_field` (no video, no transcript) when neither
   strategy yields a transcript. Description is still written under
   `--with-description`.

Override the YouTube/Vimeo order with `--prefer auto`. For arbitrary
policies, call the source adapter directly with your own
`fallback_ladder=` tuple — the API is more flexible than the two CLI
presets.

Full policy reference:
[`references/fallback_policy.md`](../../skills/transcript-fetcher/references/fallback_policy.md).

---

## 5. The JSON stat sidecar

### YouTube example (with `--with-description`)

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
    "got auto:ru-orig -> NSVTpCfBMK8.ru-orig.vtt",
    "description: wrote .description.md"
  ],
  "title": "Lecture 5 — Linear Algebra",
  "uploader": "MIT OpenCourseWare",
  "upload_date": "2024-02-14",
  "duration_sec": 3120,
  "description_path": "/tmp/talk.description.md",
  "embed_source": null,
  "embed_url": null
}
```

### Skool example (lesson embeds YouTube)

```json
{
  "source": "skool",
  "url": "https://www.skool.com/zero-one/classroom/.../?md=...",
  "video_id": "<lesson-id>",
  "chosen_track_kind": "auto",
  "chosen_track_lang": "en",
  "char_count": 37410,
  "speaker_turn_count": 0,
  "quality_flag": "english_auto_translation",
  "notes": [
    "delegated_to_youtube: https://youtu.be/...",
    "yt_notes: ERROR: HTTP Error 429: Too Many Requests ; got auto:en -> ....en.vtt",
    "description: wrote .description.md"
  ],
  "title": "TradingView + Chat GPT 5.5 is a Game Changer",
  "duration_sec": 2053,
  "description_path": "/tmp/lesson.description.md",
  "embed_source": "youtube",
  "embed_url": "https://youtu.be/..."
}
```

### Field reference

| Field | Meaning |
|---|---|
| `source` | `"youtube"` \| `"vimeo"` \| `"skool"`. |
| `chosen_track_kind` / `chosen_track_lang` | Which step of the ladder won; `"skool_manual"` / `"unknown"` when the Skool author-supplied transcript is used; both `null` when only the description was written (`--description-only` or transcript-less lesson). |
| `char_count` | Length of the cleaned plain text in characters. Useful for chunking. |
| `speaker_turn_count` | How many `>>` speaker-turn boundaries the VTT parser detected. Q&A and panels typically have 30–100; solo lectures 1–20. |
| `quality_flag` | One of `null`, `english_auto_translation`, `encoding_recovered`, `no_transcript_field`, `embed_source_unsupported`, `youtube_embed_unsupported`, `vimeo_embed_unsupported`, `skool_schema_mismatch`. Always inspect before consuming. |
| `notes` | Human-readable trace of every ladder step + delegation hop + description-write outcome. yt-dlp `WARNING:` lines are filtered out; only `ERROR:` or signal lines are preserved. |
| `title` / `uploader` / `upload_date` / `duration_sec` | Populated under `--with-description`; `uploader` / `upload_date` come from yt-dlp info.json for YouTube/Vimeo, are `null` for Skool (the lesson's title comes from Skool, not the embedded video). `duration_sec` for Skool is `videoLenMs / 1000`. |
| `description_path` | Absolute path to the `<out>.description.md` sidecar; `null` without `--with-description`. |
| `embed_source` / `embed_url` | Skool-only. `"youtube"` / `"vimeo"` / `"none"` / arbitrary host string (capped at 253 chars). Tells you which adapter Skool delegated to. |

---

## 6. The description sidecar (`<out>.description.md`)

Triggered by `--with-description`. Format: YAML frontmatter + optional
H1 + Markdown body.

### YouTube / Vimeo

```markdown
---
source: youtube
url: "https://youtu.be/NSVTpCfBMK8"
video_id: NSVTpCfBMK8
title: Lecture 5 — Linear Algebra
uploader: MIT OpenCourseWare
uploader_url: "https://www.youtube.com/@mit"
upload_date: 2024-02-14
duration_sec: 3120
view_count: 12345
like_count: 678
---

# Lecture 5 — Linear Algebra

<original description body, unchanged>
```

### Skool

```markdown
---
source: skool
url: "https://www.skool.com/zero-one/classroom/.../?md=..."
community: zero-one
classroom_id: a60f0bd2
lesson_id: 5dbd5cacecc34686890e838ef10f7312
title: TradingView + Chat GPT 5.5 is a Game Changer
embed_source: youtube
embed_url: "https://youtu.be/44ydkl1KS70"
duration_sec: 2053
thumbnail: "https://i.ytimg.com/vi/44ydkl1KS70/maxresdefault.jpg"
---

# TradingView + Chat GPT 5.5 is a Game Changer

<lesson body rendered from ProseMirror v2 JSON to Markdown>
```

ProseMirror nodes supported: `paragraph`, `heading` (clamped to H1–H6),
`bulletList` / `unorderedList` / `bullet_list` / `unordered_list`,
`orderedList` / `ordered_list`, `codeBlock` (with optional language),
`horizontalRule`, `blockquote`, `image`, `hardBreak`. Marks: `bold`,
`italic`, `code`, `strike`, `link`, `underline`. Unknown nodes emit
`<!-- unsupported node: type=<name> -->` and are recorded in
`stat.notes`. URL `src` / `href` are restricted to `http` / `https` /
`mailto` and parens are percent-encoded so a hostile lesson body
cannot break out of Markdown link syntax.

Full format reference:
[`references/description_metadata.md`](../../skills/transcript-fetcher/references/description_metadata.md).

---

## 7. Composition: fetch → summarize

The skill pairs naturally with
[`summarizing-meetings`](../../skills/summarizing-meetings/). Two-step
chain:

```bash
# Step 1: fetch the transcript (with description, if you want metadata).
./scripts/.venv/bin/python skills/transcript-fetcher/scripts/fetch.py \
    "https://youtu.be/<id>" \
    --out /tmp/talk.txt --with-description

# Step 2: read the JSON stat. Surface quality_flag warnings.
python3 -c "
import json
stat = json.load(open('/tmp/talk.txt.stat.json'))
if stat['quality_flag']:
    print(f'WARNING: {stat[\"quality_flag\"]}')
print('Title:', stat.get('title'))
"

# Step 3: pass the .txt to summarizing-meetings (or its educational
#         workflow extension /generate-detailed-meeting-summary).
```

The Skool path composes the same way — `summarizing-meetings` only
consumes the `.txt`. Its accompanying `.description.md` is a separate
artifact suitable for direct ingestion into RAG indexes, Obsidian, or
human review without re-decoding the stat JSON.

---

## 8. Troubleshooting

### "No caption track available for ..."

Means every step of the fallback ladder failed (YouTube/Vimeo path) or
the Skool lesson has neither a transcript field nor a delegatable
embed. The `notes` field of the (would-be) stat record carries
per-step diagnostics. Common causes:

| Note fragment | Cause | Fix |
|---|---|---|
| `rate-limit (http error 429)` | yt-dlp hit YouTube/Vimeo's anti-bot rate limit. | Wait 5–10 min, re-run. For batch, reduce concurrency. |
| `rate-limit (sign in to confirm you're not a bot)` | YouTube wants a logged-in cookie jar. | Pass `--cookies-file <Netscape cookies.txt>`. |
| `hard-failure (video unavailable)` | Video deleted, geoblocked, or region-restricted. | Confirm in a browser; no remedy from this skill. |
| `hard-failure (private video)` | Private upload. | Owner must make it public/unlisted; or pass cookies if you have access. |
| `no subtitle returned for X:Y` | The track simply doesn't exist for that language. | Try `--lang en` or `--prefer auto`. |
| `embed_source_unsupported` | Skool lesson embeds Loom / Wistia / native MP4. | No remedy; combine with `--with-description` for at least the lesson description. |
| `no_transcript_field` | Skool lesson has no video and no author-supplied transcript. | Combine with `--with-description` for the lesson description. |

### `SourceAuthError` (exit code 5)

Source returned HTTP 401 or 403. For Skool, the lesson belongs to a
private / paid community — pass `--cookies-file PATH` to a Netscape
cookies.txt with an authenticated browser session. For YouTube/Vimeo,
cookies fix age-gated and unlisted videos.

If the error persists with cookies supplied: the cookies expired (most
browsers rotate session tokens every few days). Re-export.

### `SourceRateLimitError` (exit code 6)

HTTP 429. Wait 5–10 minutes, then retry. Reduce batch concurrency.

### `MissingDependencyError` (exit code 7)

A required external tool is absent. The message + `details.remediation`
(with `--json-errors`) say which:

| Cause | Fix |
|---|---|
| yt-dlp not installed | `bash scripts/install.sh` (re-creates the venv). |
| **No ASR backend** for caption-less X media | Install MacWhisper (`mw`), or `./scripts/.venv/bin/python scripts/install_components.py --install-whisper` (Whisper CLI + ffmpeg), or run with `--asr-allow-cloud` + an API key. Run `install_components.py` for a status report. |
| ffmpeg required but absent | Only the Whisper/whisper.cpp backends need it; MacWhisper does not. `brew install ffmpeg` or `install_components.py --system --run`. |

This is distinct from exit `3` (`TranscriptFetchError`): exit 7 means
the toolchain is incomplete; exit 3 means the tools ran but no transcript
could be produced.

For X media specifically, see `transcript_origin` in the stat to confirm
which path/engine produced the text. The X path is **opt-in for the
cloud**: by default only local engines run, so no audio leaves your
machine unless you pass `--asr-allow-cloud`.

### `quality_flag: "english_auto_translation"`

Only English auto-captions were available. The transcript is technically
complete but is YouTube's auto-translation of speech that may have been
in another language. Idioms, names, and technical terms will be mangled.
Surface a warning. If a manual transcription is available offline
(Whisper, paid service), prefer it.

### `quality_flag: "encoding_recovered"`

The VTT file was not valid UTF-8; the parser fell back to CP1251 or
UTF-16. Text is correct as far as the codec ladder could tell, but
re-encode the source if you can — silent codec drift is hard to debug.

### `quality_flag: "skool_schema_mismatch"`

Skool's Next.js page rendered, but the lesson dict at `pageProps.course[...].course`
did not have the expected `metadata` shape. Most common cause: Skool
changed their schema. Inspect `stat.notes` for details and file an
issue with the offending lesson URL.

### Output looks repetitive (`"и я думаю что и я думаю что"`)

The dedup heuristic only collapses suffix-prefix overlaps of **3 word
tokens or longer** (a deliberately conservative threshold to avoid
false-positive merging on common 2-word phrases like "это нужно" / "и
вот"). Two-word overlaps slip through. If this hurts, post-process
with a more aggressive dedup downstream — or open an issue with a
real fixture.

### `>>` markers in places that aren't speaker turns

The parser anchors `>>` to the **start of a cue's text** only. A
talk about C++ stream operators or shell redirection that emits
`cout >> x` mid-cue is preserved verbatim. If you see a stray `\n\n>>`
that doesn't correspond to a speaker change, the source VTT had a
leading `>>` on that cue — that's the broadcast-caption convention,
and the parser is doing the right thing. Inspect the raw `.vtt` if
uncertain.

### Skool lesson HTML is huge / times out

The adapter caps HTTP body reads at 16 MB; anything larger raises
`TranscriptFetchError`. Genuine Skool lesson HTML is ~150-500 KB. If
you hit the cap, the URL was likely redirected (the adapter refuses
redirects to non-Skool hosts and non-http(s) schemes, but a
cooperative-malicious Skool redirect within `skool.com` could still
serve a large body).

---

## 9. Limitations and roadmap

- **Zoom and podcast adapters reserved, not implemented.** Slots are
  documented in
  [`references/supported_sources.md`](../../skills/transcript-fetcher/references/supported_sources.md).
- **No Whisper fallback.** Videos / native Skool MP4s with no captions
  cannot be transcribed by this skill. Pair with a separate Whisper
  invocation for caption-less content.
- **Cookies path appears in `ps` output** when forwarded to yt-dlp via
  `--cookies <path>`. The value (cookies themselves) is not exposed;
  only the file path is. Use a path outside of shared mounts when this
  matters.
- **Skool URL gate is strict.** Only `/<community>/classroom/<id>?md=<lesson>`
  is accepted; `/about`, `/calendar`, posts, comments are rejected by
  design.
- **Multi-source batch** dispatches per-URL via the same `_detect_source`
  allowlist. Mixed-source batches work; collisions across sources use
  per-URL `<id>.txt` naming.

---

## 10. Anti-patterns

| DO NOT | WHY |
|---|---|
| Strip `>>` markers from the output before summarization | They are speaker-turn boundaries. Removing them collapses a panel into a single voice. |
| Trust the `.txt` without reading the `.stat.json` | The `quality_flag` tells you whether the captions are high-quality manual subs, low-quality English auto-translation, or absent (Skool transcript-field-only path). |
| Assume Skool always needs cookies | Public communities (e.g. `zero-one`) serve lesson HTML without auth. Only private / paid ones answer 401/403. The skill itself never blocks on missing cookies up-front. |
| Loop the CLI shell-side over arbitrary URLs | Use `--batch <file>`. The batch path handles collisions, partial failures, mixed sources, and JSON-stat aggregation correctly. |
| `pip install -g yt-dlp` and bypass the venv | The skill invokes `python -m yt_dlp` from its per-skill `.venv`. A globally-installed yt-dlp may be a different version with different output formats. |
| Pass `--prefer auto` by default | Manual subs (when they exist) are higher fidelity than ASR. Default `--prefer manual` is correct for almost all use cases. |
| Hand-edit `<out>.description.md` and re-feed it to downstream tools without re-validating frontmatter | The YAML frontmatter is hand-rolled (escapes `\n\r  ` and quotes attacker-controlled keys); manual edits can break frontmatter parsers. |
| `chmod 644 cookies.txt` | The cookies loader refuses world-readable files. Keep `cookies.txt` at `0600`. |

---

## 11. References

- [SKILL.md](../../skills/transcript-fetcher/SKILL.md) — orchestration contract, anti-rationalization rules.
- [scripts/fetch.py](../../skills/transcript-fetcher/scripts/fetch.py) — CLI entry point.
- [scripts/sources/youtube.py](../../skills/transcript-fetcher/scripts/sources/youtube.py) — yt-dlp adapter, fallback ladder, snapshot-aware VTT discovery, info-json piggy-back.
- [scripts/sources/vimeo.py](../../skills/transcript-fetcher/scripts/sources/vimeo.py) — minimal Vimeo adapter (shares helpers with YouTube).
- [scripts/sources/skool.py](../../skills/transcript-fetcher/scripts/sources/skool.py) — Skool lesson adapter (HTML scrape + ProseMirror render + embed delegation).
- [scripts/sources/_vtt_to_text.py](../../skills/transcript-fetcher/scripts/sources/_vtt_to_text.py) — pure-Python WebVTT cleaner.
- [scripts/sources/_stat.py](../../skills/transcript-fetcher/scripts/sources/_stat.py) — shared `TranscriptStat` dataclass + sidecar writer + error classes.
- [scripts/sources/_description.py](../../skills/transcript-fetcher/scripts/sources/_description.py) — `.description.md` writer (YAML frontmatter + Markdown body).
- [scripts/sources/_cookies.py](../../skills/transcript-fetcher/scripts/sources/_cookies.py) — Netscape cookies.txt loader + restricted-redirect opener.
- [scripts/sources/_prosemirror.py](../../skills/transcript-fetcher/scripts/sources/_prosemirror.py) — ProseMirror/TipTap v2 → Markdown for Skool lesson bodies.
- [references/youtube_caption_format.md](../../skills/transcript-fetcher/references/youtube_caption_format.md) — `>>`, `&gt;`, rolling captions, `ru-orig` semantics.
- [references/fallback_policy.md](../../skills/transcript-fetcher/references/fallback_policy.md) — language ladder rationale.
- [references/supported_sources.md](../../skills/transcript-fetcher/references/supported_sources.md) — current and planned source slots, adapter contract.
- [references/description_metadata.md](../../skills/transcript-fetcher/references/description_metadata.md) — `.description.md` format for YouTube and Skool.
- [references/skool_adapter.md](../../skills/transcript-fetcher/references/skool_adapter.md) — Skool auth flow, schema notes, embed delegation rules, ProseMirror node coverage.
</content>
</invoke>