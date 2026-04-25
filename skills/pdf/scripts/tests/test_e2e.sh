#!/usr/bin/env bash
# End-to-end smoke tests for the pdf skill.
#
# Runs each user-facing CLI on a fixture, verifies the output exists
# and has the expected shape. Self-contained: builds its own AcroForm
# fixture via reportlab so the AcroForm path is exercised without
# shipping a binary fixture in examples/.
#
# Run:  bash skills/pdf/scripts/tests/test_e2e.sh
# Or:   from anywhere; the script cd's to its own directory first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t pdf_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

# --- md2pdf -----------------------------------------------------------------
echo "md2pdf:"
"$PY" md2pdf.py ../examples/fixture.md "$TMP/out.pdf" --no-mermaid >/dev/null 2>&1 \
    && [ -s "$TMP/out.pdf" ] && ok "fixture.md → out.pdf" \
    || nok "fixture.md → out.pdf" "missing or empty"

# --- pdf_merge --------------------------------------------------------------
echo "pdf_merge:"
"$PY" md2pdf.py ../examples/fixture.md "$TMP/a.pdf" --no-mermaid >/dev/null 2>&1
"$PY" md2pdf.py ../examples/fixture.md "$TMP/b.pdf" --no-mermaid >/dev/null 2>&1
"$PY" pdf_merge.py "$TMP/merged.pdf" "$TMP/a.pdf" "$TMP/b.pdf" >/dev/null 2>&1 \
    && [ -s "$TMP/merged.pdf" ] && ok "merge a + b → merged.pdf" \
    || nok "merge a + b → merged.pdf" "missing or empty"

# Verify page count = sum
pages_a=$("$PY" -c "import pypdf; print(len(pypdf.PdfReader('$TMP/a.pdf').pages))")
pages_m=$("$PY" -c "import pypdf; print(len(pypdf.PdfReader('$TMP/merged.pdf').pages))")
[ "$pages_m" -eq "$((pages_a * 2))" ] \
    && ok "merged page count = sum ($pages_m)" \
    || nok "merged page count" "expected $((pages_a * 2)), got $pages_m"

# --- pdf_split --------------------------------------------------------------
echo "pdf_split:"
mkdir -p "$TMP/split"
"$PY" pdf_split.py "$TMP/merged.pdf" --each-page "$TMP/split/" >/dev/null 2>&1
n=$(ls "$TMP/split/" | wc -l | tr -d ' ')
[ "$n" -eq "$pages_m" ] \
    && ok "--each-page → $n files" \
    || nok "--each-page" "expected $pages_m, got $n"

# --- pdf_fill_form ---------------------------------------------------------
echo "pdf_fill_form:"
"$PY" tests/_acroform_fixture.py "$TMP/form.pdf"
"$PY" pdf_fill_form.py --check "$TMP/form.pdf" >/dev/null 2>&1 \
    && ok "--check returns 0 on AcroForm" \
    || nok "--check on AcroForm" "non-zero exit"

# --check on a non-form PDF should exit 12 (EXIT_NO_FORM, refactored
# from 3 → 12 to leave 0–9 for argparse / shell convention).
set +e
"$PY" pdf_fill_form.py --check "$TMP/a.pdf" >/dev/null 2>&1
[ "$?" -eq 12 ] && ok "--check returns 12 on non-form PDF" || nok "--check on non-form" "wrong exit code"
set -e

