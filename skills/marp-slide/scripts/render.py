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
                     [--mermaid-config PATH]

Examples:
  render.py deck.md                               # -> deck.pptx, mermaid pre-rendered
  render.py deck.md --format pdf                  # -> deck.pdf
  render.py deck.md --output /tmp/out.pptx        # explicit output path
  render.py deck.md --no-mermaid                  # skip preprocessing (diagrams stay as code)
  render.py deck.md --theme business              # override frontmatter theme
  render.py deck.md --mermaid-config conf.json    # pass -c to mmdc (Cyrillic/CJK font fix)

Exit codes:
  0 — success
  1 — bad args or input
  2 — marp CLI not installed (fatal)
  3 — marp rendering failed or timed out
  4 — mermaid preprocessing failed AND --strict-mermaid was set

Security note:
  render.py always invokes marp with --allow-local-files, which lets marp embed any file
  the current user can read. Render only Marp `.md` files you trust.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_BIN = SCRIPT_DIR / 'node_modules' / '.bin'
DEFAULT_MERMAID_CONFIG = SCRIPT_DIR / 'mermaid-config.json'

MERMAID_BLOCK_RE = re.compile(r'```mermaid\s*\n(.*?)\n```', re.DOTALL)
SUPPORTED_FORMATS = ('pptx', 'pdf', 'html', 'png', 'jpeg')
SUBPROCESS_TIMEOUT = 300  # seconds per marp / mmdc invocation


def die(code: int, msg: str) -> None:
    print(f'[render.py] ERROR: {msg}', file=sys.stderr)
    sys.exit(code)


def _tool_path(name: str) -> Path | None:
    """Resolve a CLI tool, preferring local node_modules/.bin over system PATH.
    The binary must exist AND be executable — a present-but-non-executable file
    (e.g. permissions lost during tar restore) is treated as missing so the caller
    gets the friendly "run install.sh" message instead of a raw PermissionError."""
    local = LOCAL_BIN / name
    if local.exists() and os.access(local, os.X_OK):
        return local
    found = shutil.which(name)
    return Path(found) if found else None


def _subprocess_env() -> dict[str, str]:
    """Return an env with scripts/node_modules/.bin prepended to PATH,
    so any child process resolves our locally-installed binaries first."""
    env = os.environ.copy()
    env['PATH'] = f'{LOCAL_BIN}{os.pathsep}' + env.get('PATH', '')
    return env


def _mmdc_cache_key(mmdc: Path, mermaid_config: Path | None, env: dict[str, str]) -> str:
    """Fingerprint of the rendering toolchain: mmdc version + the flag set + the
    config file content. Mixed into each diagram's SHA1 so cached SVGs are
    invalidated when the user upgrades mmdc or changes the config."""
    version = ''
    try:
        result = subprocess.run(
            [str(mmdc), '--version'],
            capture_output=True, text=True, check=False,
            timeout=30, env=env,
        )
        version = (result.stdout or '').strip()
    except (subprocess.SubprocessError, OSError):
        pass
    config_bytes = b''
    if mermaid_config and mermaid_config.exists():
        config_bytes = mermaid_config.read_bytes()
    return hashlib.sha1(
        version.encode('utf-8') + b'|-b|transparent|' + config_bytes
    ).hexdigest()[:8]


