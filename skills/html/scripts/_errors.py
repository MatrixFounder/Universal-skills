"""Unified error-reporting helper for office-skill CLI scripts.

Two modes:

  default       — human-readable message on stderr; the integer return
                  value goes back to the shell as the exit code.
  --json-errors — single line of JSON on stderr, then the same exit code.

JSON envelope:

    {"v":     1,                       # schema version (always present)
     "error": "<message>",
     "code":  <int>,                   # NEVER 0 — see report_error guard
     "type":  "<ErrorClass>",          # optional
     "details": {<context>}}            # optional, free-form

The schema version `v` is set so that wrappers can detect future
breaking changes (e.g. renaming a field) and refuse old payloads
gracefully. Bump only when the meaning of an existing field changes.

Why this exists: agent wrappers (CI runners, skill harnesses, the
ultrareview pipeline) parse stderr to surface failures back to the
model. Free-form text means each wrapper writes ad-hoc parsing per
script; a uniform JSON line means one parser covers every skill that
carries this module.

The stdout side of the same contract lives here too, in
`write_json_stdout`: a script's JSON *payload* must survive the caller's
locale exactly as its error envelope must. Both are machine channels, and
Python encodes neither of them for you — see that function's docstring for
the measurements.

Replication: this file is byte-identical across five skills
(`skills/docx/scripts/_errors.py`, `…/xlsx/…`, `…/pptx/…`, `…/pdf/…`,
`…/html/…`). docx is the master copy.
"""
from __future__ import annotations

import argparse
import contextlib
import errno
import io
import json
import os
import re
import sys
from typing import IO, Any, Callable, Iterator


SCHEMA_VERSION = 1

# Compiled once: `write_json_stdout` runs this over every payload, and a
# per-character Python loop showed up in the timings on multi-hundred-KB dumps.
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _escape_lone_surrogates(text: str) -> str:
    """Replace unpaired surrogates (U+D800-DFFF) with their `\\udXXX` JSON
    escape.

    UTF-8 is the one thing these characters cannot be encoded as, and they do
    occur: POSIX decodes undecodable filename bytes that way (`surrogateescape`),
    and a PDF with a broken `/ToUnicode` CMap hands the extractor whatever code
    point the CMap names. JSON carries them fine as escapes, and a parser turns
    the escape back into the same character, so escaping loses nothing. Cheap
    to check (`str.isascii()` short-circuits the common case) and it cannot
    fail twice: nothing unencodable is left afterwards.
    """
    if text.isascii() or not _LONE_SURROGATE.search(text):
        return text
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


def _envelope_line(envelope: dict[str, Any]) -> str:
    """Serialise an envelope as one line of ASCII-only JSON.

    `ensure_ascii=True` is not a style choice here. stderr is opened with
    `errors="backslashreplace"`, so a non-ASCII envelope never crashes — it
    quietly stops being JSON: measured under `PYTHONIOENCODING=ascii`, a
    Latin-1 message came out as `caf\\xe9` and an emoji as `\\U0001f600`,
    and neither `\\x` nor `\\U` is a legal JSON escape, so the wrapper this
    envelope exists for fails to parse it. (BMP characters survive only by
    coincidence: Python's `\\uXXXX` happens to be JSON's too.) Under
    `cp1252`, text outside that codec raises outright. ASCII-only output is
    encodable by every codec a caller can set and parses back to exactly the
    same string.
    """
    return json.dumps(envelope, ensure_ascii=True) + "\n"


def abandon_stdout(stream: IO[str] | None = None) -> None:
    """Point a dead stdout's file descriptor at `/dev/null`.

    Call this after a `BrokenPipeError`. Without it the interpreter flushes
    the same dead fd again while shutting down: it prints `Exception ignored
    while flushing sys.stdout` — a second, non-JSON line on stderr, right
    after the envelope — and **replaces the exit status with 120**, so the
    process contradicts the `code` it just reported. Measured across five
    scripts, the substitution is size-dependent and therefore not something a
    caller can reason about: a payload of ~90-130 KB exits 120, a larger one
    escapes as a raw traceback and exits 1.

    Best-effort by design: a stream with no real fd (a test's `StringIO`, a
    wrapper's proxy object) has nothing to redirect and needs nothing.
    """
    target = sys.stdout if stream is None else stream
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, target.fileno())
        os.close(devnull)
    except (OSError, ValueError, AttributeError):
        pass


