"""Property-based fuzz tests for skills/docx/scripts/md2docx.js (q-5)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from hypothesis import given

from strategies import markdown_doc


def _run_md2docx(node: str, script: Path, md: str, work: Path,
                 ) -> subprocess.CompletedProcess:
    inp = work / "in.md"
    out = work / "out.docx"
    inp.write_text(md, encoding="utf-8")
    return subprocess.run(
        [node, str(script), str(inp), str(out)],
        capture_output=True, timeout=60,
    )


@given(md=markdown_doc)
def test_md2docx_no_node_traceback(md: str,
                                   docx_node: str,
                                   docx_md2docx_js: Path) -> None:
    """md2docx.js either exits 0 producing a non-empty .docx, or exits
    non-zero with a controlled error — never a node uncaught exception
    stack trace.
    """
    with tempfile.TemporaryDirectory(prefix="prop-md2docx-") as work:
        r = _run_md2docx(docx_node, docx_md2docx_js, md, Path(work))
        if r.returncode == 0:
            out = Path(work) / "out.docx"
            assert out.exists() and out.stat().st_size > 0, \
                f"exit 0 but no docx for input: {md!r}"
        else:
            stderr = r.stderr.decode(errors="replace")
            assert "node:internal" not in stderr and \
                   "UnhandledPromiseRejection" not in stderr, (
                f"node crashed on input {md!r}\nstderr: {stderr}"
            )
