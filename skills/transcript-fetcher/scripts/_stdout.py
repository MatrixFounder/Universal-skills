"""Locale-independent JSON on stdout — the machine channel's byte contract.

Every machine-readable line this skill prints (the ``doctor --json`` envelope,
the single-URL stat record, the batch JSONL stream, ``install_components.py
--json``) used to go out as ``print``/``sys.stdout.write`` of a ``json.dumps(…,
ensure_ascii=False)`` string. That writes **text**, so the bytes on the wire are
chosen by the process locale, and a dead reader is reported by the interpreter
instead of by the CLI. Two measured consequences, both on the SUCCESS path:

  * ``PYTHONIOENCODING=ascii`` / ``LC_ALL=C`` — ``UnicodeEncodeError`` instead of
    the promised JSON. Measured on ``fetch.py doctor --json``: 0 bytes of JSON on
    stdout, a 733-byte traceback on stderr, exit 1. In batch mode it was worse
    than a bad line: ``UnicodeEncodeError`` is a subclass of ``ValueError``, so
    the success-record write was caught by the loop's ``except ValueError``,
    relabelled ``UsageError`` and counted as a failure — three transcripts
    fetched and written to disk, stdout reporting ``3/3 URLs failed``, exit 4.
    A throw from an error-record write (those sit inside ``except`` blocks) had
    nowhere to go at all and aborted the whole run: measured 3 URLs in, 0
    records out, exit 1, URLs 2-3 never fetched.
  * ``PYTHONIOENCODING=cp1252`` (a routine Windows locale) — exit 0, no warning,
    and output that is not UTF-8: measured 1009 bytes where UTF-8 gives 1013,
    with the em dash of a remediation hint written as the single byte 0x97.
    JSON is UTF-8 by definition (RFC 8259 §8.1), so a strict reader rejects a
    payload the skill just declared successful.

Plus the pipe axis: with the reader gone, CPython's shutdown flush hits the dead
fd, prints ``Exception ignored while flushing sys.stdout`` on stderr and
**replaces the exit status with 120** — measured on ``fetch.py doctor --json``
and ``install_components.py --json`` (rc 120, 85 bytes of non-JSON stderr) and,
with a 360 KB record, on the batch loop (raw traceback, rc 120).

Issue: ``docs/issues/pdf-cli-stdout-json-locale-class.md`` (the class);
``docs/issues/pdf-extract-stdout-locale-encoding.md`` and
``pdf-extract-broken-pipe-exit-120.md`` (the two measured instances that set the
fix pattern).

WHY THIS IS NOT ``office/_errors.py``
-------------------------------------
The four office skills and ``html`` already carry a byte-identical
``_errors.py`` exporting the same two functions, and reusing it would be the
obvious DRY move. It is not available to this skill:

  * **Licence scope.** ``skills/docx|xlsx|pptx|pdf`` and ``skills/html`` are
    **Proprietary, All Rights Reserved**; this repository's root — and
    ``transcript-fetcher`` with it — is **Apache-2.0** (``CLAUDE.md`` §3).
    Importing or copying that module would embed proprietary source into an
    Apache-2.0 skill, which is exactly the reasoning that made ``html``
    proprietary rather than the reverse.
  * **Replication protocol.** ``_errors.py`` is byte-identical across five
    skills under a ``diff -q`` gate (``CLAUDE.md`` §2, docx is master). A sixth
    copy here would either break that gate or silently bind an Apache-2.0 skill
    to a proprietary master's change protocol.

So this is a separate, stdlib-only module: nothing here imports from, or is
imported by, an office skill, and this file is not part of the ``_errors.py``
replication set. It is deliberately smaller than that module — no error
envelope (this skill has its own ``_emit_error`` in ``fetch.py``, whose stdout
records carry no ``code`` field and must not be homogenised with the office
one), no ``default=``/``separators=`` hooks.

Be precise about what "separate" claims, because the two files will look alike
to an auditor: the *sequence* is common property, not authorship. There is one
correct way to do this — escape the surrogates, serialise once, flush the text
layer so the two layers cannot interleave, write UTF-8 to ``.buffer``, and on
``EPIPE`` redirect the fd (the idiom CPython's own documentation prescribes)
before re-raising — and any correct implementation converges on it. What is
NOT shared is a dependency: neither module can change the other, and this one
answers to this skill's licence and its own tests
(``tests/test_stdout_channel.py``).

WHAT THIS DOES NOT COVER (honest scope)
---------------------------------------
  * **stdout only.** The ``--json-errors`` envelope on stderr is a different
    channel with different defaults (stderr is opened ``errors="backslashreplace"``,
    so it mangles rather than raises) and is untouched here.
  * **The human-facing reports are still locale-fragile.** ``install_components.py``
    with no flags and ``fetch.py doctor`` without ``--json`` print ``✓``/``✗``/``→``
    through plain ``print()`` and still raise ``UnicodeEncodeError`` under
    ``LC_ALL=C``. That is a presentation surface, not a machine channel: its
    fix has to respect the caller's locale rather than override it, so it is
    recorded separately as ``docs/issues/tf-human-report-locale-crash.md``
    (open, unfixed).
  * **No process-wide reconfiguration.** Nothing here calls
    ``sys.stdout.reconfigure()``: the caller's codec choice still governs every
    other write the process makes, including its human-readable stderr.
  * **A stream without ``.buffer``** (a test's ``StringIO``, a wrapper's proxy)
    keeps the text path, where the caller owns the encoding. Only the surrogate
    escape is shared by both paths.
  * **Not atomic across records.** Each call writes one payload in one buffer
    write; a batch that dies mid-run still leaves the records it already
    streamed on the wire — that is the JSONL contract, not a defect.

Stdlib only, and no imports from ``sources/`` or ``asr/`` — same rule as
``_procgroup.py``: this module is imported by the CLI entry points and must
never drag the yt-dlp/caption/ASR stack in behind it.
"""
from __future__ import annotations

