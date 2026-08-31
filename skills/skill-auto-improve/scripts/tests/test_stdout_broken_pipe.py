"""A reader that closes early must not rewrite `auto_improve.py`'s exit status.

CPython flushes `sys.stdout` again while shutting down. If that flush hits a dead
pipe it prints `Exception ignored while flushing sys.stdout` on stderr and
**replaces the exit status with 120**. That matters here beyond tidiness:
`backends/claude.py` turns any non-zero return code from a driven script into
`RuntimeError`, so a truncating reader upstream becomes a fabricated failure.

Measured on this machine (pipe capacity 65,536 bytes): a payload of ~90-130 KB
exits 120, a larger one escapes as a raw traceback and exits 1. Both bands are
covered, because `print()` alone does not raise in the first one — the EPIPE only
surfaces at flush, so a `try/except BrokenPipeError` around a bare `print()` is
green in the large band and still broken in the 120 band.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHILD = Path(__file__).resolve().parent / "_stdout_pipe_child.py"

MID_BAND = 95_000    # renders to ~105-125 KB — the exit-120 band
LARGE = 400_000      # renders to >400 KB — the raw-traceback band


def run_with_dead_reader(target_bytes, workdir):
    """Run the child, consume 20 bytes, close the pipe. Returns (rc, stderr).

    `bufsize=0` is load-bearing: the default BufferedReader drains 8 KiB per
    `read()`, and consuming that much moves the EPIPE inside `print()`, where a
    bare try/except already catches it. Twenty raw bytes is what `... | head -c 20`
    does and is the case where only the shutdown flush fails.
    """
    proc = subprocess.Popen(
        [sys.executable, str(CHILD), str(target_bytes), str(workdir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    got = b""
    while len(got) < 20:
        chunk = proc.stdout.read(20 - len(got))
        if not chunk:
            break
        got += chunk
    proc.stdout.close()
    stderr = proc.stderr.read()
    proc.stderr.close()
    return proc.wait(), stderr.decode("utf-8", "replace")


class TestAutoImproveStdout(unittest.TestCase):
    def _assert_clean(self, target_bytes):
        with tempfile.TemporaryDirectory() as tmp:
            rc, err = run_with_dead_reader(target_bytes, tmp)
        self.assertNotEqual(rc, 120, "the shutdown flush overrode the exit status")
        self.assertEqual(rc, 0, f"stderr was:\n{err}")
        self.assertNotIn("Exception ignored", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(err, "", f"unexpected stderr:\n{err}")

    def test_a_dead_reader_mid_band_keeps_the_scripts_own_exit_code(self):
        self._assert_clean(MID_BAND)

    def test_a_dead_reader_large_payload_keeps_the_scripts_own_exit_code(self):
        self._assert_clean(LARGE)


if __name__ == "__main__":
    unittest.main()
