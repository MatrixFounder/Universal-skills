"""Unit tests for `_soffice.run(profile_seed=...)` — no LibreOffice needed.

Why profile_seed exists: LibreOffice (observed on 26.2) honours the
FIRST `-env:UserInstallation=` argument on the command line. `run()`
always injects its own throwaway profile first, so the historical
pattern of appending a second `-env:UserInstallation=` via `args`
(used by the old macro:/// callers) is silently ignored — the caller's
profile is never read, soffice still exits 0, and the intended action
simply does not happen. `profile_seed` writes caller-provided files
INTO the throwaway profile `run()` creates — the only profile
LibreOffice actually uses.

These tests mock `subprocess.run` and inspect the profile at the
moment soffice would be launched (the TemporaryDirectory is gone
afterwards).

Run:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_soffice_profile_seed
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse
from urllib.request import url2pathname

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent  # skills/<skill>/scripts
sys.path.insert(0, str(SCRIPTS))

import _soffice  # noqa: E402


class TestProfileSeed(unittest.TestCase):
    def _run_capturing_profile(self, **run_kwargs):
        """Invoke _soffice.run with a mocked subprocess and return what
        the profile looked like at launch time."""
        captured: dict = {}

        def fake_subprocess_run(cmd, **_kw):
            env_args = [a for a in cmd if isinstance(a, str)
                        and a.startswith("-env:UserInstallation=")]
            if not env_args:
                # Not the soffice launch: in AF_UNIX-blocked sandboxes
                # (or with LO_SHIM_FORCE=1) _soffice.run() also shells
                # out to the shim build.sh and `codesign` through
                # subprocess.run — swallow those instead of crashing.
                return subprocess.CompletedProcess(cmd, 0, "", "")
            captured["env_args"] = env_args
            profile = Path(url2pathname(urlparse(env_args[0].split("=", 1)[1]).path))
            captured["files"] = {
                str(p.relative_to(profile)): p.read_text(encoding="utf-8")
                for p in profile.rglob("*")
                if p.is_file()
            }
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with mock.patch.object(_soffice, "find_soffice", return_value="/fake/soffice"), \
             mock.patch.object(_soffice.subprocess, "run", side_effect=fake_subprocess_run):
            _soffice.run(["--convert-to", "xlsx"], **run_kwargs)
        return captured

    def test_seed_files_written_into_active_profile(self) -> None:
        cap = self._run_capturing_profile(
            profile_seed={
                "user/registrymodifications.xcu": "<seed/>",
                "user/basic/Standard/Module1.xba": "<module/>",
            }
        )
        self.assertEqual(cap["files"].get("user/registrymodifications.xcu"), "<seed/>")
        self.assertEqual(cap["files"].get("user/basic/Standard/Module1.xba"), "<module/>")

    def test_exactly_one_user_installation_arg(self) -> None:
        """run() must own the profile: a single -env:UserInstallation.
        (A second one appended via args is ignored by LO 26.2 — that
        silent-loser pattern is exactly what profile_seed replaces.)"""
        cap = self._run_capturing_profile(
            profile_seed={"user/registrymodifications.xcu": "x"}
        )
        self.assertEqual(len(cap["env_args"]), 1)

    def test_no_seed_leaves_profile_empty(self) -> None:
        cap = self._run_capturing_profile()
        self.assertEqual(cap["files"], {})

    def test_escaping_relative_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._run_capturing_profile(profile_seed={"../escape.txt": "x"})

    def test_absolute_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._run_capturing_profile(profile_seed={"/etc/evil": "x"})

    def test_convert_to_forwards_profile_seed(self) -> None:
        """convert_to() must pass profile_seed through to run()."""
        captured: dict = {}

        def fake_subprocess_run(cmd, **_kw):
            env_args = [a for a in cmd if isinstance(a, str)
                        and a.startswith("-env:UserInstallation=")]
            if not env_args:
                # shim build.sh / codesign side calls — not the launch.
                return subprocess.CompletedProcess(cmd, 0, "", "")
            profile = Path(url2pathname(urlparse(env_args[0].split("=", 1)[1]).path))
            seed = profile / "user" / "registrymodifications.xcu"
            captured["seed"] = seed.read_text(encoding="utf-8") if seed.is_file() else None
            # Emulate LibreOffice producing the converted file.
            out_flag = cmd.index("--outdir")
            out_dir = Path(cmd[out_flag + 1])
            src = Path(cmd[-1])
            (out_dir / f"{src.stem}.xlsx").write_bytes(b"stub")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.xlsx"
            src.write_bytes(b"stub-in")
            with mock.patch.object(_soffice, "find_soffice", return_value="/fake/soffice"), \
                 mock.patch.object(_soffice.subprocess, "run", side_effect=fake_subprocess_run):
                produced = _soffice.convert_to(
                    src, Path(tmp) / "out", "xlsx",
                    profile_seed={"user/registrymodifications.xcu": "<via-convert-to/>"},
                )
            self.assertEqual(captured["seed"], "<via-convert-to/>")
            self.assertTrue(produced.name.endswith(".xlsx"))


if __name__ == "__main__":
    unittest.main()
