# ARCHITECTURE: TASK 014 (backlog row `pdf-7`) — PDF outline (TOC bookmarks)

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v2 — **amended 2026-05-22** during development: Chromium
> emits the PDF outline only with `page.pdf(tagged=True)` set alongside
> `outline=True` (empirically verified). §1, §5.2, §6, §8, §10(c), §12 Q-3, §13
> D2 revised to add `tagged=True` (user-confirmed scope amendment). See TASK
> 014 §1.1a.
> **TASK:** [TASK.md](TASK.md) (TASK 014, slug `pdf-outline-bookmarks`, backlog
> row `pdf-7`).
> **Living document:** updated in place. The prior content (TASK 013 / `pdf-12`
> `pdf_extract.py`) was completed and merged; its design is preserved in the
> archived task/plan pair `docs/tasks/task-013-pdf-to-markdown-master.md` +
> `docs/plans/plan-013-pdf-to-markdown.md` and in git history. Per the
> living-document rule this file is **not** per-task snapshotted (it is 603 →
> well under the 1500-line Index-Mode threshold).
> **Template:** `architecture-format-core` (Core) — this is a small,
> well-bounded modification of one existing module, not a new system; the
> Extended template's TIER-2 triggers (new system / >3-component refactor) do
> not apply.

---

## 1. Task Description

A PDF **outline** (a.k.a. *bookmarks* / *document outline*) is the navigable
heading tree a PDF viewer shows in its sidebar. Backlog row `pdf-7` asks a
verification question: does the pdf skill already emit an outline from
`<h1>`–`<h6>`, or is a CSS flag / code change required?

**Verification outcome (Analysis-phase reconnaissance, 2026-05-22):**

| Render path | Outline today? | Mechanism |
|-------------|----------------|-----------|
| `md2pdf.py` (weasyprint) | ✅ emitted | weasyprint UA stylesheet `bookmark-level`/`bookmark-label` on `h1`–`h6` |
| `html2pdf.py` default engine (weasyprint) | ✅ emitted | same |
| `html2pdf.py --engine chrome` (Playwright) | ❌ absent | `render_chrome()` `page.pdf()` omits `outline=True` **and the `tagged=True` Chromium requires alongside it** |

The two weasyprint paths produce a correct nested outline **out of the box** —
no CSS flag needed, and the bundled `DEFAULT_CSS` does not override the UA
`bookmark-*` properties. The single gap is the opt-in chrome engine (pdf-11).

> **Development finding (2026-05-22, amended into the design).** A controlled
> Playwright probe during Task 014-02 established that Chromium's
> `page.pdf(outline=True)` emits an outline **only when `tagged=True` is also
> passed** (`outline=True` alone → 0 bookmarks; `outline=True, tagged=True` →
> the correct nested outline). Chromium builds the outline from the tagged-PDF
> structure tree. The chrome engine therefore passes **both** flags, and a
> chrome-rendered PDF is now a *tagged PDF* — an accepted, necessary
> side-effect (user-confirmed scope amendment; TASK 014 §1.1a / Q-3). The
> weasyprint paths are unaffected (their `bookmark-level` outline needs no
> tagging).

This task therefore has two architecturally distinct halves:

- **Part A — verify & lock (no behaviour change):** add regression tests that
  pin the weasyprint outline so a future CSS edit cannot silently strip it.
- **Part B — chrome parity (two-keyword behaviour change):** add `outline=True`
  **and `tagged=True`** to the chrome engine's `page.pdf()` call; raise the
  Playwright floor to the release that introduced those options; make the
  installer upgrade an already-present too-old Playwright.

Full requirement set: TASK 014 §2 (R1–R9, 3 Epics). Non-goals (no PDF/UA
*conformance* claim, no `--no-outline` flag, no custom labelling): TASK §1.2.

---

## 2. Functional Architecture

### 2.1. Functional Components

