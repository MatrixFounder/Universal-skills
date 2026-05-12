"""Unit tests for `_relocator.py` (docx-008 chain).

Stage 0 (task-008-01a) state: every test except the import-boundary
regression-lock is annotated `@unittest.skip("stub-first; logic
lands in 008-0X")`. As each sub-task lands logic for a function,
the corresponding tests are unskipped (decorator removed).

Downstream sub-task mapping per class:
  TestAssertSafeTarget            → 008-01b
  TestCopyExtraMedia              → 008-02
  TestMaxExistingRid              → 008-02
  TestMergeRelationships          → 008-02
  TestRemapRidsInClones           → 008-02
  TestMergeContentTypesDefaults   → 008-02
  TestRelocationReportInvariants  → 008-02 (zero-report) + 008-07 (rels_appended invariant)
  TestCopyNonmediaParts           → 008-03
  TestApplyNonmediaRenameToRels   → 008-03
  TestReadRelTargets              → 008-03
  TestMergeNumbering              → 008-05
  TestRemapNumidInClones          → 008-05
  TestEnsureNumberingPart         → 008-05
  TestRelocateAssetsIdempotent    → 008-07
  TestImportBoundary              → 008-01a (LIVE GREEN)

Total at chain end (post-008-07): 49 LIVE GREEN / 0 skipped.

Forward references for tests that live in `test_docx_replace.py`
(not in this file) so callers know where they land:
  TestRunSuccessLine (3 tests)        → 008-07; lives in test_docx_replace.py
  TestPathTraversal (2 tests)         → 008-07; lives in test_docx_replace.py
"""
from __future__ import annotations

import ast
import shutil
import tempfile
import unittest
from pathlib import Path

from lxml import etree  # type: ignore

import _relocator  # noqa: F401
from _relocator import (  # noqa: F401
    RelocationReport,
    relocate_assets,
    _copy_extra_media,
    _max_existing_rid,
    _merge_relationships,
    _copy_nonmedia_parts,
    _read_rel_targets,
    _apply_nonmedia_rename_to_rels,
    _remap_rids_in_clones,
    _merge_content_types_defaults,
    _merge_numbering,
    _ensure_numbering_part,
    _remap_numid_in_clones,
    _assert_safe_target,
    _MERGEABLE_REL_TYPES,
    _RID_ATTRS,
    R_NS,
    PR_NS,
    CT_NS,
)
from _app_errors import Md2DocxOutputInvalid


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_rels_xml(rels: "list[tuple[str, str, str]]") -> bytes:
    """Build a rels XML byte string from a list of (Id, Type, Target)."""
    nsmap = {None: PR_NS}
    root = etree.Element(f"{{{PR_NS}}}Relationships", nsmap=nsmap)
    for rid, rtype, target in rels:
        rel = etree.SubElement(root, f"{{{PR_NS}}}Relationship")
        rel.set("Id", rid)
        rel.set("Type", rtype)
        rel.set("Target", target)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True,
    )


