# Task 003.05: `constants.py` + `exceptions.py` (F-Constants + F-Errors)

## Use Case Connection
- **R1.h** (`version: 1` enforcement value).
- **R6.d** (cross-5 `--json-errors` envelope wiring).
- **R13** (D4 / D5 enforcement points — `OPENPYXL_ERROR_CODES` + `REDOS_REJECT_PATTERNS`).

## Task Goal
Implement the two zero-dependency leaf modules. Phase-2 begins here; turning these green un-skips the corresponding `TestConstants` and `TestExceptions` classes in `tests/test_xlsx_check_rules.py`.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/constants.py`

Implement the full constants module per ARCHITECTURE §3.2:

```python
"""F-Constants — magic values shared across the xlsx_check_rules package.

This module has zero internal package dependencies (top of the import
graph). All names are immutable; users may not monkey-patch.
"""
from __future__ import annotations
import sys

__all__ = [
    "RULES_MAX_BYTES", "COMPOSITE_MAX_DEPTH", "BUILTIN_WHITELIST",
    "EXCEL_SERIAL_DATE_RANGE", "OPENPYXL_ERROR_CODES",
    "DEFAULT_TIMEOUT_SECONDS", "DEFAULT_MAX_FINDINGS",
    "DEFAULT_SUMMARIZE_AFTER", "DEFAULT_REGEX_TIMEOUT_MS",
    "REDOS_REJECT_PATTERNS",
    "SCHEMA_VERSION", "RULES_FILE_VERSION",
    "SEVERITY_LEVELS", "MAX_FINDINGS_SENTINEL_ROW",
    "MAX_FINDINGS_SENTINEL_COL",
]

