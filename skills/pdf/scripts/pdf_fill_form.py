#!/usr/bin/env python3
"""Fill / inspect AcroForm fields in a PDF.

Three modes:

  pdf_fill_form.py --check IN.pdf
      Print JSON describing the form: {"type": "acroform"|"xfa"|"none",
      "fields": [{"name", "type", "value", "options"?, "rect"}, ...]}.
      Exit 0 on AcroForm, 11 on XFA, 12 when no form is present.

  pdf_fill_form.py --extract-fields IN.pdf -o fields.json
      Same payload as --check, written to fields.json. Use this to
      inspect what to fill, then edit the values, then feed it back via
      the default mode.

  pdf_fill_form.py IN.pdf DATA.json -o OUT.pdf [--flatten]
      Fill the form using DATA.json (a flat {field_name: value} map).
      Checkbox values are name objects in pypdf's vocabulary —
      "/Yes" / "/Off" — and radio values are the export name of the
      chosen button (NOT its index). Unknown field names are ignored
      with a warning. --flatten drops the form dictionary so the
      filled values stick but the file is no longer interactively
      editable in viewers.

XFA (Adobe LiveCycle) forms are detected and refused — pypdf cannot
fill them. Use commercial tooling or reauthor the form as AcroForm.

Every JSON payload this script puts on stdout goes out as UTF-8
**bytes** (via `_errors.write_json_stdout`), so it does not change with
the caller's locale. The `--extract-fields -o FILE` half writes its JSON
to the file, which was already locale-independent (`encoding="utf-8"`)
and is unchanged; what that branch puts on stdout is one human-readable
status line, and a human line is NOT part of the JSON byte contract — it
stays encoded with the caller's codec, with characters that codec cannot
render degraded to escapes rather than aborting a run whose file is
already on disk (see `_print_status`).

A reader that goes away — `| head`, or a consumer that exits first —
ends every one of those writes, the status line included, as exit 13
plus an `OutputWriteFailed` envelope, never a raw traceback and never
the interpreter's substituted 120.

Exit codes are in the 10s deliberately: argparse reserves 0-2, so
overloading 2/3 for our domain errors collides with usage errors.
"""
from __future__ import annotations

import argparse
import errno
import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter  # type: ignore
from pypdf.generic import NameObject  # type: ignore

from _errors import (
    abandon_stdout, add_json_errors_argument, report_error, write_json_stdout,
)


# Custom exit codes start at 10 to leave 0-9 for argparse / shell convention.
EXIT_OK = 0
EXIT_FILL_ERROR = 10  # any pypdf write/read failure during fill mode
EXIT_XFA = 11
EXIT_NO_FORM = 12
EXIT_OUTPUT_WRITE = 13  # stdout died mid-write (broken pipe)


def _print_status(text: str) -> None:
    """Write one human-readable status line to stdout.

    Not the JSON channel: this line is presentation, so the caller's codec
    still governs it — reconfiguring stdout would override a choice the
    caller made for the whole process. What is not acceptable is failing the
    run over it. `print()` raises `UnicodeEncodeError` on a character the
    codec cannot render, and the one such character here is inside the user's
    own `-o` path: measured before this helper, `--extract-fields -o
    'поля—fields.json'` under `PYTHONIOENCODING=ascii` wrote the file
    correctly and then died on the status line with an 8-line traceback at
    exit 1, so the caller was told the run failed about a file that exists.
    `backslashreplace` degrades those characters to escapes instead.

    A stream with no `.buffer` (a test's `StringIO`, a wrapper's proxy) keeps
    the text path, where the caller owns the encoding — same split as
    `_errors.write_json_stdout`.

    `BrokenPipeError` propagates: the fd is abandoned first (so the
    interpreter's shutdown flush cannot replace the exit status with 120),
    but only the caller knows which envelope and exit code it owes.
    """
    line = text + "\n"
    target = sys.stdout
    if target is None:
        # fd 1 closed before the process started (`prog >&-`): CPython leaves
        # `sys.stdout` as None and `print()` silently does nothing. Report the
        # sink as gone, which is what it is.
        raise BrokenPipeError(errno.EBADF, "stdout is closed")
    buffer = getattr(target, "buffer", None)
    try:
        if buffer is None:
            target.write(line)
            target.flush()
            return
        target.flush()   # keep the two layers in order
        encoding = getattr(target, "encoding", None) or "utf-8"
        buffer.write(line.encode(encoding, "backslashreplace"))
        buffer.flush()
    except BrokenPipeError:
        abandon_stdout(target)
        raise


