"""TASK 023 bead 023-02 — vendor-agnostic RemoteReader provider construction.

Run from ``skills/html/scripts``:  python -m unittest discover -s html2md/tests
Offline / stdlib-only (env-driven; no network).
"""
from __future__ import annotations

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire  # noqa: E402
from html2md.cli import build_parser  # noqa: E402
from html2md.exceptions import FetchFailed  # noqa: E402

_ENV_KEYS = ("HTML_READER_URL", "HTML_READER_PROVIDERS", "HTML_READER_TOKEN",
             "JINA_API_KEY", "HTML_SEARCH_URL", "HTML_SEARCH_PROVIDERS")


def _opts(**over):
    args = build_parser().parse_args(["https://x.com"])
    for k, v in over.items():
        setattr(args, k, v)
    return args


class _EnvIsolated(unittest.TestCase):
    """Snapshot + clear the provider env so tests don't contaminate each other."""

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestProviderOrder(_EnvIsolated):
    def test_provider_order_default(self):
        """TC-02-01: no env, engine auto → [jina] only."""
        provs = acquire._remote_providers(_opts(engine="auto"))
        self.assertEqual([p.name for p in provs], ["jina"])
        self.assertEqual(provs[0].base, acquire._JINA_READER_PREFIX)

    def test_provider_order_single_url(self):
        """TC-02-02a: HTML_READER_URL + auto → [remote:<host>, jina]."""
        os.environ["HTML_READER_URL"] = "https://r.internal/"
        provs = acquire._remote_providers(_opts(engine="auto"))
        self.assertEqual([p.name for p in provs], ["remote:r.internal", "jina"])

    def test_provider_order_explicit_list_no_jina(self):
        """TC-02-02b: explicit PROVIDERS list → exact order, jina NOT appended."""
        os.environ["HTML_READER_PROVIDERS"] = "https://a/ https://b/"
        provs = acquire._remote_providers(_opts(engine="auto"))
        self.assertEqual([p.name for p in provs], ["remote:a", "remote:b"])

    def test_engine_remote_configured_only(self):
        """TC-02-02c: engine remote → configured providers ONLY (never a jina fall-back)."""
        os.environ["HTML_READER_URL"] = "https://r.internal/"
        provs = acquire._remote_providers(_opts(engine="remote"))
        self.assertEqual([p.name for p in provs], ["remote:r.internal"])

    def test_engine_jina_only(self):
        """engine jina → the built-in jina provider only, even with env set."""
        os.environ["HTML_READER_URL"] = "https://r.internal/"
        provs = acquire._remote_providers(_opts(engine="jina"))
        self.assertEqual([p.name for p in provs], ["jina"])


class TestBuildReaderRequest(_EnvIsolated):
    def test_build_reader_request_jina(self):
        """TC-02-03: jina URL = base + target; X-Return-Format html; key → Authorization."""
        jina = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, None)
        url, headers = acquire._build_reader_request(jina, "https://x.com/p", _opts())
        self.assertEqual(url, "https://r.jina.ai/https://x.com/p")
        self.assertEqual(headers["X-Return-Format"], "html")
        self.assertNotIn("Authorization", headers)
        keyed = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, "SEKRET")
        _, h2 = acquire._build_reader_request(keyed, "https://x.com/p", _opts())
        self.assertEqual(h2["Authorization"], "Bearer SEKRET")

    def test_build_reader_request_remote_format_markdown(self):
        """X-Return-Format follows --remote-format."""
        jina = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, None)
        _, headers = acquire._build_reader_request(
            jina, "https://x.com/p", _opts(remote_format="markdown"))
        self.assertEqual(headers["X-Return-Format"], "markdown")

    def test_build_reader_request_generic_token(self):
        """TC-02-04: a generic configured provider carries HTML_READER_TOKEN."""
        os.environ["HTML_READER_TOKEN"] = "TKN"
        prov = acquire._reader_from_base("https://r.internal/")
        url, headers = acquire._build_reader_request(prov, "https://x.com", _opts())
        self.assertEqual(url, "https://r.internal/https://x.com")
        self.assertEqual(headers["Authorization"], "Bearer TKN")

    def test_target_space_is_encoded(self):
        """A space in the target is percent-encoded (no request-splitting via spaces)."""
        jina = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, None)
        url, _ = acquire._build_reader_request(jina, "https://x.com/a b", _opts())
        self.assertIn("%20", url)
        self.assertNotIn(" ", url)

    def test_query_param_base_fully_encodes_target(self):
        """S-3: a `?url=`-style reader base encodes the target as one query value so its
        &/=/? cannot inject into the reader's own query."""
        prov = acquire._RemoteReader("remote:r", "https://r/api?url=", None)
        url, _ = acquire._build_reader_request(prov, "https://x.com/?a=1&b=2", _opts())
        self.assertTrue(url.startswith("https://r/api?url="))
        self.assertNotIn("?a=1&b=2", url)   # target query NOT literal
        self.assertIn("%26", url)            # the '&' is encoded
        self.assertIn("%3F", url)            # the '?' is encoded

    def test_target_selector_crlf_refused(self):
        """L-3: a CR/LF in --target-selector is refused (header-injection guard)."""
        jina = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, None)
        with self.assertRaises(FetchFailed) as cm:
            acquire._build_reader_request(jina, "https://x.com",
                                          _opts(target_selector="a\r\nX-Evil: y"))
        self.assertEqual(cm.exception.details["kind"], "refused")


if __name__ == "__main__":
    unittest.main()
