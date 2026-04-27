# Supported Sources

The skill is source-agnostic by design. Each platform is one adapter
file under `scripts/sources/`. A new source is added by writing one
new file plus one extra branch in `_detect_source` in `fetch.py`.

## 1. Currently supported

| Source | Adapter | Status | Notes |
| --- | --- | --- | --- |
| YouTube | `scripts/sources/youtube.py` | Active | yt-dlp; ladder default `manual:ru -> auto:ru-orig -> auto:ru -> auto:en` |

## 2. Planned slots (not implemented)

| Source | Likely adapter | Approach | Why deferred |
| --- | --- | --- | --- |
| Vimeo | `scripts/sources/vimeo.py` | yt-dlp also handles Vimeo, so the diff would be small — mostly the URL detection branch and language ladder defaults | No urgent demand from the meeting-summary workflow |
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
    **kwargs,
) -> TranscriptStat:
    ...
```

And reuse the common helpers:

- `_vtt_to_text.vtt_file_to_plain` for cleaning.
- `_vtt_to_text.count_speaker_turns` for the stat field.
- `TranscriptStat` for the return shape (so the CLI's stat handling
  works unchanged).

## 4. URL detection

`fetch.py::_detect_source` parses the URL with `urllib.parse.urlparse`
and checks the hostname against an explicit **allowlist**. Substring
matching on the URL string was removed in v1.1 because it accepted
typosquats like `phishing-youtu.be.evil.com` and path-embedded
`?ref=youtube.com`.

Adding a new source means three concrete edits:

1. Add the new hosts to a hostname set in `fetch.py`. Today there is
   only `_YOUTUBE_HOSTS`; for a second source, refactor into a
   `host → source` lookup table:

   ```python
   _SOURCE_BY_HOST: dict[str, str] = {}
   for h in ("youtu.be", "www.youtu.be", "youtube.com", ...):
       _SOURCE_BY_HOST[h] = "youtube"
   for h in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
       _SOURCE_BY_HOST[h] = "vimeo"
   ```

   Then `_detect_source` becomes a single dict lookup.

2. Add one dispatch branch in `_fetch_one`:

   ```python
   if source == "vimeo":
       stat = fetch_vimeo_transcript(url, out_path, fallback_ladder=ladder)
   ```

3. Drop the new adapter at `scripts/sources/<source>.py`. Reuse the
   common helpers (`_vtt_to_text`, `TranscriptStat`).

Keep the dispatch flat. Do not introduce a registry pattern unless we
have ≥ 4 sources — three branches in a dict are still more readable
than reflection.
