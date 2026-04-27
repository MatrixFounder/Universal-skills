#!/usr/bin/env python3
"""transcript-fetcher CLI.

Pull a clean plain-text transcript from a video/podcast URL and emit a
small JSON stat record alongside.

Currently supported sources:
    - YouTube (via yt-dlp)

Single-URL example::

    python3 scripts/fetch.py https://youtu.be/NSVTpCfBMK8 \\
        --out /tmp/talk.txt

Batch example (one URL per line)::

    python3 scripts/fetch.py --batch urls.txt --out-dir /tmp/transcripts/

The CLI emits one JSON line per URL on stdout with the stat record
(source, picked subtitle language/track, char count, speaker-turn
count, quality flag). On failure, exits non-zero. With
``--json-errors``, failure messages are emitted as a single JSON line
on stderr to keep the contract machine-readable.
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

from sources.youtube import (  # noqa: E402  (after sys.path tweak)
    DEFAULT_FALLBACK_RU,
    DEFAULT_TIMEOUT_SEC,
    TranscriptFetchError,
    extract_video_id,
    fetch_youtube_transcript,
    write_stat_sidecar,
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


_YOUTUBE_HOSTS = frozenset(
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


def _detect_source(url: str) -> str:
    """Classify a URL by its hostname. Hostname allowlist (not substring).

    Substring matching on the URL string is unsafe (a path segment or
    query value containing ``youtube.com`` would match). We parse the
    URL and check the hostname against an explicit allowlist instead.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in _YOUTUBE_HOSTS:
        return "youtube"
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
) -> dict:
    source = _detect_source(url)
    if source != "youtube":
        raise ValueError(f"Source {source!r} not yet implemented")

    ladder = _build_ladder(prefer=prefer, lang=lang)
    stat = fetch_youtube_transcript(
        url,
        out_path,
        fallback_ladder=ladder,
        timeout_sec=timeout_sec,
    )
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
            "(YouTube only at the moment)."
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
            )
        except TranscriptFetchError as e:
            return _emit_error(
                str(e),
                code=3,
                error_type="TranscriptFetchError",
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
