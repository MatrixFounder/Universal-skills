"""Deck reader → document model (FC-1, bead 020-02).

``open_deck`` runs the encryption pre-flight (single ``EncryptedFileError``, exit 3)
then opens the deck with ``BadInput`` wrapping; ``build_deck`` walks
slides/shapes/groups into the ``Deck → Slide → [Block]`` model (ARCH §4.1).

Classification order (AR-1): branch on ``shape.shape_type`` FIRST, and only touch
``shape.image`` through the guarded ``images.safe_image_meta`` helper — ``.ext`` /
``.content_type`` raise (via Pillow) on EMF/SVG/unreadable blobs, so an unreadable
picture degrades to a ``Placeholder`` rather than crashing the deck.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path
from zipfile import BadZipFile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.exc import PackageNotFoundError
from pptx.oxml.ns import qn
from pptx.parts.image import Image as _PptxImage
from pptx.shapes.picture import Picture

from office._encryption import assert_not_encrypted

from .exceptions import BadInput
from .images import safe_image_meta
from .model import Block, Bullets, BulletItem, Deck, Heading, ImageRef, Placeholder, Slide, Table

_BLIP_TAG = qn("a:blip")  # {drawingml}blip — appears in pictures, shape fills, and bg fills


def _warn(message: str) -> None:
    """Best-effort warning to stderr (never on the Markdown stream)."""
    sys.stderr.write(f"warning: {message}\n")
    sys.stderr.flush()


def assert_openable(path: Path) -> None:
    """Reject encrypted/legacy CFB inputs before parsing (R-D3 / D-6).

    Raises ``EncryptedFileError`` (mapped to exit 3 in ``cli.main``) for a
    password-protected OOXML *or* a legacy ``.ppt`` — one type, message names both.
    """
    assert_not_encrypted(path)


def open_deck(path: Path):
    """Encryption pre-flight + open. Returns a python-pptx ``Presentation``.

    Raises:
        EncryptedFileError: CFB container (encrypted or legacy ``.ppt``) — exit 3.
        BadInput: not a usable OOXML package (corrupt / not a ``.pptx``) — exit 1.
    """
    assert_openable(path)
    try:
        return Presentation(str(path))
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as exc:
        raise BadInput(
            f"Not a usable .pptx: {path.name}",
            details={"path": path.name, "reason": type(exc).__name__},
        ) from exc


def _is_hidden(slide) -> bool:
    """A slide is hidden when ``p:sld@show`` is the XSD-boolean false (AR-6 — no
    public python-pptx API, so read the raw OOXML attribute). ``@show`` is
    ``xsd:boolean``, so non-PowerPoint producers may write ``"false"`` as well as
    ``"0"``; both mean hidden."""
    return slide._element.get("show") in ("0", "false")


def _extract_notes(slide) -> str | None:
    """Return non-empty speaker-notes text, or ``None`` (AR-7 — guard on
    ``has_notes_slide`` to avoid the create-on-access side effect)."""
    if not slide.has_notes_slide:
        return None
    tf = slide.notes_slide.notes_text_frame
    if tf is None:
        return None
    text = tf.text.strip()
    return text or None


def _escape_cell(text: str) -> str:
    """Escape a table cell for GFM.

    Order matters: escape ``\\`` BEFORE ``|`` (otherwise a pre-existing ``\\|`` in
    the source would have its pipe un-escaped). Outer whitespace/newlines are
    trimmed first so a cell padded with blank lines does not emit leading/trailing
    ``<br>`` litter; remaining internal newlines become ``<br>``.

    Honest scope: inline HTML in a cell value is NOT neutralised (GFM renders it).
    This matches the single-tenant local-CLI office trust model and the sibling
    ``xlsx2md`` behaviour — Markdown is a text format, not a sandbox.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    t = t.replace("\\", "\\\\").replace("|", "\\|")
    return t.replace("\n", "<br>")


def _table_block(shape) -> Table:
    """Convert a table graphic-frame to a ``Table`` block (rows[0] = header)."""
    rows: list[list[str]] = []
    for row in shape.table.rows:
        rows.append([_escape_cell(cell.text) for cell in row.cells])
    return Table(rows=rows)


def _bullets(text_frame) -> Bullets:
    """Convert a text frame to a ``Bullets`` block; blank paragraphs are dropped."""
    items: list[BulletItem] = []
    for para in text_frame.paragraphs:
        text = para.text
        if not text.strip():
            continue
        # Clamp to the OOXML/model range 0..8 (a hand-edited deck may carry lvl>8).
        level = max(0, min(8, para.level or 0))
        items.append(BulletItem(level=level, text=text.strip()))
    return Bullets(items=items)


