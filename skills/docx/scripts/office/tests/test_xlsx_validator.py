"""Unit tests for `XlsxValidator`.

Builds minimal `.xlsx` archives in memory and verifies the validator
flags each documented integrity problem (missing sheet part, duplicate
sheet name / sheetId, out-of-range shared-string indices,
out-of-range cell-style indices, orphan worksheets) while leaving a
clean package with no errors.

Run from inside the skill:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_xlsx_validator
"""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent
sys.path.insert(0, str(SCRIPTS))

from office.validators.xlsx import XlsxValidator  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal-xlsx builder
# ---------------------------------------------------------------------------

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

_PKG_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rIdSheet1"/>
  </sheets>
</workbook>
"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdSheet1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rIdSST" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
  <Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

_SHEET_PLAIN = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><v>42</v></c></row>
  </sheetData>
</worksheet>
"""

# 1 shared string, 1 cellXf — defined together so tests can extend.
_SHARED_STRINGS_ONE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">
  <si><t>hello</t></si>
</sst>
"""

_STYLES_ONE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cellXfs count="1"><xf/></cellXfs>
</styleSheet>
"""

_BASE_PARTS: dict[str, str] = {
    "[Content_Types].xml": _CONTENT_TYPES,
    "_rels/.rels": _PKG_RELS,
    "xl/workbook.xml": _WORKBOOK,
    "xl/_rels/workbook.xml.rels": _WORKBOOK_RELS,
    "xl/worksheets/sheet1.xml": _SHEET_PLAIN,
    "xl/sharedStrings.xml": _SHARED_STRINGS_ONE,
    "xl/styles.xml": _STYLES_ONE,
}


def _build_xlsx(parts: dict[str, str | bytes]) -> Path:
    import os
    import tempfile
    fd, name = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for path, body in parts.items():
            data = body.encode("utf-8") if isinstance(body, str) else body
            z.writestr(path, data)
    return Path(name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestXlsxValidatorClean(unittest.TestCase):
    def test_clean_minimal_xlsx_validates(self) -> None:
        path = _build_xlsx(_BASE_PARTS)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertFalse(report.errors, report.errors)


class TestXlsxValidatorInstanceIsolation(unittest.TestCase):
    """Regression for VDD iter-4 HIGH: `xsd_map` was a class-level
    mutable dict (shared across instances)."""

    def test_xsd_map_is_per_instance(self) -> None:
        v1 = XlsxValidator()
        v2 = XlsxValidator()
        self.assertIsNot(v1.xsd_map, v2.xsd_map)
        self.assertIsNot(v1.xsd_map, XlsxValidator.xsd_map)

    def test_dynamic_add_does_not_leak(self) -> None:
        v1 = XlsxValidator()
        v1.xsd_map["xl/worksheets/sheet99.xml"] = "sml.xsd"
        v2 = XlsxValidator()
        self.assertNotIn("xl/worksheets/sheet99.xml", v2.xsd_map)
        self.assertNotIn("xl/worksheets/sheet99.xml", XlsxValidator.xsd_map)


class TestXlsxValidatorSheetChain(unittest.TestCase):
    def test_missing_sheet_part_is_an_error(self) -> None:
        parts = dict(_BASE_PARTS)
        del parts["xl/worksheets/sheet1.xml"]
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "missing part" in e and "sheet1" in e for e in report.errors
        ), report.errors)

    def test_orphan_worksheet_warns(self) -> None:
        parts = dict(_BASE_PARTS)
        parts["xl/worksheets/sheet42.xml"] = _SHEET_PLAIN
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "Orphan sheet part" in w and "sheet42.xml" in w
            for w in report.warnings
        ), report.warnings)

    def test_orphan_chartsheet_warns(self) -> None:
        # Regression for VDD iter-4 MED: orphan detection used to look
        # only at xl/worksheets/, missing chartsheets and dialogsheets.
        parts = dict(_BASE_PARTS)
        parts["xl/chartsheets/sheet1.xml"] = (
            '<chartsheet xmlns='
            '"http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "Orphan sheet part" in w and "chartsheets/sheet1.xml" in w
            for w in report.warnings
        ), report.warnings)


class TestXlsxValidatorSheetUniqueness(unittest.TestCase):
    def test_duplicate_sheet_name_is_an_error(self) -> None:
        bad = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Data" sheetId="1" r:id="rIdSheet1"/>
    <sheet name="Data" sheetId="2" r:id="rIdSheet1"/>
  </sheets>
</workbook>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/workbook.xml"] = bad
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "duplicate sheet name 'Data'" in e for e in report.errors
        ), report.errors)

    def test_case_insensitive_duplicate_sheet_name_is_an_error(self) -> None:
        # Regression for VDD iter-4 MED: Excel folds case when
        # comparing sheet names — `Sheet1` + `SHEET1` is rejected at
        # open time. We use a unique sheetId/r:id to keep the OTHER
        # uniqueness checks from masking this one.
        bad = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rIdSheet1"/>
    <sheet name="SHEET1" sheetId="2" r:id="rIdSheet2"/>
  </sheets>
</workbook>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/workbook.xml"] = bad
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "duplicate sheet name 'SHEET1'" in e and "case-insensitive" in e
            for e in report.errors
        ), report.errors)

    def test_zero_sheet_workbook_is_an_error(self) -> None:
        # Regression for VDD iter-4 MED: empty <workbook/> was silently
        # accepted; Excel rejects it with "the workbook contains no
        # sheets".
        empty_wb = (
            '<?xml version="1.0"?><workbook '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
        parts = dict(_BASE_PARTS)
        parts["xl/workbook.xml"] = empty_wb
        del parts["xl/worksheets/sheet1.xml"]
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "no <sheet> elements" in e for e in report.errors
        ), report.errors)

    def test_duplicate_sheetid_is_an_error(self) -> None:
        bad = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="A" sheetId="7" r:id="rIdSheet1"/>
    <sheet name="B" sheetId="7" r:id="rIdSheet1"/>
  </sheets>
</workbook>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/workbook.xml"] = bad
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "duplicate sheetId '7'" in e for e in report.errors
        ), report.errors)


class TestXlsxValidatorRelsAndPaths(unittest.TestCase):
    """Regressions for VDD iter-4 MED — diagnostic quality + path
    normalization."""

    def test_missing_workbook_rels_says_so(self) -> None:
        parts = dict(_BASE_PARTS)
        del parts["xl/_rels/workbook.xml.rels"]
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        # Old wording was "parse error 'There is no item named ...'" —
        # confusing because the file isn't a parse-error-prone file,
        # it's missing entirely.
        self.assertTrue(any(
            "relationship file missing from package" in e
            for e in report.errors
        ), report.errors)

    def test_percent_encoded_target_resolves(self) -> None:
        from office.validators.base import _resolve_zip_path
        # OPC says Target is a URI reference. ZIP namelist holds the
        # decoded form, so our resolver must percent-decode.
        self.assertEqual(
            _resolve_zip_path("xl", "worksheets/sheet%201.xml"),
            "xl/worksheets/sheet 1.xml",
        )

    def test_backslash_target_normalised(self) -> None:
        from office.validators.base import _resolve_zip_path
        # Some legacy writers emit Windows-style separators.
        self.assertEqual(
            _resolve_zip_path("xl", "worksheets\\sheet1.xml"),
            "xl/worksheets/sheet1.xml",
        )


class TestXlsxValidatorSharedStringIndex(unittest.TestCase):
    def test_oob_sst_index_is_an_error(self) -> None:
        # sharedStrings has 1 entry → only index 0 is valid.
        # Cell B1 references index 5 → out of range.
        bad_sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>5</v></c>
    </row>
  </sheetData>
</worksheet>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/worksheets/sheet1.xml"] = bad_sheet
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "sst index 5 out of range" in e and "B1" in e
            for e in report.errors
        ), report.errors)

    def test_t_shared_string_without_v_is_an_error(self) -> None:
        # Regression for VDD iter-4 MED: <c t="s"></c> (no <v> child)
        # was silently accepted; ECMA-376 §18.3.1.4 requires <v>.
        bad_sheet = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="s"></c></row></sheetData>
</worksheet>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/worksheets/sheet1.xml"] = bad_sheet
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "no <v> child" in e and "A1" in e for e in report.errors
        ), report.errors)

    def test_sst_reference_without_part_is_an_error(self) -> None:
        # Cell uses t="s" but xl/sharedStrings.xml is missing.
        parts = dict(_BASE_PARTS)
        del parts["xl/sharedStrings.xml"]
        parts["xl/worksheets/sheet1.xml"] = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>
</worksheet>
"""
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "sharedStrings.xml is absent" in e for e in report.errors
        ), report.errors)


