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

import _config as cfg  # noqa: E402
from asr import DEFAULT_ASR_TIMEOUT_SEC  # noqa: E402
from sources import _auth  # noqa: E402
from sources._log import debug_enabled  # noqa: E402
from sources._stat import (  # noqa: E402
    MissingDependencyError,
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
    extract_vimeo_id,
    fetch_vimeo_transcript,
)
from sources.x import (  # noqa: E402
    DEFAULT_FALLBACK_X,
    extract_x_id,
    fetch_x_transcript,
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
        # Make the remedy operator-visible even without --json-errors (F15) —
        # `details["remediation"]` already exists for TranscriptFetchError's
        # transient-timeout hint AND MissingDependencyError's install hint;
        # this is the only place either reaches non-JSON stderr.
        remediation = (details or {}).get("remediation")
        if remediation:
            sys.stderr.write(f"remediation: {remediation}\n")
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
for _h in (
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
):
    _SOURCE_BY_HOST[_h] = "x"

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
    concurrent_fragments: Optional[int] = None,
    media_timeout_sec: Optional[int] = None,
    with_description: bool = False,
    description_only: bool = False,
    cookies_file: Optional[Path] = None,
    auth_map: Optional[dict] = None,
    cookies_from_browser: Optional[str] = None,
    asr_allow_cloud: bool = False,
    asr_model: Optional[str] = None,
    asr_timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
    max_duration_min: Optional[float] = None,
    remove_silence: bool = True,
    debug: bool = False,
) -> dict:
    source = _detect_source(url)
    ladder = _build_ladder(prefer=prefer, lang=lang)
    # Resolve the effective cookies file: explicit --cookies-file wins; else the
    # ~/.transcript-fetcher auth-map (pre-loaded once by the caller) / convention
    # for this URL's host (source-agnostic — the resolved Netscape file feeds
    # yt-dlp --cookies / Skool's opener).
    cookies_file = _auth.resolve_cookies_file(
        url, explicit_cookies_file=cookies_file, auth_map=auth_map
    )

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
    elif source == "x":
        # X media: the adapter chooses captions-first vs ASR internally. The
        # caption ladder is X-shaped (manual/auto en first); `lang` is the ASR
        # language hint. No special-casing of X leaks beyond this branch.
        x_ladder = tuple(
            (k, l) for k, l in ladder if not l.endswith("-orig")
        ) or DEFAULT_FALLBACK_X
        stat = fetch_x_transcript(
            url,
            out_path,
            fallback_ladder=x_ladder,
            lang=lang,
            timeout_sec=timeout_sec,
            concurrent_fragments=concurrent_fragments,
            media_timeout_sec=media_timeout_sec,
            cookies_file=cookies_file,
            cookies_from_browser=cookies_from_browser,
            with_description=with_description,
            description_only=description_only,
            asr_allow_cloud=asr_allow_cloud,
            asr_model=asr_model,
            asr_timeout_sec=asr_timeout_sec,
            max_duration_min=max_duration_min,
            remove_silence=remove_silence,
            debug=debug,
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
        epilog=(
            "Readiness check: fetch.py doctor [--json] — reports interpreter, "
            "yt-dlp, ffmpeg, ASR backends + remediation."
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
        "--concurrent-fragments",
        type=int,
        default=None,
        help="(X) Parallel HLS fragment downloads for the media (audio) "
        "download. Default: 8, or TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS. "
        "1 = serial (pre-029 behaviour). Ignored by YouTube/Vimeo/Skool.",
    )
    p.add_argument(
        "--media-timeout-sec",
        type=int,
        default=None,
        help="(X) Per-attempt timeout budget for the X media (audio) download "
        "ONLY — the metadata probe keeps --timeout-sec. Default: "
        "duration-derived max(600, duration*4)s capped at 21600s (6h), "
        "else 1800s; or TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC.",
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
    p.add_argument(
        "--debug",
        action="store_true",
        help="Emit stage-by-stage progress to stderr (also via "
        "TRANSCRIPT_FETCHER_DEBUG=1). Stdout stays pure JSON. Off by default.",
    )
    p.add_argument(
        "--asr-allow-cloud",
        action="store_true",
        help="Permit the OPT-IN cloud ASR backend (OpenAI Whisper API or any "
        "OpenAI-compatible server). Requires an API key (OPENAI_API_KEY or "
        ".env). The audio is uploaded to that service — off by default for "
        "privacy. Local backends (MacWhisper/whisper/whisper.cpp) are always "
        "tried first.",
    )
    p.add_argument(
        "--asr-model",
        default=None,
        help="Model id forwarded to the chosen ASR backend (e.g. MacWhisper "
        "'engine:model-id', whisper model name, whisper.cpp ggml path, or a "
        "cloud model). Overrides any .env default.",
    )
    p.add_argument(
        "--asr-timeout-sec",
        type=int,
        default=None,
        help="Per-backend ASR transcription timeout in seconds. Default "
        f"{DEFAULT_ASR_TIMEOUT_SEC} (or TRANSCRIPT_FETCHER_ASR_TIMEOUT_SEC).",
    )
    p.add_argument(
        "--max-duration-min",
        type=float,
        default=None,
        help="(X ASR) Transcribe only the first N minutes — clips the download "
        "(yt-dlp --download-sections, needs ffmpeg) so a long Broadcast/Space "
        "bounds both bytes and ASR time. Default: whole media.",
    )
    p.add_argument(
        "--keep-silence",
        action="store_true",
        help="(X ASR) Do NOT strip long silences before transcription. By "
        "default the X ASR path removes dead air (ffmpeg silenceremove) to cut "
        "Whisper hallucinated filler on silent lead-in/out; pass this to keep "
        "the audio untouched. Also configurable via "
        "TRANSCRIPT_FETCHER_SILENCE_REMOVAL/_THRESHOLD/_MIN_GAP_SEC/_KEEP_SEC.",
    )
    p.add_argument(
        "--auth-map",
        type=str,
        default=None,
        help="Path to a JSON host->{cookies_file} auth-map. Default: "
        "TRANSCRIPT_FETCHER_AUTH_MAP or ~/.transcript-fetcher/auth-map.json. "
        "Per-host cookies for any source; the convention "
        "~/.transcript-fetcher/<host>-cookies.txt also works without a map. "
        "Files must be 0600 (not a symlink).",
    )
    p.add_argument(
        "--cookies-from-browser",
        type=str,
        default=None,
        metavar="BROWSER",
        help="(X) Load cookies directly from a local browser via yt-dlp "
        "(e.g. chrome, safari, firefox[:PROFILE]). Reads the browser's cookie "
        "store — opt-in. Alternative to --cookies-file for protected/age-gated media.",
    )
    return p


# --------------------------------------------------------------------- #
# `doctor` subcommand (UC-2, arch-016 §10.3)
# --------------------------------------------------------------------- #


def _run_doctor(argv: list[str]) -> int:
    """``fetch.py doctor [--json]`` — cheap, import-free readiness check.

    Reuses :func:`install_components._components` as the SINGLE source of
    truth for component detection (no probe-logic fork). ``install_components``
    is imported locally (not at module scope) so a plain ``fetch.py <url>``
    run never pays for it; the module itself imports only stdlib + ``_config``,
    so this stays free of ``yt_dlp``/``whisper``/``weasyprint`` imports either way.

    ``.env`` is already loaded by ``main()`` (``cfg.load_skill_env()`` runs
    before the positional dispatch) — doctor deliberately reports what a REAL
    fetch run would see (``TRANSCRIPT_FETCHER_*_BIN`` overrides, ASR_ALLOW_CLOUD,
    OPENAI_API_KEY, …), not the bare process environment. A doctor that ignored
    ``.env`` could report "not ready" while a real run succeeds, or vice-versa.

    Never touches the network and never imports ``yt_dlp`` — only distribution
    metadata (:func:`install_components.yt_dlp_version`) and ``shutil.which``
    probes for everything else.

    Remediation contract (F1/F2/F5/F11 from cycle 1; REFINED in cycle 3 —
    "flow-blocking gaps vs informational hints"): ``remediation`` names ONLY
    the gaps that can actually block a flow:

      (a) yt-dlp missing        — its install hint (the skill cannot run);
      (b) ffmpeg missing        — the bespoke conditional-required line (it
          back-stops X Broadcast/Space (HLS) ASR AND whisper/whisper.cpp at
          runtime despite being an optional component itself);
      (c) NO ASR capability AT ALL — no local backend present AND NOT
          (cloud ``key_present`` AND ``allow_cloud``) — one line naming the
          options and the consequence ("caption-less X media (Broadcasts/
          Spaces) will exit 7").

    An individual missing local ASR engine while ASR capability EXISTS
    elsewhere (another local engine present, or cloud fully configured) is
    NOT flow-blocking and never lands in ``remediation`` — cycle-2 found the
    prior "every missing component" contract made ``remediation == []`` /
    ``✓ Ready.`` unattainable on any real box short of all three local ASR
    engines installed simultaneously (impossible on Linux, where MacWhisper
    doesn't exist). Those non-blocking gaps are still surfaced in the HUMAN
    report only, as an indented ``→`` install-hint line under each missing
    component's row (see :func:`_print_doctor_report`) — informational, not a
    remediation demand. A cloud-configured, no-local-ASR box additionally
    gets one informational note line in the human report (not JSON
    ``remediation``, since the ASR chain genuinely resolves via cloud).
    JSON envelope KEYS are unchanged (``{v, interpreter, in_venv, ready,
    components, remediation}``). Exit code stays 0 iff yt-dlp is present
    (R5d, UNCHANGED) — a non-empty ``remediation`` with ``ready: true`` means
    "usable, but a real flow-blocking gap remains", not failure.
    """
    p = argparse.ArgumentParser(
        prog="fetch.py doctor",
        description="Report transcript-fetcher readiness (import-free; no network).",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable status.")
    args = p.parse_args(argv)

    import install_components as ic  # local: keeps a plain fetch run import-free

    raw_components = ic._components()
    components: dict = {}
    for c in raw_components:
        entry = {"present": c["present"], "required": c["required"]}
        if c["key"] == "yt-dlp":
            entry["version"] = ic.yt_dlp_version()
        components[c["key"]] = entry
    # Synthetic cloud row — boolean signals ONLY, never the key value.
    components["cloud"] = {
        "key_present": bool(cfg.openai_api_key()),
        "allow_cloud": cfg.asr_allow_cloud_default(),
    }

    ready = components["yt-dlp"]["present"]
    cloud = components["cloud"]
    local_asr_present = any(components[key]["present"] for key in ic._ASR_KEYS)
    cloud_ready = bool(cloud["key_present"] and cloud["allow_cloud"])

    # Remediation contract (cycle-3 refinement — see docstring above):
    # ONLY the three flow-blocking gap kinds land in `remediation`. An
    # individual missing local ASR engine, while ASR capability exists
    # elsewhere, is surfaced solely in the human report (`->` line under its
    # own row) — never here.
    remediation: list[str] = []
    for c in raw_components:
        if c["present"]:
            continue
        if c["key"] == "yt-dlp":
            remediation.append(f"{c['key']} — {c['install_hint']}")
        elif c["key"] == "ffmpeg":
            remediation.append(
                "ffmpeg — needed for X Broadcast/Space (HLS) ASR and by "
                f"whisper/whisper.cpp at runtime: {c['install_hint']}"
            )
        # else: an individual missing ASR engine is informational-only —
        # gated below on whether ASR capability exists at all.
    if not local_asr_present and not cloud_ready:
        remediation.append(
            "No local ASR backend detected — install MacWhisper/whisper/"
            "whisper.cpp (see `install_components.py`), or pass "
            "--asr-allow-cloud with an OPENAI_API_KEY. Caption-less X "
            "media (Broadcasts/Spaces) will exit 7."
        )

    envelope = {
        "v": 1,
        "interpreter": sys.executable,
        "in_venv": sys.prefix != sys.base_prefix,
        "ready": ready,
        "components": components,
        "remediation": remediation,
    }

    if args.json:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        _print_doctor_report(envelope, raw_components, local_asr_present, cloud_ready)

    return 0 if ready else 7


def _print_doctor_report(
    envelope: dict,
    raw_components: list[dict],
    local_asr_present: bool,
    cloud_ready: bool,
) -> None:
    """Human-mode doctor report.

    Every missing component — flow-blocking or not — gets an indented ``→``
    install-hint line directly under its ``[✗]`` row (mirrors
    ``install_components._print_report``); this is always informational, and
    is printed regardless of whether that component's hint also made it into
    the ``Remediation:`` block below. A cloud-configured box with no local
    ASR backend additionally gets one informational note (the ASR chain
    resolves via cloud, so this is deliberately NOT in ``remediation``).
    Final summary line depends on the remediation contract (cycle-3
    refinement — see ``_run_doctor`` docstring):

      * ``remediation`` empty              → ``"✓ Ready."`` (no flow-blocking
        gap — attainable with just one local ASR engine + ffmpeg + yt-dlp, or
        a fully-configured cloud backend; missing ALTERNATIVE engines above
        are informational only).
      * ``remediation`` non-empty, ready   → ``"✓ Core ready ..."`` (yt-dlp is
        present so the CLI itself works, but a flow-blocking gap listed above
        — ffmpeg, or no ASR capability at all — may bite a specific flow).
      * ``remediation`` non-empty, NOT ready → no extra summary line; the
        ``Remediation:`` block above (which always includes the yt-dlp hint
        in this case) IS the failure output.
    """
    print("transcript-fetcher — doctor\n")
    print(f"  interpreter : {envelope['interpreter']}")
    print(f"  in venv     : {'yes' if envelope['in_venv'] else 'no'}")
    print()
    for c in raw_components:
        entry = envelope["components"][c["key"]]
        mark = "✓" if entry["present"] else "✗"
        req = " (required)" if c["required"] else ""
        version = f" [{entry['version']}]" if entry.get("version") else ""
        print(f"  [{mark}] {c['label']}{req}{version}")
        if not entry["present"]:
            print(f"        → {c['install_hint']}")
    cloud = envelope["components"]["cloud"]
    cloud_mark = "✓" if cloud["key_present"] else "✗"
    print(
        f"  [{cloud_mark}] cloud ASR key present "
        f"(allow_cloud={cloud['allow_cloud']})"
    )
    print()
    remediation = envelope["remediation"]
    if remediation:
        print("  Remediation:")
        for hint in remediation:
            print(f"    → {hint}")
    if not local_asr_present and cloud_ready:
        if remediation:
            print()
        print(
            "  Note: no local ASR backend, but cloud ASR is configured "
            "(--asr-allow-cloud + key) — caption-less media will use the "
            "cloud backend."
        )
    if not remediation:
        print("  ✓ Ready.")
    elif envelope["ready"]:
        print()
        print(
            "  ✓ Core ready (yt-dlp present) — gaps above may block "
            "specific flows."
        )


def _read_batch(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main(argv: Optional[list[str]] = None) -> int:
    # Skill-local `.env` (secrets-safe) BEFORE any config read. Encapsulation:
    # the skill's settings/secrets travel with it; opt out via
    # TRANSCRIPT_FETCHER_NO_DOTENV=1. Process env always wins.
    cfg.load_skill_env()

    # Positional `doctor` dispatch BEFORE the normal argparse contract —
    # `doctor` is never a valid URL, so there is no collision. Placed AFTER
    # `cfg.load_skill_env()` so `.env` tool-bin overrides are honoured, but
    # BEFORE `parser.parse_args` (own mini-parser, see `_run_doctor`).
    effective_argv = sys.argv[1:] if argv is None else argv
    if effective_argv and effective_argv[0] == "doctor":
        return _run_doctor(effective_argv[1:])

    parser = _build_parser()
    args = parser.parse_args(argv)

    json_errors = bool(args.json_errors)
    debug = debug_enabled(args.debug)
    asr_allow_cloud = bool(args.asr_allow_cloud) or cfg.asr_allow_cloud_default()
    asr_model = args.asr_model or cfg.asr_model_default()
    # Silence removal (X ASR) is ON by default; --keep-silence or the config
    # default switches it off.
    remove_silence = (not args.keep_silence) and cfg.silence_removal_default()
    asr_timeout_sec = (
        args.asr_timeout_sec
        if args.asr_timeout_sec
        else cfg.asr_timeout_sec(DEFAULT_ASR_TIMEOUT_SEC)
    )
    # X media budget (arch-016 §10, task 029.02): CLI flag wins, else the
    # TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS / _MEDIA_TIMEOUT_SEC env knobs.
    # Resolved ONCE here — NOT forwarded as a bare `None` from the CLI layer,
    # because `download_audio`/`media_timeout_for` treat `None` as "use the
    # library default", which would silently discard the env override
    # (R2/R3a: an env-only run must still reach `download_audio`'s argv).
    concurrent_fragments = (
        args.concurrent_fragments
        if args.concurrent_fragments is not None
        else cfg.concurrent_fragments()
    )
    media_timeout_sec = (
        args.media_timeout_sec
        if args.media_timeout_sec is not None
        else cfg.media_timeout_sec()
    )

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

    if args.asr_timeout_sec is not None and args.asr_timeout_sec <= 0:
        return _emit_error(
            f"--asr-timeout-sec must be positive, got {args.asr_timeout_sec}.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.concurrent_fragments is not None and args.concurrent_fragments <= 0:
        return _emit_error(
            f"--concurrent-fragments must be positive, got {args.concurrent_fragments}.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.media_timeout_sec is not None and args.media_timeout_sec <= 0:
        return _emit_error(
            f"--media-timeout-sec must be positive, got {args.media_timeout_sec}.",
            code=2,
            error_type="UsageError",
            json_mode=json_errors,
        )

    if args.max_duration_min is not None and args.max_duration_min <= 0:
        return _emit_error(
            f"--max-duration-min must be positive, got {args.max_duration_min}.",
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

    # Load the ~/.transcript-fetcher auth-map ONCE (not per URL) so a malformed /
    # insecure map fails fast with exit 2 — in BOTH single-URL and batch modes —
    # instead of being re-parsed and mis-mapped per URL.
    try:
        resolved_auth_map = _auth.load_configured_auth_map(args.auth_map)
    except _auth.AuthMapError as e:
        return _emit_error(
            str(e), code=2, error_type="UsageError", json_mode=json_errors
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
                concurrent_fragments=concurrent_fragments,
                media_timeout_sec=media_timeout_sec,
                with_description=args.with_description,
                description_only=args.description_only,
                cookies_file=args.cookies_file,
                auth_map=resolved_auth_map,
                cookies_from_browser=args.cookies_from_browser,
                asr_allow_cloud=asr_allow_cloud,
                asr_model=asr_model,
                asr_timeout_sec=asr_timeout_sec,
                max_duration_min=args.max_duration_min,
                remove_silence=remove_silence,
                debug=debug,
            )
        except MissingDependencyError as e:
            # exit 7 — a required external tool is absent (yt-dlp/ffmpeg/no ASR
            # backend). NOT a subclass of TranscriptFetchError, so this clause
            # must precede the generic handler (else swallowed as exit 1).
            detail = {"url": args.url}
            if getattr(e, "remediation", None):
                detail["remediation"] = e.remediation
            return _emit_error(
                str(e),
                code=7,
                error_type="MissingDependencyError",
                details=detail,
                json_mode=json_errors,
            )
        except TranscriptFetchError as e:
            detail = {"url": args.url}
            if getattr(e, "remediation", None):
                detail["remediation"] = e.remediation
            return _emit_error(
                str(e),
                code=3,
                error_type="TranscriptFetchError",
                details=detail,
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
                concurrent_fragments=concurrent_fragments,
                media_timeout_sec=media_timeout_sec,
                with_description=args.with_description,
                description_only=args.description_only,
                cookies_file=args.cookies_file,
                auth_map=resolved_auth_map,
                cookies_from_browser=args.cookies_from_browser,
                asr_allow_cloud=asr_allow_cloud,
                asr_model=asr_model,
                asr_timeout_sec=asr_timeout_sec,
                max_duration_min=args.max_duration_min,
                remove_silence=remove_silence,
                debug=debug,
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
        except MissingDependencyError as e:
            # Surface the remediation hint per-URL (arch-016 §4.3 — exit 7
            # handling must exist in BOTH the single-URL and batch paths). The
            # batch run still aggregates to exit 4, but the record carries the
            # actionable type + remediation instead of a generic "Exception".
            failures += 1
            err_record = {
                "v": _JSON_ERRORS_SCHEMA,
                "error": str(e),
                "type": "MissingDependencyError",
                "url": url,
            }
            if getattr(e, "remediation", None):
                err_record["remediation"] = e.remediation
            sys.stdout.write(json.dumps(err_record, ensure_ascii=False) + "\n")
        except TranscriptFetchError as e:
            # Surface the transient (media-download timeout) remediation hint
            # per-URL, same as MissingDependencyError above — the batch run
            # still aggregates to exit 4, but the record carries the
            # actionable type + remediation instead of a generic "Exception".
            failures += 1
            err_record = {
                "v": _JSON_ERRORS_SCHEMA,
                "error": str(e),
                "type": "TranscriptFetchError",
                "url": url,
            }
            if getattr(e, "remediation", None):
                err_record["remediation"] = e.remediation
            sys.stdout.write(json.dumps(err_record, ensure_ascii=False) + "\n")
        except ValueError as e:
            # Mirror the single-URL path: a usage-class error (bad URL, or a
            # per-host convention cookies file that fails the 0600/symlink gate
            # -> AuthMapError, a ValueError subclass) is labelled UsageError, not
            # a generic "Exception". (A bad auth-MAP already fails fast pre-loop.)
            failures += 1
            err_record = {
                "v": _JSON_ERRORS_SCHEMA,
                "error": str(e),
                "type": "UsageError",
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
    vid = _extract_any_id(url) or _slugify(url)
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


def _extract_any_id(url: str) -> Optional[str]:
    """Source-aware id extraction for batch output filenames.

    Tries the YouTube, Vimeo, then X extractors so an X status/broadcast URL is
    named by its real id instead of a slugified URL. Returns ``None`` when no
    source pattern matches (caller falls back to :func:`_slugify`).
    """
    return extract_video_id(url) or extract_vimeo_id(url) or extract_x_id(url)


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
