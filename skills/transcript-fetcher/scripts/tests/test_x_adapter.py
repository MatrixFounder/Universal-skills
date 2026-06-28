"""Offline tests for the X.com adapter + its CLI wiring.

All network/subprocess/ASR calls are mocked — these assert the routing logic
(captions-first vs ASR), provenance stat fields, temp-file cleanup, error
mapping, exit-code-7, and debug logging. No yt-dlp, no `mw`, no network.
"""
from __future__ import annotations

import contextlib
import io
import json
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

import fetch  # noqa: E402
import asr  # noqa: E402
from sources import x as xmod  # noqa: E402
from sources import _ytdlp_media as ytm  # noqa: E402
from sources._stat import (  # noqa: E402
    MissingDependencyError,
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
)

_VTT = (
    "WEBVTT\n\n"
    "00:00:00.000 --> 00:00:02.000\nHello world\n\n"
    "00:00:02.000 --> 00:00:04.000\nthis is a caption\n"
)

_INFO_NO_CAPTIONS = {
    "id": "1nxnRRZnwbBxO",
    "title": "Building AI-Native Startups [003]",
    "uploader": "cyber•Fund",
    "subtitles": {},
    "automatic_captions": {},
}
_INFO_WITH_CAPTIONS = {
    "id": "20",
    "title": "a status video",
    "subtitles": {},
    "automatic_captions": {"en": [{"ext": "vtt"}]},
}


class TestXDetect(unittest.TestCase):
    def test_hosts_map_to_x(self) -> None:
        for u in (
            "https://x.com/i/broadcasts/1nxnRRZnwbBxO",
            "https://www.x.com/jack/status/20",
            "https://mobile.x.com/i/broadcasts/abc",
            "https://twitter.com/jack/status/20",
            "https://www.twitter.com/jack/status/20",
            "https://mobile.twitter.com/jack/status/20",
        ):
            self.assertEqual(fetch._detect_source(u), "x", u)

    def test_typosquat_rejected(self) -> None:
        for u in (
            "https://x.com.evil.com/i/broadcasts/abc",
            "https://notx.com/jack/status/20",
            "https://evil.com/?ref=x.com/status/1",
        ):
            with self.assertRaises(ValueError):
                fetch._detect_source(u)

    def test_extract_id(self) -> None:
        self.assertEqual(
            ytm.extract_x_id("https://x.com/i/broadcasts/1nxnRRZnwbBxO"),
            "1nxnRRZnwbBxO",
        )
        self.assertEqual(ytm.extract_x_id("https://twitter.com/jack/status/20"), "20")
        self.assertEqual(ytm.extract_x_id("https://x.com/i/spaces/xYz"), "xYz")
        self.assertIsNone(ytm.extract_x_id("https://example.com/foo"))


class TestCaptionPath(unittest.TestCase):
    def test_uses_embedded_captions_no_asr(self) -> None:
        def fake_download_subtitle(*, workdir, lang, **kw):
            p = Path(workdir) / f"media.{lang}.vtt"
            p.write_text(_VTT, encoding="utf-8")
            return True, p, f"got auto:{lang}"

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_WITH_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_subtitle",
                                   side_effect=fake_download_subtitle), \
                 mock.patch.object(asr, "transcribe_with_fallback") as asr_mock:
                stat = xmod.fetch_x_transcript(
                    "https://twitter.com/jack/status/20", out
                )
            asr_mock.assert_not_called()
            self.assertEqual(stat.source, "x")
            self.assertEqual(stat.transcript_origin, "embedded-captions")
            self.assertEqual(stat.chosen_track_kind, "auto")
            self.assertEqual(stat.chosen_track_lang, "en")
            self.assertIn("Hello", out.read_text(encoding="utf-8"))


