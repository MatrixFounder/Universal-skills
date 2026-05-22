# Task 014-02 [LOGIC IMPLEMENTATION]: Chrome-engine `page.pdf(outline=True, tagged=True)` parity

> **Predecessor:** 014-01 (`_outline_probe.py` + the `pdf-7` E2E section exist).
> **RTM:** **completes** [R4][R5][R6].
> **ARCH:** §2.1 F3/F4, §5.2 (`render_chrome` change), §5.3 (dependency +
> installer), §5.5 (chrome E2E block), §13 D2/D3/D4/D7/D8.
>
> **Spec amendment (2026-05-22, TASK 014 §1.1a / Q-3):** during this task a
> Playwright probe established that Chromium emits the outline **only** when
> `page.pdf(tagged=True)` is set *together with* `outline=True` (`outline`
> alone → 0 bookmarks). Both flags are now required; the chrome PDF becomes a
> tagged PDF (accepted side-effect, user-confirmed). This task file reflects
> the amended (v2) spec.

## Use Case Connection

- **UC-2 main** — agent renders HTML→PDF via `--engine chrome`; outline present
  (parity with the weasyprint engine).
- **UC-2 / A1** — chrome engine not installed → the chrome outline test
  soft-skips.
- **UC-2 / A2** — old Playwright (< 1.42) → the R6.4 capability probe fails
  loudly instead of letting a silent `TypeError` through.

## Task Goal

