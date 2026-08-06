"""CLI surface + orchestration for the html Web/HTML → Markdown converter (FC-5).

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
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# scripts/ on sys.path so the sibling ``_errors`` helper imports under any entry
# (the shim inserts it at runtime; tests run with scripts/ as cwd).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _errors  # noqa: E402

from .exceptions import (  # noqa: E402
    BadInput, EmptyExtraction, InternalError, SelfOverwriteRefused, Usage, _AppError,
)
from ._env import env as _env  # noqa: E402

_EXIT_OK = 0
_EXIT_USAGE = 2
_EXIT_ENGINE = 3
_EXIT_SELF_OVERWRITE = 6  # SelfOverwriteRefused.CODE owns the raise
_EXIT_FETCH = 10
_EXIT_EMPTY = 11          # EmptyExtraction.CODE owns the raise
# `html get --stdout` only: the consumer closed the pipe, so it holds a PREFIX of the bytes.
# 128+SIGPIPE is the shell convention; the skill's own map has no code for a write failure,
# and exit 0 here would be the undetectable truncation the file path exists to exclude.
_EXIT_BROKEN_PIPE = 141
_DEFAULT_ATTACH_DIR = "_attachments"

# Empty-extraction guard (R-7a): a substantial source page that converts to a near-empty
# Markdown body is silent content loss — treat it as a typed failure, not exit 0.
_MIN_BODY_CHARS = 16            # stripped whole-page Markdown shorter than this ⇒ "empty"
_SUBSTANTIAL_SOURCE_CHARS = 2048  # only flag when the SOURCE HTML was non-trivial

# OP3 `html get` — default byte cap. The conversion flags default `--max-bytes` to None
# (unbounded) because the text path bounds itself downstream; for an ARBITRARY BINARY
# download that default is a DoS foot-gun, so `get` carries a finite one. 64 MiB matches
# the cap the wiki-import consumer already applied to its own (now removed) urlopen.
_GET_DEFAULT_MAX_BYTES = 64 * 1024 * 1024

# OP3 `html get` — TOTAL wall-clock budget. `--timeout` is PER OPERATION and bounds nothing in
# total: a redirect chain multiplies it by (max_redirects + 1) inside EVERY retry pass, and a
# slow-drip body resets the read timeout on each chunk while `--max-bytes` caps only SIZE.
# Both measured: a 5-hop chain stalling under the timeout ran 2.4x the per-op budget, and a
# body dripping 1 byte / 1.6 s returned OK after 12.85 s against a 2 s timeout. At the shipped
# defaults the redirect case alone is 60 x 6 x 4 = 1440 s. This is the bound a consumer sizes
# its `subprocess(timeout=…)` against — so it has to be a real one, not a documented estimate.
_GET_DEFAULT_DEADLINE_S = 300.0

# The verb roster, surfaced in `html --help`. Until now the verbs were intercepted in `main`
# BEFORE the flat parser and therefore appeared in NO help output at all — so a consumer had
# no way to detect which verbs an installed copy supports. That matters because a caller that
# depends on a verb must fail CLOSED on an older install, and `html <verb> --help` cannot tell
# them apart: on a copy without the verb, argparse treats it as INPUT, sees --help, prints the
# top-level help and exits 0 — a FALSE POSITIVE.
# Each line therefore carries a full, unambiguous usage string (`html get URL OUTPUT_PATH`)
# that cannot occur by accident. Probe with e.g. `html --help | grep -q 'html get URL'`;
# a bare `grep -q get` would match `--target-selector`. Pinned by test_get.py.
_VERB_HELP = (
    "Verbs (each takes its own --help):\n"
    "  html fetch INPUT [OUTPUT_DIR]   download to <slug>.html + .meta.json (OP1)\n"
    "  html md INPUT [OUTPUT_DIR]      convert artifact/HTML/URL to Markdown (OP2)\n"
    "  html get URL OUTPUT_PATH        download raw bytes, guarded, no conversion (OP3)\n"
    "  html search QUERY [OUTPUT_DIR]  web search to Markdown notes\n"
    "  html login URL                  mint a browser session (headful)\n"
)


# --------------------------------------------------------------------------- #
# Argparse surface (ARCH §5.1)
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the full CLI surface. Defaults are the 022-01 frozen baseline."""
    p = argparse.ArgumentParser(
        prog="html",
        description="TASK 022: Convert a web URL or saved HTML/MHTML/webarchive into Markdown.",
        epilog=(
            "INPUT is a URL or a local .html/.htm/.mhtml/.mht/.webarchive. By default "
            "BOTH <slug>.md (whole page) and <slug>.reader.md (reader-extracted) are "
            "written, and images are downloaded into _attachments/. The Chrome engine "
            "(--engine chrome) is OPT-IN and soft-optional.\n\n" + _VERB_HELP
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
    reader.add_argument(
        "--reader-only", dest="reader_only", action="store_true", default=False,
        help="Emit ONLY the reader-extracted content as a single <slug>.md (no whole-page "
             "file, no <slug>.reader.md). Falls back to the whole page when the reader "
             "extraction is empty/over-stripped — never an empty note. For note pipelines.",
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
                  else Path.cwd() / "tmp" / "html_out").resolve()
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
            _env("READER_URL") or _env("READER_PROVIDERS")):
        raise Usage(
            "--engine remote requires HTML_READER_URL or HTML_READER_PROVIDERS "
            "(use --engine jina for the built-in reader).")
    if args.max_results is not None and args.max_results < 1:
        raise Usage("--max-results must be >= 1.")

    # Chrome auth (TASK 024 R2/R10): env fallbacks; sources mutually exclusive; any source forces
    # the chrome engine (never silently drop the credential to lite); a missing/unreadable
    # storage_state/cookies file → typed BadInput (graceful, not a traceback). Paths are
    # ``~``-expanded so a value from the auto-loaded `.env` (literal ``~``, unlike a shell `export`)
    # resolves correctly.
    def _expand(p):
        return os.path.expanduser(p) if p else p
    args.chrome_storage_state = _expand(getattr(args, "chrome_storage_state", None)
                                        or _env("CHROME_STORAGE_STATE"))
    args.chrome_cookies_file = _expand(getattr(args, "chrome_cookies_file", None)
                                       or _env("CHROME_COOKIES_FILE"))
    args.chrome_user_data_dir = _expand(getattr(args, "chrome_user_data_dir", None)
                                        or _env("CHROME_USER_DATA_DIR"))
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
    # set-and-forget HTML_CHROME_AUTH_MAP does not turn every public page into a chrome render).
    args.chrome_auth_map = _expand(getattr(args, "chrome_auth_map", None)
                                   or _env("CHROME_AUTH_MAP"))
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

    # Chrome scroll via env — parity with the --chrome-* env fallbacks. An env-only caller (e.g.
    # wiki-import, which forwards os.environ but hardcodes its html flags) can thus pull lazy
    # content: X articles/threads materialize ONLY after scrolling (no scroll → EmptyExtraction).
    # Harmless when the chrome engine isn't used (only _fetch_chrome_html reads it).
    if not args.chrome_scroll and _env(
            "CHROME_SCROLL", default="").strip().lower() in ("1", "true", "yes", "on"):
        args.chrome_scroll = True
    _passes = _env("CHROME_SCROLL_PASSES")
    if _passes and getattr(args, "chrome_scroll_passes", 8) == 8:  # env fills only the default
        try:
            args.chrome_scroll_passes = int(_passes)
        except ValueError:
            raise Usage("HTML_CHROME_SCROLL_PASSES must be an integer.")


def _resolve_search_paths(args: argparse.Namespace) -> tuple[Path | None, bool]:
    """Resolve OUTPUT_DIR for ``--search`` (no INPUT — the positional is the OUTPUT_DIR).

    ``--stdout`` → ``(None, True)``; an explicit dir → that; otherwise the default
    ``./tmp/html_out/``. Raises :class:`Usage` on >1 positional.
    """
    positionals = [p for p in (args.INPUT, args.OUTPUT_DIR) if p is not None]
    if len(positionals) > 1:
        raise Usage("--search accepts at most one OUTPUT_DIR positional.")
    if bool(args.stdout):
        return None, True
    out = Path(positionals[0]) if positionals else (Path.cwd() / "tmp" / "html_out")
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
    # --reader-only also needs the reader variant computed (emit collapses to it).
    want_reader = (bool(args.reader) or bool(getattr(args, "reader_only", False))) and query is None
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
        sys.stderr.write(f"html: no results for query: {args.search!r}\n")
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
    """``html login URL [--save-state PATH]`` — mint a Playwright ``storage_state`` via a
    HEADFUL browser (TASK 024 R3): the one interactive step; runtime is always headless. The
    surface is frozen here (024-01); the actual render lands in 024-04."""
    p = argparse.ArgumentParser(
        prog="html login",
        description="Open URL in a headful browser, log in by hand (2FA ok), then save the "
                    "session as a storage_state JSON (chmod 0600) for --chrome-storage-state.")
    p.add_argument("URL", help="page to open for login (e.g. https://x.com)")
    p.add_argument("--save-state", dest="save_state", metavar="PATH",
                   default="html-state.json",
                   help="where to write the storage_state JSON (default: ./html-state.json)")
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


_SKILL_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"  # <skill>/.env (one above scripts/)


def _load_skill_env(path: Path = _SKILL_ENV_PATH) -> None:
    """Skill-LOCAL config bootstrap (encapsulation): load ``<skill>/.env`` into the process
    environment so the skill's settings (auth map, scroll, reader/jina keys) travel WITH the skill.
    ANY caller — invoking the CLI directly or via the ``~/.claude/skills/html`` symlink — then
    picks them up with zero awareness, WITHOUT polluting the machine-global environment. Called only
    from the shim entry point, so importing the package (tests) never triggers it.

    - **Process env wins:** an already-set variable is never overridden (a caller may still override).
    - **Opt out:** ``HTML_NO_DOTENV=1`` skips it (the test harness sets this for determinism).
    - **Secrets-safe:** the file may hold tokens → skipped (with a stderr warning) if it is a symlink
      or group/world-accessible (require ``0600``). Never raises — config must not break a run (R10).
    """
    if _env("NO_DOTENV", default="").strip().lower() in ("1", "true", "yes", "on"):
        return
    try:
        if path.is_symlink() or not path.is_file():
            return
        if path.stat().st_mode & 0o077:
            sys.stderr.write(
                f"html: ignoring {path.name} (group/world-accessible — chmod 600 to enable)\n")
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if key and key not in os.environ:  # process env wins — never override a caller's value
                os.environ[key] = _dotenv_value(val)
    except OSError:
        return  # config must never break a run


def _dotenv_value(val: str) -> str:
    """Parse a `.env` RHS the way shell sourcing does: a quoted value keeps its contents (trailing
    text ignored); an unquoted value drops an inline ``#`` comment that follows whitespace (so
    ``KEY=jina_xxx   # note`` → ``jina_xxx``, never the comment), then is stripped."""
    val = val.strip()
    if val[:1] in ("'", '"'):
        q = val[0]
        end = val.find(q, 1)
        return val[1:end] if end != -1 else val[1:]
    for sep in (" #", "\t#"):
        i = val.find(sep)
        if i != -1:
            val = val[:i]
    return val.strip()


def _fetch_main(argv: list[str]) -> int:
    """``html fetch INPUT [OUTPUT_DIR]`` — OP1: download a URL/HTML/archive to an on-disk
    ``<slug>.html`` + ``<slug>.meta.json`` sidecar (+ localized ``_attachments/``), directly
    consumable by the pdf skill and by ``html md``. The HTML is sanitized (file:/javascript:
    refs stripped) before write; an authenticated fetch's body is written ``0600``.

    Reuses the shared flag surface; flags that only apply to conversion (``--reader-mode``)
    are accepted-and-ignored here. ``--remote-format markdown`` is refused: ``fetch`` emits
    HTML (the trust-markdown reader path is convert-only — use ``html md``)."""
    parser = build_parser()
    parser.prog = "html fetch"
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)
    try:
        if args.search is not None:
            raise Usage("`html fetch` does not take --search; use `html search`.")
        _validate_usage(args)
        if getattr(args, "remote_format", "html") == "markdown":
            raise Usage("--remote-format markdown is a convert-stage option; use `html md`.")
        input_ref, _mode, output_dir, stdout_mode = _resolve_paths(args)

        from . import acquire as acquire_mod
        from . import serialize as serialize_mod
        acq = acquire_mod.acquire(input_ref, args)
        if getattr(acq, "content_kind", "html") == "markdown":
            raise Usage("the remote reader returned Markdown, not HTML; use `html md`.")

        if stdout_mode:  # fetch --stdout: the sanitized (absolutized) HTML, no files
            html = acq.html
            if acq.mode == "url" and acq.base_url:
                html = acquire_mod._absolutize_img_srcs(
                    acquire_mod._absolutize_links(html, acq.base_url), acq.base_url)
            sys.stdout.write(serialize_mod.sanitize_untrusted_html(html))
            return _EXIT_OK

        art = serialize_mod.write_artifact(acq, output_dir, args, input_ref=input_ref)
        note = f"html fetch: wrote {art.html_path.name} + {art.meta_path.name}"
        if art.attachments_dir is not None:
            note += f" + {art.attachments_dir.name}/"
        sys.stderr.write(note + "\n")
        return _EXIT_OK
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr)


