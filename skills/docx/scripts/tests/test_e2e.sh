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
ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
SKILL=docx
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t docx_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

source "$ROOT/tests/visual/_visual_helper.sh"

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

# --- cross-7: real password-protect (set/remove via msoffcrypto-tool) -----
echo "cross-7 password-protect:"

# --check on a clean file: exit 10 + "not encrypted" message.
set +e
out=$("$PY" office_passwd.py "$TMP/out.docx" --check 2>&1)
rc=$?
set -e
[ "$rc" -eq 10 ] && echo "$out" | grep -q "not encrypted" \
    && ok "--check on clean docx → exit 10" \
    || nok "--check on clean" "exit=$rc out=$out"

# --encrypt: produces a CFB-wrapped output that --check sees as encrypted.
"$PY" office_passwd.py "$TMP/out.docx" "$TMP/enc.docx" --encrypt hunter2 >/dev/null 2>&1 \
    && [ -s "$TMP/enc.docx" ] \
    && ok "--encrypt creates non-empty output" \
    || nok "--encrypt" "missing or empty"
set +e
out=$("$PY" office_passwd.py "$TMP/enc.docx" --check 2>&1)
rc=$?
set -e
[ "$rc" -eq 0 ] && echo "$out" | grep -q "encrypted" \
    && ok "--check on encrypted docx → exit 0" \
    || nok "--check on encrypted" "exit=$rc out=$out"

# --decrypt round-trip: result validates with office.validate AND has the
# same OOXML parts list as the original (lossless).
"$PY" office_passwd.py "$TMP/enc.docx" "$TMP/dec.docx" --decrypt hunter2 >/dev/null 2>&1 \
    && [ -s "$TMP/dec.docx" ] \
    && ok "--decrypt creates non-empty output" \
    || nok "--decrypt" "missing or empty"
"$PY" -m office.validate "$TMP/dec.docx" >/dev/null 2>&1 \
    && ok "decrypted output passes office.validate" \
    || nok "validate decrypted" "rejected"
"$PY" -c "
import zipfile, sys
a = sorted(zipfile.ZipFile('$TMP/out.docx').namelist())
b = sorted(zipfile.ZipFile('$TMP/dec.docx').namelist())
assert a == b, f'parts differ\\nbefore: {a}\\nafter:  {b}'
" \
    && ok "round-trip preserves OOXML parts list" \
    || nok "round-trip parts" "differ"

# Wrong password: exit 4 AND no half-written output is left behind.
set +e
err=$("$PY" office_passwd.py "$TMP/enc.docx" "$TMP/bad.docx" --decrypt nopenope 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 4 ] && [ ! -e "$TMP/bad.docx" ] && echo "$err" | grep -qi "wrong password" \
    && ok "wrong password → exit 4 + output cleaned up" \
    || nok "wrong password" "exit=$rc, output=$([ -e "$TMP/bad.docx" ] && echo present || echo absent), msg=$err"

# State-mismatch: --encrypt on already-encrypted → exit 5.
set +e
err=$("$PY" office_passwd.py "$TMP/enc.docx" "$TMP/x.docx" --encrypt foo 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 5 ] && echo "$err" | grep -qi "already encrypted" \
    && ok "--encrypt on already-encrypted → exit 5" \
    || nok "encrypt-already-encrypted" "exit=$rc msg=$err"

# State-mismatch: --decrypt on a clean file → exit 5.
set +e
err=$("$PY" office_passwd.py "$TMP/out.docx" "$TMP/x.docx" --decrypt foo 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 5 ] && echo "$err" | grep -qi "not encrypted" \
    && ok "--decrypt on clean → exit 5" \
    || nok "decrypt-clean" "exit=$rc msg=$err"

# Stdin password: lets callers avoid putting the secret in argv.
"$PY" office_passwd.py "$TMP/enc.docx" "$TMP/dec_stdin.docx" --decrypt - <<<"hunter2" >/dev/null 2>&1 \
    && [ -s "$TMP/dec_stdin.docx" ] \
    && ok "--decrypt - reads password from stdin" \
    || nok "stdin password" "no output"

