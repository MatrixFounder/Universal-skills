"""Convert WebVTT caption files to clean plain text.

YouTube auto-captions arrive in a verbose format: timestamps, position
cues, inline word-timing tags (`<00:00:10.000><c>...</c>`), HTML
entity-encoded `&gt;&gt;` speaker-change markers (anchored at the start
of a cue's text), and rolling-caption overlap (each new cue is a
prefix-extension of the previous, sometimes with non-prefix suffix
overlap at sentence boundaries).

This module strips all of that down to readable prose suitable for
downstream summarization, while preserving leading `>>` turn boundaries
as visible newline-prefixed paragraph breaks so a downstream LLM can
attribute statements correctly. `>>` that appears mid-cue (e.g. a
talk discussing C++ stream operators or shell redirection) is left
untouched.

Encoding fallback: tries UTF-8 first, then CP1251, then UTF-16, before
giving up. Older Russian content from non-YouTube sources sometimes
ships in CP1251.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

# A WebVTT cue header line, e.g. "00:00:09.390 --> 00:00:11.350 align:start position:0%"
TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*")
# Inline timing/style tags YouTube interleaves into cue text
INLINE_TAG_RE = re.compile(r"<[^>]+>")
# WebVTT file-header / block-header lines we always drop
HEADER_PREFIXES = ("WEBVTT", "Kind:", "Language:", "STYLE", "NOTE", "REGION")
# Sentinel for line-leading turn markers — survives whitespace normalisation
# without colliding with any printable content.
_TURN_SENTINEL = "\x00TURN\x00"


def vtt_text_to_plain(raw: str) -> str:
    """Convert a WebVTT string to clean plain text.

    Steps:
      1. Group lines into cues (one cue = one or more text lines between
         a timestamp header and the next blank-line boundary).
      2. Drop file-header / block-header lines (``WEBVTT``, ``Kind:``,
         ``Language:``, ``STYLE``, ``NOTE``, ``REGION``).
      3. Strip inline timing tags within each cue's text.
      4. Decode HTML entities (``&gt;&gt;`` -> ``>>``, ``&amp;`` -> ``&``).
      5. Detect leading ``>>`` (speaker-turn marker) on each cue.
      6. Deduplicate rolling-caption overlap at the cue level: prefix
         extensions and suffix-prefix overlaps both collapse.
      7. Render: cues marked as turn starts are joined with a paragraph
         break; others with a space. Mid-cue ``>>`` is preserved verbatim.
    """
    cues = _parse_cues(raw)
    cleaned: list[tuple[str, bool]] = []  # (text, is_turn_start)
    for cue_text in cues:
        cue_text = INLINE_TAG_RE.sub("", cue_text)
        cue_text = html.unescape(cue_text)
        cue_text = re.sub(r"\s+", " ", cue_text).strip()
        if not cue_text:
            continue
        is_turn = cue_text.startswith(">>")
        if is_turn:
            cue_text = cue_text[2:].lstrip()
            if not cue_text:
                # `>>` alone is a degenerate turn-start; skip — next cue
                # will carry the actual content.
                continue
        cleaned.append((cue_text, is_turn))

    # Cue-level dedup: handle both prefix-extension and suffix-prefix overlap.
    deduped: list[tuple[str, bool]] = []
    for text, is_turn in cleaned:
        if not deduped:
            deduped.append((text, is_turn))
            continue
        prev_text, prev_turn = deduped[-1]
        if text == prev_text:
            continue
        if prev_text.startswith(text):
            # current is a strict prefix of previous; drop current
            continue
        if text.startswith(prev_text):
            # current extends previous; replace previous, keep its turn flag
            deduped[-1] = (text, prev_turn or is_turn)
            continue
        # Suffix-prefix overlap: previous ends with N words that begin current.
        merged = _splice_suffix_prefix(prev_text, text)
        if merged is not None:
            deduped[-1] = (merged, prev_turn or is_turn)
            continue
        deduped.append((text, is_turn))

    # Render with sentinels for turn boundaries.
    parts: list[str] = []
    for i, (text, is_turn) in enumerate(deduped):
        if is_turn:
            parts.append(_TURN_SENTINEL + text)
        else:
            parts.append(text)
    joined = " ".join(parts)
    joined = re.sub(r"[ \t]+", " ", joined)
    # Convert sentinels to paragraph breaks. The first sentinel at offset 0
    # also gets a leading newline-pair, but we strip those at the end.
    out = joined.replace(_TURN_SENTINEL, "\n\n>> ")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def vtt_file_to_plain(vtt_path: Path) -> str:
    """Read a ``.vtt`` file and convert it to plain text.

    Tries UTF-8 first, then CP1251, then UTF-16. Strips a UTF-8/UTF-16 BOM
    if present. Raises ``ValueError`` if no codec succeeds.
    """
    text, _ = _read_vtt_with_codec(vtt_path)
    return vtt_text_to_plain(text)


def vtt_file_to_plain_meta(vtt_path: Path) -> tuple[str, str]:
    """Like :func:`vtt_file_to_plain` but also returns the codec used.

    Returns ``(plain_text, codec_name)``. Callers can flag the result
    when ``codec_name`` is anything other than ``"utf-8"`` or
    ``"utf-8-sig"`` (those are the expected codecs for YouTube output).
    """
    text, codec = _read_vtt_with_codec(vtt_path)
    return vtt_text_to_plain(text), codec


def _read_vtt_with_codec(vtt_path: Path) -> tuple[str, str]:
    raw_bytes = vtt_path.read_bytes()
    text, codec = _decode_with_fallback(raw_bytes)
    if text.startswith("﻿"):
        text = text[1:]
    return text, codec


def count_speaker_turns(text: str) -> int:
    """Count `>>` speaker-turn markers in cleaned plain text.

    The first turn at the very start of the document (text starting with
    ``">> "``) is also counted, even though it has no preceding newlines.
    """
    if not text:
        return 0
    n = text.count("\n\n>> ")
    if text.startswith(">> "):
        n += 1
    return n


# --------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------- #


def _parse_cues(raw: str) -> list[str]:
    """Group raw VTT lines into cue text strings.

    A cue is opened by a timestamp header line and closed by a blank
    line (or EOF). Multiple text lines within a cue are joined by a
    single space. File/block headers, cue indices, and standalone STYLE/
    NOTE/REGION blocks are skipped entirely.
    """
    cues: list[str] = []
    in_cue = False
    in_skip_block = False  # inside a STYLE / NOTE / REGION block
    current: list[str] = []

    def _flush() -> None:
        nonlocal in_cue, current
        if in_cue and current:
            cues.append(" ".join(current))
        in_cue = False
        current = []

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            _flush()
            in_skip_block = False
            continue
        if any(s.startswith(p) for p in HEADER_PREFIXES):
            # STYLE / NOTE / REGION introduce a block we drop until blank line
            if s.startswith(("STYLE", "NOTE", "REGION")):
                in_skip_block = True
            continue
        if in_skip_block:
            continue
        if s.isdigit():
            # cue index like "42" — skip
            continue
        if TS_RE.match(s):
            _flush()
            in_cue = True
            continue
        if in_cue:
            current.append(s)
    _flush()
    return cues


def _splice_suffix_prefix(prev: str, current: str) -> str | None:
    """If ``prev`` ends with words that begin ``current``, return the splice.

    Returns the merged string when the overlap is at least 3 word tokens
    (to avoid spurious matches on single short words). Returns ``None``
    when there is no qualifying overlap.
    """
    prev_words = prev.split()
    curr_words = current.split()
    max_overlap = min(len(prev_words), len(curr_words))
    # Try the longest overlap first; require >= 3 word tokens to dedup.
    for n in range(max_overlap, 2, -1):
        if prev_words[-n:] == curr_words[:n]:
            return " ".join(prev_words + curr_words[n:])
    return None


def _decode_with_fallback(raw_bytes: bytes) -> tuple[str, str]:
    """Decode VTT bytes using a small ladder of likely codecs.

    Order: UTF-8 (incl. BOM) -> CP1251 -> UTF-16 (with BOM). Returns
    ``(text, codec_name)``. Raises ``ValueError`` if none succeed.
    """
    if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
        try:
            return raw_bytes.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    for codec in ("utf-8-sig", "utf-8", "cp1251", "utf-16"):
        try:
            return raw_bytes.decode(codec), codec
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "Could not decode VTT bytes with utf-8, cp1251, or utf-16. "
        "Pre-convert the file to UTF-8 before passing it in."
    )
