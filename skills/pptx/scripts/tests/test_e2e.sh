#!/usr/bin/env bash
# End-to-end smoke tests for the pptx skill.
#
# Run:  bash skills/pptx/scripts/tests/test_e2e.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t pptx_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

# --- md2pptx ---------------------------------------------------------------
echo "md2pptx:"
node md2pptx.js ../examples/fixture-slides.md "$TMP/out.pptx" >/dev/null 2>&1 \
    && [ -s "$TMP/out.pptx" ] && ok "fixture-slides.md → out.pptx" \
    || nok "fixture-slides.md → out.pptx" "missing or empty"

"$PY" -m office.validate "$TMP/out.pptx" >/dev/null 2>&1 \
    && ok "office.validate accepts md2pptx output" \
    || nok "office.validate" "rejected the produced .pptx"

# Slide count: fixture has 4 horizontal-rule separated sections + title
slide_count=$(unzip -l "$TMP/out.pptx" | grep -cE "ppt/slides/slide[0-9]+\.xml$" || true)
[ "$slide_count" -ge 3 ] \
    && ok "expected ≥3 slides, got $slide_count" \
    || nok "slide count" "expected ≥3, got $slide_count"

# --- pptx_thumbnails -------------------------------------------------------
# Skip if soffice is missing; thumbnails go through LibreOffice.
if command -v soffice >/dev/null 2>&1; then
    echo "pptx_thumbnails:"
    "$PY" pptx_thumbnails.py "$TMP/out.pptx" "$TMP/thumbs.jpg" >/dev/null 2>&1 \
        && [ -s "$TMP/thumbs.jpg" ] && ok "out.pptx → thumbs.jpg" \
        || nok "thumbnails" "missing or empty"
    file "$TMP/thumbs.jpg" 2>/dev/null | grep -qE "JPEG|JFIF" \
        && ok "thumbnails output is JPEG" \
        || nok "JPEG check" "$(file "$TMP/thumbs.jpg" 2>/dev/null)"
else
    echo "pptx_thumbnails: skipped (soffice not on PATH)"
fi

# --- pptx_to_pdf -----------------------------------------------------------
if command -v soffice >/dev/null 2>&1; then
    echo "pptx_to_pdf:"
    "$PY" pptx_to_pdf.py "$TMP/out.pptx" "$TMP/out.pdf" >/dev/null 2>&1 \
        && [ -s "$TMP/out.pdf" ] && ok "out.pptx → out.pdf" \
        || nok "pptx_to_pdf" "missing or empty"
    head -c 5 "$TMP/out.pdf" | grep -q "%PDF" \
        && ok "PDF magic-bytes present" \
        || nok "PDF magic" "missing %PDF header"
else
    echo "pptx_to_pdf: skipped (soffice not on PATH)"
fi

# --- pptx_clean -----------------------------------------------------------
echo "pptx_clean:"
# Inject orphan slide99.xml + orphan media into a fresh copy of out.pptx
"$PY" -c "
import zipfile, shutil, os
shutil.copy('$TMP/out.pptx', '$TMP/dirty.pptx')
items = []
with zipfile.ZipFile('$TMP/dirty.pptx', 'r') as z:
    for n in z.namelist():
        items.append((n, z.read(n)))
items.append(('ppt/slides/slide99.xml',
              b'<?xml version=\"1.0\"?><p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree/></p:cSld></p:sld>'))
items.append(('ppt/media/image_orphan.png', b'\\x89PNG\\r\\n\\x1a\\n' + b'\\x00' * 100))
os.unlink('$TMP/dirty.pptx')
with zipfile.ZipFile('$TMP/dirty.pptx', 'w', zipfile.ZIP_DEFLATED) as z:
    for n, data in items:
        z.writestr(n, data)
"
"$PY" pptx_clean.py "$TMP/dirty.pptx" --output "$TMP/cleaned.pptx" >/dev/null 2>&1 \
    && [ -s "$TMP/cleaned.pptx" ] && ok "clean produced output" \
    || nok "clean" "missing output"

