"""Hypothesis strategies for fuzzing the office CLI inputs (q-5).

The strategies are deliberately small and focused — we want to find
crashes (Python tracebacks, node uncaught exceptions, segfaults) on
edge inputs, not exhaustive correctness. Examples that survive
generation include the empty input, single-character corners, mixed-
unicode (latin + cyrillic + CJK + emoji), table-cell-as-pipe-character
collisions, and large-but-not-pathological inputs.
"""
from __future__ import annotations

from hypothesis import strategies as st


# Drop control + surrogate codepoints — markdown2 / openpyxl / mmdc all
# refuse them outright (and our goal is to crash the *parser*, not to
# verify input sanitisation, which is a separate concern).
_unicode_chars = st.characters(
    blacklist_categories=("Cs", "Cc"),
    # Whitelist categories that appear in real-world Office inputs:
    # letters, numbers, marks, punctuation, symbols, separators.
    whitelist_categories=None,
)

inline_text = st.text(alphabet=_unicode_chars, min_size=0, max_size=200)


def _heading_line(level: int, text: str) -> str:
    # Forbid embedded newlines — they'd promote the next line to a body
    # paragraph and the heading would silently lose half its text.
    return "#" * level + " " + text.replace("\n", " ").replace("\r", " ")


heading = st.builds(
    _heading_line,
    st.integers(min_value=1, max_value=6),
    inline_text,
)

# A markdown table row, written as "| c1 | c2 | ... |".
# Cell escapes the pipe character that would otherwise terminate the
# cell (markdown2 does not auto-escape and would mis-parse).
def _cells_to_row(cells: list[str]) -> str:
    safe = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
    return "| " + " | ".join(safe) + " |"


table_row = st.lists(inline_text, min_size=1, max_size=8).map(_cells_to_row)

block = st.one_of(heading, inline_text, table_row)
markdown_doc = st.lists(block, min_size=0, max_size=50) \
    .map(lambda blocks: "\n\n".join(blocks))


# CSV: cells with no embedded comma/newline (would change column count
# without quoting); separated rows; row counts kept modest for speed.
def _scrub_csv_cell(s: str) -> str:
    return s.replace(",", ";").replace("\n", " ").replace("\r", " ") \
            .replace('"', "'")


csv_cell = st.text(alphabet=_unicode_chars, min_size=0, max_size=80) \
    .map(_scrub_csv_cell)
csv_row = st.lists(csv_cell, min_size=1, max_size=10) \
    .map(lambda cells: ",".join(cells))
csv_doc = st.lists(csv_row, min_size=1, max_size=200) \
    .map(lambda rows: "\n".join(rows))
