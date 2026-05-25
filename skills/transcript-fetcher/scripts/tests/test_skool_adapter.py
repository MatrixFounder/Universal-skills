"""Tests for the Skool adapter.

All tests are OFFLINE — network is bypassed via ``html_override``,
delegated YouTube/Vimeo fetchers are injected as mocks.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources import skool as sk  # noqa: E402
from sources._stat import TranscriptStat  # noqa: E402


_FIXTURES = _HERE / "fixtures"
# Identifiers must match the synthetic values used by the sanitiser
# (see scripts/tests/_sanitize_fixture.py::_SYNTHETIC). Real Skool
# UUIDs must never appear in this file.
_LESSON_URL = (
    "https://www.skool.com/example-community/classroom/aaaaaaaa"
    "?md=00000000000000000000000000000001"
)
_LESSON_ID = "00000000000000000000000000000001"
_LESSON_TITLE = "Fixture Lesson"
_LESSON_VIDEO_URL = "https://youtu.be/aaaaaaaaaaa"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------- #
# URL gate
# --------------------------------------------------------------------- #


class TestUrlGate(unittest.TestCase):
    def test_canonical_lesson_url(self) -> None:
        ref = sk.parse_skool_lesson_url(_LESSON_URL)
        self.assertEqual(ref.community, "example-community")
        self.assertEqual(ref.classroom_id, "aaaaaaaa")
        self.assertEqual(ref.lesson_id, _LESSON_ID)

    def test_app_subdomain_accepted(self) -> None:
        ref = sk.parse_skool_lesson_url(
            "https://app.skool.com/foo/classroom/bar?md=baz"
        )
        self.assertEqual(ref.community, "foo")

    def test_non_skool_host_rejected(self) -> None:
        with self.assertRaises(sk.SkoolUrlError):
            sk.parse_skool_lesson_url("https://example.com/x/classroom/y?md=z")

    def test_landing_page_rejected(self) -> None:
        with self.assertRaises(sk.SkoolUrlError):
            sk.parse_skool_lesson_url(
                "https://www.skool.com/example-community/about"
            )

    def test_missing_md_rejected(self) -> None:
        with self.assertRaises(sk.SkoolUrlError):
            sk.parse_skool_lesson_url(
                "https://www.skool.com/example-community/classroom/aaaaaaaa"
            )


# --------------------------------------------------------------------- #
# Parse + classify
# --------------------------------------------------------------------- #


class TestNextDataExtraction(unittest.TestCase):
    def test_lesson_extracted_from_fixture(self) -> None:
        html = _read("skool_lesson_youtube_embed.html")
        lesson = sk._extract_lesson(html, lesson_id=_LESSON_ID)
        self.assertEqual(lesson["id"], _LESSON_ID)
        md = lesson["metadata"]
        self.assertEqual(md["title"], _LESSON_TITLE)
        self.assertEqual(md["videoLink"], _LESSON_VIDEO_URL)
        self.assertEqual(md["videoLenMs"], 1082000)

    def test_landing_html_raises(self) -> None:
        html = _read("skool_community_landing.html")
        with self.assertRaises(sk.SkoolSchemaError):
            sk._extract_lesson(html, lesson_id=_LESSON_ID)

    def test_missing_next_data_raises(self) -> None:
        with self.assertRaises(sk.SkoolSchemaError):
            sk._extract_lesson("<html><body>no script</body></html>",
                               lesson_id=_LESSON_ID)


class TestEmbedClassification(unittest.TestCase):
    def test_youtube_short(self) -> None:
        self.assertEqual(sk._classify_embed_host("https://youtu.be/abc"), "youtube")

    def test_youtube_long(self) -> None:
        self.assertEqual(
            sk._classify_embed_host("https://www.youtube.com/watch?v=abc"),
            "youtube",
        )

    def test_vimeo(self) -> None:
        self.assertEqual(sk._classify_embed_host("https://vimeo.com/123"), "vimeo")

    def test_player_vimeo(self) -> None:
        self.assertEqual(
            sk._classify_embed_host("https://player.vimeo.com/video/123"),
            "vimeo",
        )

    def test_loom_is_other_host(self) -> None:
        self.assertEqual(
            sk._classify_embed_host("https://www.loom.com/share/abc"),
            "www.loom.com",
        )

    def test_none(self) -> None:
        self.assertEqual(sk._classify_embed_host(None), "none")

    def test_typosquat_youtube_not_youtube(self) -> None:
        # Regression: previous implementation used host.endswith("youtube.com")
        # which incorrectly matched arbitrary subdomains.
        self.assertNotEqual(
            sk._classify_embed_host("https://notyoutube.com/watch?v=abc"),
            "youtube",
        )
        self.assertNotEqual(
            sk._classify_embed_host("https://evilyoutube.com/watch?v=abc"),
            "youtube",
        )

    def test_typosquat_vimeo_not_vimeo(self) -> None:
        self.assertNotEqual(
            sk._classify_embed_host("https://notvimeo.com/123"),
            "vimeo",
        )

    def test_long_host_capped(self) -> None:
        long_host = "a" * 1000 + ".example.com"
        result = sk._classify_embed_host(f"https://{long_host}/x")
        self.assertLessEqual(len(result), sk._EMBED_HOST_LEN_CAP)


class TestFindNodeByIdConstraints(unittest.TestCase):
    """Regression: must only match nodes whose `metadata` is a dict."""

    def test_id_collision_with_non_lesson_node_is_skipped(self) -> None:
        tree = {
            "children": [
                # An id-collider that lacks `metadata` (e.g. a pinned post).
                {"id": "X", "type": "post"},
                # The real lesson, nested deeper.
                {"children": [
                    {"course": {"id": "X", "metadata": {"title": "real"}}}
                ]},
            ]
        }
        found = sk._find_node_by_id(tree, "X")
        self.assertIsNotNone(found)
        self.assertEqual(found["metadata"]["title"], "real")

    def test_depth_cap_does_not_recurse_forever(self) -> None:
        # Wrap a target deeper than _MAX_TREE_DEPTH; lookup should
        # return None instead of overflowing the iterative stack.
        node: dict = {"id": "leaf", "metadata": {}}
        for _ in range(sk._MAX_TREE_DEPTH + 10):
            node = {"child": node}
        self.assertIsNone(sk._find_node_by_id(node, "leaf"))


# --------------------------------------------------------------------- #
# Delegation
# --------------------------------------------------------------------- #


def _stub_yt_stat(out_path: Path, *, char: int = 150) -> TranscriptStat:
    return TranscriptStat(
        source="youtube",
        url=_LESSON_VIDEO_URL,
        video_id="aaaaaaaaaaa",
        output_path=str(out_path),
        chosen_track_kind="auto",
        chosen_track_lang="ru-orig",
        char_count=char,
        speaker_turn_count=2,
        notes=["got auto:ru-orig -> aaaaaaaaaaa.ru-orig.vtt"],
    )


class TestYoutubeDelegation(unittest.TestCase):
    def test_youtube_embed_delegates(self) -> None:
        html = _read("skool_lesson_youtube_embed.html")
        captured: dict = {}

        def fake_yt(url, out_path, *, fallback_ladder, timeout_sec, **kw):
            captured["url"] = url
            Path(out_path).write_text("stub transcript", encoding="utf-8")
            return _stub_yt_stat(out_path, char=15)

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
                _youtube_fetcher=fake_yt,
            )
        self.assertEqual(captured["url"], _LESSON_VIDEO_URL)
        self.assertEqual(stat.source, "skool")
        self.assertEqual(stat.embed_source, "youtube")
        self.assertEqual(stat.embed_url, _LESSON_VIDEO_URL)
        self.assertEqual(stat.chosen_track_kind, "auto")
        self.assertEqual(stat.chosen_track_lang, "ru-orig")
        self.assertEqual(stat.title, _LESSON_TITLE)
        self.assertEqual(stat.duration_sec, 1082)  # 1082000 ms -> 1082 s
        notes_joined = " | ".join(stat.notes)
        self.assertIn("delegated_to_youtube", notes_joined)


class TestVimeoDelegation(unittest.TestCase):
    def test_vimeo_embed_delegates(self) -> None:
        html = _read("skool_lesson_vimeo_embed.html")
        captured: dict = {}

        def fake_vimeo(url, out_path, *, fallback_ladder, timeout_sec, **kw):
            captured["url"] = url
            Path(out_path).write_text("vimeo stub", encoding="utf-8")
            return TranscriptStat(
                source="vimeo",
                url=url,
                video_id="76979871",
                output_path=str(out_path),
                chosen_track_kind="manual",
                chosen_track_lang="en",
                char_count=10,
                speaker_turn_count=0,
                notes=[],
            )

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
                _vimeo_fetcher=fake_vimeo,
            )
        self.assertEqual(captured["url"], "https://vimeo.com/76979871")
        self.assertEqual(stat.embed_source, "vimeo")
        notes_joined = " | ".join(stat.notes)
        self.assertIn("delegated_to_vimeo", notes_joined)

    def test_vimeo_delegation_failure_flags_quality(self) -> None:
        html = _read("skool_lesson_vimeo_embed.html")

        def fake_vimeo(*a, **kw):
            raise RuntimeError("simulated yt-dlp failure")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
                _vimeo_fetcher=fake_vimeo,
                with_description=True,
            )
        self.assertEqual(stat.quality_flag, "vimeo_embed_unsupported")
        self.assertTrue(stat.description_path)


class TestUnsupportedEmbed(unittest.TestCase):
    def test_loom_flags_unsupported(self) -> None:
        html = _read("skool_lesson_loom_embed.html")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
                with_description=True,  # always need this for unsupported embed
            )
        self.assertEqual(stat.embed_source, "www.loom.com")
        self.assertEqual(stat.quality_flag, "embed_source_unsupported")
        self.assertTrue(stat.description_path)


class TestTranscriptFieldPath(unittest.TestCase):
    def test_author_transcript_used(self) -> None:
        html = _read("skool_lesson_with_transcript.html")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
            )
            self.assertEqual(stat.chosen_track_kind, "skool_manual")
            self.assertGreater(stat.char_count, 0)
            self.assertTrue(out.exists())
            text = out.read_text(encoding="utf-8")
            self.assertIn("Welcome to the lesson", text)


# --------------------------------------------------------------------- #
# Description sidecar
# --------------------------------------------------------------------- #


class TestDescriptionSidecar(unittest.TestCase):
    def test_with_description_writes_md_with_lesson_frontmatter(self) -> None:
        html = _read("skool_lesson_youtube_embed.html")

        def fake_yt(url, out_path, *, fallback_ladder, timeout_sec, **kw):
            Path(out_path).write_text("yt content", encoding="utf-8")
            return _stub_yt_stat(out_path)

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            stat = sk.fetch_skool_transcript(
                _LESSON_URL,
                out,
                cookies_file=None,
                html_override=html,
                _youtube_fetcher=fake_yt,
                with_description=True,
            )
            self.assertTrue(stat.description_path)
            text = Path(stat.description_path).read_text(encoding="utf-8")
            # Frontmatter assertions
            self.assertIn("source: skool", text)
            self.assertIn("community: example-community", text)
            self.assertIn(f"lesson_id: {_LESSON_ID}", text)
            self.assertIn("embed_source: youtube", text)
            # URLs contain ':' → YAML writer double-quotes them.
            self.assertIn(f'embed_url: "{_LESSON_VIDEO_URL}"', text)
            # H1 from title
            self.assertIn(f"# {_LESSON_TITLE}", text)
            # The body has horizontal-rule + code block from prosemirror.
            self.assertIn("---", text)
            self.assertIn("```", text)


# --------------------------------------------------------------------- #
# Auth surface
# --------------------------------------------------------------------- #


class TestAuthErrors(unittest.TestCase):
    def test_http_401_raises_source_auth_error(self) -> None:
        """A private/paid Skool lesson responds 401 — surface as auth error."""
        from sources._stat import SourceAuthError
        from urllib.error import HTTPError
        import io

        def fake_open(req, timeout=None):
            raise HTTPError(
                _LESSON_URL, 401, "Unauthorized", {}, io.BytesIO(b""),
            )
        opener = mock.Mock()
        opener.open = fake_open
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            with mock.patch.object(
                sk, "build_authenticated_opener", return_value=opener
            ):
                with self.assertRaises(SourceAuthError):
                    sk.fetch_skool_transcript(
                        _LESSON_URL, out, cookies_file=None,
                    )


if __name__ == "__main__":
    unittest.main()