class TestXlsxValidatorStyleIndex(unittest.TestCase):
    def test_oob_style_index_is_an_error(self) -> None:
        # styles.xml has 1 cellXf → only s="0" is valid.
        bad_sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" s="9"><v>1</v></c></row></sheetData>
</worksheet>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/worksheets/sheet1.xml"] = bad_sheet
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "style index 9 out of range" in e and "A1" in e
            for e in report.errors
        ), report.errors)

    def test_empty_cellxfs_message_is_distinct(self) -> None:
        # Regression for VDD iter-4 MED: when cellXfs is empty, every
        # <c s="N"> previously produced "out of range [0, 0)" — true
        # but cryptic. We now special-case the message.
        empty_styles = (
            '<?xml version="1.0"?><styleSheet '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
        bad_sheet = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" s="0"><v>1</v></c></row></sheetData>
</worksheet>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/styles.xml"] = empty_styles
        parts["xl/worksheets/sheet1.xml"] = bad_sheet
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "no <cellXfs> entries" in e and "A1" in e
            for e in report.errors
        ), report.errors)


class TestXlsxValidatorDefinedNames(unittest.TestCase):
    def test_duplicate_defined_name_is_an_error(self) -> None:
        bad = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rIdSheet1"/>
  </sheets>
  <definedNames>
    <definedName name="MyRange">Sheet1!$A$1</definedName>
    <definedName name="MyRange">Sheet1!$B$1</definedName>
  </definedNames>
</workbook>
"""
        parts = dict(_BASE_PARTS)
        parts["xl/workbook.xml"] = bad
        path = _build_xlsx(parts)
        try:
            report = XlsxValidator().validate(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(any(
            "duplicate definedName 'MyRange'" in e for e in report.errors
        ), report.errors)


if __name__ == "__main__":
    unittest.main()
