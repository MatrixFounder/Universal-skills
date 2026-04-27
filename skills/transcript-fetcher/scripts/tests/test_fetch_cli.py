"""CLI-level tests for ``fetch.py``.

Exercises:
- The hostname-allowlist source dispatch (``_detect_source``).
- The batch-mode output-path collision policy (``_resolve_batch_path``).
- The error envelope in JSON-mode.
- Argument validation (mutually-exclusive modes, required flags).

All tests are offline; subprocess calls into yt-dlp are mocked.
"""
from __future__ import annotations

import io
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

import fetch  # noqa: E402


class TestSourceDetect(unittest.TestCase):
    def test_youtube_short_form(self) -> None:
        self.assertEqual(fetch._detect_source("https://youtu.be/abc"), "youtube")

    def test_youtube_main(self) -> None:
        self.assertEqual(
            fetch._detect_source("https://www.youtube.com/watch?v=abc"),
            "youtube",
        )

    def test_youtube_music(self) -> None:
        self.assertEqual(
            fetch._detect_source("https://music.youtube.com/watch?v=abc"),
            "youtube",
        )

    def test_substring_match_rejected(self) -> None:
        # A path containing 'youtube.com' must NOT match.
        with self.assertRaises(ValueError):
            fetch._detect_source("https://malicious.com/?ref=youtube.com")

    def test_typosquat_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fetch._detect_source("https://phishing-youtu.be.evil.com/abc")

    def test_unsupported_host_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fetch._detect_source("https://vimeo.com/12345")


class TestBatchCollisionResolution(unittest.TestCase):
    def test_error_policy_raises_on_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            seen: set = set()
            url = "https://youtu.be/abcdefghijk"  # 11-char id
            p1 = fetch._resolve_batch_path(url, out_dir, seen, "error")
            self.assertIsNotNone(p1)
            with self.assertRaises(fetch._BatchCollisionError):
                fetch._resolve_batch_path(url, out_dir, seen, "error")

    def test_skip_policy_returns_none_on_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            seen: set = set()
            url = "https://youtu.be/abcdefghijk"
            fetch._resolve_batch_path(url, out_dir, seen, "skip")
            second = fetch._resolve_batch_path(url, out_dir, seen, "skip")
            self.assertIsNone(second)

    def test_suffix_policy_appends_numeric_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            seen: set = set()
            url = "https://youtu.be/abcdefghijk"
            p1 = fetch._resolve_batch_path(url, out_dir, seen, "suffix")
            p2 = fetch._resolve_batch_path(url, out_dir, seen, "suffix")
            p3 = fetch._resolve_batch_path(url, out_dir, seen, "suffix")
            self.assertEqual(p1, out_dir / "abcdefghijk.txt")
            self.assertEqual(p2, out_dir / "abcdefghijk-2.txt")
            self.assertEqual(p3, out_dir / "abcdefghijk-3.txt")
            # All three are distinct.
            self.assertEqual(len({p1, p2, p3}), 3)


class TestSlugify(unittest.TestCase):
    def test_alphanumeric_passthrough(self) -> None:
        self.assertEqual(fetch._slugify("abc123"), "abc123")

    def test_special_chars_replaced(self) -> None:
        out = fetch._slugify("https://x.com/a?b=c")
        for ch in out:
            self.assertTrue(
                ch.isalnum() or ch in ("-", "_"),
                f"Unexpected char {ch!r} in slug",
            )

    def test_truncated_to_64(self) -> None:
        self.assertLessEqual(len(fetch._slugify("a" * 200)), 64)

    def test_empty_input_yields_default(self) -> None:
        self.assertEqual(fetch._slugify(""), "transcript")


