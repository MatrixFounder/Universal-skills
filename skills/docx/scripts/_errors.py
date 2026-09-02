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
import atexit
import codecs
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


def _utf8(text: str) -> bytes:
    return text.encode("utf-8")


def _write_encoded_stdout(
    text: str,
    encode: Callable[[str], bytes],
    stream: IO[str] | None = None,
) -> None:
    """Shared tail of every MACHINE-channel write: bytes to the fd, chosen by
    `encode`, never by the process locale.

    Factored out of `write_json_stdout` when the path-list writers below
    needed exactly the same four guarantees and differed only in how text
    becomes bytes.
    """
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
        buffer.write(encode(text))
        buffer.flush()
    except BrokenPipeError:
        abandon_stdout(target)
        raise


def write_text_stdout(
    text: str,
    *,
    newline: bool = True,
    stream: IO[str] | None = None,
) -> None:
    """Write non-JSON MACHINE output — a TSV row, a listing a tool greps — as
    UTF-8 bytes, independent of the caller's locale.

    Same contract as `write_json_stdout`, minus the serialisation. Use it
    wherever a program, not a person, consumes the line: transliterating it
    through `say` would corrupt the very field the consumer matches on.
    """
    _write_encoded_stdout(text + ("\n" if newline else ""), _utf8, stream)


def write_path_stdout(path: object, *, stream: IO[str] | None = None) -> None:
    """Write one filesystem path to stdout, byte-exactly.

    `os.fsencode`, not UTF-8, and the difference is not pedantry: POSIX
    filenames are bytes, and Python carries an undecodable one as a lone
    surrogate via `surrogateescape`. `os.fsencode` turns that back into the
    ORIGINAL bytes, so the caller's `$(...)` receives a path that actually
    opens; `.encode("utf-8")` would raise on it.

    This exists because a path list is a MACHINE channel — `skills/pdf/SKILL.md`
    says "All stdout goes to the output path list" — and the human channel's
    answer is wrong for it twice over. `print()` raised under a non-UTF-8
    locale AFTER the files were already on disk (measured: `pdf_split` wrote
    three chunks, then exited 1 with 0 bytes, so a caller that cleans up on
    failure deletes real output); and the human channel's degradation would
    have spelled the path as `\u0447...`, which is worse — a plausible-looking
    string that opens nothing. See
    docs/issues/human-cli-output-locale-class.md.
    """
    _write_encoded_stdout(str(path) + "\n", os.fsencode, stream)


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
    _write_encoded_stdout(text, _utf8, stream)


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


# --------------------------------------------------------------------- #
# The HUMAN channel — reports, progress, --help
# --------------------------------------------------------------------- #
#
# The machine helpers above must ignore the caller's locale: JSON is UTF-8 by
# RFC 8259 §8.1. Prose is the opposite — it must OBEY the caller's codec,
# because UTF-8 written into a terminal that declared cp1252 is mojibake, not
# robustness.
#
# Until this existed it obeyed by dying. stderr is opened
# errors="backslashreplace" and survives; stdout gets "surrogateescape" (or
# "strict" under an explicit PYTHONIOENCODING), and NEITHER can represent an
# em dash — surrogateescape rescues lone surrogates and nothing else. So one
# `—` or `✓` in a report, or in an argparse `help=` string, took the whole
# command down.
#
# The fix belongs to the STREAM, not to the call sites. `codecs.register_error`
# is the documented extension point for exactly this question — "what should
# happen to a character this codec cannot represent?" — and once the handler
# is on stdout it covers `print`, argparse's own `file.write`, a bare
# `sys.stdout.write` deep inside a renderer, and any third-party write in the
# same process. Nothing to remember at the call site, because there is no call
# site to remember.
#
# The first version of this fix did the opposite: a `say()` wrapper, a
# `HumanArgumentParser` subclass and a stream shim, ~157 lines copied into
# every skill, with every `print` rewritten to match. It worked, and it was
# the wrong shape — mutation testing showed a forgotten `print` still slipped
# through, and the duplicated block was mechanism rather than data. What is
# left below is data (the table) plus fifteen lines that hand it to CPython.
#
# Issue: docs/issues/human-cli-output-locale-class.md.

#: Name under which the handler is registered process-wide. Also usable as an
#: `errors=` argument anywhere: `text.encode("ascii", HUMAN_ERRORS)` gives
#: exactly what a report would look like under that codec, which is how the
#: tests state their expectations without restating the table.
HUMAN_ERRORS = "human_channel.asciify"

