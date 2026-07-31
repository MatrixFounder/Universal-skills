"""Tests for the Yandex VH/Strm adapter.

Focus is the traps the adapter exists to avoid (see the module docstring of
``sources/yandex.py``) plus the defects an adversarial review reproduced
against the first revision. Every regression class below traces to a
finding that was independently reproduced, not to a hypothetical:

* the config JSON's ``duration`` field lies -> the real duration must come
  from summing ``#EXTINF``;
* ``download_audio`` returns a path even when yt-dlp FAILED, which silently
  defeated the DASH->HLS fallback and swallowed the error;
* a stream URL from remote JSON is untrusted, and the pre-flight allowlist
  check said nothing about where the bytes finally came from (redirects);
* the description sidecar must go through the shared writer, not a fork.

Where a test drives the download path it uses the REAL ``download_audio``
return contract (a path may come back alongside a non-empty stderr) rather
than the shape the author first imagined — mocking that contract wrongly is
exactly what let the fallback bug ship.
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

from sources import yandex as yx  # noqa: E402
from sources._stat import (  # noqa: E402
    MissingDependencyError,
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
)

STREAMS = {
    "hls": "https://strm.yandex.ru/vod/x/master.m3u8",
    "dash": "https://strm.yandex.ru/vod/x/manifest.mpd",
}
EP = "vple7dqmd5w2awbjijmo"
URL = f"https://runtime.strm.yandex.ru/player/episode/{EP}"


def _resolved(**over) -> dict:
    out = {
        **STREAMS,
        "episode_id": EP,
        "title": "Глубокое погружение",
        "description": "Дмитрий Рыбалко и Сергей Золотов…",
        "json_duration": 4365,   # WRONG on purpose; real is 3800
        "rejected": [],
    }
    out.update(over)
    return out


class TestEpisodeIdExtraction(unittest.TestCase):
    def test_runtime_strm_canonical(self) -> None:
        self.assertEqual(yx.extract_episode_id(URL), EP)

    def test_with_query_params(self) -> None:
        self.assertEqual(
            yx.extract_episode_id(
                "https://runtime.strm.yandex.ru/player/episode/"
                "vplefi4lxqhmuvgzujwm?autoplay=1&mute=1"
            ),
            "vplefi4lxqhmuvgzujwm",
        )

    def test_frontend_vh_form(self) -> None:
        self.assertEqual(
            yx.extract_episode_id(
                "https://frontend.vh.yandex.ru/player/vplegzpe463wsyw4qk7j"
            ),
            "vplegzpe463wsyw4qk7j",
        )

    def test_unrelated_url_returns_none(self) -> None:
        self.assertIsNone(yx.extract_episode_id("https://www.youtube.com/watch?v=abc"))

    def test_empty_and_junk(self) -> None:
        self.assertIsNone(yx.extract_episode_id(""))
        self.assertIsNone(yx.extract_episode_id("not a url"))

    def test_too_short_id_rejected(self) -> None:
        self.assertIsNone(
            yx.extract_episode_id("https://runtime.strm.yandex.ru/player/episode/short")
        )

    def test_foreign_host_with_matching_path_is_rejected(self) -> None:
        """The adapter is a public entry point, not just a CLI dispatch target.

        The `/player/episode/<id>` path shape used to match on ANY host, so a
        direct library call recorded an attacker-supplied URL in `stat.url`
        next to content actually fetched from runtime.strm.yandex.ru.
        """
        self.assertIsNone(
            yx.extract_episode_id("https://evil.example.com/player/episode/abcdefghij")
        )
        self.assertFalse(yx.is_yandex_player_url("https://evil.example.com/x"))
        self.assertTrue(yx.is_yandex_player_url(URL))

    def test_overlong_id_is_rejected_not_silently_truncated(self) -> None:
        """A 100-char slug must NOT be captured truncated at 64 chars.

        Truncating produced a DIFFERENT, valid-looking id, so the adapter
        would confidently resolve the wrong episode.
        """
        long_id = "a" * 100
        self.assertIsNone(
            yx.extract_episode_id(
                f"https://runtime.strm.yandex.ru/player/episode/{long_id}"
            )
        )


class TestEpisodeIdIsUrlSafe(unittest.TestCase):
    """The id is interpolated into CONFIG_ENDPOINT — it must not escape it."""

    def test_fullmatch_rejects_path_and_query_chars(self) -> None:
        for bad in ("abc/def/ghi", "abcdefgh?x=1", "abcdefgh#frag", "http://evil.com"):
            self.assertIsNone(
                yx._EPISODE_ID_RE.fullmatch(bad),
                f"{bad!r} must not be a valid episode id",
            )

    def test_trailing_newline_rejected(self) -> None:
        """`re.match` + `$` accepts a trailing newline; `fullmatch` must not.

        The newline reached http.client as a control character in the URL.
        """
        self.assertIsNone(yx._EPISODE_ID_RE.fullmatch("abcdefgh\n"))

    def test_resolve_streams_refuses_malformed_id(self) -> None:
        with self.assertRaises(TranscriptFetchError):
            yx.resolve_streams("../../etc/passwd")

    def test_resolve_streams_refuses_trailing_newline_id(self) -> None:
        with mock.patch.object(yx, "_http_get") as m:
            with self.assertRaises(TranscriptFetchError):
                yx.resolve_streams("abcdefgh\n")
        m.assert_not_called()


class TestStreamUrlAllowlist(unittest.TestCase):
    def test_stream_hosts_allowed(self) -> None:
        for url in (
            "https://strm.yandex.ru/vod/whatever/master.m3u8",
            "https://runtime.strm.yandex.ru/x.mpd",
        ):
            self.assertTrue(yx._is_allowed_stream_url(url), url)

    def test_foreign_host_refused(self) -> None:
        self.assertFalse(yx._is_allowed_stream_url("https://evil.example.com/a.m3u8"))

    def test_lookalike_host_refused(self) -> None:
        self.assertFalse(yx._is_allowed_stream_url("https://yandex.ru.evil.com/a.m3u8"))

    def test_plain_http_refused(self) -> None:
        self.assertFalse(yx._is_allowed_stream_url("http://strm.yandex.ru/a.m3u8"))

    def test_user_controlled_object_storage_refused(self) -> None:
        """`*.yandexcloud.net` is object storage — anyone can make a bucket.

        A suffix rule there turned the allowlist into an open redirect.
        """
        self.assertFalse(
            yx._is_allowed_stream_url("https://mybucket.storage.yandexcloud.net/e.m3u8")
        )
        self.assertFalse(
            yx._is_allowed_stream_url("https://storage.yandexcloud.net/a/b.m3u8")
        )

    def test_malformed_url_returns_false_not_valueerror(self) -> None:
        """urlparse raises on a bad IPv6 literal; that must not escape."""
        self.assertFalse(yx._is_allowed_stream_url("https://[oops/a.m3u8"))

    def test_userinfo_cannot_smuggle_an_allowed_host(self) -> None:
        self.assertFalse(
            yx._is_allowed_stream_url("https://strm.yandex.ru@evil.example.com/a.m3u8")
        )


def _config_payload(**over) -> bytes:
    doc = {
        "content": {
            "content_id": EP,
            "title": "Глубокое погружение в работу с LLM и агентскими API",
            "description": "Дмитрий Рыбалко и Сергей Золотов…",
            "duration": 4365,   # WRONG on purpose — real is 3800
            "streams": [
                {"type": "hls", "url": STREAMS["hls"]},
                {"type": "dash", "url": STREAMS["dash"]},
            ],
        }
    }
    doc["content"].update(over)
    return json.dumps(doc).encode("utf-8")


class TestResolveStreams(unittest.TestCase):
    def test_happy_path(self) -> None:
        with mock.patch.object(yx, "_http_get", return_value=_config_payload()):
            got = yx.resolve_streams(EP)
        self.assertEqual(got["hls"], STREAMS["hls"])
        self.assertEqual(got["dash"], STREAMS["dash"])
        self.assertEqual(got["json_duration"], 4365)
        self.assertIn("LLM", got["title"])

    def test_offhost_stream_is_dropped_and_recorded(self) -> None:
        payload = _config_payload(
            streams=[
                {"type": "hls", "url": "https://evil.example.com/master.m3u8"},
                {"type": "dash", "url": STREAMS["dash"]},
            ]
        )
        with mock.patch.object(yx, "_http_get", return_value=payload):
            got = yx.resolve_streams(EP)
        self.assertIsNone(got["hls"], "off-host HLS must never reach yt-dlp")
        self.assertEqual(got["dash"], STREAMS["dash"])
        self.assertTrue(
            any("evil.example.com" in r for r in got["rejected"]),
            "the skip must be observable, not a silent `continue`",
        )

    def test_no_usable_stream_raises_and_names_the_rejects(self) -> None:
        payload = _config_payload(
            streams=[{"type": "hls", "url": "https://evil.example.com/master.m3u8"}]
        )
        with mock.patch.object(yx, "_http_get", return_value=payload):
            with self.assertRaises(TranscriptFetchError) as cm:
                yx.resolve_streams(EP)
        self.assertIn("evil.example.com", str(cm.exception))

    def test_invalid_json_raises_fetch_error(self) -> None:
        with mock.patch.object(yx, "_http_get", return_value=b"<html>captcha</html>"):
            with self.assertRaises(TranscriptFetchError):
                yx.resolve_streams(EP)

    def test_non_object_json_raises_fetch_error_not_attributeerror(self) -> None:
        """`[]` is valid JSON — it used to reach .get() and die as exit 1."""
        for payload in (b"[]", b'"x"', b"null", b"3"):
            with self.subTest(payload=payload):
                with mock.patch.object(yx, "_http_get", return_value=payload):
                    with self.assertRaises(TranscriptFetchError):
                        yx.resolve_streams(EP)


_MASTER = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=348328,RESOLUTION=256x144
/vod/x/index-v1-a1.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3591790,RESOLUTION=1920x1080
/vod/x/index-v6-a1.m3u8
"""