def _write_rels_file(
    path: Path, rels: "list[tuple[str, str, str]]",
) -> None:
    """Write a rels file with the given relationships."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_rels_xml(rels))


def _write_content_types(
    path: Path, defaults: "list[tuple[str, str]]",
) -> None:
    """Write a [Content_Types].xml file with the given <Default> entries.
    Each entry is (Extension, ContentType)."""
    nsmap = {None: CT_NS}
    root = etree.Element(f"{{{CT_NS}}}Types", nsmap=nsmap)
    for ext, ctype in defaults:
        d = etree.SubElement(root, f"{{{CT_NS}}}Default")
        d.set("Extension", ext)
        d.set("ContentType", ctype)
    path.write_bytes(etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True,
    ))


# ---------------------------------------------------------------------------
# 008-01a — LIVE GREEN: import-boundary regression-lock (Decision D3)
# ---------------------------------------------------------------------------

class TestImportBoundary(unittest.TestCase):
    """NIT-1 regression-lock for Decision D3 (re-use docx_merge.py
    helpers BY COPY, NOT by import). An AST walk over `_relocator.py`
    asserts the no-import invariant. If a future contributor refactors
    the duplication away via `from docx_merge import ...`, this test
    fails immediately and demands a TASK revision."""

    def test_relocator_does_not_import_docx_merge(self) -> None:
        relocator_src = Path(__file__).resolve().parent.parent / "_relocator.py"
        source = relocator_src.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(
                        "docx_merge", alias.name,
                        f"_relocator.py imports {alias.name} — violates D3",
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                self.assertNotIn(
                    "docx_merge", module_name,
                    f"_relocator.py uses `from {module_name} import ...` — violates D3",
                )


# ---------------------------------------------------------------------------
# 008-01b — _assert_safe_target (F16) path-traversal guards
# ---------------------------------------------------------------------------

class TestAssertSafeTarget(unittest.TestCase):
    """F16 — path-traversal security primitive. Four reject branches:
    absolute_or_empty / drive_letter / parent_segment / outside_base.
    Each populates `details.reason` with a fixed token."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="docx-relocator-"))
        (self.tmpdir / "word").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_relative_target_ok(self) -> None:
        # Should not raise on legitimate relative paths.
        _assert_safe_target("media/img.png", self.tmpdir)
        _assert_safe_target("charts/chart1.xml", self.tmpdir)
        _assert_safe_target("embeddings/oleObject1.bin", self.tmpdir)
        _assert_safe_target("diagrams/data1.xml", self.tmpdir)

    def test_absolute_path_rejected(self) -> None:
        # Absolute paths (starts with '/').
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("/etc/passwd", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")
        # Empty string.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")
        # UNC / backslash.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("\\\\server\\share\\f.png", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")
        # NUL byte in target — Path.resolve() would raise ValueError otherwise,
        # violating the contract. (Sarcasmotron MIN-1.)
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("media/img\x00.png", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")

    def test_parent_segment_rejected(self) -> None:
        # Plain '..' escape.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("../../etc/passwd", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")
        # Embedded '..'.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("media/../../../etc/passwd", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")
        # Single leading '..'.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("../foo", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")

    def test_drive_letter_rejected(self) -> None:
        # Windows drive-letter forms.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("C:/Windows/system32/cmd.exe", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "drive_letter")
        # Drive letter without slash.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("D:nofile.txt", self.tmpdir)
        self.assertEqual(ctx.exception.details["reason"], "drive_letter")

    def test_outside_base_rejected(self) -> None:
        # Symlink trick: word/linked → outside-tree directory.
        # Use resolved parent for portability across macOS /tmp → /private/tmp
        # symlink pair (Sarcasmotron MIN-2).
        escape = self.tmpdir.resolve().parent / f"escape-{self.tmpdir.name}"
        try:
            escape.mkdir(exist_ok=True)
            (self.tmpdir / "word" / "linked").symlink_to(
                escape, target_is_directory=True,
            )
            with self.assertRaises(Md2DocxOutputInvalid) as ctx:
                _assert_safe_target("linked/escape.png", self.tmpdir)
            self.assertEqual(
                ctx.exception.details["reason"], "outside_base",
            )
        finally:
            shutil.rmtree(escape, ignore_errors=True)


# ---------------------------------------------------------------------------
# 008-02 — Image relocator core (F10 + F11 + F12 + R4 + R5)
# ---------------------------------------------------------------------------

class TestCopyExtraMedia(unittest.TestCase):
    """F10 — media copy with fixed insert_ prefix; collision-safe counter."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-insert-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    def test_no_media_dir_returns_empty_map(self) -> None:
        # insert has no word/media at all → empty map.
        result = _copy_extra_media(self.base, self.insert)
        self.assertEqual(result, {})

    def test_single_file_copied_with_prefix(self) -> None:
        media = self.insert / "word" / "media"
        media.mkdir(parents=True)
        src = media / "img.png"
        src.write_bytes(b"PNGDATA")
        result = _copy_extra_media(self.base, self.insert)
        self.assertEqual(result, {"media/img.png": "media/insert_img.png"})
        dst = self.base / "word" / "media" / "insert_img.png"
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_bytes(), b"PNGDATA")

    def test_collision_renamed_to_counter(self) -> None:
        media = self.insert / "word" / "media"
        media.mkdir(parents=True)
        (media / "img.png").write_bytes(b"NEW")
        # Pre-create the collision target.
        base_media = self.base / "word" / "media"
        base_media.mkdir(parents=True)
        (base_media / "insert_img.png").write_bytes(b"EXISTING1")
        # First collision → insert_2_img.png.
        result = _copy_extra_media(self.base, self.insert)
        self.assertEqual(
            result, {"media/img.png": "media/insert_2_img.png"},
        )
        self.assertEqual(
            (base_media / "insert_2_img.png").read_bytes(), b"NEW",
        )
        # Original collision target preserved.
        self.assertEqual(
            (base_media / "insert_img.png").read_bytes(), b"EXISTING1",
        )
        # Triple-collision → insert_3_img.png.
        (media / "img.png").write_bytes(b"THIRD")
        result2 = _copy_extra_media(self.base, self.insert)
        self.assertEqual(
            result2, {"media/img.png": "media/insert_3_img.png"},
        )

    def test_returns_relative_target_map(self) -> None:
        media = self.insert / "word" / "media"
        media.mkdir(parents=True)
        (media / "a.jpg").write_bytes(b"A")
        (media / "b.png").write_bytes(b"B")
        result = _copy_extra_media(self.base, self.insert)
        # Keys + values use "media/..." prefix (relative, not absolute).
        for k, v in result.items():
            self.assertTrue(k.startswith("media/"))
            self.assertTrue(v.startswith("media/"))
            self.assertFalse(k.startswith("/"))
            self.assertFalse(v.startswith("/"))


class TestMaxExistingRid(unittest.TestCase):
    """F11 — largest numeric N in rId<N> attributes."""

    @staticmethod
    def _root(rels: "list[tuple[str, str, str]]") -> "etree._Element":
        return etree.fromstring(_make_rels_xml(rels))

    def test_empty_rels_returns_zero(self) -> None:
        root = self._root([])
        self.assertEqual(_max_existing_rid(root), 0)

    def test_single_rid_returned(self) -> None:
        root = self._root([
            ("rId5", f"{R_NS}/image", "media/img.png"),
        ])
        self.assertEqual(_max_existing_rid(root), 5)

    def test_gap_filled_returns_max(self) -> None:
        root = self._root([
            ("rId1", f"{R_NS}/image", "media/a.png"),
            ("rId7", f"{R_NS}/image", "media/b.png"),
            ("rId3", f"{R_NS}/image", "media/c.png"),
        ])
        self.assertEqual(_max_existing_rid(root), 7)

    def test_non_numeric_id_skipped(self) -> None:
        root = self._root([
            ("rIdABC", f"{R_NS}/image", "media/a.png"),
            ("rId4", f"{R_NS}/image", "media/b.png"),
            ("foo", f"{R_NS}/image", "media/c.png"),
        ])
        self.assertEqual(_max_existing_rid(root), 4)


class TestMergeRelationships(unittest.TestCase):
    """F12 — append mergeable rels with rId offset + path-traversal guard."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-mrels-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-mrels-insert-"))
        (self.base / "word").mkdir()
        self.base_rels = self.base / "word" / "_rels" / "document.xml.rels"
        self.insert_rels = self.insert / "word" / "_rels" / "document.xml.rels"

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    def _read_appended(self) -> "list[dict]":
        """Read base rels and return list of {Id, Type, Target, TargetMode}."""
        tree = etree.parse(str(self.base_rels))
        out = []
        for r in tree.getroot().findall(f"{{{PR_NS}}}Relationship"):
            out.append({
                "Id": r.get("Id"),
                "Type": r.get("Type"),
                "Target": r.get("Target"),
                "TargetMode": r.get("TargetMode"),
            })
        return out

    def test_mergeable_only_appended(self) -> None:
        # insert has 1 image (mergeable) + 1 styles (NOT mergeable).
        _write_rels_file(self.base_rels, [])
        _write_rels_file(self.insert_rels, [
            ("rId1", f"{R_NS}/image", "media/a.png"),
            ("rId2", f"{R_NS}/styles", "styles.xml"),
        ])
        rid_map = _merge_relationships(
            self.base_rels, self.insert_rels, {}, 1, self.base,
        )
        appended = self._read_appended()
        # Only the image rel was appended.
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["Type"], f"{R_NS}/image")
        # Only the image rel is in rid_map.
        self.assertEqual(set(rid_map.keys()), {"rId1"})

    def test_rid_offset_avoids_collision(self) -> None:
        # base has rId1..rId5; insert image should get rId6.
        _write_rels_file(self.base_rels, [
            (f"rId{i}", f"{R_NS}/image", f"media/x{i}.png")
            for i in range(1, 6)
        ])
        _write_rels_file(self.insert_rels, [
            ("rId1", f"{R_NS}/image", "media/new.png"),
        ])
        rid_map = _merge_relationships(
            self.base_rels, self.insert_rels, {}, 6, self.base,
        )
        self.assertEqual(rid_map, {"rId1": "rId6"})
        appended = self._read_appended()
        # 5 original + 1 new = 6 total.
        self.assertEqual(len(appended), 6)
        # The appended rel has Id=rId6.
        new_rels = [r for r in appended if r["Target"] == "media/new.png"]
        self.assertEqual(len(new_rels), 1)
        self.assertEqual(new_rels[0]["Id"], "rId6")

    def test_image_target_rewritten_via_rename_map(self) -> None:
        _write_rels_file(self.base_rels, [])
        _write_rels_file(self.insert_rels, [
            ("rId1", f"{R_NS}/image", "media/img.png"),
        ])
        media_rename = {"media/img.png": "media/insert_img.png"}
        _merge_relationships(
            self.base_rels, self.insert_rels, media_rename, 1, self.base,
        )
        appended = self._read_appended()
        self.assertEqual(appended[0]["Target"], "media/insert_img.png")

    def test_external_hyperlink_skips_path_guard(self) -> None:
        # An external hyperlink with a URL that would otherwise look
        # "absolute" — Branch 1 would reject it, but External skips guard.
        _write_rels_file(self.base_rels, [])
        # We must write TargetMode="External" attribute; the helper
        # doesn't support it directly, so write manually.
        root = etree.Element(f"{{{PR_NS}}}Relationships", nsmap={None: PR_NS})
        r = etree.SubElement(root, f"{{{PR_NS}}}Relationship")
        r.set("Id", "rId1")
        r.set("Type", f"{R_NS}/hyperlink")
        r.set("Target", "http://evil.example.com/")
        r.set("TargetMode", "External")
        self.insert_rels.parent.mkdir(parents=True, exist_ok=True)
        self.insert_rels.write_bytes(etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True,
        ))
        # Should not raise.
        rid_map = _merge_relationships(
            self.base_rels, self.insert_rels, {}, 1, self.base,
        )
        self.assertEqual(set(rid_map.keys()), {"rId1"})
        appended = self._read_appended()
        self.assertEqual(appended[0]["TargetMode"], "External")
        self.assertEqual(appended[0]["Target"], "http://evil.example.com/")

    def test_returns_complete_rid_map(self) -> None:
        # Multiple mergeable rels (image + chart + diagramData) → all in map.
        _write_rels_file(self.base_rels, [])
        _write_rels_file(self.insert_rels, [
            ("rId10", f"{R_NS}/image", "media/a.png"),
            ("rId11", f"{R_NS}/chart", "charts/chart1.xml"),
            ("rId12", f"{R_NS}/diagramData", "diagrams/data1.xml"),
            ("rId13", f"{R_NS}/theme", "theme/theme1.xml"),  # NOT mergeable
        ])
        rid_map = _merge_relationships(
            self.base_rels, self.insert_rels, {}, 1, self.base,
        )
        # The three mergeable rels are mapped; theme is dropped.
        self.assertEqual(set(rid_map.keys()), {"rId10", "rId11", "rId12"})
        # Allocated rIds are unique and non-colliding.
        self.assertEqual(len(set(rid_map.values())), 3)


