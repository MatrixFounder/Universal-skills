#!/usr/bin/env python3
"""Shared contracts and helpers for skill-auto-improve.

This module is the single source of truth for the data contracts that flow
between the orchestrator, the Proposer, the Evaluator, and the deterministic
utility scripts. Keeping them here prevents drift between independently
written components.

Self-contained: no runtime imports from sibling skills (skill-creator etc.).
The skill must be installable/runnable in isolation, including as a packaged
.skill archive.
"""

from __future__ import annotations

import argparse
import atexit
import codecs
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Iteration status constants (written to improvement_history.tsv `status`)
# ---------------------------------------------------------------------------
STATUS_BASELINE = "baseline"
STATUS_KEEP = "keep"
STATUS_REVERT = "revert"
STATUS_NO_SIGNAL = "no-signal"          # |Δ| <= σ → treated as REVERT (no drift)
STATUS_NO_CHANGE = "no-change"          # Proposer produced empty/invalid diff
STATUS_IMMUTABILITY = "immutability-violation"
STATUS_ERROR = "error"

# Artifact types
ARTIFACT_SKILL = "skill"
ARTIFACT_PROMPT = "prompt"
ARTIFACT_WORKFLOW = "workflow"
ARTIFACT_DATASET = "dataset"
ARTIFACT_FULL_SKILL = "full-skill"
ARTIFACT_TEXT = "text"  # arbitrary text improved against a quality rubric (0-100)
ARTIFACT_TYPES = (
    ARTIFACT_SKILL,
    ARTIFACT_PROMPT,
    ARTIFACT_WORKFLOW,
    ARTIFACT_DATASET,
    ARTIFACT_FULL_SKILL,
    ARTIFACT_TEXT,
)

# Proposal diff formats. NOTE: a raw `unified-diff` format was intentionally
# REMOVED — applying attacker-controlled diffs via `git apply --unsafe-paths` /
# `patch -p0` let a Proposal escape the artifact scope and tamper with the
# (immutable) eval harness. All edits are now scoped, structured operations.
DIFF_SECTION_REPLACE = "section-replace"   # replace one `## Header` section body
DIFF_DATASET_OP = "dataset-op"             # structured ops on evals.json
DIFF_FRONTMATTER_FIELD = "frontmatter-field"  # set one mutable frontmatter field (e.g. description)
DIFF_TEXT_REPLACE = "text-replace"         # scoped find/replace within the artifact (prose)
ALLOWED_DIFF_FORMATS = (
    DIFF_SECTION_REPLACE, DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_TEXT_REPLACE,
)

# Frontmatter fields the loop is allowed to change (description/version only).
MUTABLE_FRONTMATTER_FIELDS = ("description", "version")

# Dataset shape vocabulary — kept in ONE place so the scorer, the immutability
# gate, and the apply step cannot drift on which wrapper key / immutable fields
# they recognize.
DATASET_WRAPPER_KEYS = ("evals", "results", "cases")
DATASET_IMMUTABLE_FIELDS = ("id", "skill_name", "grader")
DATASET_REF_FIELDS = ("files", "file", "fixtures")


def resolve_dataset_items(data):
    """Return (items_list, wrapper_key) for a dataset document.

    For a top-level list, wrapper_key is None. For a dict, returns the first
    recognized wrapper key's list (live reference, mutable in place). If a dict
    has no recognized key, returns ([], None) — callers that ADD must then
    create the canonical 'evals' key rather than mutating an orphan list.
    """
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in DATASET_WRAPPER_KEYS:
            if isinstance(data.get(key), list):
                return data[key], key
    return [], None

# Tiers (deterministically derived from change size; NOT chosen by the Proposer)
TIER_TRIVIAL = "trivial"
TIER_SMALL = "small"
TIER_MEDIUM = "medium"
TIER_LARGE = "large"


class ProposalError(ValueError):
    """Raised when a Proposer payload is structurally invalid."""


