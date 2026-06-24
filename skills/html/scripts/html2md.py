#!/usr/bin/env python3
"""``html2md`` — the combined end-to-end command: a URL/HTML in, clean Markdown out.

The convenience one-shot built from the skill's two primitives:
``html fetch`` (download a page to HTML on disk) → ``html md`` (convert HTML → Markdown)
→ delete the intermediate HTML, leaving just ``<slug>.md`` (+ ``.reader.md``) and the
``_attachments/`` folder. Use the ``html`` launcher's ``fetch`` / ``md`` verbs directly
when you want to KEEP the intermediate HTML (e.g. to feed it to the pdf skill).

Mirrors the ``html`` launcher's bootstrap (venv re-exec), then dispatches to
:func:`html2md.combined_main` instead of the multi-verb ``main``. The internal package is
imported as ``html2md`` (the package dir takes precedence over this same-named script
file, so ``from html2md import …`` always resolves to the package, never to this file).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/
import _venv_bootstrap  # noqa: E402

_venv_bootstrap.reexec_into_venv(requires=("html2md",), _file=__file__)

from html2md import combined_main, _load_skill_env  # noqa: E402,F401

if __name__ == "__main__":
    _load_skill_env()  # skill-local <skill>/.env → env, BEFORE any flag/env read
    sys.exit(combined_main())
