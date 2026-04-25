"""Base class for OOXML validators.

Subclasses provide the list of root-level XML parts they care about and
the XSD files to bind against. The base runs a handful of checks that
apply regardless of format:

- Container is a readable ZIP.
- `[Content_Types].xml` exists and parses.
- `_rels/.rels` points to an existing office-document part.
- Relationship files reference only parts that exist in the container.
- IDs that ECMA-376 requires to be unique (`w:bookmarkStart/@w:id`,
  `w:comment/@w:id`, etc.) are unique within their XML document.
- Namespace declarations actually resolve to something we can parse.
- (Optional) each discovered XML part validates against an XSD schema
  when one is provided.

XSD validation is best-effort. ECMA-376 is a large standard and real
files frequently use elements from schemas we don't ship. The validator
reports those as warnings, not errors, unless `strict=True`.
"""

from __future__ import annotations

import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree  # type: ignore


def _safe_parser() -> "etree.XMLParser":
    """XML parser with external entity resolution disabled.

    ECMA-376 parts do not use DTDs or external entities, so turning
    those features off closes the XXE / SSRF vector without affecting
    valid input.
    """
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def _resolve_zip_path(base_dir: str, target: str) -> str:
    """Resolve `target` (which may contain `..` and `.`, and may be
    absolute) against the POSIX-style `base_dir`, returning a cleaned
    ZIP-relative path.

    Per the Open Packaging Conventions (OPC, ISO/IEC 29500-2 §9.3),
    relationship `Target` attributes are URI references:
      - leading `/` → absolute against the package root (ignore
        `base_dir`); openpyxl writes its workbook→sheet relationships
        this way.
      - otherwise → relative to the part's directory. `python-docx`,
        `pptxgenjs`, and Word/PowerPoint themselves prefer this form.

    Works on string fragments only; we never touch the filesystem
    because ZIP entries are virtual paths. `PurePosixPath` does not
    collapse `..` (since real filesystems may have symlinks), so we
    walk the components manually.

    Examples:
        _resolve_zip_path("ppt/slides", "../slideLayouts/x.xml")
            → "ppt/slideLayouts/x.xml"           # relative + ..
        _resolve_zip_path("word", "media/image1.png")
            → "word/media/image1.png"            # plain relative
        _resolve_zip_path("xl", "/xl/worksheets/sheet1.xml")
            → "xl/worksheets/sheet1.xml"         # absolute (openpyxl)
    """
    if target.startswith("/"):
        path = target
    else:
        path = base_dir + "/" + target
    parts: list[str] = []
    for piece in path.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if parts:
                parts.pop()
            # Going above root is silently clamped — same behaviour as
            # a typical ZIP reader, which would just fail on an
            # impossible path later.
            continue
        parts.append(piece)
    return "/".join(parts)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationReport") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def to_dict(self) -> dict[str, list[str]]:
        return {"errors": self.errors, "warnings": self.warnings, "ok": self.ok}


class BaseSchemaValidator:
    expected_parts: tuple[str, ...] = ()
    xsd_map: dict[str, str] = {}

    def __init__(self, schemas_dir: Path | None = None, *, strict: bool = False) -> None:
        self.schemas_dir = schemas_dir
        self.strict = strict

    def validate(self, input_path: Path) -> ValidationReport:
        report = ValidationReport()
        if not zipfile.is_zipfile(str(input_path)):
            report.errors.append(f"Not a ZIP-based OOXML container: {input_path}")
            return report
        with zipfile.ZipFile(str(input_path)) as archive:
            self._validate_container(archive, report)
        return report

    def _validate_container(self, archive: zipfile.ZipFile, report: ValidationReport) -> None:
        namelist = set(archive.namelist())

        if "[Content_Types].xml" not in namelist:
            report.errors.append("Missing [Content_Types].xml")
        else:
            try:
                etree.fromstring(archive.read("[Content_Types].xml"), _safe_parser())
            except etree.XMLSyntaxError as exc:
                report.errors.append(f"[Content_Types].xml parse error: {exc}")

        if "_rels/.rels" not in namelist:
            report.errors.append("Missing _rels/.rels")
        else:
            self._check_relationships(archive, "_rels/.rels", namelist, report)

        for part in self.expected_parts:
            if part not in namelist:
                report.errors.append(f"Missing expected part: {part}")

        for name in namelist:
            if not name.endswith(".xml"):
                continue
            if self.strict:
                # Every XML part must at least parse.
                try:
                    etree.fromstring(archive.read(name), _safe_parser())
                except etree.XMLSyntaxError as exc:
                    report.errors.append(f"{name}: parse error {exc}")
            if self.schemas_dir is None:
                continue
            self._validate_against_xsd(archive, name, report)

        self._check_unique_ids(archive, namelist, report)

    def _check_relationships(
        self,
        archive: zipfile.ZipFile,
        rel_path: str,
        namelist: set[str],
        report: ValidationReport,
    ) -> None:
        try:
            root = etree.fromstring(archive.read(rel_path), _safe_parser())
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"{rel_path}: parse error {exc}")
            return
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        for rel in root.findall(f"{{{ns}}}Relationship"):
            target_mode = rel.get("TargetMode", "Internal")
            if target_mode == "External":
                continue
            target = rel.get("Target", "")
            if not target or target.startswith("#"):
                continue
            base = Path(rel_path).parent.parent if "/" in rel_path else Path("")
            resolved = (base / target).as_posix().lstrip("./")
            if resolved not in namelist:
                report.warnings.append(
                    f"{rel_path}: relationship points to missing part '{target}'"
                )

    def _check_unique_ids(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        report: ValidationReport,
    ) -> None:
        id_attrs = {
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id",
        }
        for name in namelist:
            if not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(archive.read(name), _safe_parser())
            except etree.XMLSyntaxError:
                continue
            seen: dict[str, list[str]] = defaultdict(list)
            for el in root.iter():
                for attr in id_attrs:
                    value = el.get(attr)
                    if value is None:
                        continue
                    local = etree.QName(el).localname
                    if local in {"comment", "bookmarkStart", "ins", "del", "commentRangeStart", "commentRangeEnd"}:
                        key = f"{local}:{value}"
                        seen[key].append(name)
            for key, paths in seen.items():
                if len(paths) > 1:
                    report.warnings.append(
                        f"Duplicate id '{key}' across {len(paths)} parts in {name}"
                    )

    def _validate_against_xsd(
        self,
        archive: zipfile.ZipFile,
        name: str,
        report: ValidationReport,
    ) -> None:
        xsd_name = self.xsd_map.get(name)
        if not xsd_name or self.schemas_dir is None:
            return
        xsd_path = self.schemas_dir / xsd_name
        if not xsd_path.is_file():
            if self.strict:
                report.warnings.append(f"XSD not bundled: {xsd_name}")
            return
        try:
            schema = etree.XMLSchema(etree.parse(str(xsd_path), _safe_parser()))
            doc = etree.fromstring(archive.read(name), _safe_parser())
            if not schema.validate(doc):
                for err in schema.error_log:  # type: ignore[attr-defined]
                    level = "errors" if self.strict else "warnings"
                    getattr(report, level).append(f"{name}: {err.message} (line {err.line})")
        except etree.XMLSchemaParseError as exc:
            report.warnings.append(f"Could not load XSD {xsd_name}: {exc}")
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"{name}: parse error {exc}")
