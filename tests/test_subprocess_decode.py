#!/usr/bin/env python3
"""Repo-wide guard for SUBPROCESS-TEXT-DECODE-LOCALE-CLASS.

``subprocess.run(cmd, text=True)`` does not name a codec. CPython takes one
from the locale, so the CHILD's bytes are decoded with the PARENT's locale
codec under a ``strict`` handler — and the child (node, soffice, tesseract,
git, pdftoppm, ffmpeg, yt-dlp) never agreed to that codec. Under
``LC_ALL=C`` a Cyrillic filename echoed back by soffice raises
``UnicodeDecodeError`` from inside ``subprocess.communicate``, i.e. a crash
in the middle of a read with a traceback out of stdlib.

The fix is one keyword: name the codec the child actually uses.

    subprocess.run(..., text=True, encoding="utf-8", errors="replace")

This file walks the repository and fails on any production call site that
went textual without naming a codec. It is stdlib-only and needs no venv or
system tools, so it runs in the pure-bash CI `harness` job.

Deliberate scope, two limits, both load-bearing:

* **Test files are exempt** (`tests/` directories, ``test_*.py``). There a
  decode error is the signal — the suite fails loudly and a human reads the
  traceback. In production the same error aborts a user's conversion with
  no output file. Different contract, so this gate covers only production.
  ``count_exempt_test_sites`` reports how many sites that exemption covers,
  so the carve-out stays visible instead of reading as full coverage.
* **``**kwargs`` splats are caught by the dict rule, not by call-graph
  analysis.** A kwargs dict that goes textual must name a codec in the same
  literal — see ``_procgroup.py``. A dict assembled across several
  statements would slip past; nothing in this repo does that.

See docs/issues/subprocess-text-decode-locale-class.md for the measurement
this gate locks in.
"""

import ast
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Vendored trees, build products, and the frozen upstream snapshot in
# archive/ are not ours to edit.
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", "archive", "tmp",
             "site-packages", ".pytest_cache"}

SUBPROCESS_CALLS = {"run", "Popen", "check_output", "call", "check_call"}

# The two keywords that put a child's pipes into text mode. Matched as
# whole keyword names, never as substrings: `remove_blank_text=True` is an
# lxml XMLParser argument and contains "text=True", which is exactly how it
# got into the first, grep-built version of this inventory as a phantom
# call site.
TEXT_MODE_KEYWORDS = ("text", "universal_newlines")


def _python_sources():
    """Every Python file in the repo, including extensionless CLIs."""
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.suffix == ".py":
            yield path
        elif path.suffix == "":
            try:
                with path.open("rb") as fh:
                    shebang = fh.read(64)
            except OSError:
                continue
            if shebang.startswith(b"#!") and b"python" in shebang:
                yield path


def _is_test_file(path):
    return "tests" in path.parts or path.name.startswith("test_")


def _goes_textual(keywords):
    """True if this keyword list turns the child's pipes into text mode."""
    for kw in keywords:
        if kw.arg in TEXT_MODE_KEYWORDS:
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _names_a_codec(keywords):
    return any(kw.arg == "encoding" for kw in keywords)


