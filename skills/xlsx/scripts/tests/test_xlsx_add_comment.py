"""Unit tests for `xlsx_add_comment.py` (xlsx-6) — v1 regression suite.

Organised by component (see class headers): cell-syntax parser,
sheet resolver, scanners, part-counter, person record, content-types
patcher, batch loader, merged-cell resolver, duplicate-cell matrix,
post-validate guard, same-path guard, honest-scope locks, golden-diff
mask. Every test is a real assertion — there are no `skipTest` stubs
in v1.

Run from inside the skill:
    cd skills/xlsx/scripts
    ./.venv/bin/python -m unittest discover -s tests

Test-name conventions (so `grep` can navigate):
    - `# M-N`   → architecture-review minor-N (e.g. M-1 = idmap-as-list).
    - `# m-N`   → architecture-review minor-N (lowercase variant).
    - `# mN`    → TASK round-1 minor-N (no hyphen) (e.g. m1 = casefold STRAẞE).
    - `# Rx`    → RTM row in `docs/TASK.md`.
    - `# R9.x`  → honest-scope clause (a..g) — locked by `TestHonestScope`.

Imports of `xlsx_add_comment` live inside test methods (not at module
level) so the file imports cleanly even when an in-development helper
has not yet landed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make `skills/xlsx/scripts/` importable so tests can `from xlsx_add_comment import ...`.
# Mirrors the path setup in `office/tests/test_xlsx_validator.py`.
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
# Also make the tests/ directory importable so `_golden_diff` is reachable.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _clean_input_path() -> Path:
    """Return the path to `tests/golden/inputs/clean.xlsx` (task 1.04 fixture)."""
    return _HERE / "golden" / "inputs" / "clean.xlsx"


def _write_synthetic_vml(
    tree_root: Path,
    name: str,
    *,
    idmap_data: str | None = None,
    shape_ids: list[str] | None = None,
) -> Path:
    """Build a minimal `xl/drawings/vmlDrawing*.xml` part for scanner tests.

    `idmap_data`: literal string for `<o:idmap data="...">` or `None` to
    omit the `<o:idmap>` element entirely.
    `shape_ids`: list of `<v:shape id="...">` values (e.g. `["_x0000_s1025"]`).
    """
    vml_dir = tree_root / "xl" / "drawings"
    vml_dir.mkdir(parents=True, exist_ok=True)
    parts = ['<o:shapelayout v:ext="edit">']
    if idmap_data is not None:
        parts.append(f'<o:idmap v:ext="edit" data="{idmap_data}"/>')
    parts.append('</o:shapelayout>')
    for sid in shape_ids or []:
        parts.append(f'<v:shape id="{sid}" o:spid="{sid}" type="#_x0000_t202"/>')
    body = "\n".join(parts)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel">\n'
        f'{body}\n'
        '</xml>'
    )
    path = vml_dir / name
    path.write_text(xml, encoding="utf-8")
    return path


class TestCellSyntaxParser(unittest.TestCase):
    """F2 — `parse_cell_syntax` + `resolve_sheet`. Implemented in task 2.02."""

    # --- parse_cell_syntax (pure, no I/O) ---

    def test_simple_a1(self):
        from xlsx_add_comment import parse_cell_syntax
        self.assertEqual(parse_cell_syntax("A5"), (None, "A5"))

    def test_qualified_sheet(self):
        from xlsx_add_comment import parse_cell_syntax
        self.assertEqual(parse_cell_syntax("Sheet2!B5"), ("Sheet2", "B5"))

    def test_quoted_sheet_with_space(self):
        from xlsx_add_comment import parse_cell_syntax
        self.assertEqual(parse_cell_syntax("'Q1 2026'!A1"), ("Q1 2026", "A1"))

    def test_apostrophe_escape(self):
        from xlsx_add_comment import parse_cell_syntax
        # `''` inside a quoted sheet name → literal `'`.
        self.assertEqual(
            parse_cell_syntax("'Bob''s Sheet'!A1"),
            ("Bob's Sheet", "A1"),
        )

    def test_invalid_cell_ref(self):
        from xlsx_add_comment import parse_cell_syntax, InvalidCellRef
        # No digits → not A1-shape.
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("ZZ")

    def test_invalid_cell_ref_empty_input(self):  # MIN-1 coverage
        from xlsx_add_comment import parse_cell_syntax, InvalidCellRef
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("")
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("   ")

    def test_invalid_cell_ref_unterminated_quote(self):  # MIN-1 coverage
        from xlsx_add_comment import parse_cell_syntax, InvalidCellRef
        # Opening `'` without a closing `'` before end-of-string.
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("'Sheet1!A5")

    def test_invalid_cell_ref_quoted_no_bang(self):  # MIN-1 coverage
        from xlsx_add_comment import parse_cell_syntax, InvalidCellRef
        # Closing `'` not followed by `!`.
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("'Sheet1'A5")

    def test_invalid_cell_ref_empty_sheet_name(self):  # MAJ-1 lock
        from xlsx_add_comment import parse_cell_syntax, InvalidCellRef
        # Empty quoted sheet name `''!A1` and empty unquoted `!A5` —
        # both must fail at parse, not at sheet-resolve.
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("''!A1")
        with self.assertRaises(InvalidCellRef):
            parse_cell_syntax("!A5")

    # --- resolve_sheet (uses parsed sheet metadata) ---

    def test_unknown_sheet_includes_available(self):
        from xlsx_add_comment import resolve_sheet, SheetNotFound
        sheets = [
            {"name": "Sheet1", "state": "visible"},
            {"name": "Sheet2", "state": "visible"},
        ]
        with self.assertRaises(SheetNotFound) as cm:
            resolve_sheet("GhostSheet", sheets)
        self.assertEqual(cm.exception.available, ["Sheet1", "Sheet2"])
        # No case-insensitive match → no suggestion.
        self.assertIsNone(cm.exception.suggestion)

    def test_case_mismatch_includes_suggestion(self):  # M3
        from xlsx_add_comment import resolve_sheet, SheetNotFound
        sheets = [{"name": "Sheet2", "state": "visible"}]
        with self.assertRaises(SheetNotFound) as cm:
            resolve_sheet("sheet2", sheets)  # lowercase mismatch
        self.assertEqual(cm.exception.suggestion, "Sheet2")

    def test_first_visible_skips_hidden(self):  # M2
        from xlsx_add_comment import resolve_sheet
        sheets = [
            {"name": "Sheet1", "state": "hidden"},
            {"name": "Sheet2", "state": "visible"},
        ]
        # qualified=None → default-sheet rule → first VISIBLE = Sheet2.
        self.assertEqual(resolve_sheet(None, sheets), "Sheet2")

    def test_no_visible_sheet_envelope(self):  # M2
        from xlsx_add_comment import resolve_sheet, NoVisibleSheet
        sheets = [
            {"name": "S1", "state": "hidden"},
            {"name": "S2", "state": "veryHidden"},
        ]
        with self.assertRaises(NoVisibleSheet):
            resolve_sheet(None, sheets)

    def test_explicit_hidden_qualifier_warns_to_stderr(self):  # MAJ-3 lock
        """When the user explicitly qualifies a hidden sheet, `resolve_sheet`
        proceeds but emits a stderr info note. Locks the AC line:
        'Hidden-sheet stderr info note appears when the user explicitly
        qualifies a hidden sheet (--cell Hidden!A1)'."""
        import io
        from contextlib import redirect_stderr

        from xlsx_add_comment import resolve_sheet
        sheets = [
            {"name": "Hidden", "state": "hidden"},
            {"name": "Visible", "state": "visible"},
        ]
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = resolve_sheet("Hidden", sheets)
        self.assertEqual(result, "Hidden")
        stderr_text = buf.getvalue()
        self.assertIn("Hidden", stderr_text)
        self.assertIn("hidden", stderr_text.lower())
        # Negative: a visible-sheet qualifier should NOT emit any note.
        buf2 = io.StringIO()
        with redirect_stderr(buf2):
            resolve_sheet("Visible", sheets)
        self.assertEqual(buf2.getvalue(), "")


