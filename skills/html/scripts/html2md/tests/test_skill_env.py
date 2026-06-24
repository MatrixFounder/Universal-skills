"""Skill-local `.env` auto-load (encapsulation) — `cli._load_skill_env`.

The skill's config travels WITH the skill: any caller of the CLI (or the
`~/.claude/skills/html` symlink) picks it up with zero awareness, without polluting the
machine-global environment. Process env wins; opt out via HTML_NO_DOTENV=1; secrets-safe
(0600 + symlink rejected). Loaded ONLY from the shim entry point — importing the package
(these tests) never triggers it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import cli  # noqa: E402


class TestLoadSkillEnv(unittest.TestCase):
    @staticmethod
    def _env(d, body, mode=0o600):
        p = Path(d) / ".env"
        p.write_text(body, encoding="utf-8")
        os.chmod(p, mode)
        return p

    def test_loads_keys_into_environ(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "# comment\nHTML_CHROME_SCROLL=1\nexport HTML_X=\"yes\"\n\n")
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": ""}, clear=False):
                os.environ.pop("HTML_CHROME_SCROLL", None)
                os.environ.pop("HTML_X", None)
                cli._load_skill_env(p)
                self.assertEqual(os.environ.get("HTML_CHROME_SCROLL"), "1")
                self.assertEqual(os.environ.get("HTML_X"), "yes")  # quotes + `export ` stripped

    def test_process_env_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "HTML_CHROME_SCROLL=1\n")
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": "", "HTML_CHROME_SCROLL": "0"}):
                cli._load_skill_env(p)
                self.assertEqual(os.environ["HTML_CHROME_SCROLL"], "0")  # caller's value kept

    def test_opt_out(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "HTML_FOO=bar\n")
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "1"}, clear=False):
                os.environ.pop("HTML_FOO", None)
                cli._load_skill_env(p)
                self.assertIsNone(os.environ.get("HTML_FOO"))

    def test_skips_group_world_accessible(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "HTML_FOO=bar\n", mode=0o644)
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": ""}, clear=False):
                os.environ.pop("HTML_FOO", None)
                cli._load_skill_env(p)  # warns to stderr + skips
                self.assertIsNone(os.environ.get("HTML_FOO"))

    def test_symlink_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            real = self._env(d, "HTML_FOO=bar\n")
            link = Path(d) / "link.env"
            link.symlink_to(real)
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": ""}, clear=False):
                os.environ.pop("HTML_FOO", None)
                cli._load_skill_env(link)
                self.assertIsNone(os.environ.get("HTML_FOO"))

    def test_missing_file_is_noop(self):
        with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": ""}, clear=False):
            cli._load_skill_env(Path("/nonexistent/dir/.env"))  # must not raise

    def test_inline_comment_and_quotes_stripped(self):
        """Shell-style RHS: inline `# comment` dropped, quotes honored, `#` inside a value kept."""
        self.assertEqual(cli._dotenv_value("jina_abc123   # raises the quota"), "jina_abc123")
        self.assertEqual(cli._dotenv_value('"yes"  # note'), "yes")
        self.assertEqual(cli._dotenv_value("~/.html/auth-map.json"), "~/.html/auth-map.json")
        self.assertEqual(cli._dotenv_value("ab#cd"), "ab#cd")  # no space before # → part of value

    def test_inline_comment_not_swallowed_into_value(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "JINA_API_KEY=jina_secret123   # raises the quota\n")
            with mock.patch.dict(os.environ, {"HTML_NO_DOTENV": "", "HTML_NO_DOTENV": ""}, clear=False):
                os.environ.pop("JINA_API_KEY", None)
                cli._load_skill_env(p)
                self.assertEqual(os.environ.get("JINA_API_KEY"), "jina_secret123")

if __name__ == "__main__":
    unittest.main()
