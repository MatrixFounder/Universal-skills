"""Skool source adapter.

A Skool classroom lesson URL has the shape::

    https://www.skool.com/<community>/classroom/<classroom-id>?md=<lesson-id>

The lesson page is server-rendered as a Next.js app — all lesson data
lives inside the ``__NEXT_DATA__`` JSON blob embedded in the HTML.
Pages without an ``?md=`` query (community landing, ``/about``,
``/calendar`` …) are rejected with a usage error.

What this adapter does:

1. **Fetch**: fires a single ``GET`` for the lesson URL via :mod:`_cookies`
   (which builds a minimal-handler opener). Cookies are OPTIONAL —
   public communities serve lesson HTML without any auth; private/paid
   communities reply HTTP 401/403 and the caller must supply
   ``--cookies-file <Netscape cookies.txt>``.
2. **Parse**: extracts ``__NEXT_DATA__``, walks the course tree to the
   node whose ``id`` matches ``pageProps.selectedModule``. From its
   ``metadata`` it reads ``title``, ``desc`` (ProseMirror v2 JSON),
   ``videoLink``, ``videoLenMs``, ``videoThumbnail``, ``resources``,
   and the optional ``transcript`` field.
3. **Embed delegation**: if ``videoLink`` resolves to YouTube or Vimeo,
   the adapter calls the existing YouTube/Vimeo fetcher to pull the
   transcript. Other hosts (Loom, Wistia, native Skool mp4) are
   flagged ``embed_source_unsupported`` — description is still written.
4. **Transcript field**: if ``metadata.transcript`` is non-empty, it
   wins over embed delegation (the author already curated it).
5. **Description**: with ``--with-description`` we always write
   ``<out>.description.md`` containing a Markdown rendering of
   ``metadata.desc`` (via :mod:`_prosemirror`).

The adapter never downloads native Skool mp4 — Whisper / video
decoding is intentionally out of scope.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from ._cookies import CookieFileError, build_authenticated_opener
from ._description import write_description_md
from ._prosemirror import ProseMirrorError, prosemirror_to_markdown
from ._stat import (
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
    TranscriptStat,
)
from ._vtt_to_text import count_speaker_turns


SKOOL_HOSTS = frozenset(
    {"skool.com", "www.skool.com", "app.skool.com"}
)

DEFAULT_TIMEOUT_SEC = 60

# Maximum HTML body we'll read from Skool. 16 MB is generous for any
# plausible lesson page and bounds the parser against hostile origins
# streaming arbitrary bytes (and against runaway redirect targets).
_MAX_HTML_BYTES = 16 * 1024 * 1024

# Match the script tag emitted by Next.js (the JSON is opaque to a strict
# HTML parser anyway, so a non-greedy regex on the raw bytes is fine).
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


class SkoolUrlError(ValueError):
    """Raised when a Skool URL is well-formed but not a lesson URL."""


class SkoolSchemaError(RuntimeError):
    """Raised when __NEXT_DATA__ does not contain the expected lesson shape."""


@dataclass
class SkoolLessonRef:
    """Parsed components of a Skool lesson URL."""

    community: str
    classroom_id: str
    lesson_id: str


def parse_skool_lesson_url(url: str) -> SkoolLessonRef:
    """Validate and parse a Skool lesson URL.

    Raises :class:`SkoolUrlError` for any non-lesson URL (community
    landing pages, calendar, posts, etc).
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in SKOOL_HOSTS:
        raise SkoolUrlError(f"not a Skool host: {host!r}")
    path = parsed.path.rstrip("/")
    parts = path.split("/")
    if len(parts) < 4 or parts[2] != "classroom" or not parts[3]:
        raise SkoolUrlError(
            f"not a lesson URL — expected /<community>/classroom/<id>?md=<lesson>, got: {path}"
        )
    community = parts[1]
    classroom_id = parts[3]
    qs = parse_qs(parsed.query)
    md_vals = qs.get("md")
    if not md_vals or not md_vals[0]:
        raise SkoolUrlError(
            "Skool lesson URL is missing the ?md=<lesson-id> query parameter"
        )
    return SkoolLessonRef(
        community=community,
        classroom_id=classroom_id,
        lesson_id=md_vals[0],
    )