def _subprocess_aliases(tree):
    """`import subprocess as _subprocess` is used in xlsx_comment."""
    aliases = {"subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess" and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def _unpinned_sites(path):
    """Textual call sites in `path` that never named a codec."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (UnicodeDecodeError, OSError, SyntaxError):
        return []

    aliases = _subprocess_aliases(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        is_subprocess_call = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in aliases
            and func.attr in SUBPROCESS_CALLS
        )
        # A kwargs dict that goes textual must name the codec in the same
        # literal, whether it is `dict(...)` or `{...}`. This is what
        # reaches the splat sites without following the variable.
        is_kwargs_dict = (
            isinstance(func, ast.Name) and func.id == "dict"
        )

        if is_subprocess_call or is_kwargs_dict:
            if _goes_textual(node.keywords) and not _names_a_codec(node.keywords):
                found.append(node.lineno)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if not any(k in TEXT_MODE_KEYWORDS for k in keys):
            continue
        textual = any(
            isinstance(k, ast.Constant) and k.value in TEXT_MODE_KEYWORDS
            and isinstance(v, ast.Constant) and v.value is True
            for k, v in zip(node.keys, node.values)
        )
        if textual and "encoding" not in keys:
            found.append(node.lineno)

    return sorted(set(found))


def production_violations():
    """(path, line) for every unpinned textual site in production code."""
    out = []
    for path in _python_sources():
        if _is_test_file(path):
            continue
        for line in _unpinned_sites(path):
            out.append((str(path.relative_to(REPO)), line))
    return out


def count_exempt_test_sites():
    """How many sites the test-file exemption covers — reported, not hidden."""
    return sum(len(_unpinned_sites(p))
               for p in _python_sources() if _is_test_file(p))


class TestEveryTextualSubprocessNamesItsCodec(unittest.TestCase):

    def test_the_walker_finds_this_file_s_own_sources(self):
        """A walker that silently matched nothing would make the gate vacuous."""
        sources = list(_python_sources())
        self.assertGreater(len(sources), 100, "the source walk collapsed")
        self.assertIn(Path(__file__).resolve(), sources)
        # Extensionless CLIs must be reached: design-md ships `lint` and
        # `check-contrast` with no .py suffix, and both call subprocess.
        names = {p.name for p in sources}
        self.assertIn("lint", names, "extensionless CLIs are not being walked")

    def test_the_production_walk_reaches_the_files_it_must_gate(self):
        """The test-file exemption must not quietly swallow production too.

        Widen SKIP_DIRS or loosen `_is_test_file` and `production_violations`
        goes green by covering nothing. This pins the files it has to reach.
        """
        walked = {p for p in _python_sources() if not _is_test_file(p)}
        self.assertGreater(len(walked), 150, "the production walk collapsed")
        for must_reach in (
            "skills/docx/scripts/_soffice.py",
            "skills/docx/scripts/preview.py",
            "skills/pdf/scripts/md2pdf.py",
            "skills/pptx/scripts/pptx2md/ocr.py",
            "skills/transcript-fetcher/scripts/_procgroup.py",
            "skills/xlsx/scripts/xlsx_comment/cli_helpers.py",
            "skills/design-md/scripts/lint",
        ):
            self.assertIn(REPO / must_reach, walked,
                          f"{must_reach} is no longer gated")

    def test_the_walker_reads_keyword_names_not_substrings(self):
        """`remove_blank_text=True` is not a call site. It cost us one already."""
        tree = ast.parse(
            "import subprocess\n"
            "etree.XMLParser(remove_blank_text=True)\n"
            "subprocess.run(cmd, remove_blank_text=True)\n"
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self.assertFalse(
                    _goes_textual(node.keywords),
                    "matched a keyword whose NAME merely ends in 'text'",
                )

    def _sites_in(self, source):
        """Run the real detector over `source` written to a scratch file."""
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch.py"
            scratch.write_text(source, encoding="utf-8")
            return _unpinned_sites(scratch)

    def test_the_walker_flags_every_known_bad_shape(self):
        """Negative controls: the gate must be able to fail, in each shape."""
        for label, bad in (
            ("plain", "import subprocess\nsubprocess.run(cmd, text=True)\n"),
            ("legacy alias of text=",
             "import subprocess\nsubprocess.run(cmd, universal_newlines=True)\n"),
            ("module alias", "import subprocess as sp\nsp.run(cmd, text=True)\n"),
            ("Popen", "import subprocess\nsubprocess.Popen(a, text=True)\n"),
            ("check_output",
             "import subprocess\nsubprocess.check_output(a, text=True)\n"),
            ("dict() kwargs splat",
             "import subprocess\nkw = dict(text=True)\n"
             "subprocess.Popen(a, **kw)\n"),
            ("dict literal kwargs splat",
             "import subprocess\nkw = {'text': True}\n"
             "subprocess.Popen(a, **kw)\n"),
        ):
            with self.subTest(shape=label):
                self.assertTrue(self._sites_in(bad), f"{label} slipped past the gate")

    def test_the_walker_accepts_every_pinned_shape(self):
        """Positive controls: the fix must actually clear the gate."""
        for label, good in (
            ("plain", 'import subprocess\n'
                      'subprocess.run(c, text=True, encoding="utf-8", errors="replace")\n'),
            ("module alias", 'import subprocess as sp\n'
                             'sp.run(c, text=True, encoding="utf-8", errors="replace")\n'),
            ("dict() kwargs splat",
             'import subprocess\n'
             'kw = dict(text=True, encoding="utf-8", errors="replace")\n'
             'subprocess.Popen(a, **kw)\n'),
            ("bytes mode needs no codec",
             "import subprocess\nsubprocess.run(c, capture_output=True)\n"),
            ("not subprocess at all",
             "import subprocess\netree.XMLParser(remove_blank_text=True)\n"),
        ):
            with self.subTest(shape=label):
                self.assertEqual(self._sites_in(good), [],
                                 f"{label} was flagged, but it is correct")

    def test_no_production_site_decodes_with_the_locale_codec(self):
        violations = production_violations()
        if violations:
            listing = "\n".join(f"  {f}:{n}" for f, n in violations)
            self.fail(
                f"{len(violations)} production subprocess call site(s) go "
                f"textual without naming a codec, so they decode the child "
                f"with the parent's LOCALE codec:\n{listing}\n\n"
                f'Fix: add encoding="utf-8", errors="replace" to each call.\n'
                f"See docs/issues/subprocess-text-decode-locale-class.md"
            )


if __name__ == "__main__":
    print(f"exempt test-file sites (not gated): {count_exempt_test_sites()}",
          file=sys.stderr)
    unittest.main(verbosity=2)
