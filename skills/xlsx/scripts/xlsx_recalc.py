#!/usr/bin/env python3
"""Force formula recalculation in an .xlsx via headless LibreOffice.

Why this is needed: `openpyxl` saves formulas as *strings* with no
cached value. Consumers that read the file with `data_only=True` see
`None` until some spreadsheet engine opens and resaves the workbook.
LibreOffice can do that headlessly via a one-shot StarBasic macro.

After recalculation the script (optionally) scans every cell for
formula errors (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`,
`#NUM!`, `#NULL!`) and reports them.

Usage:
    python3 xlsx_recalc.py input.xlsx [--output out.xlsx]
                                       [--timeout 120]
                                       [--scan-errors]
                                       [--json]

If `--output` is omitted, the input file is rewritten in place.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

from openpyxl import load_workbook  # type: ignore

from _errors import add_json_errors_argument, report_error
from _soffice import SofficeError, run as soffice_run
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped


BASIC_MACRO = textwrap.dedent(
    """\
    Sub RecalcAndSave(sUrl As String)
        Dim oDoc As Object
        Dim oArgs(0) As New com.sun.star.beans.PropertyValue
        oArgs(0).Name = "Hidden"
        oArgs(0).Value = True
        oDoc = StarDesktop.loadComponentFromURL(sUrl, "_blank", 0, oArgs())
        If IsNull(oDoc) Then
            Exit Sub
        End If
        oDoc.calculateAll()
        oDoc.store()
        oDoc.close(True)
    End Sub
    """
)

ERROR_TOKENS = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}


def _install_macro(profile: Path) -> None:
    basic_dir = profile / "user" / "basic" / "Standard"
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


def recalc(input_path: Path, output_path: Path, *, timeout: int) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path != output_path:
        shutil.copyfile(input_path, output_path)

    with tempfile.TemporaryDirectory(prefix="lo-recalc-") as tmp:
        profile = Path(tmp) / "profile"
        _install_macro(profile)
        soffice_run(
            [
                f"-env:UserInstallation={profile.as_uri()}",
                f'macro:///Standard.Module1.RecalcAndSave("{output_path.as_uri()}")',
            ],
            timeout=timeout,
        )


def scan_errors(path: Path) -> dict[str, list[str]]:
    """Report cells whose data_type is 'e' (Excel error) only.

    A cell can hold the literal string "#REF!" without being a formula
    error; we use the Excel-level data type to distinguish the two.
    """
    wb = load_workbook(str(path), data_only=True, read_only=True)
    hits: dict[str, list[str]] = {}
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type != "e":
                        continue
                    value = cell.value
                    if isinstance(value, str) and value in ERROR_TOKENS:
                        hits.setdefault(value, []).append(f"{sheet_name}!{cell.coordinate}")
    finally:
        wb.close()
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .xlsx")
    parser.add_argument("--output", type=Path, default=None, help="Destination .xlsx (default: rewrite in place)")
    parser.add_argument("--timeout", type=int, default=120, help="soffice timeout (default 120s)")
    parser.add_argument("--scan-errors", action="store_true", help="Scan for formula-error cells after recalc")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    output = args.output or args.input
    warn_if_macros_will_be_dropped(args.input, output, sys.stderr)

    try:
        assert_not_encrypted(args.input)
        recalc(args.input, output, timeout=args.timeout)
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

    if not args.scan_errors:
        if args.json:
            print(json.dumps({"ok": True, "errors": {}}, ensure_ascii=False))
        else:
            print("Recalculated.")
        return 0

    errors = scan_errors(output)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    else:
        if not errors:
            print("Recalculated, no formula errors.")
        else:
            for code, cells in errors.items():
                print(f"{code}: {len(cells)} cells — {', '.join(cells[:10])}"
                      + ("..." if len(cells) > 10 else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
