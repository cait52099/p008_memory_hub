#!/usr/bin/env bash
set -euo pipefail

# Memory Fabric - Smoke Test

echo "==> Running smoke test"

TEST_DIR=$(mktemp -d)
export MEMORY_HUB_DIR="${TEST_DIR}"
trap "rm -rf ${TEST_DIR}" EXIT

export PYTHONPATH="${PYTHONPATH:-}:./src"
export PYTHONPATH="${PYTHONPATH#:}"

echo "=== Memory Fabric Smoke Test ==="
echo "Data dir: ${TEST_DIR}"

echo "Test 1: Importing modules..."
python3 -c "from memory_hub import event_store, database, retrieval, context_assembler; from cli import commands" || { echo "FAIL: Import"; exit 1; }
echo "OK: All modules import successfully"

echo "Test 2: Event store..."
python3 -c "
from memory_hub.event_store import EventStore
es = EventStore('${TEST_DIR}')
event_id = es.append('test', {'content': 'hello'})
print(f'OK: Event store works (event_id={event_id})')
" || { echo "FAIL: Event store"; exit 1; }

echo "Test 3: Database..."
DB_PATH="${TEST_DIR}/memory.db"
python3 -c "
from memory_hub.database import MemoryDatabase
db = MemoryDatabase('${DB_PATH}')
db.insert_memory('test', 'test memory', 'general')
print('OK: Database works')
" || { echo "FAIL: Database"; exit 1; }

echo "Test 4: FTS search..."
python3 -c "
from memory_hub.database import MemoryDatabase
db = MemoryDatabase('${DB_PATH}')
results = db.search_memories_fts('test')
assert len(results) > 0
print(f'OK: FTS search found {len(results)} results')
" || { echo "FAIL: FTS search"; exit 1; }

echo "Test 5: Hybrid retrieval..."
python3 -c "
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase
db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
results = hr.search('test', top_k=5)
print(f'OK: Hybrid retrieval found {len(results)} results')
" || { echo "FAIL: Hybrid retrieval"; exit 1; }

echo "Test 6: Context assembler..."
python3 -c "
from memory_hub.context_assembler import ContextAssembler
from memory_hub.retrieval import HybridRetrieval
from memory_hub.database import MemoryDatabase
db = MemoryDatabase('${DB_PATH}')
hr = HybridRetrieval(db)
ca = ContextAssembler(hr, db)
context = ca.assemble('test', max_tokens=100)
print(f'OK: Context assembler works ({context.token_used} tokens used)')
" || { echo "FAIL: Context assembler"; exit 1; }

echo "Test 7: CLI..."
MEMORY_ID=$(python3 -m cli.commands write "test memory" --type test 2>/dev/null | grep -o '[a-f0-9]\{8\}' | head -1)
if [ -n "$MEMORY_ID" ]; then
  echo "Memory created: $MEMORY_ID"
  echo "OK: CLI works"
else
  echo "FAIL: CLI"
  exit 1
fi

echo "=== All smoke tests passed! ==="
