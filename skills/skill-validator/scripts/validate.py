"""Skill Validator: Security & Compliance Audit.

Main entry point that orchestrates structure checks, bash scanning,
static analysis, and Base64 payload inspection in a single file pass.
"""
import atexit
import codecs
import sys
import os
import argparse
import json

# Add current directory to path so we can import scanners
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from scanners import structure_check, bash_scanner, static_analyzer, ai_scanner
except ImportError as e:
    # Defer error reporting until we know the output format
    _import_error = str(e)
    structure_check = None
    bash_scanner = None
    static_analyzer = None
    ai_scanner = None
else:
    _import_error = None

# Version must match SKILL.md frontmatter
VERSION = "1.3"

# Binary file extensions to skip during scanning
BINARY_EXTENSIONS = frozenset((
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.bmp', '.webp',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.pyc', '.pyo', '.so', '.dylib', '.dll',
))

# Maximum file size to scan (10 MB). Files larger than this are skipped.
MAX_FILE_SIZE = 10 * 1024 * 1024

# P6: Magic number signatures for polyglot detection.
# Maps binary magic bytes to their file type description.
MAGIC_SIGNATURES = {
    b'\x7fELF':      'ELF executable',
    b'MZ':           'PE/Windows executable',
    b'\xfe\xed\xfa': 'Mach-O binary',
    b'\xcf\xfa\xed': 'Mach-O 64-bit binary',
    b'PK':           'ZIP archive',
    b'\x1f\x8b':     'GZIP compressed',
    b'\x89PNG':      'PNG image',
    b'\xff\xd8\xff': 'JPEG image',
    b'GIF8':         'GIF image',
    b'%PDF':         'PDF document',
}

# Extensions that should contain text, not binary data
TEXT_EXTENSIONS = frozenset((
    '.py', '.sh', '.bash', '.js', '.ts', '.rb', '.pl',
    '.md', '.txt', '.yml', '.yaml', '.json', '.toml',
    '.html', '.css', '.xml', '.csv', '.cfg', '.ini',
))


def check_polyglot(file_path, rel_path):
    """Check if a text-extension file has a binary magic number (polyglot attack)."""
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in TEXT_EXTENSIONS:
        return []

    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
    except Exception:
        return []

    for magic, description in MAGIC_SIGNATURES.items():
        if header.startswith(magic):
            return [{
                "type": "critical",
                "message": f"Polyglot file detected: {rel_path} has text extension but contains {description} magic bytes",
            }]
    return []


def print_result(result):
    """Print a single issue with color-coded severity prefix."""
    type_color = {
        "critical": "\033[91m[CRITICAL]\033[0m",
        "error":    "\033[91m[ERROR]\033[0m",
        "warning":  "\033[93m[WARNING]\033[0m",
        "info":     "\033[94m[INFO]\033[0m",
    }
    prefix = type_color.get(result.get("type", "info"), "[UNKNOWN]")
    print(f"{prefix} {result.get('message')}")
    if "line" in result:
        print(f"    Line: {result['line']}")


def load_scanignore(skill_path, honor_scanignore):
    """Load .scanignore file and return a set of relative paths to skip.

    Args:
        skill_path: Path to skill directory.
        honor_scanignore: If False, .scanignore is ignored entirely.

    Returns:
        Set of relative paths to exclude from content scanning.
    """
    if not honor_scanignore:
        return set()

    ignore_path = os.path.join(skill_path, ".scanignore")
    ignored = set()
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignored.add(line)
        except Exception as e:
            # M3: Report the error instead of swallowing it
            print(f"\033[93m[WARNING] Could not read .scanignore: {e}\033[0m",
                  file=sys.stderr)
    return ignored


