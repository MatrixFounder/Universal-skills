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
from sources import _auth  # noqa: E402
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
        def fake_download_captions(*, workdir, lang, **kw):
            p = Path(workdir) / f"media.{lang}.vtt"
            p.write_text(_VTT, encoding="utf-8")
            return True, p, "vtt", f"got auto:{lang}"

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_WITH_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_captions",
                                   side_effect=fake_download_captions), \
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

    def test_any_caption_fallback_when_ladder_misses_language(self) -> None:
        # Media has only a `manual en` track, but the ladder is ru-only (the
        # default --lang ru case). Captions-first must still win over ASR.
        info = {"id": "20", "subtitles": {"en": [{"ext": "vtt"}]},
                "automatic_captions": {}}

        def fake_download_captions(*, workdir, lang, **kw):
            p = Path(workdir) / f"media.{lang}.vtt"
            p.write_text(_VTT, encoding="utf-8")
            return True, p, "vtt", f"got manual:{lang}"

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(info, None)), \
                 mock.patch.object(ytm, "download_captions",
                                   side_effect=fake_download_captions), \
                 mock.patch.object(asr, "transcribe_with_fallback") as asr_mock:
                stat = xmod.fetch_x_transcript(
                    "https://twitter.com/jack/status/20", out,
                    fallback_ladder=(("manual", "ru"), ("auto", "ru")),
                )
            asr_mock.assert_not_called()
            self.assertEqual(stat.transcript_origin, "embedded-captions")
            self.assertEqual(stat.chosen_track_kind, "manual")
            self.assertEqual(stat.chosen_track_lang, "en")
            self.assertTrue(any("using the available" in n for n in stat.notes))

    def test_empty_caption_falls_through_to_asr(self) -> None:
        # A downloaded caption that parses to no text must NOT be written as a
        # silent-empty "embedded-captions" transcript — it falls through to ASR.
        def fake_download_captions(*, workdir, lang, **kw):
            p = Path(workdir) / f"media.{lang}.vtt"
            p.write_text("WEBVTT\n\n", encoding="utf-8")  # header only → empty text
            return True, p, "vtt", f"got auto:{lang}"

        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="asr body text", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_WITH_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_captions",
                                   side_effect=fake_download_captions), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result) as asr_mock:
                stat = xmod.fetch_x_transcript(
                    "https://twitter.com/jack/status/20", out
                )
            asr_mock.assert_called_once()
            self.assertEqual(stat.transcript_origin, "macwhisper")
            self.assertEqual(out.read_text(encoding="utf-8"), "asr body text")
            self.assertTrue(any("no text" in n for n in stat.notes))

    def test_malicious_ttml_caption_refused_falls_through(self) -> None:
        billion = (
            '<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY a "x">]>\n'
            '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
            "<p>&a;</p></div></body></tt>"
        )

        def fake_download_captions(*, workdir, lang, **kw):
            p = Path(workdir) / f"media.{lang}.ttml"
            p.write_text(billion, encoding="utf-8")
            return True, p, "ttml", f"got auto:{lang}"

        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="safe asr text", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_WITH_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_captions",
                                   side_effect=fake_download_captions), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result) as asr_mock:
                stat = xmod.fetch_x_transcript(
                    "https://twitter.com/jack/status/20", out
                )
            asr_mock.assert_called_once()
            self.assertEqual(stat.transcript_origin, "macwhisper")
            self.assertTrue(any("parse failed" in n for n in stat.notes))


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
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "test: silence-removal off")), \
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
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "test: silence-removal off")), \
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
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "test: silence-removal off")), \
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
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "test: silence-removal off")), \
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
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "test: silence-removal off")), \
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


