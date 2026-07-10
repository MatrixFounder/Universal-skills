"""Tests for `fetch.py doctor` — readiness check (task 029.03, arch-016 §10.3).

Exercises:
- Exit codes (0 present / 7 absent) and the `--json` envelope shape.
- Import-free guarantee: a doctor run never imports `yt_dlp`.
- Secret safety: an API key is NEVER printed, only a boolean `key_present`.
- Human-mode output + exit code parity with `--json`.

All tests are offline. The yt-dlp presence/version probes are patched directly
on `install_components`; the ffmpeg/ASR-backend `shutil.which` probes are
patched via `install_components._have` so the suite is host-independent (does
not depend on what happens to be installed on the machine running it).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import fetch  # noqa: E402
import install_components as ic  # noqa: E402


def _patch_yt_dlp_present():
    return (
        mock.patch.object(ic, "_have_yt_dlp", return_value=True),
        mock.patch.object(ic, "yt_dlp_version", return_value="2026.3.17"),
    )


def _patch_yt_dlp_absent():
    return (
        mock.patch.object(ic, "_have_yt_dlp", return_value=False),
        mock.patch.object(ic, "yt_dlp_version", return_value=None),
    )


def _patch_no_local_asr():
    # `_have` backs ffmpeg + all three ASR-backend probes in `_components()` —
    # forcing it False makes the doctor report host-independent.
    return mock.patch.object(ic, "_have", return_value=False)


def _patch_ffmpeg_absent_asr_present():
    """ffmpeg absent; every OTHER `_have`-backed probe (macwhisper/whisper-cli/
    whisper-cpp) present — isolates the ffmpeg-specific remediation entry from
    the separate "no local ASR backend" hint so the two contracts (F1/F5/F11
    vs F2) can be locked independently."""

    def fake_have(cmd):
        return cmd != "ffmpeg"

    return mock.patch.object(ic, "_have", side_effect=fake_have)


def _patch_mw_and_ffmpeg_present_whisper_absent():
    """The flagship "correctly-provisioned box" from cycle-2's finding: mw +
    ffmpeg present, whisper-cli/whisper-cpp absent — ASR capability already
    resolves via mw, so the two missing ALTERNATIVE engines must be
    informational-only (never flow-blocking `remediation`)."""

    def fake_have(cmd):
        return cmd in ("mw", "ffmpeg")

    return mock.patch.object(ic, "_have", side_effect=fake_have)


def _patch_no_local_asr_but_ffmpeg_present():
    """ffmpeg present; every ASR-backend probe absent — isolates the
    no-local-ASR / cloud-aware contract from ffmpeg's own remediation entry
    (mirrors `_patch_ffmpeg_absent_asr_present`'s isolation, inverted)."""

    def fake_have(cmd):
        return cmd == "ffmpeg"

    return mock.patch.object(ic, "_have", side_effect=fake_have)


class _DoctorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # TC-03 guard: a prior test elsewhere in the suite must not leave
        # `yt_dlp` imported before we assert its absence.
        sys.modules.pop("yt_dlp", None)
        # Host-independence: a developer's local `scripts/.env` (git-ignored,
        # never present in CI) may carry a real TRANSCRIPT_FETCHER_OPENAI_API_KEY
        # for manual e2e runs. `doctor` intentionally loads `.env` (see
        # `fetch._run_doctor` docstring), so without this guard these tests
        # would read whatever secret happens to be on the developer's machine
        # instead of the value each test sets up explicitly.
        # Also force TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD=0 (029.03 review
        # carry-over): an exported shell var would otherwise flip
        # `components.cloud.allow_cloud` to True and flake
        # `test_key_never_printed_json`'s exact-dict assertion. (There is no
        # bare `ASR_ALLOW_CLOUD` fallback in `_config.asr_allow_cloud_default`
        # — only the prefixed key is honoured, so only it needs guarding.)
        env_patch = mock.patch.dict(
            os.environ,
            {
                "TRANSCRIPT_FETCHER_NO_DOTENV": "1",
                "TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD": "0",
            },
            clear=False,
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)


class TestDoctorExitCodes(_DoctorTestCase):
    def test_exit_0_and_json_shape_when_present(self) -> None:
        """TC-01: yt-dlp present -> exit 0, envelope shape + version populated."""
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor", "--json"])
        self.assertEqual(rc, 0)
        env = json.loads(buf.getvalue())
        self.assertEqual(env["v"], 1)
        self.assertIs(env["ready"], True)
        self.assertIs(env["components"]["yt-dlp"]["present"], True)
        self.assertEqual(env["components"]["yt-dlp"]["version"], "2026.3.17")
        self.assertIn("interpreter", env)
        self.assertIn("in_venv", env)

    def test_exit_7_when_absent(self) -> None:
        """TC-02: yt-dlp absent -> exit 7, ready False, install.sh remediation."""
        buf = io.StringIO()
        absent, version = _patch_yt_dlp_absent()
        with absent, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor", "--json"])
        self.assertEqual(rc, 7)
        env = json.loads(buf.getvalue())
        self.assertIs(env["ready"], False)
        self.assertIs(env["components"]["yt-dlp"]["present"], False)
        self.assertIsNone(env["components"]["yt-dlp"]["version"])
        self.assertTrue(env["remediation"])
        self.assertTrue(
            any("install.sh" in hint for hint in env["remediation"]),
            env["remediation"],
        )

    def test_human_mode_exit_0_when_present(self) -> None:
        """TC-05: human mode (no --json) mirrors the --json exit code."""
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("transcript-fetcher", out)
        # Must not be JSON in human mode.
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_human_mode_exit_7_when_absent(self) -> None:
        buf = io.StringIO()
        absent, version = _patch_yt_dlp_absent()
        with absent, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 7)
        self.assertIn("Remediation", buf.getvalue())


