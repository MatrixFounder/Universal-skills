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

# --- html2docx preprocess unit tests (q-7) --------------------------------
# Synthetic-HTML unit cases for every preprocessing stage in
# `_html2docx_preprocess.js`. Run BEFORE the html2docx E2E so a stage-
# level regression fails fast instead of getting buried under an
# end-to-end document mismatch. Output parsing is anchored on the
# node:test summary lines (`pass N` / `fail N`); the leading info
# glyph isn't part of the match.
echo "html2docx preprocess unit tests:"
pp_rc=0
pp_out=$(node tests/test_html2docx_preprocess.test.js 2>&1) || pp_rc=$?
pp_pass=$(echo "$pp_out" | grep -E '(^|[[:space:]])pass [0-9]+$' | grep -oE '[0-9]+' | tail -1)
pp_fail=$(echo "$pp_out" | grep -E '(^|[[:space:]])fail [0-9]+$' | grep -oE '[0-9]+' | tail -1)
pp_pass=${pp_pass:-0}
pp_fail=${pp_fail:-0}
if [ "$pp_rc" -eq 0 ] && [ "$pp_fail" = "0" ] && [ "$pp_pass" -gt 0 ]; then
    ok "preprocess unit-tests: $pp_pass passed"
else
    nok "preprocess unit-tests" "rc=$pp_rc pass=$pp_pass fail=$pp_fail"
    echo "$pp_out" | tail -30
fi

# --- html2docx -------------------------------------------------------------
echo "html2docx:"
node html2docx.js ../examples/fixture-simple.html "$TMP/html_out.docx" >/dev/null 2>&1 \
    && [ -s "$TMP/html_out.docx" ] && ok "fixture.html → html_out.docx" \
    || nok "fixture.html → html_out.docx" "missing or empty"

"$PY" -m office.validate "$TMP/html_out.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts html2docx output" \
    || nok "office.validate (html2docx)" "rejected the produced .docx"

# Round-trip via docx2md to confirm content survived the cheerio→docx walk.
node docx2md.js "$TMP/html_out.docx" "$TMP/html_back.md" >/dev/null 2>&1
grep -q "Quarterly report" "$TMP/html_back.md" \
    && ok "html→docx→md preserves heading text" \
    || nok "html heading round-trip" "lost in cheerio walk"
grep -q "915,000" "$TMP/html_back.md" \
    && ok "html→docx→md preserves table cell" \
    || nok "html table cell round-trip" "lost in cheerio walk"

