"""Build and write the ``.description.md`` sidecar.

Format: YAML frontmatter + Markdown body. One file per transcript so
the description can be reviewed without re-decoding the stat JSON
(YAML is widely understood by Obsidian, RAG ingestors, and humans).

The frontmatter shape differs by source — YouTube emits
``source/url/title/uploader/upload_date/duration_sec``; Skool adds
``community/classroom_id/lesson_id/embed_source/embed_url/thumbnail/
resources``. Both are produced by the same writer, which YAML-encodes
whatever caller hands in as the ``frontmatter`` mapping.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Optional


def description_path_for(out_path: Path) -> Path:
    """Compute the description-sidecar path.

    The plain transcript lives at ``<out>.txt``; the description is
    ``<out>.description.md`` (we strip the ``.txt`` suffix if present
    so ``foo.txt`` -> ``foo.description.md``).
    """
    out_path = Path(out_path)
    name = out_path.name
    if name.endswith(".txt"):
        stem = name[: -len(".txt")]
    else:
        stem = name
    return out_path.with_name(stem + ".description.md")


def write_description_md(
    out_path: Path,
    *,
    frontmatter: Mapping[str, Any],
    title: Optional[str],
    body: str,
) -> Path:
    """Write ``<out>.description.md`` and return its path.

    Args:
        out_path: The path used for the plain-text transcript.
            ``description_path_for`` derives the sidecar path from it.
        frontmatter: Mapping serialised as YAML frontmatter (order is
            preserved by relying on insertion order of dict). Values
            are coerced via :func:`_yaml_value`. Keys with ``None``
            values are omitted.
        title: Optional H1 heading rendered before the body. ``None``
            skips the heading.
        body: Markdown body. Trailing whitespace is stripped.

    Returns:
        The path to the written sidecar.
    """
    desc_path = description_path_for(out_path)
    desc_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["---"]
    for key, value in frontmatter.items():
        if value is None:
            continue
        lines.append(_yaml_line(key, value))
    lines.append("---")
    lines.append("")
    if title:
        lines.append(f"# {_escape_md_heading(title)}")
        lines.append("")
    lines.append(body.rstrip())
    lines.append("")
    desc_path.write_text("\n".join(lines), encoding="utf-8")
    return desc_path


def _yaml_line(key: str, value: Any) -> str:
    safe_key = _yaml_key(key)
    if isinstance(value, list):
        if not value:
            return f"{safe_key}: []"
        rendered = "\n".join(f"  - {_yaml_value(v)}" for v in value)
        return f"{safe_key}:\n{rendered}"
    if isinstance(value, dict):
        if not value:
            return f"{safe_key}: {{}}"
        rendered = "\n".join(
            f"  {_yaml_key(k)}: {_yaml_value(v)}" for k, v in value.items()
        )
        return f"{safe_key}:\n{rendered}"
    return f"{safe_key}: {_yaml_value(value)}"


# Characters that force double-quoted form. \r is in addition to \n
# because YAML 1.2 treats \r as a line break; PyYAML in 1.1 mode treats
# \r\n / \r / \n equivalently. U+2028 (LS) and U+2029 (PS) are YAML 1.2
# line breaks too. NEL (U+0085) historically also; included for safety.
_YAML_BREAK_CHARS = "\n\r  "
_NEEDS_QUOTE_RE = re.compile(
    r'[:#"\']|[' + _YAML_BREAK_CHARS + r']|^[\s\-?&*!@`%>|]|^$'
)
# A safe bare YAML key — alphanumeric + ``_`` ``-``, must start with a
# letter or underscore. Anything else gets double-quoted via _yaml_value.
_SAFE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _yaml_key(key: Any) -> str:
    """Render a dict key, double-quoting if it's not a safe bare key.

    Attacker-controlled keys (e.g. from a Skool ``resources`` array) must
    not break out of the frontmatter; rendering through
    :func:`_yaml_value` enforces the same escape contract as values.
    """
    if isinstance(key, str) and _SAFE_KEY_RE.match(key):
        return key
    return _yaml_value(key)


def _yaml_value(value: Any) -> str:
    """Render a scalar YAML value, quoting when ambiguous.

    Quoting is conservative: anything with YAML-special characters or
    leading reserved chars goes through double-quoted form with `\\`
    and `"` escaped, and every YAML line-break character (``\n``, ``\r``,
    U+2028, U+2029, U+0085) is replaced with its escape sequence so a
    multiline value cannot escape the scalar. Numbers and bools render
    bare.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    s = str(value)
    if _NEEDS_QUOTE_RE.search(s):
        # NOTE: the three trailing replace() calls below use invisible
        # literals — U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR,
        # U+0085 NEL — as needle. They are YAML 1.2 line breaks that
        # would otherwise split a quoted scalar across multiple lines.
        escaped = (
            s.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n")
             .replace("\r", "\\r")
             .replace(" ", "\\u2028")
             .replace(" ", "\\u2029")
             .replace("", "\\u0085")
        )
        return f'"{escaped}"'
    return s


def _escape_md_heading(title: str) -> str:
    """Strip newlines + leading hashes that would break an H1."""
    one_line = " ".join(title.split())
    return one_line.lstrip("#").strip()