class TestPartCounter(unittest.TestCase):
    """F4 — `next_part_counter`. Implemented in task 2.03."""

    def test_counter_starts_at_1_when_empty(self):
        import tempfile
        from xlsx_add_comment import next_part_counter
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                next_part_counter(Path(td), "xl/comments*.xml"), 1
            )

    def test_counter_independent_for_comments_and_vml(self):
        import tempfile
        from xlsx_add_comment import next_part_counter
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            # Pre-existing comments1.xml AND vmlDrawing1.xml — counters
            # are independent globs, not a shared shared-counter table.
            (tree / "xl").mkdir()
            (tree / "xl" / "comments1.xml").write_text("<comments/>")
            (tree / "xl" / "drawings").mkdir()
            (tree / "xl" / "drawings" / "vmlDrawing1.xml").write_text("<xml/>")
            self.assertEqual(next_part_counter(tree, "xl/comments*.xml"), 2)
            self.assertEqual(
                next_part_counter(tree, "xl/drawings/vmlDrawing*.xml"), 2
            )

    def test_counter_uses_max_plus_1(self):
        import tempfile
        from xlsx_add_comment import next_part_counter
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            (tree / "xl").mkdir()
            (tree / "xl" / "comments1.xml").write_text("<comments/>")
            (tree / "xl" / "comments3.xml").write_text("<comments/>")
            # Gap at 2 → next is max+1 = 4 (NOT gap-fill 2; rels-target
            # ambiguity prevention on round-trip).
            self.assertEqual(next_part_counter(tree, "xl/comments*.xml"), 4)


class TestIdmapScanner(unittest.TestCase):  # M-1: idmap data is a LIST, not a scalar
    """F4 — `scan_idmap_used`. Implemented in task 2.03 with M-1 list-aware parser."""

    def test_scalar_data_attr(self):
        import tempfile
        from xlsx_add_comment import scan_idmap_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data="5")
            self.assertEqual(scan_idmap_used(tree), {5})

    def test_list_data_attr_returns_all_integers(self):  # M-1 LOCK
        """data='1,5,9' → {1,5,9}. The architecture-review M-1 fix:
        a naive scalar parse would corrupt heavily-edited workbooks
        where Excel emitted multi-claim lists."""
        import tempfile
        from xlsx_add_comment import scan_idmap_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data="1,5,9")
            self.assertEqual(scan_idmap_used(tree), {1, 5, 9})

    def test_workbook_wide_union(self):
        import tempfile
        from xlsx_add_comment import scan_idmap_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data="1,3")
            _write_synthetic_vml(tree, "vmlDrawing2.xml", idmap_data="2")
            self.assertEqual(scan_idmap_used(tree), {1, 2, 3})

    def test_empty_data_attr_contributes_nothing(self):  # spec edge case
        import tempfile
        from xlsx_add_comment import scan_idmap_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data="")
            self.assertEqual(scan_idmap_used(tree), set())

    def test_missing_idmap_element_contributes_nothing(self):  # spec edge case
        import tempfile
        from xlsx_add_comment import scan_idmap_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            # idmap_data=None omits the <o:idmap> element entirely.
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data=None)
            self.assertEqual(scan_idmap_used(tree), set())

    def test_malformed_integer_raises(self):  # MalformedVml lock
        """Non-integer token in <o:idmap data> → MalformedVml (exit 1)."""
        import tempfile
        from xlsx_add_comment import scan_idmap_used, MalformedVml
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml", idmap_data="1,abc,3")
            with self.assertRaises(MalformedVml):
                scan_idmap_used(tree)

    def test_broken_xml_raises_malformed_vml(self):  # LOW coverage gap fix
        """Truncated/garbage XML in vmlDrawing*.xml → MalformedVml.
        Locks the second `_parse_vml` raise site (XMLSyntaxError path)
        so the entity-hardened `_VML_PARSER` can't silently regress."""
        import tempfile
        from xlsx_add_comment import scan_idmap_used, scan_spid_used, MalformedVml
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            (tree / "xl" / "drawings").mkdir(parents=True)
            (tree / "xl" / "drawings" / "vmlDrawing1.xml").write_bytes(
                b"<not-xml without closing"
            )
            with self.assertRaises(MalformedVml):
                scan_idmap_used(tree)
            with self.assertRaises(MalformedVml):
                scan_spid_used(tree)


class TestSpidScanner(unittest.TestCase):  # C1: distinct collision domain from idmap
    """F4 — `scan_spid_used`. Implemented in task 2.03."""

    def test_scans_all_vml_parts(self):
        import tempfile
        from xlsx_add_comment import scan_spid_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml",
                                 shape_ids=["_x0000_s1025"])
            _write_synthetic_vml(tree, "vmlDrawing2.xml",
                                 shape_ids=["_x0000_s1026"])
            self.assertEqual(scan_spid_used(tree), {1025, 1026})

    def test_returns_max_plus_1_baseline(self):
        import tempfile
        from xlsx_add_comment import scan_spid_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(tree, "vmlDrawing1.xml",
                                 shape_ids=["_x0000_s1025", "_x0000_s1026"])
            used = scan_spid_used(tree)
            # Allocator pattern: max+1 (m-1 chosen rule, NOT 1024-stride).
            self.assertEqual(max(used) + 1, 1027)

    def test_non_conforming_shape_ids_skipped(self):  # spec edge case
        """Excel sometimes emits non-_x0000_s shape ids for legacy AutoShapes;
        scan_spid_used skips them rather than crashing."""
        import tempfile
        from xlsx_add_comment import scan_spid_used
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)
            _write_synthetic_vml(
                tree, "vmlDrawing1.xml",
                shape_ids=["_x0000_s1025", "AutoShape42", "_x0000_s1026"],
            )
            self.assertEqual(scan_spid_used(tree), {1025, 1026})


