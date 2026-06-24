"""CLI surface + orchestration for the html2md Web/HTML → Markdown converter (FC-5).

Owns the argparse contract (ARCH §5.1), INPUT (URL-or-path) + OUTPUT_DIR resolution
(self-overwrite guard + stdout mode), and the ``_errors`` envelope routing on every
failure path — mirroring ``pptx2md/cli.py``. ``main``/``convert`` are wired
end-to-end in bead 022-05; in the stub phase (022-01) ``main`` runs the real path
guards then returns ``_STUB_SENTINEL``.

Exit-code map (ARCH §5.1): 0 ok · 1 BadInput/ConvertFailed/internal · 2 usage ·
3 EngineNotInstalled · 6 SelfOverwriteRefused · 10 FetchFailed · 11 EmptyExtraction.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# scripts/ on sys.path so the sibling ``_errors`` helper imports under any entry
# (the shim inserts it at runtime; tests run with scripts/ as cwd).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _errors  # noqa: E402

from .exceptions import (  # noqa: E402
    BadInput, EmptyExtraction, InternalError, SelfOverwriteRefused, Usage, _AppError,
)

_EXIT_OK = 0
_EXIT_USAGE = 2
_EXIT_ENGINE = 3
_EXIT_SELF_OVERWRITE = 6  # SelfOverwriteRefused.CODE owns the raise
_EXIT_FETCH = 10
_EXIT_EMPTY = 11          # EmptyExtraction.CODE owns the raise
_DEFAULT_ATTACH_DIR = "_attachments"

# Empty-extraction guard (R-7a): a substantial source page that converts to a near-empty
# Markdown body is silent content loss — treat it as a typed failure, not exit 0.
_MIN_BODY_CHARS = 16            # stripped whole-page Markdown shorter than this ⇒ "empty"
_SUBSTANTIAL_SOURCE_CHARS = 2048  # only flag when the SOURCE HTML was non-trivial


# --------------------------------------------------------------------------- #
# Argparse surface (ARCH §5.1)
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the full CLI surface. Defaults are the 022-01 frozen baseline."""
    p = argparse.ArgumentParser(
        prog="html2md.py",
        description="TASK 022: Convert a web URL or saved HTML/MHTML/webarchive into Markdown.",
        epilog=(
            "INPUT is a URL or a local .html/.htm/.mhtml/.mht/.webarchive. By default "
            "BOTH <slug>.md (whole page) and <slug>.reader.md (reader-extracted) are "
            "written, and images are downloaded into _attachments/. The Chrome engine "
            "(--engine chrome) is OPT-IN and soft-optional."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "INPUT", nargs="?", default=None,
        help="URL or path to .html/.htm/.mhtml/.mht/.webarchive (required at runtime).",
    )
    p.add_argument(
        "OUTPUT_DIR", nargs="?", default=None,
        help="Directory to write Markdown + _attachments into (default: stdout mode).",
    )
    p.add_argument(
        "--engine", choices=("lite", "chrome", "auto", "jina", "remote"), default="auto",
        help="URL fetch engine: lite (httpx+trafilatura), chrome (Playwright), "
             "auto (local-first: lite→chrome→remote last-resort), jina (Jina Reader "
             "r.jina.ai, remote-first + local fallback), or remote (a configured "
             "vendor-agnostic reader, remote-first + local fallback). The remote tier "
             "sends the URL to an external service. Default: auto.",
    )
    p.add_argument(
        "--no-remote", dest="no_remote", action="store_true", default=False,
        help="Disable the remote-reader tier entirely (auto + on-demand). No URL is ever "
             "sent to an external reader; jina/remote engines become local-only.",
    )
    p.add_argument(
        "--remote-format", dest="remote_format", choices=("html", "markdown"),
        default="html",
        help="What the remote reader returns: html (default — flows through the local "
             "clean→turndown pipeline) or markdown (trust the reader's own clean Markdown).",
    )
    p.add_argument(
        "--target-selector", dest="target_selector", metavar="SEL", default=None,
        help="X-Target-Selector sent to the remote reader to extract just the article "
             "(default: 'article, main, [role=main]').",
    )
    p.add_argument(
        "--search", metavar="QUERY", default=None,
        help="Web-search mode: QUERY → top results → Markdown notes (vendor-agnostic; "
             "s.jina.ai default). Mutually exclusive with a URL/file INPUT; the first "
             "positional is then the OUTPUT_DIR.",
    )
    p.add_argument(
        "--max-results", dest="max_results", metavar="N", type=int, default=5,
        help="For --search: max number of top results to fetch + convert (default: 5).",
    )
    # Authenticated Chrome (TASK 024). The three auth sources are mutually exclusive; any of
    # them forces the chrome engine (the credential is never silently dropped to lite). Auth is
    # strictly opt-in — with none set, behaviour is byte-for-byte the prior render (R10).
    chrome_auth = p.add_mutually_exclusive_group()
    chrome_auth.add_argument(
        "--chrome-storage-state", dest="chrome_storage_state", metavar="PATH", default=None,
        help="Playwright storage_state JSON (cookies + localStorage) from a prior login — the "
             "portable, server-deployable auth primitive. Mint with the `login` subcommand.",
    )
    chrome_auth.add_argument(
        "--chrome-cookies-file", dest="chrome_cookies_file", metavar="PATH", default=None,
        help="Netscape cookies.txt (cookie-only session) injected into the Chrome context.",
    )
    chrome_auth.add_argument(
        "--chrome-user-data-dir", dest="chrome_user_data_dir", metavar="DIR", default=None,
        help="Persistent Chrome profile dir (local convenience; self-refreshes, survives 2FA; "
             "NOT for concurrent/server use).",
    )
    chrome_auth.add_argument(
        "--chrome-auth-map", dest="chrome_auth_map", metavar="PATH", default=None,
        help="Per-domain auth map (JSON: host → {cookies_file|storage_state}) for MULTIPLE "
             "logged-in sites. Forces chrome ONLY for a mapped target domain; non-mapped targets "
             "keep the normal ladder. Map + each referenced file must be chmod 600.",
    )
    p.add_argument(
        "--chrome-scroll", dest="chrome_scroll", action="store_true", default=False,
        help="After load, scroll to pull lazy content (e.g. replies). Bounded by "
             "--chrome-scroll-passes + an internal wall-clock cap; never hangs.",
    )
    p.add_argument(
        "--chrome-scroll-passes", dest="chrome_scroll_passes", metavar="N", type=int, default=8,
        help="Max scroll passes for --chrome-scroll (default: 8).",
    )
    reader = p.add_mutually_exclusive_group()
    reader.add_argument(
        "--reader-mode", dest="reader", action="store_true", default=True,
        help="Also emit <slug>.reader.md (default: on).",
    )
    reader.add_argument(
        "--no-reader", dest="reader", action="store_false",
        help="Suppress the reader-extracted variant; emit a single .md only.",
    )
    dl = p.add_mutually_exclusive_group()
    dl.add_argument(
        "--download-images", dest="download_images", action="store_true", default=True,
        help="Download images into the attachments dir (default: on).",
    )
    dl.add_argument(
        "--no-download-images", dest="download_images", action="store_false",
        help="Keep remote image URLs verbatim (no download).",
    )
    p.add_argument(
        "--attachments-dir", metavar="DIR", default=_DEFAULT_ATTACH_DIR,
        help=f"Attachments folder name (default: {_DEFAULT_ATTACH_DIR}).",
    )
    p.add_argument(
        "--archive-frame", metavar="SPEC", default="main",
        help="For .webarchive/.mhtml: which subframe (main|N|all|auto; default main).",
    )
    p.add_argument(
        "--max-bytes", metavar="N", type=int, default=None,
        help="Cap bytes fetched per request (SSRF/DoS bound; default: unbounded).",
    )
    p.add_argument(
        "--max-images", metavar="N", type=int, default=None,
        help="Cap the number of images downloaded (default: unbounded).",
    )
    p.add_argument(
        "--retries", metavar="N", type=int, default=2,
        help="Transient-failure retries per fetch (transport errors / HTTP 5xx / 429 "
             "with exponential backoff). Default: 2. Use 0 to disable.",
    )
    p.add_argument(
        "--rate-limit", metavar="REQS_PER_SEC", type=float, default=None,
        help="Throttle outbound fetches (page + images) to N requests/sec "
             "(default: unbounded). Polite-crawl bound for image-heavy pages.",
    )
    p.add_argument(
        "--stdout", action="store_true", default=False,
        help="Emit frontmatter + whole-page Markdown to stdout (agent-step mode; "
             "no files, reader variant + image download skipped).",
    )
    _errors.add_json_errors_argument(p)
    return p


# --------------------------------------------------------------------------- #
# Path / URL resolution
# --------------------------------------------------------------------------- #
def _resolve_paths(args: argparse.Namespace) -> tuple[str, str, Path | None, bool]:
    """Resolve INPUT (URL or local) + OUTPUT_DIR.

    Returns ``(input_ref, mode, output_dir|None, stdout_mode)`` where ``mode`` is
    ``"url"`` (scheme http/https — no filesystem stat) or ``"local"`` (resolved,
    must exist; ``acquire`` later refines local → file/archive).

    Raises:
        BadInput (1): INPUT omitted, or a local path that does not exist.
        SelfOverwriteRefused (6): OUTPUT_DIR resolves to the INPUT file (incl. symlink).
    """
    if args.INPUT is None:
        raise BadInput("INPUT is required (a URL or a local .html/.mhtml/.webarchive).")

    scheme = urlparse(args.INPUT).scheme.lower()
    if scheme in ("http", "https"):
        mode = "url"
        input_ref = args.INPUT
    else:
        mode = "local"
        try:
            input_ref = str(Path(args.INPUT).resolve(strict=True))
        except FileNotFoundError as exc:
            raise BadInput(
                f"Input not found: {Path(args.INPUT).name}",
                details={"path": Path(args.INPUT).name},
            ) from exc

    if bool(args.stdout):
        return input_ref, mode, None, True

    # Default output (no OUTPUT_DIR, no --stdout): a folder under ./tmp/, matching the
    # docx/pdf convention of writing files to an explicit working-dir path (never
    # silently to stdout). An explicit OUTPUT_DIR overrides; --stdout opts into stdout.
    output_dir = (Path(args.OUTPUT_DIR) if args.OUTPUT_DIR
                  else Path.cwd() / "tmp" / "html2md_out").resolve()
    if mode == "local" and output_dir == Path(input_ref):
        raise SelfOverwriteRefused(
            f"OUTPUT_DIR resolves to INPUT: {Path(input_ref).name}",
            details={"path": Path(input_ref).name},
        )
    # NB: the directory is created lazily by emit() right before writing — a run
    # that fails earlier (fetch error, EngineNotInstalled, …) leaves no empty dir.
    return input_ref, mode, output_dir, False


# --------------------------------------------------------------------------- #
# Pipeline (wired in 022-05)
# --------------------------------------------------------------------------- #
def _extraction_is_empty(md_whole: str, source_html: str) -> bool:
    """True when a SUBSTANTIAL source page yielded a near-empty whole-page body (R-7a).

    The whole-page Markdown is the faithful fallback (the reader variant may legitimately
    empty); if even *it* collapses while the source HTML was non-trivial, extraction
    silently lost the content — a typed failure, not a successful empty note.
    """
    return (len(md_whole.strip()) < _MIN_BODY_CHARS
            and len(source_html or "") >= _SUBSTANTIAL_SOURCE_CHARS)


def _validate_usage(args: argparse.Namespace) -> None:
    """Post-parse usage checks argparse can't express → raise :class:`Usage` (exit 2).

    - ``--search`` takes a QUERY, not a URL: a URL positional is a usage error (the first
      positional is the OUTPUT_DIR in search mode).
    - ``--engine remote`` needs a configured reader (never a silent fall-back to jina.ai).
    - ``--max-results`` must be ≥ 1.
    """
    if args.search is not None:
        for pos in (args.INPUT, args.OUTPUT_DIR):
            if pos is not None and urlparse(pos).scheme in ("http", "https"):
                raise Usage("--search takes a QUERY, not a URL; pass an OUTPUT_DIR positional.")
    if args.engine == "remote" and not (
            os.environ.get("HTML2MD_READER_URL") or os.environ.get("HTML2MD_READER_PROVIDERS")):
        raise Usage(
            "--engine remote requires HTML2MD_READER_URL or HTML2MD_READER_PROVIDERS "
            "(use --engine jina for the built-in reader).")
    if args.max_results is not None and args.max_results < 1:
        raise Usage("--max-results must be >= 1.")

    # Chrome auth (TASK 024 R2/R10): env fallbacks; sources mutually exclusive; any source forces
    # the chrome engine (never silently drop the credential to lite); a missing/unreadable
    # storage_state/cookies file → typed BadInput (graceful, not a traceback).
    args.chrome_storage_state = (getattr(args, "chrome_storage_state", None)
                                 or os.environ.get("HTML2MD_CHROME_STORAGE_STATE"))
    args.chrome_cookies_file = (getattr(args, "chrome_cookies_file", None)
                                or os.environ.get("HTML2MD_CHROME_COOKIES_FILE"))
    args.chrome_user_data_dir = (getattr(args, "chrome_user_data_dir", None)
                                 or os.environ.get("HTML2MD_CHROME_USER_DATA_DIR"))
    _auth = [s for s in (args.chrome_storage_state, args.chrome_cookies_file,
                         args.chrome_user_data_dir) if s]
    if len(_auth) > 1:
        raise Usage("--chrome-storage-state / --chrome-cookies-file / --chrome-user-data-dir "
                    "are mutually exclusive.")
    if _auth and args.search is not None:
        # Security (vdd-multi L-1): a login session must NOT be fanned out across
        # attacker-influenceable search-result URLs (would defeat the S-1 chrome-escalation guard).
        raise Usage("--chrome-* auth cannot be combined with --search.")
    if _auth:
        args.engine = "chrome"  # auth ⇒ chrome (credential never dropped to lite)
        for f in (args.chrome_storage_state, args.chrome_cookies_file):
            if f and not Path(f).is_file():
                raise BadInput(f"chrome auth file not found: {Path(f).name}",
                               details={"path": Path(f).name})

    # Per-domain auth map (TASK 026, multi-site): env fallback; cannot mix with a fixed source or
    # --search (a session must not fan over search results). Unlike a fixed source it forces chrome
    # ONLY when the target domain is mapped — non-mapped targets keep the normal ladder (so a
    # set-and-forget HTML2MD_CHROME_AUTH_MAP does not turn every public page into a chrome render).
    args.chrome_auth_map = (getattr(args, "chrome_auth_map", None)
                            or os.environ.get("HTML2MD_CHROME_AUTH_MAP"))
    if args.chrome_auth_map:
        if _auth:
            raise Usage("--chrome-auth-map cannot be combined with --chrome-storage-state / "
                        "--chrome-cookies-file / --chrome-user-data-dir.")
        if args.search is not None:
            raise Usage("--chrome-auth-map cannot be combined with --search.")
        if args.INPUT and urlparse(args.INPUT).scheme in ("http", "https"):
            from . import _chrome_auth
            amap = _chrome_auth.load_auth_map(Path(args.chrome_auth_map))  # hardened: 0600/JSON/shape
            if _chrome_auth.host_in_map(args.INPUT, amap):
                args.engine = "chrome"  # mapped domain ⇒ authed chrome; others stay on the ladder


def _resolve_search_paths(args: argparse.Namespace) -> tuple[Path | None, bool]:
    """Resolve OUTPUT_DIR for ``--search`` (no INPUT — the positional is the OUTPUT_DIR).

    ``--stdout`` → ``(None, True)``; an explicit dir → that; otherwise the default
    ``./tmp/html2md_out/``. Raises :class:`Usage` on >1 positional.
    """
    positionals = [p for p in (args.INPUT, args.OUTPUT_DIR) if p is not None]
    if len(positionals) > 1:
        raise Usage("--search accepts at most one OUTPUT_DIR positional.")
    if bool(args.stdout):
        return None, True
    out = Path(positionals[0]) if positionals else (Path.cwd() / "tmp" / "html2md_out")
    return out.resolve(), False


def _convert_one(
    acq, args: argparse.Namespace, output_dir: Path | None, *,
    stdout_mode: bool, input_ref: str, query: str | None = None,
) -> int:
    """Convert ONE acquired document → emit. Shared by the single-input path and the
    ``--search`` per-result loop (so a search result and a direct URL take identical
    treatment). ``query`` is threaded to emit's frontmatter in 023-06; the
    ``content_kind == "markdown"`` trust-mode bypass is added in 023-05.
    """
    from . import emit as emit_mod
    from .md_clean import tidy_markdown

    # Trust-markdown (R4): the remote reader already returned clean Markdown — bypass
    # web_clean + turndown; only frontmatter + image localization apply (no reader variant).
    if getattr(acq, "content_kind", "html") == "markdown":
        md_whole = tidy_markdown(acq.markdown or "")
        emit_mod.emit(acq, None, md_whole, None, args,
                      output_dir=output_dir, stdout_mode=stdout_mode, input_ref=input_ref,
                      query=query)
        return _EXIT_OK

    from . import clean as clean_mod
    from . import core_bridge

    # Search results are emitted as ONE note each (R9: N results → N notes); a direct
    # conversion keeps the dual-output default. `query is not None` ⇒ search mode.
    want_reader = bool(args.reader) and query is None
    cleaned = clean_mod.clean(acq, reader=want_reader)
    md_whole = tidy_markdown(core_bridge.html_to_markdown(cleaned.whole_html))
    md_reader = (
        tidy_markdown(core_bridge.html_to_markdown(cleaned.reader_html))
        if (want_reader and cleaned.reader_html is not None) else None
    )
    if _extraction_is_empty(md_whole, acq.html):
        raise EmptyExtraction(
            f"extracted an empty body from a {len(acq.html)}-char source "
            f"({Path(input_ref).name or input_ref}). The page may render its content "
            "via JavaScript or a non-standard layout — try --engine chrome / jina, or a "
            "site-specific endpoint (e.g. Wikipedia's REST page/html).",
            details={"source_chars": len(acq.html), "body_chars": len(md_whole.strip()),
                     "engine": acq.engine},
        )
    emit_mod.emit(
        acq, cleaned, md_whole, md_reader, args,
        output_dir=output_dir, stdout_mode=stdout_mode, input_ref=input_ref, query=query,
    )
    return _EXIT_OK


def _convert_search(args: argparse.Namespace) -> int:
    """``--search`` branch: query → top-N results → one note per result (023-06 logic)."""
    from . import acquire as acquire_mod
    output_dir, stdout_mode = _resolve_search_paths(args)
    results = acquire_mod.run_search(args.search, args)
    if not results:  # healthy search, zero results → not content-loss (exit 0 + note)
        sys.stderr.write(f"html2md: no results for query: {args.search!r}\n")
        return _EXIT_OK
    for i, acq in enumerate(results):
        ref = (acq.source_meta.url if acq.source_meta else None) or args.search
        if stdout_mode and i:
            sys.stdout.write("\n\n")  # blank-line + `---` frontmatter = note boundary (L-5)
        _convert_one(acq, args, output_dir, stdout_mode=stdout_mode,
                     input_ref=ref, query=args.search)
    return _EXIT_OK


def convert(args: argparse.Namespace) -> int:
    """Run the full pipeline for parsed ``args``: acquire → clean → core → emit.

    Returns 0 on success.
    """
    _validate_usage(args)
    if args.search is not None:
        return _convert_search(args)

    from . import acquire as acquire_mod
    input_ref, mode, output_dir, stdout_mode = _resolve_paths(args)
    acq = acquire_mod.acquire(input_ref, args)
    return _convert_one(acq, args, output_dir, stdout_mode=stdout_mode, input_ref=input_ref)


def _login_main(argv: list[str]) -> int:
    """``html2md.py login URL [--save-state PATH]`` — mint a Playwright ``storage_state`` via a
    HEADFUL browser (TASK 024 R3): the one interactive step; runtime is always headless. The
    surface is frozen here (024-01); the actual render lands in 024-04."""
    p = argparse.ArgumentParser(
        prog="html2md.py login",
        description="Open URL in a headful browser, log in by hand (2FA ok), then save the "
                    "session as a storage_state JSON (chmod 0600) for --chrome-storage-state.")
    p.add_argument("URL", help="page to open for login (e.g. https://x.com)")
    p.add_argument("--save-state", dest="save_state", metavar="PATH",
                   default="html2md-state.json",
                   help="where to write the storage_state JSON (default: ./html2md-state.json)")
    _errors.add_json_errors_argument(p)
    args = p.parse_args(argv)
    json_mode = bool(args.json_errors)
    try:
        from . import acquire as acquire_mod
        acquire_mod._login_render(args.URL, args.save_state, args)
        return _EXIT_OK
    except _AppError as exc:
        return _errors.report_error(str(exc), code=exc.CODE, error_type=exc.error_type,
                                    details=exc.details, json_mode=json_mode, stream=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — graceful: any login error → typed envelope, no traceback
        return _errors.report_error(f"login failed: {type(exc).__name__}",
                                    code=InternalError.CODE, error_type="InternalError",
                                    json_mode=json_mode, stream=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Top-level orchestrator. Routes every failure through ``_errors.report_error``.

    Exit map (§5.1): 0 ok · 1 BadInput/ConvertFailed/internal · 2 usage ·
    3 EngineNotInstalled · 6 SelfOverwriteRefused · 10 FetchFailed · 11 EmptyExtraction.
    A leading ``login`` verb is intercepted BEFORE the flat parser (the positional INPUT is
    ``nargs="?"``, so ``login URL`` would otherwise mis-parse as INPUT="login")."""
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "login":
        return _login_main(argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)

    try:
        return convert(args)
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