#: ASCII spellings for the decoration these reports print. A FALLBACK table,
#: not a transliterator: consulted only for characters the caller's codec has
#: already rejected, and anything missing from it degrades to a
#: `backslashreplace` escape rather than being dropped.
_ASCII_FALLBACK = {
    "—": "--", "–": "-", "…": "...", "→": "->", "←": "<-",
    "✓": "+", "✔": "+", "✗": "x", "✘": "x", "×": "x",
    "⚠": "!", "❌": "x", "✅": "+", "❗": "!", "•": "*", "§": "S",
    "±": "+/-", "≥": ">=", "≤": "<=", "≠": "!=", "°": " deg",
    "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
    # U+FE0F / U+FE0E only select an emoji's presentation; they carry no
    # meaning of their own. `⚠️` is U+26A0 U+FE0F, so mapping just the base
    # glyph left the selector behind and the report read `!️`. Dropping
    # them is the whole fix — the base character already says it.
    "️": "", "︎": "",
}


def _asciify(exc):
    """Spell an unencodable run in ASCII instead of letting it kill the write.

    The codec calls this once per unencodable RUN, not once per character:
    `exc.object[exc.start:exc.end]` can be several characters long, hence the
    loop. Degradation stays per character so a codec keeps everything it can
    carry — under cp1251 `доклад — ✓` keeps the Cyrillic AND the em dash and
    only the check mark moves.

    Anything the table does not know falls back to `backslashreplace`, which
    is what stderr has always done and precisely why stderr never crashed.

    Re-raises anything that is not an encode error. A decode error reaching
    here would mean the handler was installed on a readable stream, where
    guessing would corrupt input rather than tidy output.
    """
    if not isinstance(exc, UnicodeEncodeError):
        raise exc
    spelled = []
    for ch in exc.object[exc.start:exc.end]:
        replacement = _ASCII_FALLBACK.get(ch)
        if replacement is None:
            # Escaped against ASCII, NOT against `exc.encoding`. For every
            # charmap codec -- cp1251, cp1252, latin-1, cp850, cp932 -- the
            # exception reports `exc.encoding == "charmap"`, the literal
            # string, not the codec's name. Re-encoding through *that* does
            # not raise: the bare `charmap` codec falls back to Latin-1 and
            # hands back the RAW BYTE, so `é` came out of cp1251 as b"\xe9"
            # and the following decode blew up. ASCII escapes are also the
            # only universally safe answer -- the character is here precisely
            # because the caller's codec rejected it.
            replacement = ch.encode("ascii", "backslashreplace").decode("ascii")
        spelled.append(replacement)
    return "".join(spelled), exc.end


codecs.register_error(HUMAN_ERRORS, _asciify)


def _quiet_a_dead_stdout():
    """Drain stdout at exit, and if it is already gone, point fd 1 at devnull.

    Registered by `install_human_channel`, and the second half of the exit-code
    contract. `line_buffering` makes the CLI's own `except BrokenPipeError`
    handler see the failure and return its verdict — but the interpreter then
    flushes the SAME dead fd again during finalization, prints "Exception
    ignored while flushing sys.stdout" on stderr, and replaces that verdict
    with 120. Measured: `install_components.py` with no reader at all printed
    its own broken-pipe line, returned 1, and exited 120.

    atexit callbacks run before that final flush, so draining here leaves it
    nothing to fail on. A stream with no real fd (a test's StringIO) has
    nothing to redirect and needs nothing, hence the swallowed exceptions.
    """
    try:
        sys.stdout.flush()
    except (BrokenPipeError, ValueError, OSError):
        try:
            fd = sys.stdout.fileno()
        except (OSError, ValueError, AttributeError):
            return
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
        except OSError:
            return
        try:
            os.dup2(devnull, fd)
        finally:
            os.close(devnull)
    except AttributeError:
        pass


def install_human_channel(*streams):
    """Point stdout's and stderr's error handler at `_asciify`.

    Call once, early in `main()` — NOT at import. Registering the handler
    above is inert, but `reconfigure` mutates a process-wide stream, and a
    module that does that on import imposes it on everything that merely
    imports the module.

    stderr is included even though it never crashed: its `backslashreplace`
    turns an em dash into the six characters `\\u2014`, and `--` is strictly
    better for the same cost.

    `line_buffering` is set for a second, unrelated reason, and it matters:
    piped stdout is BLOCK-buffered, so `report | head` surfaces the dead reader
    during interpreter shutdown, where CPython prints "Exception ignored while
    flushing sys.stdout" and **replaces the exit status with 120** — a command
    contradicting the verdict it just gave. Line-buffered, the write itself
    raises BrokenPipeError inside `main()`, where the CLI's own handler sees
    it. This also just restores the behaviour stdout already has on a terminal;
    only redirection took it away.

    Failure is silent by design. A replaced stdout — a test's `StringIO`, a
    capture proxy, `prog >&-` leaving `sys.stdout` as None — has no
    `reconfigure` to call, and none of that is a reason to fail a report.
    """
    if not streams:
        atexit.register(_quiet_a_dead_stdout)
    for stream in streams or (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors=HUMAN_ERRORS, line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass

