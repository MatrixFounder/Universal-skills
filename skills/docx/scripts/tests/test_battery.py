"""Battery regression tests for html2docx.

Mirrors `skills/pdf/scripts/tests/test_battery.py` (q-6) for the
docx skill. Reads `battery_signatures.json` and exercises every
fixture in three locations:

  * Tier 0 — `tests/tmp/<fixture>` (real .webarchive / .mhtml / .html,
    gitignored). Skipped per-fixture when the file is missing on disk.
  * Tier 2 — `examples/regression/<fixture>` (committed synthetic
    micro-fixtures targeting deterministic edge cases).
  * Tier 3 — `tests/fixtures/platforms/<fixture>` (committed
    hand-stripped real-platform slices with verbatim sentinels).

Per-mode assertions:

  * `min_paragraphs` ≤ docx-paragraph-count ≤ `max_paragraphs`
  * `min_size_kb` ≤ docx-file-kb ≤ `max_size_kb`
  * every `required_needles[i]` substring appears in the body text
  * none of `forbidden_needles[i]` substrings appear in the body text

A nullable `regular`/`reader` entry (set to `null` in the JSON) means
"this fixture isn't expected to render in that mode" — the test
SKIPS instead of failing.

Text extraction uses stdlib `zipfile` + `lxml.etree` to read
`word/document.xml` directly (no python-docx required, though it's
installed). Paragraph count = number of `<w:p>` elements; text = all
`<w:t>` content joined with spaces, then whitespace-normalised.

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
import zipfile
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent
REPO_ROOT = SKILL_ROOT.parent.parent          # …/Universal-skills/

# tmp/ lives inside `tests/` (rather than at REPO_ROOT) because the docx
# skill must be runnable in isolation as a packaged `.skill` archive —
# fixtures next to the test runner travel with the bundle, fixtures at
# REPO_ROOT do not. The pdf skill chose REPO_ROOT/tmp/ historically; both
# layouts are valid, just don't share fixtures across skills.
TMP_DIR = HERE / "tmp"
SYNTHETIC_DIR = SKILL_ROOT / "examples" / "regression"
PLATFORM_DIR = HERE / "fixtures" / "platforms"
SIGNATURES_PATH = HERE / "battery_signatures.json"

# Hard render budget for any single battery render. html2docx tends to be
# slower than html2pdf on the same fixture (DOM walker + docx-js Packer),
# so we give 120s instead of pdf's 90s.
BATTERY_TIMEOUT = 120

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


class _SignaturesLoadError(Exception):
    """Surfaced via a SkipTest class instead of crashing the test loader."""


def _signatures() -> dict:
    """Load battery_signatures.json; return {} if file missing."""
    if not SIGNATURES_PATH.exists():
        return {}
    try:
        return json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _SignaturesLoadError(
            f"battery_signatures.json is not valid JSON at "
            f"line {exc.lineno}, col {exc.colno}: {exc.msg}. "
            f"Run `python3 -m json.tool {SIGNATURES_PATH}` to locate."
        ) from exc


def _resolve_source(fixture_name: str, sig: dict) -> Path | None:
    """Resolve where the fixture lives on disk based on its sig's 'source' hint."""
    src = sig.get("source", "tmp")
    if src == "synthetic":
        path = SYNTHETIC_DIR / fixture_name
    elif src == "platform":
        path = PLATFORM_DIR / fixture_name
    else:
        path = TMP_DIR / fixture_name
    return path if path.is_file() else None