# 760 segments x 5.0 s = 3800 s — the REAL duration, vs the config's 4365.
_MEDIA = (
    "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n"
    + "".join("#EXTINF:5.000,\nseg.ts\n" for _ in range(760))
    + "#EXT-X-ENDLIST\n"
)


class TestRealDurationBeatsJsonField(unittest.TestCase):
    """Trap 1 — the config's ``duration`` must never be used as the truth."""

    def _fake_get(self, url, *, timeout_sec, cookies_file=None):
        return (_MASTER if url.endswith("master.m3u8") else _MEDIA).encode()

    def test_sums_extinf_from_media_playlist(self) -> None:
        with mock.patch.object(yx, "_http_get", side_effect=self._fake_get):
            secs = yx.probe_duration_via_manifest(STREAMS["hls"])
        self.assertEqual(secs, 3800)
        self.assertNotEqual(secs, 4365, "must not fall back to the JSON duration")

    def test_variant_url_is_resolved_relative_to_master(self) -> None:
        seen: list[str] = []

        def fake(url, *, timeout_sec, cookies_file=None):
            seen.append(url)
            return (_MASTER if url.endswith("master.m3u8") else _MEDIA).encode()

        with mock.patch.object(yx, "_http_get", side_effect=fake):
            yx.probe_duration_via_manifest(STREAMS["hls"])
        self.assertEqual(seen[1], "https://strm.yandex.ru/vod/x/index-v1-a1.m3u8")

    def test_media_playlist_passed_directly(self) -> None:
        with mock.patch.object(
            yx, "_http_get",
            side_effect=lambda u, *, timeout_sec, cookies_file=None: _MEDIA.encode(),
        ):
            self.assertEqual(
                yx.probe_duration_via_manifest("https://strm.yandex.ru/vod/x/m.m3u8"),
                3800,
            )

    def test_unreachable_manifest_returns_none_not_a_lie(self) -> None:
        with mock.patch.object(
            yx, "_http_get", side_effect=TranscriptFetchError("boom")
        ):
            self.assertIsNone(yx.probe_duration_via_manifest(STREAMS["hls"]))

    def test_sum_extinf_empty(self) -> None:
        self.assertIsNone(yx._sum_extinf("#EXTM3U\n#EXT-X-ENDLIST\n"))

    def test_sum_extinf_overflow_returns_none_not_overflowerror(self) -> None:
        """A huge literal overflows to inf, and int(round(inf)) raises.

        Note the regex has no exponent branch, so `1e400` is NOT the trigger
        (it matches just the `1`) — it takes ~309+ digits to reach inf.
        """
        huge = "9" * 400
        self.assertIsNone(yx._sum_extinf(f"#EXTINF:{huge},\nseg.ts\n"))