class TestRemapRidsInClones(unittest.TestCase):
    """R4 — rewrite r:embed/r:link/r:id/r:dm/r:lo/r:qs/r:cs attrs."""

    def test_rewrite_embed(self) -> None:
        # <a:blip r:embed="rId7"/>
        a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        clone = etree.fromstring(
            f'<wrap xmlns:a="{a_ns}" xmlns:r="{R_NS}">'
            f'<a:blip r:embed="rId7"/></wrap>'.encode()
        )
        count = _remap_rids_in_clones([clone], {"rId7": "rId12"})
        self.assertEqual(count, 1)
        blip = clone.find(f"{{{a_ns}}}blip")
        self.assertEqual(blip.get(f"{{{R_NS}}}embed"), "rId12")

    def test_rewrite_link_and_id(self) -> None:
        a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        clone = etree.fromstring(
            f'<wrap xmlns:a="{a_ns}" xmlns:r="{R_NS}">'
            f'<a:blip r:link="rId3"/>'
            f'<hyperlink r:id="rId4"/></wrap>'.encode()
        )
        count = _remap_rids_in_clones(
            [clone], {"rId3": "rId30", "rId4": "rId40"},
        )
        self.assertEqual(count, 2)
        self.assertEqual(
            clone.find(f"{{{a_ns}}}blip").get(f"{{{R_NS}}}link"), "rId30",
        )
        self.assertEqual(
            clone.find("hyperlink").get(f"{{{R_NS}}}id"), "rId40",
        )

    def test_unmapped_rid_left_alone(self) -> None:
        a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        clone = etree.fromstring(
            f'<wrap xmlns:a="{a_ns}" xmlns:r="{R_NS}">'
            f'<a:blip r:embed="rId99"/></wrap>'.encode()
        )
        # Empty map → no rewrites.
        count = _remap_rids_in_clones([clone], {})
        self.assertEqual(count, 0)
        # Unmapped rId → no rewrite, attr unchanged.
        count = _remap_rids_in_clones([clone], {"rId1": "rId100"})
        self.assertEqual(count, 0)
        self.assertEqual(
            clone.find(f"{{{a_ns}}}blip").get(f"{{{R_NS}}}embed"), "rId99",
        )


