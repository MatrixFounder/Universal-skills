"""One-shot fixture builder for tracked-change test fixtures.

Task reference: task-006-08 (Q-U1 tracked insertion/deletion fixtures).
Plan-review MIN-3 carve-out: surgical lxml edit of an md2docx-generated
baseline. This is the same precedent as the .docm fixture in 006-03
(single [Content_Types].xml edit) and the headers-fixture splice deferred
to 006-04. LibreOffice UNO automation was assessed as impractical on this
host (soffice not installed, no UNO binding).

Spec deviation accepted: see plan-review delta — LibreOffice unavailable
on host; surgical-edit fallback used per MIN-3 carve-out and .docm/headers
precedents from 006-03/006-04.

Pipeline:
  1. Generate baseline .docx from a minimal markdown "FOO" paragraph
     via md2docx.js (R11.d-compliant baseline).
  2. Unpack via office.unpack.
  3. Use lxml to locate the <w:r> containing "FOO" in word/document.xml
     and surgically wrap it in <w:ins> (for the _ins fixture) or
     <w:del> / <w:delText> (for the _del fixture).
  4. Repack via office.pack.
  5. Output committed to skills/docx/examples/.

The helper is invoked ONCE at fixture-build time. The resulting .docx files
are committed; the helper is re-invoked only if the fixtures need refreshing.
Do NOT invoke this at test run time.

Usage (from skills/docx/scripts/):
    ./.venv/bin/python tests/build_tracked_change_fixture.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from lxml import etree

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_EXAMPLES_DIR = _SCRIPTS_DIR.parent / "examples"
_MD2DOCX = _SCRIPTS_DIR / "md2docx.js"

# Namespaces
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _qn(local: str) -> str:
    return f"{{{_W}}}{local}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_baseline(md_content: str, tmp_dir: Path) -> Path:
    """Generate a baseline .docx from markdown content via md2docx.js."""
    md_path = tmp_dir / "baseline.md"
    md_path.write_text(md_content, encoding="utf-8")
    out_docx = tmp_dir / "baseline.docx"
    result = subprocess.run(
        ["node", str(_MD2DOCX), str(md_path), str(out_docx)],
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not out_docx.is_file():
        raise RuntimeError(
            f"md2docx.js failed (rc={result.returncode}): {result.stderr}"
        )
    return out_docx


def _unpack(docx: Path, dest: Path) -> None:
    """Unpack a .docx into dest directory."""
    # Use the skill's venv office.unpack
    sys.path.insert(0, str(_SCRIPTS_DIR))
    from office.unpack import unpack  # type: ignore
    unpack(docx, dest)


def _pack(tree_root: Path, out_docx: Path) -> None:
    """Pack a tree into a .docx file."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    from office.pack import pack  # type: ignore
    pack(tree_root, out_docx)


def _find_run_with_text(doc_root: etree._Element, text: str) -> etree._Element:
    """Find the first <w:r> containing a <w:t> with exactly `text`."""
    for r in doc_root.iter(_qn("r")):
        t = r.find(_qn("t"))
        if t is not None and t.text and text in t.text:
            return r
    raise ValueError(f"No <w:r> found containing text {text!r}")


def _build_ins_fixture(tmp_dir: Path) -> Path:
    """Build docx_replace_tracked_ins.docx.

    Structure: paragraph with <w:ins><w:r><w:t>FOO paragraph</w:t></w:r></w:ins>
    so that _concat_paragraph_text() finds "FOO" (w:ins content is live).
    """
    # Step 1: baseline
    baseline_dir = tmp_dir / "ins_baseline"
    baseline_dir.mkdir(exist_ok=True)
    baseline = _generate_baseline("FOO paragraph", baseline_dir)

    # Step 2: unpack
    unpack_dir = tmp_dir / "ins_unpacked"
    unpack_dir.mkdir()
    _unpack(baseline, unpack_dir)

    # Step 3: surgical edit
    doc_xml_path = unpack_dir / "word" / "document.xml"
    tree = etree.parse(str(doc_xml_path))
    root = tree.getroot()

    target_run = _find_run_with_text(root, "FOO")
    parent = target_run.getparent()
    pos = list(parent).index(target_run)

    # Remove run from parent
    parent.remove(target_run)

    # Create <w:ins> wrapper with required OOXML attributes
    ins_el = etree.Element(_qn("ins"))
    ins_el.set(_qn("id"), "1")
    ins_el.set(_qn("author"), "Test Author")
    ins_el.set(_qn("date"), "2024-01-15T10:00:00Z")
    ins_el.append(target_run)

    # Re-insert at same position
    parent.insert(pos, ins_el)

    # Write modified document.xml back
    doc_xml_path.write_bytes(
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    )

    # Step 4: repack
    out_path = _EXAMPLES_DIR / "docx_replace_tracked_ins.docx"
    _pack(unpack_dir, out_path)
    return out_path