class TestPersonRecord(unittest.TestCase):
    """F4 — `add_person`. Implemented in task 2.05."""

    def _empty_person_list(self):
        from lxml import etree
        from xlsx_add_comment import THREADED_NS
        return etree.Element(
            f"{{{THREADED_NS}}}personList", nsmap={None: THREADED_NS},
        )

    def test_uuidv5_stable_on_displayName(self):
        """`add_person("Alice")` returns the SAME id across calls AND
        equals `{UUIDv5(NAMESPACE_URL, "Alice")}` upper-cased + braced."""
        import uuid as uuid_mod
        from xlsx_add_comment import add_person, THREADED_NS
        from lxml import etree
        root = self._empty_person_list()
        id_first = add_person(root, "Alice")
        id_second = add_person(root, "Alice")
        self.assertEqual(id_first, id_second, "dedup must reuse id")
        # Only one <person> element after two calls.
        persons = root.findall(f"{{{THREADED_NS}}}person")
        self.assertEqual(len(persons), 1)
        # Stability: matches the deterministic UUIDv5 derivation.
        expected = "{" + str(uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "Alice")).upper() + "}"
        self.assertEqual(id_first, expected)

    def test_providerId_literal_None_string(self):
        """`providerId` attribute is the literal 3-char string "None",
        NOT Python's None object (would be missing-attribute via lxml)."""
        from xlsx_add_comment import add_person, THREADED_NS
        root = self._empty_person_list()
        add_person(root, "Q")
        person = root.find(f"{{{THREADED_NS}}}person")
        self.assertEqual(person.get("providerId"), "None")
        # Sanity: attribute is present, not None.
        self.assertIsNotNone(person.get("providerId"))

    def test_userId_casefold_strasse(self):  # m1 — non-ASCII via casefold()
        """German `STRAẞE` → `casefold()` → `strasse` (ß → ss). `.lower()`
        on the same string would produce `straße` which trips downstream
        consumers that ASCII-fold userIds."""
        from xlsx_add_comment import add_person, THREADED_NS
        root = self._empty_person_list()
        add_person(root, "STRAẞE")
        person = root.find(f"{{{THREADED_NS}}}person")
        self.assertEqual(person.get("userId"), "strasse")

    def test_dedup_case_sensitive_displayName(self):  # m5
        """`Alice` and `alice` produce TWO distinct `<person>` records
        (case-sensitive on `displayName`). Mirrors `<authors>` dedup
        in legacy comments (task 2.04 m5 lock)."""
        from xlsx_add_comment import add_person, THREADED_NS
        root = self._empty_person_list()
        id1 = add_person(root, "Alice")
        id2 = add_person(root, "alice")
        self.assertNotEqual(id1, id2)
        persons = root.findall(f"{{{THREADED_NS}}}person")
        self.assertEqual(len(persons), 2)
        self.assertEqual(
            sorted(p.get("displayName") for p in persons),
            ["Alice", "alice"],
        )


class TestAuthorsDedup(unittest.TestCase):
    """F4 — `<authors>` dedup logic inside `add_legacy_comment`. Task 2.04."""

    def _empty_comments(self):
        from lxml import etree
        from xlsx_add_comment import SS_NS
        root = etree.Element(f"{{{SS_NS}}}comments", nsmap={None: SS_NS})
        etree.SubElement(root, f"{{{SS_NS}}}authors")
        etree.SubElement(root, f"{{{SS_NS}}}commentList")
        return root

    def test_case_sensitive_identity(self):  # m5
        from lxml import etree
        from xlsx_add_comment import add_legacy_comment, SS_NS
        root = self._empty_comments()
        # Insert "Alice" twice — second call must reuse authorId 0 (no dup).
        a1 = add_legacy_comment(root, "A1", "Alice", "first")
        a2 = add_legacy_comment(root, "A2", "Alice", "second")
        self.assertEqual(a1, 0)
        self.assertEqual(a2, 0)
        # Insert "alice" (lowercase) — case-sensitive ≠ "Alice", new authorId 1.
        a3 = add_legacy_comment(root, "A3", "alice", "third")
        self.assertEqual(a3, 1)
        authors = root.findall(f"{{{SS_NS}}}authors/{{{SS_NS}}}author")
        self.assertEqual([a.text for a in authors], ["Alice", "alice"])


class TestVmlAnchor(unittest.TestCase):
    """F4 — `add_vml_shape` emits the locked default Excel anchor (R9.c)."""

    def test_default_anchor_offsets(self):
        from lxml import etree
        from xlsx_add_comment import (
            add_vml_shape, DEFAULT_VML_ANCHOR, V_NS, X_NS,
        )
        root = etree.Element("xml")
        add_vml_shape(root, "A5", spid=1025)
        shape = root.find(f"{{{V_NS}}}shape")
        self.assertIsNotNone(shape)
        anchor = shape.find(f"{{{X_NS}}}ClientData/{{{X_NS}}}Anchor")
        self.assertIsNotNone(anchor)
        # R9.c lock: exact match against the Excel default offset list.
        self.assertEqual(anchor.text, DEFAULT_VML_ANCHOR)

    def test_row_col_zero_based(self):
        from lxml import etree
        from xlsx_add_comment import add_vml_shape, V_NS, X_NS
        root = etree.Element("xml")
        # A5 → col=0, row=4 (1-based A1 → 0-based VML).
        add_vml_shape(root, "A5", spid=1025)
        shape = root.find(f"{{{V_NS}}}shape")
        cd = shape.find(f"{{{X_NS}}}ClientData")
        self.assertEqual(cd.find(f"{{{X_NS}}}Row").text, "4")
        self.assertEqual(cd.find(f"{{{X_NS}}}Column").text, "0")
        # AB10 → col=27 (A=0..Z=25, AA=26, AB=27), row=9.
        root2 = etree.Element("xml")
        add_vml_shape(root2, "AB10", spid=1026)
        shape2 = root2.find(f"{{{V_NS}}}shape")
        cd2 = shape2.find(f"{{{X_NS}}}ClientData")
        self.assertEqual(cd2.find(f"{{{X_NS}}}Row").text, "9")
        self.assertEqual(cd2.find(f"{{{X_NS}}}Column").text, "27")

    def test_spid_id_format(self):
        from lxml import etree
        from xlsx_add_comment import add_vml_shape, V_NS, O_NS
        root = etree.Element("xml")
        add_vml_shape(root, "A1", spid=1042)
        shape = root.find(f"{{{V_NS}}}shape")
        # `id` and `o:spid` both follow the Excel `_x0000_sNNNN` pattern.
        self.assertEqual(shape.get("id"), "_x0000_s1042")
        self.assertEqual(shape.get(f"{{{O_NS}}}spid"), "_x0000_s1042")
        self.assertEqual(shape.get("type"), "#_x0000_t202")