def _md_main(argv: list[str]) -> int:
    """``html md INPUT [OUTPUT_DIR]`` — OP2: convert a fetched artifact / local HTML / URL →
    Markdown. A local ``.html``/``.htm`` with a sibling ``<slug>.meta.json`` is hydrated from
    the sidecar (full trafilatura-grade frontmatter); a URL fetches+converts in one process;
    other local files / archives go through ``acquire``."""
    parser = build_parser()
    parser.prog = "html md"
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)
    try:
        if args.search is not None:
            raise Usage("`html md` does not take --search; use `html search`.")
        _validate_usage(args)
        input_ref, mode, output_dir, stdout_mode = _resolve_paths(args)
        from . import acquire as acquire_mod
        from . import serialize as serialize_mod
        if mode == "local" and Path(input_ref).suffix.lower() in (".html", ".htm"):
            acq = serialize_mod.read_artifact(Path(input_ref))   # sidecar-aware
        else:
            acq = acquire_mod.acquire(input_ref, args)
        return _convert_one(acq, args, output_dir, stdout_mode=stdout_mode, input_ref=input_ref)
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr)


def _parse_headers(raw: "list[str] | None") -> "dict[str, str] | None":
    """``--header 'Key: value'`` (repeatable) → the ``extra_headers`` dict.

    Rejects control characters in BOTH halves. The URL gets the same treatment from
    ``acquire._assert_safe_target``; a header pair is a second injection surface into the
    same request, and this one is introduced by ``get`` itself, so it carries its own check
    rather than assuming the transport will catch it (httpx does today — that is a property
    of the dependency, not a guarantee of ours)."""
    if not raw:
        return None
    out: dict[str, str] = {}
    for item in raw:
        # ★ Check the RAW item BEFORE any stripping. Checking after `.strip()` is a real
        # bypass and it shipped in the first draft: `str.strip()` removes \r and \n, so
        # "X-Bad\n: c" became "X-Bad" and the control-char test never saw the newline.
        if any(ord(c) < 0x20 or ord(c) == 0x7f for c in item):
            raise Usage("--header contains control characters.")
        key, sep, value = item.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise Usage("--header must be 'KEY: VALUE'.")
        out[key] = value
    return out


