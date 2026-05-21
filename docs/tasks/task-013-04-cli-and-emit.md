# Task 013-04 [LOGIC IMPLEMENTATION]: CLI glue + JSON emitter

> **Predecessor:** 013-03 (scan classifier).
> **RTM:** **completes** [R9]; [R7] sub-feature 7.3 (output sink); advances [R12] (E2E green per `tdd-stub-first §2.4`).
> **ARCH:** §2.1 FC2/FC5, §5.1, §5.2, §5.3, §5.4.

## Use Case Connection

- UC-1 main — digital PDF → dump emitted (exit 0).
- UC-2 (all) — whole-doc scan → exit 10; A1 — `--json-errors` envelope.
- UC-3 — full exit-code matrix exercised by tests.

## Task Goal

Replace the `main` and `_emit` stubs with the real CLI front-end and JSON
emitter, wiring the complete contract from ARCH §5: exit-code matrix
{0,1,2,10}, `--json-errors` envelope, idempotent output, `--password`
plumb-through, and the whole-doc-scan loud signal. After this task the full
E2E suite is green, including the encrypted success path (TASK R12.7).

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_extract.py`

**Function `_emit(dump, out_path)`** — implement:
- `text = json.dumps(dump, ensure_ascii=False, indent=2)`.
- `out_path is None` → write `text` to **stdout**.
- else → write `text` to `out_path` (overwrite — idempotent, ARCH §5.4 / D4).
- stdout always carries the dump, never the envelope (ARCH §5.2, reviewer M-3).

**Function `main(argv=None)`** — implement (remove `_STUB_SENTINEL`):
- Build parser, `parse_args(argv)`; argparse usage errors already routed to
  exit 2 / `UsageError` via `add_json_errors_argument` (013-01).
- Resolve `INPUT` → `Path`; if missing → `report_error(..., code=_EXIT_FAIL,
  error_type="InputNotFound", json_mode=args.json_errors)`.
- `try:` `dump = extract_pdf(input_path, password=args.password,
  layout=args.layout)`.
  - `except _ExtractError as e:` → `report_error(e.message, code=_EXIT_FAIL,
    error_type=e.type, json_mode=...)`; return `_EXIT_FAIL`.
  - `except Exception as e:` (catch-all) → `report_error("Internal error: …",
    code=_EXIT_FAIL, error_type="InternalError", json_mode=...)`; return
    `_EXIT_FAIL`.
- `_emit(dump, args.output)` — the dump is written on **every** non-usage path,
  including a whole-doc scan.
- If `dump["doc_scanned"]` → write the remediation message to stderr
  (`report_error("Document appears scanned/image-only — N pages, 0 extractable
  text. Run OCR (ocrmypdf) or render pages as images with the Read tool; see
  references/pdf-to-markdown.md.", code=_EXIT_SCANNED,
  error_type="DocumentScanned", details={"page_count": …},
  json_mode=args.json_errors)`) and `return _EXIT_SCANNED`.
- Else, if `dump["scanned_pages"]` non-empty (partial scan) → stderr **warning**
  naming the pages (`"pages 9, 10 appear scanned"`) — not an error envelope,
  just a warning line; `return _EXIT_OK`.
- Else → `return _EXIT_OK`.

### Component Integration

`main` is the single integration point — it ties `_build_parser` (013-01),
`extract_pdf` (013-02), the classifier verdict (013-03), and `_emit` together.

## Test Cases

### E2E Tests (final — all real assertions)

1. **TC-E2E-04 `test_cli_digital_stdout`** — subprocess `pdf_extract.py
   digital.pdf` → exit 0; stdout parses as JSON with `doc_scanned false`,
   `page_count 2`.
2. **TC-E2E-05 `test_cli_digital_file_output`** — `pdf_extract.py digital.pdf
   -o OUT.json` → exit 0; `OUT.json` is the dump; stdout empty.
3. **TC-E2E-06 `test_cli_scanned_exit10`** — `pdf_extract.py scanlike.pdf` →
   exit 10; stdout still carries the JSON dump (`doc_scanned true`); stderr
   names OCR / the Read tool.
4. **TC-E2E-07 `test_cli_scanned_json_errors`** — `pdf_extract.py scanlike.pdf
   --json-errors` → exit 10; stderr line parses as JSON `{"v":1, "code":10,
   "type":"DocumentScanned", …}`; stdout still carries the dump.
5. **TC-E2E-08 `test_cli_encrypted_success`** — `pdf_extract.py encrypted.pdf
   --password test-pw` → exit 0, correct dump (TASK R12.7).
6. **TC-E2E-09 `test_cli_encrypted_fail`** — `pdf_extract.py encrypted.pdf`
   (no password) → exit 1; `--json-errors` → envelope `type:"EncryptedPDF"`.
7. **TC-E2E-10 `test_cli_missing_input`** — `pdf_extract.py nope.pdf` → exit 1,
   `type:"InputNotFound"`.
8. **TC-E2E-11 `test_cli_usage_error`** — `pdf_extract.py` (no INPUT)
   `--json-errors` → exit 2, envelope `type:"UsageError"`.
9. **TC-E2E-12 `test_cli_idempotent`** — running TC-E2E-05 twice → byte-identical
   `OUT.json` (TASK R12.4).

### Unit Tests

1. **TC-UNIT-21 `test_emit_stdout`** — `_emit(dump, None)` writes valid JSON to
   stdout.
2. **TC-UNIT-22 `test_emit_file_overwrite`** — `_emit` to an existing file
   overwrites it; second call → identical bytes.
3. **TC-UNIT-23 `test_main_exit_matrix`** — `main` **returns** `0` / `1` / `10`
   directly for the digital / missing-input / whole-doc-scan cases. The `2` /
   `UsageError` path is NOT asserted here (a direct `main([])` raises
   `SystemExit(2)` from argparse rather than returning) — it is exercised by
   TC-E2E-11 instead. Together TC-UNIT-23 + TC-E2E-11 cover the full
   {0,1,2,10} matrix (TASK R12.5).
4. **TC-UNIT-24 `test_emit_json_indent`** — emitted JSON uses `indent=2`,
   `ensure_ascii=False` (non-ASCII text survives).

### Regression Tests

- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_extract` — all green.
- `bash skills/pdf/scripts/tests/test_e2e.sh` — pre-existing pdf suite green.

