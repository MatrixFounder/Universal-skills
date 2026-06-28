#!/usr/bin/env python3
"""Doctor + opt-in installer for transcript-fetcher's optional ASR components.

The skill's only HARD dependency is ``yt-dlp`` (installed by ``install.sh`` into
the per-skill venv). Everything used for the ASR fallback — MacWhisper (``mw``),
the OpenAI Whisper CLI (``whisper``), whisper.cpp (``whisper-cli``/``main``) and
``ffmpeg`` — is an **optional external tool**. This script:

  * **Detects** what is present (honours the ``TRANSCRIPT_FETCHER_*_BIN``
    overrides from ``_config``);
  * **Guides** — prints the exact, platform-aware install command for anything
    missing (default, mutates nothing);
  * **Installs on request** — ``--install-whisper`` pip-installs ``openai-whisper``
    into THIS venv (safe, in-venv); ``--system --run`` executes the system
    package-manager commands for ``ffmpeg`` / whisper.cpp (opt-in, double-gated).

Usage::

    ./scripts/.venv/bin/python scripts/install_components.py            # report only
    ./scripts/.venv/bin/python scripts/install_components.py --json
    ./scripts/.venv/bin/python scripts/install_components.py --install-whisper
    ./scripts/.venv/bin/python scripts/install_components.py --system           # print sys cmds
    ./scripts/.venv/bin/python scripts/install_components.py --system --run     # run them

Nothing here is destructive; system installs require BOTH ``--system`` and
``--run`` and never use ``sudo`` implicitly (the printed command is shown first).
"""
from __future__ import annotations

import argparse
import json
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import _config as cfg  # noqa: E402

_OS = platform.system()  # "Darwin" | "Linux" | "Windows"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _have_yt_dlp() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _have_pymodule(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _brew_or_apt(pkg_brew: str, pkg_apt: str) -> str:
    if _OS == "Darwin":
        return f"brew install {pkg_brew}"
    if _OS == "Linux":
        return f"sudo apt-get install -y {pkg_apt}"
    return f"(install {pkg_brew} for your platform)"


def _components() -> list[dict]:
    """Describe each component: probe result + how to get it."""
    mw_bin = cfg.tool_bin("MW", "mw")
    whisper_bin = cfg.tool_bin("WHISPER", "whisper")
    ffmpeg = cfg.ffmpeg_bin()
    wcpp = cfg.tool_bin("WHISPER_CPP", "") or ("whisper-cli" if _have("whisper-cli") else "main")

    return [
        {
            "key": "yt-dlp",
            "label": "yt-dlp (REQUIRED — metadata + media download)",
            "present": _have_yt_dlp(),
            "required": True,
            "install_hint": "bash scripts/install.sh   # installs into the venv",
            "kind": "venv",
        },
        {
            "key": "macwhisper",
            "label": f"MacWhisper CLI ('{mw_bin}') — ASR #1, local, fast on Apple Silicon",
            "present": _have(mw_bin),
            "required": False,
            "install_hint": (
                "Install the MacWhisper app (https://goodsnooze.gumroad.com/l/macwhisper "
                "or the Mac App Store); the 'mw' CLI ships with it. macOS only."
            ),
            "kind": "app",
        },
        {
            "key": "ffmpeg",
            "label": f"ffmpeg ('{ffmpeg}') — REQUIRED for X Broadcast/Space ASR (extract m4a from HLS); also needed by whisper/whisper.cpp",
            "present": _have(ffmpeg),
            "required": False,
            "install_hint": _brew_or_apt("ffmpeg", "ffmpeg"),
            "kind": "system",
            "sys_cmd": _brew_or_apt("ffmpeg", "ffmpeg"),
        },
        {
            "key": "whisper-cli",
            "label": f"OpenAI Whisper CLI ('{whisper_bin}') — ASR #2 (pip, needs ffmpeg)",
            "present": _have(whisper_bin),
            "required": False,
            "install_hint": f"{Path(sys.executable).name} -m pip install -U openai-whisper   (or: --install-whisper)",
            "kind": "pip-venv",
        },
        {
            "key": "whisper-cpp",
            "label": f"whisper.cpp ('{wcpp}') — ASR #3 (needs ffmpeg + a ggml model via --asr-model)",
            "present": _have("whisper-cli") or _have("main") or (bool(cfg.tool_bin("WHISPER_CPP", "")) and _have(cfg.tool_bin("WHISPER_CPP", ""))),
            "required": False,
            "install_hint": _brew_or_apt("whisper-cpp", "whisper.cpp"),
            "kind": "system",
            "sys_cmd": _brew_or_apt("whisper-cpp", "whisper.cpp"),
        },
    ]


