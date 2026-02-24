#!/bin/bash
# Memory Fabric - Smoke Test
# Verifies core functionality works

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="/tmp/memory_hub_test_$$"

echo "=== Memory Fabric Smoke Test ==="
echo "Data dir: $DATA_DIR"

# Cleanup on exit
trap "rm -rf $DATA_DIR" EXIT

cd "$PROJECT_DIR"

# Test 1: Import modules
echo ""
echo "Test 1: Importing modules..."
python3 -c "
from src.memory_hub import EventStore, MemoryDatabase, HybridRetrieval, ContextAssembler
from src.memory_hub import create_event_store, create_database
print('OK: All modules import successfully')
"

# Test 2: Event store
echo ""
echo "Test 2: Event store..."
python3 -c "
import tempfile
from pathlib import Path
from src.memory_hub import create_event_store

es = create_event_store('$DATA_DIR/events')
event_id = es.append('test_event', {'message': 'hello'})
assert event_id, 'Event ID should be returned'
count = es.count()
assert count == 1, f'Expected 1 event, got {count}'
print(f'OK: Event store works (event_id={event_id})')
"

# Test 3: Database
echo ""
echo "Test 3: Database..."
python3 -c "
import tempfile
from pathlib import Path
from src.memory_hub import create_database

db = create_database('$DATA_DIR/test.db')
mem_id = db.insert_memory('test-001', 'Test memory content', 'general', source='test')
assert mem_id, 'Memory ID should be returned'
mem = db.get_memory('test-001')
assert mem, 'Memory should be retrievable'
assert mem['content'] == 'Test memory content', 'Content should match'
print('OK: Database works')
db.close()
"

# Test 4: FTS search
echo ""
echo "Test 4: FTS search..."
python3 -c "
from pathlib import Path
from src.memory_hub import create_database

db = create_database('$DATA_DIR/test.db')
# Insert multiple memories
db.insert_memory('fts-001', 'Python is a great programming language', 'general')
db.insert_memory('fts-002', 'JavaScript runs in the browser', 'general')
db.insert_memory('fts-003', 'Rust is systems programming', 'general')

results = db.search_memories_fts('Python', limit=10)
assert len(results) >= 1, 'Should find Python'
print(f'OK: FTS search found {len(results)} results')
db.close()
"

# Test 5: Hybrid retrieval
echo ""
echo "Test 5: Hybrid retrieval..."
python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
db.insert_memory('hybrid-001', 'Machine learning is AI', 'general', importance=0.9)
db.insert_memory('hybrid-002', 'Deep learning is ML', 'general', importance=0.8)

retrieval = HybridRetrieval(db)
results = retrieval.search('learning', top_k=5)
assert len(results) > 0, 'Should find results'
print(f'OK: Hybrid retrieval found {len(results)} results')
print(f'    Top result: {results[0].memory_id} score={results[0].score:.2f}')
db.close()
"

# Test 6: Context assembler
echo ""
echo "Test 6: Context assembler..."
python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval, ContextAssembler

db = create_database('$DATA_DIR/test.db')
db.insert_memory('ctx-001', 'The architecture uses event sourcing', 'architecture', importance=0.9)
db.insert_memory('ctx-002', 'Decisions are recorded in decision log', 'decision', importance=0.8)

retrieval = HybridRetrieval(db)
assembler = ContextAssembler(retrieval, db)
pack = assembler.assemble('architecture', max_tokens=1000)

assert pack.query == 'architecture', 'Query should match'
assert pack.token_budget == 1000, 'Token budget should match'
assert len(pack.memories) > 0, 'Should have memories'
print(f'OK: Context assembler works ({pack.token_used} tokens used)')
db.close()
"

# Test 7: CLI
echo ""
echo "Test 7: CLI..."
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"
python3 -m cli.commands --data-dir "$DATA_DIR" write "CLI test memory" --type test
python3 -m cli.commands --data-dir "$DATA_DIR" search "CLI" --json | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert len(data) > 0, 'Should find results'
print('OK: CLI works')
"

echo ""
echo "=== All smoke tests passed! ==="