class TestRelsHelpers(unittest.TestCase):
    """F4 — rels-related helpers (Sarcasmotron MIN-3 / MIN-5 coverage)."""

    def test_make_relative_target_uses_forward_slash(self):  # MAJ-1 lock
        """OPC mandates `/` in Target= regardless of OS. Lock against
        os.path.relpath returning the platform-native separator."""
        from xlsx_add_comment import _make_relative_target
        rels_path = Path("xl/worksheets/_rels/sheet1.xml.rels")
        target = Path("xl/comments1.xml")
        result = _make_relative_target(rels_path, target)
        self.assertEqual(result, "../comments1.xml")
        self.assertNotIn("\\", result, "Target= must NEVER contain backslash")

    def test_allocate_rid_skips_non_conforming_ids(self):  # MIN-3 lock
        """openpyxl-style `<Relationship Id="comments">` (literal id, not
        rId<N>) must NOT confuse the allocator — skipped, allocator
        stays in the rId<N> namespace."""
        from lxml import etree
        from xlsx_add_comment import _allocate_rid, PR_NS
        root = etree.Element(f"{{{PR_NS}}}Relationships", nsmap={None: PR_NS})
        etree.SubElement(
            root, f"{{{PR_NS}}}Relationship",
            Id="comments", Type="...", Target="../comments/comment1.xml",
        )
        etree.SubElement(
            root, f"{{{PR_NS}}}Relationship",
            Id="anysvml", Type="...", Target="../drawings/commentsDrawing1.vml",
        )
        # Both ids non-conforming → next allocation starts at rId1.
        self.assertEqual(_allocate_rid(root), "rId1")
        # Mix of conforming + non-conforming → max(N) + 1 over conforming only.
        etree.SubElement(
            root, f"{{{PR_NS}}}Relationship",
            Id="rId3", Type="...", Target="x.xml",
        )
        self.assertEqual(_allocate_rid(root), "rId4")


class TestContentTypesOverride(unittest.TestCase):
    """F4 — `_patch_content_types` idempotency + m-3 default-extension rule."""

    def _empty_ct(self):
        from lxml import etree
        from xlsx_add_comment import CT_NS
        return etree.Element(f"{{{CT_NS}}}Types", nsmap={None: CT_NS})

    def test_idempotent_skip(self):
        from xlsx_add_comment import _patch_content_types, CT_NS
        ct = self._empty_ct()
        _patch_content_types(ct, "/xl/comments1.xml", "application/test")
        _patch_content_types(ct, "/xl/comments1.xml", "application/test")
        # Two identical patches → only one Override.
        overrides = ct.findall(f"{{{CT_NS}}}Override")
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0].get("PartName"), "/xl/comments1.xml")

    def test_default_extension_skips_per_part_override(self):  # m-3
        """If <Default Extension="vml"> is already declared with the
        matching ContentType, do NOT add a redundant per-part Override."""
        from lxml import etree
        from xlsx_add_comment import _patch_content_types, VML_CT, CT_NS
        ct = self._empty_ct()
        # Pre-existing <Default Extension="vml" ContentType=VML_CT/>
        etree.SubElement(
            ct, f"{{{CT_NS}}}Default",
            Extension="vml", ContentType=VML_CT,
        )
        _patch_content_types(
            ct, "/xl/drawings/vmlDrawing1.xml", VML_CT,
            default_extension="vml",
        )
        overrides = ct.findall(f"{{{CT_NS}}}Override")
        # m-3: NO per-part Override because Default already covers it.
        self.assertEqual(len(overrides), 0)

    def test_default_extension_mismatch_still_adds_override(self):
        """If Default Extension is declared but ContentType DIFFERS,
        the per-part Override is still added (no false-skip)."""
        from lxml import etree
        from xlsx_add_comment import _patch_content_types, VML_CT, CT_NS
        ct = self._empty_ct()
        etree.SubElement(
            ct, f"{{{CT_NS}}}Default",
            Extension="vml", ContentType="application/different",
        )
        _patch_content_types(
            ct, "/xl/drawings/vmlDrawing1.xml", VML_CT,
            default_extension="vml",
        )
        overrides = ct.findall(f"{{{CT_NS}}}Override")
        self.assertEqual(len(overrides), 1)