def _stdout_broken_pipe(
    json_mode: bool,
    *,
    message: str = "stdout closed before the JSON was fully written "
                   "(broken pipe)",
    details: dict | None = None,
) -> int:
    """Turn a dead stdout into this script's own envelope + exit code.

    The write site redirects fd 1 to /dev/null before re-raising, so the
    interpreter's shutdown flush finds nothing to retry and cannot replace
    the status with 120. That redirect is best-effort, not a guarantee:
    `_errors.abandon_stdout` swallows the failure when the stream has no real
    fd (a test's `StringIO`, a wrapper's proxy object), and the closed-fd
    case (`prog >&-`, where `sys.stdout` is None) never reaches it at all —
    in neither of those is there a buffered fd for the shutdown flush to trip
    over, which is why leaving them un-redirected is safe rather than merely
    tolerated.

    Measured before the change, `--check` on a 352 KB payload through
    `| head -c 20` exited 120 with a 13-line traceback on stderr, and the two
    `print(...)` sites exited 1 with an 8-line traceback — in every case
    where `--json-errors` promises exactly one line of JSON.

    13 rather than 10: `EXIT_FILL_ERROR` means the *fill* failed and the
    output PDF is suspect, which is a different thing from a reader hanging
    up on a report the script produced successfully.
    """
    return report_error(
        message, code=EXIT_OUTPUT_WRITE, error_type="OutputWriteFailed",
        details=details or {"path": "stdout"}, json_mode=json_mode,
    )


