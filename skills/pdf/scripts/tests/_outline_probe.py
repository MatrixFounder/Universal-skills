"""Dump a PDF's document outline (bookmarks) for shell-test assertions.

Test-only helper — NOT a user-facing CLI, NOT wired into the ``_errors.py``
``--json-errors`` envelope. It reads the outline via ``pypdf`` and prints it
depth-indented (two spaces per nesting level) so the ``test_e2e.sh`` pdf-7
blocks can ``grep`` for expected bookmark titles and the indentation that
proves hierarchical nesting.

Exit codes:
  0 — the PDF has a non-empty outline (>= 1 bookmark printed to stdout).
  3 — the outline is empty. This is a *private test-harness sentinel* for
      "no bookmarks"; it is deliberately NOT an ``_errors.py``-style error
      code (this helper stays outside the ``--json-errors`` convention
      because it is test scaffolding, not a shipped CLI).
  2 — usage error (wrong argument count).

Usage:
    python3 _outline_probe.py PDF
"""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader  # type: ignore


def _walk(items: list, depth: int, out: list[str]) -> None:
    """Flatten pypdf's nested-list outline into depth-indented title lines.

    ``pypdf`` represents the outline tree as a list in which a nested *list*
    element is a child group (one nesting level deeper) and any other element
    is a ``Destination`` carrying a ``.title`` bookmark label. Recurse into
    the lists; emit ``"  " * depth + title`` for each destination.
    """
    for it in items:
        if isinstance(it, list):
            _walk(it, depth + 1, out)
        else:
            title = getattr(it, "title", "") or ""
            out.append("  " * depth + title)


def dump_outline(pdf_path: Path) -> list[str]:
    """Return the PDF's outline as depth-indented title lines (may be empty)."""
    reader = PdfReader(str(pdf_path))
    lines: list[str] = []
    _walk(reader.outline, 0, lines)
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: _outline_probe.py PDF", file=sys.stderr)
        return 2
    lines = dump_outline(Path(argv[0]))
    for line in lines:
        print(line)
    return 0 if lines else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
