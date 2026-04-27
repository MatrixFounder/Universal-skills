"""Source adapters for transcript-fetcher.

Each adapter knows how to:
1. Recognise a URL/identifier for its source platform.
2. Pull captions in a consistent intermediate format (currently WebVTT).
3. Convert that to clean plain text + a small JSON stat record.

Currently shipped:
    youtube — YouTube videos via yt-dlp.

Planned (slot reserved): vimeo, zoom, podcast (RSS + Whisper).
"""
