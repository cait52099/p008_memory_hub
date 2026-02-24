#!/bin/bash
# Memory Fabric - Evaluation: Redaction
# Asserts that sensitive data is properly masked

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="/tmp/memory_hub_redact_$$"

echo "=== Memory Fabric Redaction Evaluation ==="
echo "Data dir: $DATA_DIR"

# Cleanup on exit
trap "rm -rf $DATA_DIR" EXIT

cd "$PROJECT_DIR"

# Setup test data with sensitive content
python3 -c "
from pathlib import Path
from src.memory_hub import create_event_store

# Create data directory structure
Path('$DATA_DIR').mkdir(parents=True, exist_ok=True)

es = create_event_store('$DATA_DIR/events')

# Create events with sensitive data
es.append('secret_created', {
    'api_key': 'sk-1234567890abcdef',
    'password': 'super_secret_pass',
    'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
    'message': 'This is a normal message'
})

es.append('config_saved', {
    'database_url': 'postgresql://user:password@localhost/db',
    'secret_key': 'my_secret_key_123',
    'name': 'Test Config'
})

es.append('normal_event', {
    'message': 'This is a normal event without sensitive data',
    'timestamp': '2024-01-01T00:00:00Z'
})

print('Test events created with sensitive data')
"

FAILED=0

# Test 1: Redaction masks API keys
echo ""
echo "Test 1: API keys should be redacted..."
OUTPUT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_event_store

es = create_event_store('$DATA_DIR/events')
es.export('/tmp/redacted_export.jsonl', redact=True)

with open('/tmp/redacted_export.jsonl') as f:
    content = f.read()

# Check for redacted markers
if '[REDACTED]' in content:
    print('PASS: Found [REDACTED] in output')
else:
    print('FAIL: No redaction found')
    exit(1)
")

# Test 2: Passwords masked
echo ""
echo "Test 2: Passwords should be masked..."
OUTPUT=$(python3 -c "
with open('/tmp/redacted_export.jsonl') as f:
    content = f.read()

if 'password' in content.lower() and 'super_secret_pass' not in content:
    print('PASS: Password key present but value masked')
elif 'password' not in content.lower():
    # Also acceptable - entire key-value pair removed
    print('PASS: Password not present in output')
else:
    print('FAIL: Password not properly masked')
    exit(1)
")

# Test 3: Tokens masked
echo ""
echo "Test 3: Tokens should be masked..."
OUTPUT=$(python3 -c "
with open('/tmp/redacted_export.jsonl') as f:
    content = f.read()

if 'token' in content.lower() and 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in content:
    print('PASS: Token key present but value masked')
elif 'token' not in content.lower():
    print('PASS: Token not present in output')
else:
    print('FAIL: Token not properly masked')
    exit(1)
")

# Test 4: Non-sensitive data preserved
echo ""
echo "Test 4: Non-sensitive data should be preserved..."
OUTPUT=$(python3 -c "
with open('/tmp/redacted_export.jsonl') as f:
    content = f.read()

if 'normal message' in content.lower() or 'normal event' in content.lower():
    print('PASS: Non-sensitive data preserved')
else:
    print('FAIL: Non-sensitive data was removed')
    exit(1)
")

# Test 5: Export without redaction has full data
echo ""
echo "Test 5: Non-redacted export should have full data..."
OUTPUT=$(python3 -c "
from pathlib import Path
from src.memory_hub import create_event_store

es = create_event_store('$DATA_DIR/events')
es.export('/tmp/full_export.jsonl', redact=False)

with open('/tmp/full_export.jsonl') as f:
    content = f.read()

if 'super_secret_pass' in content or 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' in content:
    print('PASS: Full data present in non-redacted export')
else:
    print('FAIL: Data missing from non-redacted export')
    exit(1)
")

# Clean up temp files
rm -f /tmp/redacted_export.jsonl /tmp/full_export.jsonl

echo ""
if [[ $FAILED -eq 0 ]]; then
    echo "=== All redaction eval tests passed! ==="
    exit 0
else
    echo "=== Some tests failed ==="
    exit 1
fi