RULES_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB pre-parse cap (§2 SPEC)
COMPOSITE_MAX_DEPTH = 16  # §5.7 cap
BUILTIN_WHITELIST = frozenset({
    "sum", "avg", "mean", "min", "max", "median", "stdev",
    "count", "count_nonempty", "count_distinct", "count_errors",
    "len",
})
EXCEL_SERIAL_DATE_RANGE = (25569, 73050)  # 1970-01-01 .. 2099-12-31
# D4 closure (architect-review): openpyxl recognises EXACTLY these 7.
OPENPYXL_ERROR_CODES = ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!",
                        "#NAME?", "#NUM!", "#N/A")
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_FINDINGS = 1000
DEFAULT_SUMMARIZE_AFTER = 100
DEFAULT_REGEX_TIMEOUT_MS = 100
# D5 closure (architect-review m1): hand-coded reject-list — sole
# parse-time ReDoS lint. recheck (JVM CLI) is NOT used.
REDOS_REJECT_PATTERNS = (
    # 4 classic catastrophic-backtracking shapes
    r"\(.+\+\)\+",   # (a+)+
    r"\(.+\*\)\*",   # (a*)*
    r"\(.+\|.+\)\+", # (a|a)+ etc
    r"\(.+\|.+\)\*", # (a|aa)* etc
)
SCHEMA_VERSION = 1
RULES_FILE_VERSION = 1
SEVERITY_LEVELS = ("error", "warning", "info")
# Per §7.1.2 sentinel substitution
MAX_FINDINGS_SENTINEL_ROW = 2 ** 31 - 1
MAX_FINDINGS_SENTINEL_COL = "￿"  # U+FFFF
```

#### File: `skills/xlsx/scripts/xlsx_check_rules/exceptions.py`

Implement the 16-typed exception hierarchy per ARCHITECTURE §3.2:

```python
"""F-Errors — closed taxonomy of xlsx-7 raise-able errors.

Every error carries (code, type, details) suitable for cross-5
`_errors.report_error` envelope wrapping when --json-errors is set.
Internal sentinel tokens (CellError) inherit from object, not _AppError.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "_AppError", "RulesFileTooLarge", "RulesParseError",
    "AmbiguousHeader", "HeaderNotFound", "MergedHeaderUnsupported",
    "EncryptedInput", "CorruptInput", "IOError",
    "SelfOverwriteRefused", "TimeoutExceeded",
    "RegexLintFailed", "AggregateTypeMismatch", "RuleEvalError",
    "CellError", "MissingDefaultAuthor",  # CellError is a sentinel token
]

class _AppError(Exception):
    """Base for all xlsx-7 typed errors."""
    code: int = 1
    type_: str = "AppError"
    def __init__(self, message: str, **details: Any):
        super().__init__(message)
        self.details = details

class RulesFileTooLarge(_AppError):
    code = 2; type_ = "RulesFileTooLarge"

class RulesParseError(_AppError):
    code = 2; type_ = "RulesParseError"
    # subtype passed via details["subtype"] ∈ {VersionMismatch,
    # UnknownBuiltin, CompositeDepth, IncompatibleFlags, MultiAreaName,
    # YamlAlias, YamlCustomTag, YamlDupKey, BadGrammar, ...}

class AmbiguousHeader(_AppError):
    code = 2; type_ = "AmbiguousHeader"

class HeaderNotFound(_AppError):
    code = 2; type_ = "HeaderNotFound"

class MergedHeaderUnsupported(_AppError):
    code = 2; type_ = "MergedHeaderUnsupported"

class EncryptedInput(_AppError):
    code = 3; type_ = "EncryptedInput"

class CorruptInput(_AppError):
    code = 3; type_ = "CorruptInput"

class IOError(_AppError):
    code = 5; type_ = "IOError"

class SelfOverwriteRefused(_AppError):
    code = 6; type_ = "SelfOverwriteRefused"

class TimeoutExceeded(_AppError):
    code = 7; type_ = "TimeoutExceeded"

class RegexLintFailed(_AppError):
    code = 2; type_ = "RegexLintFailed"

# Internal — not raised, internal flow control
class AggregateTypeMismatch(Exception):
    pass

class RuleEvalError(Exception):
    pass

@dataclass(frozen=True)
class CellError:
    """Sentinel token for Excel error cells. NOT raised."""
    code: str  # one of OPENPYXL_ERROR_CODES
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestConstants` and `TestExceptions`. Add the
following test methods:

- **TestConstants:**
  - `test_redos_patterns_count_is_four` — locks D5: 4 shapes only.
  - `test_openpyxl_error_codes_is_seven_only` — locks D4: 7 codes; modern codes (`#SPILL!`, `#CALC!`, `#GETTING_DATA`) NOT present.
  - `test_builtin_whitelist_is_twelve` — locks SPEC §6.2: 12 names.
  - `test_composite_max_depth_is_sixteen`.
  - `test_rules_max_bytes_is_one_mib`.

- **TestExceptions:**
  - `test_app_error_carries_code_type_details`.
  - `test_each_typed_error_has_exit_code` — iterate over all `_AppError` subclasses, assert each has the documented `code` (2/3/5/6/7).
  - `test_cell_error_is_dataclass_not_exception` — `CellError` MUST NOT inherit from `Exception` (it's a sentinel value, not raised).

## Test Cases

### Unit Tests
- All `TestConstants` and `TestExceptions` methods pass (~ 8 new tests).

### Regression Tests
- xlsx-6 + xlsx_check_rules import smokes still green.
- `test_battery.py` still xfail for all 42 fixtures (no F-region implemented yet).

## Acceptance Criteria
- [ ] `constants.py` complete with full `__all__` (≤ 80 LOC excluding docstrings).
- [ ] `exceptions.py` complete with 16-typed hierarchy (≤ 220 LOC).
- [ ] D4 (`OPENPYXL_ERROR_CODES`) and D5 (`REDOS_REJECT_PATTERNS`) test-locked.
- [ ] `unittest discover -s tests` passes (no skipped methods in TestConstants / TestExceptions).
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- `RULES_MAX_BYTES = 1 * 1024 * 1024` — be explicit; `2**20` reads as a magic number.
- Subtypes of `RulesParseError` are NOT separate classes (would explode the taxonomy). Carry subtype in `details["subtype"]: str`. Documented in the docstring.
- `CellError` is a frozen dataclass to make it hashable (needed for use in finding sets and aggregate cache `error_cells` lists).