# Fill round-trip
cat > "$TMP/data.json" <<'JSON'
{"customer_name": "Acme Inc.", "invoice_date": "2026-04-25", "agree_terms": "/Yes"}
JSON
"$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/data.json" -o "$TMP/filled.pdf" >/dev/null 2>&1
filled=$("$PY" -c "
from pypdf import PdfReader
f = PdfReader('$TMP/filled.pdf').get_fields()
import json; print(json.dumps({k: str(v.get('/V')) for k, v in f.items()}))
")
echo "$filled" | grep -q '"customer_name": "Acme Inc."' \
    && ok "fill: customer_name persisted" \
    || nok "fill: customer_name" "got $filled"
echo "$filled" | grep -q '"agree_terms": "/Yes"' \
    && ok "fill: checkbox /Yes persisted" \
    || nok "fill: checkbox" "got $filled"

# --- pdf_fill_form: error-path coverage -----------------------------------
echo "pdf_fill_form (error paths):"

# --extract-fields with no -o → JSON to stdout
out=$("$PY" pdf_fill_form.py --extract-fields "$TMP/form.pdf" 2>&1)
echo "$out" | grep -q '"acroform"' \
    && ok "--extract-fields stdout returns AcroForm JSON" \
    || nok "--extract-fields stdout" "missing 'acroform' marker"

# Malformed JSON should be a usage error (argparse exit 2)
echo 'not valid json {' > "$TMP/bad.json"
set +e
"$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/bad.json" -o "$TMP/_x.pdf" >/dev/null 2>&1
[ "$?" -eq 2 ] && ok "malformed JSON exits 2 (usage error)" || nok "malformed JSON exit" "got $?"
set -e

# Missing -o in fill mode → usage error
set +e
"$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/data.json" >/dev/null 2>&1
[ "$?" -eq 2 ] && ok "missing -o exits 2 (usage error)" || nok "missing -o exit" "got $?"
set -e

# Typo'd field name should fill the recognised ones AND warn (exit 0)
cat > "$TMP/typo.json" <<'JSON'
{"customer_name": "Beta Corp.", "non_existent_field": "ignored"}
JSON
set +e
warn=$("$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/typo.json" -o "$TMP/typo.pdf" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && ok "typo'd field: exit 0 (fills known, skips unknown)" \
    || nok "typo'd field exit" "got $rc"
echo "$warn" | grep -q "did not match" \
    && ok "typo'd field: warning surfaces in stderr" \
    || nok "typo'd field warning" "no warn in stderr"

# --flatten actually drops /AcroForm from the saved file
"$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/data.json" -o "$TMP/flat.pdf" --flatten >/dev/null 2>&1
has_form=$("$PY" -c "
from pypdf import PdfReader
r = PdfReader('$TMP/flat.pdf')
print('yes' if '/AcroForm' in r.trailer['/Root'] else 'no')
")
[ "$has_form" = "no" ] \
    && ok "--flatten removes /AcroForm from saved file" \
    || nok "--flatten dictionary removal" "still has /AcroForm"

# XFA exit code is reachable from --check (exit 11 reserved). We can't
# easily build an XFA fixture, so smoke-test the no-form code path
# instead — confirms the new code (12) replaced the old (3).
set +e
"$PY" pdf_fill_form.py --check "$TMP/a.pdf" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 12 ] \
    && ok "--check returns 12 on non-form (was 3 before exit-code refactor)" \
    || nok "--check no-form exit" "expected 12, got $rc"

# Boolean coercion: int 1 should map to /Yes for a checkbox field
cat > "$TMP/intbool.json" <<'JSON'
{"agree_terms": 1}
JSON
"$PY" pdf_fill_form.py "$TMP/form.pdf" "$TMP/intbool.json" -o "$TMP/intbool.pdf" >/dev/null 2>&1
agree=$("$PY" -c "
from pypdf import PdfReader
print(str(PdfReader('$TMP/intbool.pdf').get_fields()['agree_terms'].get('/V')))
")
[ "$agree" = "/Yes" ] \
    && ok "checkbox: int 1 → /Yes" \
    || nok "checkbox int coercion" "got '$agree'"

# --- mermaid (only if mmdc available) -------------------------------------
if [ -x "node_modules/.bin/mmdc" ]; then
    echo "md2pdf with mermaid:"
    cat > "$TMP/with_mermaid.md" <<'MD'
# Test

```mermaid
graph LR
    A[Start] --> B[End]
```
MD
    "$PY" md2pdf.py "$TMP/with_mermaid.md" "$TMP/with_mermaid.pdf" >/dev/null 2>&1
    [ -d "$TMP/with_mermaid_assets" ] && [ "$(ls "$TMP/with_mermaid_assets"/*.png 2>/dev/null | wc -l)" -gt 0 ] \
        && ok "mermaid block → PNG asset rendered" \
        || nok "mermaid → PNG" "no png in assets dir"

    # Bundled mermaid-config.json must exist and be valid JSON — the
    # default-config path is opted into automatically by md2pdf, so a
    # broken file here would silently degrade every Cyrillic diagram.
    [ -s mermaid-config.json ] && "$PY" -c "import json; json.load(open('mermaid-config.json'))" \
        && ok "bundled mermaid-config.json exists and parses" \
        || nok "bundled mermaid-config" "missing or invalid JSON"

    # --mermaid-config with a non-existent path: warn + degrade (not strict)
    set +e
    err=$("$PY" md2pdf.py "$TMP/with_mermaid.md" "$TMP/cfg_warn.pdf" \
              --mermaid-config "$TMP/does_not_exist.json" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && echo "$err" | grep -q "does not exist" \
        && ok "missing --mermaid-config → warn + degrade" \
        || nok "missing config handling" "exit $rc / msg: $err"

    # Cache key honours config: switching config (or its content) must
    # produce a NEW digest, so a stale PNG can never sneak through.
    # The assets dir is named after OUTPUT stem, so the two runs land
    # in DIFFERENT dirs (wm_default_assets vs wm_alt_assets) and we
    # compare the digests in the filenames.
    cat > "$TMP/alt_cfg.json" <<'JSON'
{"theme": "dark", "fontFamily": "monospace"}
JSON
    "$PY" md2pdf.py "$TMP/with_mermaid.md" "$TMP/wm_default.pdf" >/dev/null 2>&1
    digest_default=$(ls "$TMP/wm_default_assets"/*.png | head -1 | xargs basename)
    "$PY" md2pdf.py "$TMP/with_mermaid.md" "$TMP/wm_alt.pdf" \
          --mermaid-config "$TMP/alt_cfg.json" >/dev/null 2>&1
    digest_alt=$(ls "$TMP/wm_alt_assets"/*.png | head -1 | xargs basename)
    [ "$digest_default" != "$digest_alt" ] \
        && ok "config change invalidates PNG cache (digest differs)" \
        || nok "cache invalidation" "same digest: $digest_default"
fi

# --- cross-1: preview.py — pdf path (no soffice required) ----------------
echo "preview (pdf path):"
"$PY" preview.py "$TMP/out.pdf" "$TMP/preview.jpg" --dpi 80 >/dev/null 2>&1 \
    && [ -s "$TMP/preview.jpg" ] \
    && file "$TMP/preview.jpg" | grep -q "JPEG image" \
    && ok "pdf → preview.jpg (PNG-grid via pdftoppm)" \
    || nok "preview.py pdf" "missing or wrong format"

set +e
"$PY" preview.py /nope.pdf "$TMP/_missing.jpg" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && ok "preview.py: missing input exits 1" \
    || nok "preview.py missing" "exit $rc"

set +e
out=$("$PY" preview.py "$TMP/out.pdf" "$TMP/_x.jpg" --json-errors --dpi -1 2>&1 >/dev/null)
rc=$?
set -e
# Negative DPI must be caught BEFORE pdftoppm so we get a structured
# JSON envelope, not a Python traceback. Regression for VDD HIGH-2.
[ "$rc" -eq 2 ] \
    && echo "$out" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='InvalidArgument' and j['details']['flag']=='dpi', j" 2>/dev/null \
    && ok "preview.py: --dpi -1 → InvalidArgument JSON (no traceback)" \
    || nok "preview.py bad dpi" "exit=$rc msg=$out"

set +e
out=$("$PY" preview.py "$TMP/out.pdf" "$TMP/_y.jpg" --json-errors --cols 0 2>&1 >/dev/null)
rc=$?
set -e
# Same regression for cols=0 — would otherwise be ZeroDivisionError.
[ "$rc" -eq 2 ] \
    && echo "$out" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='InvalidArgument' and j['details']['flag']=='cols', j" 2>/dev/null \
    && ok "preview.py: --cols 0 → InvalidArgument JSON (no ZeroDivisionError)" \
    || nok "preview.py cols=0" "exit=$rc msg=$out"

# --- cross-5: --json-errors envelope (pdf) -------------------------------
echo "cross-5 unified errors:"
set +e
err=$("$PY" pdf_merge.py "$TMP/_out.pdf" /nope1.pdf /nope2.pdf --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==1 and j['type']=='FileNotFound' and len(j['details']['missing'])==2, j" 2>/dev/null \
    && ok "pdf_merge --json-errors envelope (lists missing inputs)" \
    || nok "pdf_merge --json-errors" "exit=$rc msg=$err"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
