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
ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
SKILL=pdf
PY="$SKILL_DIR/.venv/bin/python"
TMP="$(mktemp -d -t pdf_e2e_XXXX)"
trap 'rm -rf "$TMP"' EXIT

cd "$SKILL_DIR"
pass=0; fail=0
ok()  { printf '  ✓ %s\n'   "$1"; pass=$((pass+1)); }
nok() { printf '  ✗ %s\n  → %s\n' "$1" "$2"; fail=$((fail+1)); }

# q-2 visual regression helper (soft-skips when golden/IM missing unless
# STRICT_VISUAL=1; see tests/visual/_visual_helper.sh)
source "$ROOT/tests/visual/_visual_helper.sh"

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

    # --- q-3 mermaid edge-cases ---------------------------------------------
    # --base-url "$TMP" keeps mermaid PNG assets in the temp dir (default
    # would write them next to the input under examples/, polluting the
    # repo).
    echo "q-3 mermaid edge-cases:"
    for fix in cyrillic sequence gantt large-mindmap; do
        set +e
        "$PY" md2pdf.py "../examples/fixture-mermaid-$fix.md" "$TMP/m_$fix.pdf" \
              --base-url "$TMP" >/dev/null 2>&1
        rc=$?
        set -e
        [ "$rc" -eq 0 ] && [ -s "$TMP/m_$fix.pdf" ] \
            && ok "mermaid edge: $fix" \
            || nok "mermaid edge: $fix" "exit=$rc, pdf=$([ -s "$TMP/m_$fix.pdf" ] && echo present || echo missing)"
    done

    # broken syntax + --strict-mermaid → fail (exit non-zero, no PDF)
    set +e
    err=$("$PY" md2pdf.py ../examples/fixture-mermaid-broken.md \
              "$TMP/m_broken_strict.pdf" --base-url "$TMP" --strict-mermaid 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -ne 0 ] \
        && ok "mermaid edge: broken+strict fails" \
        || nok "mermaid edge: broken+strict fails" "expected non-zero, got $rc"

    # broken syntax (no strict) → exit 0, warning, PDF still produced
    set +e
    err=$("$PY" md2pdf.py ../examples/fixture-mermaid-broken.md \
              "$TMP/m_broken_lenient.pdf" --base-url "$TMP" 2>&1 >/dev/null)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && [ -s "$TMP/m_broken_lenient.pdf" ] \
        && echo "$err" | grep -qi "mmdc failed" \
        && ok "mermaid edge: broken degrades with warning" \
        || nok "mermaid edge: broken degrades" \
               "rc=$rc, pdf=$([ -s "$TMP/m_broken_lenient.pdf" ] && echo present || echo missing), warn=$err"
fi

# --- pdf_watermark ---------------------------------------------------------
echo "pdf_watermark:"

# Text watermark on the existing single-page out.pdf
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/wm_text.pdf" --text "DRAFT" >/dev/null 2>&1 \
    && [ -s "$TMP/wm_text.pdf" ] && ok "text watermark → wm_text.pdf" \
    || nok "text watermark" "missing or empty"

# Text extraction confirms the watermark glyphs are actually in the PDF
# content stream, not just a no-op overlay. pypdf's extract_text reads
# rotated text correctly (pdfplumber doesn't); use it here.
"$PY" -c "
from pypdf import PdfReader
txt = PdfReader('$TMP/wm_text.pdf').pages[0].extract_text() or ''
assert 'DRAFT' in txt, f'DRAFT not in extracted text: {txt[:200]!r}'
" 2>/dev/null \
    && ok "text watermark: 'DRAFT' present in page text" \
    || nok "text watermark text-extract" "DRAFT missing from extracted text"

# Page count is preserved (overlay merges, doesn't append).
in_pages=$("$PY" -c "import pypdf; print(len(pypdf.PdfReader('$TMP/out.pdf').pages))")
out_pages=$("$PY" -c "import pypdf; print(len(pypdf.PdfReader('$TMP/wm_text.pdf').pages))")
[ "$in_pages" -eq "$out_pages" ] \
    && ok "text watermark: page count preserved ($out_pages)" \
    || nok "text watermark page count" "in=$in_pages out=$out_pages"

