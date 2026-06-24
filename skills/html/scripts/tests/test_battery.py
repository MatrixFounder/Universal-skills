"""html conversion-quality battery (mirrors docx/pdf `test_battery.py`).

Reads `battery_signatures.json` and, for every fixture present on disk, re-converts and
asserts:
  • count metrics within ±25 % (±2 floor) of the captured baseline (lines / headings /
    GFM-table-rows / code-fences),
  • **empty_headings == 0** and **stray_chrome == 0** — the invariants that lock the
    GitBook/Mintlify/Fern heading + chrome fixes against regression,
  • every `required_needle` appears in the whole-page Markdown.

Tier-0 real fixtures (gitignored `tmp/`) skip per-fixture when absent; the committed
synthetic `gitbook-style-doc.html` always runs (so CI has a real assertion).

Refresh baselines:  ./.venv/bin/python tests/capture_signatures.py --refresh
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import capture_signatures as cap  # noqa: E402

_SIG = json.loads(cap.SIG_PATH.read_text("utf-8")) if cap.SIG_PATH.exists() else {}


def _within(baseline: float, actual: float, tol: float = 0.25, floor: float = 2) -> bool:
    lo = min(baseline * (1 - tol), baseline - floor)
    hi = max(baseline * (1 + tol), baseline + floor)
    return lo <= actual <= hi


class TestBattery(unittest.TestCase):
    pass


def _make(name: str, sig: dict):
    def test(self):
        spec = cap.FIXTURES.get(name)
        if not spec or not spec["path"].exists():
            self.skipTest(f"fixture absent: {name}")
        whole, _reader = cap.convert(spec["path"])
        self.assertIsNotNone(whole, f"{name}: conversion failed")
        m = cap.metrics(whole)
        w = sig["whole"]
        # Quality invariants (the fixes) — hard zero.
        self.assertEqual(m["empty_headings"], 0, f"{name}: empty ATX headings leaked")
        self.assertEqual(m["stray_chrome"], 0, f"{name}: stray chrome lines leaked")
        # Structural drift within tolerance.
        for key in ("lines", "headings", "table_rows", "code_fences"):
            self.assertTrue(
                _within(w[key], m[key]),
                f"{name}.{key}: {m[key]} outside ±25% of baseline {w[key]}")
        for needle in w.get("required_needles", []):
            self.assertIn(needle, whole, f"{name}: required needle missing: {needle!r}")

    return test


for _name, _sig in _SIG.items():
    _slug = re.sub(r"\W+", "_", _name)[:48].strip("_")
    setattr(TestBattery, f"test_{_slug}", _make(_name, _sig))


if __name__ == "__main__":
    unittest.main()
