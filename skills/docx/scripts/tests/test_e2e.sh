#!/usr/bin/env bash
# End-to-end smoke tests for the docx skill.
#
# Round-trips fixture-simple.md → .docx → .md and exercises the
# template-fill path. Validates each output with office/validate.
#
# Run:  bash skills/docx/scripts/tests/test_e2e.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t docx_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

# --- md2docx ----------------------------------------------------------------
echo "md2docx:"
node md2docx.js ../examples/fixture-simple.md "$TMP/out.docx" >/dev/null 2>&1 \
    && [ -s "$TMP/out.docx" ] && ok "fixture.md → out.docx" \
    || nok "fixture.md → out.docx" "missing or empty"

# Validate with our own validator (zip integrity + XML schema where present)
"$PY" -m office.validate "$TMP/out.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts md2docx output" \
    || nok "office.validate" "rejected the produced .docx"

# --- docx2md (round-trip) --------------------------------------------------
echo "docx2md:"
node docx2md.js "$TMP/out.docx" "$TMP/back.md" >/dev/null 2>&1 \
    && [ -s "$TMP/back.md" ] && ok "out.docx → back.md" \
    || nok "out.docx → back.md" "missing or empty"

# Round-trip should preserve at least the heading text and table cells
grep -q "Quarterly report" "$TMP/back.md" \
    && ok "heading text preserved" \
    || nok "heading text" "lost in round-trip"
grep -q "915,000" "$TMP/back.md" \
    && ok "table cell preserved" \
    || nok "table cell" "lost in round-trip"

# --- docx_fill_template ---------------------------------------------------
echo "docx_fill_template:"
# docx_fill_template walks dotted keys as nested JSON paths
# (customer.name → data["customer"]["name"]).
cat > "$TMP/data.json" <<'JSON'
{"customer": {"name": "Acme Inc."}, "invoice": {"total": "$1,234.56", "due_date": "2026-05-01"}}
JSON
"$PY" docx_fill_template.py "$TMP/out.docx" "$TMP/data.json" "$TMP/filled.docx" >/dev/null 2>&1 \
    && [ -s "$TMP/filled.docx" ] && ok "out.docx + data.json → filled.docx" \
    || nok "fill template" "produced empty/missing file"

"$PY" -m office.validate "$TMP/filled.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts filled output" \
    || nok "validate filled" "rejected the filled .docx"

# Round-trip the filled doc back to md and check substitutions landed
node docx2md.js "$TMP/filled.docx" "$TMP/filled.md" >/dev/null 2>&1
grep -q "Acme Inc." "$TMP/filled.md" \
    && ok "substitution: customer.name visible after round-trip" \
    || nok "substitution: customer.name" "not in re-extracted .md"

# --- encryption / legacy-CFB fail-fast -----------------------------------
echo "encryption fail-fast:"
# Same byte test catches encrypted .docx AND legacy .doc — both are
# CFB containers. The error message must mention BOTH possibilities so
# users hitting the legacy case aren't sent on a wild goose chase
# looking for a password.
"$PY" -c "
from pathlib import Path
Path('$TMP/cfb.docx').write_bytes(b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1' + b'\\x00' * 100)
"
set +e
err=$("$PY" docx_fill_template.py "$TMP/cfb.docx" "$TMP/data.json" "$TMP/_x.docx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && echo "$err" | grep -q "legacy" \
    && ok "docx_fill_template: exit 3 + message names both encrypted AND legacy" \
    || nok "encrypted rejection (fill_template)" "exit $rc / msg: $err"

# Same fixture, different reader script — verifies the wiring isn't
# specific to fill_template. Use a soffice-gated guard since
# docx_accept_changes goes through LibreOffice.
if command -v soffice >/dev/null 2>&1; then
    set +e
    err=$("$PY" docx_accept_changes.py "$TMP/cfb.docx" "$TMP/_y.docx" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 3 ] && echo "$err" | grep -q "CFB\|password-protected" \
        && ok "docx_accept_changes also refuses CFB with exit 3" \
        || nok "encrypted rejection (accept_changes)" "exit $rc / msg: $err"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
