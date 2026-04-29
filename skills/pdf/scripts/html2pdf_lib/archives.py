"""Archive extraction for `.mhtml` and `.webarchive` inputs.

Both formats package an HTML document plus its sub-resources (images,
CSS, fonts) into a single file:

  * `.mhtml` / `.mht`: MIME multipart, parsed via `email.message_from_bytes`.
  * `.webarchive`: Apple binary plist, parsed via `plistlib`.

The extractor writes sub-resources into a caller-supplied work directory,
rewrites URLs in the HTML and CSS to local filenames, strips remote
@font-face declarations from extracted CSS, and returns
`(html_text, base_url)` ready for `render.convert()`.
"""
from __future__ import annotations

import email
import email.policy
import plistlib
import re
import urllib.parse
from pathlib import Path

from .preprocess import strip_all_fontfaces


def _make_absolute_urls(text: str, page_url: str) -> str:
    """Rewrite root-relative (/) and protocol-relative (//) URLs to absolute.

    Root-relative paths like /assets/app.css appear in HTML attribute values
    and CSS url() calls, but the webarchive/MHTML subresource map stores full
    absolute URLs. Converting them here makes _rewrite_urls able to match and
    localise them.

    page_url is the archive's declared origin URL (e.g. https://vc.ru/).
    """
    parsed = urllib.parse.urlparse(page_url)
    if not parsed.scheme or not parsed.netloc:
        return text
    origin = f"{parsed.scheme}://{parsed.netloc}"
    scheme = parsed.scheme

    def _fix_url(url: str) -> str:
        if url.startswith("//"):
            return scheme + ":" + url
        if url.startswith("/"):
            return origin + url
        return url

    def _fix_attr(m: re.Match) -> str:
        return m.group(1) + _fix_url(m.group(2)) + m.group(3)

    def _fix_css_url(m: re.Match) -> str:
        return m.group(1) + _fix_url(m.group(2)) + m.group(3)

    # HTML attributes: href="...", src="...", action="...", data-src="..."
    text = re.sub(
        r'((?:href|src|action|data-src)\s*=\s*["\'])([^"\']*?)(["\'])',
        _fix_attr,
        text,
        flags=re.IGNORECASE,
    )
    # CSS url() values (handles quoted and unquoted)
    text = re.sub(
        r'(url\s*\(\s*["\']?)([^"\')\s]+)(["\']?\s*\))',
        _fix_css_url,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _rewrite_urls(text: str, url_map: dict[str, str]) -> str:
    """Replace every key in url_map with its local filename in text."""
    for url, local in url_map.items():
        text = text.replace(url, local)
    return text


def _fixup_css_subresources(
    css_parts: list[tuple[Path, bytes]],
    page_url: str,
    url_map: dict[str, str],
) -> None:
    """Rewrite URL references inside extracted CSS files in-place.

    Called by both extract_mhtml and extract_webarchive after all
    sub-resources have been written to disk. Strips @font-face blocks
    and rewrites absolute/root-relative URLs to local filenames so
    weasyprint can resolve @font-face / background-image without
    a network round-trip.
    """
    for css_path, css_raw in css_parts:
        css_text = css_raw.decode("utf-8", errors="replace")
        css_text = _make_absolute_urls(css_text, page_url)
        css_text = strip_all_fontfaces(css_text)
        css_text = _rewrite_urls(css_text, url_map)
        css_path.write_text(css_text, encoding="utf-8")


def extract_mhtml(src: Path, work_dir: Path) -> tuple[str, str]:
    """Parse a MIME HTML archive into work_dir.

    Returns (html_text, base_url) where base_url is str(work_dir).
    Sub-resources are written to work_dir; relative URL references in
    the HTML are rewritten to their local filenames so weasyprint can
    resolve them without a network. CSS subresources also have their
    URLs rewritten so embedded @font-face / background-image references
    resolve correctly from the temp dir.
    """
    raw = src.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    html_bytes: bytes | None = None
    page_url: str = ""
    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []   # (dest_path, raw_bytes)

    for part in msg.walk():
        ct      = part.get_content_type()
        loc     = part.get("Content-Location", "")
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if ct == "text/html" and html_bytes is None:
            html_bytes = payload
            page_url = loc  # origin URL for root-relative resolution
        elif loc:
            fname = Path(urllib.parse.unquote(loc.split("?")[0])).name or "resource"
            dest  = work_dir / fname
            idx   = 0
            while dest.exists():          # deduplicate on collision
                idx += 1
                dest = work_dir / f"{idx}_{fname}"
            dest.write_bytes(payload)
            url_map[loc] = dest.name
            if ct == "text/css":
                css_parts.append((dest, payload))

    if html_bytes is None:
        raise ValueError(f"no text/html part found in {src.name}")

    html_text = html_bytes.decode("utf-8", errors="replace")
    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)

    _fixup_css_subresources(css_parts, page_url, url_map)
    return html_text, str(work_dir)


def extract_webarchive(src: Path, work_dir: Path) -> tuple[str, str]:
    """Parse an Apple WebKit binary-plist archive into work_dir.

    Returns (html_text, base_url) where base_url is str(work_dir).
    Sub-resources (images, CSS, fonts) are written to work_dir and
    absolute URLs in the HTML are rewritten to their local filenames.
    CSS subresources also have their URLs rewritten so embedded
    @font-face / background-image references resolve correctly.
    """
    with open(src, "rb") as f:
        plist = plistlib.load(f)

    main = plist.get("WebMainResource", {})
    html_data = main.get("WebResourceData", b"")
    enc       = main.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
    page_url  = main.get("WebResourceURL", "")
    html_text = (
        html_data.decode(enc, errors="replace")
        if isinstance(html_data, bytes)
        else str(html_data)
    )

    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []

    for sub in plist.get("WebSubresources", []):
        url  = sub.get("WebResourceURL", "")
        mime = sub.get("WebResourceMIMEType", "")
        data = sub.get("WebResourceData", b"")
        if not url or not isinstance(data, bytes) or not data:
            continue
        # Skip data: URIs — they are already inline in the HTML/CSS.
        if url.startswith("data:"):
            continue
        fname = Path(urllib.parse.unquote(url.split("?")[0])).name or "resource"
        dest  = work_dir / fname
        idx   = 0
        while dest.exists():
            idx += 1
            dest = work_dir / f"{idx}_{fname}"
        dest.write_bytes(data)
        url_map[url] = dest.name
        if mime == "text/css":
            css_parts.append((dest, data))

    # Resolve root-relative (/path) and protocol-relative (//host) URLs to
    # absolute before URL rewriting — the subresource map stores full URLs,
    # so root-relative paths in the HTML would never match otherwise.
    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)

    _fixup_css_subresources(css_parts, page_url, url_map)
    return html_text, str(work_dir)