def fetch_skool_transcript(
    url: str,
    out_path: Path,
    *,
    cookies_file: Optional[Path] = None,
    fallback_ladder: Iterable[tuple[str, str]] = (("manual", "ru"),),
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    with_description: bool = False,
    description_only: bool = False,
    html_override: Optional[str] = None,
    _youtube_fetcher: Optional[Any] = None,
    _vimeo_fetcher: Optional[Any] = None,
) -> TranscriptStat:
    """Fetch a Skool lesson.

    Args:
        url: Lesson URL (must contain ``/classroom/<id>?md=<lesson>``).
        out_path: Where to write the transcript (when available).
        cookies_file: Optional Netscape cookies.txt with an authenticated
            Skool session. Public communities (e.g. ``zero-one``) serve
            lesson HTML without any auth; only private / paid
            communities respond with HTTP 401/403 and need a cookies
            file. The adapter always attempts the fetch first and
            raises :class:`SourceAuthError` only on a real 401/403.
        fallback_ladder: Forwarded to the delegated YouTube/Vimeo
            fetcher when the lesson embeds one of those.
        timeout_sec: HTTP fetch timeout.
        with_description: If True, write a ``.description.md`` sidecar
            (Skool description content is usually rich and worth saving
            regardless of whether a transcript is available).
        description_only: Skip the transcript path entirely. The
            ``.txt`` file is NOT created; the stat reports the
            description outcome only.
        html_override: For testing — bypass the network and parse this
            HTML directly. The ``cookies_file`` argument is ignored
            when set.
        _youtube_fetcher / _vimeo_fetcher: Injected for tests. When
            ``None``, the real ``fetch_youtube_transcript`` /
            ``fetch_vimeo_transcript`` are loaded lazily so that
            test patches on the function attribute take effect.
    """
    out_path = Path(out_path)
    ref = parse_skool_lesson_url(url)

    # Mirror youtube/vimeo: --description-only implies --with-description so
    # at least the sidecar is produced. (CLI catches this combination earlier
    # at exit code 2, but library-level callers also need the guarantee.)
    if description_only:
        with_description = True

    html = html_override
    if html is None:
        html = _fetch_lesson_html(
            url=url, cookies_file=cookies_file, timeout_sec=timeout_sec
        )

    lesson = _extract_lesson(html, lesson_id=ref.lesson_id)

    md = lesson.get("metadata") or {}
    if not isinstance(md, dict):
        raise SkoolSchemaError("lesson.metadata is not a dict")
    title = md.get("title") or "(untitled lesson)"
    desc_raw = md.get("desc")
    video_link = md.get("videoLink") or None
    video_len_ms = md.get("videoLenMs")
    thumbnail = md.get("videoThumbnail")
    resources_raw = md.get("resources") or "[]"
    transcript_field = md.get("transcript")

    duration_sec: Optional[int] = None
    if isinstance(video_len_ms, (int, float)):
        duration_sec = int(video_len_ms // 1000)

    notes: list[str] = []
    quality_flag: Optional[str] = None
    chosen_kind: Optional[str] = None
    chosen_lang: Optional[str] = None
    char_count = 0
    speaker_turn_count = 0
    plain_written = False

    embed_source: Optional[str] = None
    embed_url: Optional[str] = video_link

    # Path 1: author-uploaded transcript wins outright.
    if (
        not description_only
        and isinstance(transcript_field, str)
        and transcript_field.strip()
    ):
        plain = transcript_field.strip() + "\n"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(plain, encoding="utf-8")
        plain_written = True
        char_count = len(plain)
        speaker_turn_count = count_speaker_turns(plain)
        chosen_kind = "skool_manual"
        chosen_lang = "unknown"
        embed_source = _classify_embed_host(video_link) if video_link else "none"
        notes.append("transcript: used metadata.transcript field")
    elif not description_only:
        # Path 2: delegate to the embedded video's adapter.
        embed_source = _classify_embed_host(video_link) if video_link else "none"
        if embed_source == "youtube":
            yt_stat = _delegate(
                "youtube",
                _youtube_fetcher,
                url=video_link,
                out_path=out_path,
                fallback_ladder=fallback_ladder,
                timeout_sec=timeout_sec,
            )
            if isinstance(yt_stat, TranscriptStat):
                plain_written = True
                char_count = yt_stat.char_count
                speaker_turn_count = yt_stat.speaker_turn_count
                chosen_kind = yt_stat.chosen_track_kind
                chosen_lang = yt_stat.chosen_track_lang
                quality_flag = yt_stat.quality_flag
                notes.append(f"delegated_to_youtube: {video_link}")
                if yt_stat.notes:
                    notes.append("yt_notes: " + " ; ".join(yt_stat.notes[-3:]))
            else:
                notes.append(f"youtube delegation failed: {yt_stat}")
                quality_flag = "youtube_embed_unsupported"
        elif embed_source == "vimeo":
            vm_stat = _delegate(
                "vimeo",
                _vimeo_fetcher,
                url=video_link,
                out_path=out_path,
                fallback_ladder=fallback_ladder,
                timeout_sec=timeout_sec,
            )
            if isinstance(vm_stat, TranscriptStat):
                plain_written = True
                char_count = vm_stat.char_count
                speaker_turn_count = vm_stat.speaker_turn_count
                chosen_kind = vm_stat.chosen_track_kind
                chosen_lang = vm_stat.chosen_track_lang
                quality_flag = vm_stat.quality_flag
                notes.append(f"delegated_to_vimeo: {video_link}")
                if vm_stat.notes:
                    notes.append("vimeo_notes: " + " ; ".join(vm_stat.notes[-3:]))
            else:
                notes.append(f"vimeo delegation failed: {vm_stat}")
                quality_flag = "vimeo_embed_unsupported"
        elif embed_source == "none":
            quality_flag = "no_transcript_field"
            notes.append("lesson has neither videoLink nor transcript field")
        else:
            quality_flag = "embed_source_unsupported"
            notes.append(
                f"embed host {embed_source!r} not handled — describe only"
            )

    stat = TranscriptStat(
        source="skool",
        url=url,
        video_id=ref.lesson_id,
        output_path=str(out_path),
        chosen_track_kind=chosen_kind,
        chosen_track_lang=chosen_lang,
        char_count=char_count,
        speaker_turn_count=speaker_turn_count,
        quality_flag=quality_flag,
        notes=notes,
        title=title,
        duration_sec=duration_sec,
        embed_source=embed_source,
        embed_url=embed_url,
    )

    if with_description:
        body, unsupported = _render_desc_body(desc_raw)
        if unsupported:
            stat.notes.append(
                "prosemirror unsupported nodes: " + ",".join(sorted(set(unsupported)))
            )
        resources = _parse_resources(resources_raw)
        frontmatter: dict = {
            "source": "skool",
            "url": url,
            "community": ref.community,
            "classroom_id": ref.classroom_id,
            "lesson_id": ref.lesson_id,
            "title": title,
            "embed_source": embed_source,
            "embed_url": embed_url,
            "duration_sec": duration_sec,
            "thumbnail": thumbnail,
        }
        if resources:
            frontmatter["resources"] = resources
        desc_path = write_description_md(
            out_path, frontmatter=frontmatter, title=title, body=body
        )
        stat.description_path = str(desc_path)
        stat.notes.append("description: wrote .description.md")

    if not plain_written and not description_only and not with_description:
        # User asked for transcript but we couldn't produce one and
        # didn't write a description either. Be explicit.
        raise TranscriptFetchError(
            f"Skool lesson {url} has no transcript and embed_source="
            f"{embed_source!r} is not delegatable. Re-run with "
            "--with-description to at least save the lesson description."
        )

    return stat


# --------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------- #


def _fetch_lesson_html(
    *, url: str, cookies_file: Optional[Path], timeout_sec: int
) -> str:
    # Public Skool communities (e.g. ``zero-one``) serve the lesson HTML
    # without authentication; private / paid communities respond with
    # 401/403 (raised as ``SourceAuthError`` so the CLI maps to exit 5)
    # or 429 (raised as ``SourceRateLimitError`` → exit 6). Off-host
    # redirects, DNS / TCP failures, and 5xx responses are surfaced as
    # ``TranscriptFetchError``.
    try:
        opener = build_authenticated_opener(
            cookies_file, allowed_hosts=SKOOL_HOSTS,
        )
    except CookieFileError as e:
        raise SourceAuthError(str(e)) from e
    try:
        with opener.open(url, timeout=timeout_sec) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            # Bounded read: a 16 MB cap is generous for any plausible
            # Skool lesson page and protects against a hostile origin
            # streaming arbitrary bytes at the parser.
            raw = resp.read(_MAX_HTML_BYTES + 1)
            if len(raw) > _MAX_HTML_BYTES:
                raise TranscriptFetchError(
                    f"Skool response exceeded {_MAX_HTML_BYTES // (1024 * 1024)} MB cap"
                )
            return raw.decode(charset, errors="replace")
    except HTTPError as e:
        if e.code in (401, 403):
            hint = (
                "pass --cookies-file <Netscape cookies.txt>"
                if cookies_file is None
                else "cookies expired or account lacks access"
            )
            raise SourceAuthError(
                f"Skool returned HTTP {e.code} — {hint}."
            ) from e
        if e.code == 429:
            raise SourceRateLimitError(
                f"Skool returned HTTP 429 — rate-limited. Retry later."
            ) from e
        raise TranscriptFetchError(
            f"Skool HTTP {e.code}: {e.reason}"
        ) from e
    except (URLError, HTTPException) as e:
        raise TranscriptFetchError(
            f"Skool network error: {e}"
        ) from e


# --------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------- #


def _extract_lesson(html: str, *, lesson_id: str) -> dict:
    """Pull the lesson dict (by id) out of the __NEXT_DATA__ JSON blob."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise SkoolSchemaError(
            "Skool page is missing __NEXT_DATA__ — was the cookies file "
            "valid? An unauthenticated request returns a redirect, not "
            "the lesson page."
        )
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SkoolSchemaError(f"__NEXT_DATA__ is not valid JSON: {e}") from e
    pp = data.get("props", {}).get("pageProps")
    if not isinstance(pp, dict):
        raise SkoolSchemaError("props.pageProps missing in __NEXT_DATA__")
    selected = pp.get("selectedModule")
    if not isinstance(selected, str) or not selected:
        raise SkoolSchemaError(
            "pageProps.selectedModule missing — this URL likely points "
            "to a community landing page, not a lesson"
        )
    if selected != lesson_id:
        # Skool stores the lesson id in both URL and page state. A
        # mismatch usually means we landed on a redirect.
        raise SkoolSchemaError(
            f"selectedModule={selected!r} does not match URL ?md={lesson_id!r} — "
            "Skool may have redirected; check cookies and lesson id."
        )
    course = pp.get("course")
    found = _find_node_by_id(course, selected)
    if found is None:
        raise SkoolSchemaError(
            f"lesson id {selected!r} not found in pageProps.course tree"
        )
    return found


_MAX_TREE_DEPTH = 64  # Skool course trees are 4-5 levels deep; cap defends
                      # against pathological / attacker-influenced payloads.


def _find_node_by_id(node: Any, target_id: str) -> Optional[dict]:
    """Iteratively locate the dict whose ``id`` equals ``target_id``.

    Restricts matches to nodes that look like Skool lessons (have a dict
    ``metadata`` field) so an id collision with a non-lesson object
    (post, comment, attached resource) does not hijack which dict the
    adapter treats as the lesson. Depth-capped to defend against
    deeply-nested hostile payloads.
    """
    stack: list[tuple[Any, int]] = [(node, 0)]
    while stack:
        cur, depth = stack.pop()
        if depth > _MAX_TREE_DEPTH:
            continue
        if isinstance(cur, dict):
            if cur.get("id") == target_id and isinstance(cur.get("metadata"), dict):
                return cur
            stack.extend((v, depth + 1) for v in cur.values())
        elif isinstance(cur, list):
            stack.extend((v, depth + 1) for v in cur)
    return None


_YOUTUBE_EMBED_HOSTS = frozenset(
    {
        "youtu.be",
        "www.youtu.be",
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)
_VIMEO_EMBED_HOSTS = frozenset(
    {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}
)
_EMBED_HOST_LEN_CAP = 253  # RFC 1035 hostname length limit


def _classify_embed_host(video_link: Optional[str]) -> str:
    """Map a videoLink URL to one of: youtube/vimeo/none/<host>.

    Uses an explicit allowlist (NOT ``str.endswith``) so typosquats like
    ``notyoutube.com`` cannot route to the YouTube fetcher.
    """
    if not video_link:
        return "none"
    host = (urlparse(video_link).hostname or "").lower()
    if host in _YOUTUBE_EMBED_HOSTS:
        return "youtube"
    if host in _VIMEO_EMBED_HOSTS:
        return "vimeo"
    if host:
        # Cap the host string we propagate so a hostile lesson cannot
        # bloat the stat sidecar via unbounded embed_source values.
        return host[:_EMBED_HOST_LEN_CAP]
    return "none"


def _parse_resources(raw: Any) -> list[dict]:
    """Skool stores ``metadata.resources`` as a JSON-encoded string."""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if not isinstance(raw, str):
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [r for r in parsed if isinstance(r, dict)]
    return []


def _render_desc_body(desc_raw: Any) -> tuple[str, list[str]]:
    if desc_raw is None:
        return "", []
    if not isinstance(desc_raw, str):
        return "", []
    try:
        return prosemirror_to_markdown(desc_raw)
    except ProseMirrorError:
        return desc_raw, ["raw"]


# --------------------------------------------------------------------- #
# Delegation
# --------------------------------------------------------------------- #


def _delegate(
    kind: str,
    injected: Optional[Any],
    *,
    url: str,
    out_path: Path,
    fallback_ladder: Iterable[tuple[str, str]],
    timeout_sec: int,
) -> Any:
    """Call the YouTube/Vimeo adapter, returning the TranscriptStat or
    the underlying Exception object so the caller can record it.

    The fetcher is loaded lazily so that tests patching
    ``sources.skool.fetch_youtube_transcript`` (etc.) on a module
    attribute don't need to bypass an early-bound reference.
    """
    if injected is not None:
        fetcher = injected
    elif kind == "youtube":
        from .youtube import fetch_youtube_transcript as fetcher  # type: ignore
    elif kind == "vimeo":
        from .vimeo import fetch_vimeo_transcript as fetcher  # type: ignore
    else:
        return RuntimeError(f"no delegate for kind={kind!r}")
    try:
        return fetcher(
            url,
            out_path,
            fallback_ladder=fallback_ladder,
            timeout_sec=timeout_sec,
        )
    except Exception as e:  # noqa: BLE001 — surface to caller as note text
        return e


__all__ = (
    "SKOOL_HOSTS",
    "SkoolLessonRef",
    "SkoolSchemaError",
    "SkoolUrlError",
    "fetch_skool_transcript",
    "parse_skool_lesson_url",
)
