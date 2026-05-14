"""F6 — Shared cell-value inline rendering. LIVE since task 012-04.

Shared cell-value rendering helpers that are format-agnostic up to the
point where GFM and HTML diverge. Consumed by both :mod:`emit_gfm` and
:mod:`emit_html`.

Public API
----------
- :func:`render_cell_value` — central dispatcher; consumes all params.
- :func:`_escape_pipe_gfm` — ``|`` → ``\\|`` (GFM pipe-table compat).
- :func:`_escape_html_entities` — ``html.escape(text)`` (HTML output).
- :func:`_newlines_to_br` — ``\\n`` → ``<br>`` (UC-12).
- :func:`_render_hyperlink` — scheme-allowlist filter + GFM/HTML emit.

Hyperlink scheme allowlist (D-A15 / R10a)
------------------------------------------
- Default allowlist: ``frozenset({"http", "https", "mailto"})``.
- Pass ``allowed_schemes=None`` to allow ALL schemes (wildcard sentinel;
  NOT recommended — may enable XSS / link-injection in HTML output).
- Pass ``allowed_schemes=frozenset()`` to block ALL hyperlinks (plain
  text only).
- Scheme matching is case-insensitive (RFC 3986 §3.1).
- Empty scheme (relative URL like ``page.html``) is treated as ``"http"``
  (R10a c).
- Blocked schemes emit plain ``value`` text + a ``UserWarning``; the cell
  content is preserved (no hard fail).

xlsx_read hyperlink shape (observed, 012-04)
---------------------------------------------
``xlsx_read.read_table(include_hyperlinks=True)`` returns the hyperlink
**URL** as the cell value (display text is replaced by the URL string).
As a result, ``render_cell_value`` is normally called with the URL as
``value`` and ``hyperlink_href=None``. The ``hyperlink_href`` parameter
is provided for callers that have access to both the display text and
the href separately (e.g., future dict-shape API or manual test
construction).

Multi-row header detection heuristic (ARCH §10 A-A3)
-----------------------------------------------------
Headers containing `` › `` (U+203A with surrounding spaces) are treated
as multi-row flattened headers by :mod:`emit_gfm`. A workbook with a
literal U+203A character in cell text (not as a separator) will be
misdetected. This is a documented accepted limitation (A-A3).
"""
from __future__ import annotations

import html
import urllib.parse
import warnings
from typing import Any, Literal


def render_cell_value(
    value: Any,
    *,
    mode: Literal["gfm", "html"] = "gfm",
    include_formulas: bool = False,
    formula: str | None = None,
    hyperlink_href: str | None = None,
    allowed_schemes: frozenset[str] | None,
    cell_addr: str | None = None,
) -> str:
    """Central dispatcher: render a cell value to a format-appropriate string.

    Pipeline:
    1. ``None`` → ``""`` (empty cell).
    2. ``hyperlink_href`` is not None → route through
       :func:`_render_hyperlink` (D-A15 / R10a).
    3. Otherwise: convert ``value`` to text and apply format-specific
       escaping + newline transform.
       - GFM: :func:`_escape_pipe_gfm` then :func:`_newlines_to_br`.
       - HTML: :func:`_escape_html_entities` then :func:`_newlines_to_br`.
    4. ``include_formulas`` + ``formula``: the formula string is consumed
       by ``emit_html._format_cell_html`` via a ``data-formula`` attribute
       path — NOT injected into the returned text. This branch returns the
       cached value text; the formula attribute is a caller concern.

    Parameters
    ----------
    value:
        Raw cell value from ``TableData.rows`` (or headers).
    mode:
        Render target — ``"gfm"`` or ``"html"``.
    include_formulas:
        If True, the caller intends to emit formula annotations. The
        formula attribute path is NOT handled here (see note above).
    formula:
        Formula string (e.g. ``"=A1+B1"``); unused here, present for
        API symmetry with ``emit_html._format_cell_html``.
    hyperlink_href:
        If not None, treat ``value`` as display text and render a link
        to this URL (scheme-filtered per ``allowed_schemes``).
    allowed_schemes:
        ``None`` → allow all; ``frozenset()`` → block all; otherwise
        a set of lowercase scheme names (e.g. ``{"http", "https", "mailto"}``).
    cell_addr:
        Optional cell address string (e.g. ``"Sheet1!A2"``) for warning
        messages.
    """
    if value is None:
        return ""

    if hyperlink_href is not None:
        return _render_hyperlink(
            value,
            hyperlink_href,
            mode=mode,
            allowed_schemes=allowed_schemes,
            cell_addr=cell_addr,
        )

    text = str(value)
    if mode == "gfm":
        text = _escape_pipe_gfm(text)
        text = _newlines_to_br(text)
    else:  # html
        text = _escape_html_entities(text)
        text = _newlines_to_br(text)
    return text


def _escape_pipe_gfm(text: str) -> str:
    r"""Replace ``|`` with ``\|`` for GFM pipe-table compatibility.

    Other GFM special characters (``*``, ``_``, `` ` ``) pass through
    intentionally — they are treated as markdown-in-cell affordances per
    the xlsx-3 inline contract (ARCH D-A9).
    """
    return text.replace("|", "\\|")


def _escape_html_entities(text: str) -> str:
    """Apply ``html.escape(text)`` for HTML output.

    Escapes ``&``, ``<``, ``>``, ``"``, ``'``.  Consumed by
    ``emit_html.py`` (012-05); defined here because this is the shared
    inline-rendering module (ARCH §2.1 F6).
    """
    return html.escape(text)


