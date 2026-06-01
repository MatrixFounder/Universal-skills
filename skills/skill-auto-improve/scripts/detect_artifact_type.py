#!/usr/bin/env python3
"""Detect the artifact type for a given path.

Heuristics (first match wins):
  - dir contains SKILL.md            → "skill"      (or "full-skill" with --full)
  - file named evals.json / *.evals.json, or a JSON list of {query,...}
                                     → "dataset"
  - file under a workflows/ dir, or md with workflow-ish frontmatter
                                     → "workflow"
  - any other .md / .txt / prompt    → "prompt"

Prints the detected type to stdout. Exit 0 on success, 2 on unknown.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import shared constants whether run as script or imported as a module.
try:
    from scripts.common import (  # type: ignore
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_WORKFLOW,
    )
except ImportError:
    from common import (
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_WORKFLOW,
    )


def _looks_like_dataset(path: Path) -> bool:
    if path.suffix != ".json":
        return False
    if path.name == "evals.json" or path.name.endswith(".evals.json"):
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = set(data[0])
        return bool(keys & {"query", "prompt", "should_trigger", "expectations"})
    return False


def detect_type(path: Path, full: bool = False) -> str:
    path = Path(path)
    if path.is_dir():
        if (path / "SKILL.md").exists():
            return ARTIFACT_FULL_SKILL if full else ARTIFACT_SKILL
        raise ValueError(f"directory has no SKILL.md: {path}")

    if not path.exists():
        raise FileNotFoundError(path)

    if _looks_like_dataset(path):
        return ARTIFACT_DATASET

    # workflow: lives under a workflows/ directory, or is a command file
    parts = {p.lower() for p in path.parts}
    if "workflows" in parts or "commands" in parts:
        return ARTIFACT_WORKFLOW

    if path.suffix in (".md", ".markdown", ".txt", ".prompt"):
        return ARTIFACT_PROMPT

    raise ValueError(f"cannot determine artifact type for: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect artifact type")
    parser.add_argument("path")
    parser.add_argument("--full", action="store_true", help="report full-skill for skill dirs")
    args = parser.parse_args()
    try:
        print(detect_type(Path(args.path), full=args.full))
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"unknown: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
