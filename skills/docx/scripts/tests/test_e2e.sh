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

# argparse usage errors must ALSO honour --json-errors. Regression for
# VDD HIGH-1 (parser.error bypass): exit 2 with a JSON envelope of
# type=UsageError, NOT plain-text usage.
set +e
err=$("$PY" docx_fill_template.py --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='UsageError' and j['v']==1, j" 2>/dev/null \
    && ok "argparse usage error routed to JSON envelope (UsageError + v=1)" \
    || nok "usage-error envelope" "exit=$rc msg=$err"

# Schema version: every JSON envelope carries v=1 (regression for LOW-1).
set +e
err=$("$PY" docx_fill_template.py /nope.docx /nope.json /tmp/_z.docx --json-errors 2>&1 >/dev/null)
set -e
echo "$err" | "$PY" -c "import sys, json; assert json.loads(sys.stdin.read())['v']==1" 2>/dev/null \
    && ok "domain-error envelope carries v=1" \
    || nok "v=1 missing on domain error" "got: $err"

# Defensive: report_error(code=0) must coerce to 1 (regression for MED-1).
# AND in JSON mode it must NOT split output across lines (regression for
# iter-3 MED self-regress: the dev-hint line corrupted the envelope).
set +e
out=$("$PY" -c "
import sys
sys.path.insert(0, '.')
from _errors import report_error
import io
stream = io.StringIO()
rc = report_error('boom', code=0, json_mode=True, stream=stream)
print('rc=', rc)
output = stream.getvalue()
# Must be exactly one line (the JSON envelope).
print('lines=', output.count(chr(10)))
print('json=', output.strip())
import json
obj = json.loads(output)
assert obj['code'] == 1
assert obj['details']['coerced_from_zero'] is True, obj
print('ok')
" 2>&1)
set -e
echo "$out" | grep -q "rc= 1" \
    && echo "$out" | grep -q "lines= 1" \
    && echo "$out" | grep -q "ok" \
    && ok "report_error(code=0) JSON: single line + coerced_from_zero in details" \
    || nok "code=0 coercion (JSON mode single-line)" "got: $out"

# Parameterized cross-5: every plumbed CLI must emit a JSON envelope
# with --json-errors when fed a missing-input failure (regression for
# MED-6 — half of the plumbed scripts had no envelope coverage).
echo "cross-5 envelope on every plumbed CLI:"
for cli in docx_fill_template.py docx_accept_changes.py; do
    set +e
    out=$("$PY" "$cli" /nope.docx /nope.docx --json-errors 2>&1 >/dev/null)
    set -e
    echo "$out" | "$PY" -c "import sys, json; json.loads(sys.stdin.read())" 2>/dev/null \
        && ok "  $cli emits JSON envelope" \
        || nok "  $cli envelope" "got: $out"
done

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

# iter-3 LOW: _load_font legacy-fallback. Pillow ≥10.1 honours
# load_default(size=N); older builds reject the kwarg — verify the
# try/except TypeError path returns a usable font object instead of
# crashing.
"$PY" -c "
import sys
sys.path.insert(0, '.')
from PIL import ImageFont
import preview

orig_truetype = ImageFont.truetype
orig_load_default = ImageFont.load_default

# Force the candidate-font truetype lookups to fail (filesystem paths
# only). Internal Pillow truetype calls use BytesIO and must keep
# working — load_default() hits truetype on its bundled font.
def selective_truetype(font, *a, **kw):
    if isinstance(font, str):
        raise OSError('mocked: filesystem font unreadable')
    return orig_truetype(font, *a, **kw)
ImageFont.truetype = selective_truetype

# Make load_default(size=...) reject the kwarg, simulating Pillow <10.1.
def legacy_load_default(*a, **kw):
    if 'size' in kw:
        raise TypeError('mocked: legacy Pillow does not accept size kwarg')
    return orig_load_default()
ImageFont.load_default = legacy_load_default

font = preview._load_font(14)
assert font is not None
print('legacy fallback returned a usable font object')

ImageFont.truetype = orig_truetype
ImageFont.load_default = orig_load_default
" 2>&1 | grep -q "legacy fallback returned a usable font object" \
    && ok "_load_font: legacy Pillow fallback (TypeError on size kwarg)" \
    || nok "_load_font legacy fallback" "TypeError path crashed"

# iter-3 LOW: pack.py uses pack-specific warning text (no "input is"
# framing — pack works on a tree, not a source file).
"$PY" -c "
import sys
sys.path.insert(0, '.')
from office._macros import format_pack_macro_loss_warning
msg = format_pack_macro_loss_warning('.docx', '.docm')
assert 'source tree' in msg, msg
assert 'input is' not in msg, 'pack warning must NOT use input-file framing'
print('pack-specific warning OK')
" 2>&1 | grep -q "pack-specific warning OK" \
    && ok "pack.py warning uses 'source tree' framing (no false 'input is' claim)" \
    || nok "pack warning framing" "iter-3 LOW regressed"

# MED-5: template macro extension (.dotm) must be detected as macro-
# enabled and the warning helper must fire when packing into .dotx.
"$PY" -c "
import zipfile, shutil, sys, io
sys.path.insert(0, '.')
from office._macros import (
    is_macro_enabled_file, warn_if_macros_will_be_dropped, MACRO_EXT_FOR,
)
from pathlib import Path
shutil.copy('$TMP/out.docx', '$TMP/template.dotm')
with zipfile.ZipFile('$TMP/template.dotm', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
ct = data['[Content_Types].xml'].decode('utf-8')
ct = ct.replace(
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
    'application/vnd.ms-word.template.macroEnabledTemplate.main+xml',
)
data['[Content_Types].xml'] = ct.encode('utf-8')
data['word/vbaProject.bin'] = b'fake-vba'
with zipfile.ZipFile('$TMP/template.dotm', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)

assert is_macro_enabled_file(Path('$TMP/template.dotm')) is True, 'dotm not detected'
buf = io.StringIO()
fired = warn_if_macros_will_be_dropped(
    Path('$TMP/template.dotm'), Path('$TMP/lossy.dotx'), buf,
)
assert fired is True, 'warning did not fire on .dotm → .dotx'
assert '.dotm' in buf.getvalue() and '.dotx' in buf.getvalue(), buf.getvalue()
" \
    && ok ".dotm → .dotx triggers macro-loss warning (template path covered)" \
    || nok ".dotm template macro warning" "MED-5 regression"

# False-positive guard A: stray vbaProject.bin in a regular .docx must
# NOT trip the detector. Office ignores the bin without the matching
# content-type, so warning would lie. Regression for VDD HIGH-4.
"$PY" -c "
import zipfile, shutil, sys
sys.path.insert(0, '.')
from office._macros import is_macro_enabled_file
from pathlib import Path
shutil.copy('$TMP/out.docx', '$TMP/stray.docx')
with zipfile.ZipFile('$TMP/stray.docx', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
data['word/vbaProject.bin'] = b'leftover'
with zipfile.ZipFile('$TMP/stray.docx', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
assert is_macro_enabled_file(Path('$TMP/stray.docx')) is False, 'stray bin must not trigger'
" \
    && ok "stray vbaProject.bin without macro CT → False (no false positive)" \
    || nok "stray vbaProject.bin" "false-positive returned True"

# False-positive guard B: substring mention of macroEnabled in an XML
# comment must NOT trip the detector. XML-aware parse rejects this.
# Regression for VDD HIGH-3.
"$PY" -c "
import zipfile, shutil, sys
sys.path.insert(0, '.')
from office._macros import is_macro_enabled_file
from pathlib import Path
shutil.copy('$TMP/out.docx', '$TMP/comment.docx')
with zipfile.ZipFile('$TMP/comment.docx', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
ct = data['[Content_Types].xml'].decode('utf-8')
ct = ct.replace('<Types ', '<!-- macroEnabled.main+xml --><Types ', 1)
data['[Content_Types].xml'] = ct.encode('utf-8')
with zipfile.ZipFile('$TMP/comment.docx', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
assert is_macro_enabled_file(Path('$TMP/comment.docx')) is False, 'comment substring must not trigger'
" \
    && ok "macroEnabled mention in XML comment → False (no substring false positive)" \
    || nok "comment substring" "false-positive returned True"

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
