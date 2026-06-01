#!/usr/bin/env python3
"""Snapshot + git-isolation helpers for skill-auto-improve.

Two layers:

  * File snapshots (core, always available, offline-testable): copy the artifact
    (file or directory) into the workspace before each apply; restore on REVERT.
    This is the revert mechanism and does not depend on git.

  * Git isolation (when the artifact is inside a git repo): run the whole loop
    on a dedicated branch `auto-improve/<slug>/<ts>` so intermediate commits
    never land on the user's working branch. KEEP advances the branch with a
    commit; the user merges the winner explicitly. Phase 0 refuses to start on
    a dirty working tree.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


# ----------------------------- file snapshots ------------------------------
# Heavy, regenerable, or out-of-scope subtrees never need snapshotting. NOTE:
# `evals` is intentionally NOT ignored — it is the immutable harness and we want
# the snapshot to be able to restore it verbatim if anything ever touches it.
_SNAPSHOT_IGNORE = shutil.ignore_patterns(
    "node_modules", ".venv", "venv", "__pycache__", ".git", ".pytest_cache",
)


def save_snapshot(artifact_path: Path, workspace: Path, iteration: int) -> str:
    """Copy artifact into workspace/snapshots/iter-<n>/ and return the ref path."""
    artifact_path = Path(artifact_path)
    dest = Path(workspace) / "snapshots" / f"iter-{iteration}" / artifact_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if artifact_path.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(artifact_path, dest, ignore=_SNAPSHOT_IGNORE)
    else:
        shutil.copy2(artifact_path, dest)
    return str(dest)


def restore_snapshot(artifact_path: Path, ref: str) -> None:
    """Restore the artifact from a snapshot ref produced by save_snapshot."""
    artifact_path = Path(artifact_path)
    src = Path(ref)
    if src.is_dir():
        if artifact_path.exists():
            shutil.rmtree(artifact_path)
        shutil.copytree(src, artifact_path)
    else:
        shutil.copy2(src, artifact_path)


# ------------------------------- git helpers --------------------------------
def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def is_git_repo(cwd: Path) -> bool:
    return _git(["rev-parse", "--is-inside-work-tree"], cwd).returncode == 0


def is_clean(cwd: Path) -> bool:
    """True if the working tree has no uncommitted changes."""
    res = _git(["status", "--porcelain"], cwd)
    return res.returncode == 0 and res.stdout.strip() == ""


def current_branch(cwd: Path) -> str | None:
    res = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return res.stdout.strip() if res.returncode == 0 else None


def create_branch(cwd: Path, branch: str) -> bool:
    """Create and checkout an isolation branch. Returns success."""
    return _git(["checkout", "-b", branch], cwd).returncode == 0


def commit_all(cwd: Path, message: str, paths: list[str] | None = None) -> str | None:
    """Stage paths (or all) and commit. Returns the commit SHA, or None."""
    add_args = ["add", *(paths or ["-A"])]
    if _git(add_args, cwd).returncode != 0:
        return None
    if _git(["commit", "-m", message], cwd).returncode != 0:
        return None
    res = _git(["rev-parse", "HEAD"], cwd)
    return res.stdout.strip() if res.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot / git-isolation helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("artifact")
    s.add_argument("--workspace", required=True)
    s.add_argument("--iteration", type=int, required=True)
    r = sub.add_parser("restore")
    r.add_argument("artifact")
    r.add_argument("--ref", required=True)
    c = sub.add_parser("clean-check")
    c.add_argument("--cwd", default=".")
    args = parser.parse_args()

    if args.cmd == "save":
        print(save_snapshot(Path(args.artifact), Path(args.workspace), args.iteration))
    elif args.cmd == "restore":
        restore_snapshot(Path(args.artifact), args.ref)
    elif args.cmd == "clean-check":
        cwd = Path(args.cwd)
        if not is_git_repo(cwd):
            print("not-a-repo")
            return 0
        print("clean" if is_clean(cwd) else "dirty")
        return 0 if is_clean(cwd) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
