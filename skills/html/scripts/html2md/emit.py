"""FC-4 — Markdown assembly + Obsidian wrapping (ARCH §2.1, §4.3).

Builds YAML frontmatter, optionally downloads images into a shared ``_attachments/``
(sha1-deduped, relative links), and writes dual-output (``<slug>.md`` +
``<slug>.reader.md``) or streams the whole-page Markdown to stdout.

Image resolution in this bead is OFFLINE only (archive/file inputs, whose <img>
src resolve against ``acq.base_url``). Remote (http/https) image download is wired
in bead 022-06 via :func:`html2md.acquire._resolve_url_image`.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .model import AcquireResult, CleanResult, SourceMeta

# Markdown image syntax: ![alt](src "optional title")
_IMG_RE = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(\s+"[^"]*")?\s*\)')
_SVG_HEAD = (b"<svg", b"<?xml")


# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #
def _yaml_escape(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    value = re.sub(r"[\r\n]+", " ", value)  # keep the scalar single-line (no stray `---`)
    return '"' + value + '"'


def _frontmatter(meta: SourceMeta, query: str | None = None,
                 engine: str | None = None) -> str:
    """YAML frontmatter block from the source metadata (ARCH §4.3). ``query`` is set for
    ``--search`` results; ``engine`` records the real fetch tier (provenance — TASK 023 R6)."""
    lines = ["---"]
    for key, val in (("source", meta.url), ("title", meta.title),
                     ("date", meta.date), ("author", meta.author)):
        if val:
            lines.append(f"{key}: {_yaml_escape(val)}")
    if engine:
        lines.append(f"engine: {_yaml_escape(engine)}")
    if query:
        lines.append(f"query: {_yaml_escape(query)}")
    lines.append("tags: []")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "untitled"


def _base_name(acq: AcquireResult, input_ref: str) -> str:
    """Deterministic output base name from the INPUT (filename / URL path stem).

    The human title lives in frontmatter; the file name is derived from the input
    so the same input always yields the same output name (agent-friendly).
    """
    if acq.mode == "url":
        parsed = urlparse(input_ref)
        last = Path(parsed.path).name or parsed.netloc or "page"
        return Path(last).stem or "page"
    return Path(input_ref).stem


# --------------------------------------------------------------------------- #
# Image resolution (offline)
# --------------------------------------------------------------------------- #
def _base_dir(base_url: str) -> Path:
    if base_url.startswith("file://"):
        return Path(url2pathname(urlparse(base_url).path))
    return Path(base_url)


def _sniff_ext(src: str, data: bytes) -> str:
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


def _resolve_local_image(src: str, base_dir: Path) -> bytes | None:
    """Read bytes for a local (relative / file://) image src; None if unresolved.

    SECURITY (CWE-22 / CWE-73): the ``src`` is attacker-controlled (it comes from the
    HTML of an untrusted page/archive). Reads are **confined to ``base_dir``** so a
    crafted ``<img src="../../etc/passwd">`` / ``/etc/passwd`` / ``file:///etc/passwd``
    cannot read arbitrary off-disk files into the user's vault. Legitimate archive/file
    images are always bare names inside ``base_dir`` (``web_clean`` localizes them), so
    confinement breaks no real input.
    """
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https", "data"):
        return None  # remote/data — download lands in 022-06
    if parsed.scheme == "file":
        candidate = Path(url2pathname(parsed.path))
    else:
        rel = unquote(src)
        candidate = Path(rel) if os.path.isabs(rel) else (base_dir / rel)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base_dir.resolve())  # ValueError if outside base_dir
    except (OSError, ValueError):
        return None
    try:
        return resolved.read_bytes()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Image download + link rewrite
# --------------------------------------------------------------------------- #
def _download_and_rewrite(
    markdowns: list[str | None],
    acq: AcquireResult,
    *,
    attach_dir: Path,
    attach_name: str,
    max_images: int | None,
    remote_resolver=None,
) -> list[str | None]:
    """Download every resolvable image referenced in ``markdowns`` into ``attach_dir``
    (sha1-deduped) and rewrite the links to ``<attach_name>/<sha1><ext>``. The SAME
    sha1 map is shared across all markdown variants so identical bytes map to ONE file.

    Local (relative/file://) images are read from ``acq.base_url`` (confined). Remote
    (http/https) images are fetched via ``remote_resolver(src) -> bytes|None`` when
    provided (url-mode, 022-06); otherwise left as the original link.
    """
    base_dir = _base_dir(acq.base_url)
    by_sha: dict[str, str] = {}          # sha1 -> relative link
    src_to_link: dict[str, str] = {}     # original src -> rewritten link (cache)
    written = 0

    def _rewrite(md: str | None) -> str | None:
        nonlocal written
        if md is None:
            return None

        def _sub(m: re.Match) -> str:
            nonlocal written
            alt, src, title = m.group(1), m.group(2), m.group(3) or ""
            if src in src_to_link:
                return f"![{alt}]({src_to_link[src]}{title})"
            data = _resolve_local_image(src, base_dir)
            if data is None and remote_resolver is not None:
                # Gate the REMOTE fetch by --max-images BEFORE issuing it, so the cap
                # bounds outbound network requests (SSRF amplification), not just disk
                # writes. Local resolution above is offline + base_dir-confined.
                if max_images is not None and written >= max_images:
                    return m.group(0)
                data = remote_resolver(src)  # url-mode remote fetch (022-06)
            if data is None:
                return m.group(0)  # leave remote/unresolved untouched
            sha = hashlib.sha1(data).hexdigest()
            if sha not in by_sha:
                if max_images is not None and written >= max_images:
                    return m.group(0)
                fname = sha + _sniff_ext(src, data)
                attach_dir.mkdir(parents=True, exist_ok=True)
                (attach_dir / fname).write_bytes(data)
                by_sha[sha] = f"{attach_name}/{fname}"
                written += 1
            src_to_link[src] = by_sha[sha]
            return f"![{alt}]({by_sha[sha]}{title})"

        return _IMG_RE.sub(_sub, md)

    return [_rewrite(md) for md in markdowns]


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        tmp.write_text(text, encoding="utf-8")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)


def _src_marker(input_ref: str) -> str:
    """A stable, opaque per-input provenance marker (invisible HTML comment).

    A short hash of the INPUT — never the raw path (no local-path leak) — so two
    DIFFERENT inputs that slugify to the same name get distinct output files, while
    re-running the SAME input overwrites its own file (idempotent).
    """
    sid = hashlib.sha1(input_ref.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return f"<!-- html2md-source-id: {sid} -->"


def _resolve_base(output_dir: Path, slug: str, marker: str, *, cap: int = 10000) -> str:
    """Pick a collision-free output base name in ``output_dir``.

    ``slug`` for the first claimant; ``slug-2``, ``slug-3``, … for distinct inputs
    that collide. An existing ``<base>.md`` is reused (overwritten) ONLY if it carries
    THIS input's ``marker`` — so re-running the same input is idempotent, while a
    different input never silently clobbers it.
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


def emit(
    acq: AcquireResult,
    clean_res: CleanResult,
    md_whole: str,
    md_reader: str | None,
    opts,
    *,
    output_dir: Path | None,
    stdout_mode: bool,
    input_ref: str,
    query: str | None = None,
) -> None:
    """Write frontmatter + Markdown (+ optional attachments / reader variant), or
    stream the whole-page Markdown to stdout."""
    front = _frontmatter(acq.source_meta, query, getattr(acq, "engine", None))

    # stdout mode: whole-page Markdown only, no files, no image download (ARCH §5.1).
    if stdout_mode:
        sys.stdout.write(front + md_whole.strip() + "\n")
        return

    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)  # lazy: only once a write is certain
    slug = _slugify(_base_name(acq, input_ref))
    attach_name = getattr(opts, "attachments_dir", "_attachments")
    attach_dir = output_dir / attach_name

    if getattr(opts, "download_images", True):
        remote_resolver = None
        if acq.mode == "url":
            from . import acquire as _acquire_mod
            remote_resolver = lambda src: _acquire_mod._resolve_url_image(src, opts)  # noqa: E731
        md_whole, md_reader = _download_and_rewrite(
            [md_whole, md_reader], acq,
            attach_dir=attach_dir, attach_name=attach_name,
            max_images=getattr(opts, "max_images", None),
            remote_resolver=remote_resolver,
        )

    # Collision-free, idempotent output base (slug / slug-2 / slug-3 …).
    marker = _src_marker(input_ref)
    base = _resolve_base(output_dir, slug, marker)
    _atomic_write(output_dir / f"{base}.md",
                  front + md_whole.strip() + "\n\n" + marker + "\n")
    if md_reader is not None:
        _atomic_write(output_dir / f"{base}.reader.md",
                      front + md_reader.strip() + "\n\n" + marker + "\n")
