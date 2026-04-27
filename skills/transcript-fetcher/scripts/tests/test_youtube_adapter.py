"""Adapter-level tests for the YouTube source.

By default these tests are OFFLINE and never call yt-dlp over the
network. They cover:

- Video-id extraction across URL forms.
- The ``_build_ladder`` helper used by the CLI.
- The ``TranscriptStat.to_dict`` serialisation contract.
- Failure classification (rate-limit, hard-failure, generic rc!=0).
- ``_find_new_vtt`` ignores stale files (snapshot behaviour).
- ``fetch_youtube_transcript`` materialises the fallback ladder so a
  generator can be passed safely.
- yt-dlp argv contains a ``--`` separator before the URL.

An optional end-to-end test that DOES call yt-dlp is gated behind the
environment variable ``TRANSCRIPT_FETCHER_E2E=1``.
"""
from __future__ import annotations

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

from sources import youtube as yt  # noqa: E402
from sources.youtube import (  # noqa: E402
    DEFAULT_FALLBACK_RU,
    TranscriptFetchError,
    TranscriptStat,
    extract_video_id,
    fetch_youtube_transcript,
    write_stat_sidecar,
)
from fetch import _build_ladder  # noqa: E402


class TestVideoIdExtraction(unittest.TestCase):
    def test_short_form(self) -> None:
        self.assertEqual(
            extract_video_id("https://youtu.be/NSVTpCfBMK8"),
            "NSVTpCfBMK8",
        )

    def test_watch_form(self) -> None:
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=NSVTpCfBMK8&t=42"),
            "NSVTpCfBMK8",
        )

    def test_shorts_form(self) -> None:
        self.assertEqual(
            extract_video_id("https://youtube.com/shorts/NSVTpCfBMK8"),
            "NSVTpCfBMK8",
        )

    def test_embed_form(self) -> None:
        self.assertEqual(
            extract_video_id("https://www.youtube.com/embed/NSVTpCfBMK8"),
            "NSVTpCfBMK8",
        )

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(extract_video_id("https://example.com/video/abc"))


class TestLadderBuilder(unittest.TestCase):
    def test_default_ru_ladder(self) -> None:
        self.assertEqual(_build_ladder("manual", "ru"), DEFAULT_FALLBACK_RU)

    def test_auto_first_for_ru(self) -> None:
        ladder = _build_ladder("auto", "ru")
        self.assertEqual(ladder[0], ("auto", "ru-orig"))
        self.assertEqual(ladder[-1], ("auto", "en"))

    def test_non_ru_lang_skips_lang_orig(self) -> None:
        ladder = _build_ladder("manual", "es")
        kinds_langs = list(ladder)
        self.assertNotIn(("auto", "es-orig"), kinds_langs)
        self.assertIn(("manual", "es"), kinds_langs)
        self.assertIn(("auto", "es"), kinds_langs)
        self.assertIn(("auto", "en"), kinds_langs)


class TestStatSerialisation(unittest.TestCase):
    def test_to_dict_round_trip(self) -> None:
        stat = TranscriptStat(
            source="youtube",
            url="https://youtu.be/abc",
            video_id="abc",
            output_path="/tmp/out.txt",
            chosen_track_kind="auto",
            chosen_track_lang="ru-orig",
            char_count=12345,
            speaker_turn_count=4,
            quality_flag=None,
            notes=["got auto:ru-orig -> abc.ru-orig.vtt"],
        )
        d = stat.to_dict()
        again = json.loads(json.dumps(d, ensure_ascii=False))
        self.assertEqual(again["source"], "youtube")
        self.assertEqual(again["chosen_track_lang"], "ru-orig")
        self.assertEqual(again["speaker_turn_count"], 4)
        self.assertIsNone(again["quality_flag"])

    def test_write_stat_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plain = Path(td) / "out.txt"
            plain.write_text("hello", encoding="utf-8")
            stat = TranscriptStat(
                source="youtube",
                url="https://youtu.be/abc",
                video_id="abc",
                output_path=str(plain),
                chosen_track_kind="manual",
                chosen_track_lang="ru",
                char_count=5,
                speaker_turn_count=0,
            )
            sidecar = write_stat_sidecar(stat, plain)
            self.assertTrue(sidecar.exists())
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(payload["video_id"], "abc")


class TestFailureClassification(unittest.TestCase):
    """yt-dlp stderr -> human-readable failure reason."""

    def test_hard_failure_video_unavailable(self) -> None:
        reason = yt._classify_failure("ERROR: Video unavailable")
        self.assertIsNotNone(reason)
        self.assertIn("hard-failure", reason)

    def test_hard_failure_private_video(self) -> None:
        reason = yt._classify_failure("ERROR: This is a private video")
        self.assertIn("hard-failure", reason)

    def test_rate_limit_429(self) -> None:
        reason = yt._classify_failure("HTTP Error 429: Too Many Requests")
        self.assertIn("rate-limit", reason)

    def test_rate_limit_bot_check(self) -> None:
        reason = yt._classify_failure(
            "ERROR: Sign in to confirm you're not a bot"
        )
        self.assertIn("rate-limit", reason)

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(yt._classify_failure(""))
        self.assertIsNone(yt._classify_failure("ERROR: random thing"))