class TestBatchLoader(unittest.TestCase):
    """F3 — `load_batch`. Implemented in task 2.06.

    The 8 MiB pre-parse cap is enforced at the boundary between the
    file-stat / stdin-read step and `json.loads` — verified in
    `test_size_cap_pre_parse` without actually allocating > 8 MiB.
    """

    def _write(self, body: str) -> str:
        import tempfile
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        )
        f.write(body)
        f.close()
        return f.name

    def test_flat_array_shape(self):
        from xlsx_add_comment import load_batch
        path = self._write(
            '[{"cell":"A2","author":"Bob","text":"n1"},'
            ' {"cell":"B3","author":"Alice","text":"n2","initials":"AL"},'
            ' {"cell":"C4","author":"Bob","text":"n3","threaded":true}]'
        )
        rows, skipped = load_batch(path, default_author=None, default_threaded=False)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].cell, "A2")
        self.assertEqual(rows[0].author, "Bob")
        self.assertIsNone(rows[0].initials)
        self.assertFalse(rows[0].threaded)
        self.assertEqual(rows[1].initials, "AL")
        self.assertTrue(rows[2].threaded)

    def test_envelope_shape(self):
        from xlsx_add_comment import load_batch
        path = self._write(
            '{"ok":false, "summary":{"errors":2,"warnings":0,"findings":2},'
            ' "findings":['
            '   {"cell":"A2","row":2,"col":"A","message":"e1"},'
            '   {"cell":"B3","row":3,"col":"B","message":"e2"}'
            ' ]}'
        )
        rows, skipped = load_batch(
            path, default_author="Validator Bot", default_threaded=True,
        )
        self.assertEqual(skipped, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].cell, "A2")
        self.assertEqual(rows[0].text, "e1")  # mapped from .message
        self.assertEqual(rows[0].author, "Validator Bot")
        # I2.2: initials derived from --default-author (first letter of each token).
        self.assertEqual(rows[0].initials, "VB")
        self.assertTrue(rows[0].threaded)

    def test_envelope_missing_findings_key(self):
        from xlsx_add_comment import load_batch, InvalidBatchInput
        path = self._write('{"foo":1, "bar":2}')
        with self.assertRaises(InvalidBatchInput):
            load_batch(path, default_author="V", default_threaded=False)

    def test_envelope_skips_group_findings_with_row_null(self):
        from xlsx_add_comment import load_batch
        path = self._write(
            '{"ok":false, "summary":{"errors":1,"warnings":0,"findings":3},'
            ' "findings":['
            '   {"cell":"A2","row":2,"message":"real"},'
            '   {"cell":null,"row":null,"message":"group"},'
            '   {"cell":"B5","row":5,"message":"real2"}'
            ' ]}'
        )
        rows, skipped = load_batch(
            path, default_author="V", default_threaded=False,
        )
        self.assertEqual(skipped, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].cell, "A2")
        self.assertEqual(rows[1].cell, "B5")

    def test_size_cap_pre_parse(self):  # m2 / m-4 — 8 MiB cap boundary
        from xlsx_add_comment import load_batch, BatchTooLarge
        # Don't actually write 8 MiB to disk: monkey-patch Path.stat to
        # return an oversized st_size. load_batch must reject BEFORE
        # touching the file's bytes (m-4 pre-parse semantic).
        import os
        from pathlib import Path
        path = self._write("[]")
        try:
            real_stat = Path.stat
            def fake_stat(self_arg):
                st = real_stat(self_arg)
                # Emulate a 9 MiB file via os.stat_result tuple replacement.
                fields = list(st)
                fields[6] = 9 * 1024 * 1024  # st_size
                return os.stat_result(tuple(fields))
            Path.stat = fake_stat
            with self.assertRaises(BatchTooLarge) as cm:
                load_batch(path, default_author=None, default_threaded=False)
            self.assertEqual(cm.exception.size_bytes, 9 * 1024 * 1024)
        finally:
            Path.stat = real_stat


class TestMergedResolver(unittest.TestCase):
    """F5 — `resolve_merged_target` (task 2.07). Sheet-local merge resolution."""

    def _sheet_with_merge(self, range_ref: str):
        from lxml import etree
        from xlsx_add_comment import SS_NS
        worksheet = etree.Element(f"{{{SS_NS}}}worksheet", nsmap={None: SS_NS})
        merges = etree.SubElement(worksheet, f"{{{SS_NS}}}mergeCells")
        etree.SubElement(merges, f"{{{SS_NS}}}mergeCell", ref=range_ref)
        return worksheet

    def test_anchor_passes_through(self):
        from xlsx_add_comment import resolve_merged_target
        root = self._sheet_with_merge("A1:C3")
        # R6.c: anchor cell of a merged range passes through unchanged.
        self.assertEqual(resolve_merged_target(root, "A1", False), "A1")
        self.assertEqual(resolve_merged_target(root, "A1", True), "A1")

    def test_non_anchor_raises_default(self):
        from xlsx_add_comment import resolve_merged_target, MergedCellTarget
        root = self._sheet_with_merge("A1:C3")
        with self.assertRaises(MergedCellTarget) as cm:
            resolve_merged_target(root, "B2", False)
        self.assertEqual(cm.exception.target, "B2")
        self.assertEqual(cm.exception.anchor, "A1")
        self.assertEqual(cm.exception.range_ref, "A1:C3")

    def test_non_anchor_redirects_with_flag(self):
        from xlsx_add_comment import resolve_merged_target
        root = self._sheet_with_merge("A1:C3")
        # R6.b: --allow-merged-target rewrites to anchor.
        self.assertEqual(resolve_merged_target(root, "B2", True), "A1")
        self.assertEqual(resolve_merged_target(root, "C3", True), "A1")

    def test_outside_any_range_passes_through(self):
        from xlsx_add_comment import resolve_merged_target
        root = self._sheet_with_merge("A1:C3")
        # Cells outside merged ranges are unchanged regardless of flag.
        self.assertEqual(resolve_merged_target(root, "D5", False), "D5")
        self.assertEqual(resolve_merged_target(root, "D5", True), "D5")


class TestDuplicateMatrix(unittest.TestCase):
    """ARCH §6.1 duplicate-cell matrix (task 2.07 / M-2 lock).

    Drives `_enforce_duplicate_matrix` directly with synthesised state
    dicts so the test does not depend on a fixture ordering.
    """

    def test_legacy_only_no_threaded_raises(self):
        from xlsx_add_comment import (
            _enforce_duplicate_matrix, DuplicateLegacyComment,
        )
        state = {"has_legacy": True, "has_threaded": False, "thread_size": 0}
        with self.assertRaises(DuplicateLegacyComment) as cm:
            _enforce_duplicate_matrix(
                state, threaded_mode=False, sheet_name="Sheet1", ref="A5",
            )
        self.assertEqual(cm.exception.cell, "A5")
        self.assertEqual(cm.exception.sheet, "Sheet1")

    def test_legacy_only_threaded_passes(self):
        # Legacy-only + --threaded → no raise (Q7 fidelity dual-write).
        from xlsx_add_comment import _enforce_duplicate_matrix
        state = {"has_legacy": True, "has_threaded": False, "thread_size": 0}
        _enforce_duplicate_matrix(
            state, threaded_mode=True, sheet_name="Sheet1", ref="A5",
        )  # no exception

    def test_threaded_exists_no_threaded_raises(self):
        from xlsx_add_comment import (
            _enforce_duplicate_matrix, DuplicateThreadedComment,
        )
        state = {"has_legacy": True, "has_threaded": True, "thread_size": 2}
        with self.assertRaises(DuplicateThreadedComment) as cm:
            _enforce_duplicate_matrix(
                state, threaded_mode=False, sheet_name="Sheet1", ref="A5",
            )
        self.assertEqual(cm.exception.existing_thread_size, 2)
        self.assertEqual(cm.exception.cell, "A5")

    def test_threaded_exists_threaded_passes(self):
        from xlsx_add_comment import _enforce_duplicate_matrix
        state = {"has_legacy": False, "has_threaded": True, "thread_size": 1}
        _enforce_duplicate_matrix(
            state, threaded_mode=True, sheet_name="Sheet1", ref="A5",
        )  # no exception — appends to thread

    def test_empty_cell_passes(self):
        from xlsx_add_comment import _enforce_duplicate_matrix
        state = {"has_legacy": False, "has_threaded": False, "thread_size": 0}
        _enforce_duplicate_matrix(
            state, threaded_mode=False, sheet_name="Sheet1", ref="A5",
        )
        _enforce_duplicate_matrix(
            state, threaded_mode=True, sheet_name="Sheet1", ref="A5",
        )


