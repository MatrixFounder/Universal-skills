"""Multi-format caption → plain-text dispatch (VTT, SRT, TTML/DFXP).

The X adapter (and any future yt-dlp source) asks yt-dlp for a *preference list*
of subtitle formats (``vtt/srt/ttml/best``) instead of VTT-only, so a track that
a source serves only as SRT or TTML is no longer treated as absent → ASR
(closes TF-X-4). This module turns whichever text caption file came back into the
same clean prose the VTT path produces, by **reusing** the battle-tested VTT
machinery in :mod:`sources._vtt_to_text`:

* **SRT** is WebVTT with comma decimal separators and no header — normalise the
  two and feed it straight through the VTT parser (all the rolling-caption
  dedup, ``>>`` turn handling and codec fallback come for free).
* **TTML/DFXP** is XML — extract ``<p>`` text with the stdlib
  :mod:`xml.etree.ElementTree`, mapping ``<br/>`` to a space and joining cues
  with newlines.

Security: TTML is parsed XML from a (semi-trusted) remote caption track. A
``<!DOCTYPE``/``<!ENTITY`` declaration is **refused outright** before parsing —
this neutralises XXE and the billion-laughs entity-expansion DoS with no
``defusedxml`` dependency — and the input is size-capped. A refusal raises
``ValueError``, which the adapter records as a note and falls through to ASR
(never a crash, never a silent empty).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ._vtt_to_text import (
    _decode_with_fallback,
    vtt_file_to_plain_meta,
    vtt_text_to_plain,
)

# yt-dlp file extensions we know how to turn into text. ``best`` in the format
# request may still grab something else (e.g. a YouTube ``srv3``); the finder
# only claims these, so an unparseable format is treated as "no caption".
SUPPORTED_CAPTION_EXTS = ("vtt", "srt", "ttml", "dfxp", "xml")

# Cap the XML we will parse (caption files are tiny; a multi-MB "caption" is an
# attack or a mistake). 16 MiB is generous for any real subtitle track.
_MAX_TTML_BYTES = 16 * 1024 * 1024

# SRT timestamps use a comma decimal separator: ``00:00:01,000``. VTT (and the
# shared cue parser's ``TS_RE``) want a dot. Match only inside a timecode so we
# never touch comma-containing caption text.
_SRT_TS_RE = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_DTD_RE = re.compile(r"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)


def captions_file_to_plain_meta(path: Path, fmt: str | None = None) -> tuple[str, str]:
    """Convert a caption file to ``(plain_text, codec_name)``, format-aware.

    ``fmt`` (the lowercased extension) selects the parser; when ``None`` it is
    taken from the file suffix. Unknown formats fall back to the VTT parser
    (the most permissive). Mirrors :func:`vtt_file_to_plain_meta`'s return
    contract so the X adapter's caption branch is format-agnostic.
    """
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    if fmt == "srt":
        return srt_file_to_plain_meta(path)
    if fmt in ("ttml", "dfxp", "xml"):
        return ttml_file_to_plain_meta(path)
    # vtt (and anything else we let through) → the VTT specialist.
    return vtt_file_to_plain_meta(path)


# --------------------------------------------------------------------- #
# SRT
# --------------------------------------------------------------------- #
def srt_text_to_plain(raw: str) -> str:
    """Convert a SubRip (``.srt``) string to clean plain text via the VTT parser."""
    vtt = "WEBVTT\n\n" + _SRT_TS_RE.sub(r"\1.\2", raw)
    return vtt_text_to_plain(vtt)


def srt_file_to_plain_meta(path: Path) -> tuple[str, str]:
    """Read a ``.srt`` file (codec-fallback) → ``(plain_text, codec_name)``."""
    text, codec = _decode_with_fallback(path.read_bytes())
    if text.startswith("﻿"):
        text = text[1:]
    return srt_text_to_plain(text), codec


# --------------------------------------------------------------------- #
# TTML / DFXP (XML)
# --------------------------------------------------------------------- #
def ttml_text_to_plain(raw: str) -> str:
    """Convert a TTML/DFXP caption string to clean plain text.

    Each ``<p>`` becomes one line; nested styling spans contribute their text,
    ``<br/>`` becomes a space. Raises ``ValueError`` on a DTD/entity declaration
    (XXE / billion-laughs guard) or unparseable XML so the caller falls back to
    ASR rather than crashing.
    """
    if _DTD_RE.search(raw):
        raise ValueError(
            "TTML caption contains a DTD/entity declaration — refused "
            "(XXE / entity-expansion guard)"
        )
    # Map line breaks to spaces BEFORE parsing so itertext() doesn't fuse the
    # words either side of a <br/> (e.g. "Next<br/>line" → "Next line").
    raw = _BR_RE.sub(" ", raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"could not parse TTML caption: {exc}") from exc

    lines: list[str] = []
    for el in root.iter():
        # Strip the XML namespace: "{http://www.w3.org/ns/ttml}p" → "p".
        if el.tag.rsplit("}", 1)[-1].lower() != "p":
            continue
        text = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def ttml_file_to_plain_meta(path: Path) -> tuple[str, str]:
    """Read a ``.ttml``/``.dfxp``/``.xml`` file → ``(plain_text, codec_name)``.

    Size-capped (``_MAX_TTML_BYTES``) before decode/parse. Raises ``ValueError``
    on an oversized or malformed/DTD-bearing file.
    """
    raw_bytes = path.read_bytes()
    if len(raw_bytes) > _MAX_TTML_BYTES:
        raise ValueError(
            f"TTML caption is {len(raw_bytes)} bytes (> {_MAX_TTML_BYTES} cap) — refused"
        )
    text, codec = _decode_with_fallback(raw_bytes)
    if text.startswith("﻿"):
        text = text[1:]
    return ttml_text_to_plain(text), codec


__all__ = (
    "SUPPORTED_CAPTION_EXTS",
    "captions_file_to_plain_meta",
    "srt_file_to_plain_meta",
    "srt_text_to_plain",
    "ttml_file_to_plain_meta",
    "ttml_text_to_plain",
)
