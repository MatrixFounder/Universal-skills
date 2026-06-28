"""OpenAI Whisper CLI ASR backend (``whisper`` on PATH).

Contract::

    whisper <file> --model <m> --output_format txt --output_dir <dir> \
            --language <lang> --task transcribe

The CLI writes ``<stem>.txt`` into ``--output_dir`` (and echoes to stdout). The
upstream ``whisper`` package decodes audio with **ffmpeg**, so availability is
gated on both ``whisper`` and ``ffmpeg`` being present — otherwise the backend
would be selected only to fail, instead of cleanly stepping aside for the next
one in the chain.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import _config as cfg

from ._base import ASRBackend, ASRError, ASRResult, stderr_tail


class WhisperCLIBackend(ASRBackend):
    name = "whisper-cli"

    def _bin(self) -> str:
        return cfg.tool_bin("WHISPER", "whisper")

    def available(self) -> bool:
        return (
            shutil.which(self._bin()) is not None
            and shutil.which(cfg.ffmpeg_bin()) is not None
        )

    def transcribe(
        self, audio_path: Path, *, lang: Optional[str] = None
    ) -> ASRResult:
        out_dir = audio_path.parent
        stem = audio_path.stem
        argv = [
            self._bin(),
            str(audio_path),
            "--output_format", "txt",
            "--output_dir", str(out_dir),
            "--task", "transcribe",
        ]
        if self.model:
            argv += ["--model", self.model]
        if lang:
            argv += ["--language", lang]
        proc = self._run(argv)
        if proc.returncode != 0:
            tail = stderr_tail(proc.stderr)
            raise ASRError(
                f"whisper-cli: exited {proc.returncode}"
                + (f": {tail}" if tail else "")
            )
        txt_path = out_dir / f"{stem}.txt"
        text = ""
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            # Fall back to stdout if the file wasn't found/empty.
            text = (proc.stdout or "").strip()
        if not text:
            raise ASRError("whisper-cli: produced empty transcript")
        return ASRResult(
            text=text, backend_name=self.name, language=lang, model=self.model
        )
