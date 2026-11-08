#!/usr/bin/env python3
"""Detect the host agent vendor for the agentic-eval backend (capability B).

Self-contained reimplementation (inspired by skill-parallel-orchestration §1,
but with no dependency on it). Detection order, most reliable first:

  1. Explicit override:  AUTO_IMPROVE_VENDOR env var
  2. Tool-fingerprint:    a CLI binary on PATH (claude / gemini / codex)
  3. Repo markers:        CLAUDE.md → claude, GEMINI.md → gemini
  4. Fallback:            "fallback" (no agentic CLI)

The returned vendor selects an adapter from scripts/backends/. Only the claude
adapter can run skill-trigger eval; with any other vendor a `skill` /
`full-skill` run stops before the baseline with exit code 2 (no LLM-grading
substitute). Prompt, workflow, dataset and text runs need no agentic CLI.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from scripts.common import install_human_channel  # type: ignore
except ImportError:
    from common import install_human_channel

VENDOR_CLAUDE = "claude"
VENDOR_GEMINI = "gemini"
VENDOR_CODEX = "codex"
VENDOR_FALLBACK = "fallback"

_CLI_BY_VENDOR = {
    VENDOR_CLAUDE: "claude",
    VENDOR_GEMINI: "gemini",
    VENDOR_CODEX: "codex",
}


def _find_marker(start: Path, names: set[str]) -> str | None:
    """Walk upward from start to a .git boundary / fs root looking for markers."""
    for parent in [start, *start.parents]:
        for name in names:
            if (parent / name).exists():
                return name
        if (parent / ".git").exists():
            break
    return None


def detect_vendor(cwd: Path | None = None) -> str:
    override = os.environ.get("AUTO_IMPROVE_VENDOR")
    if override:
        return override.strip().lower()

    # Tool-fingerprint: prefer a vendor whose CLI is actually installed.
    for vendor, binary in _CLI_BY_VENDOR.items():
        if shutil.which(binary):
            return vendor

    # Repo markers.
    start = Path(cwd or Path.cwd()).resolve()
    marker = _find_marker(start, {"CLAUDE.md", "GEMINI.md"})
    if marker == "CLAUDE.md":
        return VENDOR_CLAUDE
    if marker == "GEMINI.md":
        return VENDOR_GEMINI

    return VENDOR_FALLBACK


def main() -> int:
    install_human_channel()
    parser = argparse.ArgumentParser(description="Detect host agent vendor")
    parser.add_argument("--cwd", default=None, help="directory to detect from")
    args = parser.parse_args()
    print(detect_vendor(Path(args.cwd) if args.cwd else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
