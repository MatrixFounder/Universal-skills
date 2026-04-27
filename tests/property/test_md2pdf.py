"""Property-based fuzz tests for skills/pdf/scripts/md2pdf.py (q-5)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from hypothesis import given

from strategies import markdown_doc


def _run_md2pdf(py: Path, script: Path, md: str, work: Path,
                ) -> subprocess.CompletedProcess:
    inp = work / "in.md"
    out = work / "out.pdf"
    inp.write_text(md, encoding="utf-8")
    return subprocess.run(
        [str(py), str(script), str(inp), str(out), "--no-mermaid"],
        capture_output=True, timeout=60,
    )


@given(md=markdown_doc)
def test_md2pdf_no_python_traceback(md: str,
                                    pdf_python: Path,
                                    pdf_md2pdf_py: Path) -> None:
    """For any input md2pdf either exits 0 with non-empty PDF, or exits
    non-zero with a stderr message — never a Python traceback.

    A traceback on stderr means the script failed to wrap an exception
    in the cross-5 envelope. That contract is part of the public CLI
    surface (wrappers parse stderr line-by-line as JSON).
    """
    # Per-example tempdir: pytest's tmp_path is function-scoped and
    # hypothesis (rightly) refuses to reuse it across generated inputs.
    with tempfile.TemporaryDirectory(prefix="prop-md2pdf-") as work:
        r = _run_md2pdf(pdf_python, pdf_md2pdf_py, md, Path(work))
        if r.returncode == 0:
            out = Path(work) / "out.pdf"
            assert out.exists() and out.stat().st_size > 0, \
                f"exit 0 but no PDF for input: {md!r}"
        else:
            assert b"Traceback" not in r.stderr, (
                f"crashed with traceback on input {md!r}\n"
                f"stderr: {r.stderr.decode(errors='replace')}"
            )
