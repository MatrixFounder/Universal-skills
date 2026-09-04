#!/usr/bin/env python3
import argparse
import atexit
import codecs
import os
import re
import sys
from pathlib import Path

# Constants for Paths
SKILL_ROOT = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_ROOT / "references"
STYLES_DIR = REFERENCES_DIR / "styles"
ASSETS_DIR = SKILL_ROOT / "assets"

GENRE_MAP = {
    # Objective / Neutral Modes (Use Wiki Patterns)
    "encyclopedic": "patterns_wiki.md",
    "academic": "patterns_wiki.md",
    "technical": "patterns_wiki.md",
    "journalistic": "patterns_wiki.md",
    "science": "patterns_wiki.md",

    # Subjective / Creative Modes (Use Creative Patterns)
    "blog": "patterns_creative.md",
    "social": "patterns_creative.md",
    "marketing": "patterns_creative.md",
    "corporate": "patterns_creative.md",
    "food": "patterns_creative.md",
    "crypto": "patterns_creative.md"
}

# Genre -> base role category
ROLE_MAP = {
    "encyclopedic": "encyclopedic",
    "academic": "encyclopedic",
    "technical": "encyclopedic",
    "journalistic": "encyclopedic",
    "science": "encyclopedic",
    "blog": "creative",
    "social": "creative",
    "marketing": "creative",
    "corporate": "creative",
    "food": "creative",
    "crypto": "crypto",
}

# Default intensity per genre
INTENSITY_DEFAULTS = {
    "marketing": "max",
    "social": "max",
    "blog": "high",
    "food": "high",
    "crypto": "high",
    "corporate": "medium",
    "journalistic": "medium",
    "encyclopedic": "medium",
    "academic": "medium",
    "technical": "low",
    "science": "medium",
}

# Which priority tags to include at each intensity level
INTENSITY_PRIORITIES = {
    "max":     {"A", "B", "C", "D"},
    "high":    {"A", "B", "C"},
    "medium":  {"A", "B"},
    "low":     {"A"},
    "minimal": {"A"},
}


