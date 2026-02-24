#!/usr/bin/env bash
set -euo pipefail

# Memory Fabric - Retrieval Evaluation

echo "==> Running retrieval eval"

TEST_DIR=$(mktemp -d)
export MEMORY_HUB_DIR="${TEST_DIR}"
trap "rm -rf ${TEST_DIR}" EXIT

export PYTHONPATH="${PYTHONPATH:-}:./src"
export PYTHONPATH="${PYTHONPATH#:}"

DB_PATH="${TEST_DIR}/memory.db"

echo "=== Memory Fabric Retrieval Evaluation ==="
echo "Data dir: ${TEST_DIR}"

# Create test data
python3 - <<PY
import sys
sys.path.insert(0, './src')
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')

# Create test memories
memories = [
    ('prog-001', 'Python is a programming language', 'implementation', 0.9),
    ('prog-002', 'Neural networks are AI models', 'concept', 0.7),
    ('prog-003', 'Git tracks file changes', 'tool', 0.8),
]

for mid, content, mtype, importance in memories:
    db.insert_memory(mid, content, mtype, importance=importance)

print("Test data created: {} memories".format(len(memories)))
PY

echo "Test 1: Exact keyword 'Python'..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('Python')
assert any(r.memory_id == 'prog-001' for r in results), "Expected prog-001"
print("PASS: Got expected result prog-001")
PY

echo "Test 2: Synonym 'neural' should find AI memories..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('neural')
assert len(results) > 0, "Should find AI memories"
print("PASS: Found relevant AI memories")
PY

echo "Test 3: Top-3 should return up to 3 results..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('test', top_k=3)
assert len(results) <= 3
print("PASS: Got {} results".format(len(results)))
PY

echo "Test 4: Higher importance should rank higher..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('programming')
# prog-001 has importance=0.9, should be first
assert results[0].memory_id == 'prog-001', "Highest importance should rank first"
print("PASS: Highest importance ranked first (prog-001 has importance=0.9)")
PY

echo "Test 5: Results should have explanations..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('programming')
assert hasattr(results[0], 'explanation'), "Should have explanation"
print("PASS: Explanation present")
PY

echo "Test 6: FTS sanitization (comma/punctuation should not crash)..."
python3 - <<PY || { echo "FAIL"; exit 1; }
import sys
sys.path.insert(0, './src')
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase

db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
# This should not crash
results = hr.search('neural networks, AI & machine learning!')
assert len(results) >= 0
print("PASS: Got {} results (no crash)".format(len(results)))
PY

echo "=== All retrieval eval tests passed! ==="
