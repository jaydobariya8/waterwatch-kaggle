#!/usr/bin/env bash
# WaterWatch — one-command local setup. Creates a venv, installs deps, and prints
# the run command. Runs fully offline; no API keys required.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "💧 WaterWatch setup"
echo "──────────────────────────────────────────────"

if [ ! -d ".venv" ]; then
  echo "→ creating virtual environment (.venv)"
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ upgrading pip"
python -m pip install --upgrade pip >/dev/null

echo "→ installing core dependencies"
pip install -r requirements.txt

if [ "${1:-}" = "--cloud" ]; then
  echo "→ installing cloud/AI extras (Gemini, MCP, Firestore)"
  pip install -r requirements-cloud.txt
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "→ created .env (optional — add GEMINI_API_KEY to enable Gemini)"
fi

echo ""
echo "✅ Done. Start WaterWatch with:"
echo ""
echo "   source .venv/bin/activate"
echo "   uvicorn waterwatch.main:app --reload --port 8080"
echo ""
echo "   then open http://localhost:8080"
echo ""
echo "   Run the eval harness:  python -m eval.run_eval"
echo "   Run the tests:         pytest -q"
