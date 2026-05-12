"""Text replacement / insertion / paragraph deletion for .docx files.

UC-1 (--replace): replace anchor text in-place, preserving run formatting.
Anchor must fit within a single run (honest scope — cross-run matching
requires run splitting which risks corrupting complex formatting; D6/B).

UC-2 (--insert-after): graft OOXML paragraphs after anchor paragraphs.
Images in Markdown source are NOT resolved to live r:embed (R10.b).

UC-3 (--delete-paragraph): remove paragraphs containing anchor. Refuses to
empty <w:body> — the last body paragraph is never deleted (R10.c).

UC-4 (--unpacked-dir): library mode — operate on an already-unpacked tree.
Lands in task-006-07b.
"""
from __future__ import annotations

import argparse
import contextlib
import errno
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterator

from _errors import add_json_errors_argument, report_error
from _app_errors import (
    _AppError,
    AnchorNotFound,
    EmptyInsertSource,
    InsertSourceTooLarge,
    Md2DocxFailed,
    Md2DocxNotAvailable,
    Md2DocxOutputInvalid,
    LastParagraphCannotBeDeleted,
    NotADocxTree,
    PostValidateFailed,
    SelfOverwriteRefused,
)
from _actions import (
    _do_replace,
    _materialise_md_source,
    _extract_insert_paragraphs,
    _do_insert_after,
    _do_delete_paragraph,
    _iter_searchable_parts,
    _deep_clone,
    _safe_remove_paragraph,
    _WP_CONTENT_TYPES,
    _fallback_glob_parts,
)
from office.unpack import unpack  # type: ignore
from office.pack import pack  # type: ignore
from office._encryption import assert_not_encrypted, EncryptedFileError  # type: ignore
from office._macros import warn_if_macros_will_be_dropped  # type: ignore


# ---------------------------------------------------------------------------
# F1: cross-cutting pre-flight helpers
# ---------------------------------------------------------------------------

def _assert_distinct_paths(input_path: Path, output_path: Path) -> None:
    """Raise SelfOverwriteRefused if input and output resolve to the same path.

    Uses Path.resolve(strict=False) so the check works when output does not
    yet exist. Symlinks are followed for both sides (cross-7).
    """
    resolved_in = Path(input_path).resolve(strict=False)
    resolved_out = Path(output_path).resolve(strict=False)
    if resolved_in == resolved_out:
        raise SelfOverwriteRefused(
            f"Input and output resolve to the same path: {resolved_in}. "
            "Self-overwrite is refused to prevent data loss.",
            code=6,
            error_type="SelfOverwriteRefused",
            details={"input": str(resolved_in), "output": str(resolved_out)},
        )


def _read_stdin_capped(max_bytes: int = 16 * 1024 * 1024) -> bytes:
    """Read up to max_bytes from stdin.buffer; raise InsertSourceTooLarge if exceeded."""
    data = sys.stdin.buffer.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InsertSourceTooLarge(
            f"Insert source from stdin exceeds the {max_bytes}-byte cap "
            f"(read at least {len(data)} bytes).",
            code=2,
            error_type="InsertSourceTooLarge",
            details={"max_bytes": max_bytes, "actual_bytes_min": len(data)},
        )
    return data


@contextlib.contextmanager
def _tempdir(prefix: str = "docx_replace-") -> Iterator[Path]:
    """Context manager: temporary directory as a Path, cleaned up on exit."""
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        yield Path(tmp)


# ---------------------------------------------------------------------------
# docx-6.7: --scope filter (Task 007 [LIGHT])
# ---------------------------------------------------------------------------

_VALID_SCOPES = {"body", "headers", "footers", "footnotes", "endnotes", "all"}


def _parse_scope(raw: str) -> set[str]:
    """Parse --scope value: comma-separated, case-insensitive, dedup'd.

    Returns a set of role names matching the keys used by
    `_iter_searchable_parts` (`document`, `header`, `footer`,
    `footnotes`, `endnotes`). The CLI surface uses friendlier plurals
    (`body`, `headers`, `footers`) — this function maps them to the
    internal role names. `all` expands to the full set.

    Raises `_AppError(UsageError, code=2)` on invalid input.
    """
    items = {v.strip().lower() for v in raw.split(",") if v.strip()}
    if not items:
        raise _AppError(
            "--scope must specify at least one value",
            code=2, error_type="UsageError",
            details={"valid": sorted(_VALID_SCOPES)},
        )
    invalid = items - _VALID_SCOPES
    if invalid:
        raise _AppError(
            f"--scope: unknown value(s): {sorted(invalid)}",
            code=2, error_type="UsageError",
            details={"invalid": sorted(invalid),
                     "valid": sorted(_VALID_SCOPES)},
        )
    if "all" in items:
        items = _VALID_SCOPES - {"all"}
    # Map CLI plurals to internal role names used by _iter_searchable_parts.
    cli_to_role = {
        "body": "document",
        "headers": "header",
        "footers": "footer",
        "footnotes": "footnotes",
        "endnotes": "endnotes",
    }
    return {cli_to_role[v] for v in items}


