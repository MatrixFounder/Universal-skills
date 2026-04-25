"""Unified error-reporting helper for office-skill CLI scripts.

Two modes:

  default       — human-readable message on stderr; the integer return
                  value goes back to the shell as the exit code.
  --json-errors — single line of JSON on stderr, then the same exit code.

JSON envelope:

    {"v":     1,                       # schema version (always present)
     "error": "<message>",
     "code":  <int>,                   # NEVER 0 — see report_error guard
     "type":  "<ErrorClass>",          # optional
     "details": {<context>}}            # optional, free-form

The schema version `v` is set so that wrappers can detect future
breaking changes (e.g. renaming a field) and refuse old payloads
gracefully. Bump only when the meaning of an existing field changes.

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


SCHEMA_VERSION = 1


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
                "v": SCHEMA_VERSION,
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

    Defensive coercion: `code=0` would mean "report an error then exit
    success", which is a contradiction and almost always a typo. We
    coerce to 1 and write a developer hint to stderr so the bug shows
    up in tests instead of masquerading as success in production.
    """
    if code == 0:
        # Stay loud — wrappers and CI runners would silently succeed
        # if we honoured a 0 here. A literal warning to stderr ensures
        # whoever wrote `code=0` notices on first run.
        sys.stderr.write(
            "report_error: WARNING — caller passed code=0 with a "
            "non-empty error message; coercing to 1 to avoid a "
            "false-success exit.\n"
        )
        code = 1
    if json_mode:
        envelope: dict[str, Any] = {
            "v": SCHEMA_VERSION,
            "error": message,
            "code": code,
        }
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
