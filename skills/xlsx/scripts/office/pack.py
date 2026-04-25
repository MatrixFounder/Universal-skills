#!/usr/bin/env python3
"""Pack a directory tree previously produced by `unpack.py` back into an
OOXML (.docx/.xlsx/.pptx) file.

Steps:
1. Walk the directory tree and collect every file (preserving relative
   paths inside the ZIP).
2. For each `.xml`/`.rels` part:
   - Convert numeric entities that `unpack.py` inserted for smart quotes
     and dashes back into UTF-8 characters.
   - Optionally strip whitespace-only text nodes (the "condense" pass)
     so the final file matches Word's usual low-whitespace style.
3. Write the archive with `ZIP_DEFLATED`, preserving Content Types
   ordering (`[Content_Types].xml` must be the first member per
   ECMA-376 Part 2).

Usage (module):
    python -m office.pack unpacked_dir/ output.docx
Usage (script):
    python office/pack.py unpacked_dir/ output.docx
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from lxml import etree  # type: ignore

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from office._macros import (
        MACRO_EXT_FOR, NON_MACRO_EXTENSIONS, VBA_PROJECT_PARTS,
        format_macro_loss_warning,
    )
else:
    from ._macros import (
        MACRO_EXT_FOR, NON_MACRO_EXTENSIONS, VBA_PROJECT_PARTS,
        format_macro_loss_warning,
    )


SMART_REVERSE = {
    "&#x2018;": "‘",
    "&#x2019;": "’",
    "&#x201C;": "“",
    "&#x201D;": "”",
    "&#x2013;": "–",
    "&#x2014;": "—",
    "&#x2026;": "…",
}


def _is_xml_like(path: Path) -> bool:
    return path.suffix.lower() in {".xml", ".rels"}


def _unescape_smart(data: bytes) -> bytes:
    text = data.decode("utf-8")
    for entity, ch in SMART_REVERSE.items():
        text = text.replace(entity, ch)
    return text.encode("utf-8")


def _condense_xml(data: bytes) -> bytes:
    try:
        parser = etree.XMLParser(
            remove_blank_text=True,
            remove_comments=False,
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
        )
        tree = etree.fromstring(data, parser)
    except etree.XMLSyntaxError:
        return data
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)


def _ordered_members(root: Path) -> list[Path]:
    # ECMA-376 recommends [Content_Types].xml as the first member.
    members: list[Path] = []
    first: Path | None = None
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        if item.name == "[Content_Types].xml" and item.parent == root:
            first = item
        else:
            members.append(item)
    members.sort(key=lambda p: p.relative_to(root).as_posix())
    return ([first] + members) if first else members


def _tree_has_vba(input_dir: Path) -> bool:
    for part in VBA_PROJECT_PARTS:
        if (input_dir / part).is_file():
            return True
    return False


def pack(
    input_dir: Path,
    output_path: Path,
    *,
    unescape_smart_quotes: bool = True,
    condense: bool = True,
) -> None:
    if not input_dir.is_dir():
        raise ValueError(f"Not a directory: {input_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out_suffix = output_path.suffix.lower()
    if _tree_has_vba(input_dir) and out_suffix in NON_MACRO_EXTENSIONS:
        # We don't have an "input file" suffix here (pack works on a
        # tree), so synthesise the implied source extension from the
        # output by mapping it to its macro twin. Reusing the shared
        # `format_macro_loss_warning` keeps the wording in sync with
        # the writer-script warnings users see elsewhere.
        suggested = MACRO_EXT_FOR.get(out_suffix, out_suffix)
        sys.stderr.write(format_macro_loss_warning(
            in_suffix=suggested, out_suffix=out_suffix, suggested=suggested,
        ))
        sys.stderr.flush()

    members = _ordered_members(input_dir)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for member in members:
            relative = member.relative_to(input_dir).as_posix()
            data = member.read_bytes()
            if _is_xml_like(member):
                if unescape_smart_quotes:
                    data = _unescape_smart(data)
                if condense:
                    data = _condense_xml(data)
            archive.writestr(relative, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input_dir", type=Path, help="Unpacked directory tree")
    parser.add_argument("output", type=Path, help="Destination .docx/.xlsx/.pptx file")
    parser.add_argument("--no-unescape-quotes", action="store_true", help="Keep smart-quote entities as-is")
    parser.add_argument("--no-condense", action="store_true", help="Preserve whitespace in XML parts")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
        return 1
    try:
        pack(
            args.input_dir,
            args.output,
            unescape_smart_quotes=not args.no_unescape_quotes,
            condense=not args.no_condense,
        )
    except Exception as exc:
        print(f"Pack failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
