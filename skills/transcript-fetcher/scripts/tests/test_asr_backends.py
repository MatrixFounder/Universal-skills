"""Offline tests for the pluggable ASR backend layer.

No real engine is invoked: ``shutil.which`` / ``subprocess`` / ``urlopen`` are
mocked. Covers availability probing, the priority-ordered fallback chain,
MissingDependency vs all-failed semantics, the MacWhisper argv shape, and the
cloud backend's endpoint/header/encoding.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import asr  # noqa: E402
from asr import macwhisper, openai_api, whisper_cli, whisper_cpp  # noqa: E402
from asr._base import ASRBackend, ASRError, ASRResult  # noqa: E402
from sources._stat import MissingDependencyError, TranscriptFetchError  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class _Fake(ASRBackend):
    """A controllable backend for fallback-chain tests."""

    def __init__(self, name, avail, result=None, error=None):
        super().__init__()
        self.name = name
        self._avail = avail
        self._result = result
        self._error = error
        self.called = False

    def available(self) -> bool:
        return self._avail

    def transcribe(self, audio_path, *, lang=None):
        self.called = True
        if self._error is not None:
            raise self._error
        return self._result


class TestAvailability(unittest.TestCase):
    def test_macwhisper_probe(self) -> None:
        with mock.patch.object(macwhisper.shutil, "which", return_value="/usr/local/bin/mw"):
            self.assertTrue(macwhisper.MacWhisperBackend().available())
        with mock.patch.object(macwhisper.shutil, "which", return_value=None):
            self.assertFalse(macwhisper.MacWhisperBackend().available())

    def test_whisper_cli_needs_both_whisper_and_ffmpeg(self) -> None:
        which = {"whisper": "/x/whisper", "ffmpeg": "/x/ffmpeg"}
        with mock.patch.object(whisper_cli.shutil, "which", side_effect=which.get):
            self.assertTrue(whisper_cli.WhisperCLIBackend().available())
        with mock.patch.object(whisper_cli.shutil, "which",
                               side_effect={"whisper": "/x/whisper"}.get):
            self.assertFalse(whisper_cli.WhisperCLIBackend().available())  # no ffmpeg

    def test_whisper_cpp_needs_bin_ffmpeg_and_model(self) -> None:
        which = {"whisper-cli": "/x/whisper-cli", "ffmpeg": "/x/ffmpeg"}
        with mock.patch.object(whisper_cpp.shutil, "which", side_effect=which.get):
            self.assertFalse(whisper_cpp.WhisperCppBackend().available())  # no model
            self.assertTrue(
                whisper_cpp.WhisperCppBackend(model="/m/ggml.bin").available()
            )

    def test_openai_is_opt_in(self) -> None:
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-x"}, clear=False):
            self.assertFalse(openai_api.OpenAIWhisperBackend(allow_cloud=False).available())
            self.assertTrue(openai_api.OpenAIWhisperBackend(allow_cloud=True).available())
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(openai_api.OpenAIWhisperBackend(allow_cloud=True).available())


class TestFallbackChain(unittest.TestCase):
    def test_no_backend_available_raises_missing_dependency(self) -> None:
        with mock.patch.object(asr, "build_backends",
                               return_value=[_Fake("a", False), _Fake("b", False)]):
            with self.assertRaises(MissingDependencyError):
                asr.transcribe_with_fallback(Path("/x/a.m4a"))

    def test_falls_through_to_next_on_engine_error(self) -> None:
        good = ASRResult(text="ok", backend_name="b")
        b1 = _Fake("a", True, error=ASRError("a boom"))
        b2 = _Fake("b", True, result=good)
        logs: list[str] = []
        with mock.patch.object(asr, "build_backends", return_value=[b1, b2]):
            res = asr.transcribe_with_fallback(Path("/x/a.m4a"), log=logs.append)
        self.assertEqual(res.text, "ok")
        self.assertTrue(b1.called and b2.called)
        self.assertTrue(any("Using MacWhisper" in m for m in logs) or
                        any("Using" in m for m in logs))

    def test_all_available_fail_raises_transcript_fetch_error(self) -> None:
        b1 = _Fake("a", True, error=ASRError("a boom"))
        b2 = _Fake("b", True, error=ASRError("b boom"))
        with mock.patch.object(asr, "build_backends", return_value=[b1, b2]):
            with self.assertRaises(TranscriptFetchError):
                asr.transcribe_with_fallback(Path("/x/a.m4a"))

    def test_priority_order_first_available_wins(self) -> None:
        first = _Fake("first", True, result=ASRResult(text="1", backend_name="first"))
        second = _Fake("second", True, result=ASRResult(text="2", backend_name="second"))
        with mock.patch.object(asr, "build_backends", return_value=[first, second]):
            res = asr.transcribe_with_fallback(Path("/x/a.m4a"))
        self.assertEqual(res.backend_name, "first")
        self.assertFalse(second.called)


class TestMacWhisperArgv(unittest.TestCase):
    def test_argv_shape_and_success(self) -> None:
        with mock.patch.object(macwhisper.MacWhisperBackend, "_run",
                               return_value=_proc(0, "the transcript", "")) as run:
            res = macwhisper.MacWhisperBackend().transcribe(Path("/tmp/media.mp4"))
        argv = run.call_args[0][0]
        self.assertEqual(argv[:2], ["mw", "transcribe"])
        self.assertEqual(argv[2], "/tmp/media.mp4")
        self.assertNotIn("--persist", argv)
        self.assertNotIn("--stream", argv)
        self.assertEqual(res.text, "the transcript")
        self.assertEqual(res.backend_name, "macwhisper")

    def test_model_flag(self) -> None:
        with mock.patch.object(macwhisper.MacWhisperBackend, "_run",
                               return_value=_proc(0, "t", "")) as run:
            macwhisper.MacWhisperBackend(model="whisperkit:large-v3").transcribe(
                Path("/tmp/m.m4a")
            )
        argv = run.call_args[0][0]
        self.assertIn("--model", argv)
        self.assertIn("whisperkit:large-v3", argv)

    def test_nonzero_exit_and_empty_output_raise(self) -> None:
        with mock.patch.object(macwhisper.MacWhisperBackend, "_run",
                               return_value=_proc(1, "", "engine error")):
            with self.assertRaises(ASRError):
                macwhisper.MacWhisperBackend().transcribe(Path("/tmp/m.m4a"))
        with mock.patch.object(macwhisper.MacWhisperBackend, "_run",
                               return_value=_proc(0, "   ", "")):
            with self.assertRaises(ASRError):
                macwhisper.MacWhisperBackend().transcribe(Path("/tmp/m.m4a"))


class TestOpenAIBackend(unittest.TestCase):
    def test_multipart_encoding(self) -> None:
        body, ctype = openai_api._encode_multipart(
            {"model": "whisper-1", "response_format": "text"},
            file_field="file", filename="a.m4a",
            file_bytes=b"AUDIO", file_mime="audio/mp4",
        )
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="model"', body)
        self.assertIn(b'name="file"; filename="a.m4a"', body)
        self.assertIn(b"AUDIO", body)

    def test_rejects_crlf_in_model(self) -> None:
        # CRLF in --asr-model must NOT reach the multipart body (injection guard).
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-x"}, clear=False):
            b = openai_api.OpenAIWhisperBackend(
                allow_cloud=True, model="whisper-1\r\nX-Injected: 1"
            )
            with self.assertRaises(openai_api.ASRError):
                b.transcribe(Path("/tmp/does-not-matter.m4a"))

    def test_rejects_oversize_audio(self) -> None:
        tmp = "/tmp/tf_x_big.m4a"
        Path(tmp).write_bytes(b"x" * 100)
        try:
            with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-x"}, clear=False), \
                 mock.patch.object(openai_api.cfg, "openai_max_upload_bytes",
                                   return_value=10):
                with self.assertRaises(openai_api.ASRError):
                    openai_api.OpenAIWhisperBackend(allow_cloud=True).transcribe(Path(tmp))
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_transcribe_uses_config_endpoint_and_auth(self, tmpfile="/tmp/tf_x_audio.m4a") -> None:
        Path(tmpfile).write_bytes(b"AUDIO")
        captured = {}

        class _Resp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self, n=-1):
                return b"hello from cloud"

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            return _Resp()

        env = {
            "OPENAI_API_KEY": "sk-secret",
            "TRANSCRIPT_FETCHER_OPENAI_TRANSCRIBE_ENDPOINT":
                "https://api.groq.com/openai/v1/audio/transcriptions",
        }
        with mock.patch.dict("os.environ", env, clear=False), \
             mock.patch.object(openai_api.urlrequest, "urlopen", side_effect=fake_urlopen):
            res = openai_api.OpenAIWhisperBackend(allow_cloud=True).transcribe(
                Path(tmpfile), lang="en"
            )
        self.assertEqual(res.text, "hello from cloud")
        self.assertEqual(captured["url"],
                         "https://api.groq.com/openai/v1/audio/transcriptions")
        self.assertEqual(captured["auth"], "Bearer sk-secret")
        Path(tmpfile).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
