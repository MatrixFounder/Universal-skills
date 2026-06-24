#!/usr/bin/env bash
# html2md E2E entrypoint (used by the office-skills CI matrix).
# Runs the full unit + e2e Python suite AND the two-master replication gate (G-1/G-2):
#   - web_clean/*.py byte-identical to the pdf master
#   - html2md_core.js byte-identical to the docx master
#   - _errors.py / _venv_bootstrap.py byte-identical to the docx master
#   - the weasyprint/playwright carriers are NOT replicated (G-2 trap)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # scripts/
ROOT="$(cd "$HERE/../../.." && pwd)"                        # repo root
cd "$HERE"
PY="./.venv/bin/python"; [ -x "$PY" ] || PY=python3
export HTML2MD_NO_DOTENV=1   # hermetic: never auto-load a developer's skill .env during tests
fail=0

echo "== html2md unit suite =="
"$PY" -m unittest discover -s html2md/tests -p 'test_*.py' || fail=1
echo "== html2md e2e suite =="
"$PY" -m unittest discover -s tests -p 'test_*.py' || fail=1

echo "== G-1 two-master replication (diff -q) =="
find "$ROOT/skills" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
for m in archives reader_mode preprocess dom_utils normalize_css; do
  diff -q "$ROOT/skills/pdf/scripts/html2pdf_lib/$m.py" "$HERE/web_clean/$m.py" || fail=1
done
diff -q "$ROOT/skills/docx/scripts/html2md_core.js" "$HERE/html2md_core.js" || fail=1
for h in _errors.py _venv_bootstrap.py; do
  diff -q "$ROOT/skills/docx/scripts/$h" "$HERE/$h" || fail=1
done

echo "== G-2 excluded weasyprint/playwright carriers must NOT be replicated =="
for c in render chrome_engine; do
  if [ -e "$HERE/web_clean/$c.py" ]; then echo "LEAK: web_clean/$c.py must not exist"; fail=1; fi
done
if [ ! -e "$HERE/web_clean/__init__.py" ]; then
  echo "missing html2md-owned web_clean/__init__.py"; fail=1
elif diff -q "$HERE/web_clean/__init__.py" "$ROOT/skills/pdf/scripts/html2pdf_lib/__init__.py" >/dev/null 2>&1; then
  echo "LEAK: web_clean/__init__.py is the pdf carrier (must be html2md-owned thin facade)"; fail=1
fi

if [ $fail -eq 0 ]; then echo "html2md test_e2e: PASS"; else echo "html2md test_e2e: FAIL"; fi
exit $fail