def _alt_text(shape) -> str:
    """Best-effort alt text from the shape name; fallback ``"image"``."""
    return (getattr(shape, "name", "") or "").strip() or "image"


def _walk_shapes(shapes, blocks: list[Block], slide_index: int, skip_id, counter, blobs: dict) -> None:
    """Append a ``Block`` per shape in document order; recurse into groups (R-A1).

    ``skip_id`` is the title placeholder's ``shape_id`` — NOT the object —
    because ``slide.shapes.title`` returns a *different* wrapper object than the
    one iteration yields, so an ``is`` identity check silently fails and the title
    gets emitted twice (once as the Heading, once as a duplicate Bullets).
    """
    for shape in shapes:
        if skip_id is not None and getattr(shape, "shape_id", None) == skip_id:
            continue
        # C1: shape_type itself raises (NotImplementedError) on shapes python-pptx
        # cannot classify (some OLE / AlternateContent / producer-specific sp) —
        # guard it so one weird shape degrades to a Placeholder, never a crash (AR-1).
        try:
            st = shape.shape_type
        except (NotImplementedError, ValueError, KeyError, AttributeError) as exc:
            blocks.append(Placeholder(slide=slide_index, shape=next(counter),
                                      kind="unclassifiable", note=type(exc).__name__))
            _warn(f"slide {slide_index}: unclassifiable shape ({type(exc).__name__}) → placeholder")
            continue
        if st == MSO_SHAPE_TYPE.GROUP:
            # N1: the group's .shapes collection is built lazily from grpSp/spTree;
            # a malformed group can raise on access. Guard it in the same AR-1
            # degradation style as the shape_type access above (never crash).
            try:
                child_shapes = shape.shapes
            except (AttributeError, KeyError, ValueError) as exc:
                blocks.append(Placeholder(slide=slide_index, shape=next(counter),
                                          kind="unclassifiable", note=type(exc).__name__))
                _warn(f"slide {slide_index}: unreadable group ({type(exc).__name__}) → placeholder")
                continue
            # H2/H3: recurse with skip_id=None — the title placeholder is always a
            # top-level shape, so a grouped body shape can never legitimately match
            # the title's shape_id (guards against an over-skip on id reuse).
            _walk_shapes(child_shapes, blocks, slide_index, None, counter, blobs)
            continue
        # The per-slide counter advances once per SOURCE shape reached here (groups
        # recurse without consuming; the title is skipped) — so the index is stable
        # regardless of whether a picture classifies as ImageRef or Placeholder.
        # That is what makes (slide, shape) a deterministic dedup/placeholder key (R-A5).
        shape_idx = next(counter)

        # AR-1: classify before touching shape.image (isinstance is a safe check;
        # safe_image_meta guards the .image access). `isinstance(shape, Picture)`
        # catches BOTH a plain PICTURE and a **picture-placeholder** (PlaceholderPicture
        # subclasses Picture but reports shape_type==PLACEHOLDER, so `== PICTURE` missed
        # it — that silently dropped image-content slides, e.g. tmp8/slides-5 sl 2-3).
        if isinstance(shape, Picture):
            meta = safe_image_meta(shape)
            if meta is None:
                blocks.append(Placeholder(slide=slide_index, shape=shape_idx,
                                          kind="image", note="unreadable/unsupported image"))
                _warn(f"slide {slide_index}: dropped unreadable image → placeholder")
            else:
                blob, sha1, ext, content_type = meta
                # Record the raw bytes once per distinct image (deduped by sha1) for
                # images.materialise to write; ImageRef stays a pure sha1 pointer.
                blobs.setdefault(sha1, (blob, content_type))
                blocks.append(ImageRef(slide=slide_index, shape=shape_idx,
                                       sha1=sha1, ext=ext, alt=_alt_text(shape)))
            continue
        if st == MSO_SHAPE_TYPE.MEDIA:
            blocks.append(Placeholder(slide=slide_index, shape=shape_idx,
                                      kind="media", note="embedded audio/video"))
            _warn(f"slide {slide_index}: embedded media → placeholder")
            continue

        try:
            if shape.has_table:
                blocks.append(_table_block(shape))
                continue
            if shape.has_chart:
                blocks.append(Placeholder(slide=slide_index, shape=shape_idx,
                                          kind="chart", note="chart"))
                _warn(f"slide {slide_index}: chart → placeholder")
                continue
            if shape.has_text_frame:
                bullets = _bullets(shape.text_frame)
                if bullets.items:
                    blocks.append(bullets)
                continue
        except (ValueError, AttributeError, KeyError) as exc:
            blocks.append(Placeholder(slide=slide_index, shape=shape_idx,
                                      kind="unreadable", note=type(exc).__name__))
            _warn(f"slide {slide_index}: unreadable shape ({type(exc).__name__}) → placeholder")
            continue
        # Other shapes (empty placeholders, undetectable SmartArt) are skipped.