def _build_del_fixture(tmp_dir: Path) -> Path:
    """Build docx_replace_tracked_del.docx.

    Structure: paragraph with <w:del><w:r><w:delText>FOO paragraph</w:delText></w:r></w:del>
    so that _concat_paragraph_text() does NOT find "FOO" (w:del content excluded).
    """
    # Step 1: generate baseline into the del_baseline subdir
    baseline_dir = tmp_dir / "del_baseline"
    baseline_dir.mkdir(exist_ok=True)
    baseline = _generate_baseline("FOO paragraph", baseline_dir)

    # Step 2: unpack
    unpack_dir = tmp_dir / "del_unpacked"
    unpack_dir.mkdir()
    _unpack(baseline, unpack_dir)

    # Step 3: surgical edit
    doc_xml_path = unpack_dir / "word" / "document.xml"
    tree = etree.parse(str(doc_xml_path))
    root = tree.getroot()

    target_run = _find_run_with_text(root, "FOO")
    parent = target_run.getparent()
    pos = list(parent).index(target_run)

    # Find the <w:t> inside the run and replace with <w:delText>
    t_elem = target_run.find(_qn("t"))
    if t_elem is None:
        raise ValueError("<w:t> not found inside target run")

    # Create <w:delText> (tracked deletions use delText, not t)
    del_text = etree.SubElement(target_run, _qn("delText"))
    del_text.text = t_elem.text
    # Preserve xml:space="preserve" if present on original
    space_attr = "{http://www.w3.org/XML/1998/namespace}space"
    if t_elem.get(space_attr):
        del_text.set(space_attr, t_elem.get(space_attr))
    target_run.remove(t_elem)

    # Remove run from parent
    parent.remove(target_run)

    # Create <w:del> wrapper with required OOXML attributes
    del_el = etree.Element(_qn("del"))
    del_el.set(_qn("id"), "2")
    del_el.set(_qn("author"), "Test Author")
    del_el.set(_qn("date"), "2024-01-15T10:00:00Z")
    del_el.append(target_run)

    # Re-insert at same position
    parent.insert(pos, del_el)

    # Write modified document.xml back
    doc_xml_path.write_bytes(
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    )

    # Step 4: repack
    out_path = _EXAMPLES_DIR / "docx_replace_tracked_del.docx"
    _pack(unpack_dir, out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Build both tracked-change fixtures and report results."""
    print("Building tracked-change fixtures for task-006-08 Q-U1 tests...")
    print(f"Output dir: {_EXAMPLES_DIR}")

    with tempfile.TemporaryDirectory(prefix="build_tracked_") as tmp_str:
        tmp = Path(tmp_str)

        print("  [1/2] Building docx_replace_tracked_ins.docx ...")
        ins_path = _build_ins_fixture(tmp)
        print(f"        → {ins_path} ({ins_path.stat().st_size} bytes)")

        print("  [2/2] Building docx_replace_tracked_del.docx ...")
        del_path = _build_del_fixture(tmp)
        print(f"        → {del_path} ({del_path.stat().st_size} bytes)")

    print("Done. Verify with:")
    print(f"  python3 -c \"from office.unpack import unpack; from pathlib import Path; "
          f"import tempfile; t=tempfile.mkdtemp(); "
          f"unpack(Path('{ins_path}'), Path(t)); "
          f"d=Path(t)/'word'/'document.xml'; print(d.read_text()[:2000])\"")


if __name__ == "__main__":
    main()
