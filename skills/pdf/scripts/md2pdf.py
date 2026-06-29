#!/usr/bin/env python3
"""Render Markdown to a well-typeset PDF via weasyprint.

Pipeline:
    Markdown --(katex, optional)--> MathML  ($…$ / $$…$$)
    Markdown --(mmdc, optional)--> PNG diagrams
    Markdown --(markdown2)--> HTML --(weasyprint)--> PDF

Supports GFM tables, fenced code blocks with basic styling, and
custom CSS via `--css`. A sensible default stylesheet handles
page size, margins, typography, code blocks, and tables. Fenced
```mermaid blocks are pre-rendered to PNG via mmdc when available;
without mmdc they degrade to a code block (no error). Inline `$…$`
and display `$$…$$` math are pre-rendered to MathML via the bundled
KaTeX (weasyprint typesets MathML natively — it runs no JS, so
client-side KaTeX/MathJax is impossible); without node/KaTeX they
degrade to literal text. Currency ("$5") and `$` inside code are
left untouched.

Usage:
    python3 md2pdf.py INPUT.md OUTPUT.pdf
        [--css EXTRA.css] [--page-size letter|a4|legal]
        [--base-url DIR] [--no-mermaid] [--strict-mermaid]
        [--no-math] [--strict-math]

`--base-url DIR` controls how relative image paths resolve. Defaults
to the directory containing the input Markdown file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown2  # type: ignore
from weasyprint import CSS, HTML  # type: ignore

from _errors import add_json_errors_argument, report_error

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


KATEX_RENDER_JS = SCRIPT_DIR / "katex_render.js"
KATEX_TIMEOUT = 60  # seconds for the whole-document batch render

# Math delimiters. Display `$$…$$` is unambiguous. Inline `$…$` uses the pandoc heuristic
# to avoid eating currency ("$5 and $10"): the opening `$` is not followed by whitespace,
# the closing `$` is not preceded by whitespace, and an escaped `\$` is never a delimiter.
_MATH_DISPLAY_RE = re.compile(r"(?<!\\)\$\$(?!\$)(.+?)(?<!\\)\$\$", re.DOTALL)
_MATH_INLINE_RE = re.compile(r"(?<![\\$])\$(?!\s)((?:\\.|[^$\\])+?)(?<![\s\\])\$(?!\$)")
# Fenced blocks + inline code spans are passed through verbatim (a `$x` in a shell snippet
# is not math).
_CODE_SPLIT_RE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)")
# Above this many `$` chars, treat the doc as currency/noise and skip math preprocessing
# (guards the O(n²) inline scan on pathological `$`-dense input, before any Node timeout).
_MATH_DOLLAR_CAP = 10000


def _node_path() -> Path | None:
    """Resolve the `node` binary (PATH). Returns None when unavailable."""
    found = shutil.which("node")
    return Path(found) if found else None


def preprocess_math(md_text: str, *, strict: bool = False) -> str:
    """Render inline `$…$` / display `$$…$$` TeX to MathML (via the bundled KaTeX), which
    weasyprint typesets natively. One Node batch for the whole doc. Code spans/fences are
    skipped. Degrades to the literal `$…$` (with a warning) when node/KaTeX is missing or a
    formula fails to parse — never aborts the render unless `strict`."""
    if "$" not in md_text:
        return md_text
    # Pathological-input guard: the inline scan is O(n²) on `$`-dense input (each `$` is a
    # candidate opener that may scan far before failing), and this runs BEFORE the Node
    # timeout protects anything. A doc with thousands of `$` is currency/noise, not math →
    # skip math preprocessing (degraded to literal, never a multi-second Python-side hang).
    if md_text.count("$") > _MATH_DOLLAR_CAP:
        if strict:
            raise RuntimeError(f"too many '$' ({md_text.count('$')}) — refusing math preprocessing")
        print(f"[md2pdf] WARN: {md_text.count('$')} '$' chars exceed the math cap "
              f"({_MATH_DOLLAR_CAP}) — skipping math (kept as literal text).", file=sys.stderr)
        return md_text

    # Collect formulas from non-code segments only.
    segments = _CODE_SPLIT_RE.split(md_text)
    formulas: list[dict] = []          # [{tex, display}]
    index: dict[tuple[str, bool], int] = {}

    def _collect(tex: str, display: bool) -> None:
        key = (tex, display)
        if key not in index:
            index[key] = len(formulas)
            formulas.append({"tex": tex, "display": display})

    for s_i in range(0, len(segments), 2):  # even = prose; odd = code
        seg = segments[s_i]
        if "$$" in seg:
            for m in _MATH_DISPLAY_RE.finditer(seg):
                _collect(m.group(1).strip(), True)
            # Strip display spans before scanning inline so `$$…$$` isn't seen as two `$…$`.
            # (Only allocate the stripped copy when display math is actually present.)
            inline_basis = _MATH_DISPLAY_RE.sub("", seg)
        else:
            inline_basis = seg
        for m in _MATH_INLINE_RE.finditer(inline_basis):
            _collect(m.group(1).strip(), False)

    if not formulas:
        return md_text

    node = _node_path()
    if node is None or not KATEX_RENDER_JS.exists():
        msg = ("math ($…$) found but the KaTeX renderer is unavailable "
               "(need node + scripts/node_modules/katex — run scripts/install.sh)")
        if strict:
            raise RuntimeError(msg)
        print(f"[md2pdf] WARN: {msg} — formulas kept as literal text.", file=sys.stderr)
        return md_text

    try:
        proc = subprocess.run(
            [str(node), str(KATEX_RENDER_JS)],
            input=json.dumps(formulas), capture_output=True, text=True,
            timeout=KATEX_TIMEOUT, cwd=str(SCRIPT_DIR),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"katex_render exit {proc.returncode}")
        results = json.loads(proc.stdout)
    except (subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        if strict:
            raise RuntimeError(f"KaTeX render failed: {exc}") from exc
        print(f"[md2pdf] WARN: KaTeX render failed ({exc}) — formulas kept as literal text.",
              file=sys.stderr)
        return md_text

    rendered = 0
    failures = 0

    failed_display: list[str] = []  # un-rendered $$…$$ stashed behind a $-free sentinel

    def _mathml(tex: str, display: bool) -> str | None:
        nonlocal failures
        # Defensive .get: the inline pass can encounter a `$…$` inside an un-rendered
        # display block that was never collected (collection scanned display-stripped
        # text). A missing key is a render-failure, not a crash.
        idx = index.get((tex, display))
        if idx is not None and results[idx].get("mathml"):
            return results[idx]["mathml"]
        failures += 1
        return None

    def _sub_display(m: re.Match) -> str:
        nonlocal rendered
        ml = _mathml(m.group(1).strip(), True)
        if ml is None:
            # Stash the un-rendered display verbatim behind a NUL-delimited, $-free
            # sentinel so the following inline pass cannot match a `$` inside it
            # (prevents both the KeyError crash and inline-mangling the literal).
            failed_display.append(m.group(0))
            return f"\x00MD{len(failed_display) - 1}\x00"
        rendered += 1
        return f'<div class="math-display">{ml}</div>'

    def _sub_inline(m: re.Match) -> str:
        nonlocal rendered
        ml = _mathml(m.group(1).strip(), False)
        if ml is None:
            return m.group(0)
        rendered += 1
        return f'<span class="math-inline">{ml}</span>'

    _sentinel = re.compile(r"\x00MD(\d+)\x00")
    for s_i in range(0, len(segments), 2):
        seg = _MATH_DISPLAY_RE.sub(_sub_display, segments[s_i])
        seg = _MATH_INLINE_RE.sub(_sub_inline, seg)
        segments[s_i] = _sentinel.sub(lambda mm: failed_display[int(mm.group(1))], seg)

    if rendered:
        note = f" ({failures} failed → kept as text)" if failures else ""
        print(f"[md2pdf] Rendered {rendered} math formula(s) via KaTeX{note}.")
    return "".join(segments)


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

/* Math (KaTeX → MathML, typeset by weasyprint). Inline flows with the text; display
   math is centred on its own line and kept off page breaks. */
.math-inline { white-space: nowrap; }
.math-display {
    text-align: center;
    margin: 0.8em 0;
    page-break-inside: avoid;
}
math { font-size: 1em; }
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
    use_math: bool = True,
    strict_math: bool = False,
) -> None:
    md_text = input_path.read_text(encoding="utf-8")
    if use_math:
        # TeX → MathML before markdown2 so the inline/block HTML passes through (same model
        # as mermaid). weasyprint typesets the MathML; no JS runs at render time.
        md_text = preprocess_math(md_text, strict=strict_math)
    if use_mermaid:
        # Diagrams live next to the INPUT in <output_stem>_assets/ so the
        # relative path emitted by preprocess_mermaid resolves against the
        # default base_url (input_path.parent). User-overridden --base-url
        # is the caller's responsibility — they can disable mermaid then.
        base_dir = Path(base_url) if base_url else input_path.parent
        assets_dir = base_dir / f"{output_path.stem}_assets"
        # Default to the bundled office-friendly config (Cyrillic-capable
        # fonts) when caller passed neither `--mermaid-config` nor
        # `--no-mermaid-config`. The literal sentinel False (set when
        # --no-mermaid-config is on) means "skip the default and let
        # mmdc use its built-in config".
        if mermaid_config is False:
            mermaid_config = None
        elif mermaid_config is None and DEFAULT_MERMAID_CONFIG.exists():
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
    parser.add_argument("--no-math", action="store_true",
                        help="Skip math preprocessing ($…$/$$…$$ stay as literal text).")
    parser.add_argument("--strict-math", action="store_true",
                        help="Fail if KaTeX is unavailable or any formula can't be rendered.")
    cfg_group = parser.add_mutually_exclusive_group()
    cfg_group.add_argument("--mermaid-config", type=Path, default=None,
                           help="JSON config passed to mmdc -c (theme, fontFamily, etc.). "
                                "Default: scripts/mermaid-config.json (office-friendly, Cyrillic-capable).")
    cfg_group.add_argument("--no-mermaid-config", dest="no_mermaid_config",
                           action="store_true",
                           help="Render with mmdc's built-in defaults (skip the bundled config).")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    try:
        convert(
            args.input,
            args.output,
            page_size=args.page_size,
            extra_css_path=args.css,
            base_url=args.base_url,
            use_mermaid=not args.no_mermaid,
            strict_mermaid=args.strict_mermaid,
            # `False` means user passed --no-mermaid-config; convert()
            # interprets that as "skip the bundled default and let
            # mmdc use its built-in config".
            mermaid_config=False if args.no_mermaid_config else args.mermaid_config,
            use_math=not args.no_math,
            strict_math=args.strict_math,
        )
    except Exception as exc:
        return report_error(
            f"Conversion failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