class TestPostValidateGuard(unittest.TestCase):
    """R8 / 2.08 — opt-in post-pack `_post_pack_validate` guard.

    Behaviour: env var `XLSX_ADD_COMMENT_POST_VALIDATE=1` triggers a
    subprocess call to office/validate.py after pack(); unset → no call.
    """

    def _run_with_env(self, env_value, mock_validate):
        # Sarcasmotron MIN-4 lock: don't `clear=True` os.environ — that
        # wipes PATH/HOME/LANG/TMPDIR and makes the test fragile against
        # any code path that consults them. Just override the one var.
        import os, shutil, tempfile
        from pathlib import Path
        from unittest import mock
        from xlsx_add_comment import main
        overrides = {}
        if env_value is None:
            # Use empty string → `_post_validate_enabled()` reads it as off.
            overrides["XLSX_ADD_COMMENT_POST_VALIDATE"] = ""
        else:
            overrides["XLSX_ADD_COMMENT_POST_VALIDATE"] = env_value
        with mock.patch.dict(os.environ, overrides, clear=False), \
             mock.patch("xlsx_add_comment._post_pack_validate", mock_validate):
            with tempfile.TemporaryDirectory() as td:
                src = Path(td) / "in.xlsx"
                shutil.copy(_clean_input_path(), src)
                out = Path(td) / "out.xlsx"
                rc = main([str(src), str(out), "--cell", "A5",
                           "--author", "Q", "--text", "msg"])
        return rc, out

    def test_env_var_off_skips_validation(self):
        from unittest import mock
        m = mock.MagicMock()
        rc, out = self._run_with_env(None, m)
        self.assertEqual(rc, 0)
        m.assert_not_called()

    def test_env_var_on_runs_validation(self):
        from unittest import mock
        m = mock.MagicMock()
        rc, out = self._run_with_env("1", m)
        self.assertEqual(rc, 0)
        m.assert_called_once_with(out)

    def test_truthy_zero_treated_as_off(self):
        # MIN-1 lock: "0" / "false" / "no" must NOT enable the guard.
        from unittest import mock
        for falsy in ("0", "false", "no", "off", "FALSE", "  "):
            with self.subTest(value=falsy):
                m = mock.MagicMock()
                rc, _ = self._run_with_env(falsy, m)
                self.assertEqual(rc, 0)
                m.assert_not_called()

    def test_truthy_alternates_treated_as_on(self):
        # MIN-1 lock: 1/true/yes/on (case-insensitive) all enable.
        from unittest import mock
        for truthy in ("1", "true", "yes", "on", "TRUE", "Yes"):
            with self.subTest(value=truthy):
                m = mock.MagicMock()
                rc, _ = self._run_with_env(truthy, m)
                self.assertEqual(rc, 0)
                m.assert_called_once()

    def test_xlsm_unknown_extension_treated_as_no_op(self):
        # MAJ-1 lock: validate.py exits 2 on .xlsm "Unknown extension";
        # the guard must skip cleanly + emit a stderr note (NOT raise).
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from unittest import mock
        from xlsx_add_comment import _post_pack_validate
        fake_result = mock.MagicMock(
            returncode=2, stdout="", stderr="Unknown extension: .xlsm",
        )
        capture = io.StringIO()
        with mock.patch("xlsx_add_comment._subprocess.run",
                        return_value=fake_result), redirect_stderr(capture):
            _post_pack_validate(Path("/tmp/whatever.xlsm"))
        self.assertIn("post-pack validate skipped", capture.getvalue())
        self.assertIn(".xlsm", capture.getvalue())

    def test_real_failure_unlinks_output(self):
        # MAJ-3 lock: a genuine validation failure must unlink the output
        # so a downstream consumer cannot pick up a half-broken artefact.
        import shutil, tempfile
        from pathlib import Path
        from unittest import mock
        from xlsx_add_comment import _post_pack_validate, OutputIntegrityFailure
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.xlsx"
            shutil.copy(_clean_input_path(), out)
            self.assertTrue(out.is_file())
            fake_result = mock.MagicMock(
                returncode=1, stdout="malformed Override", stderr="",
            )
            with mock.patch("xlsx_add_comment._subprocess.run",
                            return_value=fake_result):
                with self.assertRaises(OutputIntegrityFailure):
                    _post_pack_validate(out)
            self.assertFalse(out.is_file(),
                             "output must be unlinked after validation failure")


class TestSamePathGuard(unittest.TestCase):
    """`_assert_distinct_paths` (cross-7 H1). Implemented in task 2.01."""

    def test_identical_path_exits_6(self):
        import shutil
        import tempfile
        from pathlib import Path

        from xlsx_add_comment import main

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.xlsx"
            shutil.copy(_clean_input_path(), src)
            rc = main([str(src), str(src), "--cell", "A5",
                       "--author", "Q", "--text", "msg"])
            self.assertEqual(rc, 6, "same-path INPUT==OUTPUT must exit 6")

    def test_symlink_resolves_to_same_path(self):
        import shutil
        import tempfile
        from pathlib import Path

        from xlsx_add_comment import main

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target.xlsx"
            link = Path(td) / "link.xlsx"
            shutil.copy(_clean_input_path(), target)
            link.symlink_to(target)
            rc = main([str(target), str(link), "--cell", "A5",
                       "--author", "Q", "--text", "msg"])
            self.assertEqual(rc, 6, "symlink to same target must exit 6")


