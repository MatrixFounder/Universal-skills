"""FC-3 bridge — Python → Node turndown core (ARCH §2.1, §5.2).

Spawns ``node html2md_core.js`` as a pure ``stdin → stdout`` filter: cleaned HTML
in, GFM Markdown out. No shell, bounded timeout. ``html2md_core.js`` is the
docx-mastered, ``diff -q``-gated converter (lifted verbatim from ``docx2md.js``).
"""
from __future__ import annotations

import os
import subprocess

from .exceptions import ConvertFailed

# scripts/html2md_convert.js — the html2md-owned turndown wrapper (ARIA tables +
# button strip) over the docx-mastered html2md_core.js. Sibling of the package dir.
_CORE_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "html2md_convert.js"
)
_TIMEOUT_S = 120


def html_to_markdown(html: str) -> str:
    """Convert cleaned HTML → GFM Markdown via the Node turndown core.

    Raises:
        ConvertFailed: node missing, the core errored, or it timed out.
    """
    try:
        proc = subprocess.run(
            ["node", _CORE_JS],
            input=html,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise ConvertFailed(
            "node executable not found — install Node.js (see scripts/install.sh).",
            details={"reason": "node-missing"},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ConvertFailed(
            f"html2md_core timed out after {_TIMEOUT_S}s.",
            details={"timeout_s": _TIMEOUT_S},
        ) from exc
    if proc.returncode != 0:
        raise ConvertFailed(
            f"html2md_core failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}",
            details={"returncode": proc.returncode},
        )
    return proc.stdout
