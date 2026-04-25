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

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
