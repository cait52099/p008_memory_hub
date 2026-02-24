#!/bin/bash
# Memory Fabric - Evaluation: Retrieval Quality
# Asserts that top-K retrieval returns relevant results

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="/tmp/memory_hub_eval_$$"

echo "=== Memory Fabric Retrieval Evaluation ==="
echo "Data dir: $DATA_DIR"

# Cleanup on exit
trap "rm -rf $DATA_DIR" EXIT

cd "$PROJECT_DIR"

# Setup test data
python3 -c "
from pathlib import Path
from src.memory_hub import create_database, create_event_store

# Create data directory structure
Path('$DATA_DIR').mkdir(parents=True, exist_ok=True)

db = create_database('$DATA_DIR/test.db')
es = create_event_store('$DATA_DIR/events')

# Insert test memories with known relevance
# Category: programming
db.insert_memory('prog-001', 'Python is a high-level programming language', 'general', importance=0.9)
db.insert_memory('prog-002', 'JavaScript runs in browsers and Node.js', 'general', importance=0.8)
db.insert_memory('prog-003', 'Rust is a systems programming language', 'general', importance=0.7)

# Category: AI/ML
db.insert_memory('ai-001', 'Machine learning is a subset of artificial intelligence', 'general', importance=0.9)
db.insert_memory('ai-002', 'Neural networks are inspired by biological brains', 'general', importance=0.8)
db.insert_memory('ai-003', 'Deep learning uses multi-layer neural networks', 'general', importance=0.7)

# Category: database
db.insert_memory('db-001', 'SQL databases use structured query language', 'general', importance=0.8)
db.insert_memory('db-002', 'NoSQL databases are non-relational', 'general', importance=0.7)

print('Test data created: 8 memories')
db.close()
"

FAILED=0

# Test 1: Exact keyword match
echo ""
echo "Test 1: Exact keyword 'Python'..."
RESULT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)
results = retrieval.search('Python', top_k=3)
print(results[0].memory_id if results else 'none')
db.close()
")

if [[ "$RESULT" == "prog-001" ]]; then
    echo "PASS: Got expected result prog-001"
else
    echo "FAIL: Expected prog-001, got $RESULT"
    FAILED=1
fi

# Test 2: Synonym match (should still find relevant)
echo ""
echo "Test 2: Synonym 'neural' should find AI memories..."
RESULT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)
results = retrieval.search('neural', top_k=3)
found = [r.memory_id for r in results]
print(','.join(found) if found else 'none')
db.close()
")

if [[ "$RESULT" == *"ai-002"* ]] || [[ "$RESULT" == *"ai-003"* ]]; then
    echo "PASS: Found relevant AI memories"
else
    echo "FAIL: Did not find expected AI memories, got: $RESULT"
    FAILED=1
fi

# Test 3: Top-K should return multiple results
echo ""
echo "Test 3: Top-3 should return up to 3 results..."
COUNT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)
results = retrieval.search('programming', top_k=3)
print(len(results))
db.close()
")

if [[ "$COUNT" -ge 2 ]]; then
    echo "PASS: Got $COUNT results"
else
    echo "FAIL: Expected at least 2 results, got $COUNT"
    FAILED=1
fi

# Test 4: Importance affects ranking
echo ""
echo "Test 4: Higher importance should rank higher..."
RESULT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)
results = retrieval.search('language', top_k=5)
print(results[0].memory_id if results else 'none')
db.close()
")

if [[ "$RESULT" == "prog-001" ]]; then
    echo "PASS: Highest importance ranked first (prog-001 has importance=0.9)"
else
    echo "FAIL: Expected prog-001, got $RESULT"
    FAILED=1
fi

# Test 5: Score explanation present
echo ""
echo "Test 5: Results should have explanations..."
python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)
results = retrieval.search('test', top_k=1)

if results and results[0].explanation:
    print('PASS: Explanation present')
else:
    print('FAIL: No explanation')
    exit(1)
db.close()
" || FAILED=1

# Test 6: FTS query sanitization (no crash on punctuation)
echo ""
echo "Test 6: FTS sanitization (comma/punctuation should not crash)..."
python3 -c "
from pathlib import Path
from src.memory_hub import create_database, HybridRetrieval

db = create_database('$DATA_DIR/test.db')
retrieval = HybridRetrieval(db)

# This should NOT crash even with punctuation
results = retrieval.search('hello, do you see my project?', top_k=3)
print(f'PASS: Got {len(results)} results (no crash)')
db.close()
" || FAILED=1

echo ""
if [[ $FAILED -eq 0 ]]; then
    echo "=== All retrieval eval tests passed! ==="
    exit 0
else
    echo "=== Some tests failed ==="
    exit 1
fi
