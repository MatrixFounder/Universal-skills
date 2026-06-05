# Task 019-02 [LOGIC]: wire bootstrap into docx CLI entrypoints + cross-skill replicate

> **Predecessor:** 019-01 (`_venv_bootstrap.py` exists + GREEN).
> **RTM:** completes [A3][A3b][A4][E1][E2][E3]; [F1b][F1c][F1e] at the wired level.
> **ARCH:** §2.1 FC-1b, §3.2, §5.2, §9 (replication boundary), §12 D-A2/D-A5.

## Use Case Connection
- UC-1, UC-3, UC-7 (replication integrity) — **real** here.

## Goal
Add the bootstrap prelude as the **first executable statement** of every docx **CLI
entrypoint** (file with `if __name__ == "__main__"`), exclude the import-only helpers,
then **replicate** the touched shared/office masters byte-identically per CLAUDE.md §2.

## Step 1 — wire docx CLI entrypoints (10 files)

The 10 CLI entrypoints (files with `__main__`, verified): `preview.py`,
`office/{unpack,pack,validate}.py`, `office_passwd.py`, `docx_accept_changes.py`,
`docx_add_comment.py`, `docx_fill_template.py`, `docx_merge.py`, `docx_replace.py`.
**Excluded:** `_soffice.py` (subprocess helper with a diagnostic `__main__`, no heavy
top-level import, imported widely → inherits venv) + the 4 pure import-only helpers.

For `scripts/preview.py` and the `docx_*` CLIs, the prelude (top of file, before heavy
imports) is:
```python
import _venv_bootstrap; _venv_bootstrap.reexec_into_venv(requires=("PIL",), _file=__file__)
```
(scripts/ is already `sys.path[0]` when run as a script, so `import _venv_bootstrap` works
directly.) **Derivation rule for `requires`:** name the third-party module the entrypoint
needs *first* — directly or transitively (it only affects the venv-absent diagnostic; the
re-exec when venv exists is unconditional). **Verified per-file values:**
- `preview.py` → `("PIL",)` (top-level `from PIL import …` :38)
- `docx_add_comment.py` → `("docx",)` (top-level `docx`+`lxml` :94-95)
- `docx_fill_template.py` → `("docx",)` (top-level `from docx import Document` :33)
- `docx_merge.py` → `("docx",)` (top-level `docx`+`lxml` :50-51)
- `docx_replace.py` → `("lxml",)` (**no** heavy top import; pulls `lxml` transitively via
  `_actions`/`office.unpack`/`office.pack` :43,55-57)
- `docx_accept_changes.py` → `("lxml",)` (no heavy top import; pulls `lxml` transitively
  via `office._macros` :35)

For `scripts/office/{unpack,pack,validate}.py` — **new unconditional 3-line prelude at the
very top, ABOVE the existing heavy imports (`unpack.py:29-30`, etc.) and distinct from the
existing `__package__`-guarded `sys.path.insert`** (ARCH §2.1 BLOCKER fix):
```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/
import _venv_bootstrap  # noqa: E402
_venv_bootstrap.reexec_into_venv(requires=("lxml",), _file=__file__)             # then heavy imports
```
Per-file `requires`: `unpack.py` → `("defusedxml","lxml")`; `pack.py` → `("lxml",)`;
`validate.py` → `("lxml",)` (proxy for the `office.validators.*` chain). The existing
guarded `sys.path.insert` block stays as-is (it serves the `office`-package import).

For `scripts/office_passwd.py` → `("msoffcrypto",)`.

**Do NOT touch** the import-only helpers: `_actions.py`, `_relocator.py`, `docx_anchor.py`,
`office/_macros.py` (no `__main__`; they inherit the venv from their entrypoint — D-A2).

## Step 2 — replicate (CLAUDE.md §2, SAME commit)
```bash
# 4-skill: _venv_bootstrap.py + preview.py → xlsx, pptx, pdf
for s in xlsx pptx pdf; do
  cp skills/docx/scripts/_venv_bootstrap.py skills/$s/scripts/_venv_bootstrap.py
  cp skills/docx/scripts/preview.py         skills/$s/scripts/preview.py
done
# 3-skill: office/ + office_passwd.py → xlsx, pptx
for s in xlsx pptx; do
  rm -rf skills/$s/scripts/office && cp -R skills/docx/scripts/office skills/$s/scripts/office
  cp skills/docx/scripts/office_passwd.py skills/$s/scripts/office_passwd.py
done
find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```

## Step 3 — verify byte-identity (all silent)
```bash
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
for s in xlsx pptx pdf; do
  diff -q skills/docx/scripts/_venv_bootstrap.py skills/$s/scripts/_venv_bootstrap.py
  diff -q skills/docx/scripts/preview.py         skills/$s/scripts/preview.py
done
for s in xlsx pptx; do diff -q skills/docx/scripts/office_passwd.py skills/$s/scripts/office_passwd.py; done
```

## Step 4 — 4-skill validation + per-skill suites
```bash
for s in docx xlsx pptx pdf; do python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s; done
# + run each skill's E2E/unit suite (office/tests + skill tests) — must stay green
```

## Test Cases (bootstrap E2E)
1. **TC-E2E-bootstrap-reexec (F1b)** — invoke a docx CLI with a **non-venv** python3 on a
   host where `.venv` exists; assert exit 0, no `ModuleNotFoundError`. (Use the system
   `python3` if it lacks deps; else simulate via a wrapper interpreter.)
2. **TC-E2E-venv-absent (F1c)** — temporarily point at a missing `.venv` (e.g. run a copy
   in a scratch dir without `.venv`) → friendly remediation on stderr, non-zero exit, no
   traceback.
3. **TC-import-chain (F1e)** — `docx_replace.py` (entrypoint) imports `_actions →
   _relocator → docx_anchor`; run once under venv → no second re-exec / no exit.

## Acceptance Criteria
- [ ] 10 docx CLI entrypoints carry the prelude as the first executable statement; office
  entrypoints use the new top-of-file 3-line block above the heavy imports.
- [ ] Import-only helpers (`_actions`/`_relocator`/`docx_anchor`/`office/_macros`) carry
  **no** bootstrap.
- [ ] `python3 scripts/preview.py …` and `python3 scripts/office/unpack.py …` exit 0 with
  no `ModuleNotFoundError` on a non-venv-`python3` host (`.venv` present).
- [ ] All `diff`/`diff -qr` gates silent; `validate_skill.py` exit 0 ×4; every replicate-
  target skill suite green (xlsx, pptx, pdf) — bead not done until all green.
- [ ] No xlsx/pptx/pdf master of a replicated file edited directly.

## Notes
- After `os.execv` the module re-runs from the top → office prelude's `sys.path.insert`
  runs twice (harmless; second pass `proceed`-branches). Do NOT remove the second insert.
- This bead closes **Problem A** end-to-end.