class TestManifestOrdering(unittest.TestCase):
    """ffmpeg cannot open Yandex's DASH manifest, so a CLIPPED run needs HLS."""

    def test_unclipped_prefers_dash_for_audio_only_bytes(self) -> None:
        self.assertEqual(
            [k for k, _ in yx.manifest_candidates(STREAMS, clipping=False)],
            ["dash", "hls"],
        )

    def test_clipped_prefers_hls_because_ffmpeg_cannot_open_dash(self) -> None:
        self.assertEqual(
            [k for k, _ in yx.manifest_candidates(STREAMS, clipping=True)],
            ["hls", "dash"],
        )

    def test_missing_format_is_skipped(self) -> None:
        self.assertEqual(
            yx.manifest_candidates({"hls": None, "dash": STREAMS["dash"]}, clipping=True),
            [("dash", STREAMS["dash"])],
        )


class _FetchHarness(unittest.TestCase):
    """Drives the real fetch_yandex_transcript with only the edges stubbed."""

    def _run(self, download, *, streams=None, **kw):
        calls: list[str] = []

        def wrapped(url, workdir, **kwargs):
            calls.append(url)
            return download(url, Path(workdir), **kwargs)

        with mock.patch.object(yx, "resolve_streams",
                               return_value=streams or _resolved()), \
             mock.patch.object(yx, "probe_duration_via_manifest", return_value=3800), \
             mock.patch.object(yx.ytm, "ffmpeg_available", return_value=True), \
             mock.patch.object(yx.ytm, "download_audio", side_effect=wrapped), \
             mock.patch.object(yx.ytm, "remove_silence", return_value=(None, "n/a")), \
             mock.patch.object(yx.ytm, "probe_media_duration", return_value=3800), \
             mock.patch.dict(sys.modules, {"asr": mock.MagicMock()}):
            sys.modules["asr"].transcribe_with_fallback.return_value = mock.Mock(
                text="привет", language="ru", backend_name="macwhisper", model="m"
            )
            with tempfile.TemporaryDirectory() as td:
                stat = yx.fetch_yandex_transcript(URL, Path(td) / "out.txt", **kw)
        return stat, calls


