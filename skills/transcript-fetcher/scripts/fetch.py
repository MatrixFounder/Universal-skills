#!/usr/bin/env python3
"""transcript-fetcher CLI.

Pull a clean plain-text transcript from a video/podcast URL and emit a
small JSON stat record alongside.

Currently supported sources:
    - YouTube (via yt-dlp)
    - Vimeo   (via yt-dlp)
    - Skool   (via authenticated HTML scrape + delegated YouTube/Vimeo)

Single-URL example::

    python3 scripts/fetch.py https://youtu.be/NSVTpCfBMK8 \\
        --out /tmp/talk.txt

With description sidecar::

    python3 scripts/fetch.py https://youtu.be/NSVTpCfBMK8 \\
        --out /tmp/talk.txt --with-description

Skool lesson (cookies OPTIONAL — only needed for private/paid
communities; public ones work without)::

    # Public community — no cookies needed.
    python3 scripts/fetch.py \\
        "https://www.skool.com/zero-one/classroom/AAA?md=BBB" \\
        --out /tmp/lesson.txt --with-description

    # Private / paid community — pass cookies.txt.
    python3 scripts/fetch.py \\
        "https://www.skool.com/private-foo/classroom/AAA?md=BBB" \\
        --out /tmp/lesson.txt --with-description \\
        --cookies-file ~/.config/skool-cookies.txt

Batch example (one URL per line)::

    python3 scripts/fetch.py --batch urls.txt --out-dir /tmp/transcripts/

The CLI emits one JSON line per URL on stdout with the stat record
(source, picked subtitle language/track, char count, speaker-turn
count, quality flag, optionally description metadata). On failure,
exits non-zero. With ``--json-errors``, failure messages are emitted
as a single JSON line on stderr to keep the contract machine-readable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Allow ``python3 scripts/fetch.py`` and ``python -m scripts.fetch`` both.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sources._stat import (  # noqa: E402
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
    write_stat_sidecar,
)
from sources.skool import (  # noqa: E402
    SkoolSchemaError,
    SkoolUrlError,
    fetch_skool_transcript,
)
from sources.vimeo import (  # noqa: E402
    DEFAULT_FALLBACK_VIMEO,
    fetch_vimeo_transcript,
)
from sources.youtube import (  # noqa: E402  (after sys.path tweak)
    DEFAULT_FALLBACK_RU,
    DEFAULT_TIMEOUT_SEC,
    extract_video_id,
    fetch_youtube_transcript,
)


# --------------------------------------------------------------------- #
# Error envelope (lightweight version of the office-skills pattern)
# --------------------------------------------------------------------- #

_JSON_ERRORS_SCHEMA = 1


def _emit_error(
    message: str,
    *,
    code: int = 1,
    error_type: str = "TranscriptFetcherError",
    details: Optional[dict] = None,
    json_mode: bool = False,
) -> int:
    if json_mode:
        envelope = {
            "v": _JSON_ERRORS_SCHEMA,
            "error": message,
            "code": code if code != 0 else 1,
            "type": error_type,
        }
        if details:
            envelope["details"] = details
        sys.stderr.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()
    return code if code != 0 else 1


# --------------------------------------------------------------------- #
# Source dispatch
# --------------------------------------------------------------------- #


_SOURCE_BY_HOST: dict[str, str] = {}
for _h in (
    "youtu.be",
    "www.youtu.be",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
):
    _SOURCE_BY_HOST[_h] = "youtube"
for _h in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
    _SOURCE_BY_HOST[_h] = "vimeo"
for _h in ("skool.com", "www.skool.com", "app.skool.com"):
    _SOURCE_BY_HOST[_h] = "skool"

# Retained for backwards-compat with existing tests that imported the set.
_YOUTUBE_HOSTS = frozenset(
    h for h, s in _SOURCE_BY_HOST.items() if s == "youtube"
)


def _detect_source(url: str) -> str:
    """Classify a URL by its hostname. Hostname allowlist (not substring).

    Substring matching on the URL string is unsafe (a path segment or
    query value containing ``youtube.com`` would match). We parse the
    URL and check the hostname against an explicit allowlist instead.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    source = _SOURCE_BY_HOST.get(host)
    if source is not None:
        return source
    raise ValueError(f"Unsupported source for URL: {url}")


