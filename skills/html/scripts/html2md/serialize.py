"""OP1 fetch-artifact (de)serialization + the untrusted-HTML sanitizer (TASK 027).

``html fetch`` materializes an arbitrary, *attacker-controlled* web page to disk as a
``.html`` that the pdf and docx skills then read/render. The monolith never did this — it
only ever ran turndown (a text transform) over fetched HTML — so two protections are added
here for the new trust boundary:

1. :func:`sanitize_untrusted_html` strips ``file:`` / ``javascript:`` / ``vbscript:``
   resource refs (and private-literal-host refs) from the saved HTML. The pdf renderers
   resolve ``file://`` with **no path confinement** (``html2pdf_lib/render.py`` /
   ``chrome_engine.py``), so an un-sanitized ``<img src="file:///…/.ssh/id_rsa">`` would be
   baked into a rendered PDF — a CWE-22 local-file exfiltration that did not exist before.
2. Images are **localized at the HTML ``<img src>`` level** into a sibling ``_attachments/``
   (sha1-deduped, relative links) so OP2 / pdf resolve them against ``base_url`` with the
   existing confinement and issue **no new network fetch**. The only remote fetch is the
   download here, which routes through the SSRF-guarded :func:`acquire._resolve_url_image`.

Honest scope: the sanitizer is a regex pass, not a full HTML/CSS parser — it neutralizes
the documented vectors (``src``/``href``/``srcset``/``poster``/``data``/``xlink:href`` and
CSS ``url(...)``) but a determined obfuscation could slip a ref past it; the Phase-3
``html2pdf.py --untrusted`` flag (renderer-side ``file://`` refusal) is the belt-and-suspenders.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import naming
from .model import AcquireResult, FetchArtifact, SourceMeta

SCHEMA = "html/fetch-artifact@1"

# Schemes that, in a renderer with file:// access, read local files or execute script.
# `data:` is intentionally NOT here: it is self-contained inline content (no file read).
_DANGER_SCHEME = "(?:file|javascript|vbscript)"
# Resource-bearing attributes whose value can point at a local file / script URL.
_RES_ATTR = r"(?:src|href|poster|data|formaction|background|xlink:href)"

# attr="file:..."  →  drop the value (keep the attribute shell so markup stays valid)
_ATTR_DANGER_RE = re.compile(
    r'(\b' + _RES_ATTR + r'\s*=\s*["\'])\s*' + _DANGER_SCHEME + r'\s*:[^"\']*(["\'])',
    re.IGNORECASE)
# srcset="… file:… …"  →  drop the whole srcset (any candidate using a dangerous scheme)
_SRCSET_DANGER_RE = re.compile(
    r'(\bsrcset\s*=\s*["\'])[^"\']*\b' + _DANGER_SCHEME + r'\s*:[^"\']*(["\'])',
    re.IGNORECASE)
# CSS url(file:…) in a style="" attr or a <style> block  →  url()
_CSS_URL_DANGER_RE = re.compile(
    r'url\(\s*["\']?\s*' + _DANGER_SCHEME + r'\s*:[^)]*\)', re.IGNORECASE)
# Private / loopback / link-local literal hosts in an http(s) resource ref (no DNS — a
# cheap defense-in-depth; full SSRF is handled at fetch time by _assert_public_http).
_PRIVATE_HOST_RE = re.compile(
    r'(\b' + _RES_ATTR + r'\s*=\s*["\'])\s*https?://'
    r'(?:localhost|127\.\d+|0\.0\.0\.0|169\.254\.|10\.\d+|192\.168\.|'
    r'172\.(?:1[6-9]|2\d|3[01])\.)[^"\']*(["\'])',
    re.IGNORECASE)


def sanitize_untrusted_html(html: str) -> str:
    """Neutralize ``file:`` / ``javascript:`` / ``vbscript:`` and private-host resource
    refs in untrusted HTML before it is written to disk (see module docstring)."""
    html = _ATTR_DANGER_RE.sub(r"\1\2", html)
    html = _SRCSET_DANGER_RE.sub(r"\1\2", html)
    html = _CSS_URL_DANGER_RE.sub("url()", html)
    html = _PRIVATE_HOST_RE.sub(r"\1\2", html)
    return html


def _localize_images(html: str, acq: AcquireResult, attach_dir: Path, attach_name: str,
                     *, max_images, opts) -> "tuple[str, bool]":
    """Download every resolvable ``<img src>`` into ``attach_dir`` (sha1-deduped) and
    rewrite it to ``<attach_name>/<sha1><ext>``. Returns ``(html, wrote_any)``.

    Local (relative/file://) srcs resolve against ``acq.base_url`` (CWE-22 confined);
    remote http(s) srcs go through the SSRF-guarded :func:`acquire._resolve_url_image`.
    """
    from . import acquire  # local import: acquire does not import serialize

    if acq.mode == "url" and acq.base_url:
        html = acquire._absolutize_img_srcs(html, acq.base_url)
    base = naming.base_dir(acq.base_url) if acq.mode in ("file", "archive") else None

    by_sha: dict[str, str] = {}
    src_to_link: dict[str, str] = {}
    written = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal written
        pre, src, post = m.group(1), m.group(2), m.group(3)
        if src in src_to_link:
            return pre + src_to_link[src] + post
        data = naming.resolve_local_image(src, base) if base is not None else None
        if data is None:
            if max_images is not None and written >= max_images:
                return m.group(0)
            data = acquire._resolve_url_image(src, opts)
        if data is None:
            return m.group(0)  # unresolved (file:/data:/broken) → left for the sanitizer
        sha = hashlib.sha1(data).hexdigest()
        if sha not in by_sha:
            if max_images is not None and written >= max_images:
                return m.group(0)
            fname = sha + naming.sniff_ext(src, data)
            attach_dir.mkdir(parents=True, exist_ok=True)
            (attach_dir / fname).write_bytes(data)
            by_sha[sha] = f"{attach_name}/{fname}"
            written += 1
        src_to_link[src] = by_sha[sha]
        return pre + by_sha[sha] + post

    html = acquire._IMG_SRC_RE.sub(_sub, html)
    return html, written > 0


def _is_authenticated(opts) -> bool:
    """True when the fetch replayed a credential — its rendered body is sensitive."""
    return any(getattr(opts, a, None) for a in (
        "chrome_storage_state", "chrome_cookies_file",
        "chrome_user_data_dir", "chrome_auth_map"))


def write_artifact(acq: AcquireResult, output_dir: Path, opts, *, input_ref: str) -> FetchArtifact:
    """OP1: localize images → sanitize → write ``<slug>.html`` + ``<slug>.meta.json``.

    Returns a :class:`FetchArtifact` describing what was written. An authenticated fetch's
    HTML + sidecar are written ``0600`` (the body may hold session-bound/private content).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = naming.slugify(naming.base_name(acq.mode, input_ref))
    attach_name = getattr(opts, "attachments_dir", "_attachments")
    attach_dir = output_dir / attach_name

    html = acq.html
    wrote_imgs = False
    if getattr(opts, "download_images", True):
        html, wrote_imgs = _localize_images(
            html, acq, attach_dir, attach_name,
            max_images=getattr(opts, "max_images", None), opts=opts)

    # Sanitize AFTER localization: legit local images are now relative `_attachments/…`
    # links; any remaining file:/javascript: ref (non-img, or an out-of-base img the
    # CWE-22 confinement refused to download) is neutralized before it reaches a renderer.
    html = sanitize_untrusted_html(html)

    # Collision-free base name, keyed on the original source URL (round-trip idempotent).
    provenance = (acq.source_meta.url if acq.source_meta and acq.source_meta.url
                  else input_ref)
    marker = naming.src_marker(provenance)
    base = naming.resolve_base(output_dir, slug, marker)
    html_path = output_dir / f"{base}.html"
    meta_path = output_dir / f"{base}.meta.json"

    sidecar = {
        "schema": SCHEMA,
        "source": acq.source_meta.url if acq.source_meta else None,
        "title": acq.source_meta.title if acq.source_meta else None,
        "date": acq.source_meta.date if acq.source_meta else None,
        "author": acq.source_meta.author if acq.source_meta else None,
        "engine": getattr(acq, "engine", None),
        "content_kind": getattr(acq, "content_kind", "html"),
        "base_kind": "dir",
        "input_ref": input_ref,
    }
    naming.atomic_write(html_path, html if html.endswith("\n") else html + "\n")
    naming.atomic_write(meta_path, json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n")

    if _is_authenticated(opts):  # bearer-derived body → owner-only (mirror the login mint)
        for p in (html_path, meta_path):
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass

    return FetchArtifact(
        html_path=html_path,
        meta_path=meta_path,
        attachments_dir=(attach_dir if wrote_imgs else None),
        source_meta=acq.source_meta if acq.source_meta else SourceMeta(),
        engine=getattr(acq, "engine", None),
        base_url=str(output_dir.resolve()),
    )


def read_artifact(html_path: Path) -> AcquireResult:
    """OP2 input: load ``<slug>.html`` + (when present) its ``<slug>.meta.json`` sidecar.

    Frontmatter is recovered from the sidecar (preferred — it carries the trafilatura-grade
    title/author/date + the real origin URL the live fetch computed); a hand-saved ``.html``
    with no sidecar degrades gracefully to HTML-derived metadata. ``base_url`` is the html
    file's parent dir, so the localized ``_attachments/`` images resolve.
    """
    from . import acquire  # for the no-sidecar metadata fallback

    html_path = Path(html_path)
    html = html_path.read_text(encoding="utf-8", errors="replace")
    base_url = str(html_path.parent.resolve())
    meta_path = html_path.with_name(html_path.stem + ".meta.json")  # <base>.html → <base>.meta.json

    if meta_path.is_file():
        try:
            d = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            d = {}
        meta = SourceMeta(url=d.get("source"), title=d.get("title"),
                          date=d.get("date"), author=d.get("author"))
        return AcquireResult(
            html=html, base_url=base_url, mode="file",
            engine=d.get("engine"), source_meta=meta,
            content_kind=d.get("content_kind", "html"))

    # No sidecar → derive metadata from the HTML itself (file-branch behaviour).
    meta = acquire._meta_from_html(html, url=Path(html_path).resolve().as_uri())
    return AcquireResult(html=html, base_url=base_url, mode="file",
                         engine=None, source_meta=meta, content_kind="html")
