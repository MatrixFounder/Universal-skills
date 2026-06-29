"""Tests for the shared yt-dlp media core (`_ytdlp_media`).

Subprocess is mocked — these assert argv shape for the clip (--download-sections),
browser-cookie passthrough, and ffprobe duration parsing. No network, no yt-dlp.
"""
from __future__ import annotations

import shutil
import subprocess
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

_HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


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


class TestDownloadCaptions(unittest.TestCase):
    def test_argv_format_list_and_detection(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "vid.en.srt").write_text("1\n", encoding="utf-8")
                return _proc(0)

            with mock.patch.object(ytm.subprocess, "run", side_effect=fake_run):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/jack/status/20", lang="en", kind="auto",
                    workdir=workdir, pre_existing=set(),
                    cookies_file=Path("/c/cookies.txt"),
                    cookies_from_browser="chrome",
                )
            argv = captured["argv"]
            self.assertIn("--sub-format", argv)
            self.assertIn("vtt/srt/ttml/best", argv)   # preference list, not vtt-only
            self.assertIn("--write-auto-subs", argv)
            self.assertIn("--cookies", argv)
            self.assertIn("--cookies-from-browser", argv)
            self.assertIn("chrome", argv)
            self.assertTrue(ok)
            self.assertEqual(fmt, "srt")
            self.assertEqual(path.name, "vid.en.srt")

    def test_auth_failure_classified(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            with mock.patch.object(
                ytm.subprocess, "run",
                return_value=_proc(1, stderr="ERROR: This account is protected"),
            ):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/i/broadcasts/z", lang="en", kind="auto",
                    workdir=workdir, pre_existing=set(),
                )
            self.assertFalse(ok)
            self.assertIsNone(path)
            self.assertIn("auth", note)

    def test_no_file_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            with mock.patch.object(ytm.subprocess, "run", return_value=_proc(0)):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/jack/status/20", lang="en", kind="manual",
                    workdir=workdir, pre_existing=set(),
                )
            self.assertFalse(ok)
            self.assertIn("no subtitle", note)


class TestCaptionFinder(unittest.TestCase):
    def test_prefers_vtt_over_srt(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            (workdir / "v.en.srt").write_text("x", encoding="utf-8")
            (workdir / "v.en.vtt").write_text("x", encoding="utf-8")
            found = ytm._find_new_caption(workdir, "en", set())
            self.assertEqual(found.suffix, ".vtt")

    def test_excludes_pre_existing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            old = workdir / "v.en.vtt"
            old.write_text("x", encoding="utf-8")
            pre = {old.resolve()}
            self.assertIsNone(ytm._find_new_caption(workdir, "en", pre))

    def test_existing_caption_files_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            (workdir / "v.en.vtt").write_text("x", encoding="utf-8")
            (workdir / "v.en.srt").write_text("x", encoding="utf-8")
            (workdir / "v.info.json").write_text("{}", encoding="utf-8")  # not a caption
            snap = ytm.existing_caption_files(workdir)
            names = {p.name for p in snap}
            self.assertEqual(names, {"v.en.vtt", "v.en.srt"})


class TestPickAnyCaption(unittest.TestCase):
    def test_prefers_manual_over_auto(self) -> None:
        info = {"subtitles": {"en": [{}], "de": [{}]},
                "automatic_captions": {"fr": [{}]}}
        self.assertEqual(ytm.pick_any_caption(info), ("manual", "en"))

    def test_falls_to_auto_when_no_manual(self) -> None:
        info = {"subtitles": {}, "automatic_captions": {"ja": [{}]}}
        self.assertEqual(ytm.pick_any_caption(info), ("auto", "ja"))

    def test_none_when_no_captions(self) -> None:
        self.assertIsNone(
            ytm.pick_any_caption({"subtitles": {}, "automatic_captions": {}})
        )


class TestRemoveSilence(unittest.TestCase):
    def test_skips_gracefully_without_ffmpeg(self) -> None:
        with mock.patch.object(ytm, "ffmpeg_available", return_value=False):
            out, note = ytm.remove_silence(Path("/x/m.m4a"), Path("/x"))
        self.assertIsNone(out)
        self.assertIn("ffmpeg not available", note)

    def test_argv_and_success(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "media.desilenced.m4a").write_bytes(b"yy")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(ytm, "probe_media_duration",
                                   side_effect=[100, 40]):
                out, note = ytm.remove_silence(media, workdir)
            argv = captured["argv"]
            self.assertIn("-af", argv)
            af = next(a for a in argv if "silenceremove=" in a)
            # Threshold MUST keep the dB suffix — silenceremove parses "dB"
            # natively; a bare negative number makes ffmpeg error "Result too
            # large" (empirically verified). Regression lock against a "convert
            # to linear" change that would break the filter.
            self.assertIn("threshold=-45dB", af)
            # Durations carry an explicit `s` unit.
            self.assertIn("stop_duration=1.0s", af)
            self.assertIn("stop_silence=0.3s", af)
            self.assertIsNotNone(out)
            self.assertEqual(out.name, "media.desilenced.m4a")
            self.assertIn("stripped ~60s", note)

    def test_no_silence_removed_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")

            def fake_run(args, **kw):
                (workdir / "media.desilenced.m4a").write_bytes(b"yy")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(ytm, "probe_media_duration",
                                   side_effect=[40, 40]):
                out, note = ytm.remove_silence(media, workdir)
            self.assertIsNone(out)
            self.assertIn("no long silence", note)
            # the useless re-encode was cleaned up
            self.assertFalse((workdir / "media.desilenced.m4a").exists())

    def test_ffmpeg_nonzero_exit_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")
            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run",
                                   return_value=_proc(1, stderr="boom")):
                out, note = ytm.remove_silence(media, workdir)
            self.assertIsNone(out)
            self.assertIn("no usable output", note)

    @unittest.skipUnless(_HAVE_FFMPEG, "ffmpeg/ffprobe required for the live filter test")
    def test_real_ffmpeg_strips_silence(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            src = workdir / "media.m4a"
            # 4s digital silence + 2s 440Hz tone + 4s silence = 10s.
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=16000",
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=4",
                    "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
                    str(src),
                ],
                check=True, capture_output=True,
            )
            before = ytm.probe_media_duration(src)
            out, note = ytm.remove_silence(src, workdir)
            self.assertIsNotNone(out, note)
            after = ytm.probe_media_duration(out)
            self.assertLess(after, before)   # dead air collapsed
            self.assertLessEqual(after, 5)    # ~2s tone + a little kept silence


if __name__ == "__main__":
    unittest.main()
