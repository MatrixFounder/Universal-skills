"""F-Errors — closed taxonomy of xlsx_check_rules raise-able errors.

Every typed error is a subclass of `_AppError` and carries:
  - `code`     — process exit code (2/3/5/6/7) per SPEC §7.3.
  - `type_`    — JSON envelope `type` field (cross-5).
  - `details`  — keyword-arg dict; subtype + diagnostic context
                 (e.g. `subtype='VersionMismatch'`, `got=2`).

Subtypes are NOT separate classes — `RulesParseError` is the umbrella
for grammar / version / depth-cap / unknown-builtin / multi-area-name
/ YAML hostile-input rejections, with the specific subtype carried in
`details["subtype"]`. This avoids exploding the taxonomy (architect
note in TASK §3).

Internal flow-control exceptions (`AggregateTypeMismatch`,
`RuleEvalError`) are plain `Exception` subclasses — they are caught
inside the package and translated to findings, never propagated to
the cross-5 envelope.

`CellError` is a frozen dataclass (NOT an exception) — it is a
sentinel value for Excel error cells (`<c t="e">`). Frozen + hashable
so it can live inside set-typed finding fields and aggregate-cache
`error_cells` lists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "_AppError",
    # Exit-code 2 (rules-file / scope / parse / flag-combo)
    "RulesFileTooLarge",
    "RulesParseError",
    "AmbiguousHeader",
    "HeaderNotFound",
    "MergedHeaderUnsupported",
    "RegexLintFailed",
    # Exit-code 3 (workbook unreadable / encrypted)
    "EncryptedInput",
    "CorruptInput",
    # Exit-code 5 (I/O)
    "IOError",
    # Exit-code 6 (cross-7 H1 same-path)
    "SelfOverwriteRefused",
    # Exit-code 7 (wall-clock timeout)
    "TimeoutExceeded",
    # Internal flow-control (NOT raised to the cross-5 envelope)
    "AggregateTypeMismatch",
    "RuleEvalError",
    # Sentinel value (NOT an exception)
    "CellError",
]


class _AppError(Exception):
    """Base class for all xlsx_check_rules typed errors.

    Subclasses MUST override the class attributes `code` (process
    exit code) and `type_` (JSON envelope type tag).
    """

    code: int = 1
    type_: str = "AppError"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details)


# === Exit-code 2 — rules / scope / parse / flag rejection =================
# All exit-2 errors are user-correctable (bad input or bad flags) and
# share the cross-5 envelope-wrap path when --json-errors is set.

class RulesFileTooLarge(_AppError):
    """SPEC §2: rules file exceeds RULES_MAX_BYTES (pre-parse cap)."""

    code = 2
    type_ = "RulesFileTooLarge"


class RulesParseError(_AppError):
    """Umbrella for rules-file syntax / shape / depth / version / YAML errors.

    Subtype carried in `details["subtype"]`. Known subtypes:

    - `VersionMismatch`        — Q7=hard: missing or non-1 `version`.
    - `UnknownBuiltin`         — SPEC §6.2: builtin not in BUILTIN_WHITELIST.
    - `CompositeDepth`         — SPEC §5.7: composite tree > 16 levels.
    - `IncompatibleFlags`      — SPEC §8.2.1: streaming + auto / append.
    - `MultiAreaName`          — SPEC §11: multi-area `definedName` rejected.
    - `YamlAlias`              — SPEC §2.1: anchor / alias rejected pre-composition.
    - `YamlAnchor`             — SPEC §2.1: anchor declaration rejected.
    - `YamlCustomTag`          — SPEC §2.1: tag outside YAML 1.2 schema.
    - `YamlDupKey`             — SPEC §2.1: duplicate map key.
    - `YamlSyntax`             — generic YAML parser failure.
    - `JsonSyntax`             — generic JSON parser failure.
    - `BadGrammar`             — DSL parser rejected token / shape.
    - `RootShape`              — root must be a JSON object.
    - `RulesShape`             — `rules` must be non-empty list.
    - `UnrecognisedExtension`  — `--rules` path has unsupported extension.
    """

    code = 2
    type_ = "RulesParseError"


class AmbiguousHeader(_AppError):
    """SPEC §4.2: two columns share a header name on the same sheet."""

    code = 2
    type_ = "AmbiguousHeader"


class HeaderNotFound(_AppError):
    """SPEC §4.2: rule references a header absent from the sheet.

    `details["available"]` carries the list of present headers
    (truncated to first 50) for the user-facing diagnostic.
    """

    code = 2
    type_ = "HeaderNotFound"


class MergedHeaderUnsupported(_AppError):
    """SPEC §4.2: header row contains `<mergeCell>` ranges (not supported in v1)."""

    code = 2
    type_ = "MergedHeaderUnsupported"


class RegexLintFailed(_AppError):
    """D5 parse-time ReDoS lint: pattern matches a catastrophic-backtracking shape.

    `details["pattern"]` is the user's regex; `details["shape"]` is
    the matching REDOS_REJECT_PATTERNS entry. Per-rule `unsafe_regex:
    true` opts out (still subject to the per-cell timeout).
    """

    code = 2
    type_ = "RegexLintFailed"


# === Exit-code 3 — workbook unreadable ====================================

class EncryptedInput(_AppError):
    """cross-3 fail-fast: encrypted .xlsx (legacy CFB or modern OOXML password)."""

    code = 3
    type_ = "EncryptedInput"


class CorruptInput(_AppError):
    """Workbook can't be unpacked (zip-truncated, malformed OOXML)."""

    code = 3
    type_ = "CorruptInput"


