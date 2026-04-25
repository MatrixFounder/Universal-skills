"""PPTX-specific extensions of the base OOXML validator.

Beyond the structural / relationship / id-uniqueness checks the base
class performs, this module verifies the PresentationML graph is
internally consistent:

  1. **Slide chain** — every `<p:sldId>` in `ppt/presentation.xml`
     resolves to an existing `ppt/slides/slideN.xml` via
     `ppt/_rels/presentation.xml.rels`.
  2. **Slide-id uniqueness and bounds** — `p:sldId/@id` values must be
     unique and within the ECMA-376 §19.2.1.34 range (256–2147483647).
  3. **Layout chain** — each slide's `_rels/slideN.xml.rels` references
     a slide layout that exists; each layout references a slide master
     that exists.
  4. **Media references** — every `<a:blip r:embed="rIdN">` and
     `<p:videoFile r:link="rIdN">` in a slide resolves to a media part
     present in the ZIP namelist.
  5. **Notes slides** — when present, each notes slide has the
     reciprocal relationship back to its slide.
  6. **Orphan parts** — `ppt/slides/*.xml` with no incoming relation
     from `presentation.xml.rels`. Often left behind after manual
     deletion in PowerPoint or `pptx_clean.py --dry-run` skipping
     a step.

XSD binding (`xsd_map`) is extended to cover the slide/layout/master
parts on top of `presentation.xml`. Since real packages may use
extension schemas we don't ship (e.g. `mc:AlternateContent` from
markup-compatibility), all XSD failures stay warnings unless `--strict`.
"""

from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

from lxml import etree  # type: ignore

from .base import (
    BaseSchemaValidator, ValidationReport, _resolve_zip_path, _safe_parser,
)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Relationship type URIs we care about. ECMA-376 Part 1 §15.2 lists the
# canonical types; we match by suffix to be tolerant of the
# "officeDocument/2006/relationships/" vs. ".../strict/" variants.
_REL_TYPE_SLIDE = "/slide"
_REL_TYPE_SLIDELAYOUT = "/slideLayout"
_REL_TYPE_SLIDEMASTER = "/slideMaster"
_REL_TYPE_NOTESSLIDE = "/notesSlide"
_REL_TYPE_THEME = "/theme"
_REL_TYPE_IMAGE = "/image"
_REL_TYPE_MEDIA = "/media"
_REL_TYPE_VIDEO = "/video"

# ECMA-376 §19.2.1.34 ST_SlideId ranges.
_SLIDE_ID_MIN = 256
_SLIDE_ID_MAX = 2_147_483_647


