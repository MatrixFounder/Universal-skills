# Supported Sources

The skill is source-agnostic by design. Each platform is one adapter
file under `scripts/sources/`. A new source is added by writing one
new file plus one extra entry in `_SOURCE_BY_HOST` in `fetch.py`.

## 1. Currently supported

| Source | Adapter | Status | Notes |
| --- | --- | --- | --- |
| YouTube | `scripts/sources/youtube.py` | Active | yt-dlp; ladder default `manual:ru -> auto:ru-orig -> auto:ru -> auto:en`. Supports `--with-description` via `--write-info-json`. |
| Vimeo | `scripts/sources/vimeo.py` | Active | yt-dlp; minimal ladder `manual:en -> auto:en` by default. Vimeo auto-captions are rare — expect `no_caption_track` for some videos. |
| Skool | `scripts/sources/skool.py` | Active | `--cookies-file` is OPTIONAL — public communities (e.g. `zero-one`) serve lesson HTML without auth; private/paid communities respond with HTTP 401/403 and need a Netscape `cookies.txt`. Parses `__NEXT_DATA__`, picks lesson by `?md=<lesson-id>`, then either uses the author-uploaded transcript or delegates the embedded YouTube/Vimeo URL to the corresponding adapter. |

## 2. Planned slots (not implemented)

| Source | Likely adapter | Approach | Why deferred |
| --- | --- | --- | --- |
| Zoom Cloud | `scripts/sources/zoom.py` | Zoom exports VTT directly when "audio transcript" is enabled in account settings; the adapter would accept a Zoom share URL + access token and download the existing VTT | Requires per-account auth; not a single-URL problem |
| Podcast (RSS + Whisper) | `scripts/sources/podcast.py` | Resolve enclosure URL from RSS, run a local Whisper model, produce a synthetic VTT, then reuse the same cleaner | Whisper adds heavy GPU/CPU deps; better as a separate optional install path |

## 3. Adapter contract

Every source adapter MUST expose:

```python
def fetch_<source>_transcript(
    url: str,
    out_path: Path,
    *,
    fallback_ladder: Iterable[tuple[str, str]] = ...,
    timeout_sec: int = ...,
    cookies_file: Optional[Path] = None,
    with_description: bool = False,
    description_only: bool = False,
    **kwargs,
) -> TranscriptStat:
    ...
```

And reuse the common helpers:

- `_vtt_to_text.vtt_file_to_plain` / `vtt_file_to_plain_meta` for cleaning.
- `_vtt_to_text.count_speaker_turns` for the stat field.
- `_stat.TranscriptStat` for the return shape (so the CLI's stat handling
  works unchanged).
- `_stat.write_stat_sidecar` for the `.stat.json` writer.
- `_description.write_description_md` for the `.description.md` writer
  (skip when `with_description=False`).

## 4. URL detection

`fetch.py::_detect_source` parses the URL with `urllib.parse.urlparse`
and checks the hostname against a `_SOURCE_BY_HOST: dict[str, str]`
lookup. Substring matching on the URL string was removed in v1.1 to
prevent typosquats like `phishing-youtu.be.evil.com` and
path-embedded `?ref=youtube.com`.

Adding a new source means three concrete edits:

1. Append the new hosts to `_SOURCE_BY_HOST` in `fetch.py`:

   ```python
   for h in ("zoom.us", "us02web.zoom.us", ...):
       _SOURCE_BY_HOST[h] = "zoom"
   ```

2. Add one dispatch branch in `_fetch_one`:

   ```python
   if source == "zoom":
       stat = fetch_zoom_transcript(url, out_path, fallback_ladder=ladder, ...)
   ```

3. Drop the new adapter at `scripts/sources/<source>.py`. Reuse the
   common helpers under `_stat.py`, `_description.py`, `_vtt_to_text.py`,
   and `_cookies.py` (for auth-walled sources).

Keep the dispatch flat. The current set is exactly the size where a
plain `if/elif` chain is still more readable than reflection.
