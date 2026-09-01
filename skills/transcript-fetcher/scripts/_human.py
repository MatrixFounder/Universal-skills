"""Locale-tolerant human-readable output — the presentation channel's contract.

The sibling module ``_stdout`` fixed the MACHINE channel: JSON on stdout must be
UTF-8 whatever the caller's locale says, because RFC 8259 §8.1 says so. This
module is the other half, and its contract is the OPPOSITE one.

``fetch.py doctor`` (without ``--json``) and ``install_components.py`` (without
flags) print prose for a person, decorated with ``—``, ``✓``, ``✗``, ``→``,
``⚠`` and ``…``. Python encodes a text stream with the codec taken from the
process locale, and the two standard streams get **different error handlers**:
stderr is always ``backslashreplace``, stdout is ``surrogateescape`` (or
``strict`` when ``PYTHONIOENCODING`` is set explicitly). Measured::

    LC_ALL=C                 stdout ascii/surrogateescape  stderr ascii/backslashreplace
    PYTHONIOENCODING=ascii   stdout ascii/strict           stderr ascii/backslashreplace

Only ``backslashreplace`` has a representation for an arbitrary unencodable
character. ``surrogateescape`` rescues lone surrogates and nothing else, so it
raises on an em dash exactly as ``strict`` does — which is why the asymmetry
bites even without ``PYTHONIOENCODING``. An em dash in a heading is fatal:

    PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C python3 install_components.py
    # rc=1, 0 bytes on stdout, UnicodeEncodeError on
    #   print("transcript-fetcher — component status\\n")

Both commands died on their FIRST line. A tool whose entire job is to say what
is missing from the system said nothing at all, and did it on a clean install —
the trigger is a literal in the source, not anything the user supplied.

Issue: ``docs/issues/tf-human-report-locale-crash.md``. The machine-channel
sibling is ``docs/issues/pdf-cli-stdout-json-locale-class.md``.

WHY NOT JUST FORCE UTF-8
------------------------
Because that is the machine channel's answer, and it is wrong here. Writing
UTF-8 into a terminal that declared itself cp1252 produces mojibake: the caller
asked for a codec and is entitled to get it. So ``write_json_stdout`` — which
correctly ignores the locale and writes UTF-8 bytes to ``sys.stdout.buffer`` —
must never be used for this text, and nothing here calls
``sys.stdout.reconfigure(encoding=...)``.

What the human channel owes the caller is narrower: **never crash, and lose as
little as the caller's codec allows.** Hence two layers, applied only when the
stream cannot take the string as-is:

  1. **Transliterate what has an ASCII spelling.** ``—`` → ``--``, ``✓`` → ``+``,
     ``→`` → ``->``. A report that degrades to ASCII art is still a report; one
     rendered as ``\\u2713`` is line noise.
  2. **``backslashreplace`` for everything else.** Arbitrary user data reaches
     this channel — the doctor prints ``c['label']`` and ``c['install_hint']``,
     which interpolate ``TRANSCRIPT_FETCHER_*_BIN`` overrides and
     ``sys.executable`` — and no table can anticipate it. An escape is lossy
     but legible, and it is what stderr has always done.

Both are **per character**, not per string, so a codec keeps what it can
represent: under cp1252 the em dash survives as 0x97 and only ``✓✗→⚠`` degrade.
Under UTF-8 — the overwhelmingly common case — the fast path proves the whole
string encodes and returns it untouched, so output is byte-identical to before
and no existing assertion moves.

WHAT ELSE THIS FIXES
--------------------
  * **``--help``.** The most-run human command of all, and the one nobody
    thinks of as output. argparse funnels help, usage and its own error text
    through ``ArgumentParser._print_message``, which guards ``AttributeError``
    and ``OSError`` but not ``UnicodeEncodeError`` — so a single em dash in one
    ``help=`` string 2350 characters in takes down the whole listing. Measured
    on ``fetch.py --help``: rc 1, 0 bytes. :class:`HumanArgumentParser` closes
    it without ASCII-ifying the help text everybody else reads.
  * **Lone surrogates, even under UTF-8.** ``str(out_path)`` can carry a
    ``\\udcXX`` when POSIX decodes an undecodable filename byte with
    ``surrogateescape``. UTF-8 is the one codec with no representation for
    those, so ``print(f"→ {path}")`` raises on a *correctly* configured
    machine. Measured: ``'utf-8' codec can't encode character '\\udcff'``.
  * **The dead-reader exit status.** With no reader on fd 1, the interpreter's
    shutdown flush printed ``Exception ignored while flushing sys.stdout`` and
    **replaced the exit status with 120** — measured on both human commands,
    including a ``doctor`` whose real answer was 7. This is the same axis
    ``_stdout`` closed for JSON; it was never closed here.

WHAT THIS DELIBERATELY DOES NOT TOUCH
-------------------------------------
  * ``fetch._emit_error`` — the ``--json-errors`` envelope and its plain-text
    remediation line on stderr. Different channel, different contract, its own
    tests (``tests/test_fetch_cli.py::test_non_json_mode_prints_remediation_line``),
    and it cannot crash (stderr is ``backslashreplace`` already). Routing it
    through here would change bytes a test pins, to fix nothing.
  * The process. No stream is reconfigured, no global is set; every other write
    the process makes still sees exactly the streams the caller handed it.

Stdlib only, and no imports from ``sources/`` or ``asr/`` — same rule as
``_stdout`` and ``_procgroup``: the CLI entry points import this, and it must
never drag the yt-dlp/caption/ASR stack in behind it.
"""
from __future__ import annotations

