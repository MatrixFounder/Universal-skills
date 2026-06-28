"""ASR backend abstraction — the speech-to-text half of transcript-fetcher.

This is the Python equivalent of the spec's TypeScript ``TranscriptProvider``
interface. An :class:`ASRBackend` turns an *audio (or video) file* into text.
It is deliberately **orthogonal** to the source-adapter abstraction in
``sources/`` — a source adapter (youtube/vimeo/skool/x) knows how to fetch a
platform's media; an ASR backend knows how to transcribe a local file. Any
source can consume any backend.

Design rules (mirrors the deferred-import discipline of ``sources/youtube.py``):

* ``available()`` is a **cheap, side-effect-free probe** — ``shutil.which`` for
  a CLI tool, or an env/flag check for the cloud backend. No network calls and
  no heavy imports at module import time, so unit tests for routing never need
  a real engine installed.
* ``transcribe()`` raises :class:`ASRError` for an engine-level failure
  (engine present but ran badly / produced empty output). The registry then
  falls through to the next available backend.
* Adding a backend is a new file + one REGISTRY entry — **zero** edits to the X
  provider or the CLI core.
"""
from __future__ import annotations

import abc
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Generous default: local transcription of a long broadcast/Space can take
# several minutes. Callers may override via ``--asr-timeout-sec``.
DEFAULT_ASR_TIMEOUT_SEC = 1800


@dataclass
class ASRResult:
    """Result of transcribing one media file."""

    text: str
    backend_name: str  # "macwhisper" | "whisper-cli" | "whisper-cpp" | "openai-api"
    language: Optional[str] = None
    model: Optional[str] = None


class ASRError(RuntimeError):
    """Engine-level failure: the backend was available but failed to produce text.

    The registry treats this as recoverable — it falls through to the next
    available backend. If *every* available backend raises, the caller surfaces
    a ``TranscriptFetchError`` (exit 3). This is distinct from
    ``MissingDependencyError`` (exit 7), which means no backend was available
    in the first place.
    """


class ASRBackend(abc.ABC):
    """Pluggable speech-to-text engine.

    Concrete subclasses set the class attribute :attr:`name` and implement
    :meth:`available` and :meth:`transcribe`.
    """

    name: str = "base"

    def __init__(
        self,
        *,
        allow_cloud: bool = False,
        model: Optional[str] = None,
        timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
    ) -> None:
        self.allow_cloud = allow_cloud
        self.model = model
        self.timeout_sec = timeout_sec

    @abc.abstractmethod
    def available(self) -> bool:
        """Return True iff this backend can run on the current machine.

        Must be cheap and side-effect-free (no network, no heavy import).
        """

    @abc.abstractmethod
    def transcribe(
        self, audio_path: Path, *, lang: Optional[str] = None
    ) -> ASRResult:
        """Transcribe ``audio_path`` to text.

        Raises:
            ASRError: if the engine ran but failed or produced empty output.
        """

    # ----------------------------------------------------------------- #
    # Shared subprocess helper (argv-array form — never a shell string)
    # ----------------------------------------------------------------- #
    def _run(
        self, argv: list[str], *, timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Run an external command, returning the CompletedProcess.

        Always uses the argv-array form (no ``shell=True``) so a crafted path
        cannot inject shell metacharacters. Wraps the two expected process
        failures into :class:`ASRError` with an actionable message.
        """
        try:
            return subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout if timeout is not None else self.timeout_sec,
            )
        except FileNotFoundError as e:  # tool vanished between probe and run
            raise ASRError(f"{self.name}: executable not found: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise ASRError(
                f"{self.name}: timed out after {e.timeout}s transcribing "
                f"{audio_name(argv)}"
            ) from e


def stderr_tail(stderr: Optional[str], n_lines: int = 3) -> str:
    """Last ``n`` non-empty stderr lines joined by ' | ' (for error messages)."""
    if not stderr:
        return ""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    return " | ".join(lines[-n_lines:])


def audio_name(argv: list[str]) -> str:
    """Best-effort: the last argv token that looks like a path (for messages)."""
    for tok in reversed(argv):
        if "/" in tok or tok.endswith((".m4a", ".mp4", ".wav", ".ts", ".mp3")):
            return tok
    return argv[-1] if argv else "<audio>"