class TestMergeContentTypesDefaults(unittest.TestCase):
    """R5 — merge <Default Extension> entries, case-fold compared."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="docx-reloc-ct-"))
        self.base = self.tmpdir / "base_ct.xml"
        self.insert = self.tmpdir / "insert_ct.xml"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_op_when_no_new_extensions(self) -> None:
        _write_content_types(self.base, [("png", "image/png")])
        _write_content_types(self.insert, [("png", "image/png")])
        original_size = self.base.stat().st_size
        count = _merge_content_types_defaults(self.base, self.insert)
        self.assertEqual(count, 0)
        # File unchanged (size identical).
        self.assertEqual(self.base.stat().st_size, original_size)

    def test_appends_missing_default(self) -> None:
        _write_content_types(self.base, [("png", "image/png")])
        _write_content_types(self.insert, [
            ("png", "image/png"),
            ("jpeg", "image/jpeg"),
            ("svg", "image/svg+xml"),
        ])
        count = _merge_content_types_defaults(self.base, self.insert)
        self.assertEqual(count, 2)
        # Verify jpeg + svg are now in base.
        root = etree.parse(str(self.base)).getroot()
        exts = {d.get("Extension") for d in root.findall(f"{{{CT_NS}}}Default")}
        self.assertEqual(exts, {"png", "jpeg", "svg"})

    def test_case_fold_extension_check(self) -> None:
        _write_content_types(self.base, [("PNG", "image/png")])
        _write_content_types(self.insert, [("png", "image/png")])
        count = _merge_content_types_defaults(self.base, self.insert)
        self.assertEqual(count, 0)


class TestRelocationReportInvariants(unittest.TestCase):
    """RelocationReport invariants from ARCH §12.3.1."""

    def test_zero_report_no_op_invocation(self) -> None:
        # Until 008-04 wires the orchestrator, relocate_assets stub returns
        # an all-zero report. Asserts the stub contract.
        tmp = Path(tempfile.mkdtemp(prefix="docx-reloc-zero-"))
        try:
            (tmp / "insert").mkdir()
            (tmp / "base").mkdir()
            report = relocate_assets(tmp / "insert", tmp / "base", [])
            self.assertEqual(
                report,
                RelocationReport(0, 0, 0, 0, 0, 0, 0, 0),
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rels_appended_equals_len_rid_map(self) -> None:
        """ARCH §12.3.1 invariant: rels_appended == len(rid_map) inside
        relocate_assets (every mergeable rel in insert produces one entry
        in rid_map; that entry is reported in rels_appended)."""
        base = Path(tempfile.mkdtemp(prefix="docx-reloc-inv-base-"))
        insert = Path(tempfile.mkdtemp(prefix="docx-reloc-inv-insert-"))
        try:
            # Insert has 3 mergeable rels (image + chart + diagramData) +
            # 1 non-mergeable (theme).
            (insert / "word" / "_rels").mkdir(parents=True)
            _write_rels_file(insert / "word" / "_rels" / "document.xml.rels", [
                ("rId10", f"{R_NS}/image", "media/a.png"),
                ("rId11", f"{R_NS}/chart", "charts/c1.xml"),
                ("rId12", f"{R_NS}/diagramData", "diagrams/d1.xml"),
                ("rId13", f"{R_NS}/theme", "theme/theme1.xml"),
            ])
            (base / "word").mkdir(parents=True)
            report = relocate_assets(insert, base, [])
            # rels_appended counts every mergeable rel = 3 (theme dropped).
            self.assertEqual(report.rels_appended, 3)
        finally:
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(insert, ignore_errors=True)


# ---------------------------------------------------------------------------
# 008-03 — Non-media part copy (F13) + helpers
# ---------------------------------------------------------------------------

class TestCopyNonmediaParts(unittest.TestCase):
    """F13 — chart/OLE/SmartArt part copy; verbatim default; collision-rename."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-nm-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-nm-insert-"))
        (self.base / "word").mkdir()
        (self.insert / "word").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    def test_chart_part_and_sibling_rels_copied(self) -> None:
        charts = self.insert / "word" / "charts"
        charts.mkdir()
        (charts / "chart1.xml").write_bytes(b"<chartXML/>")
        (charts / "_rels").mkdir()
        (charts / "_rels" / "chart1.xml.rels").write_bytes(b"<relsXML/>")
        rename_map = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/chart", "charts/chart1.xml"),
        ])
        self.assertEqual(rename_map, {})  # No collision, no rename.
        # Part copied byte-identical.
        dst_part = self.base / "word" / "charts" / "chart1.xml"
        self.assertTrue(dst_part.is_file())
        self.assertEqual(dst_part.read_bytes(), b"<chartXML/>")
        # Sibling rels copied verbatim.
        dst_rels = self.base / "word" / "charts" / "_rels" / "chart1.xml.rels"
        self.assertTrue(dst_rels.is_file())
        self.assertEqual(dst_rels.read_bytes(), b"<relsXML/>")

    def test_ole_part_copied(self) -> None:
        emb = self.insert / "word" / "embeddings"
        emb.mkdir()
        (emb / "oleObject1.bin").write_bytes(b"OLEDATA")
        rename_map = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/oleObject", "embeddings/oleObject1.bin"),
        ])
        self.assertEqual(rename_map, {})
        dst = self.base / "word" / "embeddings" / "oleObject1.bin"
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_bytes(), b"OLEDATA")

    def test_smartart_diagrams_copied(self) -> None:
        diag = self.insert / "word" / "diagrams"
        diag.mkdir()
        (diag / "data1.xml").write_bytes(b"<data1/>")
        (diag / "layout1.xml").write_bytes(b"<layout1/>")
        (diag / "quickStyle1.xml").write_bytes(b"<qs1/>")
        (diag / "colors1.xml").write_bytes(b"<colors1/>")
        rename_map = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/diagramData", "diagrams/data1.xml"),
            (f"{R_NS}/diagramLayout", "diagrams/layout1.xml"),
            (f"{R_NS}/diagramQuickStyle", "diagrams/quickStyle1.xml"),
            (f"{R_NS}/diagramColors", "diagrams/colors1.xml"),
        ])
        self.assertEqual(rename_map, {})
        for name in ("data1.xml", "layout1.xml", "quickStyle1.xml", "colors1.xml"):
            self.assertTrue((self.base / "word" / "diagrams" / name).is_file())

    def test_verbatim_when_no_collision(self) -> None:
        charts = self.insert / "word" / "charts"
        charts.mkdir()
        (charts / "chart1.xml").write_bytes(b"<chart/>")
        rename_map = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/chart", "charts/chart1.xml"),
        ])
        # MAJ-3 contract: verbatim copy → NOT in rename_map.
        self.assertEqual(rename_map, {})
        self.assertNotIn("charts/chart1.xml", rename_map)

    def test_collision_renamed_with_insert_prefix(self) -> None:
        # Base PRE-EXISTS the target → first collision → insert_chart1.xml.
        base_charts = self.base / "word" / "charts"
        base_charts.mkdir()
        (base_charts / "chart1.xml").write_bytes(b"<BASE chart/>")
        insert_charts = self.insert / "word" / "charts"
        insert_charts.mkdir()
        (insert_charts / "chart1.xml").write_bytes(b"<INSERT chart/>")
        rename_map = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/chart", "charts/chart1.xml"),
        ])
        self.assertEqual(rename_map, {
            "charts/chart1.xml": "charts/insert_chart1.xml",
        })
        # Base chart1.xml untouched; insert_chart1.xml is the insert's bytes.
        self.assertEqual(
            (base_charts / "chart1.xml").read_bytes(), b"<BASE chart/>",
        )
        self.assertEqual(
            (base_charts / "insert_chart1.xml").read_bytes(), b"<INSERT chart/>",
        )
        # Triple-collision → insert_2_chart1.xml.
        (base_charts / "insert_2_chart1.xml").write_bytes(b"none yet")
        (insert_charts / "chart1.xml").write_bytes(b"<THIRD/>")
        # Actually, second invocation tests a new collision against
        # insert_chart1.xml and insert_2_chart1.xml.
        rename_map2 = _copy_nonmedia_parts(self.base, self.insert, [
            (f"{R_NS}/chart", "charts/chart1.xml"),
        ])
        # Pre-existing: chart1.xml + insert_chart1.xml + insert_2_chart1.xml.
        # → next available is insert_3_chart1.xml.
        self.assertEqual(rename_map2, {
            "charts/chart1.xml": "charts/insert_3_chart1.xml",
        })