# JSON envelope on wrong password (cross-5 integration).
set +e
err=$("$PY" office_passwd.py "$TMP/enc.docx" "$TMP/x.docx" --decrypt nope --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 4 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==4 and j['type']=='InvalidPassword' and j['v']==1, j" 2>/dev/null \
    && ok "wrong-password JSON envelope (code=4, type=InvalidPassword, v=1)" \
    || nok "json envelope" "exit=$rc msg=$err"

# --- cross-7 VDD-iter-2 regressions (HIGH-1, MED-1..4, LOW-1) ------------
echo "cross-7 VDD-iter-2:"

# H1: same-path I/O destroys the source. Fix is a pre-flight refusal that
# returns exit 6 BEFORE any open() touches the filesystem. Without the
# guard the source file is truncated to 0 bytes by the write-open before
# the read-open finishes streaming.
cp "$TMP/out.docx" "$TMP/victim.docx"
sz_before=$(wc -c < "$TMP/victim.docx" | tr -d ' ')
set +e
err=$("$PY" office_passwd.py "$TMP/victim.docx" "$TMP/victim.docx" --encrypt p 2>&1 >/dev/null)
rc=$?
set -e
sz_after=$(wc -c < "$TMP/victim.docx" | tr -d ' ')
[ "$rc" -eq 6 ] && [ "$sz_before" = "$sz_after" ] \
    && echo "$err" | grep -qi "same path" \
    && ok "H1: same-path --encrypt refused (exit 6, source intact $sz_before B)" \
    || nok "H1 same-path encrypt" "rc=$rc, before=$sz_before after=$sz_after, msg=$err"

# Same guard on the decrypt path. The state-mismatch check (NotEncrypted)
# would also fire on a clean self-input, but a CFB self-input would skip
# that and still trip the truncation. Test on the encrypted file we
# already produced earlier in this suite.
cp "$TMP/enc.docx" "$TMP/victim_enc.docx"
sz_before=$(wc -c < "$TMP/victim_enc.docx" | tr -d ' ')
set +e
err=$("$PY" office_passwd.py "$TMP/victim_enc.docx" "$TMP/victim_enc.docx" --decrypt hunter2 2>&1 >/dev/null)
rc=$?
set -e
sz_after=$(wc -c < "$TMP/victim_enc.docx" | tr -d ' ')
[ "$rc" -eq 6 ] && [ "$sz_before" = "$sz_after" ] \
    && ok "H1: same-path --decrypt refused (exit 6, source intact $sz_before B)" \
    || nok "H1 same-path decrypt" "rc=$rc, before=$sz_before after=$sz_after"

# H1 must also fold through --json-errors (cross-5 contract).
set +e
err=$("$PY" office_passwd.py "$TMP/victim.docx" "$TMP/victim.docx" --encrypt p --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==6 and j['type']=='SelfOverwriteRefused' and j['v']==1, j" 2>/dev/null \
    && ok "H1 JSON envelope: code=6, type=SelfOverwriteRefused" \
    || nok "H1 JSON envelope" "rc=$rc msg=$err"

# Symlink twist: INPUT and OUTPUT can resolve() to the same file via a
# symlink even when the literal paths differ. Path.resolve(strict=False)
# normalises the symlink, so the guard MUST still fire.
ln -sf "$TMP/victim.docx" "$TMP/victim_link.docx"
set +e
"$PY" office_passwd.py "$TMP/victim.docx" "$TMP/victim_link.docx" --encrypt p >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && ok "H1: symlink → same inode also refused (exit 6)" \
    || nok "H1 symlink" "rc=$rc (resolve() didn't follow the link)"

# M1: encrypt failure must not leave a half-written output decoy.
echo "hello world" > "$TMP/notooxml.txt"
rm -f "$TMP/decoy.docx"
set +e
"$PY" office_passwd.py "$TMP/notooxml.txt" "$TMP/decoy.docx" --encrypt p >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && [ ! -e "$TMP/decoy.docx" ] \
    && ok "M1: non-OOXML --encrypt → exit 1 + output cleaned up" \
    || nok "M1 encrypt cleanup" "rc=$rc, decoy=$([ -e "$TMP/decoy.docx" ] && echo present || echo absent)"

# M2: msoffcrypto.exceptions.{ParseError,DecryptionError,EncryptionError}
# must not propagate as a Python traceback — they would corrupt the JSON
# envelope contract. Verify by importing them through Python and asserting
# the exception classes ARE in the catch tuple.
"$PY" -c "
import sys
sys.path.insert(0, '.')
from office_passwd import _msoffcrypto_runtime_errors
import msoffcrypto
caught = _msoffcrypto_runtime_errors(msoffcrypto)
needed = (msoffcrypto.exceptions.ParseError,
          msoffcrypto.exceptions.DecryptionError,
          msoffcrypto.exceptions.EncryptionError)
for cls in needed:
    assert cls in caught, f'{cls.__name__} not in runtime catch tuple {caught}'
" \
    && ok "M2: ParseError + DecryptionError + EncryptionError in runtime catch tuple" \
    || nok "M2 runtime errors" "see python output"

# M3: malformed CFB must produce a friendly user message, NOT the
# CPython int-string-conversion diagnostic. Guard test: make sure the
# user-facing message does NOT mention sys.set_int_max_str_digits.
{ printf '\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'; head -c 1024 /dev/urandom; } > "$TMP/fakedoc.bin"
set +e
err=$("$PY" office_passwd.py "$TMP/fakedoc.bin" "$TMP/fakedoc-dec.docx" --decrypt anypw 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] && ! echo "$err" | grep -q "set_int_max_str_digits" \
    && echo "$err" | grep -qi "malformed\|not a real encrypted" \
    && ok "M3: CPython int-limit error reskinned to user-friendly text" \
    || nok "M3 reskin" "rc=$rc msg=$err"

# M3 also validates JSON envelope stays single-line on the same input.
set +e
err=$("$PY" office_passwd.py "$TMP/fakedoc.bin" "$TMP/fakedoc-dec.docx" --decrypt anypw --json-errors 2>&1 >/dev/null)
rc=$?
set -e
n_lines=$(echo "$err" | wc -l | tr -d ' ')
[ "$rc" -eq 1 ] && [ "$n_lines" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['v']==1, j" 2>/dev/null \
    && ok "M3: malformed CFB --json-errors stays single-line + valid envelope" \
    || nok "M3 envelope" "rc=$rc lines=$n_lines msg=$err"

# M4: office.validate.py must reject CFB inputs with cross-3 message
# (exit 3, not its own bare 'Not a ZIP-based OOXML container').
set +e
err=$("$PY" -m office.validate "$TMP/enc.docx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && echo "$err" | grep -q "legacy" \
    && ok "M4: office.validate refuses encrypted with cross-3 exit 3" \
    || nok "M4 cross-3 in validate" "rc=$rc msg=$err"

# L1: stdin password with trailing whitespace must produce a stderr warning.
set +e
err=$(printf "hunter2 " | "$PY" office_passwd.py "$TMP/out.docx" "$TMP/L1.docx" --encrypt - 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] && echo "$err" | grep -qi "ends in whitespace" \
    && ok "L1: trailing-whitespace stdin password emits warning" \
    || nok "L1 whitespace warning" "rc=$rc msg=$err"

# L1 negative: a clean stdin password (no trailing whitespace) must NOT warn.
set +e
err=$(printf "hunter2" | "$PY" office_passwd.py "$TMP/out.docx" "$TMP/L1clean.docx" --encrypt - 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] && ! echo "$err" | grep -qi "ends in whitespace" \
    && ok "L1: clean stdin password emits no spurious warning" \
    || nok "L1 false positive" "rc=$rc msg=$err"

# --- docx-1: docx_add_comment ---------------------------------------------
echo "docx-1 add_comment:"
"$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/commented.docx" \
    --anchor-text "Quarterly" --comment "Verify against source" \
    --author "QA Bot" >/dev/null 2>&1 \
    && [ -s "$TMP/commented.docx" ] \
    && ok "anchor → output produced" \
    || nok "add_comment basic" "no output"

"$PY" -m office.validate "$TMP/commented.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts commented output" \
    || nok "validate commented" "rejected"

# Comment present in word/comments.xml with the author and body
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/commented.docx') as z:
    cx = z.read('word/comments.xml').decode()
assert re.search(r'<w:comment [^/]*w:author=\"QA Bot\"', cx), 'author missing'
assert 'Verify against source' in cx, 'body missing'
assert re.search(r'<w:comment [^/]*w:id=\"', cx), 'id missing'
print('comment verified')
" 2>&1 | grep -q "comment verified" \
    && ok "comment XML carries author + body + id" \
    || nok "comment xml content" "see python output"

# Anchor markers present in document.xml
"$PY" -c "
import zipfile
with zipfile.ZipFile('$TMP/commented.docx') as z:
    doc = z.read('word/document.xml').decode()
assert '<w:commentRangeStart' in doc, 'no commentRangeStart'
assert '<w:commentRangeEnd' in doc, 'no commentRangeEnd'
assert '<w:commentReference' in doc, 'no commentReference'
print('anchors verified')
" 2>&1 | grep -q "anchors verified" \
    && ok "document.xml has commentRangeStart/End + commentReference" \
    || nok "anchor markers" "missing in document.xml"

# Anchor not found → exit 2 with AnchorNotFound JSON envelope
set +e
err=$("$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/_x.docx" \
    --anchor-text "ZZZNOTPRESENTZZZ" --comment "x" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='AnchorNotFound' and j['v']==1, j" 2>/dev/null \
    && ok "anchor not found → exit 2 + AnchorNotFound envelope" \
    || nok "anchor not found" "rc=$rc msg=$err"

# --all multi-match: comment count > 1 when the anchor occurs multiple times
"$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/all.docx" \
    --anchor-text "the" --comment "n" --author "B" --all >/dev/null 2>&1
n_cmts=$("$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/all.docx') as z:
    print(len(re.findall(r'<w:comment ', z.read('word/comments.xml').decode())))
")
[ "$n_cmts" -ge 2 ] \
    && ok "--all adds >1 comments (got $n_cmts)" \
    || nok "--all multi-match" "got only $n_cmts comment(s)"

# VDD-A regression: --all must catch INTRA-paragraph repeats. Build a fixture
# with three lowercase "the" in a single paragraph; expect exactly 3 comments
# AND 3 matching commentRangeStart/End markers in the document body.
cat > "$TMP/intra.md" <<'MD'
# Intra

The cat saw the dog and the bird in the same garden.
MD
node md2docx.js "$TMP/intra.md" "$TMP/intra.docx" >/dev/null 2>&1
"$PY" docx_add_comment.py "$TMP/intra.docx" "$TMP/intra_out.docx" \
    --anchor-text "the" --comment "x" --author "Q" --all >/dev/null 2>&1
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/intra_out.docx') as z:
    cx = z.read('word/comments.xml').decode()
    doc = z.read('word/document.xml').decode()
n_cmt = len(re.findall(r'<w:comment ', cx))
n_crs = len(re.findall(r'<w:commentRangeStart', doc))
n_cre = len(re.findall(r'<w:commentRangeEnd', doc))
n_ref = len(re.findall(r'<w:commentReference', doc))
assert n_cmt == 3, f'expected 3 comments, got {n_cmt}'
assert n_crs == n_cre == n_ref == 3, f'marker counts mismatch: crs={n_crs} cre={n_cre} ref={n_ref}'
print('intra-paragraph triple-match verified')
" 2>&1 | grep -q "triple-match verified" \
    && ok "VDD-A: --all catches all 3 'the' in a single paragraph (was 1/3 before fix)" \
    || nok "VDD-A intra-paragraph multi-match" "see python output"

# VDD-A negative: default mode (no --all) must still produce exactly 1 comment
"$PY" docx_add_comment.py "$TMP/intra.docx" "$TMP/single.docx" \
    --anchor-text "the" --comment "x" --author "Q" >/dev/null 2>&1
n=$("$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/single.docx') as z:
    print(len(re.findall(r'<w:comment ', z.read('word/comments.xml').decode())))
")
[ "$n" -eq 1 ] \
    && ok "VDD-A: default mode still produces exactly 1 comment (got $n)" \
    || nok "VDD-A default-mode regression" "got $n, expected 1"

# VDD-B: same-path I/O must refuse with exit 6 + SelfOverwriteRefused envelope
cp "$TMP/out.docx" "$TMP/vdb.docx"
sz_b=$(wc -c < "$TMP/vdb.docx" | tr -d ' ')
set +e
out=$("$PY" docx_add_comment.py "$TMP/vdb.docx" "$TMP/vdb.docx" \
    --anchor-text "Quarterly" --comment "x" --author "Q" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
sz_a=$(wc -c < "$TMP/vdb.docx" | tr -d ' ')
[ "$rc" -eq 6 ] && [ "$sz_b" = "$sz_a" ] \
    && echo "$out" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='SelfOverwriteRefused' and j['code']==6, j" 2>/dev/null \
    && ok "VDD-B: add_comment same-path → exit 6 + source intact + envelope" \
    || nok "VDD-B add_comment same-path" "rc=$rc before=$sz_b after=$sz_a msg=$out"

# VDD-B: same-path on merge (output == input[0]) must also refuse with exit 6
cp "$TMP/out.docx" "$TMP/m_in.docx"
cp "$TMP/out.docx" "$TMP/m_other.docx"
set +e
out=$("$PY" docx_merge.py "$TMP/m_in.docx" "$TMP/m_in.docx" "$TMP/m_other.docx" \
        --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$out" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='SelfOverwriteRefused' and j['code']==6, j" 2>/dev/null \
    && ok "VDD-B: merge same-path → exit 6 + envelope" \
    || nok "VDD-B merge same-path" "rc=$rc msg=$out"

# VDD-B: symlink resolves to same inode — must also be caught
ln -sf "$TMP/m_in.docx" "$TMP/m_link.docx"
set +e
"$PY" docx_merge.py "$TMP/m_link.docx" "$TMP/m_in.docx" "$TMP/m_other.docx" \
      >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && ok "VDD-B: merge with symlink → same-inode caught (exit 6)" \
    || nok "VDD-B merge symlink" "rc=$rc"

# --- docx-2: docx_merge ---------------------------------------------------
echo "docx-2 merge:"
# Build 3 distinct inputs from inline markdown
for f in a b c; do
    cat > "$TMP/m_$f.md" <<MD
# Doc $f
Content of $f section.
MD
    node md2docx.js "$TMP/m_$f.md" "$TMP/m_$f.docx" >/dev/null 2>&1
done

"$PY" docx_merge.py "$TMP/merged.docx" \
    "$TMP/m_a.docx" "$TMP/m_b.docx" "$TMP/m_c.docx" \
    --page-break-between >/dev/null 2>&1 \
    && [ -s "$TMP/merged.docx" ] \
    && ok "3 inputs → merged.docx" \
    || nok "merge basic" "no output"

"$PY" -m office.validate "$TMP/merged.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts merged output" \
    || nok "validate merged" "rejected"

# Round-trip back to MD: all three headings must be present in order
node docx2md.js "$TMP/merged.docx" "$TMP/merged.md" >/dev/null 2>&1
"$PY" -c "
content = open('$TMP/merged.md').read()
ai = content.find('Doc a')
bi = content.find('Doc b')
ci = content.find('Doc c')
assert 0 <= ai < bi < ci, f'order wrong: a={ai} b={bi} c={ci}'
print('order ok')
" 2>&1 | grep -q "order ok" \
    && ok "merge preserves input order (a → b → c)" \
    || nok "merge order" "headings not in order"

# Page break preservation (--page-break-between inserts <w:br w:type=\"page\"/>)
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/merged.docx') as z:
    doc = z.read('word/document.xml').decode()
n_pb = len(re.findall(r'<w:br [^/]*w:type=\"page\"', doc))
assert n_pb >= 2, f'expected >=2 page breaks (one per appended doc), got {n_pb}'
print(f'page breaks: {n_pb}')
" 2>&1 | grep -q "page breaks:" \
    && ok "--page-break-between inserted page breaks" \
    || nok "page break insertion" "missing or too few"

# Single-input rejected with NotEnoughInputs envelope
set +e
err=$("$PY" docx_merge.py "$TMP/_solo.docx" "$TMP/m_a.docx" \
        --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='NotEnoughInputs', j" 2>/dev/null \
    && ok "single input → NotEnoughInputs envelope" \
    || nok "single-input rejection" "rc=$rc msg=$err"

# Encrypted input → exit 3 (cross-3 contract)
set +e
err=$("$PY" docx_merge.py "$TMP/_enc.docx" "$TMP/cfb.docx" "$TMP/m_a.docx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && ok "merge refuses CFB input with exit 3" \
    || nok "merge cfb rejection" "rc=$rc msg=$err"

# --- q-2: visual regression (docx → soffice → pdf, then compare) ----------
# docx itself isn't a PDF; convert via soffice headless first, gated on
# soffice availability. The conversion uses a dedicated profile dir to
# avoid colliding with other LibreOffice instances on the host.
if command -v soffice >/dev/null 2>&1; then
    echo "q-2 visual regression:"
    soffice --headless --norestore --nologo --nodefault \
            "-env:UserInstallation=file://$TMP/lo-profile" \
            --convert-to pdf --outdir "$TMP" "$TMP/out.docx" >/dev/null 2>&1
    if [ -s "$TMP/out.pdf" ]; then
        visual_check "$TMP/out.pdf" "fixture-simple"
    else
        nok "visual: fixture-simple" "soffice did not produce out.pdf"
    fi
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
