"""Shared naming / output / local-image helpers (used by both OP1 fetch and OP2 emit).

Extracted from ``emit`` so the fetch artifact (``serialize``) and the Markdown emit
(``emit``) derive identical slugs, provenance markers, collision-free output names, and
resolve local images with the same CWE-22 confinement. Pure helpers — no package
imports beyond the stdlib.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

_SVG_HEAD = (b"<svg", b"<?xml")


# --------------------------------------------------------------------------- #
# Slug / base name / provenance marker / collision-free output base
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "untitled"


def base_name(mode: str, input_ref: str) -> str:
    """Deterministic output base name from the INPUT (filename / URL path stem).

    The human title lives in frontmatter; the file name is derived from the input
    so the same input always yields the same output name (agent-friendly).
    """
    if mode == "url":
        parsed = urlparse(input_ref)
        last = Path(parsed.path).name or parsed.netloc or "page"
        return Path(last).stem or "page"
    return Path(input_ref).stem


def src_marker(provenance: str) -> str:
    """A stable, opaque provenance marker (invisible HTML comment).

    A short hash of ``provenance`` (the original source URL when known, else the input
    path) — never the raw path (no local-path leak) — so two DIFFERENT inputs that
    slugify to the same name get distinct output files, while re-running the SAME source
    overwrites its own file (idempotent). Keying on the recorded source URL (not the
    transient local artifact path) keeps the fetch→md round-trip idempotent.
    """
    sid = hashlib.sha1(provenance.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return f"<!-- html-source-id: {sid} -->"


def resolve_base(output_dir: Path, slug: str, marker: str, *, cap: int = 10000) -> str:
    """Pick a collision-free output base name in ``output_dir``.

    ``slug`` for the first claimant; ``slug-2``, ``slug-3``, … for distinct inputs that
    collide. An existing ``<base>.md`` is reused (overwritten) ONLY if it carries THIS
    input's ``marker`` — so re-running the same input is idempotent, while a different
    input never silently clobbers it.
    """
    for i in range(cap):
        base = slug if i == 0 else f"{slug}-{i + 1}"
        md = output_dir / f"{base}.md"
        if not md.exists():
            return base
        try:
            if marker in md.read_text(encoding="utf-8", errors="replace"):
                return base  # our own prior output → idempotent overwrite
        except OSError:
            pass
    return f"{slug}-{marker[-15:-4]}"  # pathological fallback (unbounded collisions)


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        tmp.write_text(text, encoding="utf-8")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Local-image resolution (offline, base_dir-confined) + extension sniffing
# --------------------------------------------------------------------------- #
def base_dir(base_url: str) -> Path:
    if base_url.startswith("file://"):
        return Path(url2pathname(urlparse(base_url).path))
    return Path(base_url)


def sniff_ext(src: str, data: bytes) -> str:
    ext = Path(urlparse(src).path).suffix.lower()
    if ext and len(ext) <= 5 and re.fullmatch(r"\.[a-z0-9]+", ext):
        return ext
    if data[:8].startswith(b"\x89PNG"):
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.lstrip()[:5].lower().startswith(_SVG_HEAD):
        return ".svg"
    return ".img"


def resolve_local_image(src: str, base: Path) -> bytes | None:
    """Read bytes for a local (relative / file://) image src; None if unresolved.

    SECURITY (CWE-22 / CWE-73): the ``src`` is attacker-controlled (it comes from the
    HTML of an untrusted page/archive). Reads are **confined to ``base``** so a crafted
    ``<img src="../../etc/passwd">`` / ``/etc/passwd`` / ``file:///etc/passwd`` cannot
    read arbitrary off-disk files. Legitimate archive/file images are always bare names
    inside ``base`` (``web_clean`` localizes them), so confinement breaks no real input.
    """
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https", "data"):
        return None  # remote/data — handled by the remote resolver
    if parsed.scheme == "file":
        candidate = Path(url2pathname(parsed.path))
    else:
        rel = unquote(src)
        candidate = Path(rel) if os.path.isabs(rel) else (base / rel)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base.resolve())  # ValueError if outside base
    except (OSError, ValueError):
        return None
    try:
        return resolved.read_bytes()
    except OSError:
        return None