def walk_and_scan(skill_path, honor_scanignore, enable_ai_scan=False):
    """Single os.walk pass that feeds each file to all scanners.

    Respects .scanignore only when honor_scanignore is True.
    Enforces MAX_FILE_SIZE limit per file.

    Returns:
        List of issue dicts from bash_scanner, static_analyzer, and optionally ai_scanner.
    """
    ignored_paths = load_scanignore(skill_path, honor_scanignore)
    all_issues = []
    for root, dirs, files in os.walk(skill_path):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, skill_path)

            # Skip files listed in .scanignore
            if rel_path in ignored_paths:
                continue

            # Skip binary files by extension
            _, ext = os.path.splitext(filename)
            if ext.lower() in BINARY_EXTENSIONS:
                continue

            # M1: Skip oversized files to prevent OOM
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                file_size = 0
            if file_size > MAX_FILE_SIZE:
                all_issues.append({
                    "type": "warning",
                    "message": f"Skipped oversized file ({file_size // 1024 // 1024}MB): {rel_path}",
                })
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                all_issues.append({
                    "type": "error",
                    "message": f"Unreadable file: {rel_path}: {e}",
                })
                continue

            # P6: Check for polyglot files (magic number vs text extension)
            all_issues.extend(check_polyglot(file_path, rel_path))

            # Feed content to scanners
            all_issues.extend(bash_scanner.scan_file_content(content, rel_path))
            all_issues.extend(static_analyzer.scan_file_content(content, rel_path))
            
            if enable_ai_scan:
                all_issues.extend(ai_scanner.scan_file_content(content, rel_path))

    return all_issues


def compute_risk_level(issues):
    """Compute a risk level based on the scan results.

    Returns:
        A string: "SAFE", "CAUTION", or "DANGER".
        SAFE    = no critical/error issues, scanner coverage was complete.
        CAUTION = errors (e.g., unreadable files) but no critical threats.
        DANGER  = critical security issues detected.
    """
    has_critical = any(i.get("type") == "critical" for i in issues)
    has_error = any(i.get("type") == "error" for i in issues)
    if has_critical:
        return "DANGER"
    if has_error:
        return "CAUTION"
    return "SAFE"


# ---------------------------------------------------------------------------
# stdout JSON channel
#
# Duplicated verbatim in the sibling tooling skills (skill-creator and
# skill-enhancer carry it in their own `skill_utils.py`, skill-validator in
# `validate.py`, skill-auto-improve in `common.py`). The duplication is
# deliberate: each skill must be installable and runnable in isolation,
# including as a packaged `.skill` archive, so no skill imports a helper from
# another. There is no diff -q gate on these copies -- unlike the office
# skills' `_errors.py`, they are not a declared replication unit.
# ---------------------------------------------------------------------------

def abandon_stdout():
    """Point a dead stdout's file descriptor at os.devnull. Best effort.

    Call this after a BrokenPipeError. Without it the interpreter flushes the
    same dead fd again while shutting down: it prints "Exception ignored while
    flushing sys.stdout" on stderr and **replaces the exit status with 120**,
    so the process contradicts the verdict it just returned. A stream with no
    real fd (a test's StringIO, a wrapper's proxy object) has nothing to
    redirect and needs nothing, hence the swallowed exceptions.
    """
    try:
        fd = sys.stdout.fileno()
    except (OSError, ValueError, AttributeError):
        return
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        os.dup2(devnull, fd)
    except OSError:
        pass
    finally:
        os.close(devnull)


def emit_text(text):
    """Write `text` plus a newline to stdout and flush, surviving a dead pipe.

    Returns True when the line reached stdout, False when the sink was already
    gone. See `emit_json` for the two failure modes this exists to close; this
    is the same contract for a stdout payload that is not JSON (e.g. a bare
    digest).
    """
    if sys.stdout is None:
        return False
    line = text + "\n"
    # No degradation here. This helper's contract is "the line reached stdout",
    # and a non-ASCII character used to break it by raising rather than by
    # returning False -- but the repair belongs to the stream, not to every
    # writer: `install_human_channel()` puts the ASCII-fallback handler on
    # stdout once, and every write in the process inherits it.
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except BrokenPipeError:
        abandon_stdout()
        return False
    return True


