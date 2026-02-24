#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Running smoke test"
bash scripts/smoke_test.sh

echo "==> Running retrieval eval"
bash scripts/eval_retrieval.sh

echo "==> Running redaction eval"
bash scripts/eval_redaction.sh

echo "✅ All checks passed"
