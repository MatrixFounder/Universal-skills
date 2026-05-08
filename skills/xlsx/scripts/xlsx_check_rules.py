#!/usr/bin/env python3
"""Declarative business-rule validator for `.xlsx` workbooks (xlsx-7).

Thin shim — implementation lives in the `xlsx_check_rules` package
next to this file. See `xlsx_check_rules/cli.py` for the entry point
and `xlsx_check_rules/{constants,exceptions,ast_nodes,rules_loader,
dsl_parser,cell_types,scope_resolver,evaluator,aggregates,output,
remarks_writer,cli_helpers}.py` for the F1-F11 components.

This shim exists to:
  1. Provide a single user-facing entry point (`xlsx_check_rules.py`).
  2. Re-export a stable test-compat surface so the test suite at
     tests/test_xlsx_check_rules.py works without knowing the package
     internals.

Usage and design details:
  * SPEC contract: ../references/xlsx-rules-format.md (12 sections + §13 battery).
  * Architecture: ../../docs/ARCHITECTURE.md (F1-F11 functional decomposition).
  * Plan: ../../docs/PLAN.md (20-task atomic chain).

Status (task 003.01): SKELETON ONLY. Every package function raises
`NotImplementedError("xlsx-7 stub — task-003-NN")` when invoked,
EXCEPT `build_parser` / `parse_args` (a minimal argparse stub so
`--help` short-circuits cleanly per task-003-01 TC-E2E-01) — full
22-flag table lands in 003.14a. The orchestrator `_run` raises NIE
until 003.14b. Phase-1 E2E tests are expected to fail uniformly
with `NotImplementedError` until the F-region tasks (003.05–003.15)
replace the stubs.
"""
from __future__ import annotations

import sys

# === Test-compat re-exports ===
# Symbols re-exported from the package so external callers (tests,
# downstream tooling) have a stable import path independent of the
# internal module layout. The list grows as 003.05–003.15 ship the
# F-region modules; final size target ~25 symbols (see PLAN §"Stub-First
# Phasing").
#
# DO NOT import through this shim from inside the xlsx_check_rules
# package — that creates a re-import cycle.

# rules_loader (1) — F2 (impl: 003.09). Single public entrypoint;
# helpers stay private to keep the test-compat surface minimal.
from xlsx_check_rules.rules_loader import load_rules_file  # noqa: F401

# dsl_parser (6) — F3 (impl: 003.10)
from xlsx_check_rules.dsl_parser import (  # noqa: F401
    build_rule_spec,
    lint_regex,
    parse_check,
    parse_composite,
    parse_scope,
    validate_builtin,
)

# cell_types (6) — F5 (impl: 003.07)
from xlsx_check_rules.cell_types import (  # noqa: F401
    ClassifiedCell,
    LogicalType,
    classify,
    coerce_text_as_date,
    is_excel_serial_date,
    whitespace_strip,
)

# scope_resolver (7) — F6 (impl: 003.08)
from xlsx_check_rules.scope_resolver import (  # noqa: F401
    ScopeResult,
    iter_cells,
    parse_sheet_qualifier,
    resolve_header,
    resolve_named,
    resolve_scope,
    resolve_sheet,
)

# evaluator (7) — F7 (impl: 003.11)
from xlsx_check_rules.evaluator import (  # noqa: F401
    EvalContext,
    Finding,
    eval_arithmetic,
    eval_check,
    eval_regex,
    eval_rule,
    format_message,
)

# aggregates (3) — F8 (impl: 003.12)
from xlsx_check_rules.aggregates import (  # noqa: F401
    AggregateCache,
    AggregateCacheEntry,
    eval_group_by,
)

# output (5) — F9 (impl: 003.13). M2 architect-locked all-three-keys
# envelope invariant verified end-to-end against xlsx-6 batch.py:122.
from xlsx_check_rules.output import (  # noqa: F401
    apply_max_findings,
    apply_summarize_after,
    build_envelope,
    emit_findings,
    emit_human_report,
)

# remarks_writer (5) — F10 (impl: 003.15). M-1 architect-lock dual-stream
# design verified end-to-end (remark column need not be rightmost).
from xlsx_check_rules.remarks_writer import (  # noqa: F401
    allocate_remark_column,
    apply_remark_mode,
    assert_distinct_paths,
    write_remarks,
    write_remarks_streaming,
)

# cli (3) — F1 + F11 (impl: 003.14a + 003.14b)
from xlsx_check_rules.cli import build_parser, main, parse_args  # noqa: F401

# constants (15) — F-Constants (impl: 003.05)
from xlsx_check_rules.constants import (  # noqa: F401
    BUILTIN_WHITELIST,
    COMPOSITE_MAX_DEPTH,
    DEFAULT_MAX_FINDINGS,
    DEFAULT_REGEX_TIMEOUT_MS,
    DEFAULT_SUMMARIZE_AFTER,
    DEFAULT_TIMEOUT_SECONDS,
    EXCEL_SERIAL_DATE_RANGE,
    MAX_FINDINGS_SENTINEL_COL,
    MAX_FINDINGS_SENTINEL_ROW,
    OPENPYXL_ERROR_CODES,
    REDOS_REJECT_PATTERNS,
    RULES_FILE_VERSION,
    RULES_MAX_BYTES,
    SCHEMA_VERSION,
    SEVERITY_LEVELS,
)

# exceptions (14) — F-Errors (impl: 003.05). `IOError` aliased to avoid
# shadowing the builtin in the test-compat surface.
from xlsx_check_rules.exceptions import (  # noqa: F401
    AggregateTypeMismatch,
    AmbiguousHeader,
    CellError,
    CorruptInput,
    EncryptedInput,
    HeaderNotFound,
    IOError as XlsxIOError,
    MergedHeaderUnsupported,
    RegexLintFailed,
    RuleEvalError,
    RulesFileTooLarge,
    RulesParseError,
    SelfOverwriteRefused,
    TimeoutExceeded,
    _AppError,
)

# ast_nodes (24) — F4 (impl: 003.06; ValueRef added in 003.10 for the
# DSL's magic implicit `value` identifier). 22 closed AST node types +
# RuleSpec wrapper + to_canonical_str.
from xlsx_check_rules.ast_nodes import (  # noqa: F401
    Between,
    BinaryOp,
    BuiltinCall,
    CellRef,
    ColRef,
    DatePredicate,
    GroupByCheck,
    In,
    LenPredicate,
    Literal,
    Logical,
    MultiColRef,
    NamedRef,
    RangeRef,
    RegexPredicate,
    RowRef,
    RuleSpec,
    SheetRef,
    StringPredicate,
    TableRef,
    TypePredicate,
    UnaryOp,
    ValueRef,
    to_canonical_str,
)

# Future re-export anchors — added when later F-region tasks land:
#   - evaluator.py:  Finding, EvalContext, ... (003.11)
#   - aggregates.py: AggregateCacheEntry, AggregateCache, ... (003.12)

if __name__ == "__main__":
    sys.exit(main())
