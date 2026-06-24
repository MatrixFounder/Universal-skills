# Agent Rules — Universal-Skills

This file is the authoritative behavioural contract for agents
(Claude Code, Anthropic Agent SDK, etc.) working in this repository.
It is kept **in lockstep** with [`GEMINI.md`](GEMINI.md) — any rule
added here is added there too. Public-facing project documentation
is in [`README.md`](README.md); contributor protocol is in
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

---

## 1. Local-development rules

### Package management

- **Python**: Always use `.venv/` virtual environment (per skill).
  Never `pip install` globally.
  ```bash
  cd skills/<skill>/scripts
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **Node.js**: Always use local `node_modules/` (per skill).
  Never `npm install -g`.
  ```bash
  cd skills/<skill>/scripts && npm install
  ```
- **Bootstrap shortcut** for skills that have one:
  `bash skills/<skill>/scripts/install.sh`. The script creates
  `.venv/` + `node_modules/` and prints install hints for missing
  system tools (LibreOffice, Poppler, pango, …) — it does NOT install
  system tools itself; that's the user's choice.

### Testing

- Tests run through the per-skill venv:
  ```bash
  cd skills/<skill>/scripts
  ./.venv/bin/python -m unittest discover -s <module>/tests
  ```
- Skill structural validation (Gold Standard / CSO):
  ```bash
  python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/<skill>
  ```
  Must exit 0 before declaring any change complete.
- Always run end-to-end on a real fixture from `examples/` or
  `tmp/test-data/`. Don't ship code that hasn't actually run on data.

---

## 2. Office-skills modification protocol — STRICT

`docx`, `xlsx`, and `pptx` share an identical OOXML helper module
(`scripts/office/`) and LibreOffice wrapper (`scripts/_soffice.py`).
The **`docx` skill is the MASTER**. `xlsx` and `pptx` carry
**byte-identical copies** of those files. There is no symlink, no
submodule, no shared import — physical duplication is intentional
(per project plan §"Независимость скиллов": each skill must be
installable and runnable in isolation, including as a packaged
`.skill` archive).

### Rule

When you change ANYTHING under
`skills/docx/scripts/office/` or `skills/docx/scripts/_soffice.py`:

1. **Edit only the docx copy.** Never edit the xlsx or pptx copies.
2. **Run the docx tests** (`office/tests/`) to confirm the change
   works.
3. **Replicate** to xlsx and pptx in the SAME commit:
   ```bash
   rm -rf skills/xlsx/scripts/office skills/pptx/scripts/office
   cp -R skills/docx/scripts/office skills/xlsx/scripts/office
   cp -R skills/docx/scripts/office skills/pptx/scripts/office
   cp skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
   cp skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
   find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   ```
4. **Verify byte-identity** before committing:
   ```bash
   diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
   diff -qr skills/docx/scripts/office skills/pptx/scripts/office
   diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
   diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
   ```
   All four must produce no output.
5. **Re-run skill-validator** on all four office skills:
   ```bash
   for s in docx xlsx pptx pdf; do
       python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s
   done
   ```

### What counts as an office/ change

In scope (must replicate): everything under
`skills/docx/scripts/office/` (unpack, pack, validate, validators/,
helpers/, shim/, tests/, `_encryption.py`, `_macros.py`,
schemas/README.md, schemas/fetch.sh, schemas/w3c/) plus
`skills/docx/scripts/_soffice.py`.

Out of scope (docx-only, no replication): `skills/docx/scripts/docx_*.py`,
`skills/docx/SKILL.md`, `skills/docx/references/`,
`skills/docx/examples/`, `skills/docx/scripts/package.json`,
`skills/docx/scripts/requirements.txt`, `skills/docx/scripts/install.sh`.

### Cross-skill scripts (4-skill replication, includes pdf)

Two helper files live at `skills/<skill>/scripts/` (sibling to
`_soffice.py`, NOT inside `office/`) and are byte-identical across
**all four** office skills (`docx`, `xlsx`, `pptx`, `pdf`):

- `_errors.py` — `--json-errors` envelope helper used by every Python
  CLI for uniform machine-readable failure output.
- `preview.py` — universal `INPUT → PNG-grid` renderer; routes `.pdf`
  through Poppler directly and `.docx`/`.xlsx`/`.pptx` (incl. `.docm`/
  `.xlsm`/`.pptm`) through LibreOffice → Poppler.

When you change either of these:

1. Edit only the docx copy.
2. Replicate to xlsx, pptx, AND pdf (note: pdf is included even though
   it has no `office/`):
   ```bash
   for s in xlsx pptx pdf; do
       cp skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
       cp skills/docx/scripts/preview.py skills/$s/scripts/preview.py
   done
   ```
3. Verify byte-identity:
   ```bash
   for s in xlsx pptx pdf; do
       diff -q skills/docx/scripts/_errors.py skills/$s/scripts/_errors.py
       diff -q skills/docx/scripts/preview.py  skills/$s/scripts/preview.py
   done
   ```
4. Re-run all four E2E suites + `validate_skill.py` on all four skills.

### Cross-skill scripts (3-skill replication, OOXML only)

One helper file is byte-identical across the **three OOXML** office
skills (`docx`, `xlsx`, `pptx`) but NOT pdf, because it operates on
the OOXML container format directly:

- `office_passwd.py` — set/remove password protection on
  `.docx`/`.xlsx`/`.pptx` via `msoffcrypto-tool` (MS-OFB Agile,
  Office 2010+). Pdf has its own encryption mechanism (pypdf
  `PdfWriter.encrypt`) and does not use this script.

When you change `office_passwd.py`:

1. Edit only the docx copy.
2. Replicate to xlsx and pptx:
   ```bash
   cp skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
   cp skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
   ```
3. Verify byte-identity:
   ```bash
   diff -q skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
   diff -q skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
   ```
4. Re-run E2E for the three OOXML skills + `validate_skill.py`.

The `msoffcrypto-tool>=5.4.0` dependency must stay in
`requirements.txt` of all three OOXML skills; it is NOT a pdf
dependency.

### Skill `html` (formerly `html2md`) — TWO-master replication

The standalone skill **`html`** (**Proprietary, All Rights Reserved** —
it embeds byte-identical copies of proprietary docx/pdf code, so it joins the
office-proprietary set per §3 License hygiene, NOT Apache-2.0; Web/HTML
acquisition + HTML→Markdown for Obsidian clipping + agent workflows; see
[`docs/office-skills-backlog.md` §2 «html»](docs/office-skills-backlog.md)
and TASK 022 / TASK 027) reuses hardened code from **both** docx and pdf. Because
the HTML-cleaning code physically originates in pdf and the conversion core in
docx, `html` is the **one documented exception** to "docx is always
master" — it has **two masters**. Follow this topology exactly and do NOT fork.

**Naming caveat (load-bearing — do not "fix"):** the user-facing launcher is the
**extensionless** file `skills/html/scripts/html` (NOT `html.py`), and the internal
Python package is still `skills/html/scripts/html2md/`. A `html.py` file or a `html/`
package on `scripts/` (which sits at `sys.path[0]`) would shadow the stdlib `html`
module that `acquire.py` and the pdf-mastered `web_clean/preprocess.py` import
(`html.escape` / `html.unescape`). Keep the launcher extensionless and the package
named `html2md`. `skills/html/scripts/html2md.py` is the combined end-to-end command
(fetch → md → delete the intermediate HTML). Config env vars are `HTML_*` (a hard
rename from `HTML2MD_*`, no aliases).

Replication units (each byte-identical, `diff -q` gated):

1. **HTML→MD core — MASTER = docx.** `html2md_core.js` is lifted verbatim
   from `skills/docx/scripts/docx2md.js` (`buildTurndown` +
   `expandTableToGrid`, lines ~258-336). `docx2md.js` imports it; `html`
   carries a byte-identical copy — **KEEP the `html2md_core.js` filename** (it
   matches the docx master; `diff -q` is content-based). Edit only the docx copy.
2. **HTML-cleaning cluster — MASTER = pdf** (the exception). The five
   pure-regex/stdlib modules under `skills/pdf/scripts/html2pdf_lib/` —
   `archives.py`, `reader_mode.py`, `preprocess.py`, `dom_utils.py`,
   `normalize_css.py` — replicate to `skills/html/scripts/web_clean/`.
   Edit only the pdf copy. **NEVER replicate `render.py`,
   `chrome_engine.py`, or the package `__init__.py`** — they are the only
   weasyprint/playwright carriers (weasyprint is a module-level import in
   `render.py` alone). `html` ships its OWN thin `web_clean/__init__.py`
   (html-authored, NOT under the gate) re-exporting only clean symbols.
3. **Shared helpers — MASTER = docx, 4→5-skill loop.** `_errors.py` and
   `_venv_bootstrap.py` include `html` in their replication loop.
   `preview.py` / `_soffice.py` are NOT needed (`html` emits Markdown,
   not renderable office docs).

Guards (non-negotiable):

- An import smoke-test MUST assert `weasyprint` and `playwright` stay out
  of `sys.modules` after importing `web_clean` (the `__init__.py` trap).
- Carry the pdf cleaning modules **whole** — do NOT trim weasyprint-
  specific functions. They are inert regex with no heavy imports; trimming
  makes `diff -q` impossible and silently forks on the next pdf change.
- The CI `diff -q` gate lives in `skills/html/scripts/tests/test_e2e.sh` (run by
  the office-skills matrix) covering both the docx→core and pdf→cluster replicas;
  it also fails on a zero-test `discover` run.
- **Licensing:** `html` is **Proprietary** (derived work embedding
  proprietary docx/pdf source) — its per-skill `LICENSE`/`NOTICE`
  mirror the office four, `THIRD_PARTY_NOTICES.md` re-points to it, and it is never
  published under Apache-2.0 (see §3 License hygiene).

### Anti-patterns — DO NOT

- ❌ Edit `skills/xlsx/scripts/office/foo.py` directly.
- ❌ Replicate from xlsx → docx (always docx is source of truth).
- ❌ Symlink `skills/xlsx/scripts/office -> ../../docx/scripts/office`.
- ❌ Forget to clean `__pycache__` before `diff -qr` (false positives).
- ❌ Replicate without running tests + validator afterwards.
- ❌ Re-point the `html` skill's `web_clean/` cluster to docx-master —
  its master is **pdf** (documented exception above). Conversely, do NOT
  copy `render.py`/`chrome_engine.py`/`__init__.py` into `html`.

Full protocol with rationale:
[`docs/CONTRIBUTING.md` §3](docs/CONTRIBUTING.md#3-office-skills-modification-protocol-strict).

---

## 3. Behavioural conventions

### Spec-first when explicitly requested

If the user asks for a *specification* / *plan* / *spec* (and not
code), produce the planning artifact (e.g. `implementation_plan.md`
or write to the plan file in `~/.claude/plans/` if in plan-mode) and
**STOP**. Do not start writing code until the user explicitly says
"implement".

### Tests first when the change is non-trivial

For changes >5 lines of business logic, write or update tests in
the relevant `tests/` directory before declaring the work done. Tests
are the contract; passing tests is the verification that the change
behaves as advertised.

### Honest scope, not aspirational

If a feature has a known limitation (e.g. the AF_UNIX shim does NOT
provide cross-process IPC — see
[`skills/docx/scripts/office/shim/lo_socket_shim.c`](skills/docx/scripts/office/shim/lo_socket_shim.c)
file-level comment), document the limitation in the file's docstring
AND lock it in with a regression test (e.g.
`TestShimCrossProcessIPCLimitation`). Do not let documentation
overstate what the code does.

### License hygiene

This repository uses a **split licensing model** (effective
2026-04-25):

- **Repository root** and all skills **except** the four office
  skills are **Apache-2.0** ([`LICENSE`](LICENSE)).
- The **four office skills** — `skills/docx/`, `skills/xlsx/`,
  `skills/pptx/`, `skills/pdf/` — are **Proprietary, All Rights
  Reserved**, governed by their per-skill `LICENSE` and `NOTICE`
  files (e.g. [`skills/docx/LICENSE`](skills/docx/LICENSE)). Source
  is available for audit only; any use, execution, copying,
  modification, or distribution requires prior written permission.
- **`skills/html/`** (formerly `html2md`; TASK 022 / TASK 027) is **also
  Proprietary, All Rights Reserved** — it embeds byte-identical copies of
  proprietary `docx`/`pdf` code (turndown core, `web_clean/` cluster) and
  therefore **cannot** be Apache-2.0. It has its own per-skill `LICENSE`/
  `NOTICE` mirroring the office four; the first bullet's "except the four
  office skills" should be read as "except the four office skills and `html`".

All third-party material (XSD schemas from ECMA-376 / Microsoft OSP
/ W3C, runtime dependencies, external CLI tools) is attributed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) (root, governs
both license scopes) and re-pointed from each office skill's
`NOTICE` file. When you add a new external dependency, update
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) in the same
commit. Do **not** alter or strip the per-skill `LICENSE` /
`NOTICE` files in the four office skills.

---

## 4. Reference index for agents working here

- [`README.md`](README.md) — public registry of all skills.
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — full contributor
  protocol (this file is a behavioural summary; CONTRIBUTING is the
  reference).
- [`docs/SKILL_EXECUTION_POLICY.md`](docs/SKILL_EXECUTION_POLICY.md)
  — script-first vs prompt-first; Tier definitions.
- [`docs/Manuals/office-skills_manual.md`](docs/Manuals/office-skills_manual.md)
  — practical guide to docx/xlsx/pptx/pdf.
- [`docs/refactoring-office-skills.md`](docs/refactoring-office-skills.md)
  — historical design rationale for the open-source office-skills
  architecture; do not edit, supersede via `docs/CONTRIBUTING.md`.
- [`.claude/skills/skill-creator/`](.claude/skills/skill-creator/)
  — `init_skill.py` for new skills; `validate_skill.py` for
  Gold-Standard checks.
- [`.claude/skills/skill-validator/`](.claude/skills/skill-validator/)
  — security and structural compliance scanner.
