"""XLSX-specific extensions of the base OOXML validator.

Beyond the structural / relationship / id-uniqueness checks the base
class performs, this module verifies the SpreadsheetML graph is
internally consistent:

  1. **Sheet chain** — every `<sheet r:id="rId…">` in
     `xl/workbook.xml` resolves through `xl/_rels/workbook.xml.rels`
     to an existing `xl/worksheets/sheetN.xml` (or chartsheet, or
     dialogsheet).
  2. **Sheet name + sheetId uniqueness** — ECMA-376 §18.2.20 requires
     both attributes to be unique within `<sheets>`; Excel will refuse
     to open a workbook that violates either.
  3. **Defined-name uniqueness** — `<definedName name="…">` per
     `localSheetId`; duplicates are an Excel hard-fail.
  4. **SharedStrings index bounds** — every `<c t="s"><v>N</v></c>` in
     each worksheet must reference a `<si>` index that exists in
     `xl/sharedStrings.xml`. Out-of-range indices crash Excel's
     formula engine on first calc.
  5. **Cell style index bounds** — every `<c s="N">` must reference a
     `cellXfs` entry that exists in `xl/styles.xml`. Same failure
     mode as out-of-range strings.
  6. **Orphan parts** — worksheets on disk not referenced from the
     workbook's sheet list.

XSD binding (`xsd_map`) covers the workbook + per-worksheet parts.
The shared-strings and styles parts use a separate schema
(`sml.xsd` covers them too in ECMA-376 5th-ed); only the workbook is
bound by default to keep the per-file XSD load count manageable.

`xlsx_validate.py` at the skill level handles the orthogonal task of
formula-error scanning (`#REF!`/`#DIV/0!`/…), so we deliberately do
NOT duplicate that here.
"""

from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

from lxml import etree  # type: ignore

from .base import (
    BaseSchemaValidator, ValidationReport, _resolve_zip_path, _safe_parser,
)


S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_REL_TYPE_WORKSHEET = "/worksheet"
_REL_TYPE_CHARTSHEET = "/chartsheet"
_REL_TYPE_DIALOGSHEET = "/dialogsheet"
_REL_TYPE_SHAREDSTRINGS = "/sharedStrings"
_REL_TYPE_STYLES = "/styles"


