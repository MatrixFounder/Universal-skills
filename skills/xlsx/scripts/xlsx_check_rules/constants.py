"""F-Constants — magic values shared across the xlsx_check_rules package.

This module is the top of the package import graph; it has zero
internal package dependencies. All names are immutable values
(`frozenset`, `tuple`, `int`, `str`); users may not monkey-patch
them via reassignment without breaking caller invariants.

References:
    SPEC §2 (rules-file size cap), §5.0 (cell triage), §5.7
    (composite depth cap), §6.2 (builtin whitelist), §7.1.2 (sort
    sentinels). D4 / D5 are architect-locked decisions (see
    docs/ARCHITECTURE.md §1).
"""
from __future__ import annotations

__all__ = [
    "RULES_MAX_BYTES",
    "COMPOSITE_MAX_DEPTH",
    "BUILTIN_WHITELIST",
    "EXCEL_SERIAL_DATE_RANGE",
    "OPENPYXL_ERROR_CODES",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_FINDINGS",
    "DEFAULT_SUMMARIZE_AFTER",
    "DEFAULT_REGEX_TIMEOUT_MS",
    "REDOS_REJECT_PATTERNS",
    "SCHEMA_VERSION",
    "RULES_FILE_VERSION",
    "SEVERITY_LEVELS",
    "MAX_FINDINGS_SENTINEL_ROW",
    "MAX_FINDINGS_SENTINEL_COL",
]

# SPEC §2 — pre-parse rules-file size cap; refuses files > 1 MiB
# before reading the bytes (Path.stat().st_size guard in F2).
RULES_MAX_BYTES = 1 * 1024 * 1024

# SPEC §5.7 — composite (and/or/not) tree-depth cap.
COMPOSITE_MAX_DEPTH = 16

# SPEC §6.2 — closed builtin-call whitelist (12 names; case-sensitive).
BUILTIN_WHITELIST = frozenset({
    "sum",
    "avg",
    "mean",
    "min",
    "max",
    "median",
    "stdev",
    "count",
    "count_nonempty",
    "count_distinct",
    "count_errors",
    "len",
})

# SPEC §5.4.1 path 3 — Excel-serial date window
# (1970-01-01 .. 2099-12-31). Used by `--treat-numeric-as-date`.
EXCEL_SERIAL_DATE_RANGE = (25569, 73050)

# D4 lock (architect-review) — openpyxl 3.1.5 ERROR_CODES recognises
# EXACTLY these 7 codes. Modern codes (#SPILL!, #CALC!, #GETTING_DATA)
# are stored as text by openpyxl and intentionally NOT auto-emitted
# (SPEC §5.0 + §11.2 honest-scope; user-rule workaround).
OPENPYXL_ERROR_CODES = (
    "#NULL!",
    "#DIV/0!",
    "#VALUE!",
    "#REF!",
    "#NAME?",
    "#NUM!",
    "#N/A",
)

# Wall-clock + finding-volume defaults (SPEC §8.1).
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_FINDINGS = 1000
DEFAULT_SUMMARIZE_AFTER = 100
DEFAULT_REGEX_TIMEOUT_MS = 100

# D5 lock (architect-review m1) — hand-coded reject-list is the SOLE
# parse-time ReDoS lint. `recheck` is a JVM CLI (NOT a Python wheel)
# and is intentionally NOT used; per-cell regex.fullmatch(timeout=)
# is the runtime safety net. Each pattern below is a stdlib-`re`
# regex applied via `re.search` to the user's regex string AT PARSE
# TIME (NOT against cell values at rule-eval time).
REDOS_REJECT_PATTERNS = (
    r"\(.+\+\)\+",     # (a+)+ — outer quantifier wraps + group
    r"\(.+\*\)\*",     # (a*)* — outer quantifier wraps * group
    r"\(.+\|.+\)\+",   # (a|a)+ / (a|b)+ — alternation in outer + group
    r"\(.+\|.+\)\*",   # (a|aa)* / similar — alternation in outer * group
)

# S3: hard length cap on user regex patterns. The 1 MiB rules-file cap
# bounds total file size, but a single 800 KiB regex can still trigger
# pathological compile times. 4 KiB is generous for any realistic
# business-rule regex (largest reasonable: a regional-locale numeric
# format with ~50 alternations × ~30 chars ≈ 1.5 KiB).
REGEX_PATTERN_MAX_BYTES = 4 * 1024

# SPEC §7.1 envelope schema_version + rules-file required version.
SCHEMA_VERSION = 1
RULES_FILE_VERSION = 1

# SPEC §3 / §7.1.1 finding severity vocabulary.
SEVERITY_LEVELS = ("error", "warning", "info")

# SPEC §7.1.2 type-homogeneous sort sentinels for grouped findings.
# `2**31 - 1` keeps the row sortable as int alongside per-cell rows;
# U+FFFF is the highest BMP code point — sorts after every column letter.
MAX_FINDINGS_SENTINEL_ROW = 2 ** 31 - 1
MAX_FINDINGS_SENTINEL_COL = "￿"