class TestDownloadFailureIsNotMistakenForSuccess(_FetchHarness):
    """`download_audio` returns a path even when yt-dlp EXITED NON-ZERO.

    Gating the fallback on `media is not None` alone let a postprocessor
    failure look like success: HLS was never tried and the real stderr was
    discarded. Mocking `(None, err)` — the shape the author imagined — never
    exercised this.
    """

    def test_path_with_stderr_is_a_failure_and_falls_back(self) -> None:
        def dl(url, workdir, **kw):
            f = workdir / "media.mp4"
            f.write_bytes(b"x" * 32)
            if url.endswith(".mpd"):
                # Complete file, non-zero rc — the real postprocessor failure.
                return f, "ERROR: Postprocessing: Invalid data found"
            return f, None

        stat, calls = self._run(dl)
        self.assertEqual(len(calls), 2, "DASH 'success' with stderr must not stop the loop")
        self.assertTrue(calls[0].endswith(".mpd"))
        self.assertTrue(calls[1].endswith(".m3u8"))
        self.assertIn("fell back to HLS manifest", " ".join(stat.notes))

    def test_stale_artifact_is_purged_between_attempts(self) -> None:
        """Candidate 2 must not inherit candidate 1's leftover `media.*`."""
        seen: list[list[str]] = []

        def dl(url, workdir, **kw):
            seen.append(sorted(p.name for p in workdir.glob("media.*")))
            f = workdir / "media.mp4"
            f.write_bytes(b"x" * 32)
            if url.endswith(".mpd"):
                return f, "ERROR: boom"
            return f, None

        self._run(dl)
        self.assertEqual(seen[0], [], "workdir must start clean")
        self.assertEqual(seen[1], [], "stale media.* from attempt 1 must be purged")

    def test_all_manifests_failing_raises(self) -> None:
        def dl(url, workdir, **kw):
            f = workdir / "media.mp4"
            f.write_bytes(b"x")
            return f, "ERROR: boom"

        with self.assertRaises(TranscriptFetchError):
            self._run(dl)