class TestASRPath(unittest.TestCase):
    def test_falls_back_to_asr_when_no_captions(self) -> None:
        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.mp4"
            p.write_bytes(b"\x00\x00fakemedia")
            return p, None

        result = asr.ASRResult(
            text="hello world transcript body", backend_name="macwhisper", model=None
        )
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result) as asr_mock:
                stat = xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/1nxnRRZnwbBxO", out
                )
            asr_mock.assert_called_once()
            self.assertEqual(stat.transcript_origin, "macwhisper")
            self.assertEqual(stat.chosen_track_kind, "asr")
            self.assertEqual(stat.asr_backend, "macwhisper")
            self.assertEqual(out.read_text(encoding="utf-8"), result.text)


class TestDurationFill(unittest.TestCase):
    def test_asr_fills_duration_via_ffprobe_when_metadata_none(self) -> None:
        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="hello world body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio", side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "probe_media_duration", return_value=1834), \
                 mock.patch.object(asr, "transcribe_with_fallback", return_value=result):
                stat = xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
            self.assertEqual(stat.duration_sec, 1834)
            self.assertTrue(any("ffprobe" in n for n in stat.notes))


class TestCleanup(unittest.TestCase):
    def test_tempdir_removed_even_on_success(self) -> None:
        created: list[str] = []
        real_mkdtemp = tempfile.mkdtemp

        def capturing_mkdtemp(*a, **k):
            d = real_mkdtemp(*a, **k)
            created.append(d)
            return d

        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.mp4"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="t", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(xmod.tempfile, "mkdtemp",
                                   side_effect=capturing_mkdtemp), \
                 mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
        self.assertTrue(created, "tempdir should have been created")
        for d in created:
            self.assertFalse(os.path.exists(d), f"workdir not cleaned: {d}")

    def test_tempdir_removed_on_error(self) -> None:
        created: list[str] = []
        real_mkdtemp = tempfile.mkdtemp

        def capturing_mkdtemp(*a, **k):
            d = real_mkdtemp(*a, **k)
            created.append(d)
            return d

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(xmod.tempfile, "mkdtemp",
                                   side_effect=capturing_mkdtemp), \
                 mock.patch.object(ytm, "probe_metadata",
                                   return_value=(None, "ERROR: This tweet is unavailable")):
                with self.assertRaises(TranscriptFetchError):
                    xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
        for d in created:
            self.assertFalse(os.path.exists(d), f"workdir not cleaned on error: {d}")


class TestErrorMapping(unittest.TestCase):
    def _run_with_probe_error(self, stderr: str):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(None, stderr)):
                return xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)

    def test_protected_is_auth(self) -> None:
        with self.assertRaises(SourceAuthError):
            self._run_with_probe_error("ERROR: This account is protected")

    def test_rate_limit(self) -> None:
        with self.assertRaises(SourceRateLimitError):
            self._run_with_probe_error("ERROR: HTTP Error 429: Too Many Requests")

    def test_unavailable_is_hard(self) -> None:
        with self.assertRaises(TranscriptFetchError):
            self._run_with_probe_error("ERROR: This broadcast is unavailable")


class TestDebugLogging(unittest.TestCase):
    def _run(self, debug: bool) -> str:
        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.mp4"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="t", backend_name="macwhisper")
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with contextlib.redirect_stderr(buf), \
                 mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out, debug=debug
                )
        return buf.getvalue()

    def test_debug_emits_stages(self) -> None:
        err = self._run(debug=True)
        for stage in ("Detected X media", "Fetching metadata",
                      "Downloading audio", "Cleaning temporary files", "Finished"):
            self.assertIn(stage, err)

    def test_silent_without_debug(self) -> None:
        self.assertEqual(self._run(debug=False), "")