def emit_json(payload, indent=2):
    """Write `payload` to stdout as one JSON document, then flush.

    Replaces `print(json.dumps(payload, indent=2))`, which has two measured
    failure modes.

    **A reader that is already gone.** Payload size is not the gate: a reader
    that disappeared before the write raises EPIPE for a 65-byte document just
    as readily as for a 500 KB one (measured on CPython 3.14.4 / macOS: the
    immutability gate's 83-byte `{"ok": ..., "reason": ...}` line, written into
    a pipe whose read end was already closed, turned `return 1` into exit 120).
    Size only decides *which way* a bare `print()` fails. Measured on this
    machine, with the reader gone before the write: at 131_071 payload bytes
    and below the text stays in `sys.stdout`'s buffer, `print()` returns
    normally, and only the interpreter's shutdown flush hits the dead fd --
    which prints "Exception ignored while flushing sys.stdout" on stderr and
    replaces the exit status with 120; at 131_072 bytes and above the write
    itself raises and the traceback escapes with exit 1. Both land in
    `emit_text`'s `except` arm, where `abandon_stdout()` leaves the shutdown
    flush nothing to fail on, so the caller's own exit code survives.

    (A reader that is merely *slow* rather than gone -- `... | head -c 20` --
    reaches those same two modes, but only once the document outgrows the
    ~64 KB pipe buffer. That is why the tests use the already-gone reader: it
    takes payload size out of the contract, so a shrinking fixture cannot turn
    a real regression green.)

    **fd 1 closed before the process started** (`prog >&-`): CPython sets
    `sys.stdout` to None and makes `print()` a silent no-op, so the caller sees
    exit 0 and no document. Detected here and reported through the return value
    rather than raising AttributeError.

    `json.dumps` runs to completion before anything is written, so a reader
    gets a whole document or none of it, never one truncated mid-serialization.

    `ensure_ascii` keeps its default, so the document is pure ASCII and the
    text layer's codec (`PYTHONIOENCODING`, then the process locale) can
    neither alter these bytes nor abort mid-write on them. A caller that needs
    non-ASCII output must move to a byte-level write (as
    `_errors.write_json_stdout` does in the office skills), not merely flip
    `ensure_ascii`.

    Returns True when the document reached stdout, False when the sink was
    already gone. The caller's exit path runs unchanged either way.
    """
    return emit_text(json.dumps(payload, indent=indent))


def main():
    install_human_channel()
    parser = argparse.ArgumentParser(description="Skill Validator: Security & Compliance Audit")
    parser.add_argument("skill_path", help="Path to the skill directory to validate")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--version", action="version", version=f"skill-validator {VERSION}")
    parser.add_argument(
        "--no-scanignore", action="store_true",
        help="Ignore .scanignore files (recommended for untrusted skills)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit with code 2 if warnings are found (useful for CI/CD)",
    )
    parser.add_argument(
        "--ai-scan", action="store_true",
        help="Enable AI threat detection (prompt injection, jailbreaks)",
    )
    args = parser.parse_args()

    # Handle import errors in the correct output format
    if _import_error:
        err = {"type": "error", "message": f"Scanner import failed: {_import_error}"}
        if args.json:
            emit_json({"error": err})
        else:
            print(f"\033[91m[ERROR] {err['message']}\033[0m")
        sys.exit(1)

    skill_path = os.path.abspath(args.skill_path)
    if not os.path.isdir(skill_path):
        err = {"type": "error", "message": f"Directory not found: {skill_path}"}
        if args.json:
            emit_json({"error": err})
        else:
            print(f"\033[91m[ERROR] {err['message']}\033[0m")
        sys.exit(1)

    all_issues = []

    # 1. Structure Check
    all_issues.extend(structure_check.check_structure(skill_path))

    # 2. Single-pass file scanning (bash + static analysis + optional AI scan)
    # .scanignore from the scanned skill is honored by default.
    # Use --no-scanignore to disable it when scanning untrusted skills.
    honor_scanignore = not args.no_scanignore
    all_issues.extend(walk_and_scan(skill_path, honor_scanignore, args.ai_scan))

    # 3. Compute risk level
    risk_level = compute_risk_level(all_issues)

    critical_count = len([i for i in all_issues if i.get("type") == "critical"])

    error_count = len([i for i in all_issues if i.get("type") == "error"])
    warning_count = len([i for i in all_issues if i.get("type") == "warning"])
    info_count = len([i for i in all_issues if i.get("type") == "info"])

    if args.json:
        output = {
            "skill": os.path.basename(skill_path),
            "risk_level": risk_level,
            "issues": all_issues,
            "summary": {
                "critical": critical_count,
                "error": error_count,
                "warning": warning_count,
                "info": info_count,
            },
        }
        emit_json(output)
    else:
        print(f"\n==========================================")
        print(f"Skill Validator Report for: {os.path.basename(skill_path)}")
        print(f"Risk Level: {risk_level}")
        print(f"==========================================")

        if not all_issues:
            print("\n\033[92m[SUCCESS] No issues found!\033[0m")
            sys.exit(0)  # L2: Early exit for clean path

        sorted_issues = sorted(
            all_issues,
            key=lambda x: {"critical": 0, "error": 1, "warning": 2, "info": 3}.get(
                x.get("type", "info"), 4
            ),
        )
        for issue in sorted_issues:
            print_result(issue)

        print(f"\nSummary: {critical_count} Critical, {error_count} Errors, "
              f"{warning_count} Warnings, {info_count} Info")

        if critical_count > 0:
            print("\033[91mFAILED: Critical security issues detected.\033[0m")
            sys.exit(1)
        elif error_count > 0:
            print("\033[91mFAILED: Structural errors detected.\033[0m")
            sys.exit(1)
        elif warning_count > 0 and args.strict:
            print("\033[93mFAILED (strict): Warnings treated as errors.\033[0m")
            sys.exit(2)  # L3: Distinct exit code for warnings in strict mode
        else:
            print("\033[93mPASSED with Warnings.\033[0m" if warning_count > 0
                  else "\033[92mPASSED.\033[0m")

    sys.exit(0)