class TestApplyNonmediaRenameToRels(unittest.TestCase):
    """_apply_nonmedia_rename_to_rels — rewrite Target attrs for collision-renamed parts."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="docx-reloc-apply-"))
        self.rels = self.tmpdir / "doc.rels"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_map_is_noop(self) -> None:
        _write_rels_file(self.rels, [
            ("rId1", f"{R_NS}/chart", "charts/chart1.xml"),
        ])
        original = self.rels.read_bytes()
        _apply_nonmedia_rename_to_rels(self.rels, {})
        # No-op: bytes unchanged.
        self.assertEqual(self.rels.read_bytes(), original)

    def test_renames_only_listed_targets(self) -> None:
        _write_rels_file(self.rels, [
            ("rId1", f"{R_NS}/chart", "charts/chart1.xml"),
            ("rId2", f"{R_NS}/image", "media/img.png"),
            ("rId3", f"{R_NS}/hyperlink", "http://example.com"),
        ])
        _apply_nonmedia_rename_to_rels(self.rels, {
            "charts/chart1.xml": "charts/insert_chart1.xml",
        })
        # Read back; verify only chart Target rewritten.
        root = etree.parse(str(self.rels)).getroot()
        targets = {
            r.get("Id"): r.get("Target")
            for r in root.findall(f"{{{PR_NS}}}Relationship")
        }
        self.assertEqual(targets["rId1"], "charts/insert_chart1.xml")
        self.assertEqual(targets["rId2"], "media/img.png")
        self.assertEqual(targets["rId3"], "http://example.com")


class TestReadRelTargets(unittest.TestCase):
    """_read_rel_targets — pre-scan helper for non-media part copy."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="docx-reloc-read-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_pairs_in_doc_order(self) -> None:
        rels = self.tmpdir / "doc.rels"
        _write_rels_file(rels, [
            ("rId1", f"{R_NS}/image", "media/a.png"),
            ("rId2", f"{R_NS}/chart", "charts/chart1.xml"),
            ("rId3", f"{R_NS}/oleObject", "embeddings/o.bin"),
        ])
        result = _read_rel_targets(rels)
        # Document order preserved.
        self.assertEqual(result, [
            (f"{R_NS}/image", "media/a.png"),
            (f"{R_NS}/chart", "charts/chart1.xml"),
            (f"{R_NS}/oleObject", "embeddings/o.bin"),
        ])

    def test_missing_file_returns_empty(self) -> None:
        result = _read_rel_targets(self.tmpdir / "does-not-exist.rels")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# 008-05 — Numbering relocator (F14 + F15 + R9–R13)
# ---------------------------------------------------------------------------

W_NS_T = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_numbering_xml(
    abstractnums: "list[tuple[str, str]]",  # [(abstractNumId, marker), ...]
    nums: "list[tuple[str, str]]",  # [(numId, abstractNumId), ...]
    cleanup_value: "str | None" = None,
) -> bytes:
    """Build a numbering.xml byte string with the given defs."""
    root = etree.Element(f"{{{W_NS_T}}}numbering", nsmap={"w": W_NS_T})
    for anum_id, marker in abstractnums:
        a = etree.SubElement(root, f"{{{W_NS_T}}}abstractNum")
        a.set(f"{{{W_NS_T}}}abstractNumId", anum_id)
        # Optional marker element to verify clone identity.
        m = etree.SubElement(a, f"{{{W_NS_T}}}lvl")
        m.set(f"{{{W_NS_T}}}ilvl", "0")
        m.set(f"{{{W_NS_T}}}marker", marker)
    for num_id, anum_ref in nums:
        n = etree.SubElement(root, f"{{{W_NS_T}}}num")
        n.set(f"{{{W_NS_T}}}numId", num_id)
        anum = etree.SubElement(n, f"{{{W_NS_T}}}abstractNumId")
        anum.set(f"{{{W_NS_T}}}val", anum_ref)
    if cleanup_value is not None:
        c = etree.SubElement(root, f"{{{W_NS_T}}}numIdMacAtCleanup")
        c.set(f"{{{W_NS_T}}}val", cleanup_value)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True,
    )