def _collect_nonpic_images(slide, slide_index: int, counter, blobs: dict, captured_sha1s: set) -> list:
    """Collect images NOT carried by a ``Picture`` shape (R-A1 extension).

    Two real sources the shape walk cannot reach: **slide-background fills**
    (``p:cSld/p:bg`` — the whole marp/exported slide is a full-page background PNG)
    and **shape blip-fills**. Each ``a:blip`` embed rId is resolved to its image part
    via the slide's relationships. Deduped by rId within the slide and by ``sha1``
    against pictures already emitted on the same slide. Unreadable/unresolvable →
    ``Placeholder`` (never a crash, AR-1).
    """
    results: list = []
    seen_rids: set = set()
    for blip in slide._element.iter(_BLIP_TAG):
        # Blips inside a p:pic are handled by the shape walk (isinstance Picture); skip.
        if blip.xpath("ancestor::p:pic"):
            continue
        rid = blip.get(qn("r:embed"))
        if not rid or rid in seen_rids:
            continue
        seen_rids.add(rid)
        shape_idx = next(counter)
        try:
            part = slide.part.related_part(rid)
            image = _PptxImage.from_blob(part.blob)
            blob, sha1, ext, ct = image.blob, image.sha1, image.ext, image.content_type
        except Exception as exc:  # noqa: BLE001 — unresolvable/unreadable bg/fill → placeholder
            results.append(Placeholder(slide=slide_index, shape=shape_idx,
                                       kind="image", note="unreadable background/fill image"))
            _warn(f"slide {slide_index}: unreadable background/fill image "
                  f"({type(exc).__name__}) → placeholder")
            continue
        if sha1 in captured_sha1s:
            continue  # same image already emitted as a Picture on this slide
        blobs.setdefault(sha1, (blob, ct))
        results.append(ImageRef(slide=slide_index, shape=shape_idx,
                                sha1=sha1, ext=ext, alt="background"))
    return results


def build_deck(prs, opts, source_name: str = "") -> Deck:
    """Walk a python-pptx ``Presentation`` into the document model.

    ``opts`` is the argparse namespace (uses ``opts.include_hidden``). Title-first
    ordering (R-A2a), group recursion (R-A1), notes when present (R-D1).
    ``source_name`` is the caller-supplied input basename (``cli.main`` passes
    ``input_path.name``); threaded in rather than spelunked from python-pptx
    private attrs (M4).
    """
    slides: list[Slide] = []
    blobs: dict[str, tuple[bytes, str]] = {}
    for idx, slide in enumerate(prs.slides, start=1):
        if not opts.include_hidden and _is_hidden(slide):
            continue
        blocks: list[Block] = []

        # Title first, regardless of its XML/z-order (R-A2a / MINOR-1).
        title_shape = slide.shapes.title
        title_text = title_shape.text.strip() if title_shape is not None else ""
        # Skip the title in the body walk by shape_id (object identity is unreliable
        # — slide.shapes.title is a different wrapper than the iterated shape).
        skip_id = title_shape.shape_id if title_shape is not None else None
        if title_text:
            blocks.append(Heading(level=3, text=title_text))

        counter = itertools.count(1)
        _walk_shapes(slide.shapes, blocks, idx, skip_id, counter, blobs)
        # Slide-background + shape-fill images the shape walk can't see (marp/exported
        # decks whose whole slide is a background image; picture-fills on autoshapes).
        captured = {b.sha1 for b in blocks if isinstance(b, ImageRef)}
        blocks.extend(_collect_nonpic_images(slide, idx, counter, blobs, captured))

        slides.append(Slide(index=idx, blocks=blocks, notes=_extract_notes(slide)))

    return Deck(slides=slides, source_name=source_name, blobs=blobs)
