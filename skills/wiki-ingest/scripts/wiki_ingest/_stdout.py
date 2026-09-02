"""F1 · locale-independent JSON writer for the CLI's stdout channel.

Every subcommand of `wiki_ops.py` answers on stdout with one JSON
document. That is a **machine** channel — the `/wiki-enrich` bridge,
operator CI, `jq` — so its bytes must be the same on every host, and a
reader that walks away must not be able to rewrite the command's verdict.
Neither property holds for `print(json.dumps(...))`, which is why this
module exists.

Two independent defects are closed here. Both were measured on this
package at HEAD and after the fix, on macOS 26.5 / CPython 3.14.4, over a
vault the CLI builds itself — a personal wiki is non-ASCII by default,
not by exception:

    wiki_ops.py init /tmp/wi/vault
    wiki_ops.py upsert-page /tmp/wi/vault --kind concept \
        --name 'Кривая доходности' --definition '…' …
    wiki_ops.py upsert-page /tmp/wi/vault --kind concept \
        --name 'Спред кредитный'   --definition '…' …
    wiki_ops.py upsert-page /tmp/wi/vault --kind entity  \
        --name 'Böhm-Bawerk'       --definition '…' …

The vault's absolute path is a field of `scan`'s manifest, so the byte
totals below move with it; the exit codes and the deltas do not.

**A · the process locale picked the codec.** `print()` hands text to
`sys.stdout`'s `TextIOWrapper`, which encodes with `PYTHONIOENCODING`
and then the locale. `json.dumps` builds the whole document first, so
the encode fails on one `write` and the command emits **nothing**. HEAD,
`PYTHONUTF8=0`, three codecs, exit code / stdout bytes / stderr lines:

    scan   utf-8  0 / 463 / 0    ascii  1 / 0 / 11    cp1252  1 / 0 / 14
    lint   utf-8  0 / 820 / 0    ascii  1 / 0 / 13    cp1252  1 / 0 / 16
    find   utf-8  0 / 301 / 0    ascii  1 / 0 / 15    cp1252  1 / 0 / 18
           (`find … --terms Спред`)

Every failing run ended in an unhandled `UnicodeEncodeError` traceback
where the contract promises one JSON document and exit 0.

The **silent** variant of the same root needs a name the legacy codec
*can* encode, which a Russian wiki also has — the entity page
`Böhm-Bawerk.md`. On a second vault holding only that page, HEAD `scan`
under `cp1252` exited **0** and wrote **382** bytes instead of 383, the
`ö` left as the single byte `0xF6` at offset 247: the output the skill
had just called successful was not valid UTF-8, and
`open(f, 'rb').read().decode('utf-8')` refused it with `invalid start
byte`. JSON is UTF-8 by definition (RFC 8259 §8.1). Writing the encoded
bytes to `sys.stdout.buffer` takes the locale out of the loop — after the
fix all three codecs produce byte-identical output (same md5) for all
four runs: 463 / 820 / 301 / 383 bytes, exit 0, empty stderr.

Only the sites that passed `ensure_ascii=False` were exposed: the ones
that kept the `json.dumps` default emit pure ASCII, which every codec a
caller can set encodes identically. `upsert-page` was measured at 178
bytes with one md5 under utf-8, ascii and cp1252, at HEAD and after, and
stays that way.

**B · a closed reader replaced the exit code.** An unflushed buffer on a
dead fd is flushed again while CPython shuts down; it prints `Exception
ignored while flushing sys.stdout` and **substitutes exit status 120**
for the code `main()` returned.

**Payload size is not the gate.** A reader that is already gone takes
EPIPE whatever the size: HEAD `scan` on the fixture vault — a
**463-byte** document, contract verdict 0 — piped into
`bash -c 'exit 0'` exited **120** with those two non-JSON stderr lines in
**10 runs out of 10**, and `lint` on the same vault (820 bytes, verdict
0) did the same 10/10.

Size only selects *which* wrong answer a **still-draining** reader gets,
and that is why no test may rest on it. Against `… | head -c 20` the same
463-byte `scan` is absorbed by the kernel and exits 0 — the defect is
invisible at that size. Sweeping a synthetic HEAD-shaped writer
(`print(json.dumps(…, indent=2, ensure_ascii=False))` then
`sys.exit(7)`):

* reader **already gone** — **120** at every size measured from 128 B
  through 129 620 B; from 135 020 B a raw `BrokenPipeError` traceback
  escapes instead, for exit **1**.
* reader **drains 20 bytes, then closes** — the declared 7 survives up to
  64 820 B; **120** from 70 220 B through 129 620 B; **1** from
  135 020 B.

This machine's pipe holds 65 536 bytes (measured by filling a fresh
`os.pipe()`), which is why the draining reader's first failure sits just
above 64 820 B — and why the already-gone reader has no threshold at all.

On a 2 600-page vault the real command is in the top band under both
reader shapes: `scan` (343 564 bytes, verdict 0) exits **1** with an
11-line traceback, 10 runs out of 10. All three bands are wrong in the
same way: the exit status stops describing the work. `write_json`
swallows the `BrokenPipeError` after pointing the fd at `/dev/null`, so
the caller's own `return <code>` is what the shell sees — measured 0 with
empty stderr for every case above, 10 runs each.

Deliberately NOT covered:

- **The bytes are not made identical across `ensure_ascii` settings.**
  `ensure_ascii` mirrors `json.dumps` and each call site keeps the value
  it already had, because `tests/test_r11_byte_identity.py` gates
  `scan` / `lint` / `classify-folder` stdout byte-for-byte. This module
  fixes *how* the bytes reach the fd, never *which* bytes they are.
- **Non-JSON stdout writing.** `_safety.write_text`'s `--dry-run` echo,
  `commands/ingest.py::_emit`'s human summary lines and `wiki_ops.py
  --version` still `print()` through the text layer, and the `--dry-run`
  echo therefore keeps defect A: measured, `upsert-page … --dry-run`
  under `PYTHONIOENCODING=ascii` exits 1 with a 14-line
  `UnicodeEncodeError` traceback and 0 bytes of the page it would have
  written — identically before and after this change. That channel is
  markdown for a human to read, not the JSON contract this module owns,
  and routing prose through a JSON writer would be a different change; it
  is left open, not fixed by accident.
- **stderr.** `_safety.die` and `commands/ingest.py::_json_error_envelope`
  are a separate channel with a separate (`backslashreplace`) failure
  mode; nothing here moves a record between channels.
- **Telling the caller output was truncated.** `write_json` returns
  `False` on a dead pipe, but no call site branches on it: a reader that
  closed the pipe is not there to be told, and `… | head` is expected to
  be silent. The return value exists so a future caller *can* care.

Stdlib-only; F1 layer, imports nothing from `wiki_ingest`.
Contract locked by `../tests/test__stdout.py`.
"""
from __future__ import annotations

