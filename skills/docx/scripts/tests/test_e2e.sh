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

# --- cross-5: --json-errors envelope --------------------------------------
echo "cross-5 unified errors:"
# Default (plain) mode: stderr is a free-form line.
set +e
err=$("$PY" docx_fill_template.py /nope.docx "$TMP/data.json" "$TMP/_z.docx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] && echo "$err" | grep -q "not found" \
    && ok "plain stderr: 'not found'" \
    || nok "plain mode" "exit=$rc msg=$err"

# JSON mode: stderr is a single line of valid JSON with the documented keys.
set +e
err=$("$PY" docx_fill_template.py /nope.docx "$TMP/data.json" "$TMP/_z.docx" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==1 and j['type']=='FileNotFound', j" 2>/dev/null \
    && ok "--json-errors envelope: code+type set" \
    || nok "--json-errors" "exit=$rc msg=$err"

# --- cross-4: macro detection (docx) --------------------------------------
echo "cross-4 macro warnings:"
# Build a minimal macro-enabled .docm by patching fixture.docx
"$PY" -c "
import zipfile, shutil
shutil.copy('$TMP/out.docx', '$TMP/macro.docm')
with zipfile.ZipFile('$TMP/macro.docm', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
ct = data['[Content_Types].xml'].decode('utf-8')
ct = ct.replace(
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
    'application/vnd.ms-word.document.macroEnabled.main+xml',
)
data['[Content_Types].xml'] = ct.encode('utf-8')
data['word/vbaProject.bin'] = b'fake-vba'
with zipfile.ZipFile('$TMP/macro.docm', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
"
# Pure-detection unit-style smoke through a small Python expression — no need
# to involve any heavy CLI. Catches a regression in is_macro_enabled_file().
"$PY" -c "
from office._macros import is_macro_enabled_file
from pathlib import Path
assert is_macro_enabled_file(Path('$TMP/macro.docm')) is True
assert is_macro_enabled_file(Path('$TMP/out.docx')) is False
" \
    && ok "is_macro_enabled_file: True for .docm, False for .docx" \
    || nok "is_macro_enabled_file" "detection mismatch"

# Mismatched extension warning fires on writer scripts.
set +e
err=$("$PY" docx_fill_template.py "$TMP/macro.docm" "$TMP/data.json" "$TMP/lossy.docx" 2>&1)
set -e
echo "$err" | grep -q "macro-enabled" \
    && echo "$err" | grep -q ".docm" \
    && ok "writer warns when .docm → .docx (macros lost)" \
    || nok "macro-loss warning" "no warning in stderr: $err"

# Matching extension: writer must NOT print the macro warning.
set +e
err=$("$PY" docx_fill_template.py "$TMP/macro.docm" "$TMP/data.json" "$TMP/preserve.docm" 2>&1)
set -e
n_warns=$(echo "$err" | grep -c "macro-enabled" || true)
[ "$n_warns" -eq 0 ] \
    && ok ".docm → .docm produces no macro-loss warning" \
    || nok "false-positive macro warning" "warned $n_warns times"

# unpack also surfaces a one-time note on macro-enabled inputs.
set +e
err=$("$PY" -m office.unpack "$TMP/macro.docm" "$TMP/macro_unpacked/" 2>&1 >/dev/null)
set -e
echo "$err" | grep -q "macro-enabled" \
    && ok "office.unpack notes macro-enabled input" \
    || nok "unpack macro note" "no note: $err"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
