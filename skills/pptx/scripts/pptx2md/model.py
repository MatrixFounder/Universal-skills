"""Document model for the pptx → Markdown converter (ARCH §4).

The converter is a pipeline ``extract → (images, ocr) → emit`` over an explicit
in-memory model: ``Deck → Slide → [Block]`` plus the ``MediaAsset`` /
``PlaceholderAsset`` / ``OcrResult`` side records. Decoupling extraction from
emission is what makes the output deterministic (R-A5) and lets the emitter be
unit-tested as a pure function over data.

Honest scope (ARCH §10): outer dataclasses are ``frozen`` for immutability; inner
lists (e.g. ``Slide.blocks``, ``Bullets.items``, ``Table.rows``) are ordinary
mutable lists — the builder appends to them while constructing a slide, then the
slide is frozen. Callers must not mutate them after construction (mirrors the
``xlsx_read`` M3 honest-scope note).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# --------------------------------------------------------------------------- #
# Block union — the ordered content items inside a slide.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Heading:
    """A heading line. The slide title is emitted as ``level=3`` (``### ``)."""

    level: int
    text: str


@dataclass(frozen=True)
class BulletItem:
    """One paragraph in a text frame. ``level`` (0..8) → bullet indentation."""

    level: int
    text: str


@dataclass(frozen=True)
class Bullets:
    """A run of bullet items from a single text frame."""

    items: list[BulletItem] = field(default_factory=list)


@dataclass(frozen=True)
class Table:
    """A table; ``rows[0]`` is the header. Cells are pre-escaped for GFM."""

    rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class ImageRef:
    """A pointer to a picture. The bytes are resolved to a ``MediaAsset`` by
    ``images.materialise`` (keyed on ``sha1``)."""

    slide: int
    shape: int
    sha1: str
    ext: str
    alt: str


@dataclass(frozen=True)
class Placeholder:
    """An unsupported / unreadable shape. ``kind`` is one of ``chart``, ``image``
    (unreadable picture / EMF / SVG), ``media`` (audio/video), ``unclassifiable``,
    ``unreadable``.

    Emitted as a ``[kind]`` marker + a warning at build time (R-B3). Keyed by
    ``(slide, shape)`` — NOT ``sha1`` — because the accessors that would yield a
    sha1/ext raised (AR-1). NOTE: SmartArt is NOT classified here — python-pptx has
    no reliable SmartArt detector, so a SmartArt graphicFrame is silently skipped
    (documented v1 limitation), never a ``Placeholder``."""

    slide: int
    shape: int
    kind: str
    note: str = ""


Block = Union[Heading, Bullets, Table, ImageRef, Placeholder]


# --------------------------------------------------------------------------- #
# Slide / Deck
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Slide:
    """One slide as an ordered list of blocks, plus optional speaker notes.

    Business rule (R-A2a / MINOR-1): when a non-empty title placeholder exists,
    ``blocks[0]`` is its ``Heading`` regardless of the title shape's XML/z-order.
    """

    index: int  # 1-based, presentation order
    blocks: list[Block] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class Deck:
    """The whole presentation.

    ``blobs`` is the deck-level raw-image side table (``sha1 → (bytes,
    content_type)``) that ``extract`` populates while walking pictures and
    ``images.materialise`` consumes to write the sidecar files. It keeps
    ``ImageRef`` a pure pointer (sha1) while the bytes live in one deduplicated
    place — resolved by ``images`` into ``MediaAsset`` records. Mutable inner dict
    per the module's honest-scope note.

    Memory honest-scope: the stored ``bytes`` **alias** the same objects python-pptx
    already holds resident in the open ``Presentation`` (``Image.blob`` returns
    ``self._blob`` by reference, not a copy), and ``setdefault`` keeps one entry per
    *distinct* sha1 — so the side table costs one dict entry per unique image, not a
    second copy of the pixels. The footprint is bounded by the deck's own distinct
    image bytes, which are in RAM regardless once the deck is open.
    """

    slides: list[Slide] = field(default_factory=list)
    source_name: str = ""
    blobs: dict[str, tuple[bytes, str]] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Side tables (images / ocr)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MediaAsset:
    """An extracted image written to the sidecar media dir.

    Business rule (R-B1d / MAJOR-3): one row per distinct ``sha1``; ``filename``
    is the first-occurrence (lowest ``(slide, shape)``) name; every later
    identical blob links to the same file → naming + dedup both deterministic.
    """

    sha1: str  # primary key
    filename: str  # slide{N}-img{M}.{ext}
    rel_path: str  # link base joined with filename (POSIX separators)
    content_type: str


@dataclass(frozen=True)
class PlaceholderAsset:
    """An image whose ``.ext``/``.content_type`` access raised (AR-1).

    Keyed by ``(slide, shape)`` — NOT sha1/ext. Has no file on disk and is not
    OCR-eligible."""

    slide: int
    shape: int
    kind: str
    note: str = ""


@dataclass(frozen=True)
class OcrResult:
    """Per-image OCR text record (reserved).

    NOTE (as-built): the live ``--ocr`` path does NOT instantiate this — it caches
    OCR text as a plain ``{MediaAsset: str}`` map keyed by the deduplicated
    ``MediaAsset`` (see ``cli._build_ocr_text``), so a deduped image is OCR'd once and
    an empty result emits no marker (R-C4b/d). This dataclass is retained as a typed
    placeholder for a future structured-OCR surface; it is not on the current path."""

    sha1: str
    text: str
    ok: bool
