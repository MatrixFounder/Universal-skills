#!/usr/bin/env python3
"""Unpack an OOXML (.docx/.xlsx/.pptx) container into a directory tree.

Each OOXML file is a ZIP archive of XML parts. This command:
1. Extracts every member into `output_dir/`.
2. Pretty-prints every `.xml` and `.rels` part with two-space indent so
   the tree is diff-friendly.
3. For DOCX: optionally runs `merge_runs` and `simplify_redlines` so the
   canonicalised tree plays nicely with text-oriented edits.
4. Rewrites common "smart" quotes and dashes in text nodes into numeric
   XML entities. Round-tripping these as-is through edit cycles is
   brittle because different editors handle UTF-8 vs. entity forms
   differently; encoding them as entities keeps the round trip
   deterministic. The inverse is applied by `pack.py`.

Usage (module):
    python -m office.unpack input.docx output_dir/ [--no-merge-runs] [--no-pretty]
Usage (script):
    python office/unpack.py input.docx output_dir/
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from defusedxml import minidom  # type: ignore
from lxml import etree  # type: ignore

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from office.helpers.merge_runs import merge_runs_in_tree
    from office.helpers.simplify_redlines import simplify_redlines_in_tree
else:
    from .helpers.merge_runs import merge_runs_in_tree
    from .helpers.simplify_redlines import simplify_redlines_in_tree


SMART_QUOTES = {
    "‘": "&#x2018;",
    "’": "&#x2019;",
    "“": "&#x201C;",
    "”": "&#x201D;",
    "–": "&#x2013;",
    "—": "&#x2014;",
    "…": "&#x2026;",
}


def _is_xml_like(path: Path) -> bool:
    return path.suffix.lower() in {".xml", ".rels"}


def _pretty_print(raw_xml: bytes) -> bytes:
    dom = minidom.parseString(raw_xml)
    pretty = dom.toprettyxml(indent="  ", encoding="UTF-8")
    # minidom inserts blank lines between elements — strip them.
    lines = [line for line in pretty.splitlines() if line.strip()]
    return b"\n".join(lines) + b"\n"


def _escape_smart_quotes(xml_bytes: bytes) -> bytes:
    text = xml_bytes.decode("utf-8")
    for ch, entity in SMART_QUOTES.items():
        text = text.replace(ch, entity)
    return text.encode("utf-8")


def _apply_docx_helpers(xml_path: Path) -> None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        tree = etree.parse(str(xml_path), parser)
    except etree.XMLSyntaxError:
        return
    root = tree.getroot()
    if not root.tag.endswith("}document"):
        return
    merged = merge_runs_in_tree(tree)
    simplified = simplify_redlines_in_tree(tree)
    if merged or simplified:
        tree.write(str(xml_path), xml_declaration=True, encoding="UTF-8")


def unpack(
    input_path: Path,
    output_dir: Path,
    *,
    pretty: bool = True,
    escape_smart_quotes: bool = True,
    apply_docx_helpers: bool = True,
) -> None:
    if not zipfile.is_zipfile(str(input_path)):
        raise ValueError(f"Not a ZIP-based OOXML container: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(input_path)) as archive:
        archive.extractall(output_dir)

    is_docx = input_path.suffix.lower() == ".docx"

    for item in output_dir.rglob("*"):
        if not item.is_file() or not _is_xml_like(item):
            continue
        data = item.read_bytes()
        try:
            if pretty:
                data = _pretty_print(data)
            if escape_smart_quotes:
                data = _escape_smart_quotes(data)
            item.write_bytes(data)
        except Exception as exc:
            print(f"Warning: could not normalise {item}: {exc}", file=sys.stderr)

        if is_docx and apply_docx_helpers and item.name == "document.xml":
            _apply_docx_helpers(item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .docx/.xlsx/.pptx file")
    parser.add_argument("output_dir", type=Path, help="Directory to unpack into (created if missing)")
    parser.add_argument("--no-pretty", action="store_true", help="Skip XML pretty-printing")
    parser.add_argument("--no-escape-quotes", action="store_true", help="Do not escape smart quotes/dashes")
    parser.add_argument("--no-merge-runs", action="store_true", help="Skip DOCX run-merge/redline-simplify helpers")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1
    try:
        unpack(
            args.input,
            args.output_dir,
            pretty=not args.no_pretty,
            escape_smart_quotes=not args.no_escape_quotes,
            apply_docx_helpers=not args.no_merge_runs,
        )
    except Exception as exc:
        print(f"Unpack failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
