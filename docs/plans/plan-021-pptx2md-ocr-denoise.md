# PLAN 021 — pptx2md `--ocr-denoise` (stub-first)

Maps TASK 021 R1–R8. Files touched (all pptx-specific, **outside** the office
replication boundary): `pptx2md/cli.py`, `pptx2md/ocr.py`, `pptx2md/emit.py`,
`pptx2md/tests/*`, docs. No change to `office/`, `_soffice.py`, `_errors.py`,
`preview.py`, `office_passwd.py`.

## Stub-first ordering

- **021-01 — CLI surface + plumbing (STUB, proves R4).**
  Add `--ocr-denoise` (store_true, default False), `--ocr-min-px` (int, default 48),
  `--ocr-min-confidence` (float, default 50). Thread the three values from `args`
  into `ocr_asset(...)` (via `_build_ocr_text`) and into `emit.render_deck(...)`.
  Filter bodies are **no-ops when denoise is off**. Green gate: the *entire existing
  suite stays green unchanged* — default path is byte-identical (R4/R7).

- **021-02 — R1 size-gate.** In `ocr_asset`, when denoise on, after the lazy
  `Image.open`, return `""` if `min(w, h) < min_px` (before spawning tesseract).
  Tests: TC-1 (tiny→skip, large→runs).

- **021-03 — R2 confidence-gate.** When denoise on, invoke `tesseract … tsv`
  (not `stdout`); add pure helper `_filter_tsv(tsv: str, min_conf: float) -> str`
  → keep words with `conf >= min_conf`, regroup by (block,par,line), join lines,
  drop block entirely if no word survives or mean surviving conf `< min_conf`.
  Default path (denoise off) keeps `stdout`. Tests: TC-2 (mixed/all-low TSV),
  TC-5 (malformed TSV → `""`, no raise).

- **021-04 — R3 dedup.** In `emit.render_deck`, when denoise on, keep a `seen`
  set of normalized (`strip()`) OCR texts; suppress a block whose text was already
  emitted. Tests: TC-3 (same text ×3 → once).

- **021-05 — docs + dogfood + gates.**
  `references/pptx-to-markdown.md` (new `--ocr-denoise` subsection + best-practice
  note), `ARCHITECTURE.md` (D-12 entry + §10 honest-scope), `.AGENTS.md`.
  Re-export tmp8 with `--ocr --ocr-denoise`, report empty/noise-block delta per
  deck, confirm no audited-substantive text lost. Gates: full pptx2md suite +
  legacy `test_e2e.sh` + `validate_skill.py skills/pptx` + confirm the office §9
  diff matrices remain silent (we touch no replicated file). Adversarial review
  (logic critic) on the filter + dedup before declaring done. No auto-commit.

## Acceptance

R4 (default unchanged) is the hard gate — verified at 021-01 and re-verified after
every step. R1–R3 each land behind `--ocr-denoise` with a unit test; R8 dogfood
quantifies the win on tmp8.