import argparse
import atexit
import codecs
import json
import os
import sys
from typing import IO, Any


def _escape_lone_surrogates(text: str) -> str:
    """Replace unpaired surrogates (U+D800-DFFF) with their `\\udXXX` JSON
    escape.

    UTF-8 is the one thing these code points cannot be encoded as, and a
    vault produces them: POSIX decodes an undecodable filename byte that
    way (`surrogateescape`), and those filenames become `path` fields in
    `scan` / `lint` / `find` output. JSON carries them as escapes and a
    parser turns the escape back into the same character, so nothing is
    lost. `str.isascii()` short-circuits the common case, and the pass
    cannot fail twice — a lone surrogate is the only thing UTF-8 rejects,
    and none survives it.

    A no-op when `ensure_ascii=True`: `json.dumps` has already escaped
    them itself.
    """
    if text.isascii():
        return text
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        return text
    return "".join(
        f"\\u{ord(ch):04x}" if 0xD800 <= ord(ch) <= 0xDFFF else ch
        for ch in text
    )


def abandon_stdout(stream: IO[str] | None = None) -> None:
    """Point a dead stdout's file descriptor at `/dev/null`.

    Call this after a `BrokenPipeError`. Without it CPython flushes the
    same dead fd again while shutting down, prints `Exception ignored
    while flushing sys.stdout` on stderr and replaces the process exit
    status with 120 — measured above.

    Best-effort by design: a stream with no real fd (a test's `StringIO`,
    a wrapper's proxy object) and a `None` stream (fd 1 closed before the
    process started) have nothing to redirect and need nothing. Nothing
    raises out of here, and no descriptor is leaked on the way.
    """
    target = sys.stdout if stream is None else stream
    try:
        fd = target.fileno()
    except (AttributeError, OSError, ValueError):
        return
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        os.dup2(devnull, fd)
    except OSError:
        pass
    finally:
        os.close(devnull)


def write_json(
    payload: Any,
    *,
    indent: int | None = None,
    ensure_ascii: bool = True,
    stream: IO[str] | None = None,
) -> bool:
    """Write `payload` to stdout as one line-terminated JSON document.

    Drop-in for `print(json.dumps(payload, indent=…, ensure_ascii=…))`:
    the keyword defaults match `json.dumps`, and the trailing newline
    `print` supplied is written here instead. Bytes are unchanged for a
    given `(payload, indent, ensure_ascii)` — deliberately, see the module
    docstring.

    Serialisation is one-shot, not streamed: an unserialisable payload
    raises with **nothing** written, rather than leaving half a document
    on the wire the way `json.dump(obj, sys.stdout)` does.

    stdout receives LF on every platform, Windows included — bytes written
    to `sys.stdout.buffer` bypass the text layer's newline translation.
    Only the terminator is affected; a newline inside a JSON string is
    always the `\\n` escape.

    A `stream` with no `.buffer` (a test's `redirect_stdout(StringIO())`,
    a wrapper's proxy) keeps the text path, and the caller owns the
    encoding there. The surrogate escape runs before that branch so both
    paths carry the identical value.

    Returns `True` when the document reached the stream, `False` when
    there was no reader left to take it — the pipe was already closed, or
    fd 1 was closed before the process started (`cmd >&-`, where CPython
    leaves `sys.stdout` as `None` and `print()` is a silent no-op). In
    both cases the exception is swallowed — on a dead pipe after pointing
    the fd at `/dev/null` — so the caller's own `return <exit code>` is
    what the shell observes: a missing reader never rewrites a verdict.
    Every other write error (`ENOSPC`, a closed file object) still
    propagates.
    """
    text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii)
    if not ensure_ascii:
        text = _escape_lone_surrogates(text)
    text += "\n"
    target = sys.stdout if stream is None else stream
    if target is None:
        # fd 1 closed at exec time. `print()` was a silent no-op here, and
        # every call site returns its exit code straight after this call;
        # raising would turn a command that exited 0 into a traceback.
        return False
    buffer = getattr(target, "buffer", None)
    try:
        if buffer is None:
            target.write(text)
            target.flush()
            return True
        # Anything already queued on the text layer must reach the fd
        # before our bytes do, or the two layers interleave out of order.
        target.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
        return True
    except BrokenPipeError:
        abandon_stdout(target)
        return False


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