# ---------------------------------------------------------------------------
# Frontmatter / SKILL.md parsing (vendored — no dependency on skill-creator)
# ---------------------------------------------------------------------------
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown document into (frontmatter_block, body).

    Returns ("", text) when no frontmatter fence is present. The frontmatter
    block is the raw YAML text between the leading `---` fences.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal, dependency-free YAML-ish frontmatter parser.

    Handles the flat `key: value` pairs that SKILL.md frontmatter uses
    (name, description, tier, version). Values keep their raw string form;
    surrounding quotes are stripped. Block scalars and nested maps are not
    supported here — frontmatter for skills is intentionally flat.
    """
    block, _ = split_frontmatter(text)
    result: dict[str, str] = {}
    if not block:
        return result
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip a single trailing inline comment only when unquoted.
        if value and value[0] not in "\"'" and " #" in value:
            value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            quote = value[0]
            value = value[1:-1]
            # Symmetric with set_frontmatter_field: double-quoted scalars
            # escape \\ and \"; single-quoted scalars double embedded quotes.
            if quote == '"':
                value = _unescape_double(value)
            else:
                value = value.replace("''", "'")
        result[key] = value
    return result


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_injection_markup(text: str) -> str:
    """Remove HTML comments + control chars but PRESERVE whitespace/newlines.

    Used when the text's own formatting matters (e.g. prose fed to a quality
    judge — collapsing newlines would corrupt what is being judged). Defangs the
    obvious comment/control injection vector without altering visible structure.
    """
    return _CONTROL_RE.sub("", _HTML_COMMENT_RE.sub(" ", text))


def sanitize_injectable_value(value: str) -> str:
    """Defang a value embedded into an agent-readable context AND collapse to a
    single line (for short scalar fields like a skill `description`).

    The description is later written into a `claude -p` command file and read by
    a tool-enabled agent, so a Proposer (steerable by a poisoned artifact body)
    could smuggle instructions via HTML comments or control characters. Strip
    those and collapse to one line. This is data, not instructions.
    """
    return " ".join(strip_injection_markup(value).split())


def _unescape_double(text: str) -> str:
    """Reverse the \\ and \" escaping used for double-quoted scalars."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in '"\\':
            out.append(text[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_skill_md(skill_dir: Path) -> tuple[str, str, str]:
    """Return (name, description, body) for a SKILL.md under skill_dir."""
    skill_md = Path(skill_dir) / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    _, body = split_frontmatter(text)
    return fm.get("name", ""), fm.get("description", ""), body


# ---------------------------------------------------------------------------
# Section addressing for `## Header` section-replacement edits
# ---------------------------------------------------------------------------
_H2_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def find_sections(body: str) -> list[dict[str, Any]]:
    """Index markdown sections by their `## ...` (level-2) headers.

    Returns a list of {header, level, start, body_start, end} where offsets are
    line indices into body.splitlines(keepends=True)-style reconstruction is
    avoided; we operate on the raw text via character offsets for fidelity.
    """
    lines = body.splitlines(keepends=True)
    headers: list[dict[str, Any]] = []
    offset = 0
    for line in lines:
        m = _H2_RE.match(line)
        if m and len(m.group(1)) == 2:
            headers.append({
                "header": line.strip(),
                "title": m.group(2).strip(),
                "char_start": offset,
            })
        offset += len(line)
    # Compute each section's end as the next level-2 header start, or EOF.
    sections: list[dict[str, Any]] = []
    for i, h in enumerate(headers):
        end = headers[i + 1]["char_start"] if i + 1 < len(headers) else len(body)
        sections.append({
            "header": h["header"],
            "title": h["title"],
            "char_start": h["char_start"],
            "char_end": end,
        })
    return sections


def _normalize_header(name: str) -> str:
    """Normalize a header for matching: strip leading #, whitespace, case."""
    return name.lstrip("#").strip().casefold()


def replace_section(body: str, target_header: str, new_section_text: str) -> str:
    """Replace the full text of the section whose header matches target_header.

    `target_header` may be given with or without leading `## `. The matched
    span runs from its header line up to (but excluding) the next level-2
    header. `new_section_text` MUST include its own header line. Raises
    KeyError if the section is not found, ValueError if ambiguous.
    """
    want = _normalize_header(target_header)
    sections = find_sections(body)
    matches = [s for s in sections if _normalize_header(s["header"]) == want]
    if not matches:
        raise KeyError(f"section not found: {target_header!r}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous section header: {target_header!r}")
    s = matches[0]
    return body[: s["char_start"]] + _ensure_trailing_newline(new_section_text) + body[s["char_end"]:]


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def apply_text_replace(content: str, find: str, replace: str) -> tuple[str | None, str]:
    """Scoped find/replace within an artifact's own text (prose improvement).

    Returns (new_content, how) on success or (None, reason) on failure — NEVER
    raises. Unlike a unified diff, this only mutates the artifact's own string
    content (no file paths, no scope escape). Two rungs:
      1. exact   — `find` occurs verbatim (replaced once)
      2. fuzzy-ws — whitespace-tolerant: runs of whitespace in `find` match any
                    whitespace run in `content` (handles LLM newline/spacing drift)
    """
    if not find:
        return None, "empty-find"
    if find in content:
        return content.replace(find, replace, 1), "exact"
    tokens = find.split()
    if tokens:
        pattern = re.compile(r"\s+".join(re.escape(t) for t in tokens))
        m = pattern.search(content)
        if m:
            return content[: m.start()] + replace + content[m.end():], "fuzzy-ws"
    return None, "not-found"


def set_frontmatter_field(text: str, field: str, value: str) -> str:
    """Return `text` with the frontmatter `field:` line set to `value`.

    Preserves all other frontmatter lines and the body. The value is written
    as a double-quoted scalar with inner quotes/newlines escaped, which is
    valid for the flat single-line fields skills use. Raises KeyError if there
    is no frontmatter block, or ValueError if the field is absent (we update
    in place rather than inventing fields).
    """
    block, body = split_frontmatter(text)
    if not block:
        raise KeyError("no frontmatter block to update")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    new_line = f'{field}: "{escaped}"'
    out_lines: list[str] = []
    found = False
    for line in block.splitlines():
        key = line.partition(":")[0].strip()
        if key == field and not found:
            out_lines.append(new_line)
            found = True
        else:
            out_lines.append(line)
    if not found:
        raise ValueError(f"frontmatter field not found: {field!r}")
    return f"---\n" + "\n".join(out_lines) + "\n---\n" + body


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

