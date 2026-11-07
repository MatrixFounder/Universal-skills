#!/usr/bin/env python3
"""Check that each skill this repository copies from agentic-development matches canonical.

agentic-development is the master of every skill it also carries. A directory of `skills/`
is a copy when `.agentic-development/.agent/skills/<name>` is a directory; the list is derived,
so a new copy needs no edit here. A copy is edited in canonical, copied with `cp`, and checked
with this script (CLAUDE.md, "Framework copies").

The comparison is byte-wise, over the working trees of both sides, plus the executable bit
outside Windows. These names are not compared: `.DS_Store`, `__pycache__`, `.venv`,
`node_modules`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, and files ending in `.pyc`.

Drift kinds: `differs`, `mode differs`, `only in canonical`, `only in copy`, `symlink in
canonical|copy` (a link inside a skill is not followed), `special in canonical|copy` (a FIFO,
a socket or a device, which is never read), and `the copy is a symlink` (a copy directory that
links elsewhere: `.agentic-development` is not published, so the link would dangle).

Known limits:
    - An empty directory on one side only is not reported; git does not track one either.
    - An untracked file of canonical, such as a scratch note, counts: it shows as
      `only in canonical`. Delete it or ignore it in canonical; do not publish it.
    - A canonical skill directory that is itself a link is followed.
    - A Windows junction is not a symlink to `os.path.islink` and is walked into.

Exit codes:
    0  every copy matches, or `.agentic-development` does not resolve (`SKIPPED`)
    1  at least one copy differs
    2  `skills/` is absent or cannot be listed; `--canonical`, or the default canonical behind a
       resolving `.agentic-development`, names no directory; no copy is found; an entry could
       not be read (`unreadable`); or stdout closed before the report was written.
       2 takes precedence over 1.
"""

import argparse
import os
import stat
import sys
from pathlib import Path

IGNORED_NAMES = {".DS_Store", "__pycache__", ".venv", "node_modules", ".pytest_cache",
                 ".mypy_cache", ".ruff_cache"}
IGNORED_SUFFIXES = (".pyc",)
COMPARE_MODE = os.name != "nt"


def install_human_channel():
    """Degrade a character the locale cannot encode instead of crashing (CLAUDE.md, CLI I/O).

    `errors=` only, never `encoding=`: the caller's codec stays. `line_buffering` makes a
    closed pipe raise inside `main()` rather than at interpreter shutdown.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace", line_buffering=True)


def abandon_stdout():
    """Point a dead stdout's descriptor at /dev/null, so the shutdown flush cannot fail again.

    Without it CPython prints "Exception ignored while flushing sys.stdout" and replaces the
    exit status with 120 (the recipe of transcript-fetcher's `_stdout.abandon_stdout`).
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError, AttributeError):
        pass


class Tree:
    """The compared entries under one skill directory, keyed by POSIX relative path."""

    def __init__(self, root):
        self.files, self.symlinks, self.specials, self.unreadable = {}, set(), set(), []
        root = Path(root)

        def rel(path):
            return Path(path).relative_to(root).as_posix()

        def on_error(exc):
            self.unreadable.append((rel(exc.filename), exc.strerror or str(exc)))

        for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
            here = Path(dirpath)
            kept = []
            for name in sorted(dirnames):
                if name in IGNORED_NAMES:
                    continue
                if (here / name).is_symlink():
                    self.symlinks.add(rel(here / name))
                else:
                    kept.append(name)
            dirnames[:] = kept
            for name in filenames:
                if name in IGNORED_NAMES or name.endswith(IGNORED_SUFFIXES):
                    continue
                path = here / name
                try:
                    mode = path.lstat().st_mode
                except OSError as exc:
                    self.unreadable.append((rel(path), exc.strerror or str(exc)))
                    continue
                if stat.S_ISLNK(mode):
                    self.symlinks.add(rel(path))
                elif stat.S_ISREG(mode):
                    self.files[rel(path)] = (path, mode)
                else:
                    self.specials.add(rel(path))


def read(path, rel, unreadable):
    """The bytes of `path`, or None after recording why they could not be read."""
    try:
        return path.read_bytes()
    except OSError as exc:
        unreadable.append((rel, exc.strerror or str(exc)))
        return None


def under(rel, prefixes):
    """True when `rel` is one of `prefixes` or lies below one of them ("." is the root)."""
    return any(p == "." or rel == p or rel.startswith(p + "/") for p in prefixes)


