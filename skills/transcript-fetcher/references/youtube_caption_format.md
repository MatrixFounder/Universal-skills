# YouTube Caption Format — Reference

YouTube serves captions as WebVTT (`.vtt`) files. The flavour YouTube
emits is verbose and contains several artefacts that need cleaning
before the text is useful for downstream summarization. This file
documents what those artefacts are and why the cleaner does what it
does.

## 1. File header

```
WEBVTT
Kind: captions
Language: ru
```

The first three lines identify the file as WebVTT, the kind of cue
track (always `captions` for our purposes), and the language. The
cleaner drops these — they carry no transcript content.

## 2. Cue blocks

Each cue is a small block:

```
00:00:09.390 --> 00:00:11.350 align:start position:0%

здравствуйте.<00:00:10.000><c> Добрый</c><00:00:10.320><c> день,</c>
```

The cleaner drops:

- The timestamp line (matched by `^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->`).
- Any standalone numeric line (cue index — some tools add them).
- Inline timing tags `<HH:MM:SS.mmm>` and `<c>...</c>` style markers
  (regex `<[^>]+>`).

## 3. HTML entity encoding

YouTube encodes literal `>` characters as `&gt;`. Speaker-change markers
appear in the wild as `&gt;&gt;`, and ampersands as `&amp;`. The cleaner
runs `html.unescape()` on every cue line so the downstream text reads
as plain UTF-8.

## 4. Rolling-caption overlap

This is the most important transformation. YouTube emits cues that
extend the previous cue character-by-character so the on-screen reader
sees a smooth scroll:

```
00:00:00.000 --> 00:00:01.000  | "А вот это уже"
00:00:01.000 --> 00:00:02.000  | "А вот это уже интересно"
00:00:02.000 --> 00:00:03.000  | "А вот это уже интересно сегодня"
```

A naive concatenation yields the same prefix three times. The cleaner
deduplicates by keeping the longest extension of each rolling chain.

## 5. The `>>` speaker-turn marker

In multi-speaker recordings, YouTube auto-captions insert `>>` (rendered
as `&gt;&gt;` in the file) at the start of each new speaker's segment.
This is the only attribution signal available without speaker
diarisation. We preserve it as a paragraph break (`\n\n>> `) so a
downstream LLM can still distinguish "Alice: ..." from "Bob: ...".

If you strip these markers, multi-speaker meetings collapse into a
single undifferentiated stream. **Do not strip them.**

## 6. `ru` vs `ru-orig` vs `en`

YouTube's caption track menu can offer multiple Russian tracks. They
are NOT equivalent:

| Track id | What it is | Quality |
| --- | --- | --- |
| `ru` (manual) | User-uploaded human transcription | Best |
| `ru-orig` (auto) | ASR of the original Russian audio | Good |
| `ru` (auto) | YouTube auto-translation TO Russian (from English ASR) | Poor — sounds Russian, but technical terms and names mangled |
| `en` (auto) | ASR + auto-translation to English | Worst for non-English source |

Our default fallback ladder reflects this: `manual:ru` -> `auto:ru-orig`
-> `auto:ru` -> `auto:en`. The last step is a last-resort safety net
and triggers a `quality_flag = "english_auto_translation"` in the stat
sidecar so callers can warn the user.

## 7. yt-dlp invocation specifics

We invoke yt-dlp with:

- `--skip-download` — never pull the video bytes; we only want subs.
- `--sub-format vtt` — pin output format so the cleaner sees exactly
  one shape.
- `--sub-langs <lang>` + (`--write-subs` | `--write-auto-subs`) — pick
  one track at a time; let the fallback ladder handle priority.
- `--output <id>.<ext>` — deterministic filename so we can find the
  result.

We invoke via `python -m yt_dlp` from the per-skill venv so the user's
system `yt-dlp` (which may be a different version) does not interfere.