# --------------------------------------------------------------------- #
# The HUMAN channel — reports, progress, --help
# --------------------------------------------------------------------- #
#
# The machine helpers above must ignore the caller's locale: JSON is UTF-8 by
# RFC 8259 §8.1. Prose is the opposite — it must OBEY the caller's codec,
# because UTF-8 written into a terminal that declared cp1252 is mojibake, not
# robustness.
#
# Until this existed it obeyed by dying. stderr is opened
# errors="backslashreplace" and survives; stdout gets "surrogateescape" (or
# "strict" under an explicit PYTHONIOENCODING), and NEITHER can represent an
# em dash — surrogateescape rescues lone surrogates and nothing else. So one
# `—` or `✓` in a report, or in an argparse `help=` string, took the whole
# command down.
#
# The fix belongs to the STREAM, not to the call sites. `codecs.register_error`
# is the documented extension point for exactly this question — "what should
# happen to a character this codec cannot represent?" — and once the handler
# is on stdout it covers `print`, argparse's own `file.write`, a bare
# `sys.stdout.write` deep inside a renderer, and any third-party write in the
# same process. Nothing to remember at the call site, because there is no call
# site to remember.
#
# The first version of this fix did the opposite: a `say()` wrapper, a
# `HumanArgumentParser` subclass and a stream shim, ~157 lines copied into
# every skill, with every `print` rewritten to match. It worked, and it was
# the wrong shape — mutation testing showed a forgotten `print` still slipped
# through, and the duplicated block was mechanism rather than data. What is
# left below is data (the table) plus fifteen lines that hand it to CPython.
#
# Issue: docs/issues/human-cli-output-locale-class.md.

#: Name under which the handler is registered process-wide. Also usable as an
#: `errors=` argument anywhere: `text.encode("ascii", HUMAN_ERRORS)` gives
#: exactly what a report would look like under that codec, which is how the
#: tests state their expectations without restating the table.
HUMAN_ERRORS = "human_channel.asciify"

#: ASCII spellings for the decoration these reports print. A FALLBACK table,
#: not a transliterator: consulted only for characters the caller's codec has
#: already rejected, and anything missing from it degrades to a
#: `backslashreplace` escape rather than being dropped.
_ASCII_FALLBACK = {
    "—": "--", "–": "-", "…": "...", "→": "->", "←": "<-",
    "✓": "+", "✔": "+", "✗": "x", "✘": "x", "×": "x",
    "⚠": "!", "❌": "x", "✅": "+", "❗": "!", "•": "*", "§": "S",
    "±": "+/-", "≥": ">=", "≤": "<=", "≠": "!=", "°": " deg",
    "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
    # U+FE0F / U+FE0E only select an emoji's presentation; they carry no
    # meaning of their own. `⚠️` is U+26A0 U+FE0F, so mapping just the base
    # glyph left the selector behind and the report read `!️`. Dropping
    # them is the whole fix — the base character already says it.
    "️": "", "︎": "",
}


