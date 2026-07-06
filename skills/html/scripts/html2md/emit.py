"""FC-4 — Markdown assembly + Obsidian wrapping (ARCH §2.1, §4.3).

Builds YAML frontmatter, optionally downloads images into a shared ``_attachments/``
(sha1-deduped, relative links), and writes dual-output (``<slug>.md`` +
``<slug>.reader.md``) or streams the whole-page Markdown to stdout.

Slug / provenance-marker / collision / local-image helpers live in ``naming`` (shared
with the OP1 fetch artifact); this module imports them under their historical private
names. Remote (http/https) image download is wired via
:func:`html2md.acquire._resolve_url_image`.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import sys
import urllib.parse
from pathlib import Path

from .exceptions import SelfOverwriteRefused
from .model import AcquireResult, CleanResult, SourceMeta
from .naming import (  # shared with serialize (OP1) — re-aliased to the historical names
    atomic_write as _atomic_write,
    base_dir as _base_dir,
    base_name as _base_name,
    resolve_base as _resolve_base,
    resolve_local_image as _resolve_local_image,
    sniff_ext as _sniff_ext,
    slugify as _slugify,
    src_marker as _src_marker,
)

# Markdown image syntax: ![alt](src "optional title") or ![alt](<src with spaces>).
# A bare destination has no ')' or whitespace (a data: URI is captured whole — base64
# alphabet + the mime prefix exclude both); an angle-bracketed destination (CommonMark)
# may contain spaces/parens — html_convert.js emits that form for localized archive
# subresources whose decoded filenames carry spaces (e.g. Confluence attachments).
# Groups: 1=alt, 2=bracketed src, 3=bare src, 4=title.
_IMG_RE = re.compile(r'!\[([^\]]*)\]\(\s*(?:<([^<>\n]*)>|([^)\s>]+))(\s+"[^"]*")?\s*\)')


def _img_src(m: re.Match) -> str:
    """The destination of an ``_IMG_RE`` match, whichever alternative matched."""
    return m.group(2) if m.group(2) is not None else m.group(3)

# data:[<mediatype>][;base64],<payload>  (RFC 2397). <mediatype> = mime *(";" param), so
# the metadata segment is everything up to the FIRST comma; ``;base64`` (if present) is its
# last token. We split on that comma rather than a fixed ``;base64`` slot so media-type
# parameters (e.g. ``image/svg+xml;charset=utf-8;base64``) are tolerated.
_DATA_URI_RE = re.compile(r'(?i)^data:([^,]*),(.*)$', re.DOTALL)
# Kept in sync with html_convert.js DATA_URI_MIN_LEN — the JS converter already drops
# sub-threshold data: images, so this is a defense-in-depth floor for the file/round-trip
# path (a fetched artifact whose <img> still carries an inline data: URI).
_DATA_URI_MIN_LEN = 1024          # min ENCODED URI length (fast reject)
_DATA_URI_MIN_DECODED = 512       # min DECODED bytes (icon-vs-content; catches percent-encoded)


def _strip_data_images(md: str | None) -> str | None:
    """Drop inline ``![](data:…)`` images from Markdown. Used when we will NOT localize
    them (stdout mode) so a content-sized data: image does not dump a multi-KB base64 blob
    into the stream — restoring the clean-text guarantee of the universal agent step
    (SKILL §7.3). Non-data images are left untouched."""
    if md is None:
        return None
    return _IMG_RE.sub(
        lambda m: "" if _img_src(m)[:5].lower() == "data:" else m.group(0), md)


def _decode_data_uri(src: str) -> bytes | None:
    """Decode a ``data:`` image URI → raw bytes (``None`` if not a usable data: image).

    Handles base64 and percent-encoded payloads, with or without media-type parameters.
    Sub-threshold blobs (tiny icons) and non-image / malformed URIs return ``None`` so they
    are left untouched, never written."""
    if len(src) < _DATA_URI_MIN_LEN:
        return None
    m = _DATA_URI_RE.match(src)
    if not m:
        return None
    meta, payload = m.group(1).strip(), m.group(2)
    is_b64 = meta.lower().endswith(";base64")
    mime = meta.split(";", 1)[0].strip().lower()
    if mime and not mime.startswith("image/"):
        return None  # only localize images (svg/png/jpeg/…); skip data:text/* etc.
    try:
        raw = (base64.b64decode(payload, validate=False) if is_b64
               else urllib.parse.unquote_to_bytes(payload))
    except (binascii.Error, ValueError):
        return None
    if not raw:
        return None  # all-garbage base64 decodes to b"" under validate=False → drop
    # The encoded-length floor above is a fast reject, but percent-encoding expands ~3× so a
    # tiny icon can clear it; re-check the DECODED size (the quantity the "drop tiny icons"
    # intent is really about). Real content diagrams are multi-KB; sub-512-byte blobs are icons.
    if len(raw) < _DATA_URI_MIN_DECODED:
        return None
    return raw

# --reader-only fallback: a reader extraction whose body is shorter than this is treated as
# empty/over-stripped → fall back to the faithful whole page (mirrors wiki-import's heuristic).
_READER_ONLY_MIN_BODY = 200


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


# --------------------------------------------------------------------------- #
# Image download + link rewrite (Markdown level)
# --------------------------------------------------------------------------- #
def _download_and_rewrite(
    markdowns: list[str | None],
    acq: AcquireResult,
    *,
    attach_dir,
    attach_name: str,
    max_images: int | None,
    remote_resolver=None,
) -> list[str | None]:
    """Download every resolvable image referenced in ``markdowns`` into ``attach_dir``
    (sha1-deduped) and rewrite the links to ``<attach_name>/<sha1><ext>``. The SAME
    sha1 map is shared across all markdown variants so identical bytes map to ONE file.

    Local (relative/file://) images are read from ``acq.base_url`` (confined). Remote
    (http/https) images are fetched via ``remote_resolver(src) -> bytes|None`` when
    provided (url-mode); otherwise left as the original link.
    """
    base = _base_dir(acq.base_url)
    by_sha: dict[str, str] = {}          # sha1 -> relative link
    src_to_link: dict[str, str] = {}     # original src -> rewritten link (cache)
    written = 0

    def _rewrite(md: str | None) -> str | None:
        nonlocal written
        if md is None:
            return None

        def _sub(m: re.Match) -> str:
            nonlocal written
            alt, src, title = m.group(1), _img_src(m), m.group(4) or ""
            if src in src_to_link:
                return f"![{alt}]({src_to_link[src]}{title})"
            # Inline data: image → decode to bytes (offline; no network, no base_dir read).
            # Identical URIs hit src_to_link below; identical decoded bytes from different
            # URIs still collapse to one file via the sha1 map.
            data = _decode_data_uri(src) if src[:5].lower() == "data:" else None
            if data is None:
                data = _resolve_local_image(src, base)
            if data is None and remote_resolver is not None:
                # Gate the REMOTE fetch by --max-images BEFORE issuing it, so the cap
                # bounds outbound network requests (SSRF amplification), not just disk
                # writes. Local resolution above is offline + base_dir-confined.
                if max_images is not None and written >= max_images:
                    return m.group(0)
                data = remote_resolver(src)  # url-mode remote fetch
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
def emit(
    acq: AcquireResult,
    clean_res: CleanResult,
    md_whole: str,
    md_reader: str | None,
    opts,
    *,
    output_dir,
    stdout_mode: bool,
    input_ref: str,
    query: str | None = None,
) -> None:
    """Write frontmatter + Markdown (+ optional attachments / reader variant), or
    stream the whole-page Markdown to stdout."""
    front = _frontmatter(acq.source_meta, query, getattr(acq, "engine", None))

    # --reader-only: collapse to a SINGLE output = the reader extraction, falling back to
    # the faithful whole page when the reader is empty/over-stripped (so a note is never
    # empty). Reuses the single-output path (md_reader=None ⇒ one <slug>.md, no .reader.md,
    # stdout streams the reader content). Not applied to --search results (one note each).
    if query is None and getattr(opts, "reader_only", False):
        md_whole = (md_reader if (md_reader is not None
                                  and len(md_reader.strip()) >= _READER_ONLY_MIN_BODY)
                    else md_whole)
        md_reader = None

    # stdout mode: single Markdown body to stdout, no files, no image download (ARCH §5.1).
    # Strip inline data: images — they can't be localized here and a content-sized blob
    # would dump KBs of base64 into the stream (agent-step bloat).
    if stdout_mode:
        sys.stdout.write(front + (_strip_data_images(md_whole) or "").strip() + "\n")
        return

    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)  # lazy: only once a write is certain
    slug = _slugify(_base_name(acq.mode, input_ref))
    attach_name = getattr(opts, "attachments_dir", "_attachments")
    attach_dir = output_dir / attach_name

    if getattr(opts, "download_images", True):
        remote_resolver = None
        # Enable the SSRF-guarded remote fetch for url-mode AND file-mode (a fetched
        # artifact whose <img> may still be absolute http(s) — e.g. `fetch --no-images`
        # then `md` — must still recover images; round-trip fix #2). Archives are
        # self-contained, so they stay local-only.
        if acq.mode in ("url", "file"):
            from . import acquire as _acquire_mod
            remote_resolver = lambda src: _acquire_mod._resolve_url_image(src, opts)  # noqa: E731
        md_whole, md_reader = _download_and_rewrite(
            [md_whole, md_reader], acq,
            attach_dir=attach_dir, attach_name=attach_name,
            max_images=getattr(opts, "max_images", None),
            remote_resolver=remote_resolver,
        )

    # Collision-free, idempotent output base (slug / slug-2 / slug-3 …). Key the marker on
    # the original source URL when known (round-trip idempotency), else the input path.
    provenance = (acq.source_meta.url if acq.source_meta and acq.source_meta.url
                  else input_ref)
    marker = _src_marker(provenance)
    base = _resolve_base(output_dir, slug, marker)
    out_md = output_dir / f"{base}.md"
    out_reader = output_dir / f"{base}.reader.md"

    # File-level self-overwrite guard (the dir-vs-file check in _resolve_paths can't see
    # this): never let an emitted file clobber the INPUT being converted (e.g. a fetch→md
    # round-trip in the same folder, or a local input whose name collides with an output).
    try:
        in_resolved = Path(input_ref).resolve()
        if out_md.resolve() == in_resolved or out_reader.resolve() == in_resolved:
            raise SelfOverwriteRefused(
                f"output would overwrite the input: {Path(input_ref).name}",
                details={"path": Path(input_ref).name})
    except OSError:
        pass  # input_ref is a URL or unresolvable → no local collision possible

    _atomic_write(out_md, front + md_whole.strip() + "\n\n" + marker + "\n")
    if md_reader is not None:
        _atomic_write(out_reader, front + md_reader.strip() + "\n\n" + marker + "\n")
    elif out_reader.exists():
        # A prior run wrote <base>.reader.md; this --no-reader / search re-run must not
        # leave a stale phantom dual-output for downstream (Obsidian/docx/pdf) to pick up.
        out_reader.unlink(missing_ok=True)