# Orphan slide and orphan media should be gone
post=$("$PY" -c "
import zipfile
files = zipfile.ZipFile('$TMP/cleaned.pptx').namelist()
print('orphan_slide=' + ('yes' if 'ppt/slides/slide99.xml' in files else 'no'))
print('orphan_media=' + ('yes' if 'ppt/media/image_orphan.png' in files else 'no'))
")
echo "$post" | grep -q "orphan_slide=no" \
    && ok "orphan slide99.xml removed" \
    || nok "orphan slide" "$post"
echo "$post" | grep -q "orphan_media=no" \
    && ok "orphan media removed" \
    || nok "orphan media" "$post"

# Cleaned file must still validate via office.validate
"$PY" -m office.validate "$TMP/cleaned.pptx" >/dev/null 2>&1 \
    && ok "cleaned pptx still validates" \
    || nok "validate after clean" "rejected"

# Dry-run should print what would be removed AND not write the output
rm -f "$TMP/_unused.pptx"
"$PY" pptx_clean.py "$TMP/dirty.pptx" --dry-run --output "$TMP/_unused.pptx" 2>&1 \
    | grep -q '"dry_run": true' \
    && ok "--dry-run reports" \
    || nok "dry-run reports" "no dry_run marker in output"
# The --output path was supplied but --dry-run won the early-return —
# the file must not exist. This guards against future refactors that
# accidentally move the write before the dry-run check.
[ ! -e "$TMP/_unused.pptx" ] \
    && ok "--dry-run did not write the output file" \
    || nok "dry-run leaked write" "$TMP/_unused.pptx exists"

# --- encryption / legacy-CFB fail-fast (pptx side) ------------------------
echo "encryption fail-fast:"
"$PY" -c "
from pathlib import Path
Path('$TMP/cfb.pptx').write_bytes(b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1' + b'\\x00' * 100)
"
set +e
err=$("$PY" pptx_clean.py "$TMP/cfb.pptx" --dry-run 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && echo "$err" | grep -q "legacy" \
    && ok "pptx_clean: exit 3 + message names both encrypted AND legacy" \
    || nok "encrypted rejection (clean)" "exit $rc / msg: $err"

if command -v soffice >/dev/null 2>&1; then
    set +e
    err=$("$PY" pptx_thumbnails.py "$TMP/cfb.pptx" "$TMP/_thumbs.jpg" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 3 ] && echo "$err" | grep -q "CFB\|password-protected" \
        && ok "pptx_thumbnails also refuses CFB with exit 3" \
        || nok "encrypted rejection (thumbnails)" "exit $rc / msg: $err"

    set +e
    err=$("$PY" pptx_to_pdf.py "$TMP/cfb.pptx" "$TMP/_x.pdf" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 3 ] && echo "$err" | grep -q "CFB\|password-protected" \
        && ok "pptx_to_pdf also refuses CFB with exit 3" \
        || nok "encrypted rejection (to_pdf)" "exit $rc / msg: $err"
fi

# --- outline2pptx (heading-only outline → slide skeleton) -----------------
echo "outline2pptx:"
cat > "$TMP/outline.md" <<'MD'
# Q2 Strategy

## Goals
- Hit 20% growth
- Launch 3 products

## Risks

### Short-term
- Supplier squeeze

### Long-term
- Currency volatility

## Next steps
MD
node outline2pptx.js "$TMP/outline.md" "$TMP/outline.pptx" >/dev/null 2>&1 \
    && [ -s "$TMP/outline.pptx" ] && ok "outline → outline.pptx" \
    || nok "outline → pptx" "missing or empty"

# Slide count: 1 title + 3 content (## headings) = 4
slides=$(unzip -l "$TMP/outline.pptx" 2>/dev/null | grep -cE "ppt/slides/slide[0-9]+\.xml$" || true)
[ "$slides" -eq 4 ] \
    && ok "outline → 4 slides (1 title + 3 content)" \
    || nok "outline slide count" "expected 4, got $slides"

# Output must validate via office.validate
"$PY" -m office.validate "$TMP/outline.pptx" >/dev/null 2>&1 \
    && ok "outline.pptx validates" \
    || nok "outline validate" "rejected"

# Empty / heading-less input → fail with clear error
echo "no headings here, just prose" > "$TMP/no_headings.md"
set +e
err=$(node outline2pptx.js "$TMP/no_headings.md" "$TMP/_x.pptx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -ne 0 ] && echo "$err" | grep -q "No headings" \
    && ok "outline2pptx fails clearly on heading-less input" \
    || nok "no-headings handling" "exit $rc / msg: $err"

# --- mermaid config bundling (cross-6) -----------------------------------
echo "bundled mermaid-config:"
[ -s mermaid-config.json ] && "$PY" -c "import json; json.load(open('mermaid-config.json'))" \
    && ok "bundled mermaid-config.json exists and parses" \
    || nok "bundled mermaid-config" "missing or invalid JSON"

# md2pptx --mermaid-config: pointing at non-existent file should fail cleanly
set +e
err=$(node md2pptx.js ../examples/fixture-slides.md "$TMP/_x.pptx" \
          --mermaid-config "$TMP/missing.json" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -ne 0 ] && echo "$err" | grep -q "does not exist" \
    && ok "md2pptx --mermaid-config: missing path exits non-zero" \
    || nok "md2pptx missing config" "exit $rc / msg: $err"

# --- cross-5: --json-errors envelope (pptx) ------------------------------
echo "cross-5 unified errors:"
set +e
err=$("$PY" pptx_to_pdf.py /nope.pptx --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==1 and j['type']=='FileNotFound' and j['v']==1, j" 2>/dev/null \
    && ok "pptx_to_pdf --json-errors envelope (v=1)" \
    || nok "pptx_to_pdf --json-errors" "exit=$rc msg=$err"

# Parameterized cross-5: every plumbed pptx CLI emits a JSON envelope.
for cli in pptx_thumbnails.py pptx_clean.py; do
    set +e
    out=$("$PY" "$cli" /nope.pptx --json-errors 2>&1 >/dev/null)
    set -e
    echo "$out" | "$PY" -c "import sys, json; json.loads(sys.stdin.read())" 2>/dev/null \
        && ok "  $cli emits JSON envelope" \
        || nok "  $cli envelope" "got: $out"
done

# --- cross-4: macro detection (pptx) -------------------------------------
echo "cross-4 macro warnings:"
"$PY" -c "
import zipfile, shutil
shutil.copy('$TMP/out.pptx', '$TMP/macro.pptm')
with zipfile.ZipFile('$TMP/macro.pptm', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
ct = data['[Content_Types].xml'].decode('utf-8')
ct = ct.replace(
    'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
    'application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml',
)
data['[Content_Types].xml'] = ct.encode('utf-8')
data['ppt/vbaProject.bin'] = b'fake-vba'
with zipfile.ZipFile('$TMP/macro.pptm', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
from office._macros import is_macro_enabled_file
from pathlib import Path
assert is_macro_enabled_file(Path('$TMP/macro.pptm')) is True
" \
    && ok "is_macro_enabled_file detects pptm" \
    || nok "pptm detection" "is_macro_enabled_file returned False"

set +e
err=$("$PY" pptx_clean.py "$TMP/macro.pptm" --output "$TMP/lossy.pptx" 2>&1)
rc=$?
set -e
echo "$err" | grep -q "macro-enabled" && [ "$rc" -eq 0 ] \
    && ok "pptx_clean warns when .pptm → .pptx" \
    || nok "macro-loss warning (pptx)" "exit=$rc msg=$err"

# --- pptx-4: PptxValidator deep checks ------------------------------------
echo "pptx-4 deep validation:"

# Real fixture must validate cleanly (regression: the slide/layout/master
# chain check easily produces false positives if path resolution is off).
"$PY" -m office.validate "$TMP/out.pptx" --json > "$TMP/_v.json" 2>&1
"$PY" -c "
import json
r = json.load(open('$TMP/_v.json'))
assert r['ok'] is True, r
assert not r['errors'], r
" \
    && ok "real pptx fixture: zero errors from deep validator" \
    || nok "real pptx clean validation" "got: $(cat $TMP/_v.json)"

# Inject an orphan slide → must produce a warning, not an error
"$PY" -c "
import zipfile, shutil
shutil.copy('$TMP/out.pptx', '$TMP/orphan.pptx')
with zipfile.ZipFile('$TMP/orphan.pptx', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
# Pick the first slide and copy it to slide99.xml without referencing it.
slide_bytes = data.get('ppt/slides/slide1.xml')
assert slide_bytes is not None, 'fixture has no ppt/slides/slide1.xml'
data['ppt/slides/slide99.xml'] = slide_bytes
with zipfile.ZipFile('$TMP/orphan.pptx', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
"
set +e
"$PY" -m office.validate "$TMP/orphan.pptx" --json > "$TMP/_o.json" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && "$PY" -c "
import json
r = json.load(open('$TMP/_o.json'))
assert any('Orphan slide part' in w and 'slide99' in w for w in r['warnings']), r
" \
    && ok "orphan slide → warning surfaced (slide99 not referenced)" \
    || nok "orphan slide detection" "exit=$rc out=$(cat $TMP/_o.json)"

# Strict-mode XSD probe: --strict promotes "XSD not bundled" to a
# warning, which then exits 1 (per validate.py: "warnings present when
# --strict"). On a checkout that has NOT run schemas/fetch.sh this is
# expected behaviour; we assert exit-1 + the specific warning shape so
# the test holds regardless of whether the schemas got fetched.
set +e
out=$("$PY" -m office.validate "$TMP/out.pptx" --strict --json 2>&1)
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
    ok "real pptx fixture passes --strict (schemas bundled)"
elif [ "$rc" -eq 1 ] && echo "$out" | grep -q "XSD not bundled"; then
    ok "real pptx --strict: exit 1 + 'XSD not bundled' (run schemas/fetch.sh)"
else
    nok "pptx --strict" "exit=$rc, expected 0 (schemas present) or 1 + bundle hint"
fi

# Unit-test suite for PptxValidator (9 tests; quick).
"$PY" -m unittest office.tests.test_pptx_validator 2>&1 | tail -1 | grep -q "^OK$" \
    && ok "office.tests.test_pptx_validator: all 9 unit tests pass" \
    || nok "PptxValidator unit tests" "see python -m unittest output"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