class TestArgValidation(unittest.TestCase):
    """`_validate_args` MX-A/B + DEP-1/DEP-3. Implemented in task 2.01.

    Each test isolates its OUTPUT path inside `tempfile.TemporaryDirectory()`
    to avoid `/tmp/`-pollution races on parallel CI runs (Sarcasmotron m-5).
    """

    def test_mxa_cell_and_batch_mutually_exclusive(self):
        import tempfile
        from pathlib import Path
        from xlsx_add_comment import main
        with tempfile.TemporaryDirectory() as td:
            rc = main([str(_clean_input_path()), str(Path(td) / "out.xlsx"),
                       "--cell", "A5", "--batch", str(_clean_input_path())])
        self.assertEqual(rc, 2, "--cell + --batch must exit 2")

    def test_mxb_threaded_and_no_threaded_mutually_exclusive(self):
        import tempfile
        from pathlib import Path
        from xlsx_add_comment import main
        with tempfile.TemporaryDirectory() as td:
            rc = main([str(_clean_input_path()), str(Path(td) / "out.xlsx"),
                       "--cell", "A5", "--author", "Q", "--text", "msg",
                       "--threaded", "--no-threaded"])
        self.assertEqual(rc, 2, "--threaded + --no-threaded must exit 2")

    def test_dep1_cell_requires_text_and_author(self):
        import tempfile
        from pathlib import Path
        from xlsx_add_comment import main
        # --cell with --author but missing --text → exit 2 DEP-1.
        with tempfile.TemporaryDirectory() as td:
            rc = main([str(_clean_input_path()), str(Path(td) / "out.xlsx"),
                       "--cell", "A5", "--author", "Q"])
        self.assertEqual(rc, 2, "--cell missing --text must exit 2 (DEP-1)")

    def test_dep3_default_threaded_with_cell_rejected(self):
        import tempfile
        from pathlib import Path
        from xlsx_add_comment import main
        with tempfile.TemporaryDirectory() as td:
            rc = main([str(_clean_input_path()), str(Path(td) / "out.xlsx"),
                       "--cell", "A5", "--author", "Q", "--text", "msg",
                       "--default-threaded"])
        self.assertEqual(rc, 2, "--default-threaded + --cell must exit 2 (DEP-3)")


class TestHonestScope(unittest.TestCase):
    """Regression locks for the v1 honest-scope clauses (R9.a..R9.g)
    — task 2.09. Each test ensures the named limitation has NOT silently
    grown into an implemented feature.

    All tests invoke the CLI via `subprocess.run` rather than in-process
    `main(argv)` so they verify the user-facing surface, including
    argparse rejection of removed flags.
    """

    @staticmethod
    def _cli(args: list[str], cwd: Path = None) -> "subprocess.CompletedProcess":
        import os, subprocess
        cmd = [
            sys.executable,
            str(_SCRIPTS / "xlsx_add_comment.py"),
            *args,
        ]
        # Hermetic invocation: don't inherit a developer's
        # XLSX_ADD_COMMENT_POST_VALIDATE — the post-pack guard's
        # behaviour is not under test here, and a regression in the
        # guard could mask an honest-scope failure with a confusing
        # validate.py message.
        env = {**os.environ, "XLSX_ADD_COMMENT_POST_VALIDATE": ""}
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd or _SCRIPTS, env=env,
        )

    def test_HonestScope_no_parentId(self):  # R9.a
        # Two writes on the same cell with --threaded form a thread.
        # No <threadedComment> in the output may carry parentId.
        import shutil, tempfile, zipfile
        from lxml import etree
        from xlsx_add_comment import THREADED_NS
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.xlsx"
            shutil.copy(_clean_input_path(), src)
            step1 = Path(td) / "s1.xlsx"
            step2 = Path(td) / "s2.xlsx"
            r1 = self._cli([str(src), str(step1), "--cell", "A5",
                            "--author", "T1", "--text", "first", "--threaded",
                            "--date", "2026-01-01T00:00:00Z"])
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = self._cli([str(step1), str(step2), "--cell", "A5",
                            "--author", "T2", "--text", "second", "--threaded",
                            "--date", "2026-01-02T00:00:00Z"])
            self.assertEqual(r2.returncode, 0, r2.stderr)

            with zipfile.ZipFile(step2) as z:
                threaded_part = next(
                    n for n in z.namelist()
                    if "threadedComments" in n and "rels" not in n
                )
                threaded_root = etree.fromstring(z.read(threaded_part))

            tcs = list(threaded_root.iter(f"{{{THREADED_NS}}}threadedComment"))
            self.assertEqual(len(tcs), 2,
                             f"expected 2 threadedComment, got {len(tcs)}")
            for tc in tcs:
                self.assertIsNone(
                    tc.get("parentId"),
                    f"R9.a violation: parentId={tc.get('parentId')!r} "
                    f"on threadedComment {tc.get('id')}",
                )

    def test_HonestScope_plain_text_body(self):  # R9.b
        # Threaded body must be a direct text node — no <r>/<rPr> children
        # inside the <text> wrapper. Legacy body has the standard
        # <comment><text><r><t> shape (allowed) but the <t> text is the
        # literal payload — no nested formatting elements beyond <r>+<t>.
        import shutil, tempfile, zipfile
        from lxml import etree
        from xlsx_add_comment import THREADED_NS, SS_NS
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.xlsx"
            shutil.copy(_clean_input_path(), src)
            out = Path(td) / "out.xlsx"
            r = self._cli([str(src), str(out), "--cell", "A5",
                           "--author", "Q", "--text", "msg",
                           "--threaded", "--date", "2026-01-01T00:00:00Z"])
            self.assertEqual(r.returncode, 0, r.stderr)

            with zipfile.ZipFile(out) as z:
                threaded_xml = next(
                    z.read(n) for n in z.namelist()
                    if "threadedComments" in n and "rels" not in n
                )
                comments_xml = z.read("xl/comments1.xml")

            # Threaded: <text> contains literal "msg" with no rich-run children.
            tc_root = etree.fromstring(threaded_xml)
            text_el = tc_root.find(
                f"{{{THREADED_NS}}}threadedComment/{{{THREADED_NS}}}text"
            )
            self.assertIsNotNone(text_el)
            self.assertEqual(text_el.text, "msg")
            children = list(text_el)
            self.assertEqual(
                len(children), 0,
                f"R9.b violation: threadedComment.text has children "
                f"{[c.tag for c in children]}",
            )

            # Legacy: <comment><text><r><t>msg</t></r></text> — exactly that
            # shape, no extra formatting elements (closing Sarcasmotron
            # LOW: also assert <text> has only the single <r> child, so a
            # sibling <phoneticPr/> regression doesn't slip through).
            cm_root = etree.fromstring(comments_xml)
            comment = cm_root.find(f"{{{SS_NS}}}commentList/{{{SS_NS}}}comment")
            text = comment.find(f"{{{SS_NS}}}text")
            rs = text.findall(f"{{{SS_NS}}}r")
            self.assertEqual(len(rs), 1, f"expected 1 <r>, got {len(rs)}")
            self.assertEqual(
                len(list(text)), 1,
                "R9.b violation: legacy <text> may contain only one <r>",
            )
            r_children = list(rs[0])
            self.assertEqual(len(r_children), 1)
            self.assertEqual(r_children[0].tag, f"{{{SS_NS}}}t")
            self.assertEqual(r_children[0].text, "msg")

    def test_HonestScope_default_vml_anchor(self):  # R9.c
        # <x:Anchor> must equal the locked default — no custom positioning.
        import shutil, tempfile, zipfile
        from lxml import etree
        from xlsx_add_comment import X_NS, DEFAULT_VML_ANCHOR
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.xlsx"
            shutil.copy(_clean_input_path(), src)
            out = Path(td) / "out.xlsx"
            r = self._cli([str(src), str(out), "--cell", "A5",
                           "--author", "Q", "--text", "msg"])
            self.assertEqual(r.returncode, 0, r.stderr)

            with zipfile.ZipFile(out) as z:
                vml_xml = next(
                    z.read(n) for n in z.namelist()
                    if "vmlDrawing" in n and "rels" not in n
                )
            vml_root = etree.fromstring(vml_xml)
            anchors = list(vml_root.iter(f"{{{X_NS}}}Anchor"))
            self.assertEqual(len(anchors), 1)
            self.assertEqual(anchors[0].text, DEFAULT_VML_ANCHOR,
                             "R9.c violation: VML anchor drifted from default")

    def test_HonestScope_threadedComment_id_is_uuidv4(self):  # R9.e
        import re, shutil, tempfile, zipfile
        from lxml import etree
        from xlsx_add_comment import THREADED_NS
        UUIDV4_RE = re.compile(
            r"^\{[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}\}$"
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.xlsx"
            shutil.copy(_clean_input_path(), src)
            out_a = Path(td) / "a.xlsx"
            out_b = Path(td) / "b.xlsx"
            ra = self._cli([str(src), str(out_a), "--cell", "A5",
                            "--author", "Q", "--text", "msg",
                            "--threaded", "--date", "2026-01-01T00:00:00Z"])
            rb = self._cli([str(src), str(out_b), "--cell", "B5",
                            "--author", "Q", "--text", "msg",
                            "--threaded", "--date", "2026-01-01T00:00:00Z"])
            self.assertEqual(ra.returncode, 0, ra.stderr)
            self.assertEqual(rb.returncode, 0, rb.stderr)

            ids = []
            for path in (out_a, out_b):
                with zipfile.ZipFile(path) as z:
                    threaded_xml = next(
                        z.read(n) for n in z.namelist()
                        if "threadedComments" in n and "rels" not in n
                    )
                root = etree.fromstring(threaded_xml)
                tc = root.find(f"{{{THREADED_NS}}}threadedComment")
                ids.append(tc.get("id"))
            for id_str in ids:
                self.assertRegex(
                    id_str, UUIDV4_RE,
                    f"R9.e violation: id {id_str!r} not UUIDv4",
                )
            self.assertNotEqual(
                ids[0], ids[1],
                "R9.e violation: --date pinned + same author → ids "
                "must still differ (UUIDv4 non-determinism lock)",
            )

    def test_HonestScope_no_unpacked_dir_flag(self):  # R9.g
        # 1. --help text must NOT mention --unpacked-dir.
        # 2. invoking with --unpacked-dir → argparse usage error (exit 2).
        r_help = self._cli(["--help"])
        self.assertEqual(r_help.returncode, 0)
        self.assertNotIn("--unpacked-dir", r_help.stdout,
                         "R9.g violation: --unpacked-dir surfaced in --help")
        # Reject on actual invocation. Use clean.xlsx as input and any
        # output path; argparse should fail before either is read.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = self._cli([
                str(_clean_input_path()), str(Path(td) / "x.xlsx"),
                "--unpacked-dir", "/tmp/foo",
                "--cell", "A5", "--author", "Q", "--text", "msg",
            ])
            self.assertEqual(r.returncode, 2,
                             f"argparse must reject --unpacked-dir; "
                             f"got rc={r.returncode}, stderr={r.stderr}")

    def test_HonestScope_no_default_initials_flag(self):  # R9.f
        # 1. --help must NOT mention the flag.
        # 2. invoking with the flag → argparse usage error (mirrors R9.g
        #    so a future SUPPRESS-trick can't sneak past --help inspection).
        r_help = self._cli(["--help"])
        self.assertEqual(r_help.returncode, 0)
        self.assertNotIn("--default-initials", r_help.stdout,
                         "R9.f violation: --default-initials surfaced in --help")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = self._cli([
                str(_clean_input_path()), str(Path(td) / "x.xlsx"),
                "--default-initials", "QQ",
                "--cell", "A5", "--author", "Q", "--text", "msg",
            ])
            self.assertEqual(r.returncode, 2,
                             f"argparse must reject --default-initials; "
                             f"got rc={r.returncode}, stderr={r.stderr}")

    def test_HonestScope_goldens_README_protocol_marker(self):  # R9.d / m4
        readme = _HERE / "golden" / "README.md"
        self.assertTrue(readme.is_file(),
                        f"R9.d expected fixture protocol README at {readme}")
        body = readme.read_text(encoding="utf-8")
        self.assertIn(
            "DO NOT open these files in Excel", body,
            "R9.d violation: agent-output-only protocol marker missing",
        )


