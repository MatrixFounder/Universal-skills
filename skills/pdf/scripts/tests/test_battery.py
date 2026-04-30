"""Battery regression tests for html2pdf.

Reads `battery_signatures.json` and exercises every fixture in three
locations:

  * Tier 0 — `tmp/<fixture>` (real .webarchive / .mhtml / .html, gitignored).
    Skipped per-fixture when the file is missing on disk; the test runs
    on developer machines where the fixtures are present and skips
    cleanly in CI checkouts where they aren't.
  * Tier 2 — `examples/regression/<fixture>` (committed synthetic
    micro-fixtures targeting deterministic edge cases).
  * Tier 3 — `tests/fixtures/platforms/<fixture>` (committed
    hand-stripped real-platform slices with verbatim sentinels).

Each entry in the JSON describes both `regular` and `reader` modes
(plus an optional `synthetic_fixture` / `platform_slice` flag for
where to look on disk; default is `tmp/`). Per-mode assertions:

  * `min_pages` ≤ pdf-page-count ≤ `max_pages`
  * `min_size_kb` ≤ pdf-file-kb ≤ `max_size_kb`
  * every `required_needles[i]` substring appears in pdftotext output
  * none of `forbidden_needles[i]` substrings appear in pdftotext output

A nullable `regular`/`reader` entry (set to `null` in the JSON) means
"this fixture isn't expected to render in that mode" — the test
SKIPS instead of failing. Used for synthetic fixtures targeting
reader-only behaviour.

Run:

    python3 -m unittest tests.test_battery -v
    # or via the e2e harness:
    bash tests/test_e2e.sh
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent
REPO_ROOT = SKILL_ROOT.parent.parent          # …/Universal-skills/

TMP_DIR = REPO_ROOT / "tmp"
SYNTHETIC_DIR = SKILL_ROOT / "examples" / "regression"
PLATFORM_DIR = HERE / "fixtures" / "platforms"
SIGNATURES_PATH = HERE / "battery_signatures.json"

# Hard render budget for any single battery render. Must be > the longest
# legitimate render time across `tmp/` (~30s on the largest webarchive)
# but small enough that a real hang fails fast.
BATTERY_TIMEOUT = 90


def _signatures() -> dict:
    if not SIGNATURES_PATH.exists():
        return {}
    return json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))


def _resolve_source(fixture_name: str, sig: dict) -> Path | None:
    """Resolve where the fixture lives on disk based on its sig's 'source' hint.

    Default location is `tmp/<fixture>`. Sig may declare `"source":
    "synthetic"` (→ examples/regression/) or `"source": "platform"`
    (→ tests/fixtures/platforms/). Returns None if not found.
    """
    src = sig.get("source", "tmp")
    if src == "synthetic":
        path = SYNTHETIC_DIR / fixture_name
    elif src == "platform":
        path = PLATFORM_DIR / fixture_name
    else:
        path = TMP_DIR / fixture_name
    return path if path.is_file() else None


def _run_html2pdf(src: Path, dst: Path, *, reader: bool) -> tuple[int, str]:
    """Run html2pdf.py; return (rc, stderr)."""
    cmd = [
        sys.executable, str(SCRIPTS / "html2pdf.py"),
        str(src), str(dst),
        "--timeout", str(BATTERY_TIMEOUT),
    ]
    if reader:
        cmd.append("--reader-mode")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=BATTERY_TIMEOUT + 30,
        )
        return proc.returncode, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "subprocess timed out"


def _pdf_pages(pdf: Path) -> int:
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30,
    ).stdout
    m = re.search(r"^Pages:\s*(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else 0


def _pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(pdf), "-"],
        capture_output=True, text=True, timeout=60,
    ).stdout


class _BatteryMixin:
    """Battery test logic as a mixin. NOT a TestCase subclass on its own —
    unittest's loader auto-runs every TestCase in the module, and we don't
    want a parameterless "base" test to appear in output. Concrete subclasses
    in `_make_test_class` inherit (`_BatteryMixin`, `unittest.TestCase`).
    """

    fixture_name: str = ""
    mode: str = ""
    sig: dict = {}
    source_path: Path | None = None

    def test_render_and_assert(self) -> None:
        if self.source_path is None:
            self.skipTest(
                f"fixture not on disk: {self.fixture_name} "
                f"(source: {self.sig.get('source', 'tmp')})"
            )
        if self.sig.get(self.mode) is None:
            self.skipTest(f"{self.fixture_name} has no {self.mode} baseline")

        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / f"out-{self.mode}.pdf"
            rc, stderr = _run_html2pdf(
                self.source_path, pdf, reader=(self.mode == "reader"),
            )
            self.assertEqual(
                rc, 0,
                f"html2pdf returned rc={rc} on {self.fixture_name} "
                f"({self.mode})\nstderr: {stderr[-500:]}",
            )
            self.assertTrue(pdf.exists(), "no PDF produced")
            self.assertGreater(pdf.stat().st_size, 1024, "PDF suspiciously small")

            entry = self.sig[self.mode]
            pages = _pdf_pages(pdf)
            size_kb = pdf.stat().st_size // 1024
            # Collapse whitespace runs (incl. line breaks) to single spaces
            # before needle search. pdftotext wraps long lines according to
            # the PDF's typeset width; a needle phrase like "продуктовую
            # разработку" can land on either side of a line break depending
            # on font metrics. Normalising lets sentinels work regardless
            # of typesetting decisions. Same normalisation runs on both
            # sides of the search.
            text = re.sub(r"\s+", " ", _pdf_text(pdf))

            self.assertGreaterEqual(
                pages, entry["min_pages"],
                f"page count {pages} below min {entry['min_pages']} "
                f"({self.fixture_name} {self.mode})",
            )
            self.assertLessEqual(
                pages, entry["max_pages"],
                f"page count {pages} above max {entry['max_pages']} "
                f"({self.fixture_name} {self.mode})",
            )
            self.assertGreaterEqual(
                size_kb, entry["min_size_kb"],
                f"size {size_kb}kB below min {entry['min_size_kb']} "
                f"({self.fixture_name} {self.mode})",
            )
            self.assertLessEqual(
                size_kb, entry["max_size_kb"],
                f"size {size_kb}kB above max {entry['max_size_kb']} "
                f"({self.fixture_name} {self.mode})",
            )
            for needle in entry.get("required_needles", []):
                self.assertIn(
                    needle, text,
                    f"required needle {needle!r} missing from "
                    f"{self.fixture_name} ({self.mode})",
                )
            for needle in entry.get("forbidden_needles", []):
                self.assertNotIn(
                    needle, text,
                    f"forbidden needle {needle!r} leaked into "
                    f"{self.fixture_name} ({self.mode}) — chrome bypass",
                )


def _make_test_class(name: str, fixture: str, mode: str, sig: dict) -> type:
    """Build a TestCase class dynamically so each fixture/mode is its own
    discoverable test name in unittest output."""
    return type(name, (_BatteryMixin, unittest.TestCase), {
        "fixture_name": fixture,
        "mode": mode,
        "sig": sig,
        "source_path": _resolve_source(fixture, sig),
    })


def _slugify(name: str) -> str:
    """Make fixture name safe for use as a Python class name suffix."""
    s = re.sub(r"[^\w]", "_", name)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "anon"


# Generate one TestCase class per fixture × mode at module import.
_signatures_data = _signatures()
_globals = globals()
if not _signatures_data:
    class TestBatteryEmpty(unittest.TestCase):
        def test_no_signatures_file(self) -> None:
            self.skipTest(
                f"no signatures file at {SIGNATURES_PATH}; "
                "run tests/capture_signatures.py first"
            )
    _globals["TestBatteryEmpty"] = TestBatteryEmpty
else:
    for _fixture_name, _sig in _signatures_data.items():
        _slug = _slugify(_fixture_name)
        for _mode in ("regular", "reader"):
            _cls_name = f"TestBattery_{_slug}_{_mode}"
            _globals[_cls_name] = _make_test_class(
                _cls_name, _fixture_name, _mode, _sig,
            )


if __name__ == "__main__":
    if shutil.which("pdfinfo") is None or shutil.which("pdftotext") is None:
        print("WARNING: pdfinfo / pdftotext (Poppler) not in PATH; tests will fail.",
              file=sys.stderr)
    unittest.main(verbosity=2)
