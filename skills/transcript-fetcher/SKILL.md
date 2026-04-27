---
name: transcript-fetcher
description: >-
  Use when the user wants a clean plain-text transcript of a video URL
  (YouTube today; Vimeo/Zoom/podcast slots reserved). Fetches captions
  via yt-dlp, applies a manual->auto language fallback, dedups rolling
  captions, preserves >> speaker turns, and emits a JSON stat sidecar.
tier: 2
version: 1.0
status: active
changelog: Initial release — YouTube adapter, ru/ru-orig/en fallback ladder, offline tests.
---

# Transcript Fetcher

**Purpose**: Given a video URL, produce a clean plain-text transcript
ready for downstream summarization or analysis. Single responsibility:
fetch + clean. Composes well with `summarizing-meetings` (run this
first, then feed the resulting `.txt` to that skill).

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**

- "I'll just paste the URL into the model and ask it to transcribe" -> **WRONG**. Models do not have audio access and will hallucinate. Always run `fetch.py` and read back the resulting `.txt`.
- "Manual `ru` failed, I'll just use `en` auto-translation, no warning needed" -> **WRONG**. Auto-translated English subtitles destroy idioms, names, and technical terms. The `quality_flag: english_auto_translation` in the stat MUST be surfaced to the user.
- "I'll skip writing the JSON stat sidecar, the .txt is enough" -> **WRONG**. The sidecar records WHICH track was picked. Without it, downstream cannot tell whether the transcript is high-quality manual subs or low-quality auto-translation.
- "The transcript has weird `>>` markers, I'll strip them" -> **WRONG**. Those are speaker-turn boundaries. Removing them collapses multi-speaker meetings into a single voice and ruins downstream attribution.
- "Auto-generated Russian (`ru-orig`) is garbage, I'll prefer `en` instead" -> **WRONG**. `ru-orig` is the actual Russian audio transcribed; `ru` (without `-orig`) is often an English auto-translation back to Russian. `ru-orig` > `ru` > `en`.
- "I'll add `ffmpeg` to the deps just in case" -> **WRONG**. WebVTT parsing is pure Python in this skill. Do not pull in heavy dependencies.

## 2. Capabilities

- **Fetch** YouTube captions via `yt-dlp` (no audio download).
- **Fall back** through a configurable ladder (default for ru: manual ru -> auto ru-orig -> auto ru -> auto en).
- **Clean** WebVTT to plain text: strip timestamps, inline timing tags, and rolling-caption overlap; decode HTML entities.
- **Preserve** `>>` speaker-turn markers as paragraph breaks.
- **Emit** a JSON stat sidecar (chosen track, char count, speaker-turn count, quality flag).
- **Batch** mode for processing multiple URLs from a text file.
- **Source-agnostic** architecture: each platform is one file under `scripts/sources/`. Slots reserved for Vimeo/Zoom/podcast.

## 3. Execution Mode

- **Mode**: `script-first`
- **Why this mode**: Fetching captions, parsing WebVTT, deduplicating rolling captions, and applying the fallback ladder are deterministic operations with > 5 lines of business logic. The CLI is the contract; SKILL.md is orchestration.

## 4. Script Contract

- **Install** (one-time):
  ```bash
  bash skills/transcript-fetcher/scripts/install.sh
  ```
- **Single URL**:
  ```bash
  cd skills/transcript-fetcher
  ./scripts/.venv/bin/python scripts/fetch.py <URL> --out <path/to/output.txt>
  ```
  Optional flags: `--lang ru` (default), `--prefer manual|auto` (default `manual`), `--json-errors`.
- **Batch**:
  ```bash
  ./scripts/.venv/bin/python scripts/fetch.py --batch urls.txt --out-dir transcripts/
  ```
- **Inputs**: A YouTube URL (or a file with one URL per line). Empty lines and `#` comments in the batch file are ignored.
- **Outputs**:
  - `<out>.txt` — clean plain text, UTF-8.
  - `<out>.txt.stat.json` — sidecar with the chosen track and quality flag.
  - One JSON stat record per URL on stdout.
- **Failure semantics**: Non-zero exit. With `--json-errors`, stderr carries a single JSON line `{v, error, code, type, details?}`. Exit codes: `2` usage error, `3` no caption track in fallback ladder, `4` partial batch failure, `1` unexpected.
- **Idempotency**: Re-running overwrites the output file and sidecar. yt-dlp itself caches nothing the skill depends on; behaviour is reproducible given network availability.
- **Dry-run support**: Not currently exposed as a flag. Inspect the fallback ladder via `_build_ladder` if needed.

## 5. Safety Boundaries

- **Allowed scope**: Reads from the network (yt-dlp HTTPS to YouTube). Writes ONLY to the user-specified `--out` / `--out-dir` path and a `.stat.json` sidecar next to it.
- **Default exclusions**: Never downloads the video itself (only `--skip-download` + subtitle tracks). Never writes to any path the user did not explicitly pass via `--out` / `--out-dir`.
- **Destructive actions**: None. The script does not delete or modify any pre-existing files outside the chosen output paths. In batch mode, output path collisions are handled per `--on-collision={error,skip,suffix}` (default: `error`).
- **Optional artifacts**: The JSON stat sidecar is mandatory in single-URL mode (it is the audit trail for which track was used).
- **URL allowlist**: Source dispatch is hostname-based against an explicit allowlist (`youtu.be`, `youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtube-nocookie.com`). URLs that merely contain `youtube.com` as a substring elsewhere are rejected.

## 6. Validation Evidence