class TestMediaFailureExitCodes(_FetchHarness):
    """A 403 must not report the exit code documented for 'no transcript'."""

    def test_auth_failure_becomes_source_auth_error(self) -> None:
        def dl(url, workdir, **kw):
            return None, "ERROR: unable to download: HTTP Error 403: Forbidden"

        with self.assertRaises(SourceAuthError):
            self._run(dl)

    def test_rate_limit_becomes_source_rate_limit_error(self) -> None:
        def dl(url, workdir, **kw):
            return None, "ERROR: HTTP Error 429: Too Many Requests"

        with self.assertRaises(SourceRateLimitError):
            self._run(dl)

    def test_generic_failure_stays_fetch_error(self) -> None:
        def dl(url, workdir, **kw):
            return None, "ERROR: something else entirely"

        with self.assertRaises(TranscriptFetchError):
            self._run(dl)


class TestDurationAndBudget(_FetchHarness):
    def test_real_duration_not_json_duration_in_stat(self) -> None:
        stat, _ = self._run(
            lambda u, w, **k: ((w / "media.m4a").write_bytes(b"x") or (w / "media.m4a"), None)
        )
        self.assertEqual(stat.duration_sec, 3800)
        self.assertNotEqual(stat.duration_sec, 4365)
        self.assertTrue(any("is wrong — ignored" in n for n in stat.notes))

    def test_budget_is_clamped_by_max_duration_min(self) -> None:
        """Deriving the budget from the FULL duration hands a 6 h ceiling to a
        10 min clipped job, turning a stall into a 6 h hang."""
        budgets: list[int] = []

        def dl(url, workdir, **kw):
            budgets.append(kw["timeout_sec"])
            f = workdir / "media.m4a"
            f.write_bytes(b"x")
            return f, None

        self._run(dl, max_duration_min=10)
        self.assertEqual(budgets[0], yx.ytm.media_timeout_for(600))
        self.assertLess(budgets[0], yx.ytm.media_timeout_for(3800))

    def test_dash_only_config_notes_the_unknown_duration(self) -> None:
        stat, _ = self._run(
            lambda u, w, **k: ((w / "media.m4a").write_bytes(b"x") or (w / "media.m4a"), None),
            streams=_resolved(hls=None),
        )
        self.assertTrue(
            any("duration: unknown" in n for n in stat.notes),
            "a silent short budget on a long recording looks like a hang",
        )


class TestDescriptionSidecar(_FetchHarness):
    """The sidecar must go through the shared writer, not a fork."""

    def _sidecar(self, **kw):
        with mock.patch.object(yx, "resolve_streams", return_value=_resolved(**kw)), \
             mock.patch.object(yx, "probe_duration_via_manifest", return_value=3800), \
             mock.patch.object(yx.ytm, "ffmpeg_available", return_value=True):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "talk.txt"
                stat = yx.fetch_yandex_transcript(
                    URL, out, description_only=True
                )
                return stat, Path(stat.description_path).read_text(encoding="utf-8")

    def test_has_yaml_frontmatter(self) -> None:
        _, text = self._sidecar()
        self.assertTrue(text.startswith("---\n"), "documented format is YAML frontmatter")
        self.assertIn("source: yandex", text)
        self.assertIn("duration_sec: 3800", text)

    def test_sidecar_path_matches_shared_convention(self) -> None:
        stat, _ = self._sidecar()
        self.assertTrue(stat.description_path.endswith("talk.description.md"))

    def test_hostile_title_cannot_forge_a_heading(self) -> None:
        """Title is unescaped remote data; `# X` must not become a real H1."""
        _, text = self._sidecar(title="# Injected")
        self.assertNotIn("\n# # Injected", text)

    def test_description_only_needs_no_ffmpeg(self) -> None:
        """`--description-only` touches no media, so an ffmpeg-less box must
        still produce the sidecar (the guard used to fire far too early)."""
        with mock.patch.object(yx, "resolve_streams", return_value=_resolved()), \
             mock.patch.object(yx, "probe_duration_via_manifest", return_value=3800), \
             mock.patch.object(yx.ytm, "ffmpeg_available", return_value=False):
            with tempfile.TemporaryDirectory() as td:
                stat = yx.fetch_yandex_transcript(
                    URL, Path(td) / "o.txt", description_only=True
                )
                # Assert INSIDE the context manager — the tempdir is gone after.
                self.assertTrue(Path(stat.description_path).exists())


