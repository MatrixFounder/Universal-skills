#!/usr/bin/env bash
# End-to-end smoke tests for the xlsx skill.
#
# Run:  bash skills/xlsx/scripts/tests/test_e2e.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
SKILL=xlsx
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t xlsx_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

source "$ROOT/tests/visual/_visual_helper.sh"

# --- fixture bootstrap ----------------------------------------------------
# The xlsx-6 synthetic fixtures (clean.xlsx, multi_sheet.xlsx,
# hidden_first.xlsx, merged.xlsx, with_legacy.xlsx, macro.xlsm) are
# .gitignored (see tests/golden/inputs/.gitignore — "produced by
# regenerate_synthetic_inputs.py … live on the developer's filesystem
# only"). On a fresh checkout — including every CI run — they don't
# exist, and every test that opens them fails with "Input not found".
# Regenerate idempotently before the suite runs. The script is
# deterministic (pinned 2026-01-01 epoch) so re-running is a no-op
# byte-for-byte. encrypted.xlsx is intentionally non-deterministic
# (fresh salt per run) and is produced separately via office_passwd.py.
GOLDEN_IN="tests/golden/inputs"
if [ ! -s "$GOLDEN_IN/clean.xlsx" ] || [ ! -s "$GOLDEN_IN/encrypted.xlsx" ]; then
    echo "fixtures bootstrap:"
    # Call the 5 gitignored fixture generators directly. We avoid running
    # `regenerate_synthetic_inputs.py` as a script because its main()
    # also re-emits the committed macro.xlsm (a 1-byte-different but
    # functionally equivalent deterministic copy), which would dirty a
    # local working tree on first run.
    "$PY" -c "
import sys; sys.path.insert(0, 'tests')
from regenerate_synthetic_inputs import (
    make_clean, make_multi_sheet, make_hidden_first,
    make_merged, make_with_legacy,
)
for fn in (make_clean, make_multi_sheet, make_hidden_first, make_merged, make_with_legacy):
    fn()
" >/dev/null \
        && ok "regenerate_synthetic_inputs (5 fixtures, macro.xlsm left as committed)" \
        || nok "regenerate_synthetic_inputs" "exit=$?"
    "$PY" office_passwd.py --encrypt password123 \
        "$GOLDEN_IN/clean.xlsx" "$GOLDEN_IN/encrypted.xlsx" >/dev/null 2>&1 \
        && [ -s "$GOLDEN_IN/encrypted.xlsx" ] \
        && ok "office_passwd.py --encrypt → encrypted.xlsx" \
        || nok "office_passwd.py --encrypt" "encrypted.xlsx missing or empty"
fi

# --- csv2xlsx -------------------------------------------------------------
echo "csv2xlsx:"
"$PY" csv2xlsx.py ../examples/fixture.csv "$TMP/out.xlsx" >/dev/null 2>&1 \
    && [ -s "$TMP/out.xlsx" ] && ok "fixture.csv → out.xlsx" \
    || nok "csv2xlsx" "missing or empty"

"$PY" -m office.validate "$TMP/out.xlsx" >/dev/null 2>&1 \
    && ok "office.validate accepts csv2xlsx output" \
    || nok "office.validate" "rejected the produced .xlsx"