import argparse
import sys
from typing import IO, Any, Optional

from _stdout import abandon_stdout

#: ASCII spellings for the decorations this skill actually prints, plus the
#: punctuation a future edit most plausibly reaches for. This is a FALLBACK
#: table, not a transliterator: it is consulted only for characters the
#: caller's codec has already rejected, and anything missing from it degrades
#: to a ``backslashreplace`` escape rather than being dropped.
_ASCII_FALLBACK = {
    "—": "--",   # — em dash          headings, component labels
    "–": "-",    # – en dash
    "…": "...",  # … ellipsis         "Installing … "
    "→": "->",   # → rightwards arrow install hints
    "✓": "+",    # ✓ check mark       present / ready
    "✗": "x",    # ✗ ballot x         missing
    "⚠": "!",    # ⚠ warning sign     no-ASR warning
    "•": "*",    # • bullet
    "‘": "'",    # ‘
    "’": "'",    # ’
    "“": '"',    # “
    "”": '"',    # ”
    " ": " ",    # non-breaking space
    "≥": ">=",   # ≥
    "≤": "<=",   # ≤
    "×": "x",    # ×
}


def _encodable(text: str, encoding: str) -> bool:
    """Can ``encoding`` represent every character of ``text``?

    ``LookupError`` counts as "no": a stream may report an encoding name this
    interpreter cannot resolve, and guessing is worse than degrading.
    ``TypeError`` likewise — ``.encoding`` is only conventionally a ``str``,
    and a proxy object that returns something else must not become a crash.
    """
    try:
        text.encode(encoding)
    except (UnicodeError, LookupError, TypeError):
        return False
    return True


def _usable(encoding: object) -> bool:
    """Can ``str.encode`` actually use this codec name?

    Separate from :func:`_encodable`, which asks about a *string*. This asks
    about the *codec*, and the distinction matters: a bogus name makes every
    later ``encode`` raise no matter what the text is.
    """
    try:
        "".encode(encoding)  # type: ignore[arg-type]
    except (LookupError, TypeError):
        return False
    return True


def ascii_fallback(text: str, encoding: str) -> str:
    """Return ``text`` reduced to something ``encoding`` can represent.

    Pure and side-effect free, so it is unit-testable without a stream.

    The fast path matters: a string the codec already accepts is returned
    unchanged, by identity. That is the UTF-8 case — i.e. almost every real
    run — and it is why this fix moves no bytes on a correctly configured
    machine.

    The slow path is per character, so a codec is not punished for the one
    glyph it lacks; ``café — ✓`` under cp1252 keeps both the é and the em dash
    and degrades only the check mark. The final re-check is a backstop for
    stateful codecs (ISO-2022-JP and friends), where "each character encodes"
    does not strictly imply "the string encodes".
    """
    if not _usable(encoding):
        # The stream named a codec this interpreter cannot encode text with —
        # unknown, empty, non-``str``, or a bytes-to-bytes codec like ``base64``
        # that ``str.encode`` refuses outright. Every ``encode`` below would
        # raise ``LookupError``/``TypeError``, i.e. the crash this function
        # exists to prevent, thrown from inside the preventer. Fall back to
        # plain ASCII: the write is likely to fail anyway, but it fails in the
        # caller's ``try``, not here.
        encoding = "ascii"
    if _encodable(text, encoding):
        return text
    out = []
    for ch in text:
        if _encodable(ch, encoding):
            out.append(ch)
            continue
        replacement = _ASCII_FALLBACK.get(ch)
        if replacement is not None and _encodable(replacement, encoding):
            out.append(replacement)
        else:
            out.append(ch.encode(encoding, "backslashreplace").decode(encoding, "replace"))
    joined = "".join(out)
    if _encodable(joined, encoding):
        return joined
    return text.encode(encoding, "backslashreplace").decode(encoding, "replace")


