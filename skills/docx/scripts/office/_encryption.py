"""Detect non-OOXML inputs to docx/xlsx/pptx scripts at the byte level.

Two unrelated cases produce the same surface symptom — `zipfile.ZipFile`
raises `BadZipFile: File is not a zip file` deep inside python-docx /
openpyxl / our own unpack code, with a stack trace that doesn't tell
the user what's actually wrong:

  1. Modern Office encryption (Word/Excel/PowerPoint 2010+) wraps the
     entire OOXML package in a Compound File Binary (CFB / OLE2)
     container with an `EncryptedPackage` stream.
  2. Legacy Office formats — .doc / .xls / .ppt — are CFB containers
     too, but unencrypted. They were the standard before 2007.

Both share the CFB signature `D0 CF 11 E0 A1 B1 1A E1` (per [MS-CFB]
§2.2), and we cannot reliably distinguish them by sniffing only the
first few bytes — encrypted CFBs have an `EncryptedPackage` stream
inside the FAT, but parsing that requires walking the directory
structure (overkill for a pre-flight check).

So we report **both** possibilities and let the user pick the right
remediation. Every docx/xlsx/pptx reader script calls
`assert_not_encrypted(path)` early to swap a mystifying `BadZipFile`
for an actionable message.

Decryption / format conversion is intentionally NOT supported here —
the user does that upstream (msoffcrypto-tool, `soffice --convert-to`,
or re-save in the office app).
"""
from __future__ import annotations

from pathlib import Path


CFB_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class EncryptedFileError(Exception):
    """Raised when a docx/xlsx/pptx reader is handed a CFB-container
    input — i.e. either password-protected OOXML or a legacy
    .doc/.xls/.ppt. The two cases share remediation paths (one
    upstream conversion or password removal) so we don't bother
    discriminating in code."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"{path}: not a usable OOXML file. The first bytes match the "
            "Compound File Binary (CFB) signature, which means the file is "
            "either password-protected OR a legacy format (.doc/.xls/.ppt, "
            "Office 97-2003). Remediate upstream:\n"
            "  - Encrypted: remove the password (Office app or msoffcrypto-tool).\n"
            "  - Legacy:    re-save / convert as .docx/.xlsx/.pptx, e.g. "
            "`soffice --headless --convert-to docx INPUT`.\n"
            "Then re-run."
        )
        self.path = path


def is_cfb_container(path: Path) -> bool:
    """Return True iff the file's first 8 bytes match the CFB signature.
    Same byte-level test catches both encrypted OOXML and legacy
    Office 97-2003 — distinguishing the two requires reading the FAT,
    which is out of scope for a pre-flight check.

    Files smaller than 8 bytes are NOT CFB (they're broken or empty);
    we let the caller's normal open() surface that error."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        # Caller's normal error path will produce a better message
        # (file-not-found, permission denied, ...). Don't shadow.
        return False
    return head == CFB_SIGNATURE


# Backwards-compatible alias — earlier the helper was named
# `is_encrypted` before we realised the same byte test catches legacy
# CFBs too. The new name is more accurate; the old one stays for any
# downstream scripts already importing it.
is_encrypted = is_cfb_container


def assert_not_encrypted(path: Path) -> None:
    """Raise EncryptedFileError if `path` is a CFB container (either
    encrypted OOXML or legacy .doc/.xls/.ppt); otherwise return
    silently. Cheap (8-byte read) — safe to call at the top of every
    CLI's main() before any heavyweight library loads the file."""
    if is_cfb_container(path):
        raise EncryptedFileError(path)