class TestHttpHardening(unittest.TestCase):
    def test_redirects_are_pinned_to_the_allowlist(self) -> None:
        """The pre-flight check is on the PRE-redirect URL; urllib's default
        opener happily follows a cross-host 302, so the bytes could come from
        anywhere. `_http_get` must use the restricted opener."""
        import sources._cookies as ck

        with mock.patch.object(
            ck, "build_authenticated_opener", wraps=ck.build_authenticated_opener
        ) as spy, mock.patch.object(yx, "build_authenticated_opener", spy):
            with self.assertRaises(Exception):
                yx._http_get("https://strm.yandex.ru/x", timeout_sec=1)
        self.assertTrue(spy.called, "must not fall back to the global opener")
        hosts = spy.call_args.kwargs.get("allowed_hosts")
        self.assertIsNotNone(hosts, "redirects must be host-pinned")
        self.assertNotIn("evil.example.com", set(hosts))

    def test_oversized_response_is_refused(self) -> None:
        big = b"x" * (yx._MAX_DOC_BYTES + 10)

        class _Resp:
            def read(self, n=-1):
                return big[:n] if n and n > 0 else big
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        opener = mock.Mock()
        opener.open.return_value = _Resp()
        with mock.patch.object(yx, "build_authenticated_opener", return_value=opener):
            with self.assertRaises(TranscriptFetchError):
                yx._http_get("https://strm.yandex.ru/x", timeout_sec=5)

    def _http_error(self, code: int):
        import urllib.error
        return urllib.error.HTTPError("u", code, "msg", {}, None)

    def _with_error(self, exc):
        opener = mock.Mock()
        opener.open.side_effect = exc
        return mock.patch.object(yx, "build_authenticated_opener", return_value=opener)

    def test_403_becomes_auth_error(self) -> None:
        with self._with_error(self._http_error(403)):
            with self.assertRaises(SourceAuthError):
                yx._http_get("https://strm.yandex.ru/x", timeout_sec=5)

    def test_429_becomes_rate_limit(self) -> None:
        with self._with_error(self._http_error(429)):
            with self.assertRaises(SourceRateLimitError):
                yx._http_get("https://strm.yandex.ru/x", timeout_sec=5)

    def test_500_becomes_fetch_error(self) -> None:
        with self._with_error(self._http_error(500)):
            with self.assertRaises(TranscriptFetchError):
                yx._http_get("https://strm.yandex.ru/x", timeout_sec=5)

    def test_read_phase_failures_are_typed_not_raw(self) -> None:
        """urllib does NOT wrap failures raised during read(): a half-sent body
        surfaced as a bare TimeoutError/IncompleteRead and escaped as exit 1."""
        import http.client

        for exc in (TimeoutError("timed out"), http.client.IncompleteRead(b"ab")):
            with self.subTest(exc=type(exc).__name__):
                with self._with_error(exc):
                    with self.assertRaises(TranscriptFetchError):
                        yx._http_get("https://strm.yandex.ru/x", timeout_sec=5)

    def test_probe_degrades_to_none_on_read_phase_failure(self) -> None:
        with self._with_error(TimeoutError("timed out")):
            self.assertIsNone(yx.probe_duration_via_manifest(STREAMS["hls"]))


class TestNoCaptionLadder(unittest.TestCase):
    """The adapter is ASR-only by design — it must not grow a caption path.

    The first version asserted only that three NAMES were absent, which the
    caption-carrying siblings also satisfy (proved by an adversarial review),
    so it had zero discriminating power. Assert on behaviour instead.
    """

    def test_module_never_downloads_captions(self) -> None:
        import inspect
        src = inspect.getsource(yx)
        for token in ("download_captions", "download_subtitle", "pick_caption",
                      "automatic_captions", "write-subs", "--sub-langs"):
            self.assertNotIn(token, src, f"{token} implies a caption path")

    def test_stat_always_reports_asr_provenance(self) -> None:
        """A caption path would show up as a non-'asr' chosen_track_kind."""
        with mock.patch.object(yx, "resolve_streams", return_value=_resolved()), \
             mock.patch.object(yx, "probe_duration_via_manifest", return_value=3800), \
             mock.patch.object(yx.ytm, "ffmpeg_available", return_value=True), \
             mock.patch.object(
                 yx.ytm, "download_audio",
                 side_effect=lambda u, w, **k: (
                     (Path(w) / "media.m4a").write_bytes(b"x") or Path(w) / "media.m4a", None)), \
             mock.patch.object(yx.ytm, "remove_silence", return_value=(None, "n/a")), \
             mock.patch.dict(sys.modules, {"asr": mock.MagicMock()}):
            sys.modules["asr"].transcribe_with_fallback.return_value = mock.Mock(
                text="привет", language="ru", backend_name="macwhisper", model="m"
            )
            with tempfile.TemporaryDirectory() as td:
                stat = yx.fetch_yandex_transcript(URL, Path(td) / "o.txt")
        self.assertEqual(stat.chosen_track_kind, "asr")
        self.assertEqual(stat.transcript_origin, "macwhisper")


