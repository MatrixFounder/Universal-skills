"""Centralised, ``.env``-backed configuration for transcript-fetcher.

Mirrors the **`html` skill's** config pattern (skill-local `.env` encapsulation,
TASK 027) so settings — endpoints, model ids, tool paths, secrets — travel WITH
the skill and any caller picks them up with zero awareness, WITHOUT polluting the
machine-global environment. **No endpoint, model id, or external tool name is
hard-coded in a backend** — point the cloud backend at Groq / a self-hosted
whisper server / an internal gateway purely through config.

Resolution order for any key (first match wins):

  1. an explicit CLI flag / function argument (callers, e.g. ``--asr-model``);
  2. a real process **environment variable**;
  3. a key in the skill-local ``.env`` (loaded into ``os.environ`` at the entry
     point by :func:`load_skill_env`);
  4. the built-in default in the typed accessor.

Env-var prefix is ``TRANSCRIPT_FETCHER_`` (consistent with the pre-existing
``TRANSCRIPT_FETCHER_DEBUG`` / ``TRANSCRIPT_FETCHER_E2E``). The conventional
unprefixed ``OPENAI_API_KEY`` is also honoured as a fallback.

SECURE SECRET STORAGE (mandatory — the ``.env`` may hold an API key):
  * The ``.env`` is loaded ONLY from the CLI entry point, never on import.
  * A ``.env`` that is a **symlink** or is **group/world-accessible** is
    **refused** (require ``chmod 600``) — secrets never load from a file other
    users can read.
  * **Process env always wins** — a caller's value is never overridden by ``.env``.
  * ``.env`` is git-ignored (the skill-root ``.gitignore`` covers both
    ``.env`` and ``scripts/.env``); only ``.env.example`` (placeholders, no
    secrets) is committed.
  * Secrets are passed to the network backend in an HTTP ``Authorization`` header
    only — **never on argv** and **never logged** (the debug logger prints stage
    names, never config values). Opt out of dotenv entirely with
    ``TRANSCRIPT_FETCHER_NO_DOTENV=1``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

PREFIX = "TRANSCRIPT_FETCHER_"
_TRUTHY = {"1", "true", "yes", "on"}

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS_DIR.parent
# Candidate `.env` locations: skill root (html parity) AND scripts/ (the "в
# скриптах скила" interpretation). Both are honoured; skill-root takes priority.
_ENV_CANDIDATES = (_SKILL_DIR / ".env", _SCRIPTS_DIR / ".env")


# --------------------------------------------------------------------- #
# Thin accessor over TRANSCRIPT_FETCHER_<suffix> (mirrors html `_env`)
# --------------------------------------------------------------------- #
def env(suffix: str, *, default: Optional[str] = None) -> Optional[str]:
    """Read ``TRANSCRIPT_FETCHER_<suffix>`` from the env (``default`` if unset/empty)."""
    value = os.environ.get(PREFIX + suffix)
    return value if value not in (None, "") else default


def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in _TRUTHY


# --------------------------------------------------------------------- #
# Skill-local `.env` bootstrap (secure)
# --------------------------------------------------------------------- #
def load_skill_env(paths: Optional[tuple[Path, ...]] = None) -> None:
    """Load the skill-local ``.env`` file(s) into ``os.environ`` (secure).

    Called once from the CLI entry point BEFORE any flag/env read, so importing
    the package (e.g. in tests) never triggers it. Never raises — a broken config
    must not break a run.
    """
    if _is_truthy(os.environ.get(PREFIX + "NO_DOTENV")):
        return
    for path in (paths if paths is not None else _ENV_CANDIDATES):
        _load_one(path)


def _load_one(path: Path) -> None:
    try:
        if path.is_symlink() or not path.is_file():
            return
        # Secrets-safe: refuse a group/world-accessible secrets file.
        if path.stat().st_mode & 0o077:
            sys.stderr.write(
                f"transcript-fetcher: ignoring {path} "
                "(group/world-accessible — chmod 600 to enable)\n"
            )
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if key and key not in os.environ:  # process env wins
                os.environ[key] = _dotenv_value(val)
    except OSError:
        return  # config must never break a run


def _dotenv_value(val: str) -> str:
    """Parse a `.env` RHS like shell sourcing: quoted value kept verbatim;
    unquoted value drops a trailing ``#`` comment after whitespace, then stripped."""
    val = val.strip()
    if val[:1] in ("'", '"'):
        quote = val[0]
        end = val.find(quote, 1)
        return val[1:end] if end != -1 else val[1:]
    for sep in (" #", "\t#"):
        i = val.find(sep)
        if i != -1:
            val = val[:i]
    return val.strip()


# --------------------------------------------------------------------- #
# Typed accessors — the ONLY thing backends should call
# --------------------------------------------------------------------- #
def openai_api_key() -> Optional[str]:
    """Bearer token for the transcription endpoint.

    ``TRANSCRIPT_FETCHER_OPENAI_API_KEY`` first, then the conventional
    ``OPENAI_API_KEY``. For a keyless OpenAI-compatible server, leave both unset
    (the cloud backend then simply stays unavailable unless a key is provided).
    """
    return env("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or None


def openai_base_url() -> str:
    return (env("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def openai_transcribe_endpoint() -> str:
    """Full transcription URL — the single flexibility seam for any OpenAI-compatible
    server. A complete override (``OPENAI_TRANSCRIBE_ENDPOINT``) is used verbatim;
    else ``<base_url><transcribe_path>``."""
    full = env("OPENAI_TRANSCRIBE_ENDPOINT")
    if full:
        return full
    path = env("OPENAI_TRANSCRIBE_PATH") or "/audio/transcriptions"
    if not path.startswith("/"):
        path = "/" + path
    return openai_base_url() + path


def openai_model(default: Optional[str] = None) -> str:
    return env("OPENAI_MODEL") or default or "whisper-1"


def openai_max_upload_bytes() -> int:
    """Max audio bytes to upload to the cloud backend (0 = unbounded).

    Default 25 MiB (the OpenAI Whisper API limit). Raise it via
    ``TRANSCRIPT_FETCHER_OPENAI_MAX_UPLOAD_MB`` for an OpenAI-compatible server
    with a larger limit, or set it to ``0`` to disable the client-side check.
    """
    raw = env("OPENAI_MAX_UPLOAD_MB")
    if raw and raw.strip().lstrip("-").isdigit():
        mb = int(raw.strip())
        return max(0, mb) * 1024 * 1024
    return 25 * 1024 * 1024


def tool_bin(key: str, default: str) -> str:
    """Resolve an external tool's binary name/path, e.g. ``tool_bin("MW", "mw")`` →
    ``TRANSCRIPT_FETCHER_MW_BIN`` or ``"mw"`` — point at a non-standard install path
    without code changes."""
    return env(key + "_BIN") or default


def ffmpeg_bin() -> str:
    return tool_bin("FFMPEG", "ffmpeg")


def asr_timeout_sec(default: int) -> int:
    raw = env("ASR_TIMEOUT_SEC")
    return int(raw) if raw and raw.strip().isdigit() else default


def asr_allow_cloud_default() -> bool:
    """`.env`/env default for the cloud opt-in (CLI ``--asr-allow-cloud`` still wins)."""
    return _is_truthy(env("ASR_ALLOW_CLOUD"))


def asr_model_default() -> Optional[str]:
    return env("ASR_MODEL")