| # | Component | Responsibility | Change |
|---|-----------|----------------|--------|
| F1 | weasyprint outline (md2pdf) | `md2pdf.py` → weasyprint → PDF outline from `h1`–`h6` | **none** (verified path) |
| F2 | weasyprint outline (html2pdf) | `html2pdf_lib/render.py` weasyprint branch → PDF outline | **none** (verified path) |
| F3 | chrome outline | `html2pdf_lib/chrome_engine.py` `render_chrome()` → `page.pdf(outline=True)` | **modified** (Part B) |
| F4 | Playwright floor + installer | `requirements-chrome.txt` floor `>=1.42`; `install.sh --with-chrome` installs with `--upgrade` | **modified** (Part B) |
| F5 | outline regression tests | render a multi-heading fixture per path, read the PDF outline back, assert non-empty + nested + titled | **new** |
| F6 | outline probe helper | `tests/_outline_probe.py` — read a PDF's outline via `pypdf`, emit a deterministic depth-indented dump for shell assertions | **new** |
| F7 | documentation | `SKILL.md` §2; `references/html-conversion.md` note; backlog `pdf-7` row | **modified** |

### 2.2. Functional Components Diagram

```
            ┌──────────────── verify & lock (Part A) ────────────────┐
 md2pdf.py ─┤                                                        │
            │  weasyprint  ──► PDF (outline already present) ──┐      │
html2pdf.py ┤  (UA bookmark-level)                             │      │
 (engine=   │                                                  ▼      │
  weasyprint)                                          F5 regression  │
            └──────────────────────────────────────────► tests ◄──────┘
                                                            ▲
            ┌──────────────── chrome parity (Part B) ────────┘
html2pdf.py ┤  chrome_engine.render_chrome()
 (engine=   │     page.pdf(outline=True)  ──► PDF (outline now present)
  chrome)   │  requirements-chrome.txt: playwright>=1.42
            │  install.sh --with-chrome: pip install --upgrade
            └─────────────────────────────────────────────────────────

 F6 _outline_probe.py: PDF ──pypdf.PdfReader.outline──► depth-indented dump
                              consumed by F5 test blocks in test_e2e.sh
```

---

## 3. System Architecture

### 3.1. Architectural Style

Single-skill, script-level modification. No new module, no package, no new
process boundary. The pdf skill keeps its existing shape: standalone CLI
scripts (`md2pdf.py`, `html2pdf.py`) + the `html2pdf_lib/` package + a
bash-driven E2E harness (`tests/test_e2e.sh`) with inline `python -c`
assertions.

**Stub-First adaptation.** This task has no large new surface to stub. The
Stub-First discipline maps onto the **test-first** ordering:

1. F6 (`_outline_probe.py`) + F5 (test blocks) are written **first**. Against
   the weasyprint paths they pass immediately — that *is* the Part-A
   verification (Green confirms F1/F2 already work).
2. The chrome test block is **RED** at this point (chrome omits `outline=True`).
3. F3 (the `page.pdf(outline=True)` change) turns the chrome block **GREEN**.

So the natural Red→Green gate is: chrome outline test RED → F3 → GREEN.

### 3.2. System Components

| Component | Path | Kind | Notes |
|-----------|------|------|-------|
| md2pdf converter | `skills/pdf/scripts/md2pdf.py` | unchanged | weasyprint render; outline already emitted |
| html2pdf render orchestration | `skills/pdf/scripts/html2pdf_lib/render.py` | unchanged | weasyprint branch already emits outline |
| chrome engine | `skills/pdf/scripts/html2pdf_lib/chrome_engine.py` | **modified** | `render_chrome()` `page.pdf(...)` gains `outline=True` |
| chrome dependency pin | `skills/pdf/scripts/requirements-chrome.txt` | **modified** | floor `playwright>=1.40` → `>=1.42` (+ rationale comment) |
| installer | `skills/pdf/scripts/install.sh` | **modified** | `--with-chrome` block installs `requirements-chrome.txt` with `--upgrade` |
| outline probe helper | `skills/pdf/scripts/tests/_outline_probe.py` | **new** | test-only; reads `PdfReader.outline`, emits depth-indented dump |
| E2E harness | `skills/pdf/scripts/tests/test_e2e.sh` | **modified** | new outline test blocks (md2pdf / html2pdf-weasyprint / html2pdf-chrome) |
| skill manifest | `skills/pdf/SKILL.md` | **modified** | §2 Capabilities; §10/§12 reviewed |
| reference doc | `skills/pdf/references/html-conversion.md` | **modified** | outline note (engine-agnostic, automatic from headings) |
| backlog | `docs/office-skills-backlog.md` | **modified** | `pdf-7` row → ✅ DONE; stale note corrected |

