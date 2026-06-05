# TASK 019 — `docx` skill hardening: venv self-bootstrap + A4 page-size + install verify

## 0. Meta Information

| Field | Value |
|---|---|
| **Task ID** | 019 |
| **Slug** | `docx-skill-hardening` |
| **Source** | [`docs/docx-skill-improvement-spec.md`](docx-skill-improvement-spec.md) (postановка, 2026-06-05) |
| **Origin** | Real task «генерация интеграционной архитектуры в .docx» (Markdown+Mermaid → A4) surfaced two independent skill defects + one hardening gap |
| **Master skill** | `skills/docx` (OOXML helpers replicated to `xlsx`/`pptx`; `_errors.py`/`preview.py` to `pdf` too) |
| **Mode** | VDD (high-integrity), `script-first` skill |
| **Date** | 2026-06-05 |
| **Backlog** | registered as `docx-9` ✅ DONE in `docs/office-skills-backlog.md` |
| **Status** | ✅ **DONE** (2026-06-05) — all 6 beads shipped + verified; two `/vdd-multi` passes (PASS, 0 HIGH/CRITICAL); as-built recorded in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §11 status. Key as-built deviation: re-exec keys on `sys.prefix` (spec's `realpath(sys.executable)` is broken on a pyenv symlink-venv). |

> **Pipeline note.** This artifact is the output of the **Analysis** phase
> (`/vdd-start-feature`). Architecture is in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md);
> the atomic bead plan is produced by `/vdd-plan` into `docs/PLAN.md` +
> `docs/tasks/task-019-*.md`.

---

## 1. Problem Description

Running the docx skill end-to-end (Markdown with Mermaid → `.docx`, then re-layout
to **A4**) exposed three issues, all reproducible by an agent **without** the original
task context:

| # | Type | Prio | Essence |
|---|---|---|---|
| **A** | Bug | **P0** | Python CLIs crash with `ModuleNotFoundError`: `SKILL.md` tells the agent to call them with bare `python3`, but dependencies live only in `scripts/.venv`. On any host where `python3 ≠ .venv` (pyenv/conda/system Python), every Python script fails. The `SKILL.md` ↔ `install.sh` invocation contract is desynchronised. |
| **B** | Feature | **P1** | `md2docx.js` is hard-wired to US Letter. No way to produce **A4 / landscape / custom margins**. A4 required hand-patching `<w:pgSz>` inside the zip. Worse: `contentWidthDxa = 9360` is a Letter-derived constant — naïvely swapping only `pgSz` overflows tables/images past A4 margins. |
| **C** | Hardening | **P2** | The documented `unpack → edit → pack` A4 fallback was itself broken by (A). `install.sh` exits "successfully" while leaving an environment where the `SKILL.md` `python3 …` commands don't work — no verify step catches this. `Pillow`/`lxml` wheel-build failures on fresh interpreters (e.g. Python 3.14) could pass silently. |

**Goal:** the same scenario (md+Mermaid → docx → A4) passes with **stock skill commands,
no manual workarounds** (no zip-patching `pgSz`, no manual `pip install Pillow`, no
`source .venv/bin/activate`).

### 1.1 Verified ground-truth (anti-hallucination)

All spec line references were verified against the live code on 2026-06-05:

- `md2docx.js:40` → `const contentWidthDxa = 9360;` (Letter-derived) ✓
- `md2docx.js:82,85` → image `maxWidth = 620`, `maxHeight = 800` ✓
- `md2docx.js:278,281` → Mermaid `mmdMaxWidth = 620`, `mmdMaxHeight = 800` ✓
- `md2docx.js:345` → `size: { width: 12240, height: 15840 }` (Letter), margins `1440` ✓
- `md2docx.js:9-21` → arg loop handles only `--header`/`--footer` (no size flags) ✓
- `preview.py:38` → `from PIL import Image, ImageDraw, ImageFont` (top-level) ✓
- `office/unpack.py:29-30` → `from defusedxml import minidom` / `from lxml import etree` ✓
- `install.sh:135-143` → creates `.venv`, `pip install -r requirements.txt`; `install.sh:159-163` → usage hints use `./.venv/bin/python scripts/...` ✓
- `SKILL.md` §4/§6/§7.2/§7.3/§10 → command block + Quick Reference use bare `python3 scripts/...` ✓
- **NEW doc-bug found:** `references/docx-js-gotchas.md:27` claims *"`md2docx.js` accepts `--size letter`"* — **no such flag exists** (must be reconciled to the real `--page-size`).
- Heavy top-level dep imports crash under the wrong interpreter. Verified split (by `__main__` presence): **CLI entrypoints** = `preview.py`, `office/{unpack,pack,validate}.py`, `office_passwd.py`, `docx_accept_changes.py`, `docx_add_comment.py`, `docx_fill_template.py`, `docx_merge.py`, `docx_replace.py`; **import-only helpers (NO `__main__`)** = `_actions.py`, `_relocator.py`, `docx_anchor.py`, `office/_macros.py` (inherit the venv from their entrypoint — see A3b).
- Dogfood fixtures present: `tmp7/dogfood-integration-arch.md` + `tmp7/dogfood-integration-arch-A4.golden.docx` ✓.