class TestDoctorImportFree(_DoctorTestCase):
    def test_yt_dlp_never_imported_present(self) -> None:
        """TC-03: doctor must never `import yt_dlp`, even when reporting it present."""
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            fetch.main(["doctor", "--json"])
        self.assertNotIn("yt_dlp", sys.modules)

    def test_yt_dlp_never_imported_absent(self) -> None:
        buf = io.StringIO()
        absent, version = _patch_yt_dlp_absent()
        with absent, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            fetch.main(["doctor", "--json"])
        self.assertNotIn("yt_dlp", sys.modules)

    def test_yt_dlp_never_imported_unmocked(self) -> None:
        """Same guard against the REAL (unmocked) `_components()` probe path —
        the refactor, not just the test double, must stay import-free."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.main(["doctor", "--json"])
        self.assertNotIn("yt_dlp", sys.modules)


class TestDoctorSecretSafety(_DoctorTestCase):
    def test_key_never_printed_json(self) -> None:
        """TC-04 (JSON): API key value never leaks; only a boolean key_present."""
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with mock.patch.dict(
            os.environ, {"TRANSCRIPT_FETCHER_OPENAI_API_KEY": "sk-SEKRET"}, clear=False
        ), present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            fetch.main(["doctor", "--json"])
        out = buf.getvalue()
        self.assertNotIn("sk-SEKRET", out)
        env = json.loads(out)
        self.assertEqual(
            env["components"]["cloud"], {"key_present": True, "allow_cloud": False}
        )

    def test_key_never_printed_human(self) -> None:
        """TC-04 (human): same guarantee in the human-readable report."""
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with mock.patch.dict(
            os.environ, {"TRANSCRIPT_FETCHER_OPENAI_API_KEY": "sk-SEKRET"}, clear=False
        ), present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            fetch.main(["doctor"])
        out = buf.getvalue()
        self.assertNotIn("sk-SEKRET", out)
        self.assertIn("cloud ASR key present", out)

    def test_cloud_key_absent_by_default(self) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with mock.patch.dict(os.environ, {}, clear=False), present, version, \
             _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            os.environ.pop("TRANSCRIPT_FETCHER_OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            fetch.main(["doctor", "--json"])
        env = json.loads(buf.getvalue())
        self.assertFalse(env["components"]["cloud"]["key_present"])


class TestDoctorRemediationContract(_DoctorTestCase):
    """F1/F2/F5/F11 lock (cycle 1), REFINED in cycle 3: ffmpeg's absence must
    always surface a remediation line (even with a working local ASR
    backend), the human summary must distinguish "nothing to report" from
    "core ready, gaps remain", and `remediation` names ONLY flow-blocking
    gaps (yt-dlp / ffmpeg / no-ASR-capability-at-all) — an individual missing
    ALTERNATIVE local ASR engine, or a fully cloud-configured no-local-ASR
    box, must NOT appear in `remediation` (cycle-2 found the prior "every
    missing component" contract made `remediation == []` / `✓ Ready.`
    unattainable on any correctly-provisioned box)."""

    def test_ffmpeg_absent_json_remediation_names_ffmpeg(self) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_ffmpeg_absent_asr_present(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor", "--json"])
        self.assertEqual(rc, 0)
        env = json.loads(buf.getvalue())
        self.assertTrue(env["remediation"])
        self.assertTrue(
            any("ffmpeg" in hint.lower() for hint in env["remediation"]),
            env["remediation"],
        )
        # The no-local-ASR hint must NOT ALSO fire — an ASR backend IS present
        # in this fixture, only ffmpeg is absent.
        self.assertFalse(
            any("no local asr backend" in hint.lower() for hint in env["remediation"]),
            env["remediation"],
        )

    def test_ffmpeg_absent_human_report_is_core_ready_not_bare_ready(self) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_ffmpeg_absent_asr_present(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertNotIn("✓ Ready.", out)
        self.assertIn("Core ready", out)
        self.assertIn("Remediation:", out)

    def test_cloud_configured_no_local_asr_remediation_is_empty(self) -> None:
        # (FIX-2) ffmpeg present + fully-configured cloud + no local ASR: the
        # ASR chain genuinely resolves (via cloud) -> no flow-blocking gap ->
        # `remediation` is EMPTY, not carrying an informational note.
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with mock.patch.dict(
            os.environ,
            {
                "TRANSCRIPT_FETCHER_OPENAI_API_KEY": "sk-test",
                "TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD": "1",
            },
            clear=False,
        ), present, version, _patch_no_local_asr_but_ffmpeg_present(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor", "--json"])
        self.assertEqual(rc, 0)
        env = json.loads(buf.getvalue())
        self.assertEqual(env["remediation"], [])

    def test_cloud_configured_no_local_asr_human_report_has_note_and_ready(
        self,
    ) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with mock.patch.dict(
            os.environ,
            {
                "TRANSCRIPT_FETCHER_OPENAI_API_KEY": "sk-test",
                "TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD": "1",
            },
            clear=False,
        ), present, version, _patch_no_local_asr_but_ffmpeg_present(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        # (FIX-2) The empty-remediation all-clear still prints, PLUS an
        # informational note explaining the cloud fallback — not a
        # `Remediation:` demand.
        self.assertIn("✓ Ready.", out)
        self.assertNotIn("Remediation:", out)
        self.assertIn("cloud ASR is configured", out)
        # Missing local engines (mw/whisper-cli/whisper-cpp) still show as
        # informational `->` install-hint lines under their own [✗] rows.
        self.assertIn("→", out)

    def test_local_asr_alternative_missing_json_remediation_empty(self) -> None:
        # (FIX-2) The flagship "correctly-provisioned box": mw + ffmpeg
        # present, whisper-cli/whisper-cpp absent, no cloud. ASR capability
        # already resolves via mw -> the two missing ALTERNATIVE engines are
        # never flow-blocking -> remediation == [].
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_mw_and_ffmpeg_present_whisper_absent(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor", "--json"])
        self.assertEqual(rc, 0)
        env = json.loads(buf.getvalue())
        self.assertEqual(env["remediation"], [])

    def test_local_asr_alternative_missing_human_report_is_ready(self) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_mw_and_ffmpeg_present_whisper_absent(), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("✓ Ready.", out)
        self.assertNotIn("Core ready", out)
        self.assertNotIn("Remediation:", out)

    def test_missing_optional_engine_shows_arrow_hint_line_in_human_report(
        self,
    ) -> None:
        # (FIX-2) A missing ALTERNATIVE engine never lands in `remediation`
        # but must still surface as an indented `->` install-hint line under
        # its own [✗] row (mirrors `install_components._print_report`).
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_mw_and_ffmpeg_present_whisper_absent(), \
             contextlib.redirect_stdout(buf):
            fetch.main(["doctor"])
        out = buf.getvalue()
        with mock.patch.object(
            ic, "_have", side_effect=lambda cmd: cmd in ("mw", "ffmpeg")
        ):
            comps = {c["key"]: c for c in ic._components()}
        for key in ("whisper-cli", "whisper-cpp"):
            self.assertFalse(comps[key]["present"], key)
            self.assertIn(f"→ {comps[key]['install_hint']}", out)

    def test_no_asr_no_cloud_hint_states_exit_7_consequence(self) -> None:
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, _patch_no_local_asr(), contextlib.redirect_stdout(buf):
            fetch.main(["doctor", "--json"])
        env = json.loads(buf.getvalue())
        self.assertTrue(
            any("will exit 7" in h.lower() for h in env["remediation"]),
            env["remediation"],
        )

    def test_all_present_remediation_empty_and_ready_line(self) -> None:
        # Everything present (yt-dlp + a full `_have` True) -> remediation []
        # and the bare "✓ Ready." line.
        buf = io.StringIO()
        present, version = _patch_yt_dlp_present()
        with present, version, mock.patch.object(ic, "_have", return_value=True), \
             contextlib.redirect_stdout(buf):
            rc = fetch.main(["doctor"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("✓ Ready.", out)
        self.assertNotIn("Core ready", out)
        self.assertNotIn("Remediation:", out)


if __name__ == "__main__":
    unittest.main()
