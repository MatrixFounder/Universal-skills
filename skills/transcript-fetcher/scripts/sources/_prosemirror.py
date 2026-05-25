"""Convert ProseMirror / TipTap v2 JSON to Markdown.

Skool stores lesson descriptions in TipTap's ProseMirror-style JSON,
prefixed with a version tag like ``[v2]`` followed by a JSON array of
top-level block nodes. Example::

    [v2][
        {"type": "paragraph",
         "content": [{"type": "text", "text": "Hello"}]},
        {"type": "horizontalRule"},
        ...
    ]

This module accepts either the raw ``[v2]...`` string from Skool, a
pre-stripped JSON string, or an already-parsed Python list/dict.

Unknown node types do NOT raise — they render as an HTML comment
(``<!-- unsupported node: type=foo -->``) so the output stays valid
Markdown and the loss is visible to downstream readers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


_VERSION_PREFIX_RE = re.compile(r"^\s*\[v\d+\]\s*", re.DOTALL)


class ProseMirrorError(ValueError):
    """Raised when the input cannot be parsed as ProseMirror JSON at all."""


def prosemirror_to_markdown(payload: Any) -> tuple[str, list[str]]:
    """Convert a ProseMirror v2 payload to Markdown.

    Args:
        payload: One of
            - the raw Skool string ``"[v2][{...}]"``,
            - a bare JSON string (the inner array),
            - the parsed Python object (list of block nodes, or a
              single ``doc`` dict with a ``content`` list).

    Returns:
        ``(markdown, unsupported_nodes)`` — Markdown text plus a list
        of node-type names that were rendered as comments because no
        renderer exists for them. Empty list = clean conversion.

    Raises:
        ProseMirrorError: If the input cannot be interpreted as a
            ProseMirror tree (not a string/list/dict, malformed JSON,
            etc.).
    """
    nodes = _coerce_to_nodes(payload)
    state = _RenderState()
    try:
        out = "\n\n".join(_render_block(n, state) for n in nodes if n is not None)
    except RecursionError:
        # Defense-in-depth: the explicit depth cap in _RenderState should
        # have stopped this long before, but if mutual recursion between
        # block/inline/list still blows the stack on a pathological tree,
        # we degrade gracefully rather than letting the exception escape.
        state.unsupported.append("recursion-error")
        out = "<!-- prosemirror render aborted: recursion limit -->"
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, state.unsupported


# --------------------------------------------------------------------- #
# Input coercion
# --------------------------------------------------------------------- #


def _coerce_to_nodes(payload: Any) -> list[dict]:
    if isinstance(payload, str):
        stripped = _VERSION_PREFIX_RE.sub("", payload, count=1)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ProseMirrorError(f"invalid ProseMirror JSON: {e}") from e
        return _coerce_to_nodes(parsed)
    if isinstance(payload, dict):
        # Could be a `doc` node wrapping the actual content.
        if payload.get("type") == "doc" and isinstance(payload.get("content"), list):
            return payload["content"]
        # Or a single block node.
        return [payload]
    if isinstance(payload, list):
        return [n for n in payload if isinstance(n, dict)]
    raise ProseMirrorError(
        f"expected str, list, or dict for ProseMirror payload; got {type(payload).__name__}"
    )


# --------------------------------------------------------------------- #
# Rendering — block & inline
# --------------------------------------------------------------------- #


_MAX_BLOCK_DEPTH = 200  # hard cap on nested block recursion


class _RenderState:
    """Mutable context threaded through the recursion.

    Tracks unsupported node types and current list nesting (to indent
    nested bullets correctly without depending on caller bookkeeping).
    The ``block_depth`` field bounds recursion globally so a hostile
    or accidentally-deep ProseMirror tree cannot overflow the Python
    stack (which would propagate as an uncaught ``RecursionError``).
    """

    def __init__(self) -> None:
        self.unsupported: list[str] = []
        self.list_depth: int = 0
        self.block_depth: int = 0


def _render_block(node: dict, state: _RenderState) -> str:
    t = node.get("type") if isinstance(node, dict) else None
    if not t:
        return ""
    if state.block_depth >= _MAX_BLOCK_DEPTH:
        state.unsupported.append(f"max-depth:{t}")
        return f"<!-- max nesting depth reached: {t} -->"
    state.block_depth += 1
    try:
        return _render_block_inner(node, t, state)
    finally:
        state.block_depth -= 1


def _render_block_inner(node: dict, t: str, state: _RenderState) -> str:
    if t == "paragraph":
        return _render_inline(node.get("content", []), state)
    if t == "heading":
        level = int(node.get("attrs", {}).get("level", 1))
        level = max(1, min(level, 6))
        body = _render_inline(node.get("content", []), state)
        return f"{'#' * level} {body}".rstrip()
    # Some TipTap/ProseMirror schemas (Skool included) emit the
    # ``unorderedList`` / ``unordered_list`` alias instead of the
    # canonical ``bulletList`` — accept both.
    if t in ("bulletList", "unorderedList", "unordered_list", "bullet_list"):
        return _render_list(node, state, ordered=False)
    if t in ("orderedList", "ordered_list"):
        return _render_list(node, state, ordered=True)
    if t == "codeBlock":
        language = ""
        attrs = node.get("attrs")
        if isinstance(attrs, dict):
            language = attrs.get("language") or attrs.get("params") or ""
        text = _gather_text(node.get("content", []))
        return f"```{language}\n{text}\n```"
    if t == "horizontalRule":
        return "---"
    if t == "blockquote":
        inner_nodes = node.get("content", [])
        rendered = "\n\n".join(
            _render_block(n, state) for n in inner_nodes if isinstance(n, dict)
        )
        return "\n".join(f"> {line}" if line else ">" for line in rendered.split("\n"))
    if t == "image":
        return _render_image(node)
    if t == "hardBreak":
        return "  "
    # Unknown -> emit comment, record for stat.notes.
    state.unsupported.append(t)
    return f"<!-- unsupported node: type={t} -->"


def _render_list(node: dict, state: _RenderState, *, ordered: bool) -> str:
    items: list[str] = []
    state.list_depth += 1
    try:
        for idx, child in enumerate(node.get("content", []), start=1):
            if not isinstance(child, dict) or child.get("type") != "listItem":
                continue
            item_body = _render_list_item(child, state)
            marker = f"{idx}. " if ordered else "- "
            indent = "  " * (state.list_depth - 1)
            # Indent every line of the item body, leading line gets the marker.
            body_lines = item_body.split("\n")
            first = f"{indent}{marker}{body_lines[0]}"
            rest = [f"{indent}  {line}" if line else "" for line in body_lines[1:]]
            items.append("\n".join([first, *rest]).rstrip())
    finally:
        state.list_depth -= 1
    return "\n".join(items)


def _render_list_item(node: dict, state: _RenderState) -> str:
    parts = []
    for child in node.get("content", []):
        if not isinstance(child, dict):
            continue
        rendered = _render_block(child, state)
        if rendered:
            parts.append(rendered)
    return "\n\n".join(parts).strip()


def _render_inline(nodes: Any, state: _RenderState) -> str:
    if not isinstance(nodes, list):
        return ""
    out = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        t = n.get("type")
        if t == "text":
            text = n.get("text", "")
            marks = n.get("marks", []) or []
            has_code = any(
                isinstance(m, dict) and m.get("type") == "code" for m in marks
            )
            if not has_code:
                text = _escape_text(text)
            out.append(_apply_marks(text, marks))
        elif t == "hardBreak":
            out.append("  \n")
        elif t == "image":
            out.append(_render_image(n))
        else:
            # Some platforms nest blocks as inline — fall back to block rendering.
            rendered_block = _render_block(n, state)
            if rendered_block:
                out.append(rendered_block)
    return "".join(out)


_SAFE_URL_SCHEMES = ("http", "https", "mailto")


def _safe_url(raw: object) -> str:
    """Return a Markdown-safe URL or empty string.

    - Rejects schemes outside the allowlist (``javascript:``, ``data:``,
      ``file:``, ``vbscript:`` etc. become empty strings → renders as
      ``[label]()``).
    - Percent-encodes ``(`` and ``)`` so a hostile URL cannot terminate
      the Markdown ``[...](...)`` syntax and inject a second link.
    """
    if not isinstance(raw, str) or not raw:
        return ""
    # Schemes are case-insensitive; absolute URLs only — relative paths
    # are unsafe in a description that may be rendered out-of-context.
    lower = raw.lstrip().lower()
    if ":" in lower.split("/", 1)[0]:
        scheme = lower.split(":", 1)[0]
        if scheme not in _SAFE_URL_SCHEMES:
            return ""
    return raw.replace("(", "%28").replace(")", "%29")


def _escape_label(text: str) -> str:
    """Escape Markdown link/image label so the closing ``]`` is preserved."""
    return (
        text.replace("\\", "\\\\")
            .replace("[", "\\[")
            .replace("]", "\\]")
    )


def _render_image(node: dict) -> str:
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    src = _safe_url(attrs.get("src", ""))
    alt = attrs.get("alt") or attrs.get("title") or ""
    if not src:
        return ""
    return f"![{_escape_label(str(alt))}]({src})"


# --------------------------------------------------------------------- #
# Inline marks
# --------------------------------------------------------------------- #


def _apply_marks(text: str, marks: Any) -> str:
    if not isinstance(marks, list) or not marks:
        return text
    # Apply outermost-first so that nested marks compose correctly.
    # Order matters for tests: code is applied first so bold(code(x)) -> **`x`**.
    order = {"code": 0, "link": 1, "strike": 2, "italic": 3, "bold": 4}
    sorted_marks = sorted(
        (m for m in marks if isinstance(m, dict) and m.get("type")),
        key=lambda m: order.get(m["type"], 10),
    )
    out = text
    for m in sorted_marks:
        t = m.get("type")
        if t == "bold":
            out = f"**{out}**"
        elif t == "italic":
            out = f"*{out}*"
        elif t == "code":
            out = f"`{out}`"
        elif t == "strike":
            out = f"~~{out}~~"
        elif t == "link":
            href = _safe_url((m.get("attrs") or {}).get("href", ""))
            # Wrap the already-escaped inline payload in escaped brackets so
            # a hostile text node cannot break the link grammar.
            out = f"[{_escape_label(out)}]({href})"
        elif t == "underline":
            out = f"<u>{out}</u>"
        # Unknown marks are silently dropped (still emit the wrapped text).
    return out


_MD_ESCAPE_RE = re.compile(r"([\\`*_{}\[\]()#+\-!])")


def _escape_text(text: str) -> str:
    """Escape Markdown-special characters in raw text.

    We deliberately do NOT escape every special character — backslash,
    backtick, asterisk, underscore, brackets, hash, and bang are the
    common ones that misrender. Newlines inside a `text` node are left
    intact (ProseMirror typically uses ``hardBreak`` for explicit line
    breaks within a paragraph).
    """
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def _gather_text(nodes: Any) -> str:
    """Recursively collect raw text from a node subtree (for codeBlock)."""
    if isinstance(nodes, list):
        return "".join(_gather_text(n) for n in nodes)
    if isinstance(nodes, dict):
        if nodes.get("type") == "hardBreak":
            return "\n"
        if "text" in nodes and isinstance(nodes["text"], str):
            return nodes["text"]
        return _gather_text(nodes.get("content", []))
    return ""


def strip_version_prefix(raw: str) -> Optional[str]:
    """Return the JSON portion of a ``[vN]...`` Skool string.

    Returns ``None`` if no version prefix is detected — caller should
    treat the input as already-bare JSON.
    """
    if not isinstance(raw, str):
        return None
    m = _VERSION_PREFIX_RE.match(raw)
    if not m:
        return None
    return raw[m.end():]
