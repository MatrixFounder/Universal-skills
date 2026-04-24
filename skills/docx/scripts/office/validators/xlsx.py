"""XLSX-specific extensions of the base OOXML validator.

Stub — only structural checks for now. Extend as XLSX-specific edit
scenarios surface (formula error scanning, shared-strings integrity,
styles workbook, etc.). In the meantime, `xlsx_validate.py` at the
skill level handles the common case of error-cell scanning.
"""

from __future__ import annotations

from .base import BaseSchemaValidator


class XlsxValidator(BaseSchemaValidator):
    expected_parts = (
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    )
    xsd_map = {
        "xl/workbook.xml": "sml.xsd",
    }
