#!/usr/bin/env bash
# Bootstrap the skill-auto-improve Python environment.
# Creates a per-skill .venv and installs requirements. Provider SDKs are
# imported lazily — you only need the one matching DEFAULT_PROVIDER.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "Created .venv"
fi

./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

cat <<'EOF'

skill-auto-improve installed.

Next steps:
  1. Create a .env at the skill root with your provider keys, e.g.:
       DEFAULT_PROVIDER=anthropic
       ANTHROPIC_API_KEY=sk-...
       # or: DEFAULT_PROVIDER=openai ; OPENAI_API_KEY=... ; OPENAI_BASE_URL=...
  2. Run the offline test suite:
       ./.venv/bin/python -m unittest discover -s tests
  3. Try a dataset improvement (offline evaluator):
       ./.venv/bin/python auto_improve.py \
         --artifact-path ../evals/fixtures/thin-dataset.json \
         --artifact-type dataset --workspace /tmp/ds-run --max-iterations 5
EOF
