"""Archive extraction for `.mhtml` and `.webarchive` inputs.

Both formats package an HTML document plus its sub-resources (images,
CSS, fonts) into a single file:

  * `.mhtml` / `.mht`: MIME multipart, parsed via `email.message_from_bytes`.
  * `.webarchive`: Apple binary plist, parsed via `plistlib`.

The extractor writes sub-resources into a caller-supplied work directory,
rewrites URLs in the HTML and CSS to local filenames, strips remote
@font-face declarations from extracted CSS, and returns
`(html_text, base_url)` ready for `render.convert()`.

pdf-8: subframe-aware extraction for both formats. Webarchive carries
nested `WebSubframeArchives` (Safari iframe captures); MHTML carries
multiple `text/html` parts (Chrome iframe captures). Both surface as
"inner frames" under a unified `FrameInfo` view; `extract_archive` picks
one (`main`/`N`/`all`/`auto`) based on a structural "substantial"
heuristic — no vendor allow-list. See `list_archive_frames` for the
format-agnostic inventory used by `--list-frames`.
"""
from __future__ import annotations

import email
import email.policy
import hashlib
import plistlib
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .preprocess import strip_all_fontfaces


# ───────────────────────── URL rewriting helpers ──────────────────────────

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

    text = re.sub(
        r'((?:href|src|action|data-src)\s*=\s*["\'])([^"\']*?)(["\'])',
        _fix_attr,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'(url\s*\(\s*["\']?)([^"\')\s]+)(["\']?\s*\))',
        _fix_css_url,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _rewrite_urls(text: str, url_map: dict[str, str]) -> str:
    """Replace every key in url_map with its local filename in text.

    Critical: HTML attribute values escape `&` as `&amp;`, but
    webarchive/MHTML subresource URLs are stored unescaped. A signed-S3
    URL `https://x/img.jpg?a=1&b=2` ends up in HTML as
    `<img src="https://x/img.jpg?a=1&amp;b=2">`. Naive
    `text.replace(unescaped, local)` leaves the HTML untouched and the
    image silently fails to render (offline-fetcher refuses remote
    URL). Rewrite BOTH escaped and unescaped variants. Discovered via
    VDD-adversarial review on `email_list_client.webarchive` frame_1
    (S3 signed URL with `&` in query): JPEG was extracted to disk but
    HTML still pointed at the remote URL.

    Other HTML entities (`&lt;`, `&gt;`, `&quot;`, `&#x26;`, etc.) are
    not URL-legal so they don't appear in `<img src=>` attribute values
    in practice. We handle only `&amp;` because it's the one that
    legitimately escapes a URL-legal character.
    """
    for url, local in url_map.items():
        text = text.replace(url, local)
        # Also rewrite the html-encoded form. Cheap — replace is no-op
        # when the encoded form doesn't appear.
        if "&" in url:
            text = text.replace(url.replace("&", "&amp;"), local)
    return text


def _fixup_css_subresources(
    css_parts: list[tuple[Path, bytes]],
    page_url: str,
    url_map: dict[str, str],
) -> None:
    """Rewrite URL references inside extracted CSS files in-place.

    Strips @font-face blocks and rewrites absolute/root-relative URLs to
    local filenames so weasyprint can resolve @font-face / background-image
    without a network round-trip.
    """
    for css_path, css_raw in css_parts:
        css_text = css_raw.decode("utf-8", errors="replace")
        css_text = _make_absolute_urls(css_text, page_url)
        css_text = strip_all_fontfaces(css_text)
        css_text = _rewrite_urls(css_text, url_map)
        css_path.write_text(css_text, encoding="utf-8")


# ───────────────────────── Substantial-frame heuristic ──────────────────────

# pdf-8: structural heuristic to classify "is this inner frame real content
# or a system widget?". No vendor allow-list — purely shape-based:
#
#   * HTML payload ≥ 1 KB (excludes empty placeholders / tiny error frames)
#   * zero <script> tags inside (excludes auth widgets, hovercards, ad
#     iframes — all of which are JS-driven; real email/document iframes
#     are typically static HTML)
#   * body plain text ≥ 100 chars (excludes tracking-pixel iframes whose
#     body is just a 1×1 <img>)
#   * not a single-<img>-only body (explicit guard for tracking pixels
#     that happen to clear the size threshold via long URL strings)
#
# Verified against 7 real fixtures (3 ELMA365 + Gmail + Sentora×2 +
# ya_browser): correctly classifies all 13 inner frames present.
#
# These thresholds are intentionally conservative. Edge cases (e.g. an
# email-only iframe with literally 99 chars of body) round to non-substantial,
# but raising them risks triggering on tracking pixels with verbose URLs.
# When two heuristic choices tie, prefer rejecting (push user toward `main`
# or explicit `N`).

_FRAME_MIN_BYTES = 1024
# 30-char threshold tuned against real fixtures: includes brief signature-only
# replies ("С уважением, Демидова Татьяна" ≈ 47 chars) which are legitimate
# email content, while still rejecting truly empty iframes (Gmail bscframe at
# 0 chars; subframe[0] in email at 0 chars). Higher thresholds (100) miss
# real short emails on `tmp/email_list_client.webarchive`. Lower thresholds
# (10) risk including placeholder iframes whose body is just "Loading…".
_FRAME_MIN_TEXT  = 30


def _frame_plain_text(html: str) -> str:
    """Return body plain-text (whitespace-collapsed) of a small HTML doc.

    Used by both substantial-frame classification and `--list-frames`
    output. Cheap regex pass — frames are typically 1-50 KB so no parser
    needed.
    """
    body_m = re.search(
        r"<body[^>]*>(.*?)</body>",
        html, re.DOTALL | re.IGNORECASE,
    )
    inner = body_m.group(1) if body_m else html
    plain = re.sub(r"<[^>]+>", " ", inner)
    return re.sub(r"\s+", " ", plain).strip()


def _frame_is_only_img_body(html: str) -> bool:
    """True if <body> contains exactly one <img> tag and nothing else.

    Catches mail.ru-style "open pixel" tracking iframes that carry a
    lengthy JWT-like URL in the src= and easily exceed the byte threshold
    while being zero user content.
    """
    body_m = re.search(
        r"<body[^>]*>(.*?)</body>",
        html, re.DOTALL | re.IGNORECASE,
    )
    if not body_m:
        return False
    body_no_ws = re.sub(r"\s+", "", body_m.group(1))
    return bool(re.fullmatch(r"<img[^>]*/?>", body_no_ws, re.IGNORECASE))


def _is_substantial_frame(html_bytes: bytes, encoding: str = "utf-8") -> bool:
    """Structural classifier: is this inner-frame HTML likely user content?

    See module-level commentary for the four-rule heuristic. Returns
    False for empty/tiny/JS-driven/tracking-pixel frames, True for real
    document/email content. Vendor-agnostic: works on Gmail's Google
    chrome widgets (rejected: scripts > 0), ELMA365 email iframes
    (accepted), Yandex Cloud auth widgets (rejected: scripts > 0),
    Framer dev iframes (rejected: scripts > 0).
    """
    # Defensive guard — caller could plausibly pass None for an empty
    # / missing payload (plistlib won't, but external callers might).
    # `len(None)` would crash; better to return False uniformly.
    if not isinstance(html_bytes, (bytes, bytearray)):
        return False
    if len(html_bytes) < _FRAME_MIN_BYTES:
        return False
    try:
        html = html_bytes.decode(encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        html = html_bytes.decode("utf-8", errors="replace")
    if "<script" in html.lower():
        return False
    if len(_frame_plain_text(html)) < _FRAME_MIN_TEXT:
        return False
    if _frame_is_only_img_body(html):
        return False
    return True


# ───────────────────────── Frame inventory (--list-frames) ──────────────────

@dataclass(frozen=True)
class FrameInfo:
    """Format-agnostic descriptor of one frame in a webarchive/MHTML.

    `index` is 1-indexed for inner frames; the main resource is index 0.
    `kind` is "main" or "subframe" for human-friendly reporting.
    """
    index: int
    kind: str
    url: str
    bytes: int
    scripts: int
    text_len: int
    substantial: bool


def _frame_metrics(html_bytes: bytes, encoding: str) -> tuple[int, int]:
    """Return (script_count, plain_text_length) for one frame's HTML."""
    try:
        html = html_bytes.decode(encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        html = html_bytes.decode("utf-8", errors="replace")
    return html.lower().count("<script"), len(_frame_plain_text(html))


def list_archive_frames(src: Path) -> list[FrameInfo]:
    """Return the frame inventory for `--list-frames` output.

    Format-detected from extension: `.webarchive` → plist parse,
    `.mhtml`/`.mht` → MIME parse. Index 0 is the main resource; 1+ are
    inner frames in declaration order.
    """
    ext = src.suffix.lower()
    frames: list[FrameInfo] = []
    if ext == ".webarchive":
        with open(src, "rb") as f:
            plist = plistlib.load(f)
        main = plist.get("WebMainResource", {})
        main_data = main.get("WebResourceData", b"")
        main_enc  = main.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
        main_url  = main.get("WebResourceURL", "")
        if isinstance(main_data, bytes):
            sc, tl = _frame_metrics(main_data, main_enc)
            frames.append(FrameInfo(
                index=0, kind="main", url=main_url,
                bytes=len(main_data), scripts=sc, text_len=tl,
                substantial=_is_substantial_frame(main_data, main_enc),
            ))
        for i, fr in enumerate(plist.get("WebSubframeArchives", []) or [], 1):
            fmain = fr.get("WebMainResource", {})
            fdata = fmain.get("WebResourceData", b"")
            fenc  = fmain.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
            furl  = fmain.get("WebResourceURL", "")
            if not isinstance(fdata, bytes):
                continue
            sc, tl = _frame_metrics(fdata, fenc)
            frames.append(FrameInfo(
                index=i, kind="subframe", url=furl,
                bytes=len(fdata), scripts=sc, text_len=tl,
                substantial=_is_substantial_frame(fdata, fenc),
            ))
    elif ext in (".mhtml", ".mht"):
        raw = src.read_bytes()
        msg = email.message_from_bytes(raw, policy=email.policy.compat32)
        idx = -1
        for part in msg.walk():
            if part.is_multipart():
                continue
            ct  = part.get_content_type()
            if ct != "text/html":
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            loc     = part.get("Content-Location", "")
            idx += 1
            kind = "main" if idx == 0 else "subframe"
            sc, tl = _frame_metrics(payload, charset)
            substantial = (
                _is_substantial_frame(payload, charset) if idx > 0
                else False  # main is never reported as "substantial subframe"
            )
            frames.append(FrameInfo(
                index=idx, kind=kind, url=loc,
                bytes=len(payload), scripts=sc, text_len=tl,
                substantial=substantial,
            ))
    else:
        raise ValueError(f"unsupported archive format: {ext}")
    return frames


# ───────────────────────── Image dedup (sha1) ───────────────────────────────

# Max filename length (basename, including extension). Most filesystems
# cap at 255 bytes; we keep well under so multi-byte UTF-8 names + the
# write-collision suffix `123_` still fit. Triggered by tracking-pixel
# URLs whose last path segment is a 250+ char JWT (mail.ru, sendgrid).
_MAX_BASENAME = 120


def _safe_basename(fname: str, fallback_key: str) -> str:
    """Return a filesystem-safe basename ≤ _MAX_BASENAME bytes.

    For overlong basenames (tracking-pixel JWTs, signed S3 URLs), keep the
    file extension and replace the stem with a sha1-derived short token so
    the result is stable across runs (same input URL → same local name).
    """
    if len(fname.encode("utf-8")) <= _MAX_BASENAME:
        return fname
    stem, dot, ext = fname.rpartition(".")
    if dot and len(ext) <= 8 and "/" not in ext:
        token = hashlib.sha1(fallback_key.encode("utf-8")).hexdigest()[:16]
        return f"resource_{token}.{ext}"
    token = hashlib.sha1(fallback_key.encode("utf-8")).hexdigest()[:16]
    return f"resource_{token}"


class _DedupWriter:
    """Per-extract sha1-content-keyed image writer.

    Same image bytes (e.g. shared signature logo across multiple emails in
    `--archive-frame all` mode) → single physical file, multiple url_map
    entries point to it. Pure space optimization; correctness-neutral.
    Also caps overlong basenames (tracking-pixel URLs etc.) to keep the
    OS happy on macOS / Linux (255-byte filename limit).
    """

    def __init__(self, root: Path):
        self.root = root
        self._by_sha1: dict[str, str] = {}   # sha1 → relative path under root

    def write(self, subdir: str, fname: str, data: bytes) -> str:
        """Write `data` under root/[subdir/]fname, dedup by sha1.

        Returns the relative path (forward-slash) usable in HTML src=.
        """
        h = hashlib.sha1(data).hexdigest()
        if h in self._by_sha1:
            return self._by_sha1[h]
        # Cap filename length using the (already-computed) content sha1 as
        # the stable token — that way two writes of the same bytes produce
        # the same rewritten name, even though dedup means we only write
        # once. The fallback key is the original fname so different overlong
        # names map to different short names.
        fname = _safe_basename(fname, fallback_key=fname)
        target_dir = self.root / subdir if subdir else self.root
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / fname
        idx = 0
        while dest.exists():
            idx += 1
            dest = target_dir / f"{idx}_{fname}"
        dest.write_bytes(data)
        rel = (f"{subdir}/" if subdir else "") + dest.name
        self._by_sha1[h] = rel
        return rel


# ───────────────────────── Webarchive: extract one frame ────────────────────

def _decode_webarchive_frame(
    frame: dict,
    work_dir: Path,
    *,
    subdir: str = "",
    writer: _DedupWriter | None = None,
) -> tuple[str, str, dict[str, str], list[tuple[Path, bytes]]]:
    """Decode one webarchive resource (main or subframe) into work_dir.

    Returns (html_text, page_url, url_map, css_parts). The caller is
    responsible for invoking `_fixup_css_subresources` once per extract
    session (so CSS files written by per-frame writes still get the
    final URL rewrite).

    `subdir` namespaces the per-frame output (used by `all`-mode). `writer`
    may be passed in to share sha1-dedup state across frames; if None, a
    fresh writer rooted at work_dir is created.
    """
    main = frame.get("WebMainResource", {})
    html_data = main.get("WebResourceData", b"")
    enc       = main.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
    page_url  = main.get("WebResourceURL", "")
    if isinstance(html_data, bytes):
        try:
            html_text = html_data.decode(enc, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html_text = html_data.decode("utf-8", errors="replace")
    else:
        html_text = str(html_data)

    if writer is None:
        writer = _DedupWriter(work_dir)

    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []

    for sub in frame.get("WebSubresources", []) or []:
        url  = sub.get("WebResourceURL", "")
        mime = sub.get("WebResourceMIMEType", "")
        data = sub.get("WebResourceData", b"")
        if not url or not isinstance(data, bytes) or not data:
            continue
        if url.startswith("data:"):
            continue
        fname = Path(urllib.parse.unquote(url.split("?")[0])).name or "resource"
        rel = writer.write(subdir, fname, data)
        url_map[url] = rel
        if mime == "text/css":
            css_parts.append((writer.root / rel, data))

    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)
    return html_text, page_url, url_map, css_parts


# ───────────────────────── MHTML: extract one frame ─────────────────────────

def _decode_mhtml(
    src: Path,
    work_dir: Path,
    *,
    frame_index: int,
    subdir: str = "",
    writer: _DedupWriter | None = None,
) -> tuple[str, str, dict[str, str], list[tuple[Path, bytes]]]:
    """Extract one HTML part from an MHTML archive into work_dir.

    `frame_index` 0 = first text/html part (main); 1+ = subsequent
    text/html parts (frame iframes captured by Chrome's "Save as Single
    File"). All non-HTML parts in the message are written as resources
    regardless of which frame is selected (images/CSS/fonts are typically
    shared, e.g. site-level logos referenced by multiple frame contents).
    """
    raw = src.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    if writer is None:
        writer = _DedupWriter(work_dir)

    html_parts: list[tuple[bytes, str, str]] = []   # (bytes, charset, content-location)
    url_map: dict[str, str] = {}
    css_parts: list[tuple[Path, bytes]] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        ct      = part.get_content_type()
        loc     = part.get("Content-Location", "")
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if ct == "text/html":
            charset = part.get_content_charset() or "utf-8"
            html_parts.append((payload, charset, loc))
        elif loc:
            fname = Path(urllib.parse.unquote(loc.split("?")[0])).name or "resource"
            rel = writer.write(subdir, fname, payload)
            url_map[loc] = rel
            if ct == "text/css":
                css_parts.append((writer.root / rel, payload))

    if not html_parts:
        raise ValueError(f"no text/html part found in {src.name}")
    if frame_index >= len(html_parts):
        raise IndexError(
            f"MHTML frame index {frame_index} out of range "
            f"(archive has {len(html_parts)} text/html parts)"
        )

    html_bytes, charset, page_url = html_parts[frame_index]
    try:
        html_text = html_bytes.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html_text = html_bytes.decode("utf-8", errors="replace")
    html_text = _make_absolute_urls(html_text, page_url)
    html_text = _rewrite_urls(html_text, url_map)
    return html_text, page_url, url_map, css_parts


# ───────────────────────── Public entry: extract_archive ────────────────────

# Wrapper template for `--archive-frame all` concat output. Each substantial
# frame's body is wrapped in a section preceded by a flat `<h2>Frame N</h2>`
# separator. No metadata pulling in v1 (subject/from/date heuristic deferred
# to pdf-8a) — headers are minimal but vendor-agnostic.
_ALL_MODE_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Archive frames</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Helvetica Neue", sans-serif;
          font-size: 13px; line-height: 1.5; margin: 0; padding: 12px; }}
  hr.archive-frame-sep {{ border: 0; border-top: 1px solid #cccccc;
                          margin: 24px 0 8px 0; }}
  h2.archive-frame-title {{ font-size: 18px; margin: 0 0 12px 0;
                            color: #444444; }}
  div.archive-frame-body {{ margin-bottom: 16px; }}
</style></head>
<body>
{sections}
</body>
</html>
"""

_FRAME_SECTION_TEMPLATE = """<hr class="archive-frame-sep">
<h2 class="archive-frame-title">Frame {n}</h2>
<div class="archive-frame-body">
{body}
</div>
"""


def _extract_body_inner(html: str) -> str:
    """Return the inner HTML of <body> for `all`-mode concat.

    Falls back to the entire string if there's no <body> tag (some email
    iframes are body-less HTML fragments).
    """
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else html


class NoSubstantialFrames(ValueError):
    """Raised when `--archive-frame all` runs against an archive with 0
    substantial inner frames. Fail-loud per pdf-8 honest scope: silently
    falling back to main would surprise the user (they explicitly asked
    for all-frames concat). Use `--archive-frame main` or `auto` instead.
    """


_AUTO_SUBFRAME_DOMINANCE_RATIO = 0.10


def _resolve_auto_mode(frames: list[FrameInfo]) -> str:
    """Auto-mode rule (vendor-agnostic, structural):

      * 0 substantial subframes  → main
      * 1 substantial subframe   → that subframe ONLY if its text is
                                   ≥ 10% of main's text length;
                                   otherwise main (the substantial
                                   subframe is likely a system
                                   error/notification overlay, not
                                   the user's intended content)
      * ≥ 2 substantial subframes → all

    The 10% dominance ratio handles the HubSpot for WordPress case
    (VDD-adversarial finding): a tiny "navigation-modal" iframe (180
    chars) qualifies as substantial but represents an out-of-band
    error page, while main HTML (5960 chars) carries the actual app
    description. Without the ratio guard, auto-mode silently picks
    the error overlay. Tuned conservatively: 10% means a real email
    body in subframe (typical 1000-7000 chars vs SPA-stub main of
    100-3000) easily clears the bar, but 200-char system overlays
    do not.
    """
    main = next((f for f in frames if f.kind == "main"), None)
    substantial = [f for f in frames if f.kind == "subframe" and f.substantial]
    if not substantial:
        return "main"
    if len(substantial) == 1:
        # Single substantial subframe. Compare against main text-length.
        # If subframe is small fraction of main, main is likely the real
        # content and the substantial frame is a system overlay.
        if main is not None and main.text_len > 0:
            if substantial[0].text_len < main.text_len * _AUTO_SUBFRAME_DOMINANCE_RATIO:
                return "main"
        return str(substantial[0].index)
    return "all"


def extract_archive(
    src: Path,
    work_dir: Path,
    *,
    frame_spec: str = "main",
) -> tuple[str, str]:
    """Universal archive extractor with frame selection.

    `frame_spec`:
      * "main"  — main resource only (current default behaviour, explicit).
      * "N"     — 1-indexed inner frame N (1 = first subframe).
      * "all"   — concat all substantial inner frames in declaration order.
      * "auto"  — 0 substantial → main; 1 → that frame; 2+ → all.

    Returns (html_text, base_url) ready for `render.convert()`. Same
    contract as the legacy single-frame functions.
    """
    ext = src.suffix.lower()
    if frame_spec == "auto":
        frame_spec = _resolve_auto_mode(list_archive_frames(src))

    if ext == ".webarchive":
        with open(src, "rb") as f:
            plist = plistlib.load(f)
        subframes = plist.get("WebSubframeArchives", []) or []

        if frame_spec == "main":
            html_text, page_url, url_map, css_parts = _decode_webarchive_frame(
                plist, work_dir,
            )
            _fixup_css_subresources(css_parts, page_url, url_map)
            return html_text, str(work_dir)

        if frame_spec == "all":
            substantial: list[tuple[int, dict]] = []
            for i, fr in enumerate(subframes, 1):
                fmain = fr.get("WebMainResource", {})
                fdata = fmain.get("WebResourceData", b"")
                fenc  = fmain.get("WebResourceTextEncodingName", "utf-8") or "utf-8"
                if isinstance(fdata, bytes) and _is_substantial_frame(fdata, fenc):
                    substantial.append((i, fr))
            if not substantial:
                raise NoSubstantialFrames(
                    f"webarchive has 0 substantial inner frames; nothing to "
                    f"concat. Use --archive-frame main or auto. "
                    f"(See --list-frames for the full inventory.)"
                )
            writer = _DedupWriter(work_dir)
            sections: list[str] = []
            page_urls: list[str] = []
            url_maps: list[dict[str, str]] = []
            css_parts_all: list[tuple[Path, bytes]] = []
            for i, fr in substantial:
                subdir = f"frame_{i}"
                ftext, furl, fmap, fcss = _decode_webarchive_frame(
                    fr, work_dir, subdir=subdir, writer=writer,
                )
                sections.append(_FRAME_SECTION_TEMPLATE.format(
                    n=i, body=_extract_body_inner(ftext),
                ))
                page_urls.append(furl)
                url_maps.append(fmap)
                css_parts_all.extend(fcss)
            html_text = _ALL_MODE_TEMPLATE.format(sections="\n".join(sections))
            # CSS subresources may carry per-frame absolute URLs back to
            # their origin; rewrite each within its own page_url namespace
            # so font-faces / background-images resolve.
            for parts, purl, umap in zip(
                _group_css_by_frame(css_parts_all, url_maps),
                page_urls, url_maps, strict=True,
            ):
                _fixup_css_subresources(parts, purl, umap)
            return html_text, str(work_dir)

        # Numeric frame_spec ("1", "2", …)
        try:
            n = int(frame_spec)
        except ValueError as exc:
            raise ValueError(
                f"invalid --archive-frame value {frame_spec!r}; "
                f"expected main / N (1-indexed) / all / auto"
            ) from exc
        if n < 1 or n > len(subframes):
            raise IndexError(
                f"webarchive has {len(subframes)} subframes; "
                f"--archive-frame {n} out of range (1..{len(subframes)})"
            )
        html_text, page_url, url_map, css_parts = _decode_webarchive_frame(
            subframes[n - 1], work_dir,
        )
        _fixup_css_subresources(css_parts, page_url, url_map)
        return html_text, str(work_dir)

    elif ext in (".mhtml", ".mht"):
        # Inventory once to know how many text/html parts exist.
        all_frames = list_archive_frames(src)
        n_subframes = sum(1 for f in all_frames if f.kind == "subframe")

        if frame_spec == "main":
            html_text, page_url, url_map, css_parts = _decode_mhtml(
                src, work_dir, frame_index=0,
            )
            _fixup_css_subresources(css_parts, page_url, url_map)
            return html_text, str(work_dir)

        if frame_spec == "all":
            substantial_indices: list[int] = []
            for f in all_frames:
                if f.kind == "subframe" and f.substantial:
                    substantial_indices.append(f.index)
            if not substantial_indices:
                raise NoSubstantialFrames(
                    f"MHTML has 0 substantial inner frames; nothing to "
                    f"concat. Use --archive-frame main or auto."
                )
            writer = _DedupWriter(work_dir)
            sections: list[str] = []
            page_urls: list[str] = []
            url_maps: list[dict[str, str]] = []
            css_parts_all: list[tuple[Path, bytes]] = []
            for i in substantial_indices:
                subdir = f"frame_{i}"
                ftext, furl, fmap, fcss = _decode_mhtml(
                    src, work_dir, frame_index=i,
                    subdir=subdir, writer=writer,
                )
                sections.append(_FRAME_SECTION_TEMPLATE.format(
                    n=i, body=_extract_body_inner(ftext),
                ))
                page_urls.append(furl)
                url_maps.append(fmap)
                css_parts_all.extend(fcss)
            html_text = _ALL_MODE_TEMPLATE.format(sections="\n".join(sections))
            for parts, purl, umap in zip(
                _group_css_by_frame(css_parts_all, url_maps),
                page_urls, url_maps, strict=True,
            ):
                _fixup_css_subresources(parts, purl, umap)
            return html_text, str(work_dir)

        try:
            n = int(frame_spec)
        except ValueError as exc:
            raise ValueError(
                f"invalid --archive-frame value {frame_spec!r}; "
                f"expected main / N / all / auto"
            ) from exc
        if n < 1 or n > n_subframes:
            raise IndexError(
                f"MHTML has {n_subframes} subframes; "
                f"--archive-frame {n} out of range (1..{n_subframes})"
            )
        html_text, page_url, url_map, css_parts = _decode_mhtml(
            src, work_dir, frame_index=n,
        )
        _fixup_css_subresources(css_parts, page_url, url_map)
        return html_text, str(work_dir)

    else:
        raise ValueError(f"unsupported archive format: {ext}")


def _group_css_by_frame(
    css_parts: list[tuple[Path, bytes]],
    url_maps: list[dict[str, str]],
) -> list[list[tuple[Path, bytes]]]:
    """Partition flat css_parts list back into per-frame groups.

    Naive: matches each css path to the url_map that contains its name.
    For dedup-shared CSS files (rare — most CSS is per-page), the first
    matching frame "owns" the CSS and rewrites it with that frame's
    page_url. Functionally OK because @font-face URLs are origin-relative
    and CSS background-images are typically self-referential.
    """
    groups: list[list[tuple[Path, bytes]]] = [[] for _ in url_maps]
    for path, data in css_parts:
        for i, umap in enumerate(url_maps):
            if str(path).endswith(tuple(umap.values())):
                groups[i].append((path, data))
                break
        else:
            groups[0].append((path, data))
    return groups


# ───────────────────────── Legacy entry points (back-compat) ────────────────

def extract_mhtml(src: Path, work_dir: Path) -> tuple[str, str]:
    """Legacy single-frame MHTML extractor — extracts main HTML part only.

    Equivalent to `extract_archive(src, work_dir, frame_spec="main")` for
    .mhtml. Kept for callers (in-tree and external) that haven't migrated
    to the unified entry point.
    """
    return extract_archive(src, work_dir, frame_spec="main")


def extract_webarchive(src: Path, work_dir: Path) -> tuple[str, str]:
    """Legacy single-frame webarchive extractor — extracts main resource only.

    Equivalent to `extract_archive(src, work_dir, frame_spec="main")` for
    .webarchive. Kept for back-compat with callers that already imported
    this name.
    """
    return extract_archive(src, work_dir, frame_spec="main")
