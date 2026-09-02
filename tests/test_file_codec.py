#!/usr/bin/env python3
"""Repo-wide guard for FILE-TEXT-CODEC-LOCALE-CLASS.

``Path.read_text()``, ``Path.write_text()`` and ``open(path, "r"/"w")`` name no
codec, so CPython takes one from the locale. Every file this repository reads
and writes is UTF-8 — SKILL.md, the eval JSON, the generated HTML reports — but
under ``LC_ALL=C`` the codec is ASCII, and the first em dash raises
``UnicodeDecodeError`` from inside ``read_text``.

Measured 2026-09-02: ``package_skill.py`` line 35 read ``SKILL.md`` unpinned.
Adding an em dash to ``skills/text-humanizer/SKILL.md`` — ordinary prose, in a
Red Flags section — turned a passing command into a traceback under an ASCII
locale, and took two of ``skill-creator``'s own tests with it. The file did not
change encoding; it only stopped being accidentally ASCII.

The fix is one keyword: name the codec the file actually is.

    path.read_text(encoding="utf-8")
    open(path, "w", encoding="utf-8")

This is the fourth member of the same family, and the third guard:

* HUMAN-CLI-OUTPUT-LOCALE-CLASS  — what a process writes to its own stdout.
* PDF-CLI-STDOUT-JSON-LOCALE-CLASS — the machine channel on that same stdout.
* SUBPROCESS-TEXT-DECODE-LOCALE-CLASS — what a process reads from its children
  (``tests/test_subprocess_decode.py``).
* this one — what a process reads from and writes to FILES.

Deliberate scope, three limits, all load-bearing:

* **Test files are exempt** (``tests/`` directories, ``test_*.py``), matching
  ``test_subprocess_decode.py``: there a decode error is the signal and a human
  reads the traceback, while in production it aborts a user's run with no
  output. ``count_exempt_test_sites`` reports the size of that carve-out so it
  stays visible instead of reading as full coverage.
* **Binary modes are not in scope.** ``open(p, "rb")`` has no codec to name.
* **Only the stdlib spellings are matched** — ``pathlib``'s two methods and the
  builtin ``open``. A project helper that happens to be called ``read_text``
  is NOT a call site: ``wiki-ingest``'s ``_safety.read_text(path)`` takes no
  ``encoding=`` at all, and "fixing" it raises ``TypeError``. The walker
  therefore skips a call whose receiver is a bare module-style name; that
  exemption is asserted below so it cannot silently widen.
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
             "site-packages", ".pytest_cache", ".agentic-development"}

PATHLIB_TEXT_METHODS = {"read_text", "write_text"}

# Receivers that are a project module rather than a Path. `_safety.read_text`
# is wiki-ingest's symlink-refusing, size-capping reader; it has its own
# signature and no `encoding` parameter.
HELPER_MODULES = {"_safety"}


def _python_sources():
    """Every Python file in the repo, including extensionless CLIs."""
    for path in sorted(REPO.rglob("*")):
        # `relative_to(REPO)`, not `path.parts`: the absolute prefix is not
        # ours to filter on. A checkout under ~/tmp/ or /private/tmp/ made every
        # part-wise match hit on "tmp" and skipped the whole repository, leaving
        # the gate vacuous. Measured: 0 files walked from
        # /private/tmp/.../Universal-skills.
        if not path.is_file():
            continue
        if any(p in SKIP_DIRS for p in path.relative_to(REPO).parts):
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
    # `relative_to(REPO)` for the same reason `_python_sources` uses it: matched
    # against absolute parts, a checkout under any directory named `tests`
    # classifies the whole repository as test code and the gate passes on
    # everything.
    return ("tests" in path.relative_to(REPO).parts
            or path.name.startswith("test_"))


def _names_a_codec(node):
    return any(kw.arg == "encoding" for kw in node.keywords)


def _open_mode(node):
    """The mode string of an `open()` call, defaulting to 'r'."""
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return "r"


def _is_helper_receiver(node):
    """True when `x.read_text(...)` calls a project helper, not a Path."""
    receiver = node.func.value
    return isinstance(receiver, ast.Name) and receiver.id in HELPER_MODULES


def _unpinned_sites(path):
    """Textual file-I/O sites in `path` that never named a codec."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (UnicodeDecodeError, OSError, SyntaxError):
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in PATHLIB_TEXT_METHODS:
            if _is_helper_receiver(node) or _names_a_codec(node):
                continue
            found.append((node.lineno, f"{func.attr}()"))
        elif isinstance(func, ast.Name) and func.id == "open":
            if "b" in _open_mode(node) or _names_a_codec(node):
                continue
            found.append((node.lineno, "open()"))
    return found


def count_exempt_test_sites():
    """How many sites the test-file carve-out covers. Keeps it visible."""
    return sum(len(_unpinned_sites(p))
               for p in _python_sources() if _is_test_file(p))


