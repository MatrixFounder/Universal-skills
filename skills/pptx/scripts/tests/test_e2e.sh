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

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
