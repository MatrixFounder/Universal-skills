#!/usr/bin/env python3
"""Accept all tracked changes in a .docx file.

Uses LibreOffice headless with an inline StarBasic command to dispatch
`.uno:AcceptAllTrackedChanges`, then re-saves the document. The macro
is written to a temporary user profile so the command runs from a
clean environment and doesn't leak into the user's normal profile.

Reference (public):
- LibreOffice dispatch commands:
  https://wiki.documentfoundation.org/Development/DispatchCommands
- UNO API:
  https://api.libreoffice.org/

Usage:
    python docx_accept_changes.py input.docx output.docx [--timeout 120]

Exit codes:
    0 — success
    1 — soffice not found, timeout, or dispatch failed
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import textwrap
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


def _install_macro(profile_dir: Path) -> None:
    """Write the BASIC macro into a fresh user profile's Standard library."""
    basic_dir = profile_dir / "user" / "basic" / "Standard"
    basic_dir.mkdir(parents=True, exist_ok=True)

    (basic_dir / "Module1.xba").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">\n'
        '<script:module xmlns:script="http://openoffice.org/2000/script" '
        'script:name="Module1" script:language="StarBasic">\n'
        f"{BASIC_MACRO}\n"
        "</script:module>\n",
        encoding="utf-8",
    )
    (basic_dir / "script.xlb").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
        '<library:library xmlns:library="http://openoffice.org/2000/library" '
        'library:name="Standard" library:readonly="false" library:passwordprotected="false">\n'
        '  <library:element library:name="Module1"/>\n'
        "</library:library>\n",
        encoding="utf-8",
    )
    (basic_dir / "dialog.xlb").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
        '<library:library xmlns:library="http://openoffice.org/2000/library" '
        'library:name="Standard" library:readonly="false" library:passwordprotected="false"/>\n',
        encoding="utf-8",
    )


def accept_changes(input_path: Path, output_path: Path, *, timeout: int) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, output_path)

    with tempfile.TemporaryDirectory(prefix="lo-accept-") as tmp:
        profile = Path(tmp) / "profile"
        _install_macro(profile)
        profile_url = profile.as_uri()
        doc_url = output_path.as_uri()

        soffice_run(
            [
                f"-env:UserInstallation={profile_url}",
                f'macro:///Standard.Module1.AcceptAllChanges("{doc_url}")',
            ],
            timeout=timeout,
        )


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