def _get_main(argv: list[str]) -> int:
    """``html get URL OUTPUT_PATH`` — OP3: download a URL to raw bytes on disk, verbatim.

    **What this is for.** :func:`acquire._fetch_lite_html` (the TEXT path) deliberately
    refuses a ``%PDF-`` payload — turndown blows its call stack on binary input — which is
    right for Markdown conversion and fatal for a caller that *wants* the bytes. Before this
    verb existed, such a caller had nothing to shell out to and fell back to a bare
    ``urllib.request.urlopen`` with **no SSRF guard at all**.

    **It bypasses no guard.** ``get`` calls :func:`acquire._assert_safe_target` and then
    :func:`acquire._http_get_bytes` — the same two the text path uses — and simply omits the
    content-type interpretation layered *above* them. The ladder is the function being
    called, not a check being skipped: control-char/CRLF refusal, http(s) only, **every** hop
    re-validated by ``_assert_public_http``, DNS resolved-then-pinned, redirects followed
    manually under a cap, the body streamed and aborted the moment it passes the cap, bounded
    timeout, no credential forwarding.

    ⚠️ **One inherited caveat, stated rather than implied**: the DNS pin is authoritative
    only on a DIRECT connection. ``httpx`` honours ``trust_env`` by default, so when an
    http(s) proxy is configured — including a macOS System Configuration proxy that
    ``env | grep -i proxy`` does NOT reveal — the proxy performs the target resolution and
    the pin never fires. The per-hop ``_assert_public_http`` pre-check still runs. This is a
    property of the shared ladder (the text path has it identically), not of this verb.

    **No content interpretation, by design**: no decode, no sanitize, no sniffing. A caller
    asking for bytes gets bytes; deciding what they are is the caller's job (that is what
    makes this composable with the pdf skill, which makes zero network calls of its own).
    Consequence the caller owns: these are UNSANITIZED, fully remote-controlled bytes written
    under a caller-chosen name — do not point ``get`` at a path that will then be rendered.

    Design notes (rationale lives in ``scripts/.AGENTS.md``): dedicated parser rather than
    ``build_parser()``, following the ``_login_main`` primitive-verb precedent;
    ``OUTPUT_PATH`` is a FILE, not an ``OUTPUT_DIR``.

    **Time is bounded for real, not estimated.** ``--timeout`` is PER OPERATION, so it bounds
    nothing in total: a redirect chain multiplies it by ``max_redirects + 1`` inside every
    retry pass, and a slow-drip body resets the read timeout on each chunk while
    ``--max-bytes`` caps only SIZE. ``--deadline`` (default 300 s) is the total wall clock,
    enforced inside the ladder at each hop and each chunk — it is the number to size a
    ``subprocess(timeout=…)`` against. Exceeding it is exit 10 with ``details.kind ==
    "deadline"``.

    Exit map: 0 ok · 2 usage (**including a non-http(s) URL**, so a caller's typo is
    distinguishable from a security refusal) · 10 FetchFailed (``details.kind`` discriminates
    ``refused`` / ``deadline`` / ``unreachable``, and ``details.max_bytes`` marks over-cap) ·
    1 internal · **141 broken pipe** (``--stdout`` only — the consumer closed the pipe and
    holds a PREFIX; reporting 0 there would be the undetectable truncation the file path
    exists to exclude).
    """
    parser = argparse.ArgumentParser(
        prog="html get",
        description="Download URL to OUTPUT_PATH as raw bytes, through the SSRF-guarded "
                    "fetch ladder. No conversion, no content sniffing.")
    parser.add_argument("url", metavar="URL", help="http(s) URL to download")
    parser.add_argument("output", metavar="OUTPUT_PATH", nargs="?", default=None,
                        help="file to write, replaced atomically (parent dirs are created; "
                             "an existing file is OVERWRITTEN). Omit only with --stdout.")
    parser.add_argument("--stdout", action="store_true",
                        help="write the bytes to stdout instead of a file (no temp-file "
                             "lifecycle for the caller)")
    parser.add_argument("--max-bytes", metavar="N", type=int,
                        default=_GET_DEFAULT_MAX_BYTES,
                        help=f"abort past N bytes (default: {_GET_DEFAULT_MAX_BYTES}). The "
                             f"body is buffered, so this is also the memory bound.")
    parser.add_argument("--timeout", metavar="S", type=float, default=60.0,
                        help="PER-OPERATION timeout in seconds, 0 < S <= 300 (default: 60). "
                             "It does NOT bound the total — see --deadline.")
    parser.add_argument("--deadline", metavar="S", type=float,
                        default=_GET_DEFAULT_DEADLINE_S,
                        help=f"TOTAL wall-clock budget in seconds, 0 < S <= 3600 "
                             f"(default: {_GET_DEFAULT_DEADLINE_S:g}). This is the number to "
                             f"size a subprocess timeout against.")
    parser.add_argument("--retries", metavar="N", type=int, default=2,
                        help="transient-failure retry budget, 0..10 (default: 2)")
    parser.add_argument("--header", metavar="KEY:VALUE", action="append", default=None,
                        help="extra request header (repeatable). Needed for content "
                             "negotiation, e.g. 'Accept: application/pdf,*/*'.")
    parser.add_argument("--browser-ua", action="store_true",
                        help="send a browser User-Agent from the first request instead of "
                             "the honest default (which escalates only on a 403)")
    _errors.add_json_errors_argument(parser)  # ALSO routes argparse's own usage errors
    try:                                      # through the JSON envelope — the consumer
        args = parser.parse_args(argv)        # parses stderr as JSON and chokes on banners
    except SystemExit as exc:
        # argparse already printed usage/help; RETURN the code rather than raise, because
        # this verb's consumer is another program calling `main()` directly.
        # ⚠️ `exc.code or _EXIT_USAGE` would be WRONG: `--help` exits 0, and 0 is falsy, so
        # the fallback would turn a successful --help into exit 2 — and a capability probe
        # (`html get --help`) would then read as "verb missing" on an install that HAS it.
        return _EXIT_USAGE if exc.code is None else int(exc.code)

    json_mode = bool(args.json_errors)
    try:
        if args.max_bytes <= 0:
            raise Usage("--max-bytes must be a positive integer.")
        if not 0 <= args.retries <= 10:
            raise Usage("--retries must be between 0 and 10.")
        # `type=float` accepts 0, -5, 1e9 and nan without complaint, and httpx applies the
        # value PER OPERATION rather than as a total budget — so an unvalidated timeout is a
        # slow-drip window, not just a bad number.
        if not (args.timeout > 0) or args.timeout > 300:  # `not >` also rejects nan
            raise Usage("--timeout must be a number in (0, 300].")
        if not (args.deadline > 0) or args.deadline > 3600:
            raise Usage("--deadline must be a number in (0, 3600].")
        if (args.output is None) == (not args.stdout):
            raise Usage("pass exactly one of OUTPUT_PATH or --stdout.")
        if args.browser_ua and any(k.lower() == "user-agent"
                                   for k in (h.partition(":")[0].strip()
                                             for h in (args.header or []))):
            # `_http_get_bytes` does `headers.update(extra_headers)` AFTER seeding the UA, so
            # the header would silently win and --browser-ua would be a no-op. Refuse rather
            # than pick a winner the caller cannot see.
            raise Usage("--browser-ua conflicts with --header 'User-Agent: …'; pass one.")

        # A caller mistake must NOT masquerade as a network refusal. Delegating scheme
        # checking to the ladder reports `html get /tmp/x.pdf` as exit 10 "refused
        # non-http(s) target", which reads as an SSRF block in the consumer's logs.
        if urlparse(args.url).scheme not in ("http", "https"):
            raise Usage(f"URL must be http(s), got: {args.url!r}")

        out: Path | None = None
        if args.output is not None:
            out = Path(args.output)
            # `write_bytes` opens 'wb', which FOLLOWS a symlink and writes through it. This
            # is the one hazard the caller cannot audit from the path it passed, and `get` is
            # the only verb that writes unsanitized remote bytes to a caller-named path.
            if out.is_symlink():
                raise Usage(f"OUTPUT_PATH is a symlink; refusing to write through it: "
                            f"{args.output!r}")
            if out.is_dir():
                raise Usage(f"OUTPUT_PATH is a directory: {args.output!r}")

        extra_headers = _parse_headers(args.header)

        from . import acquire as acquire_mod
        # Same order the text path uses: control-char refusal, THEN the network ladder.
        acquire_mod._assert_safe_target(args.url)
        # The single network seam. Any refusal (scheme, private/unresolvable host, redirect
        # cap, over-cap body) raises FetchFailed → exit 10 BEFORE anything is written.
        raw = acquire_mod._http_get_bytes(
            args.url, max_bytes=args.max_bytes, timeout=args.timeout,
            retries=args.retries, extra_headers=extra_headers,
            deadline_s=args.deadline,
            **({"ua": acquire_mod._BROWSER_UA} if args.browser_ua else {}))

        if out is None:
            try:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                # `html get URL --stdout | head` is ordinary usage, and it must not surface as
                # `Internal error: BrokenPipeError`. But it must not report SUCCESS either:
                # the caller received a PREFIX, and silently returning 0 is exactly the
                # undetectable truncation the file path is built to exclude. So: distinct,
                # documented exit 141 (128+SIGPIPE, the shell convention — the skill's own map
                # has no code for a write failure). Re-point stdout at /dev/null first, or
                # CPython prints "Exception ignored" at shutdown when it flushes again.
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
                return _EXIT_BROKEN_PIPE
            sys.stderr.write(f"html get: wrote {len(raw)} bytes to stdout\n")
            return _EXIT_OK

        out.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace via a UNIQUE sibling temp: a crash or a full disk mid-write can never
        # leave a TRUNCATED artifact under the caller's name, which the caller has no way to
        # detect. `mkstemp` rather than a fixed `<name>.part` because the fixed form collided
        # — an existing `.part` DIRECTORY produced `Internal error: PermissionError` — and
        # because two concurrent `get`s to one OUTPUT_PATH would otherwise share it.
        # mkstemp also creates 0600, so a capability-URL artifact is not world-readable while
        # in flight, and `os.replace` carries that mode to the final file.
        # (A refusal earlier than this leaves a pre-existing OUTPUT_PATH untouched — `get`
        # never unlinks a file it did not create.)
        fd, tmp_name = tempfile.mkstemp(dir=out.parent, prefix=out.name + ".", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            os.replace(tmp_name, out)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        sys.stderr.write(f"html get: wrote {out.name} ({len(raw)} bytes)\n")
        return _EXIT_OK
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr)


