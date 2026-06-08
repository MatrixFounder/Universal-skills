"""Document model → Markdown (FC-4).

The only module that knows Markdown syntax. ``render_deck`` is a pure generator over
the model + media/OCR side-data — pure-function-over-data makes it deterministic
(R-A5/I-1) and unit-testable without a real ``.pptx``.
"""
from __future__ import annotations

from typing import Iterator

from .model import (
    Bullets,
    Heading,
    ImageRef,
    MediaAsset,
    Placeholder,
    Slide,
    Table,
)


def _render_bullets(b: Bullets) -> Iterator[str]:
    for item in b.items:
        indent = "  " * max(0, item.level)
        yield f"{indent}- {item.text}\n"
    yield "\n"


def _render_table(t: Table) -> Iterator[str]:
    if not t.rows:
        return
    width = max(len(r) for r in t.rows)

    def _row(cells: list[str]) -> str:
        padded = list(cells) + [""] * (width - len(cells))
        return "| " + " | ".join(padded[:width]) + " |\n"

    yield _row(t.rows[0])
    yield "| " + " | ".join(["---"] * width) + " |\n"
    for row in t.rows[1:]:
        yield _row(row)
    yield "\n"


def _render_image(block: ImageRef, asset, ocr: str) -> Iterator[str]:
    if asset is None:
        # --no-images (or unresolved) → no link emitted.
        return
    if isinstance(asset, MediaAsset):
        yield f"![{block.alt}]({asset.rel_path})\n"
    else:  # PlaceholderAsset
        yield f"[image unavailable: {asset.kind}]\n"
    if ocr:
        # OCR-sourced text — marked so it is distinguishable from authored text.
        yield "\n<!-- ocr -->\n"
        for line in ocr.splitlines():
            yield f"> {line}\n"
    yield "\n"


def _render_notes(notes: str) -> Iterator[str]:
    yield "> **Notes:**\n"
    for line in notes.splitlines():
        yield f"> {line}\n"
    yield "\n"


def render_deck(deck, assets: dict, ocr_text: dict, opts) -> Iterator[str]:
    """Stream Markdown for the whole deck, one slide at a time (R-A / R-D1).

    ``assets`` maps ``ImageRef -> MediaAsset|PlaceholderAsset`` (empty/absent →
    image skipped); ``ocr_text`` maps the resolved ``MediaAsset -> str`` (only when
    ``--ocr``). Pure generator over data → deterministic.
    """
    no_notes = bool(getattr(opts, "no_notes", False))
    for slide in deck.slides:
        yield f"## Slide {slide.index}\n\n"
        for block in slide.blocks:
            if isinstance(block, Heading):
                yield f"### {block.text}\n\n"
            elif isinstance(block, Bullets):
                yield from _render_bullets(block)
            elif isinstance(block, Table):
                yield from _render_table(block)
            elif isinstance(block, ImageRef):
                asset = assets.get(block)
                ocr = ""
                if isinstance(asset, MediaAsset):
                    ocr = ocr_text.get(asset, "") or ""
                yield from _render_image(block, asset, ocr)
            elif isinstance(block, Placeholder):
                yield f"[{block.kind}]\n\n"
        if slide.notes and not no_notes:
            yield from _render_notes(slide.notes)
