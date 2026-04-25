"""Read-only support for macro-enabled OOXML files (.docm/.xlsm/.pptm).

OOXML carries VBA macros in a `vbaProject.bin` part inside the ZIP and
distinguishes macro-enabled documents from regular ones via the
[Content_Types].xml main content-type:

  Word        .docm  ↔ application/vnd.ms-word.document.macroEnabled.main+xml
  Excel       .xlsm  ↔ application/vnd.ms-excel.sheet.macroEnabled.main+xml
  PowerPoint  .pptm  ↔ application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml

Templates (.dotm / .xltm / .potm) follow the same convention.

What this module does:

  1. Detect macro-enabled inputs on a fast (zip-list-only) path.
  2. Warn when a writer/repacker is asked to drop the `m` from the
     extension — Office apps silently strip macros when they open a
     file whose [Content_Types].xml declares the non-macro main type,
     even if `vbaProject.bin` survives in the ZIP.

What this module does NOT do:

  - Execute, modify, or analyse VBA bytecode. Macro authoring /
    inspection is a security-sensitive domain that we leave to
    dedicated tools (oletools, msoffcrypto-tool).
  - Convert between macro and non-macro formats. The user does that
    upstream by re-saving in the host application or via
    `soffice --convert-to`.

Replication: this file lives under `office/` and is therefore covered
by the existing docx → xlsx + pptx replication protocol (CLAUDE.md §2).
docx is the master copy.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import IO


MACRO_CONTENT_TYPES: tuple[str, ...] = (
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
    "application/vnd.ms-excel.template.macroEnabled.main+xml",
    "application/vnd.ms-powerpoint.template.macroEnabled.main+xml",
)

MACRO_EXTENSIONS: frozenset[str] = frozenset({
    ".docm", ".xlsm", ".pptm",
    ".dotm", ".xltm", ".potm",
})

NON_MACRO_EXTENSIONS: frozenset[str] = frozenset({
    ".docx", ".xlsx", ".pptx",
    ".dotx", ".xltx", ".potx",
})

VBA_PROJECT_PARTS: tuple[str, ...] = (
    "word/vbaProject.bin",
    "xl/vbaProject.bin",
    "ppt/vbaProject.bin",
)

# Pairs a non-macro extension with its macro counterpart for "rename
# the output to preserve macros" hints.
MACRO_EXT_FOR: dict[str, str] = {
    ".docx": ".docm", ".docm": ".docm",
    ".xlsx": ".xlsm", ".xlsm": ".xlsm",
    ".pptx": ".pptm", ".pptm": ".pptm",
    ".dotx": ".dotm", ".dotm": ".dotm",
    ".xltx": ".xltm", ".xltm": ".xltm",
    ".potx": ".potm", ".potm": ".potm",
}


def is_macro_enabled_file(path: Path) -> bool:
    """Return True iff `path` is an OOXML container declaring a
    macro-enabled main content-type or carrying `vbaProject.bin`.

    Cheap: opens the ZIP, reads `[Content_Types].xml` (≤ a few KB), no
    XML parsing. Returns False for missing files, non-ZIPs, or any I/O
    error — this is a hint, not a security-sensitive check, so failure
    must not bubble up.
    """
    if not path.is_file() or not zipfile.is_zipfile(str(path)):
        return False
    try:
        with zipfile.ZipFile(str(path)) as zf:
            names = zf.namelist()
            if any(n in VBA_PROJECT_PARTS for n in names):
                return True
            if "[Content_Types].xml" in names:
                ct = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                return any(t in ct for t in MACRO_CONTENT_TYPES)
    except (zipfile.BadZipFile, OSError, KeyError):
        return False
    return False


def warn_if_macros_will_be_dropped(
    input_path: Path, output_path: Path, stream: IO[str]
) -> bool:
    """Emit a warning to `stream` when packing a macro-enabled input
    into a non-macro output extension.

    Returns True iff a warning was emitted, so callers can record the
    fact (e.g. for downstream tooling that wants to fail-fast on data
    loss). Pure observation — never raises, never modifies state.
    """
    if not is_macro_enabled_file(input_path):
        return False
    out_suffix = output_path.suffix.lower()
    in_suffix = input_path.suffix.lower()
    if out_suffix not in NON_MACRO_EXTENSIONS:
        return False
    suggested = MACRO_EXT_FOR.get(in_suffix, in_suffix)
    stream.write(
        f"Warning: input is macro-enabled ({in_suffix}); output "
        f"extension {out_suffix} will cause Office apps to silently drop "
        f"macros even if vbaProject.bin survives in the ZIP. To preserve "
        f"the macros, name the output with a macro-friendly extension "
        f"(e.g. {suggested}).\n"
    )
    stream.flush()
    return True