Deliver **Part B** — close the one real gap: `html2pdf.py --engine chrome` does
not emit a PDF outline because `render_chrome()`'s `page.pdf()` call omits
Playwright's `outline=True` **and `tagged=True`** options. Chromium builds the
outline from the tagged-PDF structure tree, so **both** are required —
`outline=True` alone emits 0 bookmarks (empirically verified; TASK §1.1a). Add
both arguments, raise the Playwright floor to the release that introduced them,
make the installer upgrade an already-present too-old Playwright, and add the
chrome outline E2E block (RED → GREEN within this task).

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/html2pdf_lib/chrome_engine.py`

**`render_chrome()` — the `page.pdf(...)` call** (currently ~lines 717–724):
**append two** keyword arguments, `outline=True` and `tagged=True`, **after the
existing `margin` argument** — leave the existing five arguments (`path`,
`format`, `print_background`, `scale`, `margin`) in their current order:

```python
page.pdf(
    path=str(output_path),
    format=fmt,
    print_background=print_background,
    scale=pdf_scale,
    margin={"top": "1cm", "right": "1cm",
            "bottom": "1cm", "left": "1cm"},
    # pdf-7 / TASK 014: emit a PDF outline (bookmarks) from the document
    # headings — parity with the weasyprint engine (UA bookmark-level).
    # tagged=True is REQUIRED, not optional: Chromium builds the outline
    # from the tagged-PDF structure tree, so outline=True alone emits 0
    # bookmarks (TASK 014 §1.1a). The chrome PDF is consequently a tagged
    # PDF — an accepted, necessary side-effect.
    outline=True,
    tagged=True,
)
```

- **Append after `margin`, do not reorder** the existing five arguments.
- **No new `render_chrome()` parameter** — both flags are hardcoded at the
  call site. There is no `--no-outline` CLI flag (ARCH D2, TASK Q-2); nothing
  varies them.
- **No other `page.pdf()` argument changes** (`path`, `format`,
  `print_background`, `scale`, `margin` untouched — TASK R4.4).
- `<h1>`–`<h6>` content elements already survive `_strip_script_tags` and the
  `_LAYOUT_NORMALIZE_CSS` injection — confirmed by reading the module; the
  chrome E2E block re-verifies (R4.3).

#### File: `skills/pdf/scripts/requirements-chrome.txt`

Change the version pin (last line) `playwright>=1.40,<2.0` →
`playwright>=1.42,<2.0`. Update the adjacent comment to record **why**: 1.42
is the Playwright release that added the `page.pdf()` `outline` **and `tagged`**
options (both used by `render_chrome()` for `pdf-7`); `>=1.40` could resolve to
1.40/1.41 where `page.pdf(outline=True, tagged=True)` raises `TypeError`
(R5.1, R5.2).

#### File: `skills/pdf/scripts/install.sh`

In the `--with-chrome` block, the `requirements-chrome.txt` install line
(currently `./.venv/bin/pip install --quiet -r requirements-chrome.txt`,
~line 107): add `--upgrade` →

```sh
./.venv/bin/pip install --quiet --upgrade -r requirements-chrome.txt
```

so re-running `install.sh --with-chrome` lifts an already-present **too-old**
Playwright (1.40/1.41 from a pdf-11-era install) — a plain `pip install -r`
does not upgrade an already-satisfied package (R5.3, TASK M-1). Adjust the
nearby comment if it claims plain idempotence.

#### File: `skills/pdf/scripts/tests/test_e2e.sh`

Append a **chrome-engine** block to the `pdf-7: PDF outline` section created by
014-01 — placed **after** Block B (it reuses `$TMP/outline.html`, the
plain-content fixture written there; ARCH D8). Soft-skip pattern, mirroring the
`mermaid_renders` precedent:

1. **Capability probe (R6.4)** — run a small `"$PY" - <<'PY' … PY` snippet:
   `import inspect; from playwright.sync_api import Page` →
   `"outline" in inspect.signature(Page.pdf).parameters`. Three outcomes
   (the probe runs **before** any render — ARCH §11 / m-3):
   - Playwright not importable → **`skip`** "chrome outline — Playwright not
     installed (opt-in: `bash install.sh --with-chrome`)".
   - Playwright present but `Page.pdf` has **no** `outline` parameter →
     **`nok`** "installed Playwright's `page.pdf()` lacks the `outline` kwarg —
     upgrade to >=1.42 (re-run `install.sh --with-chrome`)". This is the loud
     R6.4 diagnostic — a `nok`, not a skip.
   - `outline` parameter present → proceed.
2. **Render + assert** — run
   `"$PY" html2pdf.py "$TMP/outline.html" "$TMP/outline_chrome.pdf" --engine chrome`.
   - If it exits non-zero (e.g. the Chromium binary is not installed) →
     **`skip`** "chrome outline — engine unavailable at render time".
   - Else probe `$TMP/outline_chrome.pdf` with `_outline_probe.py`: **`ok`**
     iff the probe exits `0` (non-empty) **and** its output shows nesting
     (at least one indented line) and the `Alpha` title (R6.1, R6.3) — else
     **`nok`**.
3. Add a comment recording the **A-6 verification point**: a passing assertion
   here empirically confirms that `render_chrome()`'s `emulate_media("screen")`
   does **not** suppress the chrome outline (TASK A-6 / R6.3).

> Use `playwright.__version__` **nowhere** — the module exposes no such
> attribute (confirmed in Analysis). The `inspect.signature` probe is the
> reliable capability check.

## Component Integration

`render_chrome()` is called by `html2pdf_lib/render.py` `convert()` on the
`engine == "chrome"` branch; that call site is unchanged. The chrome E2E block
exercises the whole `html2pdf.py --engine chrome` path end-to-end.

## Test Cases

### E2E Tests (Red → Green within this task)

1. **`html2pdf --engine chrome → non-empty nested PDF outline`** — the chrome
   block above. **RED** before the `outline=True` change (no outline →
   `_outline_probe.py` exits 3 → `nok`); **GREEN** after it. When
   Playwright/Chromium is absent the check **soft-skips** (still a green
   suite). (R4, R6.)
2. **chrome capability probe** — `Page.pdf` exposes the `outline` kwarg
   (R6.4); `nok` if not.

### Regression Tests

- `bash skills/pdf/scripts/tests/test_e2e.sh` — full suite green (the 014-01
  weasyprint checks unaffected; pre-existing pdf-11 chrome coverage unaffected).
- `diff -q skills/docx/scripts/_errors.py skills/pdf/scripts/_errors.py` and
  `… preview.py` — silent.

## Acceptance Criteria

- [ ] `render_chrome()`'s `page.pdf()` call passes `outline=True` **and
      `tagged=True`** (both appended after `margin`); the existing five
      arguments are unchanged in order ([R4] 4.1 / 4.4).
- [ ] `requirements-chrome.txt` floor is `playwright>=1.42,<2.0` with a comment
      explaining the `outline`-option rationale ([R5] 5.1 / 5.2).
- [ ] `install.sh --with-chrome` installs `requirements-chrome.txt` with
      `--upgrade` ([R5] 5.3).
- [ ] No `THIRD_PARTY_NOTICES.md` change — a floor bump on an already-declared
      dependency is not a new dependency ([R5] 5.4).
- [ ] `test_e2e.sh` chrome outline block: capability probe (R6.4) + soft-skip
      when Playwright/Chromium absent (R6.2) + non-empty&nested assertion when
      available (R6.1 / 6.3); the block ends the suite **green** in every
      environment (skip or pass).
- [ ] With the chrome engine available, `html2pdf.py --engine chrome` on the
      plain-content fixture yields a non-empty nested outline ([R4] 4.2).
- [ ] Cross-skill `diff -q` silent (`_errors.py`, `preview.py`).
- [ ] Only `chrome_engine.py`, `requirements-chrome.txt`, `install.sh`,
      `tests/test_e2e.sh` are modified.

## Stub-First Gate (`tdd-stub-first §2`)

The chrome E2E block is the failing test written **first** (RED — chrome lacks
the outline); the `page.pdf(outline=True, tagged=True)` change is the logic
that turns it **GREEN**. Both halves land inside this one task so it ends
green. The 014-01 weasyprint checks are the regression floor and must stay
green throughout.

> **RED→GREEN observed (2026-05-22):** with the chrome block added but the fix
> not yet applied, `html2pdf.py --engine chrome` rendered successfully but the
> outline was empty (`_outline_probe.py` exit 3) — RED. The probe that
> uncovered the `tagged=True` requirement: `outline=True` alone → 0 bookmarks;
> `outline=True, tagged=True` → 4 bookmarks. After applying both flags → GREEN.

## Notes

- Playwright **is** importable in the dev `.venv`, its `Page.pdf` exposes both
  `outline` and `tagged` parameters, and the Chromium binary is installed
  (confirmed during 014-02) — so in this environment the chrome block runs the
  real RED→GREEN, not a soft-skip. On an environment without the chrome engine
  the block soft-skips (R6.2) — expected and correct.
- `tagged=True` **is** added (alongside `outline=True`) — it is **required**
  for the outline, per the spec amendment (TASK §1.1a / Q-3, user-confirmed
  2026-05-22). The chrome PDF is consequently a tagged PDF; this is an accepted
  side-effect, not a PDF/UA *conformance* claim (TASK §1.2 / §1.4(c)).