class TestEveryTextualFileCallNamesItsCodec(unittest.TestCase):
    def test_no_production_site_reads_or_writes_text_unpinned(self):
        offenders = []
        for path in _python_sources():
            if _is_test_file(path):
                continue
            for lineno, kind in _unpinned_sites(path):
                offenders.append(f"{path.relative_to(REPO)}:{lineno} {kind}")
        self.assertEqual(
            offenders, [],
            "these read or write text with the locale's codec instead of the "
            "file's; add encoding=\"utf-8\":\n  " + "\n  ".join(offenders))

    def test_the_walker_finds_this_file_s_own_sources(self):
        """A walker that silently matched nothing would make the gate vacuous."""
        names = {p.name for p in _python_sources()}
        self.assertIn("analyze_gaps.py", names)
        self.assertIn("package_skill.py", names)
        self.assertGreater(len(names), 50)

    def test_the_walker_is_not_fooled_by_the_path_above_the_repo(self):
        """A checkout under ~/tmp/ must not skip the whole repository.

        SKIP_DIRS is matched against parts RELATIVE to the repo. Matched against
        the absolute parts, a repo living under any directory named `tmp`,
        `archive`, `node_modules`, `.git` ... walks ZERO files and the gate
        passes on everything. Measured before the fix: 0 sources found from
        /private/tmp/.../Universal-skills, in both this guard and
        test_subprocess_decode.py.

        The fixture puts a repo under a directory named `tmp` and one named
        `archive`, and asserts the walker still sees inside it.
        """
        global REPO
        self.assertIn("tmp", SKIP_DIRS, "this test guards the tmp entry")
        original = REPO
        try:
            for outer in ("tmp", "archive", "node_modules"):
                with self.subTest(outer_dir=outer), tempfile.TemporaryDirectory() as td:
                    fake = Path(td) / outer / "checkout"
                    (fake / "skills" / "s" / "scripts").mkdir(parents=True)
                    (fake / "skills" / "s" / "scripts" / "run.py").write_text(
                        "from pathlib import Path\nPath('a').read_text()\n",
                        encoding="utf-8")
                    (fake / ".venv").mkdir()
                    (fake / ".venv" / "vendored.py").write_text(
                        "open('a')\n", encoding="utf-8")
                    REPO = fake
                    found = {p.name for p in _python_sources()}
                    self.assertIn("run.py", found,
                                  f"a repo under {outer}/ walked zero files")
                    self.assertNotIn("vendored.py", found,
                                     "SKIP_DIRS stopped applying inside the repo")
        finally:
            REPO = original

    def test_the_walker_flags_every_known_bad_shape(self):
        """Negative controls: the gate must be able to fail, in each shape."""
        bad = [
            "from pathlib import Path\nPath('a').read_text()\n",
            "from pathlib import Path\nPath('a').write_text('x')\n",
            "open('a')\n",
            "open('a', 'w')\n",
            "open('a', mode='w')\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for i, src in enumerate(bad):
                p = Path(tmp) / f"bad_{i}.py"
                p.write_text(src, encoding="utf-8")
                self.assertTrue(_unpinned_sites(p), f"missed: {src!r}")

    def test_the_fix_and_the_exemptions_clear_the_gate(self):
        """Positive controls: pinned, binary and helper calls are not sites."""
        good = [
            "from pathlib import Path\nPath('a').read_text(encoding='utf-8')\n",
            "from pathlib import Path\nPath('a').write_text('x', encoding='utf-8')\n",
            "open('a', 'rb')\n",
            "open('a', 'wb')\n",
            "open('a', mode='rb')\n",
            "open('a', encoding='utf-8')\n",
            "import _safety\n_safety.read_text(p)\n",
            "import _safety\n_safety.write_text(p, t, dry_run=False)\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for i, src in enumerate(good):
                p = Path(tmp) / f"good_{i}.py"
                p.write_text(src, encoding="utf-8")
                self.assertEqual(_unpinned_sites(p), [], f"false positive: {src!r}")

    def test_the_helper_exemption_covers_exactly_what_it_claims(self):
        """`_safety` is exempt because its signature has no `encoding`."""
        safety = REPO / "skills/wiki-ingest/scripts/wiki_ingest/_safety.py"
        if not safety.is_file():
            self.skipTest("wiki-ingest is not in this checkout")
        tree = ast.parse(safety.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in PATHLIB_TEXT_METHODS:
                names = {a.arg for a in node.args.args} | {
                    a.arg for a in node.args.kwonlyargs}
                self.assertNotIn(
                    "encoding", names,
                    f"_safety.{node.name} now takes encoding=; drop it from "
                    "HELPER_MODULES so the gate covers it")

    def test_the_test_carve_out_is_reported_not_hidden(self):
        exempt = count_exempt_test_sites()
        self.assertIsInstance(exempt, int)
        print(f"\n  test-file sites exempt from this gate: {exempt}", file=sys.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