def _newlines_to_br(text: str) -> str:
    """Split on ``\\n`` and join with ``<br>`` (UC-12).

    No trailing ``<br>`` unless the input ends with ``\\n``.

    Example::

        _newlines_to_br("first\\nsecond") == "first<br>second"
        _newlines_to_br("line\\n")        == "line<br>"
    """
    return "<br>".join(text.split("\n"))


def _render_hyperlink(
    value: Any,
    href: str,
    *,
    mode: Literal["gfm", "html"],
    allowed_schemes: frozenset[str] | None,
    cell_addr: str | None = None,
) -> str:
    """Render a hyperlink cell with scheme-allowlist filter (D-A15 / R10a).

    The cell's **display text** is ``str(value or "")``, with pipe-escape
    and newline-to-``<br>`` applied before embedding in GFM / HTML.

    Scheme decision (R10a):
    - Parse ``urllib.parse.urlsplit(href).scheme.lower()``.
    - Empty scheme (relative URL like ``page.html``) → treated as
      ``"http"`` (R10a c).
    - ``allowed_schemes is None`` → allow all (wildcard sentinel).
    - ``allowed_schemes == frozenset()`` → block all.
    - Else: ``scheme in allowed_schemes`` → allow; otherwise block.

    If allowed:
    - ``mode == "gfm"``  → ``[text](href)`` (empty text → ``[](href)``).
    - ``mode == "html"`` → ``<a href="escaped_href">text</a>``.

    If blocked:
    - Emit ``UserWarning`` (with ``cell_addr`` prefix if provided).
    - Return plain ``value_text`` (no markup; cell content preserved).

    **xlsx_read hyperlink shape** (observed, 012-04): ``read_table`` with
    ``include_hyperlinks=True`` returns the URL as the cell value string
    (display text is replaced). Callers that want ``[text](url)`` output
    must pass the display text as ``value`` and the URL as ``href``
    separately. When both ``value`` and ``href`` are the same URL string
    (the common case with the current API), the GFM output is
    ``[https://example.com](https://example.com)`` — valid but redundant.
    A future dict-shape API would supply display text separately.
    """
    # Determine the scheme; empty scheme → treat as "http" (R10a c).
    scheme = urllib.parse.urlsplit(href).scheme.lower()
    if not scheme:
        scheme = "http"

    # Scheme decision.
    if allowed_schemes is None:
        allowed = True
    elif not allowed_schemes:  # frozenset() — block all
        allowed = False
    else:
        allowed = scheme in allowed_schemes

    # Display text with format-safe transforms.
    value_text = _escape_pipe_gfm(str(value or ""))
    value_text = _newlines_to_br(value_text)

    if allowed:
        if mode == "gfm":
            # M8 fix (iter 2 sec-HIGH completion): GFM hrefs containing
            # ')', '(', whitespace, '\n', '<', or '>' break the
            # [text](url) parenthesis-matching contract. CommonMark §6.3
            # angle-bracket form [text](<url>) permits parens inside
            # but NOT unescaped '<', '>', or LINE BREAKS. Iter-1 M8
            # patched `>` only — leaving `<`, `\n`, `\r`, `\t`
            # unescaped, which allowed a markdown-injection bypass of
            # the scheme-allowlist: an attacker-planted hyperlink with
            # `target="https://ok.com/\n[evil](javascript:alert(1))"`
            # (LF planted via raw XML edit) would end the angle-form
            # destination at the LF, then parse the remainder as fresh
            # markdown — surfacing a clickable `javascript:` link
            # despite the allowlist that already approved the `https`
            # half. Iter-2 fix: percent-encode the FULL set so the
            # angle-form remains a single URL token.
            if any(c in href for c in "()\n\r\t <>"):
                safe_href = (
                    href.replace("<", "%3C")
                        .replace(">", "%3E")
                        .replace("\n", "%0A")
                        .replace("\r", "%0D")
                        .replace("\t", "%09")
                )
                return f"[{value_text}](<{safe_href}>)"
            return f"[{value_text}]({href})"
        else:  # html
            safe_href = html.escape(href, quote=True)
            safe_text = html.escape(str(value or ""))
            safe_text = _newlines_to_br(safe_text)
            return f'<a href="{safe_href}">{safe_text}</a>'
    else:
        # Blocked: emit warning, return plain text.
        # H2 fix: HTML mode MUST apply `html.escape` to the value before
        # returning. Previously the blocked branch returned ``value_text``
        # which had only ``_escape_pipe_gfm`` + ``_newlines_to_br`` applied —
        # a value containing ``<script>...</script>`` would have survived raw
        # into a ``<td>`` element (XSS vector if a direct API caller bypassed
        # the dispatch-side scheme-allowlist filter). The dispatch boundary
        # normally drops blocked-scheme cells before they reach this branch,
        # so this is "defense in depth", but the contract demands it.
        if cell_addr is not None:
            msg = (
                f"cell {cell_addr}: hyperlink scheme {scheme!r} not in "
                f"allowlist; emitted text-only"
            )
        else:
            msg = f"hyperlink scheme {scheme!r} not in allowlist; emitted text-only"
        warnings.warn(msg, UserWarning, stacklevel=2)
        if mode == "html":
            safe_text = html.escape(str(value or ""))
            safe_text = _newlines_to_br(safe_text)
            return safe_text
        return value_text  # gfm path: pipe-escape already applied