def say(
    *values: Any,
    sep: Optional[str] = None,
    end: Optional[str] = None,
    file: Optional[IO[str]] = None,
    flush: bool = True,
) -> None:
    """``print()`` for the human channel: same signature, but it cannot raise
    ``UnicodeEncodeError`` and it does not lie about the exit status.

    Stays on the TEXT layer — unlike ``_stdout.write_json_stdout``, which
    bypasses it to force UTF-8 bytes. That asymmetry IS the contract: the
    machine channel overrides the caller's codec, the human channel obeys it.
    It also keeps newline translation and lets an in-process test capture this
    output with a plain ``StringIO``.

    A sink with no ``encoding`` attribute (``StringIO``, a wrapper's proxy) is
    a pure-``str`` sink that can hold anything, so nothing is degraded for it.

    The parameter is ``file``, not ``stream`` as in ``_stdout``, and the
    divergence is deliberate: every call site here is a former ``print``, and
    the migration is mechanical. Naming it anything else invites exactly the
    bug this signature prevents — a converted ``print(..., file=sys.stderr)``
    that raises ``TypeError`` on a branch too rare for a test to cover. (One
    was written, and caught, during this fix.) ``write_json_stdout`` keeps
    ``stream`` because nothing was ever a ``print`` there.

    ``file=None`` resolves to ``sys.stdout`` **at call time**, not at import
    time, because the tests patch it.

    The flush is load-bearing, not tidiness: ``print`` leaves stdout
    block-buffered into a pipe, so without it a dead reader would surface not
    here but in the interpreter's shutdown flush — which is the very path that
    rewrites the exit status to 120.
    """
    # print() treats sep=None/end=None as "use the default", and callers pass
    # them through from their own optional parameters. Rejecting them would
    # make this a drop-in everywhere except the one place it matters.
    sep = " " if sep is None else sep
    end = "\n" if end is None else end
    target = sys.stdout if file is None else file
    if target is None:
        # `prog >&-`: fd 1 was closed before the process started, so CPython
        # sets sys.stdout to None and print() is a silent no-op. Match that.
        # The machine channel raises here instead — a dropped JSON record is a
        # broken promise, a dropped progress line is not.
        return
    text = sep.join(str(v) for v in values) + end
    encoding = getattr(target, "encoding", None)
    if encoding:
        text = ascii_fallback(text, encoding)
    try:
        target.write(text)
        if flush:
            # Default True, unlike print. See the docstring: without it a dead
            # reader surfaces in the shutdown flush, which rewrites the status.
            target.flush()
    except BrokenPipeError:
        # Without this the shutdown flush hits the same dead fd, prints
        # "Exception ignored while flushing sys.stdout" and rewrites the exit
        # status to 120 — measured on `fetch.py doctor` (real answer: 7) and
        # `install_components.py` (real answer: 0). Re-raised because only the
        # caller knows what to report.
        abandon_stdout(target)
        raise


class HumanArgumentParser(argparse.ArgumentParser):
    """``ArgumentParser`` whose ``--help`` survives the caller's locale.

    ``help=`` and ``description=`` strings are prose, so they collect the same
    ``—``/``→``/``…`` as any other prose, and argparse writes them with a bare
    ``file.write``. Its own guard catches ``AttributeError`` and ``OSError``
    but not ``UnicodeEncodeError``, so ``fetch.py --help`` under ``LC_ALL=C``
    printed 0 bytes and exited 1 — over one em dash, 2350 characters into the
    listing, in the ``--media-timeout-sec`` help.

    ``_print_message`` is the single funnel for ``print_help``,
    ``print_usage``, ``error`` and ``exit``; overriding it covers all four,
    where patching the public methods would still miss ``exit``. It is private
    by name but has been stable since argparse entered the stdlib, and
    ``tests/test_human_channel.py`` asserts the funnel still exists so a future
    CPython would break a test rather than production.

    The ``except`` reproduces argparse's own contract — printing help must not
    raise — with the one difference that ``say`` has already pointed a dead fd
    at ``/dev/null``, so the interpreter's shutdown flush can no longer rewrite
    the exit status to 120.
    """

    def _print_message(self, message: str, file: Optional[IO[str]] = None) -> None:
        if not message:
            return
        try:
            say(message, end="", file=file if file is not None else sys.stderr)
        except (AttributeError, OSError):
            pass