# ---------------------------------------------------------------------------
# F8: post-validate hook
# ---------------------------------------------------------------------------

def _post_validate_enabled() -> bool:
    """True if DOCX_REPLACE_POST_VALIDATE env-var is in the truthy
    allowlist {1, true, yes, on} (case-insensitive). R9.d lock."""
    raw = os.environ.get("DOCX_REPLACE_POST_VALIDATE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _run_post_validate(output: Path, scripts_dir: Path) -> None:
    """subprocess.run([sys.executable, '-m', 'office.validate', OUTPUT]).
    Non-zero → unlink(output); raise PostValidateFailed (exit 7).

    Subprocess uses cwd=output.parent (known-clean tmpdir we own; Security
    follow-up post-VDD-Multi) + PYTHONPATH=scripts_dir so `office.validate`
    resolves from the codebase, not from whatever cwd the user invoked us
    in. Mitigates the MED-Security finding about a too-broad cwd."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(scripts_dir) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "office.validate", str(output)],
            shell=False, timeout=60, capture_output=True, text=True,
            cwd=str(output.parent),
            env=env,
        )
    except subprocess.TimeoutExpired:
        unlink_err = _try_unlink(output)
        details = {"output": str(output), "reason": "timeout"}
        if unlink_err is not None:
            details["unlink_error"] = unlink_err
        raise PostValidateFailed(
            f"Post-validate timeout (60s) on {output}",
            code=7, error_type="PostValidateFailed",
            details=details,
        )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "")[:8192]
        unlink_err = _try_unlink(output)
        details = {"output": str(output), "stderr": snippet,
                   "returncode": result.returncode}
        if unlink_err is not None:
            details["unlink_error"] = unlink_err
        raise PostValidateFailed(
            f"Post-validate failed on {output}",
            code=7, error_type="PostValidateFailed",
            details=details,
        )


def _try_unlink(path: Path) -> str | None:
    """Unlink `path` if it exists; return None on success or string error
    message on OSError (e.g. read-only fs, AV-locked file). Callers should
    propagate the error message into `_AppError.details["unlink_error"]`
    so a surviving corrupt artifact is surfaced to the caller rather than
    silently ignored (Logic-MED follow-up post-VDD-Multi)."""
    try:
        path.unlink(missing_ok=True)
        return None
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# F7: orchestrator
# ---------------------------------------------------------------------------

def _dispatch_action(
    args: argparse.Namespace,
    tree_root: Path,
    tmpdir: Path,
    scripts_dir: Path,
) -> tuple[int, str]:
    """Dispatch to the chosen action; return (count, summary)."""
    # docx-6.7: parse --scope once per invocation. Default "all" expands
    # to the full role set (back-compat: identical to v1 behavior).
    scope = _parse_scope(getattr(args, "scope", "all"))
    if args.replace is not None:
        count = _do_replace(
            tree_root, args.anchor, args.replace, anchor_all=args.all,
            scope=scope,
        )
        return count, (
            f"replaced {count} anchor(s) "
            f"(anchor={args.anchor!r} -> {args.replace!r})"
        )
    if args.insert_after is not None:
        base_has_numbering = (tree_root / "word" / "numbering.xml").is_file()
        if args.insert_after == "-":
            data = _read_stdin_capped()
            if not data.strip():
                raise EmptyInsertSource(
                    "Empty stdin for --insert-after",
                    code=2, error_type="EmptyInsertSource",
                    details={"source": "<stdin>"},
                )
            md_path = tmpdir / "stdin.md"
            md_path.write_bytes(data)
        else:
            md_path = Path(args.insert_after)
            if not md_path.is_file():
                raise FileNotFoundError(args.insert_after)
            if md_path.stat().st_size == 0:
                raise EmptyInsertSource(
                    f"Empty insert source: {md_path}",
                    code=2, error_type="EmptyInsertSource",
                    details={"source": str(md_path)},
                )
        insert_docx = _materialise_md_source(md_path, scripts_dir, tmpdir)
        insert_tree_root = tmpdir / "insert_unpacked"
        insert_tree_root.mkdir()
        unpack(insert_docx, insert_tree_root)
        insert_paragraphs = _extract_insert_paragraphs(
            insert_tree_root, base_has_numbering=base_has_numbering,
        )
        count = _do_insert_after(
            tree_root, args.anchor, insert_paragraphs,
            anchor_all=args.all, scope=scope,
        )
        return count, (
            f"inserted {len(insert_paragraphs)} paragraph(s) after "
            f"anchor {args.anchor!r} ({count} match(es))"
        )
    if args.delete_paragraph:
        count = _do_delete_paragraph(
            tree_root, args.anchor, anchor_all=args.all, scope=scope,
        )
        return count, (
            f"deleted {count} paragraph(s) (anchor={args.anchor!r})"
        )
    raise _AppError(
        "No action specified",
        code=2, error_type="UsageError",
        details={"prog": "docx_replace.py"},
    )


def _run_library_mode(
    args: argparse.Namespace, tree_root: Path, scripts_dir: Path,
) -> int:
    """Library-mode entry: caller owns the unpacked tree.

    Cross-cutting checks (cross-7/3/4) are SKIPPED; no pack; no
    post-validate. The tree is mutated in place.
    """
    with _tempdir() as tmpdir:
        count, action_summary = _dispatch_action(
            args, tree_root, tmpdir, scripts_dir,
        )
        if count == 0:
            raise AnchorNotFound(
                f"Anchor not found: {args.anchor!r}",
                code=2, error_type="AnchorNotFound",
                details={"anchor": args.anchor},
            )
        print(
            f"<unpacked>: {action_summary}",
            file=sys.stderr,
        )
        return 0


def _run(args: argparse.Namespace) -> int:
    """Full zip-mode pipeline."""
    scripts_dir = Path(__file__).resolve().parent

    # Universal anchor validation — applies to both zip and library mode.
    # Empty anchor causes infinite loops in _replace_in_run and matches
    # every paragraph in _find_paragraphs_containing_anchor (DoS / silent
    # corruption). Reject before any I/O is attempted.
    if args.anchor is None or not args.anchor:
        raise _AppError(
            "--anchor must be a non-empty string",
            code=2, error_type="UsageError",
            details={"anchor": args.anchor},
        )

    # docx-6.7: validate --scope EARLY so bad values fail before any I/O
    # (otherwise the user sees `Not a ZIP-based OOXML container` after a
    # fruitless unpack attempt). The parsed set is discarded here and
    # re-parsed inside _dispatch_action; cost is negligible and avoids
    # threading the parsed set through library-mode / _dispatch.
    _parse_scope(getattr(args, "scope", "all"))

    # Step 1: Library-mode dispatch (FIRST per ARCH §F7 MAJ-1 fix).
    if args.unpacked_dir is not None:
        if args.input is not None or args.output is not None:
            raise _AppError(
                "Cannot combine --unpacked-dir with INPUT/OUTPUT positionals",
                code=2, error_type="UsageError",
                details={"prog": "docx_replace.py"},
            )
        tree_root = Path(args.unpacked_dir).resolve(strict=False)
        if not (tree_root / "word" / "document.xml").is_file():
            raise NotADocxTree(
                f"Not a docx tree: {tree_root}",
                code=1, error_type="NotADocxTree",
                details={"dir": str(tree_root)},
            )
        return _run_library_mode(args, tree_root, scripts_dir)

    # Step 2: require positional args for zip-mode (library mode handled above).
    if args.input is None or args.output is None:
        raise _AppError(
            "INPUT and OUTPUT positional args are required (or use --unpacked-dir)",
            code=2, error_type="UsageError",
        )

    input_path = Path(args.input)
    output_path = Path(args.output)

    # Step 3: cross-7 same-path guard.
    _assert_distinct_paths(input_path, output_path)
    # Step 4: cross-3 encryption check.
    assert_not_encrypted(input_path)
    # Step 5: cross-4 macro warning.
    warn_if_macros_will_be_dropped(input_path, output_path, sys.stderr)
    # Step 6: unpack → dispatch → pack → post-validate → atomic move.
    with _tempdir() as tmpdir:
        unpack(input_path, tmpdir)
        tree_root = tmpdir
        count, action_summary = _dispatch_action(args, tree_root, tmpdir, scripts_dir)
        if count == 0:
            raise AnchorNotFound(
                f"Anchor not found: {args.anchor!r}",
                code=2, error_type="AnchorNotFound",
                details={"anchor": args.anchor},
            )
        # Step 7: pack to a tmp path inside tmpdir (not the final output)
        # to close the unlink-race window between pack and post-validate.
        tmp_out = tmpdir / "packed.docx"
        pack(tree_root, tmp_out)
        # Step 8: opt-in post-validate (operates on tmp file).
        if _post_validate_enabled():
            _run_post_validate(tmp_out, scripts_dir)
        # Step 9: atomic move to final destination; symlink-safe.
        # On Linux, os.replace raises EXDEV (errno 18) when tmpdir and the
        # output path are on different filesystem mounts (e.g. /tmp on tmpfs,
        # output on /home/runner or an NFS mount in CI).  Fall back to
        # shutil.move which handles cross-fs via copy+delete.  This loses
        # atomicity on the cross-fs path (the copy window is ~ms), but the
        # alternative is a hard failure — acceptable per FIX-6 follow-up.
        try:
            os.replace(str(tmp_out), str(output_path))
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                # Cross-filesystem: tmpdir on tmpfs, output on a different mount.
                shutil.move(str(tmp_out), str(output_path))
            else:
                raise
        # Step 10: success summary.
        print(f"{output_path.name}: {action_summary}", file=sys.stderr)
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for docx_replace.py.

    Honest-scope notes in help text (R8.j):
      single-run anchor only | image r:embed not wired | last paragraph
      deletion refused | blast-radius warning for --all --delete-paragraph
    """
    parser = argparse.ArgumentParser(
        prog="docx_replace.py",
        description=(
            "Replace, insert after, or delete paragraphs in .docx files.\n\n"
            "Honest scope:\n"
            "  * Anchor matching is single-run only. A phrase that spans a "
            "formatting boundary will not be found.\n"
            "  * --insert-after: any image in the Markdown source appears as "
            "a broken reference (no live r:embed wired).\n"
            "  * --delete-paragraph refuses to remove the last paragraph "
            "from <w:body>.\n"
            "  * --all --delete-paragraph on a common word is a large "
            "blast-radius operation — verify the anchor is specific first."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input", nargs="?", default=None, metavar="INPUT",
        help="Source .docx/.docm path (omit when --unpacked-dir is set in 006-07b).",
    )
    parser.add_argument(
        "output", nargs="?", default=None, metavar="OUTPUT",
        help="Destination .docx path (omit when --unpacked-dir is set in 006-07b).",
    )
    parser.add_argument("--anchor", metavar="TEXT",
                        help="Anchor text to search for in document paragraphs.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--replace", metavar="TEXT",
                        help="Replace anchor with TEXT (empty string removes anchor).")
    action.add_argument("--insert-after", metavar="SOURCE",
                        help="Insert paragraphs from SOURCE (file or '-' for stdin) after anchor.")
    action.add_argument("--delete-paragraph", action="store_true", default=False,
                        help="Delete every paragraph containing the anchor text.")
    parser.add_argument("--all", action="store_true", default=False,
                        help="Apply action to all matching paragraphs (default: first only).")
    parser.add_argument("--unpacked-dir", metavar="DIR", type=Path, default=None,
                        help="Library mode: operate on an unpacked OOXML tree (UC-4; task-006-07b).")
    parser.add_argument(
        "--scope", metavar="LIST", default="all",
        help=("Comma-separated parts to search: "
              "body, headers, footers, footnotes, endnotes, all "
              "(default: all). Example: --scope=body,headers to skip "
              "notes; --scope=body to limit edits to word/document.xml. "
              "Order within the requested set is preserved (document → "
              "headers → footers → footnotes → endnotes). [docx-6.7]"),
    )
    add_json_errors_argument(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint — returns the integer exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2
    je = getattr(args, "json_errors", False)
    try:
        return _run(args)
    except _AppError as exc:
        return report_error(exc.message, code=exc.code, error_type=exc.error_type,
                            details=exc.details, json_mode=je)
    except EncryptedFileError as exc:
        return report_error(str(exc), code=3, error_type="EncryptedFileError", json_mode=je)
    except NotImplementedError as exc:
        return report_error(str(exc), code=1, error_type="NotImplemented",
                            details={"stub": True}, json_mode=je)
    except FileNotFoundError as exc:
        return report_error(str(exc), code=1, error_type="FileNotFound", json_mode=je)
    except OSError as exc:
        return report_error(str(exc), code=1, error_type="IOError", json_mode=je)
    except Exception as exc:
        return report_error(
            f"Unexpected internal error: {type(exc).__name__}: {exc}",
            code=1, error_type="InternalError",
            details={"exc_type": type(exc).__name__},
            json_mode=je,
        )


if __name__ == "__main__":
    sys.exit(main())