class TestErrorEnvelope(unittest.TestCase):
    def test_json_error_shape(self) -> None:
        # Capture stderr while emitting a JSON-mode error.
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            rc = fetch._emit_error(
                "boom",
                code=3,
                error_type="MyType",
                details={"a": 1},
                json_mode=True,
            )
        self.assertEqual(rc, 3)
        line = buf.getvalue().strip()
        payload = json.loads(line)
        self.assertEqual(payload["v"], 1)
        self.assertEqual(payload["error"], "boom")
        self.assertEqual(payload["code"], 3)
        self.assertEqual(payload["type"], "MyType")
        self.assertEqual(payload["details"], {"a": 1})

    def test_zero_code_coerced_to_one(self) -> None:
        # Failures should never exit 0; the helper coerces.
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            rc = fetch._emit_error("oops", code=0)
        self.assertEqual(rc, 1)


class TestCliArgValidation(unittest.TestCase):
    def test_missing_url_and_batch_returns_2(self) -> None:
        rc = fetch.main([])
        self.assertEqual(rc, 2)

    def test_both_url_and_batch_returns_2(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("https://youtu.be/abc\n")
            batch_path = f.name
        try:
            rc = fetch.main(
                ["https://youtu.be/abc", "--batch", batch_path, "--out", "/tmp/x"]
            )
            self.assertEqual(rc, 2)
        finally:
            Path(batch_path).unlink(missing_ok=True)

    def test_negative_timeout_rejected(self) -> None:
        rc = fetch.main(
            ["https://youtu.be/abc", "--out", "/tmp/x", "--timeout-sec", "-5"]
        )
        self.assertEqual(rc, 2)

    def test_single_url_without_out_returns_2(self) -> None:
        rc = fetch.main(["https://youtu.be/abc"])
        self.assertEqual(rc, 2)


class TestBatchMode(unittest.TestCase):
    """Integration test for batch mode with mocked transcript fetching."""

    def test_batch_processes_each_url(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            batch_file = Path(td) / "urls.txt"
            batch_file.write_text(
                "# this is a comment\n"
                "https://youtu.be/aaaaaaaaaaa\n"
                "\n"
                "https://youtu.be/bbbbbbbbbbb\n",
                encoding="utf-8",
            )

            captured_calls: list = []

            def fake_fetch_one(url, out_path, *, lang, prefer, timeout_sec):
                captured_calls.append(url)
                # Pretend each URL produced a 100-char transcript.
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_text("hello", encoding="utf-8")
                return {
                    "source": "youtube",
                    "url": url,
                    "video_id": fetch.extract_video_id(url),
                    "output_path": str(out_path),
                    "char_count": 5,
                    "speaker_turn_count": 0,
                }

            with mock.patch.object(fetch, "_fetch_one", side_effect=fake_fetch_one):
                rc = fetch.main(
                    ["--batch", str(batch_file), "--out-dir", str(out_dir)]
                )
        self.assertEqual(rc, 0)
        self.assertEqual(len(captured_calls), 2)
        self.assertIn("https://youtu.be/aaaaaaaaaaa", captured_calls)
        self.assertIn("https://youtu.be/bbbbbbbbbbb", captured_calls)

    def test_batch_collision_error_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            batch_file = Path(td) / "urls.txt"
            # Same URL twice (or same video, different forms) -> collision.
            batch_file.write_text(
                "https://youtu.be/aaaaaaaaaaa\n"
                "https://www.youtube.com/watch?v=aaaaaaaaaaa\n",
                encoding="utf-8",
            )

            def fake_fetch_one(*args, **kwargs):
                # First call succeeds; second won't be reached because
                # the resolver raises on duplicate.
                return {
                    "source": "youtube",
                    "url": args[0],
                    "char_count": 5,
                    "speaker_turn_count": 0,
                }

            with mock.patch.object(fetch, "_fetch_one", side_effect=fake_fetch_one):
                rc = fetch.main(
                    ["--batch", str(batch_file), "--out-dir", str(out_dir)]
                )
        # Default --on-collision=error -> partial failure -> rc 4.
        self.assertEqual(rc, 4)


if __name__ == "__main__":
    unittest.main()
