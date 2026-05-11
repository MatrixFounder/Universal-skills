"""xlsx-3 F5 — inline markdown strip.

task-005-05: full bodies for `strip_inline_markdown` and
`_decode_html_entities`. Pure transforms; idempotent.

Consumed by `tables.py` (per-cell strip before coerce) and
`naming.py` (heading text strip before sanitisation).

Order of operations matters (each pass operates on the output of the
previous):
  1. Decode HTML entities (`&amp;` → `&`, etc.).
  2. `<br>` / `<br/>` / `<br />` → literal `\\n` (R9.c lock).
  3. `**X**` / `__X__` → `X` (bold; non-greedy).
  4. `*X*` / `_X_` → `X` (italic; word-boundary aware so `var_name`
     stays intact).
  5. `` `X` `` → `X` (code span).
  6. `[text](url)` → `text` (link target dropped).
  7. `~~X~~` → `X` (strikethrough).
  8. Strip remaining inline HTML tags (`<span>`, `<em>`, etc.) →
     text content kept.
"""
from __future__ import annotations

import html
import re


_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
# Bold MUST run before italic — otherwise `**bold**` is consumed as
# two italic spans `*bold*`.
_BOLD_STAR_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_UNDER_RE = re.compile(r"__(.+?)__")
# Italic: use a "not surrounded by word-chars on outside" stance to
# avoid eating `var_name`. We require the underscore/star NOT be
# preceded/followed by a word char on the outside.
_ITALIC_STAR_RE = re.compile(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])")
_ITALIC_UNDER_RE = re.compile(r"(?<![_\w])_([^_\n]+?)_(?![_\w])")
_CODE_RE = re.compile(r"`([^`]+?)`")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _decode_html_entities(text: str) -> str:
    """Thin wrapper around `html.unescape` — kept as a separate
    symbol so future v2 custom-entity handling has a stable hook.
    """
    return html.unescape(text)


def strip_inline_markdown(text: str) -> str:
    """Strip GFM inline markdown + decode HTML entities + replace
    `<br>` with literal newline. Idempotent.
    """
    if not text:
        return text
    # 1. Entities first so `&lt;br&gt;` becomes `<br>` becomes `\n`.
    text = _decode_html_entities(text)
    # 2. <br> → newline.
    text = _BR_RE.sub("\n", text)
    # 3. Bold (must run before italic).
    text = _BOLD_STAR_RE.sub(r"\1", text)
    text = _BOLD_UNDER_RE.sub(r"\1", text)
    # 4. Italic with word-boundary protection.
    text = _ITALIC_STAR_RE.sub(r"\1", text)
    text = _ITALIC_UNDER_RE.sub(r"\1", text)
    # 5. Code span.
    text = _CODE_RE.sub(r"\1", text)
    # 6. Link target dropped, anchor text kept.
    text = _LINK_RE.sub(r"\1", text)
    # 7. Strikethrough.
    text = _STRIKE_RE.sub(r"\1", text)
    # 8. Strip remaining inline HTML tags (run last so `<br>` is
    #    already converted to `\n` and entities are decoded).
    text = _HTML_TAG_RE.sub("", text)
    return text
