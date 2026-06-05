# Task 019-01 [STUB+TEST]: `_venv_bootstrap.py` helper + RED→GREEN tests

> **Predecessor:** none (bootstrap task of the chain).
> **RTM:** completes [A1][A2][A5]; scaffolds [A3][A4] (wiring lands 019-02);
> completes [F1b][F1c][F1e] test surface (subprocess-level).
> **ARCH:** §2.1 FC-1, §4.2 BootstrapContext, §4.3 I-1/I-2, §5.2, §7 S-1..S-3, §12 D-A1.

## Use Case Connection
- UC-1 (re-exec), UC-3 (venv-absent friendly fail) — **real** at the helper level here.
- UC-1/A3 (module-mode / already-in-venv no-op) — **real**.

## Goal
A single **stdlib-only** helper `skills/docx/scripts/_venv_bootstrap.py` exposing
`reexec_into_venv(requires=())`, that makes `python3 scripts/X.py` behave like
`./.venv/bin/python scripts/X.py`, and fails *legibly* when `.venv` is absent. It must be
importable under **any** interpreter (no third-party imports) and **position-independent**
(resolve `.venv` from `__file__`) so the byte-identical copy is correct in every skill.

> **STATUS: ✅ DONE (2026-06-05).** Implemented + verified (8/8 unit GREEN; end-to-end
> probe under base `python3` re-execs into `scripts/.venv` and imports PIL). **As-built
> deviation from the pseudocode below:** the re-exec decision uses **`sys.prefix`**, not
> `realpath(sys.executable)` — a pyenv venv symlinks `bin/python` to the same base binary,
> so the executable realpaths are identical and the spec's guard would never fire (verified
> on this host). A loop-guard env sentinel (`_VENV_BOOTSTRAP_REEXEC`) bounds re-exec to one.
> See the as-built [`skills/docx/scripts/_venv_bootstrap.py`](../../skills/docx/scripts/_venv_bootstrap.py).

## New file — `scripts/_venv_bootstrap.py`

```python
"""Self-bootstrap a docx-skill CLI into its own scripts/.venv.

Byte-identical across the office skills (docx master → xlsx/pptx/pdf, CLAUDE.md §2).
stdlib-only so it imports under ANY interpreter; position-independent so the replicated
copy finds the CALLING skill's own .venv (never a hard-coded path). Call it as the FIRST
executable statement of a CLI entrypoint, before any third-party import.
"""
from __future__ import annotations
import importlib.util
import os
import sys


def _venv_python(start: str) -> str:
    """Absolute path to <owning scripts/>/.venv/bin/python, derived from `start`.

    `start` is the caller's __file__. scripts/*.py live directly in scripts/;
    scripts/office/*.py live one level down — walk up until a `.venv` is found,
    bounded to two levels (scripts/ and scripts/office/)."""
    here = os.path.dirname(os.path.abspath(start))
    for root in (here, os.path.dirname(here)):
        cand = os.path.join(root, ".venv", "bin", "python")
        if os.path.exists(cand):
            return cand
    # default: assume sibling scripts/.venv even if absent (for the message path)
    return os.path.join(here, ".venv", "bin", "python")


def reexec_into_venv(requires: tuple[str, ...] = (), *, _file: str | None = None) -> None:
    """Re-exec the current process under scripts/.venv if needed; else fail legibly.

    - venv exists and we are NOT it  -> os.execv into it (preserves argv + exit code).
    - venv exists and we ARE it       -> return (no-op; common case).
    - venv absent + a `requires` module unimportable -> print remediation, exit 1.
    - venv absent + all `requires` present            -> return (deps somehow present).
    The realpath compare bounds this to at most ONE re-exec (no exec loop)."""
    caller = _file or _caller_file()
    venv_py = _venv_python(caller)
    if os.path.exists(venv_py):
        if os.path.realpath(sys.executable) != os.path.realpath(venv_py):
            os.execv(venv_py, [venv_py, *sys.argv])  # replaces process; no return
        return
    # venv absent: fail legibly only if a declared dep is actually missing
    missing = [m for m in requires if importlib.util.find_spec(m) is None]
    if missing:
        scripts_dir = os.path.dirname(os.path.dirname(venv_py))  # .../scripts
        sys.stderr.write(
            f"dependencies missing ({', '.join(missing)}) — run: "
            f"bash {os.path.join(scripts_dir, 'install.sh')}\n")
        raise SystemExit(1)


def _caller_file() -> str:
    """__file__ of the module that called reexec_into_venv (one frame up)."""
    f = sys._getframe(2)
    return f.f_globals.get("__file__", __file__)
```

