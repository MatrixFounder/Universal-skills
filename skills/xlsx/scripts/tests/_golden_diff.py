"""Golden-diff harness for `xlsx_add_comment.py` regression tests.

Compares an actual `.xlsx` produced by the script against a committed
`.golden.xlsx` under canonical XML (m-5 / A-Q3) with two volatile
attributes masked (R9.e UUIDv4 + un-pinned `<threadedComment dT>`).

Public surface:
    canon_part(xml_bytes)  -> bytes
    diff_xlsx(actual, golden) -> str | None    # None == match.

Used by `test_xlsx_add_comment.TestGoldenDiff` (unit tests for the
mask itself) and the golden-diff block in `test_e2e.sh`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

THREADED_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
_VOLATILE_XPATH = f".//{{{THREADED_NS}}}threadedComment"
_PINNED_DATE_MARKER = "2026-01-01"

# Parts excluded from the c14n diff because their content is volatile in
# ways the test doesn't care about:
#   - docProps/core.xml: openpyxl unconditionally overwrites
#     `<dcterms:modified>` with `datetime.now(UTC)` on every save, even
#     when `wb.properties.modified` is pinned. xlsx_add_comment is a
#     pure unpack→edit→pack pipeline (office/pack.py) that passes
#     docProps/core.xml through unchanged FROM THE INPUT — so as soon
#     as the input fixture is regenerated (which test_e2e.sh does on
#     fresh checkouts), `modified` drifts to the regen time and the
#     diff fails on a part orthogonal to comment-injection correctness.
#     This excludes only docProps/core.xml — comment-bearing parts
#     (comments*.xml, threadedComments*.xml, vmlDrawing*.xml, sheet
#     rels, [Content_Types].xml) remain fully checked.
_VOLATILE_PARTS = frozenset({"docProps/core.xml"})


def canon_part(xml_bytes: bytes) -> bytes:
    """Mask volatile attributes, then C14N-serialise.

    Volatile rules (R9.e + goldens-pin convention):
      - `<threadedComment id>` always rewritten to `{MASKED}` — UUIDv4.
      - `<threadedComment dT>` rewritten to `"MASKED"` UNLESS the value
        contains the pinned-date marker `2026-01-01` (the deterministic
        `--date` value used to generate goldens).
    """
    root = etree.fromstring(xml_bytes)
    for tc in root.iterfind(_VOLATILE_XPATH):
        if "id" in tc.attrib:
            tc.attrib["id"] = "{MASKED}"
        dt = tc.attrib.get("dT", "")
        if dt and _PINNED_DATE_MARKER not in dt:
            tc.attrib["dT"] = "MASKED"
    return etree.tostring(root, method="c14n")


def diff_xlsx(actual_path: Path, golden_path: Path) -> str | None:
    """Compare two `.xlsx` packages part-by-part under canonicalisation.

    Returns:
      - `None` on byte-equivalent (under c14n + mask) match.
      - `str` describing the first mismatch on divergence (part list
        delta, or first part whose c14n bytes differ).

    Binary parts (anything not `.xml` / `.rels`) are skipped — those
    have their own invariants (e.g. vbaProject.bin sha256 in 2.08).
    """
    actual_path = Path(actual_path)
    golden_path = Path(golden_path)
    with zipfile.ZipFile(actual_path) as a, zipfile.ZipFile(golden_path) as g:
        a_parts = set(a.namelist())
        g_parts = set(g.namelist())
        if a_parts != g_parts:
            only_a = sorted(a_parts - g_parts)
            only_g = sorted(g_parts - a_parts)
            return (
                f"Part list differs: only-in-actual={only_a}, "
                f"only-in-golden={only_g}"
            )
        for part in sorted(a_parts):
            if not (part.endswith(".xml") or part.endswith(".rels")):
                continue
            if part in _VOLATILE_PARTS:
                continue
            a_canon = canon_part(a.read(part))
            g_canon = canon_part(g.read(part))
            if a_canon != g_canon:
                return f"Part {part} differs under c14n + volatile mask"
    return None
