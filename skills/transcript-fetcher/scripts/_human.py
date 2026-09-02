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

``reconfigure(errors=...)`` is a different thing entirely and is exactly what
this module does use. It leaves the caller's codec alone and changes only what
happens to a character that codec cannot represent — which is the whole
question.

WHY THE STREAM AND NOT THE CALL SITES
-------------------------------------
The first version of this module exported a ``say()`` replacement for ``print``
and a ``HumanArgumentParser`` subclass for ``--help``, and every call site in
the skill was rewritten to use them. That worked, and it was the wrong shape:
it is ~157 lines of mechanism duplicated into every skill in the repository,
and it fails open — a ``print`` added later, by someone who did not know about
this file, silently reintroduces the crash. Mutation testing caught exactly
that.

``codecs.register_error`` is the documented extension point for "what should
happen to a character this codec cannot represent?". Installed on the stream,
it covers ``print``, argparse's own ``file.write`` (which no audit of
``print()`` call sites would ever have found), a bare ``sys.stdout.write``
inside a renderer, and any third-party write in the same process. There is
nothing to remember at the call site because there is no call site.

What remains duplicated per skill is the table — data, not mechanism.
"""

from __future__ import annotations

import atexit
import codecs
import os
import sys

#: Name under which the handler is registered process-wide. Also usable as an
#: ``errors=`` argument anywhere: ``text.encode("ascii", HUMAN_ERRORS)`` gives
#: exactly what a report would look like under that codec, which is how the
#: tests state their expectations without restating the table.
HUMAN_ERRORS = "human_channel.asciify"

#: ASCII spellings for the decoration these reports print. A FALLBACK table,
#: not a transliterator: consulted only for characters the caller's codec has
#: already rejected, and anything missing from it degrades to a
#: ``backslashreplace`` escape rather than being dropped.
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
    ``exc.object[exc.start:exc.end]`` can be several characters long, hence the
    loop. Degradation stays per character so a codec keeps everything it can
    carry — under cp1251 ``доклад — ✓`` keeps the Cyrillic AND the em dash and
    only the check mark moves.

    Anything the table does not know falls back to ``backslashreplace``, which
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
    """Point stdout's and stderr's error handler at :func:`_asciify`.

    Call once, early in ``main()`` — NOT at import. Registering the handler
    above is inert, but ``reconfigure`` mutates a process-wide stream, and a
    module that does that on import imposes it on everything that merely
    imports the module.

    stderr is included even though it never crashed: its ``backslashreplace``
    turns an em dash into the six characters ``\\u2014``, and ``--`` is
    strictly better for the same cost.

    ``line_buffering`` is set for a second, unrelated reason, and it matters:
    piped stdout is BLOCK-buffered, so ``doctor | head`` surfaced the dead
    reader during interpreter shutdown, where CPython prints "Exception ignored
    while flushing sys.stdout" and **replaces the exit status with 120** —
    ``doctor`` reported 120 where its real answer was 7. Line-buffered, the
    write itself raises BrokenPipeError inside ``main()``, where this skill's
    own handler already catches it. It also restores the behaviour stdout has
    on a terminal anyway; only redirection took it away.

    Failure is silent by design. A replaced stdout — a test's ``StringIO``, a
    capture proxy, ``prog >&-`` leaving ``sys.stdout`` as None — has no
    ``reconfigure`` to call, and none of that is a reason to fail a report.
    """
    if not streams:
        atexit.register(_quiet_a_dead_stdout)
    for stream in streams or (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors=HUMAN_ERRORS, line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass
