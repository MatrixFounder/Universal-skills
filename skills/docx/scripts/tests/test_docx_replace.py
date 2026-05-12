"""Unit tests for docx_replace.py (docx-6 chain).

These tests form the Red state established in task-006-01b.
Each stub body is ``self.fail()`` so the CI red bar SHRINKS
monotonically as downstream Phase-2 tasks flip individual stubs
to real assertions. NOT ``unittest.skip`` — silent skip = false-green.

Each ``self.fail()`` message names the downstream sub-task that
turns it GREEN.

Downstream sub-task mapping per class:
  TestCrossCutting             → task-006-03
  TestPartWalker               → task-006-04
  TestReplaceAction            → task-006-04
  TestInsertAfterAction        → task-006-05
  TestDeleteParagraphAction    → task-006-06
  TestCli                      → task-006-07a
  TestPostValidate             → task-006-07a
  TestLibraryMode              → task-006-07b
  TestHonestScopeLocks         → task-006-08
"""

import copy
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from docx_replace import (
        _assert_distinct_paths,
        _deep_clone,
        _do_delete_paragraph,
        _do_insert_after,
        _do_replace,
        _extract_insert_paragraphs,
        _iter_searchable_parts,
        _materialise_md_source,
        _parse_scope,
        _post_validate_enabled,
        _run_post_validate,
        _read_stdin_capped,
        _run,
        _safe_remove_paragraph,
        _tempdir,
        build_parser,
        main,
        AnchorNotFound,
        LastParagraphCannotBeDeleted,
        EmptyInsertSource,
        InsertSourceTooLarge,
        Md2DocxFailed,
        Md2DocxNotAvailable,
        NotADocxTree,
        PostValidateFailed,
        SelfOverwriteRefused,
    )
    _DOCX_REPLACE_AVAILABLE = True
except ImportError:
    # Module doesn't exist until 006-03+; tests still collectable.
    _DOCX_REPLACE_AVAILABLE = False

# ── per-class stub message constants ────────────────────────────────────────

_STUB_03 = "docx-6 stub — to be implemented in task-006-03"
_STUB_04 = "docx-6 stub — to be implemented in task-006-04"
_STUB_05 = "docx-6 stub — to be implemented in task-006-05"
_STUB_06 = "docx-6 stub — to be implemented in task-006-06"
_STUB_07a = "docx-6 stub — to be implemented in task-006-07a"
_STUB_07b = "docx-6 stub — to be implemented in task-006-07b (or N/A if deferred to docx-6.4 backlog)"
_STUB_08 = "docx-6 stub — to be implemented in task-006-08"


# ── TestCrossCutting ─────────────────────────────────────────────────────────

@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestCrossCutting(unittest.TestCase):
    """Cross-cutting concerns (exit codes, envelopes, macros, library mode gate).

    Flipped GREEN in task-006-03.
    """

    def test_assert_distinct_paths_raises_on_collision(self):
        """_assert_distinct_paths("a.docx", "a.docx") raises SelfOverwriteRefused."""
        with self.assertRaises(SelfOverwriteRefused):
            _assert_distinct_paths(Path("a.docx"), Path("a.docx"))

    def test_assert_distinct_paths_follows_symlinks(self):
        """b.docx symlinked to a.docx → _assert_distinct_paths raises SelfOverwriteRefused."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            a = d / "a.docx"
            a.touch()
            b = d / "b.docx"
            b.symlink_to(a)
            with self.assertRaises(SelfOverwriteRefused):
                _assert_distinct_paths(a, b)

    def test_read_stdin_capped_raises_on_overflow(self):
        """stdin with max_bytes+1 bytes raises InsertSourceTooLarge."""
        max_bytes = 1024

        class _FakeBuffer:
            def read(self, n):
                # Return exactly n bytes (max_bytes+1) to trigger overflow
                return b"\0" * n

        class _FakeStdin:
            buffer = _FakeBuffer()

        old_stdin = sys.stdin
        sys.stdin = _FakeStdin()  # type: ignore[assignment]
        try:
            with self.assertRaises(InsertSourceTooLarge) as ctx:
                _read_stdin_capped(max_bytes=max_bytes)
            exc = ctx.exception
            self.assertEqual(exc.details["max_bytes"], max_bytes)
            self.assertGreaterEqual(exc.details["actual_bytes_min"], max_bytes + 1)
        finally:
            sys.stdin = old_stdin

    def test_read_stdin_capped_accepts_at_limit(self):
        """stdin with exactly max_bytes bytes returns successfully."""
        max_bytes = 1024
        payload = b"\x42" * max_bytes

        class _FakeBuffer:
            def read(self, n):
                # n is max_bytes+1; return only max_bytes → no overflow
                return payload[:max_bytes]

        class _FakeStdin:
            buffer = _FakeBuffer()

        old_stdin = sys.stdin
        sys.stdin = _FakeStdin()  # type: ignore[assignment]
        try:
            result = _read_stdin_capped(max_bytes=max_bytes)
            self.assertEqual(len(result), max_bytes)
        finally:
            sys.stdin = old_stdin

    def test_tempdir_cleans_up_on_exception(self):
        """_tempdir context manager removes the directory even after an exception."""
        captured_path: list[Path] = []
        with self.assertRaises(RuntimeError):
            with _tempdir() as p:
                captured_path.append(p)
                self.assertTrue(p.exists())
                raise RuntimeError("x")
        self.assertFalse(captured_path[0].exists())

    def test_main_argparse_usage_error_returns_envelope(self):
        """main(["--invalid"]) returns exit code 2 without raising."""
        rc = main(["--invalid"])
        self.assertEqual(rc, 2)

    def test_empty_anchor_returns_usage_error(self):
        """FIX-1 regression: --anchor '' in zip-mode → exit 2 + UsageError envelope.

        Uses subprocess so real stderr is captured (report_error binds
        sys.stderr at import time, before redirect_stderr takes effect).
        """
        import json
        scripts_dir = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "docx_replace.py",
             "a.docx", "b.docx", "--anchor", "", "--replace", "y",
             "--json-errors"],
            capture_output=True, text=True, cwd=str(scripts_dir),
        )
        self.assertEqual(result.returncode, 2,
                          f"Expected exit 2, got {result.returncode}; "
                          f"stderr={result.stderr!r}")
        stderr = result.stderr.strip()
        try:
            envelope = json.loads(stderr)
        except json.JSONDecodeError:
            self.fail(f"stderr not valid JSON: {stderr!r}")
        self.assertEqual(envelope.get("type"), "UsageError",
                          f"Expected UsageError envelope, got: {envelope}")

    def test_library_mode_empty_anchor_returns_usage_error(self):
        """FIX-1 regression: --anchor '' in library-mode → exit 2 + UsageError envelope.

        Uses subprocess so real stderr is captured.
        """
        import json
        scripts_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "docx_replace.py",
                 "--unpacked-dir", tmp, "--anchor", "",
                 "--delete-paragraph", "--json-errors"],
                capture_output=True, text=True, cwd=str(scripts_dir),
            )
        self.assertEqual(result.returncode, 2,
                          f"Expected exit 2, got {result.returncode}; "
                          f"stderr={result.stderr!r}")
        stderr = result.stderr.strip()
        try:
            envelope = json.loads(stderr)
        except json.JSONDecodeError:
            self.fail(f"stderr not valid JSON: {stderr!r}")
        self.assertEqual(envelope.get("type"), "UsageError",
                          f"Expected UsageError envelope, got: {envelope}")

    def test_main_catches_generic_exception_with_envelope(self):
        """FIX-5 regression: unexpected exception → exit 1 + InternalError envelope.

        Uses subprocess with a tiny helper script that monkey-patches _run to
        raise RuntimeError; real stderr is captured so the JSON envelope is
        visible (report_error binds sys.stderr at import time).
        """
        import json
        scripts_dir = Path(__file__).resolve().parent.parent
        # Write a small helper script into a tmp file to avoid inline
        # multi-statement -c quoting issues.
        helper = (
            "import sys\n"
            "sys.path.insert(0, '.')\n"
            "from unittest import mock\n"
            "import docx_replace\n"
            "with mock.patch('docx_replace._run',\n"
            "                side_effect=RuntimeError('synthetic')):\n"
            "    rc = docx_replace.main(\n"
            "        ['a.docx', 'b.docx', '--anchor', 'x',\n"
            "         '--replace', 'y', '--json-errors'])\n"
            "sys.exit(rc)\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(scripts_dir)
        ) as fh:
            fh.write(helper)
            helper_path = fh.name
        try:
            result = subprocess.run(
                [sys.executable, helper_path],
                capture_output=True, text=True, cwd=str(scripts_dir),
            )
        finally:
            Path(helper_path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 1,
                          f"Expected exit 1, got {result.returncode}; "
                          f"stderr={result.stderr!r}")
        stderr = result.stderr.strip()
        try:
            envelope = json.loads(stderr)
        except json.JSONDecodeError:
            self.fail(f"stderr not valid JSON: {stderr!r}")
        self.assertEqual(envelope.get("type"), "InternalError",
                          f"Expected InternalError envelope, got: {envelope}")


# ── helpers ─────────────────────────────────────────────────────────────────

_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WP_DOC_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_WP_HDR_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
_WP_FTR_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
_WP_FN_CT  = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
_WP_EN_CT  = "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"


def _make_ct_xml(overrides: list[tuple[str, str]]) -> bytes:
    """Build a minimal [Content_Types].xml bytes with the given (PartName, ContentType) overrides."""
    lines = [b'<?xml version="1.0" encoding="UTF-8"?>',
             b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">']
    for part_name, ct in overrides:
        lines.append(
            f'  <Override PartName="{part_name}" ContentType="{ct}"/>'.encode()
        )
    lines.append(b'</Types>')
    return b"\n".join(lines)


def _make_word_part(text: str = "stub") -> bytes:
    """Build a minimal word/*.xml bytes (just an XML root element)."""
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
    )


def _build_doc_xml(paragraphs: list[list[tuple[dict, str]]]) -> bytes:
    """Build a minimal word/document.xml.

    paragraphs: list of paragraphs, each is a list of (rpr_attrs, text) run pairs.
    rpr_attrs: dict of w: attributes to put in w:rPr (e.g. {"b": ""} for bold).
    """
    from lxml import etree
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    doc = etree.Element(f"{{{W}}}document")
    body = etree.SubElement(doc, f"{{{W}}}body")
    for runs in paragraphs:
        p_el = etree.SubElement(body, f"{{{W}}}p")
        for rpr_attrs, text in runs:
            r_el = etree.SubElement(p_el, f"{{{W}}}r")
            if rpr_attrs is not None:
                rpr = etree.SubElement(r_el, f"{{{W}}}rPr")
                for tag, val in rpr_attrs.items():
                    child = etree.SubElement(rpr, f"{{{W}}}{tag}")
                    if val:
                        child.text = val
            t_el = etree.SubElement(r_el, f"{{{W}}}t")
            t_el.text = text
    return etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)


# ── TestPartWalker ───────────────────────────────────────────────────────────

@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestPartWalker(unittest.TestCase):
    """Part-walker logic (Content_Types registry, glob fallback, ordering).

    Flipped GREEN in task-006-04.

    NOTE: docx_replace_headers.docx fixture deferred to 006-04.
    The header-scope E2E case (R5 header parts) will be added when
    the fixture generation step (md2docx + manual header-part splice)
    is completed in that task. See task-006-04 spec §fixtures.
    """

    def test_content_types_primary_source(self):
        """[Content_Types].xml is the authoritative source for part URIs.

        Build a tmp tree with [Content_Types].xml listing 1 doc + 2 headers
        + 1 footer + footnotes + endnotes; assert iterator yields 6 parts in
        deterministic order: document, header1, header2, footer1, footnotes,
        endnotes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            # Create part files
            parts = [
                "document.xml", "header1.xml", "header2.xml",
                "footer1.xml", "footnotes.xml", "endnotes.xml",
            ]
            for name in parts:
                (word_dir / name).write_bytes(_make_word_part())
            # Write [Content_Types].xml
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header1.xml",  _WP_HDR_CT),
                ("/word/header2.xml",  _WP_HDR_CT),
                ("/word/footer1.xml",  _WP_FTR_CT),
                ("/word/footnotes.xml", _WP_FN_CT),
                ("/word/endnotes.xml",  _WP_EN_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(_make_ct_xml(ct_overrides))
            result = list(_iter_searchable_parts(tree_root))
            names = [p.name for p, _ in result]
            self.assertEqual(
                names,
                ["document.xml", "header1.xml", "header2.xml",
                 "footer1.xml", "footnotes.xml", "endnotes.xml"],
            )

    def test_glob_fallback_when_content_types_missing(self):
        """Glob fallback used when [Content_Types].xml is absent/corrupt.

        Write malformed [Content_Types].xml; iterator falls back to glob and
        emits a warning on stderr.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            (word_dir / "document.xml").write_bytes(_make_word_part())
            (word_dir / "header1.xml").write_bytes(_make_word_part())
            # Write malformed Content_Types.xml
            (tree_root / "[Content_Types].xml").write_bytes(b"<Types")
            buf = io.StringIO()
            import contextlib
            with contextlib.redirect_stderr(buf):
                result = list(_iter_searchable_parts(tree_root))
            names = [p.name for p, _ in result]
            self.assertIn("document.xml", names)
            self.assertIn("header1.xml", names)
            warning = buf.getvalue()
            self.assertIn("WARNING", warning)

    def test_deterministic_part_order(self):
        """Parts are walked in deterministic (alphabetical) order.

        Fixture with header10.xml AND header2.xml both listed in Content_Types;
        lexicographic (ASCII) sort puts header10.xml BEFORE header2.xml because
        '1' < '2' in ASCII. This is intentional — natural-number sort was
        rejected because it adds complexity and the OOXML spec does not mandate
        any particular header numbering scheme. Callers should not rely on
        numeric ordering of header parts.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            for name in ["document.xml", "header2.xml", "header10.xml"]:
                (word_dir / name).write_bytes(_make_word_part())
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header2.xml",  _WP_HDR_CT),
                ("/word/header10.xml", _WP_HDR_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(_make_ct_xml(ct_overrides))
            result = list(_iter_searchable_parts(tree_root))
            names = [p.name for p, _ in result]
            # Lexicographic: "header10.xml" < "header2.xml" (ASCII '1' < '2')
            h_names = [n for n in names if n.startswith("header")]
            self.assertEqual(h_names, ["header10.xml", "header2.xml"])

    def test_content_types_no_word_overrides_falls_back(self):
        """FIX-2 regression: CT parses but contains zero WP overrides →
        glob fallback fires and document.xml is yielded; WARNING on stderr."""
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            # Create word/document.xml on disk.
            (word_dir / "document.xml").write_bytes(_make_word_part())
            # [Content_Types].xml parses fine but has only a styles Override —
            # no WordprocessingML document entry → should trigger fallback.
            styles_ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
            (tree_root / "[Content_Types].xml").write_bytes(
                _make_ct_xml([("/word/styles.xml", styles_ct)])
            )
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                result = list(_iter_searchable_parts(tree_root))
            # document.xml must be yielded via glob fallback.
            names = [p.name for p, _ in result]
            self.assertIn("document.xml", names,
                          "document.xml must be found via glob fallback")
            # A WARNING must be emitted.
            warning = buf.getvalue()
            self.assertIn("WARNING", warning,
                          "A WARNING must be printed when CT has no WP Overrides")

    def test_missing_on_disk_part_silent_skip(self):
        """A part listed in Content_Types but absent on disk is skipped silently."""
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            # Only create document.xml and footer1.xml; omit header2.xml
            (word_dir / "document.xml").write_bytes(_make_word_part())
            (word_dir / "footer1.xml").write_bytes(_make_word_part())
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header2.xml",  _WP_HDR_CT),  # listed but missing on disk
                ("/word/footer1.xml",  _WP_FTR_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(_make_ct_xml(ct_overrides))
            # Must not raise; missing part is silently skipped
            result = list(_iter_searchable_parts(tree_root))
            names = [p.name for p, _ in result]
            self.assertIn("document.xml", names)
            self.assertIn("footer1.xml", names)
            self.assertNotIn("header2.xml", names)


# ── TestScopeFilter (docx-6.7) ──────────────────────────────────────────────


@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestScopeFilter(unittest.TestCase):
    """``--scope`` filter for `_iter_searchable_parts` (docx-6.7).

    R1 / R2 coverage — locks the parse + filter contract. Default
    (`scope=None` or `--scope=all`) must be byte-identical to v1.
    """

    def test_parse_scope_default_all_expands_to_full_set(self):
        """`_parse_scope("all")` yields the 5 internal role names."""
        result = _parse_scope("all")
        self.assertEqual(
            result,
            {"document", "header", "footer", "footnotes", "endnotes"},
        )

    def test_parse_scope_body_only_maps_to_document(self):
        """CLI plural `body` maps to internal `document` role."""
        result = _parse_scope("body")
        self.assertEqual(result, {"document"})

    def test_parse_scope_comma_separated_case_insensitive(self):
        """`--scope=Body,Headers` is case-insensitive + dedup'd."""
        result = _parse_scope("Body,Headers,body,HEADERS,FOOTERS")
        self.assertEqual(result, {"document", "header", "footer"})

    def test_parse_scope_invalid_value_raises_usage_error(self):
        """Unknown value → `_AppError(UsageError)` exit 2 with envelope."""
        from docx_replace import _AppError
        with self.assertRaises(_AppError) as ctx:
            _parse_scope("body,not_a_role,headers")
        exc = ctx.exception
        self.assertEqual(exc.code, 2)
        self.assertEqual(exc.error_type, "UsageError")
        self.assertIn("not_a_role", exc.details["invalid"])
        self.assertIn("body", exc.details["valid"])

    def test_parse_scope_empty_raises_usage_error(self):
        """`--scope=` (empty / whitespace-only) → UsageError."""
        from docx_replace import _AppError
        with self.assertRaises(_AppError):
            _parse_scope("")
        with self.assertRaises(_AppError):
            _parse_scope("   ,  ,")

    def test_iter_searchable_parts_scope_body_only_yields_document(self):
        """`scope={"document"}` drops headers/footers/notes from walk.

        Build a tree with all 6 parts; filter to body only; assert ONE
        part yielded and it's `word/document.xml`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            parts = [
                "document.xml", "header1.xml", "header2.xml",
                "footer1.xml", "footnotes.xml", "endnotes.xml",
            ]
            for name in parts:
                (word_dir / name).write_bytes(_make_word_part())
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header1.xml",  _WP_HDR_CT),
                ("/word/header2.xml",  _WP_HDR_CT),
                ("/word/footer1.xml",  _WP_FTR_CT),
                ("/word/footnotes.xml", _WP_FN_CT),
                ("/word/endnotes.xml",  _WP_EN_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(
                _make_ct_xml(ct_overrides)
            )
            result = list(_iter_searchable_parts(tree_root, scope={"document"}))
            names = [p.name for p, _ in result]
            self.assertEqual(names, ["document.xml"])

    def test_iter_searchable_parts_scope_none_back_compat(self):
        """`scope=None` (default) preserves pre-docx-6.7 behavior:
        ALL 5 roles yielded in deterministic order. R3.a regression lock.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            parts = ["document.xml", "header1.xml", "footer1.xml",
                     "footnotes.xml", "endnotes.xml"]
            for name in parts:
                (word_dir / name).write_bytes(_make_word_part())
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header1.xml",  _WP_HDR_CT),
                ("/word/footer1.xml",  _WP_FTR_CT),
                ("/word/footnotes.xml", _WP_FN_CT),
                ("/word/endnotes.xml",  _WP_EN_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(
                _make_ct_xml(ct_overrides)
            )
            # No scope arg = back-compat call (must match pre-docx-6.7).
            v1_result = list(_iter_searchable_parts(tree_root))
            # Explicit scope=None must match too.
            v2_explicit = list(_iter_searchable_parts(tree_root, scope=None))
            self.assertEqual(
                [p.name for p, _ in v1_result],
                [p.name for p, _ in v2_explicit],
            )
            self.assertEqual(
                [p.name for p, _ in v1_result],
                ["document.xml", "header1.xml", "footer1.xml",
                 "footnotes.xml", "endnotes.xml"],
            )

    def test_iter_searchable_parts_scope_filter_preserves_order(self):
        """Order WITHIN the requested set follows R5.g deterministic
        order (document → headers → footers → footnotes → endnotes),
        even when only a subset is requested."""
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            parts = ["document.xml", "header1.xml", "footer1.xml",
                     "footnotes.xml", "endnotes.xml"]
            for name in parts:
                (word_dir / name).write_bytes(_make_word_part())
            ct_overrides = [
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header1.xml",  _WP_HDR_CT),
                ("/word/footer1.xml",  _WP_FTR_CT),
                ("/word/footnotes.xml", _WP_FN_CT),
                ("/word/endnotes.xml",  _WP_EN_CT),
            ]
            (tree_root / "[Content_Types].xml").write_bytes(
                _make_ct_xml(ct_overrides)
            )
            # Request body + footnotes — NOT in CLI input order, but
            # output must follow R5.g (document before footnotes).
            result = list(_iter_searchable_parts(
                tree_root, scope={"footnotes", "document"},
            ))
            names = [p.name for p, _ in result]
            self.assertEqual(names, ["document.xml", "footnotes.xml"])


# ── TestReplaceAction ────────────────────────────────────────────────────────

def _build_minimal_tree(paragraphs: list[list[tuple]]) -> tempfile.TemporaryDirectory:
    """Build a minimal unpacked OOXML tree in a temp dir.

    Returns the TemporaryDirectory (caller must use as ctx manager or call cleanup()).
    The tree contains:
      [Content_Types].xml  — single Override for /word/document.xml
      word/document.xml    — from _build_doc_xml(paragraphs)
    """
    tmp = tempfile.TemporaryDirectory()
    tree_root = Path(tmp.name)
    word_dir = tree_root / "word"
    word_dir.mkdir()
    doc_bytes = _build_doc_xml(paragraphs)
    (word_dir / "document.xml").write_bytes(doc_bytes)
    ct_bytes = _make_ct_xml([("/word/document.xml", _WP_DOC_CT)])
    (tree_root / "[Content_Types].xml").write_bytes(ct_bytes)
    return tmp


@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestReplaceAction(unittest.TestCase):
    """``--replace`` action: R1.a through R1.g coverage.

    Flipped GREEN in task-006-04.
    """

    def test_r1a_single_run_replace(self):
        """R1.a: anchor fully within one run → replace in-place."""
        # Paragraph: single plain run "May 2024"
        tmp = _build_minimal_tree([[({}, "May 2024")]])
        with tmp:
            count = _do_replace(Path(tmp.name), "May 2024", "April 2025", anchor_all=False)
        self.assertEqual(count, 1)

    def test_r1b_replace_preserves_run_formatting(self):
        """R1.b: replacement text inherits original run formatting (bold preserved)."""
        from lxml import etree
        from docx.oxml.ns import qn
        # Paragraph: single bold run "May 2024"
        tmp = _build_minimal_tree([[({'b': ''}, "May 2024")]])
        with tmp as tmp_name:
            tree_root = Path(tmp_name)
            count = _do_replace(tree_root, "May 2024", "April 2025", anchor_all=False)
            # Re-read the written document.xml to check formatting preserved
            from lxml import etree as _etree
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            runs = doc.findall(f".//{{{W}}}r")
            self.assertTrue(any(
                r.find(f"{{{W}}}rPr/{{{W}}}b") is not None
                for r in runs
            ), "Bold rPr should be preserved after replacement")
            texts = [t.text for t in doc.findall(f".//{{{W}}}t") if t.text]
            self.assertTrue(any("April 2025" in t for t in texts), "Replacement text not found")
        self.assertEqual(count, 1)

    def test_r1c_all_flag_replaces_multiple_occurrences(self):
        """R1.c: --all replaces every occurrence in paragraph order."""
        # Three paragraphs each containing "foo"
        paras = [
            [({}, "foo bar")],
            [({}, "baz foo")],
            [({}, "foo foo")],
        ]
        tmp = _build_minimal_tree(paras)
        with tmp:
            count = _do_replace(Path(tmp.name), "foo", "X", anchor_all=True)
        # "foo bar" → 1, "baz foo" → 1, "foo foo" → 2 = 4 total
        self.assertEqual(count, 4)

    def test_r1d_empty_replacement_strips_anchor(self):
        """R1.d: --replace '' removes the anchor text entirely."""
        tmp = _build_minimal_tree([[({}, "May 2024 is here")]])
        with tmp as tmp_name:
            tree_root = Path(tmp_name)
            count = _do_replace(tree_root, "May 2024", "", anchor_all=False)
            from lxml import etree as _etree
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            texts = "".join(t.text or "" for t in doc.findall(f".//{{{W}}}t"))
            self.assertNotIn("May 2024", texts)
        self.assertEqual(count, 1)

    def test_r1e_anchor_not_found_raises(self):
        """R1.e: no match → _do_replace returns 0 (caller raises AnchorNotFound)."""
        tmp = _build_minimal_tree([[({}, "Some other text")]])
        with tmp:
            count = _do_replace(Path(tmp.name), "ZZZNOTFOUND", "x", anchor_all=False)
        self.assertEqual(count, 0)

    def test_replace_first_match_default_single_part(self):
        """Without --all, only the FIRST paragraph match is replaced; count == 1.

        Spec lines 213-215. Fixture: 3 paragraphs each containing anchor "foo".
        After _do_replace(..., anchor_all=False), only paragraph[0] has "bar";
        paragraphs[1] and [2] still have "foo".
        """
        from lxml import etree as _etree
        paras = [
            [({}, "foo alpha")],
            [({}, "foo beta")],
            [({}, "foo gamma")],
        ]
        tmp = _build_minimal_tree(paras)
        with tmp as tmp_name:
            tree_root = Path(tmp_name)
            count = _do_replace(tree_root, "foo", "bar", anchor_all=False)
            self.assertEqual(count, 1)
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            texts = [t.text or "" for t in doc.findall(f".//{{{W}}}t")]
            # First paragraph replaced
            self.assertTrue(any("bar" in t for t in texts), "Replacement 'bar' not found")
            # Paragraphs 1 and 2 still have original "foo"
            foo_count = sum(t.count("foo") for t in texts)
            self.assertEqual(foo_count, 2, f"Expected 2 remaining 'foo' occurrences, got {foo_count}")

    def test_replace_first_match_default_multi_part(self):
        """Without --all, only the first PART gets a replacement; second part unchanged.

        Spec Notes §282-290. Fixture: document.xml (anchor in para 1) AND
        word/header1.xml (anchor in para 1). Deterministic order puts
        document.xml first → document.xml gets the replacement; header1.xml
        remains unchanged; count == 1.
        """
        from lxml import etree as _etree

        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        def _make_para_xml(text: str) -> bytes:
            doc = _etree.Element(f"{{{W}}}hdr")
            p = _etree.SubElement(doc, f"{{{W}}}p")
            r = _etree.SubElement(p, f"{{{W}}}r")
            t = _etree.SubElement(r, f"{{{W}}}t")
            t.text = text
            return _etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)

        tmp = tempfile.TemporaryDirectory()
        try:
            tree_root = Path(tmp.name)
            word_dir = tree_root / "word"
            word_dir.mkdir()
            # document.xml — anchor present
            doc_bytes = _build_doc_xml([[({}, "ANCHOR_TEXT")]])
            (word_dir / "document.xml").write_bytes(doc_bytes)
            # header1.xml — anchor also present
            (word_dir / "header1.xml").write_bytes(_make_para_xml("ANCHOR_TEXT"))
            ct_bytes = _make_ct_xml([
                ("/word/document.xml", _WP_DOC_CT),
                ("/word/header1.xml",  _WP_HDR_CT),
            ])
            (tree_root / "[Content_Types].xml").write_bytes(ct_bytes)

            count = _do_replace(tree_root, "ANCHOR_TEXT", "REPLACED", anchor_all=False)
            self.assertEqual(count, 1)

            # document.xml → replaced
            doc_root = _etree.parse(str(word_dir / "document.xml")).getroot()
            doc_texts = "".join(t.text or "" for t in doc_root.findall(f".//{{{W}}}t"))
            self.assertIn("REPLACED", doc_texts)
            self.assertNotIn("ANCHOR_TEXT", doc_texts)

            # header1.xml → unchanged
            hdr_root = _etree.parse(str(word_dir / "header1.xml")).getroot()
            hdr_texts = "".join(t.text or "" for t in hdr_root.findall(f".//{{{W}}}t"))
            self.assertIn("ANCHOR_TEXT", hdr_texts)
            self.assertNotIn("REPLACED", hdr_texts)
        finally:
            tmp.cleanup()

    def test_replace_cross_run_anchor_returns_zero(self):
        """Anchor split across runs with DIFFERENT rPr → _do_replace returns 0.

        Spec lines 220-223. "May 2024" is split: <w:r rPr=bold>May</w:r>
        then <w:r> 2024</w:r>. Different rPr → _merge_adjacent_runs keeps
        them separate → _replace_in_run finds neither "May 2024" in any
        single run → count == 0.
        """
        # Two runs: first bold "May", second plain " 2024" — different rPr
        paras = [
            [({'b': ''}, "May"), ({}, " 2024")],
        ]
        tmp = _build_minimal_tree(paras)
        with tmp:
            count = _do_replace(Path(tmp.name), "May 2024", "April 2025", anchor_all=False)
        self.assertEqual(count, 0)


# ── TestInsertAfterAction helpers ─────────────────────────────────────────────

def _build_insert_tree(paragraphs_xml: list[str], include_sectPr: bool = False) -> tempfile.TemporaryDirectory:
    """Build a minimal insert unpacked tree with word/document.xml.

    paragraphs_xml: list of XML strings for body children (e.g. '<w:p/>')
    include_sectPr: if True, append a <w:sectPr/> as the last body child.
    """
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    from lxml import etree
    doc = etree.Element(f"{{{W}}}document")
    body = etree.SubElement(doc, f"{{{W}}}body")
    for p_xml in paragraphs_xml:
        child = etree.fromstring(p_xml)
        body.append(child)
    if include_sectPr:
        body.append(etree.Element(f"{{{W}}}sectPr"))
    tmp = tempfile.TemporaryDirectory()
    tree_root = Path(tmp.name)
    word_dir = tree_root / "word"
    word_dir.mkdir()
    (word_dir / "document.xml").write_bytes(
        etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    )
    return tmp


# ── TestInsertAfterAction ────────────────────────────────────────────────────

@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestInsertAfterAction(unittest.TestCase):
    """``--insert-after`` action (UC-2).

    Flipped GREEN in task-006-05.
    """

    def test_materialise_md_source_subprocess_argv(self):
        """md2docx subprocess called with correct argv list and shell=False."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmpdir = Path(tmp_str)
            scripts_dir = tmpdir / "scripts"
            scripts_dir.mkdir()
            md2docx_path = scripts_dir / "md2docx.js"
            md2docx_path.touch()
            md_path = tmpdir / "source.md"
            md_path.write_text("# Hello\n")
            out_docx = tmpdir / "insert.docx"
            # Patch subprocess.run: return success AND create the output file.
            def fake_run(args, **kwargs):
                # Create the expected output file so _materialise_md_source succeeds.
                out_docx.touch()
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            with mock.patch("subprocess.run", side_effect=fake_run) as mock_run:
                result = _materialise_md_source(md_path, scripts_dir, tmpdir)
            call_args = mock_run.call_args
            argv = call_args[0][0]
            self.assertEqual(argv[0], "node")
            self.assertEqual(argv[1], str(md2docx_path))
            self.assertEqual(argv[2], str(md_path))
            # argv[3] is the out_docx path
            self.assertFalse(call_args[1].get("shell", False), "shell must be False")

    def test_materialise_md_source_failure_raises_md2docx_failed(self):
        """Non-zero rc from subprocess → Md2DocxFailed with details."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmpdir = Path(tmp_str)
            scripts_dir = tmpdir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "md2docx.js").touch()
            md_path = tmpdir / "source.md"
            md_path.write_text("# Hello\n")
            fake_result = subprocess.CompletedProcess(
                args=["node", "md2docx.js", str(md_path), "out.docx"],
                returncode=2,
                stdout="",
                stderr="boom",
            )
            with mock.patch("subprocess.run", return_value=fake_result):
                with self.assertRaises(Md2DocxFailed) as ctx:
                    _materialise_md_source(md_path, scripts_dir, tmpdir)
            exc = ctx.exception
            self.assertEqual(exc.details["stderr"], "boom")
            self.assertEqual(exc.details["returncode"], 2)

    def test_extract_insert_paragraphs_strips_sectPr(self):
        """<w:sectPr> body child is stripped; only <w:p> elements returned."""
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        # Build insert tree with 2 paragraphs + 1 sectPr; build matching base tree.
        tmp = _build_insert_tree(
            [f'<w:p xmlns:w="{W}"/>',
             f'<w:p xmlns:w="{W}"/>'],
            include_sectPr=True,
        )
        with tmp:
            insert_tree_root = Path(tmp.name)
            with tempfile.TemporaryDirectory() as base_dir:
                base_tree_root = Path(base_dir)
                (base_tree_root / "word").mkdir()
                clones, _report = _extract_insert_paragraphs(
                    insert_tree_root, base_tree_root,
                )
        self.assertEqual(len(clones), 2, "Expected 2 paragraphs (sectPr stripped)")
        from lxml import etree as _etree
        for el in clones:
            self.assertNotEqual(
                _etree.QName(el).localname, "sectPr",
                "sectPr must not appear in result",
            )

    def test_extract_relocates_image(self):
        """docx-008 R10.b → GREEN: r:embed on inserted body now relocated;
        NO WARNING; rId rewritten to base-side; report.rels_appended ≥ 1."""
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        # Build insert tree with a paragraph whose <a:blip r:embed="rId7">
        # references an image, AND the insert rels file declaring rId7.
        para_xml = (
            f'<w:p xmlns:w="{W}" xmlns:r="{R}">'
            f'<w:r><w:drawing>'
            f'<a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:embed="rId7"/>'
            f'</w:drawing></w:r>'
            f'</w:p>'
        )
        tmp = _build_insert_tree([para_xml])
        with tmp:
            insert_tree_root = Path(tmp.name)
            # Add insert rels file with rId7 → media/img.png
            insert_rels = (insert_tree_root / "word" / "_rels"
                           / "document.xml.rels")
            insert_rels.parent.mkdir(parents=True, exist_ok=True)
            PR_NS_LOCAL = "http://schemas.openxmlformats.org/package/2006/relationships"
            insert_rels.write_text(
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="{PR_NS_LOCAL}">'
                f'<Relationship Id="rId7" Type="{R}/image" Target="media/img.png"/>'
                f'</Relationships>'
            )
            # Add the insert image bytes.
            insert_media = insert_tree_root / "word" / "media"
            insert_media.mkdir()
            (insert_media / "img.png").write_bytes(b"PNGDATA")

            with tempfile.TemporaryDirectory() as base_dir:
                base_tree_root = Path(base_dir)
                (base_tree_root / "word").mkdir()
                stderr_buf = io.StringIO()
                import contextlib
                with contextlib.redirect_stderr(stderr_buf):
                    clones, report = _extract_insert_paragraphs(
                        insert_tree_root, base_tree_root,
                    )
                # Assertion 1: no WARNING emitted.
                self.assertNotIn(
                    "[docx_replace] WARNING", stderr_buf.getvalue(),
                    "R10.b WARNING line must be deleted in docx-008",
                )
                # Assertion 2: relocator report shows ≥ 1 media + ≥ 1 rels.
                self.assertGreaterEqual(report.media_copied, 1)
                self.assertGreaterEqual(report.rels_appended, 1)
                self.assertGreaterEqual(report.rid_rewrites, 1)
                # Assertion 3: clone's r:embed was rewritten to a different rId.
                embed_attr = f"{{{R}}}embed"
                live_embeds = [
                    el.get(embed_attr) for el in clones[0].iter()
                    if embed_attr in el.attrib
                ]
                self.assertEqual(len(live_embeds), 1)
                self.assertNotEqual(
                    live_embeds[0], "rId7",
                    "r:embed should have been remapped from insert-side rId7",
                )
                # Assertion 4: the image file was copied to base.
                copied = list((base_tree_root / "word" / "media").iterdir())
                self.assertEqual(len(copied), 1)
                self.assertTrue(copied[0].name.startswith("insert_"))
                self.assertEqual(copied[0].read_bytes(), b"PNGDATA")

    def test_do_insert_after_first_match(self):
        """First anchor match: 2 insert paragraphs appear after matched <w:p>; count==1."""
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        from lxml import etree as _etree
        # Build base tree with one paragraph containing anchor.
        base_tmp = _build_minimal_tree([[({}, "Article 5. Content")]])
        # Build 2 insert paragraphs.
        p1 = _etree.fromstring(f'<w:p xmlns:w="{W}"><w:r><w:t>Inserted A</w:t></w:r></w:p>')
        p2 = _etree.fromstring(f'<w:p xmlns:w="{W}"><w:r><w:t>Inserted B</w:t></w:r></w:p>')
        insert_paragraphs = [p1, p2]
        with base_tmp as tmp_name:
            tree_root = Path(tmp_name)
            count = _do_insert_after(
                tree_root, "Article 5.", insert_paragraphs, anchor_all=False
            )
            self.assertEqual(count, 1)
            # Read back the document and verify order.
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            texts = [t.text or "" for t in doc.findall(f".//{{{W}}}t")]
            # Should have original + "Inserted A" + "Inserted B"
            self.assertIn("Inserted A", texts)
            self.assertIn("Inserted B", texts)
            # Verify order: anchor para comes before inserted paragraphs.
            all_paras = doc.findall(f".//{{{W}}}p")
            anchor_idx = next(
                (i for i, p in enumerate(all_paras) if "Article 5." in (
                    "".join(t.text or "" for t in p.findall(f".//{{{W}}}t"))
                )),
                None,
            )
            self.assertIsNotNone(anchor_idx, "Anchor paragraph must be present")
            self.assertGreater(len(all_paras), anchor_idx + 2,
                               "Two inserted paragraphs must follow anchor")

    def test_do_insert_after_all_duplicates(self):
        """--all: anchor in 3 paragraphs → 6 new paragraphs total; deep-clone independent."""
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        from lxml import etree as _etree
        # Build base tree with 3 paragraphs each containing anchor.
        base_tmp = _build_minimal_tree([
            [({}, "Anchor text here")],
            [({}, "Anchor text here also")],
            [({}, "Anchor text here again")],
        ])
        p1 = _etree.fromstring(f'<w:p xmlns:w="{W}"><w:r><w:t>Clone Para 1</w:t></w:r></w:p>')
        p2 = _etree.fromstring(f'<w:p xmlns:w="{W}"><w:r><w:t>Clone Para 2</w:t></w:r></w:p>')
        insert_paragraphs = [p1, p2]
        with base_tmp as tmp_name:
            tree_root = Path(tmp_name)
            count = _do_insert_after(
                tree_root, "Anchor text", insert_paragraphs, anchor_all=True
            )
            self.assertEqual(count, 3, "Expected 3 anchor matches")
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            all_paras = doc.findall(f".//{{{W}}}p")
            # 3 originals + 3×2 = 9 total
            self.assertEqual(len(all_paras), 9, f"Expected 9 paragraphs total, got {len(all_paras)}")
            # Verify deep-clone independence: mutate a found "Clone Para 1" text;
            # other clones should be unaffected.
            clone_paras = [
                p for p in all_paras
                if "Clone Para 1" in "".join(t.text or "" for t in p.findall(f".//{{{W}}}t"))
            ]
            self.assertEqual(len(clone_paras), 3, "Expected 3 clones of 'Clone Para 1'")
            # Mutate the first clone's text element.
            first_t = clone_paras[0].find(f".//{{{W}}}t")
            if first_t is not None:
                first_t.text = "MUTATED"
            # Confirm siblings are not mutated.
            for other in clone_paras[1:]:
                other_t = other.find(f".//{{{W}}}t")
                self.assertIsNotNone(other_t)
                self.assertNotEqual(
                    other_t.text, "MUTATED",
                    "Deep clone must be independent — mutating one must not affect siblings",
                )


# ── TestDeleteParagraphAction ─────────────────────────────────────────────────

def _build_doc_xml_raw(body_xml: str) -> bytes:
    """Build word/document.xml bytes with a fully-formed body via raw XML string."""
    from lxml import etree as _etree
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    doc = _etree.Element(f"{{{W}}}document")
    body = _etree.fromstring(body_xml)
    doc.append(body)
    return _etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_tree(tree_root, body_xml: str) -> None:
    """Write word/document.xml and [Content_Types].xml into tree_root."""
    word_dir = tree_root / "word"
    word_dir.mkdir(exist_ok=True)
    (word_dir / "document.xml").write_bytes(_build_doc_xml_raw(body_xml))
    (tree_root / "[Content_Types].xml").write_bytes(
        _make_ct_xml([("/word/document.xml", _WP_DOC_CT)])
    )


@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestDeleteParagraphAction(unittest.TestCase):
    """``--delete-paragraph`` action (UC-3).

    Flipped GREEN in task-006-06.
    """

    _W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def _para(self, text: str) -> str:
        W = self._W
        return (
            f'<w:p xmlns:w="{W}"><w:r><w:t>{text}</w:t></w:r></w:p>'
        )

    def test_delete_body_paragraph(self):
        """Fixture body has 5 paragraphs (P1..P5); anchor matches P3;
        after delete, body has 4 paragraphs and P3 text is gone."""
        from lxml import etree as _etree
        W = self._W
        body_xml = (
            f'<w:body xmlns:w="{W}">'
            + "".join(self._para(f"P{i}") for i in range(1, 6))
            + "</w:body>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _write_tree(tree_root, body_xml)
            count = _do_delete_paragraph(tree_root, "P3", anchor_all=False)
            self.assertEqual(count, 1)
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            paras = doc.findall(f".//{{{W}}}p")
            self.assertEqual(len(paras), 4)
            texts = "".join(t.text or "" for t in doc.findall(f".//{{{W}}}t"))
            self.assertNotIn("P3", texts)

    def test_delete_all_matches(self):
        """3 paragraphs each contain anchor; with anchor_all=True all 3 removed;
        count == 3."""
        from lxml import etree as _etree
        W = self._W
        body_xml = (
            f'<w:body xmlns:w="{W}">'
            + self._para("PREFIX anchor SUFFIX")
            + self._para("anchor standalone")
            + self._para("anchor again")
            + self._para("unrelated paragraph")
            + "</w:body>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _write_tree(tree_root, body_xml)
            count = _do_delete_paragraph(tree_root, "anchor", anchor_all=True)
            self.assertEqual(count, 3)
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            paras = doc.findall(f".//{{{W}}}p")
            self.assertEqual(len(paras), 1)

    def test_delete_last_body_paragraph_refused(self):
        """Body with exactly one paragraph; _do_delete_paragraph raises
        LastParagraphCannotBeDeleted (R10.c lock)."""
        W = self._W
        body_xml = (
            f'<w:body xmlns:w="{W}">'
            + self._para("ONLY PARAGRAPH HERE")
            + "</w:body>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _write_tree(tree_root, body_xml)
            with self.assertRaises(LastParagraphCannotBeDeleted) as ctx:
                _do_delete_paragraph(tree_root, "ONLY PARAGRAPH", anchor_all=False)
            self.assertEqual(ctx.exception.details.get("anchor"), "ONLY PARAGRAPH")

    def test_delete_table_cell_paragraph_inserts_placeholder(self):
        """Paragraph in <w:tc> removed; cell has exactly one empty <w:p/>
        placeholder afterwards (Q-A5). Body paragraph count unchanged
        (body still has 1 <w:p>; the guard does NOT fire)."""
        from lxml import etree as _etree
        W = self._W
        body_xml = (
            f'<w:body xmlns:w="{W}">'
            + self._para("placeholder body para")
            + f'<w:tbl xmlns:w="{W}"><w:tr><w:tc>'
            + self._para("DEPRECATED CLAUSE")
            + "</w:tc></w:tr></w:tbl>"
            + "</w:body>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _write_tree(tree_root, body_xml)
            count = _do_delete_paragraph(
                tree_root, "DEPRECATED CLAUSE", anchor_all=False
            )
            self.assertEqual(count, 1)
            doc = _etree.parse(str(tree_root / "word" / "document.xml")).getroot()
            # Find the tc
            tcs = doc.findall(f".//{{{W}}}tc")
            self.assertEqual(len(tcs), 1)
            tc = tcs[0]
            tc_paras = tc.findall(f"{{{W}}}p")
            self.assertEqual(len(tc_paras), 1, "tc must have exactly 1 <w:p> placeholder")
            # Placeholder must be empty (no <w:r> children)
            placeholder = tc_paras[0]
            self.assertEqual(len(list(placeholder)), 0, "Placeholder <w:p> must have no children")

    def test_delete_with_sectPr_at_body_tail_does_not_count_sectPr(self):
        """Body has <w:p>foo</w:p><w:p>bar</w:p><w:sectPr/>.
        Delete anchor 'foo' succeeds (sectPr not counted, body still has 1 <w:p>).
        Then deleting 'bar' (the only remaining <w:p>) raises LastParagraphCannotBeDeleted."""
        from lxml import etree as _etree
        W = self._W
        body_xml = (
            f'<w:body xmlns:w="{W}">'
            + self._para("foo")
            + self._para("bar")
            + f'<w:sectPr xmlns:w="{W}"/>'
            + "</w:body>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _write_tree(tree_root, body_xml)
            # First deletion succeeds
            count = _do_delete_paragraph(tree_root, "foo", anchor_all=False)
            self.assertEqual(count, 1)
            # Second deletion: only "bar" remains; should raise
            with self.assertRaises(LastParagraphCannotBeDeleted):
                _do_delete_paragraph(tree_root, "bar", anchor_all=False)


# ── TestCli ──────────────────────────────────────────────────────────────────

class TestCli(unittest.TestCase):
    """CLI argument parsing and output-path handling.

    test_build_parser_7_flags flipped GREEN in task-006-03.
    Remaining methods flip GREEN in task-006-07a.
    """

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_build_parser_7_flags(self):
        """build_parser() registers INPUT, OUTPUT positionals + 7 flags."""
        parser = build_parser()
        # Collect all option strings and positional dest names
        option_strings: set[str] = set()
        positional_dests: set[str] = set()
        for action in parser._actions:
            if action.option_strings:
                option_strings.update(action.option_strings)
            else:
                positional_dests.add(action.dest)
        # Positionals
        self.assertIn("input", positional_dests, "positional INPUT missing")
        self.assertIn("output", positional_dests, "positional OUTPUT missing")
        # Flags
        self.assertIn("--anchor", option_strings, "--anchor missing")
        self.assertIn("--replace", option_strings, "--replace missing")
        self.assertIn("--insert-after", option_strings, "--insert-after missing")
        self.assertIn("--delete-paragraph", option_strings, "--delete-paragraph missing")
        self.assertIn("--all", option_strings, "--all missing")
        self.assertIn("--unpacked-dir", option_strings, "--unpacked-dir missing")
        self.assertIn("--json-errors", option_strings, "--json-errors missing")

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_unpacked_dir_forbids_positional(self):
        """--unpacked-dir combined with INPUT/OUTPUT positionals → exit 2 + UsageError envelope.

        R4.b lock: combining --unpacked-dir with positional args is refused.
        Verified via subprocess so real stderr is captured (report_error binds
        sys.stderr at import time and is not affected by redirect_stderr).
        """
        import json
        scripts_dir = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [
                sys.executable, "docx_replace.py",
                "a.docx", "b.docx",
                "--unpacked-dir", "/tmp/x",
                "--anchor", "x",
                "--delete-paragraph",
                "--json-errors",
            ],
            capture_output=True,
            text=True,
            cwd=str(scripts_dir),
        )
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}; stderr={result.stderr!r}")
        stderr_text = result.stderr.strip()
        try:
            envelope = json.loads(stderr_text)
        except json.JSONDecodeError:
            self.fail(f"stderr is not valid JSON: {stderr_text!r}")
        self.assertEqual(
            envelope.get("type"), "UsageError",
            f"Expected type=UsageError in envelope, got: {envelope}",
        )

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_mutex_group_rejects_two_actions(self):
        """Two of {--replace, --insert-after, --delete-paragraph} → exit 2 UsageError (R4.a)."""
        parser = build_parser()
        with self.assertRaises(SystemExit) as cm:
            parser.parse_args([
                "in.docx", "out.docx",
                "--anchor", "x",
                "--replace", "y",
                "--delete-paragraph",
            ])
        self.assertEqual(cm.exception.code, 2)

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_missing_action_usage_error(self):
        """No action flag → argparse UsageError / exit 2."""
        rc = main(["in.docx", "out.docx", "--anchor", "x"])
        self.assertEqual(rc, 2)

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_output_extension_preserved_r8k(self):
        """Output path extension is preserved as-is (R8.k); .docm stays .docm."""
        import tempfile
        from pathlib import Path
        # Use the docm fixture from examples/ (skill root, not scripts/).
        skill_dir = Path(__file__).resolve().parent.parent.parent
        fixture = skill_dir / "examples" / "docx_replace_body.docm"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.docm"
            rc = main([
                str(fixture), str(out),
                "--anchor", "May 2024",
                "--replace", "June 2025",
            ])
            self.assertEqual(rc, 0, "Expected successful replace on .docm input")
            self.assertTrue(out.exists(), "Output file must exist")
            self.assertEqual(out.suffix, ".docm", "Output extension must be .docm (R8.k)")


# ── TestPostValidate ──────────────────────────────────────────────────────────

class TestPostValidate(unittest.TestCase):
    """Post-operation validation gate (office.validate subprocess).

    Flipped GREEN in task-006-07a.
    """

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_env_truthy_enables_validator(self):
        """DOCX_REPLACE_POST_VALIDATE env truthy → _post_validate_enabled() returns True."""
        truthy_values = {"1", "true", "yes", "on", "True", "ON", "Yes"}
        falsy_values = {"", "0", "no", "off", "foo"}
        for val in truthy_values:
            with mock.patch.dict("os.environ", {"DOCX_REPLACE_POST_VALIDATE": val}):
                self.assertTrue(
                    _post_validate_enabled(),
                    f"Expected True for DOCX_REPLACE_POST_VALIDATE={val!r}",
                )
        for val in falsy_values:
            with mock.patch.dict("os.environ", {"DOCX_REPLACE_POST_VALIDATE": val}):
                self.assertFalse(
                    _post_validate_enabled(),
                    f"Expected False for DOCX_REPLACE_POST_VALIDATE={val!r}",
                )

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_validator_failure_unlinks_output_exit7(self):
        """Validator exit non-zero → output file unlinked + PostValidateFailed raised."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.docx"
            out.write_bytes(b"fake docx content")
            scripts_dir = Path(tmp)
            fake_result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="INVALID",
            )
            with mock.patch("subprocess.run", return_value=fake_result):
                with self.assertRaises(PostValidateFailed) as ctx:
                    _run_post_validate(out, scripts_dir)
            self.assertFalse(out.exists(), "Output must be unlinked on validate failure")
            exc = ctx.exception
            self.assertEqual(exc.code, 7)
            self.assertIn("INVALID", exc.details.get("stderr", ""))

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_env_unset_no_subprocess(self):
        """DOCX_REPLACE_POST_VALIDATE unset → no office.validate subprocess spawned.

        NOTE: The unit tests test_validator_failure_unlinks_output_exit7 and
        the timeout variant provide the primary R9 coverage. An E2E sabotage
        test would require patching office.validate in-process, which is not
        straightforward from shell. The unit tests are considered sufficient.
        """
        import tempfile
        from pathlib import Path
        skill_dir = Path(__file__).resolve().parent.parent.parent
        fixture = skill_dir / "examples" / "docx_replace_body.docx"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")
        # Remove the env var to ensure it's unset.
        env_without_var = {
            k: v for k, v in __import__("os").environ.items()
            if k != "DOCX_REPLACE_POST_VALIDATE"
        }
        with mock.patch.dict("os.environ", env_without_var, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "result.docx"
                with mock.patch("subprocess.run", wraps=subprocess.run) as mock_run:
                    rc = main([
                        str(fixture), str(out),
                        "--anchor", "May 2024",
                        "--replace", "June 2025",
                    ])
                self.assertEqual(rc, 0)
                # Verify no call to office.validate was made.
                for call in mock_run.call_args_list:
                    args = call[0][0] if call[0] else call[1].get("args", [])
                    cmd_str = " ".join(str(a) for a in args)
                    self.assertNotIn(
                        "office.validate", cmd_str,
                        "office.validate must NOT be called when env var is unset",
                    )

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_pack_validate_replace_pattern(self):
        """FIX-6 regression: pack writes to tmpdir → on validate failure,
        final output file must NOT exist (atomic os.replace never reached)."""
        import argparse
        examples_dir = Path(__file__).resolve().parent.parent.parent / "examples"
        fixture = examples_dir / "docx_replace_body.docx"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")
        with tempfile.TemporaryDirectory() as tmp:
            final_out = Path(tmp) / "result.docx"
            args = argparse.Namespace(
                input=str(fixture),
                output=str(final_out),
                unpacked_dir=None,
                anchor="May 2024",
                replace="June 2025",
                insert_after=None,
                delete_paragraph=False,
                all=False,
                json_errors=False,
            )
            # Patch _run_post_validate to raise PostValidateFailed, and
            # enable the post-validate gate via env var.
            with mock.patch.dict("os.environ",
                                  {"DOCX_REPLACE_POST_VALIDATE": "1"}):
                with mock.patch("docx_replace._run_post_validate",
                                side_effect=PostValidateFailed(
                                    "synthetic failure", code=7,
                                    error_type="PostValidateFailed",
                                    details={},
                                )):
                    with self.assertRaises(PostValidateFailed):
                        _run(args)
            # Final output must NOT exist (os.replace was never called).
            self.assertFalse(
                final_out.exists(),
                "Final output must not exist when post-validate fails "
                "(pack-to-tmpdir + atomic replace pattern)",
            )

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_run_post_validate_timeout_unlinks_output(self):
        """TimeoutExpired → PostValidateFailed with details['reason']=='timeout' + output unlinked."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.docx"
            out.write_bytes(b"fake docx content")
            scripts_dir = Path(tmp)
            with mock.patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60),
            ):
                with self.assertRaises(PostValidateFailed) as ctx:
                    _run_post_validate(out, scripts_dir)
            self.assertFalse(out.exists(), "Output must be unlinked on timeout")
            exc = ctx.exception
            self.assertEqual(exc.code, 7)
            self.assertEqual(exc.details.get("reason"), "timeout")

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_cross_filesystem_replace_falls_back_to_shutil_move(self):
        """FIX-6 follow-up: when os.replace raises EXDEV (cross-fs mount),
        shutil.move must be called and the output must land at the correct path.

        Simulates Linux CI where /tmp (tmpdir) is on tmpfs and the output
        destination is on a different filesystem mount (EXDEV errno 18).
        """
        import errno as _errno
        examples_dir = Path(__file__).resolve().parent.parent.parent / "examples"
        fixture = examples_dir / "docx_replace_body.docx"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")

        move_calls: list[tuple[str, str]] = []

        def fake_move(src: str, dst: str) -> None:
            """Record call and actually copy the file so the output exists."""
            import shutil as _shutil
            move_calls.append((src, dst))
            _shutil.copy2(src, dst)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "result.docx"
            # Patch os.replace to raise EXDEV (cross-device link error).
            exdev_exc = OSError(_errno.EXDEV, "Invalid cross-device link")
            with mock.patch("docx_replace.os.replace", side_effect=exdev_exc), \
                 mock.patch("docx_replace.shutil.move", side_effect=fake_move):
                rc = main([
                    str(fixture), str(out_path),
                    "--anchor", "May 2024",
                    "--replace", "April 2025",
                ])
            self.assertEqual(rc, 0, "main() must return 0 even on EXDEV fallback")
            self.assertTrue(out_path.exists(), "Output file must exist after shutil.move fallback")
            self.assertEqual(len(move_calls), 1, "shutil.move must be called exactly once")
            # dst must be the requested output path.
            self.assertEqual(move_calls[0][1], str(out_path))


# ── TestLibraryMode ───────────────────────────────────────────────────────────

@unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
class TestLibraryMode(unittest.TestCase):
    """Library-mode (in-process, no temp files) dispatch.

    Flipped GREEN in task-006-07b.
    """

    def _get_examples_dir(self):
        """Return the skill examples/ directory."""
        skill_dir = Path(__file__).resolve().parent.parent.parent
        return skill_dir / "examples"

    def test_library_mode_dispatch_first(self):
        """Library-mode: --unpacked-dir dispatches action without calling pack.

        UC-4 acceptance: pre-unpack the fixture, build a Namespace with
        unpacked_dir set and input/output=None, run _run(args), assert:
          1. office.pack is NOT called (library caller owns persistence).
          2. The action ran: anchor paragraph deleted from word/document.xml.
        """
        from unittest import mock
        import argparse
        examples_dir = self._get_examples_dir()
        fixture = examples_dir / "docx_replace_body.docx"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            # Unpack the fixture into the tmp dir.
            from office.unpack import unpack as _unpack  # type: ignore
            _unpack(fixture, tree_root)
            # Verify word/document.xml exists.
            doc_xml = tree_root / "word" / "document.xml"
            self.assertTrue(doc_xml.is_file(), "Fixture did not unpack correctly")
            # Count paragraphs containing "May 2024" before deletion.
            from lxml import etree as _etree
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            doc_before = _etree.parse(str(doc_xml)).getroot()
            paras_before = [
                p for p in doc_before.findall(f".//{{{W}}}p")
                if "May 2024" in "".join(t.text or "" for t in p.findall(f".//{{{W}}}t"))
            ]
            self.assertGreater(len(paras_before), 0, "Fixture must contain 'May 2024' paragraph")
            # Build argparse Namespace for library-mode deletion.
            args = argparse.Namespace(
                unpacked_dir=str(tree_root),
                input=None,
                output=None,
                anchor="May 2024",
                replace=None,
                insert_after=None,
                delete_paragraph=True,
                all=False,
                json_errors=False,
            )
            # Patch office.pack to confirm it is NOT called.
            with mock.patch("docx_replace.pack") as mock_pack:
                rc = _run(args)
            self.assertEqual(rc, 0, "Library mode should return 0 on success")
            mock_pack.assert_not_called()
            # Verify the paragraph was deleted from the tree on disk.
            doc_after = _etree.parse(str(doc_xml)).getroot()
            paras_after = [
                p for p in doc_after.findall(f".//{{{W}}}p")
                if "May 2024" in "".join(t.text or "" for t in p.findall(f".//{{{W}}}t"))
            ]
            self.assertEqual(len(paras_after), 0, "'May 2024' paragraph must be deleted from tree")

    def test_library_mode_missing_document_xml(self):
        """--unpacked-dir pointing at dir without word/document.xml → NotADocxTree.

        The details dict must contain 'dir' matching the given directory.
        """
        import argparse
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            # Do NOT create word/document.xml — empty dir.
            args = argparse.Namespace(
                unpacked_dir=str(tree_root),
                input=None,
                output=None,
                anchor="x",
                replace=None,
                insert_after=None,
                delete_paragraph=True,
                all=False,
                json_errors=False,
            )
            with self.assertRaises(NotADocxTree) as ctx:
                _run(args)
            exc = ctx.exception
            self.assertEqual(exc.code, 1)
            self.assertIn(
                str(tree_root.resolve()),
                exc.details.get("dir", ""),
                f"details['dir'] should contain the tree_root path, got: {exc.details}",
            )

    def test_library_mode_insert_after_does_not_pollute_user_tree(self):
        """2026-05-12 scratch-leak regression-lock for library mode.

        `_run_library_mode` passes the user's `tree_root` and an internal
        `_tempdir()` as two SEPARATE directories to `_dispatch_action`.
        This is structurally correct (no alias), but a careless future
        refactor could re-introduce the alias. Lock the invariant: after
        a successful `--unpacked-dir` + `--insert-after` call, the
        user's tree must contain NO scratch artefacts at the top level.
        """
        import argparse
        examples_dir = self._get_examples_dir()
        fixture = examples_dir / "docx_replace_body.docx"
        if not fixture.is_file():
            self.skipTest(f"Fixture not found: {fixture}")

        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            from office.unpack import unpack as _unpack  # type: ignore
            _unpack(fixture, tree_root)
            # Snapshot top-level entries before the call.
            before = {p.name for p in tree_root.iterdir()}

            md_path = tree_root.parent / "lib_insert.md"
            md_path.write_text("Library-mode insert.\n", encoding="utf-8")

            args = argparse.Namespace(
                unpacked_dir=str(tree_root),
                input=None, output=None,
                anchor="Article 5.",
                replace=None,
                insert_after=str(md_path),
                delete_paragraph=False,
                all=False,
                json_errors=False,
            )
            rc = _run(args)
            self.assertEqual(rc, 0, "Library-mode insert-after must succeed")

            after = {p.name for p in tree_root.iterdir()}
            new_entries = after - before
            # The action mutates word/document.xml in place; no top-level
            # entries should appear (insert.docx / insert_unpacked /
            # stdin.md must land in the internal _tempdir(), not here).
            self.assertEqual(
                new_entries, set(),
                f"Library mode polluted user tree: new top-level "
                f"entries {new_entries} appeared. The tempdir alias bug "
                "from zip-mode must not creep into library mode.",
            )


# ── TestHonestScopeLocks ──────────────────────────────────────────────────────

class TestHonestScopeLocks(unittest.TestCase):
    """Honest-scope boundary locks (D6/B, R10, A4, NIT-3, Q-U1).

    Flipped GREEN in task-006-08.
    These tests encode the "honest scope" design decisions so that
    future refactoring cannot accidentally remove them.
    """

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _examples_dir() -> Path:
        """Return the skill examples/ directory."""
        return Path(__file__).resolve().parent.parent.parent / "examples"

    @staticmethod
    def _scripts_dir() -> Path:
        """Return the skill scripts/ directory."""
        return Path(__file__).resolve().parent.parent

    @staticmethod
    def _make_minimal_png(path: Path) -> None:
        """Write a minimal valid 8×8 red PNG to path."""
        try:
            from PIL import Image  # type: ignore
            img = Image.new("RGB", (8, 8), color=(255, 0, 0))
            img.save(str(path))
        except ImportError:
            import struct
            import zlib

            def _chunk(tag: bytes, data: bytes) -> bytes:
                crc = zlib.crc32(tag + data) & 0xFFFFFFFF
                return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
            # 8 rows of 8 RGB pixels = 8 * (1 filter byte + 8*3 bytes)
            raw = b""
            for _ in range(8):
                raw += b"\x00" + b"\xff\x00\x00" * 8
            idat = _chunk(b"IDAT", zlib.compress(raw))
            iend = _chunk(b"IEND", b"")
            path.write_bytes(sig + ihdr + idat + iend)

    @staticmethod
    def _run_md2docx(md_path: Path, out_docx: Path) -> bool:
        """Run md2docx.js; return True if output exists and non-empty."""
        import subprocess as _sp
        scripts = Path(__file__).resolve().parent.parent
        result = _sp.run(
            ["node", str(scripts / "md2docx.js"), str(md_path), str(out_docx)],
            shell=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and out_docx.is_file() and out_docx.stat().st_size > 0

    # ── R10.a: cross-run anchor not found ───────────────────────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_cross_run_anchor_returns_anchor_not_found(self):
        """Anchor spanning a formatting boundary → AnchorNotFound (R10.a).

        Regression lock for the honest-scope limitation D6/B:
        only intra-run anchors are matched; cross-run search is
        not attempted because it requires run-splitting which risks
        corrupting complex formatting.

        Fixture: "**May** 2024" markdown → bold <w:r> "May" + plain <w:r> " 2024".
        Different rPr keys → _merge_adjacent_runs cannot coalesce.
        → _do_replace returns 0 → _run raises AnchorNotFound → exit 2.
        Cross-5 envelope must include details["anchor"] == "May 2024".
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "cross_run.md"
            out_docx = t / "cross_run.docx"
            md_path.write_text("**May** 2024\n", encoding="utf-8")
            ok = self._run_md2docx(md_path, out_docx)
            if not ok:
                self.skipTest("md2docx.js not available; skipping R10.a E2E")

            result_docx = t / "result.docx"
            rc = main([
                str(out_docx), str(result_docx),
                "--anchor", "May 2024",
                "--replace", "April 2025",
                "--json-errors",
            ])
            self.assertEqual(rc, 2, "Expected exit 2 (AnchorNotFound) for cross-run anchor")
            # Output file must NOT exist (pack never reached).
            self.assertFalse(result_docx.exists(),
                             "Output must not be written when anchor not found")

    # ── R10.b: image-bearing MD → warning + no live r:embed ─────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_image_relocated_no_warning(self):
        """docx-008 R10.b → GREEN. MD insert source with image →
        image is relocated into base/word/media/insert_*; rId rewritten
        to base-side; NO WARNING; output validates."""
        examples = self._examples_dir()
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            png_path = t / "real_image.png"
            self._make_minimal_png(png_path)
            md_path = t / "img_source.md"
            md_path.write_text(
                f"# Image heading\n\n![test image]({png_path})\n",
                encoding="utf-8",
            )
            out_docx = t / "result.docx"

            import io, contextlib
            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                rc = main([
                    str(base_docx), str(out_docx),
                    "--anchor", "Article 5.",
                    "--insert-after", str(md_path),
                ])

            stderr_text = stderr_buf.getvalue()
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}; stderr={stderr_text!r}")
            # Assertion 1: no R10.b WARNING line.
            self.assertNotIn(
                "[docx_replace] WARNING", stderr_text,
                "R10.b WARNING line must be deleted in docx-008",
            )
            # Assertion 2: success line carries the [relocated K media ...] suffix.
            self.assertIn("[relocated", stderr_text)
            # Assertion 3: image relocated to base/word/media/insert_*.
            from office.unpack import unpack  # type: ignore
            unpack_dir = t / "unpacked_out"
            unpack_dir.mkdir()
            unpack(out_docx, unpack_dir)
            media_dir = unpack_dir / "word" / "media"
            self.assertTrue(media_dir.is_dir())
            insert_media = [
                p for p in media_dir.iterdir()
                if p.name.startswith("insert_")
            ]
            self.assertGreaterEqual(
                len(insert_media), 1,
                "expected ≥ 1 relocated media file with insert_ prefix",
            )
            # Assertion 4: doc.xml r:embed values RESOLVE in base rels
            # (the opposite of R10.b honest-scope assertion).
            doc_xml = (unpack_dir / "word" / "document.xml").read_text()
            rels_path = unpack_dir / "word" / "_rels" / "document.xml.rels"
            rels_text = rels_path.read_text() if rels_path.is_file() else ""
            import re
            base_rids = set(re.findall(r'Id="(rId[^"]+)"', rels_text))
            embed_vals = set(re.findall(r'r:embed="([^"]+)"', doc_xml))
            # All r:embed values in doc MUST resolve in base rels.
            unresolved = embed_vals - base_rids
            self.assertEqual(
                unresolved, set(),
                f"All r:embed values must resolve in base rels; unresolved={unresolved}",
            )

    # ── R10.c: last paragraph refused ───────────────────────────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_last_paragraph_guard_single_delete(self):
        """Single --delete-paragraph on last body paragraph → exit 2 (R10.c).

        Fixture: a .docx generated from a single-paragraph markdown.
        _do_delete_paragraph raises LastParagraphCannotBeDeleted.
        Output file must NOT exist (pack never reached).
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "single.md"
            src_docx = t / "single.docx"
            md_path.write_text("ONLY PARAGRAPH HERE\n", encoding="utf-8")
            ok = self._run_md2docx(md_path, src_docx)
            if not ok:
                self.skipTest("md2docx.js not available; skipping R10.c E2E")

            out_docx = t / "result.docx"
            rc = main([
                str(src_docx), str(out_docx),
                "--anchor", "ONLY PARAGRAPH",
                "--delete-paragraph",
                "--json-errors",
            ])
            self.assertEqual(rc, 2, "Expected exit 2 (LastParagraphCannotBeDeleted)")
            self.assertFalse(
                out_docx.exists(),
                "Output file must NOT exist when delete is refused",
            )

    # ── R10.d: --all delete trips last-paragraph guard ──────────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_all_delete_paragraph_last_paragraph_guard_wins(self):
        """--all --delete-paragraph: last-paragraph guard still triggered (R10.d).

        Fixture: a .docx generated from markdown with 3 paragraphs each
        containing "the". --all --delete-paragraph --anchor "the" trips the
        last-paragraph guard mid-loop when body shrinks to 1 paragraph.
        → exit 2 LastParagraphCannotBeDeleted. Output file must NOT exist.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "the_fixture.md"
            src_docx = t / "the_fixture.docx"
            md_path.write_text(
                "This is the first paragraph.\n\n"
                "This is the second paragraph.\n\n"
                "This is the third paragraph.\n",
                encoding="utf-8",
            )
            ok = self._run_md2docx(md_path, src_docx)
            if not ok:
                self.skipTest("md2docx.js not available; skipping R10.d E2E")

            out_docx = t / "result.docx"
            rc = main([
                str(src_docx), str(out_docx),
                "--anchor", "the",
                "--delete-paragraph",
                "--all",
                "--json-errors",
            ])
            self.assertEqual(rc, 2, "Expected exit 2 (LastParagraphCannotBeDeleted) mid-loop")
            self.assertFalse(
                out_docx.exists(),
                "Output file must NOT exist when guard trips mid-loop",
            )

    # ── R10.e: numId is now RELOCATED, no warning (docx-008) ────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_numbering_relocated_no_warning(self):
        """docx-008 R10.e → GREEN. List-producing markdown produces inserted
        numId; numbering.xml installed verbatim in base (if base had none) OR
        merged with offset; NO WARNING."""
        examples = self._examples_dir()
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "list.md"
            md_path.write_text("# Heading\n\n1. step one\n2. step two\n", encoding="utf-8")
            out_docx = t / "result.docx"
            import io, contextlib
            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                rc = main([
                    str(base_docx), str(out_docx),
                    "--anchor", "Article 5.",
                    "--insert-after", str(md_path),
                ])
            stderr_text = stderr_buf.getvalue()
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}; stderr={stderr_text!r}")
            # Assertion 1: no R10.e WARNING.
            self.assertNotIn(
                "[docx_replace] WARNING", stderr_text,
                "R10.e WARNING line must be deleted in docx-008",
            )
            # Assertion 2: output has <w:numId> in document.xml AND <w:num>
            # def in numbering.xml.
            from office.unpack import unpack  # type: ignore
            unpack_dir = t / "unpacked"
            unpack_dir.mkdir()
            unpack(out_docx, unpack_dir)
            doc_xml = (unpack_dir / "word" / "document.xml").read_text()
            self.assertIn("w:numId", doc_xml, "inserted paragraph should reference numId")
            num_xml_path = unpack_dir / "word" / "numbering.xml"
            self.assertTrue(num_xml_path.is_file(), "base should have numbering.xml")

    @unittest.skip("R10.e WARNING deleted in docx-008; replaced by test_numbering_relocated_no_warning above")
    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_numid_survives_replace(self):
        """<w:numId> in inserted list items survives; stderr warns when base
        has no word/numbering.xml (R10.e).

        Fixture: insert-source MD with "1. list item" → md2docx produces
        <w:numId> in output. Base docx has word/numbering.xml DELETED before
        invocation. After --insert-after:
          - stderr contains "[docx_replace] WARNING: inserted body contains
            <w:numId>" (R10.e warning).
          - Exit code 0 (warn-and-proceed).
          - Output unpack contains <w:numId> in word/document.xml (not stripped).
        """
        import zipfile
        import shutil
        import io, contextlib
        from lxml import etree as _etree

        examples = self._examples_dir()
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # Build insert source: a list-producing markdown
            md_path = t / "list_source.md"
            md_path.write_text("1. list item\n", encoding="utf-8")

            # Build base without numbering.xml: copy body.docx → strip numbering.xml
            base_no_num = t / "base_no_num.docx"
            with zipfile.ZipFile(str(base_docx), "r") as zin:
                parts = {n: zin.read(n) for n in zin.namelist()}
            # Remove numbering.xml if present (may not exist in this fixture)
            parts.pop("word/numbering.xml", None)
            # Also remove from Content_Types
            ct = parts.get("[Content_Types].xml", b"").decode("utf-8")
            if "numbering" in ct:
                import re
                ct = re.sub(r'<Override[^>]*numbering\.xml[^/]*/>', "", ct)
                parts["[Content_Types].xml"] = ct.encode("utf-8")
            # Also remove from rels
            rels_key = "word/_rels/document.xml.rels"
            if rels_key in parts:
                rels = parts[rels_key].decode("utf-8")
                if "numbering" in rels:
                    rels = re.sub(r'<Relationship[^>]*numbering\.xml[^/]*/>', "", rels)
                    parts[rels_key] = rels.encode("utf-8")
            with zipfile.ZipFile(str(base_no_num), "w", zipfile.ZIP_DEFLATED) as zout:
                for name, data in parts.items():
                    zout.writestr(name, data)

            out_docx = t / "result.docx"
            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                rc = main([
                    str(base_no_num), str(out_docx),
                    "--anchor", "Article 5.",
                    "--insert-after", str(md_path),
                ])

            stderr_text = stderr_buf.getvalue()
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}; stderr={stderr_text!r}")
            self.assertIn(
                "[docx_replace] WARNING: inserted body contains <w:numId>",
                stderr_text,
                "Expected <w:numId> warning in stderr",
            )
            # Verify output docx contains <w:numId> (not stripped).
            self.assertTrue(out_docx.exists(), "Output docx must be created")
            from office.unpack import unpack  # type: ignore
            unpack_dir = t / "unpacked_out"
            unpack_dir.mkdir()
            unpack(out_docx, unpack_dir)
            doc_xml = (unpack_dir / "word" / "document.xml").read_text()
            self.assertIn(
                "<w:numId",
                doc_xml,
                "<w:numId> must be present in output (not stripped)",
            )

    # ── 2026-05-12 scratch-leak fix: ZIP must contain only OOXML parts ───────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_insert_after_zip_contains_only_ooxml_parts(self):
        """2026-05-12 scratch-leak regression-lock: --insert-after must
        not pack scratch artefacts into the final OOXML container.

        Real-world reproducer: inserting an image via --insert-after on a
        plain docx produced a package with `insert.docx` and
        `insert_unpacked/` at the archive root. Microsoft Word refuses
        to open such packages ("содержимое не удалось прочитать");
        LibreOffice and `office.validate` both tolerated them silently.

        Whitelist-based assertion: every ZIP entry MUST start with one of
        the canonical OOXML package prefixes. Black-listing known scratch
        filenames would silently miss any future scratch artefact whose
        name happens to be different.
        """
        import zipfile
        examples = self._examples_dir()
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "insert.md"
            md_path.write_text("New paragraph.\n", encoding="utf-8")
            out_docx = t / "result.docx"
            rc = main([
                str(base_docx), str(out_docx),
                "--anchor", "Article 5.",
                "--insert-after", str(md_path),
            ])
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}")
            self.assertTrue(out_docx.exists(), "Output docx must be created")

            # ECMA-376 §11.3.10: package members MUST live under the
            # canonical part hierarchy. Top-level admits only
            # `[Content_Types].xml` and the package-rels file
            # `_rels/.rels`; all other parts MUST be under `_rels/`,
            # `word/` (or peer `xl/`, `ppt/`), `docProps/`, or
            # `customXml/`. Any other entry is a scratch leak.
            allowed_prefixes = (
                "[Content_Types].xml",
                "_rels/",
                "word/",
                "docProps/",
                "customXml/",
            )
            with zipfile.ZipFile(str(out_docx), "r") as zf:
                names = zf.namelist()
            for name in names:
                self.assertTrue(
                    any(name.startswith(p) for p in allowed_prefixes),
                    f"Non-OOXML entry leaked into ZIP: {name!r}. "
                    f"Allowed prefixes: {allowed_prefixes}. "
                    "This breaks Word's open-time integrity check "
                    "(2026-05-12 scratch-leak regression).",
                )

    # ── Q-U1: tracked insertion matched, tracked deletion ignored ────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_qu1_tracked_ins_matched_del_ignored(self):
        """Q-U1: <w:ins> content matched by anchor search; <w:del> content invisible.

        Two sub-cases:
          (a) docx_replace_tracked_ins.docx: paragraph has <w:ins><w:r><w:t>FOO...
              → --anchor "FOO" --replace "BAR" succeeds (exit 0).
          (b) docx_replace_tracked_del.docx: paragraph has <w:del><w:r><w:delText>FOO...
              → --anchor "FOO" --delete-paragraph returns AnchorNotFound (exit 2).

        Verifies _concat_paragraph_text INCLUDES <w:ins> and EXCLUDES <w:del>.
        The fixtures are pre-built by tests/build_tracked_change_fixture.py.
        """
        examples = self._examples_dir()
        ins_fixture = examples / "docx_replace_tracked_ins.docx"
        del_fixture = examples / "docx_replace_tracked_del.docx"

        if not ins_fixture.is_file() or not del_fixture.is_file():
            self.skipTest(
                "Tracked-change fixtures not found; run "
                "tests/build_tracked_change_fixture.py first"
            )

        # Sub-case (a): <w:ins> → anchor found, replace succeeds.
        with tempfile.TemporaryDirectory() as tmp:
            out_ins = Path(tmp) / "ins_result.docx"
            rc_ins = main([
                str(ins_fixture), str(out_ins),
                "--anchor", "FOO",
                "--replace", "BAR",
            ])
            self.assertEqual(
                rc_ins, 0,
                "<w:ins> content must be visible to anchor search (exit 0 expected)",
            )
            self.assertTrue(out_ins.exists(), "Output must be written on successful replace")

        # Sub-case (b): <w:del> → anchor NOT found, AnchorNotFound exit 2.
        with tempfile.TemporaryDirectory() as tmp:
            out_del = Path(tmp) / "del_result.docx"
            rc_del = main([
                str(del_fixture), str(out_del),
                "--anchor", "FOO",
                "--delete-paragraph",
                "--json-errors",
            ])
            self.assertEqual(
                rc_del, 2,
                "<w:del> content must be INVISIBLE to anchor search (exit 2 / AnchorNotFound expected)",
            )
            self.assertFalse(
                out_del.exists(),
                "Output must NOT be written when anchor not found",
            )

    # ── A4 TOCTOU: symlink resolves to same path ─────────────────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_a4_toctou_symlink_race_acceptance(self):
        """A4 TOCTOU: _assert_distinct_paths catches symlink → same inode (A4).

        In tmp_path: create real.docx; create alias.docx as symlink to real.docx.
        Even though literal paths differ, Path.resolve(strict=False) normalises
        both to the same real path.
        → Expected: exit 6 SelfOverwriteRefused.

        Acceptance note (mirroring xlsx-2 ARCH §10 precedent):
        This test covers the same-path-via-symlink case in the HAPPY path.
        The actual TOCTOU race (symlink rewritten between resolve() and open())
        is NOT regression-tested here — that requires a controlled filesystem
        race harness and is documented as an accepted v1 limitation.
        """
        examples = self._examples_dir()
        # We need a real (non-zero) .docx to use as input; borrow body fixture.
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # Copy fixture so we have a real.docx in tmp.
            import shutil
            real_docx = t / "real.docx"
            shutil.copy(str(base_docx), str(real_docx))
            # Create alias.docx as a symlink pointing to real.docx.
            alias_docx = t / "alias.docx"
            alias_docx.symlink_to(real_docx)

            rc = main([
                str(real_docx), str(alias_docx),
                "--anchor", "May 2024",
                "--replace", "April 2025",
                "--json-errors",
            ])
            self.assertEqual(
                rc, 6,
                "Expected exit 6 (SelfOverwriteRefused) when output symlinks to input; "
                "Path.resolve() must normalise both to the same path.",
            )

    # ── R1.g E2E: xml:space='preserve' on replaced <w:t> ────────────────────

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_r1g_xml_space_preserve_e2e(self):
        """R1.g E2E: xml:space='preserve' set when replacement has leading/trailing space.

        Fixture: single-run paragraph with anchor "MARKER". Replace with " leading space".
        Verify that the output <w:t> element has xml:space="preserve" attribute.
        (Without the attribute, Word trims leading/trailing whitespace on render.)
        """
        from lxml import etree as _etree
        from office.unpack import unpack  # type: ignore

        examples = self._examples_dir()
        base_docx = examples / "docx_replace_body.docx"
        if not base_docx.is_file():
            self.skipTest(f"Base fixture not found: {base_docx}")

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            md_path = t / "marker.md"
            src_docx = t / "marker.docx"
            md_path.write_text("MARKER\n", encoding="utf-8")
            ok = self._run_md2docx(md_path, src_docx)
            if not ok:
                self.skipTest("md2docx.js not available; skipping R1.g E2E")

            out_docx = t / "result.docx"
            rc = main([
                str(src_docx), str(out_docx),
                "--anchor", "MARKER",
                "--replace", " leading space",
            ])
            self.assertEqual(rc, 0, f"Expected exit 0, got {rc}")
            self.assertTrue(out_docx.exists(), "Output must be written")

            # Unpack and verify xml:space="preserve" on the replaced <w:t>.
            unpack_dir = t / "unpacked_out"
            unpack_dir.mkdir()
            unpack(out_docx, unpack_dir)
            doc_xml = (unpack_dir / "word" / "document.xml").read_text()
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            XML_NS = "http://www.w3.org/XML/1998/namespace"
            doc_root = _etree.parse(str(unpack_dir / "word" / "document.xml")).getroot()
            t_elements = doc_root.findall(f".//{{{W}}}t")
            space_preserve_found = any(
                el.get(f"{{{XML_NS}}}space") == "preserve"
                for el in t_elements
            )
            self.assertTrue(
                space_preserve_found,
                "Expected xml:space='preserve' on a <w:t> in output when replacement "
                "has leading whitespace (R1.g)",
            )


class TestPathTraversal(unittest.TestCase):
    """G11 (docx-008): malicious insert rels with traversal Target →
    Md2DocxOutputInvalid (exit 1). Tests are defence-in-depth + faster
    debug for the shell-E2E case `T-docx-insert-after-path-traversal`."""

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_relocator_rejects_parent_segment_target(self) -> None:
        # Directly invoke the relocator with a crafted malicious insert tree.
        from _relocator import relocate_assets
        from _app_errors import Md2DocxOutputInvalid
        base = Path(tempfile.mkdtemp(prefix="docx-pt-base-"))
        insert = Path(tempfile.mkdtemp(prefix="docx-pt-insert-"))
        try:
            (base / "word").mkdir()
            (insert / "word" / "_rels").mkdir(parents=True)
            R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            PR = "http://schemas.openxmlformats.org/package/2006/relationships"
            (insert / "word" / "_rels" / "document.xml.rels").write_text(
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="{PR}">'
                f'<Relationship Id="rId1" Type="{R}/image" Target="../../../etc/passwd"/>'
                f'</Relationships>'
            )
            with self.assertRaises(Md2DocxOutputInvalid) as ctx:
                relocate_assets(insert, base, [])
            self.assertEqual(ctx.exception.details["reason"], "parent_segment")
        finally:
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(insert, ignore_errors=True)

    @unittest.skipUnless(_DOCX_REPLACE_AVAILABLE, "docx_replace not yet importable")
    def test_relocator_rejects_absolute_target(self) -> None:
        from _relocator import relocate_assets
        from _app_errors import Md2DocxOutputInvalid
        base = Path(tempfile.mkdtemp(prefix="docx-pt-abs-base-"))
        insert = Path(tempfile.mkdtemp(prefix="docx-pt-abs-insert-"))
        try:
            (base / "word").mkdir()
            (insert / "word" / "_rels").mkdir(parents=True)
            R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            PR = "http://schemas.openxmlformats.org/package/2006/relationships"
            (insert / "word" / "_rels" / "document.xml.rels").write_text(
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="{PR}">'
                f'<Relationship Id="rId1" Type="{R}/image" Target="/etc/passwd"/>'
                f'</Relationships>'
            )
            with self.assertRaises(Md2DocxOutputInvalid) as ctx:
                relocate_assets(insert, base, [])
            self.assertEqual(ctx.exception.details["reason"], "absolute_or_empty")
        finally:
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(insert, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