class TestMergeNumbering(unittest.TestCase):
    """F14 — merge insert numbering.xml into base with offset shift."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-num-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-num-insert-"))
        (self.base / "word").mkdir()
        (self.insert / "word").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    def test_no_insert_numbering_returns_empty(self) -> None:
        # No insert/word/numbering.xml → empty result, base untouched.
        result = _merge_numbering(self.base, self.insert)
        self.assertEqual(result, ({}, 0, 0))

    def test_insert_empty_numbering_returns_empty(self) -> None:
        # Insert has numbering.xml but with no <w:abstractNum>/<w:num>.
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([], []),
        )
        result = _merge_numbering(self.base, self.insert)
        self.assertEqual(result, ({}, 0, 0))

    def test_install_verbatim_when_base_has_none(self) -> None:
        # Base has no numbering; insert has 1 abstractNum + 1 num.
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "•")], [("1", "0")]),
        )
        # Ensure base has [Content_Types].xml + word rels (preconditions
        # for _ensure_numbering_part to wire it in).
        (self.base / "[Content_Types].xml").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        )
        rels_dir = self.base / "word" / "_rels"
        rels_dir.mkdir()
        (rels_dir / "document.xml.rels").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )
        result = _merge_numbering(self.base, self.insert)
        # Identity remap on verbatim install.
        self.assertEqual(result, ({"1": "1"}, 1, 1))
        # Base numbering.xml exists and is byte-identical to insert's.
        self.assertEqual(
            (self.base / "word" / "numbering.xml").read_bytes(),
            (self.insert / "word" / "numbering.xml").read_bytes(),
        )
        # Override added.
        ct_text = (self.base / "[Content_Types].xml").read_text()
        self.assertIn("numbering.xml", ct_text)
        # Relationship added.
        rels_text = (rels_dir / "document.xml.rels").read_text()
        self.assertIn("numbering", rels_text)

    def test_offset_shift_collision_avoided(self) -> None:
        # Base has abstractNumIds {0,1,2} and numIds {1,2}; insert has
        # abstractNumIds {0,1} and numIds {1,2}.
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml(
                [("0", "BASE-A"), ("1", "BASE-B"), ("2", "BASE-C")],
                [("1", "0"), ("2", "1")],
            ),
        )
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml(
                [("0", "INS-A"), ("1", "INS-B")],
                [("1", "0"), ("2", "1")],
            ),
        )
        remap, anum_count, num_count = _merge_numbering(self.base, self.insert)
        # anum_offset = max(0,1,2)+1 = 3 → add to each insert ID:
        #   insert abstractNumId 0 → 0+3=3, 1 → 1+3=4.
        # num_offset = max(1,2)+1 = 3 → insert numIds (1,2) → (4,5).
        self.assertEqual(remap, {"1": "4", "2": "5"})
        self.assertEqual(anum_count, 2)
        self.assertEqual(num_count, 2)
        # Verify base now has abstractNumIds {0,1,2,3,4}.
        root = etree.parse(str(self.base / "word" / "numbering.xml")).getroot()
        all_anums = {
            a.get(f"{{{W_NS_T}}}abstractNumId")
            for a in root.findall(f"{{{W_NS_T}}}abstractNum")
        }
        self.assertEqual(all_anums, {"0", "1", "2", "3", "4"})

    def test_ecma_376_17_9_20_abstractnum_before_num_preserved(self) -> None:
        """ECMA-376 §17.9.20 regression-lock: every <w:abstractNum> MUST
        precede every <w:num>; <w:numIdMacAtCleanup> is the optional tail."""
        # Base: [abstractNum(0), abstractNum(1), num(1), num(2), cleanup]
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml(
                [("0", "BA"), ("1", "BB")],
                [("1", "0"), ("2", "1")],
                cleanup_value="5",
            ),
        )
        # Insert: [abstractNum(0), num(1)]
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "IA")], [("1", "0")]),
        )
        _merge_numbering(self.base, self.insert)
        # Re-parse base; walk in document order.
        root = etree.parse(str(self.base / "word" / "numbering.xml")).getroot()
        kinds = [etree.QName(c).localname for c in root]
        # All "abstractNum" must precede any "num"; cleanup is the tail.
        seen_num = False
        seen_cleanup = False
        for kind in kinds:
            if kind == "abstractNum":
                self.assertFalse(seen_num, "abstractNum after num — schema violation")
                self.assertFalse(seen_cleanup, "abstractNum after cleanup")
            elif kind == "num":
                seen_num = True
                self.assertFalse(seen_cleanup, "num after cleanup")
            elif kind == "numIdMacAtCleanup":
                seen_cleanup = True

    def test_abstractnum_with_malformed_id_skipped(self) -> None:
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml(
                [("ABC", "M-A"), ("0", "M-B")],   # ABC is invalid
                [],
            ),
        )
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([], []),
        )
        _, anum_count, _ = _merge_numbering(self.base, self.insert)
        # Only the valid abstractNum is inserted.
        self.assertEqual(anum_count, 1)

    def test_num_with_missing_abstractnum_child_skipped(self) -> None:
        # Build insert numbering with a <w:num> lacking <w:abstractNumId>.
        root = etree.Element(f"{{{W_NS_T}}}numbering", nsmap={"w": W_NS_T})
        a = etree.SubElement(root, f"{{{W_NS_T}}}abstractNum")
        a.set(f"{{{W_NS_T}}}abstractNumId", "0")
        n = etree.SubElement(root, f"{{{W_NS_T}}}num")
        n.set(f"{{{W_NS_T}}}numId", "1")
        # NO <w:abstractNumId> child.
        (self.insert / "word" / "numbering.xml").write_bytes(
            etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        )
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([], []),
        )
        remap, _, num_count = _merge_numbering(self.base, self.insert)
        # Skipped.
        self.assertEqual(num_count, 0)
        self.assertEqual(remap, {})

    def test_idempotent_when_called_twice_with_same_state(self) -> None:
        # Q-A3 weaker-invariant test: second call still produces an OOXML-valid
        # state (ECMA-376 §17.9.20 ordering preserved).
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "B")], [("1", "0")]),
        )
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "I")], [("1", "0")]),
        )
        _merge_numbering(self.base, self.insert)
        _merge_numbering(self.base, self.insert)
        # Verify ECMA ordering still holds after two passes.
        root = etree.parse(str(self.base / "word" / "numbering.xml")).getroot()
        seen_num = False
        for c in root:
            if etree.QName(c).localname == "num":
                seen_num = True
            elif etree.QName(c).localname == "abstractNum":
                self.assertFalse(seen_num, "ECMA order broken after 2 passes")


class TestRemapNumidInClones(unittest.TestCase):
    def test_rewrite_w_numId(self) -> None:
        clone = etree.fromstring(
            f'<w:p xmlns:w="{W_NS_T}">'
            f'<w:pPr><w:numPr><w:numId w:val="3"/></w:numPr></w:pPr>'
            f'</w:p>'.encode()
        )
        count = _remap_numid_in_clones([clone], {"3": "7"})
        self.assertEqual(count, 1)
        numid = clone.find(f".//{{{W_NS_T}}}numId")
        self.assertEqual(numid.get(f"{{{W_NS_T}}}val"), "7")

    def test_unmapped_numid_left_alone(self) -> None:
        clone = etree.fromstring(
            f'<w:p xmlns:w="{W_NS_T}">'
            f'<w:pPr><w:numPr><w:numId w:val="99"/></w:numPr></w:pPr>'
            f'</w:p>'.encode()
        )
        count = _remap_numid_in_clones([clone], {})
        self.assertEqual(count, 0)
        # Unchanged.
        numid = clone.find(f".//{{{W_NS_T}}}numId")
        self.assertEqual(numid.get(f"{{{W_NS_T}}}val"), "99")


class TestEnsureNumberingPart(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-ensure-"))
        (self.base / "word" / "_rels").mkdir(parents=True)
        (self.base / "[Content_Types].xml").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        )
        (self.base / "word" / "_rels" / "document.xml.rels").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)

    def test_adds_content_type_override_when_missing(self) -> None:
        _ensure_numbering_part(self.base)
        ct_root = etree.parse(str(self.base / "[Content_Types].xml")).getroot()
        ovrs = ct_root.findall(f"{{{CT_NS}}}Override")
        self.assertEqual(len(ovrs), 1)
        self.assertEqual(ovrs[0].get("PartName"), "/word/numbering.xml")
        # And a Relationship of numbering type.
        rels_root = etree.parse(
            str(self.base / "word" / "_rels" / "document.xml.rels")
        ).getroot()
        rels = rels_root.findall(f"{{{PR_NS}}}Relationship")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].get("Type"), f"{R_NS}/numbering")

    def test_idempotent(self) -> None:
        _ensure_numbering_part(self.base)
        _ensure_numbering_part(self.base)
        ct_root = etree.parse(str(self.base / "[Content_Types].xml")).getroot()
        self.assertEqual(len(ct_root.findall(f"{{{CT_NS}}}Override")), 1)
        rels_root = etree.parse(
            str(self.base / "word" / "_rels" / "document.xml.rels")
        ).getroot()
        self.assertEqual(
            len(rels_root.findall(f"{{{PR_NS}}}Relationship")), 1,
        )


# ---------------------------------------------------------------------------
# 008-07 — Idempotency regression-lock (Q-A3)
# ---------------------------------------------------------------------------

class TestRelocateAssetsIdempotent(unittest.TestCase):
    """Q-A3 regression-lock: calling relocator twice with fresh clones of
    the same insert against an evolving base produces an OOXML-valid state
    (ECMA-376 §17.9.20 ordering preserved). The relocator does NOT detect
    duplicates — second pass adds another offset layer; the test asserts
    the WEAKER invariant: schema validity after two passes."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-idem-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-idem-insert-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    def _build_fixture(self) -> None:
        # Minimal base: word/ + [Content_Types].xml + empty rels.
        (self.base / "word" / "_rels").mkdir(parents=True)
        (self.base / "[Content_Types].xml").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        )
        (self.base / "word" / "_rels" / "document.xml.rels").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )
        # Minimal insert with numbering.xml (1 abstractNum + 1 num).
        (self.insert / "word" / "_rels").mkdir(parents=True)
        (self.insert / "[Content_Types].xml").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        )
        (self.insert / "word" / "_rels" / "document.xml.rels").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "M")], [("1", "0")]),
        )

    def _fresh_clones(self) -> "list[etree._Element]":
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        # A single <w:p> referencing numId=1 (from insert's numbering).
        return [etree.fromstring(
            f'<w:p xmlns:w="{W}">'
            f'<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>'
            f'</w:p>'.encode()
        )]

    def test_relocator_idempotent_on_same_inputs(self) -> None:
        self._build_fixture()
        # Pass 1.
        report_1 = relocate_assets(self.insert, self.base, self._fresh_clones())
        self.assertGreaterEqual(report_1.num_added, 1)
        # Pass 2 (fresh clones; base now contains pass-1 artifacts).
        report_2 = relocate_assets(self.insert, self.base, self._fresh_clones())
        # The relocator adds another offset layer; semantically duplicates,
        # but base must remain OOXML-valid.
        num_path = self.base / "word" / "numbering.xml"
        if num_path.is_file():
            root = etree.parse(str(num_path)).getroot()
            seen_num = False
            for child in root:
                local = etree.QName(child).localname
                if local == "num":
                    seen_num = True
                elif local == "abstractNum":
                    self.assertFalse(
                        seen_num,
                        "ECMA-376 §17.9.20 ordering broken after 2 relocations",
                    )
        # report_2 should still report ≥ 1 abstractNum added (offset shift).
        self.assertGreaterEqual(report_2.abstractnum_added, 1)