def combined_main(argv: list[str] | None = None) -> int:
    """The combined ``html2md`` command: **fetch → md → delete the intermediate HTML**.

    Built from the two primitives (OP1 ``write_artifact`` → OP2 convert-from-artifact) so the
    split is the single source of truth: the caller is left with just ``<slug>.md`` (+
    ``.reader.md``) + ``_attachments/`` — no leftover HTML. ``--stdout`` and the trust-markdown
    reader path have nothing to persist, so they convert in one pass."""
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    parser.prog = "html2md"
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)
    try:
        _validate_usage(args)  # before the --search dispatch (parity with convert())
        if args.search is not None:
            return _convert_search(args)  # search is inherently fetch+convert per result
        input_ref, _mode, output_dir, stdout_mode = _resolve_paths(args)
        from . import acquire as acquire_mod
        from . import serialize as serialize_mod
        acq = acquire_mod.acquire(input_ref, args)
        if stdout_mode or getattr(acq, "content_kind", "html") == "markdown":
            return _convert_one(acq, args, output_dir, stdout_mode=stdout_mode,
                                input_ref=input_ref)
        art = serialize_mod.write_artifact(acq, output_dir, args, input_ref=input_ref)
        try:
            rc = _convert_one(serialize_mod.read_artifact(art.html_path), args, output_dir,
                              stdout_mode=False, input_ref=str(art.html_path))
        finally:  # cleanup the intermediate HTML + sidecar (keep .md / .reader.md / _attachments)
            for p in (art.html_path, art.meta_path):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        return rc
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Top-level orchestrator. Routes every failure through ``_errors.report_error``.

    Exit map (§5.1): 0 ok · 1 BadInput/ConvertFailed/internal · 2 usage ·
    3 EngineNotInstalled · 6 SelfOverwriteRefused · 10 FetchFailed · 11 EmptyExtraction.
    Leading verbs (the roster is ``_VERB_HELP``, which is also what ``--help`` prints) are
    intercepted BEFORE the flat parser (the positional INPUT is ``nargs="?"``, so
    ``fetch URL`` would otherwise mis-parse as INPUT="fetch"). A bare ``INPUT [OUTPUT_DIR] …``
    (no verb) is the end-to-end pipeline (fetch+convert in one process); the combined
    ``html2md`` command builds on it."""
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "login":
        return _login_main(argv[1:])
    if argv and argv[0] == "fetch":
        return _fetch_main(argv[1:])
    if argv and argv[0] == "md":
        return _md_main(argv[1:])
    if argv and argv[0] == "get":  # OP3: raw bytes, guarded ladder, no interpretation
        return _get_main(argv[1:])
    if argv and argv[0] == "search":  # `html search QUERY [OUT]` → the --search flag branch
        return main(["--search", *argv[1:]])
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