def _build_ladder(prefer: str, lang: str) -> tuple[tuple[str, str], ...]:
    """Build a fallback ladder.

    ``prefer`` is one of:
        - ``"manual"`` (default for ru): manual lang -> auto lang-orig -> auto lang -> auto en
        - ``"auto"``: auto lang-orig -> auto lang -> manual lang -> auto en

    For non-ru languages the ``lang-orig`` step is skipped (it is a
    YouTube-specific marker for an auto-caption that is the original
    language of the speaker, mainly meaningful for non-English speech).
    """
    if lang == "ru":
        if prefer == "auto":
            return (
                ("auto", "ru-orig"),
                ("auto", "ru"),
                ("manual", "ru"),
                ("auto", "en"),
            )
        return DEFAULT_FALLBACK_RU
    # Generic lang: try manual, then auto, then English auto fallback.
    if prefer == "auto":
        return (
            ("auto", lang),
            ("manual", lang),
            ("auto", "en"),
        )
    return (
        ("manual", lang),
        ("auto", lang),
        ("auto", "en"),
    )


def _fetch_one(
    url: str,
    out_path: Path,
    *,
    lang: str,
    prefer: str,
    timeout_sec: int,
    with_description: bool = False,
    description_only: bool = False,
    cookies_file: Optional[Path] = None,
) -> dict:
    source = _detect_source(url)
    ladder = _build_ladder(prefer=prefer, lang=lang)

    if source == "youtube":
        stat = fetch_youtube_transcript(
            url,
            out_path,
            fallback_ladder=ladder,
            timeout_sec=timeout_sec,
            cookies_file=cookies_file,
            with_description=with_description,
            description_only=description_only,
        )
    elif source == "vimeo":
        # Vimeo has no ``<lang>-orig`` quirk; strip those from the ladder.
        # Always retain the user's --lang/--prefer choice; only synthesize
        # the English tail if it was missing (Vimeo auto-en is the
        # last-ditch fallback when explicit lang has no track).
        vimeo_ladder = tuple((k, l) for k, l in ladder if not l.endswith("-orig"))
        if ("auto", "en") not in vimeo_ladder:
            vimeo_ladder = vimeo_ladder + (("auto", "en"),)
        if not vimeo_ladder:
            vimeo_ladder = DEFAULT_FALLBACK_VIMEO
        stat = fetch_vimeo_transcript(
            url,
            out_path,
            fallback_ladder=vimeo_ladder,
            timeout_sec=timeout_sec,
            cookies_file=cookies_file,
            with_description=with_description,
            description_only=description_only,
        )
    elif source == "skool":
        stat = fetch_skool_transcript(
            url,
            out_path,
            cookies_file=cookies_file,
            fallback_ladder=ladder,
            timeout_sec=timeout_sec,
            with_description=with_description,
            description_only=description_only,
        )
    else:  # pragma: no cover — _detect_source guards this
        raise ValueError(f"Source {source!r} not yet implemented")

    write_stat_sidecar(stat, out_path)
    return stat.to_dict()


# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetch.py",
        description=(
            "Fetch a clean plain-text transcript from a video URL "
            "(YouTube, Vimeo, or Skool lesson)."
        ),
    )
    p.add_argument(
        "url",
        nargs="?",
        help="A single video URL. Mutually exclusive with --batch.",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output path for the cleaned plain-text transcript "
        "(single-URL mode).",
    )
    p.add_argument(
        "--batch",
        type=Path,
        help="Path to a text file with one URL per line "
        "(blank lines and lines starting with # are ignored).",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        help="Output directory for batch mode. Each transcript is "
        "written as <video_id>.txt with a sibling .stat.json.",
    )
    p.add_argument(
        "--lang",
        default="ru",
        help="Preferred caption language (default: ru).",
    )
    p.add_argument(
        "--prefer",
        choices=("manual", "auto"),
        default="manual",
        help="Caption track preference. 'manual' tries human-uploaded "
        "subs first; 'auto' tries auto-generated first. Default: manual.",
    )
    p.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Per-attempt timeout for each yt-dlp call. "
        f"Default: {DEFAULT_TIMEOUT_SEC}s. Increase for very long "
        "videos or flaky networks.",
    )
    p.add_argument(
        "--on-collision",
        choices=("error", "skip", "suffix"),
        default="error",
        help="Batch mode behaviour when two URLs would write the same "
        "output file. 'error' fails the run; 'skip' leaves the first "
        "write intact; 'suffix' appends -2, -3, … to later writes. "
        "Default: error.",
    )
    p.add_argument(
        "--with-description",
        action="store_true",
        help="Also fetch the video description / lesson body and write a "
        "<out>.description.md sidecar. Populates title/uploader/upload_date/"
        "duration_sec in the stat. Off by default for backward compat.",
    )
    p.add_argument(
        "--description-only",
        action="store_true",
        help="Skip the transcript download entirely; produce only the "
        "<out>.description.md sidecar. Requires --with-description.",
    )
    p.add_argument(
        "--cookies-file",
        type=Path,
        help="Path to a Netscape cookies.txt with an authenticated "
        "session. ALWAYS OPTIONAL. For Skool, public communities "
        "work without cookies; only private/paid ones need them "
        "(SourceAuthError with exit code 5 if the server returns "
        "HTTP 401/403). For YouTube/Vimeo, forwarded to yt-dlp's "
        "--cookies for age-gated or unlisted videos.",
    )
    p.add_argument(
        "--json-errors",
        action="store_true",
        help="On failure, emit a single JSON line on stderr "
        "({error, code, type, details?}). Stdout stat lines are "
        "always JSON regardless of this flag.",
    )
    return p


