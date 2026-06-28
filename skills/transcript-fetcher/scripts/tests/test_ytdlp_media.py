"""Tests for the shared yt-dlp media core (`_ytdlp_media`).

Subprocess is mocked — these assert argv shape for the clip (--download-sections),
browser-cookie passthrough, and ffprobe duration parsing. No network, no yt-dlp.
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources import _ytdlp_media as ytm  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestDownloadAudioArgv(unittest.TestCase):
    def test_clip_and_browser_cookies_with_ffmpeg(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "media.mp4").write_bytes(b"x")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run):
                media, err = ytm.download_audio(
                    "https://x.com/i/broadcasts/z", workdir,
                    max_duration_min=30, cookies_from_browser="chrome",
                )
            argv = captured["argv"]
            # ffmpeg present → audio-only extraction
            self.assertIn("-x", argv)
            self.assertIn("--audio-format", argv)
            # clip: first 30 min == 1800 s
            self.assertIn("--download-sections", argv)
            self.assertIn("*0-1800", argv)
            # browser cookies passed through to yt-dlp
            self.assertIn("--cookies-from-browser", argv)
            self.assertIn("chrome", argv)
            self.assertIsNotNone(media)

    def test_no_clip_without_ffmpeg(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "media.mp4").write_bytes(b"x")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=False), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run):
                ytm.download_audio(
                    "https://x.com/i/broadcasts/z", workdir, max_duration_min=30,
                )
            argv = captured["argv"]
            # the clip lives inside the ffmpeg branch → absent without ffmpeg
            self.assertNotIn("--download-sections", argv)
            self.assertNotIn("-x", argv)


class TestProbeMetadataBrowserCookies(unittest.TestCase):
    def test_browser_cookies_in_probe_argv(self) -> None:
        captured: dict = {}

        def fake_run(args, **kw):
            captured["argv"] = list(args)
            return _proc(0, stdout='{"id":"z","subtitles":{},"automatic_captions":{}}')

        with mock.patch.object(ytm.subprocess, "run", side_effect=fake_run):
            info, err = ytm.probe_metadata(
                "https://x.com/i/broadcasts/z", cookies_from_browser="safari",
            )
        self.assertIn("--cookies-from-browser", captured["argv"])
        self.assertIn("safari", captured["argv"])
        self.assertIsNotNone(info)


class TestProbeMediaDuration(unittest.TestCase):
    def test_parses_float_seconds(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(0, stdout="1834.56\n")):
            self.assertEqual(ytm.probe_media_duration(Path("/x/m.m4a")), 1834)

    def test_nonzero_exit_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(1, stdout="")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))

    def test_missing_ffprobe_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               side_effect=FileNotFoundError("ffprobe")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))

    def test_garbage_output_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(0, stdout="N/A\n")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))


if __name__ == "__main__":
    unittest.main()
