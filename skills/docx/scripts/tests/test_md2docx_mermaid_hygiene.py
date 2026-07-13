"""DOCX-MERMAID-EXECSYNC regression: mermaid rendering must not touch the CWD.

The `.mmd`/`.png` pair used to be written as predictable `temp_N.*` names into
the CURRENT working directory and the render command was a shell string passed
to `execSync`. The fix renders inside an unpredictable `mkdtemp` scratch (rm'd
in `finally`) and execs `npx` in argv form. These tests drive the FAILURE path
with a stubbed `npx` (exit 1) — no network, no real mermaid-cli — because that
is exactly the path that used to leak `temp_1.mmd`.

Run::  cd skills/docx/scripts && ./.venv/bin/python -m unittest tests.test_md2docx_mermaid_hygiene -v
"""

import os
import stat
import subprocess
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
MD2DOCX = os.path.join(SCRIPTS, "md2docx.js")

_FIXTURE_MD = """# Mermaid Hygiene Fixture

```mermaid
graph TD; A-->B;
```

A paragraph after the diagram.
"""


class TestMermaidCwdHygiene(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name
        stub_dir = os.path.join(self.cwd, "stub")
        os.mkdir(stub_dir)
        stub = os.path.join(stub_dir, "npx")
        with open(stub, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
        self.env = dict(os.environ)
        self.env["PATH"] = stub_dir + os.pathsep + self.env["PATH"]
        with open(os.path.join(self.cwd, "t.md"), "w", encoding="utf-8") as f:
            f.write(_FIXTURE_MD)

    def _convert(self):
        return subprocess.run(
            ["node", MD2DOCX, "t.md", "out.docx"],
            cwd=self.cwd, env=self.env, capture_output=True, text=True,
            timeout=120,
        )

    def test_failed_render_leaves_cwd_clean(self):
        r = self._convert()
        self.assertEqual(r.returncode, 0, r.stderr)
        leaked = [n for n in os.listdir(self.cwd)
                  if n.endswith((".mmd", ".png")) or n.startswith("temp_")]
        self.assertEqual(leaked, [], "mermaid temps must never land in the CWD")

    def test_failed_render_still_produces_docx(self):
        r = self._convert()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(self.cwd, "out.docx")
        self.assertTrue(os.path.exists(out),
                        "conversion must survive a failed diagram render")
        self.assertGreater(os.path.getsize(out), 0)
