"""OpenAI Whisper API ASR backend (opt-in cloud, lowest priority).

This is the **only** backend that egresses audio off the machine, so it is
strictly **opt-in**: ``available()`` returns True only when BOTH the
``--asr-allow-cloud`` flag was passed (``self.allow_cloud``) AND an
``OPENAI_API_KEY`` is present in the environment. It is never auto-selected
otherwise (honest-scope HS-3 in arch-016).

Implemented with **stdlib only** (``urllib``) — no ``openai``/``requests``
dependency is added (AC-6: yt-dlp stays the sole pip dep). The audio is sent as
``multipart/form-data`` to the transcription endpoint with
``response_format=text`` so the response body is the plain transcript.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Optional
from urllib import error as urlerror
from urllib import parse as urlparse_mod
from urllib import request as urlrequest

import _config as cfg

from ._base import ASRBackend, ASRError, ASRResult

# A transcription response is plain text (bounded by audio duration). Cap the
# success-path read so a misconfigured / hostile endpoint can't OOM the client.
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024

_MIME_BY_EXT = {
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ts": "video/mp2t",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
}


class OpenAIWhisperBackend(ASRBackend):
    name = "openai-api"

    def available(self) -> bool:
        return bool(self.allow_cloud) and bool(cfg.openai_api_key())

    def transcribe(
        self, audio_path: Path, *, lang: Optional[str] = None
    ) -> ASRResult:
        api_key = cfg.openai_api_key()
        if not api_key:  # pragma: no cover — guarded by available()
            raise ASRError("openai-api: no API key (set OPENAI_API_KEY)")

        endpoint = cfg.openai_transcribe_endpoint()
        # Warn (don't block — a local http server may be intentional) if the key
        # would travel in cleartext to a non-loopback http endpoint.
        _parsed = urlparse_mod.urlparse(endpoint)
        if _parsed.scheme != "https" and _parsed.hostname not in (
            "localhost", "127.0.0.1", "::1",
        ):
            sys.stderr.write(
                "transcript-fetcher: WARNING — cloud ASR endpoint is not https "
                f"({endpoint}); the API key would be sent in cleartext.\n"
            )
        model = self.model or cfg.openai_model()

        # Reject CRLF in any value that lands in the multipart body — a
        # crafted --asr-model / --lang could otherwise inject part headers /
        # corrupt the encoding (defence at the encoder boundary).
        for label, value in (("model", model), ("language", lang),
                             ("filename", audio_path.name)):
            if value and ("\r" in str(value) or "\n" in str(value)):
                raise ASRError(f"openai-api: illegal newline in {label!r}")

        # Fail fast on an over-limit file instead of buffering it then having
        # the server reject it. The cap is configurable (0 = unbounded) for
        # OpenAI-compatible servers with a different limit.
        cap = cfg.openai_max_upload_bytes()
        try:
            size = audio_path.stat().st_size
        except OSError as e:
            raise ASRError(f"openai-api: cannot stat audio: {e}") from e
        if cap and size > cap:
            raise ASRError(
                f"openai-api: audio is {size // (1024 * 1024)} MiB, exceeds the "
                f"{cap // (1024 * 1024)} MiB cloud upload limit — use a local "
                "backend (MacWhisper/whisper) or raise "
                "TRANSCRIPT_FETCHER_OPENAI_MAX_UPLOAD_MB"
            )
        try:
            audio_bytes = audio_path.read_bytes()
        except OSError as e:
            raise ASRError(f"openai-api: cannot read audio: {e}") from e

        fields = {"model": model, "response_format": "text"}
        if lang:
            fields["language"] = lang
        mime = _MIME_BY_EXT.get(audio_path.suffix.lower(), "application/octet-stream")
        body, content_type = _encode_multipart(
            fields, file_field="file", filename=audio_path.name,
            file_bytes=audio_bytes, file_mime=mime,
        )

        req = urlrequest.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": content_type,
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_sec) as resp:
                # Bound the response read — a transcript is small; a
                # misconfigured/hostile server must not OOM us.
                raw = resp.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise ASRError(
                        "openai-api: response exceeded "
                        f"{_MAX_RESPONSE_BYTES // (1024 * 1024)} MiB cap"
                    )
                text = raw.decode("utf-8", errors="replace").strip()
        except urlerror.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise ASRError(
                f"openai-api: HTTP {e.code} {e.reason}"
                + (f" — {detail}" if detail else "")
            ) from e
        except (urlerror.URLError, TimeoutError) as e:
            raise ASRError(f"openai-api: request failed: {e}") from e

        if not text:
            raise ASRError("openai-api: empty transcript in response")
        return ASRResult(
            text=text, backend_name=self.name, language=lang, model=model
        )


def _encode_multipart(
    fields: dict,
    *,
    file_field: str,
    filename: str,
    file_bytes: bytes,
    file_mime: str,
) -> tuple[bytes, str]:
    """Encode ``multipart/form-data`` with stdlib only. Returns (body, content_type)."""
    boundary = f"----transcriptfetcher{uuid.uuid4().hex}"
    crlf = b"\r\n"
    out: list[bytes] = []
    for key, value in fields.items():
        out.append(b"--" + boundary.encode())
        out.append(
            f'Content-Disposition: form-data; name="{key}"'.encode()
        )
        out.append(b"")
        out.append(str(value).encode("utf-8"))
    out.append(b"--" + boundary.encode())
    out.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"'.encode()
    )
    out.append(f"Content-Type: {file_mime}".encode())
    out.append(b"")
    # Assemble with ONE join so the (potentially large) audio payload is copied
    # exactly once — avoid `body = ... + file_bytes` followed by a non-in-place
    # `body +=`, which transiently holds 2-3 copies of the audio in memory.
    prefix = crlf.join(out) + crlf
    suffix = crlf + b"--" + boundary.encode() + b"--" + crlf
    body = b"".join((prefix, file_bytes, suffix))
    return body, f"multipart/form-data; boundary={boundary}"