class PptxValidator(BaseSchemaValidator):
    expected_parts = (
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
    )
    xsd_map = {
        "ppt/presentation.xml": "pml.xsd",
        # The slides themselves use the same schema namespace; binding
        # is opt-in (only when the user has run schemas/fetch.sh).
        # Per-slide entries are added dynamically in _validate_container
        # so the map adapts to each container's slide count.
    }

    def _validate_container(
        self, archive: zipfile.ZipFile, report: ValidationReport
    ) -> None:
        super()._validate_container(archive, report)
        namelist = set(archive.namelist())
        if "ppt/presentation.xml" not in namelist:
            return  # base() already errored
        try:
            pres = etree.fromstring(
                archive.read("ppt/presentation.xml"), _safe_parser()
            )
        except etree.XMLSyntaxError as exc:
            report.errors.append(f"ppt/presentation.xml: parse error {exc}")
            return

        self._check_slide_id_list(pres, report)
        slide_targets = self._slide_chain(archive, namelist, report)
        self._check_layout_master_chain(archive, namelist, slide_targets, report)
        self._check_media_references(archive, namelist, slide_targets, report)
        self._check_notes_reciprocity(archive, namelist, slide_targets, report)
        self._check_orphan_slides(namelist, slide_targets, report)

    # ------------------------------------------------------------------
    # ppt/presentation.xml — sldIdLst structural rules
    # ------------------------------------------------------------------
    def _check_slide_id_list(
        self, pres: etree._Element, report: ValidationReport
    ) -> None:
        seen_ids: set[str] = set()
        seen_rids: set[str] = set()
        for sld in pres.iter(f"{{{P_NS}}}sldId"):
            sid = sld.get("id")
            rid = sld.get(f"{{{R_NS}}}id")
            if sid is None:
                report.errors.append("ppt/presentation.xml: <p:sldId> missing @id")
            else:
                try:
                    sid_int = int(sid)
                except ValueError:
                    report.errors.append(
                        f"ppt/presentation.xml: <p:sldId @id='{sid}'> not an integer"
                    )
                else:
                    if not (_SLIDE_ID_MIN <= sid_int <= _SLIDE_ID_MAX):
                        report.errors.append(
                            f"ppt/presentation.xml: <p:sldId @id='{sid}'> out of "
                            f"ECMA-376 ST_SlideId range "
                            f"[{_SLIDE_ID_MIN}, {_SLIDE_ID_MAX}]"
                        )
                if sid in seen_ids:
                    report.errors.append(
                        f"ppt/presentation.xml: duplicate <p:sldId @id='{sid}'>"
                    )
                seen_ids.add(sid)
            if rid is None:
                report.errors.append("ppt/presentation.xml: <p:sldId> missing @r:id")
            else:
                if rid in seen_rids:
                    report.errors.append(
                        f"ppt/presentation.xml: duplicate r:id '{rid}' in sldIdLst"
                    )
                seen_rids.add(rid)

    # ------------------------------------------------------------------
    # Relationship-graph helpers
    # ------------------------------------------------------------------
    def _read_rels(
        self,
        archive: zipfile.ZipFile,
        rels_path: str,
        report: ValidationReport,
    ) -> dict[str, tuple[str, str]]:
        """Parse a `.rels` file and return `{Id: (Type, resolved_part)}`.

        `resolved_part` is the ZIP-relative path the relationship points
        to (External targets are skipped). Failure to parse is recorded
        in `report` and an empty dict is returned.
        """
        try:
            root = etree.fromstring(archive.read(rels_path), _safe_parser())
        except (KeyError, etree.XMLSyntaxError) as exc:
            report.errors.append(f"{rels_path}: parse error {exc}")
            return {}
        out: dict[str, tuple[str, str]] = {}
        # Relationships live in `<dir>/_rels/<name>.rels`; relative
        # Targets are resolved against `<dir>` (the part's directory),
        # which is the rels-file path's parent's parent.
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

    def _slide_chain(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        report: ValidationReport,
    ) -> set[str]:
        """Walk `presentation.xml.rels` for slide relationships, verify
        each target exists, and return the set of slide part paths."""
        slides: set[str] = set()
        rels = self._read_rels(archive, "ppt/_rels/presentation.xml.rels", report)
        for rid, (rtype, target) in rels.items():
            if not rtype.endswith(_REL_TYPE_SLIDE):
                continue
            if target not in namelist:
                report.errors.append(
                    f"ppt/_rels/presentation.xml.rels: rId={rid} points to "
                    f"missing slide part '{target}'"
                )
                continue
            slides.add(target)
        return slides

    # ------------------------------------------------------------------
    # Layout / master chain
    # ------------------------------------------------------------------
    def _check_layout_master_chain(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        slides: set[str],
        report: ValidationReport,
    ) -> None:
        """For each slide → resolve its slideLayout → resolve master.

        Every link must exist; otherwise PowerPoint shows the slide as
        broken (no theme inheritance).
        """
        for slide_part in sorted(slides):
            slide_dir = PurePosixPath(slide_part).parent
            rels_path = f"{slide_dir}/_rels/{PurePosixPath(slide_part).name}.rels"
            if rels_path not in namelist:
                report.warnings.append(
                    f"{slide_part}: missing companion {rels_path}"
                )
                continue
            rels = self._read_rels(archive, rels_path, report)
            layouts = [
                target for (rtype, target) in rels.values()
                if rtype.endswith(_REL_TYPE_SLIDELAYOUT)
            ]
            if not layouts:
                report.warnings.append(
                    f"{slide_part}: no slideLayout relationship "
                    "(slide will inherit nothing)"
                )
                continue
            for layout in layouts:
                if layout not in namelist:
                    report.errors.append(
                        f"{slide_part}: slideLayout '{layout}' missing"
                    )
                    continue
                # And the layout's master.
                lay_dir = PurePosixPath(layout).parent
                lay_rels = f"{lay_dir}/_rels/{PurePosixPath(layout).name}.rels"
                if lay_rels not in namelist:
                    report.warnings.append(
                        f"{layout}: missing companion {lay_rels}"
                    )
                    continue
                lr = self._read_rels(archive, lay_rels, report)
                masters = [
                    target for (rtype, target) in lr.values()
                    if rtype.endswith(_REL_TYPE_SLIDEMASTER)
                ]
                if not masters:
                    report.warnings.append(
                        f"{layout}: no slideMaster relationship"
                    )
                for master in masters:
                    if master not in namelist:
                        report.errors.append(
                            f"{layout}: slideMaster '{master}' missing"
                        )

    # ------------------------------------------------------------------
    # Media (images, audio, video)
    # ------------------------------------------------------------------
    def _check_media_references(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        slides: set[str],
        report: ValidationReport,
    ) -> None:
        """Each `<a:blip r:embed=…>` or `<p:videoFile r:link=…>` must
        resolve to a part that exists in the package.
        """
        for slide_part in sorted(slides):
            slide_dir = PurePosixPath(slide_part).parent
            rels_path = f"{slide_dir}/_rels/{PurePosixPath(slide_part).name}.rels"
            rels = self._read_rels(archive, rels_path, report) if rels_path in namelist else {}
            try:
                slide_doc = etree.fromstring(
                    archive.read(slide_part), _safe_parser()
                )
            except etree.XMLSyntaxError as exc:
                report.errors.append(f"{slide_part}: parse error {exc}")
                continue
            referenced_rids: list[tuple[str, str]] = []
            for blip in slide_doc.iter(f"{{{A_NS}}}blip"):
                for attr in (f"{{{R_NS}}}embed", f"{{{R_NS}}}link"):
                    rid = blip.get(attr)
                    if rid:
                        referenced_rids.append(("blip", rid))
            for video in slide_doc.iter(f"{{{P_NS}}}videoFile"):
                rid = video.get(f"{{{R_NS}}}link")
                if rid:
                    referenced_rids.append(("video", rid))
            for kind, rid in referenced_rids:
                if rid not in rels:
                    report.errors.append(
                        f"{slide_part}: {kind} references unknown rId '{rid}' "
                        f"(no entry in {rels_path})"
                    )
                    continue
                _, target = rels[rid]
                if target not in namelist:
                    report.errors.append(
                        f"{slide_part}: {kind} rId '{rid}' → '{target}' "
                        "(media part not in package)"
                    )

    # ------------------------------------------------------------------
    # Notes-slide reciprocity
    # ------------------------------------------------------------------
    def _check_notes_reciprocity(
        self,
        archive: zipfile.ZipFile,
        namelist: set[str],
        slides: set[str],
        report: ValidationReport,
    ) -> None:
        """If slide N references notesSlideN, then notesSlideN's rels
        must point back to slide N. PowerPoint silently drops
        unreciprocated notes-slide pairs."""
        for slide_part in sorted(slides):
            slide_dir = PurePosixPath(slide_part).parent
            rels_path = f"{slide_dir}/_rels/{PurePosixPath(slide_part).name}.rels"
            if rels_path not in namelist:
                continue
            rels = self._read_rels(archive, rels_path, report)
            note_targets = [
                target for (rtype, target) in rels.values()
                if rtype.endswith(_REL_TYPE_NOTESSLIDE)
            ]
            for note in note_targets:
                if note not in namelist:
                    report.errors.append(
                        f"{slide_part}: notesSlide '{note}' missing"
                    )
                    continue
                note_dir = PurePosixPath(note).parent
                note_rels = f"{note_dir}/_rels/{PurePosixPath(note).name}.rels"
                if note_rels not in namelist:
                    report.warnings.append(
                        f"{note}: missing companion {note_rels} "
                        "(notes-slide cannot reference back to its slide)"
                    )
                    continue
                back = self._read_rels(archive, note_rels, report)
                back_slides = [
                    target for (rtype, target) in back.values()
                    if rtype.endswith(_REL_TYPE_SLIDE)
                ]
                if slide_part not in back_slides:
                    report.warnings.append(
                        f"{note}: notes-slide does not link back to "
                        f"its parent slide '{slide_part}'"
                    )

    # ------------------------------------------------------------------
    # Orphan slides
    # ------------------------------------------------------------------
    def _check_orphan_slides(
        self,
        namelist: set[str],
        slides: set[str],
        report: ValidationReport,
    ) -> None:
        """Find `ppt/slides/slideN.xml` files not referenced from
        `presentation.xml.rels`. They bloat the package and confuse
        `pptx_clean.py` consumers."""
        on_disk = {
            n for n in namelist
            if n.startswith("ppt/slides/")
            and n.endswith(".xml")
            and "/_rels/" not in n
        }
        orphans = sorted(on_disk - slides)
        for orphan in orphans:
            report.warnings.append(
                f"Orphan slide part '{orphan}' (not referenced from "
                "ppt/_rels/presentation.xml.rels — run pptx_clean.py)"
            )

    # ------------------------------------------------------------------
    # XSD binding for slides (extends parent's xsd_map dynamically)
    # ------------------------------------------------------------------
    def _validate_against_xsd(
        self,
        archive: zipfile.ZipFile,
        name: str,
        report: ValidationReport,
    ) -> None:
        # Bind every slideN.xml / slideLayoutN.xml / slideMasterN.xml
        # to pml.xsd in addition to the static xsd_map entries. The
        # base class only consults `self.xsd_map`, so synthesise an
        # entry on the fly.
        if name not in self.xsd_map:
            if (name.startswith("ppt/slides/slide")
                    or name.startswith("ppt/slideLayouts/slideLayout")
                    or name.startswith("ppt/slideMasters/slideMaster")):
                if name.endswith(".xml"):
                    self.xsd_map[name] = "pml.xsd"
        super()._validate_against_xsd(archive, name, report)