class TestGoldenDiff(unittest.TestCase):
    """Volatile-attribute mask in `_golden_diff.canon_part` (task 2.10)."""

    def _build_threaded_part(self, **attrs) -> bytes:
        from lxml import etree
        from xlsx_add_comment import THREADED_NS
        root = etree.Element(
            f"{{{THREADED_NS}}}ThreadedComments",
            nsmap={None: THREADED_NS},
        )
        tc = etree.SubElement(
            root, f"{{{THREADED_NS}}}threadedComment", **attrs,
        )
        text = etree.SubElement(tc, f"{{{THREADED_NS}}}text")
        text.text = "msg"
        return etree.tostring(root)

    def test_canon_part_masks_threaded_id(self):
        from _golden_diff import canon_part
        xml = self._build_threaded_part(
            ref="A5",
            id="{ABC12345-DEAD-4BEE-8000-FACEFACEFACE}",
            personId="{P}",
            dT="2026-01-01T00:00:00Z",
        )
        out = canon_part(xml).decode()
        self.assertIn('id="{MASKED}"', out)
        self.assertNotIn("ABC12345-DEAD-4BEE-8000-FACEFACEFACE", out)

    def test_canon_part_masks_unpinned_dT(self):
        from _golden_diff import canon_part
        # Unpinned date → masked.
        xml = self._build_threaded_part(
            ref="A5", id="{X}", personId="{P}",
            dT="2099-12-31T23:59:59Z",
        )
        self.assertIn('dT="MASKED"', canon_part(xml).decode())
        # Pinned date marker → preserved.
        xml = self._build_threaded_part(
            ref="A5", id="{X}", personId="{P}",
            dT="2026-01-01T00:00:00Z",
        )
        out = canon_part(xml).decode()
        self.assertIn('dT="2026-01-01T00:00:00Z"', out)
        self.assertNotIn('dT="MASKED"', out)


if __name__ == "__main__":
    unittest.main()