class TestMediaBudgetRouting(unittest.TestCase):
    """Media budget resolved ONCE in x.py and passed ONLY to `download_audio`
    (arch-016 §10, task 029.02). Probe keeps its own small `timeout_sec`."""

    _INFO_LONG = {
        "id": "z", "duration": 4200,
        "subtitles": {}, "automatic_captions": {},
    }
    _INFO_NO_DURATION = {
        "id": "z", "duration": None,
        "subtitles": {}, "automatic_captions": {},
    }

    def test_duration_derived_budget_reaches_download_audio(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    concurrent_fragments=16,
                )
        self.assertEqual(captured["timeout_sec"], 16800)  # max(600, 4200*4)
        self.assertEqual(captured["concurrent_fragments"], 16)

    def test_cli_or_env_override_wins_over_duration(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    media_timeout_sec=3600,
                )
        self.assertEqual(captured["timeout_sec"], 3600)

    def test_no_duration_falls_back_to_1800(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_NO_DURATION, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
        self.assertEqual(captured["timeout_sec"], 1800)

    def test_probe_keeps_its_own_small_timeout(self) -> None:
        captured: dict = {}

        def fake_probe_metadata(url, *, timeout_sec, **kw):
            captured["probe_timeout_sec"] = timeout_sec
            return self._INFO_LONG, None

        def fake_download_audio(url, workdir, **kw):
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   side_effect=fake_probe_metadata), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    timeout_sec=180, media_timeout_sec=3600,
                )
        # The probe got the small general timeout_sec, NOT the media budget.
        self.assertEqual(captured["probe_timeout_sec"], 180)


class TestMediaBudgetClip(unittest.TestCase):
    """F3/F7 lock: the media-download budget must respect --max-duration-min —
    it derives from the EFFECTIVE (clipped) duration, not the full probed one.
    FIX-6 (cycle 3): that clip only applies when ffmpeg is present — mirrors
    `download_audio`, where `--download-sections` (the actual clip) is only
    emitted in the ffmpeg branch."""

    _INFO_LONG = {
        "id": "z", "duration": 4200,
        "subtitles": {}, "automatic_captions": {},
    }

    def test_max_duration_min_clips_the_budget(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    max_duration_min=1,  # clip to 60s << the 4200s duration
                )
        # media_timeout_for(min(4200, 60)) == max(600, 60*4) == 600
        self.assertEqual(captured["timeout_sec"], 600)

    def test_no_clip_when_max_duration_min_unset(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript("https://x.com/i/broadcasts/z", out)
        self.assertEqual(captured["timeout_sec"], 16800)  # unclipped: 4200*4

    def test_no_clip_when_ffmpeg_absent(self) -> None:
        # FIX-6: `download_audio`'s `--download-sections` clip is emitted
        # ONLY inside its `ffmpeg_available()` branch — without ffmpeg a
        # progressive download pulls the FULL media, so the budget must NOT
        # be clipped either, even though --max-duration-min is set.
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=False), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    max_duration_min=1,  # would clip to 60s IF ffmpeg present
                )
        # media_timeout_for(4200) == max(600, 4200*4) == 16800 — the FULL
        # (unclipped) duration, because ffmpeg is absent so the download
        # itself is never actually clipped.
        self.assertEqual(captured["timeout_sec"], 16800)

    def test_explicit_media_timeout_sec_still_wins_over_clip(self) -> None:
        captured: dict = {}

        def fake_download_audio(url, workdir, **kw):
            captured.update(kw)
            p = Path(workdir) / "media.m4a"
            p.write_bytes(b"x")
            return p, None

        result = asr.ASRResult(text="body", backend_name="macwhisper")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(self._INFO_LONG, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm, "remove_silence",
                                   return_value=(None, "off")), \
                 mock.patch.object(asr, "transcribe_with_fallback",
                                   return_value=result):
                xmod.fetch_x_transcript(
                    "https://x.com/i/broadcasts/z", out,
                    max_duration_min=1, media_timeout_sec=9999,
                )
        self.assertEqual(captured["timeout_sec"], 9999)


