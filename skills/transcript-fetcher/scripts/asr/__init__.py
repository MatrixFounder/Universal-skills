"""Pluggable ASR (speech-to-text) backends for transcript-fetcher.

Public surface:

* :class:`ASRBackend`, :class:`ASRResult`, :class:`ASRError` — the interface.
* :data:`REGISTRY` — backend classes in **priority order**.
* :func:`select_backend` — first available backend (or ``None``).
* :func:`transcribe_with_fallback` — try available backends in order, returning
  the first success; raise on dependency-absence vs all-failed.

Priority order (per TASK 026 B2): MacWhisper → Whisper CLI → whisper.cpp →
OpenAI Whisper API (cloud, opt-in last). Adding a backend = append its class to
:data:`REGISTRY`; **no** changes to the X provider or CLI core are required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sources._stat import MissingDependencyError, TranscriptFetchError

from ._base import (
    DEFAULT_ASR_TIMEOUT_SEC,
    ASRBackend,
    ASRError,
    ASRResult,
)
from .macwhisper import MacWhisperBackend
from .openai_api import OpenAIWhisperBackend
from .whisper_cli import WhisperCLIBackend
from .whisper_cpp import WhisperCppBackend

# Priority-ordered backend classes. Order IS the fallback chain.
REGISTRY: tuple[type[ASRBackend], ...] = (
    MacWhisperBackend,
    WhisperCLIBackend,
    WhisperCppBackend,
    OpenAIWhisperBackend,  # opt-in; available() only when allow_cloud + key
)


def build_backends(
    *,
    allow_cloud: bool = False,
    model: Optional[str] = None,
    timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
) -> list[ASRBackend]:
    """Instantiate every registered backend in priority order."""
    return [
        cls(allow_cloud=allow_cloud, model=model, timeout_sec=timeout_sec)
        for cls in REGISTRY
    ]


def available_backends(backends: list[ASRBackend]) -> list[ASRBackend]:
    """Filter to the backends whose ``available()`` probe passes."""
    return [b for b in backends if b.available()]


def select_backend(
    *,
    allow_cloud: bool = False,
    model: Optional[str] = None,
    timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
) -> Optional[ASRBackend]:
    """Return the highest-priority available backend, or ``None`` if none are."""
    for b in build_backends(
        allow_cloud=allow_cloud, model=model, timeout_sec=timeout_sec
    ):
        if b.available():
            return b
    return None


def _remediation(allow_cloud: bool) -> str:
    hint = (
        "Install one of: MacWhisper (`mw`), OpenAI Whisper (`whisper` + ffmpeg), "
        "or whisper.cpp (`whisper-cli`/`main` + ffmpeg + --asr-model)."
    )
    if not allow_cloud:
        hint += (
            " Or enable the cloud backend with `--asr-allow-cloud` and set "
            "`OPENAI_API_KEY`."
        )
    return hint


def transcribe_with_fallback(
    audio_path: Path,
    *,
    lang: Optional[str] = None,
    allow_cloud: bool = False,
    model: Optional[str] = None,
    timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
    log: Optional[Callable[[str], None]] = None,
) -> ASRResult:
    """Transcribe ``audio_path``, falling through the priority chain.

    Args:
        audio_path: Local media file (audio or video) to transcribe.
        lang: Optional language hint forwarded to the backend.
        allow_cloud: Permit the opt-in OpenAI Whisper API backend.
        model: Optional model id forwarded to the chosen backend.
        timeout_sec: Per-backend transcription timeout.
        log: Optional callable for debug stage lines (e.g. "Using MacWhisper").

    Returns:
        The first successful :class:`ASRResult`.

    Raises:
        MissingDependencyError: No ASR backend is available at all (exit 7).
        TranscriptFetchError: Every available backend ran but failed (exit 3).
    """
    backends = build_backends(
        allow_cloud=allow_cloud, model=model, timeout_sec=timeout_sec
    )
    usable = available_backends(backends)
    if not usable:
        raise MissingDependencyError(
            "No ASR backend is available to transcribe caption-less media.",
            remediation=_remediation(allow_cloud),
        )

    errors: list[str] = []
    for backend in usable:
        if log is not None:
            log(f"Using {_human_name(backend.name)}")
        try:
            return backend.transcribe(audio_path, lang=lang)
        except ASRError as e:
            errors.append(f"{backend.name}: {e}")
            if log is not None:
                log(f"{backend.name} failed, trying next backend")
            continue

    raise TranscriptFetchError(
        "All available ASR backends failed: " + " | ".join(errors)
    )


def _human_name(name: str) -> str:
    return {
        "macwhisper": "MacWhisper",
        "whisper-cli": "Whisper CLI",
        "whisper-cpp": "whisper.cpp",
        "openai-api": "OpenAI Whisper API",
    }.get(name, name)


__all__ = (
    "ASRBackend",
    "ASRError",
    "ASRResult",
    "DEFAULT_ASR_TIMEOUT_SEC",
    "REGISTRY",
    "available_backends",
    "build_backends",
    "select_backend",
    "transcribe_with_fallback",
)
