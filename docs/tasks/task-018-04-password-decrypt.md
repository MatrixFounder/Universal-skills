# Task 018-04 [LOGIC IMPLEMENTATION]: `--password` decrypt-to-temp (post-MVP)

> **Predecessor:** 018-03. **Post-MVP — gated separately (D-A2). Run only if
> prioritized.**
> **RTM:** **completes** [R5] (a/b/c).
> **ARCH:** §2.1 (FC-5 R5 pre-decrypt), §7 (S-3 temp lifecycle), §12 (D-A2, D-A3).

## Use Case Connection

- UC-4 — encrypted scanned PDF → decrypt → OCR → searchable (unencrypted) output.

## Task Goal

Implement `--password`: because ocrmypdf does **not** accept an input password
natively (D-A3), decrypt with `pikepdf` to a `0600` temp in the OUTPUT directory,
feed that temp to `run_ocr`, and shred the temp in `finally`. Encrypted-without-
or wrong-password fails loud (exit 1, `EncryptedInput`), never silent.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_ocr.py`

**Function `_decrypt_to_temp(inp: Path, password: str, out_dir: Path) -> Path`**
(new helper):
- `import pikepdf` (transitive ocrmypdf dep; lazy, mapped to
  `OcrEngineUnavailable` if somehow absent).
- `try: pdf = pikepdf.open(inp, password=password)` →
  `except pikepdf.PasswordError: raise _OcrError("Wrong or missing password for
  encrypted input.", error_type="EncryptedInput")`.
- Save to a `NamedTemporaryFile(dir=out_dir, suffix=".dec.pdf", delete=False)`
  created with mode `0600` (`os.open(..., 0o600)` then `pdf.save(fd)`), return
  its Path.

**Function `run_ocr` (wire the pre-stage):**
- At the top, `decrypted = None`; if `password` is not None:
  `decrypted = _decrypt_to_temp(inp, password, outp.parent)` and use `decrypted`
  as the ocrmypdf input instead of `inp`.
- In the existing `try/finally`, also unlink `decrypted` if set (S-3 — shred on
  success **and** failure).

**Exception mapping (extend FC-6):** ensure an `EncryptedPdfError` surfaced by
ocrmypdf when **no** `--password` was supplied still maps to `EncryptedInput`
with a "supply --password" hint (so the no-password case is as loud as the
wrong-password case).

## Test Cases

### E2E Tests (engine-gated — soft-skip without engine)
1. **TC-E2E-07 `test_encrypted_roundtrip`** — build an encrypted scan fixture
   (`_pdf_ocr_fixtures.build_encrypted_scan(path, "test-pw")` — add to the
   builder); `pdf_ocr.py enc.pdf out.pdf --password test-pw` → exit 0; output is
   a searchable, **unencrypted** PDF (opens without a password); `pdf_extract`
   reads the needle.
2. **TC-E2E-08 `test_encrypted_wrong_password`** — wrong `--password` → exit 1,
   `type == EncryptedInput`.
3. **TC-E2E-09 `test_encrypted_no_password`** — encrypted input, no `--password`
   → exit 1, `EncryptedInput` with a "supply --password" hint.

### Unit Tests
1. **TC-UNIT-17 `test_decrypt_temp_mode_0600`** — the temp is created `0600`.
2. **TC-UNIT-18 `test_decrypt_temp_shredded`** — temp is unlinked on both the
   success and the failure path (patch `run_ocr`'s inner call to raise).
3. **TC-UNIT-19 `test_wrong_password_maps`** — `_decrypt_to_temp` with a bad
   password raises `_OcrError(type="EncryptedInput")`.

### Regression Tests
- Full pdf unittest suite + `test_e2e.sh` green; MVP paths unaffected.

## Acceptance Criteria

- [ ] `--password` decrypts via pikepdf to a `0600` temp in OUTPUT dir, OCRs it,
      shreds the temp on every path ([R5a], S-3, I-3).
- [ ] Wrong/absent password on encrypted input → exit 1 `EncryptedInput`, loud
      ([R5b]).
- [ ] `--password` argv-visibility documented in `--help` + `references/ocr.md`
      ([R5c]) — update the honest-scope note in `ocr.md`.
- [ ] Output is unencrypted (re-encryption out of scope — documented).
- [ ] `validate_skill.py skills/pdf` exit 0; cross-skill `diff -q` silent.

## Stub-First Gate

Self-contained logic bead — the decrypt helper + its units are added/green;
the encrypted E2E is engine-gated (soft-skip). Updates `references/ocr.md` +
`SKILL.md` password note in the same task.

## Notes

- pikepdf is already pulled transitively by ocrmypdf (ARCH §6) — no new line in
  `requirements-ocr.txt` unless the floor needs pinning.
- Keep the decrypted temp inside `outp.parent` so it shares the filesystem and
  never lands in a world-readable `/tmp` on a multi-user host.
