#!/usr/bin/env python3
"""Thin CLI entrypoint for the html2md skill (FC-5 shim).

Re-execs into ``scripts/.venv`` so ``python3 html2md.py …`` works on any host
(pyenv/conda/system), then delegates to the ``html2md`` package. The body lives in
the package; this shim only wires the venv bootstrap + re-exports.

``requires=("html2md",)`` is a no-op venv-absent marker: the package is always
importable via the inserted ``scripts/`` path, so when no ``.venv`` exists the CLI
still runs offline on the current interpreter; heavy deps (httpx/trafilatura/
playwright) fail legibly at their use-site instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/
import _venv_bootstrap  # noqa: E402

_venv_bootstrap.reexec_into_venv(requires=("html2md",), _file=__file__)

from html2md import main, _load_skill_env  # noqa: E402,F401
from html2md import (  # noqa: E402,F401
    BadInput,
    ConvertFailed,
    EngineNotInstalled,
    FetchFailed,
    InternalError,
    SelfOverwriteRefused,
    _AppError,
)

if __name__ == "__main__":
    _load_skill_env()  # skill-local <skill>/.env → env (encapsulation), BEFORE any flag/env read
    sys.exit(main())