def write_json_stdout(
    payload: Any,
    *,
    indent: int | None = None,
    default: Callable[[Any], Any] | None = None,
    separators: tuple[str, str] | None = None,
    newline: bool = True,
    stream: IO[str] | None = None,
) -> None:
    """Write `payload` to stdout as UTF-8 JSON whose bytes do not depend on
    the process locale.

    The text layer encodes with the process codec, so
    `print(json.dumps(x, ensure_ascii=False))` is locale-dependent output on
    a machine-readable channel. Measured: under `PYTHONIOENCODING=ascii` it
    aborts mid-write (`pdf_fill_form.py --check` left 58 bytes of truncated
    JSON on stdout and an 11-line traceback where `--json-errors` promises
    one JSON line), and under `cp1252` it silently emits bytes that are not
    valid UTF-8 at exit 0 (an em dash written as the single byte 0x97). JSON
    is UTF-8 by definition — RFC 8259 §8.1 — so these bytes must not depend
    on the caller's locale.

    Serialisation is one-shot, not streamed: if the payload cannot be
    serialised the caller gets an exception with *nothing* written, rather
    than a truncated document already on the wire.

    stdout receives LF on every platform, Windows included: bytes written to
    `sys.stdout.buffer` bypass the text layer's newline translation. Only
    inter-token whitespace is affected — a newline inside a JSON string is
    always the `\\n` escape — and a JSON reader cannot tell the difference.

    A `stream` with no `.buffer` (a test's `StringIO`, a wrapper's proxy)
    keeps the text path and the caller owns the encoding there. The
    lone-surrogate escape is applied before that branch, so both paths carry
    the identical value.

    On a dead pipe this redirects the fd (see `abandon_stdout`) and re-raises
    `BrokenPipeError`: the caller still owns its own envelope and exit code,
    which this module promises will agree.
    """
    text = _escape_lone_surrogates(json.dumps(
        payload, ensure_ascii=False, indent=indent, default=default,
        separators=separators,
    ))
    if newline:
        text += "\n"
    target = sys.stdout if stream is None else stream
    if target is None:
        # fd 1 was closed before the process even started (`prog >&-`): CPython
        # sets `sys.stdout` to None and makes `print()` a silent no-op — the one
        # outcome this module exists to prevent. Report it as the sink being
        # gone, which is exactly what every caller's BrokenPipeError arm already
        # says, rather than dying on an AttributeError three frames down.
        raise BrokenPipeError(errno.EBADF, "stdout is closed")
    buffer = getattr(target, "buffer", None)
    try:
        if buffer is None:
            target.write(text)
            target.flush()
            return
        # Anything already queued on the text layer must reach the fd before
        # our bytes do, or the two layers interleave out of order.
        target.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    except BrokenPipeError:
        abandon_stdout(target)
        raise


@contextlib.contextmanager
def utf8_stdout() -> Iterator[IO[str]]:
    """Yield a text stream over stdout that always encodes UTF-8.

    `write_json_stdout` serialises in one shot, which is the right shape for
    every payload a caller can hold in memory — but not for a producer that
    streams *because* it cannot: `xlsx2csv2json` serialises a 3M-cell workbook
    row by row precisely to avoid the several-hundred-MB intermediate string.
    This gives such a producer the same guarantee at the stream level: an
    `io.TextIOWrapper` bound to `sys.stdout.buffer` with `encoding="utf-8"`,
    so the locale's codec never sees the text, and `newline="\n"` so the
    document is byte-identical on every platform.

    The wrapper is detached, never closed — closing it would close the
    process's stdout. A `sys.stdout` with no `.buffer` (a test's `StringIO`) is
    yielded unchanged, the same text-path escape hatch the rest of this module
    keeps. On a dead pipe the fd is redirected (see `abandon_stdout`) and
    `BrokenPipeError` propagates to the caller, which owns the envelope.
    """
    target = sys.stdout
    if target is None:
        raise BrokenPipeError(errno.EBADF, "stdout is closed")
    buffer = getattr(target, "buffer", None)
    if buffer is None:
        yield target
        return
    target.flush()
    wrapper = io.TextIOWrapper(buffer, encoding="utf-8", newline="\n",
                               write_through=True)
    try:
        yield wrapper
        wrapper.flush()
    except BrokenPipeError:
        abandon_stdout(target)
        raise
    finally:
        try:
            wrapper.detach()
        except (OSError, ValueError):
            pass


