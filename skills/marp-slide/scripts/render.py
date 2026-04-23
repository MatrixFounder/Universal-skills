#!/usr/bin/env python3
"""marp-slide renderer with mermaid preprocessing (local-venv edition).

Standalone. Python 3.10+. Stdlib only. No internal dependencies on other skills.

External tools (installed locally under ``scripts/node_modules/`` by ``install.sh``):
  - marp (https://github.com/marp-team/marp-cli) — REQUIRED
  - mmdc (https://github.com/mermaid-js/mermaid-cli) — RECOMMENDED;
      without it mermaid blocks degrade to code.

Usage:
  render.py INPUT.md [--format pptx|pdf|html|png|jpeg] [--output OUTPUT]
                     [--no-mermaid] [--strict-mermaid] [--theme NAME]

Examples:
  render.py deck.md                               # -> deck.pptx, mermaid pre-rendered
  render.py deck.md --format pdf                  # -> deck.pdf
  render.py deck.md --output /tmp/out.pptx        # explicit output path
  render.py deck.md --no-mermaid                  # skip preprocessing (diagrams stay as code)
  render.py deck.md --theme business              # override frontmatter theme

Exit codes:
  0 — success
  1 — bad args or input
  2 — marp CLI not installed (fatal)
  3 — marp rendering failed
  4 — mermaid preprocessing failed AND --strict-mermaid was set
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

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_BIN = SCRIPT_DIR / 'node_modules' / '.bin'

MERMAID_BLOCK_RE = re.compile(r'```mermaid\s*\n(.*?)\n```', re.DOTALL)
SUPPORTED_FORMATS = ('pptx', 'pdf', 'html', 'png', 'jpeg')


def die(code: int, msg: str) -> None:
    print(f'[render.py] ERROR: {msg}', file=sys.stderr)
    sys.exit(code)


def _tool_path(name: str) -> Path | None:
    """Resolve a CLI tool, preferring local node_modules/.bin over system PATH."""
    local = LOCAL_BIN / name
    if local.exists():
        return local
    found = shutil.which(name)
    return Path(found) if found else None


def check_tool(name: str) -> bool:
    return _tool_path(name) is not None


def _subprocess_env() -> dict[str, str]:
    """Return an env with scripts/node_modules/.bin prepended to PATH,
    so any child process resolves our locally-installed binaries first."""
    env = os.environ.copy()
    env['PATH'] = f'{LOCAL_BIN}{os.pathsep}' + env.get('PATH', '')
    return env


def preprocess_mermaid(md_text: str, assets_dir: Path, strict: bool = False) -> str:
    """Replace mermaid code blocks with SVG image references.
    If mmdc is unavailable, optionally warn and leave blocks untouched (degrades to code)."""
    if not MERMAID_BLOCK_RE.search(md_text):
        return md_text

    mmdc = _tool_path('mmdc')
    if mmdc is None:
        if strict:
            die(4, "mermaid blocks found and --strict-mermaid set, but 'mmdc' is not available. "
                   "Run scripts/install.sh to install it locally under scripts/node_modules/.")
        print("[render.py] WARN: 'mmdc' not found; mermaid blocks will render as code. "
              "Run scripts/install.sh to install mermaid-cli locally.", file=sys.stderr)
        return md_text

    assets_dir.mkdir(parents=True, exist_ok=True)
    env = _subprocess_env()
    # The rewritten .md sits next to the input, so SVG refs must be relative to input_md.parent
    # (e.g. "deck_assets/diagram-<sha1>.svg"), not just the bare filename.
    ref_base = assets_dir.parent

    def replace(match: re.Match) -> str:
        body = match.group(1)
        digest = hashlib.sha1(body.encode('utf-8')).hexdigest()[:10]
        mmd_path = assets_dir / f'diagram-{digest}.mmd'
        svg_path = assets_dir / f'diagram-{digest}.svg'
        if not svg_path.exists():
            mmd_path.write_text(body, encoding='utf-8')
            try:
                subprocess.run(
                    [str(mmdc), '-i', str(mmd_path), '-o', str(svg_path),
                     '-b', 'transparent'],
                    check=True, capture_output=True, env=env,
                )
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else ''
                if strict:
                    die(4, f"mmdc failed on diagram {digest}: {stderr}")
                print(f"[render.py] WARN: mmdc failed on diagram {digest}; keeping as code. {stderr}",
                      file=sys.stderr)
                return match.group(0)
        rel = svg_path.relative_to(ref_base).as_posix()
        return f'![w:900]({rel})'

    return MERMAID_BLOCK_RE.sub(replace, md_text)


def render(
    input_md: Path,
    output: Path,
    fmt: str,
    *,
    use_mermaid: bool = True,
    strict_mermaid: bool = False,
    theme: str | None = None,
) -> None:
    marp = _tool_path('marp')
    if marp is None:
        die(2, "'marp' CLI not found. Run scripts/install.sh to install marp-cli locally "
               "under scripts/node_modules/.")

    if fmt not in SUPPORTED_FORMATS:
        die(1, f"format must be one of {SUPPORTED_FORMATS}, got '{fmt}'")

    src = input_md.read_text(encoding='utf-8')
    assets_dir = input_md.parent / f'{input_md.stem}_assets'
    processed = preprocess_mermaid(src, assets_dir, strict=strict_mermaid) if use_mermaid else src

    rewritten_md = input_md.with_name(input_md.stem + '.rendered' + input_md.suffix)
    rewritten_md.write_text(processed, encoding='utf-8')

    cmd = [str(marp), f'--{fmt}', '--allow-local-files', str(rewritten_md), '-o', str(output)]
    if theme:
        cmd.extend(['--theme', theme])

    try:
        subprocess.run(cmd, check=True, env=_subprocess_env())
    except subprocess.CalledProcessError as exc:
        die(3, f"marp failed (exit {exc.returncode}); see stderr above")
    finally:
        if rewritten_md.exists():
            rewritten_md.unlink()

    print(f'[render.py] wrote {output} ({output.stat().st_size} bytes)')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render a Marp markdown with mermaid preprocessing.')
    parser.add_argument('input', type=Path, help='Input .md file')
    parser.add_argument('--format', default='pptx', choices=SUPPORTED_FORMATS,
                        help='Output format (default: pptx)')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output path (default: <input_stem>.<format>)')
    parser.add_argument('--no-mermaid', action='store_true',
                        help='Skip mermaid preprocessing (faster; diagrams stay as code blocks)')
    parser.add_argument('--strict-mermaid', action='store_true',
                        help='Fail if mermaid blocks exist but cannot be rendered')
    parser.add_argument('--theme', default=None, help='Override theme (name or CSS path)')
    args = parser.parse_args(argv)

    if not args.input.exists():
        die(1, f"input file not found: {args.input}")

    output = args.output or args.input.with_suffix(f'.{args.format}')
    render(args.input, output, args.format,
           use_mermaid=not args.no_mermaid,
           strict_mermaid=args.strict_mermaid,
           theme=args.theme)
    return 0


if __name__ == '__main__':
    sys.exit(main())