class TestAuthMessageHostDerivedCookieName(unittest.TestCase):
    """F10 lock: the auth-failure remediation hint names the convention cookie
    file DERIVED FROM THE URL HOST, not a hardcoded x.com-cookies.txt."""

    def test_twitter_com_url_names_twitter_com_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(
                ytm, "probe_metadata",
                return_value=(None, "ERROR: This account is protected"),
            ):
                with self.assertRaises(SourceAuthError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://twitter.com/jack/status/20", out
                    )
        self.assertIn("twitter.com-cookies.txt", str(ctx.exception))
        self.assertNotIn("x.com-cookies.txt", str(ctx.exception))

    def test_www_prefix_stripped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(
                ytm, "probe_metadata",
                return_value=(None, "ERROR: This account is protected"),
            ):
                with self.assertRaises(SourceAuthError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://www.x.com/jack/status/20", out
                    )
        self.assertIn("x.com-cookies.txt", str(ctx.exception))
        self.assertNotIn("www.x.com-cookies.txt", str(ctx.exception))

    def test_hinted_convention_path_round_trips_through_resolver(self) -> None:
        # FIX-1 (cycle 3) round-trip lock: creating EXACTLY the file named by
        # the exit-5 hint (the www./mobile.-stripped host) must make
        # `_auth.resolve_cookies_file` find it on retry — closes the F10
        # residual where the hint and the resolver disagreed.
        with tempfile.TemporaryDirectory() as d:
            cookies = Path(d) / "x.com-cookies.txt"
            cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            os.chmod(cookies, 0o600)
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                resolved = _auth.resolve_cookies_file(
                    "https://www.x.com/jack/status/20"
                )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.name, "x.com-cookies.txt")


class TestRateLimitConcurrentFragmentsHint(unittest.TestCase):
    """F8 lock: a rate-limit failure during the media DOWNLOAD names
    --concurrent-fragments; the same failure from the metadata PROBE does not
    (the probe never uses concurrent fragments)."""

    def test_download_path_names_concurrent_fragments(self) -> None:
        def fake_download_audio(url, workdir, **kw):
            return None, "ERROR: HTTP Error 429: Too Many Requests"

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True):
                with self.assertRaises(SourceRateLimitError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://x.com/i/broadcasts/z", out
                    )
        self.assertIn("--concurrent-fragments", str(ctx.exception))

    def test_probe_path_does_not_name_concurrent_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(
                ytm, "probe_metadata",
                return_value=(None, "ERROR: HTTP Error 429: Too Many Requests"),
            ):
                with self.assertRaises(SourceRateLimitError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://x.com/i/broadcasts/z", out
                    )
        self.assertNotIn("--concurrent-fragments", str(ctx.exception))


class TestTransientRemediation(unittest.TestCase):
    def test_audio_timeout_raises_transcriptfetcherror_with_remediation(self) -> None:
        def fake_download_audio(url, workdir, **kw):
            return None, "timeout downloading audio (>1800s)"

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(ytm, "probe_metadata",
                                   return_value=(_INFO_NO_CAPTIONS, None)), \
                 mock.patch.object(ytm, "download_audio",
                                   side_effect=fake_download_audio), \
                 mock.patch.object(ytm, "ffmpeg_available", return_value=True):
                with self.assertRaises(TranscriptFetchError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://x.com/i/broadcasts/z", out
                    )
        remediation = ctx.exception.remediation
        self.assertIsNotNone(remediation)
        self.assertIn("--concurrent-fragments", remediation)
        self.assertIn("--media-timeout-sec", remediation)


class TestAuthMessageCookiePath(unittest.TestCase):
    def test_convention_path_named_without_cookies_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            with mock.patch.object(
                ytm, "probe_metadata",
                return_value=(None, "ERROR: This account is protected"),
            ):
                with self.assertRaises(SourceAuthError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://x.com/i/broadcasts/z", out
                    )
        self.assertIn("x.com-cookies.txt", str(ctx.exception))

    def test_resolved_path_named_with_cookies_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            cookies = Path(d) / "mine-cookies.txt"
            cookies.write_text("# netscape cookies\n", encoding="utf-8")
            with mock.patch.object(
                ytm, "probe_metadata",
                return_value=(None, "ERROR: This account is protected"),
            ):
                with self.assertRaises(SourceAuthError) as ctx:
                    xmod.fetch_x_transcript(
                        "https://x.com/i/broadcasts/z", out,
                        cookies_file=cookies,
                    )
        self.assertIn(str(cookies), str(ctx.exception))


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
