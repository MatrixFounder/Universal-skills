"""Guard tests for `capture_signatures.py` — the cross-platform-refresh footgun.

Background: committed `synthetic` (examples/regression/) and `platform`
(tests/fixtures/platforms/) battery fixtures render on BOTH a dev's macOS box
and Ubuntu CI. macOS (CoreText) embeds ~2x the bytes Ubuntu (freetype/
fontconfig) does — `vcru-entry-tail` regular is 8.5x. Their committed size
bands therefore use a deliberate 1 kB floor (set in d71ff36) so the band spans
both platforms. Running `capture_signatures.py --refresh` on macOS re-bakes
those bands to tight CoreText sizes Ubuntu can't satisfy — the regression that
turned office-skills CI red in 1f55847 (24 battery assertions "size below min").

These tests lock the guard (`_should_capture` keeps committed baselines
untouched off-Linux) and the resulting on-disk invariant (committed floors
stay at 1 kB).

Run:  ./.venv/bin/python -m unittest tests.test_capture_guard -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import capture_signatures as cap  # noqa: E402


class TestShouldCapture(unittest.TestCase):
    """The pure decision function — the heart of the guard."""

    def _cap(self, **kw) -> bool:
        return cap._should_capture(**kw)[0]

    def _reason(self, **kw) -> str:
        return cap._should_capture(**kw)[1]

    def test_committed_refresh_off_linux_is_blocked(self):
        # THE regression: macOS `--refresh` must NOT touch committed bands.
        for source in ("synthetic", "platform"):
            do, reason = cap._should_capture(
                source=source, in_existing=True, refresh=True, on_linux=False)
            self.assertFalse(do, f"{source} refresh off-Linux should be blocked")
            self.assertIn("committed", reason)
            self.assertIn(source, reason)

    def test_committed_refresh_on_linux_is_allowed(self):
        # CI (Ubuntu) IS allowed to regenerate committed bands.
        for source in ("synthetic", "platform"):
            self.assertTrue(self._cap(
                source=source, in_existing=True, refresh=True, on_linux=True))

    def test_tmp_refresh_off_linux_is_allowed(self):
        # tmp/ fixtures are dev-only (skipped in CI); refreshing them on the
        # dev's own macOS box is the whole point — never blocked.
        self.assertTrue(self._cap(
            source="tmp", in_existing=True, refresh=True, on_linux=False))

    def test_new_committed_fixture_is_always_captured(self):
        # A brand-new committed fixture (no entry yet) must be captured even
        # off-Linux — otherwise it would have no baseline at all. (The caller
        # then forces its size floor to 1 kB; see TestCommittedBands.)
        for on_linux in (True, False):
            self.assertTrue(self._cap(
                source="synthetic", in_existing=False, refresh=True,
                on_linux=on_linux))
            self.assertTrue(self._cap(
                source="platform", in_existing=False, refresh=False,
                on_linux=on_linux))

    def test_existing_without_refresh_is_skipped(self):
        do, reason = cap._should_capture(
            source="tmp", in_existing=True, refresh=False, on_linux=True)
        self.assertFalse(do)
        self.assertEqual(reason, "already in baseline")


class TestSourceOf(unittest.TestCase):
    """Directory-based source classification (ground truth for the guard)."""

    def test_classifies_by_directory(self):
        from pathlib import Path
        syn = Path("/x/examples/regression")
        plat = Path("/x/tests/fixtures/platforms")
        self.assertEqual(cap._source_of(syn / "a.html", syn, plat), "synthetic")
        self.assertEqual(cap._source_of(plat / "b.html", syn, plat), "platform")
        self.assertEqual(cap._source_of(Path("/x/tmp/c.webarchive"), syn, plat), "tmp")


class TestCommittedBandsAreCrossPlatform(unittest.TestCase):
    """On-disk invariant: every committed synthetic/platform band keeps the
    1 kB floor that lets it span macOS + Ubuntu. This is the assertion that
    fails the instant someone re-bakes the bands on a single platform
    (exactly what 1f55847 did)."""

    def test_committed_floors_are_one_kb(self):
        if not cap.SIGNATURES_PATH.exists():
            self.skipTest("battery_signatures.json absent")
        data = json.loads(cap.SIGNATURES_PATH.read_text("utf-8"))
        offenders = []
        committed = 0
        for name, sig in data.items():
            if sig.get("source") not in ("synthetic", "platform"):
                continue
            committed += 1
            for mode in ("regular", "reader"):
                entry = sig.get(mode)
                if entry is not None and entry.get("min_size_kb") != 1:
                    offenders.append(f"{name}/{mode}={entry.get('min_size_kb')}kB")
        self.assertGreater(committed, 0, "no committed fixtures found — schema drift?")
        self.assertEqual(
            offenders, [],
            "committed synthetic/platform fixtures must keep a 1 kB size floor "
            "(cross-platform band). Offenders likely re-baked on a single "
            f"platform — regenerate on Ubuntu CI: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
