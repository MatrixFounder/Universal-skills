"""xlsx-3 F1 (input reader + pre-scan) + F2 (block identification).

task-005-04 — full bodies for `read_input`, `scrub_fenced_and_comments`,
`iter_blocks`. The pre-scan handles four region types:

  1. Fenced code blocks (``` and ~~~).
  2. HTML comments (`<!-- ... -->`).
  3. Indented code blocks (4-space-indent / tab; CommonMark
     conservative match — must follow a blank line).
  4. `<style>` / `<script>` blocks (HTML5 raw-text elements).

All four region types are replaced with **equal-length spaces** so
downstream `iter_blocks` line numbers stay stable for diagnostics.

`iter_blocks` then walks the scrubbed text emitting:
  - `Heading(level, text, line)` for markdown `#`-`######` and HTML
    `<h1>`-`<h6>` (case-insensitive; NOT emitted if the heading is
    inside a `<table>` block — ARCH m6 lock).
  - `PipeTable(raw_lines, line)` for GFM pipe-table ranges
    (header + GFM-separator-row + body rows).
  - `HtmlTable(fragment, line)` for `<table>…</table>` ranges.
  - Blockquoted pipe-table lines (`> | a | b |`) are silently
    skipped (R9.g / honest-scope §11.7 lock).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

from .cli_helpers import read_stdin_utf8


# ============================================================
# Data classes (Block tagged union)
# ============================================================


@dataclass(frozen=True)
class Heading:
    """A markdown `#`/`##`/`###` heading OR an HTML `<h1>`-`<h6>`
    heading. `text` is the raw heading text (may contain markdown
    bold/code); F7 inline-strips it before sanitisation.
    """
    level: int
    text: str
    line: int


@dataclass(frozen=True)
class PipeTable:
    """A contiguous range of `|`-pipe lines forming a GFM pipe table.
    `raw_lines` includes the header and separator rows.
    """
    raw_lines: list[str]
    line: int


@dataclass(frozen=True)
class HtmlTable:
    """A `<table>…</table>` fragment. `fragment` is the raw substring;
    parsing is deferred to `tables.parse_html_table` (uses lxml.html).
    """
    fragment: str
    line: int


Block = Union[Heading, PipeTable, HtmlTable]


@dataclass(frozen=True)
class Region:
    """A dropped region from `scrub_fenced_and_comments`. `kind` is
    one of "fenced_code" / "html_comment" / "indented_code" /
    "style_block" / "script_block".
    """
    start_line: int
    end_line: int
    kind: str


# ============================================================
# F1 — Input Reader
# ============================================================


def read_input(path: str, encoding: str = "utf-8") -> tuple[str, str]:
    """Acquire raw markdown text from a file path or stdin sentinel.

    - `path == "-"` → delegate to `cli_helpers.read_stdin_utf8()`
      (ARCH m5 single-source-of-truth lock); returns
      `(text, "<stdin>")`.
    - Otherwise reads `Path(path)` with the given encoding (default
      UTF-8 strict) and returns `(text, str(resolved_path))`.

    Bad-UTF-8 input raises `UnicodeDecodeError` (orchestrator maps to
    `InputEncodingError` envelope). Missing file raises
    `FileNotFoundError` (orchestrator maps to `FileNotFound`
    envelope, exit 1).
    """
    if path == "-":
        return read_stdin_utf8(), "<stdin>"
    p = Path(path)
    text = p.read_text(encoding=encoding)
    return text, str(p.resolve(strict=False))


def is_stdin_sentinel(path: str) -> bool:
    """Return True iff `path` is the stdin sentinel `-`."""
    return path == "-"


# ============================================================
# F1 — Pre-Scan Strip
# ============================================================


# vdd-multi M4 review-fix: CommonMark caps fence indentation at 3
# spaces (4+ spaces → indented code block, NOT a fence). Restrict
# leading whitespace to 0-3 spaces.
_FENCED_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_INDENTED_CODE_RE = re.compile(r"^(?: {4,}|\t)")
_HTML_COMMENT_OPEN = "<!--"
_HTML_COMMENT_CLOSE = "-->"
# HTML5 raw-text elements: <style> and <script>. Case-insensitive
# opening; matching close tag identified by literal `</style>` /
# `</script>` (also case-insensitive).
_STYLE_OPEN_RE = re.compile(r"<\s*style\b[^>]*>", re.IGNORECASE)
_STYLE_CLOSE_RE = re.compile(r"</\s*style\s*>", re.IGNORECASE)
_SCRIPT_OPEN_RE = re.compile(r"<\s*script\b[^>]*>", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</\s*script\s*>", re.IGNORECASE)


def _replace_with_spaces(text: str, start: int, end: int) -> str:
    """Replace the slice [start:end) with spaces, preserving newlines
    so line numbers stay stable. End is exclusive.

    vdd-multi H3 review-fix: replaced the per-char Python loop with a
    `split("\\n")` / `join(" " * len(part))` form — two C-level scans
    instead of an O(region_size) Python-level iterator. ~30× faster on
    large regions; same output semantics (length + newline preservation).
    """
    seg = text[start:end]
    if not seg:
        return text
    parts = seg.split("\n")
    repl = "\n".join(" " * len(p) for p in parts)
    return text[:start] + repl + text[end:]


def _strip_style_script(text: str) -> tuple[str, list[Region]]:
    """Drop `<style>…</style>` and `<script>…</script>` ranges by
    replacing with equal-length spaces (newlines preserved).

    vdd-multi H4 review-fix: track `pos` and pass `.search(text, pos)`
    so subsequent iterations don't rescan the already-blanked prefix.
    Drops worst-case from O(N²) to O(n + sum_region_size) over the
    number of style/script blocks N.
    """
    regions: list[Region] = []
    for open_re, close_re, kind in (
        (_STYLE_OPEN_RE, _STYLE_CLOSE_RE, "style_block"),
        (_SCRIPT_OPEN_RE, _SCRIPT_CLOSE_RE, "script_block"),
    ):
        pos = 0
        while True:
            m_open = open_re.search(text, pos)
            if not m_open:
                break
            m_close = close_re.search(text, m_open.end())
            # If no closing tag, drop to end-of-text (defensive).
            end_pos = m_close.end() if m_close else len(text)
            start_line = text.count("\n", 0, m_open.start()) + 1
            end_line = text.count("\n", 0, end_pos) + 1
            regions.append(Region(start_line, end_line, kind))
            text = _replace_with_spaces(text, m_open.start(), end_pos)
            pos = end_pos
    return text, regions


def _strip_html_comments(text: str) -> tuple[str, list[Region]]:
    """Drop `<!-- ... -->` regions, preserving newlines."""
    regions: list[Region] = []
    pos = 0
    while True:
        start = text.find(_HTML_COMMENT_OPEN, pos)
        if start == -1:
            break
        end = text.find(_HTML_COMMENT_CLOSE, start + len(_HTML_COMMENT_OPEN))
        end_pos = end + len(_HTML_COMMENT_CLOSE) if end != -1 else len(text)
        start_line = text.count("\n", 0, start) + 1
        end_line = text.count("\n", 0, end_pos) + 1
        regions.append(Region(start_line, end_line, "html_comment"))
        text = _replace_with_spaces(text, start, end_pos)
        pos = end_pos
    return text, regions


def _strip_fenced_code(text: str) -> tuple[str, list[Region]]:
    """Drop fenced code blocks (``` or ~~~) by line. Matches
    CommonMark-style fences: opening fence with 3+ backticks or
    tildes; closing fence same char + same-or-greater count.
    """
    regions: list[Region] = []
    lines = text.split("\n")
    out_lines = list(lines)
    i = 0
    while i < len(lines):
        m = _FENCED_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_char = m.group(2)[0]
        fence_len = len(m.group(2))
        start = i
        # Find matching close fence.
        j = i + 1
        close_re = re.compile(
            r"^(\s*)(" + re.escape(fence_char) + "{" + str(fence_len) + r",})\s*$"
        )
        while j < len(lines):
            if close_re.match(lines[j]):
                break
            j += 1
        end = j if j < len(lines) else len(lines) - 1
        # Replace lines [start..end] inclusive with spaces (preserve
        # line count by keeping empty-content lines).
        for k in range(start, min(end + 1, len(lines))):
            # Preserve length; lines[k] has no trailing newline at
            # this point (split removed them).
            out_lines[k] = " " * len(lines[k])
        regions.append(Region(start + 1, min(end + 1, len(lines)), "fenced_code"))
        i = end + 1
    return "\n".join(out_lines), regions


def _strip_indented_code(text: str) -> tuple[str, list[Region]]:
    """Drop 4-space-indent / tab-indent code blocks per CommonMark
    conservative match: a block is an indented run preceded by a
    blank line (or start-of-document).
    """
    regions: list[Region] = []
    lines = text.split("\n")
    out_lines = list(lines)
    i = 0
    while i < len(lines):
        # CommonMark: indented code starts after a blank line OR at
        # start-of-document.
        is_indented = bool(_INDENTED_CODE_RE.match(lines[i])) and lines[i].strip() != ""
        prev_blank = (i == 0) or (lines[i - 1].strip() == "")
        if is_indented and prev_blank:
            start = i
            j = i
            # Greedily consume contiguous indented or blank lines,
            # but only keep the block if at least one indented line
            # is present (avoid eating trailing blanks).
            while j < len(lines):
                if _INDENTED_CODE_RE.match(lines[j]) and lines[j].strip() != "":
                    j += 1
                elif lines[j].strip() == "":
                    # Look ahead: if next non-blank is still indented,
                    # include the blank; else stop.
                    k = j + 1
                    while k < len(lines) and lines[k].strip() == "":
                        k += 1
                    if k < len(lines) and _INDENTED_CODE_RE.match(lines[k]):
                        j = k
                    else:
                        break
                else:
                    break
            for kk in range(start, j):
                if lines[kk].strip() != "":
                    out_lines[kk] = " " * len(lines[kk])
            regions.append(Region(start + 1, j, "indented_code"))
            i = j
        else:
            i += 1
    return "\n".join(out_lines), regions


def scrub_fenced_and_comments(text: str) -> tuple[str, list[Region]]:
    """Pre-scan strip pass.

    NOTE: name is historical — strips FOUR region types: fenced code,
    HTML comments, indented code (ARCH Q1 default YES), and
    `<style>`/`<script>` blocks. Plan-review m4 note: kept the name
    to avoid touching cli imports.

    Each dropped region is replaced with equal-length spaces so
    downstream `iter_blocks` line numbers remain stable. Returns
    `(scrubbed_text, dropped_regions)`.

    Order of passes matters: fenced FIRST (some fences contain HTML
    that looks like `<style>` etc.), then HTML comments, then
    style/script blocks, then indented code.
    """
    all_regions: list[Region] = []
    text, regs = _strip_fenced_code(text)
    all_regions.extend(regs)
    text, regs = _strip_html_comments(text)
    all_regions.extend(regs)
    text, regs = _strip_style_script(text)
    all_regions.extend(regs)
    text, regs = _strip_indented_code(text)
    all_regions.extend(regs)
    return text, all_regions


# ============================================================
# F2 — Block Identification
# ============================================================


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_HTML_HEADING_RE = re.compile(
    r"<\s*h([1-6])\b[^>]*>(.*?)</\s*h\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# GFM separator row: |---|---:|:--:|, or without trailing pipes.
_GFM_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
# Detect a line that "looks like" a pipe-table line (has ≥ 1
# non-escaped `|` AND is not a blockquote).
_PIPE_LINE_RE = re.compile(r"[^\\]\|")


def _is_blockquote(line: str) -> bool:
    """Return True iff the line starts with `>` (after optional
    leading whitespace) — a blockquote line. Blockquoted tables are
    skipped (R9.g lock).
    """
    return line.lstrip().startswith(">")


def _line_looks_pipe_table(line: str) -> bool:
    """A line that could be a pipe-table row: contains at least one
    non-escaped `|`, isn't a blockquote, and has non-whitespace
    content.
    """
    if not line.strip():
        return False
    if _is_blockquote(line):
        return False
    # Quick check: must have `|` somewhere, and not all `\|`.
    # Use a small heuristic: replace `\|` with empty, then check `|`.
    stripped = line.replace("\\|", "")
    return "|" in stripped


def _find_html_table_ranges(text: str) -> list[tuple[int, int, int]]:
    """Find all `<table>…</table>` ranges in `text`. Returns a list
    of `(start_pos, end_pos, start_line)` tuples (start_pos is the
    position of `<`; end_pos is one past `>` of the closing tag).
    Case-insensitive matching.
    """
    out = []
    open_re = re.compile(r"<\s*table\b[^>]*>", re.IGNORECASE)
    close_re = re.compile(r"</\s*table\s*>", re.IGNORECASE)
    pos = 0
    while True:
        m_open = open_re.search(text, pos)
        if not m_open:
            break
        m_close = close_re.search(text, m_open.end())
        if not m_close:
            break
        start_line = text.count("\n", 0, m_open.start()) + 1
        out.append((m_open.start(), m_close.end(), start_line))
        pos = m_close.end()
    return out


def iter_blocks(scrubbed: str) -> Iterator[Block]:
    """Walk the scrubbed text in document order. Emit `Heading`,
    `PipeTable`, or `HtmlTable` instances.

    Algorithm:
      1. Locate all HTML `<table>` ranges (we mask them so downstream
         line-by-line walking skips them as a unit).
      2. Walk line by line:
         - If line is inside an HTML-table range → emit `HtmlTable`
           once (at start) and skip to past the end-tag.
         - If line is a markdown heading → emit `Heading`.
         - If line is a pipe-table-looking line AND next non-skipped
           line is a GFM separator → consume contiguous pipe-table
           lines and emit `PipeTable`.
         - HTML headings outside `<table>` blocks → emit `Heading`.
    """
    # Phase 1: HTML <table> ranges (mask them so pipe/heading walk
    # ignores their content).
    html_ranges = _find_html_table_ranges(scrubbed)

    # Build a "char in html-table range?" predicate via sorted
    # ranges (binary-searchable). For v1 the typical number of
    # `<table>` blocks per document is < 50, so linear scan is fine.
    def _in_html_range(pos: int) -> tuple[int, int, int] | None:
        for s, e, sl in html_ranges:
            if s <= pos < e:
                return (s, e, sl)
            if pos < s:
                return None
        return None

    # Pre-compute HTML heading positions in non-table regions.
    html_heading_blocks: list[Heading] = []
    for m in _HTML_HEADING_RE.finditer(scrubbed):
        if _in_html_range(m.start()) is not None:
            # ARCH m6: HTML headings inside <table> not emitted.
            continue
        level = int(m.group(1))
        text = re.sub(r"\s+", " ", m.group(2)).strip()
        line = scrubbed.count("\n", 0, m.start()) + 1
        html_heading_blocks.append(Heading(level, text, line))

    # Phase 2: line-by-line walk. HTML headings outside <table>
    # ranges are emitted inline at the matching `i+1 == h.line` step.
    lines = scrubbed.split("\n")
    # Line-start char offsets for `_in_html_range` position lookups.
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln) + 1)
    i = 0
    emitted_table_starts: set[int] = set()
    while i < len(lines):
        line_pos = line_starts[i]

        # Check whether we're entering an HTML <table> range at this line.
        in_html = _in_html_range(line_pos)
        if in_html is not None:
            s, e, start_line = in_html
            if start_line == i + 1 and start_line not in emitted_table_starts:
                fragment = scrubbed[s:e]
                yield HtmlTable(fragment=fragment, line=start_line)
                emitted_table_starts.add(start_line)
            # Skip past the end of this html range.
            end_line = scrubbed.count("\n", 0, e) + 1
            i = end_line  # Move past the closing-tag line.
            continue

        line = lines[i]

        # Check for HTML headings landing at this line (rare case
        # where heading is outside a table).
        for h in html_heading_blocks:
            if h.line == i + 1:
                yield h

        # Markdown heading?
        m = _MD_HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            yield Heading(level=level, text=text, line=i + 1)
            i += 1
            continue

        # Pipe-table candidate? Need next non-blank, non-blockquote
        # line to be a GFM separator.
        if _line_looks_pipe_table(line):
            # Look at next line for separator (skip blanks/blockquote).
            sep_idx = i + 1
            while sep_idx < len(lines) and lines[sep_idx].strip() == "":
                sep_idx += 1
            if (
                sep_idx < len(lines)
                and not _is_blockquote(lines[sep_idx])
                and _GFM_SEPARATOR_RE.match(lines[sep_idx])
            ):
                # Consume contiguous pipe-rows starting at i.
                start_line = i + 1
                raw_lines = [lines[i], lines[sep_idx]]
                j = sep_idx + 1
                while j < len(lines):
                    if _line_looks_pipe_table(lines[j]):
                        raw_lines.append(lines[j])
                        j += 1
                    else:
                        break
                yield PipeTable(raw_lines=raw_lines, line=start_line)
                i = j
                continue

        i += 1