class FormError(Exception):
    """Domain error from `fill()`. Carries the kind so `main()` can map
    to an exit code without resorting to SystemExit-as-control-flow."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message)
        self.kind = kind  # "xfa" | "no_form"


# ---- Detection -----------------------------------------------------------

def _form_type(reader: PdfReader) -> str:
    acroform = reader.trailer["/Root"].get("/AcroForm")
    if not acroform:
        return "none"
    # XFA may live next to a regular AcroForm (hybrid) or be the only
    # form data (pure XFA). Either way we refuse to fill — pypdf only
    # writes back to the AcroForm widget tree, so values typed into an
    # XFA-only file would silently fail to render in Acrobat.
    if acroform.get("/XFA"):
        return "xfa"
    return "acroform"


def _describe_fields(reader: PdfReader) -> list[dict]:
    """Flatten reader.get_fields() into a list of {name, type, value, ...}.
    pypdf's field types come back as PDF name objects (e.g. /Tx, /Btn,
    /Ch); translate to friendlier strings."""
    raw = reader.get_fields() or {}
    type_map = {"/Tx": "text", "/Btn": "button", "/Ch": "choice", "/Sig": "signature"}
    out = []
    for name, field in raw.items():
        ft = field.get("/FT", "")
        entry = {
            "name": name,
            "type": type_map.get(str(ft), str(ft) or "unknown"),
            "value": field.get("/V"),
        }
        # Buttons split into checkbox vs radio by /Ff flag bit 16
        # (Pushbutton) or 15 (Radio); in practice we only need to know
        # the export-value vocabulary, not the subtype, so include
        # /Opt or /AP keys for the caller.
        opts = field.get("/Opt")
        if opts is not None:
            entry["options"] = [str(o) for o in opts]
        ap = field.get("/AP")
        if ap and "/N" in ap:
            entry["export_values"] = list(ap["/N"].keys())
        rect = field.get("/Rect")
        if rect is not None:
            # PDF spec allows /Rect entries to be indirect refs that
            # resolve to non-numerics in malformed files; coerce
            # defensively so --check on an unusual PDF doesn't crash.
            coerced_rect = []
            for x in rect:
                try:
                    coerced_rect.append(float(x))
                except (TypeError, ValueError):
                    coerced_rect.append(None)
            entry["rect"] = coerced_rect
        out.append(entry)
    return out


def _form_summary(reader: PdfReader) -> dict:
    return {"type": _form_type(reader), "fields": _describe_fields(reader)}


# ---- Fill ----------------------------------------------------------------

def _coerce_button_value(value, export_keys: set[str] | None = None):
    """Normalise a JSON-shaped value into pypdf's NameObject vocabulary
    for AcroForm buttons. Accepts:
      - bool True/False  → /Yes, /Off
      - int 1/0          → /Yes, /Off (common JSON shorthand)
      - "/Yes", "/Off"   → as-is, wrapped in NameObject
      - "Yes", "Off"     → prepended slash, wrapped (typo recovery)
      - export-key match → wrapped in NameObject (radio button by name)
    Anything else passes through unchanged so callers retain control;
    pypdf will reject the value and the warning hint will surface."""
    if value is True:
        return NameObject("/Yes")
    if value is False:
        return NameObject("/Off")
    if value == 1:  # int, not bool — already handled above
        return NameObject("/Yes")
    if value == 0:
        return NameObject("/Off")
    if isinstance(value, str):
        if value.startswith("/"):
            return NameObject(value)
        # Bare strings: if the field's /AP exposes a matching export
        # key (e.g. "Yes" matches "/Yes"), prepend the slash. This
        # silently fixes the most common typo.
        if export_keys and value in export_keys:
            return NameObject(f"/{value}")
        # Special-case the universal binary pair too — many PDFs use
        # Yes/Off without exposing /AP keys we can sniff.
        if value in ("Yes", "Off"):
            return NameObject(f"/{value}")
    return value


def _button_export_keys(field) -> set[str]:
    """Mining /AP/N's keys so radio/checkbox callers can pass bare
    names. Returns an empty set if the field has no appearance dict."""
    ap = field.get("/AP")
    if not ap or "/N" not in ap:
        return set()
    return {str(k).lstrip("/") for k in ap["/N"].keys()}


def _writer_root(writer: PdfWriter):
    """pypdf 5.x exposes `writer.root_object`; 4.x only `_root_object`.
    Prefer the public name so the flatten path doesn't tie us to a
    specific pypdf release."""
    return getattr(writer, "root_object", None) or writer._root_object


def fill(input_pdf: Path, data: dict, output_pdf: Path, *, flatten: bool) -> dict:
    reader = PdfReader(str(input_pdf))
    kind = _form_type(reader)
    if kind == "none":
        raise FormError("no_form", f"{input_pdf} has no AcroForm.")
    if kind == "xfa":
        raise FormError("xfa", f"{input_pdf} is an XFA form (not fillable via pypdf).")

    writer = PdfWriter(clone_from=reader)
    fields_meta = reader.get_fields() or {}
    known = set(fields_meta.keys())

    coerced: dict = {}
    skipped: list[str] = []
    for k, v in data.items():
        if k not in known:
            skipped.append(k)
            continue
        meta = fields_meta[k]
        # Buttons (/Btn) need NameObject; everything else passes through.
        if str(meta.get("/FT", "")) == "/Btn":
            coerced[k] = _coerce_button_value(v, _button_export_keys(meta))
        else:
            coerced[k] = v

    for page in writer.pages:
        writer.update_page_form_field_values(page, coerced)

    root = _writer_root(writer)
    if flatten and "/AcroForm" in root:
        # Surgical flatten: drop the form dictionary. Values stay in
        # the page's annotations and render correctly; viewers no
        # longer offer to edit them. For a true draw-into-page-content
        # flatten use pikepdf or pdf-lib (out of scope here).
        del root["/AcroForm"]

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pdf, "wb") as fh:
        writer.write(fh)

    return {
        "filled": list(coerced.keys()),
        "skipped_unknown_fields": skipped,
        "flattened": flatten,
        "output": str(output_pdf),
    }


# ---- CLI -----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, nargs="?", help="Input PDF")
    parser.add_argument("data", type=Path, nargs="?", help="JSON {field: value}")
    parser.add_argument("-o", "--output", type=Path, help="Output PDF (fill mode)")
    parser.add_argument("--check", action="store_true",
                        help="Print form-type + fields as JSON. Exit 0/11/12 = AcroForm/XFA/none.")
    parser.add_argument("--extract-fields", action="store_true",
                        help="Write field schema to --output (or stdout) as JSON.")
    parser.add_argument("--flatten", action="store_true",
                        help="After filling, drop /AcroForm so values stay but form is non-editable.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    # parser.error() exits with code 2 — that's the argparse contract
    # we deliberately leave alone (so usage errors stay distinguishable
    # from our domain exit codes 10–12).
    if not args.input or not args.input.is_file():
        parser.error("input PDF is required")

    if args.check:
        info = _form_summary(PdfReader(str(args.input)))
        try:
            write_json_stdout(info, indent=2, default=str)
        except BrokenPipeError:
            return _stdout_broken_pipe(je)
        return {"none": EXIT_NO_FORM, "xfa": EXIT_XFA}.get(info["type"], EXIT_OK)

    if args.extract_fields:
        info = _form_summary(PdfReader(str(args.input)))
        if args.output:
            # The file half was never locale-dependent and still needs the
            # serialised string; the stdout half now goes out as bytes. Both
            # carry the same JSON — `write_json_stdout` serialises with the
            # identical arguments.
            payload = json.dumps(info, indent=2, ensure_ascii=False, default=str)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
            try:
                _print_status(
                    f"Wrote {len(info['fields'])} field(s) to {args.output}")
            except BrokenPipeError:
                # The schema IS on disk; only the status line failed to
                # arrive. Say which file, the way the OSError arm names its
                # sink — an envelope claiming "stdout" here would send the
                # caller looking for a payload that went to a file.
                return _stdout_broken_pipe(
                    je,
                    message=(
                        "stdout closed before the status line was written "
                        f"(broken pipe); the field schema was written to "
                        f"{args.output}"
                    ),
                    details={"path": "stdout",
                             "output_path": str(args.output)},
                )
        else:
            try:
                write_json_stdout(info, indent=2, default=str)
            except BrokenPipeError:
                return _stdout_broken_pipe(je)
        return EXIT_OK

    # Fill mode.
    if not args.data or not args.data.is_file():
        parser.error("DATA.json is required for fill mode")
    if not args.output:
        parser.error("-o OUTPUT.pdf is required for fill mode")

    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # argparse exit code 2 collides with our domain codes only if
        # we'd reused 2 ourselves — we don't. Use parser.error which
        # exits 2 to keep "bad input" errors uniform.
        parser.error(f"Invalid JSON in {args.data}: {exc}")
    if not isinstance(data, dict):
        parser.error(f"{args.data} must hold a JSON object {{field: value}}.")

    try:
        report = fill(args.input, data, args.output, flatten=args.flatten)
    except FormError as ex:
        if ex.kind == "xfa":
            return report_error(
                f"{args.input} is an XFA form — pypdf cannot fill it. "
                "Re-author as AcroForm or use commercial tooling.",
                code=EXIT_XFA, error_type="XFAForm",
                details={"path": str(args.input)}, json_mode=je,
            )
        if ex.kind == "no_form":
            return report_error(
                f"{args.input} has no AcroForm. For non-fillable PDFs use "
                "the visual-overlay path (see references/forms.md).",
                code=EXIT_NO_FORM, error_type="NoAcroForm",
                details={"path": str(args.input)}, json_mode=je,
            )
        return report_error(
            f"FormError: {ex}",
            code=EXIT_FILL_ERROR, error_type="FormError", json_mode=je,
        )
    except Exception as ex:  # pypdf write/clone failure on broken PDFs
        return report_error(
            f"Fill failed: {type(ex).__name__}: {ex}",
            code=EXIT_FILL_ERROR, error_type=type(ex).__name__,
            json_mode=je,
        )

    try:
        write_json_stdout(report, indent=2)
    except BrokenPipeError:
        return _stdout_broken_pipe(je)
    if report["skipped_unknown_fields"]:
        # Not an error per se, but worth surfacing — typo in field
        # name is the most common reason a fill "looks right" but
        # the field stays empty.
        print(f"WARN: {len(report['skipped_unknown_fields'])} field(s) in {args.data} "
              "did not match any AcroForm field; check spelling.", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
