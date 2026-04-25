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

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
