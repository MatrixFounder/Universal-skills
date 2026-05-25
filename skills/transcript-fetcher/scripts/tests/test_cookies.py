"""Tests for ``sources._cookies`` — symlink/mode hardening + redirect handler.

These cover the SEC-H4 (cookie file permissions, symlink-follow) and
SEC-C3 (restricted redirect handler) regressions added in v1.1.1.
"""
from __future__ import annotations

import io
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

from sources._cookies import (  # noqa: E402
    CookieFileError,
    _RestrictedRedirectHandler,
    build_authenticated_opener,
    load_cookie_jar,
)


_NETSCAPE_HEADER = (
    "# Netscape HTTP Cookie File\n"
    "# Synthetic — for tests only.\n"
)
_SAMPLE_COOKIES = (
    _NETSCAPE_HEADER
    + ".skool.com\tTRUE\t/\tTRUE\t1999999999\tsession\tfake-token\n"
)


def _write_cookies(td: Path, *, mode: int = 0o600) -> Path:
    p = td / "cookies.txt"
    p.write_text(_SAMPLE_COOKIES, encoding="utf-8")
    p.chmod(mode)
    return p


# --------------------------------------------------------------------- #
# load_cookie_jar
# --------------------------------------------------------------------- #


class TestCookieFileHardening(unittest.TestCase):
    def test_loads_secure_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _write_cookies(Path(td), mode=0o600)
            jar = load_cookie_jar(p)
            self.assertTrue(any(c.name == "session" for c in jar))

    def test_rejects_world_readable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _write_cookies(Path(td), mode=0o644)
            with self.assertRaises(CookieFileError) as ctx:
                load_cookie_jar(p)
            self.assertIn("world-readable", str(ctx.exception))

    def test_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            real = _write_cookies(Path(td), mode=0o600)
            link = Path(td) / "link.txt"
            os.symlink(real, link)
            with self.assertRaises(CookieFileError) as ctx:
                load_cookie_jar(link)
            self.assertIn("symlink", str(ctx.exception))

    def test_missing_file_clean_message(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(CookieFileError) as ctx:
                load_cookie_jar(Path(td) / "absent.txt")
            msg = str(ctx.exception)
            self.assertIn("not found", msg)
            # Must NOT echo a full absolute path or directory contents.
            self.assertNotIn(td, msg)

    def test_parse_error_does_not_leak_file_contents(self) -> None:
        # Hand the loader an unparseable file. The error message must
        # name the file by basename only and must NOT include the
        # underlying loader's line snippet (which is the file's first
        # malformed line).
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bogus.txt"
            p.write_text("THIS IS NOT NETSCAPE\nsecret_token_xyz\n",
                         encoding="utf-8")
            p.chmod(0o600)
            with self.assertRaises(CookieFileError) as ctx:
                load_cookie_jar(p)
            self.assertNotIn("secret_token_xyz", str(ctx.exception))


# --------------------------------------------------------------------- #
# Restricted redirect handler
# --------------------------------------------------------------------- #


class TestRestrictedRedirectHandler(unittest.TestCase):
    def _fake_redirect(self, newurl: str, allowed: tuple = ("skool.com",)):
        handler = _RestrictedRedirectHandler(allowed)
        req = mock.Mock()
        req.full_url = "https://www.skool.com/x"
        from urllib.request import Request
        return handler.redirect_request(
            Request("https://www.skool.com/x"),
            io.BytesIO(b""), 302, "Found", {}, newurl,
        )

    def test_off_allowlist_host_blocked(self) -> None:
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as ctx:
            self._fake_redirect("https://evil.example.com/y")
        self.assertIn("off-allowlist", str(ctx.exception))

    def test_file_scheme_blocked(self) -> None:
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as ctx:
            self._fake_redirect("file:///etc/passwd")
        self.assertIn("non-http", str(ctx.exception))

    def test_allowed_host_passes(self) -> None:
        # Should not raise — returns a new Request object.
        out = self._fake_redirect(
            "https://www.skool.com/redirected",
            allowed=("www.skool.com",),
        )
        # urllib's redirect_request returns Request|None — None means
        # "stop", which we don't want either.
        self.assertIsNotNone(out)


class TestOpenerHandlerSet(unittest.TestCase):
    """The opener must NOT have FileHandler or FTPHandler registered."""

    def test_no_file_or_ftp_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _write_cookies(Path(td), mode=0o600)
            opener = build_authenticated_opener(
                p, allowed_hosts=("www.skool.com",),
            )
        handler_classes = {type(h).__name__ for h in opener.handlers}
        self.assertNotIn("FileHandler", handler_classes)
        self.assertNotIn("FTPHandler", handler_classes)


if __name__ == "__main__":
    unittest.main()
