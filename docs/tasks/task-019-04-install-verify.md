# Task 019-04 [LOGIC]: `install.sh` dependency-verify + smoke-test

> **Predecessor:** 019-02 (`preview.py` self-bootstrap) + 019-03 (`md2docx.js`).
> **RTM:** completes [C1][C2][C3].
> **ARCH:** §2.1 FC-3, §5.3, §12; spec §4.

## Use Case Connection
- UC-4 (install proves the documented command works), UC-4/A1 (broken dep → die),
  UC-4/A2 (re-run idempotent) — **real** here.

## Goal
Make `scripts/install.sh` exit 0 **only if** the SKILL.md-documented command really runs,
and fail loud on an incomplete dependency install — catching the spec §4 Python-3.14
silent-wheel-failure case.

## Steps (edit `scripts/install.sh`, after the npm install at `:150`)
1. **C2 — dependency-import verify.** After `pip install`, assert each required wheel
   imports in the venv:
   ```bash
   say "Verifying Python dependencies import..."
   ./.venv/bin/python - <<'PY' || die "A required Python dependency failed to import — re-run install or check the wheel build (Pillow/lxml may lack prebuilt wheels on this interpreter)."
   import importlib.util, sys          # NOT `import importlib` — the .util submodule must be imported explicitly
   missing = [m for m in ("PIL", "lxml", "defusedxml") if importlib.util.find_spec(m) is None]
   if missing:
       sys.stderr.write("MISSING: " + ", ".join(missing) + "\n")   # surface names so `die` context shows them
   sys.exit(1 if missing else 0)
   PY
   ```
   The heredoc prints the missing module names to stderr before exiting (C2b — "naming the
   missing package"); the `die` line adds the remediation hint. **Note** `import
   importlib.util` (not bare `import importlib`) — the submodule is not auto-imported and a
   bare import can `AttributeError` on fresh interpreters, the exact hosts this check guards.
2. **C1 — smoke-test with the SKILL.md command (bare `python3`).**
   ```bash
   say "Smoke-testing the documented commands..."
   SMOKE_DIR="$(mktemp -d)"; trap 'rm -rf "$SMOKE_DIR"' EXIT
   node scripts/md2docx.js examples/fixture-simple.md "$SMOKE_DIR/smoke.docx" >/dev/null \
     || die "md2docx.js smoke-test failed."
   # DELIBERATELY bare python3 — this is the proof that fix A (self-bootstrap) works:
   python3 scripts/preview.py "$SMOKE_DIR/smoke.docx" "$SMOKE_DIR/smoke.jpg" >/dev/null 2>"$SMOKE_DIR/err" \
     || { cat "$SMOKE_DIR/err" >&2; die "preview.py smoke-test failed (ModuleNotFoundError? self-bootstrap broken)."; }
   python3 scripts/office/validate.py "$SMOKE_DIR/smoke.docx" >/dev/null 2>>"$SMOKE_DIR/err" \
     || { cat "$SMOKE_DIR/err" >&2; die "office/validate.py smoke-test failed."; }
   say "Smoke-test PASS — documented python3 commands work."
   ```
   - The `SOFFICE`/poppler dependency of `preview.py`: if soffice is absent the smoke-test
     should degrade gracefully — gate the `preview.py` step on `find_soffice` success (it
     is already probed earlier as `missing_host`), OR run a lighter probe
     (`python3 scripts/office/validate.py` alone) when soffice is missing, so a host
     without LibreOffice doesn't fail install for an unrelated reason. **Decide and
     document:** validate.py (pure-python, no soffice) is the minimal mandatory smoke;
     preview.py runs only when soffice was found.
3. **C3 — idempotency.** The smoke scratch is a `mktemp -d` cleaned by `trap … EXIT`; no
   repo-tree residue; re-running `install.sh` stays exit 0. `set -euo pipefail` intact.
4. Update the trailing "Usage" block to mention `--page-size` for `md2docx.js`.

## Test Cases
1. **TC-install-smoke-pass** — on a healthy host, `bash scripts/install.sh` ends with
   `Smoke-test PASS` and exit 0; `$SMOKE_DIR` is gone afterward.
2. **TC-install-dep-missing** — simulate a missing wheel (e.g. temporarily a venv without
   Pillow) → `die` naming the dependency, non-zero exit. (Manual / documented; not a
   committed destructive test.)
3. **TC-install-rerun** — second `bash scripts/install.sh` → exit 0, no residue.

## Verification
```bash
cd skills/docx && bash scripts/install.sh   # must end with "Smoke-test PASS"; exit 0
ls "$SMOKE_DIR" 2>/dev/null || echo "scratch cleaned ✓"
```

## Acceptance Criteria
- [ ] `install.sh` runs dep-import verify + smoke-test using bare `python3` on the
  documented commands; exits 0 only when they actually run.
- [ ] Any dependency gap surfaces at install (die + name), not at first use.
- [ ] Smoke scratch is `mktemp`-isolated + trap-cleaned; re-run idempotent; `pipefail` intact.
- [ ] soffice-absent hosts do not fail install for an unrelated reason (validate.py is the
  mandatory minimal smoke; preview.py gated on soffice presence).

## Notes
- `install.sh` is **docx-only** (not replicated). The same pattern can later be ported to
  xlsx/pptx/pdf install scripts (out of scope — TASK OQ-1 / D-A6).
