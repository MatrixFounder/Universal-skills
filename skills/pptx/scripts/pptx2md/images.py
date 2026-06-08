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


def rasterise_vector(blob: bytes, fmt: str, timeout: float) -> bytes | None:
    """Render a vector image (WMF/EMF) Pillow can't decode to **PNG bytes** via
    LibreOffice (``_soffice.convert_to``), or return ``None``.

    Used by ``materialise`` (so the sidecar media file is a renderable ``.png``,
    displayable inline) and by ``ocr.ocr_asset`` (so a WMF's text can be OCR'd).
    Soft-optional + fail-closed: returns ``None`` when ``fmt`` is not a
    LibreOffice-convertible vector, ``soffice`` is absent, or the conversion
    fails/times out — **never raises** (the bare ``except`` also swallows a
    ``RuntimeWarning``-as-error from the macOS hardened-shim path, preserving the
    AR-1 never-crash contract). Each call gets its own throw-away
    ``UserInstallation`` profile (``_soffice.run``), so it is safe under ``--jobs>1``.
    ``_soffice`` is imported lazily so the base path never needs LibreOffice.
    """
    ext = {"WMF": "wmf", "EMF": "emf"}.get((fmt or "").upper())
    if ext is None:  # not a LibreOffice-rasterisable vector (raster bombs etc.) → skip
        return None
    try:
        import os
        import tempfile

        from _soffice import convert_to, find_soffice

        find_soffice()  # raises if LibreOffice is not installed
        with tempfile.TemporaryDirectory(prefix="pptx2md-vec-") as d:
            src = os.path.join(d, f"vec.{ext}")
            with open(src, "wb") as fh:
                fh.write(blob)
            produced = convert_to(src, d, "png", timeout=max(60, int(timeout)))
            with open(produced, "rb") as fh:
                return fh.read()
    except Exception:  # noqa: BLE001 — soft-optional best-effort; any failure → None (AR-1)
        return None


def _prerender_vectors(deck, timeout: float, jobs: int) -> dict:
    """Rasterise every UNIQUE WMF/EMF image in the deck to PNG, in PARALLEL.

    Returns ``{sha1: png_bytes}`` for the ones that rendered. LibreOffice startup
    (~2 s) dominates each conversion, so a deck with many vector images would be slow
    serially; each ``rasterise_vector`` call is profile-isolated, so we fan them out
    over a thread pool (same ``--jobs`` budget as OCR). De-duplicated by ``sha1``.
    """
    todo: dict = {}
    for slide in deck.slides:
        for block in slide.blocks:
            # In practice pipeline vectors arrive as ext "wmf" (python-pptx's Image.ext
            # has no EMF key — an EMF Pillow labels "EMF" raises → Placeholder, and one
            # it mislabels "WMF" comes through as "wmf"). The "emf" arm is defensive
            # belt-and-suspenders for any future python-pptx that adds an EMF ext.
            if (isinstance(block, ImageRef) and block.ext in ("wmf", "emf")
                    and block.sha1 not in todo):
                entry = deck.blobs.get(block.sha1)
                if entry is not None:
                    todo[block.sha1] = (entry[0], block.ext)
    if not todo:
        return {}

    from concurrent.futures import ThreadPoolExecutor

    rendered: dict = {}
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {
            pool.submit(rasterise_vector, blob, ext, timeout): sha1
            for sha1, (blob, ext) in todo.items()
        }
        for fut in futures:
            png = fut.result()  # rasterise_vector never raises (fail-closed → None)
            if png is not None:
                rendered[futures[fut]] = png
    return rendered


def materialise(
    deck,
    media_dir: Path,
    link_base: str,
    *,
    no_images: bool = False,
    input_path: Path | None = None,
    vector_timeout: float = 180,
    jobs: int = 1,
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

    # Pre-render all WMF/EMF vectors to PNG in parallel (LibreOffice startup amortised).
    prerendered = _prerender_vectors(deck, vector_timeout, jobs)

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
            ext = block.ext
            # WMF/EMF: use the parallel-pre-rendered PNG so the sidecar image displays
            # inline (most Markdown viewers won't render .wmf/.emf). Soft-optional — if
            # soffice was absent / the render failed, the sha1 isn't in `prerendered`
            # and the original vector bytes are kept. On success also update deck.blobs
            # so --ocr OCRs the PNG (no second soffice call).
            png = prerendered.get(block.sha1)
            if png is not None:
                blob, content_type, ext = png, "image/png", "png"
                deck.blobs[block.sha1] = (png, "image/png")
            pic_ordinal[block.slide] = pic_ordinal.get(block.slide, 0) + 1
            filename = f"slide{block.slide}-img{pic_ordinal[block.slide]}.{ext}"
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