def add_json_errors_argument(parser: argparse.ArgumentParser) -> None:
    """Wire the `--json-errors` flag into a CLI's argparse and route
    argparse's own usage errors (`parser.error`, missing required args,
    type-conversion failures) through the same JSON envelope.

    Call this in every script's `main()` right after the parser is
    constructed so the flag is uniform across the four skills.

    Implementation note: argparse's built-in `parser.error` exits 2 with
    plain-text usage to stderr. That bypasses the JSON envelope and is
    the most common way wrappers get tripped up — they parse stderr as
    JSON and choke on usage banners. We monkey-patch `parser.error`
    here so the same flag covers both domain errors (via
    `report_error`) and usage errors.
    """
    parser.add_argument(
        "--json-errors",
        dest="json_errors",
        action="store_true",
        help=(
            "Emit failures as a single line of JSON on stderr "
            "(machine-readable: {error, code, type?, details?})."
        ),
    )

    _argparse_error = parser.error

    def _json_aware_error(message: str) -> None:
        # We can't read parsed args here — argparse calls error() during
        # parsing, before parse_args() returns. Fall back to a literal
        # scan of sys.argv. False positives only happen if a string
        # arg literally contains "--json-errors", which is harmless
        # (we'd just emit the JSON form on a usage error — strictly
        # better for wrappers).
        if "--json-errors" in sys.argv[1:]:
            envelope = {
                "v": SCHEMA_VERSION,
                "error": message,
                "code": 2,
                "type": "UsageError",
                "details": {"prog": parser.prog},
            }
            sys.stderr.write(_envelope_line(envelope))
            sys.stderr.flush()
            sys.exit(2)
        _argparse_error(message)

    parser.error = _json_aware_error  # type: ignore[method-assign]


def report_error(
    message: str,
    *,
    code: int = 1,
    error_type: str | None = None,
    details: dict[str, Any] | None = None,
    json_mode: bool = False,
    stream: IO[str] = sys.stderr,
) -> int:
    """Write `message` to `stream` and return `code`.

    Idiom in callers:

        return report_error("Input not found", code=1, json_mode=args.json_errors)

    `code` is returned as-is so the caller can `sys.exit(main())` and
    the exit status matches the JSON envelope's `code` field — wrappers
    don't have to reconcile two sources of truth.

    Defensive coercion: `code=0` would mean "report an error then exit
    success", which is a contradiction and almost always a typo. We
    coerce to 1 and surface the fact so the bug shows up in tests
    instead of masquerading as success in production.

    JSON-mode coercion: the dev-hint is folded into `details` as
    `coerced_from_zero: true` so the envelope stays a single line of
    JSON — wrappers reading `head -1 stderr | jq` keep working. In
    plain mode the hint is written before the message because there
    is no envelope to fold into.
    """
    coerced_from_zero = code == 0
    if coerced_from_zero:
        code = 1
    if json_mode:
        envelope: dict[str, Any] = {
            "v": SCHEMA_VERSION,
            "error": message,
            "code": code,
        }
        if error_type is not None:
            envelope["type"] = error_type
        merged_details = dict(details) if details else {}
        if coerced_from_zero:
            merged_details["coerced_from_zero"] = True
        if merged_details:
            envelope["details"] = merged_details
        stream.write(_envelope_line(envelope))
    else:
        if coerced_from_zero:
            stream.write(
                "report_error: WARNING — caller passed code=0 with a "
                "non-empty error message; coercing to 1 to avoid a "
                "false-success exit.\n"
            )
        stream.write(message)
        if not message.endswith("\n"):
            stream.write("\n")
    stream.flush()
    return code
