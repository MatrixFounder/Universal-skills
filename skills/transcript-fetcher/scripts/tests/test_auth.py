"""Tests for `~/.transcript-fetcher` per-host cookie resolution (`sources/_auth`).

Locks the resolution order, the label-boundary host match (typosquat rejection),
and the bearer-credential hardening (symlink-reject / 0600).
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

from sources import _auth  # noqa: E402


def _cookies(d, name="x.txt", mode=0o600) -> Path:
    p = Path(d) / name
    p.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    os.chmod(p, mode)
    return p


def _map(d, mapping, mode=0o600) -> Path:
    p = Path(d) / "auth-map.json"
    p.write_text(json.dumps(mapping), encoding="utf-8")
    os.chmod(p, mode)
    return p


class TestResolution(unittest.TestCase):
    def test_explicit_wins(self) -> None:
        self.assertEqual(
            _auth.resolve_cookies_file("https://x.com/i/broadcasts/z",
                                       explicit_cookies_file=Path("/tmp/explicit.txt")),
            Path("/tmp/explicit.txt"),
        )

    def test_no_map_no_convention_returns_none(self) -> None:
        # Point the default dir at an empty temp dir so a real ~/.transcript-fetcher
        # on the dev box can't leak into the test.
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                self.assertIsNone(
                    _auth.resolve_cookies_file("https://x.com/i/broadcasts/z"))

    def test_auth_map_hit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            amap = _auth.load_auth_map(_map(d, {"x.com": {"cookies_file": str(ck)}}))
            r = _auth.resolve_cookies_file("https://x.com/i/broadcasts/z", auth_map=amap)
            self.assertEqual(r, ck)

    def test_auth_map_label_boundary_rejects_typosquat(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            amap = _auth.load_auth_map(_map(d, {"x.com": {"cookies_file": str(ck)}}))
            for host in ("https://x.com.evil.com/z", "https://evilx.com/z",
                         "https://notx.com/z"):
                self.assertIsNone(
                    _auth.resolve_cookies_file(host, auth_map=amap), host)

    def test_subdomain_matches(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            amap = _auth.load_auth_map(_map(d, {"x.com": {"cookies_file": str(ck)}}))
            self.assertEqual(
                _auth.resolve_cookies_file("https://mobile.x.com/z", auth_map=amap),
                ck,
            )

    def test_load_configured_returns_none_when_unset(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                self.assertIsNone(_auth.load_configured_auth_map())

    def test_convention_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="x.com-cookies.txt")
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                r = _auth.resolve_cookies_file("https://x.com/i/broadcasts/z")
                self.assertEqual(r.name, "x.com-cookies.txt")


class TestConventionMirrorPrefixFallback(unittest.TestCase):
    """FIX-1 (cycle 3): the auth-hint printed by x.py's exit-5 message names the
    STRIPPED-host convention file for a www./mobile./m. URL — the resolver must
    actually find that file for the round-trip to work (closes the F10
    residual: 4 of 6 documented X hosts were a dead end)."""

    def test_www_x_com_resolves_x_com_cookies_via_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="x.com-cookies.txt")
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                r = _auth.resolve_cookies_file("https://www.x.com/jack/status/1")
                self.assertIsNotNone(r)
                self.assertEqual(r.name, "x.com-cookies.txt")

    def test_mobile_twitter_com_resolves_twitter_com_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="twitter.com-cookies.txt")
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                r = _auth.resolve_cookies_file(
                    "https://mobile.twitter.com/jack/status/1"
                )
                self.assertIsNotNone(r)
                self.assertEqual(r.name, "twitter.com-cookies.txt")

    def test_exact_host_file_wins_over_stripped_when_both_exist(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="www.x.com-cookies.txt")
            _cookies(d, name="x.com-cookies.txt")
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                r = _auth.resolve_cookies_file("https://www.x.com/jack/status/1")
                self.assertEqual(r.name, "www.x.com-cookies.txt")

    def test_lookalike_prefix_without_dot_boundary_not_stripped(self) -> None:
        # "wwwx.com" — the first label is "wwwx", NOT "www" + a dot boundary —
        # must never fall back to "x.com-cookies.txt".
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="x.com-cookies.txt")
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                r = _auth.resolve_cookies_file("https://wwwx.com/z")
                self.assertIsNone(r)

    def test_fallback_file_still_rejected_when_insecure(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _cookies(d, name="x.com-cookies.txt", mode=0o644)
            with mock.patch.object(_auth, "DEFAULT_AUTH_DIR", Path(d)), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(_auth._ENV_AUTH_MAP, None)
                with self.assertRaises(_auth.AuthMapError):
                    _auth.resolve_cookies_file("https://www.x.com/z")


class TestHardening(unittest.TestCase):
    def test_auth_map_must_be_0600(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            amap = _map(d, {"x.com": {"cookies_file": str(ck)}}, mode=0o644)
            with self.assertRaises(_auth.AuthMapError):
                _auth.load_auth_map(amap)

    def test_cookies_file_must_be_0600(self) -> None:
        # map is 0600 (loads fine) but the cookies file it points to is world-
        # readable → hardened at resolve time.
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d, mode=0o644)
            amap = _auth.load_auth_map(_map(d, {"x.com": {"cookies_file": str(ck)}}))
            with self.assertRaises(_auth.AuthMapError):
                _auth.resolve_cookies_file("https://x.com/z", auth_map=amap)

    def test_symlink_map_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            real = _map(d, {"x.com": {"cookies_file": str(ck)}})
            link = Path(d) / "link-map.json"
            os.symlink(real, link)
            with self.assertRaises(_auth.AuthMapError):
                _auth.load_auth_map(link)

    def test_malformed_map_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            amap = _map(d, {"x.com": {"storage_state": "/x"}})  # no cookies_file
            with self.assertRaises(_auth.AuthMapError):
                _auth.load_auth_map(amap)

    def test_bare_tld_key_rejected(self) -> None:
        # A dotless key ("com") would match every *.com → cross-tenant leak.
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            for badkey in ("com", "localhost"):
                amap = _map(d, {badkey: {"cookies_file": str(ck)}})
                with self.assertRaises(_auth.AuthMapError):
                    _auth.load_auth_map(amap)

    def test_non_string_cookies_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            amap = _map(d, {"x.com": {"cookies_file": ["a", "b"]}})
            with self.assertRaises(_auth.AuthMapError):
                _auth.load_auth_map(amap)

    def test_duplicate_host_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ck = _cookies(d)
            amap = Path(d) / "auth-map.json"
            amap.write_text(
                '{"x.com": {"cookies_file": "%s"}, "X.COM": {"cookies_file": "%s"}}'
                % (ck, ck), encoding="utf-8")
            os.chmod(amap, 0o600)
            with self.assertRaises(_auth.AuthMapError):
                _auth.load_auth_map(amap)


if __name__ == "__main__":
    unittest.main()
