#!/usr/bin/env python3
"""Accept all tracked changes in a .docx file.

Uses LibreOffice headless with an inline StarBasic command to dispatch
`.uno:AcceptAllTrackedChanges`, then re-saves the document. The macro
(plus `MacroSecurityLevel=0` so it may run) is seeded into the
throwaway user profile that `_soffice.run` owns, so the command runs
from a clean environment and doesn't leak into the user's normal
profile.

KNOWN LIMITATION (LibreOffice 26.2): the CLI `macro:///` dispatch is
unreliable on 26.2 — cold profiles drop the macro argument during
first-run initialisation while soffice still exits 0, and no
warm-up sequence proved deterministic. This script therefore VERIFIES
the output: if `<w:ins>`/`<w:del>` revision marks survive, it deletes
the bogus output and exits non-zero instead of silently handing back
an unmodified copy. Locked in by the functional contract test in
`tests/test_e2e.sh`. The planned fix is driving LibreOffice over the
UNO bridge (`--accept=pipe` + bundled LibreOfficePython) — see
docs/office-skills-backlog.md.

Reference (public):
- LibreOffice dispatch commands:
  https://wiki.documentfoundation.org/Development/DispatchCommands
- UNO API:
  https://api.libreoffice.org/

Usage:
    python docx_accept_changes.py input.docx output.docx [--timeout 120]

Exit codes:
    0 — success (verified: no revision marks remain)
    1 — soffice not found, timeout, dispatch failed, or the tracked
        changes were NOT accepted (silent no-op detected)
"""

from __future__ import annotations

import _venv_bootstrap  # self-bootstrap into scripts/.venv (TASK 019; replicated per CLAUDE.md §2)
_venv_bootstrap.reexec_into_venv(requires=("lxml",), _file=__file__)

import argparse
import re
import shutil
import sys
import textwrap
import zipfile
from pathlib import Path

from _errors import add_json_errors_argument, report_error
from _soffice import SofficeError, run as soffice_run
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped


BASIC_MACRO = textwrap.dedent(
    """\
    Sub AcceptAllChanges(sUrl As String)
        Dim oDoc As Object
        Dim oArgs(0) As New com.sun.star.beans.PropertyValue
        oArgs(0).Name = "Hidden"
        oArgs(0).Value = True
        oDoc = StarDesktop.loadComponentFromURL(sUrl, "_blank", 0, oArgs())
        If IsNull(oDoc) Then
            Exit Sub
        End If
        Dim oDispatcher As Object
        oDispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
        oDispatcher.executeDispatch(oDoc.CurrentController.Frame, ".uno:AcceptAllTrackedChanges", "", 0, Array())
        oDoc.store()
        oDoc.close(True)
    End Sub
    """
)


# Seeded into the throwaway profile `_soffice.run` owns. LibreOffice
# 26.2 honours only the FIRST -env:UserInstallation= argument, so the
# old pattern (macro installed into a second profile passed via args)
# put the macro into a profile LibreOffice never read.
# MacroSecurityLevel=0 lets the freshly seeded Standard library run.
MACRO_PROFILE_SEED = {
    "user/basic/Standard/Module1.xba": (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">\n'
        '<script:module xmlns:script="http://openoffice.org/2000/script" '
        'script:name="Module1" script:language="StarBasic">\n'
        f"{BASIC_MACRO}\n"
        "</script:module>\n"
    ),
    "user/basic/Standard/script.xlb": (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
        '<library:library xmlns:library="http://openoffice.org/2000/library" '
        'library:name="Standard" library:readonly="false" library:passwordprotected="false">\n'
        '  <library:element library:name="Module1"/>\n'
        "</library:library>\n"
    ),
    "user/basic/Standard/dialog.xlb": (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
        '<library:library xmlns:library="http://openoffice.org/2000/library" '
        'library:name="Standard" library:readonly="false" library:passwordprotected="false"/>\n'
    ),
    "user/registrymodifications.xcu": (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        ' <item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse">'
        "<value>0</value></prop></item>\n"
        "</oor:items>\n"
    ),
}

# Every OOXML revision-marker ELEMENT an accept-all must remove:
# run/paragraph insertions and deletions, tracked moves (incl. their
# range markers), tracked formatting changes on every level (run,
# paragraph, section, table, row, cell, grid, numbering), and
# table-cell revisions. Prefix-agnostic (\w+ instead of a literal w)
# because non-Word producers may bind the WML namespace to another
# prefix. The [\s>/] tail keeps <w:insideH>/<w:delText> and friends
# from false-positiving while accepting attributes split across lines.
_REVISION_MARK = re.compile(
    rb"<\w+:(?:"
    rb"ins|del|cellIns|cellDel|cellMerge"
    rb"|moveFrom(?:RangeStart|RangeEnd)?"
    rb"|moveTo(?:RangeStart|RangeEnd)?"
    rb"|rPrChange|pPrChange|sectPrChange|tblPrChange|trPrChange"
    rb"|tcPrChange|tblGridChange|numberingChange"
    rb")[\s>/]"
)


class AcceptChangesVerificationError(RuntimeError):
    """soffice exited 0 but tracked changes are still in the output."""


def verify_no_tracked_changes(path: Path) -> None:
    """Raise when any word/*.xml part still carries revision markers
    (<w:ins>, <w:del>, tracked moves, formatting changes, cell
    revisions).

    This is the loud replacement for the LibreOffice 26.2 silent
    no-op: the CLI macro dispatch can be dropped while soffice exits
    0, leaving an unmodified copy that looks like a success.
    """
    with zipfile.ZipFile(str(path)) as z:
        for name in z.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            if _REVISION_MARK.search(z.read(name)):
                raise AcceptChangesVerificationError(
                    f"LibreOffice exited 0 but {name} still contains tracked "
                    "changes — the accept dispatch did not run (known "
                    "LibreOffice 26.2 limitation: CLI macro:/// is dropped "
                    "on cold profiles). The unaccepted output copy was "
                    "removed. Workarounds: accept the changes in a desktop "
                    "Word/LibreOffice session, or use LibreOffice 25.x."
                )


def accept_changes(input_path: Path, output_path: Path, *, timeout: int) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, output_path)

    doc_url = output_path.as_uri()
    try:
        soffice_run(
            [f'macro:///Standard.Module1.AcceptAllChanges("{doc_url}")'],
            timeout=timeout,
            profile_seed=MACRO_PROFILE_SEED,
        )
        verify_no_tracked_changes(output_path)
    except Exception:
        # Never leave an unaccepted copy behind: downstream tooling
        # would take it for a successfully processed document.
        if output_path != input_path:
            output_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .docx file")
    parser.add_argument("output", type=Path, help="Destination .docx with changes accepted")
    parser.add_argument("--timeout", type=int, default=120, help="soffice timeout in seconds (default 120)")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    warn_if_macros_will_be_dropped(args.input, args.output, sys.stderr)

    try:
        assert_not_encrypted(args.input)
        accept_changes(args.input, args.output, timeout=args.timeout)
    except EncryptedFileError as exc:
        return report_error(
            str(exc), code=3, error_type="EncryptedFileError",
            details={"path": str(args.input)}, json_mode=je,
        )
    except FileNotFoundError as exc:
        return report_error(
            f"Input not found: {exc}",
            code=1, error_type="FileNotFound", json_mode=je,
        )
    except SofficeError as exc:
        return report_error(
            str(exc), code=1, error_type="SofficeError", json_mode=je,
        )
    except AcceptChangesVerificationError as exc:
        return report_error(
            str(exc), code=1, error_type="AcceptChangesVerificationError",
            details={"path": str(args.input)}, json_mode=je,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