### 3.3. Components Diagram

```
skills/pdf/scripts/
├── md2pdf.py                      ← F1  (unchanged — verified)
├── html2pdf.py                    ←     (unchanged)
├── html2pdf_lib/
│   ├── render.py                  ← F2  (unchanged — verified, weasyprint)
│   └── chrome_engine.py           ← F3  (MODIFIED — page.pdf(outline=True))
├── requirements-chrome.txt        ← F4  (MODIFIED — playwright>=1.42)
├── install.sh                     ← F4  (MODIFIED — pip install --upgrade)
└── tests/
    ├── _outline_probe.py          ← F6  (NEW — outline dump helper)
    └── test_e2e.sh                ← F5  (MODIFIED — 3 outline test blocks)

skills/pdf/SKILL.md                ← F7  (MODIFIED — §2)
skills/pdf/references/
└── html-conversion.md             ← F7  (MODIFIED — outline note)
docs/office-skills-backlog.md      ← F7  (MODIFIED — pdf-7 row)
```

---

## 4. Data Model (Conceptual)

There is no persisted data model. The single domain entity is the **PDF
outline** — produced *by the render engine*, not constructed by skill code.
It is modelled here only to fix the **contract the F5 regression tests assert
against**.

### 4.1. Entity: `PdfOutline`

The document outline embedded in a generated PDF.

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | ordered list of `OutlineItem` | top-level bookmarks, in document order |
| `is_empty` | bool (derived) | `len(items) == 0` — true for a headingless source (valid; not an error — TASK UC-1/A2) |

### 4.2. Entity: `OutlineItem`

One bookmark node.

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | str | bookmark label = the heading's text content (`<h1>`–`<h6>` inner text) |
| `depth` | int ≥ 0 | nesting depth in the outline tree (0 = top level) |
| `children` | ordered list of `OutlineItem` | nested bookmarks (a deeper heading following a shallower one) |
| `target` | page reference | the page the bookmark jumps to |

**Read interface (tests only).** `pypdf.PdfReader.outline` returns this tree as
nested Python lists of `Destination` objects (`.title` = label). `pypdf` is
already a declared pdf-skill dependency (`requirements.txt`, used by
`pdf_merge.py`) — **no new test dependency** (TASK A-4).

### 4.3. Derived rule: outline well-formedness (test contract)

For a source document whose headings are `h1 → h2 → h3 → h2 → h1` the produced
`PdfOutline` MUST satisfy:

```
is_empty            == False
len(items)          == 2          # two top-level h1
items[0].title      == "<text of first h1>"
items[0].children   non-empty     # the h2/h3 nest under the first h1
depth strictly increases by 1 for each heading-level increase
```

