#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Running all tests"

bash scripts/smoke_test.sh
bash scripts/eval_retrieval.sh
bash scripts/eval_redaction.sh

echo "==> Running regression tests"
python3 tests/test_project_override.py

echo "==> Running episode tests"
PYTHONPATH=./src:${PYTHONPATH:-} python3 -m pytest tests/test_episode.py -v

echo "==> Running redaction tests"
PYTHONPATH=./src:${PYTHONPATH:-} python3 -m pytest tests/test_redaction.py -v

echo "✅ All checks passed"