class TestStderrTail(unittest.TestCase):
    def test_keeps_last_n_nonblank_lines(self) -> None:
        stderr = "first\n\nsecond\nthird\n  \nfourth\n"
        tail = yt._stderr_tail(stderr, n_lines=2)
        self.assertEqual(tail, "third | fourth")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(yt._stderr_tail("", 5), "")


class TestFindNewVtt(unittest.TestCase):
    """Snapshot behaviour: pre-existing VTTs are NOT returned."""

    def test_returns_only_files_not_in_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            stale = workdir / "stale.ru.vtt"
            stale.write_text("WEBVTT\n", encoding="utf-8")
            snapshot = {p.resolve() for p in workdir.glob("*.vtt")}
            self.assertIn(stale.resolve(), snapshot)
            # No new file yet -> None
            self.assertIsNone(yt._find_new_vtt(workdir, "ru", snapshot))
            # Add a "new" file matching the lang.
            fresh = workdir / "fresh.ru.vtt"
            fresh.write_text("WEBVTT\n", encoding="utf-8")
            found = yt._find_new_vtt(workdir, "ru", snapshot)
            self.assertEqual(found, fresh)
            self.assertNotEqual(found, stale)

    def test_ignores_other_languages(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "abc.en.vtt").write_text("WEBVTT\n", encoding="utf-8")
            snapshot = set()
            self.assertIsNone(yt._find_new_vtt(workdir, "ru", snapshot))


class TestLadderMaterialisation(unittest.TestCase):
    """Generators passed as fallback_ladder must work and be re-iterable
    for the error path."""

    def test_generator_ladder_failure_message_lists_what_was_tried(self) -> None:
        # Build a generator (single-use iterator). The function must
        # materialise it so the error path can list what was attempted.
        def gen():
            yield ("manual", "ru")
            yield ("auto", "ru")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            with mock.patch.object(
                yt, "_try_download_subtitle"
            ) as patched:
                patched.return_value = (False, None, "no subs")
                with self.assertRaises(TranscriptFetchError) as ctx:
                    fetch_youtube_transcript(
                        "https://youtu.be/abc",
                        out,
                        fallback_ladder=gen(),
                        workdir=Path(td) / "workdir",
                    )
                msg = str(ctx.exception)
                self.assertIn("manual:ru", msg)
                self.assertIn("auto:ru", msg)


class TestSubprocessArgvShape(unittest.TestCase):
    """Verify the subprocess argv shape — `--` before URL, expected flags."""

    def test_argv_includes_double_dash_before_url(self) -> None:
        captured: dict = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            # Pretend yt-dlp succeeded but produced no file.
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            with mock.patch("subprocess.run", side_effect=fake_run):
                yt._try_download_subtitle(
                    url="https://youtu.be/abc",
                    lang="ru",
                    kind="auto",
                    workdir=workdir,
                    pre_existing=set(),
                    yt_dlp_bin=None,
                    timeout_sec=30,
                )
        args = captured["args"]
        # `--` must come immediately before the URL (the last element).
        self.assertEqual(args[-1], "https://youtu.be/abc")
        self.assertEqual(args[-2], "--")
        self.assertIn("--write-auto-subs", args)
        self.assertIn("--skip-download", args)


class TestRateLimitSurfacedInNote(unittest.TestCase):
    """When yt-dlp returns rc!=0 with a rate-limit phrase, the note
    must reflect that — not silently say 'no subtitle returned'."""

    def test_rate_limit_recorded_in_note(self) -> None:
        def fake_run(args, **kwargs):
            return mock.Mock(
                returncode=1,
                stdout="",
                stderr="ERROR: HTTP Error 429: Too Many Requests",
            )

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            with mock.patch("subprocess.run", side_effect=fake_run):
                ok, vtt, note = yt._try_download_subtitle(
                    url="https://youtu.be/abc",
                    lang="ru",
                    kind="auto",
                    workdir=workdir,
                    pre_existing=set(),
                    yt_dlp_bin=None,
                    timeout_sec=30,
                )
        self.assertFalse(ok)
        self.assertIsNone(vtt)
        self.assertIn("rate-limit", note)
        self.assertIn("429", note)
        self.assertNotEqual(note, "no subtitle returned for auto:ru")


@unittest.skipUnless(
    os.environ.get("TRANSCRIPT_FETCHER_E2E") == "1",
    "E2E network test disabled (set TRANSCRIPT_FETCHER_E2E=1 to enable)",
)
class TestYouTubeFetchE2E(unittest.TestCase):
    """Real-network smoke test. Disabled by default."""

    def test_fetch_real_video(self) -> None:
        from sources.youtube import fetch_youtube_transcript

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = fetch_youtube_transcript(
                "https://youtu.be/NSVTpCfBMK8",
                out,
            )
            self.assertGreater(stat.char_count, 1000)
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
