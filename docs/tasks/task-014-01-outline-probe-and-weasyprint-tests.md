# Task 014-01 [STUB + TEST]: `_outline_probe.py` helper + weasyprint outline E2E

> **Predecessor:** none (bootstrap).
> **RTM:** **completes** [R1][R2][R3].
> **ARCH:** §2.1 F5/F6, §3.1 (Stub-First test-first adaptation), §4 (data model
> = test contract), §5.4 (`_outline_probe.py` interface), §5.5 (E2E blocks),
> §13 D5/D6.

## Use Case Connection

- **UC-1 main** — a reader navigates a generated PDF via its bookmark sidebar.
- **UC-1 / A1** — `--no-default-css` must not disable the outline.
- **UC-3** — the test scaffold the maintainer later runs.

## Task Goal

Deliver **Part A** of TASK 014 — *verify and lock* that weasyprint already
emits a PDF outline (TOC bookmarks) from `<h1>`–`<h6>` out of the box:

1. Create the test-only helper `tests/_outline_probe.py` (ARCH §5.4 / D5).
2. Add two outline regression blocks to `tests/test_e2e.sh` — one for
   `md2pdf.py`, one for `html2pdf.py` (weasyprint engine, incl. a
   `--no-default-css` variant).

**No production code is changed in this task.** The blocks pass on the
**unmodified** `md2pdf.py` / `html2pdf.py` — that Green run *is* the R1
verification (`tdd-stub-first §1.4`: the E2E asserts the already-correct
observed behaviour). The chrome path is **not** touched here — it is 014-02.

## Changes Description

### New Files

#### File: `skills/pdf/scripts/tests/_outline_probe.py`

A test-only helper, peer of `tests/_acroform_fixture.py` — **not** shipped as a
user-facing CLI, **not** wired into the `_errors.py` `--json-errors` envelope.

**Module docstring** — state: reads a PDF's document outline (bookmarks) via
`pypdf` and prints it depth-indented for shell assertions; **exit 3 is a
private test-harness sentinel for "empty outline", NOT an `_errors.py`-style
code** (ARCH §5.4).

**Behaviour:**
- `argv`: exactly one positional — the PDF path. Wrong arg count → print
  `usage: _outline_probe.py PDF` to stderr, exit 2 (the conventional argparse
  usage-error code).
- Open with `pypdf.PdfReader(path)`; read `reader.outline`.
- Walk the outline tree recursively. `pypdf` represents the tree as a nested
  list: a **list** element is a child group (depth + 1); any other element is
  a `Destination`-like object with a `.title` attribute (the bookmark label).
  Print one line per bookmark: `"  " * depth + title`.
- Exit `0` if at least one bookmark line was printed; exit `3` if the outline
  is empty (no bookmarks). Exit `2` on a usage error.

**Reference walker** (the shape verified during Analysis reconnaissance):

```python
def _walk(items, depth, out):
    for it in items:
        if isinstance(it, list):
            _walk(it, depth + 1, out)
        else:
            out.append("  " * depth + (it.title or ""))
```

`pypdf` is already a declared pdf-skill dependency (`requirements.txt`) — **no
new dependency** (TASK A-4).

### Changes in Existing Files

#### File: `skills/pdf/scripts/tests/test_e2e.sh`

Add a new section — **`pdf-7: PDF outline (TOC bookmarks)`** — containing the
two weasyprint blocks below. Place it **immediately before** the
`# --- q-2: visual regression` comment block (so the produced outline PDFs are
also available to a future visual check if desired). Use the established
`ok` / `nok` / `skip` helpers and the `$PY` / `$TMP` variables. Fixtures are
written inline via heredoc into `$TMP` (ARCH D6 — no committed fixture files).

**Block A — `md2pdf.py` outline (R2):**
- Write `$TMP/outline.md` with headings `# Chapter One` / `## Section 1.1` /
  `### Subsection 1.1.1` / `## Section 1.2` / `# Chapter Two` (each followed by
  a line of body text).
- Run `"$PY" md2pdf.py "$TMP/outline.md" "$TMP/outline_md.pdf" --no-mermaid`.
- `ol=$("$PY" tests/_outline_probe.py "$TMP/outline_md.pdf")` ; capture exit
  code.
