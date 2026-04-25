#!/usr/bin/env python3
"""Fill `{{placeholder}}` values in a .docx template from JSON data.

Handles Word's habit of splitting a single run of text across multiple
`<w:r>` elements (common after spell-check or autocorrect passes). Without
run normalization, a placeholder like `{{name}}` can end up stored as
`{{` + `na` + `me` + `}}` and never match a regex. We first walk each
paragraph and merge adjacent runs that share identical formatting, then
apply substitutions.

Placeholders follow Jinja-like syntax: `{{key}}` or `{{key.subkey}}`.
Conditionals and loops are NOT supported — this script does plain
variable substitution. For complex templating use docxtpl or write
your own DOCX assembler via python-docx.

Usage:
    python docx_fill_template.py template.docx data.json output.docx

Exit codes:
    0 — filled successfully
    1 — missing file, invalid JSON, or unresolved required placeholder
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from docx import Document  # type: ignore
from docx.oxml.ns import qn  # type: ignore
from lxml import etree  # type: ignore

from office._encryption import EncryptedFileError, assert_not_encrypted


PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _rpr_key(run_element: etree._Element) -> bytes:
    """Stable identity for a run's formatting.

    Two runs share the same key iff their `<w:rPr>` subtrees are
    byte-identical after canonical XML serialization. Empty rPr (no
    formatting) is treated as its own identity.
    """
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        return b""
    return etree.tostring(rpr, method="c14n")


def _merge_adjacent_runs(paragraph_elem: etree._Element) -> None:
    """Merge adjacent `<w:r>` siblings that share identical `<w:rPr>`.

    Only simple text runs are merged — any run containing elements other
    than `<w:rPr>` and `<w:t>` (e.g. breaks, drawings, fields) is left
    alone so we don't corrupt non-text content.
    """
    runs = paragraph_elem.findall(qn("w:r"))
    i = 0
    while i < len(runs) - 1:
        a, b = runs[i], runs[i + 1]
        if not _is_simple_text_run(a) or not _is_simple_text_run(b):
            i += 1
            continue
        if _rpr_key(a) != _rpr_key(b):
            i += 1
            continue

        a_t = a.find(qn("w:t"))
        b_t = b.find(qn("w:t"))
        if a_t is None or b_t is None:
            i += 1
            continue

        a_t.text = (a_t.text or "") + (b_t.text or "")
        # Preserve leading/trailing whitespace when merged.
        if " " in (a_t.text or ""):
            a_t.set(
                "{http://www.w3.org/XML/1998/namespace}space",
                "preserve",
            )
        b.getparent().remove(b)
        runs = paragraph_elem.findall(qn("w:r"))
    return None


def _is_simple_text_run(run_element: etree._Element) -> bool:
    for child in run_element:
        tag = etree.QName(child).localname
        if tag not in {"rPr", "t"}:
            return False
    return True


def _resolve(data: dict[str, Any], key_path: str) -> str | None:
    value: Any = data
    for part in key_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _fill_paragraph(paragraph_elem: etree._Element, data: dict[str, Any], unresolved: set[str]) -> None:
    _merge_adjacent_runs(paragraph_elem)
    for text_elem in paragraph_elem.iter(qn("w:t")):
        original = text_elem.text or ""
        if "{{" not in original:
            continue

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = _resolve(data, key)
            if value is None:
                unresolved.add(key)
                return match.group(0)
            return value

        new_text = PLACEHOLDER_RE.sub(replace, original)
        if new_text != original:
            text_elem.text = new_text
            # Protect leading/trailing whitespace in substituted text.
            if new_text != new_text.strip():
                text_elem.set(
                    "{http://www.w3.org/XML/1998/namespace}space",
                    "preserve",
                )


def fill_template(template: Path, data: dict[str, Any], output: Path) -> set[str]:
    doc = Document(str(template))
    unresolved: set[str] = set()

    # Body paragraphs (including those nested inside tables).
    for paragraph in doc.paragraphs:
        _fill_paragraph(paragraph._p, data, unresolved)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _fill_paragraph(paragraph._p, data, unresolved)

    # Headers and footers.
    for section in doc.sections:
        for part in (section.header, section.footer, section.first_page_header,
                     section.first_page_footer, section.even_page_header, section.even_page_footer):
            if part is None:
                continue
            for paragraph in part.paragraphs:
                _fill_paragraph(paragraph._p, data, unresolved)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))
    return unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("template", type=Path, help="Source .docx template with {{placeholders}}")
    parser.add_argument("data", type=Path, help="JSON file with key/value substitutions")
    parser.add_argument("output", type=Path, help="Destination .docx file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any placeholder remains unresolved (default: warn, continue)",
    )
    args = parser.parse_args(argv)

    if not args.template.is_file():
        print(f"Template not found: {args.template}", file=sys.stderr)
        return 1
    if not args.data.is_file():
        print(f"Data file not found: {args.data}", file=sys.stderr)
        return 1
    try:
        assert_not_encrypted(args.template)
    except EncryptedFileError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.data}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("Data JSON must be an object at the top level.", file=sys.stderr)
        return 1

    unresolved = fill_template(args.template, data, args.output)
    if unresolved:
        joined = ", ".join(sorted(unresolved))
        print(f"Unresolved placeholders: {joined}", file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
