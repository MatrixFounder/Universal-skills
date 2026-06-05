# Task 019-03 [LOGIC]: `md2docx.js` page geometry (A4 / landscape / margins)

> **Predecessor:** none (independent of 01/02; Node surface).
> **RTM:** completes [B1][B2][B3][B4][B5][F1a][F1d].
> **ARCH:** §2.1 FC-2, §4.1 PageGeometry, §4.3 I-3, §5.1, §10, §12 D-A3/D-A7.

## Use Case Connection
- UC-2 (A4 one-command), UC-2/A1 (landscape), UC-2/A2 (margins), UC-2/A3 (bad flag),
  UC-6 (Letter regression) — all **real** here.

## Goal
Parametrise `scripts/md2docx.js`: add `--page-size A4|Letter` (default Letter),
`--landscape`, `--margins T,R,B,L`; **derive all geometry from the resolved page** — no
surviving Letter literal on any geometry path; reject unknown `--`flags.

## Steps (edit `scripts/md2docx.js`)
1. **Arg parser (`:9-21`).** Extend the loop to consume `--page-size <val>`,
   `--landscape` (boolean), `--margins <csv>`. **Reject unknown `--`-prefixed tokens**
   (currently they fall through to `positional[]`) → `console.error(usage); process.exit(1)`.
   Update the usage string (`:26`).
2. **Resolve geometry (after parsing, before `contentWidthDxa`).**
   - `const SIZES = { letter: {w:12240,h:15840}, a4: {w:11906,h:16838} };`
   - validate `--page-size` ∈ {A4, Letter} (case-insensitive); unknown → exit 1.
   - `let {w:pageW, h:pageH} = SIZES[size]; if (landscape) [pageW,pageH]=[pageH,pageW];`
   - parse `--margins`: 4 ints (dxa) `T,R,B,L`; per-value optional `mm` suffix →
     `Math.round(parseFloat(v)*56.7)`; default all `1440`; malformed → exit 1.
3. **Derived constants (replace `:40` hardcode).**
   - `const contentWidthDxa = pageW - marginL - marginR;` (Letter default ⇒ 9360; A4 ⇒ 9026)
   - `const maxWidthPx  = Math.floor(contentWidthDxa / 15);`
   - `const maxHeightPx = Math.floor((pageH - marginT - marginB) / 15);`
4. **Thread into emitters.**
   - image `buildImageRun` (`:82-89`): replace literal `620`/`800` with
     `maxWidthPx`/`maxHeightPx`.
   - Mermaid (`:278-284`): replace `mmdMaxWidth=620`/`mmdMaxHeight=800` with the same.
   - table width/colWidth already use `contentWidthDxa` (`:233,261`) — confirm no residue.
   - section `page` (`:343-346`): `size:{width:pageW,height:pageH}`,
     `margin:{top:marginT,right:marginR,bottom:marginB,left:marginL}`.

## Test Cases — `scripts/tests/test_md2docx_pagesize.py` (`unittest`, drives node)
(Pattern: shell out to `node scripts/md2docx.js`, read `word/document.xml` via stdlib
`zipfile`, assert with regex.)
1. **test_a4_pgsz (F1a/B1)** — `--page-size A4` ⇒ `<w:pgSz w:w="11906" w:h="16838"…>`.
2. **test_letter_default_pgsz_exact (F1d/B5c)** — no flags ⇒ `w:w="12240" w:h="15840"`.
3. **test_letter_content_width_unchanged (F1d/I-3)** — no-flag table colWidth derives from
   9360 (assert a wide table's first cell width == floor(9360/numCols)). The load-bearing
   regression invariant.
4. **test_a4_table_no_overflow (B5b)** — wide table on A4: every cell `w:w` sums ≤ 9026;
   no cell width exceeds A4 content width.
5. **test_landscape (B2)** — `--page-size A4 --landscape` ⇒ `w:w="16838" w:h="11906"`.
6. **test_margins (B3)** — `--margins 1134,1134,1134,1134` ⇒ `<w:pgMar … w:top="1134" …>`;
   `--margins 20mm,20mm,20mm,20mm` ⇒ `≈1134` (20×56.7); contentWidthDxa recomputed.
7. **test_unknown_flag_rejected (B1c/MINOR#7)** — `--page-sizes A4` (typo) ⇒ non-zero exit.
8. **test_bad_pagesize / test_bad_margins** — `--page-size A3` / `--margins 1,2,3` ⇒ exit 1.
9. **test_a4_validates** — A4 output passes `office/validate.py` (`OK`).

## Verification
```bash
cd skills/docx
node scripts/md2docx.js examples/fixture-simple.md /tmp/a4.docx --page-size A4
python3 -c "import zipfile,re; print(re.findall(r'<w:pgSz[^>]*>', zipfile.ZipFile('/tmp/a4.docx').read('word/document.xml').decode()))"
# expect: ['<w:pgSz w:w="11906" w:h="16838" .../>']
node scripts/md2docx.js examples/fixture-simple.md /tmp/letter.docx
python3 -c "...assert 12240x15840..."     # Letter regression
./.venv/bin/python -m unittest tests.test_md2docx_pagesize -v
```

## Acceptance Criteria
- [ ] `--page-size A4` ⇒ `11906×16838`; no-flag ⇒ `12240×15840` (byte-exact pgSz).
- [ ] `contentWidthDxa` derived (9360 Letter / 9026 A4); no `9360`/`620`/`800` literal on a
  geometry path (grep the diff).
- [ ] A4 tables/images fit content width (no-overflow test green).
- [ ] `--landscape`/`--margins` (incl. `mm`) reflected in `pgSz`/`pgMar`.
- [ ] Unknown/bad flags exit non-zero with usage.
- [ ] A4 output `office/validate.py OK`; all md2docx tests green; existing
  `docx_replace.py --insert-after` E2E (flag-free `md2docx.js`) stays green.

## Notes
- Letter image caps shift 620→624 / 800→864 (geometrically exact). The Letter regression
  asserts **pgSz + contentWidthDxa** (the load-bearing invariants), NOT the px caps (ARCH
  §4.3 I-3). Do not re-introduce the old literals.
- `md2docx.js` is **docx-only** (not replicated) — no cross-skill copy here.