class TestHostDispatch(unittest.TestCase):
    def test_fetch_py_routes_yandex_hosts(self) -> None:
        import fetch

        for host in yx.YANDEX_HOSTS:
            self.assertEqual(
                fetch._detect_source(f"https://{host}/player/episode/{EP}"), "yandex", host
            )

    def test_unknown_yandex_host_still_unsupported(self) -> None:
        import fetch

        with self.assertRaises(ValueError):
            fetch._detect_source("https://music.yandex.ru/album/1")

    def test_batch_filenames_use_the_episode_id(self) -> None:
        import fetch

        self.assertEqual(fetch._extract_any_id(URL), EP)


class TestFetchOneYandexDispatchKwargs(unittest.TestCase):
    """Lock the fetch.py branch itself.

    An adversarial review mutated this branch (`lang=lang` -> `lang="en"`,
    `asr_allow_cloud` deleted) and the whole 385-test suite still passed —
    nothing exercised it. These assertions are what make that mutation fail.
    """

    def _dispatch(self, **over):
        import fetch

        kw = dict(
            url=URL, out_path=Path("/tmp/o.txt"), lang="ru", prefer="manual",
            timeout_sec=90, with_description=True, description_only=False,
            asr_allow_cloud=True, asr_model="big", asr_timeout_sec=42,
            max_duration_min=7, remove_silence=False, debug=True,
            concurrent_fragments=4, media_timeout_sec=555,
            cookies_file=None, cookies_from_browser="chrome",
        )
        kw.update(over)
        with mock.patch.object(fetch, "fetch_yandex_transcript") as m, \
             mock.patch.object(fetch, "write_stat_sidecar"):
            m.return_value = mock.Mock(to_dict=lambda: {})
            fetch._fetch_one(**kw)
        return m.call_args

    def test_forwards_every_asr_and_media_kwarg(self) -> None:
        call = self._dispatch()
        kw = call.kwargs
        self.assertEqual(kw["lang"], "ru")
        self.assertEqual(kw["asr_allow_cloud"], True)
        self.assertEqual(kw["asr_model"], "big")
        self.assertEqual(kw["asr_timeout_sec"], 42)
        self.assertEqual(kw["max_duration_min"], 7)
        self.assertEqual(kw["remove_silence"], False)
        self.assertEqual(kw["concurrent_fragments"], 4)
        self.assertEqual(kw["media_timeout_sec"], 555)
        self.assertEqual(kw["with_description"], True)
        self.assertEqual(kw["debug"], True)

    def test_forwards_cookie_options(self) -> None:
        """supported_sources.md: every adapter MUST accept cookies_file."""
        kw = self._dispatch().kwargs
        self.assertIn("cookies_file", kw)
        self.assertEqual(kw["cookies_from_browser"], "chrome")


class TestFetchGuards(unittest.TestCase):
    def test_bad_url_raises_before_any_network(self) -> None:
        with mock.patch.object(yx, "_http_get") as m:
            with self.assertRaises(TranscriptFetchError):
                yx.fetch_yandex_transcript("https://example.com/nope", Path("/tmp/o.txt"))
        m.assert_not_called()

    def test_missing_ffmpeg_fails_before_the_download(self) -> None:
        with mock.patch.object(yx, "resolve_streams", return_value=_resolved()), \
             mock.patch.object(yx, "probe_duration_via_manifest", return_value=3800), \
             mock.patch.object(yx.ytm, "ffmpeg_available", return_value=False), \
             mock.patch.object(yx.ytm, "download_audio") as dl:
            with self.assertRaises(MissingDependencyError):
                yx.fetch_yandex_transcript(URL, Path("/tmp/o.txt"))
        dl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