# === Exit-code 5 — I/O ====================================================

class IOError(_AppError):  # noqa: A001 — intentional shadow; xlsx-7 typed error
    """File system error reading rules / workbook or writing output.

    Shadows the builtin `IOError` (which itself is an alias for
    `OSError` since Python 3.3). xlsx-7 callers should catch this
    typed variant via `from .exceptions import IOError as XlsxIOError`
    to disambiguate.
    """

    code = 5
    type_ = "IOError"


# === Exit-code 6 — same-path guard (cross-7 H1) ===========================

class SelfOverwriteRefused(_AppError):
    """`--output` resolves (Path.resolve() with symlink follow) to the input path."""

    code = 6
    type_ = "SelfOverwriteRefused"


# === Exit-code 7 — wall-clock timeout =====================================

class TimeoutExceeded(_AppError):
    """`--timeout` exceeded; partial findings flushed via M-2 main-thread `_partial_flush`."""

    code = 7
    type_ = "TimeoutExceeded"


# === Internal flow-control (NOT raised to the cross-5 envelope) ===========
# These are caught inside the package boundary and translated to
# findings (`rule-eval-error`, `aggregate-type-mismatch`). They never
# reach the user as a process-exit-code envelope.

class AggregateTypeMismatch(Exception):
    """SPEC §5.5.1 sentinel — DECLARED for typed-error vocabulary
    completeness; NEVER raised by xlsx_check_rules at runtime. The
    `--strict-aggregates` path surfaces non-numeric-cell-in-aggregate
    via the `aggregate-type-mismatch` *Finding* (severity=error, which
    drives exit 1) rather than via a process-fatal exception, because
    the user wants to see WHICH cells violated the rule, not just that
    one did. This class exists for typed-error documentation; locked
    by `TestExceptionsTaxonomy` regression test."""


class RuleEvalError(Exception):
    """SPEC §5.5.2 sentinel — DECLARED for typed-error vocabulary
    completeness; NEVER raised. Division-by-zero, NaN, date-vs-date
    arithmetic etc. surface as `rule-eval-error` *Findings* via
    `_eval_error()` so the run continues with diagnostic visibility.
    Locked by `TestExceptionsTaxonomy`."""


# === Sentinel value (NOT an exception) ====================================

@dataclass(frozen=True)
class CellError:
    """Sentinel token for Excel error cells (`<c t="e">`).

    Frozen + hashable so instances can live inside set-typed Finding
    fields and the F8 aggregate-cache `error_cells` lists. The `code`
    field is one of `OPENPYXL_ERROR_CODES` (D4 — 7-tuple).

    NOT an `Exception` subclass — instances are values, not raised.
    The corresponding test (`test_cell_error_is_dataclass_not_exception`)
    locks the invariant.
    """

    code: str