# Sanity: openpyxl should read it and find header + 10 data rows
rows=$("$PY" -c "
import openpyxl
wb = openpyxl.load_workbook('$TMP/out.xlsx', read_only=True)
ws = wb.active
print(sum(1 for _ in ws.iter_rows()))
")
[ "$rows" -eq 11 ] \
    && ok "row count = header+10 ($rows)" \
    || nok "row count" "expected 11, got $rows"

# --- xlsx_validate --------------------------------------------------------
echo "xlsx_validate:"
"$PY" xlsx_validate.py "$TMP/out.xlsx" >/dev/null 2>&1 \
    && ok "validator passes on clean csv2xlsx output" \
    || nok "xlsx_validate" "false positive on clean workbook"

# Build a workbook with a deliberate #DIV/0! and ensure validate flags it.
# Mutation goes through lxml (not string.replace) so the test stays
# robust against future openpyxl/lxml whitespace/attribute-order changes.
"$PY" -c "
import openpyxl, zipfile, shutil
from pathlib import Path
from lxml import etree

src = Path('$TMP/bad.xlsx')
dst = Path('$TMP/bad_error.xlsx')

# Step 1: openpyxl-built workbook with a /0 formula but no cached value.
wb = openpyxl.Workbook()
ws = wb.active
ws['A1'] = 1
ws['A2'] = 0
ws['A3'] = '=A1/A2'
wb.save(src)

# Step 2: rewrite sheet1.xml so cell A3 carries t='e' and a cached
# error value of #DIV/0!. lxml lets us address the cell by attribute
# instead of guessing whitespace.
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(src, 'r') as z:
    sheet_xml = z.read('xl/worksheets/sheet1.xml')
tree = etree.fromstring(sheet_xml)
cell = tree.find(\".//s:row/s:c[@r='A3']\", NS)
assert cell is not None, 'expected cell A3 in fixture'
cell.set('t', 'e')
v = cell.find('s:v', NS)
if v is None:
    v = etree.SubElement(cell, '{%s}v' % NS['s'])
v.text = '#DIV/0!'
patched = etree.tostring(tree, xml_declaration=True, encoding='UTF-8', standalone=True)

# Step 3: rewrite the zip in place. zipfile has no in-place edit, so
# rebuild the archive entry-by-entry, swapping sheet1.xml.
shutil.copy(src, dst)
import os
items = []
with zipfile.ZipFile(dst, 'r') as z:
    for n in z.namelist():
        items.append((n, z.read(n)))
os.unlink(dst)
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
    for n, data in items:
        z.writestr(n, patched if n == 'xl/worksheets/sheet1.xml' else data)
"
set +e
"$PY" xlsx_validate.py "$TMP/bad_error.xlsx" --fail-empty >"$TMP/_xv.txt" 2>&1
rc=$?
set -e
# Validator should signal non-zero OR print a #DIV/0! line
if [ "$rc" -ne 0 ] || grep -q "DIV/0" "$TMP/_xv.txt"; then
    ok "validator flags injected #DIV/0!"
else
    nok "validator on bad cell" "exit $rc and no DIV/0 in stdout"
fi

# --- xlsx_add_chart -------------------------------------------------------
echo "xlsx_add_chart:"
"$PY" xlsx_add_chart.py "$TMP/out.xlsx" --type bar --data "F2:F11" --categories "C2:C11" \
    --title "Revenue" --output "$TMP/with_chart.xlsx" >/dev/null 2>&1 \
    && [ -s "$TMP/with_chart.xlsx" ] && ok "bar chart written to new workbook" \
    || nok "add bar chart" "missing or empty"

# Verify the chart actually landed via openpyxl's _charts list
charts=$("$PY" -c "
import openpyxl
wb = openpyxl.load_workbook('$TMP/with_chart.xlsx')
ws = wb.active
print(len(ws._charts))
print(','.join(type(c).__name__ for c in ws._charts))
")
n=$(echo "$charts" | head -1)
[ "$n" = "1" ] \
    && ok "chart object present in saved workbook (count=$n)" \
    || nok "chart object" "expected 1, got $n"

# Pie + line variants exercise the type dispatch
"$PY" xlsx_add_chart.py "$TMP/out.xlsx" --type pie --data "F2:F11" --categories "C2:C11" \
    --output "$TMP/pie.xlsx" >/dev/null 2>&1 \
    && ok "pie chart variant" \
    || nok "pie chart" "non-zero exit"
"$PY" xlsx_add_chart.py "$TMP/out.xlsx" --type line --data "D2:F11" --categories "A2:A11" \
    --output "$TMP/line.xlsx" >/dev/null 2>&1 \
    && ok "line chart variant" \
    || nok "line chart" "non-zero exit"

# Bad range syntax → exit 1 with clear stderr
set +e
err=$("$PY" xlsx_add_chart.py "$TMP/out.xlsx" --type bar --data "garbage" \
    --output "$TMP/_x.xlsx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] && echo "$err" | grep -q "is not in" \
    && ok "bad range exits 1 with hint" \
    || nok "bad range" "exit $rc / msg: $err"

# --- encryption fail-fast (cross-cutting, applies to all readers) ---------
echo "encryption fail-fast:"
# Forge a CFB-magic file (D0CF11E0A1B11AE1) — not a valid OOXML, but
# enough to trigger our pre-flight check.
"$PY" -c "
from pathlib import Path
Path('$TMP/cfb.xlsx').write_bytes(b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1' + b'\\x00' * 100)
"
# Same fixture used by all three xlsx readers — verifies wiring is
# consistent across xlsx_validate / xlsx_add_chart / xlsx_recalc
# (the latter only when soffice is on PATH).
set +e
err=$("$PY" xlsx_validate.py "$TMP/cfb.xlsx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && echo "$err" | grep -q "legacy" \
    && ok "xlsx_validate: exit 3 + message names both encrypted AND legacy" \
    || nok "encrypted rejection (validate)" "exit $rc / msg: $err"

set +e
err=$("$PY" xlsx_add_chart.py "$TMP/cfb.xlsx" --type bar --data "A1:B5" --output "$TMP/_x.xlsx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "CFB\|password-protected" \
    && ok "xlsx_add_chart also refuses CFB with exit 3" \
    || nok "encrypted rejection (add_chart)" "exit $rc / msg: $err"

if command -v soffice >/dev/null 2>&1; then
    set +e
    err=$("$PY" xlsx_recalc.py "$TMP/cfb.xlsx" --output "$TMP/_y.xlsx" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 3 ] && echo "$err" | grep -q "CFB\|password-protected" \
        && ok "xlsx_recalc also refuses CFB with exit 3" \
        || nok "encrypted rejection (recalc)" "exit $rc / msg: $err"
fi

# --- xlsx_recalc ---------------------------------------------------------
# Skip if soffice missing; recalc goes via LibreOffice.
if command -v soffice >/dev/null 2>&1; then
    echo "xlsx_recalc:"
    # Build a workbook with a SUM formula, no cached value
    "$PY" -c "
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.append([1, 2, 3])
ws['D1'] = '=SUM(A1:C1)'
wb.save('$TMP/sum.xlsx')
"
    "$PY" xlsx_recalc.py "$TMP/sum.xlsx" --output "$TMP/sum_recalc.xlsx" >/dev/null 2>&1 \
        && [ -s "$TMP/sum_recalc.xlsx" ] && ok "recalc produced output" \
        || nok "recalc" "missing output"
    # The macro `oDoc.calculateAll()` may or may not persist cached
    # values to the saved file depending on LO version (some versions
    # only update calc-on-open dirty markers). Assert only that the
    # formula survived the round-trip — that's the user-facing
    # contract: "I gave you formulas, you didn't drop them."
    formula=$("$PY" -c "
import openpyxl
wb = openpyxl.load_workbook('$TMP/sum_recalc.xlsx')
print(wb.active['D1'].value)
")
    [ "$formula" = "=SUM(A1:C1)" ] \
        && ok "recalc preserves formula in D1" \
        || nok "recalc preserve formula" "got '$formula'"
else
    echo "xlsx_recalc: skipped (soffice not on PATH)"
fi

# --- cross-5: --json-errors envelope --------------------------------------
echo "cross-5 unified errors:"
set +e
err=$("$PY" xlsx_validate.py /nope.xlsx --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='FileNotFound' and j['v']==1, j" 2>/dev/null \
    && ok "xlsx_validate --json-errors envelope (v=1)" \
    || nok "xlsx_validate --json-errors" "exit=$rc msg=$err"

# Parameterized cross-5: every plumbed xlsx CLI emits a JSON envelope.
for cli in csv2xlsx.py xlsx_recalc.py xlsx_add_chart.py; do
    set +e
    if [ "$cli" = "xlsx_add_chart.py" ]; then
        out=$("$PY" "$cli" /nope.xlsx --type bar --data "A1:B5" --json-errors 2>&1 >/dev/null)
    else
        out=$("$PY" "$cli" /nope.xlsx /tmp/_x.xlsx --json-errors 2>&1 >/dev/null)
    fi
    set -e
    echo "$out" | "$PY" -c "import sys, json; json.loads(sys.stdin.read())" 2>/dev/null \
        && ok "  $cli emits JSON envelope" \
        || nok "  $cli envelope" "got: $out"
done

# --- cross-4: macro detection --------------------------------------------
echo "cross-4 macro warnings:"
"$PY" -c "
import zipfile, openpyxl
wb = openpyxl.Workbook()
wb.active.append([1, 2, 3])
wb.save('$TMP/macro.xlsm')
with zipfile.ZipFile('$TMP/macro.xlsm', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
ct = data['[Content_Types].xml'].decode('utf-8')
ct = ct.replace(
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
    'application/vnd.ms-excel.sheet.macroEnabled.main+xml',
)
data['[Content_Types].xml'] = ct.encode('utf-8')
data['xl/vbaProject.bin'] = b'fake-vba'
with zipfile.ZipFile('$TMP/macro.xlsm', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
from office._macros import is_macro_enabled_file
from pathlib import Path
assert is_macro_enabled_file(Path('$TMP/macro.xlsm')) is True
" \
    && ok "is_macro_enabled_file detects xlsm" \
    || nok "xlsm detection" "is_macro_enabled_file returned False"

set +e
err=$("$PY" xlsx_add_chart.py "$TMP/macro.xlsm" --type bar --data "A1:C1" \
    --output "$TMP/lossy.xlsx" 2>&1)
rc=$?
set -e
echo "$err" | grep -q "macro-enabled" && [ "$rc" -eq 0 ] \
    && ok "xlsx_add_chart warns when .xlsm → .xlsx" \
    || nok "macro-loss warning (xlsx)" "exit=$rc msg=$err"

# --- xlsx-5: XlsxValidator deep checks ------------------------------------
echo "xlsx-5 deep validation:"

# Real fixture must validate cleanly (sheet chain, sst+styles bounds).
"$PY" -m office.validate "$TMP/out.xlsx" --json > "$TMP/_v.json" 2>&1
"$PY" -c "
import json
r = json.load(open('$TMP/_v.json'))
assert r['ok'] is True, r
assert not r['errors'], r
" \
    && ok "real xlsx fixture: zero errors from deep validator" \
    || nok "real xlsx clean validation" "got: $(cat $TMP/_v.json)"

# Inject an out-of-range shared-string index — Excel would refuse to
# open this; our validator must error. csv2xlsx output has no
# sharedStrings.xml (numeric data only), so we inject one with 1 entry
# and reference index 9999 → out-of-range against count=1.
"$PY" -c "
import zipfile, shutil
shutil.copy('$TMP/out.xlsx', '$TMP/oob_sst.xlsx')
with zipfile.ZipFile('$TMP/oob_sst.xlsx', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
data['xl/sharedStrings.xml'] = (
    '<?xml version=\"1.0\" encoding=\"UTF-8\"?>'
    '<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" count=\"1\" uniqueCount=\"1\">'
    '<si><t>only-string</t></si>'
    '</sst>'
).encode('utf-8')
# Patch [Content_Types].xml so the package declares sharedStrings.xml.
ct = data['[Content_Types].xml'].decode('utf-8')
if 'sharedStrings.xml' not in ct:
    ct = ct.replace('</Types>',
        '<Override PartName=\"/xl/sharedStrings.xml\" '
        'ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml\"/></Types>',
        1)
    data['[Content_Types].xml'] = ct.encode('utf-8')
sheet_xml = data['xl/worksheets/sheet1.xml'].decode('utf-8')
patched = sheet_xml.replace(
    '</sheetData>',
    '<row r=\"99\"><c r=\"Z99\" t=\"s\"><v>9999</v></c></row></sheetData>',
    1,
)
data['xl/worksheets/sheet1.xml'] = patched.encode('utf-8')
with zipfile.ZipFile('$TMP/oob_sst.xlsx', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
"
set +e
"$PY" -m office.validate "$TMP/oob_sst.xlsx" --json > "$TMP/_o.json" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && "$PY" -c "
import json
r = json.load(open('$TMP/_o.json'))
assert any('sst index 9999 out of range' in e for e in r['errors']), r
" \
    && ok "out-of-range sst index: error emitted, exit 1" \
    || nok "oob sst detection" "exit=$rc out=$(cat $TMP/_o.json)"

# Inject a duplicate sheet name (Excel hard-fail).
"$PY" -c "
import zipfile, shutil
shutil.copy('$TMP/out.xlsx', '$TMP/dup_name.xlsx')
with zipfile.ZipFile('$TMP/dup_name.xlsx', 'r') as src:
    data = {n: src.read(n) for n in src.namelist()}
wb = data['xl/workbook.xml'].decode('utf-8')
# Naively duplicate the <sheet/> element. csv2xlsx writes one sheet
# named 'Sheet1'; so we insert a second one with the same name.
wb = wb.replace(
    '</sheets>',
    '<sheet name=\"Sheet1\" sheetId=\"99\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" r:id=\"rIdSheet1\"/></sheets>',
    1,
)
data['xl/workbook.xml'] = wb.encode('utf-8')
with zipfile.ZipFile('$TMP/dup_name.xlsx', 'w', zipfile.ZIP_DEFLATED) as out:
    for n, d in data.items():
        out.writestr(n, d)
"
set +e
"$PY" -m office.validate "$TMP/dup_name.xlsx" --json > "$TMP/_d.json" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && "$PY" -c "
import json
r = json.load(open('$TMP/_d.json'))
assert any(\"duplicate sheet name 'Sheet1'\" in e for e in r['errors']), r
" \
    && ok "duplicate sheet name: error emitted, exit 1" \
    || nok "duplicate sheet name detection" "exit=$rc out=$(cat $TMP/_d.json)"

# Unit-test suite for XlsxValidator (9 tests; quick).
"$PY" -m unittest office.tests.test_xlsx_validator 2>&1 | tail -1 | grep -q "^OK$" \
    && ok "office.tests.test_xlsx_validator: all 9 unit tests pass" \
    || nok "XlsxValidator unit tests" "see python -m unittest output"

# --- cross-7: real password-protect (set/remove via msoffcrypto-tool) -----
echo "cross-7 password-protect:"

set +e
out=$("$PY" office_passwd.py "$TMP/out.xlsx" --check 2>&1)
rc=$?
set -e
[ "$rc" -eq 10 ] && echo "$out" | grep -q "not encrypted" \
    && ok "--check on clean xlsx → exit 10" \
    || nok "--check on clean" "exit=$rc out=$out"

"$PY" office_passwd.py "$TMP/out.xlsx" "$TMP/enc.xlsx" --encrypt s3cret >/dev/null 2>&1 \
    && [ -s "$TMP/enc.xlsx" ] \
    && ok "--encrypt creates non-empty output" \
    || nok "--encrypt" "missing or empty"
set +e
out=$("$PY" office_passwd.py "$TMP/enc.xlsx" --check 2>&1)
rc=$?
set -e
[ "$rc" -eq 0 ] && echo "$out" | grep -q "encrypted" \
    && ok "--check on encrypted xlsx → exit 0" \
    || nok "--check on encrypted" "exit=$rc out=$out"

"$PY" office_passwd.py "$TMP/enc.xlsx" "$TMP/dec.xlsx" --decrypt s3cret >/dev/null 2>&1 \
    && [ -s "$TMP/dec.xlsx" ] \
    && ok "--decrypt creates non-empty output" \
    || nok "--decrypt" "missing or empty"
"$PY" -m office.validate "$TMP/dec.xlsx" >/dev/null 2>&1 \
    && ok "decrypted output passes office.validate" \
    || nok "validate decrypted" "rejected"
# Decrypted xlsx must still be readable by openpyxl with the same row count
# as the original csv2xlsx output (header + 10 fixture rows).
"$PY" -c "
import openpyxl
wb = openpyxl.load_workbook('$TMP/dec.xlsx', read_only=True)
rows = sum(1 for _ in wb.active.iter_rows())
assert rows == 11, f'expected 11 rows after round-trip, got {rows}'
" \
    && ok "decrypted xlsx readable by openpyxl (11 rows preserved)" \
    || nok "openpyxl read decrypted" "row count off"

set +e
err=$("$PY" office_passwd.py "$TMP/enc.xlsx" "$TMP/bad.xlsx" --decrypt nope 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 4 ] && [ ! -e "$TMP/bad.xlsx" ] && echo "$err" | grep -qi "wrong password" \
    && ok "wrong password → exit 4 + output cleaned up" \
    || nok "wrong password" "exit=$rc, output=$([ -e "$TMP/bad.xlsx" ] && echo present || echo absent)"

set +e
"$PY" office_passwd.py "$TMP/enc.xlsx" "$TMP/x.xlsx" --encrypt foo >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 5 ] \
    && ok "--encrypt on already-encrypted → exit 5" \
    || nok "encrypt-already-encrypted" "exit=$rc"

set +e
"$PY" office_passwd.py "$TMP/out.xlsx" "$TMP/x.xlsx" --decrypt foo >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 5 ] \
    && ok "--decrypt on clean → exit 5" \
    || nok "decrypt-clean" "exit=$rc"

"$PY" office_passwd.py "$TMP/enc.xlsx" "$TMP/dec_stdin.xlsx" --decrypt - <<<"s3cret" >/dev/null 2>&1 \
    && [ -s "$TMP/dec_stdin.xlsx" ] \
    && ok "--decrypt - reads password from stdin" \
    || nok "stdin password" "no output"

set +e
err=$("$PY" office_passwd.py "$TMP/enc.xlsx" "$TMP/x.xlsx" --decrypt nope --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 4 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==4 and j['type']=='InvalidPassword' and j['v']==1, j" 2>/dev/null \
    && ok "wrong-password JSON envelope (code=4, type=InvalidPassword, v=1)" \
    || nok "json envelope" "exit=$rc msg=$err"

# --- cross-7 VDD-iter-2 regressions (H1, M1, M4) ------------------------
echo "cross-7 VDD-iter-2:"

# H1: same-path I/O destroys the source. Pre-flight refusal returns
# exit 6 BEFORE any open() touches the filesystem.
cp "$TMP/out.xlsx" "$TMP/victim.xlsx"
sz_before=$(wc -c < "$TMP/victim.xlsx" | tr -d ' ')
set +e
"$PY" office_passwd.py "$TMP/victim.xlsx" "$TMP/victim.xlsx" --encrypt p >/dev/null 2>&1
rc=$?
set -e
sz_after=$(wc -c < "$TMP/victim.xlsx" | tr -d ' ')
[ "$rc" -eq 6 ] && [ "$sz_before" = "$sz_after" ] \
    && ok "H1: same-path --encrypt refused (exit 6, source intact $sz_before B)" \
    || nok "H1 same-path encrypt" "rc=$rc, before=$sz_before after=$sz_after"

# M1: encrypt failure must not leave a half-written output decoy.
echo "hello world" > "$TMP/notooxml.txt"
rm -f "$TMP/decoy.xlsx"
set +e
"$PY" office_passwd.py "$TMP/notooxml.txt" "$TMP/decoy.xlsx" --encrypt p >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && [ ! -e "$TMP/decoy.xlsx" ] \
    && ok "M1: non-OOXML --encrypt → exit 1 + output cleaned up" \
    || nok "M1 encrypt cleanup" "rc=$rc, decoy=$([ -e "$TMP/decoy.xlsx" ] && echo present || echo absent)"

# M4: office.validate.py must refuse CFB inputs with cross-3 exit 3.
set +e
err=$("$PY" -m office.validate "$TMP/enc.xlsx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] && echo "$err" | grep -q "password-protected" \
    && ok "M4: office.validate refuses encrypted xlsx with cross-3 exit 3" \
    || nok "M4 cross-3 in validate" "rc=$rc msg=$err"

# --- q-2: visual regression (xlsx → soffice → pdf, then compare) ----------
if command -v soffice >/dev/null 2>&1; then
    echo "q-2 visual regression:"
    soffice --headless --norestore --nologo --nodefault \
            "-env:UserInstallation=file://$TMP/lo-profile" \
            --convert-to pdf --outdir "$TMP" "$TMP/out.xlsx" >/dev/null 2>&1
    if [ -s "$TMP/out.pdf" ]; then
        visual_check "$TMP/out.pdf" "csv-recalc"
    else
        nok "visual: csv-recalc" "soffice did not produce out.pdf"
    fi
fi

# --- xlsx_add_comment (xlsx-6) -------------------------------------------
# v1 regression suite. Each test asserts the real OOXML shape produced
# by xlsx_add_comment.py: legacy + threaded + personList parts, sheet
# rels attachments, [Content_Types] overrides, dup-cell pre-flight gates,
# merged-cell resolver, batch-mode allocator invariants, honest-scope
# locks. Goldens block (further down) does canonical-XML diff against
# the five committed `.golden.xlsx` outputs.
echo "xlsx_add_comment (xlsx-6 v1):"

CLEAN_IN="$TMP/out.xlsx"   # already produced by csv2xlsx earlier in this run

# R8 / 2.08: turn on the in-process post-pack guard for every
# xlsx_add_comment invocation in this section. Production runs leave it
# off (latency); CI / E2E asserts it can't regress. The guard is a
# defence-in-depth check that mirrors the explicit `integrity_pair`
# below — both must agree on every produced workbook.
export XLSX_ADD_COMMENT_POST_VALIDATE=1

# R8 / 2.08: integrity-pair helper. Runs `office/validate.py` and
# `xlsx_validate.py --fail-empty` against $1; logs each as a separate
# named E2E. $2 is the test-name prefix (e.g. "T-clean-no-comments").
integrity_pair() {
    local out="$1"
    local prefix="$2"
    "$PY" -m office.validate "$out" >/dev/null 2>&1 \
        && ok "${prefix}: office.validate green" \
        || nok "${prefix}: office.validate" "rejected the produced .xlsx"
    "$PY" xlsx_validate.py "$out" --fail-empty >/dev/null 2>&1 \
        && ok "${prefix}: xlsx_validate --fail-empty green" \
        || nok "${prefix}: xlsx_validate --fail-empty" "produced workbook has empty cached values or hard errors"
}

# T-clean-no-comments — task 2.04 LANDED: clean.xlsx + --cell A5 produces
# xl/commentsN.xml + xl/drawings/vmlDrawingK.xml + Overrides + sheet rels.
# CI-diagnostic wrapper: capture stderr to file, surface on failure. The
# previous form (`>/dev/null 2>&1`) silently swallowed errors and let
# `set -euo pipefail` abort the script mid-section without context,
# leaving CI with only "Process completed with exit code 1." in the log.
set +e
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/T-clean.xlsx" \
    --cell A5 --author "Reviewer" --text "msg" >/dev/null 2>"$TMP/T-clean.err"
rc=$?
set -e
if [ "$rc" -ne 0 ] || [ ! -s "$TMP/T-clean.xlsx" ]; then
    err_blob=$(head -c 4096 "$TMP/T-clean.err" 2>/dev/null || true)
    nok "T-clean-no-comments" "exit=$rc stderr=${err_blob:-<empty>}"
fi
# Validate produced workbook + assert OOXML shape via lxml.
"$PY" -m office.validate "$TMP/T-clean.xlsx" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile, sys
from lxml import etree
SS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
with zipfile.ZipFile('$TMP/T-clean.xlsx') as z:
    names = set(z.namelist())
    assert 'xl/comments1.xml' in names, f'missing comments1: {names}'
    assert 'xl/drawings/vmlDrawing1.xml' in names, f'missing vmlDrawing1: {names}'
    assert 'xl/worksheets/_rels/sheet1.xml.rels' in names, f'missing sheet rels: {names}'
    cmt = etree.fromstring(z.read('xl/comments1.xml'))
    comments = cmt.findall(f'{SS}commentList/{SS}comment')
    assert len(comments) == 1 and comments[0].get('ref') == 'A5', comments
    rels = etree.fromstring(z.read('xl/worksheets/_rels/sheet1.xml.rels'))
    rel_types = {r.get('Type') for r in rels.findall(f'{PR}Relationship')}
    assert any('comments' in t for t in rel_types), f'comments rel missing: {rel_types}'
    assert any('vmlDrawing' in t for t in rel_types), f'vml rel missing: {rel_types}'
    ct = etree.fromstring(z.read('[Content_Types].xml'))
    parts = {ov.get('PartName') for ov in ct.findall(f'{CT}Override')}
    assert '/xl/comments1.xml' in parts, f'CT Override missing comments: {parts}'
" 2>&1 \
    && ok "T-clean-no-comments: produces commentsN+vmlDrawingK+rels+CT (full assertion)" \
    || nok "T-clean-no-comments" "lxml shape check failed"
integrity_pair "$TMP/T-clean.xlsx" "T-clean-no-comments"

# T-existing-legacy-preserve — task 2.04 LANDED: with_legacy.xlsx has 2
# pre-existing comments via openpyxl-style xl/comments/comment1.xml + 2 VML
# shapes. Adding a 3rd comment must (a) preserve original 2 byte-equivalent
# under c14n, (b) reuse the existing comments part (rels lookup, NOT
# filename-glob — the part is at a non-Excel path), (c) bump <authors>
# only if the new author is novel (m5 case-sensitive dedup).
"$PY" xlsx_add_comment.py tests/golden/inputs/with_legacy.xlsx "$TMP/T-preserve.xlsx" \
    --cell C2 --author "Auditor" --text "third comment" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] && [ -s "$TMP/T-preserve.xlsx" ] \
    && "$PY" -m office.validate "$TMP/T-preserve.xlsx" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile
from lxml import etree
SS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
with zipfile.ZipFile('$TMP/T-preserve.xlsx') as z:
    # openpyxl-style path preserved (not duplicated to Excel-style).
    cmt = etree.fromstring(z.read('xl/comments/comment1.xml'))
    comments = cmt.findall(f'{SS}commentList/{SS}comment')
    assert len(comments) == 3, f'expected 3 comments, got {len(comments)}'
    refs = [c.get('ref') for c in comments]
    assert refs == ['A2', 'B2', 'C2'], refs
    # Original 2 authors via case-sensitive dedup → new author appended.
    authors = [a.text for a in cmt.findall(f'{SS}authors/{SS}author')]
    assert authors == ['Original', 'Auditor'], authors
    # Original 2 comments byte-equivalent under c14n (only added nodes).
    orig_a2 = etree.tostring(comments[0], method='c14n')
    orig_b2 = etree.tostring(comments[1], method='c14n')
    assert b'first existing comment' in orig_a2 and b'second existing comment' in orig_b2
" 2>&1 \
    && ok "T-existing-legacy-preserve: 3 comments, original 2 byte-equivalent (m5 case-sensitive)" \
    || nok "T-existing-legacy-preserve" "exit=$rc — assertion failed"
integrity_pair "$TMP/T-preserve.xlsx" "T-existing-legacy-preserve"

# R8.b lock — task 2.08: byte-equivalence of pre-existing comments via
# canonical XML. Compare lxml.tostring(method='c14n') of each <comment>
# in the input vs output; the 2 originals must be byte-identical
# (modulo lxml-injected default xmlns), and only the new 3rd entry differs.
"$PY" -c "
import zipfile
from lxml import etree
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'

def load_legacy_comments(path):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if 'comments' in n.lower() and 'rels' not in n and not n.startswith('['):
                if n.endswith('.xml'):
                    return etree.fromstring(z.read(n))
    return None

src = load_legacy_comments('tests/golden/inputs/with_legacy.xlsx')
dst = load_legacy_comments('$TMP/T-preserve.xlsx')
src_refs = {c.get('ref'): etree.tostring(c, method='c14n') for c in src.iter(f'{{{NS}}}comment')}
dst_refs = {c.get('ref'): etree.tostring(c, method='c14n') for c in dst.iter(f'{{{NS}}}comment')}
# Every original ref must persist with byte-identical c14n.
for ref, blob in src_refs.items():
    assert ref in dst_refs, f'ref {ref} dropped from output'
    assert blob == dst_refs[ref], f'ref {ref} c14n mutated by xlsx_add_comment'
" 2>/dev/null \
    && ok "T-existing-legacy-preserve: R8.b byte-equivalence (c14n) on pre-existing <comment>s" \
    || nok "T-existing-legacy-preserve-c14n" "c14n byte-equivalence violated"

# T-threaded — task 2.05 LANDED: --threaded produces BOTH legacy (Q7
# Option A fidelity) AND threadedComments + personList. Asserts:
#   * xl/comments1.xml present (Q7 fidelity stub)
#   * xl/threadedComments1.xml — one <threadedComment> ref=A5,
#     dT pinned via --date, NO parentId (R9.a), plain-text body (R9.b)
#   * xl/persons/personList.xml — <person displayName="Q"
#     id={UUIDv5(NAMESPACE_URL,"Q")} userId="q" providerId="None">
#   * threadedComment.personId resolves to <person id>
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/T-threaded.xlsx" \
    --cell A5 --author "Q" --text "msg" --threaded \
    --date 2026-01-01T00:00:00Z >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] \
    && "$PY" -m office.validate "$TMP/T-threaded.xlsx" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile, uuid as uuid_mod
from lxml import etree
TC = '{http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments}'
with zipfile.ZipFile('$TMP/T-threaded.xlsx') as z:
    names = set(z.namelist())
    assert 'xl/comments1.xml' in names, f'Q7 fidelity legacy stub missing: {names}'
    assert 'xl/threadedComments1.xml' in names, f'threaded part missing: {names}'
    assert 'xl/persons/personList.xml' in names, f'personList missing: {names}'
    tc_root = etree.fromstring(z.read('xl/threadedComments1.xml'))
    tcs = tc_root.findall(f'{TC}threadedComment')
    assert len(tcs) == 1, len(tcs)
    tc = tcs[0]
    assert tc.get('ref') == 'A5', tc.get('ref')
    assert tc.get('dT') == '2026-01-01T00:00:00Z', tc.get('dT')
    assert tc.get('parentId') is None, 'R9.a: no parentId in v1'
    text_el = tc.find(f'{TC}text')
    assert text_el.text == 'msg' and len(list(text_el)) == 0, 'R9.b plain text'
    pl_root = etree.fromstring(z.read('xl/persons/personList.xml'))
    persons = pl_root.findall(f'{TC}person')
    assert len(persons) == 1, len(persons)
    p = persons[0]
    expected_id = '{' + str(uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, 'Q')).upper() + '}'
    assert p.get('id') == expected_id, (p.get('id'), expected_id)
    assert p.get('displayName') == 'Q'
    assert p.get('userId') == 'q'
    assert p.get('providerId') == 'None', 'literal string, NOT Python None'
    assert tc.get('personId') == expected_id, (tc.get('personId'), expected_id)
" 2>&1 \
    && { ok "T-threaded: Q7 fidelity (legacy + threaded + personList); UUIDv5 stable; R9.a/b"; integrity_pair "$TMP/T-threaded.xlsx" "T-threaded"; } \
    || nok "T-threaded" "exit=$rc — assertion failed"

# T-thread-linkage — task 2.05 LANDED: two invocations on the same
# cell append to the SAME thread (same ref + same personId), with
# distinct UUIDv4 ids per <threadedComment> (R9.e).
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/T-link-step2.xlsx" \
    --cell A5 --author "Q" --text "first" --threaded \
    --date 2026-01-01T00:00:00Z >/dev/null 2>&1 \
    && "$PY" xlsx_add_comment.py "$TMP/T-link-step2.xlsx" "$TMP/T-link-final.xlsx" \
    --cell A5 --author "Q" --text "second" --threaded \
    --date 2026-01-02T00:00:00Z >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] \
    && "$PY" -m office.validate "$TMP/T-link-final.xlsx" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile
from lxml import etree
TC = '{http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments}'
with zipfile.ZipFile('$TMP/T-link-final.xlsx') as z:
    tc_root = etree.fromstring(z.read('xl/threadedComments1.xml'))
    tcs = tc_root.findall(f'{TC}threadedComment')
    assert len(tcs) == 2, f'expected 2 threadedComments, got {len(tcs)}'
    refs = {t.get('ref') for t in tcs}
    pids = {t.get('personId') for t in tcs}
    ids = {t.get('id') for t in tcs}
    dts = {t.get('dT') for t in tcs}
    assert refs == {'A5'}, refs
    assert len(pids) == 1, f'personIds must match (single thread): {pids}'
    assert len(ids) == 2, f'<threadedComment id> must be distinct: {ids}'
    # Sarcasmotron NIT-4: pinned --date values must round-trip distinctly,
    # locking against a future regression that drops --date and inherits
    # datetime.now(UTC) on both invocations (which would still pass the
    # 'distinct ids' check above via UUIDv4 alone).
    assert dts == {'2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'}, dts
    pl = etree.fromstring(z.read('xl/persons/personList.xml'))
    persons = pl.findall(f'{TC}person')
    assert len(persons) == 1, len(persons)
" 2>&1 \
    && ok "T-thread-linkage: 2 invocations → 1 thread, 2 distinct ids, 1 person, dT pinned" \
    || nok "T-thread-linkage" "exit=$rc — assertion failed"
integrity_pair "$TMP/T-link-final.xlsx" "T-thread-linkage"

# T-threaded-rel-attachment — task 2.05 LANDED: M6 lock — personList
# Relationship MUST live on xl/_rels/workbook.xml.rels (NOT a sheet
# rels file); threadedComment Relationship MUST live on sheet rels.
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/T-rel.xlsx" \
    --cell A5 --author "Q" --text "msg" --threaded >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] \
    && "$PY" -c "
import zipfile
from lxml import etree
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
PERSON = 'http://schemas.microsoft.com/office/2017/10/relationships/person'
THREADED = 'http://schemas.microsoft.com/office/2017/10/relationships/threadedComment'
with zipfile.ZipFile('$TMP/T-rel.xlsx') as z:
    wb_rels = etree.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    wb_types = {r.get('Type') for r in wb_rels.findall(f'{PR}Relationship')}
    assert PERSON in wb_types, f'M6: personList rel missing from workbook.rels: {wb_types}'
    assert THREADED not in wb_types, f'M6: threadedComment rel WRONGLY on workbook.rels'
    sh_rels = etree.fromstring(z.read('xl/worksheets/_rels/sheet1.xml.rels'))
    sh_types = {r.get('Type') for r in sh_rels.findall(f'{PR}Relationship')}
    assert THREADED in sh_types, f'M6: threadedComment rel missing from sheet.rels: {sh_types}'
    assert PERSON not in sh_types, f'M6: personList rel WRONGLY on sheet.rels'
" 2>&1 \
    && ok "T-threaded-rel-attachment: personList on workbook.rels, threadedComment on sheet.rels (M6)" \
    || nok "T-threaded-rel-attachment" "exit=$rc"
integrity_pair "$TMP/T-rel.xlsx" "T-threaded-rel-attachment"

# T-no-threaded-no-threaded-artifacts — Q7 Option A regression: default
# mode (no --threaded) MUST NOT produce xl/threadedComments*.xml or
# xl/persons/. Locks the spec's "regression" note in task 2.05 §86-87.
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/T-noth.xlsx" \
    --cell A5 --author "Q" --text "msg" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] \
    && "$PY" -c "
import zipfile
from lxml import etree
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
PERSON = 'http://schemas.microsoft.com/office/2017/10/relationships/person'
THREADED = 'http://schemas.microsoft.com/office/2017/10/relationships/threadedComment'
with zipfile.ZipFile('$TMP/T-noth.xlsx') as z:
    names = set(z.namelist())
    assert not any(n.startswith('xl/threadedComments') for n in names), names
    assert not any(n.startswith('xl/persons/') for n in names), names
    # Sarcasmotron NIT-3: defensively assert no threaded-related rels
    # leaked into workbook.rels or sheet.rels — guards against a future
    # bug that adds the rel without writing the part (corrupt workbook
    # that office.validate would catch on next run, but this test
    # would silently miss otherwise).
    wb_rels = etree.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    wb_types = {r.get('Type') for r in wb_rels.findall(f'{PR}Relationship')}
    assert PERSON not in wb_types, f'M6 regression: orphan personList rel: {wb_types}'
    if 'xl/worksheets/_rels/sheet1.xml.rels' in names:
        sh_rels = etree.fromstring(z.read('xl/worksheets/_rels/sheet1.xml.rels'))
        sh_types = {r.get('Type') for r in sh_rels.findall(f'{PR}Relationship')}
        assert THREADED not in sh_types, f'orphan threadedComment rel: {sh_types}'
" 2>&1 \
    && ok "T-no-threaded-no-threaded-artifacts: parts AND rels both absent (Q7 + NIT-3 lock)" \
    || nok "T-no-threaded-no-threaded-artifacts" "exit=$rc"
integrity_pair "$TMP/T-noth.xlsx" "T-no-threaded-no-threaded-artifacts"

# T-multi-sheet — task 2.04 LANDED: comment on Sheet2 binds via
# xl/worksheets/_rels/sheet2.xml.rels (NOT sheet1.xml.rels). The
# commentsN filename is part-counter, NOT sheet-index — N=1 because no
# other sheets had comments before this run.
"$PY" xlsx_add_comment.py tests/golden/inputs/multi_sheet.xlsx "$TMP/T-multi.xlsx" \
    --cell "Sheet2!B5" --author "Q" --text "on sheet2" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] \
    && "$PY" -m office.validate "$TMP/T-multi.xlsx" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile
from lxml import etree
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
SS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
with zipfile.ZipFile('$TMP/T-multi.xlsx') as z:
    names = set(z.namelist())
    assert 'xl/worksheets/_rels/sheet2.xml.rels' in names, names
    assert 'xl/comments1.xml' in names, names
    rels = etree.fromstring(z.read('xl/worksheets/_rels/sheet2.xml.rels'))
    targets = [r.get('Target') for r in rels.findall(f'{PR}Relationship')]
    assert any('comments1.xml' in t for t in targets), targets
    cmt = etree.fromstring(z.read('xl/comments1.xml'))
    refs = [c.get('ref') for c in cmt.findall(f'{SS}commentList/{SS}comment')]
    assert refs == ['B5'], refs
" 2>&1 \
    && { ok "T-multi-sheet: comment binds to Sheet2 via sheet2.xml.rels (commentsN part-counter)"; integrity_pair "$TMP/T-multi.xlsx" "T-multi-sheet"; } \
    || nok "T-multi-sheet" "exit=$rc — assertion failed"

# T-pack-failure-no-orphan — Sarcasmotron MAJ-2 lock: if pack fails
# mid-write the partial OUTPUT zip must be cleaned up (mirrors
# office_passwd.py's M1 pattern). Trigger pack failure by pointing
# OUTPUT into a non-existent / unwritable directory.
mkdir -p "$TMP/readonly_dir" && chmod 555 "$TMP/readonly_dir"
set +e
"$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/readonly_dir/orphan.xlsx" \
    --cell A5 --author Q --text msg >/dev/null 2>&1
rc=$?
set -e
chmod 755 "$TMP/readonly_dir" 2>/dev/null
[ "$rc" -ne 0 ] && [ ! -e "$TMP/readonly_dir/orphan.xlsx" ] \
    && ok "T-pack-failure-no-orphan: failed pack does NOT leave half-written output" \
    || nok "T-pack-failure-no-orphan" "rc=$rc, output=$([ -e "$TMP/readonly_dir/orphan.xlsx" ] && echo present || echo absent)"

# T-EmptyCommentBody — task 2.04 LANDED: --text "" or whitespace-only →
# exit 2 EmptyCommentBody (Q2 closure). Tests both empty + whitespace.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_empty.xlsx" \
    --cell A5 --author Q --text "" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='EmptyCommentBody', j" 2>/dev/null \
    && ok "T-EmptyCommentBody: --text '' → exit 2 EmptyCommentBody (Q2)" \
    || nok "T-EmptyCommentBody" "exit=$rc msg=$err"

set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_ws.xlsx" \
    --cell A5 --author Q --text "   " --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='EmptyCommentBody', j" 2>/dev/null \
    && ok "T-EmptyCommentBody-whitespace: --text '   ' → exit 2 (Q2 strict)" \
    || nok "T-EmptyCommentBody-whitespace" "exit=$rc msg=$err"

# T-merged-cell-target — task 2.07: B2 in merged A1:C3 (non-anchor) with
# no --allow-merged-target → exit 2 MergedCellTarget envelope.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/merged.xlsx "$TMP/T-merged.xlsx" \
    --cell B2 --author "Q" --text "msg" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['code'] == 2 and j['type'] == 'MergedCellTarget', j
assert j['details']['anchor'] == 'A1', j
assert j['details']['range'] == 'A1:C3', j
" 2>/dev/null \
    && ok "T-merged-cell-target: B2 non-anchor in A1:C3 → exit 2 MergedCellTarget envelope" \
    || nok "T-merged-cell-target" "exit=$rc msg=$err"

# T-merged-cell-redirect — task 2.07: --allow-merged-target redirects
# B2 → A1; exit 0; comment lands on A1; stderr mentions MergedCellRedirect.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/merged.xlsx "$TMP/T-redirect.xlsx" \
    --cell B2 --author "Q" --text "msg" --allow-merged-target 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && echo "$err" | grep -q "MergedCellRedirect" \
    && "$PY" -c "
import zipfile
with zipfile.ZipFile('$TMP/T-redirect.xlsx') as z:
    cx = z.read('xl/comments1.xml').decode()
assert '<comment ref=\"A1\"' in cx, 'expected redirected comment on A1'
" 2>/dev/null \
    && ok "T-merged-cell-redirect: --allow-merged-target → comment on anchor A1 + stderr note" \
    || nok "T-merged-cell-redirect" "exit=$rc msg=$err"
integrity_pair "$TMP/T-redirect.xlsx" "T-merged-cell-redirect"

# T-merged-cell-anchor-passthrough — task 2.07 / R6.c: A1 IS the anchor of
# A1:C3, so no error and no redirect — comment lands on A1 directly.
"$PY" xlsx_add_comment.py tests/golden/inputs/merged.xlsx "$TMP/T-anchor.xlsx" \
    --cell A1 --author "Q" --text "msg" >/dev/null 2>&1 \
    && [ -s "$TMP/T-anchor.xlsx" ] \
    && "$PY" -c "
import zipfile
with zipfile.ZipFile('$TMP/T-anchor.xlsx') as z:
    cx = z.read('xl/comments1.xml').decode()
assert '<comment ref=\"A1\"' in cx, 'expected comment on anchor A1'
" 2>/dev/null \
    && ok "T-merged-cell-anchor-passthrough: A1 is anchor of A1:C3 → comment lands directly (R6.c)" \
    || nok "T-merged-cell-anchor-passthrough" "passthrough failed"
integrity_pair "$TMP/T-anchor.xlsx" "T-merged-cell-anchor-passthrough"

# T-duplicate-legacy — task 2.07 / R5.b: with_legacy.xlsx has comment at
# A2; --cell A2 --no-threaded → exit 2 DuplicateLegacyComment envelope.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/with_legacy.xlsx "$TMP/T-dup-leg.xlsx" \
    --cell A2 --author "Q" --text "msg" --no-threaded --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['code'] == 2 and j['type'] == 'DuplicateLegacyComment', j
assert j['details']['cell'] == 'A2', j
" 2>/dev/null \
    && ok "T-duplicate-legacy: --no-threaded over existing legacy → DuplicateLegacyComment (R5.b)" \
    || nok "T-duplicate-legacy" "exit=$rc msg=$err"

# T-duplicate-threaded-blocked — task 2.07 / M-2: build a workbook with
# an existing thread (one round-trip with --threaded), then attempt a
# legacy-only write over the same cell → exit 2 DuplicateThreadedComment
# (NEW envelope per ARCHITECTURE §6.2).
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/with-thread.xlsx" \
    --cell A5 --author "T1" --text "first" --threaded >/dev/null 2>&1
set +e
err=$("$PY" xlsx_add_comment.py "$TMP/with-thread.xlsx" "$TMP/T-dup-thr-block.xlsx" \
    --cell A5 --author "T2" --text "should-fail" --no-threaded --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['code'] == 2 and j['type'] == 'DuplicateThreadedComment', j
assert j['details']['cell'] == 'A5', j
assert j['details']['existing_thread_size'] == 1, j
" 2>/dev/null \
    && ok "T-duplicate-threaded-blocked: --no-threaded over thread → DuplicateThreadedComment (M-2)" \
    || nok "T-duplicate-threaded-blocked" "exit=$rc msg=$err"

# T-duplicate-threaded-append — task 2.07 / R5.a: same input but
# --threaded appends a second entry; thread size grows to 2.
"$PY" xlsx_add_comment.py "$TMP/with-thread.xlsx" "$TMP/T-dup-thr-app.xlsx" \
    --cell A5 --author "T2" --text "second" --threaded >/dev/null 2>&1 \
    && [ -s "$TMP/T-dup-thr-app.xlsx" ] \
    && "$PY" -c "
import zipfile
with zipfile.ZipFile('$TMP/T-dup-thr-app.xlsx') as z:
    tc = next(z.read(n).decode() for n in z.namelist() if 'threadedComments' in n and 'rels' not in n)
n = tc.count('<threadedComment ')
assert n == 2, f'expected 2 threadedComment entries, got {n}'
" 2>/dev/null \
    && ok "T-duplicate-threaded-append: --threaded over thread → 2 entries (R5.a)" \
    || nok "T-duplicate-threaded-append" "append failed"
integrity_pair "$TMP/T-dup-thr-app.xlsx" "T-duplicate-threaded-append"

# T-batch-self-collision — task 2.07 (Sarcasmotron MINOR fix): batch
# rows with same cell + mixed modes must honour the M-2 invariant as
# an OUTPUT-invariant, not just an input-state gate. Row 1 writes a
# threaded comment; row 2 attempts a legacy-only over the same cell —
# must fail with DuplicateThreadedComment.
"$PY" -c "
import json
rows = [
    {'cell': 'A5', 'author': 'T1', 'text': 'first', 'threaded': True},
    {'cell': 'A5', 'author': 'T2', 'text': 'second', 'threaded': False},
]
open('$TMP/batch_self_collision.json', 'w').write(json.dumps(rows))
"
set +e
err=$("$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-batch-self-coll.xlsx" \
    --batch "$TMP/batch_self_collision.json" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['type'] == 'DuplicateThreadedComment', j
assert j['details']['cell'] == 'A5', j
" 2>/dev/null \
    && ok "T-batch-self-collision: in-batch threaded→legacy on same cell → DuplicateThreadedComment (M-2 output-invariant)" \
    || nok "T-batch-self-collision" "exit=$rc msg=$err"

# T-batch-50 — task 2.06: 50 rows on clean input → 50 comments, no
# o:spid collisions, validates clean. Cells start at A52 to keep the
# T-batch-50-with-existing-vml variant clear of with_legacy.xlsx's
# pre-existing A2/B2 entries (otherwise task 2.07's DuplicateLegacyComment
# pre-flight gate would fire on the very first row).
"$PY" -c "
import json
rows = [{'cell': f'A{i+52}', 'author': 'Bot', 'text': f'note {i}'} for i in range(50)]
open('$TMP/batch50.json', 'w').write(json.dumps(rows))
"
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-b50.xlsx" \
    --batch "$TMP/batch50.json" >/dev/null 2>&1 \
    && [ -s "$TMP/T-b50.xlsx" ] \
    && "$PY" -c "
import zipfile, re, sys
with zipfile.ZipFile('$TMP/T-b50.xlsx') as z:
    comments_xml = z.read('xl/comments1.xml').decode()
    vml_xml = z.read('xl/drawings/vmlDrawing1.xml').decode()
n = len(re.findall(r'<comment ', comments_xml))
spids = re.findall(r'spid=\"(_x0000_s\d+)\"', vml_xml)
assert n == 50, f'expected 50 comments, got {n}'
assert len(spids) == 50, f'expected 50 spids, got {len(spids)}'
assert len(set(spids)) == 50, f'spid collision: {len(set(spids))} unique of {len(spids)}'
" 2>/dev/null \
    && "$PY" office/validate.py "$TMP/T-b50.xlsx" >/dev/null 2>&1 \
    && { ok "T-batch-50: 50 comments, 50 unique spids, validate.py OK"; integrity_pair "$TMP/T-b50.xlsx" "T-batch-50"; } \
    || nok "T-batch-50" "batch-50 assertions or validate failed"

# T-batch-50-with-existing-vml — task 2.06: input already has VML
# (with_legacy fixture: <o:idmap data="1"/> + _x0000_s1025); new shapes
# use disjoint o:spid integers (m-1 / C1 / R4.h incremental allocator).
"$PY" xlsx_add_comment.py tests/golden/inputs/with_legacy.xlsx "$TMP/T-b50v.xlsx" \
    --batch "$TMP/batch50.json" >/dev/null 2>&1 \
    && [ -s "$TMP/T-b50v.xlsx" ] \
    && "$PY" -c "
import zipfile, re, sys
with zipfile.ZipFile('$TMP/T-b50v.xlsx') as z:
    # with_legacy uses openpyxl naming under xl/drawings/commentsDrawing*.vml
    # (reused via sheet rels — the rels-driven lookup ignores the filename).
    vml_path = next(n for n in z.namelist()
                    if 'drawings' in n and n.endswith(('.vml', '.xml')))
    vml_xml = z.read(vml_path).decode()
# Existing shapes wrote 'id=' only; new shapes write BOTH 'id=' and 'o:spid='
# (so a 'spid=' regex misses existing 1026/1027 — use the unified union of
# all _x0000_s\\d+ attribute occurrences). Pre-existing fixture has 2 shapes;
# 50 new + 2 existing = 52 unique IDs across the part.
all_sids = set(re.findall(r'_x0000_s(\d+)', vml_xml))
assert len(all_sids) == 52, f'expected 52 unique spids (2 existing + 50 new), got {len(all_sids)}'
assert all(int(s) >= 1025 for s in all_sids), f'spid below 1025: {min(all_sids, key=int)}'
" 2>/dev/null \
    && "$PY" office/validate.py "$TMP/T-b50v.xlsx" >/dev/null 2>&1 \
    && { ok "T-batch-50-with-existing-vml: 52 disjoint spids (R4.h incremental allocator)"; integrity_pair "$TMP/T-b50v.xlsx" "T-batch-50-with-existing-vml"; } \
    || nok "T-batch-50-with-existing-vml" "incremental-allocator assertions or validate failed"

# T-batch-envelope-mode — task 2.06 / I2.2: xlsx-7 envelope auto-detect.
# Envelope shape requires --default-author (DEP-2). Findings are mapped
# cell ← finding.cell, text ← finding.message; row=null is skipped.
"$PY" -c "
import json
env = {
    'ok': False,
    'summary': {'errors': 2, 'warnings': 0, 'findings': 3},
    'findings': [
        {'cell': 'A2', 'row': 2, 'col': 'A', 'message': 'env note 1'},
        {'cell': 'B3', 'row': 3, 'col': 'B', 'message': 'env note 2'},
        {'cell': 'C5', 'row': 5, 'col': 'C', 'message': 'env note 3'},
    ],
}
open('$TMP/envelope.json', 'w').write(json.dumps(env))
"
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-env.xlsx" \
    --batch "$TMP/envelope.json" --default-author "Validator" >/dev/null 2>&1 \
    && "$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/T-env.xlsx') as z:
    cx = z.read('xl/comments1.xml').decode()
n = len(re.findall(r'<comment ', cx))
assert n == 3, f'expected 3 comments from envelope, got {n}'
assert 'Validator' in cx, 'envelope must use --default-author'
assert 'env note 2' in cx, 'finding[1].message missing'
" 2>/dev/null \
    && ok "T-batch-envelope-mode: xlsx-7 envelope auto-detect + DEP-2 default-author" \
    || nok "T-batch-envelope-mode" "envelope assertions failed"
integrity_pair "$TMP/T-env.xlsx" "T-batch-envelope-mode"

# T-batch-skipped-grouped — task 2.06 / R4.e: row=null findings are
# silently skipped + counted, info note emitted to stderr.
"$PY" -c "
import json
env = {
    'ok': False,
    'summary': {'errors': 1, 'warnings': 1, 'findings': 2},
    'findings': [
        {'cell': 'A2', 'row': 2, 'col': 'A', 'message': 'real'},
        {'cell': None, 'row': None, 'col': None, 'message': 'group-only'},
    ],
}
open('$TMP/env_skip.json', 'w').write(json.dumps(env))
"
set +e
err=$("$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-skip.xlsx" \
    --batch "$TMP/env_skip.json" --default-author "V" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && echo "$err" | grep -q "skipped 1 group-finding" \
    && "$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/T-skip.xlsx') as z:
    cx = z.read('xl/comments1.xml').decode()
assert len(re.findall(r'<comment ', cx)) == 1, 'expected exactly 1 non-skipped comment'
" 2>/dev/null \
    && ok "T-batch-skipped-grouped: row=null skipped + stderr 'skipped 1 group-finding'" \
    || nok "T-batch-skipped-grouped" "exit=$rc msg=$err"

# T-apostrophe-sheet (R2 / I1.1) — quoted sheet name 'Sheet1'!A1
# unwraps to ("Sheet1", "A1"); 'Bob''s Sheet'!A1 unwraps via the
# apostrophe-escape ''→'. Exit 0 + non-empty output + integrity_pair
# is the contract; the parser unit tests exercise the grammar in detail.
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-apos.xlsx" \
    --cell "'Sheet1'!A1" --author "Q" --text "msg" >/dev/null 2>&1 \
    && [ -s "$TMP/T-apos.xlsx" ] \
    && ok "T-apostrophe-sheet: 'Sheet1'!A1 quoted-form round-trip (R2)" \
    || nok "T-apostrophe-sheet" "failed to produce output"
integrity_pair "$TMP/T-apos.xlsx" "T-apostrophe-sheet"

# T-same-path — cross-7 H1: INPUT == OUTPUT → exit 6 SelfOverwriteRefused.
set +e
err=$("$PY" xlsx_add_comment.py "$CLEAN_IN" "$CLEAN_IN" \
    --cell A5 --author "Q" --text "msg" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==6 and j['type']=='SelfOverwriteRefused' and j['v']==1, j" 2>/dev/null \
    && ok "T-same-path → exit 6 SelfOverwriteRefused envelope (cross-7 H1)" \
    || nok "T-same-path" "exit=$rc msg=$err"

# T-encrypted — task 2.01 LANDED: encrypted input → exit 3
# EncryptedFileError envelope. Use the real golden fixture from task
# 1.04 (created via office_passwd.py --encrypt); the cfb.xlsx forged
# earlier in this script also triggers exit 3 via the same CFB-magic
# pre-flight check (cross-3 covers both encrypted-OOXML and legacy-CFB).
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/encrypted.xlsx "$TMP/T-enc.xlsx" \
    --cell A5 --author "Q" --text "msg" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 3 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==3 and j['type']=='EncryptedFileError' and j['v']==1, j" 2>/dev/null \
    && [ ! -e "$TMP/T-enc.xlsx" ] \
    && ok "T-encrypted → exit 3 EncryptedFileError envelope (cross-3, no output)" \
    || nok "T-encrypted" "exit=$rc msg=$err"

# T-macro-xlsm-preserves — task 2.08 / R8.c: .xlsm → .xlsm round-trip
# preserves xl/vbaProject.bin byte-for-byte (sha256 invariant). Uses
# the real macro.xlsm fixture from 1.04 (LibreOffice-emitted .xlsm
# with the standard macro module). Asserts:
#   1. exit 0;
#   2. produced .xlsm has xl/vbaProject.bin (non-empty);
#   3. sha256 of produced vbaProject.bin == sha256 of source's;
#   4. stderr does NOT contain a macro-loss warning (extension preserved).
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/macro.xlsm "$TMP/T-macro-preserve.xlsm" \
    --cell A5 --author "Q" --text "msg" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && ! echo "$err" | grep -qE '^Warning:.*macro' \
    && "$PY" -c "
import zipfile, hashlib
def vba_sha(path):
    with zipfile.ZipFile(path) as z:
        if 'xl/vbaProject.bin' not in z.namelist():
            return None
        return hashlib.sha256(z.read('xl/vbaProject.bin')).hexdigest()
src = vba_sha('tests/golden/inputs/macro.xlsm')
dst = vba_sha('$TMP/T-macro-preserve.xlsm')
assert src is not None, 'source has no vbaProject.bin'
assert dst is not None, 'output dropped vbaProject.bin'
assert src == dst, f'vbaProject.bin sha256 changed: {src} -> {dst}'
" 2>/dev/null \
    && ok "T-macro-xlsm-preserves: .xlsm → .xlsm preserves xl/vbaProject.bin (sha256 invariant, R8.c)" \
    || nok "T-macro-xlsm-preserves" "exit=$rc msg=$err"

# T-macro-xlsm-warns — task 2.01 LANDED: .xlsm → .xlsx fires cross-4
# warning to stderr, exit still 0. Real golden fixture from 1.04.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/macro.xlsm "$TMP/T-macro-as-xlsx.xlsx" \
    --cell A5 --author "Q" --text "msg" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && echo "$err" | grep -qi "macro" \
    && [ -s "$TMP/T-macro-as-xlsx.xlsx" ] \
    && ok "T-macro-xlsm-warns: .xlsm → .xlsx exits 0 + stderr mentions 'macro' (cross-4)" \
    || nok "T-macro-xlsm-warns" "exit=$rc msg=$err"

# T-macro-xlsm-no-warning — task 2.01: .xlsm → .xlsm same extension
# does NOT fire the cross-4 macro-WILL-be-dropped warning.
# (office.unpack itself emits an informational `Note:` on macro-enabled
# inputs which is fine and unrelated to cross-4 — we narrow the negative
# match to the cross-4 Warning text, not "macro" generic.)
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/macro.xlsm "$TMP/T-macro-as-xlsm.xlsm" \
    --cell A5 --author "Q" --text "msg" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && ! echo "$err" | grep -qE '^Warning:.*macro' \
    && [ -s "$TMP/T-macro-as-xlsm.xlsm" ] \
    && ok "T-macro-xlsm-no-warning: .xlsm → .xlsm exits 0, NO cross-4 Warning: prefix" \
    || nok "T-macro-xlsm-no-warning" "exit=$rc msg=$err"

# T-MX-A — task 2.01 LANDED: --cell and --batch together → exit 2 UsageError.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_x.xlsx" \
    --cell A5 --batch tests/golden/inputs/clean.xlsx --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='UsageError' and 'mutually exclusive' in j['error'], j" 2>/dev/null \
    && ok "T-MX-A: --cell + --batch → UsageError 'mutually exclusive'" \
    || nok "T-MX-A" "exit=$rc msg=$err"

# T-MX-B — task 2.01 LANDED: --threaded and --no-threaded → exit 2.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_x.xlsx" \
    --cell A5 --author Q --text msg --threaded --no-threaded --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='UsageError', j" 2>/dev/null \
    && ok "T-MX-B: --threaded + --no-threaded → UsageError" \
    || nok "T-MX-B" "exit=$rc msg=$err"

# T-DEP-1 — task 2.01 LANDED: --cell without --text → exit 2.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_x.xlsx" \
    --cell A5 --author Q --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | grep -q "DEP-1" \
    && ok "T-DEP-1: --cell missing --text → UsageError DEP-1" \
    || nok "T-DEP-1" "exit=$rc msg=$err"

# T-DEP-3 — task 2.01 LANDED: --default-threaded with --cell → exit 2.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_x.xlsx" \
    --cell A5 --author Q --text msg --default-threaded --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | grep -q "DEP-3" \
    && ok "T-DEP-3: --default-threaded with --cell → UsageError DEP-3" \
    || nok "T-DEP-3" "exit=$rc msg=$err"

# T-DEP-4 — task 2.01: argparse usage errors with --json-errors must
# route through report_error (DEP-4 wired by add_json_errors_argument's
# parser.error monkey-patch in _errors.py). Sarcasmotron M-1 lock —
# protects against drift on the 4-skill-replicated _errors.py.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/clean.xlsx "$TMP/_x.xlsx" \
    --cell A5 --author Q --text msg --bogus-flag --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==2 and j['type']=='UsageError' and j['v']==1, j" 2>/dev/null \
    && ok "T-DEP-4: argparse usage error → JSON envelope (cross-5 wired through parser.error)" \
    || nok "T-DEP-4" "exit=$rc msg=$err"

# T-encrypted-same-path — task 2.01: precedence test. INPUT == OUTPUT
# AND both encrypted: same-path guard wins (exit 6, no encryption sniff).
# Sarcasmotron M-2 lock.
set +e
err=$("$PY" xlsx_add_comment.py tests/golden/inputs/encrypted.xlsx tests/golden/inputs/encrypted.xlsx \
    --cell A5 --author Q --text msg --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==6 and j['type']=='SelfOverwriteRefused', j" 2>/dev/null \
    && ok "T-encrypted-same-path: same-path wins over encryption (exit 6, source untouched)" \
    || nok "T-encrypted-same-path" "exit=$rc msg=$err"

# T-same-path-symlink — task 2.01 LANDED: symlink resolves to same path → exit 6.
cp tests/golden/inputs/clean.xlsx "$TMP/sym_target.xlsx"
ln -sf "$TMP/sym_target.xlsx" "$TMP/sym_link.xlsx"
set +e
err=$("$PY" xlsx_add_comment.py "$TMP/sym_target.xlsx" "$TMP/sym_link.xlsx" \
    --cell A5 --author Q --text msg --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==6 and j['type']=='SelfOverwriteRefused', j" 2>/dev/null \
    && ok "T-same-path-symlink: in/out symlinked → exit 6 SelfOverwriteRefused (Path.resolve)" \
    || nok "T-same-path-symlink" "exit=$rc msg=$err"

# T-hidden-first-sheet (M2) — unqualified --cell A5 on a workbook with
# hidden Sheet1 lands on the first-VISIBLE sheet, not the first sheet.
# Note: $CLEAN_IN doesn't actually have a hidden first sheet; this test
# exercises the resolver's no-op path (no hidden state) — the M2 rule
# is unit-tested in test_xlsx_add_comment.py::TestSheetResolver.
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-hidden.xlsx" \
    --cell A5 --author "Q" --text "msg" >/dev/null 2>&1 \
    && [ -s "$TMP/T-hidden.xlsx" ] \
    && ok "T-hidden-first-sheet: unqualified --cell resolves via first-VISIBLE rule (M2)" \
    || nok "T-hidden-first-sheet" "failed to produce output"
integrity_pair "$TMP/T-hidden.xlsx" "T-hidden-first-sheet"

# T-idmap-conflict (R1.h / M-1 / C1) — clean input has no existing VML;
# the script's allocator still emits disjoint <o:idmap data> + o:spid
# integers. The list-aware scanner is unit-tested in
# test_xlsx_add_comment.py::TestIdmapScanner; the with_legacy fixture
# covers the multi-claim path through T-batch-50-with-existing-vml.
"$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-idmap.xlsx" \
    --cell A5 --author "Q" --text "msg" >/dev/null 2>&1 \
    && [ -s "$TMP/T-idmap.xlsx" ] \
    && ok "T-idmap-conflict: allocator emits disjoint integers (R1.h / M-1)" \
    || nok "T-idmap-conflict" "failed to produce output"
integrity_pair "$TMP/T-idmap.xlsx" "T-idmap-conflict"

# T-BatchTooLarge — task 2.06 / m2 / m-4: > 8 MiB batch input → exit 2
# BatchTooLarge envelope with details.size_bytes populated.
# (truncate is GNU on Linux, not always present on macOS — fall back to dd.)
truncate -s 9000000 "$TMP/big.json" 2>/dev/null \
    || dd if=/dev/zero of="$TMP/big.json" bs=1000000 count=9 2>/dev/null
set +e
err=$("$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-big.xlsx" \
    --batch "$TMP/big.json" --default-author "B" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['code'] == 2, j
assert j['type'] == 'BatchTooLarge', j
assert j['v'] == 1, j
assert j['details']['size_bytes'] == 9000000, j
" 2>/dev/null \
    && ok "T-BatchTooLarge: exit 2 BatchTooLarge envelope (size_bytes=9000000)" \
    || nok "T-BatchTooLarge" "exit=$rc msg=$err"

# T-batch-cap-boundary — task 2.06 / m-4: exactly-8-MiB batch is accepted
# (does not raise BatchTooLarge); the cap is strictly >, not >=. JSON
# content invalidity is fine — load_batch raises InvalidBatchInput, NOT
# BatchTooLarge. We assert the failure mode is shape, not size.
"$PY" -c "
with open('$TMP/exact8mib.json', 'wb') as f:
    f.write(b'A' * (8 * 1024 * 1024))
"
set +e
err=$("$PY" xlsx_add_comment.py "$CLEAN_IN" "$TMP/T-exact8mib.xlsx" \
    --batch "$TMP/exact8mib.json" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "
import sys, json
j = json.loads(sys.stdin.read())
assert j['type'] == 'InvalidBatchInput', j  # NOT BatchTooLarge — boundary respected
" 2>/dev/null \
    && ok "T-batch-cap-boundary: exactly-8-MiB accepted past size gate (m-4 boundary)" \
    || nok "T-batch-cap-boundary" "exit=$rc msg=$err"

# --- Goldens diff (task 2.10 / m-5 / A-Q3) -------------------------------
# Five named goldens (clean-no-comments / existing-legacy-preserve /
# threaded / multi-sheet / idmap-conflict). Each is regenerated from
# the live xlsx_add_comment.py with --date 2026-01-01T00:00:00Z and
# compared against the committed golden via _golden_diff.diff_xlsx
# (c14n + volatile-attr mask). Tests OUTSIDE this block rely on
# exit-code + lxml-assertion only — canonical diff is for stable-shape
# outputs, not for exit-code-error tests (m-C plan-review clarification).
echo "xlsx_add_comment goldens (task 2.10):"

run_golden() {
    local input="$1"
    local out="$2"
    local golden="$3"
    local extra="$4"
    local name="$5"
    "$PY" xlsx_add_comment.py "$input" "$out" $extra \
        --date 2026-01-01T00:00:00Z >/dev/null 2>&1 || {
        nok "$name" "xlsx_add_comment exited non-zero"
        return
    }
    "$PY" -c "
import sys
sys.path.insert(0, 'tests')
from _golden_diff import diff_xlsx
result = diff_xlsx('$out', '$golden')
if result is not None:
    print(result, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null \
        && ok "$name" \
        || nok "$name" "golden-diff mismatch (run: PY -c 'from _golden_diff import diff_xlsx; print(diff_xlsx(\"$out\", \"$golden\"))')"
}

run_golden "tests/golden/inputs/clean.xlsx" "$TMP/g-clean.xlsx" \
    "tests/golden/outputs/clean-no-comments.golden.xlsx" \
    "--cell A5 --author Reviewer --text msg" \
    "T-golden-clean-no-comments"

run_golden "tests/golden/inputs/with_legacy.xlsx" "$TMP/g-existing.xlsx" \
    "tests/golden/outputs/existing-legacy-preserve.golden.xlsx" \
    "--cell C5 --author Validator --text new_finding" \
    "T-golden-existing-legacy-preserve"

run_golden "tests/golden/inputs/clean.xlsx" "$TMP/g-thr.xlsx" \
    "tests/golden/outputs/threaded.golden.xlsx" \
    "--cell A5 --author Reviewer --text thread_starter --threaded" \
    "T-golden-threaded"

run_golden "tests/golden/inputs/multi_sheet.xlsx" "$TMP/g-multi.xlsx" \
    "tests/golden/outputs/multi-sheet.golden.xlsx" \
    "--cell Sheet2!B3 --author Q --text cross_sheet" \
    "T-golden-multi-sheet"

run_golden "tests/golden/inputs/with_legacy.xlsx" "$TMP/g-idmap.xlsx" \
    "tests/golden/outputs/idmap-conflict.golden.xlsx" \
    "--cell D7 --author Q --text added_shape" \
    "T-golden-idmap-conflict"

# ---------------------------------------------------------------------------
# xlsx_check_rules (xlsx-7) — block expanded incrementally by tasks 003.05+.
# In task-003-02 this block contains the happy-path smoke only; per-fixture
# E2E checks are added once the relevant F-region ships.
# ---------------------------------------------------------------------------
echo
echo "xlsx_check_rules (xlsx-7):"
"$PY" "$SKILL_DIR/xlsx_check_rules.py" --help > /dev/null 2>&1 \
    && ok "xlsx-7-help" \
    || nok "xlsx-7-help" "--help did not exit 0"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
