"""Typed exception contract for xlsx_read. **Final** — no logic stubs.

Five typed exceptions form the entire error-signalling surface of the
package. Callers map them to the cross-5 envelope; the library itself
NEVER writes to stdout or stderr (D-A7).
"""


class EncryptedWorkbookError(RuntimeError):
    """Raised when the OPC archive carries an `EncryptedPackage` part.

    Caller maps to exit 3 (cross-3 contract).
    """


class MacroEnabledWarning(UserWarning):
    """Emitted via `warnings.warn` when `xl/vbaProject.bin` is present.

    Cross-4 contract. Library does NOT raise. Caller decides whether
    to treat this as an error (e.g. via
    `warnings.filterwarnings("error", category=MacroEnabledWarning)`)
    or surface it as a soft warning.
    """


class OverlappingMerges(RuntimeError):
    """Raised when `<mergeCells>` ranges intersect (corrupted workbook).

    M8 / D4 fix: regardless of openpyxl's undefined behaviour on such
    inputs, this library performs an explicit detection pass before
    applying any merge policy and fails loud.
    """


class AmbiguousHeaderBoundary(UserWarning):
    """Emitted when a merge straddles the detected header/body cut.

    Soft warning — not raised. `WorkbookReader.read_table` appends the
    message to `TableData.warnings` and re-emits via `warnings.warn`.
    """


class SheetNotFound(KeyError):
    """Raised by `_sheets.resolve_sheet` for an unknown sheet name."""


class TooManyMerges(RuntimeError):
    """Raised when a worksheet's `<mergeCell>` count exceeds `_MAX_MERGES`.

    xlsx-8a-02 (Sec-MED-3 memory-exhaustion mitigation): a
    hand-crafted OOXML workbook with millions of `<mergeCell>`
    entries (legal per the spec, exploitable via hand-rolled XML)
    would otherwise materialise an unbounded Python dict in RAM
    before any `apply_merge_policy` work begins. Practical
    real-world maximum on legitimate workbooks is ~8K merges; the
    100K cap (in `_merges.py` `_MAX_MERGES`) gives 10× headroom
    while bounding the resulting `MergeMap` dict at ~6 MiB.

    Caller (`xlsx2csv2json.cli._run_with_envelope`) maps to exit 2
    via the cross-5 envelope; this exception is a closed-API
    `RuntimeError` (matches the `OverlappingMerges` precedent —
    library never writes to stdout/stderr; shim owns the envelope).

    Cap value 100_000 is policy (TASK §7.3 D2 / ARCH §15.3 D-A14).
    Fires on the (cap+1)-th iteration (100_001st merge insertion).
    """
