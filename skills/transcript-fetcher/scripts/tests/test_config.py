"""Tests for `_config` — endpoint/model/tool resolution + SECURE secret storage.

The secret-storage behaviour (0600-or-refuse, symlink rejection, opt-out,
process-env-wins) is the security contract the skill's API key relies on, so it
is locked here.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _config as cfg  # noqa: E402

P = cfg.PREFIX


class TestTypedAccessors(unittest.TestCase):
    def test_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cfg.openai_base_url(), "https://api.openai.com/v1")
            self.assertEqual(
                cfg.openai_transcribe_endpoint(),
                "https://api.openai.com/v1/audio/transcriptions",
            )
            self.assertEqual(cfg.openai_model(), "whisper-1")
            self.assertEqual(cfg.tool_bin("MW", "mw"), "mw")
            self.assertEqual(cfg.ffmpeg_bin(), "ffmpeg")
            self.assertEqual(cfg.asr_timeout_sec(1800), 1800)
            self.assertFalse(cfg.asr_allow_cloud_default())

    def test_base_and_path_combine(self) -> None:
        with mock.patch.dict(os.environ, {
            P + "OPENAI_BASE_URL": "https://api.groq.com/openai/v1/",
            P + "OPENAI_TRANSCRIBE_PATH": "audio/transcriptions",
        }, clear=True):
            self.assertEqual(
                cfg.openai_transcribe_endpoint(),
                "https://api.groq.com/openai/v1/audio/transcriptions",
            )

    def test_full_endpoint_override_wins(self) -> None:
        with mock.patch.dict(os.environ, {
            P + "OPENAI_BASE_URL": "https://ignored/v1",
            P + "OPENAI_TRANSCRIBE_ENDPOINT": "https://self.hosted/whisper",
        }, clear=True):
            self.assertEqual(cfg.openai_transcribe_endpoint(), "https://self.hosted/whisper")

    def test_overrides(self) -> None:
        with mock.patch.dict(os.environ, {
            P + "OPENAI_MODEL": "whisper-large-v3",
            P + "MW_BIN": "/opt/mw",
            P + "FFMPEG_BIN": "/opt/ffmpeg",
            P + "ASR_TIMEOUT_SEC": "42",
            P + "ASR_ALLOW_CLOUD": "yes",
        }, clear=True):
            self.assertEqual(cfg.openai_model(), "whisper-large-v3")
            self.assertEqual(cfg.tool_bin("MW", "mw"), "/opt/mw")
            self.assertEqual(cfg.ffmpeg_bin(), "/opt/ffmpeg")
            self.assertEqual(cfg.asr_timeout_sec(1800), 42)
            self.assertTrue(cfg.asr_allow_cloud_default())

    def test_invalid_timeout_falls_back(self) -> None:
        with mock.patch.dict(os.environ, {P + "ASR_TIMEOUT_SEC": "not-a-number"}, clear=True):
            self.assertEqual(cfg.asr_timeout_sec(1800), 1800)

    def test_api_key_prefers_prefixed_then_conventional(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "conv"}, clear=True):
            self.assertEqual(cfg.openai_api_key(), "conv")
        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "conv", P + "OPENAI_API_KEY": "prefixed",
        }, clear=True):
            self.assertEqual(cfg.openai_api_key(), "prefixed")


class TestSilenceConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(cfg.silence_removal_default())   # ON by default
            self.assertEqual(cfg.silence_threshold_db(), "-45dB")
            self.assertEqual(cfg.silence_min_gap_sec(), 1.0)
            self.assertEqual(cfg.silence_keep_sec(), 0.3)

    def test_removal_opt_out(self) -> None:
        with mock.patch.dict(os.environ, {P + "SILENCE_REMOVAL": "0"}, clear=True):
            self.assertFalse(cfg.silence_removal_default())

    def test_threshold_normalises_and_validates(self) -> None:
        with mock.patch.dict(os.environ, {P + "SILENCE_THRESHOLD": "-40"}, clear=True):
            self.assertEqual(cfg.silence_threshold_db(), "-40dB")
        with mock.patch.dict(os.environ, {P + "SILENCE_THRESHOLD": "-30dB"}, clear=True):
            self.assertEqual(cfg.silence_threshold_db(), "-30dB")
        # garbage → default (never an injection vector in the filter string)
        with mock.patch.dict(os.environ, {P + "SILENCE_THRESHOLD": "evil;rm"}, clear=True):
            self.assertEqual(cfg.silence_threshold_db(), "-45dB")

    def test_numeric_knobs_validate(self) -> None:
        with mock.patch.dict(os.environ, {
            P + "SILENCE_MIN_GAP_SEC": "2.5",
            P + "SILENCE_KEEP_SEC": "0.5",
        }, clear=True):
            self.assertEqual(cfg.silence_min_gap_sec(), 2.5)
            self.assertEqual(cfg.silence_keep_sec(), 0.5)
        with mock.patch.dict(os.environ, {
            P + "SILENCE_MIN_GAP_SEC": "nope",
            P + "SILENCE_KEEP_SEC": "-1",
        }, clear=True):
            self.assertEqual(cfg.silence_min_gap_sec(), 1.0)   # bad → default
            self.assertEqual(cfg.silence_keep_sec(), 0.3)      # negative → default


class TestLoadSkillEnvSecurity(unittest.TestCase):
    @staticmethod
    def _write_env(d: str, body: str, mode: int = 0o600) -> Path:
        p = Path(d) / ".env"
        p.write_text(body, encoding="utf-8")
        os.chmod(p, mode)
        return p

    def test_loads_keys_into_environ(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_env(
                d, "# c\nTRANSCRIPT_FETCHER_OPENAI_MODEL=whisper-x\n"
                   'export TRANSCRIPT_FETCHER_MW_BIN="/q/mw"  # note\n')
            with mock.patch.dict(os.environ, {P + "NO_DOTENV": ""}, clear=False):
                os.environ.pop(P + "OPENAI_MODEL", None)
                os.environ.pop(P + "MW_BIN", None)
                cfg.load_skill_env((p,))
                self.assertEqual(os.environ.get(P + "OPENAI_MODEL"), "whisper-x")
                self.assertEqual(os.environ.get(P + "MW_BIN"), "/q/mw")  # quotes+export+comment stripped

    def test_process_env_wins(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_env(d, "TRANSCRIPT_FETCHER_OPENAI_MODEL=fromfile\n")
            with mock.patch.dict(os.environ, {
                P + "NO_DOTENV": "", P + "OPENAI_MODEL": "fromenv",
            }, clear=False):
                cfg.load_skill_env((p,))
                self.assertEqual(os.environ[P + "OPENAI_MODEL"], "fromenv")

    def test_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_env(d, "TRANSCRIPT_FETCHER_FOO=bar\n")
            with mock.patch.dict(os.environ, {P + "NO_DOTENV": "1"}, clear=False):
                os.environ.pop(P + "FOO", None)
                cfg.load_skill_env((p,))
                self.assertIsNone(os.environ.get(P + "FOO"))

    def test_refuses_group_world_accessible(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_env(d, "TRANSCRIPT_FETCHER_SECRET=should-not-load\n", mode=0o644)
            with mock.patch.dict(os.environ, {P + "NO_DOTENV": ""}, clear=False):
                os.environ.pop(P + "SECRET", None)
                cfg.load_skill_env((p,))
                self.assertIsNone(os.environ.get(P + "SECRET"))

    def test_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            target = self._write_env(d, "TRANSCRIPT_FETCHER_SECRET=nope\n")
            link = Path(d) / "link.env"
            os.symlink(target, link)
            with mock.patch.dict(os.environ, {P + "NO_DOTENV": ""}, clear=False):
                os.environ.pop(P + "SECRET", None)
                cfg.load_skill_env((link,))
                self.assertIsNone(os.environ.get(P + "SECRET"))

    def test_missing_file_is_noop(self) -> None:
        with mock.patch.dict(os.environ, {P + "NO_DOTENV": ""}, clear=False):
            cfg.load_skill_env((Path("/nonexistent/.env"),))  # must not raise


class TestDotenvValue(unittest.TestCase):
    def test_quoted_and_inline_comment(self) -> None:
        self.assertEqual(cfg._dotenv_value('"sk-abc"  trailing'), "sk-abc")
        self.assertEqual(cfg._dotenv_value("sk-abc   # note"), "sk-abc")
        self.assertEqual(cfg._dotenv_value("  plain  "), "plain")


if __name__ == "__main__":
    unittest.main()
