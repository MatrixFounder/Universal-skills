#!/usr/bin/env python3
"""Render Markdown to a well-typeset PDF via weasyprint.

Pipeline:
    Markdown --(mmdc, optional)--> SVG diagrams
    Markdown --(markdown2)--> HTML --(weasyprint)--> PDF

Supports GFM tables, fenced code blocks with basic styling, and
custom CSS via `--css`. A sensible default stylesheet handles
page size, margins, typography, code blocks, and tables. Fenced
```mermaid blocks are pre-rendered to SVG via mmdc when available;
without mmdc they degrade to a code block (no error).

Usage:
    python3 md2pdf.py INPUT.md OUTPUT.pdf
        [--css EXTRA.css] [--page-size letter|a4|legal]
        [--base-url DIR] [--no-mermaid] [--strict-mermaid]

`--base-url DIR` controls how relative image paths resolve. Defaults
to the directory containing the input Markdown file.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown2  # type: ignore
from weasyprint import CSS, HTML  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_BIN = SCRIPT_DIR / "node_modules" / ".bin"
MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
MMDC_TIMEOUT = 300  # seconds per diagram

# Default mermaid-config shipped with the skill — biased toward office
# scenarios where Cyrillic / CJK labels are common. mmdc's built-in
# default uses Trebuchet MS, which has spotty non-Latin coverage on
# Linux servers; the bundled config switches to Arial Unicode MS with
# fallbacks. Users override with --mermaid-config.
DEFAULT_MERMAID_CONFIG = SCRIPT_DIR / "mermaid-config.json"


def _mmdc_path() -> Path | None:
    """Resolve mmdc, preferring scripts/node_modules/.bin/mmdc over PATH.
    Returns None when neither is available — caller decides whether to
    warn or fail."""
    local = LOCAL_BIN / "mmdc"
    if local.exists() and os.access(local, os.X_OK):
        return local
    found = shutil.which("mmdc")
    return Path(found) if found else None


def _mermaid_cache_key(mermaid_config: Path | None) -> str:
    """Per-config fingerprint mixed into each diagram's SHA1 — switching
    `--mermaid-config` (or editing it) must invalidate all cached PNGs,
    otherwise the next run silently keeps the previous theme/font."""
    if mermaid_config and mermaid_config.exists():
        config_bytes = mermaid_config.read_bytes()
    else:
        config_bytes = b""
    # Also include the renderer flags we pass to mmdc, so a future
    # `--scale 3` would invalidate cache too.
    flags = b"|-b|white|--scale|2"
    return hashlib.sha1(config_bytes + flags).hexdigest()[:8]


def preprocess_mermaid(
    md_text: str,
    assets_dir: Path,
    *,
    strict: bool = False,
    mermaid_config: Path | None = None,
) -> str:
    """Replace fenced ```mermaid blocks with `![](...svg)` references.
    Renders each unique block once (SHA1-keyed cache) so repeated runs
    on the same input are cheap. Falls through unchanged when mmdc is
    not on PATH and `strict=False`.

    `mermaid_config` is forwarded to `mmdc -c` so callers can pick a
    theme / font / layout style without editing the script. The default
    points at the bundled office-friendly config (Cyrillic-capable
    fonts); pass an explicit path to override or `None` to use mmdc's
    built-in defaults."""
    if not MERMAID_BLOCK_RE.search(md_text):
        return md_text

    mmdc = _mmdc_path()
    if mmdc is None:
        msg = ("mermaid blocks found but mmdc is not installed. "
               "Run scripts/install.sh, or install with: npm i -g @mermaid-js/mermaid-cli")
        if strict:
            raise RuntimeError(msg)
        print(f"[md2pdf] WARN: {msg} — diagrams will render as code.", file=sys.stderr)
        return md_text

    if mermaid_config and not mermaid_config.exists():
        msg = f"--mermaid-config {mermaid_config} does not exist"
        if strict:
            raise RuntimeError(msg)
        print(f"[md2pdf] WARN: {msg} — falling back to mmdc defaults.", file=sys.stderr)
        mermaid_config = None

    assets_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = f"{LOCAL_BIN}{os.pathsep}{env.get('PATH', '')}"
    config_fp = _mermaid_cache_key(mermaid_config)

    rendered = 0
    failures = 0

    def replace(match: re.Match) -> str:
        nonlocal rendered, failures
        body = match.group(1)
        # Cache key mixes diagram body AND config fingerprint so a new
        # config (or a tweak to the existing file) invalidates the PNG.
        digest = hashlib.sha1(body.encode("utf-8") + b"|" + config_fp.encode()).hexdigest()[:10]
        mmd_path = assets_dir / f"diagram-{digest}.mmd"
        # PNG (not SVG): weasyprint renders mmdc's SVG without honouring
        # the diagram's font chain (text falls back to a glyphless face on
        # many systems → "coloured rectangles" with no labels). PNG is
        # rasterised inside Chromium-via-mmdc with full font coverage,
        # and its intrinsic pixel size lets weasyprint scale-to-fit
        # cleanly via `max-width: 100%`. Scale 2 keeps it crisp on print.
        png_path = assets_dir / f"diagram-{digest}.png"
        if not png_path.exists():
            mmd_path.write_text(body, encoding="utf-8")
            cmd = [
                str(mmdc), "-i", str(mmd_path), "-o", str(png_path),
                "-b", "white", "--scale", "2",
            ]
            if mermaid_config:
                cmd.extend(["-c", str(mermaid_config)])
            try:
                subprocess.run(
                    cmd, check=True, capture_output=True, env=env,
                    timeout=MMDC_TIMEOUT, stdin=subprocess.DEVNULL,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                failures += 1
                stderr = (exc.stderr.decode("utf-8", errors="replace")
                          if isinstance(exc, subprocess.CalledProcessError) and exc.stderr
                          else "(timeout)")
                if strict:
                    raise RuntimeError(f"mmdc failed on diagram {digest}: {stderr}") from exc
                print(f"[md2pdf] WARN: mmdc failed on diagram {digest}; keeping as code. {stderr}",
                      file=sys.stderr)
                return match.group(0)
        rendered += 1
        rel = png_path.relative_to(assets_dir.parent).as_posix()
        return f'<div class="mermaid-diagram"><img src="{rel}" alt="mermaid diagram"></div>'

    out = MERMAID_BLOCK_RE.sub(replace, md_text)
    if rendered:
        note = f" ({failures} failed)" if failures else ""
        print(f"[md2pdf] Rendered {rendered} mermaid diagram(s) to {assets_dir}{note}.")
    return out


DEFAULT_CSS = """
@page {
    size: {page_size};
    margin: 18mm 20mm 22mm 20mm;
    @bottom-right { content: counter(page) " / " counter(pages); font-size: 9pt; color: #6b7280; }
}

html {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.45;
    color: #1f2937;
}

h1, h2, h3, h4 { color: #111827; line-height: 1.25; margin: 1.2em 0 0.4em; }
h1 { font-size: 22pt; border-bottom: 2px solid #1f2937; padding-bottom: 0.2em; }
h2 { font-size: 16pt; }
h3 { font-size: 13pt; }

p { margin: 0.5em 0; }

ul, ol { margin: 0.5em 0 0.5em 1.3em; padding: 0; }
li { margin: 0.15em 0; }

blockquote {
    border-left: 3px solid #2563eb;
    padding: 0.2em 0.9em;
    margin: 0.7em 0;
    color: #374151;
    background: #f3f4f6;
}

code {
    font-family: "Menlo", "Consolas", monospace;
    font-size: 9.5pt;
    background: #f3f4f6;
    padding: 0 0.25em;
    border-radius: 3px;
}

pre {
    background: #f3f4f6;
    padding: 0.6em 0.9em;
    border-radius: 4px;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code { background: transparent; padding: 0; font-size: 9pt; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.6em 0;
    font-size: 10pt;
    page-break-inside: avoid;
}
th, td { border: 1px solid #e5e7eb; padding: 0.35em 0.55em; text-align: left; vertical-align: top; }
th { background: #dbeafe; color: #111827; }

img { max-width: 100%; height: auto; }

/* Mermaid diagram block: keep on one page, centred, with a little
   breathing room. weasyprint will scale the PNG down to fit BOTH
   page width (max-width: 100%) AND a conservative max-height that
   leaves room for headings/content above. Tall diagrams (mindmap,
   long flowchart) thus shrink by their longer side instead of
   overflowing to the next page. 7in fits Letter (9.4in content
   area) and A4 (10.1in) with margin to spare. */
.mermaid-diagram {
    text-align: center;
    margin: 1em 0;
    page-break-inside: avoid;
}
.mermaid-diagram img {
    max-width: 100%;
    max-height: 7in;
    width: auto;
    height: auto;
}

a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
"""

PAGE_SIZES = {"letter": "letter", "a4": "A4", "legal": "legal"}


def convert(
    input_path: Path,
    output_path: Path,
    *,
    page_size: str,
    extra_css_path: Path | None,
    base_url: str | None,
    use_mermaid: bool = True,
    strict_mermaid: bool = False,
    mermaid_config: Path | None = None,
) -> None:
    md_text = input_path.read_text(encoding="utf-8")
    if use_mermaid:
        # Diagrams live next to the INPUT in <output_stem>_assets/ so the
        # relative path emitted by preprocess_mermaid resolves against the
        # default base_url (input_path.parent). User-overridden --base-url
        # is the caller's responsibility — they can disable mermaid then.
        base_dir = Path(base_url) if base_url else input_path.parent
        assets_dir = base_dir / f"{output_path.stem}_assets"
        # Default to the bundled office-friendly config (Cyrillic-capable
        # fonts) when the user didn't pick one explicitly. None means
        # "let mmdc use its built-in defaults".
        if mermaid_config is None and DEFAULT_MERMAID_CONFIG.exists():
            mermaid_config = DEFAULT_MERMAID_CONFIG
        md_text = preprocess_mermaid(
            md_text, assets_dir,
            strict=strict_mermaid,
            mermaid_config=mermaid_config,
        )
    html_body = markdown2.markdown(
        md_text,
        extras=["fenced-code-blocks", "tables", "strike", "cuddled-lists", "code-friendly"],
    )

    html = (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8"><title>doc</title></head><body>\n'
        + html_body
        + "\n</body></html>"
    )

    default = DEFAULT_CSS.replace("{page_size}", PAGE_SIZES.get(page_size, "letter"))
    stylesheets = [CSS(string=default)]
    if extra_css_path is not None:
        stylesheets.append(CSS(filename=str(extra_css_path)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base = base_url or str(input_path.parent.resolve())
    HTML(string=html, base_url=base).write_pdf(str(output_path), stylesheets=stylesheets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .md file")
    parser.add_argument("output", type=Path, help="Destination .pdf file")
    parser.add_argument("--page-size", choices=list(PAGE_SIZES.keys()), default="letter")
    parser.add_argument("--css", type=Path, default=None, help="Extra CSS file appended after defaults")
    parser.add_argument("--base-url", default=None, help="Base URL for resolving relative images (default: input's dir)")
    parser.add_argument("--no-mermaid", action="store_true",
                        help="Skip mermaid preprocessing (diagrams stay as code blocks).")
    parser.add_argument("--strict-mermaid", action="store_true",
                        help="Fail (exit 4) if any mermaid block can't be rendered.")
    parser.add_argument("--mermaid-config", type=Path, default=None,
                        help="JSON config passed to mmdc -c (theme, fontFamily, etc.). "
                             "Default: scripts/mermaid-config.json (office-friendly, Cyrillic-capable).")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    try:
        convert(
            args.input,
            args.output,
            page_size=args.page_size,
            extra_css_path=args.css,
            base_url=args.base_url,
            use_mermaid=not args.no_mermaid,
            strict_mermaid=args.strict_mermaid,
            mermaid_config=args.mermaid_config,
        )
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
