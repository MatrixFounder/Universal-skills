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

from defusedxml import ElementTree as ET  # type: ignore


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


def _content_types_declares_macro(xml_bytes: bytes) -> bool:
    """True iff `[Content_Types].xml` has a `<Default>` or `<Override>`
    element whose `ContentType` attribute exactly matches one of
    `MACRO_CONTENT_TYPES`.

    Substring matching is intentionally avoided — a file that mentions
    a macro content-type in an XML comment, or in some unrelated
    `<Override>` (e.g. an addon part), would otherwise produce a
    false-positive.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False
    macro_set = set(MACRO_CONTENT_TYPES)
    for elem in root.iter():
        # Strip the OOXML namespace so we match `Default`/`Override`
        # regardless of how the file declares it (default vs. prefixed).
        tag = elem.tag.split("}", 1)[-1] if "}" in elem.tag else elem.tag
        if tag not in ("Default", "Override"):
            continue
        if elem.get("ContentType") in macro_set:
            return True
    return False


def is_macro_enabled_file(path: Path) -> bool:
    """Return True iff `path` declares a macro-enabled main content-type
    in `[Content_Types].xml`.

    The content-type is the **authoritative** signal for Office: it
    decides whether the VBA runtime is invoked. A stray
    `vbaProject.bin` in the ZIP without the matching content-type is
    dead weight — Office ignores it. Older versions of this helper
    treated either signal as sufficient (logical OR), which produced
    false-positive warnings on documents that had been edited in tools
    that left orphan parts behind.

    The current rule:

      - If `[Content_Types].xml` declares a macro main type via
        `<Default>` or `<Override>` → True.
      - If `[Content_Types].xml` is missing (broken package) → fall back
        to checking for `vbaProject.bin`.
      - Otherwise → False.

    Returns False for missing files, non-ZIPs, or any I/O error — this
    is a hint, not a security-sensitive check, so failure must not
    bubble up.
    """
    if not path.is_file() or not zipfile.is_zipfile(str(path)):
        return False
    try:
        with zipfile.ZipFile(str(path)) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" in names:
                ct_bytes = zf.read("[Content_Types].xml")
                return _content_types_declares_macro(ct_bytes)
            # No content-types part — broken package. Fall back to the
            # presence of vbaProject.bin so we don't silently miss
            # genuine macro carriers.
            return any(n in VBA_PROJECT_PARTS for n in names)
    except (zipfile.BadZipFile, OSError, KeyError):
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