## Acceptance Criteria

- [ ] `main` + `_emit` fully implemented; `_STUB_SENTINEL` removed.
- [ ] Exit-code matrix asserted: `0`/`1`/`2`/`10` (TASK R12.5).
- [ ] Whole-doc scan → exit 10, dump still on stdout/`-o`, stderr remediation
      message ([R8] 8.3/8.5, [R9]).
- [ ] `--json-errors` produces a `v=1` envelope for `DocumentScanned`,
      `EncryptedPDF`, `InputNotFound`, and `UsageError` ([R9] 9.2, TASK R12.3).
- [ ] Encrypted PDF + correct `--password` → exit 0 (TASK R12.7).
- [ ] `-o` output overwrites idempotently (TASK R12.4); stdout carries the dump,
      never the envelope.
- [ ] Cross-skill `diff -q` silent (`_errors.py`, `preview.py`).
- [ ] Only `pdf_extract.py` + `test_pdf_extract.py` modified.

## Stub-First Gate (`tdd-stub-first §2`)

Last logic task — every stub in `pdf_extract.py` is now real. The E2E file
reaches its final form (TC-E2E-04..12). No `_STUB_SENTINEL` remains.

## Notes

- The partial-scan case (some pages scanned, document still text-extractable)
  is **exit 0** with a stderr *warning* — not an error envelope (ARCH §5.2 /
  TASK R8.4). Only a whole-document scan is exit 10.
- `report_error` (from `_errors`) already coerces `code=0`→1 and owns the
  envelope formatting — `main` only supplies `code`/`error_type`/`details`.