class TestCLIExit7(unittest.TestCase):
    def test_missing_dependency_maps_to_exit_7(self) -> None:
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(
                fetch, "_fetch_one",
                side_effect=MissingDependencyError(
                    "No ASR backend available.", remediation="Install MacWhisper."
                ),
            ), contextlib.redirect_stderr(buf):
                rc = fetch.main([
                    "https://x.com/i/broadcasts/z", "--out", str(out),
                    "--json-errors",
                ])
        self.assertEqual(rc, 7)
        env = json.loads(buf.getvalue().strip())
        self.assertEqual(env["code"], 7)
        self.assertEqual(env["type"], "MissingDependencyError")
        self.assertEqual(env["details"]["remediation"], "Install MacWhisper.")


class TestHLSFailFast(unittest.TestCase):
    """No ffmpeg + an HLS-only source must fail fast (exit 7) BEFORE downloading."""

    _HLS_INFO = {
        "id": "z", "subtitles": {}, "automatic_captions": {},
        "formats": [
            {"format_id": "replay-600", "protocol": "m3u8_native",
             "acodec": "mp4a.40.2", "vcodec": "avc1.64001e"},
        ],
    }

    def test_no_ffmpeg_hls_only_raises_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._HLS_INFO, None)), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=False), \
                 mock.patch.object(ytm, "download_audio") as dl, \
                 mock.patch.object(asr, "transcribe_with_fallback") as tr:
                with self.assertRaises(MissingDependencyError):
                    xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
                dl.assert_not_called()
                tr.assert_not_called()

    def test_ffmpeg_present_proceeds(self) -> None:
        def fake_dl(url, workdir, **kw):
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="ok", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._HLS_INFO, None)), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "download_audio", side_effect=fake_dl), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                stat = xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
            self.assertEqual(stat.transcript_origin, "macwhisper")

    def test_is_hls_only_detection(self) -> None:
        self.assertTrue(ytm.is_hls_only(self._HLS_INFO))
        # a progressive format present → not HLS-only
        prog = {"formats": [
            {"format_id": "http", "protocol": "https", "acodec": "mp4a", "vcodec": "avc1"},
        ]}
        self.assertFalse(ytm.is_hls_only(prog))
        self.assertFalse(ytm.is_hls_only({}))  # unknown → don't block


class TestBatchExit7(unittest.TestCase):
    def test_batch_surfaces_missing_dependency_remediation(self) -> None:
        out_buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            batch = Path(d) / "urls.txt"
            batch.write_text("https://x.com/i/broadcasts/zzz\n", encoding="utf-8")
            outdir = Path(d) / "out"
            with mock.patch.object(
                fetch, "_fetch_one",
                side_effect=MissingDependencyError(
                    "No ASR backend available.", remediation="Install MacWhisper."
                ),
            ), contextlib.redirect_stdout(out_buf):
                rc = fetch.main([
                    "--batch", str(batch), "--out-dir", str(outdir),
                ])
        self.assertEqual(rc, 4)  # batch aggregates to partial-failure
        rec = json.loads(out_buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(rec["type"], "MissingDependencyError")
        self.assertEqual(rec["remediation"], "Install MacWhisper.")


class TestAuthMapCLI(unittest.TestCase):
    def test_bad_auth_map_fails_fast_exit_2(self) -> None:
        # A malformed auth-map must fail BEFORE any fetch (exit 2 UsageError),
        # not be re-parsed per URL — in both single-URL and batch modes.
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "auth-map.json"
            bad.write_text("{ not valid json", encoding="utf-8")
            os.chmod(bad, 0o600)
            out = Path(d) / "o.txt"
            with mock.patch.object(fetch, "_fetch_one") as fetch_one, \
                 contextlib.redirect_stderr(buf):
                rc = fetch.main([
                    "https://x.com/i/broadcasts/z", "--out", str(out),
                    "--auth-map", str(bad), "--json-errors",
                ])
            fetch_one.assert_not_called()  # failed before dispatch
        self.assertEqual(rc, 2)
        env = json.loads(buf.getvalue().strip())
        self.assertEqual(env["code"], 2)
        self.assertEqual(env["type"], "UsageError")


if __name__ == "__main__":
    unittest.main()