class XlsxValidator(BaseSchemaValidator):
    expected_parts = (
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    )
    xsd_map = {
        "xl/workbook.xml": "sml.xsd",
        # Per-sheet entries are added on demand in
        # `_validate_against_xsd` so each container's sheet count is
        # covered without forcing the user to enumerate.
    }

    def _validate_container(
        self, archive: zipfile.ZipFile, report: ValidationReport
    ) -> None:
        super()._validate_container(archive, report)
        namelist = set(archive.namelist())
        if "xl/workbook.xml" not in namelist:
            return
        try:
            wb = etree.fromstring(archive.read("xl/workbook.xml"), _safe_parser())
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"xl/workbook.xml: parse error {exc}")
            return

        self._check_sheet_uniqueness(wb, report)
        self._check_defined_names(wb, report)
        sheet_targets = self._sheet_chain(archive, namelist, wb, report)
        ss_count = self._shared_strings_count(archive, namelist, report)
        styles_count = self._cell_xfs_count(archive, namelist, report)
        self._check_cell_indices(
            archive, namelist, sheet_targets, ss_count, styles_count, report,
        )
        self._check_orphan_sheets(namelist, sheet_targets, report)

    # ------------------------------------------------------------------
    # workbook.xml — sheets + definedNames structural rules
    # ------------------------------------------------------------------
    def _check_sheet_uniqueness(
        self, wb: etree._Element, report: ValidationReport
    ) -> None:
        # Excel folds case when comparing sheet names — `Sheet1` and
        # `SHEET1` are treated as identical and the workbook fails to
        # open. We mirror that by lower-casing before set membership;
        # the original (case-preserved) name is used in the error
        # message so the user sees what they wrote.
        seen_names_lc: set[str] = set()
        seen_sheet_ids: set[str] = set()
        seen_rids: set[str] = set()
        n_sheets = 0
        for sheet in wb.iter(f"{{{S_NS}}}sheet"):
            n_sheets += 1
            name = sheet.get("name")
            sheet_id = sheet.get("sheetId")
            rid = sheet.get(f"{{{R_NS}}}id")
            if name is None:
                report.errors.append(
                    "xl/workbook.xml: <sheet> missing @name"
                )
            elif name.lower() in seen_names_lc:
                report.errors.append(
                    f"xl/workbook.xml: duplicate sheet name '{name}' "
                    "(case-insensitive match — Excel refuses to open "
                    "this file)"
                )
            else:
                seen_names_lc.add(name.lower())
            if sheet_id is None:
                report.errors.append(
                    "xl/workbook.xml: <sheet> missing @sheetId"
                )
            elif sheet_id in seen_sheet_ids:
                report.errors.append(
                    f"xl/workbook.xml: duplicate sheetId '{sheet_id}'"
                )
            else:
                seen_sheet_ids.add(sheet_id)
            if rid is None:
                report.errors.append(
                    "xl/workbook.xml: <sheet> missing @r:id"
                )
            elif rid in seen_rids:
                report.errors.append(
                    f"xl/workbook.xml: duplicate r:id '{rid}' in <sheets>"
                )
            else:
                seen_rids.add(rid)
        # Excel rejects a workbook with no sheets ("Excel found
        # unreadable content"). Flag this loudly even though the rest
        # of our chain checks would silently pass on an empty list.
        if n_sheets == 0:
            report.errors.append(
                "xl/workbook.xml: no <sheet> elements (workbook must "
                "contain at least one sheet — Excel refuses to open "
                "an empty workbook)"
            )

    def _check_defined_names(
        self, wb: etree._Element, report: ValidationReport
    ) -> None:
        # definedName comparison is case-insensitive in Excel (same
        # rule as sheet names — see _check_sheet_uniqueness for the
        # rationale and message format).
        seen: set[tuple[str, str]] = set()
        for dn in wb.iter(f"{{{S_NS}}}definedName"):
            name = dn.get("name") or ""
            scope = dn.get("localSheetId") or "<workbook>"
            key = (scope, name.lower())
            if key in seen:
                report.errors.append(
                    f"xl/workbook.xml: duplicate definedName '{name}' "
                    f"in scope {scope} (case-insensitive match)"
                )
            seen.add(key)

    # ------------------------------------------------------------------
    # Relationship-graph helpers
    # ------------------------------------------------------------------
    def _read_rels(
        self,
        archive: zipfile.ZipFile,
        rels_path: str,
        report: ValidationReport,
    ) -> dict[str, tuple[str, str]]:
        try:
            raw = archive.read(rels_path)
        except KeyError:
            # File missing entirely — distinguish from a parse error so
            # the user doesn't go hunting for syntax issues in a file
            # that never existed.
            report.errors.append(
                f"{rels_path}: relationship file missing from package"
            )
            return {}
        try:
            root = etree.fromstring(raw, _safe_parser())
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"{rels_path}: parse error {exc}")
            return {}
        out: dict[str, tuple[str, str]] = {}
        base_dir = str(PurePosixPath(rels_path).parent.parent)
        for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            rid = rel.get("Id") or ""
            rtype = rel.get("Type") or ""
            mode = rel.get("TargetMode", "Internal")
            target = rel.get("Target") or ""
            if mode == "External" or not target or target.startswith("#"):
                continue
            out[rid] = (rtype, _resolve_zip_path(base_dir, target))
        return out

    def _sheet_chain(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        wb: etree._Element,
        report: ValidationReport,
    ) -> set[str]:
        """Resolve each `<sheet @r:id>` through the workbook rels and
        verify the worksheet part exists. Returns the set of resolved
        worksheet/chartsheet part paths."""
        rels = self._read_rels(archive, "xl/_rels/workbook.xml.rels", report)
        sheet_targets: set[str] = set()
        for sheet in wb.iter(f"{{{S_NS}}}sheet"):
            rid = sheet.get(f"{{{R_NS}}}id")
            if not rid:
                continue
            if rid not in rels:
                report.errors.append(
                    f"xl/workbook.xml: <sheet @name='{sheet.get('name','?')}' "
                    f"r:id='{rid}'> not declared in xl/_rels/workbook.xml.rels"
                )
                continue
            rtype, target = rels[rid]
            sheet_kinds = (
                _REL_TYPE_WORKSHEET, _REL_TYPE_CHARTSHEET, _REL_TYPE_DIALOGSHEET,
            )
            if not any(rtype.endswith(k) for k in sheet_kinds):
                report.warnings.append(
                    f"xl/workbook.xml: sheet '{sheet.get('name','?')}' "
                    f"r:id='{rid}' relationship has unexpected type '{rtype}'"
                )
            if target not in namelist:
                report.errors.append(
                    f"xl/workbook.xml: sheet '{sheet.get('name','?')}' "
                    f"→ rId '{rid}' → missing part '{target}'"
                )
                continue
            sheet_targets.add(target)
        return sheet_targets

    # ------------------------------------------------------------------
    # SharedStrings / Styles index bounds
    # ------------------------------------------------------------------
    def _shared_strings_count(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        report: ValidationReport,
    ) -> int | None:
        """Return the number of `<si>` entries in
        `xl/sharedStrings.xml`, or `None` if the part is absent (which
        is valid — workbooks without text cells skip it)."""
        if "xl/sharedStrings.xml" not in namelist:
            return None
        try:
            root = etree.fromstring(
                archive.read("xl/sharedStrings.xml"), _safe_parser()
            )
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"xl/sharedStrings.xml: parse error {exc}")
            return None
        return sum(1 for _ in root.iter(f"{{{S_NS}}}si"))

    def _cell_xfs_count(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        report: ValidationReport,
    ) -> int | None:
        """Return the number of `<xf>` entries inside
        `<cellXfs>` of `xl/styles.xml`, or `None` if absent.

        Excel uses this to resolve `<c s="N">` style references; out-
        of-range indices produce "the file is corrupted" on open.
        """
        if "xl/styles.xml" not in namelist:
            return None
        try:
            root = etree.fromstring(
                archive.read("xl/styles.xml"), _safe_parser()
            )
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"xl/styles.xml: parse error {exc}")
            return None
        cell_xfs = root.find(f"{{{S_NS}}}cellXfs")
        if cell_xfs is None:
            return 0
        return sum(1 for _ in cell_xfs.findall(f"{{{S_NS}}}xf"))

    def _check_cell_indices(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        sheets: set[str],
        ss_count: int | None,
        styles_count: int | None,
        report: ValidationReport,
    ) -> None:
        """For each worksheet, walk every `<c>` and verify shared-string
        and style indices are within bounds.
        """
        for sheet_part in sorted(sheets):
            # Chartsheets and dialogsheets don't have data cells —
            # skip them. Worksheet parts live under xl/worksheets/.
            if not sheet_part.startswith("xl/worksheets/"):
                continue
            try:
                doc = etree.fromstring(
                    archive.read(sheet_part), _safe_parser()
                )
            except etree.XMLSyntaxError as exc:
                report.errors.append(f"{sheet_part}: parse error {exc}")
                continue
            for c in doc.iter(f"{{{S_NS}}}c"):
                t_attr = c.get("t")
                s_attr = c.get("s")
                ref = c.get("r", "?")
                # Shared-string index check
                if t_attr == "s":
                    v = c.find(f"{{{S_NS}}}v")
                    if v is None or v.text is None:
                        # ECMA-376 §18.3.1.4 requires <v> for t='s'.
                        # Without it Excel shows blank and downstream
                        # tools (pandas read_excel) may raise.
                        report.errors.append(
                            f"{sheet_part}: cell {ref} has t='s' but "
                            "no <v> child (shared-string index "
                            "required by ECMA-376 §18.3.1.4)"
                        )
                    else:
                        try:
                            idx = int(v.text)
                        except ValueError:
                            report.errors.append(
                                f"{sheet_part}: cell {ref} type='s' "
                                f"but <v>{v.text}</v> is not an integer"
                            )
                            continue
                        if ss_count is None:
                            report.errors.append(
                                f"{sheet_part}: cell {ref} references "
                                "shared string but xl/sharedStrings.xml "
                                "is absent"
                            )
                        elif not (0 <= idx < ss_count):
                            report.errors.append(
                                f"{sheet_part}: cell {ref} sst index "
                                f"{idx} out of range [0, {ss_count})"
                            )
                # Style index check
                if s_attr is not None:
                    try:
                        s_idx = int(s_attr)
                    except ValueError:
                        report.errors.append(
                            f"{sheet_part}: cell {ref} has "
                            f"non-integer s='{s_attr}'"
                        )
                        continue
                    if styles_count is None:
                        report.warnings.append(
                            f"{sheet_part}: cell {ref} has style "
                            "index but xl/styles.xml is absent"
                        )
                    elif styles_count == 0:
                        # Distinct from "out of range [0, 0)" because
                        # the user otherwise has no idea WHY 0 is out
                        # of range. Real story: cellXfs is empty.
                        report.errors.append(
                            f"{sheet_part}: cell {ref} has style index "
                            f"{s_idx} but xl/styles.xml has no "
                            "<cellXfs> entries"
                        )
                    elif not (0 <= s_idx < styles_count):
                        report.errors.append(
                            f"{sheet_part}: cell {ref} style "
                            f"index {s_idx} out of range [0, {styles_count})"
                        )

    # ------------------------------------------------------------------
    # Orphan worksheets
    # ------------------------------------------------------------------
    def _check_orphan_sheets(
        self,
        namelist: set[str],
        sheets: set[str],
        report: ValidationReport,
    ) -> None:
        # All three sheet kinds (regular worksheet, chart sheet, dialog
        # sheet) live in their own subdirectory; orphans in any of them
        # bloat the package after manual editing.
        sheet_dirs = (
            "xl/worksheets/", "xl/chartsheets/", "xl/dialogsheets/",
        )
        on_disk = {
            n for n in namelist
            if any(n.startswith(d) for d in sheet_dirs)
            and n.endswith(".xml")
            and "/_rels/" not in n
        }
        orphans = sorted(on_disk - sheets)
        for orphan in orphans:
            report.warnings.append(
                f"Orphan sheet part '{orphan}' (not in workbook's <sheets>)"
            )

    # ------------------------------------------------------------------
    # XSD binding for sheets (extends parent's xsd_map dynamically)
    # ------------------------------------------------------------------
    def _validate_against_xsd(
        self,
        archive: zipfile.ZipFile,
        name: str,
        report: ValidationReport,
    ) -> None:
        # Bind SpreadsheetML parts to sml.xsd dynamically. Covers
        # regular worksheets + chart sheets + dialog sheets, plus the
        # shared strings and styles parts. Self.xsd_map is per-instance
        # (see BaseSchemaValidator.__init__) so no class-level leak.
        _SML_PREFIXES = (
            "xl/worksheets/sheet",
            "xl/chartsheets/sheet",
            "xl/dialogsheets/sheet",
        )
        if (name not in self.xsd_map and name.endswith(".xml") and (
                any(name.startswith(p) for p in _SML_PREFIXES)
                or name == "xl/sharedStrings.xml"
                or name == "xl/styles.xml")):
            self.xsd_map[name] = "sml.xsd"
        super()._validate_against_xsd(archive, name, report)
