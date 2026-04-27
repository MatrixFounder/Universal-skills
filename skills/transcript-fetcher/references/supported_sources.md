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

`fetch.py::_detect_source` does shallow string matching on the URL.
Adding a new source means adding one branch:

```python
if "vimeo.com" in u:
    return "vimeo"
```

and one dispatch in `_fetch_one`:

```python
if source == "vimeo":
    stat = fetch_vimeo_transcript(url, out_path, fallback_ladder=ladder)
```

Keep the dispatch flat. Do not introduce a registry pattern unless we
have ≥ 4 sources — three branches in an `if/elif` chain are still more
readable than reflection.
