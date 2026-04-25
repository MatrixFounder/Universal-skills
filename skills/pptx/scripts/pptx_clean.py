#!/usr/bin/env python3
"""Remove unreferenced parts from a .pptx (orphan slides, media,
embeddings, charts, themes that nothing points to anymore).

A common trap when editing a presentation by hand or by template
substitution is that you delete a slide reference but leave the
slide file itself — the part still ships in the zip, bloating the
file and confusing diff tools. This script walks the OOXML
relationship graph from `ppt/presentation.xml` outward and discards
anything not reachable.

Algorithm:
    1. Read `ppt/presentation.xml` to get the list of live slide
       relationship IDs (`<p:sldIdLst>`).
    2. Resolve each rId via `ppt/_rels/presentation.xml.rels` to a
       slide path. Those slides + presentation.xml + every part it
       references become the BFS roots.
    3. BFS through `.rels` files, adding any reachable target to
       the keep-set. Standard skeleton parts (`[Content_Types].xml`,
       `_rels/.rels`, `docProps/*`) are always kept.
    4. Files in the zip not in the keep-set are dropped.
    5. `[Content_Types].xml` Override entries pointing to dropped
       files are removed.

Usage:
    pptx_clean.py INPUT.pptx [--output OUT.pptx] [--dry-run]

--dry-run lists what would be removed without writing a file.
--output defaults to overwriting INPUT.

Limitations: this is a graph-walk cleaner, not an XML-content
sanitiser. If a slide internally references a media file that has
no `.rels` entry (broken docx), we cannot detect that — the slide
itself is kept, but its in-XML pointer dangles. Validate with
`office.validate` after running this for a full integrity check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import deque
from pathlib import Path

from lxml import etree  # type: ignore

from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped


PKG_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}

# Always-keep skeleton: opening these in the zip is mandatory for
# the pptx to be readable. We never remove them.
ALWAYS_KEEP = {
    "[Content_Types].xml",
    "_rels/.rels",
}
ALWAYS_KEEP_PREFIXES = (
    "docProps/",   # core/extended/custom properties
)


def _normalise(path: str) -> str:
    """Strip leading slash and `./` segments so paths from .rels
    Targets and zip namelist compare equal."""
    while path.startswith("/"):
        path = path[1:]
    return path.replace("\\", "/")


def _resolve_target(source_part: str, target: str) -> str:
    """A relationship's Target is RELATIVE to the part's directory.
    For `ppt/_rels/presentation.xml.rels` with Target='slides/slide1.xml',
    the resolved path is `ppt/slides/slide1.xml`."""
    if target.startswith("/"):
        return _normalise(target)
    base = source_part.rsplit("/", 1)[0] if "/" in source_part else ""
    parts = []
    if base:
        parts.extend(base.split("/"))
    for seg in target.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def _rels_path_for(part: str) -> str:
    """`ppt/slides/slide1.xml` → `ppt/slides/_rels/slide1.xml.rels`."""
    if "/" in part:
        d, name = part.rsplit("/", 1)
        return f"{d}/_rels/{name}.rels"
    return f"_rels/{part}.rels"


def _read_rels(zip_data: dict, rels_path: str, source_part: str) -> list[str]:
    """Return the list of resolved Target part-paths from a .rels file."""
    blob = zip_data.get(rels_path)
    if blob is None:
        return []
    try:
        root = etree.fromstring(blob)
    except etree.XMLSyntaxError:
        return []
    out = []
    for rel in root.findall("rels:Relationship", PKG_NS):
        target_mode = rel.get("TargetMode", "Internal")
        if target_mode == "External":
            continue
        target = rel.get("Target", "")
        if not target:
            continue
        out.append(_resolve_target(source_part, target))
    return out


def _live_slide_paths(zip_data: dict) -> list[str]:
    """Read `ppt/presentation.xml` + its .rels to get only slides that
    are listed in `<p:sldIdLst>` — anything else in `ppt/slides/` is
    an orphan that earlier edits forgot to delete."""
    pres = zip_data.get("ppt/presentation.xml")
    if pres is None:
        return []
    root = etree.fromstring(pres)
    rids = []
    for sld_id in root.iter("{%s}sldId" % PKG_NS["p"]):
        rid = sld_id.get("{%s}id" % PKG_NS["r"])
        if rid:
            rids.append(rid)
    if not rids:
        return []

    rels_blob = zip_data.get("ppt/_rels/presentation.xml.rels")
    if rels_blob is None:
        return []
    rels_root = etree.fromstring(rels_blob)
    rid_to_target: dict[str, str] = {}
    for rel in rels_root.findall("rels:Relationship", PKG_NS):
        rid_to_target[rel.get("Id", "")] = _resolve_target(
            "ppt/presentation.xml", rel.get("Target", "")
        )
    return [rid_to_target[r] for r in rids if r in rid_to_target]


def _compute_keep_set(zip_data: dict) -> set[str]:
    """BFS from live slides + presentation roots through .rels graph."""
    keep: set[str] = set(ALWAYS_KEEP)
    for name in zip_data:
        if any(name.startswith(p) for p in ALWAYS_KEEP_PREFIXES):
            keep.add(name)

    pres_path = "ppt/presentation.xml"
    pres_rels = "ppt/_rels/presentation.xml.rels"
    queue: deque[str] = deque()
    keep.add(pres_path)
    if pres_rels in zip_data:
        keep.add(pres_rels)
        # presentation.xml.rels also points at theme, slideMaster,
        # tableStyles, viewProps, presProps — pull all of those in.
        for tgt in _read_rels(zip_data, pres_rels, pres_path):
            queue.append(tgt)

    # Slides reachable via sldIdLst (orphan slide files in ppt/slides/
    # are deliberately NOT seeded — they will fall out of keep-set).
    for slide_path in _live_slide_paths(zip_data):
        queue.append(slide_path)

    while queue:
        part = queue.popleft()
        # Two early-continue guards keep the dequeue O(N): skip parts
        # that don't exist in the zip (dangling refs from a broken
        # input) and parts we've already processed (refs from multiple
        # slides to the same layout would otherwise re-walk the rels).
        if part not in zip_data:
            continue
        if part in keep:
            continue
        keep.add(part)
        rels_path = _rels_path_for(part)
        if rels_path in zip_data and rels_path not in keep:
            keep.add(rels_path)
            for tgt in _read_rels(zip_data, rels_path, part):
                if tgt not in keep:
                    queue.append(tgt)
    return keep


def _strip_content_types(blob: bytes, kept: set[str]) -> bytes:
    """Remove Override entries pointing to dropped parts. Default
    entries (PartName-less, by extension) are left intact — they
    apply to any extension match and don't enumerate parts."""
    root = etree.fromstring(blob)
    overrides_to_drop = []
    for override in root.findall("ct:Override", PKG_NS):
        part_name = _normalise(override.get("PartName", ""))
        if part_name and part_name not in kept:
            overrides_to_drop.append(override)
    for o in overrides_to_drop:
        root.remove(o)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def clean(input_path: Path, output_path: Path | None, *, dry_run: bool) -> dict:
    with zipfile.ZipFile(input_path, "r") as z:
        zip_data = {n: z.read(n) for n in z.namelist()}

    keep = _compute_keep_set(zip_data)
    drop = sorted(name for name in zip_data if name not in keep)

    report = {
        "input": str(input_path),
        "kept": len(keep),
        "removed": len(drop),
        "removed_files": drop,
        "dry_run": dry_run,
        "output": None,
    }
    if dry_run:
        return report

    out_path = output_path or input_path
    # Patch [Content_Types].xml to drop Override entries for removed parts.
    if "[Content_Types].xml" in zip_data:
        zip_data["[Content_Types].xml"] = _strip_content_types(
            zip_data["[Content_Types].xml"], keep
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(keep):
            if name in zip_data:
                z.writestr(name, zip_data[name])
    report["output"] = str(out_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .pptx")
    parser.add_argument("--output", type=Path, default=None,
                        help="Destination .pptx (default: overwrite INPUT).")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be removed without writing.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        parser.error(f"input not found: {args.input}")
    try:
        assert_not_encrypted(args.input)
    except EncryptedFileError as exc:
        return report_error(
            str(exc), code=3, error_type="EncryptedFileError",
            details={"path": str(args.input)}, json_mode=je,
        )

    if not args.dry_run:
        warn_if_macros_will_be_dropped(
            args.input, args.output or args.input, sys.stderr,
        )

    try:
        report = clean(args.input, args.output, dry_run=args.dry_run)
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        return report_error(
            f"pptx_clean: {type(exc).__name__}: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
