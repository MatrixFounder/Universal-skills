"""Image extraction → sidecar media files (FC-2).

``safe_image_meta`` is the single owner (MAJOR-B) of the *guarded* image-metadata
read — consumed by both ``extract`` (ImageRef-vs-Placeholder decision) and
``materialise`` (file write).

AR-1: ``shape.image.sha1`` / ``.blob`` are safe (sha1 is a direct hashlib digest),
but ``.ext`` / ``.content_type`` route through Pillow (``PIL.Image.open``) whose
failure surface is open-ended — ``ValueError`` (EMF/SVG), ``UnidentifiedImageError``
(unreadable), ``OSError`` (truncated), and ``DecompressionBombError`` (an absurd
declared pixel count, a *subclass of ``Exception``*, not ``ValueError``). So the
metadata read catches ``Exception`` and degrades to ``None`` → the caller emits a
Placeholder, and a single hostile/huge image can never crash the whole deck.
"""
from __future__ import annotations

from pathlib import Path

from .exceptions import SelfOverwriteRefused
from .model import ImageRef, MediaAsset, PlaceholderAsset


def safe_image_meta(shape) -> tuple[bytes, str, str, str] | None:
    """Return ``(blob, sha1, ext, content_type)`` for a picture shape, or ``None``.

    ``None`` means the picture is unusable as a linkable image (EMF/SVG/unreadable
    blob, no embedded image, or a decompression-bomb-dimensioned raster) — the
    caller emits a ``Placeholder`` instead (AR-1).

    ``blob`` + ``sha1`` come from the safe accessors. ``ext`` + ``content_type``
    invoke ``PIL.Image.open`` under the hood, which can raise a WIDE set:
    ``ValueError`` / ``UnidentifiedImageError`` (EMF/SVG), ``OSError`` (truncated),
    and — crucially — ``PIL.Image.DecompressionBombError``, which is a *direct
    subclass of ``Exception``* (NOT ``ValueError``) raised on an absurd declared
    pixel count. A single such image must NOT abort the whole deck, so this
    metadata read catches ``Exception`` and degrades to ``None``. The broad catch
    is justified here precisely because the only thing this block does is *read
    image metadata* — any failure means "this picture is not usable", which is the
    documented AR-1 degradation, not a masked logic bug (the conversion logic lives
    elsewhere and is tested directly).
    """
    try:
        image = shape.image  # raises ValueError when blip_rId is None
        blob = image.blob
        sha1 = image.sha1
    except (ValueError, KeyError, AttributeError):
        return None
    try:
        ext = image.ext
        content_type = image.content_type
    except Exception:  # noqa: BLE001 — AR-1 never-crash on a metadata read (incl. DecompressionBombError)
        return None
    return blob, sha1, ext, content_type


def _join_link(link_base: str, filename: str) -> str:
    """POSIX-join the link base and filename for the emitted ``![](...)`` path."""
    if link_base in ("", "."):
        return filename
    return f"{link_base.rstrip('/')}/{filename}"


def materialise(
    deck,
    media_dir: Path,
    link_base: str,
    *,
    no_images: bool = False,
    input_path: Path | None = None,
) -> dict:
    """Write image blobs to ``media_dir`` (sha1-deduped) → ``{ImageRef: MediaAsset |
    PlaceholderAsset}`` (R-B1/R-B2/R-B3).

    * ``no_images`` → return ``{}`` and create **no** media dir (R-B3c). The emitter
      then skips every ``ImageRef`` (no asset → no link).
    * Dedup tie-break (R-B1d / MAJOR-3): the **first** ``ImageRef`` (in slide→shape
      reading order) bearing a given ``sha1`` owns the canonical filename
      ``slide{N}-img{M}.{ext}`` and is the only blob written; later identical
      ``sha1`` refs map to the same ``MediaAsset``.
    * The media dir is created lazily on the first real asset (idempotent). Links use
      the resolved ``link_base`` (file-mode relative to the .md, stdout-mode relative
      to CWD — D-7).

    Ownership note (AR-1): the *unreadable-image* decision is made upstream in
    ``extract`` — an EMF/SVG/bomb picture becomes a ``Placeholder`` **block** there
    (via ``safe_image_meta`` returning ``None``), so it never reaches here as an
    ``ImageRef``. ``materialise``'s ``PlaceholderAsset`` branch is therefore a pure
    **defensive guard** for the (normally unreachable) case where an ``ImageRef``
    has no matching ``deck.blobs`` entry — it guarantees ``materialise`` never
    raises and always returns an entry per ``ImageRef`` so the emitter can decide.
    """
    result: dict = {}
    if no_images:
        return result

    by_sha1: dict[str, MediaAsset] = {}
    pic_ordinal: dict[int, int] = {}  # per-slide running picture counter
    made_dir = False

    for slide in deck.slides:
        for block in slide.blocks:
            if not isinstance(block, ImageRef):
                continue
            # Dedup: a sha1 already written → reuse the canonical asset.
            existing = by_sha1.get(block.sha1)
            if existing is not None:
                result[block] = existing
                continue
            entry = deck.blobs.get(block.sha1)
            if entry is None:  # defensive — extract records a blob for every ImageRef
                result[block] = PlaceholderAsset(
                    slide=block.slide, shape=block.shape,
                    kind="image", note="blob unavailable",
                )
                continue
            blob, content_type = entry
            pic_ordinal[block.slide] = pic_ordinal.get(block.slide, 0) + 1
            filename = f"slide{block.slide}-img{pic_ordinal[block.slide]}.{block.ext}"
            target = media_dir / filename
            # R-D4a: a media file must never resolve onto INPUT (exit 6).
            if input_path is not None and target.resolve() == input_path.resolve():
                raise SelfOverwriteRefused(
                    f"media file resolves to INPUT: {filename}",
                    details={"path": filename},
                )
            if not made_dir:
                media_dir.mkdir(parents=True, exist_ok=True)
                made_dir = True
            target.write_bytes(blob)
            asset = MediaAsset(
                sha1=block.sha1,
                filename=filename,
                rel_path=_join_link(link_base, filename),
                content_type=content_type,
            )
            by_sha1[block.sha1] = asset
            result[block] = asset
    return result
