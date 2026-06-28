"""MacWhisper CLI ASR backend (primary).

MacWhisper ships a ``mw`` command (verified contract, ``mw transcribe --help``)::

    mw transcribe <file> [--model <engine:model-id>] [--persist] [--stream]

* ``<file>`` may be **audio or video** — so a downloaded muxed media file works
  directly, no ffmpeg audio-extraction step needed.
* On completion it prints the **whole transcript to stdout** (we deliberately do
  NOT pass ``--stream``).
* We deliberately do NOT pass ``--persist`` — transcription must not pollute the
  user's MacWhisper history as a side effect.
* ``--model`` is optional; omitted, MacWhisper uses the user's currently selected
  model (honest-scope HS-4 in arch-016).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import _config as cfg

from ._base import ASRBackend, ASRError, ASRResult, stderr_tail


class MacWhisperBackend(ASRBackend):
    name = "macwhisper"

    def _bin(self) -> str:
        return cfg.tool_bin("MW", "mw")

    def available(self) -> bool:
        return shutil.which(self._bin()) is not None

    def transcribe(
        self, audio_path: Path, *, lang: Optional[str] = None
    ) -> ASRResult:
        argv = [self._bin(), "transcribe", str(audio_path)]
        if self.model:
            argv += ["--model", self.model]
        # MacWhisper has no documented language flag in the `transcribe`
        # subcommand; language is model/auto-detected. `lang` is accepted for
        # interface symmetry but not forwarded.
        proc = self._run(argv)
        text = (proc.stdout or "").strip()
        if proc.returncode != 0:
            tail = stderr_tail(proc.stderr)
            raise ASRError(
                f"macwhisper: `mw transcribe` exited {proc.returncode}"
                + (f": {tail}" if tail else "")
            )
        if not text:
            tail = stderr_tail(proc.stderr)
            raise ASRError(
                "macwhisper: produced empty transcript"
                + (f" ({tail})" if tail else "")
            )
        return ASRResult(
            text=text,
            backend_name=self.name,
            language=lang,
            model=self.model,
        )
