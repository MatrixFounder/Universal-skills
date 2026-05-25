# Skool Adapter

Skool is an auth-walled classroom platform (Next.js + React). A lesson
URL has the shape:

    https://www.skool.com/<community>/classroom/<classroom-id>?md=<lesson-id>

The adapter (`scripts/sources/skool.py`) does NOT download Skool's
native mp4 player. Instead it scrapes the lesson page, reads the
lesson metadata, and either uses an author-supplied transcript field
or delegates the embedded video URL to the YouTube/Vimeo adapter.

## 1. Authentication (optional)

**Cookies are NEVER required up-front.** The adapter always attempts
the fetch first; only when Skool replies HTTP 401 or 403 does it raise
`SourceAuthError` (exit code 5).

- **Public communities** (e.g. `zero-one`) serve lesson HTML to
  anyone, including agents running without any browser session. The
  CLI works with no `--cookies-file` argument at all.
- **Private / paid communities** redirect anonymous requests to the
  login page; pass `--cookies-file PATH` to a Netscape `cookies.txt`
  export of your authenticated browser session.

Export cookies with a browser extension such as *Get cookies.txt
LOCALLY* (or any equivalent producing the Netscape format).

```bash
# Public community — no auth needed.
./scripts/.venv/bin/python scripts/fetch.py \
    "https://www.skool.com/zero-one/classroom/AAA?md=BBB" \
    --out lesson.txt --with-description

# Private community — cookies.txt expected.
./scripts/.venv/bin/python scripts/fetch.py \
    "https://www.skool.com/private-foo/classroom/AAA?md=BBB" \
    --out lesson.txt --with-description \
    --cookies-file ~/.config/skool-cookies.txt
```

When supplied, the cookies file:

- Is read once at startup via `http.cookiejar.MozillaCookieJar` (stdlib).
- Must be `0600` (not world-readable) and not a symlink — the loader
  rejects both with a clear error.
- Includes both expired and session cookies (`ignore_expires=True`,
  `ignore_discard=True`).
- Is never written to or copied. It lives wherever you put it.

Auth failure surfaces as a dedicated `SourceAuthError` (exit code 5
in the CLI; `error_type: "SourceAuthError"` in `--json-errors`).

## 2. Page parsing

The lesson HTML embeds all relevant state inside
`<script id="__NEXT_DATA__" type="application/json">{...}</script>`.
The adapter regex-extracts that block, JSON-decodes it, then:

1. Reads `props.pageProps.selectedModule` — must equal `?md=<lesson-id>`.
   A mismatch usually means we landed on a public redirect; the
   adapter raises `SkoolSchemaError`.
2. Recursively walks `props.pageProps.course` to find the dict whose
   `id` equals `selectedModule`.
3. Reads `metadata.{title, desc, videoLink, videoLenMs,
   videoThumbnail, resources, transcript}`.

If the user is not authenticated, Skool serves a public landing page
that has no `selectedModule` in its `pageProps`. That path raises
`SkoolSchemaError` with a hint to verify the cookies file.

## 3. ProseMirror desc

`metadata.desc` is **not** Markdown — it's TipTap/ProseMirror JSON
prefixed with a version tag like `[v2]`:

```
[v2][
    {"type": "paragraph", "content": [...]},
    {"type": "horizontalRule"},
    {"type": "codeBlock", "attrs": {"language": "bash"}, ...}
]
```

The `_prosemirror.py` module converts this to Markdown. Supported
nodes/marks cover the common subset (paragraph, heading, lists,
codeBlock, horizontalRule, blockquote, image, hardBreak; marks: bold,
italic, code, strike, link, underline). Unknown node types render as
HTML comments and are recorded in `stat.notes`.

## 4. Embed delegation

The lesson's `metadata.videoLink` is classified by hostname:

| Host | Action |
|------|--------|
| `youtu.be`, `*.youtube.com` | Delegate to `fetch_youtube_transcript` |
| `vimeo.com`, `*.vimeo.com` | Delegate to `fetch_vimeo_transcript` |
| Any other host (Loom, Wistia, native Skool mp4) | `quality_flag = "embed_source_unsupported"`; description is still written |
| `None` | `quality_flag = "no_transcript_field"` (lesson has no video and no transcript field) |

When the delegated YouTube/Vimeo adapter raises an exception, the
Skool adapter sets `quality_flag = "<host>_embed_unsupported"` and
preserves the exception's message in `stat.notes`. Description, when
requested, is still written — partial output beats no output.

## 5. Author-supplied transcript field

If `metadata.transcript` is a non-empty string, the adapter writes it
verbatim to `<out>.txt` with:

- `chosen_track_kind = "skool_manual"`
- `chosen_track_lang = "unknown"` (Skool doesn't track the language)
- `embed_source` set to whatever `videoLink` classifies as (or `"none"`)

This path bypasses embed delegation entirely — the author already
curated the transcript, no need to re-fetch from YouTube.

## 6. Output shape

| Output | When |
|--------|------|
| `<out>.txt` | Whenever a transcript was obtained (delegated or transcript-field) |
| `<out>.txt.stat.json` | Always |
| `<out>.description.md` | Only with `--with-description` |

`stat.embed_source` / `stat.embed_url` are populated to let downstream
pipelines know whether the transcript came from a YouTube/Vimeo
delegation or from Skool itself.

## 7. Limitations

- No headless browser. Skool re-renders some content client-side; the
  adapter relies on data already embedded in `__NEXT_DATA__` at SSR.
- No native-mp4 transcription. If a lesson uses Skool's native player
  and has no transcript field, no transcript is produced — only the
  description.
- No batch authentication. One cookies file per CLI invocation.
- No automatic cookie refresh. When cookies expire you get a
  `SourceAuthError` and must re-export.
