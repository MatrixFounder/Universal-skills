"""whisper.cpp ASR backend (``whisper-cli`` / legacy ``main``).

whisper.cpp consumes a **16 kHz mono WAV**. We therefore require **ffmpeg** to
transcode the downloaded media first; without it the backend is unavailable
(``available() -> False``) rather than crashing mid-run — honest-scope HS-2 in
arch-016.

Contract (newer builds expose ``whisper-cli``; older ones ``main``)::

    ffmpeg -i <media> -ar 16000 -ac 1 -f wav <tmp>.wav
    whisper-cli -m <model.bin> -f <tmp>.wav -otxt -of <stem> -nt

``-otxt -of <stem>`` writes ``<stem>.txt``. A model file is required; we forward
``--asr-model`` as the ``-m`` path. Without a model path the backend reports
unavailable (it cannot guess where the user keeps ``ggml-*.bin``).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import _config as cfg

from ._base import ASRBackend, ASRError, ASRResult, stderr_tail


def _whisper_cpp_bin() -> Optional[str]:
    # Honour an explicit override first, then the conventional names.
    override = cfg.tool_bin("WHISPER_CPP", "")
    candidates = ([override] if override else []) + ["whisper-cli", "main"]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    return None


class WhisperCppBackend(ASRBackend):
    name = "whisper-cpp"

    def available(self) -> bool:
        # Needs the binary, ffmpeg (to make 16 kHz wav), AND a model path
        # (whisper.cpp cannot auto-discover ggml models).
        return (
            _whisper_cpp_bin() is not None
            and shutil.which(cfg.ffmpeg_bin()) is not None
            and bool(self.model)
        )

    def transcribe(
        self, audio_path: Path, *, lang: Optional[str] = None
    ) -> ASRResult:
        binary = _whisper_cpp_bin()
        if binary is None:  # pragma: no cover — guarded by available()
            raise ASRError("whisper-cpp: no whisper-cli/main on PATH")
        if not self.model:  # pragma: no cover — guarded by available()
            raise ASRError("whisper-cpp: requires --asr-model <path/to/ggml.bin>")

        wav_path = audio_path.parent / f"{audio_path.stem}.16k.wav"
        ff = self._run(
            [
                cfg.ffmpeg_bin(), "-y", "-i", str(audio_path),
                "-ar", "16000", "-ac", "1", "-f", "wav", str(wav_path),
            ]
        )
        if ff.returncode != 0 or not wav_path.exists():
            tail = stderr_tail(ff.stderr)
            raise ASRError(
                "whisper-cpp: ffmpeg failed to produce 16 kHz wav"
                + (f": {tail}" if tail else "")
            )

        out_stem = audio_path.parent / audio_path.stem
        argv = [
            binary, "-m", self.model, "-f", str(wav_path),
            "-otxt", "-of", str(out_stem), "-nt",
        ]
        if lang:
            argv += ["-l", lang]
        proc = self._run(argv)
        if proc.returncode != 0:
            tail = stderr_tail(proc.stderr)
            raise ASRError(
                f"whisper-cpp: exited {proc.returncode}"
                + (f": {tail}" if tail else "")
            )
        txt_path = Path(str(out_stem) + ".txt")
        text = ""
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            raise ASRError("whisper-cpp: produced empty transcript")
        return ASRResult(
            text=text, backend_name=self.name, language=lang, model=self.model
        )
