"""PPTX-specific extensions of the base OOXML validator.

Stub — only structural checks for now. Extend with slide-relationship
consistency checks, layout/master validation, and notes-slide
integrity when those scenarios arise.
"""

from __future__ import annotations

from .base import BaseSchemaValidator


class PptxValidator(BaseSchemaValidator):
    expected_parts = (
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
    )
    xsd_map = {
        "ppt/presentation.xml": "pml.xsd",
    }