- **`ok`** iff exit code `0` **and** the output contains all of:
  `^Chapter One$`, `^  Section 1.1$`, `^    Subsection 1.1.1$`,
  `^Chapter Two$` (the leading-space depth proves nesting; the titles prove
  labels) — else **`nok`** with the probe output in the message.

**Block B — `html2pdf.py` weasyprint-engine outline (R3):**
- Write `$TMP/outline.html` — a plain `<!DOCTYPE html>` document with
  `<h1>Alpha</h1>`, `<h2>Alpha One</h2>`, `<h2>Alpha Two</h2>`, `<h1>Beta</h1>`
  (each followed by a `<p>`). **Plain content, no `position:fixed` chrome** —
  this same fixture is reused by the 014-02 chrome block (ARCH D8).
- Run `"$PY" html2pdf.py "$TMP/outline.html" "$TMP/outline_html.pdf"` (default
  engine = weasyprint). Probe it: **`ok`** iff exit `0` and the output contains
  `^Alpha$`, `^  Alpha One$`, `^Beta$` — else **`nok`**.
- **`--no-default-css` variant (R3.2):** run
  `"$PY" html2pdf.py "$TMP/outline.html" "$TMP/outline_nocss.pdf" --no-default-css`;
  `"$PY" tests/_outline_probe.py "$TMP/outline_nocss.pdf"` must exit `0`
  (outline still present — it is owned by weasyprint's UA stylesheet, not the
  bundled `DEFAULT_CSS`). **`ok`** / **`nok`** accordingly.

Add a short comment block above the section explaining: weasyprint emits the
outline from `h1`–`h6` automatically (UA `bookmark-level`); these blocks lock
that so a future CSS edit cannot silently strip it (TASK §1.1, R1).

## Component Integration

`_outline_probe.py` is invoked by the `test_e2e.sh` blocks as
`"$PY" tests/_outline_probe.py <PDF>` (cwd is `$SKILL_DIR`, so the relative
`tests/…` path resolves). It is not imported by any production module.

## Test Cases

### E2E Tests (new — in `test_e2e.sh`)

1. **`md2pdf → non-empty nested PDF outline`** — Block A above (R2).
2. **`html2pdf (weasyprint) → non-empty nested PDF outline`** — Block B (R3).
3. **`html2pdf --no-default-css → outline still present`** — Block B variant
   (R3.2).

### Regression Tests

- `bash skills/pdf/scripts/tests/test_e2e.sh` — the pre-existing suite stays
  green; the three new checks pass on the **unmodified** production code.

## Acceptance Criteria

- [ ] `skills/pdf/scripts/tests/_outline_probe.py` created — walks
      `PdfReader.outline`, prints depth-indented titles, exit 0 / 3 / 2;
      docstring states exit-3 is a private test sentinel ([R1], ARCH §5.4).
- [ ] `test_e2e.sh` has a `pdf-7: PDF outline` section with the three new
      checks; all three **pass** on unmodified `md2pdf.py` / `html2pdf.py`
      ([R1] verified — weasyprint emits the outline out of the box; [R2], [R3]).
- [ ] The md2pdf check asserts hierarchy (depth-indent) and titles, not just
      non-emptiness ([R2] 2.2 / 2.3).
- [ ] The `--no-default-css` variant proves the outline survives suppression
      of the bundled CSS ([R3] 3.2).
- [ ] No production code (`md2pdf.py`, `html2pdf.py`, `html2pdf_lib/`) is
      modified in this task.
- [ ] `bash skills/pdf/scripts/tests/test_e2e.sh` overall green.
- [ ] Cross-skill `diff -q` silent (`_errors.py`, `preview.py`).
- [ ] Only `tests/_outline_probe.py` (new) and `tests/test_e2e.sh` (modified)
      are changed.

## Stub-First Gate (`tdd-stub-first §1`)

This is the **test-first Phase 1**. There is no new production module to stub;
the "stub" being verified is the **current production behaviour** of the
weasyprint render paths. The three E2E checks assert the already-correct
observed outline — they go Green on the unmodified code, which *is* the R1
verification. The Red→Green target (the chrome path) is created and closed in
014-02.

## Notes

- The `pypdf` outline walker shape (nested-list = child group) was confirmed
  empirically during the Analysis-phase reconnaissance against a real
  `md2pdf.py` render — the nested tree printed correctly.
- Keep `_outline_probe.py` tiny and dependency-free beyond `pypdf` (stdlib +
  `pypdf` only) — it is a test helper, not a feature.