def _print_report(components: list[dict]) -> None:
    print("transcript-fetcher — component status\n")
    any_asr = False
    for c in _components_with_asr_flag(components):
        mark = "✓" if c["present"] else "✗"
        req = " (required)" if c["required"] else ""
        print(f"  [{mark}] {c['label']}{req}")
        if not c["present"]:
            print(f"        → {c['install_hint']}")
        if c["present"] and c["key"] in _ASR_KEYS:
            any_asr = True
    print()
    if not any_asr:
        print(
            "  ⚠ No local ASR backend detected. Caption-less media (X Broadcasts/Spaces,\n"
            "    most native X video) will exit 7 (MissingDependency) unless you install one\n"
            "    of the above, or enable the cloud backend (--asr-allow-cloud + OPENAI_API_KEY)."
        )
    else:
        print("  ✓ At least one ASR backend is available — caption-less media can be transcribed.")


_ASR_KEYS = {"macwhisper", "whisper-cli", "whisper-cpp"}


def _components_with_asr_flag(components: list[dict]) -> list[dict]:
    return components


def _install_whisper() -> int:
    print("Installing openai-whisper into the venv "
          f"({sys.executable}) …")
    rc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "openai-whisper"],
        check=False,
    ).returncode
    if rc == 0:
        print("✓ openai-whisper installed. Note: it also needs ffmpeg at runtime.")
    else:
        print("✗ pip install failed (see output above).", file=sys.stderr)
    return rc


def _system_install(components: list[dict], run: bool) -> int:
    missing = [c for c in components if not c["present"] and c.get("kind") == "system"]
    if not missing:
        print("No missing system components.")
        return 0
    rc_total = 0
    for c in missing:
        cmd = c.get("sys_cmd", "")
        print(f"\n# {c['label']}\n{cmd}")
        if run and cmd and not cmd.startswith("("):
            print(f"  → running: {cmd}")
            # argv form (no shell) — the commands are fixed literals, but
            # avoiding shell=True kills the injection class outright.
            rc = subprocess.run(shlex.split(cmd), shell=False, check=False).returncode
            rc_total |= rc
            print("    ✓ done" if rc == 0 else f"    ✗ exit {rc}")
    if not run:
        print("\n(Dry run — re-run with `--system --run` to execute the commands above.)")
    return rc_total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="install_components.py",
        description="Detect / install transcript-fetcher's optional ASR components.",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable status, then exit.")
    p.add_argument("--install-whisper", action="store_true",
                   help="pip-install openai-whisper into THIS venv (safe, in-venv).")
    p.add_argument("--system", action="store_true",
                   help="Show system package-manager commands for ffmpeg / whisper.cpp.")
    p.add_argument("--run", action="store_true",
                   help="With --system, actually execute the commands (opt-in).")
    args = p.parse_args(argv)

    components = _components()

    if args.json:
        print(json.dumps(
            {c["key"]: {"present": c["present"], "required": c["required"]} for c in components},
            ensure_ascii=False, indent=2,
        ))
        return 0

    _print_report(components)

    rc = 0
    if args.install_whisper:
        print()
        rc |= _install_whisper()
    if args.system:
        rc |= _system_install(components, run=args.run)
    return rc


if __name__ == "__main__":
    sys.exit(main())
