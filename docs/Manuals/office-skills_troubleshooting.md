# Office Skills — Troubleshooting

One-stop reference for the failure modes that recur in production use
of `docx`/`xlsx`/`pptx`/`pdf`. Format: **Symptom → Cause → Fix**.

If a symptom isn't here, run the relevant skill's `test_e2e.sh` —
the failing assertion usually pinpoints the cause faster than reading
docs.

> Cross-references throughout point to:
> - [`office-skills_manual.md`](office-skills_manual.md) — the practical guide
> - [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — modification protocol & quality automation
> - per-skill `references/` — deep dives on specific topics

---

## 1. Install / runtime

### `weasyprint` cannot import — `OSError: cannot load library libpango-1.0.so.0`

**Cause.** `weasyprint` is pure Python but binds to native libs at
import time: `pango`, `cairo`, `gdk-pixbuf`, `harfbuzz`, `libffi`.

**Fix.**

```bash
# macOS
brew install pango gdk-pixbuf libffi

# Debian/Ubuntu
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                 libcairo2 libgdk-pixbuf2.0-0 libfontconfig1

# Fedora
sudo dnf install pango gdk-pixbuf2 cairo libffi
```

Then re-run `bash skills/pdf/scripts/install.sh` — the script's last
step probes `import weasyprint` and surfaces native-lib failures
explicitly.

### `mmdc not found` / mermaid blocks render as a code fence

**Cause.** Either Node isn't installed, or
`skills/{pdf,pptx}/scripts/install.sh` failed silently when running
`npm install`, or `~/.cache/puppeteer/` was wiped and Chromium
hasn't been re-fetched.

**Fix.**

```bash
# Make sure node is on PATH
node --version    # must be >= 18

# Reinstall + verify the binary
cd skills/pdf/scripts && bash install.sh
ls -l node_modules/.bin/mmdc       # must be executable
./node_modules/.bin/mmdc --version  # triggers Chromium fetch if missing
```

If you want mermaid to **fail loudly** instead of degrading silently
to a code fence, use `--strict-mermaid` (md2pdf) or call mmdc with a
broken syntax fixture and check that exit ≠ 0 — see
[`skills/pdf/examples/fixture-mermaid-broken.md`](../../skills/pdf/examples/fixture-mermaid-broken.md).

### `soffice timed out after 240s`

**Cause.** First-run cold-start of LibreOffice headless takes 10–15 s
just to write the user profile. Anti-virus scanners on Windows /
WSL can push this to several minutes.

**Fix.** The default 240-s timeout is generous. If it actually times
out:

1. Run `soffice --headless --convert-to pdf /tmp/anything.docx` once
   manually — the second-run profile is much faster.
2. If still slow, override the per-call timeout. `preview.py` and
   `pptx_thumbnails.py` accept `--soffice-timeout SECONDS`.
3. On Linux servers with long startup, consider keeping soffice warm
   via a cron-pinned `soffice --headless` background process (see
   [`office-skills_manual.md` §7](office-skills_manual.md#7-sandboxed-deployment-notes-ld_preload-shim)).

### `[Errno 13] Permission denied: '/.../soffice'` in a sandbox

**Cause.** LibreOffice spawns a child process that needs `AF_UNIX`
sockets; many Linux sandboxes (Docker without `--privileged`, Kata,
gVisor) refuse them.

**Fix.** Use the `LD_PRELOAD` shim shipped at
[`skills/docx/scripts/office/shim/lo_socket_shim.c`](../../skills/docx/scripts/office/shim/lo_socket_shim.c).
Build with `bash office/shim/build.sh`, export
`LD_PRELOAD=/path/to/lo_socket_shim.so` before invoking soffice.
**Important limitation locked in by tests:** the shim does NOT
provide cross-process IPC (it makes `bind/listen/accept` succeed
in-process). Multi-process LibreOffice features (Calc cell-recalc
dispatcher) are not supported under the shim. See the
file-level docstring in
[`lo_socket_shim.c`](../../skills/docx/scripts/office/shim/lo_socket_shim.c)
for the design rationale.

---

## 2. Encrypted / legacy input

### `Not a ZIP-based OOXML container; looks like CFB ... password-protected or legacy .doc/.xls/.ppt` (exit 3)

**Cause.** The file is either password-protected (Office 2010+ Agile
encryption — CFB container) or a legacy `.doc`/`.xls`/`.ppt` (CFB
container without encryption). All eight reader scripts share the
same `office._encryption.assert_not_encrypted()` pre-flight that
exits **3** with this message rather than letting `BadZipFile`
propagate as an opaque traceback.

**Fix.**

- If password-protected: decrypt first with cross-7's
  `office_passwd.py`:
  ```bash
  ./.venv/bin/python skills/docx/scripts/office_passwd.py \
      ENCRYPTED.docx CLEAN.docx --decrypt PASSWORD
  ```
  Pass `-` as the password to read it from stdin (avoids leaking
  via `ps` / shell history). Then feed `CLEAN.docx` to the reader.

- If legacy: open in LibreOffice and Save As `.docx`/`.xlsx`/`.pptx`,
  or run `soffice --headless --convert-to docx LEGACY.doc`.

### `office_passwd.py --encrypt` exit 5: "already encrypted"

**Cause.** State-mismatch guard: `--encrypt` requires a clean OOXML
input and `--decrypt` requires a CFB-encrypted input. Calling either
on the wrong state aborts with **exit 5** before any file write —
prevents accidentally double-encrypting.

**Fix.** Run `--check` first to gate behavior:

```bash
./.venv/bin/python skills/docx/scripts/office_passwd.py FILE.docx --check
#   exit 0  → encrypted (so you want --decrypt)
#   exit 10 → not encrypted (so you want --encrypt)
#   exit 11 → input not found
```

### `office_passwd.py --decrypt` exit 4: "wrong password"

**Cause.** Password didn't decrypt. The output file is **deleted**
to avoid a 0-byte decoy. See [`office-skills_manual.md` §9.5
cross-7](office-skills_manual.md#cross-7-realпароль-passwords-set--remove)
for the full exit-code table.

**Fix.** Try again with the correct password. For passwords with
shell-special characters, pipe via stdin: `printf 'PA$$' | ... --decrypt -`.

---

## 3. Visual regression (q-2)

### `golden not found: tests/visual/goldens/.../foo.png`

**Cause.** No golden has been recorded for this fixture/output yet,
OR you're on a fresh branch and the golden hasn't been regenerated
on the matching CI runner image.

**Fix locally.**

```bash
UPDATE_GOLDENS=1 bash skills/<skill>/scripts/tests/test_e2e.sh
git diff tests/visual/goldens/   # review
git add tests/visual/goldens/<skill>/foo.png
```

**Fix in CI.** Trigger the workflow with `workflow_dispatch` and
`update_goldens=true`; download the per-skill artifact, commit, push.
Without `STRICT_VISUAL=1` (which CI sets), missing goldens warn-and-
skip rather than fail.

### `visual diff 12345 > threshold 2350`

**Cause.** First page of the produced PDF differs from the golden
by more than 0.5% of total pixels (the default tolerance, after a
5%-fuzz per-pixel color delta). Common reasons in order of
frequency:

1. **Cross-platform drift.** Goldens generated on macOS won't
   typically match Ubuntu CI rendering even with identical inputs
   (different fontconfig, different Cairo version). Regenerate on
   the matching runner.
2. **Real regression.** Something genuinely changed — heading shifted,
   table column-width drifted, font fallback chain produced different
   glyphs.
3. **Library bump.** A new LibreOffice / weasyprint / mmdc version
   produces deliberately different output.

**Fix.**

```bash
# Inspect the diff visually first — IM produces a difference image
magick compare -metric AE -fuzz 5% \
    tests/visual/goldens/pdf/fixture-base.png \
    /tmp/captured.png \
    /tmp/diff.png && open /tmp/diff.png

# If the drift is intentional, regenerate the golden:
UPDATE_GOLDENS=1 bash skills/pdf/scripts/tests/test_e2e.sh
```

If you need to widen tolerance for a specific golden (e.g. mermaid
output is inherently noisier than typeset text), pass
`--threshold-pct 2.0` in the relevant `visual_check` call.

### "ImageMagick `compare` not found"

**Cause.** Local dev box without ImageMagick.

**Fix.**

```bash
brew install imagemagick      # macOS
sudo apt install imagemagick  # Debian/Ubuntu
```

Or just ignore — without `STRICT_VISUAL=1`, the comparator
warn-and-skips so existing E2E runs stay green. CI installs IM in
the workflow setup step.

---

## 4. Property-based fuzz (q-5)

### `hypothesis.errors.FailedHealthCheck: function-scoped fixture 'tmp_path'`

**Cause.** Pytest's `tmp_path` fixture is function-scoped; Hypothesis
(rightly) refuses to reuse it across `@given(...)`-generated inputs
because state leaks would cause non-deterministic failures.

**Fix.** Use a per-example tempdir via context manager (already done
in all three test modules):

```python
import tempfile

@given(md=markdown_doc)
def test_thing(md, ...):
    with tempfile.TemporaryDirectory(prefix="prop-") as work:
        # ... use Path(work) as the per-example workspace
```

### Fuzz takes too long in CI

**Cause.** `HYPOTHESIS_PROFILE=ci` runs 100 examples per test (3
tests × 100 × ~0.3 s/example ≈ 1.5 min). On a cold CI runner with
slow LibreOffice imports it can stretch to 4–5 min.

**Fix.** If a single example exceeds the per-example deadline
(`30_000` ms in `ci`), Hypothesis emits an unmistakable
`Flaky` error. Diagnose:

```bash
# Run with statistics to see per-example timings
tests/property/.venv/bin/pytest tests/property \
    --hypothesis-show-statistics -v
```

Don't loosen the deadline blindly — if md2pdf is taking 30+ s on a
small input, that's a real perf regression worth investigating.

---

## 5. Output / format issues

### Cyrillic / CJK text in mermaid diagrams renders as boxes

**Cause.** mmdc's built-in default font (Trebuchet MS) has no
glyphs for Cyrillic / CJK on most Linux servers. The bundled
`scripts/mermaid-config.json` (cross-6) replaces it with
`Arial Unicode MS → Noto Sans → DejaVu Sans → Liberation Sans →
Arial → sans-serif`, all of which have broad coverage.

**Fix.** Make sure you're using the bundled config (the default
when neither `--mermaid-config` nor `--no-mermaid-config` is on
the CLI). To verify a specific config is being applied:

```bash
md2pdf.py doc.md doc.pdf --mermaid-config /tmp/mine.json
```

If you see a `[md2pdf] WARN: --mermaid-config X does not exist`
banner, the path was wrong and it fell back to mmdc defaults.
Pass `--strict-mermaid` to fail loudly instead.

### Mermaid PNG looks pixelated in the PDF

**Cause.** PDF rendering scales the PNG to fit the page (`max-width:
100%`) and a low-resolution PNG gets upscaled. The bundled
`md2pdf.py` calls mmdc with `--scale 2`, which usually yields
crisp output. For very large mindmaps that span the full page,
increase the scale.

**Fix.** There's no CLI knob today; edit your
`mermaid-config.json` to raise font-size, or pre-render the diagram
manually via `mmdc --scale 3 -o big.png` and reference the PNG via
plain markdown image syntax.

### `xlsx_recalc` formulas show up as `=A1+B1` instead of computed values

**Cause.** openpyxl writes formulas as strings without a cached
result. Most consumers (pypdf, pandas-via-openpyxl, mobile Excel)
rely on the cached value. Without a recalc pass the cells display
"#N/A" or the formula text itself.

**Fix.** Run the openpyxl output through `xlsx_recalc.py`, which
opens the file in headless LibreOffice and triggers a full
recalculation:

```bash
./.venv/bin/python skills/xlsx/scripts/xlsx_recalc.py \
    INPUT.xlsx RECALCED.xlsx
```

See [`skills/xlsx/references/formula-recalc-gotchas.md`](../../skills/xlsx/references/formula-recalc-gotchas.md)
for the full list of cases where openpyxl's formula handling
diverges from Excel.

### `pdf_fill_form --check` exits 11 ("XFA, NOT fillable via pypdf")

**Cause.** The PDF uses Adobe LiveCycle XFA — a separate form
technology that pypdf can't fill. Roughly 5–10 % of corporate
forms (especially government / banking) are XFA. There is no
practical fix without Adobe Acrobat Pro.

**Fix.** Either:

1. Ask the form publisher for a non-XFA AcroForm version (most
   modern forms are dual-encoded), OR
2. Use Acrobat Pro / Foxit to "Save As → AcroForm" — strips the
   XFA layer.

The `pdf_fill_form` exit-code table is in
[`skills/pdf/references/forms.md`](../../skills/pdf/references/forms.md).

---

## 5b. `docx_merge.py` (real-world Word documents)

The merger was hardened iteratively against real Word-authored
inputs. If you see one of these symptoms after a merge, the fix is
already in place — double-check you're on a recent build:

### Word: "обнаружено содержимое, которое не удалось прочитать" (couldn't read content)

**Cause.** One of three things, in order of frequency:

1. Extra's media files (PNG / GIF) have no MIME mapping in
   `[Content_Types].xml` — base only had `Default Extension="jpeg"`
   and we copied PNG bytes in.
2. Extra body has paragraph-level `<w:sectPr>` with
   `<w:headerReference>`/`<w:footerReference>` pointing at extra's
   header/footer parts that we don't merge — refs end up resolving
   to base's rels with a different content type.
3. Numbering definitions appended in the wrong schema order
   (`<w:abstractNum>` after `<w:num>` violates ECMA-376 §17.9.20).

**Fix.** All three are handled in iter-2 of `docx_merge.py`:
`_merge_content_types_defaults` pulls missing `<Default Extension>`,
`_strip_paragraph_section_breaks` removes inline sectPr with
header/footer refs, and `_merge_numbering` inserts new abstractNums
BEFORE the first `<w:num>`. If you still see this on a fresh
build, run [`office.validate`](../../skills/docx/scripts/office/validate.py)
on the merged file — it will surface the specific class of issue.

### Headings on later pages render as bulleted "o" markers post-merge

**Cause.** Schema-order violation in `numbering.xml` →  Word
auto-repairs at open time, and during the repair pass the binding
of base's heading-style numIds gets mangled. (Specifically: appended
`<w:abstractNum>` elements landed AFTER existing `<w:num>` elements;
ECMA-376 forbids that order.)

**Fix.** Already in iter-2.3 — `_merge_numbering` now inserts new
abstractNums at the position of the first existing `<w:num>` and
appends new nums before `<w:numIdMacAtCleanup>` if it exists. To
verify a merged file:

```bash
python -c "
import zipfile
from lxml import etree
with zipfile.ZipFile('merged.docx') as z:
    root = etree.fromstring(z.read('word/numbering.xml'))
order = [etree.QName(c).localname for c in root]
saw_num = False; bad = 0
for tag in order:
    if tag == 'num': saw_num = True
    if tag == 'abstractNum' and saw_num: bad += 1
print('abstractNum-after-num violations:', bad, '(must be 0)')
"
```

### "Этот файл заблокирован для правки. Кем заблокирован: другим пользователем"

**Cause.** This is **not** a merge bug. Word reports it when a
lock file `~$<filename>.docx` is present in the same directory
(another Word session held a write-lock and didn't clean up), or
when OneDrive/Box/SharePoint sync holds the file. Neither input
nor output need `<w:documentProtection>` for this dialog to fire.

**Fix.**

```bash
# Close ALL Word windows, then remove the lock file
rm tmp/test-data/~$merged_*    # macOS / Linux
del "tmp\test-data\~$merged_*" # Windows cmd
```

Re-open the merged file. If it still says locked, check whether the
file itself is read-only (`chmod +w` / right-click → Properties).

### Merged file silently drops list continuity from extra

**Cause.** Iter-2 merges numbering definitions with offset, but if
extra's numbering relies on `<w:numStyleLink>` / `<w:styleLink>` to
chain into a base-style ID that has different semantics, the
appended list will use base's chain instead of extra's. Rare in
practice (md2docx and most Word documents define numbering inline,
not via style chains).

**Fix.** Either pre-flight extras through `office.unpack` and
manually inline the list `<w:lvl>` elements before merge, or accept
the visual difference. Future iter-3 may address numStyleLink
remapping if user demand surfaces.

---

## 6. Environment / CI

### CI fails with "validate_skill.py: not found" or skill validation 0/0

**Cause.** Workflow expects the **tracked** path
`skills/skill-creator/scripts/validate_skill.py` (committed to the
repo). The locally-cached `.claude/skills/skill-creator/...` path
referenced in CLAUDE.md exists only on developer machines.

**Fix.** Already fixed in the workflow — but if you're customizing
CI elsewhere, point at the tracked path.

### Cache-hit but old deps — pip install runs anyway

**Cause.** `actions/cache@v4` keys the per-skill cache on
`requirements.txt` + `package.json` content. If neither changed, the
cache hits and `install.sh` skips the reinstall step (it's
idempotent). System-tool changes (apt-installed pango etc.) are NOT
keyed and won't bust the cache — but they're installed every run
anyway.

**Fix.** Edit the requirements file (even adding a comment) to bust
the cache, or manually clear via the GitHub UI under Actions →
Caches.

### `magick: command not found` in CI but local works

**Cause.** ImageMagick v7 ships `magick`; v6 ships standalone
`compare`. Different distros / different `apt install imagemagick`
versions install different binaries. The visual_compare tool tries
both via `_find_compare()`.

**Fix.** Both v6 and v7 are accepted — if neither is found,
`STRICT_VISUAL=1` makes it a hard error (exit 4). The Ubuntu 22.04
runner's `apt install imagemagick` provides v6's standalone
`compare`, which works fine.

---

## 7. Where to look when this guide doesn't help

| Where | What you'll find |
|---|---|
| [`office-skills_manual.md`](office-skills_manual.md) §9.5 | Cross-skill safeguards (cross-1 / 4 / 5 / 7) — the big "shared error contracts" surface. |
| `skills/<skill>/SKILL.md` | Quick reference for that skill's CLIs and flags — the agent's primary discovery surface. |
| `skills/<skill>/references/*.md` | Deep dives: docx-js gotchas, openpyxl-vs-pandas, pptxgenjs basics, AcroForm vs XFA, weasyprint setup, financial-modeling conventions. |
| [`tests/visual/README.md`](../../tests/visual/README.md) | Visual regression tuning, golden-update workflow, cross-platform drift notes. |
| `bash skills/<skill>/scripts/tests/test_e2e.sh` | Self-contained reproducer for every contract — the assertion text usually pinpoints the failing path. |
| [`docs/refactoring-office-skills.md`](../refactoring-office-skills.md) | Historical design rationale — why an architecture decision was made (read-only; superseded by `CONTRIBUTING.md`). |
| [`docs/CONTRIBUTING.md`](../CONTRIBUTING.md) | The contributor protocol — replication rules, quality automation, commit hygiene. |
