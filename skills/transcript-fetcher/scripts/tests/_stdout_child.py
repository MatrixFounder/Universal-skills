"""Child process for the stdout-channel tests — NOT collected by ``discover``.

The stdout contract can only be exercised against a **real file descriptor**:
the locale codec is chosen when the interpreter builds ``sys.stdout``, and a
broken pipe needs a pipe. Both are out of reach of an in-process test that
patches ``sys.stdout`` with a ``StringIO`` (which is why the pre-existing
``test_fetch_cli`` batch tests stayed green against the defect).

So the tests spawn this script with the skill's own venv interpreter, a chosen
``PYTHONIOENCODING``/``LC_ALL``, and — for the pipe cases — an fd 1 whose reader
is already gone. It stubs ``fetch._fetch_one`` (no network, no ASR), runs
``fetch.main`` for real, and reports the number of stub calls on **stderr** so
the parent can tell "the batch kept going" from "the batch died on record 1".

Usage: ``_stdout_child.py MODE TARGET OUT`` — for the batch modes ``TARGET`` is
a batch file and ``OUT`` a directory; for ``single`` they are one URL and one
output file.

Modes:
  ``single``    — the single-URL path (one stat record, non-ASCII).
  ``ok``        — every URL succeeds; the stat record carries non-ASCII text
                  (an em dash and Cyrillic), which is what an ASCII locale
                  used to choke on.
  ``err``       — every URL raises ``MissingDependencyError`` with a non-ASCII
                  remediation, so the record written from inside an ``except``
                  block is the non-encodable one.
  ``big``       — success records padded to ``TF_PAD_BYTES`` (default 360 KB),
                  well past this machine's pipe buffer, so a dead reader is
                  guaranteed to surface as ``BrokenPipeError`` on the write
                  rather than only at interpreter shutdown.
  ``surrogate`` — the stat's ``output_path`` holds a lone surrogate, the way a
                  ``--out`` path with undecodable bytes reaches it through
                  POSIX ``surrogateescape``.

Stderr is therefore NOT pure envelope in these runs: the last line is always
``CALLS=<n>``. Tests strip it before parsing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import fetch  # noqa: E402
from sources._stat import MissingDependencyError  # noqa: E402

# An em dash is the exact character measured in the original failures, and the
# Cyrillic proves the fix is not "ensure_ascii=True with extra steps".
NON_ASCII_TITLE = "Лекция 1 — введение"
NON_ASCII_REMEDIATION = "ffmpeg — brew install ffmpeg"

_calls = 0


def _stat_for(url: str, out_path: Path) -> dict:
    record = {
        "v": 1,
        "source": "youtube",
        "url": url,
        "video_id": out_path.stem,
        "output_path": str(out_path),
        "title": NON_ASCII_TITLE,
        "chosen_track_kind": "manual",
        "chosen_track_lang": "ru",
        "char_count": 42,
        "speaker_turn_count": 0,
    }
    pad = int(os.environ.get("TF_PAD_BYTES", "0"))
    if pad:
        record["transcript_preview"] = "x" * pad
    return record


def main() -> int:
    mode, target, out = sys.argv[1], sys.argv[2], sys.argv[3]

    def _stub(url: str, out_path: Path, **_kw) -> dict:
        global _calls
        _calls += 1
        # The real _fetch_one writes the transcript before returning; keep that
        # ordering so "the file is on disk but the record never arrived" is
        # reproducible.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("transcript\n", encoding="utf-8")
        if mode == "err":
            raise MissingDependencyError(
                "no ASR backend available",
                remediation=NON_ASCII_REMEDIATION,
            )
        stat = _stat_for(url, out_path)
        if mode == "surrogate":
            stat["output_path"] = str(out_path) + "\udcff"
        return stat

    fetch._fetch_one = _stub  # type: ignore[assignment]
    if mode == "single":
        argv = [target, "--out", out]
    else:
        argv = ["--batch", target, "--out-dir", out]
    try:
        rc = fetch.main(argv)
    finally:
        # stderr, never stdout: stdout is the channel under test.
        sys.stderr.write(f"CALLS={_calls}\n")
        sys.stderr.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main())