This is the **engine-agnostic** assertion granularity. Per TASK §1.4(d), the
tests assert *"a non-empty, hierarchically nested outline whose titles match
the headings"* — **not** byte-identical trees across weasyprint vs. Chromium
(the two engines' grouping algorithms may differ in edge cases).

---

## 5. Interfaces

### 5.1. Render-engine outline interfaces (existing, external)

| Engine | Interface | Status |
|--------|-----------|--------|
| weasyprint | UA stylesheet sets `bookmark-level: N` + `bookmark-label: content(...)` on `h1`–`h6`; `HTML.write_pdf()` emits the outline. No skill code calls it — it is automatic. | already active |
| Chromium (Playwright) | `page.pdf(outline=True)` → Chromium derives the outline from the document heading structure and embeds it. | **activated by this task** |

### 5.2. `render_chrome()` change (F3)

`skills/pdf/scripts/html2pdf_lib/chrome_engine.py`, inside `render_chrome()`,
the existing `page.pdf(...)` call gains one keyword argument:

```python
page.pdf(
    path=str(output_path),
    format=fmt,
    print_background=print_background,
    scale=pdf_scale,
    margin={"top": "1cm", "right": "1cm",
            "bottom": "1cm", "left": "1cm"},
    outline=True,                       # ← ADDED (TASK R4.1)
    tagged=True,                        # ← ADDED — REQUIRED for the outline:
                                        #   Chromium builds the outline from
                                        #   the tagged structure tree; outline=
                                        #   True alone emits 0 bookmarks.
)
```

- **Appended last, existing five arguments unchanged in order** — the diff adds
  two lines (TASK R4.4).
- **`tagged=True` is mandatory, not optional** — empirically, `outline=True`
  alone produces an empty outline (TASK §1.1a, A-3). A chrome-rendered PDF
  consequently becomes a tagged PDF — an accepted side-effect (TASK §1.2).
- **No new `render_chrome()` parameter.** Both flags are hardcoded at the call
  site. There is no `--no-outline` CLI flag (TASK Q-2 resolved: no opt-out), so
  no caller needs to vary them — parameters would be unused surface (YAGNI).
  Decision D2.

### 5.3. Dependency + installer interface (F4)

`requirements-chrome.txt`:

```
playwright>=1.42,<2.0    # 1.42 added page.pdf(outline=True); see pdf-7 / TASK 014
```

`install.sh` `--with-chrome` block: the `pip install ... -r
requirements-chrome.txt` invocation gains `--upgrade` so a re-run upgrades an
already-present too-old Playwright (1.40/1.41 from a pdf-11-era install) —
plain `pip install -r` does not upgrade an already-satisfied package
(TASK R5.3 / M-1).

### 5.4. Test helper interface (F6) — `tests/_outline_probe.py`

A test-only helper (peer of the existing `tests/_acroform_fixture.py`).

```
python3 tests/_outline_probe.py <PDF>
  → stdout: one line per bookmark, depth-indented:
        "Chapter One"
        "  Section 1.1"
        "    Subsection 1.1.1"
        "  Section 1.2"
        "Chapter Two"
  → exit 0 if the PDF has a non-empty outline; exit 3 if the outline is empty.
```

Exit 3 is a **private test-harness sentinel**, not an `_errors.py`-style code —
`_outline_probe.py` is a test-only helper and deliberately stays outside the
`--json-errors` envelope convention; its docstring states this so a future
reader does not assume alignment.

`test_e2e.sh` blocks render a fixture, call `_outline_probe.py`, and assert
on its exit code (non-empty) + `grep` its output for expected titles and the
indentation that proves nesting. Keeping the `pypdf` traversal in one helper
avoids brittle multi-line `python -c` strings in the bash harness.

### 5.5. E2E test blocks (F5) — added to `test_e2e.sh`

| Block | Engine / flags | Asserts | Skip rule |
|-------|----------------|---------|-----------|
| `md2pdf outline` | `md2pdf.py` (weasyprint) | non-empty, nested, titled (R2) | none — always runs |
| `html2pdf outline` | `html2pdf.py` default + a second run with `--no-default-css` | non-empty, nested; outline survives `--no-default-css` (R3) | none — always runs |
| `html2pdf chrome outline` | `html2pdf.py --engine chrome` | `outline` kwarg present in `Page.pdf` signature (R6.4); non-empty + nested (R6.1/6.3) | **soft-skip** when Playwright/Chromium absent — mirrors the `mermaid_renders` pattern (R6.2) |

Fixtures are written inline (heredoc) into the harness `$TMP` dir, exactly as
the existing mermaid block writes `with_mermaid.md` — no committed fixture
files, no committed `.pdf` (the skill `.gitignore` ignores `*.pdf` outside
`examples/`). The chrome fixture is **plain content with no fixed-position
chrome** so the assertion is not coupled to `_DOM_NORMALIZE_SCRIPT` hiding a
heading inside `position:fixed` chrome (TASK R4.3 / §1.4(b)).

---

## 6. Technology Stack

| Concern | Choice | Justification |
|---------|--------|---------------|
| weasyprint outline | weasyprint UA stylesheet (`bookmark-*`) | already in use; produces the outline automatically — nothing to add |
| chrome outline | Playwright `page.pdf(outline=True, tagged=True)` | the engine's native options; **both** required — Chromium derives the outline from the tagged structure tree (`outline` alone → 0 bookmarks); introduced in Playwright 1.42 |
| outline read-back (tests) | `pypdf` `PdfReader.outline` | already a declared dependency (`requirements.txt`); no new test dependency |
| test harness | bash `test_e2e.sh` + inline assertions + `_outline_probe.py` | matches the established pdf-skill E2E style |

**No new runtime dependency.** `requirements-chrome.txt` receives a version
**floor bump** on an already-declared package — not a new dependency —
therefore **no `THIRD_PARTY_NOTICES.md` change** is required by this task
(TASK R5.4 / C-4).

---

## 7. Security

No new attack surface.

- `outline=True` is a static boolean literal at the `page.pdf()` call site — no
  file content, user input, or path is interpolated into it.
- The chrome engine's existing offline guarantees are unchanged: remote-route
  blocking (`_block_remote_routes`), `<base>` stripping, `<script>` stripping.
  Outline generation runs on the already-loaded local DOM.
- weasyprint paths are untouched — their existing `_offline_url_fetcher` and
  SIGALRM watchdog behaviour is preserved bit-for-bit.
- AuthN/AuthZ: not applicable — these are local file-conversion CLIs with no
  account model, consistent with every other pdf-skill script.
- `_outline_probe.py` is a test-only helper; it opens a PDF the test itself
  just produced in a private `$TMP` dir.

---

## 8. Scalability and Performance

- weasyprint paths: **zero** performance change (no code change).
- chrome path: `outline=True` + `tagged=True` add negligible cost — Chromium
  builds the outline and the structure tree from the layout tree it already
  computes. No extra DOM pass, no extra navigation. A tagged PDF is marginally
  larger (structure metadata) but not materially so for the documents the
  chrome engine targets.
- Test cost: three small renders (a few KB of HTML/MD each) — sub-second on
  weasyprint; the chrome block adds one ~1–3 s Chromium render *only* when the
  opt-in engine is installed, and soft-skips otherwise.

---

## 9. Cross-Skill Replication Boundary (CLAUDE.md §2)

**This task replicates nowhere.** Every file it edits or creates is pdf-only:

| File | Replication class |
|------|-------------------|
| `html2pdf_lib/chrome_engine.py` | pdf-only package module (no docx/xlsx/pptx peer) |
| `requirements-chrome.txt` | pdf-only (chrome engine; not in any replication set) |
| `install.sh` | pdf-only (explicitly out-of-scope per CLAUDE.md §2) |
| `tests/_outline_probe.py`, `tests/test_e2e.sh` | pdf-only test surface |
| `SKILL.md`, `references/html-conversion.md` | pdf-only docs |
| `docs/office-skills-backlog.md` | repo doc |

The replicated files — `office/`, `_soffice.py`, `_errors.py`, `preview.py`,
`office_passwd.py` — are **not touched**. The CLAUDE.md §2 protocol is **not
triggered**. Post-task invariant (TASK R9.3):

```bash
diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py   # silent
diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py   # silent
```

(pdf has no `office/` directory, so the `office/` `diff -qr` is N/A.)

---

## 10. Honest Scope (v1)

Each item is documented in the named file by the named component.

- **(a)** Outline derives **only** from real `<h1>`–`<h6>` tags; styled
  `<p>`/`<div>` "visual headings" do not appear → `SKILL.md` §2 + reference.
- **(b)** `--reader-mode`, the preprocessing pipeline, and (chrome)
  `_DOM_NORMALIZE_SCRIPT` may remove/hide chrome headings → outline reflects
  what survives **visible**; this is correct → reference note.
- **(c)** The chrome engine emits a **tagged PDF** (Chromium's mechanism for
  the outline — `tagged=True` is required). This is an accepted side-effect,
  **not** a PDF/UA conformance claim; tagging quality is not validated, and the
  weasyprint paths stay untagged → `SKILL.md` §2 + reference.
- **(d)** Cross-engine outline trees are not byte-identical; tests assert
  *non-empty + nested + titled*, not tree equality → §4.3 + test comments.
- **(e)** The chrome engine stays opt-in; its outline test soft-skips when
  Playwright/Chromium is absent → `test_e2e.sh` block comment.
- **(f)** A heading inside DOM-normalised hidden chrome (`display:none`d
  `position:fixed` element) is intentionally absent from the chrome outline →
  the chrome test fixture deliberately uses plain content (§5.5).
- **(g)** Open verification point A-6: `emulate_media("screen")` is assumed not
  to alter which headings reach the chrome outline; the chrome test records the
  observation → test comment + TASK A-6.

---

## 11. Atomic-Chain Skeleton (Planner handoff)

Suggested decomposition (the Planner finalises). All beads are within a 2–4 h
budget; the chain is short because the task is small.

| Bead | Type | Scope | RTM | Dep |
|------|------|-------|-----|-----|
| **014-01** | VERIFY + TEST | `tests/_outline_probe.py` (F6) + `test_e2e.sh` md2pdf & html2pdf-weasyprint outline blocks (F5) — Part A. Weasyprint blocks pass on first run = the verification (Green). | R1, R2, R3 | none |
| **014-02** | LOGIC | `page.pdf(outline=True)` in `chrome_engine.py` (F3); `requirements-chrome.txt` floor `>=1.42` (F4); `install.sh --upgrade` (F4); `test_e2e.sh` chrome outline block incl. R6.4 capability probe + soft-skip (F5). The R6.4 `inspect.signature` probe runs **before** the render so an under-floor Playwright fails loudly on the cheap check rather than mid-render. Chrome block RED→GREEN. | R4, R5, R6 | 014-01 |
| **014-03** | DOC + INTEGRATION | `SKILL.md` §2 (+ §10/§12 review); `references/html-conversion.md` note; `docs/office-skills-backlog.md` `pdf-7` row; `validate_skill.py skills/pdf` exit 0; full `test_e2e.sh` green; cross-skill `diff -q` silent. | R7, R8, R9 | 014-02 |

**Execution order:** `014-01 → 014-02 → 014-03` (strict linear; 014-03 needs
both prior beads' artifacts to exist before docs link them and validation runs).

---

## 12. Open Questions

All resolved upstream in TASK 014 §6 (Q-1..Q-4); none block design.

- **Q-1 (resolved):** chrome-engine fix in scope — user-confirmed (TASK A-2).
- **Q-2 (resolved):** no `--no-outline` flag → `outline=True` hardcoded, no
  `render_chrome()` parameter (D2).
- **Q-3 (resolved — amended 2026-05-22):** `tagged=True` **is** set on the
  chrome engine — it is *required* for the outline (Chromium couples them);
  the chrome PDF becomes a tagged PDF, an accepted side-effect. No PDF/UA
  *conformance* is claimed (Honest Scope (c)). User-confirmed amendment.
- **Q-4 (resolved):** Playwright **floor bump** to 1.42, not a runtime probe;
  the F5 chrome block additionally probes the `outline` kwarg's presence
  (R6.4) as a defence-in-depth diagnostic.
- **A-6 (open verification point, non-blocking):** `emulate_media("screen")`
  vs. chrome outline — confirmed empirically by the 014-02 chrome test and
  recorded; no design decision pends on it.

---

## 13. Decision-Record Summary

| ID | Decision | Rationale |
|----|----------|-----------|
| **D1** | weasyprint paths get **no code change** — verify-and-lock only | They already emit the outline (reconnaissance); the risk is silent *regression*, which F5 tests pin |
| **D2** | `outline=True` **and `tagged=True`** hardcoded at the `page.pdf()` call site — no new `render_chrome()` parameter | `tagged=True` is required for the outline (§1, TASK §1.1a — Chromium couples them); no `--no-outline` CLI flag (Q-2), so a parameter no caller varies is unused surface (YAGNI) |
| **D3** | Playwright floor `>=1.42` (not a runtime version probe) | 1.42 introduced `page.pdf(outline=True)`; per project memory feedback "prefer dependency upgrades on a version mismatch" |
| **D4** | `install.sh --with-chrome` installs `requirements-chrome.txt` with `--upgrade` | A floor bump alone does not upgrade an already-satisfied package; closes the pdf-11-era-install gap (M-1) |
| **D5** | New test-only helper `tests/_outline_probe.py` | Keeps the `pypdf` outline traversal out of brittle multi-line `python -c` strings; mirrors `_acroform_fixture.py` |
| **D6** | Fixtures written inline (heredoc) into `$TMP`; no committed fixture/`.pdf` files | Matches the existing mermaid-block convention; the skill `.gitignore` ignores `*.pdf` outside `examples/` |
| **D7** | Chrome outline test soft-skips when Playwright/Chromium absent | The chrome engine is opt-in; a missing optional dependency is a coverage gap, not a suite failure — mirrors the `mermaid_renders` pattern |
| **D8** | Chrome test fixture is plain content (no `position:fixed` chrome) | Decouples the assertion from `_DOM_NORMALIZE_SCRIPT` hiding headings inside hidden chrome (Honest Scope (b)/(f)) |