class TestVddMultiHardening(unittest.TestCase):
    """Regression-locks for vdd-multi critic findings (iteration 1):
       - Logic C-2: F14 cleanup-only base case (ECMA-376 §17.9.20).
       - Logic H-4: F14 dangling abstractNum refs on partial-skip.
       - Logic H-2: F16 URL-decoded %2e%2e bypass.
       - Security H1: F10 reject symlinks + path-guard on src.name.
       - Security H2: F14 size cap on insert numbering.xml.
       - Security M2 / Perf H1: F14 roundtrip clone uses _SAFE_PARSER."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="docx-reloc-vdd-base-"))
        self.insert = Path(tempfile.mkdtemp(prefix="docx-reloc-vdd-insert-"))
        (self.base / "word").mkdir()
        (self.insert / "word").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.insert, ignore_errors=True)

    # ── Logic C-2: cleanup-only base case ───────────────────────────

    def test_cleanup_only_base_preserves_ordering(self) -> None:
        """C-2 regression-lock: when base has NO <w:num> but DOES have
        <w:numIdMacAtCleanup>, the abstractNums MUST be inserted BEFORE
        cleanup, not appended after it."""
        # Base: [abstractNum(0), abstractNum(1), numIdMacAtCleanup]
        # — no <w:num> at all.
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml(
                [("0", "BA"), ("1", "BB")],
                [],
                cleanup_value="7",
            ),
        )
        # Insert: [abstractNum(0), num(1)]
        (self.insert / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([("0", "IA")], [("1", "0")]),
        )
        _merge_numbering(self.base, self.insert)
        # Verify ECMA-376 §17.9.20 ordering: every abstractNum precedes
        # every num precedes numIdMacAtCleanup.
        root = etree.parse(str(self.base / "word" / "numbering.xml")).getroot()
        kinds = [etree.QName(c).localname for c in root]
        seen_num = False
        seen_cleanup = False
        for kind in kinds:
            if kind == "abstractNum":
                self.assertFalse(seen_num, "abstractNum after num (C-2)")
                self.assertFalse(seen_cleanup, "abstractNum after cleanup (C-2)")
            elif kind == "num":
                seen_num = True
                self.assertFalse(seen_cleanup, "num after cleanup")
            elif kind == "numIdMacAtCleanup":
                seen_cleanup = True

    # ── Logic H-4: dangling abstractNum refs ────────────────────────

    def test_num_pointing_at_skipped_abstractnum_is_dropped(self) -> None:
        """H-4 regression-lock: a <w:num> whose <w:abstractNumId w:val>
        points at a skipped (malformed-id) insert abstractNum MUST also
        be skipped — otherwise the resulting num references a
        non-existent abstractNum after offset-shift."""
        # Insert: abstractNum with malformed id "ABC" (skipped) +
        # valid abstractNum "0"; num(1) → abstractNumId="ABC" (dangling)
        # and num(2) → abstractNumId="0" (valid).
        root = etree.Element(f"{{{W_NS_T}}}numbering", nsmap={"w": W_NS_T})
        # Order matters in ECMA-376: abstractNum* must precede num*.
        a_abc = etree.SubElement(root, f"{{{W_NS_T}}}abstractNum")
        a_abc.set(f"{{{W_NS_T}}}abstractNumId", "ABC")
        a_zero = etree.SubElement(root, f"{{{W_NS_T}}}abstractNum")
        a_zero.set(f"{{{W_NS_T}}}abstractNumId", "0")
        n1 = etree.SubElement(root, f"{{{W_NS_T}}}num")
        n1.set(f"{{{W_NS_T}}}numId", "1")
        n1_aref = etree.SubElement(n1, f"{{{W_NS_T}}}abstractNumId")
        n1_aref.set(f"{{{W_NS_T}}}val", "ABC")  # dangling
        n2 = etree.SubElement(root, f"{{{W_NS_T}}}num")
        n2.set(f"{{{W_NS_T}}}numId", "2")
        n2_aref = etree.SubElement(n2, f"{{{W_NS_T}}}abstractNumId")
        n2_aref.set(f"{{{W_NS_T}}}val", "0")
        (self.insert / "word" / "numbering.xml").write_bytes(
            etree.tostring(
                root, xml_declaration=True,
                encoding="UTF-8", standalone=True,
            ),
        )
        (self.base / "word" / "numbering.xml").write_bytes(
            _make_numbering_xml([], []),
        )
        remap, anum_count, num_count = _merge_numbering(self.base, self.insert)
        # ABC abstractNum skipped → anum_count == 1.
        self.assertEqual(anum_count, 1)
        # num(1) (dangling) skipped → only num(2) survives.
        self.assertEqual(num_count, 1)
        self.assertNotIn("1", remap)
        self.assertIn("2", remap)

    # ── Logic H-2: URL-decoded %2e%2e bypass ────────────────────────

    def test_assert_safe_target_rejects_url_encoded_parent(self) -> None:
        """H-2: %2e%2e URL-encoded `..` MUST be rejected (Word URL-
        decodes rels Target per ECMA-376 Part 2 §9.2)."""
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("%2e%2e/etc/passwd", self.base)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")
        # Uppercase variant.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("%2E%2E/etc/passwd", self.base)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")
        # Embedded percent-encoded traversal.
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("media/%2e%2e/etc/passwd", self.base)
        self.assertEqual(ctx.exception.details["reason"], "parent_segment")

    def test_assert_safe_target_rejects_url_encoded_absolute(self) -> None:
        """H-2 sibling: %2f path-separator decoded to absolute path."""
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _assert_safe_target("%2fetc/passwd", self.base)
        self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")

    # ── Security H1: F10 symlink rejection ──────────────────────────

    def test_copy_extra_media_rejects_symlinks(self) -> None:
        """H1: F10 must skip symlink files (don't follow links into
        sensitive system files)."""
        media = self.insert / "word" / "media"
        media.mkdir()
        # Create a real file + a symlink that points outside the tree.
        outside = self.insert.parent / f"vdd-multi-outside-{self.insert.name}"
        try:
            outside.write_bytes(b"SENSITIVE")
            real = media / "real.png"
            real.write_bytes(b"OK")
            symlink_src = media / "evil.png"
            symlink_src.symlink_to(outside)
            result = _copy_extra_media(self.base, self.insert)
            # Symlink skipped; only real.png copied.
            self.assertEqual(result, {"media/real.png": "media/insert_real.png"})
            base_media = self.base / "word" / "media"
            self.assertTrue((base_media / "insert_real.png").is_file())
            self.assertFalse((base_media / "insert_evil.png").exists())
        finally:
            outside.unlink(missing_ok=True)

    # ── Security H2: F14 numbering.xml size cap ─────────────────────

    def test_merge_numbering_rejects_oversized_input(self) -> None:
        """H2: F14 must refuse to parse insert numbering.xml > 8 MiB
        to prevent OOM DoS."""
        big_path = self.insert / "word" / "numbering.xml"
        # Write a 9 MiB file (above the 8 MiB cap).
        big_path.write_bytes(b"<?xml version='1.0'?><x>" + b"A" * (9 * 1024 * 1024) + b"</x>")
        with self.assertRaises(Md2DocxOutputInvalid) as ctx:
            _merge_numbering(self.base, self.insert)
        self.assertEqual(
            ctx.exception.details["reason"], "numbering_size_cap",
        )


if __name__ == "__main__":
    unittest.main()
