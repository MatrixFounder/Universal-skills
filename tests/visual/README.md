# Visual regression for the office skills (q-2)

Captures the first page of representative PDF outputs as PNG goldens
and re-renders them on every E2E run. Catches accidental layout / style
regressions that pass schema-validation and content-grep tests.

## How it works

```
PDF --(pdftoppm -jpeg -r 80 -f 1 -l 1)--> JPEG
    --(Pillow re-encode)--> PNG (captured)
PNG (captured) ⨯ PNG (golden) --(magick compare -metric AE -fuzz 5%)--> diff_px
```

Default tolerance: 0.5% of total pixels (≈ 2300 px on an 80-DPI letter
page). Override per-call with `--threshold-px N` or `--threshold-pct F`.

## Files

- [`visual_compare.py`](visual_compare.py) — comparator CLI.
- [`_visual_helper.sh`](_visual_helper.sh) — `visual_check` bash function
  sourced by per-skill `test_e2e.sh`.
- `goldens/<skill>/<name>.png` — committed golden images.

## Running

The visual checks run automatically as the last block of every per-skill
`test_e2e.sh`:

```bash
bash skills/pdf/scripts/tests/test_e2e.sh
# ...
# q-2 visual regression:
#   ✓ visual: fixture-base
#   ...
```

By default missing goldens or missing ImageMagick warn-and-skip. CI sets
`STRICT_VISUAL=1` to make these hard failures.

## Updating goldens

When a deliberate output change makes the existing golden stale,
regenerate:

```bash
# Single skill
UPDATE_GOLDENS=1 bash skills/pdf/scripts/tests/test_e2e.sh

# All four
UPDATE_GOLDENS=1 bash tests/run_all_e2e.sh
```

Then `git diff tests/visual/goldens/` and commit.

## Cross-platform note

Goldens here were generated on **macOS / homebrew LibreOffice**.
Rendering on Ubuntu CI (different fontconfig, different anti-alias
backend) drifts by a few percent of pixels even with identical inputs.
The 5%-fuzz / 0.5%-pct defaults absorb most of that, but if CI fails on
the first push it's normal — regenerate goldens via a `workflow_dispatch`
on the matching runner image and commit those instead.

## Adding a new golden

1. Have your `test_e2e.sh` produce the PDF (existing or new).
2. Add a `visual_check "$TMP/your.pdf" "your-name"` line in the
   `q-2 visual regression:` block.
3. `UPDATE_GOLDENS=1 bash skills/<skill>/scripts/tests/test_e2e.sh` to
   create `tests/visual/goldens/<skill>/your-name.png`.
4. Commit the .png next to your test changes.
