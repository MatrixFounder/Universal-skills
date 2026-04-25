"""Unified error-reporting helper for office-skill CLI scripts.

Two modes:

  default       — human-readable message on stderr; the integer return
                  value goes back to the shell as the exit code.
  --json-errors — single line of JSON on stderr, then the same exit code.

JSON envelope:

    {"error": "<message>",
     "code":  <int>,
     "type":  "<ErrorClass>",          # optional
     "details": {<context>}}            # optional, free-form

Why this exists: agent wrappers (CI runners, skill harnesses, the
ultrareview pipeline) parse stderr to surface failures back to the
model. Free-form text means each wrapper writes ad-hoc parsing per
script; a uniform JSON line means one parser covers the four office
skills.

Replication: this file is byte-identical across the four office skills
(`skills/docx/scripts/_errors.py`, `…/xlsx/…`, `…/pptx/…`,
`…/pdf/…`). docx is the master copy.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import IO, Any


def add_json_errors_argument(parser: argparse.ArgumentParser) -> None:
    """Wire the `--json-errors` flag into a CLI's argparse and route
    argparse's own usage errors (`parser.error`, missing required args,
    type-conversion failures) through the same JSON envelope.

    Call this in every script's `main()` right after the parser is
    constructed so the flag is uniform across the four skills.

    Implementation note: argparse's built-in `parser.error` exits 2 with
    plain-text usage to stderr. That bypasses the JSON envelope and is
    the most common way wrappers get tripped up — they parse stderr as
    JSON and choke on usage banners. We monkey-patch `parser.error`
    here so the same flag covers both domain errors (via
    `report_error`) and usage errors.
    """
    parser.add_argument(
        "--json-errors",
        dest="json_errors",
        action="store_true",
        help=(
            "Emit failures as a single line of JSON on stderr "
            "(machine-readable: {error, code, type?, details?})."
        ),
    )

    _argparse_error = parser.error

    def _json_aware_error(message: str) -> None:
        # We can't read parsed args here — argparse calls error() during
        # parsing, before parse_args() returns. Fall back to a literal
        # scan of sys.argv. False positives only happen if a string
        # arg literally contains "--json-errors", which is harmless
        # (we'd just emit the JSON form on a usage error — strictly
        # better for wrappers).
        if "--json-errors" in sys.argv[1:]:
            envelope = {
                "error": message,
                "code": 2,
                "type": "UsageError",
                "details": {"prog": parser.prog},
            }
            sys.stderr.write(json.dumps(envelope, ensure_ascii=False) + "\n")
            sys.stderr.flush()
            sys.exit(2)
        _argparse_error(message)

    parser.error = _json_aware_error  # type: ignore[method-assign]


def report_error(
    message: str,
    *,
    code: int = 1,
    error_type: str | None = None,
    details: dict[str, Any] | None = None,
    json_mode: bool = False,
    stream: IO[str] = sys.stderr,
) -> int:
    """Write `message` to `stream` and return `code`.

    Idiom in callers:

        return report_error("Input not found", code=1, json_mode=args.json_errors)

    `code` is returned as-is so the caller can `sys.exit(main())` and
    the exit status matches the JSON envelope's `code` field — wrappers
    don't have to reconcile two sources of truth.
    """
    if json_mode:
        envelope: dict[str, Any] = {"error": message, "code": code}
        if error_type is not None:
            envelope["type"] = error_type
        if details:
            envelope["details"] = details
        stream.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        stream.write(message)
        if not message.endswith("\n"):
            stream.write("\n")
    stream.flush()
    return code