### 1.2 Replication coupling (CLAUDE.md §2 — STRICT, non-negotiable)

The interpreter fix touches **shared/replicated** files, so it is **not** a docx-only
change — replication is *forced* by the byte-identity rule:

| File touched | Replication tier | Targets |
|---|---|---|
| `preview.py` | 4-skill (byte-identical) | docx → xlsx, pptx, pdf |
| `_venv_bootstrap.py` (**new** shared helper) | 4-skill (byte-identical) | docx → xlsx, pptx, pdf |
| `office/unpack.py`, `office/pack.py`, `office/validate.py`, `office/_macros.py` | 3-skill (byte-identical) | docx → xlsx, pptx |
| `office_passwd.py` | 3-skill (byte-identical) | docx → xlsx, pptx |
| `md2docx.js`, `install.sh`, `SKILL.md`, `references/docx-js-gotchas.md`, `docx_*.py` | docx-only | — |

Editing the docx master copy of any replicated file obliges a same-commit
byte-identical copy + `diff -q` verification + 4-skill `validate_skill.py` (CLAUDE.md §2).

---

## 2. Requirements Traceability Matrix (RTM)

Epics A–C map to the spec problems; D–F are the cross-cutting obligations VDD requires
to call the work *done*. MVP = the minimum that makes the headline scenario pass with
zero manual workarounds (the spec's Definition of Done §5).

### Epic A — Python venv self-bootstrap (P0 bug)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **A1** | New stdlib-only `scripts/_venv_bootstrap.py` helper | ✅ | (a) compute the skill's `.venv/bin/python` from `__file__` for both `scripts/*.py` and `scripts/office/*.py` (one level up); (b) `os.execv` re-exec preserving `sys.argv` + exit code when current interp ≠ venv python **and** venv exists; (c) no-op (return) when already running the venv interpreter (`os.path.realpath` compare) |
| **A2** | Friendly failure when `.venv` is absent | ✅ | (a) helper accepts the caller's required top-level module names; (b) when venv absent **and** a required module is not importable (`importlib.util.find_spec`), print a single clear remediation line (`run: bash scripts/install.sh`) to stderr and `sys.exit(1)`; (c) no raw `ModuleNotFoundError`/traceback reaches the user |
| **A3** | Wire bootstrap into **CLI entrypoints only** (not import-only helpers) | ✅ | (a) import + invoke the helper as the **first executable statement**, before any heavy dependency import; (b) cover the verified `__main__` entrypoints: `preview.py`, `office/{unpack,pack,validate}.py`, `office_passwd.py`, `docx_accept_changes.py`, `docx_add_comment.py`, `docx_fill_template.py`, `docx_merge.py`, `docx_replace.py`; (c) office-package entrypoints prepend `scripts/` to `sys.path` so the parent-level helper imports under bare `python3` |
| **A3b** | **Exclude pure import-only helpers from bootstrap** (M1/M2 fix) | ✅ | (a) `_actions.py`, `_relocator.py`, `docx_anchor.py`, `office/_macros.py` have **no `__main__`** (verified) — they are always imported by a CLI entrypoint that has already re-exec'd, so they inherit the venv and must **not** carry a top-level re-exec (firing `os.execv`/`sys.exit` at *import* scope is the hazard); (b) if any such helper is ever promoted to a CLI, its bootstrap goes inside `if __name__ == "__main__":`; (c) document the entrypoint-vs-helper split so the Developer does not wire re-exec into import scope |
| **A4** | Behaviour-preserving under correct interpreter | ✅ | (a) when already in venv, zero re-exec / zero extra process; (b) module-import use (`python -m office.unpack`, `from office...`) is not broken by the bootstrap; (c) idempotent — re-exec happens at most once (realpath guard prevents exec loops); (d) **import-chain safety:** an entrypoint that has re-exec'd then imports a helper (`docx_add_comment → docx_anchor`; `docx_replace → _actions → _relocator → docx_anchor`) triggers **no** second re-exec and no spurious exit |
| **A5** | Helper resolves venv relative to its own `__file__`, never a hard-coded skill path (byte-identity correctness, M3) | ✅ | (a) `.venv` path computed from `os.path.dirname(__file__)` walking up to the owning `scripts/`, so the **replicated** copy is correct in xlsx/pptx/pdf with no docx-relative assumption; (b) same source bytes work in all four skills (each finds its **own** `scripts/.venv`); (c) no skill name appears in the helper |

### Epic B — `md2docx.js` page geometry (P1 feature)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **B1** | `--page-size A4\|Letter` flag (default **Letter**) | ✅ | (a) extend arg parser (`md2docx.js:9-21`); (b) Letter = `12240×15840`, A4 = `11906×16838` (portrait twips); (c) unknown value → non-zero exit with usage message |
| **B2** | `--landscape` flag | ✅ | (a) swap width/height after size resolution; (b) reflected in `<w:pgSz w:w/w:h>` (orientation attr optional); (c) composes with `--page-size` |
| **B3** | `--margins T,R,B,L` flag | ✅ | (a) parse 4 comma-separated values in dxa; (b) optional `mm` suffix (1 mm ≈ 56.7 dxa); (c) default unchanged = `1440` all sides; (d) malformed value → non-zero exit |
| **B4** | Derive **all** geometry from actual page, not Letter constants | ✅ | (a) `contentWidthDxa = pageW − marginL − marginR` (remove hard-coded `9360`); (b) image/Mermaid `maxWidth(px) = floor(contentWidthDxa / 15)`; (c) image/Mermaid `maxHeight(px)` derived from `pageH − marginT − marginB`; (d) feed resolved `size`/`margin` into the section (`md2docx.js:343-346`); (e) table `colWidth` already derives from `contentWidthDxa` — confirm no Letter residue |
| **B5** | Output validity | ✅ | (a) A4 output `office/validate.py` → `OK`; (b) tables/images do **not** overflow A4 margins (visual via `preview.py`); (c) page count / diagram count unchanged vs Letter |

### Epic C — `install.sh` verification hardening (P2)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **C1** | Final smoke-test using the **SKILL.md-documented** command | ✅ | (a) after venv+npm install, generate a test docx (`node md2docx.js examples/fixture-simple.md …`); (b) run `preview.py` + `office/validate.py` exactly as SKILL.md prescribes; (c) on `ModuleNotFoundError`/non-zero → `die` with explicit diagnostic; (d) smoke-test artifacts written to a temp dir, cleaned up |
| **C2** | Fail loud on incomplete dependency install | ✅ | (a) verify each required wheel imports post-install (`Pillow`/`lxml`/`defusedxml`); (b) non-zero exit naming the missing package + hint, never silent continue; (c) note re: prebuilt-wheel gaps on Python 3.14. *(Promoted ⬜→✅ MVP per ARCH review — ~5 lines of bash directly addressing spec §4's Python-3.14 silent-wheel pain.)* |
| **C3** | Idempotency preserved | ✅ | (a) re-running `install.sh` after success stays exit 0; (b) smoke-test does not leave residue in the repo tree; (c) `set -euo pipefail` semantics intact |

### Epic D — Documentation reconciliation

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **D1** | `SKILL.md` invocation contract consistent with `install.sh` | ✅ | (a) resolve the `python3` vs `.venv/bin/python` desync (see OQ-2); (b) §4 Script Contract + §6 Validation Evidence + §7.2/§7.3/§7.7 + §10 Quick Reference aligned; (c) document that Python CLIs self-bootstrap into `.venv` |
| **D2** | `SKILL.md` documents the new page-size flags | ✅ | (a) §7.3 "Creating .docx from Markdown" replaces the "page size is fixed (US Letter)" paragraph; (b) §4 + §10 add `--page-size`/`--landscape`/`--margins`; (c) keep Letter-default / backward-compat statement |
| **D3** | `references/docx-js-gotchas.md` corrected | ✅ | (a) fix the false `--size letter` claim (line 27) to the real flag `--page-size`; (b) reconcile the "defaults to A4" framing with md2docx's explicit-Letter behaviour; (c) align landscape guidance with the implemented `--landscape` |

### Epic E — Cross-skill replication (CLAUDE.md §2)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **E1** | Replicate 4-skill shared files | ✅ | (a) `preview.py` + new `_venv_bootstrap.py` copied byte-identical to xlsx/pptx/pdf; (b) `diff -q` silent ×6; (c) `__pycache__` cleaned before diff |
| **E2** | Replicate 3-skill OOXML files | ✅ | (a) `office/` + `office_passwd.py` copied byte-identical to xlsx/pptx; (b) `diff -qr office` + `diff -q office_passwd.py` silent ×4; (c) docx remains the only edited master |
| **E3** | 4-skill validation gate | ✅ | (a) `validate_skill.py` exit 0 for docx/xlsx/pptx/pdf; (b) each skill's E2E/unit suite green post-replication; (c) no edit to xlsx/pptx/pdf masters of replicated files |

### Epic F — Tests & dogfooding

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **F1** | Regression tests under `scripts/tests/` | ✅ | (a) `--page-size A4` → correct `pgSz` + no table overflow (contentWidthDxa derived from A4); (b) self-bootstrap: invoking an entrypoint from a non-venv interpreter succeeds (no `ModuleNotFoundError`); (c) venv-absent → friendly remediation message, not a traceback; (d) **Letter regression**: no-flag output keeps `12240×15840` and `contentWidthDxa=9360`; (e) **import-chain idempotency** (A4d): importing a helper (`docx_anchor`/`_actions`) from an already-bootstrapped venv process triggers no second re-exec / no exit |
| **F2** | Dogfood on the real document | ✅ | (a) `md2docx.js … --page-size A4` on `tmp7/dogfood-integration-arch.md` in **one** command (no zip-patch); (b) `validate.py` `OK` + `preview.py` shows 3 Mermaid diagrams + wide tables inside A4 margins; (c) compare to `tmp7/…-A4.golden.docx`: `pgSz` match + same diagram/table count (byte-equality NOT required — Mermaid PNG is non-deterministic) |
| **F3** | Promote dogfood fixture | ⬜ | (a) copy `dogfood-integration-arch.md` → `skills/docx/examples/fixture-mermaid-a4.md`; (b) reference the golden under `scripts/tests/`; (c) wire into the regression suite |

---

## 3. Use Cases

### UC-1 — Run a Python CLI on a host where `python3 ≠ .venv` (Problem A)
- **Actors:** Agent (follows `SKILL.md`); System (the script).
- **Preconditions:** `bash scripts/install.sh` has run (`.venv` exists, fully populated); the shell's `python3` is a pyenv/conda/system interpreter **without** the skill's deps.
- **Main scenario:**
  1. Agent runs `python3 scripts/preview.py file.docx out.jpg` (exactly as `SKILL.md` says).
  2. `_venv_bootstrap` detects `sys.executable ≠ scripts/.venv/bin/python`, `.venv` exists.
  3. `os.execv` re-execs the same argv under `.venv/bin/python`.
  4. Heavy imports (`PIL`, …) resolve; the command completes.
- **Alternative scenarios:**
  - **A1 (already in venv):** `sys.executable == .venv/bin/python` → helper returns, no re-exec, no extra process.
  - **A2 (venv absent):** `.venv` missing → helper checks required modules; if absent, prints `run: bash scripts/install.sh` to stderr, `exit 1` (UC-3).
  - **A3 (module-mode):** `python -m office.unpack …` / `from office.unpack import …` → bootstrap does not break package import; no exec loop.
- **Postconditions:** identical result from `python3 scripts/X.py` and `./.venv/bin/python scripts/X.py`.
- **Acceptance:** `python3 scripts/preview.py …` and `python3 scripts/office/unpack.py …` exit 0 with no `ModuleNotFoundError` on a non-venv-`python3` host (given `.venv` exists).

### UC-2 — Generate an A4 document in one command (Problem B)
- **Actors:** Agent / user; `md2docx.js`.
- **Preconditions:** `node_modules` installed; input `.md` (may contain Mermaid + wide tables).
- **Main scenario:**
  1. `node scripts/md2docx.js in.md out.docx --page-size A4`.
  2. Resolver sets `pageW=11906, pageH=16838`, margins `1440`.
  3. `contentWidthDxa = 11906 − 2×1440 = 9026`; image/Mermaid caps derive from it.
  4. Tables (`colWidth = 9026/numCols`) and images fit within A4 content width.
  5. Section emits `<w:pgSz w:w="11906" w:h="16838"/>`.
- **Alternative scenarios:**
  - **A1 (landscape):** `--landscape` swaps to `16838×11906`.
  - **A2 (margins):** `--margins 1134,1134,1134,1134` (or `…mm`) → `contentWidthDxa` recomputed.
  - **A3 (bad value):** `--page-size A3` / malformed `--margins` → non-zero exit + usage.
- **Postconditions:** valid A4 docx; content does not overflow margins.
- **Acceptance:** `pgSz` = `11906×16838`; `validate.py` `OK`; `preview.py` shows tables within margins; B-class flags reflected in `pgSz`/`pgMar`.

### UC-3 — `.venv` missing → actionable error (Problem A edge)
- **Actors:** Agent; System.
- **Preconditions:** `.venv` not created (install.sh never run / deleted); deps absent from `python3`.
- **Main scenario:** Agent runs `python3 scripts/office/unpack.py …` → helper finds no venv, a required module unimportable → prints `dependencies missing — run: bash skills/docx/scripts/install.sh` → `exit 1`.
- **Acceptance:** stderr carries the remediation; **no** raw `ModuleNotFoundError`/traceback; exit code ≠ 0.

### UC-4 — `install.sh` proves the documented command works (Problem C)
- **Actors:** User/CI; `install.sh`.
- **Preconditions:** host tools present (node, python3); fresh or re-run.
- **Main scenario:** install venv + npm → smoke-test (`md2docx.js` → `preview.py` + `validate.py`) → all exit 0 → "All dependencies installed and verified."
- **Alternative scenarios:**
  - **A1 (broken dep):** a required wheel missing/unimportable → `die` with the package name + hint; non-zero exit.
  - **A2 (re-run):** second run stays exit 0; no repo-tree residue.
- **Acceptance:** install.sh exits 0 **only if** the SKILL.md `preview.py` command really runs; any dependency gap surfaces at install time, not first use.

### UC-5 — Dogfood: real integration-architecture doc (DoD proof)
- **Actors:** Maintainer; full toolchain.
- **Preconditions:** `tmp7/dogfood-integration-arch.md` (+ golden) present.
- **Main scenario:** `md2docx.js …/dogfood-integration-arch.md /tmp/dogfood-A4.docx --page-size A4` (one command) → confirm `pgSz` → `validate.py OK` → `preview.py --cols 2`.
- **Acceptance:** zero manual workarounds; all 3 Mermaid diagrams present & legible; wide tables (ports, availability calc, conformance matrix) inside A4 margins; `pgSz`+diagram/table counts match golden; same `.md` without `--page-size` yields Letter.

### UC-6 — Backward-compat (Letter regression)
- **Actors:** Existing consumers (incl. `docx_replace.py --insert-after`, which invokes `md2docx.js`).
- **Main scenario:** `node md2docx.js in.md out.docx` (no new flags) → **geometry-equivalent** prior behaviour: the load-bearing invariants `pgSz=12240×15840` and `contentWidthDxa=9360` are **exact**; image/Mermaid caps become the geometrically-exact 624/864 (vs old hardcoded 620/800 — a ≤4 px difference, strictly within content width, never overflowing). See ARCH §4.3 I-3.
- **Acceptance:** no-flag `pgSz` + `contentWidthDxa` byte-exact vs pre-task; image caps within ±4 px (intended geometric correction); `docx_replace.py --insert-after` E2E suite stays green.

### UC-7 — Replication integrity (CLAUDE.md §2)
- **Actors:** Developer; CI.
- **Main scenario:** after editing docx masters of replicated files, copy byte-identical to xlsx/pptx (and pdf for `preview.py`/`_venv_bootstrap.py`) → clean `__pycache__` → `diff -q`/`diff -qr` silent → `validate_skill.py` ×4 exit 0 → per-skill suites green.
- **Acceptance:** all `diff` checks silent; 4 validators exit 0; no non-docx master edited directly.

---

## 4. Acceptance Criteria (consolidated, binary)

1. **DoD-1 (B):** `node md2docx.js in.md out.docx --page-size A4` ⇒ `<w:pgSz w:w="11906" w:h="16838"/>`; `office/validate.py` ⇒ `OK`; tables/images within A4 margins (preview). *(Pass/Fail)*
2. **DoD-2 (A):** on a host where `python3 ≠ .venv`, `python3 scripts/<any>.py …` and `./.venv/bin/python scripts/<any>.py …` give the **same** result, no `ModuleNotFoundError` (given `.venv` exists). *(Pass/Fail)*
3. **DoD-3 (A edge):** `.venv` absent ⇒ clear "run install.sh" message + non-zero exit, **not** a traceback. *(Pass/Fail)*
4. **DoD-4 (D):** `SKILL.md` and `install.sh` agree on the invocation method; `docx-js-gotchas.md` no longer claims a non-existent `--size` flag. *(Pass/Fail)*
5. **DoD-5 (C):** `bash scripts/install.sh` exits 0 **only when** the documented `preview.py` smoke-test actually runs; any dependency gap fails at install. *(Pass/Fail)*
6. **DoD-6 (compat):** no-flag `md2docx.js` output is geometry-equivalent — `pgSz=12240×15840` + `contentWidthDxa=9360` **byte-exact**; image caps geometrically corrected ≤4 px (no overflow); `--landscape`/`--margins` reflected in `pgSz`/`pgMar`. *(Pass/Fail)*
7. **DoD-7 (E):** `diff -qr office` (xlsx,pptx) + `diff -q` (`_errors.py` already; `preview.py`,`_venv_bootstrap.py` ×3; `office_passwd.py` ×2) all silent; `validate_skill.py` exit 0 for docx/xlsx/pptx/pdf. *(Pass/Fail)*
8. **DoD-8 (F):** new tests cover A4-pgSz + no-overflow, self-bootstrap, venv-absent message, Letter regression; full docx E2E/unit suite green. *(Pass/Fail)*
9. **DoD-9 (dogfood):** `tmp7/dogfood-integration-arch.md` → A4 in one command, zero manual workarounds, golden `pgSz` + diagram/table-count parity. *(Pass/Fail)*

---

## 5. Out of Scope / Do-NOT-break

- **Default stays US Letter** — changing the default would break existing consumers and `docx_replace.py --insert-after`.
- Do **not** alter Mermaid/table rendering logic itself — only make their sizes derive from page geometry.
- Do **not** move deps out of `.venv` to global; do **not** change the install structure.
- Do **not** edit xlsx/pptx/pdf masters of replicated files directly — docx is the only source (CLAUDE.md §2).
- **Deferred (not this task):** wiring the *non-docx* skills' own per-skill entrypoints (`xlsx_*.py`, `pptx_*.py`, `pdf_*.py`) to call `_venv_bootstrap` (the helper lands in their `scripts/` via forced replication, and their `preview.py`/`office/*` self-bootstrap for free, but per-skill CLIs are a follow-up — see OQ-1).
- The optional `office/set_page.py` zip-patch helper (spec §3 "опционально") — **not** pursued; the `md2docx.js` flag is the chosen, superior path (the helper can't fix the already-frozen `contentWidthDxa`).

---

## 6. File-edit Map (from spec §9, verified)

| File | Locus | Action | Tier |
|---|---|---|---|
| `scripts/_venv_bootstrap.py` | new | create stdlib-only re-exec + friendly-fail helper | 4-skill |
| `scripts/md2docx.js` | 9-21, 40, 82-85, 278-281, 343-346 | add flags; derive geometry from page | docx-only |
| `scripts/preview.py` | 38 (top) | + bootstrap first line | 4-skill |
| `scripts/office/unpack.py` | 29-30 (top) | + bootstrap first line | 3-skill |
| `scripts/office/{pack,validate}.py` | top | + bootstrap (CLI entrypoints) | 3-skill |
| `scripts/office/_macros.py` | — | **no bootstrap** (import-only helper, A3b) | 3-skill |
| `scripts/office_passwd.py` | top | + bootstrap | 3-skill |
| `scripts/docx_{accept_changes,add_comment,fill_template,merge,replace}.py` | top | + bootstrap (CLI entrypoints) | docx-only |
| `scripts/_actions.py`, `_relocator.py`, `docx_anchor.py` | — | **no bootstrap** (import-only helpers, A3b) | docx-only |
| `scripts/install.sh` | 134-143, 152-163 | + smoke-test + dep-import verify | docx-only |
| `SKILL.md` | §4, §6, §7.2/§7.3/§7.7, §10 | reconcile invocation; document page-size | docx-only |
| `references/docx-js-gotchas.md` | 9-51 | fix `--size letter` → `--page-size` (line 27); reconcile "defaults to A4" heading (9-13) + landscape section (29-51) | docx-only |
| `scripts/tests/` | new | regression tests (A4, bootstrap, venv-absent, Letter) | docx-only |
| `examples/fixture-mermaid-a4.md` | new (F3) | promoted dogfood fixture | docx-only |

---

## 7. Open Questions (to be locked in Architecture; **none blocking**)

- **OQ-1 — Cross-skill entrypoint wiring scope.** Forced replication already makes
  xlsx/pptx/pdf `preview.py` and xlsx/pptx `office/*`/`office_passwd.py` self-bootstrap.
  Do we also wire each non-docx skill's *own* CLIs (`xlsx_*.py`/`pptx_*.py`/`pdf_*.py`)
  in this task? **Recommended:** defer (keeps the task docx-scoped + atomic; the helper
  is present for a fast follow-up). *Decision owner: Architect.*
- **OQ-2 — SKILL.md invocation form.** With self-bootstrap, `python3 scripts/X.py`
  works. Keep `python3` (+ a §7.2 note that scripts auto-bootstrap into `.venv`) or
  switch all examples to `./.venv/bin/python`? **Recommended:** keep `python3` (readable,
  now safe) + explicit note; leave `install.sh` hints as-is — the two no longer conflict.
- **OQ-3 — px-from-dxa factor.** Image/Mermaid `maxWidth(px)`. **Recommended:**
  `floor(contentWidthDxa / 15)` (exact: 1 dxa = 635 EMU, 1 px = 9525 EMU ⇒ px = dxa/15;
  reproduces the existing 9360 → 624 ≈ current 620 cap). Architect confirms the rounding.
- **OQ-4 — `--margins` grammar.** `T,R,B,L` dxa with optional `mm` suffix per value vs
  whole-flag. **Recommended:** per-value numeric, optional trailing `mm`, all-4 required.

**Blocking questions:** none. Sensible defaults exist for every OQ; the Architecture phase
locks them and the Architecture-Reviewer gates the choices.

---

## 8. Verification Commands (reference)

```bash
cd skills/docx && bash scripts/install.sh        # must end with smoke-test PASS (C)

# A — interpreter (host where python3 ≠ .venv)
node scripts/md2docx.js examples/fixture-simple.md /tmp/x.docx
python3 scripts/preview.py /tmp/x.docx /tmp/x.jpg            # no ModuleNotFoundError
python3 scripts/office/unpack.py /tmp/x.docx /tmp/unpacked/  # no ModuleNotFoundError

# B — A4
node scripts/md2docx.js examples/fixture-simple.md /tmp/a4.docx --page-size A4
python3 -c "import zipfile,re; print(re.findall(r'<w:pgSz[^>]*>', zipfile.ZipFile('/tmp/a4.docx').read('word/document.xml').decode()))"
# expect: <w:pgSz w:w=\"11906\" w:h=\"16838\" .../>
python3 scripts/office/validate.py /tmp/a4.docx             # OK
python3 scripts/preview.py /tmp/a4.docx /tmp/a4.jpg --cols 2

# Letter regression
node scripts/md2docx.js examples/fixture-simple.md /tmp/letter.docx
python3 -c "import zipfile,re; print(re.findall(r'<w:pgSz[^>]*>', zipfile.ZipFile('/tmp/letter.docx').read('word/document.xml').decode()))"
# expect unchanged: <w:pgSz w:w=\"12240\" w:h=\"15840\" .../>

# E — replication
find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
for s in xlsx pptx pdf; do diff -q skills/docx/scripts/preview.py skills/$s/scripts/preview.py; diff -q skills/docx/scripts/_venv_bootstrap.py skills/$s/scripts/_venv_bootstrap.py; done
for s in docx xlsx pptx pdf; do python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s; done
```
