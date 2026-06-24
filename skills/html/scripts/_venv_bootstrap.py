"""Self-bootstrap a docx-skill CLI into its own ``scripts/.venv``.

Problem this solves
-------------------
``SKILL.md`` tells the agent to run the Python CLIs as ``python3 scripts/X.py``,
but the dependencies live in ``scripts/.venv``. On any host where ``python3`` is
not that venv (pyenv, conda, a bare system Python), every CLI dies with
``ModuleNotFoundError``. This helper makes ``python3 scripts/X.py`` behave like
``./.venv/bin/python scripts/X.py`` by re-execing the process into the venv, and
fails *legibly* ("run: bash …/install.sh") when the venv is absent.

Design contract
---------------
* **stdlib-only** — it must import under *any* interpreter, before the heavy
  third-party imports it is protecting. No ``PIL`` / ``lxml`` / ``docx`` here.
* **position-independent** — the venv is resolved from the caller's ``__file__``,
  never a hard-coded path or skill name, so the **byte-identical** copy
  replicated to ``xlsx`` / ``pptx`` / ``pdf`` (CLAUDE.md §2) finds *that* skill's
  own ``scripts/.venv``.
* **``sys.prefix``, not ``realpath(sys.executable)``** — a venv's ``bin/python``
  is frequently a *symlink to the same base binary* (e.g. pyenv:
  ``.venv/bin/python -> …/pyenv/3.14.4/bin/python3``), so comparing the resolved
  executable paths reports a false "already in venv" and the re-exec never fires.
  ``sys.prefix`` is the venv root only when the venv interpreter is actually
  running, so it is the correct discriminator.

Usage (first executable statement of a CLI entrypoint, before heavy imports)::

    import _venv_bootstrap
    _venv_bootstrap.reexec_into_venv(requires=("PIL",), _file=__file__)

``requires`` names the third-party module the entrypoint needs first (directly or
transitively); it only shapes the venv-absent diagnostic — the re-exec when the
venv exists is unconditional.
"""

from __future__ import annotations

import importlib.util
import os
import sys

# Loop-guard sentinel: set just before os.execv so a pathological venv (e.g. a
# tree with .venv/bin/python but no working pyvenv.cfg, which would leave
# sys.prefix unchanged) re-execs at most once instead of forever. It is *consumed*
# (popped from os.environ) on entry so it never leaks to child processes — the guard
# is per-process, not global; a Python-of-Python child must bootstrap itself afresh.
_REEXEC_FLAG = "_VENV_BOOTSTRAP_REEXEC"


def _scripts_root(start: str) -> str:
    """Return the skill's ``scripts/`` dir (holds ``.venv`` and ``install.sh``).

    Resolves from the caller's ``__file__`` and handles both layouts:
    ``scripts/*.py`` (the dir itself) and ``scripts/office/*.py`` (one level up).
    Probes for ``.venv/bin/python`` or the committed ``install.sh`` at each level.
    """
    here = os.path.dirname(os.path.abspath(start))
    for root in (here, os.path.dirname(here)):
        if (os.path.exists(os.path.join(root, ".venv", "bin", "python"))
                or os.path.isfile(os.path.join(root, "install.sh"))):
            return root
    return here


def reexec_into_venv(requires: tuple[str, ...] = (), *, _file: str | None = None) -> None:
    """Re-exec into ``scripts/.venv`` if needed; otherwise fail legibly.

    Behaviour:

    * venv exists and we are **not** running it -> ``os.execv`` into it
      (preserves ``sys.argv`` and the eventual exit code; no return).
    * venv exists and we **are** it (``sys.prefix`` == the venv) -> return.
    * venv absent and a ``requires`` module is unimportable -> print a one-line
      remediation to stderr and ``raise SystemExit(1)``.
    * venv absent but all ``requires`` present -> return (deps already available).
    """
    # Consume the loop-guard sentinel: read it AND remove it from os.environ in one step,
    # so a correctly-bootstrapped process does not propagate it to its children (SEC-1).
    already_reexeced = os.environ.pop(_REEXEC_FLAG, None) == "1"
    root = _scripts_root(_file if _file is not None else _caller_file())
    venv_py = os.path.join(root, ".venv", "bin", "python")

    if os.path.exists(venv_py):
        venv_root = os.path.join(root, ".venv")
        in_venv = os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
        if not in_venv and not already_reexeced:
            os.environ[_REEXEC_FLAG] = "1"
            os.execv(venv_py, [venv_py, *sys.argv])  # replaces the process image
        return

    missing = [m for m in requires if importlib.util.find_spec(m) is None]
    if missing:
        sys.stderr.write(
            "dependencies missing ({}) — run: bash {}\n".format(
                ", ".join(missing), os.path.join(root, "install.sh")))
        raise SystemExit(1)


def _caller_file() -> str:
    """``__file__`` of the caller of ``reexec_into_venv`` (frame 2), or this module.

    Entrypoints SHOULD pass ``_file=__file__`` explicitly (more robust); this
    frame-walk fallback exists only so a bare ``reexec_into_venv()`` still
    resolves a sensible root.
    """
    try:
        return sys._getframe(2).f_globals.get("__file__", __file__)
    except Exception:
        return __file__