def compare(canonical, copy):
    """Return (drift, unreadable): `(kind, path)` per drifted entry, `(path, reason)` per failure.

    An entry below a directory that could not be listed is not reported as drift: the
    comparison there is incomplete, and `unreadable` already says so.
    """
    ours, theirs = Tree(canonical), Tree(copy)
    unreadable = [(f"canonical/{r}", why) for r, why in ours.unreadable]
    unreadable += [(f"copy/{r}", why) for r, why in theirs.unreadable]
    blind = {r for r, _ in ours.unreadable} | {r for r, _ in theirs.unreadable}
    drift = [(f"{kind} in canonical", r) for kind, entries in
             (("symlink", ours.symlinks), ("special", ours.specials)) for r in sorted(entries)]
    drift += [(f"{kind} in copy", r) for kind, entries in
              (("symlink", theirs.symlinks), ("special", theirs.specials)) for r in sorted(entries)]
    for rel in sorted(set(ours.files) | set(theirs.files)):
        if under(rel, blind):
            continue
        if rel not in theirs.files:
            drift.append(("only in canonical", rel))
        elif rel not in ours.files:
            drift.append(("only in copy", rel))
        else:
            (a_path, a_mode), (b_path, b_mode) = ours.files[rel], theirs.files[rel]
            a = read(a_path, f"canonical/{rel}", unreadable)
            b = read(b_path, f"copy/{rel}", unreadable)
            if a is not None and b is not None and a != b:
                drift.append(("differs", rel))
            elif COMPARE_MODE and (a_mode & 0o111) != (b_mode & 0o111):
                drift.append(("mode differs", rel))
    return drift, unreadable


def copies(skills_dir, canonical_skills):
    """Names of the directories of `skills_dir` that canonical also carries."""
    return sorted(
        p.name for p in skills_dir.iterdir()
        if p.is_dir() and (canonical_skills / p.name).is_dir()
    )


def plural(count, one, many):
    return f"{count} {one if count == 1 else many}"


def main(argv=None):
    install_human_channel()
    parser = argparse.ArgumentParser(
        description="Check that the skills copied from agentic-development match canonical.")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent,
        help="repository root (default: the parent of scripts/)")
    parser.add_argument(
        "--canonical", type=Path,
        help="canonical skills directory (default: <root>/.agentic-development/.agent/skills)")
    args = parser.parse_args(argv)

    skills_dir = args.root / "skills"
    if not skills_dir.is_dir():
        print(f"error: {skills_dir} is not a directory", file=sys.stderr)
        return 2
    if args.canonical is not None:
        canonical = args.canonical
        if not canonical.is_dir():
            print(f"error: --canonical {canonical} is not a directory", file=sys.stderr)
            return 2
    else:
        sibling = args.root / ".agentic-development"
        canonical = sibling / ".agent" / "skills"
        if not sibling.is_dir():
            print(f"SKIPPED: {sibling} does not resolve; no copy was compared")
            return 0
        if not canonical.is_dir():
            print(f"error: {sibling} resolves, but {canonical} is not a directory",
                  file=sys.stderr)
            return 2

    for listed in (skills_dir, canonical):
        try:
            os.listdir(listed)
        except OSError as exc:
            print(f"error: cannot list {listed}: {exc.strerror or exc}", file=sys.stderr)
            return 2
    names = copies(skills_dir, canonical)
    if not names:
        print(f"error: no directory of {skills_dir} is also in {canonical}", file=sys.stderr)
        return 2

    drifted, failed = 0, 0
    for name in names:
        if (skills_dir / name).is_symlink():
            drifted += 1
            print(f"DRIFT  {name}: the copy is a symlink to {os.readlink(skills_dir / name)}")
            continue
        drift, unreadable = compare(canonical / name, skills_dir / name)
        if not drift and not unreadable:
            print(f"ok     {name}")
            continue
        if drift:
            drifted += 1
            print(f"DRIFT  {name}: {plural(len(drift), 'entry', 'entries')}")
            for kind, rel in drift:
                print(f"         {kind}: {rel}")
        if unreadable:
            failed += 1
            print(f"ERROR  {name}: {plural(len(unreadable), 'entry', 'entries')} not read")
            for rel, why in unreadable:
                print(f"         unreadable: {rel} ({why})")
    print(f"{plural(len(names), 'copy', 'copies')} checked, {drifted} drifted, "
          f"{failed} not fully read (canonical: {canonical})")
    if failed:
        return 2
    return 1 if drifted else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        abandon_stdout()
        sys.exit(2)
