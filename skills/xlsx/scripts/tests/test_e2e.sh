#!/usr/bin/env bash
# End-to-end smoke tests for the xlsx skill.
#
# Run:  bash skills/xlsx/scripts/tests/test_e2e.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t xlsx_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

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

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