# cross-7 H1: same-path guard. Input HTML and output .docx have different
# extensions in the typical case, but the guard must still trip when the
# user points both args at the same path (e.g. via a typo).
cp ../examples/fixture-simple.html "$TMP/same.html"
set +e
err=$(node html2docx.js "$TMP/same.html" "$TMP/same.html" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['code']==6 and j['type']=='SelfOverwriteRefused', j" 2>/dev/null \
    && ok "same-path guard: exit 6 + SelfOverwriteRefused envelope" \
    || nok "same-path guard" "exit=$rc msg=$err"

# cross-5: --json-errors envelope on a missing-input failure (regression
# for any future change to the JS error helper).
set +e
err=$(node html2docx.js /nope.html "$TMP/_z.docx" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['v']==1 and j['code']==1 and j['type']=='FileNotFound', j" 2>/dev/null \
    && ok "html2docx --json-errors: v=1 + FileNotFound + code=1" \
    || nok "html2docx envelope" "exit=$rc msg=$err"

# VDD iter-3 unit-tests for the SVG render module — exercise helpers
# directly so a regression in trim / corrupt-PNG / sandbox-gate is caught
# even on a host without Chrome.
out=$(cd "$SKILL_DIR" && node --eval "
const r = require('./_html2docx_svg_render');
const { PNG } = require('pngjs');
const assert = require('assert');

// (1) PNG magic check.
const real = new PNG({ width: 4, height: 4 });
assert.strictEqual(r._isValidPng(PNG.sync.write(real)), true);
assert.strictEqual(r._isValidPng(Buffer.from([0xFF,0xD8,0xFF,0xE0])), false);
assert.strictEqual(r._isValidPng(Buffer.alloc(0)), false);

// (2) Trim crops all four sides — content in middle of 40×40, padding=2.
const dirty = new PNG({ width: 40, height: 40 });
for (let i = 0; i < dirty.data.length; i++) dirty.data[i] = 255;
for (let y = 12; y < 22; y++) for (let x = 15; x < 25; x++) {
    const idx = (y * 40 + x) * 4;
    dirty.data[idx] = dirty.data[idx+1] = dirty.data[idx+2] = 0;
    dirty.data[idx+3] = 255;
}
const trim1 = PNG.sync.read(r._trimPngWhitespace(PNG.sync.write(dirty), 2));
assert(trim1.width >= 12 && trim1.width <= 14, 'four-side trim width');
assert(trim1.height >= 12 && trim1.height <= 14, 'four-side trim height');

// (3) Top trim — content in BOTTOM half must collapse the top white region.
const bottomOnly = new PNG({ width: 30, height: 60 });
for (let i = 0; i < bottomOnly.data.length; i++) bottomOnly.data[i] = 255;
for (let y = 50; y < 58; y++) for (let x = 5; x < 25; x++) {
    const idx = (y * 30 + x) * 4;
    bottomOnly.data[idx] = bottomOnly.data[idx+1] = bottomOnly.data[idx+2] = 0;
    bottomOnly.data[idx+3] = 255;
}
const trim2 = PNG.sync.read(r._trimPngWhitespace(PNG.sync.write(bottomOnly), 0));
assert(trim2.height <= 12, 'top trim removes leading white, got h=' + trim2.height);

// (4) Corrupt input: helper passes through, magic check rejects.
const corrupt = Buffer.from([0xFF, 0xD8, 0xFF, 0xE0]);
assert.strictEqual(r._trimPngWhitespace(corrupt, 0), corrupt);
assert.strictEqual(r._isValidPng(corrupt), false);

// (5) Sandbox gate: opt-in env triggers disable, default leaves it on
// (skip the not-root assertion when actually running as root, e.g. CI Docker).
const wasOptIn = process.env.HTML2DOCX_ALLOW_NO_SANDBOX;
delete process.env.HTML2DOCX_ALLOW_NO_SANDBOX;
const isRoot = typeof process.getuid === 'function' && process.getuid() === 0;
if (!isRoot) assert.strictEqual(r._shouldDisableSandbox(), false);
process.env.HTML2DOCX_ALLOW_NO_SANDBOX = '1';
assert.strictEqual(r._shouldDisableSandbox(), true);
if (wasOptIn === undefined) delete process.env.HTML2DOCX_ALLOW_NO_SANDBOX;
else process.env.HTML2DOCX_ALLOW_NO_SANDBOX = wasOptIn;

console.log('OK');
" 2>&1)
echo "$out" | tail -1 | grep -q '^OK$' \
    && ok "svg-render helpers: 4-sided trim + isValidPng + sandbox gate" \
    || nok "svg-render helpers" "$out"

# SVG renderer tier detection: with HTML2DOCX_BROWSER set to a non-existent
# path, Tier 1 (Chrome) must be skipped and Tier 2 (resvg-js) must take
# over. Use a small inline-SVG fixture so the test runs fast and works on
# any host (no actual Chrome required).
#
# IMPORTANT: dimensions must be > _ICON_MAX_PX (64 px) on BOTH axes so
# `_isIconSvg` doesn't strip the SVG during preprocessing. A 60×40 SVG
# was treated as a UI icon and never reached the rasterizer, so the
# Tier-2 announce log ("resvg-js") was never emitted and this test
# silently regressed. (200×100 ≫ 64 → preprocessing keeps it.)
cat > "$TMP/svg.html" <<'HTML'
<!doctype html><html><body><svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><rect x="4" y="4" width="192" height="92" fill="#cce" stroke="#333"/><text x="100" y="56" text-anchor="middle" font-size="20">tier 2 fallback</text></svg></body></html>
HTML
out=$(HTML2DOCX_BROWSER=/no/such/browser-binary node html2docx.js \
        "$TMP/svg.html" "$TMP/svg_resvg.docx" 2>&1)
rc=$?
[ "$rc" -eq 0 ] && [ -s "$TMP/svg_resvg.docx" ] \
    && echo "$out" | grep -q "resvg-js" \
    && ok "Tier 2 (resvg-js) used when HTML2DOCX_BROWSER is unreachable" \
    || nok "tier-2 fallback" "exit=$rc out=$out"
"$PY" -m office.validate "$TMP/svg_resvg.docx" >/dev/null 2>&1 \
    && ok "Tier 2 output passes office.validate" \
    || nok "tier-2 validate" "rejected"

# VDD-iter-3 unit tests for _ensureViewBox and _svgDimensions: exercise the
# new code paths the cc24b55 backport added, since the Tier-2 fixture above
# is too small (60×40) to hit the > 200 expansion gate or the no-viewBox
# synthesis branch. Without these, "117 tests pass" would be uninformative.
out=$(cd "$SKILL_DIR" && node --eval "
const { _ensureViewBox, _svgDimensions } = require('./_html2docx_walker');
const cheerio = require('cheerio');
const assert = require('assert');

// (1) Self-closing SVG must stay self-closing AND get a viewBox synthesised.
//     Pre-fix: regex ate the '/' as part of attrs, output was
//     '<svg width=\"500\" height=\"500\"/ viewBox=\"...\">' — invalid XML.
const r1 = _ensureViewBox('<svg width=\"500\" height=\"500\"/>', 500, 500, true);
assert(r1.includes('viewBox=\"0 0 525.0 525.0\"'), 'viewBox synthesised: ' + r1);
assert(r1.endsWith('/>'), 'self-closing preserved: ' + r1);
assert(!/\/ /.test(r1), 'no stray / inside tag: ' + r1);

// (2) Existing-viewBox path must also keep self-closing form intact.
const r2 = _ensureViewBox(
    '<svg viewBox=\"0 0 800 600\" width=\"800\" height=\"600\"/>', 800, 600, true);
assert(r2.includes('viewBox=\"0 0 840.0 630.0\"'), '5%-expanded viewBox: ' + r2);
assert(r2.endsWith('/>'), 'self-closing preserved on Case 1: ' + r2);

// (3) Fallback dims (trustDims=false) must NOT synthesise from a
//     fictional 600×400 sentinel. Output must equal input.
const fallbackInput = '<svg xmlns=\"http://www.w3.org/2000/svg\"><circle r=\"5\"/></svg>';
const r3 = _ensureViewBox(fallbackInput, 600, 400, false);
assert.strictEqual(r3, fallbackInput, 'no synthesis on fallback: ' + r3);

// (4) Material-Symbols-style icon (40px rendered, viewBox 1024×1024) must
//     NOT get its viewBox expanded. Otherwise 5% extra user-units shrink
//     the icon visibly inside its 40×40 wrapper.
const iconIn = '<svg width=\"40\" height=\"40\" viewBox=\"0 0 1024 1024\"><path/></svg>';
const r4 = _ensureViewBox(iconIn, 40, 40, true);
assert.strictEqual(r4, iconIn, 'icon left untouched: ' + r4);

// (5) _svgDimensions sentinel returns {fallback:true} for shape-less SVG.
const \$ = cheerio.load('<svg></svg>', { xmlMode: true });
const dims = _svgDimensions(\$('svg'), null);
assert.strictEqual(dims.fallback, true, 'sentinel marked fallback');
assert.strictEqual(dims.w, 600, 'sentinel w preserved for backward-compat');

// (6) _svgDimensions with explicit width/height returns fallback:false.
const \$2 = cheerio.load('<svg width=\"800\" height=\"600\"></svg>', { xmlMode: true });
const dims2 = _svgDimensions(\$2('svg'), null);
assert.strictEqual(dims2.fallback, false, 'explicit dims not flagged fallback');

// (7) Drawio Confluence pattern: SVG without viewBox, parent has min-width/
//     min-height in inline style. Synthesised viewBox must equal parent dims
//     × 5% expansion, AND the result must parse cleanly as XML (no double
//     attrs, no broken tags).
const drawioIn =
    '<svg style=\"width:100%;height:100%;min-width:955px;min-height:720px\">' +
    '<g><rect width=\"50\" height=\"50\"/></g></svg>';
const r7 = _ensureViewBox(drawioIn, 955, 720, true);
assert(r7.includes('viewBox=\"0 0 1002.8 756.0\"'), 'drawio viewBox synthesised: ' + r7);
const \$7 = cheerio.load(r7, { xmlMode: true });
assert.strictEqual(\$7('svg').attr('viewBox'), '0 0 1002.8 756.0', 'parses as one attr');

console.log('OK');
" 2>&1)
echo "$out" | grep -q '^OK$' \
    && ok "_ensureViewBox: 7 unit tests (self-closing, fallback, icon, drawio)" \
    || nok "_ensureViewBox unit" "$out"

# VDD-iter-3 wrap regression: long unwrapped Cyrillic label inside a
# narrow drawio box must produce multiple <tspan> elements (one per
# wrapped line). Pre-fix: single <text> overflowed the box because
# extractLines only split on <br> / <div>; long single-span labels
# stayed as one line that escaped the shape.
out=$(cd "$SKILL_DIR" && node --eval "
const { _drawioForeignObjectsToText } = require('./_html2docx_walker');
const cheerio = require('cheerio');
const assert = require('assert');

// Single foreignObject, container width 120px, long unwrapped Cyrillic.
const svgIn = '<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 400 200\">' +
    '<foreignObject>' +
    '<div xmlns=\"http://www.w3.org/1999/xhtml\" style=\"display:flex; align-items: unsafe center; justify-content: unsafe center; width: 120px; height: 1px; padding-top: 80px; margin-left: 100px;\">' +
    '<div style=\"font-size: 12px;\">Принимает звонок (в интерфейсе ELMA365, либо снимает трубку)</div>' +
    '</div></foreignObject></svg>';
const out = _drawioForeignObjectsToText(cheerio, svgIn);
const tspans = (out.match(/<tspan /g) || []).length;
assert(tspans >= 2, 'expected ≥2 tspans for wrapped label, got ' + tspans + ': ' + out);
assert(/text-anchor=\"middle\"/.test(out), 'centred anchor preserved: ' + out);

// Container width 1px (drawio's unconstrained marker) must NOT wrap —
// label rendered as a single line at the declared anchor.
const svgUnconstrained = '<svg xmlns=\"http://www.w3.org/2000/svg\">' +
    '<foreignObject>' +
    '<div xmlns=\"http://www.w3.org/1999/xhtml\" style=\"display:flex; align-items: unsafe center; justify-content: unsafe flex-start; width: 1px; height: 1px; padding-top: 50px; margin-left: 30px;\">' +
    '<div style=\"font-size: 14px;\">Очень длинная строка которая не должна переноситься</div>' +
    '</div></foreignObject></svg>';
const out2 = _drawioForeignObjectsToText(cheerio, svgUnconstrained);
const tspans2 = (out2.match(/<tspan /g) || []).length;
assert.strictEqual(tspans2, 0, 'unconstrained label stays single-line, got ' + tspans2 + ': ' + out2);
assert(/text-anchor=\"start\"/.test(out2), 'flex-start anchor preserved');

console.log('OK');
" 2>&1)
echo "$out" | grep -q '^OK$' \
    && ok "_drawioForeignObjectsToText: word-wraps long Cyrillic labels at containerWidth" \
    || nok "wrap unit" "$out"

# VDD-iter-3 reader-mode integration test: vc.ru-style HTML where <main>
# wraps the entire site. Default mode picks <main> (chrome included).
# --reader-mode must pick .entry (article body only). Pre-fix additive
# reader-mode also picked <main> because it tried base candidates first.
# `printf 'fmt %.0s' $(seq 1 N)` repeats fmt N times. We avoid `yes | head`
# because under `set -o pipefail` that yields exit 141 (SIGPIPE) and aborts.
NAV=$(printf 'site nav text %.0s' $(seq 1 50))
ART=$(printf 'article body paragraph %.0s' $(seq 1 40))
FOOT=$(printf 'site footer %.0s' $(seq 1 30))
cat > "$TMP/vcru.html" <<HTML
<!doctype html><html><body>
<main>
  <nav>${NAV}— navigation that exceeds 500 chars.</nav>
  <div class="entry"><h1>Real article title</h1>
    <p>${ART}— article content the user wants.</p>
  </div>
  <footer>${FOOT}— copyright.</footer>
</main>
</body></html>
HTML

out_default=$(node html2docx.js "$TMP/vcru.html" "$TMP/vcru-default.docx" 2>&1)
out_reader=$(node html2docx.js "$TMP/vcru.html" "$TMP/vcru-reader.docx" --reader-mode 2>&1)

echo "$out_default" | grep -q 'via "main"' \
    && ok "default mode: picks <main> (preserves backward-compat)" \
    || nok "default mode root" "got: $out_default"

echo "$out_reader" | grep -q 'via "\.entry"' \
    && ok "--reader-mode: picks .entry (skips bare <main> chrome wrapper)" \
    || nok "reader mode root" "got: $out_reader"

# VDD-iter-3 reader-mode: Confluence diagram-only page (< 500 chars) must
# still pick #main-content. The 500-char filter applies only to fuzzy
# selectors; high-confidence Confluence IDs accept any length.
cat > "$TMP/conf-sparse.html" <<'HTML'
<!doctype html><html><body>
<div id="header">site chrome here</div>
<div id="main-content"><h1>Diagram</h1><p>Short.</p></div>
</body></html>
HTML
out_sparse=$(node html2docx.js "$TMP/conf-sparse.html" "$TMP/conf-sparse.docx" --reader-mode 2>&1)
echo "$out_sparse" | grep -q 'via "#main-content"' \
    && ok "--reader-mode: sparse Confluence page still picks #main-content" \
    || nok "reader mode sparse" "got: $out_sparse"

# VDD-iter-2 MED-1: nested <ol> inside <ul> must render as numbered, not
# inherit "bullets" reference. Round-trip via docx2md detects bullet
# regression because mammoth/turndown preserve list markers.
cat > "$TMP/nested.html" <<'HTML'
<html><body><ul><li>top<ol><li>nested-numbered-A</li><li>nested-numbered-B</li></ol></li></ul></body></html>
HTML
node html2docx.js "$TMP/nested.html" "$TMP/nested.docx" >/dev/null 2>&1
node docx2md.js "$TMP/nested.docx" "$TMP/nested.md" >/dev/null 2>&1
# After fix: nested items must appear with `1.` / `1)` / `2.` markers
# (turndown emits "1.  text"). Bug regression would emit "*  text".
grep -E "^\s*1\.\s+nested-numbered-A" "$TMP/nested.md" >/dev/null \
    && ok "MED-1: <ol> inside <ul> keeps numbering after round-trip" \
    || nok "MED-1: nested numbered list" "got: $(cat $TMP/nested.md)"

# VDD-iter-2 LOW-1: mailto: links survive as docx hyperlinks (not flat
# text). docx2md re-emits hyperlinks as `[label](url)` markdown.
cat > "$TMP/mailto.html" <<'HTML'
<html><body><p>Email <a href="mailto:foo@bar.com">support</a> please.</p></body></html>
HTML
node html2docx.js "$TMP/mailto.html" "$TMP/mailto.docx" >/dev/null 2>&1
node docx2md.js "$TMP/mailto.docx" "$TMP/mailto.md" >/dev/null 2>&1
grep -q "mailto:foo@bar.com" "$TMP/mailto.md" \
    && ok "LOW-1: mailto: link preserved through round-trip" \
    || nok "LOW-1: mailto link" "stripped to plain text: $(cat $TMP/mailto.md)"

# VDD-iter-2 MED-3: a query-string-suffixed src that doesn't exist on
# disk must yield "Local image not found" (existence check first), NOT
# "Unsupported image format" (extname mis-parse).
cat > "$TMP/queryimg.html" <<'HTML'
<html><body><img src="/no/such/file.png?version=42&v2"></body></html>
HTML
set +e
err=$(node html2docx.js "$TMP/queryimg.html" "$TMP/queryimg.docx" 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] \
    && echo "$err" | grep -q "Local image not found" \
    && ! echo "$err" | grep -q "Unsupported image format" \
    && ok "MED-3: missing image error names existence (not format)" \
    || nok "MED-3: error message" "$err"

# --- html2docx: webarchive + mhtml extractors (HIGH-1 coverage gap) -------
echo "html2docx archives:"

# Generate a minimal Safari .webarchive synthetically: bplist00 dict with
# WebMainResource{WebResourceData=<html>, MIMEType=text/html, URL=...}
# and one PNG sub-resource with a known URL → exercises addExtractedImage
# path-only key fallback.
"$PY" -c "
import plistlib, sys, base64
# Tiny 1x1 PNG (transparent) — minimum valid PNG.
PNG_1x1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
HTML = b'<!DOCTYPE html><html><head><title>WA fixture</title></head><body><h1>WebArchive heading marker</h1><p>cell-915,000 marker</p><img src=\"https://example.com/a.png\"></body></html>'
data = {
    'WebMainResource': {
        'WebResourceData': HTML,
        'WebResourceMIMEType': 'text/html',
        'WebResourceTextEncodingName': 'UTF-8',
        'WebResourceURL': 'https://example.com/page.html',
        'WebResourceFrameName': '',
    },
    'WebSubresources': [
        {
            'WebResourceData': PNG_1x1,
            'WebResourceMIMEType': 'image/png',
            'WebResourceURL': 'https://example.com/a.png',
        },
    ],
}
with open('$TMP/fx.webarchive', 'wb') as f:
    plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
"
node html2docx.js "$TMP/fx.webarchive" "$TMP/fx_wa.docx" >/dev/null 2>&1 \
    && [ -s "$TMP/fx_wa.docx" ] && ok "fx.webarchive → fx_wa.docx" \
    || nok ".webarchive → .docx" "missing or empty"
"$PY" -m office.validate "$TMP/fx_wa.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts .webarchive output" \
    || nok ".webarchive validate" "rejected"
node docx2md.js "$TMP/fx_wa.docx" "$TMP/fx_wa.md" >/dev/null 2>&1
grep -q "WebArchive heading marker" "$TMP/fx_wa.md" \
    && ok ".webarchive: heading round-trips through bplist parser" \
    || nok ".webarchive content" "lost in extraction: $(head -3 $TMP/fx_wa.md)"

# Generate a minimal Chrome .mhtml synthetically: multipart/related with
# one quoted-printable text/html part + one base64 image part. Tests:
# (a) MIME header parsing, (b) QP decode, (c) base64 decode, (d) image
# part extraction, (e) Content-Location lookup against extractedImages.
PNG_B64='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
{
    printf 'From: <Saved test>\r\n'
    printf 'Snapshot-Content-Location: https://example.com/p\r\n'
    printf 'Subject: MHTML fixture\r\n'
    printf 'MIME-Version: 1.0\r\n'
    printf 'Content-Type: multipart/related; type="text/html"; boundary="MHTML_BOUND_42"\r\n'
    printf '\r\n'
    printf '\r\n--MHTML_BOUND_42\r\n'
    printf 'Content-Type: text/html; charset=utf-8\r\n'
    printf 'Content-Transfer-Encoding: quoted-printable\r\n'
    printf 'Content-Location: https://example.com/p\r\n'
    printf '\r\n'
    # Quoted-printable body: encodes "—" as =E2=80=94 (utf-8 em-dash).
    printf '<html><body><h1>MHTML heading marker =E2=80=94 Q1</h1><table>'
    printf '<tr><th>Metric</th></tr><tr><td>915,000</td></tr></table>'
    printf '<img src="https://example.com/img.png"></body></html>\r\n'
    printf '\r\n--MHTML_BOUND_42\r\n'
    printf 'Content-Type: image/png\r\n'
    printf 'Content-Transfer-Encoding: base64\r\n'
    printf 'Content-Location: https://example.com/img.png\r\n'
    printf '\r\n'
    printf '%s\r\n' "$PNG_B64"
    printf '\r\n--MHTML_BOUND_42--\r\n'
} > "$TMP/fx.mhtml"

# (a) Conversion succeeds + image extraction reported.
out=$(node html2docx.js "$TMP/fx.mhtml" "$TMP/fx_mh.docx" 2>&1)
rc=$?
[ "$rc" -eq 0 ] && [ -s "$TMP/fx_mh.docx" ] && ok "fx.mhtml → fx_mh.docx" \
    || nok ".mhtml → .docx" "exit=$rc msg=$out"
echo "$out" | grep -q "extracted 1 image part" \
    && ok ".mhtml: image part extracted (base64 decoded)" \
    || nok ".mhtml image extraction" "expected 'extracted 1 image part': $out"
"$PY" -m office.validate "$TMP/fx_mh.docx" >/dev/null 2>&1 \
    && ok "office.validate accepts .mhtml output" \
    || nok ".mhtml validate" "rejected"
node docx2md.js "$TMP/fx_mh.docx" "$TMP/fx_mh.md" >/dev/null 2>&1
grep -q "MHTML heading marker" "$TMP/fx_mh.md" \
    && ok ".mhtml: QP-decoded heading round-trips (em-dash UTF-8)" \
    || nok ".mhtml QP decode" "got: $(head -3 $TMP/fx_mh.md)"
grep -q "915,000" "$TMP/fx_mh.md" \
    && ok ".mhtml: table cell round-trips through MIME parser" \
    || nok ".mhtml table" "lost: $(head -5 $TMP/fx_mh.md)"

# MED-2: tmpDirs registered for cleanup must be empty after the process
# exits (cleanup hook ran). Sample the temp directory of the OS — count
# our markers right before vs right after a fresh run.
TMPROOT="$(node -e 'process.stdout.write(require("os").tmpdir())')"
before=$(ls "$TMPROOT" 2>/dev/null | grep -c "html2docx-mhtml-" || true)
node html2docx.js "$TMP/fx.mhtml" "$TMP/_cleanup_check.docx" >/dev/null 2>&1
after=$(ls "$TMPROOT" 2>/dev/null | grep -c "html2docx-mhtml-" || true)
[ "$after" -le "$before" ] \
    && ok "MED-2: mhtml tmp dir cleaned up on process exit" \
    || nok "MED-2: tmp leak" "before=$before after=$after"

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

# --- docx-1b: docx_add_comment replies + library mode ---------------------
echo "docx-1b add_comment replies + library:"

# R1 reply happy-path (zip-mode): wrap an anchor, then reply to comment 0.
# Verify (a) two <w:comment>, (b) commentsExtended.xml has paraIdParent
# matching parent's paraId, (c) document.xml has 2 of each marker kind
# with reply's range nested inside parent's.
"$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/r_parent.docx" \
    --anchor-text "Quarterly" --comment "verify" --author "QA" >/dev/null 2>&1
"$PY" docx_add_comment.py "$TMP/r_parent.docx" "$TMP/r_reply.docx" \
    --parent 0 --comment "Acknowledged, fixing." --author "Dev" >/dev/null 2>&1
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/r_reply.docx') as z:
    cx = z.read('word/comments.xml').decode()
    ext = z.read('word/commentsExtended.xml').decode()
    doc = z.read('word/document.xml').decode()
assert len(re.findall(r'<w:comment ', cx)) == 2, 'expected 2 comments'
m_parent = re.search(r'<w:p[^>]*w14:paraId=\"([0-9A-F]+)\"[^>]*>', cx)
assert m_parent, 'parent paraId missing in comments.xml'
parent_para = m_parent.group(1)
assert f'w15:paraIdParent=\"{parent_para}\"' in ext, \
    f'paraIdParent {parent_para} missing in commentsExtended.xml: {ext}'
crs_ids = re.findall(r'<w:commentRangeStart w:id=\"(\d+)\"', doc)
cre_ids = re.findall(r'<w:commentRangeEnd w:id=\"(\d+)\"', doc)
ref_ids = re.findall(r'<w:commentReference w:id=\"(\d+)\"', doc)
assert sorted(crs_ids) == ['0','1'], f'crs ids: {crs_ids}'
assert sorted(cre_ids) == ['0','1'], f'cre ids: {cre_ids}'
assert sorted(ref_ids) == ['0','1'], f'ref ids: {ref_ids}'
# Reply's range must be nested inside parent's: order is crs0,crs1,...,cre1,cre0
assert crs_ids == ['0','1'], f'crs order: {crs_ids}'
assert cre_ids == ['1','0'], f'cre order: {cre_ids}'
print('R1 reply structure verified')
" 2>&1 | grep -q "R1 reply structure verified" \
    && ok "R1: reply nested inside parent + paraIdParent linkage" \
    || nok "R1 reply structure" "see python output"

"$PY" -m office.validate "$TMP/r_reply.docx" >/dev/null 2>&1 \
    && ok "R1: office.validate accepts threaded reply output" \
    || nok "R1 validate reply" "rejected"

# R2 unknown parent → exit 2 + ParentCommentNotFound envelope
set +e
err=$("$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/_y.docx" \
    --parent 999 --comment "x" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='ParentCommentNotFound' and j['code']==2 and j['details']['parent_id']==999, j" 2>/dev/null \
    && ok "R2: unknown parent → exit 2 + ParentCommentNotFound envelope" \
    || nok "R2 unknown parent" "rc=$rc msg=$err"

# R3 library-mode: unpack → anchor + reply (in-place) → pack → validate
mkdir -p "$TMP/lib_tree"
"$PY" -c "
from office.unpack import unpack
from pathlib import Path
unpack(Path('$TMP/out.docx'), Path('$TMP/lib_tree'))
" >/dev/null 2>&1
"$PY" docx_add_comment.py --unpacked-dir "$TMP/lib_tree" \
    --anchor-text "Quarterly" --comment "lib verify" --author "QA" >/dev/null 2>&1 \
    && ok "R3: --unpacked-dir anchor mode runs" \
    || nok "R3 unpacked anchor" "non-zero exit"
"$PY" docx_add_comment.py --unpacked-dir "$TMP/lib_tree" \
    --parent 0 --comment "lib reply" --author "Dev" >/dev/null 2>&1 \
    && ok "R3: --unpacked-dir reply mode runs" \
    || nok "R3 unpacked reply" "non-zero exit"
"$PY" -c "
from office.pack import pack
from pathlib import Path
pack(Path('$TMP/lib_tree'), Path('$TMP/lib.docx'))
" >/dev/null 2>&1
"$PY" -m office.validate "$TMP/lib.docx" >/dev/null 2>&1 \
    && ok "R3: library-mode round-trip validates" \
    || nok "R3 validate" "rejected"
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/lib.docx') as z:
    cx = z.read('word/comments.xml').decode()
    ext = z.read('word/commentsExtended.xml').decode()
assert len(re.findall(r'<w:comment ', cx)) == 2, f'expected 2 comments'
assert 'paraIdParent' in ext, 'no paraIdParent in commentsExtended.xml'
print('R3 content verified')
" 2>&1 | grep -q "R3 content verified" \
    && ok "R3: library-mode produces parent + reply with thread linkage" \
    || nok "R3 content" "see python output"

# R4 library-mode + INPUT/OUTPUT mutual exclusion → UsageError envelope
set +e
err=$("$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/_z.docx" \
    --unpacked-dir "$TMP/lib_tree" --parent 0 --comment x --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='UsageError' and j['code']==2, j" 2>/dev/null \
    && ok "R4: --unpacked-dir + INPUT/OUTPUT → exit 2 + UsageError envelope" \
    || nok "R4 mutual-exclusion" "rc=$rc msg=$err"

# R5 (VDD-A3): malformed OOXML side-part → MalformedOOXML envelope (no traceback)
mkdir -p "$TMP/bad_tree"
"$PY" -c "
from office.unpack import unpack
from pathlib import Path
unpack(Path('$TMP/r_reply.docx'), Path('$TMP/bad_tree'))
" >/dev/null 2>&1
echo "garbage-not-xml" > "$TMP/bad_tree/word/commentsExtended.xml"
set +e
err=$("$PY" docx_add_comment.py --unpacked-dir "$TMP/bad_tree" \
    --parent 0 --comment "x" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='MalformedOOXML' and j['code']==1 and j['v']==1, j" 2>/dev/null \
    && ok "R5 (VDD-A3): corrupt side-part → exit 1 + MalformedOOXML envelope" \
    || nok "R5 corrupt side-part" "rc=$rc msg=$err"

# R6 (VDD-A5): reply-to-reply re-targets to root — flattened thread
"$PY" docx_add_comment.py "$TMP/r_reply.docx" "$TMP/chain.docx" \
    --parent 1 --comment "second reply (should flatten to root, not chain)" \
    --author "Y" >/dev/null 2>&1
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/chain.docx') as z:
    ext = z.read('word/commentsExtended.xml').decode()
parents = re.findall(r'w15:paraIdParent=\"([0-9A-F]+)\"', ext)
assert len(parents) == 2, f'expected 2 paraIdParent entries, got {parents}'
assert parents[0] == parents[1], f'replies should share root, got {parents}'
print('R6 chain flattened to root')
" 2>&1 | grep -q "R6 chain flattened to root" \
    && ok "R6 (VDD-A5): reply-to-reply flattens to conversation root" \
    || nok "R6 chain flatten" "see python output"

# R7 (VDD-A6): newlines in --comment body → multiple <w:p>
"$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/multi_p.docx" \
    --anchor-text "Quarterly" \
    --comment $'line one\nline two\n\nline four' --author "M" >/dev/null 2>&1
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('$TMP/multi_p.docx') as z:
    cx = z.read('word/comments.xml').decode()
m = re.search(r'<w:comment[^>]*w:author=\"M\".*?</w:comment>', cx, re.S)
body = m.group(0)
n_p = body.count('<w:p ')
texts = [t for t in re.findall(r'<w:t[^>]*>([^<]*)</w:t>', body) if t]
assert n_p == 4, f'expected 4 <w:p> (incl. blank), got {n_p}'
assert texts == ['line one', 'line two', 'line four'], f'texts: {texts}'
print('R7 multi-paragraph body verified')
" 2>&1 | grep -q "R7 multi-paragraph body verified" \
    && ok "R7 (VDD-A6): newlines in body split into <w:p> paragraphs" \
    || nok "R7 multi-paragraph body" "see python output"

# R8 (VDD-A8): --parent + --anchor-text together does NOT leak anchor in stdout
out=$("$PY" docx_add_comment.py "$TMP/r_reply.docx" "$TMP/_a8.docx" \
    --parent 0 --anchor-text "should-be-ignored" --comment "ok" --author "X" 2>&1 | tail -1)
echo "$out" | grep -q "should-be-ignored" \
    && nok "R8 (VDD-A8) stdout leaked anchor" "stdout: $out" \
    || ok "R8 (VDD-A8): --parent stdout does not leak unused --anchor-text"

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

# --- docx-4 + docx-5: docx2md sidecar (comments + revisions) + footnotes ---
echo "docx-4 + docx-5 docx2md sidecar + pandoc footnotes:"

# 1. Negative case: clean fixture round-trip → no sidecar written.
node docx2md.js "$TMP/out.docx" "$TMP/clean.md" >/dev/null 2>&1
[ ! -e "$TMP/clean.docx2md.json" ] \
    && ok "clean fixture: no sidecar" \
    || nok "clean fixture sidecar" "sidecar created on doc with no comments/revisions"

# 2. Comments path: use docx_add_comment.py to inject a comment into out.docx,
#    then run docx2md and confirm sidecar shows it.
"$PY" docx_add_comment.py "$TMP/out.docx" "$TMP/d4_commented.docx" \
    --anchor-text "Quarterly" --comment "Audit note" \
    --author "Auditor" --initials "AU" >/dev/null 2>&1
node docx2md.js "$TMP/d4_commented.docx" "$TMP/d4_commented.md" >/dev/null 2>&1
[ -s "$TMP/d4_commented.docx2md.json" ] \
    && ok "commented docx → sidecar written" \
    || nok "sidecar present" "missing or empty"

"$PY" -c "
import json
with open('$TMP/d4_commented.docx2md.json') as f: j = json.load(f)
assert j['v'] == 1, f'wrong schema version: {j.get(\"v\")}'
assert isinstance(j['comments'], list) and len(j['comments']) >= 1, f'expected >=1 comment, got {len(j[\"comments\"])}'
c = j['comments'][0]
assert c['author'] == 'Auditor', c
assert c['text'] == 'Audit note', c
assert isinstance(c.get('paragraphIndex'), int) and c['paragraphIndex'] >= 0, c
assert 'anchorTextBefore' in c and 'anchorTextAfter' in c, c
print('schema ok')
" 2>&1 | grep -q "schema ok" \
    && ok "sidecar v1 schema: comment fields populated" \
    || nok "sidecar schema" "see python output"

# 3. Revisions + footnotes: programmatically inject ins/del/footnoteReference/endnoteReference
#    into out.docx and verify the sidecar + pandoc markers.
"$PY" - "$TMP/out.docx" "$TMP/d4_rich.docx" << 'PYEOF'
import sys, zipfile, shutil, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'r') as zin:
    parts = {n: zin.read(n) for n in zin.namelist()}
doc = parts['word/document.xml'].decode('utf-8')
inject = (
    '<w:ins w:id="100" w:author="Alice" w:date="2024-06-01T10:00:00Z">'
    '<w:r><w:t xml:space="preserve">[INS]</w:t></w:r></w:ins>'
    '<w:del w:id="101" w:author="Bob" w:date="2024-06-02T11:00:00Z">'
    '<w:r><w:delText xml:space="preserve">[DEL]</w:delText></w:r></w:del>'
    '<w:r><w:footnoteReference w:id="2"/></w:r>'
    '<w:r><w:endnoteReference w:id="2"/></w:r>'
)
m = re.search(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', doc, flags=re.DOTALL)
assert m, 'no <w:p>'
doc = doc[:m.start()] + m.group(1) + m.group(2) + inject + m.group(3) + doc[m.end():]
parts['word/document.xml'] = doc.encode('utf-8')
parts['word/footnotes.xml'] = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="2"><w:p><w:r><w:t xml:space="preserve">A footnote about something important.</w:t></w:r></w:p></w:footnote>'
    '</w:footnotes>'
).encode('utf-8')
parts['word/endnotes.xml'] = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:endnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:endnote>'
    '<w:endnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:endnote>'
    '<w:endnote w:id="2"><w:p><w:r><w:t xml:space="preserve">An endnote referenced in the body.</w:t></w:r></w:p></w:endnote>'
    '</w:endnotes>'
).encode('utf-8')
ct = parts['[Content_Types].xml'].decode('utf-8')
if '/word/footnotes.xml' not in ct:
    ct = ct.replace('</Types>',
        '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
        '<Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>'
        '</Types>')
    parts['[Content_Types].xml'] = ct.encode('utf-8')
rels = parts['word/_rels/document.xml.rels'].decode('utf-8')
if 'footnotes.xml' not in rels:
    rels = rels.replace('</Relationships>',
        '<Relationship Id="rIdFn999" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
        '<Relationship Id="rIdEn999" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes" Target="endnotes.xml"/>'
        '</Relationships>')
    parts['word/_rels/document.xml.rels'] = rels.encode('utf-8')
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for name, data in parts.items():
        zout.writestr(name, data)
PYEOF

node docx2md.js "$TMP/d4_rich.docx" "$TMP/d4_rich.md" >/dev/null 2>&1

"$PY" -c "
import json
with open('$TMP/d4_rich.docx2md.json') as f: j = json.load(f)
ins = [r for r in j['revisions'] if r['type'] == 'insertion']
dels = [r for r in j['revisions'] if r['type'] == 'deletion']
assert len(ins) == 1 and ins[0]['author'] == 'Alice' and ins[0]['text'] == '[INS]', ins
assert len(dels) == 1 and dels[0]['author'] == 'Bob' and dels[0]['text'] == '[DEL]', dels
assert isinstance(ins[0]['paragraphIndex'], int) and ins[0]['paragraphIndex'] >= 0
assert isinstance(ins[0]['runIndex'], int) and ins[0]['runIndex'] >= 0
print('revisions ok')
" 2>&1 | grep -q "revisions ok" \
    && ok "sidecar captures <w:ins>/<w:del> with author + paragraphIndex + runIndex" \
    || nok "revision capture" "see python output"

# Pandoc footnote markers in the markdown body
grep -E '\[\^fn-2\]' "$TMP/d4_rich.md" >/dev/null \
    && ok "pandoc footnote marker [^fn-2] in body" \
    || nok "footnote marker" "missing"
grep -E '\[\^en-2\]' "$TMP/d4_rich.md" >/dev/null \
    && ok "pandoc endnote marker [^en-2] in body" \
    || nok "endnote marker" "missing"

# Definitions block at end
grep -E '^\[\^fn-2\]: A footnote about something important' "$TMP/d4_rich.md" >/dev/null \
    && ok "footnote definition appended" \
    || nok "footnote definition" "missing"
grep -E '^\[\^en-2\]: An endnote referenced in the body' "$TMP/d4_rich.md" >/dev/null \
    && ok "endnote definition appended" \
    || nok "endnote definition" "missing"

# 4. --no-metadata suppresses the sidecar even when comments/revisions exist.
rm -f "$TMP/d4_rich.docx2md.json"
node docx2md.js "$TMP/d4_rich.docx" "$TMP/d4_no_meta.md" --no-metadata >/dev/null 2>&1
[ ! -e "$TMP/d4_no_meta.docx2md.json" ] && [ ! -e "$TMP/d4_rich.docx2md.json" ] \
    && ok "--no-metadata suppresses sidecar" \
    || nok "--no-metadata" "sidecar still written"

# 5. --no-footnotes skips the pandoc conversion (no [^fn-/[^en- markers).
node docx2md.js "$TMP/d4_rich.docx" "$TMP/d4_no_fn.md" --no-footnotes >/dev/null 2>&1
[ "$(grep -cE '\[\^fn-' "$TMP/d4_no_fn.md")" = "0" ] \
    && ok "--no-footnotes skips pandoc conversion" \
    || nok "--no-footnotes" "marker still present"

# 6. --metadata-json overrides sidecar location.
custom="$TMP/d4_custom_path.json"
node docx2md.js "$TMP/d4_rich.docx" "$TMP/d4_custom.md" --metadata-json "$custom" >/dev/null 2>&1
[ -s "$custom" ] && [ ! -e "$TMP/d4_custom.docx2md.json" ] \
    && ok "--metadata-json overrides default sidecar path" \
    || nok "--metadata-json" "wrong location"

# 7. --json-errors envelope on usage error.
set +e
err=$(node docx2md.js --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['v']==1 and j['type']=='UsageError', j" 2>/dev/null \
    && ok "docx2md --json-errors emits v=1 envelope on usage error" \
    || nok "json-errors envelope" "rc=$rc msg=$err"

# --- VDD HIGH-1: same-path guard (refuse to overwrite input docx) ---------
# Without this guard, `node docx2md.js x.docx x.docx` would silently destroy
# the input by writing markdown over it. Verified pre-fix on a 9116-byte
# valid docx → 1398-byte UTF-8 markdown.
cp "$TMP/out.docx" "$TMP/d4_selfovr.docx"
set +e
err=$(node docx2md.js "$TMP/d4_selfovr.docx" "$TMP/d4_selfovr.docx" --json-errors 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 6 ] \
    && echo "$err" | "$PY" -c "import sys, json; j=json.loads(sys.stdin.read()); assert j['type']=='SelfOverwriteRefused' and j['code']==6, j" 2>/dev/null \
    && "$PY" -m office.validate "$TMP/d4_selfovr.docx" >/dev/null 2>&1 \
    && ok "VDD HIGH-1: same-path guard refuses overwrite + input docx intact" \
    || nok "same-path guard" "rc=$rc msg=$err (input intact?)"

# --- VDD MED-1: empty footnote body → reference still resolvable ----------
# Build a fixture with one populated footnote (id=2) and one empty (id=3).
# Pre-fix bug: [^fn-3] appeared in body but had no [^fn-3]: definition.
"$PY" - "$TMP/out.docx" "$TMP/d4_emptyfn.docx" << 'PYEOF'
import sys, zipfile, shutil, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'r') as zin:
    parts = {n: zin.read(n) for n in zin.namelist()}
doc = parts['word/document.xml'].decode('utf-8')
m = re.search(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', doc, flags=re.DOTALL)
inject = '<w:r><w:footnoteReference w:id="2"/></w:r><w:r><w:footnoteReference w:id="3"/></w:r>'
doc = doc[:m.start()] + m.group(1) + m.group(2) + inject + m.group(3) + doc[m.end():]
parts['word/document.xml'] = doc.encode('utf-8')
parts['word/footnotes.xml'] = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="2"><w:p><w:r><w:t xml:space="preserve">Real footnote text.</w:t></w:r></w:p></w:footnote>'
    '<w:footnote w:id="3"><w:p/></w:footnote>'
    '</w:footnotes>'
).encode('utf-8')
ct = parts['[Content_Types].xml'].decode('utf-8')
if '/word/footnotes.xml' not in ct:
    ct = ct.replace('</Types>', '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>')
    parts['[Content_Types].xml'] = ct.encode('utf-8')
rels = parts['word/_rels/document.xml.rels'].decode('utf-8')
if 'footnotes.xml' not in rels:
    rels = rels.replace('</Relationships>', '<Relationship Id="rIdFn999" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
    parts['word/_rels/document.xml.rels'] = rels.encode('utf-8')
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for n,d in parts.items():
        zout.writestr(n, d)
PYEOF
node docx2md.js "$TMP/d4_emptyfn.docx" "$TMP/d4_emptyfn.md" >/dev/null 2>&1
# Both [^fn-2] and [^fn-3] must have matching definitions (no dangling).
grep -E '^\[\^fn-2\]:' "$TMP/d4_emptyfn.md" >/dev/null \
    && grep -E '^\[\^fn-3\]:' "$TMP/d4_emptyfn.md" >/dev/null \
    && ok "VDD MED-1: empty footnote body still gets a [^fn-N]: definition (no dangling ref)" \
    || nok "empty footnote definition" "[^fn-3]: missing"

# --- VDD MED-2: --metadata-json refuses to consume a flag as path --------
# Pre-fix bug: `--metadata-json --no-footnotes` set metadataJsonPath = "--no-footnotes"
set +e
err=$(node docx2md.js "$TMP/out.docx" "$TMP/x.md" --metadata-json --no-footnotes 2>&1 >/dev/null)
rc=$?
set -e
[ "$rc" -eq 2 ] && echo "$err" | grep -q "requires a path" \
    && ok "VDD MED-2: --metadata-json without value rejected" \
    || nok "--metadata-json validation" "rc=$rc msg=$err"

# --- VDD LOW-3: id=\"\" not coerced to 0 ---------------------------------
"$PY" - "$TMP/out.docx" "$TMP/d4_emptyid.docx" << 'PYEOF'
import sys, zipfile, shutil, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'r') as zin:
    parts = {n: zin.read(n) for n in zin.namelist()}
# Inject one well-formed and one malformed (empty id) <w:ins>
doc = parts['word/document.xml'].decode('utf-8')
m = re.search(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', doc, flags=re.DOTALL)
inject = (
    '<w:ins w:id="50" w:author="OK" w:date="2024-01-01T00:00:00Z"><w:r><w:t>good</w:t></w:r></w:ins>'
    '<w:ins w:id="" w:author="Bad" w:date="2024-01-01T00:00:00Z"><w:r><w:t>bad</w:t></w:r></w:ins>'
)
doc = doc[:m.start()] + m.group(1) + m.group(2) + inject + m.group(3) + doc[m.end():]
parts['word/document.xml'] = doc.encode('utf-8')
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for n,d in parts.items():
        zout.writestr(n, d)
PYEOF
node docx2md.js "$TMP/d4_emptyid.docx" "$TMP/d4_emptyid.md" >/dev/null 2>&1
"$PY" -c "
import json
with open('$TMP/d4_emptyid.docx2md.json') as f: j = json.load(f)
ids = [r['id'] for r in j['revisions']]
assert 50 in ids, ids
# Pre-fix: id='' coerced to 0 → ids contains 0. Post-fix: id is null.
assert 0 not in ids, f'empty id silently coerced to 0: {ids}'
assert any(i is None for i in ids), f'malformed id should serialize as null: {ids}'
print('id parsing ok')
" 2>&1 | grep -q "id parsing ok" \
    && ok "VDD LOW-3: id=\"\" serialized as null (not coerced to 0)" \
    || nok "id parsing" "see python output"

# --- VDD coverage: Cyrillic footnote text round-trip ---------------------
"$PY" - "$TMP/out.docx" "$TMP/d4_cyr.docx" << 'PYEOF'
import sys, zipfile, shutil, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'r') as zin:
    parts = {n: zin.read(n) for n in zin.namelist()}
doc = parts['word/document.xml'].decode('utf-8')
m = re.search(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', doc, flags=re.DOTALL)
doc = doc[:m.start()] + m.group(1) + m.group(2) + '<w:r><w:footnoteReference w:id="7"/></w:r>' + m.group(3) + doc[m.end():]
parts['word/document.xml'] = doc.encode('utf-8')
parts['word/footnotes.xml'] = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="7"><w:p><w:r><w:t xml:space="preserve">Сноска: проверка кириллицы и emoji 🚀</w:t></w:r></w:p></w:footnote>'
    '</w:footnotes>'
).encode('utf-8')
ct = parts['[Content_Types].xml'].decode('utf-8')
if '/word/footnotes.xml' not in ct:
    ct = ct.replace('</Types>', '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>')
    parts['[Content_Types].xml'] = ct.encode('utf-8')
rels = parts['word/_rels/document.xml.rels'].decode('utf-8')
if 'footnotes.xml' not in rels:
    rels = rels.replace('</Relationships>', '<Relationship Id="rIdFn999" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
    parts['word/_rels/document.xml.rels'] = rels.encode('utf-8')
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for n,d in parts.items():
        zout.writestr(n, d)
PYEOF
node docx2md.js "$TMP/d4_cyr.docx" "$TMP/d4_cyr.md" >/dev/null 2>&1
grep -F 'Сноска: проверка кириллицы и emoji 🚀' "$TMP/d4_cyr.md" >/dev/null \
    && ok "VDD coverage: Cyrillic + emoji footnote text round-trips" \
    || nok "Cyrillic footnote" "characters lost in pipeline"

# --- VDD coverage: rPrChange counted in unsupported ----------------------
"$PY" - "$TMP/out.docx" "$TMP/d4_rprc.docx" << 'PYEOF'
import sys, zipfile, shutil, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'r') as zin:
    parts = {n: zin.read(n) for n in zin.namelist()}
doc = parts['word/document.xml'].decode('utf-8')
m = re.search(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', doc, flags=re.DOTALL)
inject = (
    '<w:r>'
    '<w:rPr><w:rPrChange w:id="200" w:author="Reviewer" w:date="2024-01-01T00:00:00Z">'
    '<w:rPr/></w:rPrChange></w:rPr>'
    '<w:t>formatting-change carrier</w:t>'
    '</w:r>'
)
doc = doc[:m.start()] + m.group(1) + m.group(2) + inject + m.group(3) + doc[m.end():]
parts['word/document.xml'] = doc.encode('utf-8')
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for n,d in parts.items():
        zout.writestr(n, d)
PYEOF
node docx2md.js "$TMP/d4_rprc.docx" "$TMP/d4_rprc.md" >/dev/null 2>&1
"$PY" -c "
import json
with open('$TMP/d4_rprc.docx2md.json') as f: j = json.load(f)
assert j['unsupported']['rPrChange'] >= 1, j['unsupported']
print('rPrChange counted')
" 2>&1 | grep -q "rPrChange counted" \
    && ok "VDD coverage: rPrChange counted in unsupported (honest-scope)" \
    || nok "rPrChange counter" "see python output"

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

# --- q-7: html2docx regression battery -----------------------------------
# Renders every committed fixture (synthetic + platform) plus any
# user-local files in tests/tmp/ in BOTH regular and reader modes,
# then asserts: paragraph count within tolerance band, file size
# within tolerance band, required_needles present, forbidden_needles
# absent (chrome-leakage detector). Mirrors pdf-5 iter-6.
echo "q-7 regression battery:"
bat_rc=0
bat_out=$("$PY" -m unittest tests.test_battery 2>&1) || bat_rc=$?
bat_ran=$(echo "$bat_out" | grep -oE 'Ran [0-9]+ tests?' | grep -oE '[0-9]+' | tail -1)
bat_ran=${bat_ran:-0}
if [ "$bat_rc" -eq 0 ] && [ "$bat_ran" -gt 0 ]; then
    ok "battery: $bat_ran tests passed"
else
    nok "battery" "rc=$bat_rc ran=$bat_ran"
    echo "$bat_out" | tail -25
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