import errno
import json
import os
import sys
from typing import IO, Any, Optional


def escape_lone_surrogates(text: str) -> str:
    r"""Replace unpaired surrogates (U+D800-DFFF) with their ``\udXXX`` JSON
    escape.

    UTF-8 is the one encoding these code points have no representation in, and
    they reach this skill's records for a mundane reason: ``TranscriptStat.
    output_path`` is ``str(out_path)``, and POSIX decodes undecodable filename
    bytes with ``surrogateescape``. So a ``--out`` path the shell handed us as
    invalid UTF-8 puts a lone surrogate straight into a record that must be
    valid JSON.

    Escaping loses nothing: a JSON reader turns ``\udXXX`` back into the same
    character. Cheap in the common case (``str.isascii()`` short-circuits), and
    it cannot fail twice — nothing unencodable survives it.
    """
    if text.isascii():
        return text
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        return text
    return "".join(
        f"\\u{ord(ch):04x}" if 0xD800 <= ord(ch) <= 0xDFFF else ch
        for ch in text
    )


def abandon_stdout(stream: Optional[IO[str]] = None) -> None:
    """Point a dead stdout's file descriptor at ``/dev/null``.

    Call this after a ``BrokenPipeError``. Without it the interpreter flushes
    the same dead fd again while shutting down: it prints ``Exception ignored
    while flushing sys.stdout`` — a second, non-JSON line on stderr — and
    **replaces the exit status with 120**, so the process contradicts whatever
    it just reported. Measured here at rc 120 for ``fetch.py doctor --json``,
    ``install_components.py --json`` and a 360 KB batch record alike.

    Failure to redirect is not an error: a ``StringIO`` or a wrapper's proxy
    object has no ``fileno()`` to dup over, and neither has a shutdown flush to
    survive. Hence the broad ``except`` — this runs on a path that is already
    reporting a failure and must not add one of its own.
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
    indent: Optional[int] = None,
    newline: bool = True,
    stream: Optional[IO[str]] = None,
) -> None:
    """Write ``payload`` to stdout as UTF-8 JSON whose bytes do not depend on
    the process locale, then flush.

    The flush is part of the contract, not an optimisation: batch mode is a
    real JSONL stream, and its consumers see each record as it lands (measured
    through a pipe: three records at t+0.60 / 1.21 / 1.81 s with the flush,
    all three at t+1.81 s without it).

    Serialisation is one-shot, not streamed: a payload that cannot be
    serialised raises with **nothing** written, rather than leaving a truncated
    document on the wire the way ``json.dump(…, sys.stdout)`` does.

    stdout receives LF on every platform, Windows included — bytes written to
    ``sys.stdout.buffer`` bypass the text layer's newline translation. Only
    inter-token whitespace is affected (a newline inside a JSON string is
    always the ``\\n`` escape), so no reader can tell.

    On a dead pipe this redirects the fd (see :func:`abandon_stdout`) and
    re-raises ``BrokenPipeError``, because only the caller knows which exit code
    and which error envelope shape it owes its wrapper.
    """
    text = escape_lone_surrogates(
        json.dumps(payload, ensure_ascii=False, indent=indent)
    )
    if newline:
        text += "\n"
    target = sys.stdout if stream is None else stream
    if target is None:
        # fd 1 closed before the process started (`prog >&-`): CPython sets
        # sys.stdout to None and makes print() a silent no-op — the one outcome
        # this module exists to prevent. Report the sink as gone through the
        # exception every caller already handles, instead of dying on an
        # AttributeError inside an `except` block (which, in batch mode, aborts
        # the whole run and loses the URLs still queued).
        raise BrokenPipeError(errno.EBADF, "stdout is closed")
    buffer = getattr(target, "buffer", None)
    try:
        if buffer is None:
            target.write(text)
            target.flush()
            return
        # Drain the text layer first. Anything a caller already printed is
        # sitting in that wrapper's buffer, and bytes pushed straight at the
        # fd would overtake it — the record would arrive spliced into the
        # middle of an earlier line.
        target.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    except BrokenPipeError:
        abandon_stdout(target)
        raise