def preprocess_mermaid(
    md_text: str,
    assets_dir: Path,
    *,
    strict: bool = False,
    mermaid_config: Path | None = None,
) -> str:
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

    env = _subprocess_env()
    cache_key = _mmdc_cache_key(mmdc, mermaid_config, env)
    assets_dir.mkdir(parents=True, exist_ok=True)
    ref_base = assets_dir.parent

    def replace(match: re.Match) -> str:
        body = match.group(1)
        digest = hashlib.sha1(
            body.encode('utf-8') + b'|' + cache_key.encode('ascii')
        ).hexdigest()[:10]
        mmd_path = assets_dir / f'diagram-{digest}.mmd'
        svg_path = assets_dir / f'diagram-{digest}.svg'
        if not svg_path.exists():
            mmd_path.write_text(body, encoding='utf-8')
            cmd = [str(mmdc), '-i', str(mmd_path), '-o', str(svg_path),
                   '-b', 'transparent']
            if mermaid_config:
                cmd.extend(['-c', str(mermaid_config)])
            try:
                subprocess.run(
                    cmd, check=True, capture_output=True, env=env,
                    timeout=SUBPROCESS_TIMEOUT,
                    stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                if strict:
                    die(4, f"mmdc timed out after {SUBPROCESS_TIMEOUT}s on diagram {digest}.")
                print(f"[render.py] WARN: mmdc timed out on diagram {digest}; keeping as code.",
                      file=sys.stderr)
                return match.group(0)
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
    mermaid_config: Path | None = None,
    pptx_editable: bool = False,
) -> None:
    marp = _tool_path('marp')
    if marp is None:
        die(2, "'marp' CLI not found. Run scripts/install.sh to install marp-cli locally "
               "under scripts/node_modules/.")

    src = input_md.read_text(encoding='utf-8')
    assets_dir = input_md.parent / f'{input_md.stem}_assets'
    processed = preprocess_mermaid(
        src, assets_dir,
        strict=strict_mermaid,
        mermaid_config=mermaid_config,
    ) if use_mermaid else src

    # Write the rewritten markdown to a unique temp file next to the input.
    # marp resolves relative asset paths (including our rewritten mermaid SVGs)
    # against the input file's directory, so it has to live there. Using
    # tempfile.NamedTemporaryFile avoids the silent-clobber risk that a fixed
    # "<stem>.rendered.md" name carries if the user already owns such a file.
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        dir=input_md.parent,
        prefix=f'.{input_md.stem}.render-',
        suffix=input_md.suffix,
        delete=False,
    ) as tmp:
        tmp.write(processed)
        rewritten_md = Path(tmp.name)

    cmd = [str(marp), f'--{fmt}', '--allow-local-files', str(rewritten_md), '-o', str(output)]
    if theme:
        cmd.extend(['--theme', theme])
    if pptx_editable and fmt == 'pptx':
        # marp's default PPTX is rasterised (each slide becomes one PNG
        # background, which drops externally-referenced images such as
        # our pre-rendered mermaid diagrams). `--pptx-editable` emits a
        # proper editable PPTX with separate image shapes, but requires
        # LibreOffice (`soffice`) on PATH.
        if shutil.which('soffice') is None:
            die(2, "--pptx-editable requires LibreOffice (`soffice`) on PATH. "
                   "Install it: `brew install --cask libreoffice` (macOS) or "
                   "`apt install libreoffice --no-install-recommends` (Debian).")
        cmd.append('--pptx-editable')

    try:
        # stdin=DEVNULL: when stdin is a pipe (CI/background), marp waits on it
        # forever unless told otherwise. Use DEVNULL unconditionally — we never
        # pipe markdown in, always pass it as a path arg.
        subprocess.run(
            cmd, check=True, env=_subprocess_env(),
            timeout=SUBPROCESS_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        die(3, f"marp timed out after {SUBPROCESS_TIMEOUT}s")
    except subprocess.CalledProcessError as exc:
        die(3, f"marp failed (exit {exc.returncode}); see stderr above")
    finally:
        if rewritten_md.exists():
            rewritten_md.unlink()

    print(f'[render.py] wrote {output} ({output.stat().st_size} bytes)')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Render a Marp markdown with mermaid preprocessing.'
    )
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
    parser.add_argument(
        '--mermaid-config', type=Path, default=None,
        help=f'Path to a mermaid config JSON (passed to mmdc via -c). '
             f'If omitted, {DEFAULT_MERMAID_CONFIG.name} in scripts/ is auto-loaded when present. '
             f'Useful for Cyrillic/CJK font fallbacks.',
    )
    parser.add_argument(
        '--pptx-editable', action='store_true',
        help='For --format pptx: produce an editable PPTX with separate '
             'text/image shapes instead of the default rasterised slide-as-PNG. '
             'Requires LibreOffice (`soffice`) on PATH.',
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        die(1, f"input file not found: {args.input}")

    mermaid_config = args.mermaid_config
    if mermaid_config is None and DEFAULT_MERMAID_CONFIG.exists():
        mermaid_config = DEFAULT_MERMAID_CONFIG
    if mermaid_config is not None and not mermaid_config.exists():
        die(1, f"mermaid config not found: {mermaid_config}")

    output = args.output or args.input.with_suffix(f'.{args.format}')
    render(args.input, output, args.format,
           use_mermaid=not args.no_mermaid,
           strict_mermaid=args.strict_mermaid,
           theme=args.theme,
           mermaid_config=mermaid_config,
           pptx_editable=args.pptx_editable)
    return 0


if __name__ == '__main__':
    sys.exit(main())