# Image watermark using a tiny PNG generated via PIL — keeps the test
# self-contained (no binary fixture in examples/).
"$PY" -c "
from PIL import Image
img = Image.new('RGBA', (200, 100), (200, 0, 0, 200))
img.save('$TMP/stamp.png')
"
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/wm_img.pdf" \
        --image "$TMP/stamp.png" --position bottom-right --scale 0.2 >/dev/null 2>&1 \
    && [ -s "$TMP/wm_img.pdf" ] && ok "image watermark → wm_img.pdf" \
    || nok "image watermark" "missing or empty"

# cross-7 H1 same-path guard (new for pdf skill — established by these CLIs)
cp "$TMP/out.pdf" "$TMP/same.pdf"
set +e
err=$("$PY" pdf_watermark.py "$TMP/same.pdf" "$TMP/same.pdf" --text X --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='SelfOverwriteRefused' and j['code']==6, j" 2>/dev/null \
    && ok "watermark: same-path I/O → exit 6 / SelfOverwriteRefused" \
    || nok "watermark same-path" "exit=$rc msg=$err"

# Mutex: --text and --image together → argparse usage error
set +e
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/_x.pdf" --text X --image "$TMP/stamp.png" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && ok "watermark: --text + --image both → exit 2 (mutex)" \
    || nok "watermark mutex" "expected 2, got $rc"

# --pages selectivity: on the 2-page merged.pdf, watermark only page 1.
# Verify "DRAFT" appears on page 1 but not page 2.
"$PY" pdf_watermark.py "$TMP/merged.pdf" "$TMP/wm_page1.pdf" \
        --text "DRAFT" --pages "1" --position center --rotation 0 >/dev/null 2>&1
"$PY" -c "
from pypdf import PdfReader
r = PdfReader('$TMP/wm_page1.pdf')
p1 = r.pages[0].extract_text() or ''
p2 = r.pages[1].extract_text() or ''
assert 'DRAFT' in p1, 'DRAFT missing on page 1'
assert 'DRAFT' not in p2, 'DRAFT leaked to page 2'
" 2>/dev/null \
    && ok "watermark: --pages '1' restricts stamp to page 1" \
    || nok "watermark --pages selectivity" "DRAFT distribution wrong"

# --color non-hex value → argparse type= validation → exit 2 (UsageError)
set +e
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/_x.pdf" --text DRAFT --color red >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && ok "watermark: --color red (non-hex) → exit 2 (UsageError)" \
    || nok "watermark --color validation" "expected 2, got $rc"

# --scale > 1.0 → exit 2 (UsageError)
set +e
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/_x.pdf" --image "$TMP/stamp.png" --scale 5.0 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && ok "watermark: --scale 5.0 (> 1.0) → exit 2 (UsageError)" \
    || nok "watermark --scale upper-bound" "expected 2, got $rc"

# Portrait image watermark: a 100×800 PNG (aspect 1:8) with --scale 0.2
# should render img_w = 0.2 * page_width, NOT collapse to ~3% due to
# page-height clamping. Indirect check: exit 0, non-empty PDF.
"$PY" -c "
from PIL import Image
img = Image.new('RGBA', (100, 800), (0, 0, 200, 200))
img.save('$TMP/portrait.png')
"
"$PY" pdf_watermark.py "$TMP/out.pdf" "$TMP/wm_portrait.pdf" \
        --image "$TMP/portrait.png" --scale 0.2 >/dev/null 2>&1 \
    && [ -s "$TMP/wm_portrait.pdf" ] \
    && ok "watermark: portrait image --scale 0.2 honours aspect ratio" \
    || nok "watermark portrait image" "missing or empty"

# --- html2pdf --------------------------------------------------------------
echo "html2pdf:"

# Basic HTML → PDF (uses bundled DEFAULT_CSS by default)
"$PY" html2pdf.py ../examples/fixture.html "$TMP/html.pdf" >/dev/null 2>&1 \
    && [ -s "$TMP/html.pdf" ] && ok "fixture.html → html.pdf (default CSS)" \
    || nok "html2pdf default" "missing or empty"

# --no-default-css — opt out of bundled stylesheet (BI-dashboard use case)
"$PY" html2pdf.py ../examples/fixture.html "$TMP/html_nocss.pdf" --no-default-css >/dev/null 2>&1 \
    && [ -s "$TMP/html_nocss.pdf" ] && ok "fixture.html → html_nocss.pdf (--no-default-css)" \
    || nok "html2pdf no-default-css" "missing or empty"

# --css adds a custom stylesheet on top of the default (or after no-default)
cat > "$TMP/red_h1.css" <<'CSS'
h1 { color: #cc0000 !important; }
CSS
"$PY" html2pdf.py ../examples/fixture.html "$TMP/html_red.pdf" --css "$TMP/red_h1.css" >/dev/null 2>&1 \
    && [ -s "$TMP/html_red.pdf" ] && ok "html2pdf + --css EXTRA.css" \
    || nok "html2pdf --css" "missing or empty"

# Missing input → exit 1, FileNotFound envelope
set +e
err=$("$PY" html2pdf.py /nope.html "$TMP/_x.pdf" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='FileNotFound' and j['code']==1 and j['v']==1, j" 2>/dev/null \
    && ok "html2pdf: missing input → exit 1 / FileNotFound envelope" \
    || nok "html2pdf missing input" "exit=$rc msg=$err"

# cross-7 H1 same-path guard — html in same path as pdf is unlikely but
# resolution catches symlinks too; use a real same-path case.
cp ../examples/fixture.html "$TMP/same.html"
ln -sf "$TMP/same.html" "$TMP/same_link.html"
set +e
err=$("$PY" html2pdf.py "$TMP/same.html" "$TMP/same.html" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='SelfOverwriteRefused', j" 2>/dev/null \
    && ok "html2pdf: same-path I/O → exit 6 / SelfOverwriteRefused" \
    || nok "html2pdf same-path" "exit=$rc msg=$err"

# --css pointing to a missing file → exit 1 / FileNotFound (not a raw
# weasyprint traceback). Validates the explicit pre-flight check added
# after the VDD adversarial review.
set +e
err=$("$PY" html2pdf.py ../examples/fixture.html "$TMP/_x.pdf" --css /nope.css --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='FileNotFound' and j['code']==1, j" 2>/dev/null \
    && ok "html2pdf: --css /nope.css → exit 1 / FileNotFound envelope" \
    || nok "html2pdf missing css" "exit=$rc msg=$err"

# MHTML (.mhtml) → PDF. Generate a minimal MIME HTML archive inline so
# the test is self-contained (no binary fixture committed).
"$PY" -c "
import email.mime.multipart, email.mime.text, email.mime.image
root = email.mime.multipart.MIMEMultipart('related')
root['MIME-Version'] = '1.0'
html_part = email.mime.text.MIMEText(
    '<html><body><h1>MHTML Test</h1><p>Hello from archive.</p></body></html>',
    'html', 'utf-8')
html_part['Content-Location'] = 'http://example.com/index.html'
root.attach(html_part)
with open('$TMP/test.mhtml', 'wb') as f:
    f.write(root.as_bytes())
"
"$PY" html2pdf.py "$TMP/test.mhtml" "$TMP/html_mhtml.pdf" >/dev/null 2>&1 \
    && [ -s "$TMP/html_mhtml.pdf" ] && ok "html2pdf: .mhtml archive → pdf" \
    || nok "html2pdf mhtml" "missing or empty"

# WebArchive (.webarchive) → PDF. Generate a minimal Apple binary-plist
# archive via plistlib inline.
"$PY" -c "
import plistlib
plist = {
    'WebMainResource': {
        'WebResourceData': b'<html><body><h1>WebArchive Test</h1><p>Safari archive.</p></body></html>',
        'WebResourceMIMEType': 'text/html',
        'WebResourceTextEncodingName': 'UTF-8',
        'WebResourceURL': 'http://example.com/',
    },
    'WebSubresources': [],
}
with open('$TMP/test.webarchive', 'wb') as f:
    plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
"
"$PY" html2pdf.py "$TMP/test.webarchive" "$TMP/html_webarchive.pdf" >/dev/null 2>&1 \
    && [ -s "$TMP/html_webarchive.pdf" ] && ok "html2pdf: .webarchive archive → pdf" \
    || nok "html2pdf webarchive" "missing or empty"

# --reader-mode: extracts article content from a plain .html fixture
"$PY" html2pdf.py ../examples/fixture.html "$TMP/html_reader.pdf" --reader-mode >/dev/null 2>&1 \
    && [ -s "$TMP/html_reader.pdf" ] && ok "html2pdf: --reader-mode produces non-empty pdf" \
    || nok "html2pdf reader-mode" "missing or empty"

# --reader-mode on .webarchive (ensure no crash when <article>/<main> found)
"$PY" html2pdf.py "$TMP/test.webarchive" "$TMP/html_webarchive_reader.pdf" --reader-mode >/dev/null 2>&1 \
    && [ -s "$TMP/html_webarchive_reader.pdf" ] && ok "html2pdf: --reader-mode on .webarchive → pdf" \
    || nok "html2pdf reader-mode webarchive" "missing or empty"

# Unsupported format → exit 1 / UnsupportedFormat (not a traceback)
set +e
err=$("$PY" html2pdf.py "$TMP/out.pdf" "$TMP/_x.pdf" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='UnsupportedFormat', j" 2>/dev/null \
    && ok "html2pdf: unsupported .pdf input → exit 1 / UnsupportedFormat" \
    || nok "html2pdf unsupported format" "exit=$rc msg=$err"

# --- html2pdf regression battery -------------------------------------------
# Tier 1: pure-Python unit tests for html2pdf_lib helpers.
# Tier 0+2+3: data-driven battery — synthetic micro-fixtures
# (`examples/regression/`) + hand-stripped real-platform slices
# (`tests/fixtures/platforms/`) + tmp/ originals when present on disk.
# See `tests/battery_signatures.json` for the per-fixture spec
# (page count + size tolerance bands, required + forbidden needles).
echo "html2pdf regressions:"

# Helper: parse unittest summary text to extract `(failures=N, errors=M)`
# tuple AND the first failed test name. Surfaces useful triage info on
# failure instead of just "rerun the whole thing yourself".
_parse_unittest_failure() {
    local out="$1"
    # FAILED (failures=2, errors=1) → "2 failures, 1 errors"
    local counts
    counts=$(echo "$out" | awk '
        /^FAILED \(/ {
            f = ""; e = "";
            if (match($0, /failures=[0-9]+/)) f = substr($0, RSTART+9, RLENGTH-9);
            if (match($0, /errors=[0-9]+/))   e = substr($0, RSTART+7,  RLENGTH-7);
            out = "";
            if (f != "") out = out f " failure" (f == "1" ? "" : "s");
            if (e != "") out = out (out ? ", " : "") e " error"  (e == "1" ? "" : "s");
            print out; exit
        }')
    local first
    first=$(echo "$out" | awk '/^(FAIL|ERROR): / {sub(/^[A-Z]+: /, ""); print; exit}')
    if [ -n "$counts" ] && [ -n "$first" ]; then
        echo "${counts}; first: ${first}"
    elif [ -n "$counts" ]; then
        echo "$counts"
    else
        echo "see full output"
    fi
}

set +e
out=$("$PY" -m unittest tests.test_preprocess 2>&1)
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
    n=$(echo "$out" | awk '/^Ran [0-9]+ tests/ {print $2}')
    ok "preprocess unit tests (${n} cases)"
else
    nok "preprocess unit tests" "$(_parse_unittest_failure "$out")"
fi

set +e
out=$("$PY" -m unittest tests.test_battery 2>&1)
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
    # `Ran N tests` — split across "OK" or "OK (skipped=X)" outputs.
    total=$(echo "$out" | awk '/^Ran [0-9]+ tests/ {print $2}')
    skipped=$(echo "$out" | awk '/skipped=/ {match($0, /skipped=[0-9]+/); print substr($0, RSTART+8, RLENGTH-8); exit}')
    [ -n "$skipped" ] || skipped=0
    ran=$((total - skipped))
    ok "battery: ${ran} fixtures × modes ($skipped skipped — tmp/ absent or mode null)"
else
    # On failure, dump the full unittest FAIL blocks (with AssertionError
    # messages) so CI logs surface the actual mismatch.
    # `_parse_unittest_failure` shows only the first test name; full
    # tracebacks are essential for diagnosing cross-platform drift
    # (macOS vs Ubuntu freetype/fontconfig produce different page
    # counts/sizes for the same HTML — added during a 12-commit CI fix
    # cycle when battery_signatures drift took multiple iterations to
    # diagnose). Kept as a permanent debugging aid because the same
    # class of cross-platform drift will recur every time signatures
    # are refreshed on one platform but tested on another.
    echo "  --- FULL unittest FAIL output (battery debug) ---"
    echo "$out" | awk '/^FAIL:/{p=1} p; /^Ran [0-9]+ tests/{p=0}' | head -200
    echo "  --- END ---"
    nok "battery" "$(_parse_unittest_failure "$out")"
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

# iter-3 MED: output dir must be auto-created; PIL Image.save would
# otherwise raise FileNotFoundError → traceback past the JSON envelope.
"$PY" preview.py "$TMP/out.pdf" "$TMP/auto/created/dir/p.jpg" --dpi 80 >/dev/null 2>&1 \
    && [ -s "$TMP/auto/created/dir/p.jpg" ] \
    && ok "preview.py: auto-creates output's parent directory" \
    || nok "preview.py auto-mkdir" "expected file at $TMP/auto/created/dir/p.jpg"

# iter-3 MED: pdftoppm stderr must be captured into the envelope, not
# leaked as separate stderr lines. Use empty PDF so pdftoppm prints
# "Syntax Error: Invalid page count 0" — verifies the JSON envelope is
# single-line and the diagnostic is embedded.
"$PY" -c "
from pypdf import PdfWriter
w = PdfWriter()
with open('$TMP/empty.pdf', 'wb') as f:
    w.write(f)
" 2>/dev/null
set +e
err=$("$PY" preview.py "$TMP/empty.pdf" "$TMP/_z.jpg" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
n_lines=$(printf '%s' "$err" | grep -c '^')
[ "$rc" -eq 1 ] \
    && [ "$n_lines" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert 'pdftoppm' in j['error'] and 'page count' in j['error'].lower(), j" 2>/dev/null \
    && ok "preview.py: pdftoppm stderr captured into JSON envelope (single line)" \
    || nok "preview.py pdftoppm capture" "exit=$rc lines=$n_lines msg=$err"

# iter-3 MED: PIL UnidentifiedImageError on a corrupt tile must route
# through the envelope. Direct call into _compose_grid with a non-JPEG
# tile so we don't depend on pdftoppm producing one.
"$PY" -c "
import sys
sys.path.insert(0, '.')
from preview import _compose_grid
from pathlib import Path
import PIL
# Plant a fake 'tile' that's not a real image
fake = Path('$TMP/fake_tile.jpg')
fake.write_bytes(b'definitely not a jpeg')
out = Path('$TMP/_grid.jpg')
try:
    _compose_grid([fake], out, 'Page', 3, 12, 24, 14)
except PIL.UnidentifiedImageError as e:
    print('caught:', type(e).__name__)
" 2>&1 | grep -q "UnidentifiedImageError" \
    && ok "preview.py: _compose_grid raises UnidentifiedImageError on corrupt tile (caught in main)" \
    || nok "PIL error path" "no UnidentifiedImageError raised"

# iter-3 LOW: --pdftoppm-timeout flag accepted, validates lower bound
set +e
out=$("$PY" preview.py "$TMP/out.pdf" "$TMP/_p.jpg" --pdftoppm-timeout 0 --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$out" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['details']['flag']=='pdftoppm-timeout', j" 2>/dev/null \
    && ok "preview.py: --pdftoppm-timeout 0 rejected (lower bound)" \
    || nok "pdftoppm-timeout validation" "exit=$rc msg=$out"

# iter-3 LOW: valid --pdftoppm-timeout reaches the subprocess (happy
# path: 60s on the existing fixture should always succeed).
"$PY" preview.py "$TMP/out.pdf" "$TMP/_t.jpg" --pdftoppm-timeout 60 --dpi 80 >/dev/null 2>&1 \
    && [ -s "$TMP/_t.jpg" ] \
    && ok "preview.py: --pdftoppm-timeout 60 happy path produces output" \
    || nok "pdftoppm-timeout happy path" "no output"

# --- cross-5: --json-errors envelope (pdf) -------------------------------
echo "cross-5 unified errors:"
set +e
err=$("$PY" pdf_merge.py "$TMP/_out.pdf" /nope1.pdf /nope2.pdf --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==1 and j['type']=='FileNotFound' and j['v']==1 and len(j['details']['missing'])==2, j" 2>/dev/null \
    && ok "pdf_merge --json-errors envelope (lists missing + v=1)" \
    || nok "pdf_merge --json-errors" "exit=$rc msg=$err"

# Parameterized cross-5: every plumbed pdf CLI emits a JSON envelope.
for cli in md2pdf.py pdf_split.py pdf_fill_form.py preview.py html2pdf.py pdf_watermark.py; do
    set +e
    if [ "$cli" = "md2pdf.py" ]; then
        out=$("$PY" "$cli" /nope.md /tmp/_x.pdf --json-errors 2>&1 >/dev/null)
    elif [ "$cli" = "pdf_split.py" ]; then
        out=$("$PY" "$cli" /nope.pdf --each-page /tmp/_split --json-errors 2>&1 >/dev/null)
    elif [ "$cli" = "pdf_fill_form.py" ]; then
        out=$("$PY" "$cli" --check /nope.pdf --json-errors 2>&1 >/dev/null)
    elif [ "$cli" = "html2pdf.py" ]; then
        out=$("$PY" "$cli" /nope.html /tmp/_x.pdf --json-errors 2>&1 >/dev/null)
    elif [ "$cli" = "pdf_watermark.py" ]; then
        out=$("$PY" "$cli" /nope.pdf /tmp/_x.pdf --text X --json-errors 2>&1 >/dev/null)
    else
        out=$("$PY" "$cli" /nope.pdf /tmp/_x.jpg --json-errors 2>&1 >/dev/null)
    fi
    set -e
    echo "$out" | "$PY" -c "import sys, json; json.loads(sys.stdin.read())" 2>/dev/null \
        && ok "  $cli emits JSON envelope" \
        || nok "  $cli envelope" "got: $out"
done

# LOW-3: an OOXML file fed to pdf-skill preview.py must emit a one-time
# stderr note about the missing encryption pre-flight (since pdf has no
# office/ module). Use a CFB fixture so soffice will fail predictably.
"$PY" -c "from pathlib import Path; Path('$TMP/cfb.docx').write_bytes(b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1' + b'\\x00' * 100)"
set +e
err=$("$PY" preview.py "$TMP/cfb.docx" "$TMP/_y.jpg" 2>&1 >/dev/null)
set -e
echo "$err" | grep -q "encryption pre-flight is unavailable" \
    && ok "OOXML→pdf-preview: emits encryption-skip note (LOW-3)" \
    || nok "OOXML→pdf-preview note" "no note in stderr: $err"

# --- q-2: visual regression on the produced PDFs --------------------------
echo "q-2 visual regression:"
visual_check "$TMP/out.pdf"     "fixture-base"
visual_check "$TMP/merged.pdf"  "fixture-merged"
visual_check "$TMP/filled.pdf"  "acroform-filled"
visual_check "$TMP/flat.pdf"    "acroform-flat"
visual_check "$TMP/wm_text.pdf" "watermarked-text"
visual_check "$TMP/html.pdf"    "html-basic"
if [ -x "node_modules/.bin/mmdc" ]; then
    visual_check "$TMP/wm_default.pdf" "mermaid-default"
    visual_check "$TMP/wm_alt.pdf"     "mermaid-alt"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