def load_file(path):
    """Safely load a file content."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def filter_patterns_by_priority(text, allowed_priorities):
    """Filter pattern sections by priority tags.

    Each pattern section starts with '## ' and contains a `[X]` priority tag.
    Keeps only sections whose tag is in allowed_priorities.
    Also preserves any content before the first '## ' (header, legend, etc.).
    """
    # Split into sections by ## headers
    parts = re.split(r'(?=^## )', text, flags=re.MULTILINE)

    filtered = []
    for part in parts:
        # Content before the first ## (header/legend) -- always keep
        if not part.startswith("## "):
            filtered.append(part)
            continue

        # Extract priority tag like `[A]`, `[B]`, `[C]`, `[D]`
        tag_match = re.search(r'`\[([A-D])\]`', part)
        if tag_match:
            tag = tag_match.group(1)
            if tag in allowed_priorities:
                filtered.append(part)
        else:
            # No tag found -- include by default (safety)
            filtered.append(part)

    return "".join(filtered)


#: A template block that belongs to some intensities only. The alternative --
#: one more bespoke regex per conditional section, like the two that strip
#: Diagnosis and Verification by mode -- multiplies special cases and hides the
#: condition inside this file instead of stating it beside the text it governs.
CONDITIONAL_BLOCK = re.compile(
    r"<!-- if-intensity: ([a-z, ]+) -->\n(.*?)<!-- end-if -->\n?",
    re.DOTALL)

#: The same mechanism keyed on mode. It exists because the template used to open
#: with "You are an expert Prompt Engineer. Your goal is to generate a SYSTEM
#: PROMPT" and close with "Output the final System Prompt" in EVERY mode --
#: including `humanize`, whose deliverable is the rewritten text. Measured: in
#: the 2026-09-03 pressure campaign three of eighteen `with_skill` runs did what
#: that literally asks and returned a prompt instead of the edit.
MODE_BLOCK = re.compile(
    r"<!-- if-mode: ([a-z, \-]+) -->\n(.*?)<!-- end-if -->\n?",
    re.DOTALL)

MODES = ("prompt-gen", "humanize", "audit")


class TemplateError(ValueError):
    """A conditional block names an intensity or a mode that does not exist."""


def strip_conditional_blocks(text, intensity):
    """Keep a conditional block only when *intensity* is in its list.

    An unknown intensity name raises rather than silently dropping the block.
    A typo would otherwise remove a whole verification pass from every run and
    leave nothing behind to notice -- the failure mode a shipped template must
    not have.
    """
    def decide(match):
        names = {n.strip() for n in match.group(1).split(",") if n.strip()}
        unknown = names - set(INTENSITY_PRIORITIES)
        if unknown:
            raise TemplateError(
                f"conditional block names unknown intensity {sorted(unknown)}; "
                f"known: {sorted(INTENSITY_PRIORITIES)}")
        return match.group(2) if intensity in names else ""

    return CONDITIONAL_BLOCK.sub(decide, text)


def strip_mode_blocks(text, mode):
    """Keep a mode block only when *mode* is in its list.

    An unknown mode name raises for the same reason an unknown intensity does:
    a typo would silently delete the line that tells the model what to return.
    """
    def decide(match):
        names = {n.strip() for n in match.group(1).split(",") if n.strip()}
        unknown = names - set(MODES)
        if unknown:
            raise TemplateError(
                f"conditional block names unknown mode {sorted(unknown)}; "
                f"known: {sorted(MODES)}")
        return match.group(2) if mode in names else ""

    return MODE_BLOCK.sub(decide, text)


def get_available_styles():
    """List available style files."""
    return [f.stem for f in STYLES_DIR.glob("*.md")]


def main():
    install_human_channel()
    parser = argparse.ArgumentParser(description="Deterministic System Prompt Assembler for Text Humanizer")
    parser.add_argument("--genre", required=True, choices=GENRE_MAP.keys(), help="Target genre")
    parser.add_argument("--style", help=f"Target style/domain (e.g., crypto). Available: {get_available_styles()}")
    parser.add_argument("--task", default="Rewriting content", help="Description of the task")
    parser.add_argument("--mode", choices=["prompt-gen", "humanize", "audit"], default="humanize",
                        help="Output mode: humanize (rewrite), prompt-gen (generate reusable prompt), audit (diagnose only)")
    parser.add_argument("--intensity", choices=["auto", "max", "high", "medium", "low", "minimal"], default="auto",
                        help="Editing intensity. 'auto' selects based on genre.")
    parser.add_argument("--voice", help="Path to a voice passport file (writing samples analysis)", default="")
    parser.add_argument("--extra-rules", help="Additional custom constraints provided by the user", default="")

    args = parser.parse_args()

    # Resolve intensity
    if args.intensity == "auto":
        resolved_intensity = INTENSITY_DEFAULTS.get(args.genre, "medium")
    else:
        resolved_intensity = args.intensity

    allowed_priorities = INTENSITY_PRIORITIES[resolved_intensity]

    # 1. Load Components
    universal_patterns = load_file(REFERENCES_DIR / "patterns_universal.md")
    rewriting_strategy = load_file(REFERENCES_DIR / "rewriting_strategy.md")

    # Filter patterns by intensity
    universal_patterns = filter_patterns_by_priority(universal_patterns, allowed_priorities)

    # Genre logic
    genre_file = GENRE_MAP[args.genre]
    genre_patterns = load_file(REFERENCES_DIR / genre_file)
    genre_patterns = filter_patterns_by_priority(genre_patterns, allowed_priorities)

    # Style logic
    target_style = args.style if args.style else args.genre

    style_content = ""
    style_path = STYLES_DIR / f"{target_style}.md"

    if style_path.exists():
        style_content = load_file(style_path)
    elif args.style:
        print(f"Warning: Style '{args.style}' not found. Available: {get_available_styles()}", file=sys.stderr)

    # Voice passport logic
    voice_content = ""
    if args.voice:
        voice_path = Path(args.voice)
        if voice_path.exists():
            voice_content = load_file(voice_path)
        else:
            print(f"Warning: Voice file '{args.voice}' not found.", file=sys.stderr)

    # Resolve role
    role_category = ROLE_MAP.get(args.genre, "creative")

    # 2. Load Template
    template = load_file(ASSETS_DIR / "generator_template.md")

    # 3. Assemble
    final_output = template.replace("{{genre}}", args.genre.title())
    final_output = final_output.replace("{{task_description}}", args.task)
    final_output = final_output.replace("{{intensity}}", resolved_intensity)
    final_output = final_output.replace("{{mode}}", args.mode)
    final_output = final_output.replace("{{role_category}}", role_category)

    # Inject Universal Patterns (already filtered by intensity)
    final_output = final_output.replace("{{patterns_universal}}", universal_patterns)

    # Inject Rewriting Strategy
    final_output = final_output.replace("{{rewriting_strategy}}", rewriting_strategy if rewriting_strategy else "No rewriting strategy loaded.")

    # Inject Genre Patterns (already filtered by intensity)
    final_output = final_output.replace("{{patterns_genre}}", genre_patterns)

    # Inject Style
    final_output = final_output.replace("{{style_section}}", style_content if style_content else "No specific domain style applied.")

    # Inject Voice Passport
    final_output = final_output.replace("{{voice_section}}", voice_content if voice_content else "No voice passport provided. Write as a smart person explaining to a friend over coffee.")

    # Inject Extra Rules
    final_output = final_output.replace("{{extra_rules}}", args.extra_rules if args.extra_rules else "No custom constraints.")

    # 4. Strip mode-conditional sections
    if args.mode == "prompt-gen":
        # Remove Diagnosis and Verification sections (only for humanize/audit)
        final_output = re.sub(
            r'### 2\. Diagnosis \(Humanize and Audit modes only\).*?(?=### 3\.)',
            '', final_output, flags=re.DOTALL)
        final_output = re.sub(
            r'### 9\. Verification \(Humanize mode only\).*?(?=---|\Z)',
            '', final_output, flags=re.DOTALL)
    elif args.mode == "audit":
        # Remove Verification (audit doesn't rewrite, so no verification needed)
        final_output = re.sub(
            r'### 9\. Verification \(Humanize mode only\).*?(?=---|\Z)',
            '', final_output, flags=re.DOTALL)

    # 5. Strip blocks that belong to other intensities or other modes
    final_output = strip_conditional_blocks(final_output, resolved_intensity)
    final_output = strip_mode_blocks(final_output, args.mode)

    # 6. Output
    print(final_output)


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
