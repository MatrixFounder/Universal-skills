"""DOCX-specific extensions of the base OOXML validator."""

from __future__ import annotations

import zipfile

from lxml import etree  # type: ignore

from .base import BaseSchemaValidator, ValidationReport, _safe_parser


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class DocxValidator(BaseSchemaValidator):
    expected_parts = (
        "word/document.xml",
        "word/_rels/document.xml.rels",
    )
    xsd_map = {
        "word/document.xml": "wml.xsd",
    }

    def _validate_container(self, archive: zipfile.ZipFile, report: ValidationReport) -> None:
        super()._validate_container(archive, report)
        if "word/document.xml" in archive.namelist():
            try:
                doc = etree.fromstring(archive.read("word/document.xml"), _safe_parser())
            except etree.XMLSyntaxError as exc:
                report.errors.append(f"word/document.xml: parse error {exc}")
                return
            self._check_tracked_change_integrity(doc, report)
            self._check_comment_markers(doc, report)

    def _check_tracked_change_integrity(self, doc: etree._Element, report: ValidationReport) -> None:
        for el in doc.iter(f"{{{W_NS}}}del"):
            for t in el.iter(f"{{{W_NS}}}t"):
                report.warnings.append(
                    "Found <w:t> inside <w:del>; expected <w:delText> "
                    "(ECMA-376 Part 1 §17.13.5.15)"
                )
                break
        for el in doc.iter(f"{{{W_NS}}}ins"):
            for t in el.iter(f"{{{W_NS}}}delText"):
                report.warnings.append(
                    "Found <w:delText> inside <w:ins>; expected <w:t>"
                )
                break

    def _check_comment_markers(self, doc: etree._Element, report: ValidationReport) -> None:
        starts = {
            el.get(f"{{{W_NS}}}id")
            for el in doc.iter(f"{{{W_NS}}}commentRangeStart")
        }
        ends = {
            el.get(f"{{{W_NS}}}id")
            for el in doc.iter(f"{{{W_NS}}}commentRangeEnd")
        }
        refs = {
            el.get(f"{{{W_NS}}}id")
            for el in doc.iter(f"{{{W_NS}}}commentReference")
        }
        unmatched_start = starts - ends
        unmatched_end = ends - starts
        missing_ref = starts - refs
        for sid in unmatched_start:
            report.warnings.append(f"commentRangeStart id={sid} has no matching commentRangeEnd")
        for eid in unmatched_end:
            report.warnings.append(f"commentRangeEnd id={eid} has no matching commentRangeStart")
        for rid in missing_ref:
            report.warnings.append(f"commentRangeStart id={rid} has no commentReference")
