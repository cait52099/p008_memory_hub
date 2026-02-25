#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Running all tests"

bash scripts/smoke_test.sh
bash scripts/eval_retrieval.sh
bash scripts/eval_redaction.sh

echo "==> Running regression tests"
python3 tests/test_project_override.py

echo "✅ All checks passed"
