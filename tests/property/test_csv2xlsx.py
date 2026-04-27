"""Property-based fuzz tests for skills/xlsx/scripts/csv2xlsx.py (q-5)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from hypothesis import given

from strategies import csv_doc


def _run_csv2xlsx(py: Path, script: Path, csv: str, work: Path,
                  ) -> subprocess.CompletedProcess:
    inp = work / "in.csv"
    out = work / "out.xlsx"
    inp.write_text(csv, encoding="utf-8")
    return subprocess.run(
        [str(py), str(script), str(inp), str(out)],
        capture_output=True, timeout=60,
    )


@given(csv=csv_doc)
def test_csv2xlsx_no_python_traceback(csv: str,
                                      xlsx_python: Path,
                                      xlsx_csv2xlsx_py: Path) -> None:
    """csv2xlsx must never crash with a Python traceback. Either it
    produces a valid xlsx (exit 0, non-empty output) or it exits
    non-zero with a wrapped error message.
    """
    with tempfile.TemporaryDirectory(prefix="prop-csv2xlsx-") as work:
        r = _run_csv2xlsx(xlsx_python, xlsx_csv2xlsx_py, csv, Path(work))
        if r.returncode == 0:
            out = Path(work) / "out.xlsx"
            assert out.exists() and out.stat().st_size > 0, \
                f"exit 0 but no xlsx for input: {csv!r}"
        else:
            assert b"Traceback" not in r.stderr, (
                f"crashed with traceback on input {csv!r}\n"
                f"stderr: {r.stderr.decode(errors='replace')}"
            )
