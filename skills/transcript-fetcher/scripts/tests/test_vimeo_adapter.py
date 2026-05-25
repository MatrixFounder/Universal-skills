"""Tests for the Vimeo adapter.

Mostly mirrors the YouTube adapter shape — id extraction, ladder
materialisation, and verifying that subprocess argv carries the
expected ``--cookies`` / ``--`` separator when those are present.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources import vimeo as vm  # noqa: E402
from sources._stat import TranscriptFetchError  # noqa: E402


class TestVideoIdExtraction(unittest.TestCase):
    def test_canonical(self) -> None:
        self.assertEqual(vm.extract_vimeo_id("https://vimeo.com/76979871"), "76979871")

    def test_player(self) -> None:
        self.assertEqual(
            vm.extract_vimeo_id("https://player.vimeo.com/video/76979871"),
            "76979871",
        )

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(vm.extract_vimeo_id("https://example.com/x"))


class TestSubprocessShape(unittest.TestCase):
    def test_argv_includes_double_dash_and_cookies(self) -> None:
        captured: dict = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            cookies = workdir / "c.txt"
            cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            with mock.patch("subprocess.run", side_effect=fake_run):
                vm._try_download_vimeo_subtitle(
                    url="https://vimeo.com/76979871",
                    lang="en",
                    kind="auto",
                    workdir=workdir,
                    pre_existing=set(),
                    yt_dlp_bin=None,
                    timeout_sec=30,
                    cookies_file=cookies,
                )
        args = captured["args"]
        self.assertEqual(args[-1], "https://vimeo.com/76979871")
        self.assertEqual(args[-2], "--")
        self.assertIn("--write-auto-subs", args)
        self.assertIn("--cookies", args)


class TestLadderMaterialisation(unittest.TestCase):
    def test_no_caption_raises_with_full_tried_list(self) -> None:
        def gen():
            yield ("manual", "en")
            yield ("auto", "en")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            workdir = Path(td) / "wd"
            with mock.patch.object(
                vm, "_try_download_vimeo_subtitle"
            ) as patched:
                patched.return_value = (False, None, "no subs")
                with self.assertRaises(TranscriptFetchError) as ctx:
                    vm.fetch_vimeo_transcript(
                        "https://vimeo.com/76979871",
                        out,
                        fallback_ladder=gen(),
                        workdir=workdir,
                    )
                msg = str(ctx.exception)
                self.assertIn("manual:en", msg)
                self.assertIn("auto:en", msg)


class TestDescriptionPath(unittest.TestCase):
    """Vimeo adapter writes a .description.md via the same _description writer."""

    def test_description_only_returns_stat_without_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            workdir = Path(td) / "wd"
            workdir.mkdir()
            sample_info = {
                "id": "76979871",
                "title": "Sample Vimeo Title",
                "description": "Vimeo description body.",
                "uploader": "Sample Channel",
                "upload_date": "20250101",
                "duration": 600,
            }
            with mock.patch.object(vm, "_fetch_video_info", return_value=sample_info):
                stat = vm.fetch_vimeo_transcript(
                    "https://vimeo.com/76979871",
                    out,
                    workdir=workdir,
                    with_description=True,
                    description_only=True,
                )
            self.assertEqual(stat.title, "Sample Vimeo Title")
            self.assertEqual(stat.duration_sec, 600)
            self.assertEqual(stat.upload_date, "2025-01-01")
            self.assertEqual(stat.char_count, 0)
            self.assertEqual(stat.source, "vimeo")
            self.assertTrue(stat.description_path)
            self.assertFalse(out.exists(), "description_only must not write .txt")
            self.assertTrue(Path(stat.description_path).exists())


if __name__ == "__main__":
    unittest.main()