def _asciify(exc):
    """Spell an unencodable run in ASCII instead of letting it kill the write.

    The codec calls this once per unencodable RUN, not once per character:
    `exc.object[exc.start:exc.end]` can be several characters long, hence the
    loop. Degradation stays per character so a codec keeps everything it can
    carry — under cp1251 `доклад — ✓` keeps the Cyrillic AND the em dash and
    only the check mark moves.

    Anything the table does not know falls back to `backslashreplace`, which
    is what stderr has always done and precisely why stderr never crashed.

    Re-raises anything that is not an encode error. A decode error reaching
    here would mean the handler was installed on a readable stream, where
    guessing would corrupt input rather than tidy output.
    """
    if not isinstance(exc, UnicodeEncodeError):
        raise exc
    spelled = []
    for ch in exc.object[exc.start:exc.end]:
        replacement = _ASCII_FALLBACK.get(ch)
        if replacement is None:
            # Escaped against ASCII, NOT against `exc.encoding`. For every
            # charmap codec -- cp1251, cp1252, latin-1, cp850, cp932 -- the
            # exception reports `exc.encoding == "charmap"`, the literal
            # string, not the codec's name. Re-encoding through *that* does
            # not raise: the bare `charmap` codec falls back to Latin-1 and
            # hands back the RAW BYTE, so `é` came out of cp1251 as b"\xe9"
            # and the following decode blew up. ASCII escapes are also the
            # only universally safe answer -- the character is here precisely
            # because the caller's codec rejected it.
            replacement = ch.encode("ascii", "backslashreplace").decode("ascii")
        spelled.append(replacement)
    return "".join(spelled), exc.end


codecs.register_error(HUMAN_ERRORS, _asciify)


def _quiet_a_dead_stdout():
    """Drain stdout at exit, and if it is already gone, point fd 1 at devnull.

    Registered by `install_human_channel`, and the second half of the exit-code
    contract. `line_buffering` makes the CLI's own `except BrokenPipeError`
    handler see the failure and return its verdict — but the interpreter then
    flushes the SAME dead fd again during finalization, prints "Exception
    ignored while flushing sys.stdout" on stderr, and replaces that verdict
    with 120. Measured: `install_components.py` with no reader at all printed
    its own broken-pipe line, returned 1, and exited 120.

    atexit callbacks run before that final flush, so draining here leaves it
    nothing to fail on. A stream with no real fd (a test's StringIO) has
    nothing to redirect and needs nothing, hence the swallowed exceptions.
    """
    try:
        sys.stdout.flush()
    except (BrokenPipeError, ValueError, OSError):
        try:
            fd = sys.stdout.fileno()
        except (OSError, ValueError, AttributeError):
            return
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
        except OSError:
            return
        try:
            os.dup2(devnull, fd)
        finally:
            os.close(devnull)
    except AttributeError:
        pass


def install_human_channel(*streams):
    """Point stdout's and stderr's error handler at `_asciify`.

    Call once, early in `main()` — NOT at import. Registering the handler
    above is inert, but `reconfigure` mutates a process-wide stream, and a
    module that does that on import imposes it on everything that merely
    imports the module.

    stderr is included even though it never crashed: its `backslashreplace`
    turns an em dash into the six characters `\\u2014`, and `--` is strictly
    better for the same cost.

    `line_buffering` is set for a second, unrelated reason, and it matters:
    piped stdout is BLOCK-buffered, so `report | head` surfaces the dead reader
    during interpreter shutdown, where CPython prints "Exception ignored while
    flushing sys.stdout" and **replaces the exit status with 120** — a command
    contradicting the verdict it just gave. Line-buffered, the write itself
    raises BrokenPipeError inside `main()`, where the CLI's own handler sees
    it. This also just restores the behaviour stdout already has on a terminal;
    only redirection took it away.

    Failure is silent by design. A replaced stdout — a test's `StringIO`, a
    capture proxy, `prog >&-` leaving `sys.stdout` as None — has no
    `reconfigure` to call, and none of that is a reason to fail a report.
    """
    if not streams:
        atexit.register(_quiet_a_dead_stdout)
    for stream in streams or (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors=HUMAN_ERRORS, line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass


if __name__ == "__main__":
    main()

