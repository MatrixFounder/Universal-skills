"""SEC-C1 regression: committed Skool HTML fixtures must contain no PII.

The original lesson snapshots dropped into ``tmp/test-data/`` carry
real Skool group/user/lesson UUIDs, community slugs, and the original
course title. The :mod:`_sanitize_fixture` utility is supposed to strip
all of that before the file lands in :file:`tests/fixtures/`. This test
file holds the regression: an explicit denylist + a 32-hex-uuid
sniffer that catches stray real ids if the sanitiser is ever weakened.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"


# Strings known to appear in the original (un-sanitised) Skool snapshots.
# Any of these surviving in a committed fixture means the sanitiser
# either missed a code path or was bypassed. Keep this list in sync
# with :file:`_sanitize_fixture.py::_SYNTHETIC`.
_PII_DENYLIST: tuple[str, ...] = (
    # Real Skool group / user / lesson UUIDs from the original snapshot.
    "b5fc7b3e7fde48559c305150cb603ff4",
    "774092e4daf14a18ad07ecf9d5eeebc3",
    "d40ba71e3ed1474cb958b6f08b1920cc",
    "48f5dcd3fb2b41eea47108954d66fc09",
    "f527899e05dc4d578459d79943331042",
    # Real community slug + classroom id from the original URL.
    "zero-one",
    "a60f0bd2",
    # Real YouTube video id embedded in the original lesson's videoLink.
    "6njREUQAFdg",
    "maxresdefault",
    # Hormozi-tenant tag and original page title from <title>.
    "Hormozi",
    "Self-Improving Trading Agent",
    "ZeroOne Systems",
)

# Skool's own UUIDs are 32 lowercase hex chars (no dashes). Our
# synthetic replacements are also 32 chars but pad with leading zeros
# (``00000000000000000000000000000001``..``..0005``) — those should pass
# this sniffer too, but a freshly captured real UUID won't.
_REAL_UUID_RE = re.compile(r"\b[0-9a-f]{32}\b")
_SYNTHETIC_UUID_RE = re.compile(r"\b0{31}[0-9a-f]\b")


class TestFixturesContainNoPii(unittest.TestCase):
    def _fixture_paths(self) -> list[Path]:
        return sorted(_FIXTURES.glob("skool_*.html"))

    def test_denylist_strings_absent(self) -> None:
        for path in self._fixture_paths():
            text = path.read_text(encoding="utf-8")
            for needle in _PII_DENYLIST:
                self.assertNotIn(
                    needle, text,
                    f"PII string {needle!r} found in {path.name} — "
                    "re-run _sanitize_fixture.py before committing.",
                )

    def test_only_synthetic_uuids_remain(self) -> None:
        for path in self._fixture_paths():
            text = path.read_text(encoding="utf-8")
            for match in _REAL_UUID_RE.finditer(text):
                token = match.group(0)
                self.assertRegex(
                    token, _SYNTHETIC_UUID_RE,
                    f"non-synthetic 32-hex token {token!r} in {path.name}; "
                    "either it's a real UUID or the sanitiser needs to "
                    "scrub another field.",
                )


if __name__ == "__main__":
    unittest.main()