def _read_batch(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    json_errors = bool(args.json_errors)

    # Validate mutually-exclusive modes.
    if args.batch and args.url:
        return _emit_error(
            "Pass either a single URL or --batch, not both.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )
    if not args.batch and not args.url:
        return _emit_error(
            "Missing URL. Pass a single URL or use --batch <file>.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.timeout_sec <= 0:
        return _emit_error(
            f"--timeout-sec must be positive, got {args.timeout_sec}.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.description_only and not args.with_description:
        return _emit_error(
            "--description-only requires --with-description.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.cookies_file is not None and not args.cookies_file.exists():
        return _emit_error(
            f"--cookies-file not found: {args.cookies_file}",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    # Single-URL mode
    if args.url:
        if not args.out:
            return _emit_error(
                "--out is required in single-URL mode.",
                code=2,
                error_type="UsageError",
                json_mode=json_errors,
            )
        try:
            stat = _fetch_one(
                args.url,
                args.out,
                lang=args.lang,
                prefer=args.prefer,
                timeout_sec=args.timeout_sec,
                with_description=args.with_description,
                description_only=args.description_only,
                cookies_file=args.cookies_file,
            )
        except TranscriptFetchError as e:
            return _emit_error(
                str(e),
                code=3,
                error_type="TranscriptFetchError",
                details={"url": args.url},
                json_mode=json_errors,
            )
        except SourceAuthError as e:
            return _emit_error(
                str(e),
                code=5,
                error_type="SourceAuthError",
                details={"url": args.url},
                json_mode=json_errors,
            )
        except SourceRateLimitError as e:
            return _emit_error(
                str(e),
                code=6,
                error_type="SourceRateLimitError",
                details={"url": args.url},
                json_mode=json_errors,
            )
        except (SkoolUrlError, SkoolSchemaError) as e:
            return _emit_error(
                str(e),
                code=2,
                error_type=type(e).__name__,
                details={"url": args.url},
                json_mode=json_errors,
            )
        except ValueError as e:
            return _emit_error(
                str(e),
                code=2,
                error_type="UsageError",
                details={"url": args.url},
                json_mode=json_errors,
            )
        except Exception as e:  # noqa: BLE001
            return _emit_error(
                f"Unexpected error: {e}",
                code=1,
                error_type=type(e).__name__,
                details={"url": args.url},
                json_mode=json_errors,
            )
        sys.stdout.write(json.dumps(stat, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0

    # Batch mode
    if not args.out_dir:
        return _emit_error(
            "--out-dir is required in --batch mode.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    urls = _read_batch(args.batch)
    if not urls:
        return _emit_error(
            f"Batch file {args.batch} contained no URLs.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    failures = 0
    seen_paths: set[Path] = set()
    for url in urls:
        try:
            out_path = _resolve_batch_path(
                url, args.out_dir, seen_paths, args.on_collision
            )
            if out_path is None:
                # Collision skipped per policy — not a failure, but logged.
                err_record = {
                    "v": _JSON_ERRORS_SCHEMA,
                    "error": "Output path collision (skipped per --on-collision=skip)",
                    "type": "BatchCollision",
                    "url": url,
                }
                sys.stdout.write(json.dumps(err_record, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue
            stat = _fetch_one(
                url,
                out_path,
                lang=args.lang,
                prefer=args.prefer,
                timeout_sec=args.timeout_sec,
                with_description=args.with_description,
                description_only=args.description_only,
                cookies_file=args.cookies_file,
            )
            sys.stdout.write(json.dumps(stat, ensure_ascii=False) + "\n")
        except _BatchCollisionError as e:
            failures += 1
            err_record = {
                "v": _JSON_ERRORS_SCHEMA,
                "error": str(e),
                "type": "BatchCollision",
                "url": url,
            }
            sys.stdout.write(json.dumps(err_record, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            failures += 1
            err_record = {
                "v": _JSON_ERRORS_SCHEMA,
                "error": str(e),
                "type": type(e).__name__,
                "url": url,
            }
            sys.stdout.write(json.dumps(err_record, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    if failures:
        return _emit_error(
            f"{failures}/{len(urls)} URLs failed.",
            code=4,
            error_type="BatchPartialFailure",
            details={"failed": failures, "total": len(urls)},
            json_mode=json_errors,
        )
    return 0


# --------------------------------------------------------------------- #
# Batch helpers
# --------------------------------------------------------------------- #


class _BatchCollisionError(RuntimeError):
    """Raised when --on-collision=error and two URLs would clobber."""


def _resolve_batch_path(
    url: str,
    out_dir: Path,
    seen: set[Path],
    on_collision: str,
) -> Optional[Path]:
    """Decide the output path for one URL in batch mode.

    Returns ``None`` when the collision policy says to skip this URL.
    Raises :class:`_BatchCollisionError` when the policy says to error.
    Adds the chosen path to ``seen`` so subsequent URLs see the conflict.
    """
    vid = extract_video_id(url) or _slugify(url)
    out_path = out_dir / f"{vid}.txt"
    if out_path in seen:
        if on_collision == "error":
            raise _BatchCollisionError(
                f"Output path collision: {out_path} already targeted by an earlier URL "
                f"(use --on-collision=skip or --on-collision=suffix to override)"
            )
        if on_collision == "skip":
            return None
        if on_collision == "suffix":
            n = 2
            while True:
                candidate = out_dir / f"{vid}-{n}.txt"
                if candidate not in seen:
                    out_path = candidate
                    break
                n += 1
    seen.add(out_path)
    return out_path


def _slugify(text: str) -> str:
    """Cheap slug for naming files when no video id can be extracted."""
    out = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:64] or "transcript"


if __name__ == "__main__":
    sys.exit(main())