> Design notes:
> - `requires` is passed explicitly by each entrypoint (e.g. `("PIL",)`); `_caller_file`
>   fallback is only for safety. Entrypoints SHOULD pass `_file=__file__` for robustness —
>   document this in the wiring task (019-02) so office/*.py resolve correctly.
> - `os.execv` (not `subprocess`): no extra process, argv + exit code preserved, no shell.

## New file — `scripts/tests/test_venv_bootstrap.py` (`unittest`)

Write tests FIRST (RED), then implement until GREEN (`tdd-stub-first §1`).

1. **test_stdlib_only_importable** — `import _venv_bootstrap` succeeds; assert the module
   has no third-party imports (parse its source: only `os`, `sys`, `importlib.util`,
   `__future__`).
2. **test_venv_python_path_for_scripts** — `_venv_python(<scripts>/preview.py)` ==
   `<scripts>/.venv/bin/python`.
3. **test_venv_python_path_for_office** — `_venv_python(<scripts>/office/unpack.py)`
   resolves to `<scripts>/.venv/bin/python` (one level up).
4. **test_already_in_venv_is_noop** — with `sys.executable` == the venv python (the test
   runner IS the venv), `reexec_into_venv(("PIL",), _file=<scripts>/preview.py)` returns
   without raising and without exec (monkeypatch `os.execv` to record calls → asserts 0
   calls).
5. **test_reexec_when_wrong_interpreter** — monkeypatch `sys.executable` to a non-venv
   path and `os.execv` to a recorder; assert exactly one `execv` to the venv python with
   `argv` preserved.
6. **test_venv_absent_missing_dep_exits** — point `_file` at a temp dir with no `.venv`;
   `requires=("definitely_absent_xyz",)` → `SystemExit(1)`; stderr contains
   `run:` + `install.sh`.
7. **test_venv_absent_dep_present_returns** — temp dir, no `.venv`, `requires=("os",)`
   (present) → returns, no exit.
8. **test_import_chain_idempotent (F1e)** — a subprocess already running the venv python
   imports a chain (simulate: call `reexec_into_venv` twice with the venv as
   `sys.executable`) → no second execv, no exit (locks I-1).

## Verification
```bash
cd skills/docx && ./.venv/bin/python -m unittest -v \
  -s scripts/tests -p test_venv_bootstrap.py  ||  \
  ./.venv/bin/python scripts/tests/test_venv_bootstrap.py
```
(Adjust to the repo's existing `unittest` invocation; the suite must be GREEN.)

## Acceptance Criteria
- [ ] `scripts/_venv_bootstrap.py` exists; stdlib-only; `reexec_into_venv` + `_venv_python`
  present with the documented behaviour.
- [ ] All 8 tests GREEN under the docx `.venv`.
- [ ] No third-party import in the helper (locked by test 1).
- [ ] Helper is position-independent (tests 2/3) → byte-identity-safe for 019-02 replication.

## Notes
- **Do NOT** wire the helper into any entrypoint here — that is 019-02 (keeps this bead
  atomic; the helper is independently testable).
- The integration proof (bare `python3 preview.py` on a non-venv host) is exercised by
  019-04's install smoke-test + 019-06 dogfood; here we unit-test the decision logic with
  monkeypatched `sys.executable`/`os.execv`.