- **Local verification**:
  ```bash
  cd skills/transcript-fetcher
  ./scripts/.venv/bin/python -m unittest discover -s scripts/tests
  ```
  All offline tests must pass without network. The end-to-end network test is gated behind `TRANSCRIPT_FETCHER_E2E=1`.
- **Skill-validator (structural)**:
  ```bash
  python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/transcript-fetcher
  ```
- **Skill-validator (security)**:
  ```bash
  python3 .claude/skills/skill-validator/scripts/validate.py skills/transcript-fetcher
  ```
- **Expected evidence**: Both validators exit 0; unittest reports `OK`.

## 7. Instructions

### Step 1: Verify environment

If `scripts/.venv/` does not exist, run `bash scripts/install.sh` first.
The install script is idempotent — safe to re-run.

### Step 2: Choose mode

| Input | Mode | Command form |
| --- | --- | --- |
| Single URL | `single` | `fetch.py <URL> --out path.txt` |
| List of URLs in a file | `batch` | `fetch.py --batch urls.txt --out-dir dir/` |

### Step 3: Pick a fallback strategy

Default is `--lang ru --prefer manual`. This tries:

1. `manual:ru` — user-uploaded Russian subtitles (highest quality).
2. `auto:ru-orig` — YouTube auto-captions of the original Russian audio (good).
3. `auto:ru` — YouTube auto-translation TO Russian (often noisy if speech was in another language).
4. `auto:en` — English auto-captions as last resort (will set `quality_flag = english_auto_translation`).

For non-Russian content, pass `--lang en` (or another ISO code). For
non-Russian languages the `lang-orig` step is skipped — it is a YouTube
quirk that mainly matters for non-English speech.

### Step 4: Run the CLI

Capture stdout (it carries the JSON stat). Read the stat to confirm
which track was used:

```bash
./scripts/.venv/bin/python scripts/fetch.py \
    "https://youtu.be/NSVTpCfBMK8" \
    --out /tmp/talk.txt
# stdout: {"source":"youtube","url":"...","chosen_track_kind":"auto","chosen_track_lang":"ru-orig", ...}
```

### Step 5: Inspect quality

Open the generated `<out>.txt.stat.json`. If `quality_flag` is set
(currently only `"english_auto_translation"`), surface a warning to
the user before passing the transcript to a downstream summarizer:

> ⚠️ TRANSCRIPT QUALITY: only English auto-translation was available
> for this URL. Idioms, proper names, and technical terms may be
> distorted. Consider asking the user for a manual transcription.

### Step 6: Hand off

The clean `.txt` is now ready for `summarizing-meetings` or any other
downstream consumer. Pass the path; do not paste the contents inline
(transcripts are often large).

## 8. Workflows

```text
- [ ] Verify scripts/.venv/ exists (run install.sh otherwise)
- [ ] Decide single vs batch mode
- [ ] Run fetch.py with the chosen language and preference
- [ ] Read the JSON stat sidecar
- [ ] Surface quality_flag warning if set
- [ ] Hand .txt path to downstream skill
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Always read the stat sidecar after fetching | Trust the .txt without checking which track was used |
| Prefer `ru-orig` over `ru` for Russian content | Pick the first track that returns text |
| Pass batch URLs through a file | Loop the CLI shell-side with arbitrary URLs |
| Surface `quality_flag` in any user-visible output | Silently downgrade to English auto-translation |
| Use `--json-errors` in CI/automation pipelines | Parse free-form stderr |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "yt-dlp is on `$PATH` so I can just call it" | The skill invokes `python -m yt_dlp` from the per-skill venv. The system `yt-dlp` may be a different version with different output. |
| "The `>>` markers are clutter" | They are paragraph breaks for speaker turns. Downstream summarizers attribute statements by them. |
| "Rolling-caption dedup is overkill, just keep the longest cue" | The dedup IS keeping the longest cue. Without it, the same sentence would appear 3-4 times. |
| "I'll add a Vimeo adapter inline in fetch.py" | Add it as `scripts/sources/vimeo.py`. Each source is its own file. |

## 10. Examples

See `examples/`:

- `example_input_url.txt` — batch input format.
- `example_output_plain.txt` — what a cleaned transcript looks like (excerpt).
- `example_output_stat.json` — what the stat sidecar contains.

## 11. Resources

- `scripts/fetch.py` — CLI entry point.
- `scripts/sources/youtube.py` — YouTube adapter (yt-dlp orchestration + fallback ladder).
- `scripts/sources/_vtt_to_text.py` — pure-Python WebVTT cleaner.
- `scripts/install.sh` — venv bootstrap.
- `scripts/requirements.txt` — pinned deps (single source of truth for the yt-dlp version range).
- `scripts/tests/` — offline unit tests + opt-in E2E network test.
- `references/youtube_caption_format.md` — what `>>`, `&gt;`, rolling captions, and `ru-orig` actually mean.
- `references/fallback_policy.md` — the language ladder and why it is in this order.
- `references/supported_sources.md` — current and planned source slots.
- [`docs/Manuals/transcript-fetcher_manual.md`](../../docs/Manuals/transcript-fetcher_manual.md) — user-facing manual with quick reference, troubleshooting, and composition recipes.

## 12. Composition

- **Composes well with `summarizing-meetings`**: run `transcript-fetcher` first to get a clean `.txt`, then pass that file to `summarizing-meetings` for a structured Markdown summary. The two skills are intentionally separate — fetching is a deterministic file operation; summarizing is a prompt-first reasoning task.