def _run_html2docx(src: Path, dst: Path, *, reader: bool) -> tuple[int, str]:
    """Run html2docx.js; return (rc, stderr)."""
    cmd = [
        "node", str(SCRIPTS / "html2docx.js"),
        str(src), str(dst),
        "--json-errors",
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


def _docx_paragraph_count_text_and_images(docx: Path) -> tuple[int, str, int]:
    """Return (paragraph_count, body_text, image_count) from word/document.xml.

    Parses the OOXML `<w:p>` / `<w:t>` / `<w:drawing>` elements directly
    via lxml, no python-docx needed. Empty `<w:t>` is skipped to avoid
    spurious None in the joined text. Paragraph count includes table
    cells (each `<w:tc>` contains its own `<w:p>`).

    Image count = number of `<w:drawing>` elements. q-7 HIGH-1: needed
    a tighter signal than size/paragraph bands could provide for
    icon-strip rule regressions — a single 20×20 SVG icon round-tripped
    through Chrome → PNG adds only ~200 bytes (well within the ±10 %
    size tolerance) and ~1 paragraph (within ±2 slack). Counting
    `<w:drawing>` exactly catches binary "is this image present?"
    regressions without any tolerance noise.
    """
    with zipfile.ZipFile(docx, "r") as zf:
        with zf.open("word/document.xml") as f:
            tree = etree.parse(f)
    root = tree.getroot()
    paras = root.findall(".//w:p", NS)
    runs = root.findall(".//w:t", NS)
    drawings = root.findall(".//w:drawing", NS)
    text = " ".join((r.text or "") for r in runs)
    return len(paras), text, len(drawings)


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
            docx = Path(td) / f"out-{self.mode}.docx"
            rc, stderr = _run_html2docx(
                self.source_path, docx, reader=(self.mode == "reader"),
            )
            self.assertEqual(
                rc, 0,
                f"html2docx returned rc={rc} on {self.fixture_name} "
                f"({self.mode})\nstderr: {stderr[-500:]}",
            )
            self.assertTrue(docx.exists(), "no .docx produced")
            self.assertGreater(docx.stat().st_size, 1024, ".docx suspiciously small")

            entry = self.sig[self.mode]
            paragraphs, body, images = _docx_paragraph_count_text_and_images(docx)
            size_kb = docx.stat().st_size // 1024

            def _norm(s: str) -> str:
                return re.sub(r"\s+", " ", s).strip()

            text = _norm(body)

            self.assertGreaterEqual(
                paragraphs, entry["min_paragraphs"],
                f"paragraph count {paragraphs} below min {entry['min_paragraphs']} "
                f"({self.fixture_name} {self.mode})",
            )
            self.assertLessEqual(
                paragraphs, entry["max_paragraphs"],
                f"paragraph count {paragraphs} above max {entry['max_paragraphs']} "
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
            # Image count assertion is OPTIONAL (q-7 HIGH-1 fix). If the
            # signature carries `min_images`/`max_images`, we enforce them;
            # otherwise we skip the check (back-compat for fixtures captured
            # before the metric was added).
            if "min_images" in entry and "max_images" in entry:
                self.assertGreaterEqual(
                    images, entry["min_images"],
                    f"image count {images} below min {entry['min_images']} "
                    f"({self.fixture_name} {self.mode}) — preprocessing may "
                    f"have over-stripped icons or diagrams",
                )
                self.assertLessEqual(
                    images, entry["max_images"],
                    f"image count {images} above max {entry['max_images']} "
                    f"({self.fixture_name} {self.mode}) — chrome icon may "
                    f"have leaked past the strip rules",
                )
            for needle in entry.get("required_needles", []):
                self.assertIn(
                    _norm(needle), text,
                    f"required needle {needle!r} missing from "
                    f"{self.fixture_name} ({self.mode})",
                )
            for needle in entry.get("forbidden_needles", []):
                self.assertNotIn(
                    _norm(needle), text,
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
_globals = globals()
try:
    _signatures_data = _signatures()
    _load_error: str | None = None
except _SignaturesLoadError as _exc:
    _signatures_data = {}
    _load_error = str(_exc)

_node_missing = shutil.which("node") is None

if _load_error is not None:
    class TestBatterySignaturesInvalid(unittest.TestCase):
        def test_signatures_invalid(self) -> None:
            self.fail(_load_error)
    _globals["TestBatterySignaturesInvalid"] = TestBatterySignaturesInvalid
elif _node_missing:
    class TestBatteryNodeMissing(unittest.TestCase):
        def test_node_missing(self) -> None:
            self.skipTest(
                "node not on PATH — required for html2docx.js. "
                "Install: macOS `brew install node`; "
                "Debian/Ubuntu `sudo apt install nodejs npm`."
            )
    _globals["TestBatteryNodeMissing"] = TestBatteryNodeMissing
elif not _signatures_data:
    class TestBatteryEmpty(unittest.TestCase):
        def test_no_signatures_file(self) -> None:
            self.skipTest(
                f"no signatures file at {SIGNATURES_PATH}; "
                "run tests/capture_signatures.py first"
            )
    _globals["TestBatteryEmpty"] = TestBatteryEmpty
else:
    _registered_slugs: set[str] = set()
    for _fixture_name, _sig in _signatures_data.items():
        _slug = _slugify(_fixture_name)
        for _mode in ("regular", "reader"):
            _cls_name = f"TestBattery_{_slug}_{_mode}"
            if _cls_name in _registered_slugs:
                raise RuntimeError(
                    f"battery: slug collision on {_cls_name!r} "
                    f"(fixture {_fixture_name!r}). "
                    "Two fixtures slugified to the same Python class name; "
                    "rename one in tmp/ or in `battery_signatures.json` "
                    "so their slugs differ."
                )
            _registered_slugs.add(_cls_name)
            _globals[_cls_name] = _make_test_class(
                _cls_name, _fixture_name, _mode, _sig,
            )


if __name__ == "__main__":
    if shutil.which("node") is None:
        print("WARNING: node not in PATH; tests will fail.", file=sys.stderr)
    unittest.main(verbosity=2)
